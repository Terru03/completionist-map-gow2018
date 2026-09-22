#!/usr/bin/env python3
"""Derive all tracked Legendary Chest serialized GameObject identities.

Static/read-only. Uses:
1. the audited collectible catalogue;
2. the runtime/staged-proven Legendary identity-bearing transform rule;
3. the archived staged checkpoint inventory as an exact 32-row hash oracle.

No game process access, active-save reads, writes, or game-file modifications.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXPECTED_TRACKED = 33
EXPECTED_STAGED = 32
SIMPLE_STATE_CLASS = "0x75E050AB149B4062"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity = load_module(
    "_legendary_identity_helper",
    HERE / "legendary_chest_identity.py",
)


def simple_state_oracle(staged_report: dict) -> tuple[dict[str, set[int]], dict]:
    oracle: dict[str, set[int]] = {}
    details: dict[str, dict[int, dict]] = {}
    simple_total = 0

    for wad in staged_report.get("wads", []):
        name = str(wad.get("wad") or "").lower()
        if not name or not wad.get("capture_present"):
            continue

        hashes: set[int] = set()
        states: dict[int, dict] = {}
        class_keys = set()
        registry_hashes = set()

        for entry in wad.get("state_entries", []):
            signature = entry.get("field_signature") or []
            if signature != [{"name": "state", "value_tag": 1}]:
                continue
            parent = entry.get("parent") or {}
            if parent.get("record_class_key_hex") != SIMPLE_STATE_CLASS:
                continue
            go = parent.get("gameobject") or {}
            object_hash_hex = go.get("object_hash_hex")
            registry_hash_hex = go.get("registry_hash_hex")
            if not object_hash_hex or not registry_hash_hex:
                continue

            class_keys.add(parent["record_class_key_hex"])
            registry_hashes.add(registry_hash_hex)
            obj_hash = int(object_hash_hex, 16)
            hashes.add(obj_hash)
            states[obj_hash] = {
                "state_raw_hex": entry["state"]["raw_hex"],
                "state_u32": entry["state"]["decoded"],
                "state_row": entry.get("state_row"),
                "subobj_table_row": entry.get("subobj_table_row"),
            }

        if not hashes:
            continue

        expected_registry = f"0x{identity.registry_hash_for_wad(name):016X}"
        if class_keys != {SIMPLE_STATE_CLASS}:
            raise RuntimeError(
                f"{name}: simple state class keys changed: {sorted(class_keys)}"
            )
        if registry_hashes != {expected_registry}:
            raise RuntimeError(
                f"{name}: registry hash mismatch: {sorted(registry_hashes)} "
                f"!= {expected_registry}"
            )

        oracle[name] = hashes
        details[name] = states
        simple_total += len(hashes)

    return oracle, {
        "simple_state_parent_count": simple_total,
        "wad_count": len(oracle),
        "states": details,
    }


def build_identity_rows(
    rows: list[dict],
    oracle: dict[str, set[int]],
    oracle_details: dict[str, dict[int, dict]],
) -> list[dict]:
    output = []
    own = identity.CHEST_OWN_IDENTITY_ELEMENT

    for row in rows:
        scene, skipped = identity.scene_identity_elements(row)
        elements = scene + [own]
        object_hash = identity.identity_hash(elements)
        registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
        wad_key = row["source"]["wad"].lower()
        represented = wad_key in oracle
        staged_match = represented and object_hash in oracle[wad_key]
        state = oracle_details.get(wad_key, {}).get(object_hash)

        output.append({
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "instance_guid": row["native"]["instance_guid"],
            "state_instance_guid": row["native"]["state_instance_guid"],
            "identity_rule": "legendary_runtime_staged_structural_v1",
            "scene_identity_elements_hex": [item.hex() for item in scene],
            "skipped_transform_nodes": skipped,
            "own_identity_element_hex": own.hex(),
            "identity_elements_hex": [item.hex() for item in elements],
            "registry_hash_hex": f"0x{registry_hash:016X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "serialized_flag1_hex": identity.serialized_payload(
                registry_hash,
                object_hash,
            ).hex(),
            "staged_represented": represented,
            "staged_simple_state_match": staged_match,
            "staged_state": state,
        })

    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path)  # retained for runner compatibility
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--staged-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    rows = identity.tracked_rows(catalogue)
    if len(rows) != EXPECTED_TRACKED:
        raise RuntimeError(
            f"expected {EXPECTED_TRACKED} tracked rows, got {len(rows)}"
        )

    staged_report = json.loads(
        args.staged_report.read_text(encoding="utf-8")
    )
    oracle, oracle_meta = simple_state_oracle(staged_report)

    identities = build_identity_rows(
        rows,
        oracle,
        oracle_meta["states"],
    )

    represented = [row for row in identities if row["staged_represented"]]
    matched = [row for row in represented if row["staged_simple_state_match"]]
    unstaged = [row for row in identities if not row["staged_represented"]]

    if len(represented) != EXPECTED_STAGED:
        raise RuntimeError(
            f"expected {EXPECTED_STAGED} represented rows, got {len(represented)}"
        )
    if len(unstaged) != EXPECTED_TRACKED - EXPECTED_STAGED:
        raise RuntimeError(
            f"expected one unstaged tracked row, got {len(unstaged)}"
        )

    exact = len(matched) == EXPECTED_STAGED
    unique_hashes = len({row["object_hash_hex"] for row in identities})
    if unique_hashes != EXPECTED_TRACKED:
        raise RuntimeError(
            f"derived Legendary object hashes are not unique: "
            f"{unique_hashes}/{EXPECTED_TRACKED}"
        )

    status = (
        "EXACT_32_OF_32_STAGED_BINDING"
        if exact
        else "STRUCTURAL_RULE_STAGED_MISMATCH"
    )

    winner = {
        "scene_grammar": "legendary_runtime_staged_structural_v1",
        "prototype_identity_hex": identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
        "match_count": len(matched),
        "miss_count": EXPECTED_STAGED - len(matched),
        "evidence": (
            "live xpl250 slot-880 vector plus unique 32-row staged subset proof"
        ),
    }

    report = {
        "schema": 2,
        "analysis": (
            "legendary_serialized_gameobject_identity_structural_resolution"
        ),
        "status": status,
        "tracked_catalogue_count": len(rows),
        "staged_represented_count": len(represented),
        "simple_state_oracle": {
            "class_key_hex": SIMPLE_STATE_CLASS,
            "parent_count": oracle_meta["simple_state_parent_count"],
            "wad_count": oracle_meta["wad_count"],
        },
        "identity_rule": {
            "name": "legendary_runtime_staged_structural_v1",
            "own_identity_element_hex": (
                identity.CHEST_OWN_IDENTITY_ELEMENT.hex()
            ),
            "placement_source": "native.placement_final_record_id",
            "outer_scene_owner_suffixes": [
                "_ents",
                "_ents_nooffset",
                "_ents_offset",
                "_cbt",
            ],
            "omit_outer_organizational_wrappers": True,
            "omit_nested_parent_containers": True,
            "retain_nested_non_parent_chest_objects": True,
        },
        # Compatibility fields retained for the existing proof runner.
        "prototype_candidate_count": 1,
        "score_count": 1,
        "best_match_count": len(matched),
        "best_score_tie_count": 1 if exact else 0,
        "unique_exact_binding": exact,
        "winner": winner,
        "top_scores": [winner],
        "identities": identities,
        "unstaged_catalogue_ids": [
            row["catalogue_id"] for row in unstaged
        ],
        "state_semantics_proven": False,
        "safety": {
            "static_game_files_read_only": True,
            "archived_checkpoint_only": True,
            "process_accessed": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_files_written": False,
            "raven_runtime_modified": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "Completionist Map - Legendary serialized GameObject identity resolution",
        f"status={status}",
        (
            f"tracked={len(rows)} represented={len(represented)} "
            f"staged_matches={len(matched)}/{EXPECTED_STAGED}"
        ),
        (
            "identity_rule=legendary_runtime_staged_structural_v1 "
            f"own={identity.CHEST_OWN_IDENTITY_ELEMENT.hex()}"
        ),
        (
            f"simple_state_parents={oracle_meta['simple_state_parent_count']} "
            f"unique_object_hashes={unique_hashes}"
        ),
        (
            "unstaged_catalogue_ids="
            + ",".join(row["catalogue_id"] for row in unstaged)
        ),
        "state_semantics_proven=false",
        "",
        "IDENTITIES",
    ]
    for row in identities:
        state_text = (
            f" state_u32={row['staged_state']['state_u32']} "
            f"state_raw={row['staged_state']['state_raw_hex']}"
            if row["staged_state"] is not None
            else " state=absent_from_frozen_capture"
        )
        lines.append(
            f"{row['catalogue_id']} object_hash={row['object_hash_hex']} "
            f"payload={row['serialized_flag1_hex']} wad={row['wad']}"
            f"{state_text}"
        )

    lines += [
        "",
        "SAFETY",
        "static_game_files_read_only=true",
        "archived_checkpoint_only=true",
        "process_accessed=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "LEGENDARY_SERIALIZED_IDENTITY_STATIC_RESOLUTION_COMPLETE "
        f"status={status} staged={len(matched)}/{EXPECTED_STAGED} "
        f"derived={len(identities)}"
    )
    print(
        "process_accessed=false active_save_opened=false "
        "save_or_progression_written=false raven_runtime_modified=false"
    )
    return 0 if exact else 2


if __name__ == "__main__":
    raise SystemExit(main())
