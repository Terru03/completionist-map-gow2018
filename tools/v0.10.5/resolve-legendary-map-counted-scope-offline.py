#!/usr/bin/env python3
"""Resolve the map-counted Legendary Chest production set offline.

The original static catalogue contains 33 state-resolved physical Legendary
rows joined to RegionSummary parents by region-family inference. Native quest
targets show two overfull inferred groups (Riverpass +1, Helheim +1) and two
unfilled one-count groups (TyrsVault, TheHallofTyr).

This resolver keeps physical/state identity separate from map-counted
production eligibility. It:
- preserves all 33 previously solved identity rows as research evidence;
- removes two exact overflow physical placements from marker production;
- adds the two exact Caldera/Tyr physical placements that were previously
  unresolved;
- derives their serialized GameObject identities with the already accepted
  structural rule;
- replays their exact staged checkpoint carriers from the frozen capture;
- proves the corrected production set has 33 unique identities and matches every
  native Legendary RegionSummary target count exactly.

No game process, active save, progression, or game files are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENTITY_PATH = HERE / "legendary_chest_identity.py"
ANALYZE_PATH = HERE / "analyze-legendary-staged-state.py"

DEFAULT_CATALOGUE = (
    REPO / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"
)
DEFAULT_AUDIT = REPO / "docs" / "research" / "all-collectibles-native-audit.json"
DEFAULT_CAPTURE = (
    REPO / "archive" / "field-logs" / "runtime-captures"
    / "staged-wad-bitstream-raven-20260921-060345-c2c9bcc1"
)

RIVERPASS_OVERFLOW_ID = "legendary_chest_3c05899e46a619015d4cfb995fb61be0"
HELHEIM_OVERFLOW_ID = "legendary_chest_8266c175474b43a4d44938a75e21329d"
TYRS_VAULT_ID = "legendary_chest_d0b93e274754785e08235285bd6b78f2"
HALL_OF_TYR_ID = "legendary_chest_f714d2d845a3dd9e28808db4655e757f"

PRODUCTION_OVERRIDES = {
    TYRS_VAULT_ID: "RegionSummary_LegendaryChest_Parent_TyrsVault",
    HALL_OF_TYR_ID: "RegionSummary_LegendaryChest_Parent_TheHallofTyr",
}
OVERFLOW_IDS = {RIVERPASS_OVERFLOW_ID, HELHEIM_OVERFLOW_ID}
SIMPLE_STATE_CLASS = "0x75E050AB149B4062"
SIMPLE_SIGNATURE = [{"name": "state", "value_tag": 1}]
ALLOWED_STATE_BITS = {
    0x3F800000: 1.0,
    0x40000000: 2.0,
    0x40400000: 3.0,
    0x40800000: 4.0,
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity = load_module("_legendary_scope_identity", IDENTITY_PATH)
analyze = load_module("_legendary_scope_analyze", ANALYZE_PATH)

# These are offline-only diagnostic bounds for two already-known records. The
# production bridge keeps its own independent fail-closed limits.
analyze.staged.MAX_LENGTH_POSITIONS = max(
    analyze.staged.MAX_LENGTH_POSITIONS, 4096
)
analyze.staged.MAX_PARSE_STEPS = max(analyze.staged.MAX_PARSE_STEPS, 131072)
analyze.staged.MAX_PARSE_PATHS = max(analyze.staged.MAX_PARSE_PATHS, 256)


def norm(value: str) -> str:
    return "".join(
        ch for ch in value.lower().removesuffix(".wad") if ch.isalnum()
    )


def scalar_float(raw_hex: str) -> float:
    raw = bytes.fromhex(raw_hex)
    if len(raw) != 5 or raw[0] != 1:
        raise RuntimeError(f"unexpected scalar token: {raw_hex}")
    bits = int.from_bytes(raw[1:], "little")
    if bits not in ALLOWED_STATE_BITS:
        raise RuntimeError(f"unexpected chest state bits: 0x{bits:08X}")
    return struct.unpack("<f", raw[1:])[0]


def derive_identity(row: dict) -> dict:
    scene, skipped = identity.scene_identity_elements(row)
    elements = scene + [identity.CHEST_OWN_IDENTITY_ELEMENT]
    registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
    object_hash = identity.identity_hash(elements)
    return {
        "catalogue_id": row["catalogue_id"],
        "wad": row["source"]["wad"],
        "scene_identity_elements_hex": [item.hex() for item in scene],
        "skipped_transform_nodes": skipped,
        "own_identity_element_hex": identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
        "identity_elements_hex": [item.hex() for item in elements],
        "registry_hash_hex": f"0x{registry_hash:016X}",
        "object_hash_hex": f"0x{object_hash:016X}",
        "serialized_flag1_hex": identity.serialized_payload(
            registry_hash, object_hash
        ).hex(),
    }


def exact_staged_state(
    capture_dir: Path,
    source_records: list[dict],
    row: dict,
    derived: dict,
) -> dict:
    by_norm = {norm(item.get("name", "")): item for item in source_records}
    source = by_norm.get(norm(row["source"]["wad"]))
    if source is None:
        return {
            "capture_present": False,
            "exact_match": False,
            "reason": "wad_absent_from_frozen_capture",
        }
    payload_file = source.get("payload_file")
    if not payload_file:
        raise RuntimeError(f"{source['name']}: frozen record lacks payload file")

    envelope = (capture_dir / payload_file).read_bytes()
    candidates = analyze.carrier_with_tokens(
        envelope, int(source["cached_channel_a_lua_length"])
    )
    exact_hits = []
    for candidate_index, candidate in enumerate(candidates):
        entries = analyze.extract_state_entries(
            candidate["raw"], candidate["decoded"], candidate["parsed"]
        )
        for entry in entries:
            if entry.get("field_signature") != SIMPLE_SIGNATURE:
                continue
            parent = entry.get("parent") or {}
            if parent.get("record_class_key_hex") != SIMPLE_STATE_CLASS:
                continue
            go = parent.get("gameobject") or {}
            if not go:
                continue
            if (
                go.get("registry_hash_hex") != derived["registry_hash_hex"]
                or go.get("object_hash_hex") != derived["object_hash_hex"]
            ):
                continue
            raw_hex = entry["state"]["raw_hex"]
            exact_hits.append({
                "candidate_index": candidate_index,
                "candidate_alignment": candidate["alignment"],
                "candidate_bit_offset": candidate["bit_offset"],
                "state_raw_hex": raw_hex,
                "state_u32": entry["state"]["decoded"],
                "state_float32": scalar_float(raw_hex),
                "state_row": entry.get("state_row"),
                "subobj_table_row": entry.get("subobj_table_row"),
            })

    unique = {
        (
            hit["state_raw_hex"],
            hit["state_u32"],
            hit["state_row"],
            hit["subobj_table_row"],
        )
        for hit in exact_hits
    }
    if len(unique) != 1:
        raise RuntimeError(
            f"{row['catalogue_id']}: expected one unique exact staged state, "
            f"got {len(unique)} across {len(candidates)} carrier candidates"
        )
    chosen = exact_hits[0]
    return {
        "capture_present": True,
        "carrier_candidate_count": len(candidates),
        "exact_match": True,
        **chosen,
    }


def level_specific_source_hints(game_root: Path, wad: str) -> dict:
    """Collect optional level-specific textual hints without treating them as authority."""
    stem = Path(wad).stem.lower()
    tokens = {
        "TyrsVault",
        "TheHallofTyr",
        "RegionSummary_LegendaryChest_Parent_TyrsVault",
        "RegionSummary_LegendaryChest_Parent_TheHallofTyr",
    }
    roots = [
        game_root / "mods" / "lua" / "gameart" / "scripts" / "levels",
        game_root / "exec" / "dc" / "pc_le",
    ]
    matches = []
    for root in roots:
        if not root.exists():
            continue
        if root.name == "pc_le":
            candidates = [root / f"wad_{stem}.dcb"]
        else:
            candidates = [
                path for path in root.rglob("*")
                if path.is_file()
                and stem.replace("_", "") in str(path).lower().replace("_", "")
            ]
        for path in candidates:
            if not path.is_file():
                continue
            raw = path.read_bytes()
            for token in sorted(tokens):
                if token.encode("ascii") in raw:
                    matches.append({
                        "file": str(path.relative_to(game_root)).replace("\\", "/"),
                        "token": token,
                    })
    return {"stem": stem, "matches": matches}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument(
        "--game-root",
        type=Path,
        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    all_legendary = [
        row for row in catalogue["collectibles"]
        if row.get("family") == "legendary_chest"
    ]
    old_tracked = [
        row for row in all_legendary
        if row.get("production_eligibility") == "tracked_collectible"
    ]
    if len(all_legendary) != 64 or len(old_tracked) != 33:
        raise RuntimeError(
            f"unexpected Legendary baseline: raw={len(all_legendary)} "
            f"old_tracked={len(old_tracked)}"
        )

    by_id = {row["catalogue_id"]: row for row in all_legendary}
    required_ids = OVERFLOW_IDS | set(PRODUCTION_OVERRIDES)
    missing = sorted(required_ids - set(by_id))
    if missing:
        raise RuntimeError(f"scope rows missing from catalogue: {missing}")

    # The two overflow rows must still be exact physical/state-resolved objects.
    if by_id[RIVERPASS_OVERFLOW_ID]["native"]["placement_object_name"] != "gofinalchest02":
        raise RuntimeError("Riverpass overflow placement identity changed")
    if by_id[HELHEIM_OVERFLOW_ID]["source"]["wad"].lower() != "helr100_docks.wad":
        raise RuntimeError("Helheim overflow WAD identity changed")

    # Build corrected set: 33 inferred rows - 2 overflow + 2 recovered Tyr rows.
    production_rows = [
        row for row in old_tracked
        if row["catalogue_id"] not in OVERFLOW_IDS
    ]
    for catalogue_id in PRODUCTION_OVERRIDES:
        production_rows.append(by_id[catalogue_id])
    if len(production_rows) != 33:
        raise RuntimeError(
            f"corrected production row count changed: {len(production_rows)}"
        )

    # Parent-quest accounting against native quest targets.
    expected_targets = {
        name: item["target"]
        for name, item in audit["tracked_summary_targets"].items()
        if name.startswith("RegionSummary_LegendaryChest_Parent_")
    }
    parent_by_id = {}
    for row in production_rows:
        parent = PRODUCTION_OVERRIDES.get(
            row["catalogue_id"], row["progression"].get("parent_quest")
        )
        if not parent:
            raise RuntimeError(
                f"{row['catalogue_id']}: corrected production row has no parent"
            )
        parent_by_id[row["catalogue_id"]] = parent

    actual_counts = Counter(parent_by_id.values())
    mismatches = {
        name: {
            "expected": target,
            "actual": actual_counts.get(name, 0),
        }
        for name, target in expected_targets.items()
        if actual_counts.get(name, 0) != target
    }
    unexpected_parents = sorted(set(actual_counts) - set(expected_targets))
    if mismatches or unexpected_parents:
        raise RuntimeError(
            f"corrected RegionSummary accounting mismatch: "
            f"{mismatches} unexpected={unexpected_parents}"
        )
    if sum(expected_targets.values()) != 33:
        raise RuntimeError(
            f"native Legendary target total changed: "
            f"{sum(expected_targets.values())}"
        )

    # Derive every corrected production identity and require uniqueness.
    derived_rows = []
    for row in production_rows:
        item = derive_identity(row)
        item["parent_quest"] = parent_by_id[row["catalogue_id"]]
        derived_rows.append(item)
    if len({row["serialized_flag1_hex"] for row in derived_rows}) != 33:
        raise RuntimeError("corrected production serialized identities collide")
    if len({row["object_hash_hex"] for row in derived_rows}) != 33:
        raise RuntimeError("corrected production object hashes collide")

    source_report = json.loads(
        (args.capture_dir / "report.json").read_text(encoding="utf-8")
    )
    source_records = source_report.get("records", [])
    if len(source_records) != 425:
        raise RuntimeError(
            f"frozen staged capture record count changed: {len(source_records)}"
        )

    recovered = []
    for catalogue_id, parent in PRODUCTION_OVERRIDES.items():
        row = by_id[catalogue_id]
        derived = next(
            item for item in derived_rows
            if item["catalogue_id"] == catalogue_id
        )
        state = exact_staged_state(
            args.capture_dir, source_records, row, derived
        )
        recovered.append({
            **derived,
            "assigned_parent_quest": parent,
            "source_region_before_correction": row.get("region"),
            "source_region_source_before_correction": row.get("region_source"),
            "staged_state": state,
            "local_level_source_hints": level_specific_source_hints(
                args.game_root, row["source"]["wad"]
            ),
        })

    # Frozen-state reconciliation for the two overfull groups.
    accepted_report_path = (
        REPO / "archive" / "field-logs" / "source-scans"
        / "legendary-serialized-identities-static-20260922-152212"
        / "report.json"
    )
    accepted = json.loads(accepted_report_path.read_text(encoding="utf-8"))
    old_state_by_id = {
        row["catalogue_id"]: row.get("staged_state")
        for row in accepted.get("identities", [])
    }
    overflow = []
    for catalogue_id in (RIVERPASS_OVERFLOW_ID, HELHEIM_OVERFLOW_ID):
        row = by_id[catalogue_id]
        state = old_state_by_id.get(catalogue_id)
        state_float = (
            scalar_float(state["state_raw_hex"]) if state else None
        )
        overflow.append({
            "catalogue_id": catalogue_id,
            "wad": row["source"]["wad"],
            "placement": row["native"]["placement_object_name"],
            "old_inferred_parent_quest": row["progression"].get("parent_quest"),
            "old_parent_source": row["progression"].get("parent_quest_source"),
            "staged_state_raw_hex": state["state_raw_hex"] if state else None,
            "staged_state_float32": state_float,
            "production_eligibility": "exclude_non_map_counted",
        })

    report = {
        "schema": 1,
        "analysis": "legendary_map_counted_scope_resolution",
        "status": "EXACT_33_MAP_COUNTED_SCOPE_RESOLVED",
        "old_inferred_physical_identity_count": 33,
        "corrected_map_counted_production_count": 33,
        "native_region_summary_target_total": sum(expected_targets.values()),
        "production_parent_counts": dict(sorted(actual_counts.items())),
        "native_parent_targets": dict(sorted(expected_targets.items())),
        "overflow_exclusions": overflow,
        "recovered_map_counted_rows": recovered,
        "production_rows": sorted(
            derived_rows, key=lambda row: row["catalogue_id"]
        ),
        "production_catalogue_ids": sorted(
            row["catalogue_id"] for row in production_rows
        ),
        "production_serialized_identity_count": len({
            row["serialized_flag1_hex"] for row in derived_rows
        }),
        "production_object_hash_count": len({
            row["object_hash_hex"] for row in derived_rows
        }),
        "mapping_basis": {
            TYRS_VAULT_ID: (
                "cal500_runevault internal level identity plus existing "
                "TyrsVault level-script evidence and exact target accounting"
            ),
            HALL_OF_TYR_ID: (
                "cal740_leftwing is the remaining exact Caldera/Tyr physical "
                "Legendary placement after TyrsVault assignment; assigning it "
                "to TheHallofTyr closes all native target counts one-to-one"
            ),
            RIVERPASS_OVERFLOW_ID: (
                "Riverpass target=4; five inferred physical rows; exact user "
                "map evidence is 4/4 while this scripted gofinalchest02 carrier "
                "is state=2.0 and the other four are OPENED=4.0"
            ),
            HELHEIM_OVERFLOW_ID: (
                "Helheim target=3; four inferred physical rows; the three main "
                "Hel100/Hel300 carriers are OPENED=4.0 while HelR100_Docks is "
                "state=1.0; HelR100 also has independently proven untracked "
                "scripted reward context and no exact zone-to-summary binding"
            ),
        },
        "safety": {
            "offline_only": True,
            "game_process_accessed": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_files_written": False,
            "raven_runtime_modified": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "Completionist Map - Legendary map-counted production scope",
        "status=EXACT_33_MAP_COUNTED_SCOPE_RESOLVED",
        "old_inferred_physical_identities=33",
        "corrected_map_counted_production=33",
        "native_target_total=33",
        "production_object_hashes=33",
        "production_serialized_identities=33",
        "",
        "OVERFLOW EXCLUSIONS",
    ]
    for item in overflow:
        lines.append(
            f"{item['catalogue_id']} wad={item['wad']} "
            f"placement={item['placement']} "
            f"state={item['staged_state_float32']}"
        )
    lines += ["", "RECOVERED MAP-COUNTED ROWS"]
    for item in recovered:
        state = item["staged_state"]
        lines.append(
            f"{item['catalogue_id']} wad={item['wad']} "
            f"parent={item['assigned_parent_quest']} "
            f"object_hash={item['object_hash_hex']} "
            f"state={state.get('state_float32')} "
            f"exact_staged={state.get('exact_match')}"
        )
        for hint in item["local_level_source_hints"]["matches"]:
            lines.append(
                f"  source_hint file={hint['file']} token={hint['token']}"
            )
    lines += [
        "",
        "SAFETY",
        "offline_only=true",
        "game_process_accessed=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(
        "LEGENDARY_MAP_COUNTED_SCOPE_RESOLVED "
        "production=33 native_targets=33 unique_hashes=33"
    )
    for item in recovered:
        print(
            "RECOVERED "
            f"id={item['catalogue_id']} wad={item['wad']} "
            f"parent={item['assigned_parent_quest']} "
            f"hash={item['object_hash_hex']} "
            f"state={item['staged_state'].get('state_float32')}"
        )
    print(
        "offline_only=true game_process_accessed=false "
        "save_or_progression_written=false raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
