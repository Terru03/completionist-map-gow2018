"""Read-only deep native evidence probe for Ship Head 03/05 and Tyr's Vault Nornir.

This probe never mutates the catalogue. It deliberately avoids the catalogue's
first-hop nearest-record fallback and enumerates all native transform parents for
Ship Head carriers, while also locating numbered Ship Head references that do
not currently become catalogue rows. It separately inventories Tyr/Vault-related
records in cal500_runevault.wad.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collectible_catalogue as cc
import raven_catalogue as raven

SHIP_RE = re.compile(r"goartifactshiphead[^0-9\r\n\x00]{0,24}([0-9]{1,2})", re.I)
SAFE_TYR_RE = re.compile(r"tyr|vault|runevault|RegionSummary_RunicChest_Parent_TyrsVault", re.I)
MAX_PATHS = 256
MAX_DEPTH = 24


def safe_strings(record: dict, pattern: re.Pattern[str]) -> list[str]:
    values = []
    if pattern.search(record.get("name", "")):
        values.append(record["name"])
    for value in cc.strings(record["data"]):
        if len(value) <= 180 and pattern.search(value):
            values.append(value)
    return sorted(set(values), key=str.lower)


def ship_numbers(record: dict) -> list[int]:
    values = [record.get("name", "")] + cc.strings(record["data"])
    found = set()
    for value in values:
        for match in SHIP_RE.finditer(value):
            number = int(match.group(1))
            if 1 <= number <= 99:
                found.add(number)
    return sorted(found)


def transform_candidates(records: list[dict]) -> dict[bytes, list[dict]]:
    result: dict[bytes, list[dict]] = collections.defaultdict(list)
    for row in records:
        if row["kind"] == 1 and row["flags"] == 0x3D and row["size"] == 164:
            result[row["data"][0x0C:0x1C]].append(row)
    return result


def exhaustive_paths(start: dict, records: list[dict]) -> list[dict]:
    """Enumerate every transform-parent path without nearest-record selection."""
    candidates = transform_candidates(records)
    results: list[dict] = []

    def walk(current: dict, transform, chain: list[dict], seen: set[int], depth: int) -> None:
        if len(results) >= MAX_PATHS:
            return
        if depth > MAX_DEPTH:
            raise RuntimeError(f"transform depth exceeded for {start['name']}")
        parent_id = current["data"][0x54:0x64]
        parents = [row for row in candidates.get(parent_id, []) if id(row) not in seen]
        if parent_id == bytes(16) or not parents:
            placement = None
            try:
                override, final = cc.physical_placement(chain, records)
                placement = {
                    "override_name": override["name"],
                    "object_name": final["name"],
                    "instance_guid": cc.placement_instance_guid(override),
                    "record_uuid_hint": cc.record_uuid_hint(override),
                    "override_offset": f"0x{override['offset']:X}",
                    "final_offset": f"0x{final['offset']:X}",
                }
            except Exception as exc:
                placement = {"error": str(exc)}
            results.append({
                "world": list(transform[1]),
                "placement": placement,
                "chain": [
                    {
                        "name": row["name"],
                        "offset": f"0x{row['offset']:X}",
                        "record_id": row["id"].hex(),
                    }
                    for row in chain
                ],
            })
            return
        for parent in parents:
            walk(
                parent,
                raven.compose(raven.record_transform(parent), transform),
                chain + [parent],
                seen | {id(parent)},
                depth + 1,
            )

    walk(start, raven.record_transform(start), [start], {id(start)}, 0)
    return results


def first_parents(start: dict, records: list[dict]) -> list[dict]:
    candidates = transform_candidates(records)
    parent_id = start["data"][0x54:0x64]
    return [
        {
            "name": row["name"],
            "offset": f"0x{row['offset']:X}",
            "record_id": row["id"].hex(),
        }
        for row in candidates.get(parent_id, [])
    ]


def inspect_ship_wad(wad: Path, raw: bytes) -> dict | None:
    low = raw.lower()
    if b"goartifactshiphead" not in low:
        return None
    records = raven.parse_wad(raw)
    numbered_hits = []
    carriers = []

    for index, row in enumerate(records):
        numbers = ship_numbers(row)
        if numbers:
            numbered_hits.append({
                "index": index,
                "name": row["name"],
                "kind": row["kind"],
                "offset": f"0x{row['offset']:X}",
                "record_id": row["id"].hex(),
                "numbers": numbers,
                "strings": safe_strings(row, re.compile(r"shiphead|Ship Head|RegionSummary_.*Shiphead", re.I)),
                "nearby": [
                    {
                        "index": j,
                        "name": records[j]["name"],
                        "kind": records[j]["kind"],
                        "offset": f"0x{records[j]['offset']:X}",
                    }
                    for j in range(max(0, index - 3), min(len(records), index + 4))
                    if j != index
                ],
            })

        if row["name"].lower() != "goartifactscript_overrideinst":
            continue
        values = cc.strings(row["data"])
        if not any("ship head" in value.lower() or "shiphead" in value.lower() for value in values):
            continue
        item = {
            "index": index,
            "override_offset": f"0x{row['offset']:X}",
            "override_record_id": row["id"].hex(),
            "state_instance_guid": None,
            "numbers": ship_numbers(row),
            "safe_identifiers": sorted(set(
                value for value in values
                if len(value) <= 180 and (
                    "ship head" in value.lower()
                    or "shiphead" in value.lower()
                    or value.startswith("RegionSummary_")
                )
            ), key=str.lower),
            "first_parents": [],
            "all_paths": [],
            "error": None,
        }
        try:
            item["state_instance_guid"] = cc.native_instance_guid(row)
            final = cc.instance_final(records, index)
            item["carrier_final"] = {
                "name": final["name"],
                "offset": f"0x{final['offset']:X}",
                "record_id": final["id"].hex(),
            }
            item["first_parents"] = first_parents(final, records)
            item["all_paths"] = exhaustive_paths(final, records)
        except Exception as exc:
            item["error"] = str(exc)
        carriers.append(item)

    number_counts = collections.Counter()
    for hit in numbered_hits:
        for number in hit["numbers"]:
            number_counts[number] += 1
    return {
        "wad": wad.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "number_counts": {str(k): v for k, v in sorted(number_counts.items())},
        "numbered_hits": numbered_hits,
        "carriers": carriers,
    }


def inspect_cal500(wad: Path) -> dict:
    raw = wad.read_bytes()
    records = raven.parse_wad(raw)
    hits = []
    for index, row in enumerate(records):
        values = safe_strings(row, SAFE_TYR_RE)
        if not values:
            continue
        hits.append({
            "index": index,
            "name": row["name"],
            "kind": row["kind"],
            "offset": f"0x{row['offset']:X}",
            "record_id": row["id"].hex(),
            "strings": values,
            "nearby": [
                {
                    "index": j,
                    "name": records[j]["name"],
                    "kind": records[j]["kind"],
                    "offset": f"0x{records[j]['offset']:X}",
                }
                for j in range(max(0, index - 4), min(len(records), index + 5))
                if j != index
            ],
        })
    return {
        "wad": wad.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "level_region_current": cc.level_region(wad),
        "hits": hits,
    }


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

    ship_wads = []
    for wad in sorted(wad_root.glob("*.wad"), key=lambda p: p.name.lower()):
        raw = wad.read_bytes()
        row = inspect_ship_wad(wad, raw)
        if row is not None:
            ship_wads.append(row)

    cal500_path = wad_root / "cal500_runevault.wad"
    if not cal500_path.is_file():
        raise RuntimeError(f"Missing expected native WAD: {cal500_path}")
    cal500 = inspect_cal500(cal500_path)

    physical = {}
    carrier_count = 0
    carrier_path_count = 0
    first_parent_ambiguities = []
    numbered_wads: dict[int, set[str]] = collections.defaultdict(set)
    for wad in ship_wads:
        for hit in wad["numbered_hits"]:
            for number in hit["numbers"]:
                numbered_wads[number].add(wad["wad"])
        for carrier in wad["carriers"]:
            carrier_count += 1
            carrier_path_count += len(carrier["all_paths"])
            if len(carrier["first_parents"]) > 1:
                first_parent_ambiguities.append({
                    "wad": wad["wad"],
                    "state_instance_guid": carrier["state_instance_guid"],
                    "numbers": carrier["numbers"],
                    "first_parents": carrier["first_parents"],
                })
            for path in carrier["all_paths"]:
                placement = path.get("placement") or {}
                key = placement.get("instance_guid") or placement.get("record_uuid_hint")
                if key:
                    physical.setdefault(key, {
                        "world": path["world"],
                        "placement": placement,
                        "carriers": [],
                    })
                    physical[key]["carriers"].append({
                        "wad": wad["wad"],
                        "state_instance_guid": carrier["state_instance_guid"],
                        "numbers": carrier["numbers"],
                    })

    report = {
        "schema": 1,
        "scan_kind": "collectible_gap_deep_native_evidence",
        "status": "DEEP_SOURCE_EVIDENCE_ONLY",
        "runtime_generation_allowed": False,
        "catalogue_mutated": False,
        "ship_head": {
            "carrier_count": carrier_count,
            "exhaustive_carrier_path_count": carrier_path_count,
            "distinct_physical_placements_from_carriers": len(physical),
            "numbered_reference_wads": {
                str(number): sorted(wads)
                for number, wads in sorted(numbered_wads.items())
            },
            "missing_number_reference_03": sorted(numbered_wads.get(3, set())),
            "missing_number_reference_05": sorted(numbered_wads.get(5, set())),
            "first_parent_ambiguities": first_parent_ambiguities,
            "physical_placements": physical,
            "wads": ship_wads,
        },
        "tyrs_vault_nornir": cal500,
        "interpretation_contract": {
            "numbered_reference_is_physical_collectible": False,
            "exhaustive_path_is_tracked_quest_join": False,
            "filename_is_exact_quest_binding": False,
            "count_difference_is_not_identity": True,
        },
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
        "# Collectible gap deep native evidence",
        "",
        "Status: **DEEP_SOURCE_EVIDENCE_ONLY**",
        "",
        "## Ship Head",
        "",
        f"- Raw carriers: {carrier_count}",
        f"- Exhaustive carrier transform paths: {carrier_path_count}",
        f"- Distinct physical placements from carriers: {len(physical)}",
        f"- Number 03 reference WADs: {sorted(numbered_wads.get(3, set())) or 'none'}",
        f"- Number 05 reference WADs: {sorted(numbered_wads.get(5, set())) or 'none'}",
        f"- Carriers with multiple first transform parents: {len(first_parent_ambiguities)}",
        "",
        "### Numbered references",
        "",
    ]
    for number, wads in sorted(numbered_wads.items()):
        lines.append(f"- {number:02d}: {', '.join(sorted(wads))}")
    lines += ["", "### Distinct physical placements", ""]
    for key, value in sorted(physical.items()):
        lines.append(
            f"- `{key}` world={value['world']} object={value['placement'].get('object_name')} "
            f"carriers={value['carriers']}"
        )
    lines += [
        "",
        "## cal500_runevault / Tyr's Vault evidence",
        "",
        f"- Current level-region classification: {cal500['level_region_current']}",
        f"- Tyr/Vault-safe record hits: {len(cal500['hits'])}",
    ]
    for hit in cal500["hits"][:80]:
        lines.append(
            f"- idx={hit['index']} `{hit['name']}` kind={hit['kind']} off={hit['offset']} strings={hit['strings']}"
        )
    if len(cal500["hits"]) > 80:
        lines.append(f"- {len(cal500['hits']) - 80} additional hits retained in JSON")
    lines += [
        "",
        "## Interpretation",
        "",
        "This probe removes the previous first-hop nearest-record selection from the diagnostic path enumeration. Numbered references and filename/region hints remain evidence only; no tracked quest join is promoted automatically.",
        "",
        "Runtime generation remains disabled.",
        "",
    ]
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    print("COLLECTIBLE_GAP_DEEP_EVIDENCE_COMPLETED")
    print(f"shiphead_carriers={carrier_count}")
    print(f"shiphead_exhaustive_paths={carrier_path_count}")
    print(f"shiphead_distinct_physical={len(physical)}")
    print(f"shiphead_03_wads={','.join(sorted(numbered_wads.get(3, set())))}")
    print(f"shiphead_05_wads={','.join(sorted(numbered_wads.get(5, set())))}")
    print(f"shiphead_first_parent_ambiguities={len(first_parent_ambiguities)}")
    print(f"cal500_tyr_vault_hits={len(cal500['hits'])}")
    print("runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
