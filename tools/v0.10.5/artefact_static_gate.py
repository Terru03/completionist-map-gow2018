#!/usr/bin/env python3
"""Read-only Artefact census gate. Ship Head evidence stays subtype-specific."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"
SHIP_GATE = REPO / "docs/research/ship-head-static-gate.json"
PARENT_AUDIT = REPO / "docs/research/artefact-cross-subtype-parent-audit.json"
SUBTYPE_COUNTS = {"Ship Head": 9, "Mask": 9, "Alfheim": 6, "Cup": 6,
                  "Horn": 6, "Brooch": 5, "Toy": 4}
SCRIPT_GUID = "d5bbc5bf-4ba5-a0c5-897e-46985b01a28e"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def assess(catalogue: dict, audit: dict, ship_gate: dict, parent_audit: dict) -> dict:
    require(hashlib.sha256(canonical_json(catalogue).encode()).hexdigest() ==
            audit["catalogue_sha256"], "catalogue/audit digest differs")
    rows = [row for row in catalogue["collectibles"] if row["family"] == "artefact"]
    require(len(rows) == audit["physical_counts"]["artefact"] == 45,
            "Artefact physical census differs")
    require(Counter(row["subtype"] for row in rows) == SUBTYPE_COUNTS,
            "Artefact subtype census differs")
    require(ship_gate["status"] == "BLOCKED_FAIL_CLOSED" and
            ship_gate["runtime_generation_allowed"] is False and
            ship_gate["physical_count"] == 9 and ship_gate["native_target"] == 10 and
            ship_gate["native_parent_attribute_count"] == 9 and
            ship_gate["acquired_state_numeric_proven"] is True and
            ship_gate["acquired_state_numeric"] == 3,
            "Ship Head evidence gate differs or grants delivery")
    ship_by_id = {row["catalogue_id"]: row for row in ship_gate["rows"]}
    require(len(ship_by_id) == 9 and
            set(ship_by_id) == {row["catalogue_id"] for row in rows if row["subtype"] == "Ship Head"},
            "Ship Head evidence IDs differ")
    require(audit["tracked_physical_counts"]["artefact"] == 9 and
            audit["native_tracked_target_totals"]["artefact_shiphead"] == 10,
            "Artefact accounting differs")
    require(parent_audit["status"] == "TWO_CROSS_SUBTYPE_REGION_INFERENCES_REJECTED" and
            parent_audit["runtime_generation_allowed"] is False and
            parent_audit["catalogue_lf_sha256"] == hashlib.sha256(
                canonical_json(catalogue).encode()).hexdigest(),
            "Artefact parent inference audit differs")
    rejected = {item["catalogue_id"]: item for item in parent_audit["rows"]}
    require(set(rejected) == {
        "artefact_989065ff4bde64f5ec957da2759037cb",
        "artefact_c9b7e23040c21e2da5fe8ba4be8ad415",
    } and all(item["parent_present_in_exact_override"] is False and
              item["searched_parent"] == "RegionSummary_CALS_Shiphead_Parent"
              for item in rejected.values()),
            "cross-subtype parent evidence differs")

    ids: set[str] = set()
    placements: set[tuple[str, str]] = set()
    marker_uids: set[str] = set()
    output = []
    for row in sorted(rows, key=lambda item: item["catalogue_id"]):
        cid = row["catalogue_id"]
        native, source, progress = row["native"], row["source"], row["progression"]
        placement = (source["wad"].lower(), native["instance_guid"].lower())
        require(cid not in ids and placement not in placements,
                f"duplicate Artefact physical/catalogue identity: {cid}")
        ids.add(cid)
        placements.add(placement)
        uid = row["marker"]["uid"]
        require(uid not in marker_uids, f"duplicate Artefact marker UID: {uid}")
        marker_uids.add(uid)
        xyz = row["marker"]["position_world"]
        require(len(xyz) == 3 and all(math.isfinite(value) for value in xyz) and
                len(source["wad_sha256"]) == 64 and
                native["object_name"] == "goartifactscript" and
                native["script_guid"] == SCRIPT_GUID and
                row["subtype"] in native["attribute_values"],
                f"Artefact physical/script evidence differs: {cid}")
        require(progress["field"] == "state == ACQUIRED" and
                progress["state_adapter"] == "interact_loot_artifact_checkpoint_state" and
                progress["unloaded_query"] == "unresolved" and
                progress["read_only"] is True,
                f"Artefact state gate differs: {cid}")
        if row["subtype"] == "Ship Head":
            proof = ship_by_id[cid]
            require(progress["parent_quest_source"] == "exact_native_object_attribute" and
                    progress["parent_quest"] == proof["parent_quest"] and
                    native["instance_guid"] == proof["physical_guid"] and
                    source["wad"] == proof["wad"] and
                    proof["native_parent_attribute_proven"] is True,
                    f"Ship Head direct parent evidence differs: {cid}")
            binding = "direct_native_shiphead_parent"
            frozen = proof["frozen_staged_identity_proven"]
        else:
            require(progress["parent_quest"] is None and
                    progress["parent_quest_source"] is None,
                    f"non-Ship-Head row has unproved parent: {cid}")
            if cid in rejected:
                negative = rejected[cid]
                require(negative["wad"] == source["wad"] and
                        negative["wad_sha256"] == source["wad_sha256"] and
                        negative["override_offset"] == source["override_offset"] and
                        negative["override_record_id"] == native["override_record_id"],
                        f"cross-subtype override evidence differs: {cid}")
            binding = "no_region_summary_binding_proven"
            frozen = False
        output.append({
            "catalogue_id": cid, "subtype": row["subtype"], "wad": source["wad"],
            "wad_sha256": source["wad_sha256"], "physical_id": native["instance_guid"],
            "world_position": xyz, "region_binding": binding,
            "parent_quest": progress["parent_quest"],
            "frozen_serialized_identity_proven": frozen,
            "persistent_unloaded_state_proven": False,
            "production_ready": False, "marker_generation_ready": False,
        })
    return {
        "schema": 1, "status": "BLOCKED_FAIL_CLOSED", "runtime_generation_allowed": False,
        "physical_count": len(output), "subtype_counts": dict(sorted(SUBTYPE_COUNTS.items())),
        "direct_shiphead_parent_count": 9, "other_artefact_unbound_count": 36,
        "shiphead_native_target": 10,
        "frozen_serialized_identity_count": sum(r["frozen_serialized_identity_proven"] for r in output),
        "persistent_unloaded_state_count": 0,
        "production_ready_count": 0,
        "rows": output,
        "blockers": [
            "Ship Head has 9 physical objects but native target 10; exact reason remains unknown",
            "36 other Artefacts lack direct region/accounting bindings",
            "persistent unloaded ACQUIRED state lookup is unproved for all 45",
            "Artefact subtype marker resources and native suppression paths are unproved",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = (CATALOGUE, AUDIT, SHIP_GATE, PARENT_AUDIT)
    report = assess(*(json.loads(path.read_text(encoding="utf-8")) for path in sources))
    report["source_sha256"] = {str(path.relative_to(REPO)).replace("\\", "/"):
                               hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    report["source_lf_sha256"] = {str(path.relative_to(REPO)).replace("\\", "/"):
                                  hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                  for path in sources}
    target = args.output.resolve()
    require(target != REPO and REPO in target.parents, "output must stay inside repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(report), encoding="utf-8")
    print("ARTEFACT_STATIC_GATE BLOCKED_FAIL_CLOSED physical=45 shiphead_direct=9 other_unbound=36 generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
