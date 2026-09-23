#!/usr/bin/env python3
"""Audit native RegionSummary links for the 33 tracked Legendary rows.

Read-only source scan. Target names and near points cannot prove a chest link.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import uuid

import collectible_catalogue as native


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
PLACEMENTS = REPO / "docs/research/legendary-placement-audit.json"
MARKER_ASSETS = REPO / "docs/research/legendary-native-marker-assets.json"
MAPMASTER = REPO / "build/native-source-cache/mapmaster.dcb"
OUTPUT_JSON = REPO / "docs/research/legendary-region-link-audit.json"
OUTPUT_CSV = REPO / "docs/research/legendary-region-link-table.csv"
OUTPUT_MD = REPO / "docs/research/legendary-region-link-audit.md"
SCRIPT_REL = Path("mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua")
MAPMASTER_SHA256 = "aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0"
QUESTS_SHA256 = "8252d4deb03fa1a705e854397e3b284a213e677875bbb6a1e7636f162853fee6"
SCRIPT_SHA256 = "da77b852b52c53c75853e4f05d6b554f3885dae6f4166f3c1c3f907ee66670cc"
SCRIPT_LINES = {
    435: '  if chestType == "Legendary" then',
    436: '    local found, currentRegion = game.Map.FindPlayerRegion()',
    437: '    local comparisonString = LD.RegionInfo_GetName(currentRegion)',
    438: '    if found and comparisonString ~= "TyrsVault" and comparisonString ~= "TheHallofTyr" then',
    439: '      UpdateRegionSummary(currentRegion, "LegendaryChest")',
    440: '    elseif found and comparisonString == "TyrsVault" then',
    441: '      LD.ActivateAndIncrementQuest("RegionSummary_LegendaryChest_Parent_TyrsVault")',
    442: '    elseif found and comparisonString == "TheHallofTyr" then',
    443: '      LD.ActivateAndIncrementQuest("RegionSummary_LegendaryChest_Parent_TheHallofTyr")',
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_bytes(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if sha256(raw) != expected:
        raise ValueError(f"native source hash changed: {path}")
    return raw


def script_evidence(game_root: Path) -> dict:
    path = game_root / SCRIPT_REL
    raw = source_bytes(path, SCRIPT_SHA256)
    lines = raw.decode("utf-8-sig").splitlines()
    for line_number, expected in SCRIPT_LINES.items():
        if lines[line_number - 1] != expected:
            raise ValueError(f"Legendary dispatch changed at line {line_number}")
    return {
        "source_file": str(SCRIPT_REL).replace("\\", "/"),
        "sha256": sha256(raw),
        "source_kind": "extracted_loose_game_lua",
        "legendary_branch_lines": [435, 447],
        "player_region_call_line": 436,
        "generic_region_summary_line": 439,
        "tyrs_vault_quest_line": 441,
        "hall_of_tyr_quest_line": 443,
        "chest_guid_argument_present": False,
        "rule": "Legendary open selects current player region, then updates region aggregate; two region-name branches call named quests",
    }


def identity_patterns(rows: list[dict]) -> dict[bytes, list[dict]]:
    patterns: dict[bytes, list[dict]] = defaultdict(list)
    for row in rows:
        cid = row["catalogue_id"]
        guid = uuid.UUID(row["native"]["instance_guid"])
        placement = bytes.fromhex(row["native"]["placement_override_record_id"])
        values = {
            "physical_guid_ascii_lower": str(guid).encode("ascii"),
            "physical_guid_ascii_upper": str(guid).upper().encode("ascii"),
            "physical_guid_bytes": guid.bytes,
            "physical_guid_bytes_le": guid.bytes_le,
            "placement_override_record_id_bytes": placement,
        }
        for kind, value in values.items():
            patterns[value].append({"catalogue_id": cid, "encoding": kind})
    return patterns


def scan_dcb_identity_refs(dcb_root: Path, rows: list[dict]) -> tuple[int, dict[str, list[dict]]]:
    patterns = identity_patterns(rows)
    regex = re.compile(b"|".join(re.escape(value) for value in
                                 sorted(patterns, key=lambda item: (-len(item), item))))
    hits: dict[str, list[dict]] = {row["catalogue_id"]: [] for row in rows}
    files = sorted(dcb_root.glob("*.dcb"), key=lambda path: path.name.lower())
    if len(files) != 561:
        raise ValueError(f"native DCB census changed: {len(files)}")
    for path in files:
        raw = path.read_bytes()
        for match in regex.finditer(raw):
            for owner in patterns[match.group()]:
                hits[owner["catalogue_id"]].append({
                    "source_file": path.name,
                    "offset": f"0x{match.start():X}",
                    "encoding": owner["encoding"],
                })
    return len(files), hits


def target_offsets(raw: bytes, target: str) -> list[str]:
    token = target.encode("ascii") + b"\0"
    return [f"0x{match.start():X}" for match in re.finditer(re.escape(token), raw)]


def classify_link(*, physical_guid: str, target: str,
                  exact_identity_to_target_edges: list[dict],
                  map_world_point: list[float] | None,
                  proposed_target_exists: bool) -> str:
    """Only one exact native chest-to-target edge may prove a link."""
    _ = map_world_point
    if proposed_target_exists and len(exact_identity_to_target_edges) == 1:
        edge = exact_identity_to_target_edges[0]
        if (edge.get("native_record_path") and edge.get("physical_guid") == physical_guid
                and edge.get("target") == target):
            return "PROVEN_UNIQUE_NATIVE_LINK"
    return "UNRESOLVED_NO_UNIQUE_NATIVE_LINK"


def build_report(game_root: Path) -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    placements = json.loads(PLACEMENTS.read_text(encoding="utf-8"))
    marker_assets = json.loads(MARKER_ASSETS.read_text(encoding="utf-8"))
    rows = sorted((row for row in catalogue["collectibles"]
                   if row.get("family") == "legendary_chest"
                   and row.get("native_classification") == "tracked_legendary"),
                  key=lambda row: row["catalogue_id"])
    if len(rows) != 33 or len({row["catalogue_id"] for row in rows}) != 33:
        raise ValueError("tracked Legendary input changed")
    placement_rows = {row["catalogue_id"]: row for row in placements["rows"]}
    if (set(placement_rows) != {row["catalogue_id"] for row in rows}
            or placements["verified_placement_count"] != 33):
        raise ValueError("placement baseline changed")
    for row in rows:
        proven = placement_rows[row["catalogue_id"]]
        if (proven["status"] != "VERIFIED_PLACEMENT"
                or proven["physical_guid"] != row["native"]["instance_guid"]
                or proven["world_position"] != row["marker"]["position_world"]):
            raise ValueError(f"placement input differs: {row['catalogue_id']}")

    map_raw = source_bytes(MAPMASTER, MAPMASTER_SHA256)
    dcb_root = game_root / "exec/dc/pc_le"
    quests_raw = source_bytes(dcb_root / "quests.dcb", QUESTS_SHA256)
    marker_map = marker_assets["mapmaster"]
    if (marker_map["sha256"] != MAPMASTER_SHA256
            or marker_map["marker_rows"] != 382
            or marker_map["legendary_or_chest_class_hits"]):
        raise ValueError("native marker audit changed")
    script = script_evidence(game_root)
    quest_records = native.quest_target_records(dcb_root)
    dcb_count, identity_hits = scan_dcb_identity_refs(dcb_root, rows)
    claim_counts = Counter(row["progression"].get("parent_quest") for row in rows)
    results = []
    for row in rows:
        cid = row["catalogue_id"]
        target = row["progression"].get("parent_quest")
        map_offsets = target_offsets(map_raw, target)
        quest_offsets = target_offsets(quests_raw, target)
        level = native.native_level_metadata(dcb_root, row["source"]["wad"])
        if target not in quest_records or len(map_offsets) != 1 or len(quest_offsets) != 1:
            raise ValueError(f"proposed target source changed: {cid}")
        # Map and quest records name a shared target. No record joins the chest.
        exact_edges: list[dict] = []
        link_status = classify_link(
            physical_guid=row["native"]["instance_guid"], target=target,
            exact_identity_to_target_edges=exact_edges,
            map_world_point=None, proposed_target_exists=True)
        results.append({
            "catalogue_id": cid,
            "physical_guid": row["native"]["instance_guid"],
            "state_carrier_guid": row["native"]["state_instance_guid"],
            "progression_instance_key": row["progression"]["instance_key"],
            "source_wad": row["source"]["wad"],
            "source_wad_sha256": row["source"]["wad_sha256"],
            "placement_override_record_id": row["native"]["placement_override_record_id"],
            "placement_final_record_id": row["native"]["placement_final_record_id"],
            "placement_final_record_offset": next(
                node["offset"] for node in row["source"]["transform_chain"]
                if node["record_id"] == row["native"]["placement_final_record_id"]),
            "placement_transform_chain": placement_rows[cid]["transform_chain"],
            "physical_world_point": row["marker"]["position_world"],
            "source_level_dcb": level["source_file"],
            "source_level_dcb_sha256": level["source_file_sha256"],
            "source_level_export_offsets": level["wad_export_record_offsets"],
            "source_level_export_name": level["wad_export_name"],
            "source_level_to_player_region_edge": None,
            "shared_interaction_script_guid": row["native"]["script_guid"],
            "shared_interaction_script_file": script["source_file"],
            "player_region_dispatch_line": script["player_region_call_line"],
            "proposed_region_summary_target": target,
            "proposed_target_source": row["progression"].get("parent_quest_source"),
            "proposed_target_claim_row_count": claim_counts[target],
            "mapmaster_target_string_offsets": map_offsets,
            "quests_target_string_offsets": quest_offsets,
            "quests_target_record_offset": quest_records[target]["quest_record_offset"],
            "quests_target_count": quest_records[target]["target"],
            "dcb_identity_reference_hits": identity_hits[cid],
            "exact_chest_to_target_edges": exact_edges,
            "map_world_point": None,
            "world_point_comparison": "UNAVAILABLE_NO_PER_CHEST_MAP_POINT",
            "link_status": link_status,
            "link_diagnostics": {
                "missing_direct_edge": True,
                "ambiguous_direct_edges": False,
                "duplicated_direct_edges": False,
                "indirect_target_only": True,
                "unresolved": True,
            },
            "unresolved_reason": (
                "Stock Legendary script selects current player region at open. "
                "Native target and level records have no proved edge from this "
                "physical chest to that active region; target names are indirect."
            ),
        })
    distinct_targets = {row["proposed_region_summary_target"]:
                        row["quests_target_count"] for row in results}
    return {
        "schema": 1,
        "status": "BLOCKED_ARCHITECTURE_MISMATCH",
        "scope": "33 existing tracked Legendary rows; no classification or identity change",
        "tracked_count": len(results),
        "proven_unique_link_count": sum(row["link_status"] == "PROVEN_UNIQUE_NATIVE_LINK"
                                        for row in results),
        "unresolved_link_count": sum(row["link_status"] != "PROVEN_UNIQUE_NATIVE_LINK"
                                     for row in results),
        "proposed_target_count": len(distinct_targets),
        "proposed_target_goal_sum": sum(distinct_targets.values()),
        "proposed_target_source_counts": dict(sorted(Counter(
            row["proposed_target_source"] for row in results).items())),
        "native_dcb_files_scanned": dcb_count,
        "native_dcb_identity_reference_hit_count": sum(len(row["dcb_identity_reference_hits"])
                                                       for row in results),
        "mapmaster": {"source_file": "build/native-source-cache/mapmaster.dcb",
                      "sha256": sha256(map_raw), "authored_marker_rows": 382,
                      "legendary_or_chest_icon_class_hits": []},
        "quests": {"source_file": "exec/dc/pc_le/quests.dcb",
                   "sha256": sha256(quests_raw)},
        "interaction_script": script,
        "map_side_point_count": 0,
        "runtime_generation_allowed": False,
        "rows": results,
    }


def csv_text(report: dict) -> str:
    out = io.StringIO(newline="")
    columns = ["catalogue_id", "link_status", "physical_guid", "source_wad",
               "source_level_dcb", "source_level_export_offsets",
               "proposed_region_summary_target", "proposed_target_source",
               "mapmaster_target_string_offsets", "quests_target_record_offset",
               "dcb_identity_reference_hit_count", "map_world_point", "unresolved_reason"]
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        writer.writerow({
            key: (";".join(value) if isinstance(value, list) else value)
            for key, value in row.items() if key in columns
        } | {"dcb_identity_reference_hit_count": len(row["dcb_identity_reference_hits"])})
    return out.getvalue()


def markdown(report: dict) -> str:
    lines = [
        "# Legendary Chest RegionSummary link audit",
        "",
        "Static result: **0/33 unique chest-to-RegionSummary links proved**; "
        "33/33 unresolved. No runtime work may start from this result.",
        "",
        "## Native route found",
        "",
        "The extracted game Lua `interact_chest_standard.lua`, lines 435-443,",
        "calls `game.Map.FindPlayerRegion()` when a Legendary Chest opens.",
        "It updates the resulting region aggregate. Two region-name branches",
        "call the Tyr quest targets. The call takes no physical chest GUID.",
        "The active player region at each chest point has no proved static",
        "chest-to-zone edge. This breaks the assumed per-chest map link model.",
        "",
        "The pinned `mapmaster.dcb` holds the proposed target names; `quests.dcb`",
        "holds target records. These are shared summary data. A target name,",
        "WAD name, target count, or near point cannot prove chest ownership.",
        f"The {report['proposed_target_count']} proposed quest targets sum to "
        f"{report['proposed_target_goal_sum']} chests, but this count cannot bind a row.",
        f"Exact physical GUID and placement-record patterns had "
        f"{report['native_dcb_identity_reference_hit_count']} hits across "
        f"{report['native_dcb_files_scanned']} native DCB files.",
        "The pinned mapmaster has 382 authored markers and no",
        "Legendary/Chest-named icon class. No per-chest map point was found.",
        "This negative scan does not rule out a dynamic or differently named path.",
        "",
        "| WAD | Physical GUID | Proposed target | Target basis | Link |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        lines.append(f"| `{row['source_wad']}` | `{row['physical_guid']}` | "
                     f"`{row['proposed_region_summary_target']}` | "
                     f"`{row['proposed_target_source']}` | unresolved |")
    lines += [
        "",
        "## Stop point",
        "",
        "All 33 placement chains stay valid. This audit changes no catalogue row.",
        "Map-side world point and point comparison stay null for all 33.",
        "Next proof needs an exact source that binds each chest interaction",
        "point to the player region selected by `FindPlayerRegion()`, or another",
        "native chest-to-summary edge. No region assignment is guessed here.",
        "Chest #34 stays out of scope. Game stayed closed. No mapmaster,",
        "progression, persistence, runtime marker, or Raven file changed.",
        "",
        "Exact IDs, hashes, record offsets, and reasons are in",
        "`legendary-region-link-audit.json`; flat rows are in",
        "`legendary-region-link-table.csv`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=native.GAME)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report(args.game_root)
    outputs = {OUTPUT_JSON: json.dumps(report, sort_keys=True, indent=2) + "\n",
               OUTPUT_CSV: csv_text(report), OUTPUT_MD: markdown(report)}
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"audit output differs: {path}")
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Legendary RegionSummary links: {report['proven_unique_link_count']}/33 "
          f"proven; {report['unresolved_link_count']} unresolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
