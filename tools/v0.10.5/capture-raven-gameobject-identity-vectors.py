#!/usr/bin/env python3
"""Passively capture GoW's raw GameObject save-identity vectors for three known Ravens.

Version-locked, read-only research probe for the supported God of War PC build.

The native save encoder at RVA 0x549481 resolves a GameObject and calls its
virtual identity method at the proven call site near RVA 0x5495C9. Immediately
after that call, the encoder owns the exact count x 16-byte vector that it then
hashes into the serialized object_hash.

This probe attaches as a Windows debugger, installs a one-byte INT3 *after* the
virtual call, and inspects the stopped thread's stack/pointer candidates. It
accepts a vector only when GoW's exact byte hash equals one of the three frozen
Raven object hashes. The original instruction byte is restored before detach.

It does not change save/progression/quest/marker state and does not write game
files. The only process-code modification is the temporary software breakpoint,
which is restored before exit.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_CALL_RVA = 0x5495C9
COUNT_STACK_OFFSET = 0x1C0
STACK_SCAN_BYTES = 0x300
MAX_IDENTITY_ELEMENTS = 12

KNOWN = {
    0x165CD520758061E5: "raven_642d0d164af0a5d4076e77933c549a5d",
    0xADB72E5C5003A8A0: "raven_c945cb53465b58decfcbd4a221cb5326",
    0x98BE1707BA2D65A9: "raven_e32f7bab42fd7298890f6aa56a734562",
}

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
THREAD_GET_CONTEXT = 0x0008
THREAD_SET_CONTEXT = 0x0010
THREAD_QUERY_INFORMATION = 0x0040
PAGE_EXECUTE_READWRITE = 0x40
INVALID_HANDLE_VALUE = C.c_void_p(-1).value
MAX_PATH = 260

EXCEPTION_DEBUG_EVENT = 1
EXCEPTION_BREAKPOINT = 0x80000003
EXCEPTION_SINGLE_STEP = 0x80000004
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

CONTEXT_AMD64 = 0x00100000
CONTEXT_CONTROL = CONTEXT_AMD64 | 0x00000001
CONTEXT_INTEGER = CONTEXT_AMD64 | 0x00000002
CONTEXT_FLAGS = CONTEXT_CONTROL | CONTEXT_INTEGER
CONTEXT_SIZE = 0x4D0
CTX_FLAGS_OFFSET = 0x30
CTX_EFLAGS_OFFSET = 0x44
CTX_RSP_OFFSET = 0x98
CTX_RIP_OFFSET = 0xF8
TRAP_FLAG = 0x100

MASK64 = 0xFFFFFFFFFFFFFFFF


class PROCESSENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
        ("th32DefaultHeapID", C.c_size_t), ("th32ModuleID", W.DWORD),
        ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
        ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD),
        ("szExeFile", W.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD),
        ("GlblcntUsage", W.DWORD), ("ProccntUsage", W.DWORD),
        ("modBaseAddr", C.POINTER(C.c_ubyte)), ("modBaseSize", W.DWORD),
        ("hModule", W.HMODULE), ("szModule", W.WCHAR * 256),
        ("szExePath", W.WCHAR * MAX_PATH),
    ]


def configure_kernel32():
    k32 = C.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    k32.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    k32.Process32FirstW.restype = W.BOOL
    k32.Process32NextW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.restype = W.BOOL
    k32.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
    k32.Module32FirstW.restype = W.BOOL
    k32.Module32NextW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
    k32.Module32NextW.restype = W.BOOL
    k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k32.OpenProcess.restype = W.HANDLE
    k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k32.OpenThread.restype = W.HANDLE
    k32.ReadProcessMemory.argtypes = [W.HANDLE, W.LPCVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)]
    k32.ReadProcessMemory.restype = W.BOOL
    k32.WriteProcessMemory.argtypes = [W.HANDLE, W.LPVOID, W.LPCVOID, C.c_size_t, C.POINTER(C.c_size_t)]
    k32.WriteProcessMemory.restype = W.BOOL
    k32.VirtualProtectEx.argtypes = [W.HANDLE, W.LPVOID, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)]
    k32.VirtualProtectEx.restype = W.BOOL
    k32.FlushInstructionCache.argtypes = [W.HANDLE, W.LPCVOID, C.c_size_t]
    k32.FlushInstructionCache.restype = W.BOOL
    k32.DebugActiveProcess.argtypes = [W.DWORD]
    k32.DebugActiveProcess.restype = W.BOOL
    k32.DebugActiveProcessStop.argtypes = [W.DWORD]
    k32.DebugActiveProcessStop.restype = W.BOOL
    k32.DebugSetProcessKillOnExit.argtypes = [W.BOOL]
    k32.DebugSetProcessKillOnExit.restype = W.BOOL
    k32.WaitForDebugEvent.argtypes = [W.LPVOID, W.DWORD]
    k32.WaitForDebugEvent.restype = W.BOOL
    k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
    k32.ContinueDebugEvent.restype = W.BOOL
    k32.GetThreadContext.argtypes = [W.HANDLE, W.LPVOID]
    k32.GetThreadContext.restype = W.BOOL
    k32.SetThreadContext.argtypes = [W.HANDLE, W.LPVOID]
    k32.SetThreadContext.restype = W.BOOL
    k32.CloseHandle.argtypes = [W.HANDLE]
    k32.CloseHandle.restype = W.BOOL
    return k32


def winerr(prefix: str) -> RuntimeError:
    code = C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")


def close_handle(k32, handle) -> None:
    if handle and int(C.cast(handle, C.c_void_p).value or 0) not in (0, INVALID_HANDLE_VALUE):
        k32.CloseHandle(handle)


def find_process(k32, exe_name: str) -> int:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("CreateToolhelp32Snapshot(processes) failed")
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = C.sizeof(pe)
        ok = k32.Process32FirstW(snap, C.byref(pe))
        while ok:
            if pe.szExeFile.lower() == exe_name.lower():
                return int(pe.th32ProcessID)
            ok = k32.Process32NextW(snap, C.byref(pe))
    finally:
        close_handle(k32, snap)
    raise RuntimeError(f"{exe_name} is not running")


def get_main_module(k32, pid: int, exe_name: str) -> tuple[int, str]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("CreateToolhelp32Snapshot(modules) failed")
    try:
        me = MODULEENTRY32W()
        me.dwSize = C.sizeof(me)
        ok = k32.Module32FirstW(snap, C.byref(me))
        while ok:
            if me.szModule.lower() == exe_name.lower():
                base = C.cast(me.modBaseAddr, C.c_void_p).value
                if not base:
                    raise RuntimeError("GoW.exe module base resolved to NULL")
                return int(base), str(me.szExePath)
            ok = k32.Module32NextW(snap, C.byref(me))
    finally:
        close_handle(k32, snap)
    raise RuntimeError(f"could not find {exe_name} module in PID {pid}")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_mem(k32, process, address: int, size: int) -> bytes:
    buf = (C.c_ubyte * size)()
    done = C.c_size_t()
    if not k32.ReadProcessMemory(process, C.c_void_p(address), buf, size, C.byref(done)):
        raise winerr(f"ReadProcessMemory(0x{address:X}, {size}) failed")
    if done.value != size:
        raise RuntimeError(f"short ReadProcessMemory at 0x{address:X}: {done.value}/{size}")
    return bytes(buf)


def safe_read_mem(k32, process, address: int, size: int) -> bytes | None:
    try:
        return read_mem(k32, process, address, size)
    except Exception:
        return None


def write_mem(k32, process, address: int, data: bytes) -> None:
    buf = C.create_string_buffer(data)
    done = C.c_size_t()
    if not k32.WriteProcessMemory(process, C.c_void_p(address), buf, len(data), C.byref(done)):
        raise winerr(f"WriteProcessMemory(0x{address:X}, {len(data)}) failed")
    if done.value != len(data):
        raise RuntimeError(f"short WriteProcessMemory at 0x{address:X}: {done.value}/{len(data)}")


def patch_byte(k32, process, address: int, value: int) -> None:
    old = W.DWORD()
    if not k32.VirtualProtectEx(process, C.c_void_p(address), 1, PAGE_EXECUTE_READWRITE, C.byref(old)):
        raise winerr(f"VirtualProtectEx(0x{address:X}) failed")
    try:
        write_mem(k32, process, address, bytes([value]))
        if not k32.FlushInstructionCache(process, C.c_void_p(address), 1):
            raise winerr("FlushInstructionCache failed")
    finally:
        tmp = W.DWORD()
        k32.VirtualProtectEx(process, C.c_void_p(address), 1, old.value, C.byref(tmp))


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_MEM
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_MEM


def locate_post_identity_call(exe_path: str, module_base: int) -> dict:
    data = Path(exe_path).read_bytes()

    # Reuse the lightweight PE reader already checked into v0.10.5.
    import importlib.util
    helper = Path(__file__).with_name("analyze-gameobject-token-resolver.py")
    spec = importlib.util.spec_from_file_location("gow_token_resolver_pe", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load PE helper: {helper}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pe = mod.PE(data)

    off = pe.rva_to_file(EXPECTED_CALL_RVA)
    if off is None:
        raise RuntimeError("encoder virtual-call RVA is not mapped in GoW.exe")
    blob = data[off:off + 24]

    Cs, arch, mode, op_mem = load_capstone()
    md = Cs(arch, mode)
    md.detail = True
    insns = list(md.disasm(blob, module_base + EXPECTED_CALL_RVA))
    if not insns:
        raise RuntimeError("could not disassemble encoder virtual-call site")

    first = insns[0]
    valid = False
    if first.mnemonic == "call" and first.operands and first.operands[0].type == op_mem:
        mem = first.operands[0].mem
        valid = int(mem.disp) == 0x38
    if not valid:
        rendered = "; ".join(f"0x{i.address-module_base:X}:{i.mnemonic} {i.op_str}" for i in insns[:6])
        raise RuntimeError(
            "encoder identity virtual-call signature changed at RVA "
            f"0x{EXPECTED_CALL_RVA:X}: {rendered}"
        )

    return {
        "call_rva": EXPECTED_CALL_RVA,
        "call_bytes_hex": first.bytes.hex(),
        "call_size": first.size,
        "post_call_rva": EXPECTED_CALL_RVA + first.size,
        "post_call_address": module_base + EXPECTED_CALL_RVA + first.size,
        "post_call_original_byte": blob[first.size],
        "disassembly": [
            {
                "rva": i.address - module_base,
                "bytes": i.bytes.hex(),
                "mnemonic": i.mnemonic,
                "op_str": i.op_str,
            }
            for i in insns[:8]
        ],
    }


def raw_identity_hash(data: bytes) -> int:
    value = 0
    for byte in data:
        value = ((value + byte) * 0x401) & MASK64
        value ^= value >> 6
    return value


def allocate_context_buffer():
    holder = (C.c_ubyte * (CONTEXT_SIZE + 16))()
    base = C.addressof(holder)
    address = (base + 15) & ~15
    C.memset(address, 0, CONTEXT_SIZE)
    C.c_uint32.from_address(address + CTX_FLAGS_OFFSET).value = CONTEXT_FLAGS
    return holder, address


def get_thread_context(k32, thread):
    holder, address = allocate_context_buffer()
    if not k32.GetThreadContext(thread, C.c_void_p(address)):
        raise winerr("GetThreadContext failed")
    return holder, address


def context_u64(address: int, offset: int) -> int:
    return int(C.c_uint64.from_address(address + offset).value)


def context_u32(address: int, offset: int) -> int:
    return int(C.c_uint32.from_address(address + offset).value)


def set_context_u64(address: int, offset: int, value: int) -> None:
    C.c_uint64.from_address(address + offset).value = value


def set_context_u32(address: int, offset: int, value: int) -> None:
    C.c_uint32.from_address(address + offset).value = value


def event_fields(buffer) -> tuple[int, int, int, int | None, int | None]:
    raw = bytes(buffer)
    code, pid, tid = struct.unpack_from("<III", raw, 0)
    if code != EXCEPTION_DEBUG_EVENT:
        return code, pid, tid, None, None
    exception_code = struct.unpack_from("<I", raw, 16)[0]
    exception_address = struct.unpack_from("<Q", raw, 32)[0]
    return code, pid, tid, exception_code, exception_address


def plausible_pointer(value: int) -> bool:
    return 0x10000 <= value < 0x0000800000000000


def candidate_variant_map(row: dict) -> dict[str, str]:
    out: dict[str, str] = {}

    def add_raw(label: str, raw: bytes) -> None:
        variants = {
            "raw": raw,
            "reverse": raw[::-1],
            "guid_le_fields": raw[3::-1] + raw[5:3:-1] + raw[7:5:-1] + raw[8:],
            "swap_u64": raw[8:] + raw[:8],
        }
        for name, value in variants.items():
            out[value.hex()] = f"{label}.{name}"

    native = row["native"]
    for label, key in (
        ("final", "final_record_id"),
        ("override", "override_record_id"),
        ("prototype", "prototype_id"),
        ("parent_prototype", "parent_prototype_id"),
    ):
        add_raw(label, bytes.fromhex(native[key]))

    for index, part in enumerate(row["source"].get("transform_chain", [])):
        add_raw(f"transform{index}", bytes.fromhex(part["record_id"]))

    for label, key in (("instance_guid", "instance_guid"), ("script_guid", "script_guid")):
        value = uuid.UUID(native[key])
        out[value.bytes.hex()] = f"{label}.uuid_be"
        out[value.bytes_le.hex()] = f"{label}.uuid_le_fields"
        out[value.bytes[::-1].hex()] = f"{label}.uuid_reverse"
    return out


def inspect_identity_vector(k32, process, rsp: int, target_hashes: set[int]) -> tuple[dict | None, int | None]:
    stack = safe_read_mem(k32, process, rsp, STACK_SCAN_BYTES)
    if stack is None:
        return None, None

    count_hint = None
    if COUNT_STACK_OFFSET + 4 <= len(stack):
        count_hint = struct.unpack_from("<I", stack, COUNT_STACK_OFFSET)[0]

    if not (1 <= int(count_hint or 0) <= MAX_IDENTITY_ELEMENTS):
        return None, count_hint

    count = int(count_hint)
    size = count * 16
    seen_blobs: set[bytes] = set()

    def check_blob(blob: bytes, source: dict):
        if len(blob) != size or blob in seen_blobs:
            return None
        seen_blobs.add(blob)
        value = raw_identity_hash(blob)
        if value not in target_hashes:
            return None
        return {
            "object_hash": value,
            "count": count,
            "vector_hex": blob.hex(),
            "elements_hex": [blob[i:i + 16].hex() for i in range(0, len(blob), 16)],
            "source": source,
        }

    # Likely vector object pointer first.
    preferred_pointer_offsets = [0x1B0, 0x1B8, 0x1C8, 0x1D0]
    pointer_offsets = preferred_pointer_offsets + [
        off for off in range(0, len(stack) - 7, 8) if off not in preferred_pointer_offsets
    ]
    seen_ptrs: set[int] = set()
    for off in pointer_offsets:
        if off + 8 > len(stack):
            continue
        ptr = struct.unpack_from("<Q", stack, off)[0]
        if ptr in seen_ptrs or not plausible_pointer(ptr):
            continue
        seen_ptrs.add(ptr)
        blob = safe_read_mem(k32, process, ptr, size)
        if blob is None:
            continue
        match = check_blob(blob, {
            "kind": "pointer_from_stack",
            "pointer_stack_offset_hex": f"0x{off:X}",
            "pointer_hex": f"0x{ptr:X}",
        })
        if match:
            return match, count_hint

    # Inline fallback. Step one byte because the native vector is authoritative
    # and a hash match is a cryptographically strong discriminator here.
    for off in range(0, len(stack) - size + 1):
        blob = stack[off:off + size]
        match = check_blob(blob, {
            "kind": "inline_stack",
            "stack_offset_hex": f"0x{off:X}",
            "address_hex": f"0x{rsp + off:X}",
        })
        if match:
            return match, count_hint

    return None, count_hint


def capture(output: Path, timeout_s: int, catalogue_path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("identity-vector capture is Windows-only")
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("run this tool with 64-bit Python")

    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    by_id = {row["catalogue_id"]: row for row in catalogue["ravens"]}
    for catalogue_id in KNOWN.values():
        if catalogue_id not in by_id:
            raise RuntimeError(f"catalogue no longer contains {catalogue_id}")

    k32 = configure_kernel32()
    pid = find_process(k32, "GoW.exe")
    module_base, exe_path = get_main_module(k32, pid, "GoW.exe")
    actual_sha = sha256_file(exe_path)
    if actual_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(
            f"GoW.exe build mismatch; expected {EXPECTED_EXE_SHA256}, got {actual_sha}"
        )

    call = locate_post_identity_call(exe_path, module_base)
    hook_addr = int(call["post_call_address"])
    original_byte = int(call["post_call_original_byte"])

    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise winerr(f"OpenProcess({pid}) failed")

    attached = False
    breakpoint_installed = False
    single_step_tid: int | None = None
    captured: dict[int, dict] = {}
    hit_count = 0
    count_histogram: dict[str, int] = {}

    try:
        if not k32.DebugActiveProcess(pid):
            raise winerr(
                "DebugActiveProcess failed (close other debuggers and run PowerShell as the same user as GoW)"
            )
        attached = True
        if not k32.DebugSetProcessKillOnExit(False):
            raise winerr("DebugSetProcessKillOnExit(false) failed")

        live_byte = read_mem(k32, process, hook_addr, 1)[0]
        if live_byte != original_byte:
            raise RuntimeError(
                f"post-call hook byte changed at RVA 0x{call['post_call_rva']:X}: "
                f"expected {original_byte:02x}, got {live_byte:02x}"
            )
        patch_byte(k32, process, hook_addr, 0xCC)
        breakpoint_installed = True

        print(f"GoW.exe PID={pid} base=0x{module_base:X}")
        print(
            f"Identity-vector breakpoint installed after RVA 0x{call['call_rva']:X} "
            f"at RVA 0x{call['post_call_rva']:X}."
        )
        print("Return to GoW and create a manual save/checkpoint while the VikingFuneral Ravens are in the save stream.")
        print(f"Waiting up to {timeout_s} seconds for all three frozen Raven object hashes...")
        sys.stdout.flush()

        deadline = time.monotonic() + timeout_s
        complete = False
        while time.monotonic() < deadline and not complete:
            event = (C.c_ubyte * 512)()
            if not k32.WaitForDebugEvent(C.byref(event), 250):
                continue
            code, event_pid, tid, exc_code, exc_addr = event_fields(event)
            status = DBG_CONTINUE

            try:
                if code == EXCEPTION_DEBUG_EVENT and exc_code == EXCEPTION_BREAKPOINT and exc_addr == hook_addr:
                    hit_count += 1
                    thread = k32.OpenThread(
                        THREAD_GET_CONTEXT | THREAD_SET_CONTEXT | THREAD_QUERY_INFORMATION,
                        False,
                        tid,
                    )
                    if not thread:
                        raise winerr(f"OpenThread({tid}) failed")
                    try:
                        holder, ctx = get_thread_context(k32, thread)
                        rsp = context_u64(ctx, CTX_RSP_OFFSET)
                        match, count_hint = inspect_identity_vector(
                            k32, process, rsp, set(KNOWN) - set(captured)
                        )
                        count_key = str(count_hint)
                        count_histogram[count_key] = count_histogram.get(count_key, 0) + 1

                        if match is not None:
                            obj_hash = int(match["object_hash"])
                            catalogue_id = KNOWN[obj_hash]
                            match["catalogue_id"] = catalogue_id
                            match["object_hash_hex"] = f"0x{obj_hash:016X}"
                            variants = candidate_variant_map(by_id[catalogue_id])
                            match["element_catalogue_matches"] = [
                                variants.get(element) for element in match["elements_hex"]
                            ]
                            captured[obj_hash] = match
                            print(
                                f"CAPTURED {len(captured)}/3 {catalogue_id} "
                                f"object=0x{obj_hash:016X} count={match['count']} "
                                f"elements={match['elements_hex']}"
                            )
                            sys.stdout.flush()

                        # Restore original byte and replay the interrupted instruction.
                        patch_byte(k32, process, hook_addr, original_byte)
                        breakpoint_installed = False
                        set_context_u64(ctx, CTX_RIP_OFFSET, hook_addr)

                        if len(captured) == len(KNOWN):
                            flags = context_u32(ctx, CTX_EFLAGS_OFFSET) & ~TRAP_FLAG
                            set_context_u32(ctx, CTX_EFLAGS_OFFSET, flags)
                            if not k32.SetThreadContext(thread, C.c_void_p(ctx)):
                                raise winerr("SetThreadContext(final breakpoint) failed")
                            complete = True
                        else:
                            flags = context_u32(ctx, CTX_EFLAGS_OFFSET) | TRAP_FLAG
                            set_context_u32(ctx, CTX_EFLAGS_OFFSET, flags)
                            if not k32.SetThreadContext(thread, C.c_void_p(ctx)):
                                raise winerr("SetThreadContext(breakpoint) failed")
                            single_step_tid = tid
                    finally:
                        close_handle(k32, thread)

                elif (
                    code == EXCEPTION_DEBUG_EVENT
                    and exc_code == EXCEPTION_SINGLE_STEP
                    and single_step_tid is not None
                    and tid == single_step_tid
                ):
                    thread = k32.OpenThread(
                        THREAD_GET_CONTEXT | THREAD_SET_CONTEXT | THREAD_QUERY_INFORMATION,
                        False,
                        tid,
                    )
                    if not thread:
                        raise winerr(f"OpenThread({tid}) failed on single-step")
                    try:
                        holder, ctx = get_thread_context(k32, thread)
                        flags = context_u32(ctx, CTX_EFLAGS_OFFSET) & ~TRAP_FLAG
                        set_context_u32(ctx, CTX_EFLAGS_OFFSET, flags)
                        if not k32.SetThreadContext(thread, C.c_void_p(ctx)):
                            raise winerr("SetThreadContext(single-step) failed")
                        patch_byte(k32, process, hook_addr, 0xCC)
                        breakpoint_installed = True
                        single_step_tid = None
                    finally:
                        close_handle(k32, thread)

                elif code == EXCEPTION_DEBUG_EVENT and exc_code == EXCEPTION_BREAKPOINT:
                    # DebugActiveProcess may deliver a debugger-initialization breakpoint.
                    status = DBG_CONTINUE
                elif code == EXCEPTION_DEBUG_EVENT:
                    status = DBG_EXCEPTION_NOT_HANDLED
            finally:
                if not k32.ContinueDebugEvent(event_pid, tid, status):
                    raise winerr("ContinueDebugEvent failed")

        if len(captured) != len(KNOWN):
            missing = [
                f"{catalogue_id}/0x{obj_hash:016X}"
                for obj_hash, catalogue_id in KNOWN.items()
                if obj_hash not in captured
            ]
            raise RuntimeError(
                "timed out before all three identity vectors were observed; missing "
                + ", ".join(missing)
                + ". The probe only sees GameObjects the native save encoder naturally serializes."
            )

        rows = [captured[obj_hash] for obj_hash in KNOWN]
        result = {
            "schema": "completionist-map.raven-gameobject-identity-vector.v1",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "source": "temporary debugger INT3 immediately after native GameObject identity virtual call",
            "exe": {
                "path": exe_path,
                "sha256": actual_sha,
                "pid": pid,
                "module_base_hex": f"0x{module_base:X}",
            },
            "encoder": call,
            "runtime": {
                "breakpoint_hits": hit_count,
                "identity_count_histogram": count_histogram,
                "all_three_captured": True,
            },
            "records": rows,
            "safety": {
                "read_only_game_state": True,
                "save_or_progression_written_by_probe": False,
                "game_files_written": False,
                "temporary_code_breakpoint_restored": True,
            },
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"RAVEN_IDENTITY_VECTOR_CAPTURE_COMPLETE {output}")
    finally:
        if breakpoint_installed:
            try:
                patch_byte(k32, process, hook_addr, original_byte)
                print("Identity-vector breakpoint removed; original byte restored.")
            except Exception as exc:
                print(f"WARNING: failed to restore breakpoint byte: {exc}", file=sys.stderr)
        if attached:
            if not k32.DebugActiveProcessStop(pid):
                print("WARNING: DebugActiveProcessStop failed", file=sys.stderr)
            else:
                print("Debugger detached from GoW.exe.")
        close_handle(k32, process)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--catalogue", type=Path)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args()

    catalogue = args.catalogue
    if catalogue is None:
        catalogue = Path(__file__).resolve().parents[2] / "catalogue" / "odins-ravens.json"
    try:
        capture(args.output.resolve(), args.timeout_seconds, catalogue.resolve())
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
