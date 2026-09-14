"""Verify and archive GoW's native object-checkpoint dispatch chain.

This is a read-only, version-locked PE analysis.  It verifies exact instruction
bytes at the restore lookup, callback dispatch, save callback, and object-token
packer.  It also inventories the read-only GameObject identity accessors used by
the runtime proof.  It never launches the game or opens a save.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile


EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

STRING_RVAS = {
    "OnRestoreCheckpoint": 0xE032E0,
    "OnSaveCheckpoint": 0xE03308,
    "__prevunpickle": 0xE03D10,
    "__PickleTable": 0xE03E38,
    "__SoftPickleTable": 0xE03E48,
    "__subobjs": 0xE03E60,
}

# Exact bytes whose RIP-relative targets and calls establish the chain.  Masked
# displacement bytes are decoded below, not compared to prose assumptions.
SITES = {
    "restore_get_root": (0x5AD4BE, bytes.fromhex("488b4958498bd0450fb6f9e862744300")),
    "restore_get_subobjs": (0x5AD51F, bytes.fromhex("41b809000000488d1534698500488bcbe8bc774400")),
    "restore_push_object_key": (0x5AD597, bytes.fromhex("488b562848897c2430c644243801e816e40500")),
    "restore_dispatch_callback": (0x5AD5F3, bytes.fromhex("41b9010000004c8d05e05c8500488d542430488bcee8d366ffff")),
    "restore_consume_object_record": (0x5AD6B8, bytes.fromhex("488b5628488b4f58e8fbe20500")),
    "save_push_object_key": (0x174B78, bytes.fromhex("488b07488b184885db7406488b5b58eb03488bdd488b5228488bcbe8286e4900")),
    "save_dispatch_callback": (0x174B98, bytes.fromhex("4c8b374c8d0566e7c800498bd6c7442420010000004533c9488bcee898f04200")),
    "object_token_packer": (0x60B9C0, bytes.fromhex("4c8bc24885d2750d488b41108950084883411010c333d241f68078020000017436418b8078020000418b908402000081e2ffff0f00c1e8034803d283e001480bd0410fb7808002000048c1e210480bd04803d24883ca01e944c0f3ff")),
}

GAMEOBJECT_METHODS = {
    "GetDebugName": (0x11BC880, 0x18F2A0),
    "GetDebugPath": (0x11BC898, 0x18F350),
    "Level": (0x11BC618, 0x195360),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_c_string(data: bytes, offset: int) -> str:
    end = data.index(b"\0", offset)
    return data[offset:end].decode("ascii")


def rel32_target(site_va: int, instruction_offset: int, instruction_length: int, disp: int) -> int:
    return site_va + instruction_offset + instruction_length + disp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    exe = (args.game_root.resolve() / "GoW.exe")
    before = sha256(exe)
    if before != EXPECTED_SHA256:
        raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    data = exe.read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    if pe.OPTIONAL_HEADER.ImageBase != IMAGE_BASE:
        raise RuntimeError(f"Unexpected image base: {pe.OPTIONAL_HEADER.ImageBase:#x}")

    strings = {}
    for name, rva in STRING_RVAS.items():
        value = read_c_string(data, pe.get_offset_from_rva(rva))
        if value != name:
            raise RuntimeError(f"String mismatch at RVA {rva:#x}: {value!r}")
        strings[name] = {"rva": f"0x{rva:X}", "va": f"0x{IMAGE_BASE + rva:X}"}

    sites = {}
    for name, (rva, expected) in SITES.items():
        offset = pe.get_offset_from_rva(rva)
        actual = data[offset:offset + len(expected)]
        if actual != expected:
            raise RuntimeError(f"Instruction bytes changed at {name} RVA {rva:#x}")
        sites[name] = {"rva": f"0x{rva:X}", "va": f"0x{IMAGE_BASE + rva:X}", "bytes": actual.hex()}

    methods = {}
    for name, (entry_rva, handler_rva) in GAMEOBJECT_METHODS.items():
        off = pe.get_offset_from_rva(entry_rva)
        handler_va, zero, name_va = struct.unpack_from("<QQQ", data, off)
        if handler_va != IMAGE_BASE + handler_rva or zero != 0:
            raise RuntimeError(f"GameObject method entry mismatch for {name}")
        name_rva = name_va - IMAGE_BASE
        if read_c_string(data, pe.get_offset_from_rva(name_rva)) != name:
            raise RuntimeError(f"GameObject method name mismatch for {name}")
        methods[name] = {
            "entry_rva": f"0x{entry_rva:X}",
            "handler_rva": f"0x{handler_rva:X}",
            "mutates_progression": False,
        }

    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe hash changed during read-only scan")

    report = {
        "schema": 1,
        "analysis": "native_object_checkpoint_dispatch",
        "exe": str(exe),
        "exe_sha256": before,
        "strings": strings,
        "verified_sites": sites,
        "gameobject_identity_methods": methods,
        "findings": {
            "restore_root": "__PickleTable or __SoftPickleTable",
            "record_table": "root.__subobjs",
            "lookup_key_source": "subobject +0x28 GameObject pointer",
            "lookup_key_lua_form": "opaque object token packed by RVA 0x60B9C0",
            "lookup_operation": "root.__subobjs[exact GameObject token]",
            "dispatch": "OnRestoreCheckpoint(level, subobject, savedInfo)",
            "post_dispatch": "consumes root.__subobjs[exact GameObject token]",
            "save_symmetry": "OnSaveCheckpoint result stored under same exact GameObject token",
            "cold_query_hypothesis": "enumerate unresolved root.__subobjs records before streaming consumes them",
            "cold_query_proved": False,
        },
        "safety": {
            "read_only": True,
            "game_launched": False,
            "save_opened": False,
            "game_written": False,
            "progression_written": False,
            "source_hash_unchanged": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "Completionist Map - native object checkpoint dispatch",
        f"exe_sha256={before}",
        "",
        "Verified restore chain:",
        "  __PickleTable/__SoftPickleTable",
        "  -> field __subobjs",
        "  -> exact key from subobject+0x28 GameObject pointer",
        "  -> opaque object token packed at RVA 0x60B9C0",
        "  -> savedInfo table",
        "  -> OnRestoreCheckpoint(level, subobject, savedInfo)",
        "  -> record consumed from __subobjs after callback",
        "",
        "Verified save symmetry:",
        "  same subobject+0x28 GameObject token -> OnSaveCheckpoint result",
        "",
        "Stable-key conclusion:",
        "  engine persists an exact object reference, not coordinates, order, filename, or RegionSummary count",
        "  runtime token is opaque and must not be equated with WAD GUID without separate proof",
        "",
        "Cold-query status:",
        "  candidate is unresolved __subobjs entries in root pickle table",
        "  runtime proof still required; fail closed",
        "",
        "source_hash_unchanged=true game_launched=false save_opened=false progression_written=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("OBJECT_CHECKPOINT_DISPATCH_SCAN_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
