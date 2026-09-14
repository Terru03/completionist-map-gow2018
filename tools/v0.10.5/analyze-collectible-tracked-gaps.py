"""Read-only audit for the remaining tracked-count gaps in the collectible catalogue.

This tool does not change the catalogue. It rebuilds the existing static research
model from native PC assets and reports where exact physical rows do or do not
join the native RegionSummary quest targets for Nornir chests and Ship Head
artefacts. Region agreement is reported only as a candidate relationship; it is
never promoted to an exact join by this audit.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collectible_catalogue as cc


def quest_rows(audit: dict, token: str) -> dict[str, dict]:
    return {
        name: row
        for name, row in audit["tracked_summary_targets"].items()
        if token.lower() in name.lower()
    }


def compact_row(row: dict) -> dict:
    attrs = row.get("native", {}).get("attribute_values", [])
    return {
        "catalogue_id": row["catalogue_id"],
        "family": row["family"],
        "subtype": row.get("subtype"),
        "wad": row["source"]["wad"],
        "object_name": row["native"].get("object_name"),
        "instance_guid": row["native"].get("instance_guid"),
        "state_instance_guid": row["native"].get("state_instance_guid"),
        "region": row.get("region"),
        "realm": row.get("realm"),
        "region_source": row.get("region_source"),
        "parent_quest": row["progression"].get("parent_quest"),
        "position_world": row["marker"].get("position_world"),
        "region_summary_attributes": sorted(
            value for value in attrs if isinstance(value, str) and value.startswith("RegionSummary_")
        ),
    }


def candidate_quests_for_row(row: dict, targets: dict[str, dict]) -> list[str]:
    return sorted(
        name
        for name, target in targets.items()
        if target.get("realm") == row.get("realm")
        and str(target.get("region", "")).lower() == str(row.get("region", "")).lower()
    )


def family_gap(rows: list[dict], targets: dict[str, dict]) -> dict:
    joined = collections.Counter(
        row["progression"].get("parent_quest")
        for row in rows
        if row["progression"].get("parent_quest")
    )
    per_target = []
    for name, target in sorted(targets.items()):
        physical = joined.get(name, 0)
        expected = int(target.get("target") or 0)
        per_target.append({
            "quest": name,
            "realm": target.get("realm"),
            "region": target.get("region"),
            "target": expected,
            "exact_joined_physical_rows": physical,
            "deficit": expected - physical,
        })
    unmatched = []
    for row in rows:
        if row["progression"].get("parent_quest"):
            continue
        item = compact_row(row)
        item["same_region_target_candidates"] = candidate_quests_for_row(row, targets)
        unmatched.append(item)
    return {
        "physical_rows": len(rows),
        "exact_joined_rows": sum(joined.values()),
        "native_target_total": sum(int(row.get("target") or 0) for row in targets.values()),
        "per_target": per_target,
        "unmatched_rows": unmatched,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    args = ap.parse_args()

    catalogue, audit = cc.scan_native(args.game_root)
    rows = catalogue["collectibles"]

    nornir_rows = [row for row in rows if row["family"] == "nornir_chest"]
    shiphead_rows = [
        row for row in rows
        if row["family"] == "artefact" and row.get("subtype") == "Ship Head"
    ]

    nornir_targets = quest_rows(audit, "RunicChest")
    shiphead_targets = quest_rows(audit, "Shiphead")

    report = {
        "schema": 1,
        "scan_kind": "collectible_tracked_gap_audit",
        "result": "TRACKED_GAPS_AUDITED_NO_AUTO_JOIN",
        "catalogue_mutated": False,
        "runtime_generation_allowed": False,
        "interpretation_contract": {
            "same_region_candidate_is_exact_join": False,
            "count_deficit_is_individual_identity": False,
            "nearest_distance_matching_used": False,
            "catalogue_rows_changed": False,
        },
        "nornir_chest": family_gap(nornir_rows, nornir_targets),
        "ship_head": family_gap(shiphead_rows, shiphead_targets),
        "native_evidence": audit.get("native_evidence"),
        "safety": {
            "game_launched": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_written": False,
            "read_only_native_asset_scan": True,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Collectible tracked-gap audit",
        "",
        "Status: **TRACKED_GAPS_AUDITED_NO_AUTO_JOIN**",
        "",
        "This report is evidence-only. Same-region rows are candidates, not exact native joins, and the catalogue is not modified.",
        "",
    ]
    for label, key in (("Nornir Chest", "nornir_chest"), ("Ship Head", "ship_head")):
        block = report[key]
        lines += [
            f"## {label}",
            "",
            f"- Physical rows: {block['physical_rows']}",
            f"- Exact joined rows: {block['exact_joined_rows']}",
            f"- Native tracked target total: {block['native_target_total']}",
            "",
            "### Native targets",
            "",
        ]
        for target in block["per_target"]:
            lines.append(
                f"- `{target['quest']}` ({target['realm']} / {target['region']}): "
                f"target={target['target']} exact_rows={target['exact_joined_physical_rows']} deficit={target['deficit']}"
            )
        lines += ["", "### Unmatched physical rows", ""]
        if not block["unmatched_rows"]:
            lines.append("- none")
        for row in block["unmatched_rows"]:
            candidates = ", ".join(f"`{x}`" for x in row["same_region_target_candidates"]) or "none"
            attrs = ", ".join(f"`{x}`" for x in row["region_summary_attributes"]) or "none"
            lines.append(
                f"- `{row['catalogue_id']}` — {row['wad']} — {row['realm']} / {row['region']} "
                f"({row['region_source']}); same-region target candidates: {candidates}; "
                f"explicit RegionSummary attributes: {attrs}; world={row['position_world']}"
            )
        lines.append("")

    lines += [
        "## Interpretation",
        "",
        "A row may only be promoted to a tracked quest join when native object/quest evidence proves that exact relationship. Region equality or a count deficit alone is insufficient.",
        "",
        "Runtime generation remains disabled and no save/progression state was accessed or written.",
        "",
    ]
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    print("COLLECTIBLE_TRACKED_GAP_AUDIT_COMPLETED")
    print(f"nornir_physical={report['nornir_chest']['physical_rows']}")
    print(f"nornir_exact_joined={report['nornir_chest']['exact_joined_rows']}")
    print(f"nornir_target_total={report['nornir_chest']['native_target_total']}")
    print(f"nornir_unmatched={len(report['nornir_chest']['unmatched_rows'])}")
    print(f"shiphead_physical={report['ship_head']['physical_rows']}")
    print(f"shiphead_exact_joined={report['ship_head']['exact_joined_rows']}")
    print(f"shiphead_target_total={report['ship_head']['native_target_total']}")
    print(f"shiphead_unmatched={len(report['ship_head']['unmatched_rows'])}")
    print("runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
