#!/usr/bin/env python3
"""Read-only Legendary chest identity and progression audit for 33 pinned rows."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

import collectible_catalogue as catalogue_tools
import legendary_chest_identity as identity
import raven_catalogue as raven


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
PLACEMENTS = REPO / "docs/research/legendary-placement-audit.json"
REGION_LINKS = REPO / "docs/research/legendary-region-link-audit.json"
SERIALIZED = REPO / "archive/field-logs/source-scans/legendary-serialized-identities-static-20260922-152212/report.json"
STAGED = REPO / "archive/field-logs/source-scans/legendary-staged-state-20260922-142029/report.json"
OUTPUT_JSON = REPO / "docs/research/legendary-progression-identity-audit.json"
OUTPUT_CSV = REPO / "docs/research/legendary-progression-identity-table.csv"
OUTPUT_MD = REPO / "docs/research/legendary-progression-identity-audit.md"
CHEST_SCRIPT = Path("mods/lua_source/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua")
QUEST_LIBRARY = Path("mods/lua_source/gameart/scripts/libraries/design/questlibrary.lua")
CHEST_SCRIPT_SHA = "943021f321c708561e62d4c9b6926c01b3c131c2057fbed7e4c136dbed707bdc"
QUEST_LIBRARY_SHA = "c5093a0407a764aa33d1560c45a53615b2d822d6dc82d2ac36f236e30c9d5c7f"
QUESTS_SHA = "8252d4deb03fa1a705e854397e3b284a213e677875bbb6a1e7636f162853fee6"
SCAN_KINDS = (
    "logical_key_ascii", "native_state_path_ascii", "serialized_key_binary", "serialized_key_hex_ascii",
    "object_hash_le_binary", "object_hash_be_binary", "object_hash_hex_ascii",
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned_text(root: Path, relative: Path, expected_sha: str,
                required: tuple[str, ...]) -> dict:
    raw = (root / relative).read_bytes()
    if digest(raw) != expected_sha:
        raise ValueError(f"source hash changed: {relative}")
    lines = raw.decode("utf-8-sig").splitlines()
    found = {}
    for token in required:
        locations = [index + 1 for index, line in enumerate(lines) if token in line]
        if not locations:
            raise ValueError(f"source path missing {token}: {relative}")
        found[token] = locations
    return {"source_file": str(relative).replace("\\", "/"),
            "sha256": digest(raw), "symbol_lines": found}


def source_contract(game_root: Path) -> dict:
    chest = pinned_text(game_root, CHEST_SCRIPT, CHEST_SCRIPT_SHA, (
        "function OnInteractStart(", "function OnOpened()", "state = states.OPENED",
        'LD.ExecuteCallbacksForEvent(thisLevel, thisObj, onOpenedEvent, "onOpenedEvent")',
        "game.Map.FindPlayerRegion()", 'UpdateRegionSummary(currentRegion, "LegendaryChest")',
        'LD.ActivateAndIncrementQuest("RegionSummary_LegendaryChest_Parent_TyrsVault")',
        'LD.ActivateAndIncrementQuest("RegionSummary_LegendaryChest_Parent_TheHallofTyr")',
        'game.Map.GetRegionSummaryInfo(regionID)',
        'LD.RollContainerConditionLoot(reward, rewardTier, WADName, rewardTierIndex)',
        "game.World.StoreCheckpoint()", "game.SubObject.SoftSave(thisObj)",
        "function OnSaveCheckpoint(", "return {state = state}",
        "function OnRestoreCheckpoint(", "state = savedInfo.state",
    ))
    quest = pinned_text(game_root, QUEST_LIBRARY, QUEST_LIBRARY_SHA, (
        "local ActivateAndIncrementQuest = function(questName)",
        "game.QuestManager.GetQuestState(questName)",
        "game.QuestManager.StartQuest(questName)",
        "game.QuestManager.IncrementQuestProgress(questName, 1)",
    ))
    return {
        "chest_script": chest,
        "quest_library": quest,
        "chest_local_state": "OnOpened sets state=OPENED; OnSaveCheckpoint returns {state=state}; OnRestoreCheckpoint reads savedInfo.state",
        "persistence_route": "PutAway uses StoreCheckpoint when CheckpointOnOpened, else SubObject.SoftSave(thisObj) when available",
        "region_progression": "OnOpened calls FindPlayerRegion and UpdateRegionSummary; Tyr name branches call a fixed quest",
        "quest_counter": "ActivateAndIncrementQuest starts inactive quest then increments progress by 1, or increments active quest by 1",
        "reward_route": "AwardLoot calls RollContainerConditionLoot with reward/tier/WAD inputs",
        "map_ui_route": "GetRegionSummaryInfo selects a category; no per-chest marker registration proved by these scripts",
        "callback_limit": "OnOpened event entry exists; native animation caller and optional per-instance callbacks are not fully proved here",
    }


def patterns_for(rows: list[dict], identities: dict[str, dict],
                 overrides: dict[str, dict]) -> dict[bytes, list[tuple[str, str]]]:
    patterns: dict[bytes, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        cid = row["catalogue_id"]
        found = identities[cid]
        obj_hash = int(found["object_hash_hex"], 16)
        values = {
            "logical_key_ascii": row["progression"]["instance_key"].encode("ascii"),
            "native_state_path_ascii": overrides[cid]["native_state_path"].encode("ascii"),
            "serialized_key_binary": bytes.fromhex(found["serialized_flag1_hex"]),
            "serialized_key_hex_ascii": found["serialized_flag1_hex"].encode("ascii"),
            "object_hash_le_binary": obj_hash.to_bytes(8, "little"),
            "object_hash_be_binary": obj_hash.to_bytes(8, "big"),
            "object_hash_hex_ascii": found["object_hash_hex"].encode("ascii"),
        }
        for kind, token in values.items():
            patterns[token].append((cid, kind))
    return patterns


def scan_files(paths: list[Path], patterns: dict[bytes, list[tuple[str, str]]],
               category: str, *, wad_records: bool = False) -> dict[str, list[dict]]:
    expression = re.compile(b"|".join(re.escape(token) for token in
                                      sorted(patterns, key=lambda item: (-len(item), item))))
    hits: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(paths, key=lambda item: item.name.lower()):
        raw = path.read_bytes()
        matches = list(expression.finditer(raw))
        if not matches:
            continue
        records = raven.parse_wad(raw) if wad_records else []
        offsets = [record["offset"] for record in records]
        for match in matches:
            owners = patterns[match.group()]
            for cid, kind in owners:
                hit = {"source_file": path.name, "offset": f"0x{match.start():X}",
                       "representation": kind, "source_category": category}
                if records:
                    index = bisect_right(offsets, match.start()) - 1
                    record = records[index]
                    if record["offset"] + 96 <= match.start() < record["offset"] + 96 + record["size"]:
                        hit["record_name"] = record["name"]
                        hit["record_id"] = record["id"].hex()
                        hit["record_offset"] = f"0x{record['offset']:X}"
                hits[cid].append(hit)
    return hits


def scan_override_tokens(game_root: Path, rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["source"]["wad"]].append(row)
    output = {}
    for wad, wad_rows in sorted(grouped.items()):
        raw = (game_root / "exec/wad/pc_le" / wad).read_bytes()
        source_hashes = {row["source"]["wad_sha256"] for row in wad_rows}
        if source_hashes != {digest(raw)}:
            raise ValueError(f"native WAD hash changed: {wad}")
        records = raven.parse_wad(raw)
        by_id = {record["id"].hex(): record for record in records}
        by_offset = {record["offset"]: record for record in records}
        for row in wad_rows:
            script_override = by_offset[int(row["source"]["override_offset"], 16)]
            placement_override = by_id[row["native"]["placement_override_record_id"]]
            if (script_override["name"] != "gochestscript_overrideInst"
                    or script_override["id"].hex() != row["native"]["override_record_id"]):
                raise ValueError(f"script override changed: {row['catalogue_id']}")
            texts = catalogue_tools.strings(script_override["data"])
            place_texts = catalogue_tools.strings(placement_override["data"])
            relevant = ("quest", "objective", "event", "trigger", "regionsummary", "mapicon")
            state_paths = [value for value in place_texts
                           if value.startswith(row["native"]["instance_guid"] + ".")
                           and value.endswith("." + row["native"]["state_instance_guid"])]
            if len(state_paths) != 1:
                raise ValueError(f"native state path not unique: {row['catalogue_id']}")
            output[row["catalogue_id"]] = {
                "native_state_path": state_paths[0],
                "catalogue_key_matches_native_path": (
                    row["progression"]["instance_key"] == state_paths[0]),
                "script_override_record_id": script_override["id"].hex(),
                "script_override_record_offset": f"0x{script_override['offset']:X}",
                "script_override_data_sha256": digest(script_override["data"]),
                "script_override_size": script_override["size"],
                "script_override_relevant_ascii_tokens": sorted({
                    text for text in texts if any(term in text.lower() for term in relevant)}),
                "placement_override_relevant_ascii_tokens": sorted({
                    text for text in place_texts if any(term in text.lower() for term in relevant)}),
            }
    return output


def bridge_status(*, native_path_hits: list[dict], staged_exact: bool,
                  staged_represented: bool) -> str:
    if len(native_path_hits) != 1:
        return "UNRESOLVED_NATIVE_STATE_PATH_WAD_LINK"
    if staged_represented and staged_exact:
        return "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE"
    if staged_represented:
        return "UNRESOLVED_FROZEN_STATE_MISMATCH"
    return "DERIVED_LOCAL_KEY_NO_FROZEN_STATE_OBSERVATION"


def current_identities(rows: list[dict], staged: dict, prior: dict) -> dict[str, dict]:
    """Recompute current 33; prior snapshot contains two superseded tracked IDs."""
    prior_by_guid = {item["instance_guid"]: item for item in prior["identities"]}
    staged_by_wad = {item["wad"].lower(): item for item in staged["wads"]}
    output = {}
    for row in rows:
        guid = row["native"]["instance_guid"]
        wad = row["source"]["wad"].lower()
        scene, skipped = identity.scene_identity_elements(row)
        obj_hash = identity.identity_hash(scene + [identity.CHEST_OWN_IDENTITY_ELEMENT])
        registry = identity.registry_hash_for_wad(wad)
        payload = identity.serialized_payload(registry, obj_hash).hex()
        source = staged_by_wad.get(wad)
        represented = bool(source and source["capture_present"])
        matches = []
        if represented:
            for entry in source["state_entries"]:
                if entry.get("field_signature") != [{"name": "state", "value_tag": 1}]:
                    continue
                parent = entry.get("parent") or {}
                if parent.get("record_class_key_hex") != "0x75E050AB149B4062":
                    continue
                if parent.get("record_payload_hex") == payload:
                    matches.append(entry)
        if len(matches) > 1:
            raise ValueError(f"duplicate frozen state binding: {guid}")
        match = matches[0] if matches else None
        state = ({"state_raw_hex": match["state"]["raw_hex"],
                  "state_u32": match["state"]["decoded"],
                  "state_row": match.get("state_row"),
                  "subobj_table_row": match.get("subobj_table_row")}
                 if match else None)
        found = {
            "instance_guid": guid,
            "state_instance_guid": row["native"]["state_instance_guid"],
            "registry_hash_hex": f"0x{registry:016X}",
            "object_hash_hex": f"0x{obj_hash:016X}",
            "serialized_flag1_hex": payload,
            "staged_represented": represented,
            "staged_simple_state_match": match is not None,
            "staged_state": state,
            "scene_identity_elements_hex": [part.hex() for part in scene],
            "skipped_transform_nodes": skipped,
            "prior_snapshot_entry_present": guid in prior_by_guid,
        }
        old = prior_by_guid.get(guid)
        if old:
            for key in ("registry_hash_hex", "object_hash_hex", "serialized_flag1_hex",
                        "staged_represented", "staged_simple_state_match", "staged_state"):
                if old[key] != found[key]:
                    raise ValueError(f"prior frozen identity differs: {guid} {key}")
        output[row["catalogue_id"]] = found
    return output


def build_report(game_root: Path) -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    placements = json.loads(PLACEMENTS.read_text(encoding="utf-8"))
    region_links = json.loads(REGION_LINKS.read_text(encoding="utf-8"))
    serialized = json.loads(SERIALIZED.read_text(encoding="utf-8"))
    staged = json.loads(STAGED.read_text(encoding="utf-8"))
    rows = sorted((row for row in catalogue["collectibles"]
                   if row.get("family") == "legendary_chest"
                   and row.get("native_classification") == "tracked_legendary"),
                  key=lambda row: row["catalogue_id"])
    if len(rows) != 33 or placements["verified_placement_count"] != 33:
        raise ValueError("pinned 33-row input changed")
    placement_by_id = {row["catalogue_id"]: row for row in placements["rows"]}
    region_by_id = {row["catalogue_id"]: row for row in region_links["rows"]}
    ids = {row["catalogue_id"] for row in rows}
    if (set(placement_by_id) != ids or set(region_by_id) != ids
            or serialized["status"] != "EXACT_32_OF_32_STAGED_BINDING"
            or region_links["proven_unique_link_count"] != 0):
        raise ValueError("prior Legendary input audit changed")
    identities = current_identities(rows, staged, serialized)
    contract = source_contract(game_root)
    overrides = scan_override_tokens(game_root, rows)
    patterns = patterns_for(rows, identities, overrides)
    wad_names = {row["source"]["wad"] for row in rows}
    wad_root = game_root / "exec/wad/pc_le"
    wad_hits = scan_files([wad_root / name for name in wad_names], patterns, "native_wad",
                          wad_records=True)
    dcb_root = game_root / "exec/dc/pc_le"
    dcb_paths = list(dcb_root.glob("*.dcb"))
    if len(dcb_paths) != 561:
        raise ValueError("native DCB census changed")
    dcb_hits = scan_files(dcb_paths, patterns, "native_dcb")
    lua_paths = list((game_root / "mods/lua_source").rglob("*.lua"))
    if len(lua_paths) != 493:
        raise ValueError("pristine Lua source census changed")
    lua_hits = scan_files(lua_paths, patterns, "pristine_lua_source")

    quest_raw = (dcb_root / "quests.dcb").read_bytes()
    if digest(quest_raw) != QUESTS_SHA:
        raise ValueError("quests.dcb source changed")
    quest_records = catalogue_tools.quest_target_records(dcb_root)
    targets = {row["proposed_region_summary_target"]:
               row["quests_target_count"] for row in region_by_id.values()}
    if len(targets) != 18 or sum(targets.values()) != 33:
        raise ValueError("18 target aggregate changed")
    for name, count in targets.items():
        if quest_records[name]["target"] != count:
            raise ValueError(f"quest target changed: {name}")

    output_rows = []
    for row in rows:
        cid = row["catalogue_id"]
        placed = placement_by_id[cid]
        found = identities[cid]
        region = region_by_id[cid]
        if (placed["physical_guid"] != row["native"]["instance_guid"]
                or placed["world_position"] != row["marker"]["position_world"]
                or found["instance_guid"] != row["native"]["instance_guid"]
                or found["state_instance_guid"] != row["native"]["state_instance_guid"]):
            raise ValueError(f"physical/identity input changed: {cid}")
        scene, _skipped = identity.scene_identity_elements(row)
        expected_hash = identity.identity_hash(scene + [identity.CHEST_OWN_IDENTITY_ELEMENT])
        expected_registry = identity.registry_hash_for_wad(row["source"]["wad"])
        if (found["object_hash_hex"] != f"0x{expected_hash:016X}"
                or found["registry_hash_hex"] != f"0x{expected_registry:016X}"
                or found["serialized_flag1_hex"] != identity.serialized_payload(
                    expected_registry, expected_hash).hex()):
            raise ValueError(f"serialized native identity changed: {cid}")
        own_hits = wad_hits[cid]
        logical = [hit for hit in own_hits if hit["representation"] == "logical_key_ascii"]
        native_path_hits = [hit for hit in own_hits
                            if hit["representation"] == "native_state_path_ascii"]
        if (len(native_path_hits) != 1
                or native_path_hits[0]["source_file"] != row["source"]["wad"]
                or native_path_hits[0].get("record_id") != row["native"]["placement_override_record_id"]):
            raise ValueError(f"native state path lacks exact placement record: {cid}")
        status = bridge_status(native_path_hits=native_path_hits,
                               staged_exact=bool(found["staged_simple_state_match"]),
                               staged_represented=bool(found["staged_represented"]))
        staged = found.get("staged_state")
        output_rows.append({
            "catalogue_id": cid,
            "physical_guid": row["native"]["instance_guid"],
            "physical_state_key": row["progression"]["instance_key"],
            "native_state_path": overrides[cid]["native_state_path"],
            "catalogue_key_matches_native_path": overrides[cid]["catalogue_key_matches_native_path"],
            "native_state_path_record_id": native_path_hits[0]["record_id"],
            "native_state_path_record_offset": native_path_hits[0]["record_offset"],
            "world_position": placed["world_position"],
            "wad": row["source"]["wad"],
            "wad_sha256": row["source"]["wad_sha256"],
            "logical_key_native_hits": logical,
            "native_state_path_hits": native_path_hits,
            "native_gameobject_registry_hash": found["registry_hash_hex"],
            "native_gameobject_object_hash": found["object_hash_hex"],
            "native_serialized_state_key_hex": found["serialized_flag1_hex"],
            "state_carrier_guid": found["state_instance_guid"],
            "staged_frozen_capture_represented": found["staged_represented"],
            "staged_exact_match": found["staged_simple_state_match"],
            "staged_state_raw_hex": staged["state_raw_hex"] if staged else None,
            "staged_state_u32": (int(staged["state_u32"]) if staged else None),
            "prior_identity_snapshot_entry_present": found["prior_snapshot_entry_present"],
            "local_bridge_status": status,
            "local_bridge_proof_type": (
                "exact_native_placement_key_plus_structural_serialized_identity_plus_frozen_state"
                if status == "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE" else
                "exact_native_placement_key_plus_structural_serialized_identity_only"),
            "native_wad_other_key_hits": [hit for hit in own_hits
                                          if hit not in logical and hit not in native_path_hits],
            "native_dcb_key_hits": dcb_hits[cid],
            "pristine_lua_key_hits": lua_hits[cid],
            "override_evidence": overrides[cid],
            "region_quest_claim": region["proposed_region_summary_target"],
            "region_quest_goal": region["quests_target_count"],
            "region_quest_record_offset": region["quests_target_record_offset"],
            "region_quest_membership_proven": False,
            "region_link_status": region["link_status"],
            "event_or_objective_identity": None,
            "event_or_objective_unresolved_reason": (
                "No per-chest event/objective alias proved. Script has optional callbacks; "
                "native override ASCII has no named quest/event/trigger token for this row."),
            "runtime_delivery_ready": False,
            "unresolved_reason": (None if status == "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE"
                                  else "No exact state observation for this current tracked row in frozen staged capture; serialized key is structural only"),
        })
    key_counts = Counter(row["native_serialized_state_key_hex"] for row in output_rows)
    if len(key_counts) != 33 or any(count != 1 for count in key_counts.values()):
        raise ValueError("serialized state keys collide")
    return {
        "schema": 1,
        "status": "LOCAL_STATE_BRIDGE_PARTIAL_REGION_MEMBERSHIP_UNPROVED",
        "scope": "33 existing tracked Legendary rows; no runtime or progression writes",
        "tracked_count": 33,
        "proven_local_persisted_bridge_count": sum(
            row["local_bridge_status"] == "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE"
            for row in output_rows),
        "derived_unobserved_local_bridge_count": sum(
            row["local_bridge_status"] != "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE"
            for row in output_rows),
        "proven_per_chest_region_membership_count": 0,
        "native_serialized_state_key_count": len(key_counts),
        "catalogue_state_path_mismatch_count": sum(
            not row["catalogue_key_matches_native_path"] for row in output_rows),
        "current_rows_missing_prior_identity_snapshot": [row["catalogue_id"] for row in output_rows
                                                       if not row["prior_identity_snapshot_entry_present"]],
        "prior_identity_snapshot_rows_outside_current_tracked_set": sorted(
            item["catalogue_id"] for item in serialized["identities"]
            if item["instance_guid"] not in {row["physical_guid"] for row in output_rows}),
        "state_carrier_guid_count": len({row["state_carrier_guid"] for row in output_rows}),
        "quest_target_count": len(targets),
        "quest_target_goal_sum": sum(targets.values()),
        "quest_targets": dict(sorted(targets.items())),
        "native_wad_files_scanned": len(wad_names),
        "native_dcb_files_scanned": len(dcb_paths),
        "pristine_lua_files_scanned": len(lua_paths),
        "source_contract": contract,
        "frozen_identity_report": str(SERIALIZED.relative_to(REPO)).replace("\\", "/"),
        "frozen_identity_report_sha256": digest(SERIALIZED.read_bytes().replace(b"\r\n", b"\n")),
        "frozen_staged_state_report": str(STAGED.relative_to(REPO)).replace("\\", "/"),
        "frozen_staged_state_report_sha256": digest(STAGED.read_bytes().replace(b"\r\n", b"\n")),
        "native_representation_hit_counts": dict(sorted(Counter(
            hit["representation"] for row in output_rows for key in (
                "logical_key_native_hits", "native_state_path_hits", "native_wad_other_key_hits",
                "native_dcb_key_hits", "pristine_lua_key_hits") for hit in row[key]).items())),
        "script_override_data_hash_counts": dict(sorted(Counter(
            row["override_evidence"]["script_override_data_sha256"]
            for row in output_rows).items())),
        "runtime_delivery_ready": False,
        "runtime_blockers": [
            "three current tracked chests have no observed persisted state in frozen capture",
            "no native per-chest RegionSummary/active player-region membership edge",
            "Legendary marker assets and unloaded-state query path remain unproved",
        ],
        "rows": output_rows,
    }


def csv_text(report: dict) -> str:
    out = io.StringIO(newline="")
    columns = ["catalogue_id", "physical_guid", "physical_state_key", "native_state_path",
               "catalogue_key_matches_native_path", "native_state_path_record_id",
               "native_state_path_record_offset", "wad",
               "world_x", "world_y", "world_z", "native_gameobject_registry_hash",
               "native_gameobject_object_hash", "native_serialized_state_key_hex",
               "local_bridge_status", "staged_state_raw_hex", "region_quest_claim",
               "region_quest_record_offset",
               "region_quest_membership_proven", "event_or_objective_identity",
               "unresolved_reason"]
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        x, y, z = row["world_position"]
        writer.writerow({key: row.get(key) for key in columns if key not in
                         {"world_x", "world_y", "world_z"}} |
                        {"world_x": repr(x), "world_y": repr(y), "world_z": repr(z)})
    return out.getvalue()


def markdown(report: dict) -> str:
    lines = [
        "# Legendary Chest native identity and progression audit",
        "",
        "## Result",
        "",
        f"{report['proven_local_persisted_bridge_count']}/33 have an exact native "
        "placement key, derived serialized GameObject key, and exact frozen",
        "checkpoint state match. Three current tracked rows have a structural",
        "key but no state observation in the frozen capture.",
        "No per-chest RegionSummary membership or extra event/objective alias was proved.",
        "Runtime delivery stays blocked.",
        "",
        "Each physical placement override has a full native state path.",
        f"{report['catalogue_state_path_mismatch_count']} catalogue keys differ from",
        "that full path. This audit flags them; it does not alter catalogue data.",
        "The persisted checkpoint lookup uses a different 17-byte serialized",
        "GameObject key: flag 1 + WAD registry hash + object identity hash.",
        "The shared state carrier GUID is not a unique chest key by itself.",
        "All 33 serialized keys are distinct. The frozen capture has 30 exact",
        "state matches for the current tracked set. The older identity snapshot",
        "contains two superseded tracked IDs and omits two current IDs.",
        "Current keys were recomputed and checked against the frozen state report.",
        "The three unobserved WADs are `xpl100_httk.wad`,",
        "`cal500_runevault.wad`, and `cal740_leftwing.wad`.",
        "",
        "## Catalogue state-path discrepancy",
        "",
        "Two catalogue `physical.state` keys omit the middle GUID",
        "`1a10ffb6-4e57-7e17-2604-f4b11ae71140` that exists in the exact",
        "native placement override path:",
        "",
        "| Physical GUID | WAD | Catalogue key | Native state path |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        if not row["catalogue_key_matches_native_path"]:
            lines.append(f"| `{row['physical_guid']}` | `{row['wad']}` | "
                         f"`{row['physical_state_key']}` | `{row['native_state_path']}` |")
    lines += [
        "",
        "The native path and frozen GameObject state both bind these two",
        "physical chests. The catalogue is left unchanged by request.",
        "",
        "## Native open path",
        "",
        "Pristine `interact_chest_standard.lua` sets `state = states.OPENED` in",
        "`OnOpened`. `OnSaveCheckpoint` returns `{state = state}`; restore reads",
        "the same field. `PutAway` stores a checkpoint when configured, else calls",
        "`game.SubObject.SoftSave(thisObj)` when present. The optional",
        "`onOpenedEvent` callback has no proved per-chest quest/objective alias",
        "in the checked override ASCII. This is a limited negative result.",
        "",
        "The same `OnOpened` branch asks `game.Map.FindPlayerRegion()`, then",
        "increments a RegionSummary quest for that active region. The pristine",
        "`questlibrary.lua` starts an inactive quest or increments an active one",
        "by **1**. The 18 quest targets are region aggregate progress goals; their",
        "goals sum to 33, but they do not list physical chest members.",
        "`AwardLoot` uses `RollContainerConditionLoot` for rewards. The checked",
        "scripts do not register a per-chest map marker.",
        "",
        "Native sources: `" + report["source_contract"]["chest_script"]["source_file"] + "`",
        "(`OnOpened` line 366, `state = states.OPENED` line 373,",
        "`FindPlayerRegion` line 381, `OnSaveCheckpoint` line 498);",
        "`" + report["source_contract"]["quest_library"]["source_file"] + "`",
        "(`ActivateAndIncrementQuest` line 32, increment lines 37 and 39);",
        "`exec/dc/pc_le/quests.dcb` (per-target offsets in JSON/CSV).",
        "",
        f"Targeted scans covered {report['native_wad_files_scanned']} source WADs,",
        f"{report['native_dcb_files_scanned']} DCBs, and",
        f"{report['pristine_lua_files_scanned']} pristine Lua files. Each full",
        "native state path occurs once in its own placement override.",
        "Known serialized hash/key forms have no extra native source hit.",
        "These",
        "negative hits do not rule out a runtime-only registry or unnamed binary edge.",
        "",
        "| WAD | Physical GUID | Serialized object hash | Local state bridge | Region member |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        status = "proven frozen" if row["local_bridge_status"] == "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE" else "derived only"
        lines.append(f"| `{row['wad']}` | `{row['physical_guid']}` | "
                     f"`{row['native_gameobject_object_hash']}` | {status} | unproved |")
    lines += [
        "",
        "## Decision",
        "",
        "A later Raven-style marker could use the physical placement and exact",
        "checkpoint state only after an unloaded-state read path and Legendary",
        "marker assets are proved. Three keys lack frozen state observations.",
        "No region quest",
        "counter may stand in for per-chest state. No runtime code changed here.",
        "Chest #34 stays separate.",
        "",
        "See `legendary-progression-identity-audit.json` for exact file hashes,",
        "record offsets, key hits, and per-row reasons. The CSV has flat rows.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=catalogue_tools.GAME)
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
    print("Legendary local state bridges: "
          f"{report['proven_local_persisted_bridge_count']}/33 observed; "
          f"{report['derived_unobserved_local_bridge_count']} derived only; "
          "RegionSummary members 0/33 proved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
