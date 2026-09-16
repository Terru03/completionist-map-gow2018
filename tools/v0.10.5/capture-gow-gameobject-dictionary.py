#!/usr/bin/env python3
"""Passively capture every successful hashed GameObject decode seen by GoW.

This generalises the proven Raven-only passive hook. A temporary detour at
RVA 0x5493F1 records each successful hash-backed GameObject decode on GoW's
own thread into a bounded remote ring buffer. The hook reproduces the
overwritten instructions and is removed before exit.

The output is a deduplicated hash -> packed-token dictionary. It is deliberately
category-agnostic: Ravens, Nornir chests and their puzzle pieces, lore,
artefacts, legendary chests, realm tears, and other save-backed GameObjects can
all be classified later from the same evidence.
"""
from __future__ import annotations

import argparse
import csv
import ctypes as C
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
from datetime import datetime, timezone


def load_raven_helper():
    path = Path(__file__).with_name("resolve-gow-raven-gameobject-tokens.py")
    spec = importlib.util.spec_from_file_location("gow_raven_passive_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load passive-hook helper: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = load_raven_helper()
EXPECTED_EXE_SHA256 = H.EXPECTED_EXE_SHA256
HOOK_RVA = 0x5493F1
HOOK_CONTINUE_RVA = 0x549400
# mov rdi,[rsp+58h] ; mov r14,[rsp+20h] ; mov rsi,[rsp+50h]
HOOK_ORIGINAL = bytes.fromhex("488b7c24584c8b742420488b742450")

HEADER_SIZE = 0x100
ENTRY_SIZE = 32
DEFAULT_CAPACITY = 131072
CODE_SLACK = 0x1000


def generic_token_fields(token: int) -> dict[str, int | bool | str]:
    registry = (token >> 1) & 0xFFFF
    aux_flag = (token >> 17) & 1
    slot = (token >> 18) & 0xFFFFF
    flavour = (token >> 38) & 0x3F
    rebuilt = 1 | (registry << 1) | (aux_flag << 17) | (slot << 18) | (flavour << 38)
    return {
        "present": bool(token & 1),
        "registry": registry,
        "aux_flag": aux_flag,
        "slot": slot,
        "flavour": flavour,
        "known_fields_reconstructed_token_hex": f"0x{rebuilt:016X}",
        "known_fields_exact_match": token == rebuilt,
    }


def abs_jmp(target: int) -> bytes:
    return H.abs_jmp(target)


def build_capture_all_hook(
    code_addr: int,
    state_addr: int,
    entries_addr: int,
    capacity: int,
    continue_addr: int,
) -> bytes:
    """Build the all-record capture trampoline at the decoder's common success exit.

    By RVA 0x5493F1, [RBP] contains the final packed token including any optional
    upper/flavour contribution. Failed hash lookups also reach this cleanup path,
    but retain token 0, so the present-marker test excludes them.

    Header:
      +0x00 DWORD atomic reservation/write count (may exceed capacity)
      +0x04 DWORD overflow flag
    Entry (32 bytes):
      +0x00 QWORD final token ([RBP])
      +0x08 QWORD serialized registry hash ([R15+1])
      +0x10 QWORD serialized object hash ([R15+9])
      +0x18 DWORD serialized flags ([R15])
      +0x1C DWORD optional upper value ([R15+0x11] when flag 0x04 is set)
    """
    if not 1 <= capacity <= 0x7FFFFFFF:
        raise ValueError("capacity outside supported DWORD range")

    b = bytearray()
    labels: dict[str, int] = {}
    fixups: list[tuple[int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(b)

    def jcc(op2: int, name: str) -> None:
        b.extend((0x0F, op2))
        fixups.append((len(b), name))
        b.extend(b"\x00\x00\x00\x00")

    def jmp(name: str) -> None:
        b.append(0xE9)
        fixups.append((len(b), name))
        b.extend(b"\x00\x00\x00\x00")

    # Preserve every scratch register/flag touched by this no-call recorder.
    b.extend(b"\x9C")                                     # pushfq
    b.extend(b"\x50\x51\x52")                             # push rax; push rcx; push rdx
    b.extend(b"\x41\x50\x41\x51\x41\x52\x41\x53")         # push r8,r9,r10,r11

    b.extend(b"\x4C\x8B\x55\x00")                         # mov r10, [rbp]
    b.extend(b"\x41\xF6\xC2\x01")                         # test r10b, 1
    jcc(0x84, "restore")                                   # jz restore (failed decode)

    b.extend(b"\x48\xB8" + struct.pack("<Q", state_addr))   # mov rax, state
    b.extend(b"\x41\xB8\x01\x00\x00\x00")                 # mov r8d, 1
    b.extend(b"\xF0\x44\x0F\xC1\x00")                     # lock xadd dword [rax], r8d
    b.extend(b"\x41\x81\xF8" + struct.pack("<I", capacity)) # cmp r8d, capacity
    jcc(0x83, "overflow")                                  # jae overflow

    b.extend(b"\x4D\x6B\xC0\x20")                         # imul r8, r8, 32
    b.extend(b"\x49\xB9" + struct.pack("<Q", entries_addr)) # mov r9, entries
    b.extend(b"\x4D\x01\xC1")                             # add r9, r8

    b.extend(b"\x4D\x89\x11")                             # mov [r9], r10
    b.extend(b"\x49\x8B\x4F\x01")                         # mov rcx, [r15+1]
    b.extend(b"\x49\x89\x49\x08")                         # mov [r9+8], rcx
    b.extend(b"\x49\x8B\x4F\x09")                         # mov rcx, [r15+9]
    b.extend(b"\x49\x89\x49\x10")                         # mov [r9+10h], rcx
    b.extend(b"\x41\x0F\xB6\x0F")                         # movzx ecx, byte [r15]
    b.extend(b"\x41\x89\x49\x18")                         # mov [r9+18h], ecx
    b.extend(b"\x31\xC9")                                 # xor ecx, ecx
    b.extend(b"\x41\xF6\x07\x04")                         # test byte [r15], 4
    jcc(0x84, "store_upper")                               # jz store zero
    b.extend(b"\x41\x8B\x4F\x11")                         # mov ecx, [r15+11h]
    label("store_upper")
    b.extend(b"\x41\x89\x49\x1C")                         # mov [r9+1Ch], ecx
    jmp("restore")

    label("overflow")
    b.extend(b"\xC7\x40\x04\x01\x00\x00\x00")             # mov dword [rax+4],1

    label("restore")
    b.extend(b"\x41\x5B\x41\x5A\x41\x59\x41\x58")         # pop r11,r10,r9,r8
    b.extend(b"\x5A\x59\x58")                             # pop rdx; pop rcx; pop rax
    b.extend(b"\x9D")                                     # popfq

    # Reproduce all 15 overwritten cleanup bytes, then resume at 0x549400.
    b.extend(b"\x48\x8B\x7C\x24\x58")                     # mov rdi,[rsp+58h]
    b.extend(b"\x4C\x8B\x74\x24\x20")                     # mov r14,[rsp+20h]
    b.extend(b"\x48\x8B\x74\x24\x50")                     # mov rsi,[rsp+50h]
    b.extend(abs_jmp(continue_addr))

    for pos, name in fixups:
        if name not in labels:
            raise AssertionError(f"undefined hook label {name}")
        src_after = code_addr + pos + 4
        dst = code_addr + labels[name]
        rel = dst - src_after
        if not -(1 << 31) <= rel < (1 << 31):
            raise AssertionError("hook rel32 out of range")
        b[pos:pos + 4] = struct.pack("<i", rel)
    return bytes(b)


def deduplicate(raw: bytes, count: int):
    aggregates: dict[tuple[int, int, int, int, int], int] = {}
    record_tokens: dict[tuple[int, int, int, int], set[int]] = {}
    for i in range(count):
        token, registry_hash, object_hash, flags, upper = struct.unpack_from("<QQQII", raw, i * ENTRY_SIZE)
        full_key = (flags, registry_hash, object_hash, upper, token)
        aggregates[full_key] = aggregates.get(full_key, 0) + 1
        record_tokens.setdefault((flags, registry_hash, object_hash, upper), set()).add(token)

    rows = []
    for (flags, registry_hash, object_hash, upper, token), hits in sorted(
        aggregates.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0], kv[0][3], kv[0][4])
    ):
        rows.append({
            "flags": flags,
            "flags_hex": f"0x{flags:02X}",
            "registry_hash_hex": f"0x{registry_hash:016X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "upper": upper,
            "upper_hex": f"0x{upper:08X}",
            "token_hex": f"0x{token:016X}",
            **generic_token_fields(token),
            "hits": hits,
        })

    conflicts = []
    for (flags, registry_hash, object_hash, upper), tokens in sorted(record_tokens.items()):
        if len(tokens) > 1:
            conflicts.append({
                "flags_hex": f"0x{flags:02X}",
                "registry_hash_hex": f"0x{registry_hash:016X}",
                "object_hash_hex": f"0x{object_hash:016X}",
                "upper_hex": f"0x{upper:08X}",
                "token_hexes": [f"0x{x:016X}" for x in sorted(tokens)],
            })
    return rows, conflicts


def write_tsv(path: Path, rows: list[dict]) -> None:
    columns = [
        "flags_hex", "registry_hash_hex", "object_hash_hex", "upper_hex",
        "token_hex", "registry", "aux_flag", "slot", "flavour",
        "known_fields_exact_match", "hits",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def capture(output_json: Path, output_tsv: Path, capacity: int, duration_seconds: int | None) -> None:
    if sys.platform != "win32":
        raise RuntimeError("runtime capture is Windows-only")
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("run this tool with 64-bit Python")

    k32 = H._configure_kernel32()
    pid = H.find_process(k32, "GoW.exe")
    module_base, exe_path = H.get_main_module(k32, pid, "GoW.exe")
    actual_sha = H.sha256_file(exe_path)
    if actual_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(
            f"GoW.exe build mismatch: expected {EXPECTED_EXE_SHA256}, got {actual_sha}"
        )

    access = H.PROCESS_QUERY_INFORMATION | H.PROCESS_VM_OPERATION | H.PROCESS_VM_WRITE | H.PROCESS_VM_READ
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise H._winerr(f"OpenProcess({pid}) failed")

    hook_addr = module_base + HOOK_RVA
    remote = None
    patch_installed = False
    captured_at = datetime.now(timezone.utc)
    try:
        original = H.read_mem(k32, process, hook_addr, len(HOOK_ORIGINAL))
        if original != HOOK_ORIGINAL:
            raise RuntimeError(
                f"hook signature mismatch at RVA 0x{HOOK_RVA:X}: "
                f"expected {HOOK_ORIGINAL.hex()}, got {original.hex()}"
            )

        state_size = HEADER_SIZE + capacity * ENTRY_SIZE
        code_offset = (state_size + 0xFFF) & ~0xFFF
        alloc_size = code_offset + CODE_SLACK
        remote = k32.VirtualAllocEx(
            process, None, alloc_size, H.MEM_COMMIT | H.MEM_RESERVE, H.PAGE_EXECUTE_READWRITE
        )
        if not remote:
            raise H._winerr("VirtualAllocEx capture buffer failed")
        remote_base = int(C.cast(remote, C.c_void_p).value)
        state_addr = remote_base
        entries_addr = remote_base + HEADER_SIZE
        code_addr = remote_base + code_offset

        H.write_mem(k32, process, state_addr, b"\x00" * HEADER_SIZE)
        hook = build_capture_all_hook(
            code_addr, state_addr, entries_addr, capacity,
            module_base + HOOK_CONTINUE_RVA,
        )
        if len(hook) > CODE_SLACK:
            raise RuntimeError(f"generated hook is unexpectedly large: {len(hook)} bytes")
        H.write_mem(k32, process, code_addr, hook)
        k32.FlushInstructionCache(process, C.c_void_p(code_addr), len(hook))

        patch = abs_jmp(code_addr) + b"\x90"
        if len(patch) != len(HOOK_ORIGINAL):
            raise AssertionError("detour length changed")
        H.install_patch(k32, process, hook_addr, patch)
        patch_installed = True

        print(f"GoW.exe PID={pid} base=0x{module_base:X}")
        print(f"ALL-GameObject passive capture armed at final-token RVA 0x{HOOK_RVA:X}.")
        print(f"Capacity: {capacity:,} successful hashed decodes ({capacity * ENTRY_SIZE / 1048576:.1f} MiB).")
        print()
        print("Return to GoW now. Load/reload the saves and areas you want represented.")
        print("This records every successful hash-backed GameObject decode, not only Ravens.")
        if duration_seconds is None:
            input("When finished, return here and press ENTER to stop capture...")
        else:
            print(f"Capturing for {duration_seconds} seconds...")
            time.sleep(duration_seconds)

        H.install_patch(k32, process, hook_addr, HOOK_ORIGINAL)
        patch_installed = False
        time.sleep(0.05)

        reservations, overflow_flag = struct.unpack("<II", H.read_mem(k32, process, state_addr, 8))
        stored_count = min(reservations, capacity)
        raw = H.read_mem(k32, process, entries_addr, stored_count * ENTRY_SIZE) if stored_count else b""
        rows, conflicts = deduplicate(raw, stored_count)

        registry_pairs: dict[str, set[int]] = {}
        for row in rows:
            registry_pairs.setdefault(str(row["registry_hash_hex"]), set()).add(int(row["registry"]))
        registry_map = [
            {"registry_hash_hex": h, "numeric_registries": sorted(ids)}
            for h, ids in sorted(registry_pairs.items())
        ]

        document = {
            "schema": "completionist-map.gameobject-decode-dictionary.v1",
            "captured_utc": captured_at.isoformat(),
            "source": "passive in-thread capture of every successful hash-backed decode at GoW.exe RVA 0x5493F1",
            "scope": {
                "category_filter": None,
                "note": (
                    "Category-agnostic runtime dictionary. A mapping is present only if GoW "
                    "naturally decoded that record while this hook was armed."
                ),
            },
            "exe": {
                "path": exe_path,
                "sha256": actual_sha,
                "pid": pid,
                "module_base_hex": f"0x{module_base:X}",
            },
            "capture": {
                "hook_rva_hex": f"0x{HOOK_RVA:X}",
                "hook_original_bytes_hex": original.hex(),
                "capacity": capacity,
                "reservation_count": reservations,
                "stored_count": stored_count,
                "overflow": bool(overflow_flag or reservations > capacity),
                "unique_mapping_count": len(rows),
                "duplicate_hit_count": max(0, stored_count - len(rows)),
                "conflict_count": len(conflicts),
                "unique_registry_hash_count": len(registry_pairs),
            },
            "registry_map": registry_map,
            "conflicts": conflicts,
            "mappings": rows,
        }

        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        write_tsv(output_tsv, rows)

        print()
        print(
            f"CAPTURE PASS: {stored_count:,} decode events -> {len(rows):,} unique mappings; "
            f"{len(registry_pairs):,} registry hashes; conflicts={len(conflicts)}; "
            f"overflow={document['capture']['overflow']}"
        )
        print(f"JSON: {output_json}")
        print(f"TSV:  {output_tsv}")
        if document["capture"]["overflow"]:
            raise RuntimeError(
                "capture buffer overflowed; evidence was written but is incomplete. "
                "Rerun with a larger --capacity."
            )
        if not rows:
            raise RuntimeError(
                "no successful hashed GameObject decodes were observed. "
                "Arm capture before loading/reloading a save."
            )
    finally:
        if patch_installed:
            try:
                H.install_patch(k32, process, hook_addr, HOOK_ORIGINAL)
                print("Passive hook removed; original GoW code restored.")
            except Exception as exc:
                print(f"WARNING: failed to restore hook site: {exc}", file=sys.stderr)
        if remote:
            if not k32.VirtualFreeEx(process, remote, 0, H.MEM_RELEASE):
                print("WARNING: VirtualFreeEx failed for capture buffer", file=sys.stderr)
        H._close(k32, process)


def self_test() -> None:
    code_addr = 0x7FF600100000
    state_addr = 0x7FF600200000
    entries_addr = state_addr + HEADER_SIZE
    hook = build_capture_all_hook(
        code_addr, state_addr, entries_addr, 1024,
        0x7FF600549400,
    )
    if len(abs_jmp(code_addr) + b"\x90") != len(HOOK_ORIGINAL):
        raise AssertionError("patch length mismatch")
    e1 = struct.pack("<QQQII", 1 | (238 << 1) | (1796 << 18), 0x4EC230253427B2B0, 1, 1, 0)
    e2 = struct.pack("<QQQII", 1 | (238 << 1) | (1810 << 18), 0x4EC230253427B2B0, 2, 1, 0)
    rows, conflicts = deduplicate(e1 + e1 + e2, 3)
    assert len(rows) == 2
    assert not conflicts
    assert sorted(r["hits"] for r in rows) == [1, 2]
    print(f"SELF-TEST PASS: general hook bytes={len(hook)}, ring-entry aggregation valid")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--output-tsv", type=Path)
    ap.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY)
    ap.add_argument("--duration-seconds", type=int)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if args.output_json is None or args.output_tsv is None:
            ap.error("--output-json and --output-tsv are required unless --self-test is used")
        capture(args.output_json.resolve(), args.output_tsv.resolve(), args.capacity, args.duration_seconds)
        return 0
    except KeyboardInterrupt:
        print("ERROR: capture interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
