"""Prove and bound offline Raven scheduler/registry provenance.

Read-only. Version locked to one GoW.exe and one canonical WAD. This tool
checks exact instruction bytes, SQLite call edges, WAD record ancestry, and
optional frozen-save string absence. It never opens active saves.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct


EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_WAD_SHA256 = "2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268"
TARGET_GUID = "95b9c644-4d47-9ac6-8207-b1829d02909b"
TARGET_INDEX = 9633
TARGET_OFFSET = 0x32E3C60
TARGET_ID = "44c6b995c69a474d82b107829c90029d"

# Full instruction bytes at every address cited as proof by this tool.
ANCHORS = {
    "constructor_wad_selector": (0x85A432, "0fb7410e"),
    "constructor_wad_group": (0x85A43B, "0fb7b9d8010000"),
    "constructor_existing_lookup": (0x85A489, "e882010000"),
    "constructor_type_116": (0x85A4D6, "41b816010000"),
    "constructor_resource_lookup": (0x85A4DF, "e8ac76bdff"),
    "constructor_outer_tail": (0x85A524, "488b0505d49600"),
    "constructor_wad_registry": (0x85A54B, "8b883c0c0000"),
    "constructor_outer_registry": (0x85A558, "894f10"),
    "constructor_outer_config": (0x85A55B, "48896f18"),
    "constructor_outer_wad": (0x85A568, "48897740"),
    "constructor_inner_tail": (0x85A5A5, "488b4608"),
    "constructor_config_array": (0x85A5B7, "488b4718"),
    "constructor_inner_config": (0x85A5C7, "49894010"),
    "constructor_inner_outer": (0x85A5CB, "49897818"),
    "lookup_outer_wad": (0x85A650, "488b4340"),
    "lookup_wad_selector": (0x85A654, "0fb7480e"),
    "scheduler_worker_call": (0x85AEE3, "e838d4ffff"),
    "worker_inner_config": (0x858440, "4c8b5f10"),
    "worker_variant_count": (0x858444, "458b5340"),
    "worker_variant_array": (0x85844D, "498b4b38"),
    "worker_variant_weight": (0x858468, "410fbe4210"),
    "worker_lcg": (0x85847E, "691d749a96006d4ec641"),
    "worker_config_mode": (0x858536, "488b7f10"),
    "worker_variant_name": (0x8585DF, "4883c14c"),
    "worker_type_352": (0x858695, "41b852030000"),
    "worker_resource_lookup": (0x8586A1, "e8ea94bdff"),
    "metadata_filename_key": (0x82D180, "488d8b84000000"),
    "metadata_strcmp": (0x82D187, "ff1593bd5100"),
    "metadata_existing_id": (0x82D1A9, "448b6324"),
    "metadata_existing_wad_store": (0x82D203, "4189853c0c0000"),
    "metadata_new_id": (0x82D31E, "83c212"),
    "metadata_new_id_store": (0x82D321, "4389540f24"),
    "metadata_context_ordinal": (0x82D34F, "4789640f28"),
    "slot_release_entry": (0x4EF110, "4c8bdc41574883ec60"),
    "slot_release_registry": (0x4EF21E, "418b9780020000"),
    "slot_release_bank_zero": (0x4EF27D, "4c892cc8"),
    "slot_release_live_count": (0x4EF281, "ff4a0c"),
}

EXPECTED_EDGES = {
    (0x85A489, 0x85A420, "call", 0x85A610),
    (0x85A4DF, 0x85A420, "call", 0x431B90),
    (0x85AEE3, 0x85AC27, "call", 0x858320),
    (0x8586A1, 0x858320, "call", 0x431B90),
    (0x4EF19B, 0x4EF173, "call", 0x4EF110),
    (0x54FF3E, 0x54FE80, "call", 0x4EF110),
    (0x60DA17, 0x60D9E0, "call", 0x4EF110),
    (0x60EA32, 0x60EA20, "call", 0x4EF110),
    (0x60ED16, 0x60ECB0, "call", 0x4EF110),
    (0x8100FB, 0x810000, "call", 0x4EF110),
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pe_reader(path: Path):
    raw = path.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    count = struct.unpack_from("<H", raw, pe + 6)[0]
    optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
    sections = pe + 24 + optional_size

    def read(rva: int, size: int) -> bytes:
        for index in range(count):
            row = sections + index * 40
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", raw, row + 8)
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                offset = raw_offset + rva - virtual_address
                return raw[offset:offset + size]
        raise RuntimeError(f"RVA 0x{rva:X} is not file backed")

    return read


def verify_anchors(exe: Path) -> dict:
    if sha256_path(exe) != EXPECTED_EXE_SHA256:
        raise RuntimeError("GoW.exe SHA256 mismatch")
    read = pe_reader(exe)
    for name, (rva, encoded) in ANCHORS.items():
        expected = bytes.fromhex(encoded)
        actual = read(rva, len(expected))
        if actual != expected:
            raise RuntimeError(f"{name} changed at RVA 0x{rva:X}: {actual.hex()}")
    return {"sha256": EXPECTED_EXE_SHA256, "anchors_verified": len(ANCHORS)}


def verify_edges(index: Path) -> dict:
    db = sqlite3.connect(f"file:{index.resolve().as_posix()}?mode=ro", uri=True)
    try:
        actual = set(db.execute("select site,src_fn,kind,dest from edges where site in (%s)" %
                                ",".join("?" for _ in EXPECTED_EDGES),
                                tuple(row[0] for row in EXPECTED_EDGES)))
    finally:
        db.close()
    missing = sorted(EXPECTED_EDGES - actual)
    if missing:
        raise RuntimeError(f"SQLite call edges changed: {missing}")
    release_callers = sorted(row[0] for row in actual if row[3] == 0x4EF110)
    return {"edges_verified": len(EXPECTED_EDGES), "slot_release_direct_callers": [f"0x{x:X}" for x in release_callers]}


def verify_wad(wad: Path) -> dict:
    if sha256_path(wad) != EXPECTED_WAD_SHA256:
        raise RuntimeError("target WAD SHA256 mismatch")
    catalogue = load_module("raven_catalogue.py", "offline_exhaustion_catalogue")
    raw = wad.read_bytes()
    records = catalogue.parse_wad(raw)
    target = records[TARGET_INDEX]
    override = records[TARGET_INDEX - 2]
    if target["offset"] != TARGET_OFFSET or target["id"].hex() != TARGET_ID:
        raise RuntimeError("canonical Raven record identity changed")
    if TARGET_GUID.encode("ascii") not in override["data"]:
        raise RuntimeError("canonical Raven GUID is not in exact override record")
    prototype = target["data"][0x0C:0x1C]
    prototype_hits = [
        {"index": i, "offset": f"0x{row['offset']:X}", "name": row["name"], "payload_offset": row["data"].find(prototype)}
        for i, row in enumerate(records) if prototype in row["data"]
    ]
    return {
        "sha256": EXPECTED_WAD_SHA256,
        "record_count": len(records),
        "override": {"index": TARGET_INDEX - 2, "offset": f"0x{override['offset']:X}", "name": override["name"]},
        "canonical": {"index": TARGET_INDEX, "offset": f"0x{target['offset']:X}", "id": target["id"].hex(),
                      "name": target["name"], "size": target["size"], "parent_index": target["parent"]},
        "prototype_id": prototype.hex(),
        "prototype_payload_hits": prototype_hits,
        "exact_record_to_scheduler_item_proved": False,
        "reason": "scheduler item holds type-0x116 config and selects a type-0x352 resource by variant name; it has no raw record ID or physical offset field",
    }


def scan_frozen_save(path: Path) -> dict:
    save = load_module("probe-known-raven-runtime-keys.py", "offline_exhaustion_save")
    name, digest, blob = save.validate_save(path)
    needles = {
        "filename_ascii": b"alf355_chiseldungeon.wad",
        "filename_utf16le": "alf355_chiseldungeon.wad".encode("utf-16le"),
        "wad_name_ascii": b"WAD_ALF355_CHISELDUNGEON",
        "wad_name_utf16le": "WAD_ALF355_CHISELDUNGEON".encode("utf-16le"),
    }
    counts = {label: blob.count(needle) for label, needle in needles.items()}
    validated = 0
    stream_counts = {label: 0 for label in needles}
    for offset in range(len(blob) - 1):
        if not save.valid_zlib_header(blob, offset):
            continue
        item = save.decompress_stream(blob, offset)
        if item is None:
            continue
        raw, _ = item
        validated += 1
        for label, needle in needles.items():
            stream_counts[label] += raw.count(needle)
    return {"backup": name, "sha256": digest, "raw_hits": counts,
            "validated_zlib_streams": validated, "zlib_hits": stream_counts}


def build_report(exe: Path, wad: Path, index: Path, saves: list[Path]) -> dict:
    return {
        "schema": 1,
        "analysis": "gow_offline_persistent_key_exhaustion",
        "executable": verify_anchors(exe),
        "sqlite_index": verify_edges(index),
        "wad": verify_wad(wad),
        "scheduler": {
            "outer_layout": {"registry_id": "0x10", "type_116_config": "0x18", "inner_sentinel": "0x20", "resource_hash": "0x30", "wad": "0x40"},
            "inner_layout": {"type_116_config_entry": "0x10", "outer": "0x18", "state": "0x20..0x40"},
            "construction_order": "outer tail insertion; inner tail insertion in type-0x116 config array order",
            "lookup_identity": "resolved WAD context pointer plus WAD+0x1D8",
            "selection": "LCG selects a weighted variant inside one fixed inner item; list order is unchanged",
            "physical_record_mapping": "unproved",
        },
        "metadata": {
            "existing_key": "strcmp(WAD path at [WAD+0x50]+0x54, record+0x84)",
            "existing_registry_id": "record+0x24",
            "new_registry_id": "current metadata count/index + 0x12",
            "record_plus_0x28": "current runtime WAD-context slot ordinal from 64-slot scan",
            "exact_registry_id": None,
            "reason": "metadata array is deserialized at runtime, then reconciled in current 64-slot WAD-context order; neither input order is present in WAD physical records",
        },
        "allocator": {
            "slot_release": "0x4EF110 clears selected flavor bank slot and decrements live count",
            "frees_before_target_ruled_out": False,
            "static_target_slot": None,
            "reason": "six direct release entry sites and runtime object lifetimes remain between fresh registry creation and unknown target scheduler item",
        },
        "frozen_saves": [scan_frozen_save(path) for path in saves],
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "precise_remaining_edge": "bind canonical override/final record pair to its loaded type-0x116 inner config entry and observe or reconstruct complete preceding same-registry allocation/free sequence",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--save", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.exe, args.wad, args.index, args.save)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"anchors_verified={report['executable']['anchors_verified']}")
    print(f"edges_verified={report['sqlite_index']['edges_verified']}")
    print(report["gameobject_persistent_key_status"])
    print(report["production_oracle_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
