#!/usr/bin/env python3
"""Read only Nornir gate. Source placement alone never enables delivery."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def assess(catalogue: dict, audit: dict) -> dict:
    require(hashlib.sha256(canonical_json(catalogue).encode()).hexdigest()
            == audit["catalogue_sha256"], "catalogue/audit digest differs")
    rows = catalogue["collectibles"]
    parents = [row for row in rows if row["family"] == "nornir_chest"]
    children = [row for row in rows if row["family"] in
                ("nornir_seal", "nornir_bell", "nornir_mechanism")]
    require(len(parents) == 22 and len(children) == 66,
            "Nornir physical/child census differs")
    require(Counter(row["family"] for row in children) ==
            {"nornir_seal": 30, "nornir_bell": 24, "nornir_mechanism": 12},
            "Nornir child type census differs")
    acc = audit["nornir_accounting"]
    require(acc["physical_placements"] == 22 and acc["tracked_target"] == 21
            and acc["exact_joined"] == acc["pass_exact"] == 0
            and acc["blocked_exact_reason_unknown"] == 22
            and acc["binding_method"] == "validated_exact_native_reference_chain_only",
            "Nornir binding accounting differs")
    for weak in ("region_or_count_inference_used", "target_count_is_join_authority",
                 "wad_filename_is_join_authority", "prior_claims_are_join_authority"):
        require(acc[weak] is False, f"weak Nornir join authority enabled: {weak}")
    by_id = {row["catalogue_id"]: row for row in parents}
    require(len(by_id) == 22, "Nornir parent IDs repeat")
    evidence = {row["catalogue_id"]: row for row in
                audit["nornir_exact_binding_evidence"]}
    require(len(evidence) == 22 and set(evidence) == set(by_id),
            "Nornir evidence does not cover every parent")
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for child in children:
        pid = child["progression"]["parent_catalogue_id"]
        require(pid in by_id and child["native"]["parent_catalogue_id"] == pid
                and child["native"]["parent_reference_source"]
                    == "exact_lua_table_attribute_on_parent_placement",
                f"Nornir child parent reference differs: {child['catalogue_id']}")
        by_parent[pid].append(child)
    result = []
    for pid, row in sorted(by_id.items()):
        native, progress, proof = row["native"], row["progression"], evidence[pid]
        require(len(by_parent[pid]) == 3,
                f"{pid}: expected three exact linked children")
        require(proof["final_status"] == "BLOCKED_EXACT_REASON_UNKNOWN" and
                proof["physical_instance_guid"] == native["instance_guid"] and
                proof["wad"] == row["source"]["wad"] and
                proof["physical_object"]["status"] == "PASS_EXACT",
                f"{pid}: physical or ownership evidence differs")
        require(progress["parent_quest"] is None and
                progress["parent_quest_source"] is None and
                progress["unloaded_query"] == "unresolved" and
                progress["field"] == "state == OPENED" and
                progress["state_adapter"] == "interact_chest_standard_checkpoint_state",
                f"{pid}: unproved parent state or quest promoted")
        require(proof["completion_state_oracle"]["unloaded_preinstall_state_status"]
                == "BLOCKED", f"{pid}: unloaded state proof changed")
        classification = proof["tracking_classification"]
        require(classification in ("unresolved_tracked_candidate",
                                   "level_scripted_untracked_triple_chest_reward"),
                f"{pid}: tracking class differs")
        result.append({
            "catalogue_id": pid,
            "wad": row["source"]["wad"],
            "physical_guid": native["instance_guid"],
            "proposed_instance_keys": progress["instance_keys"],
            "child_ids": sorted(child["catalogue_id"] for child in by_parent[pid]),
            "tracking_classification": classification,
            "proposed_region_summary_parent": proof["proposed_region_summary_parent"],
            "direct_native_binding_proven": False,
            "unloaded_state_proven": False,
        })
    require(Counter(row["tracking_classification"] for row in result) ==
            {"unresolved_tracked_candidate": 21,
             "level_scripted_untracked_triple_chest_reward": 1},
            "Nornir tracked candidate census differs")
    hel = audit["helheim_unjoined_nornir"]
    require(hel["result"] == "PASS_EXPLAINED" and
            hel["classification"] == "level_scripted_untracked_triple_chest_reward" and
            hel["physical_instance_guid"] == next(
                row["physical_guid"] for row in result if
                row["tracking_classification"] == "level_scripted_untracked_triple_chest_reward"),
            "Helheim exception evidence differs")
    return {
        "schema": 1,
        "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "physical_count": 22,
        "tracked_candidate_count": 21,
        "explained_untracked_count": 1,
        "linked_child_count": 66,
        "direct_native_binding_count": 0,
        "unloaded_state_count": 0,
        "rows": result,
        "blockers": [
            "21 tracked candidates lack exact chest-to-RegionSummary binding",
            "per-object serialized identity and unloaded OPENED lookup are unproved",
            "Nornir-specific marker resources and native suppression path are unproved",
        ],
    }


def require_generation_ready(report: dict) -> None:
    if not report["runtime_generation_allowed"]:
        raise ValueError("Nornir generation blocked: " + "; ".join(report["blockers"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = assess(catalogue, audit)
    report["source_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CATALOGUE, AUDIT)
    }
    report["source_lf_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in (CATALOGUE, AUDIT)
    }
    if args.output:
        target = args.output.resolve()
        require(target != REPO and REPO in target.parents,
                "output must stay inside repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(report), encoding="utf-8")
    print(f"NORNIR_STATIC_GATE {report['status']} "
          "physical=22 tracked=21 direct_bindings=0 linked_children=66")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
