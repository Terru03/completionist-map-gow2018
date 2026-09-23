#!/usr/bin/env python3
"""Read only Ship Head evidence gate. Never emit runtime markers from guesses."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import raven_catalogue as raven


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def assess(catalogue: dict, audit: dict) -> dict:
    require(hashlib.sha256(canonical_json(catalogue).encode()).hexdigest()
            == audit["catalogue_sha256"], "catalogue/audit digest differs")
    rows = [row for row in catalogue["collectibles"]
            if row["family"] == "artefact" and row.get("subtype") == "Ship Head"]
    require(len(rows) == 9, "Ship Head physical census differs")
    accounting = audit["ship_head_accounting"]
    require(accounting["physical_placements"] == 9 and
            accounting["state_carriers"] == 9 and
            accounting["exhaustive_transform_paths"] == 13 and
            accounting["tracked_target"] == 10 and
            accounting["target_discrepancy_result"] == "BLOCKED_EXACT_REASON_UNKNOWN",
            "Ship Head native accounting differs")

    numbers: set[int] = set()
    placements: set[str] = set()
    marker_uids: set[str] = set()
    instance_keys: set[str] = set()
    path_count = 0
    result = []
    summaries = audit["tracked_summary_targets"]
    for row in rows:
        native, progress, source = row["native"], row["progression"], row["source"]
        number_list = native["numbered_object_evidence"]
        require(len(number_list) == 1 and 1 <= number_list[0] <= 9,
                "Ship Head number lacks exact object proof")
        number = number_list[0]
        require(number not in numbers, f"Ship Head number {number} repeats")
        numbers.add(number)
        physical = native["instance_guid"]
        require(GUID.fullmatch(physical) is not None and physical not in placements,
                f"Ship Head {number}: physical identity differs")
        placements.add(physical)
        require(row["catalogue_id"] == "artefact_" + physical.replace("-", ""),
                f"Ship Head {number}: catalogue identity differs")
        parent = progress["parent_quest"]
        require(progress["parent_quest_source"] == "exact_native_object_attribute" and
                parent in native["attribute_values"] and "Shiphead" in parent and
                parent in summaries,
                f"Ship Head {number}: native parent attribute missing")
        require(row["realm_id"] == summaries[parent]["realm_id"] and
                row["region_id"] == summaries[parent]["region_id"],
                f"Ship Head {number}: native summary region differs")
        require(progress["state_adapter"] == "interact_loot_artifact_checkpoint_state" and
                progress["field"] == "state == ACQUIRED" and
                progress["unloaded_query"] == "unresolved" and
                progress["read_only"] is True,
                f"Ship Head {number}: state claim changed")
        require(native["script_guid"] and "Ship Head" in native["attribute_values"],
                f"Ship Head {number}: artefact script proof missing")
        require(len(source["wad_sha256"]) == 64 and
                len(native["carrier_transform_paths"]) >= 1,
                f"Ship Head {number}: source path missing")
        paths = native["carrier_transform_paths"]
        path_count += len(paths)
        carrier_guids = {p["state_carrier_guid"] for p in paths}
        require(carrier_guids == set(native["state_carrier_guids"]),
                f"Ship Head {number}: carrier set differs")
        expected_keys = {f"{physical}.{guid}" for guid in carrier_guids}
        require(set(progress["instance_keys"]) == expected_keys and
                len(progress["instance_keys"]) == len(expected_keys),
                f"Ship Head {number}: proposed keys differ from carrier paths")
        for path in paths:
            require(path["physical_instance_guid"] == physical and
                    path["wad"] == source["wad"] and
                    path["world_position"] == row["marker"]["position_world"] and
                    path["transform_chain"],
                    f"Ship Head {number}: transform path differs")
        for key in expected_keys:
            require(key not in instance_keys, f"Ship Head {number}: state key repeats")
            instance_keys.add(key)
        uid = row["marker"]["uid"]
        require(uid not in marker_uids, f"Ship Head {number}: marker UID repeats")
        marker_uids.add(uid)
        result.append({
            "number": number,
            "catalogue_id": row["catalogue_id"],
            "wad": source["wad"],
            "physical_guid": physical,
            "carrier_guids": sorted(carrier_guids),
            "proposed_instance_keys": sorted(expected_keys),
            "parent_quest": parent,
            "world_position": row["marker"]["position_world"],
            "transform_paths": len(paths),
            "native_parent_attribute_proven": False,
            "serialized_save_lookup_proven": False,
            "native_marker_suppression_proven": False,
            "ship_specific_art_proven": False,
        })
    require(numbers == set(range(1, 10)), "Ship Head numbered census incomplete")
    require(path_count == 13, "Ship Head transform path census differs")
    require(len(instance_keys) == 13, "Ship Head proposed key census differs")
    result.sort(key=lambda item: item["number"])
    return {
        "schema": 1,
        "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "physical_count": len(result),
        "transform_path_count": path_count,
        "proposed_instance_key_count": len(instance_keys),
        "native_target": 10,
        "rows": result,
        "blockers": [
            "native target 10 versus nine physical objects lacks exact explanation",
            "per-object serialized save lookup and unloaded state are unproved",
            "native map pin and world marker suppression paths are unproved",
            "Ship Head specific map and world artwork and resource IDs are unproved",
        ],
    }


def verify_native_parent_attributes(catalogue: dict, report: dict,
                                    game_root: Path = GAME) -> None:
    """Recheck each parent literal in its own pinned script override record."""
    source_rows = {row["catalogue_id"]: row for row in catalogue["collectibles"]
                   if row["family"] == "artefact" and row.get("subtype") == "Ship Head"}
    by_wad: dict[str, list[dict]] = {}
    for row in report["rows"]:
        by_wad.setdefault(row["wad"], []).append(row)
    for wad_name, proof_rows in sorted(by_wad.items()):
        path = game_root / "exec/wad/pc_le" / wad_name
        raw = path.read_bytes()
        records = {record["id"].hex(): record for record in raven.parse_wad(raw)}
        for proof in proof_rows:
            source = source_rows[proof["catalogue_id"]]
            require(hashlib.sha256(raw).hexdigest() == source["source"]["wad_sha256"],
                    f"{wad_name}: shipped WAD digest differs")
            override = records.get(source["native"]["override_record_id"])
            require(override is not None and
                    override["offset"] == int(source["source"]["override_offset"], 16)
                    and override["name"].lower() == "goartifactscript_overrideinst",
                    f"{wad_name}: exact script override record differs")
            data = override["data"]
            require(proof["parent_quest"].encode() + b"\0" in data and
                    b"Ship Head\0" in data,
                    f"{wad_name}: parent quest not on own script override")
            proof["native_parent_attribute_proven"] = True
    report["native_parent_attribute_count"] = sum(
        row["native_parent_attribute_proven"] for row in report["rows"])


def require_generation_ready(report: dict) -> None:
    if not report["runtime_generation_allowed"]:
        raise ValueError("Ship Head generation blocked: " + "; ".join(report["blockers"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--game-root", type=Path, default=GAME)
    args = parser.parse_args()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = assess(catalogue, audit)
    verify_native_parent_attributes(catalogue, report, args.game_root)
    report["source_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CATALOGUE, AUDIT)
    }
    if args.output:
        target = args.output.resolve()
        require(target != REPO and REPO in target.parents,
                "output must stay inside repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(report), encoding="utf-8")
    print(f"SHIP_HEAD_STATIC_GATE {report['status']} "
          f"physical={report['physical_count']}/9 paths={report['transform_path_count']}/13 "
          f"save_lookup=0/9")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
