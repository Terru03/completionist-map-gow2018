#!/usr/bin/env python3
"""Read only Ship Head evidence gate. Never emit runtime markers from guesses."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import raven_catalogue as raven
import ship_head_staged_identity as staged_identity


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
LUA_REL = Path("mods/lua_source/gameart/scripts/levels/gameplaymodules/"
               "progression/interact_loot_artifact.lua")
LUA_SHA256 = "73a3218a53ea71de38501392471aac07acfabb787e0071a207d7c6643dd03853"
BYTECODE_SHA256 = "7c6e7b59d2ac366b2757c5016a112db271057eb14b029bc0644b4210327c960f"
GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def assess(catalogue: dict, audit: dict) -> dict:
    require(hashlib.sha256(canonical_json(catalogue).encode()).hexdigest()
            == audit["catalogue_sha256"], "catalogue/audit digest differs")
    rows = [row for row in catalogue["collectibles"]
            if row["family"] == "artefact" and row.get("subtype") == "Ship Head"]
    require(len(rows) == 9, "Ship Head physical census differs")
    accounting = audit["ship_head_accounting"]
    require(accounting["physical_placements"] == 9 and
            accounting["state_carriers"] == 9 and
            accounting["exhaustive_transform_paths"] == 13 and
            accounting["tracked_target"] == 10 and
            accounting["target_discrepancy_result"] == "BLOCKED_EXACT_REASON_UNKNOWN",
            "Ship Head native accounting differs")

    numbers: set[int] = set()
    placements: set[str] = set()
    marker_uids: set[str] = set()
    instance_keys: set[str] = set()
    path_count = 0
    result = []
    summaries = audit["tracked_summary_targets"]
    for row in rows:
        native, progress, source = row["native"], row["progression"], row["source"]
        number_list = native["numbered_object_evidence"]
        require(len(number_list) == 1 and 1 <= number_list[0] <= 9,
                "Ship Head number lacks exact object proof")
        number = number_list[0]
        require(number not in numbers, f"Ship Head number {number} repeats")
        numbers.add(number)
        physical = native["instance_guid"]
        require(GUID.fullmatch(physical) is not None and physical not in placements,
                f"Ship Head {number}: physical identity differs")
        placements.add(physical)
        require(row["catalogue_id"] == "artefact_" + physical.replace("-", ""),
                f"Ship Head {number}: catalogue identity differs")
        parent = progress["parent_quest"]
        require(progress["parent_quest_source"] == "exact_native_object_attribute" and
                parent in native["attribute_values"] and "Shiphead" in parent and
                parent in summaries,
                f"Ship Head {number}: native parent attribute missing")
        require(row["realm_id"] == summaries[parent]["realm_id"] and
                row["region_id"] == summaries[parent]["region_id"],
                f"Ship Head {number}: native summary region differs")
        require(progress["state_adapter"] == "interact_loot_artifact_checkpoint_state" and
                progress["field"] == "state == ACQUIRED" and
                progress["unloaded_query"] == "unresolved" and
                progress["read_only"] is True,
                f"Ship Head {number}: state claim changed")
        require(native["script_guid"] and "Ship Head" in native["attribute_values"],
                f"Ship Head {number}: artefact script proof missing")
        require(len(source["wad_sha256"]) == 64 and
                len(native["carrier_transform_paths"]) >= 1,
                f"Ship Head {number}: source path missing")
        paths = native["carrier_transform_paths"]
        path_count += len(paths)
        carrier_guids = {p["state_carrier_guid"] for p in paths}
        require(carrier_guids == set(native["state_carrier_guids"]),
                f"Ship Head {number}: carrier set differs")
        expected_keys = {f"{physical}.{guid}" for guid in carrier_guids}
        require(set(progress["instance_keys"]) == expected_keys and
                len(progress["instance_keys"]) == len(expected_keys),
                f"Ship Head {number}: proposed keys differ from carrier paths")
        for path in paths:
            require(path["physical_instance_guid"] == physical and
                    path["wad"] == source["wad"] and
                    path["world_position"] == row["marker"]["position_world"] and
                    path["transform_chain"],
                    f"Ship Head {number}: transform path differs")
        for key in expected_keys:
            require(key not in instance_keys, f"Ship Head {number}: state key repeats")
            instance_keys.add(key)
        uid = row["marker"]["uid"]
        require(uid not in marker_uids, f"Ship Head {number}: marker UID repeats")
        marker_uids.add(uid)
        result.append({
            "number": number,
            "catalogue_id": row["catalogue_id"],
            "wad": source["wad"],
            "physical_guid": physical,
            "carrier_guids": sorted(carrier_guids),
            "proposed_instance_keys": sorted(expected_keys),
            "parent_quest": parent,
            "world_position": row["marker"]["position_world"],
            "transform_paths": len(paths),
            "native_parent_attribute_proven": False,
            "authored_carrier_binding_proven": False,
            "serialized_save_lookup_proven": False,
            "frozen_staged_identity_proven": False,
            "native_marker_suppression_proven": False,
            "ship_specific_art_proven": False,
        })
    require(numbers == set(range(1, 10)), "Ship Head numbered census incomplete")
    require(path_count == 13, "Ship Head transform path census differs")
    require(len(instance_keys) == 13, "Ship Head proposed key census differs")
    result.sort(key=lambda item: item["number"])
    return {
        "schema": 1,
        "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "physical_count": len(result),
        "transform_path_count": path_count,
        "proposed_instance_key_count": len(instance_keys),
        "authored_carrier_binding_count": 0,
        "native_target": 10,
        "scripted_cals_fixup_path_proven": False,
        "acquired_state_numeric_proven": False,
        "frozen_staged_identity_count": 0,
        "rows": result,
        "blockers": [
            "native target 10 versus nine physical objects needs exact script/accounting proof",
            "per-object serialized save lookup and unloaded state are unproved",
            "native map pin and world marker suppression paths are unproved",
            "Ship Head specific map and world artwork and resource IDs are unproved",
        ],
    }


def verify_native_parent_attributes(catalogue: dict, report: dict,
                                    game_root: Path = GAME) -> None:
    """Recheck each parent literal in its own pinned script override record."""
    source_rows = {row["catalogue_id"]: row for row in catalogue["collectibles"]
                   if row["family"] == "artefact" and row.get("subtype") == "Ship Head"}
    by_wad: dict[str, list[dict]] = {}
    for row in report["rows"]:
        by_wad.setdefault(row["wad"], []).append(row)
    for wad_name, proof_rows in sorted(by_wad.items()):
        path = game_root / "exec/wad/pc_le" / wad_name
        raw = path.read_bytes()
        records = {record["id"].hex(): record for record in raven.parse_wad(raw)}
        for proof in proof_rows:
            source = source_rows[proof["catalogue_id"]]
            require(hashlib.sha256(raw).hexdigest() == source["source"]["wad_sha256"],
                    f"{wad_name}: shipped WAD digest differs")
            override = records.get(source["native"]["override_record_id"])
            require(override is not None and
                    override["offset"] == int(source["source"]["override_offset"], 16)
                    and override["name"].lower() == "goartifactscript_overrideinst",
                    f"{wad_name}: exact script override record differs")
            data = override["data"]
            require(proof["parent_quest"].encode() + b"\0" in data and
                    b"Ship Head\0" in data,
                    f"{wad_name}: parent quest not on own script override")
            proof["native_parent_attribute_proven"] = True
    report["native_parent_attribute_count"] = sum(
        row["native_parent_attribute_proven"] for row in report["rows"])


def verify_authored_carrier_bindings(catalogue: dict, report: dict,
                                     game_root: Path = GAME) -> None:
    """Match authored identity text to one candidate script carrier path."""
    source_rows = {row["catalogue_id"]: row for row in catalogue["collectibles"]
                   if row["family"] == "artefact" and row.get("subtype") == "Ship Head"}
    by_wad: dict[str, list[dict]] = {}
    for proof in report["rows"]:
        by_wad.setdefault(proof["wad"], []).append(proof)
    for wad_name, proof_rows in sorted(by_wad.items()):
        raw = (game_root / "exec/wad/pc_le" / wad_name).read_bytes()
        records = raven.parse_wad(raw)
        for proof in proof_rows:
            source = source_rows[proof["catalogue_id"]]
            require(hashlib.sha256(raw).hexdigest() == source["source"]["wad_sha256"],
                    f"{wad_name}: shipped WAD digest differs")
            found = [record for record in records if
                     record["id"].hex() == source["native"]["placement_override_record_id"] and
                     record["name"] == source["native"]["placement_override_name"]]
            require(len(found) == 1,
                    f"{wad_name}: placement override differs")
            overrides = found + [record for record in records if
                         record["id"].hex() == source["native"]["override_record_id"] and
                         record["name"] == source["native"]["override_name"] and
                         record not in found]
            matches = []
            for record in overrides:
                for path in source["native"]["carrier_transform_paths"]:
                    carrier = path["state_carrier_guid"]
                    authored = (proof["physical_guid"] if carrier == proof["physical_guid"]
                                else f"{proof['physical_guid']}.{carrier}")
                    if authored.encode("ascii") + b"\0" in record["data"]:
                        matches.append((carrier, authored, record))
            require(len(matches) == 1,
                    f"Ship Head {proof['number']}: authored carrier ambiguous or absent")
            proof["authored_carrier_binding_proven"] = True
            proof["authored_carrier_guid"] = matches[0][0]
            proof["authored_identifier_text"] = matches[0][1]
            proof["authored_binding_record_offset"] = hex(matches[0][2]["offset"])
            proof["authored_binding_record_id"] = matches[0][2]["id"].hex()
    report["authored_carrier_binding_count"] = sum(
        row["authored_carrier_binding_proven"] for row in report["rows"])


def verify_artifact_script(audit: dict, report: dict,
                           game_root: Path = GAME) -> None:
    """Verify the compiled source record and static Lua control path."""
    lua = (game_root / LUA_REL).read_bytes()
    require(hashlib.sha256(lua).hexdigest() == LUA_SHA256,
            "decompiled artifact Lua digest differs")
    for exact in (
        b"ACQUIRED = 3",
        b'regionSummaryQuest = thisObj:FindLuaTableAttribute("regionSummaryQuest")',
        b'if regionSummaryQuest ~= nil and regionSummaryQuest ~= "" then',
        b"LD.ActivateAndIncrementQuest(regionSummaryQuest)",
        b"state = states.ACQUIRED\r\n  SoftSave()",
        b'if game.QuestManager.GetQuestState("Quest_Artifacts_ShipHeads") == "Complete" then\r\n    FixupShipHeadRegion()',
        b'function FixupShipHeadRegion()\r\n  print("FIXING UP SHIP HEAD")\r\n  LD.ActivateAndIncrementQuest("RegionSummary_CALS_Shiphead_Parent")',
    ):
        require(exact in lua, "artifact state/summary/fixup Lua path differs")
    wad = game_root / "exec/wad/pc_le/xpl940_beachcave.wad"
    compiled = [row for row in raven.parse_wad(wad.read_bytes())
                if row["name"] == "interact_loot_artifact"]
    require(len(compiled) == 1 and compiled[0]["offset"] == 0xF79EA0 and
            hashlib.sha256(compiled[0]["data"]).hexdigest() == BYTECODE_SHA256 and
            b"FixupShipHeadRegion" in compiled[0]["data"] and
            b"RegionSummary_CALS_Shiphead_Parent" in compiled[0]["data"],
            "shipped artifact bytecode record differs")
    physical = Counter(row["parent_quest"] for row in report["rows"])
    targets = {name: target["target"] for name, target in
               audit["tracked_summary_targets"].items() if "Shiphead" in name}
    require(sum(physical.values()) == 9 and sum(targets.values()) == 10,
            "Ship Head physical/target totals changed")
    report["regional_target_delta"] = {
        name: targets[name] - physical.get(name, 0) for name in sorted(targets)
    }
    require(report["regional_target_delta"] == {
        "RegionSummary_BC_Shiphead_Parent": 0,
        "RegionSummary_BM_Shiphead_Parent": 0,
        "RegionSummary_BSW_Shiphead_Parent": 1,
        "RegionSummary_BT_Shiphead_Parent": 0,
        "RegionSummary_BW_Shiphead_Parent": -1,
        "RegionSummary_CALS_Shiphead_Parent": 1,
        "RegionSummary_ISW_Shiphead_Parent": 0,
    }, "Ship Head regional target deltas changed")
    report["scripted_cals_fixup_path_proven"] = True
    report["acquired_state_numeric_proven"] = True
    report["acquired_state_numeric"] = 3
    report["artifact_lua_sha256"] = LUA_SHA256
    report["artifact_bytecode_record_sha256"] = BYTECODE_SHA256
    report["blockers"][0] = (
        "CALS scripted fixup exists, but its exact firing count and BW/BSW "
        "regional target mismatch remain unproved"
    )


def verify_frozen_staged_identity(catalogue: dict, report: dict,
                                  capture: Path = staged_identity.CAPTURE,
                                  game_root: Path = GAME) -> None:
    """Recompute exact keys from pinned WAD roots and frozen staged state."""
    wads = {row["wad"] for row in report["rows"]}
    _, by_wad = staged_identity.read_capture(wads, capture)
    roots = staged_identity.verify_roots(wads, game_root)
    proof = staged_identity.assess(catalogue, by_wad, roots)
    require(proof["transform_path_count"] == 13 and
            proof["unresolved_physical_numbers"] == [8] and
            not proof["unloaded_state_query_proven"],
            "Ship Head frozen identity proof differs")
    by_number = {row["number"]: row for row in proof["rows"]}
    for row in report["rows"]:
        found = by_number[row["number"]]
        require(found["catalogue_id"] == row["catalogue_id"] and
                found["wad"] == row["wad"],
                "Ship Head frozen identity row differs")
        matched_carriers = [path["state_carrier_guid"]
                            for path in found["path_results"] if path["matches"]]
        require(not matched_carriers or matched_carriers == [row["authored_carrier_guid"]],
                "Ship Head frozen key disagrees with authored carrier")
        row["frozen_staged_identity_proven"] = found["frozen_identity_match"]
        selected_path = [path for path in found["path_results"] if
                         path["state_carrier_guid"] == row["authored_carrier_guid"]]
        require(len(selected_path) == 1,
                "Ship Head authored carrier path absent from identity proof")
        row["static_derived_object_hash_hex"] = selected_path[0]["canonical_object_hash_hex"]
        row["static_derived_serialized_flag1_hex"] = selected_path[0]["canonical_serialized_flag1_hex"]
        row["static_derived_identity_is_unobserved"] = not found["frozen_identity_match"]
        row["frozen_serialized_flag1_hex"] = (
            found["frozen_state"]["serialized_flag1_hex"]
            if found["frozen_state"] else None)
        row["frozen_state_raw_hex"] = (
            found["frozen_state"]["state_raw_hex"]
            if found["frozen_state"] else None)
    report["frozen_staged_identity_count"] = proof["frozen_exact_identity_count"]
    report["frozen_unresolved_numbers"] = proof["unresolved_physical_numbers"]
    report["frozen_capture_manifest_sha256"] = hashlib.sha256(
        (capture / "report.json").read_bytes()).hexdigest()
    report["frozen_payload_sha256"] = {
        wad: by_wad[wad]["meta"]["sha256"] for wad in sorted(wads)}
    report["blockers"][1] = (
        "one Ship Head lacks a frozen staged identity; unloaded per-object "
        "state lookup remains unproved for all nine"
    )


def require_generation_ready(report: dict) -> None:
    if not report["runtime_generation_allowed"]:
        raise ValueError("Ship Head generation blocked: " + "; ".join(report["blockers"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--game-root", type=Path, default=GAME)
    args = parser.parse_args()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = assess(catalogue, audit)
    verify_native_parent_attributes(catalogue, report, args.game_root)
    verify_authored_carrier_bindings(catalogue, report, args.game_root)
    verify_artifact_script(audit, report, args.game_root)
    verify_frozen_staged_identity(catalogue, report,
                                  game_root=args.game_root)
    report["source_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CATALOGUE, AUDIT)
    }
    if args.output:
        target = args.output.resolve()
        require(target != REPO and REPO in target.parents,
                "output must stay inside repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(report), encoding="utf-8")
    print(f"SHIP_HEAD_STATIC_GATE {report['status']} "
          f"physical={report['physical_count']}/9 paths={report['transform_path_count']}/13 "
          f"authored={report['authored_carrier_binding_count']}/9 "
          f"frozen_identity={report['frozen_staged_identity_count']}/9 "
          f"save_lookup=0/9")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
