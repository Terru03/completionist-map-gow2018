#!/usr/bin/env python3
"""Map selected pins to state research. Unproved rows stay unknown."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import artefact_saved_state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("completion_locations", HERE / "build-collectible-locations.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
OUTPUT = ROOT / "config/collectibles/v0.10.5/completion-bindings.json"
CHESTS = ROOT / "catalogue/legendary-chest-authority.json"
STANDARD_CHESTS = ROOT / "catalogue/standard-chest-authority.json"
ARTEFACTS = artefact_saved_state.AUTHORITY


def validate(bindings: list[dict], selected: list[dict]) -> None:
    expected = {r["catalogue_id"]: r for r in selected}
    ids = [b["catalogue_id"] for b in bindings]
    builder.need(len(ids) == len(set(ids)) and set(ids) == set(expected),
                 "binding IDs must equal selected IDs exactly once")
    owners = set()
    for binding in bindings:
        cid = binding["catalogue_id"]
        builder.need(binding["family"] == expected[cid]["family"], f"family differs: {cid}")
        builder.need(isinstance(binding["source_wad"], str) and binding["source_wad"].endswith(".wad"),
                     f"source WAD missing: {cid}")
        status, keys = binding["status"], binding["instance_keys"]
        builder.need(status in {"unproved", "proved"}, f"invalid proof status: {cid}")
        builder.need(isinstance(keys, list) and all(isinstance(k, str) and k.strip() for k in keys),
                     f"invalid instance keys: {cid}")
        builder.need(len(keys) == len(set(keys)), f"duplicate instance key: {cid}")
        if status == "unproved":
            builder.need(not keys and binding["predicate"] is None,
                         f"unproved row has active state binding: {cid}")
        else:
            builder.need(keys and isinstance(binding["predicate"], dict) and binding["predicate"]
                         and isinstance(binding["evidence"], dict) and binding["evidence"],
                         f"proved row lacks keys, predicate, or evidence: {cid}")
        for key in keys:
            owner = (binding["source_wad"].lower(), key.casefold())
            builder.need(owner not in owners, f"duplicate or conflicting owner key: {cid}")
            owners.add(owner)


def build(include_proved: bool = True) -> dict:
    rows, _, excluded = builder.definitions()
    chest_rows = json.loads(CHESTS.read_text(encoding="utf-8"))["rows"] if include_proved else []
    chests = {r["catalogue_id"]: r for r in chest_rows}
    std_rows = json.loads(STANDARD_CHESTS.read_text(encoding="utf-8"))["rows"] if include_proved else []
    standard_chests = {r["catalogue_id"]: r for r in std_rows}
    artefacts = {r['catalogue_id']: r for r in artefact_saved_state.load()} if include_proved else {}
    bindings = []
    for row in sorted(rows, key=lambda r: r["catalogue_id"]):
        source_paths = deepcopy(row.get("sources") or [row["source"]])
        native, progression = row.get("native", {}), row.get("progression", {})
        bindings.append({
            "catalogue_id": row["catalogue_id"], "family": row["family"],
            "status": "unproved", "source_wad": source_paths[0]["wad"],
            "instance_keys": [], "predicate": None,
            "evidence": {
                "kind": "catalogue_source_lead_only",
                "source_catalogue": (builder.ADDITIONAL if "sources" in row else builder.CATALOGUE)
                    .relative_to(ROOT).as_posix(),
                "source_paths": source_paths,
                "placement_record_id": row.get("placement", {}).get("record_id")
                    or native.get("placement_final_record_id"),
                "placement_name": row.get("placement", {}).get("name")
                    or native.get("placement_object_name"),
                "carrier_transform_paths": deepcopy(native.get("carrier_transform_paths", [])),
                "candidate_instance_keys": deepcopy(progression.get("instance_keys", [])),
                "candidate_predicate": progression.get("field"),
                "candidate_adapter": progression.get("state_adapter"),
                "remaining_proof": "exact saved owner, completion predicate, current-save delivery, reload and older-save proof",
            },
        })
        if row["catalogue_id"] in chests:
            chest = chests.pop(row["catalogue_id"])
            builder.need(row["family"] == "legendary_chest" and
                         chest["wad"] == source_paths[0]["wad"] and
                         chest["source_wad_sha256"] == source_paths[0]["wad_sha256"] and
                         chest["physical_guid"] == native["instance_guid"],
                         f"archived chest identity differs: {row['catalogue_id']}")
            bindings[-1].update({
                "status": "proved", "instance_keys": [chest["state_path"]],
                "predicate": {"field": "state", "type": "number", "equals": 4},
                "native_identity": {k: chest[k] for k in
                    ("registry_hash", "object_hash", "serialized_key")},
            })
            bindings[-1]["evidence"].update({
                "kind": "exact_identity_and_archived_decoder",
                "authority_source": CHESTS.relative_to(ROOT).as_posix(),
                "fixture_observed": chest["fixture_observed"],
                "live_validation": "pending",
                "remaining_proof": "current-save delivery, reload and older-save validation",
            })
        if row["catalogue_id"] in standard_chests:
            chest = standard_chests.pop(row["catalogue_id"])
            bindings[-1].update({
                "status": "proved", "instance_keys": [chest["serialized_key"]],
                "predicate": {"field": "state", "type": "number", "equals": 4},
                "native_identity": {k: chest[k] for k in
                    ("registry_hash", "object_hash", "serialized_key")},
            })
            bindings[-1]["evidence"].update({
                "kind": "exact_identity_and_archived_decoder",
                "authority_source": STANDARD_CHESTS.relative_to(ROOT).as_posix(),
                "fixture_observed": True,
                "fixture_state": chest["fixture_state"],
                "live_validation": "pending",
                "remaining_proof": "current-save delivery, reload and older-save validation",
            })
        if row['catalogue_id'] in artefacts:
            artefact = artefacts.pop(row['catalogue_id'])
            bindings[-1].update({
                'status': 'proved', 'instance_keys': [artefact['state_path']],
                'predicate': {'field': 'state', 'type': 'number', 'equals': 3},
                'native_identity': {k: artefact[k] for k in ('registry_hash', 'object_hash', 'serialized_key')},
            })
            bindings[-1]['evidence'].update({
                'kind': 'exact_identity_and_archived_decoder',
                'authority_source': ARTEFACTS.relative_to(ROOT).as_posix(),
                'fixture_observed': True,
                'fixture_state': artefact['fixture_state'],
                'live_validation': 'current_save_read; paired_collection_and_save_switch_pending',
                'remaining_proof': 'installed delivery, collection, reload and older-save validation',
            })
    builder.need(not chests, "archived chest has no selected marker")
    builder.need(not standard_chests, "archived standard chest has no selected marker")
    builder.need(not artefacts, 'archived artefact has no selected marker')
    validate(bindings, rows)
    inputs = [builder.CATALOGUE, builder.ADDITIONAL, builder.CATEGORIES, CHESTS, STANDARD_CHESTS, ARTEFACTS,
              HERE / 'artefact_saved_state.py',
              HERE / "build-collectible-locations.py", Path(__file__)]
    contract_rows = [{k: b.get(k) for k in
                     ("catalogue_id", "source_wad", "instance_keys", "predicate", "native_identity")}
                    for b in bindings]
    return {
        "schema": 1, "kind": "COLLECTIBLE_COMPLETION_BINDINGS",
        "unproved_state": "unknown", "unknown_visible": True,
        "selected_count": len(bindings), "excluded_count": len(excluded),
        "family_counts": dict(sorted(Counter(b["family"] for b in bindings).items())),
        "contract": hashlib.sha256(json.dumps(contract_rows, sort_keys=True,
                            separators=(",", ":")).encode()).hexdigest(),
        "input_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in inputs},
        "bindings": bindings, "excluded": excluded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="Check saved output without writes")
    args = parser.parse_args()
    content = (json.dumps(build(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.check:
        builder.need(args.output.read_bytes() == content, "completion bindings differ; regenerate")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print("COMPLETION_BINDINGS_OK " + str(dict(Counter(b["status"] for b in build()["bindings"]))))


if __name__ == "__main__":
    main()
