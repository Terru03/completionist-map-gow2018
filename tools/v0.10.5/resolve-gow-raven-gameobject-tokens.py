#!/usr/bin/env python3
"""Passively capture the three archived Raven GameObject tokens on GoW's real game thread.

This installs a tiny temporary detour at RVA 0x5493A1, immediately after the
decoder has resolved the packed token in RDX. The detour only records tokens
whose serialized input at R15 matches the known Raven registry/object hashes,
then reproduces the overwritten instructions and returns to normal game code.

The hook is removed before exit. It does not call the decoder from a synthetic
remote thread, so game-thread/TLS state remains exactly as GoW expects.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from datetime import datetime, timezone

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
HOOK_RVA = 0x5493A1
HOOK_RETURN_FLAGGED_RVA = 0x5493AF
HOOK_RETURN_NOFLAG_RVA = 0x5493F1
HOOK_ORIGINAL = bytes.fromhex("4889550041f607047446418b4711")
EXPECTED_REGISTRY_HASH = 0x4EC230253427B2B0
EXPECTED_OBJECT_HASHES = (
    0x165CD520758061E5,
    0xADB72E5C5003A8A0,
    0x98BE1707BA2D65A9,
)
TARGET_HEX = (
    "01b0b227342530c24ee561807520d55c16",
    "01b0b227342530c24ea0a803505c2eb7ad",
    "01b0b227342530c24ea9652dba0717be98",
)

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40
INVALID_HANDLE_VALUE = C.c_void_p(-1).value
MAX_PATH = 260

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

def _configure_kernel32():
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
    k32.ReadProcessMemory.argtypes = [W.HANDLE, W.LPCVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)]
    k32.ReadProcessMemory.restype = W.BOOL
    k32.WriteProcessMemory.argtypes = [W.HANDLE, W.LPVOID, W.LPCVOID, C.c_size_t, C.POINTER(C.c_size_t)]
    k32.WriteProcessMemory.restype = W.BOOL
    k32.VirtualAllocEx.argtypes = [W.HANDLE, W.LPVOID, C.c_size_t, W.DWORD, W.DWORD]
    k32.VirtualAllocEx.restype = W.LPVOID
    k32.VirtualFreeEx.argtypes = [W.HANDLE, W.LPVOID, C.c_size_t, W.DWORD]
    k32.VirtualFreeEx.restype = W.BOOL
    k32.VirtualProtectEx.argtypes = [W.HANDLE, W.LPVOID, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)]
    k32.VirtualProtectEx.restype = W.BOOL
    k32.FlushInstructionCache.argtypes = [W.HANDLE, W.LPCVOID, C.c_size_t]
    k32.FlushInstructionCache.restype = W.BOOL
    k32.CloseHandle.argtypes = [W.HANDLE]
    k32.CloseHandle.restype = W.BOOL
    return k32

def _winerr(prefix: str) -> RuntimeError:
    code = C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")

def _close(k32, handle) -> None:
    if handle and int(C.cast(handle, C.c_void_p).value or 0) not in (0, INVALID_HANDLE_VALUE):
        k32.CloseHandle(handle)

def find_process(k32, exe_name: str) -> int:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise _winerr("CreateToolhelp32Snapshot(processes) failed")
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = C.sizeof(pe)
        ok = k32.Process32FirstW(snap, C.byref(pe))
        while ok:
            if pe.szExeFile.lower() == exe_name.lower():
                return int(pe.th32ProcessID)
            ok = k32.Process32NextW(snap, C.byref(pe))
    finally:
        _close(k32, snap)
    raise RuntimeError(f"{exe_name} is not running.")

def get_main_module(k32, pid: int, exe_name: str) -> tuple[int, str]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise _winerr("CreateToolhelp32Snapshot(modules) failed")
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
        _close(k32, snap)
    raise RuntimeError(f"could not find {exe_name} module in PID {pid}")

def read_mem(k32, process, address: int, size: int) -> bytes:
    buf = (C.c_ubyte * size)()
    done = C.c_size_t()
    if not k32.ReadProcessMemory(process, C.c_void_p(address), buf, size, C.byref(done)):
        raise _winerr(f"ReadProcessMemory(0x{address:X}, {size}) failed")
    if done.value != size:
        raise RuntimeError(f"short ReadProcessMemory at 0x{address:X}: {done.value}/{size}")
    return bytes(buf)

def write_mem(k32, process, address: int, data: bytes) -> None:
    buf = C.create_string_buffer(data)
    done = C.c_size_t()
    if not k32.WriteProcessMemory(process, C.c_void_p(address), buf, len(data), C.byref(done)):
        raise _winerr(f"WriteProcessMemory(0x{address:X}, {len(data)}) failed")
    if done.value != len(data):
        raise RuntimeError(f"short WriteProcessMemory at 0x{address:X}: {done.value}/{len(data)}")

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def decode_token(token: int) -> dict[str, int | bool]:
    registry = (token >> 1) & 0xFFFF
    aux_flag = (token >> 17) & 1
    slot = (token >> 18) & 0xFFFFF
    flavour = (token >> 38) & 0x3F
    reconstructed = 1 | (registry << 1) | (slot << 18)
    return {
        "present": bool(token & 1),
        "registry": registry,
        "aux_flag": aux_flag,
        "slot": slot,
        "flavour": flavour,
        "reconstructed_raven_token": reconstructed,
        "raven_formula_match": token == reconstructed,
    }

def abs_jmp(target: int) -> bytes:
    return b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", target)

def build_hook(code_addr: int, capture_addr: int, noflag_addr: int, flagged_addr: int) -> bytes:
    """Build hook with rel32 labels, preserving RAX while matching records."""
    b = bytearray()
    labels: dict[str, int] = {}
    fixups: list[tuple[int, str]] = []

    def label(name: str):
        labels[name] = len(b)

    def jcc(op2: int, name: str):
        b.extend((0x0F, op2))
        fixups.append((len(b), name))
        b.extend(b"\x00\x00\x00\x00")

    def jmp(name: str):
        b.append(0xE9)
        fixups.append((len(b), name))
        b.extend(b"\x00\x00\x00\x00")

    b.append(0x50)
    b.extend(b"\x41\x80\x3F\x01")
    jcc(0x85, "done_capture")
    b.extend(b"\x48\xB8" + struct.pack("<Q", EXPECTED_REGISTRY_HASH))
    b.extend(b"\x49\x39\x47\x01")
    jcc(0x85, "done_capture")

    for i, obj in enumerate(EXPECTED_OBJECT_HASHES):
        b.extend(b"\x48\xB8" + struct.pack("<Q", obj))
        b.extend(b"\x49\x39\x47\x09")
        if i < len(EXPECTED_OBJECT_HASHES) - 1:
            jcc(0x85, f"obj_{i+1}")
        else:
            jcc(0x85, "done_capture")
        b.extend(b"\x48\xB8" + struct.pack("<Q", capture_addr + i * 16))
        b.extend(b"\x48\x89\x10")
        b.extend(b"\x48\xC7\x40\x08\x01\x00\x00\x00")
        jmp("done_capture")
        if i < len(EXPECTED_OBJECT_HASHES) - 1:
            label(f"obj_{i+1}")

    label("done_capture")
    b.append(0x58)
    b.extend(b"\x48\x89\x55\x00")
    b.extend(b"\x41\xF6\x07\x04")
    jcc(0x85, "flagged")
    b.extend(abs_jmp(noflag_addr))
    label("flagged")
    b.extend(b"\x41\x8B\x47\x11")
    b.extend(abs_jmp(flagged_addr))

    for pos, name in fixups:
        if name not in labels:
            raise AssertionError(f"undefined hook label {name}")
        src_after = code_addr + pos + 4
        dst = code_addr + labels[name]
        rel = dst - src_after
        if not -(1 << 31) <= rel < (1 << 31):
            raise AssertionError("hook rel32 out of range")
        b[pos:pos+4] = struct.pack("<i", rel)
    return bytes(b)

def install_patch(k32, process, address: int, patch: bytes) -> int:
    old = W.DWORD()
    if not k32.VirtualProtectEx(process, C.c_void_p(address), len(patch), PAGE_EXECUTE_READWRITE, C.byref(old)):
        raise _winerr(f"VirtualProtectEx(0x{address:X}) failed")
    try:
        write_mem(k32, process, address, patch)
        if not k32.FlushInstructionCache(process, C.c_void_p(address), len(patch)):
            raise _winerr("FlushInstructionCache failed")
    finally:
        tmp = W.DWORD()
        k32.VirtualProtectEx(process, C.c_void_p(address), len(patch), old.value, C.byref(tmp))
    return int(old.value)

def capture(output: Path, timeout_s: int) -> None:
    if os.name != "nt":
        raise RuntimeError("runtime capture is Windows-only")
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("run this tool with 64-bit Python")

    k32 = _configure_kernel32()
    pid = find_process(k32, "GoW.exe")
    module_base, exe_path = get_main_module(k32, pid, "GoW.exe")
    actual_sha = sha256_file(exe_path)
    if actual_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(
            "GoW.exe build mismatch; refusing hook. "
            f"expected sha256={EXPECTED_EXE_SHA256}, got {actual_sha} ({exe_path})"
        )

    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise _winerr(f"OpenProcess({pid}) failed")

    remote = None
    patch_installed = False
    hook_addr = module_base + HOOK_RVA
    try:
        original = read_mem(k32, process, hook_addr, len(HOOK_ORIGINAL))
        if original != HOOK_ORIGINAL:
            raise RuntimeError(
                f"hook-site signature mismatch at RVA 0x{HOOK_RVA:X}: "
                f"expected {HOOK_ORIGINAL.hex()}, got {original.hex()}"
            )

        remote = k32.VirtualAllocEx(process, None, 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
        if not remote:
            raise _winerr("VirtualAllocEx hook page failed")
        remote_base = int(C.cast(remote, C.c_void_p).value)
        capture_addr = remote_base
        code_addr = remote_base + 0x100
        write_mem(k32, process, capture_addr, b"\x00" * 48)

        hook = build_hook(
            code_addr=code_addr,
            capture_addr=capture_addr,
            noflag_addr=module_base + HOOK_RETURN_NOFLAG_RVA,
            flagged_addr=module_base + HOOK_RETURN_FLAGGED_RVA,
        )
        write_mem(k32, process, code_addr, hook)
        k32.FlushInstructionCache(process, C.c_void_p(code_addr), len(hook))

        patch = abs_jmp(code_addr)
        assert len(patch) == len(HOOK_ORIGINAL) == 14
        install_patch(k32, process, hook_addr, patch)
        patch_installed = True

        print(f"GoW.exe PID={pid} base=0x{module_base:X}")
        print(f"Passive Raven hook installed at RVA 0x{HOOK_RVA:X}.")
        print("NOW return to GoW and load/reload the Raven evidence save (or Restart Checkpoint if that reloads it).")
        print(f"Waiting up to {timeout_s} seconds for all 3 exact Raven records...")
        sys.stdout.flush()

        deadline = time.monotonic() + timeout_s
        last_seen = (0, 0, 0)
        vals = (0, 0, 0)
        seen = (0, 0, 0)
        while time.monotonic() < deadline:
            raw = read_mem(k32, process, capture_addr, 48)
            pairs = struct.unpack("<QQQQQQ", raw)
            vals = (pairs[0], pairs[2], pairs[4])
            seen = (pairs[1], pairs[3], pairs[5])
            if seen != last_seen:
                for i, (old_seen, new_seen, token) in enumerate(zip(last_seen, seen, vals), start=1):
                    if old_seen == 0 and new_seen != 0:
                        print(f"OBSERVED {i}/3 token=0x{token:016X}")
                sys.stdout.flush()
                last_seen = seen
            if all(seen):
                break
            time.sleep(0.10)
        else:
            raw = read_mem(k32, process, capture_addr, 48)
            pairs = struct.unpack("<QQQQQQ", raw)
            vals = (pairs[0], pairs[2], pairs[4])
            seen = (pairs[1], pairs[3], pairs[5])

        if not all(seen):
            missing = [str(i + 1) for i, v in enumerate(seen) if not v]
            raise RuntimeError(
                "timed out before all Raven records were observed; "
                f"missing target(s): {', '.join(missing)}. "
                "The hook only sees records that GoW naturally decodes while it is installed."
            )
        zero_tokens = [str(i + 1) for i, v in enumerate(vals) if v == 0]
        if zero_tokens:
            raise RuntimeError(
                "GoW naturally decoded all target record(s), but returned token 0 for target(s): "
                + ", ".join(zero_tokens)
                + ". This is now proven in-thread evidence, not a remote-thread artifact."
            )

        rows = []
        for i, (payload_hex, obj_hash, token) in enumerate(zip(TARGET_HEX, EXPECTED_OBJECT_HASHES, vals), start=1):
            fields = decode_token(token)
            if not fields["present"]:
                raise RuntimeError(f"captured target {i} has no present marker: 0x{token:016X}")
            if fields["aux_flag"] != 0:
                raise RuntimeError(f"captured target {i} has unexpected bit-17 aux flag: 0x{token:016X}")
            if fields["flavour"] != 0:
                raise RuntimeError(f"captured target {i} has unexpected flavour {fields['flavour']}")
            if not fields["raven_formula_match"]:
                raise RuntimeError(f"captured target {i} fails Raven token formula: 0x{token:016X}")
            row = {
                "index": i,
                "payload_hex": payload_hex,
                "registry_hash_hex": f"0x{EXPECTED_REGISTRY_HASH:016X}",
                "object_hash_hex": f"0x{obj_hash:016X}",
                "token_hex": f"0x{token:016X}",
                **fields,
            }
            row["reconstructed_raven_token_hex"] = f"0x{int(fields['reconstructed_raven_token']):016X}"
            rows.append(row)
            print(
                f"PASS {i}/3 object={row['object_hash_hex']} token={row['token_hex']} "
                f"registry={row['registry']} slot={row['slot']} flavour={row['flavour']}"
            )

        if len({int(r["registry"]) for r in rows}) != 1:
            raise RuntimeError("the three Raven records resolved to different numeric registries")

        document = {
            "schema": "completionist-map.raven-gameobject-token-resolution.v2",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "source": "passive in-thread hook at GoW.exe RVA 0x5493A1",
            "exe": {
                "path": exe_path,
                "sha256": actual_sha,
                "pid": pid,
                "module_base_hex": f"0x{module_base:X}",
            },
            "verification": {
                "hook_rva_hex": f"0x{HOOK_RVA:X}",
                "hook_original_bytes_hex": original.hex(),
                "all_three_resolved": True,
                "all_formula_checks_passed": True,
                "synthetic_decoder_call_used": False,
            },
            "records": rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence written: {output}")
    finally:
        if patch_installed:
            try:
                install_patch(k32, process, hook_addr, HOOK_ORIGINAL)
                print("Passive hook removed; original GoW code restored.")
            except Exception as exc:
                print(f"WARNING: failed to restore hook site: {exc}", file=sys.stderr)
        if remote:
            if not k32.VirtualFreeEx(process, remote, 0, MEM_RELEASE):
                print("WARNING: VirtualFreeEx failed for hook page", file=sys.stderr)
        _close(k32, process)

def self_test() -> None:
    test = 1 | (0xBEEF << 1) | (0xABCDE << 18)
    d = decode_token(test)
    assert d["registry"] == 0xBEEF
    assert d["slot"] == 0xABCDE
    assert d["aux_flag"] == 0
    assert d["flavour"] == 0
    assert d["raven_formula_match"] is True

    hook = build_hook(0x7FF600001000, 0x7FF600002000, 0x7FF6005493F1, 0x7FF6005493AF)
    assert len(abs_jmp(0x123456789ABCDEF0)) == 14
    assert hook.endswith(abs_jmp(0x7FF6005493AF))
    print(f"SELF-TEST PASS: hook bytes={len(hook)}, token extraction and detour layout valid")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, help="JSON evidence output path")
    ap.add_argument("--timeout-seconds", type=int, default=180)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if args.output is None:
            ap.error("--output is required unless --self-test is used")
        capture(args.output.resolve(), args.timeout_seconds)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
