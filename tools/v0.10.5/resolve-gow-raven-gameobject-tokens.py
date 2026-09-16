#!/usr/bin/env python3
"""Resolve the three archived Raven GameObject records through GoW's live decoder.

This tool calls the already-reconstructed decoder at RVA 0x5491A0 inside the
running GoW.exe. It does not guess or invert the 64-bit hashes: the game does
its normal registry/object lookup and returns the packed GameObject token.
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
from datetime import datetime, timezone

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
DECODER_RVA = 0x5491A0
OUTPUT_SITE_RVA = 0x5493A1
DECODER_PROLOGUE = bytes.fromhex("405541574883ec28")
OUTPUT_SITE_BYTES = bytes.fromhex("4889550041f60704")

TARGET_HEX = (
    "01b0b227342530c24ee561807520d55c16",
    "01b0b227342530c24ea0a803505c2eb7ad",
    "01b0b227342530c24ea9652dba0717be98",
)
TARGETS = tuple(bytes.fromhex(x) for x in TARGET_HEX)
EXPECTED_REGISTRY_HASH = 0x4EC230253427B2B0
EXPECTED_OBJECT_HASHES = (
    0x165CD520758061E5,
    0xADB72E5C5003A8A0,
    0x98BE1707BA2D65A9,
)

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_CREATE_THREAD = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INVALID_HANDLE_VALUE = C.c_void_p(-1).value
MAX_PATH = 260


class PROCESSENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD),
        ("cntUsage", W.DWORD),
        ("th32ProcessID", W.DWORD),
        ("th32DefaultHeapID", C.c_size_t),
        ("th32ModuleID", W.DWORD),
        ("cntThreads", W.DWORD),
        ("th32ParentProcessID", W.DWORD),
        ("pcPriClassBase", W.LONG),
        ("dwFlags", W.DWORD),
        ("szExeFile", W.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD),
        ("th32ModuleID", W.DWORD),
        ("th32ProcessID", W.DWORD),
        ("GlblcntUsage", W.DWORD),
        ("ProccntUsage", W.DWORD),
        ("modBaseAddr", C.POINTER(C.c_ubyte)),
        ("modBaseSize", W.DWORD),
        ("hModule", W.HMODULE),
        ("szModule", W.WCHAR * 256),
        ("szExePath", W.WCHAR * MAX_PATH),
    ]


def parse_record(payload: bytes) -> dict[str, int]:
    if len(payload) != 17:
        raise ValueError(f"expected 17-byte record, got {len(payload)}")
    return {
        "flags": payload[0],
        "registry_hash": int.from_bytes(payload[1:9], "little"),
        "object_hash": int.from_bytes(payload[9:17], "little"),
    }


def decode_token(token: int) -> dict[str, int | bool]:
    registry = (token >> 1) & 0xFFFF
    aux_flag = (token >> 17) & 1
    slot = (token >> 18) & 0xFFFFF
    flavour = (token >> 38) & 0x3F
    reconstructed_raven = 1 | (registry << 1) | (slot << 18)
    return {
        "present": bool(token & 1),
        "registry": registry,
        "aux_flag": aux_flag,
        "slot": slot,
        "flavour": flavour,
        "reconstructed_raven_token": reconstructed_raven,
        "raven_formula_match": token == reconstructed_raven,
    }


def self_test() -> None:
    parsed = [parse_record(p) for p in TARGETS]
    assert all(x["flags"] == 1 for x in parsed)
    assert all(x["registry_hash"] == EXPECTED_REGISTRY_HASH for x in parsed)
    assert tuple(x["object_hash"] for x in parsed) == EXPECTED_OBJECT_HASHES

    registry = 0xBEEF
    slot = 0xABCDE
    token = 1 | (registry << 1) | (slot << 18)
    d = decode_token(token)
    assert d["present"] is True
    assert d["registry"] == registry
    assert d["aux_flag"] == 0
    assert d["slot"] == slot
    assert d["flavour"] == 0
    assert d["raven_formula_match"] is True
    print("SELF-TEST PASS: Raven record parsing and token field extraction")


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
    k32.CreateRemoteThread.argtypes = [W.HANDLE, W.LPVOID, C.c_size_t, W.LPVOID, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)]
    k32.CreateRemoteThread.restype = W.HANDLE
    k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    k32.WaitForSingleObject.restype = W.DWORD
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
    raise RuntimeError(f"{exe_name} is not running. Start God of War and leave it at the main menu, then rerun this command.")


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


def make_stub(payload_addr: int, token_addr: int, consumed_addr: int, ok_addr: int, decoder_addr: int) -> bytes:
    # Windows x64 ABI: reserve 32 bytes shadow space + 8 bytes alignment before CALL.
    code = bytearray()
    code += b"\x48\x83\xEC\x28"                              # sub rsp, 28h
    code += b"\x48\xB9" + struct.pack("<Q", payload_addr)       # mov rcx, payload
    code += b"\xBA\x11\x00\x00\x00"                         # mov edx, 17
    code += b"\x49\xB8" + struct.pack("<Q", token_addr)         # mov r8, token_out
    code += b"\x49\xB9" + struct.pack("<Q", consumed_addr)      # mov r9, consumed_out
    code += b"\x48\xB8" + struct.pack("<Q", decoder_addr)       # mov rax, decoder
    code += b"\xFF\xD0"                                         # call rax
    code += b"\x49\xBA" + struct.pack("<Q", ok_addr)            # mov r10, ok_out
    code += b"\x41\x88\x02"                                    # mov [r10], al
    code += b"\x48\x83\xC4\x28"                              # add rsp, 28h
    code += b"\x31\xC0"                                         # xor eax, eax
    code += b"\xC3"                                               # ret
    return bytes(code)


def resolve_one(k32, process, decoder_addr: int, payload: bytes, timeout_ms: int) -> tuple[int, int, int]:
    alloc_size = 0x1000
    remote = k32.VirtualAllocEx(process, None, alloc_size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
    if not remote:
        raise _winerr("VirtualAllocEx failed")
    base = int(C.cast(remote, C.c_void_p).value)
    payload_addr = base + 0x000
    token_addr = base + 0x020
    consumed_addr = base + 0x028
    ok_addr = base + 0x02C
    code_addr = base + 0x100
    thread = None
    try:
        write_mem(k32, process, payload_addr, payload)
        write_mem(k32, process, token_addr, b"\x00" * 16)
        stub = make_stub(payload_addr, token_addr, consumed_addr, ok_addr, decoder_addr)
        write_mem(k32, process, code_addr, stub)
        k32.FlushInstructionCache(process, C.c_void_p(code_addr), len(stub))

        tid = W.DWORD()
        thread = k32.CreateRemoteThread(process, None, 0, C.c_void_p(code_addr), None, 0, C.byref(tid))
        if not thread:
            raise _winerr("CreateRemoteThread failed")
        wait = k32.WaitForSingleObject(thread, timeout_ms)
        if wait == WAIT_TIMEOUT:
            raise RuntimeError(f"live decoder call timed out after {timeout_ms} ms")
        if wait != WAIT_OBJECT_0:
            raise RuntimeError(f"WaitForSingleObject returned 0x{wait:08X}")

        token = int.from_bytes(read_mem(k32, process, token_addr, 8), "little")
        consumed = int.from_bytes(read_mem(k32, process, consumed_addr, 4), "little")
        ok = read_mem(k32, process, ok_addr, 1)[0]
        return token, consumed, ok
    finally:
        _close(k32, thread)
        if not k32.VirtualFreeEx(process, C.c_void_p(base), 0, MEM_RELEASE):
            print(f"WARNING: VirtualFreeEx failed for 0x{base:X}", file=sys.stderr)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def live_resolve(output: Path, timeout_ms: int) -> None:
    if os.name != "nt":
        raise RuntimeError("live resolution is Windows-only; use --self-test on other platforms")
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("run this tool with 64-bit Python")

    k32 = _configure_kernel32()
    pid = find_process(k32, "GoW.exe")
    module_base, exe_path = get_main_module(k32, pid, "GoW.exe")
    actual_sha = sha256_file(exe_path)
    if actual_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(
            "GoW.exe build mismatch; refusing live call. "
            f"expected sha256={EXPECTED_EXE_SHA256}, got {actual_sha} ({exe_path})"
        )

    access = PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise _winerr(f"OpenProcess({pid}) failed")
    try:
        prologue = read_mem(k32, process, module_base + DECODER_RVA, len(DECODER_PROLOGUE))
        output_site = read_mem(k32, process, module_base + OUTPUT_SITE_RVA, len(OUTPUT_SITE_BYTES))
        if prologue != DECODER_PROLOGUE:
            raise RuntimeError(
                f"decoder signature mismatch at RVA 0x{DECODER_RVA:X}: "
                f"expected {DECODER_PROLOGUE.hex()}, got {prologue.hex()}"
            )
        if output_site != OUTPUT_SITE_BYTES:
            raise RuntimeError(
                f"output-site signature mismatch at RVA 0x{OUTPUT_SITE_RVA:X}: "
                f"expected {OUTPUT_SITE_BYTES.hex()}, got {output_site.hex()}"
            )

        print(f"GoW.exe PID={pid} base=0x{module_base:X}")
        print("Build/signatures verified. Resolving the 3 Raven records through GoW itself...")
        sys.stdout.flush()

        rows = []
        for index, payload in enumerate(TARGETS, start=1):
            parsed = parse_record(payload)
            token, consumed, ok = resolve_one(k32, process, module_base + DECODER_RVA, payload, timeout_ms)
            fields = decode_token(token)
            row = {
                "index": index,
                "payload_hex": payload.hex(),
                "flags": parsed["flags"],
                "registry_hash_hex": f"0x{parsed['registry_hash']:016X}",
                "object_hash_hex": f"0x{parsed['object_hash']:016X}",
                "decoder_return": ok,
                "decoder_reported_size": consumed,
                "token_hex": f"0x{token:016X}",
                **fields,
            }
            row["reconstructed_raven_token_hex"] = f"0x{int(fields['reconstructed_raven_token']):016X}"

            if ok != 1:
                raise RuntimeError(f"decoder returned failure for target {index}: {payload.hex()}")
            if consumed != 17:
                raise RuntimeError(f"decoder reported size {consumed}, expected 17 for target {index}")
            if not fields["present"]:
                raise RuntimeError(f"decoded token missing present marker for target {index}: 0x{token:016X}")
            if fields["aux_flag"] != 0:
                raise RuntimeError(f"unexpected bit-17 aux flag for Raven target {index}: 0x{token:016X}")
            if fields["flavour"] != 0:
                raise RuntimeError(f"unexpected nonzero Raven flavour for target {index}: {fields['flavour']}")
            if not fields["raven_formula_match"]:
                raise RuntimeError(f"Raven token formula mismatch for target {index}: 0x{token:016X}")

            rows.append(row)
            print(
                f"PASS {index}/3 object={row['object_hash_hex']} token={row['token_hex']} "
                f"registry={row['registry']} slot={row['slot']} flavour={row['flavour']}"
            )
            sys.stdout.flush()

        if len({int(r["registry"]) for r in rows}) != 1:
            raise RuntimeError("the three Raven records unexpectedly resolved to different numeric registries")

        document = {
            "schema": "completionist-map.raven-gameobject-token-resolution.v1",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "source": "live GoW.exe decoder call at RVA 0x5491A0",
            "exe": {
                "path": exe_path,
                "sha256": actual_sha,
                "pid": pid,
                "module_base_hex": f"0x{module_base:X}",
            },
            "verification": {
                "decoder_rva_hex": f"0x{DECODER_RVA:X}",
                "decoder_prologue_hex": prologue.hex(),
                "output_site_rva_hex": f"0x{OUTPUT_SITE_RVA:X}",
                "output_site_bytes_hex": output_site.hex(),
                "all_three_resolved": True,
                "all_formula_checks_passed": True,
            },
            "records": rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence written: {output}")
    finally:
        _close(k32, process)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, help="JSON evidence output path")
    ap.add_argument("--timeout-ms", type=int, default=10000, help="timeout for each live decoder call")
    ap.add_argument("--self-test", action="store_true", help="run platform-independent parser/token tests")
    args = ap.parse_args()

    try:
        if args.self_test:
            self_test()
            return 0
        if args.output is None:
            ap.error("--output is required unless --self-test is used")
        live_resolve(args.output.resolve(), args.timeout_ms)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
