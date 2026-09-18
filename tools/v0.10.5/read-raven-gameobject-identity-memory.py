#!/usr/bin/env python3
"""Read-only live-memory Raven GameObject identity investigation.

This tool never debugs, pauses, patches, or writes the God of War process.
It uses only OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION) and
ReadProcessMemory.

For the three frozen carrier GameObject tokens (only one is the inserted Raven) it:
1) reproduces the proven RVA 0x4EF0B0 token resolver using memory reads;
2) resolves each token to a live GameObject pointer;
3) reads identity-related fields +0x278/+0x280/+0x284 and vtable +0x38;
4) scans a bounded read-only object pointer graph for an exact byte vector whose
   native hash equals the corresponding frozen save object_hash;
5) records the identity-method RVA/function bytes/disassembly for offline work.

No save/progression/quest/marker state is changed.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from collections import deque
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
TOKEN_RESOLVER_RVA = 0x4EF0B0
REGISTRY_TABLE_BEGIN_RVA = 0x22A98C0
REGISTRY_TABLE_END_RVA = 0x22A9AC0
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = C.c_void_p(-1).value
MAX_PATH = 260
MASK64 = 0xFFFFFFFFFFFFFFFF

KNOWN = [
    {
        "record_role": "alive_baseline_record_0",
        "catalogue_id": None,
        "token": 0x1C1001DD,
        "object_hash": 0x165CD520758061E5,
    },
    {
        "record_role": "alive_baseline_record_1",
        "catalogue_id": None,
        "token": 0x1C4801DD,
        "object_hash": 0xADB72E5C5003A8A0,
    },
    {
        "record_role": "inserted_ravenKilled_record",
        "catalogue_id": "raven_642d0d164af0a5d4076e77933c549a5d",
        "token": 0x1BB001DD,
        "object_hash": 0x98BE1707BA2D65A9,
    },
]


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
    k32.ReadProcessMemory.argtypes = [W.HANDLE, W.LPCVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)]
    k32.ReadProcessMemory.restype = W.BOOL
    k32.CloseHandle.argtypes = [W.HANDLE]
    k32.CloseHandle.restype = W.BOOL
    return k32


def close_handle(k32, handle) -> None:
    if handle and int(C.cast(handle, C.c_void_p).value or 0) not in (0, INVALID_HANDLE_VALUE):
        k32.CloseHandle(handle)


def winerr(prefix: str) -> RuntimeError:
    code = C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_supported_process(k32) -> tuple[int, str]:
    candidates = {"gow.exe", "godofwar.exe"}
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("CreateToolhelp32Snapshot(processes) failed")
    found: list[tuple[int, str]] = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = C.sizeof(pe)
        ok = k32.Process32FirstW(snap, C.byref(pe))
        while ok:
            name = str(pe.szExeFile)
            if name.lower() in candidates:
                found.append((int(pe.th32ProcessID), name))
            ok = k32.Process32NextW(snap, C.byref(pe))
    finally:
        close_handle(k32, snap)
    if not found:
        raise RuntimeError("God of War is not running (expected GoW.exe or GodOfWar.exe)")
    if len(found) != 1:
        raise RuntimeError(f"expected one God of War process, found {found}")
    return found[0]


def get_main_module(k32, pid: int, exe_name: str) -> tuple[int, int, str]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("CreateToolhelp32Snapshot(modules) failed")
    try:
        me = MODULEENTRY32W()
        me.dwSize = C.sizeof(me)
        ok = k32.Module32FirstW(snap, C.byref(me))
        while ok:
            if str(me.szModule).lower() == exe_name.lower():
                base = C.cast(me.modBaseAddr, C.c_void_p).value
                if not base:
                    raise RuntimeError("main module base is NULL")
                return int(base), int(me.modBaseSize), str(me.szExePath)
            ok = k32.Module32NextW(snap, C.byref(me))
    finally:
        close_handle(k32, snap)
    raise RuntimeError(f"could not resolve {exe_name} module")


def read_mem(k32, process, address: int, size: int) -> bytes:
    if size <= 0:
        return b""
    buf = (C.c_ubyte * size)()
    done = C.c_size_t()
    if not k32.ReadProcessMemory(process, C.c_void_p(address), buf, size, C.byref(done)):
        raise winerr(f"ReadProcessMemory(0x{address:X}, {size}) failed")
    if done.value != size:
        raise RuntimeError(f"short read at 0x{address:X}: {done.value}/{size}")
    return bytes(buf)


def safe_read(k32, process, address: int, size: int) -> bytes | None:
    try:
        return read_mem(k32, process, address, size)
    except Exception:
        return None


def u32(k32, process, address: int) -> int:
    return struct.unpack("<I", read_mem(k32, process, address, 4))[0]


def u64(k32, process, address: int) -> int:
    return struct.unpack("<Q", read_mem(k32, process, address, 8))[0]


def token_components(token: int) -> tuple[int, int, int]:
    registry = (token >> 1) & 0xFFFF
    flavor = (token >> 17) & 1
    slot = (token >> 18) & 0xFFFFF
    return registry, flavor, slot


def resolve_token_read_only(k32, process, module_base: int, token: int) -> dict:
    registry, flavor, slot = token_components(token)
    table_begin = module_base + REGISTRY_TABLE_BEGIN_RVA
    table_end = module_base + REGISTRY_TABLE_END_RVA
    matches = []
    for entry_addr in range(table_begin, table_end, 8):
        raw = safe_read(k32, process, entry_addr, 8)
        if raw is None:
            continue
        descriptor = struct.unpack("<Q", raw)[0]
        if descriptor == 0:
            continue
        rid_raw = safe_read(k32, process, descriptor, 4)
        if rid_raw is None:
            continue
        rid = struct.unpack("<I", rid_raw)[0]
        if rid != registry:
            continue
        base_off = 0x20 if flavor else 0x08
        count_off = base_off + 0x10
        count = u32(k32, process, descriptor + count_off)
        array_ptr = u64(k32, process, descriptor + base_off)
        if slot >= count:
            raise RuntimeError(
                f"token 0x{token:08X}: slot {slot} >= registry {registry} count {count}"
            )
        object_ptr = u64(k32, process, array_ptr + slot * 8)
        matches.append({
            "registry_descriptor": descriptor,
            "registry_table_entry": entry_addr,
            "registry": registry,
            "flavor": flavor,
            "slot": slot,
            "count": count,
            "array_ptr": array_ptr,
            "object_ptr": object_ptr,
        })
    if len(matches) != 1:
        raise RuntimeError(
            f"token 0x{token:08X}: expected one registry descriptor, found {len(matches)}"
        )
    if matches[0]["object_ptr"] == 0:
        raise RuntimeError(f"token 0x{token:08X}: object slot is NULL")
    return matches[0]


def raw_identity_hash(data: bytes) -> int:
    value = 0
    for byte in data:
        value = ((value + byte) * 0x401) & MASK64
        value ^= value >> 6
    return value


def plausible_pointer(value: int) -> bool:
    return 0x10000 <= value < 0x0000800000000000 and (value & 0x7) == 0


def scan_blob_for_target(blob: bytes, base_address: int, target: int, max_elements: int, source: str) -> list[dict]:
    matches = []
    for elements in range(1, max_elements + 1):
        size = elements * 16
        if size > len(blob):
            break
        for offset in range(0, len(blob) - size + 1):
            candidate = blob[offset:offset + size]
            if raw_identity_hash(candidate) == target:
                matches.append({
                    "source": source,
                    "address": base_address + offset,
                    "offset": offset,
                    "elements": elements,
                    "bytes": candidate.hex(),
                    "elements_hex": [
                        candidate[i:i + 16].hex() for i in range(0, len(candidate), 16)
                    ],
                })
    return matches


def bounded_pointer_graph_scan(
    k32,
    process,
    object_ptr: int,
    target_hash: int,
    *,
    block_size: int = 0x400,
    max_depth: int = 2,
    max_blocks: int = 128,
    max_elements: int = 12,
) -> dict:
    queue = deque([(object_ptr, 0, "object")])
    visited: set[int] = set()
    matches: list[dict] = []
    blocks = []

    while queue and len(visited) < max_blocks:
        address, depth, source = queue.popleft()
        if address in visited:
            continue
        visited.add(address)
        blob = safe_read(k32, process, address, block_size)
        if blob is None:
            continue
        blocks.append({
            "address": f"0x{address:X}",
            "depth": depth,
            "source": source,
            "sha256": hashlib.sha256(blob).hexdigest(),
        })
        matches.extend(
            scan_blob_for_target(blob, address, target_hash, max_elements, source)
        )
        if matches:
            break
        if depth >= max_depth:
            continue

        for off in range(0, len(blob) - 7, 8):
            ptr = struct.unpack_from("<Q", blob, off)[0]
            if not plausible_pointer(ptr) or ptr in visited:
                continue
            queue.append((ptr, depth + 1, f"{source}+0x{off:X}->0x{ptr:X}"))

    return {
        "blocks_scanned": len(blocks),
        "visited_addresses": len(visited),
        "matches": matches,
        "block_manifest": blocks[:128],
    }


def load_pe_helper():
    helper = Path(__file__).with_name("analyze-gameobject-token-resolver.py")
    spec = importlib.util.spec_from_file_location("gow_token_resolver_pe", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load PE helper {helper}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_MEM, X86_OP_IMM
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_MEM, X86_OP_IMM


def method_report(exe_data: bytes, module_base: int, method_ptr: int) -> dict:
    pe_mod = load_pe_helper()
    pe = pe_mod.PE(exe_data)
    method_rva = method_ptr - module_base
    fn = pe.function_for(method_rva)
    if fn is None:
        return {
            "method_ptr": f"0x{method_ptr:X}",
            "method_rva": f"0x{method_rva:X}",
            "function": None,
        }
    blob = pe.bytes_for(fn)
    report = {
        "method_ptr": f"0x{method_ptr:X}",
        "method_rva": f"0x{method_rva:X}",
        "function": {
            "begin_rva": f"0x{fn['begin']:X}",
            "end_rva": f"0x{fn['end']:X}",
            "size": fn["end"] - fn["begin"],
            "bytes_hex": blob.hex(),
        },
    }
    try:
        Cs, arch, mode, op_mem, op_imm = load_capstone()
        md = Cs(arch, mode)
        md.detail = True
        insns = []
        memory_disps = []
        direct_calls = []
        for ins in md.disasm(blob, module_base + fn["begin"]):
            row = {
                "rva": f"0x{ins.address - module_base:X}",
                "bytes": ins.bytes.hex(),
                "mnemonic": ins.mnemonic,
                "op_str": ins.op_str,
            }
            insns.append(row)
            try:
                for op in ins.operands:
                    if op.type == op_mem:
                        memory_disps.append({
                            "rva": row["rva"],
                            "disp": op.mem.disp,
                            "op": f"{ins.mnemonic} {ins.op_str}",
                        })
                    elif op.type == op_imm and ins.mnemonic == "call":
                        dest = int(op.imm)
                        if module_base <= dest < module_base + pe.size_of_image:
                            direct_calls.append({
                                "site_rva": row["rva"],
                                "dest_rva": f"0x{dest - module_base:X}",
                            })
            except Exception:
                pass
        report["disassembly"] = insns[:300]
        report["memory_displacements"] = memory_disps[:300]
        report["direct_calls"] = direct_calls[:100]
    except Exception as exc:
        report["disassembly_error"] = repr(exc)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--max-blocks", type=int, default=128)
    ap.add_argument("--block-size", type=lambda x: int(x, 0), default=0x400)
    args = ap.parse_args()

    if os.name != "nt":
        raise RuntimeError("Windows-only live memory reader")
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("run with 64-bit Python")

    k32 = configure_kernel32()
    pid, exe_name = find_supported_process(k32)
    module_base, module_size, exe_path = get_main_module(k32, pid, exe_name)
    exe_sha = sha256_file(exe_path)
    if exe_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(
            f"unsupported GoW.exe SHA-256: expected {EXPECTED_EXE_SHA256}, got {exe_sha}"
        )

    access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise winerr(f"OpenProcess({pid}) failed")

    try:
        resolver_live = read_mem(k32, process, module_base + TOKEN_RESOLVER_RVA, 0x4B)
        resolver_prefix = bytes.fromhex(
            "488d0509a8db014c8d1502aadb0166904c8b084d85c97405413909740c"
        )
        if not resolver_live.startswith(resolver_prefix):
            raise RuntimeError("live token resolver signature changed")

        exe_data = Path(exe_path).read_bytes()
        records = []
        method_cache: dict[int, dict] = {}

        for known in KNOWN:
            resolved = resolve_token_read_only(k32, process, module_base, known["token"])
            object_ptr = int(resolved["object_ptr"])
            object_head = read_mem(k32, process, object_ptr, 0x300)
            vtable_ptr = struct.unpack_from("<Q", object_head, 0)[0]
            identity_method_ptr = u64(k32, process, vtable_ptr + 0x38)

            if identity_method_ptr not in method_cache:
                method_cache[identity_method_ptr] = method_report(
                    exe_data, module_base, identity_method_ptr
                )

            graph = bounded_pointer_graph_scan(
                k32,
                process,
                object_ptr,
                known["object_hash"],
                block_size=args.block_size,
                max_depth=args.max_depth,
                max_blocks=args.max_blocks,
            )

            flags_278 = struct.unpack_from("<I", object_head, 0x278)[0]
            field_280 = struct.unpack_from("<I", object_head, 0x280)[0]
            field_284 = struct.unpack_from("<I", object_head, 0x284)[0]

            records.append({
                "catalogue_id": known["catalogue_id"],
                "token_hex": f"0x{known['token']:08X}",
                "object_hash_hex": f"0x{known['object_hash']:016X}",
                "token_components": {
                    "registry": resolved["registry"],
                    "flavor": resolved["flavor"],
                    "slot": resolved["slot"],
                },
                "registry": {
                    "descriptor": f"0x{resolved['registry_descriptor']:X}",
                    "table_entry": f"0x{resolved['registry_table_entry']:X}",
                    "count": resolved["count"],
                    "array_ptr": f"0x{resolved['array_ptr']:X}",
                },
                "object": {
                    "ptr": f"0x{object_ptr:X}",
                    "vtable_ptr": f"0x{vtable_ptr:X}",
                    "identity_method_ptr": f"0x{identity_method_ptr:X}",
                    "identity_method_rva": (
                        f"0x{identity_method_ptr - module_base:X}"
                        if module_base <= identity_method_ptr < module_base + module_size
                        else None
                    ),
                    "field_278_hex": f"0x{flags_278:08X}",
                    "field_280": field_280,
                    "field_284": field_284,
                    "head_sha256": hashlib.sha256(object_head).hexdigest(),
                },
                "identity_vector_memory_scan": graph,
            })
            print(
                f"RESOLVED {known['catalogue_id']} token=0x{known['token']:08X} "
                f"object=0x{object_ptr:X} identityMethod="
                f"0x{identity_method_ptr - module_base:X} "
                f"matches={len(graph['matches'])}"
            )

        result = {
            "schema": "completionist-map.raven-live-memory-identity.v1",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "process": {
                "pid": pid,
                "exe_name": exe_name,
                "exe_path": exe_path,
                "exe_sha256": exe_sha,
                "module_base": f"0x{module_base:X}",
                "module_size": module_size,
            },
            "resolver": {
                "rva": f"0x{TOKEN_RESOLVER_RVA:X}",
                "registry_table_begin_rva": f"0x{REGISTRY_TABLE_BEGIN_RVA:X}",
                "registry_table_end_rva": f"0x{REGISTRY_TABLE_END_RVA:X}",
                "algorithm": (
                    "registry=(token>>1)&0xFFFF; flavor=(token>>17)&1; "
                    "slot=(token>>18)&0xFFFFF; find descriptor by registry ID; "
                    "flavor0 array=descriptor+0x08 count=+0x18; "
                    "flavor1 array=descriptor+0x20 count=+0x30; object=array[slot]"
                ),
            },
            "records": records,
            "identity_methods": {
                f"0x{ptr:X}": report for ptr, report in method_cache.items()
            },
            "safety": {
                "debugger_attached": False,
                "process_write_handle_requested": False,
                "process_memory_written": False,
                "process_memory_read_only": True,
                "save_or_progression_written": False,
                "game_files_written": False,
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"RAVEN_LIVE_MEMORY_IDENTITY_READ_COMPLETE {args.output}")
        return 0
    finally:
        close_handle(k32, process)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
