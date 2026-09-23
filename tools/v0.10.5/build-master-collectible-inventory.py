#!/usr/bin/env python3
"""Build a fail-closed master collectible inventory.

Native repository evidence is authoritative. External guide counts are audit
expectations only and can never create a physical row or authorize a marker.
The builder accepts one or more catalogue JSON files so family-specific
research branches can export evidence into one normalized inventory later.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_POLICY = REPO / "config/collectibles/v0.10.5/master-collectible-policy.json"
DEFAULT_CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"

ALIASES = {
    "raven": "odin_raven", "odins_raven": "odin_raven", "odin's raven": "odin_raven",
    "artefact": "artefact", "artifact": "artefact",
    "nornir": "nornir_chest", "nornir_chest": "nornir_chest", "runic_chest": "nornir_chest",
    "legendary": "legendary_chest", "legendary_chest": "legendary_chest",
    "lore": "lore_marker", "lore_marker": "lore_marker",
    "realm_tear": "realm_tear", "realm tear": "realm_tear",
    "jotnar_shrine": "jotnar_shrine", "jotnar shrine": "jotnar_shrine",
    "cipher_chest": "cipher_chest", "cipher chest": "cipher_chest",
    "treasure_map": "treasure_map", "treasure map": "treasure_map",
    "treasure_dig": "treasure_dig", "treasure dig": "treasure_dig",
    "hidden_chamber": "hidden_chamber", "hidden chamber": "hidden_chamber",
    "valkyrie": "valkyrie", "valkyrie_queen": "valkyrie_queen",
    "mystic_gateway": "mystic_gateway", "gateway": "mystic_gateway",
    "shop": "shop", "dragon": "dragon", "favor": "favor", "favour": "favor",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def family_key(row: dict) -> str:
    raw = row.get("family") or row.get("type") or row.get("category") or ""
    token = norm_token(raw)
    if token in ALIASES:
        return ALIASES[token]
    subtype = norm_token(row.get("subtype"))
    if subtype in ALIASES:
        return ALIASES[subtype]
    name = norm_token(row.get("display_name") or row.get("name"))
    for alias, canonical in ALIASES.items():
        if alias.replace(" ", "_") in name:
            return canonical
    return token or "unknown"


def first(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def physical_id(row: dict) -> str | None:
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return first(native, "instance_guid", "physical_instance_guid") or first(row, "physical_instance_guid", "instance_guid", "guid")


def world_xyz(row: dict) -> list | None:
    marker = row.get("marker") if isinstance(row.get("marker"), dict) else {}
    value = first(marker, "position_world", "world_xyz", "position") or first(row, "world_xyz", "position_world")
    if isinstance(value, list) and len(value) >= 3:
        return value[:3]
    return None


def state_identity(row: dict) -> dict:
    progress = row.get("progression") if isinstance(row.get("progression"), dict) else {}
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return {
        "instance_keys": progress.get("instance_keys") or [],
        "object_hash_hex": first(progress, "object_hash_hex", "static_derived_object_hash_hex") or first(native, "object_hash_hex"),
        "serialized_flag1_hex": first(progress, "serialized_flag1_hex", "static_derived_serialized_flag1_hex") or first(native, "serialized_flag1_hex"),
        "state_adapter": progress.get("state_adapter"),
        "completion_field": progress.get("field"),
        "unloaded_query": progress.get("unloaded_query"),
    }


def load_catalogue(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("collectibles", "rows", "items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    raise ValueError(f"unsupported catalogue shape: {path}")


def policy_index(policy: dict) -> dict[str, dict]:
    return {row["key"]: row for row in policy["families"]}


def marker_policy(policy: dict, fam: str, subtype: str | None) -> tuple[str, str]:
    for override in policy.get("subtype_overrides", []):
        if override.get("family") == fam and norm_token(override.get("subtype")) == norm_token(subtype):
            return override["marker_policy"], "subtype_override"
    fam_policy = policy_index(policy).get(fam)
    if fam_policy:
        return fam_policy["marker_policy"], "family_policy"
    return policy["default_marker_policy"], "default_fail_closed"


def normalize(row: dict, source: Path, policy: dict) -> dict:
    fam = family_key(row)
    subtype = row.get("subtype")
    mp, mp_source = marker_policy(policy, fam, subtype)
    source_info = row.get("source") if isinstance(row.get("source"), dict) else {}
    progress = row.get("progression") if isinstance(row.get("progression"), dict) else {}
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return {
        "catalogue_id": row.get("catalogue_id") or row.get("id"),
        "family": fam,
        "subtype": subtype,
        "display_name": row.get("display_name") or row.get("name") or subtype or fam,
        "realm_id": row.get("realm_id"),
        "region_id": row.get("region_id"),
        "wad": first(source_info, "wad", "source_file") or row.get("wad"),
        "physical_id": physical_id(row),
        "world_xyz": world_xyz(row),
        "parent_summary": first(progress, "parent_quest", "region_summary") or first(native, "parent_region_summary_target"),
        "state_identity": state_identity(row),
        "native_marker_present": None,
        "native_marker_evidence": None,
        "mod_marker_policy": mp,
        "mod_marker_policy_source": mp_source,
        "mod_marker_allowed": False,
        "marker_block_reason": "Inventory evidence alone never authorizes runtime marker generation.",
        "source_catalogue": str(source).replace("\\", "/"),
        "source_row_sha256": hashlib.sha256(canonical_json(row).encode()).hexdigest(),
    }


def dedupe(rows: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    conflicts: list[str] = []
    for row in rows:
        key = row.get("catalogue_id") or (f"physical:{row['physical_id']}" if row.get("physical_id") else None)
        if key is None:
            key = "anonymous:" + row["source_row_sha256"]
        old = by_key.get(key)
        if old is None:
            by_key[key] = row
        elif old["source_row_sha256"] != row["source_row_sha256"]:
            conflicts.append(key)
    if conflicts:
        raise ValueError("conflicting duplicate collectible rows: " + ", ".join(sorted(conflicts)[:20]))
    return sorted(by_key.values(), key=lambda r: (r["family"], str(r.get("realm_id")), str(r.get("region_id")), str(r.get("catalogue_id"))))


def discrepancy(policy: dict, rows: list[dict]) -> list[dict]:
    counts = Counter(row["family"] for row in rows)
    out = []
    for fam in policy["families"]:
        actual = counts.get(fam["key"], 0)
        expected = fam.get("guide_expected")
        if expected is None:
            status = "NO_GUIDE_EXPECTATION"
        elif actual == expected:
            status = "MATCH"
        elif actual < expected:
            status = "NATIVE_INVENTORY_UNDER_GUIDE"
        else:
            status = "NATIVE_INVENTORY_OVER_GUIDE"
        out.append({
            "family": fam["key"], "display": fam["display"],
            "guide_expected": expected, "inventory_rows": actual,
            "delta": None if expected is None else actual - expected,
            "status": status, "marker_policy": fam["marker_policy"],
        })
    unknown = sorted(set(counts) - set(policy_index(policy)))
    for fam in unknown:
        out.append({"family": fam, "display": fam, "guide_expected": None,
                    "inventory_rows": counts[fam], "delta": None,
                    "status": "UNPOLICIED_NATIVE_FAMILY", "marker_policy": policy["default_marker_policy"]})
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["catalogue_id","family","subtype","display_name","realm_id","region_id","wad","physical_id","world_xyz","parent_summary","object_hash_hex","serialized_flag1_hex","unloaded_query","native_marker_present","mod_marker_policy","mod_marker_allowed","source_catalogue"]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            state = row["state_identity"]
            writer.writerow({
                **{k: row.get(k) for k in fields},
                "world_xyz": json.dumps(row.get("world_xyz"), separators=(",", ":")) if row.get("world_xyz") else "",
                "object_hash_hex": state.get("object_hash_hex"),
                "serialized_flag1_hex": state.get("serialized_flag1_hex"),
                "unloaded_query": state.get("unloaded_query"),
            })


def write_md(path: Path, report: dict) -> None:
    lines = ["# Master collectible inventory", "", f"Generated: `{report['generated_utc']}`", "",
             "Native game/repository evidence is authoritative. Guide counts are audit-only. Runtime marker generation is disabled by this report.", "",
             "## Family audit", "", "| Family | Guide | Inventory | Delta | Status | Marker policy |", "|---|---:|---:|---:|---|---|"]
    for row in report["family_audit"]:
        lines.append(f"| {row['display']} | {row['guide_expected'] if row['guide_expected'] is not None else ''} | {row['inventory_rows']} | {row['delta'] if row['delta'] is not None else ''} | {row['status']} | {row['marker_policy']} |")
    lines += ["", "## Hard marker rules", ""]
    lines += [f"- {rule}" for rule in report["policy_hard_rules"]]
    lines += ["", "## Inventory rows", "", "| Family | Subtype | Realm | Region | WAD | Physical ID | Marker policy |", "|---|---|---|---|---|---|---|"]
    for row in report["rows"]:
        lines.append(f"| {row['family']} | {row.get('subtype') or ''} | {row.get('realm_id') or ''} | {row.get('region_id') or ''} | {row.get('wad') or ''} | {row.get('physical_id') or ''} | {row['mod_marker_policy']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--catalogue", type=Path, action="append")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    catalogues = args.catalogue or [DEFAULT_CATALOGUE]
    normalized = []
    sources = []
    for path in catalogues:
        path = path.resolve()
        if path.exists():
            sources.append({"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size})
        for row in load_catalogue(path):
            normalized.append(normalize(row, path, policy))
    rows = dedupe(normalized)
    report = {
        "schema": 1,
        "analysis": "master_collectible_inventory",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": policy["source_of_truth"],
        "external_guides_are_audit_only": True,
        "runtime_generation_allowed": False,
        "source_catalogues": sources,
        "policy_sha256": sha(args.policy),
        "policy_hard_rules": policy["hard_rules"],
        "row_count": len(rows),
        "family_audit": discrepancy(policy, rows),
        "rows": rows,
    }
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "master-collectible-inventory.json").write_text(canonical_json(report), encoding="utf-8")
    write_csv(out / "master-collectible-inventory.csv", rows)
    write_md(out / "master-collectible-inventory.md", report)
    mismatches = [r for r in report["family_audit"] if r["status"] not in ("MATCH", "NO_GUIDE_EXPECTATION")]
    print(f"MASTER_COLLECTIBLE_INVENTORY rows={len(rows)} mismatched_families={len(mismatches)} runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
