#!/usr/bin/env python3
"""Check tracked Legendary placement rows against shipped WAD bytes.

This tool reads game files. It writes only research files in this repo.
It does not grant runtime marker use.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import sys
import uuid

import collectible_catalogue as catalogue_tools
import raven_catalogue as raven


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
NATIVE_AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"
OUTPUT_JSON = REPO / "docs/research/legendary-placement-audit.json"
OUTPUT_CSV = REPO / "docs/research/legendary-placement-table.csv"
OUTPUT_MD = REPO / "docs/research/legendary-placement-audit.md"
CLASS_COUNTS = {
    "tracked_legendary": 33,
    "trial_reward": 27,
    "non_map_counted_physical": 2,
    "unresolved_nontracked": 2,
}


def canonical(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def close_vector(left: object, right: object, tolerance: float = 1e-5) -> bool:
    return (isinstance(left, (list, tuple)) and isinstance(right, (list, tuple))
            and len(left) == len(right)
            and all(isinstance(a, (int, float)) and isinstance(b, (int, float))
                    and math.isfinite(a) and math.isfinite(b)
                    and abs(a - b) <= tolerance for a, b in zip(left, right)))


def valid_guid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def add_issue(issues: list[str], condition: bool, code: str) -> None:
    if not condition:
        issues.append(code)


def audit_row(row: dict, native_row: dict | None, wad_root: Path,
              wad_cache: dict[str, tuple[bytes, list[dict]]]) -> dict:
    cid = row["catalogue_id"]
    native = row["native"]
    source = row["source"]
    marker = row["marker"]
    progression = row["progression"]
    physical = native.get("instance_guid")
    carrier = native.get("state_instance_guid")
    wad = source.get("wad")
    paths = native.get("carrier_transform_paths", [])
    chain = source.get("transform_chain", [])
    point = marker.get("position_world")
    issues: list[str] = []

    add_issue(issues, valid_guid(physical), "bad_physical_guid")
    add_issue(issues, valid_guid(carrier), "bad_state_carrier_guid")
    add_issue(issues, native.get("state_carrier_guids") == [carrier], "carrier_list_mismatch")
    add_issue(issues, progression.get("instance_key") == f"{physical}.{carrier}"
              and progression.get("instance_keys") == [f"{physical}.{carrier}"],
              "progression_key_mismatch")
    add_issue(issues, progression.get("state_adapter") == "interact_chest_standard_checkpoint_state"
              and progression.get("field") == "state == OPENED"
              and progression.get("read_only") is True, "state_contract_mismatch")
    add_issue(issues, marker.get("coordinate_wad") == f"WAD_{Path(wad or '').stem}",
              "coordinate_wad_mismatch")
    add_issue(issues, marker.get("name") == catalogue_tools.marker_identity(
        "legendary_chest", physical or "")[0], "marker_name_mismatch")
    add_issue(issues, marker.get("uid") == catalogue_tools.marker_identity(
        "legendary_chest", physical or "")[1]
              and marker.get("compass_class") == "CompletionistLegendaryChest",
              "marker_metadata_mismatch")
    add_issue(issues, len(paths) == 1, "ambiguous_carrier_paths")
    add_issue(issues, len(chain) >= 3 and all(
        isinstance(node.get("name"), str) and isinstance(node.get("record_id"), str)
        and isinstance(node.get("offset"), str) for node in chain), "bad_transform_chain")
    add_issue(issues, isinstance(point, (list, tuple)) and len(point) == 3
              and close_vector(point, point),
              "bad_world_position")
    add_issue(issues, native_row is not None, "missing_native_audit_row")
    if native_row:
        add_issue(issues, native_row.get("classification") == "tracked_legendary"
                  and native_row.get("production_eligibility") == "tracked_collectible"
                  and native_row.get("physical_instance_guid") == physical
                  and native_row.get("state_carrier_guid") == carrier
                  and native_row.get("wad") == wad
                  and close_vector(native_row.get("world_xyz"), point),
                  "native_audit_mismatch")

    native_point = None
    native_matrix = None
    native_path_count = 0
    sha = None
    if wad and not issues:
        try:
            if wad not in wad_cache:
                raw = (wad_root / wad).read_bytes()
                wad_cache[wad] = raw, raven.parse_wad(raw)
            raw, records = wad_cache[wad]
            sha = hashlib.sha256(raw).hexdigest()
            add_issue(issues, sha == source.get("wad_sha256"), "wad_hash_mismatch")
            lookup = {(record["id"].hex(), f"0x{record['offset']:X}"): record
                      for record in records}
            raw_chain = [lookup[(node["record_id"], node["offset"])] for node in chain]
            add_issue(issues, all(record["kind"] == 1 and record["flags"] == 0x3D
                              and record["size"] == 164 for record in raw_chain),
                      "bad_native_transform_record")
            for child, parent in itertools.pairwise(raw_chain):
                add_issue(issues, child["data"][0x54:0x64] == parent["data"][0x0C:0x1C],
                          "broken_transform_parent_link")
            add_issue(issues, raw_chain[-1]["data"][0x54:0x64] == bytes(16),
                      "transform_chain_not_rooted")
            paths_found = catalogue_tools.exact_world_transforms(
                raw_chain[0], records, parent_name="gochest_legendary_parent")
            matching = [path for path in paths_found if path[2] == chain]
            native_path_count = len(matching)
            add_issue(issues, native_path_count == 1, "native_transform_path_not_unique")
            if native_path_count == 1:
                native_matrix, native_point, _chain, matched_raw_chain = matching[0]
                add_issue(issues, close_vector(native_point, point),
                          "world_position_mismatch")
                add_issue(issues, close_vector(native_matrix, source.get("world_transform_matrix")),
                          "world_matrix_mismatch")
                placement_override, placement_final = catalogue_tools.physical_placement(
                    matched_raw_chain, records)
                add_issue(issues, catalogue_tools.placement_instance_guid(
                    placement_override) == physical, "native_physical_guid_mismatch")
                add_issue(issues, placement_override["id"].hex()
                          == native.get("placement_override_record_id")
                          and placement_final["id"].hex()
                          == native.get("placement_final_record_id"),
                          "placement_record_mismatch")
            override = lookup[(native["override_record_id"], source["override_offset"])]
            add_issue(issues, catalogue_tools.native_instance_guid(override) == carrier,
                      "native_state_carrier_mismatch")
            add_issue(issues, override["name"] == native.get("override_name"),
                      "carrier_override_name_mismatch")
            if len(paths) == 1:
                path = paths[0]
                add_issue(issues, path.get("physical_instance_guid") == physical
                          and path.get("state_carrier_guid") == carrier
                          and path.get("wad") == wad
                          and path.get("transform_chain") == chain
                          and close_vector(path.get("world_position"), point)
                          and close_vector(path.get("world_transform_matrix"),
                                           source.get("world_transform_matrix")),
                          "carrier_path_mismatch")
        except (KeyError, IndexError, OSError, ValueError) as exc:
            issues.append(f"native_recheck_failed:{type(exc).__name__}:{exc}")

    return {
        "catalogue_id": cid,
        "status": "VERIFIED_PLACEMENT" if not issues else "UNRESOLVED_PLACEMENT",
        "issues": sorted(set(issues)),
        "physical_guid": physical,
        "state_carrier_guid": carrier,
        "progression_instance_key": progression.get("instance_key"),
        "progression_field": progression.get("field"),
        "read_only": progression.get("read_only"),
        "wad": wad,
        "coordinate_wad": marker.get("coordinate_wad"),
        "world_position": point,
        "native_recomputed_world_position": list(native_point) if native_point else None,
        "native_transform_path_match_count": native_path_count,
        "marker_name_metadata": marker.get("name"),
        "source_wad_sha256": sha,
        "source_override_offset": source.get("override_offset"),
        "source_placement_override_record_id": native.get("placement_override_record_id"),
        "transform_chain": chain,
        "world_transform_matrix": source.get("world_transform_matrix"),
        "proposed_region_summary_target": progression.get("parent_quest"),
        "region_binding_proven": False,
    }


def build_report(game_root: Path) -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    native_audit = json.loads(NATIVE_AUDIT.read_text(encoding="utf-8"))
    raw_rows = [row for row in catalogue["collectibles"]
                if row.get("family") == "legendary_chest"]
    counts = Counter(row.get("native_classification") for row in raw_rows)
    if len(raw_rows) != 64 or counts != CLASS_COUNTS:
        raise ValueError(f"Legendary raw census changed: {len(raw_rows)}, {dict(counts)}")
    if len({row["catalogue_id"] for row in raw_rows}) != len(raw_rows):
        raise ValueError("duplicate Legendary catalogue ID")
    audit_rows = {row["catalogue_id"]: row for row in
                  native_audit["legendary_classification_evidence"]}
    if set(audit_rows) != {row["catalogue_id"] for row in raw_rows}:
        raise ValueError("Legendary native audit census differs")
    tracked = sorted((row for row in raw_rows
                      if row["native_classification"] == "tracked_legendary"),
                     key=lambda row: row["catalogue_id"])
    physical_counts = Counter(row["native"].get("instance_guid") for row in raw_rows)
    cache: dict[str, tuple[bytes, list[dict]]] = {}
    rows = [audit_row(row, audit_rows.get(row["catalogue_id"]),
                      game_root / "exec/wad/pc_le", cache) for row in tracked]
    for field, code in (("physical_guid", "duplicate_physical_guid"),
                        ("progression_instance_key", "duplicate_progression_key"),
                        ("marker_name_metadata", "duplicate_marker_name")):
        keys = Counter(row[field] for row in rows)
        for row in rows:
            if keys[row[field]] != 1:
                row["issues"].append(code)
    for left, right in itertools.combinations(rows, 2):
        if close_vector(left["world_position"], right["world_position"]):
            left["issues"].append("duplicate_world_position")
            right["issues"].append("duplicate_world_position")
    for row in rows:
        if physical_counts[row["physical_guid"]] != 1:
            row["issues"].append("physical_guid_shared_with_raw_pool")
        row["issues"] = sorted(set(row["issues"]))
        row["status"] = "VERIFIED_PLACEMENT" if not row["issues"] else "UNRESOLVED_PLACEMENT"
    excluded = sorted(({"catalogue_id": row["catalogue_id"],
                        "classification": row["native_classification"],
                        "physical_guid": row["native"]["instance_guid"]}
                       for row in raw_rows if row["native_classification"] != "tracked_legendary"),
                      key=lambda item: item["catalogue_id"])
    nearest = min((math.dist(left["world_position"], right["world_position"]),
                   left["catalogue_id"], right["catalogue_id"])
                  for left, right in itertools.combinations(rows, 2))
    nearest_excluded = min((math.dist(row["world_position"], other["marker"]["position_world"]),
                            row["catalogue_id"], other["catalogue_id"],
                            other["native_classification"])
                           for row in rows for other in raw_rows
                           if other["native_classification"] != "tracked_legendary")
    return {
        "schema": 1,
        "scope": "tracked_legendary placement only; no runtime permission",
        "source_catalogue": str(CATALOGUE.relative_to(REPO)).replace("\\", "/"),
        "source_catalogue_lf_sha256": lf_sha256(CATALOGUE),
        "source_native_audit": str(NATIVE_AUDIT.relative_to(REPO)).replace("\\", "/"),
        "source_native_audit_lf_sha256": lf_sha256(NATIVE_AUDIT),
        "raw_legendary_count": len(raw_rows),
        "classification_counts": dict(sorted(counts.items())),
        "tracked_count": len(rows),
        "verified_placement_count": sum(row["status"] == "VERIFIED_PLACEMENT" for row in rows),
        "unresolved_placement_count": sum(row["status"] == "UNRESOLVED_PLACEMENT" for row in rows),
        "distinct_physical_guid_count": len({row["physical_guid"] for row in rows}),
        "distinct_state_carrier_guid_count": len({row["state_carrier_guid"] for row in rows}),
        "distinct_progression_key_count": len({row["progression_instance_key"] for row in rows}),
        "nearest_tracked_pair": {"distance_world_units": nearest[0],
                                 "catalogue_ids": [nearest[1], nearest[2]]},
        "nearest_excluded_raw_row": {
            "distance_world_units": nearest_excluded[0],
            "tracked_catalogue_id": nearest_excluded[1],
            "excluded_catalogue_id": nearest_excluded[2],
            "excluded_classification": nearest_excluded[3],
        },
        "runtime_generation_allowed": False,
        "map_count_membership_proven": False,
        "missing_34th_identity": "UNRESOLVED_SEPARATE_PROBLEM",
        "rows": rows,
        "excluded_raw_rows": excluded,
    }


def csv_text(report: dict) -> str:
    output = io.StringIO(newline="")
    fields = ["catalogue_id", "status", "physical_guid", "state_carrier_guid",
              "progression_instance_key", "wad", "coordinate_wad", "world_x",
              "world_y", "world_z", "source_wad_sha256",
              "source_placement_override_record_id", "transform_record_path", "issues"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        x, y, z = row["world_position"]
        writer.writerow({
            "catalogue_id": row["catalogue_id"], "status": row["status"],
            "physical_guid": row["physical_guid"],
            "state_carrier_guid": row["state_carrier_guid"],
            "progression_instance_key": row["progression_instance_key"],
            "wad": row["wad"], "coordinate_wad": row["coordinate_wad"],
            "world_x": repr(x), "world_y": repr(y), "world_z": repr(z),
            "source_wad_sha256": row["source_wad_sha256"],
            "source_placement_override_record_id": row["source_placement_override_record_id"],
            "transform_record_path": ">".join(node["record_id"] for node in row["transform_chain"]),
            "issues": ";".join(row["issues"]),
        })
    return output.getvalue()


def markdown(report: dict) -> str:
    counts = report["classification_counts"]
    lines = [
        "# Legendary Chest placement audit",
        "",
        "This is a static placement audit of catalogue rows classified exactly as",
        "`tracked_legendary`. It reads shipped WAD bytes. It gives no runtime permission.",
        "",
        f"Raw Legendary physical rows: {report['raw_legendary_count']}. "
        f"Tracked rows: {report['tracked_count']}. Verified placements: "
        f"{report['verified_placement_count']}. Unresolved placements: "
        f"{report['unresolved_placement_count']}.",
        "",
        f"Excluded from this table: {counts['trial_reward']} trial rewards, "
        f"{counts['non_map_counted_physical']} provisional non-map-counted rows, "
        f"{counts['unresolved_nontracked']} unresolved nontracked rows. "
        "See `excluded_raw_rows` in the JSON for exact IDs.",
        "",
        "Each row checks the physical GUID and state carrier in native overrides,",
        "the exact transform record path and parent links, source WAD hash,",
        "the recomputed world transform, catalogue progression key, and native audit row.",
        "All 33 use one shared state carrier GUID; physical GUID plus carrier GUID",
        "makes each instance key distinct.",
        "",
        "| WAD | Physical GUID | State carrier | World position (x, y, z) | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        xyz = ", ".join(repr(value) for value in row["world_position"])
        lines.append(f"| `{row['wad']}` | `{row['physical_guid']}` | "
                     f"`{row['state_carrier_guid']}` | `{xyz}` | {row['status']} |")
    nearest = report["nearest_tracked_pair"]
    near_excluded = report["nearest_excluded_raw_row"]
    lines += [
        "",
        "## Limits",
        "",
        f"Nearest two tracked positions: {nearest['distance_world_units']:.3f} world units "
        f"({', '.join(nearest['catalogue_ids'])}). No exact duplicate position found.",
        f"Nearest excluded physical row is {near_excluded['distance_world_units']:.3f} "
        f"world units from a tracked row: `{near_excluded['excluded_catalogue_id']}` "
        f"({near_excluded['excluded_classification']}). Its class stays outside this table.",
        "World position is native placement data. UI map projection, each chest's",
        "active RegionSummary owner, marker asset readiness, and live visibility",
        "remain unproved. The separate missing 34th identity remains unresolved.",
        "No marker injection, persistence, game file change, or progression write is allowed",
        "by this audit. See `legendary-static-gate.md` for the broader production gate.",
        "",
        "Machine files: `legendary-placement-audit.json` has full record offsets and",
        "transform chains; `legendary-placement-table.csv` is the flat placement table.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=catalogue_tools.GAME)
    parser.add_argument("--check", action="store_true", help="check committed output only")
    args = parser.parse_args()
    report = build_report(args.game_root)
    outputs = {OUTPUT_JSON: canonical(report), OUTPUT_CSV: csv_text(report),
               OUTPUT_MD: markdown(report)}
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"audit output differs: {path}")
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Legendary placement: {report['verified_placement_count']}/{report['tracked_count']} "
          f"verified; {report['unresolved_placement_count']} unresolved; "
          f"{len(report['excluded_raw_rows'])} raw rows excluded")
    return 0 if report["unresolved_placement_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
