#!/usr/bin/env python3
"""Stage chest map artwork without adding any Nornir HUD resources."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("map_only_base", HERE / "build-nornir-one-family-art-probe.py")
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
REPO = base.REPO
OUT = REPO / "build/nornir-map-only-art-probe/candidate/game-root"
REPORT = OUT.parents[1] / "report.json"
HUD = ("MDL_cm_nornir_chest_hud", "goProtoCompletionistNornirChestHUD",
       "gocompletionistnornirchesthud")


def map_only_wad(source: bytes, candidate: bytes) -> tuple[bytes, dict]:
    logical = base.logical
    raven = logical.parse_wad(source)
    records = logical.parse_wad(candidate)
    remove = set()
    for name in HUD:
        hits = [(i, r) for i, r in enumerate(records) if r["name"] == name and r["data"]]
        base.need(len(hits) == 1, "HUD payload missing or duplicated: " + name)
        _, row = hits[0]
        start = row["parent"]
        base.need(start is not None, "HUD group missing")
        end = logical.matching_group_end(records, start)
        remove.update(range(start, end + 1))
    base.need(sum(bool(records[i]["data"]) for i in remove) == 4,
              "expected HUD model/prototype/root plus embedded script")
    records = [r for i, r in enumerate(records) if i not in remove]
    heap, root = logical.payload_records(records)[:2]
    old_heap, old_root = logical.payload_records(raven)[:2]
    # Map chain only: material, model, prototype, instance, two texture defs.
    increments = {0xA: 1, 0x10001: 1, 0x20001: 1, 0x2000C: 1, 0x10015: 2}
    total = 0
    for row in logical.read_type_table(old_root["data"]):
        count = row["count"] + increments.get(row["key"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], total, count)
        total += count
    base.need(total == struct.unpack_from("<I", old_heap["data"], 4)[0] + 6,
              "map-only type count differs")
    struct.pack_into("<I", heap["data"], 4, total)
    struct.pack_into("<I", root["data"], 0x1C, total)
    output = logical.serialize_wad(records)
    parsed = logical.parse_wad(output)
    base.need(logical.serialize_wad(parsed) == output, "map-only WAD roundtrip differs")
    base.need(not any("nornir" in r["name"].lower() and "hud" in r["name"].lower()
                      for r in parsed), "Nornir HUD resource remains")
    base.need(len(logical.payload_records(parsed)) == len(logical.payload_records(raven)) + 8,
              "map-only physical payload count differs")
    # Remove the four new map groups, the four standalone texture records and
    # the map registration link; restoring accounting must recover all bytes.
    removal = set()
    map_names = {"MAT_cm_nornir_chest", "MDL_cm_nornir_chest",
                 "goProtoMapIconCompletionistNornirChest", "gomapiconcompletionistnornirchest"}
    for i, row in enumerate(parsed):
        if row["data"] and row["name"] in map_names:
            start = row["parent"]
            base.need(start is not None, "new map group absent")
            removal.update(range(start, logical.matching_group_end(parsed, start) + 1))
        elif row["data"] and row["name"].startswith("TX_cm_nornir_chest_"):
            removal.add(i)
        elif not row["data"] and row["name"] == "gomapiconcompletionistnornirchest" and row["kind"] == 1:
            removal.add(i)
    inverse = [r for i, r in enumerate(parsed) if i not in removal]
    for old, new in zip(logical.payload_records(raven)[:2], logical.payload_records(inverse)[:2]):
        new["data"] = copy.deepcopy(old["data"])
    base.need(logical.serialize_wad(inverse) == source, "map-only inverse differs from Raven")
    return output, {"exact_inverse_to_raven": True, "nornir_hud_resources": 0,
                    "added_physical_payloads": 8, "added_typed_payloads": 6,
                    "removed_hud_payloads": 4, "runtime_art_isolation_proven": False}


def build() -> tuple[dict[str, bytes], dict]:
    files, report = base.build()
    files[base.WAD], proof = map_only_wad((base.SOURCE / base.WAD).read_bytes(), files[base.WAD])
    report["variant"] = "MAP_ONLY_NO_NORNIR_HUD"
    report["proof"][base.WAD] = proof
    report["files"][base.WAD] = {"sha256": base.sha(files[base.WAD]), "bytes": len(files[base.WAD])}
    report["live_question"] = "Can the chest map chain render custom artwork beside Raven when no Nornir HUD chain is added?"
    return files, report


def main() -> None:
    files, report = build()
    for relative, raw in files.items():
        path = OUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("NORNIR_MAP_ONLY_ART_OFFLINE_BUILT")
    print(REPORT)


if __name__ == "__main__":
    main()
