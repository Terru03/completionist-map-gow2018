#!/usr/bin/env python3
"""Fail-closed Lore family gate from pinned catalogue and WAD evidence."""
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
BINDINGS = REPO / "docs/research/lore-native-bindings-audit.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def assess(catalogue: dict, audit: dict, bindings: dict) -> dict:
    digest = hashlib.sha256(canonical_json(catalogue).encode()).hexdigest()
    require(audit["catalogue_sha256"] == bindings["catalogue_lf_sha256"] == digest,
            "Lore source catalogue digest differs")
    rows = [row for row in catalogue["collectibles"] if row["family"] == "lore_marker"]
    require(len(rows) == audit["physical_counts"]["lore_marker"] == 43,
            "Lore physical census differs")
    require(Counter(row["subtype"] for row in rows) ==
            {"native_lore_marker": 40, "level_script_lore_marker": 3},
            "Lore subtype census differs")
    require(audit["tracked_physical_counts"]["lore_marker"] == 40 and
            audit["native_tracked_target_totals"]["lore_marker"] == 43,
            "Lore native accounting differs")
    require(bindings["status"] == "OBJECT_BINDINGS_PARTIAL" and
            bindings["runtime_generation_allowed"] is False and
            bindings["physical_count"] == 43 and
            bindings["direct_object_parent_count"] == 40 and
            bindings["level_script_context_count"] == 3,
            "Lore binding audit differs")
    proofs = {row["catalogue_id"]: row for row in bindings["rows"]}
    require(len(proofs) == len(bindings["rows"]) == 43 and
            set(proofs) == {row["catalogue_id"] for row in rows},
            "Lore proof IDs differ")
    seen_physical = set()
    seen_uid = set()
    output = []
    for row in sorted(rows, key=lambda item: item["catalogue_id"]):
        cid = row["catalogue_id"]
        native, source, progress, marker = (row["native"], row["source"],
                                             row["progression"], row["marker"])
        proof = proofs[cid]
        physical = (source["wad"].lower(), native["instance_guid"].lower())
        require(physical not in seen_physical and marker["uid"] not in seen_uid,
                f"duplicate Lore physical or marker identity: {cid}")
        seen_physical.add(physical)
        seen_uid.add(marker["uid"])
        require(proof["wad"] == source["wad"] and
                proof["wad_sha256"] == source["wad_sha256"] and
                proof["override_record_id"] == native["override_record_id"] and
                proof["override_offset"] == source["override_offset"] and
                proof["physical_id"] == native["instance_guid"] and
                proof["world_position"] == marker["position_world"],
                f"Lore physical proof differs: {cid}")
        require(len(marker["position_world"]) == 3 and
                all(math.isfinite(value) for value in marker["position_world"]) and
                len(source["wad_sha256"]) == 64 and
                progress["read_only"] is True and
                progress["unloaded_query"] == "unresolved" and
                proof["persistent_unloaded_state_proven"] is False and
                marker["map_resource"] == "goMapIconCompletionistLoreMarker" and
                marker["compass_class"] == "CompletionistLoreMarker",
                f"Lore state/marker gate differs: {cid}")
        if row["subtype"] == "native_lore_marker":
            require(proof["binding"] == "direct_object_attribute" and
                    proof["parent_quest"] == progress["parent_quest"] and
                    progress["parent_quest_source"] == "exact_native_object_attribute" and
                    progress["parent_quest"] in native["attribute_values"] and
                    progress["state_adapter"] == "langcheckruneread_checkpoint_state" and
                    progress["field"] == "mapSummaryComplete == true" and
                    native["identity_kind"] == "native_composite_component_key",
                    f"native Lore direct binding differs: {cid}")
        else:
            require(proof["binding"] == "level_script_callback_object_link_unproved" and
                    proof["parent_quest"] is None and
                    proof["proposed_script_parent"].startswith("RegionSummary_") and
                    proof["script_callback_literals_present"] is True and
                    progress["parent_quest"] is None and
                    progress["parent_quest_source"] is None and
                    progress["state_adapter"] == "level_script_checkpoint_boolean" and
                    progress["field"] in {"bRuneReadStarted == true", "wellRead == true"} and
                    progress["identity_status"] ==
                    "no_explicit_component_guid_in_object_override",
                    f"level Lore context falsely promoted: {cid}")
        output.append({
            "catalogue_id": cid, "subtype": row["subtype"],
            "wad": source["wad"], "wad_sha256": source["wad_sha256"],
            "physical_id": native["instance_guid"],
            "world_position": marker["position_world"],
            "region_binding": proof["binding"],
            "parent_quest": progress["parent_quest"],
            "proposed_script_parent": proof.get("proposed_script_parent"),
            "journal_ids": proof["journal_ids"],
            "state_adapter": progress["state_adapter"], "state_field": progress["field"],
            "persistent_unloaded_state_proven": False,
            "production_ready": False, "marker_generation_ready": False,
        })
    return {
        "schema": 1, "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False, "physical_count": 43,
        "subtype_counts": {"native_lore_marker": 40, "level_script_lore_marker": 3},
        "direct_object_parent_count": 40, "level_script_context_count": 3,
        "native_summary_target": 43, "external_guide_count_user_baseline": 39,
        "native_with_journal_id_count": sum(bool(row["journal_ids"]) and
                                             row["subtype"] == "native_lore_marker"
                                             for row in output),
        "persistent_unloaded_state_count": 0, "production_ready_count": 0,
        "rows": output,
        "blockers": [
            "3 level-script callback clues lack exact callback-to-physical-object binding",
            "43 native Summary targets differ from user-supplied external guide count 39; no physical row excluded",
            "persistent unloaded completion state query is unproved for both Lore state adapters",
            "Lore-specific native marker coverage, custom resource path, and suppression are unproved",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = (CATALOGUE, AUDIT, BINDINGS)
    report = assess(*(json.loads(path.read_text(encoding="utf-8")) for path in paths))
    report["source_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths}
    report["source_lf_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in paths}
    target = args.output.resolve()
    require(REPO in target.parents, "output must stay in repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(report), encoding="utf-8")
    print("LORE_STATIC_GATE BLOCKED_FAIL_CLOSED physical=43 direct=40 script_context=3 generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
