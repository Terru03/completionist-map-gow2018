#!/usr/bin/env python3
"""Build one forced Legendary map/compass marker from exact Raven release bytes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = REPO / "archive/legendary-live-test/raven-release-base"
BASE_GAME = BASE / "game-root"
OUTPUT = REPO / "build/v0.10.5-legendary-live-test/candidate/game-root"
REPORT = REPO / "build/v0.10.5-legendary-live-test/candidate/build-report.json"
AUDIT = REPO / "docs/research/legendary-progression-identity-audit.json"
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
STOCK_CHEST = Path("mods/lua_source/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua")
RAVEN_BUILDER = HERE / "build-all-ravens-release-candidate.py"
ROUTE_BUILDER = HERE / "build-legendary-test-route-marker.py"
TARGET_ID = "legendary_chest_529343984fc313504ac20da874d05c01"
TARGET_GUID = "52934398-4fc3-1350-4ac2-0da874d05c01"
TARGET_RAW_STATE = "010000803f"
TARGET_SERIALIZED_KEY = "01ef10efa930c0f345ff1b9925dd64a8fe"
TARGET_WORLD = (237.04469289824766, 0.9680004119873047, -30.207650585440433)
STOCK_CHEST_SHA = "943021f321c708561e62d4c9b6926c01b3c131c2057fbed7e4c136dbed707bdc"
SUPPORTED_EXE_SHA = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
SUPPORTED_INSTALLED = {
    "exec/dc/pc_le/mapmaster.dcb": "aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0",
    "exec/dc/pc_le/mapcoords.dcb": "5d0b7591032d7b56581a0d77946c3fad4f0cbc1b9d245f3578407177c40bbe7d",
    "exec/dc/pc_le/wad_r_ui.dcb": "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": "9cd37988f44cdb906415737bff4ff8eec62fbda9baf46a5359ebed6aa6466c08",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua": "c5370981988a8e4c7c01f2bee68946a2ef1aa70d6b6f391a04e165f68ae610a8",
}


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"module missing: {path}")
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


raven = module("_legendary_live_raven_builder", RAVEN_BUILDER)
route = module("_legendary_live_route_builder", ROUTE_BUILDER)
stage = raven.stage


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    require(text.count(old) == 1, f"Raven map delivery anchor changed: {label}")
    return text.replace(old, new, 1)


def target_proof(game_root: Path) -> dict:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    found = [row for row in audit["rows"] if row["catalogue_id"] == TARGET_ID]
    authored = [row for row in catalogue["collectibles"] if row["catalogue_id"] == TARGET_ID]
    require(len(found) == len(authored) == 1, "one pinned target required")
    row, source = found[0], authored[0]
    require(row["physical_guid"] == source["native"]["instance_guid"] == TARGET_GUID,
            "physical target differs")
    require(row["local_bridge_status"] == "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE",
            "target lacks frozen state bridge")
    require(row["world_position"] == source["marker"]["position_world"] == list(TARGET_WORLD),
            "target world point differs")
    require(row["staged_state_raw_hex"] == TARGET_RAW_STATE and row["staged_exact_match"],
            "target frozen state differs")
    require(row["native_serialized_state_key_hex"] == TARGET_SERIALIZED_KEY,
            "target serialized state key differs")
    require(source["native_classification"] == "tracked_legendary" and
            source["source"]["wad"] == "xpl920_islandclimb.wad" and
            source["realm"] == "Midgard", "target source differs")
    require(source["marker"]["uid"] == "67ADEF4B8D9FECD6" and
            source["marker"]["coordinate_wad"] == "WAD_xpl920_islandclimb",
            "target marker identity differs")
    chest = (game_root / STOCK_CHEST).read_bytes()
    require(sha(chest) == STOCK_CHEST_SHA, "pristine chest script differs")
    text = chest.decode("utf-8-sig")
    for token in ("ENABLED = 1", "OPENED = 4", "state = states.OPENED",
                  "return {state = state}", "state = savedInfo.state"):
        require(token in text, f"chest state enum/save symbol absent: {token}")
    raw = bytes.fromhex(TARGET_RAW_STATE)
    require(len(raw) == 5 and raw[0] == 1, "frozen scalar serialization tag differs")
    decoded = struct.unpack("<f", raw[1:])[0]
    require(decoded == 1.0 and decoded != 4.0, "target is not proven unopened")
    return {
        "catalogue_id": TARGET_ID,
        "physical_guid": TARGET_GUID,
        "wad": row["wad"],
        "world_position": list(TARGET_WORLD),
        "native_state_path": row["native_state_path"],
        "serialized_state_key_hex": TARGET_SERIALIZED_KEY,
        "frozen_raw_state": TARGET_RAW_STATE,
        "frozen_float32_state": decoded,
        "native_state_enum": {"ENABLED": 1, "OPENED": 4},
        "frozen_state_is_opened": False,
        "state_proof": "pinned pristine interact_chest_standard.lua enum plus exact frozen tagged float32",
        "chest_script_sha256": STOCK_CHEST_SHA,
        "name": source["marker"]["name"],
        "uid_hex": source["marker"]["uid"],
        "realm": source["realm"],
        "realm_id_hex": source["realm_id"],
        "diagnostic_region_id_hex": source["region_id"],
        "coordinate_wad": source["marker"]["coordinate_wad"],
        "map_label": "Legendary Chest - LIVE TEST",
    }


def release_sources() -> dict[str, bytes]:
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    proof_raw = (BASE / "release-proof.json").read_bytes()
    require(sha(proof_raw) == manifest["release_proof_sha256"], "Raven proof byte drift")
    proof = json.loads(proof_raw)
    require(proof["ready_for_runtime_test"] is True and
            proof["result"] == "ALL_RAVENS_OFFLINE_CANDIDATE_BUILT_NATIVE_DELIVERY_GATE_READY",
            "Raven release gate differs")
    require(manifest["reference_commit"] == "e522268e45bdd0d8f966bdb7ddf336eb344cad7d",
            "Raven reference commit differs")
    require(set(manifest["files"]) == set(proof["files"]) == set(SUPPORTED_INSTALLED),
            "Raven release file set differs")
    files = {}
    for relative, expected in proof["files"].items():
        raw = (BASE_GAME / relative).read_bytes()
        require(sha(raw) == expected["sha256"] == manifest["files"][relative]["sha256"]
                and len(raw) == expected["bytes"], f"Raven release byte drift: {relative}")
        files[relative] = raw
    return files


def stock_compatibility(game_root: Path, release: dict[str, bytes]) -> dict:
    require(sha((game_root / "GoW.exe").read_bytes()) == SUPPORTED_EXE_SHA,
            "unsupported GoW executable")
    current = {}
    for relative, expected in SUPPORTED_INSTALLED.items():
        raw = (game_root / relative).read_bytes()
        require(sha(raw) == expected, f"unsupported installed native file: {relative}")
        current[relative] = raw
    native = stage.load_native_module()
    stock_master = native.Dcb(game_root / raven.MASTER)
    release_master = native.Dcb(BASE_GAME / raven.MASTER)
    stock_coords = native.Dcb(game_root / raven.COORDS)
    release_coords = native.Dcb(BASE_GAME / raven.COORDS)
    require(set(raven.map_regions(stock_master)) == set(raven.map_regions(release_master)),
            "Steam and Raven release map regions differ")
    def semantic(rows: list[dict]) -> Counter:
        return Counter(tuple(sorted((k, str(v)) for k, v in row.items() if k != "offset"))
                       for row in rows)
    stock_markers = semantic(stage.marker_snapshot(stock_master))
    release_markers = semantic(stage.marker_snapshot(release_master))
    stock_points = semantic(stage.coordinate_snapshot(stock_coords))
    release_points = semantic(stage.coordinate_snapshot(release_coords))
    require(sum(stock_markers.values()) == 382 and sum(release_markers.values()) == 435,
            "Steam/Raven marker census differs")
    require(sum(stock_points.values()) == 405 and sum(release_points.values()) == 458,
            "Steam/Raven coordinate census differs")
    require(not (stock_markers - release_markers) and not (stock_points - release_points),
            "Raven release changes a Steam stock marker or coordinate")
    require(sum((release_markers - stock_markers).values()) == 53 and
            sum((release_points - stock_points).values()) == 53,
            "Raven release native delta is not exactly 53 markers and points")
    return {
        "steam_profile": "Steam build 11168363 exact installed file hashes",
        "exe_sha256": SUPPORTED_EXE_SHA,
        "installed_sha256": {key: sha(raw) for key, raw in current.items()},
        "steam_stock_markers_preserved": sum(stock_markers.values()),
        "steam_stock_coordinates_preserved": sum(stock_points.values()),
        "raven_release_added_markers": 53,
        "raven_release_added_coordinates": 53,
        "map_region_keys_equal": True,
    }


def patch_raven_pool(raw: bytes) -> tuple[bytes, dict]:
    chunks = stage.parse_dcb_chunks(raw)
    chunk = stage.one_chunk(chunks, 12)
    data = bytearray(raw[chunk["start"]:chunk["end"]])
    count, rows, end = stage.dcb_rows(data)
    donors = [row for row in rows if row["uid"] == raven.RAVEN_ICON_HASH]
    require(sum(row["capacity"] for row in donors) == 45 and donors,
            "Raven release icon capacity differs")
    inserted = donors[0]["raw"]
    after = bytearray(data[:end] + inserted + data[end:])
    struct.pack_into("<I", after, 8, count + 1)
    for field in (16, 32):
        struct.pack_into("<q", after, field, struct.unpack_from("<q", data, field)[0] + len(inserted))
    header = bytearray(raw[chunk["header"]:chunk["start"]])
    struct.pack_into("<I", header, 4, len(after))
    candidate = raw[:chunk["header"]] + header + after + raw[chunk["end"]:]
    new_chunk = stage.one_chunk(stage.parse_dcb_chunks(candidate), 12)
    new_data = candidate[new_chunk["start"]:new_chunk["end"]]
    new_count, new_rows, new_end = stage.dcb_rows(new_data)
    capacity = sum(row["capacity"] for row in new_rows if row["uid"] == raven.RAVEN_ICON_HASH)
    require(new_count == count + 1 and capacity == 46,
            "single diagnostic Raven art capacity differs")
    inverse = bytearray(new_data[:end] + new_data[new_end:])
    struct.pack_into("<I", inverse, 8, count)
    inverse[16:24] = data[16:24]
    inverse[32:40] = data[32:40]
    inverse_header = bytearray(candidate[new_chunk["header"]:new_chunk["start"]])
    struct.pack_into("<I", inverse_header, 4, len(inverse))
    require(candidate[:new_chunk["header"]] + inverse_header + inverse +
            candidate[new_chunk["end"]:] == raw, "Raven pool inverse differs")
    return candidate, {"raven_capacity_before": 45, "raven_capacity_after": 46,
                       "rows_added": 1, "inverse_exact": True}


def patch_map_lua(raw: bytes, target: dict) -> tuple[bytes, dict]:
    text = raw.decode("utf-8")
    require(text.count("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS") == 1 and
            text.count("-- END COMPLETIONIST V0.10.5 ALL RAVENS") == 1,
            "exact Raven release map hook missing")
    marker_index = text.index("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS")
    stock_prefix, text = text[:marker_index], text[marker_index:]
    row = ("  local legendaryLiveTest = {CatalogueId=%s,Name=%s,UidHex=%s,"
           "Realm=\"Midgard\",RegionId=%s,ParentQuest=nil}\n"
           "  byName[legendaryLiveTest.Name] = legendaryLiveTest\n" %
           (json.dumps(target["catalogue_id"]), json.dumps(target["name"]),
            json.dumps(target["uid_hex"]), json.dumps(target["diagnostic_region_id_hex"])))
    text = replace_once(text,
        "  for _, row in ipairs(rows) do\n    byName[row.Name] = row\n    byCatalogueId[row.CatalogueId] = row\n  end\n",
        "  for _, row in ipairs(rows) do\n    byName[row.Name] = row\n    byCatalogueId[row.CatalogueId] = row\n  end\n" + row,
        "diagnostic byName only")
    text = replace_once(text,
        "  local function shouldShow(catalogueId)\n    return hasAuthoritativeRavenState and",
        "  local function shouldShow(catalogueId)\n"
        "    if catalogueId == legendaryLiveTest.CatalogueId then return true end\n"
        "    return hasAuthoritativeRavenState and",
        "forced visibility without Raven state change")
    pin = """    local row = legendaryLiveTest
    if row.Realm == realm and icons[row.Name] == nil then
      local ok, value = pcall(function()
        local info = markerInfo(row.Name)
        if info == nil then return nil, "marker_info" end
        local found, region = Map.FindRegionFromMarker(info.Id)
        if found ~= true or region == nil then return nil, "region" end
        return Map.CreateMarkerIcon(info.Id, region, ""), nil
      end)
      local go = ok and value or nil
      if go ~= nil then
        icons[row.Name] = go
        go:Show()
        log("LEGENDARY_LIVE_TEST_MAP_PIN", "name=" .. row.Name ..
            " uid=" .. row.UidHex .. " shown=true")
      else
        log("LEGENDARY_LIVE_TEST_MAP_PIN", "name=" .. row.Name ..
            " uid=" .. row.UidHex .. " shown=false reason=" .. tostring(reason))
      end
    end
"""
    anchor = "  end\n\n  local createPins = CompletionistMapV100_CreateMapPin"
    text = replace_once(text, anchor, pin + anchor, "Raven map pin delivery")
    text = replace_once(text,
        "      self:SetReticleInfo(currState, \"Odin's Raven\", \"Completionist Map\")",
        "      if selected.CatalogueId == legendaryLiveTest.CatalogueId then\n"
        "        self:SetReticleInfo(currState, \"Legendary Chest - LIVE TEST\", \"Completionist Map\")\n"
        "      else\n"
        "        self:SetReticleInfo(currState, \"Odin's Raven\", \"Completionist Map\")\n"
        "      end",
        "selected marker caption")
    show_anchor = '    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..\n'
    text = replace_once(text, show_anchor,
        '    if selected.CatalogueId == legendaryLiveTest.CatalogueId then\n'
        '      log("LEGENDARY_LIVE_TEST_COMPASS", "name=" .. selected.Name ..\n'
        '          " uid=" .. selected.IdString .. " class=" .. ravenClass .. " shown=true")\n'
        '    end\n' + show_anchor,
        "Raven compass ShowMarker result")
    require(text.count("game.Compass.ShowMarker(selected.Name, ravenClass)") == 1,
            "Raven selected compass route changed")
    require(text.count("Map.CreateMarkerIcon(info.Id, region, \"\")") == 2,
            "Raven plus one Legendary map icon route required")
    require(text.count("Legendary Chest - LIVE TEST") == 1,
            "one diagnostic label required")
    require(text.count("local legendaryLiveTest =") == 1 and
            text.count("byCatalogueId[legendaryLiveTest.CatalogueId]") == 0,
            "diagnostic must stay outside Raven progression authority")
    require(text.count("SetMarkerState") == 0 and text.count("IncrementQuestProgress") == 0,
            "map hook acquired progression write")
    return (stock_prefix + text).encode("utf-8"), {
        "reference_mapmenu_sha256": sha(raw),
        "raven_map_delivery": "game.Map.GetMarkerInfo -> Map.FindRegionFromMarker -> Map.CreateMarkerIcon",
        "raven_selection": "MapOn.MapCollisionChangeHandler exact collision object -> GetShowOnCompassPrompt",
        "raven_compass_delivery": "MapOn.ShowOnCompass -> game.Compass.ShowMarker(name, CompletionistRaven)",
        "diagnostic_forced_visible": True,
        "raven_authority_row_count_unchanged": 53,
        "auto_route_on_map_open": False,
    }


def generate(game_root: Path) -> tuple[dict[str, bytes], dict]:
    game_root = game_root.resolve()
    target = target_proof(game_root)
    release = release_sources()
    stock = stock_compatibility(game_root, release)
    route.TARGET_UID = int(target["uid_hex"], 16)
    route.TARGET_REALM = int(target["realm_id_hex"], 16)
    route.TARGET_REGION = int(target["diagnostic_region_id_hex"], 16)
    route.TARGET_WAD = target["coordinate_wad"]
    route.TARGET_WORLD = TARGET_WORLD
    master, master_proof = route.patch_mapmaster(BASE_GAME / raven.MASTER)
    coords, coords_proof = route.patch_mapcoords(BASE_GAME / raven.COORDS)
    pool, pool_proof = patch_raven_pool(release[raven.POOL])
    lua, lua_proof = patch_map_lua(release[raven.MAP_LUA], target)
    outputs = {raven.MASTER: master, raven.COORDS: coords, raven.POOL: pool,
               raven.MAP_LUA: lua, raven.EVENT_LUA: release[raven.EVENT_LUA]}
    require(master != release[raven.MASTER] and coords != release[raven.COORDS] and
            pool != release[raven.POOL] and lua != release[raven.MAP_LUA],
            "diagnostic candidate did not change four expected Raven files")
    require(outputs[raven.EVENT_LUA] == release[raven.EVENT_LUA],
            "Raven event/progression file differs")
    delivered = coords_proof["target_position"]
    errors = [round(float(delivered[i]) - TARGET_WORLD[i], 9) for i in range(3)]
    require(max(abs(value) for value in errors) < 0.05,
            "Raven mapcoords float16 point too far from physical chest")
    proof = {
        "schema": 1,
        "result": "ONE_FORCED_LEGENDARY_MARKER_READY_FOR_MANUAL_MAP_TEST",
        "target": target,
        "supported_installed_source": stock,
        "reference_raven_commit": "e522268e45bdd0d8f966bdb7ddf336eb344cad7d",
        "reference_raven_files": json.loads((BASE / "manifest.json").read_text())["files"],
        "candidate_files": {key: {"sha256": sha(value), "bytes": len(value)}
                            for key, value in outputs.items()},
        "modified_install_files": [raven.MASTER, raven.COORDS, raven.POOL, raven.MAP_LUA,
                                   raven.EVENT_LUA],
        "map_point_delivered_float16": delivered,
        "map_point_error_xyz": errors,
        "proofs": {"mapmaster": master_proof, "mapcoords": coords_proof,
                   "ui_pool": pool_proof, "map_lua": lua_proof},
        "runtime_delivery_observed": False,
        "compass_delivery_observed": False,
        "game_launched": False,
        "game_files_written": False,
        "save_or_progression_written": False,
        "chest_behavior_modified": False,
    }
    return outputs, proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path,
                        default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    require(OUTPUT.resolve().is_relative_to((REPO / "build").resolve()),
            "candidate output escaped build tree")
    outputs, proof = generate(args.game_root)
    if args.check:
        require(json.loads(REPORT.read_text(encoding="utf-8")) == proof,
                "Legendary candidate proof differs")
        for relative, raw in outputs.items():
            require((OUTPUT / relative).read_bytes() == raw,
                    f"Legendary candidate differs: {relative}")
        print("LEGENDARY_LIVE_TEST_CANDIDATE_REBUILD_VERIFIED")
        return
    for relative, raw in outputs.items():
        path = OUTPUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("LEGENDARY_LIVE_TEST_CANDIDATE_BUILT " + TARGET_ID)
    print("LEGENDARY_LIVE_TEST_CANDIDATE_ROOT=" + str(OUTPUT.resolve()))
    print("LEGENDARY_LIVE_TEST_REPORT=" + str(REPORT.resolve()))


if __name__ == "__main__":
    main()
