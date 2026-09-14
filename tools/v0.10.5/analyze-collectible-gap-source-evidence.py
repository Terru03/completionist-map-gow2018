"""Read-only native-source probe for the remaining Nornir and Ship Head count gaps.

This intentionally does not mutate the catalogue.  It inspects every PC WAD that
contains the exact native carrier records used by the existing extractor and
reports carrier/placement evidence even when the current catalogue join logic
cannot assign a RegionSummary target.

The goal is to distinguish three cases without heuristics:
  * an extractor missed a real physical placement;
  * a physical placement exists but lacks an explicit RegionSummary join;
  * the native quest target count itself exceeds physical collectible rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collectible_catalogue as cc
import raven_catalogue as raven

TARGET_QUESTS = (
    "RegionSummary_RunicChest_Parent_TyrsVault",
    "RegionSummary_BSW_Shiphead_Parent",
    "RegionSummary_CALS_Shiphead_Parent",
)


def safe_strings(values: list[str]) -> list[str]:
    """Keep only useful native identifiers, never arbitrary binary excerpts."""
    keep = []
    for value in values:
        low = value.lower()
        if (
            value.startswith("RegionSummary_")
            or "ship head" in low
            or "shiphead" in low
            or "tyr" in low
            or "runic" in low
            or "runevault" in low
            or "artifact" in low
            or "artefact" in low
            or "gochest" in low
        ):
            keep.append(value)
    return sorted(set(keep), key=str.lower)


def chain_values(raw_chain: list[dict], records: list[dict]) -> list[str]:
    values: list[str] = []
    for row in raw_chain:
        values.extend(cc.strings(row["data"]))
        override = cc.matching_override(records, row)
        if override is not None:
            values.extend(cc.strings(override["data"]))
    return values


def compact_path(matrix, world, chain, raw_chain, records) -> dict:
    placement = None
    try:
        placement_override, placement_final = cc.physical_placement(raw_chain, records)
        placement = {
            "override_name": placement_override["name"],
            "object_name": placement_final["name"],
            "instance_guid": cc.placement_instance_guid(placement_override),
            "record_uuid_hint": cc.record_uuid_hint(placement_override),
            "override_offset": f"0x{placement_override['offset']:X}",
            "final_offset": f"0x{placement_final['offset']:X}",
        }
    except Exception as exc:
        placement = {"error": str(exc)}
    return {
        "world": list(world),
        "placement": placement,
        "chain": chain,
        "safe_chain_identifiers": safe_strings(chain_values(raw_chain, records)),
    }


def inspect_shiphead_carriers(wad: Path, raw: bytes, records: list[dict]) -> list[dict]:
    rows = []
    for index, override in enumerate(records):
        if override["name"].lower() != "goartifactscript_overrideinst":
            continue
        values = cc.strings(override["data"])
        if not any("ship head" in value.lower() or "shiphead" in value.lower() for value in values):
            continue
        item = {
            "override_offset": f"0x{override['offset']:X}",
            "override_record_id": override["id"].hex(),
            "native_instance_guid": None,
            "safe_override_identifiers": safe_strings(values),
            "paths": [],
            "error": None,
        }
        try:
            item["native_instance_guid"] = cc.native_instance_guid(override)
            final = cc.instance_final(records, index)
            paths = cc.exact_world_transforms(final, records)
            item["paths"] = [compact_path(*path, records) for path in paths]
        except Exception as exc:
            item["error"] = str(exc)
        rows.append(item)
    return rows


def inspect_nornir_carriers(wad: Path, raw: bytes, records: list[dict]) -> list[dict]:
    rows = []
    for index, override in enumerate(records):
        if override["name"].lower() not in {"gochestscript_overrideinst", "gochestscript_rn_overrideinst"}:
            continue
        values = cc.strings(override["data"])
        chest_types = [value for value in values if value in cc.CHEST_TYPES]
        if not chest_types or not any(value.startswith("Runic_") for value in chest_types):
            continue
        item = {
            "override_offset": f"0x{override['offset']:X}",
            "override_record_id": override["id"].hex(),
            "native_instance_guid": None,
            "native_types": chest_types,
            "safe_override_identifiers": safe_strings(values),
            "paths": [],
            "error": None,
        }
        try:
            item["native_instance_guid"] = cc.native_instance_guid(override)
            final = cc.instance_final(records, index)
            paths = cc.exact_world_transforms(final, records, parent_name="gochest_locked_parent")
            item["paths"] = [compact_path(*path, records) for path in paths]
        except Exception as exc:
            item["error"] = str(exc)
        rows.append(item)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.resolve()
    wad_root = game_root / "exec" / "wad" / "pc_le"
    if not wad_root.is_dir():
        raise RuntimeError(f"WAD root missing: {wad_root}")

    catalogue, audit = cc.scan_native(game_root)
    cat_rows = catalogue["collectibles"]
    catalogue_shipheads = [r for r in cat_rows if r["family"] == "artefact" and r.get("subtype") == "Ship Head"]
    catalogue_nornir = [r for r in cat_rows if r["family"] == "nornir_chest"]

    wad_results = []
    total_shiphead_carriers = 0
    total_shiphead_paths = 0
    total_nornir_carriers = 0
    total_nornir_paths = 0

    for wad in sorted(wad_root.glob("*.wad"), key=lambda p: p.name.lower()):
        raw = wad.read_bytes()
        low = raw.lower()
        relevant = (
            b"goartifactscript_overrideinst" in low
            or b"gochestscript_rn_overrideinst" in low
            or b"regionsummary_runicchest_parent_tyrsvault" in low
            or b"regionsummary_bsw_shiphead_parent" in low
            or b"regionsummary_cals_shiphead_parent" in low
        )
        if not relevant:
            continue
        records = raven.parse_wad(raw)
        shipheads = inspect_shiphead_carriers(wad, raw, records)
        nornir = inspect_nornir_carriers(wad, raw, records)
        target_literals = [q for q in TARGET_QUESTS if q.encode("ascii").lower() in low]
        filename_hint = bool(re.search(r"tyr|vault|ship|cal|xpl9|beach", wad.stem, re.I))
        if not (shipheads or nornir or target_literals or filename_hint):
            continue
        total_shiphead_carriers += len(shipheads)
        total_shiphead_paths += sum(len(x["paths"]) for x in shipheads)
        total_nornir_carriers += len(nornir)
        total_nornir_paths += sum(len(x["paths"]) for x in nornir)
        wad_results.append({
            "wad": wad.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "target_quest_literals": target_literals,
            "shiphead_carriers": shipheads,
            "nornir_carriers": nornir,
        })

    def cat_compact(row: dict) -> dict:
        return {
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "subtype": row.get("subtype"),
            "instance_guid": row["native"].get("instance_guid"),
            "state_instance_guid": row["native"].get("state_instance_guid"),
            "parent_quest": row["progression"].get("parent_quest"),
            "realm": row.get("realm"),
            "region": row.get("region"),
            "world": row["marker"].get("position_world"),
        }

    target_totals = audit["native_tracked_target_totals"]
    report = {
        "schema": 1,
        "scan_kind": "collectible_gap_source_evidence",
        "status": "SOURCE_EVIDENCE_ONLY",
        "runtime_generation_allowed": False,
        "catalogue_mutated": False,
        "interpretation_contract": {
            "carrier_is_physical_collectible": False,
            "placement_path_is_tracked_join": False,
            "quest_literal_is_exact_object_binding": False,
            "count_difference_is_not_identity": True,
        },
        "catalogue_baseline": {
            "ship_head_rows": len(catalogue_shipheads),
            "nornir_rows": len(catalogue_nornir),
            "ship_head_rows_detail": [cat_compact(r) for r in catalogue_shipheads],
            "nornir_unjoined_rows": [cat_compact(r) for r in catalogue_nornir if not r["progression"].get("parent_quest")],
        },
        "native_targets": {
            "ship_head": target_totals["artefact_shiphead"],
            "nornir": target_totals["nornir_chest"],
        },
        "raw_carrier_summary": {
            "shiphead_carriers": total_shiphead_carriers,
            "shiphead_placement_paths": total_shiphead_paths,
            "nornir_carriers": total_nornir_carriers,
            "nornir_placement_paths": total_nornir_paths,
        },
        "wads": wad_results,
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
        "# Collectible gap native-source evidence",
        "",
        "Status: **SOURCE_EVIDENCE_ONLY**",
        "",
        f"- Catalogue Ship Head rows: {len(catalogue_shipheads)}",
        f"- Native Ship Head target total: {target_totals['artefact_shiphead']}",
        f"- Raw Ship Head carriers: {total_shiphead_carriers}",
        f"- Raw Ship Head placement paths: {total_shiphead_paths}",
        f"- Catalogue Nornir rows: {len(catalogue_nornir)}",
        f"- Native Nornir target total: {target_totals['nornir_chest']}",
        f"- Raw Nornir carriers: {total_nornir_carriers}",
        f"- Raw Nornir placement paths: {total_nornir_paths}",
        "- Runtime generation allowed: **false**",
        "",
        "## WAD evidence",
        "",
    ]
    for row in wad_results:
        if not (row["shiphead_carriers"] or row["nornir_carriers"] or row["target_quest_literals"]):
            continue
        lines.append(
            f"- `{row['wad']}`: shiphead_carriers={len(row['shiphead_carriers'])}; "
            f"nornir_carriers={len(row['nornir_carriers'])}; "
            f"target_literals={row['target_quest_literals'] or 'none'}"
        )
        for carrier in row["shiphead_carriers"]:
            lines.append(
                f"  - Ship Head carrier `{carrier['native_instance_guid']}` paths={len(carrier['paths'])} "
                f"ids={carrier['safe_override_identifiers']} error={carrier['error']}"
            )
            for path in carrier["paths"]:
                lines.append(
                    f"    - world={path['world']} placement={path['placement']} ids={path['safe_chain_identifiers']}"
                )
        for carrier in row["nornir_carriers"]:
            lines.append(
                f"  - Nornir carrier `{carrier['native_instance_guid']}` types={carrier['native_types']} "
                f"paths={len(carrier['paths'])} ids={carrier['safe_override_identifiers']} error={carrier['error']}"
            )
            for path in carrier["paths"]:
                lines.append(
                    f"    - world={path['world']} placement={path['placement']} ids={path['safe_chain_identifiers']}"
                )
    lines += [
        "",
        "## Interpretation",
        "",
        "This report intentionally stops before changing any catalogue join. A native carrier or placement path must still be tied to the exact tracked quest by native evidence; counts and location similarity are not enough.",
        "",
    ]
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    print("COLLECTIBLE_GAP_SOURCE_EVIDENCE_COMPLETED")
    print(f"catalogue_shipheads={len(catalogue_shipheads)}")
    print(f"raw_shiphead_carriers={total_shiphead_carriers}")
    print(f"raw_shiphead_paths={total_shiphead_paths}")
    print(f"shiphead_target={target_totals['artefact_shiphead']}")
    print(f"catalogue_nornir={len(catalogue_nornir)}")
    print(f"raw_nornir_carriers={total_nornir_carriers}")
    print(f"raw_nornir_paths={total_nornir_paths}")
    print(f"nornir_target={target_totals['nornir_chest']}")
    print("runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
