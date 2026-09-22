#!/usr/bin/env python3
"""Build a temporary native map/compass route marker for the peak500 chest.

The source is the CURRENT installed Completionist Map game files. Output is
written only to --output-dir. The caller performs guarded installation/rollback.

This marker is diagnostic only:
- it uses the proven Completionist Raven visual/compass class;
- it points at the exact tracked Legendary Chest world coordinate;
- it does not read, infer, or write collectible/progression state.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILDER_PATH = HERE / "build-all-ravens-release-candidate.py"

TARGET_NAME = "Completionist_V105_LegendaryChest_ff46dfab43efcfc6"
TARGET_UID = 0x82300B1E715EF436
TARGET_REALM = 0x7CE593BC21393690
TARGET_REGION = 0xED623FA0A76B2934
TARGET_WAD = "WAD_peak500_chimneytop"
TARGET_WORLD = (-454.8589782714844, 1172.625, 858.6287841796875)
DONOR_UID = 0xE15E6BC82AE2773E
DONOR_ICON = "goMapIconCompletionistRaven"

MASTER_REL = Path("exec/dc/pc_le/mapmaster.dcb")
COORDS_REL = Path("exec/dc/pc_le/mapcoords.dcb")
MAP_LUA_REL = Path("mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua")
BEGIN = "-- BEGIN COMPLETIONIST LEGENDARY TEST ROUTE peak500"
END = "-- END COMPLETIONIST LEGENDARY TEST ROUTE peak500"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_module("_legendary_route_raven_builder", BUILDER_PATH)
stage = builder.stage


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def patch_mapmaster(path: Path) -> tuple[bytes, dict]:
    native = stage.load_native_module()
    source = native.Dcb(path)
    before = stage.marker_snapshot(source)

    donor = [row for row in before if int(row["uid"], 16) == DONOR_UID]
    if len(donor) != 1 or donor[0]["icon"] != DONOR_ICON:
        raise RuntimeError("proven Raven donor marker is missing")
    existing_target = [
        row for row in before if int(row["uid"], 16) == TARGET_UID
    ]
    if existing_target:
        if len(existing_target) != 1:
            raise RuntimeError("duplicate diagnostic target marker")
        row = existing_target[0]
        if (
            int(row["realm"], 16) != TARGET_REALM
            or int(row["region"], 16) != TARGET_REGION
        ):
            raise RuntimeError("existing diagnostic marker has wrong owner")
        return path.read_bytes(), {
            "already_present": True,
            "source_marker_count": len(before),
            "candidate_marker_count": len(before),
        }

    regions = builder.map_regions(source)
    key = (TARGET_REALM, TARGET_REGION)
    if key not in regions:
        raise RuntimeError("Peakspass region is absent from current mapmaster")

    region = regions[key]
    field = region + 0x38
    old_offsets = list(source.array(field, 0x48))
    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    new_start = stage.align_blob(blob)

    for old_offset in old_offsets:
        destination = len(blob)
        blob.extend(source.blob[old_offset:old_offset + 0x48])
        stage.rebase_pointer(
            source, old_offset + 0x08, blob, destination + 0x08, relocations
        )
        stage.rebase_pointer(
            source, old_offset + 0x20, blob, destination + 0x20, relocations
        )

    donor_offset = donor[0]["offset"]
    destination = len(blob)
    blob.extend(source.blob[donor_offset:donor_offset + 0x48])
    struct.pack_into("<Q", blob, destination, TARGET_UID)
    stage.rebase_pointer(
        source, donor_offset + 0x08, blob, destination + 0x08, relocations
    )
    stage.rebase_pointer(
        source, donor_offset + 0x20, blob, destination + 0x20, relocations
    )
    stage.replace_array_pointer(blob, field, new_start, len(old_offsets) + 1)

    candidate = stage.rebuild_dcb_bytes(source, blob, relocations)
    parsed = builder.parse_candidate(candidate, str(path))
    after = stage.marker_snapshot(parsed)
    found = [row for row in after if int(row["uid"], 16) == TARGET_UID]
    if len(found) != 1:
        raise RuntimeError("diagnostic target marker was not created exactly once")
    row = found[0]
    if (
        int(row["realm"], 16) != TARGET_REALM
        or int(row["region"], 16) != TARGET_REGION
        or row["icon"] != DONOR_ICON
    ):
        raise RuntimeError("diagnostic marker verification failed")

    return candidate, {
        "already_present": False,
        "source_marker_count": len(before),
        "candidate_marker_count": len(after),
        "target_icon": row["icon"],
        "target_realm": row["realm"],
        "target_region": row["region"],
    }


def patch_mapcoords(path: Path) -> tuple[bytes, dict]:
    native = stage.load_native_module()
    source = native.Dcb(path)
    before = stage.coordinate_snapshot(source)

    donor = [row for row in before if int(row["uid"], 16) == DONOR_UID]
    if len(donor) != 1:
        raise RuntimeError("proven Raven donor coordinate is missing")
    existing_target = [
        row for row in before if int(row["uid"], 16) == TARGET_UID
    ]
    if existing_target:
        if len(existing_target) != 1:
            raise RuntimeError("duplicate diagnostic target coordinate")
        row = existing_target[0]
        if row["wad"] != TARGET_WAD:
            raise RuntimeError("existing diagnostic coordinate has wrong WAD")
        return path.read_bytes(), {
            "already_present": True,
            "source_coordinate_count": len(before),
            "candidate_coordinate_count": len(before),
        }

    field = source.root("MAP_COORDS_PERM_DATA", 0x40A)
    old_offsets = list(source.array(field, 0x28))
    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    new_start = stage.align_blob(blob)

    for old_offset in old_offsets:
        destination = len(blob)
        blob.extend(source.blob[old_offset:old_offset + 0x28])
        stage.rebase_pointer(
            source, old_offset + 0x08, blob, destination + 0x08, relocations
        )

    donor_offset = donor[0]["offset"]
    destination = len(blob)
    blob.extend(source.blob[donor_offset:donor_offset + 0x28])
    struct.pack_into("<Q", blob, destination, TARGET_UID)
    struct.pack_into("<3e", blob, destination + 0x10, *TARGET_WORLD)

    string_offset = len(blob)
    blob.extend(TARGET_WAD.encode("ascii") + b"\0")
    struct.pack_into(
        "<q",
        blob,
        destination + 0x08,
        string_offset - (destination + 0x08),
    )
    relocations.add(destination + 0x08)
    stage.replace_array_pointer(blob, field, new_start, len(old_offsets) + 1)

    candidate = stage.rebuild_dcb_bytes(source, blob, relocations)
    parsed = builder.parse_candidate(candidate, str(path))
    after = stage.coordinate_snapshot(parsed)
    found = [row for row in after if int(row["uid"], 16) == TARGET_UID]
    if len(found) != 1:
        raise RuntimeError("diagnostic target coordinate was not created exactly once")
    row = found[0]
    if row["wad"] != TARGET_WAD:
        raise RuntimeError("diagnostic target WAD verification failed")

    return candidate, {
        "already_present": False,
        "source_coordinate_count": len(before),
        "candidate_coordinate_count": len(after),
        "target_wad": row["wad"],
        "target_position": row["position"],
    }


def route_hook() -> str:
    return f"""
{BEGIN}
do
  local prefix = "[CompletionistLegendaryRoute peak500] "
  local markerName = "{TARGET_NAME}"
  local compassClass = "CompletionistRaven"

  local function log(message)
    print(prefix .. message)
  end

  local function markerInfo()
    local ok, info = pcall(function()
      return game.Map.GetMarkerInfo(markerName)
    end)
    if not ok or type(info) ~= "table" or info.Id == nil then
      return nil
    end
    return info
  end

  local function routeToChest(source)
    local info = markerInfo()
    if info == nil then
      log("ROUTE_FAILED source=" .. tostring(source) .. " reason=marker_info")
      return
    end
    local ok, err = pcall(function()
      game.Compass.ShowMarker(markerName, compassClass)
    end)
    log("ROUTE source=" .. tostring(source) ..
        " ok=" .. tostring(ok) ..
        " uid=" .. tostring(info.Id) ..
        " class=" .. compassClass ..
        (ok and "" or " error=" .. tostring(err)))
  end

  local previousCreatePins = CompletionistMapV100_CreateMapPin
  if type(previousCreatePins) == "function" then
    CompletionistMapV100_CreateMapPin = function(self, currState)
      local result = previousCreatePins(self, currState)
      if self ~= nil and self.currRealmName == "Midgard" then
        local info = markerInfo()
        if info ~= nil then
          local ok, found, region = pcall(function()
            local f, r = Map.FindRegionFromMarker(info.Id)
            return f, r
          end)
          if ok and found == true and region ~= nil then
            if self.completionistLegendaryTestRouteGO ~= nil then
              pcall(function()
                Map.RecycleIcon(self.completionistLegendaryTestRouteGO)
              end)
            end
            local iconOK, go = pcall(function()
              return Map.CreateMarkerIcon(info.Id, region, "")
            end)
            if iconOK and go ~= nil then
              self.completionistLegendaryTestRouteGO = go
              pcall(function() go:Show() end)
              log("MAP_PIN shown=true uid=" .. tostring(info.Id))
            else
              log("MAP_PIN shown=false")
            end
          end
        end
        routeToChest("map_create")
      end
      return result
    end
  end

  local previousClearIcons = MapOn.ClearIcons
  if type(previousClearIcons) == "function" then
    MapOn.ClearIcons = function(self, ...)
      if self ~= nil and self.completionistLegendaryTestRouteGO ~= nil then
        pcall(function()
          Map.RecycleIcon(self.completionistLegendaryTestRouteGO)
        end)
        self.completionistLegendaryTestRouteGO = nil
      end
      return previousClearIcons(self, ...)
    end
  end

  _G.CompletionistLegendaryRoutePeak500 = routeToChest
  log("INSTALLED marker=" .. markerName ..
      " world=-454.858978,1172.625,858.628784 progressionWrites=false")
end
{END}
""".lstrip()


def patch_map_lua(path: Path) -> tuple[bytes, dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if BEGIN in text:
        if END not in text:
            raise RuntimeError("partial diagnostic route hook already installed")
        return raw, {"already_present": True, "bytes": len(raw)}
    hook = route_hook()
    candidate = (text.rstrip() + "\n\n" + hook).encode("utf-8")
    return candidate, {
        "already_present": False,
        "bytes_before": len(raw),
        "bytes_after": len(candidate),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    game_root = args.game_root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    paths = {
        "mapmaster": game_root / MASTER_REL,
        "mapcoords": game_root / COORDS_REL,
        "map_lua": game_root / MAP_LUA_REL,
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing installed source {name}: {path}")

    inputs = {name: path.read_bytes() for name, path in paths.items()}
    master, master_proof = patch_mapmaster(paths["mapmaster"])
    coords, coords_proof = patch_mapcoords(paths["mapcoords"])
    map_lua, lua_proof = patch_map_lua(paths["map_lua"])

    outputs = {
        MASTER_REL: master,
        COORDS_REL: coords,
        MAP_LUA_REL: map_lua,
    }
    for relative, raw in outputs.items():
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)

    report = {
        "schema": 1,
        "analysis": "temporary_legendary_peak500_route_marker",
        "target": {
            "catalogue_id": "legendary_chest_ff46dfab43efcfc6f0f382a33e2b571d",
            "name": TARGET_NAME,
            "uid_hex": f"{TARGET_UID:016X}",
            "realm_id_hex": f"{TARGET_REALM:016X}",
            "region_id_hex": f"{TARGET_REGION:016X}",
            "coordinate_wad": TARGET_WAD,
            "world_position": list(TARGET_WORLD),
            "compass_class_used_for_diagnostic": "CompletionistRaven",
            "map_icon_used_for_diagnostic": DONOR_ICON,
        },
        "source_sha256": {
            name: sha(raw) for name, raw in inputs.items()
        },
        "candidate_sha256": {
            str(relative).replace("\\", "/"): sha(raw)
            for relative, raw in outputs.items()
        },
        "proof": {
            "mapmaster": master_proof,
            "mapcoords": coords_proof,
            "map_lua": lua_proof,
        },
        "safety": {
            "build_writes_game_files": False,
            "save_or_progression_read": False,
            "save_or_progression_written": False,
            "collectible_state_inferred": False,
            "raven_progression_modified": False,
            "diagnostic_route_only": True,
        },
    }
    (out / "legendary-route-report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "LEGENDARY_TEST_ROUTE_CANDIDATE_BUILT "
        f"marker={TARGET_NAME} uid={TARGET_UID:016X}"
    )
    print(
        "save_or_progression_written=false "
        "collectible_state_inferred=false diagnostic_route_only=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
