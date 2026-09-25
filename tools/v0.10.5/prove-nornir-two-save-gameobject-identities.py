#!/usr/bin/env python3
"""Tie two observed Nornir checkpoint hashes to physical loaded chest objects.

This reads the A0/B0 dumps and the static catalogue. It replays the verified
GameObject identity chain/hash calculation against the loaded WAD registry.
No process, game, or save write is performed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
EVIDENCE = REPO / "docs/research/nornir-two-save-checkpoint-evidence.json"
STAGES = {"A": "A0_before_runes", "B": "B0_before_chest_open"}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DUMPS = load_module(HERE / "analyze-nornir-two-save-dumps.py", "nornir_dump_reader")
IDENTITY = load_module(HERE / "capture-all-raven-gameobject-identities-readonly.py",
                       "gameobject_identity_reader")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def runtime_guid(hex_guid: str) -> bytes:
    """The loaded element decrements the source record's final LE u32."""
    raw = bytearray.fromhex(hex_guid.replace("-", ""))
    require(len(raw) == 16, f"bad static GUID: {hex_guid}")
    tail = (int.from_bytes(raw[12:16], "little") - 1) & 0xFFFFFFFF
    raw[12:16] = tail.to_bytes(4, "little")
    return bytes(raw)


class Reader:
    def __init__(self, dump):
        self.dump = dump
        self.read_count = 0

    def read(self, address: int, size: int) -> bytes:
        self.read_count += 1
        return self.dump.read_virtual(address, size)

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]


def staged_registry_id(dump, base: int, wad: str) -> int:
    count, = struct.unpack("<I", dump.read_virtual(base + DUMPS.RECORD_COUNT_RVA, 4))
    require(count <= DUMPS.MAX_RECORDS, "implausible staged record count")
    matches = []
    for index in range(count):
        record = dump.read_virtual(base + DUMPS.RECORD_BASE_RVA +
                                   index * DUMPS.RECORD_STRIDE, DUMPS.RECORD_STRIDE)
        name = record[0x84:0xA8].split(b"\0", 1)[0].decode("ascii", errors="replace")
        if name == wad:
            registry_id, = struct.unpack_from("<I", record, 0x24)
            matches.append(registry_id)
    require(len(matches) == 1, f"expected one staged {wad} registry key; got {matches}")
    return matches[0]


def registry_slots(dump, base: int, registry_id: int) -> tuple[int, tuple[int, ...]]:
    table = dump.read_virtual(base + IDENTITY.TABLE_BEGIN,
                              IDENTITY.TABLE_END - IDENTITY.TABLE_BEGIN)
    matches = []
    for descriptor, in struct.iter_unpack("<Q", table):
        if not descriptor:
            continue
        try:
            value, = struct.unpack("<I", dump.read_virtual(descriptor, 4))
        except ValueError:
            continue
        if value != registry_id:
            continue
        array, = struct.unpack("<Q", dump.read_virtual(descriptor + 8, 8))
        count, = struct.unpack("<I", dump.read_virtual(descriptor + 24, 4))
        require(count <= 1_048_576, "implausible GameObject registry size")
        matches.append((array, count))
    require(len(matches) == 1, f"expected one loaded registry {registry_id}; got {len(matches)}")
    array, count = matches[0]
    slots = struct.unpack(f"<{count}Q", dump.read_virtual(array, count * 8)) if count else ()
    return array, slots


def inspect(root: Path, observation: dict, chest_row: dict) -> dict:
    stage = STAGES[observation["save_label"]]
    dump = DUMPS.FullMemoryDump(root / f"{stage}.dmp")
    try:
        base = dump.module_base()
        registry_id = staged_registry_id(dump, base, observation["wad"])
        _, slots = registry_slots(dump, base, registry_id)
        reader = Reader(dump)
        chest_hash = int(observation["chest_object_hash_hex"], 16)
        runic_hash = int(observation["runic_parent_object_hash_hex"], 16)
        target_hashes = {"chest": chest_hash, "runic_parent": runic_hash}
        matches = {role: [] for role in target_hashes}
        for slot, obj in enumerate(slots):
            if not obj:
                continue
            try:
                elements, _ = IDENTITY.build_identity(reader, obj)
            except (ValueError, RuntimeError, struct.error):
                continue
            object_hash = IDENTITY.identity_hash(elements)
            for role, expected in target_hashes.items():
                if object_hash == expected:
                    matches[role].append({
                        "registry_id": registry_id,
                        "slot": slot,
                        "object_pointer": f"0x{obj:X}",
                        "object_hash_hex": f"0x{object_hash:016X}",
                        "identity_elements_hex": [part.hex() for part in elements],
                    })
        require(all(len(items) == 1 for items in matches.values()),
                f"checkpoint hash not uniquely loaded in {stage}: "
                f"{ {role: len(items) for role, items in matches.items()} }")
        chest = matches["chest"][0]
        runic = matches["runic_parent"][0]
        placement = runtime_guid(chest_row["native"]["placement_final_record_id"]).hex()
        chest_script = runtime_guid(chest_row["native"]["final_record_id"]).hex()
        parent_prototype = chest_row["native"]["parent_prototype_id"].lower()
        require(placement in chest["identity_elements_hex"] and
                chest_script in chest["identity_elements_hex"],
                f"opened chest hash does not carry exact catalogue placement/script: {stage}")
        require(placement in runic["identity_elements_hex"] and
                parent_prototype in runic["identity_elements_hex"],
                f"runic parent hash does not carry exact catalogue placement/prototype: {stage}")
        return {
            "save_label": observation["save_label"],
            "stage": stage,
            "wad": observation["wad"],
            "chest_catalogue_id": observation["chest_catalogue_id"],
            "registry_id": registry_id,
            "registry_slot_count": len(slots),
            "registry_nonnull_count": sum(bool(obj) for obj in slots),
            "runtime_placement_element_hex": placement,
            "runtime_chest_script_element_hex": chest_script,
            "catalogue_parent_prototype_element_hex": parent_prototype,
            "chest": chest,
            "runic_parent": runic,
            "exact_physical_to_checkpoint_hash_binding": True,
            "game_or_save_writes": False,
        }
    finally:
        dump.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root", type=Path)
    args = parser.parse_args()
    root = args.capture_root.resolve()
    require(root.is_dir(), f"capture directory missing: {root}")
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    rows = {row["catalogue_id"]: row for row in catalogue["collectibles"]}
    results = [inspect(root, observation, rows[observation["chest_catalogue_id"]])
               for observation in evidence["observations"]]
    report = {
        "schema": 1,
        "result": "TWO_NORNIR_PHYSICAL_CHECKPOINT_IDENTITIES_PROVED",
        "game_executable_sha256": evidence["game_executable_sha256"],
        "capture_root": str(root),
        "chests": results,
        "game_or_save_writes": False,
    }
    output = root / "gameobject-identity-proof.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NORNIR_GAMEOBJECT_IDENTITIES_PROVED chests={len(results)} report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
