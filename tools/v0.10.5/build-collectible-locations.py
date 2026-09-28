#!/usr/bin/env python3
"""Build a reversible, stock-art location layer over the Raven + Nornir v4 base."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("location_native_base", HERE / "build-nornir-map-id-test.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

GAME = base.GAME
BUILD = ROOT / "build/collectible-locations"
CATALOGUE = base.CATALOGUE
ADDITIONAL = ROOT / "config/collectibles/v0.10.5/additional-locations.json"
CATEGORIES = ROOT / "config/collectibles/v0.10.5/location-marker-categories.json"
TEMPLATE = HERE / "collectible-location-map.lua"
FILES = (base.MASTER, base.COORDS, base.POOL, base.MAP_LUA)
SOURCE = {
    base.MASTER: "02e4f63522ce204827be6898daf0ac3bc99659b2678961ebce18df556457b9c0",
    base.COORDS: "ae19df8f721bdc7e610c787e3376044fdfc33d436076cc1d02edc1507a5a0bdb",
    base.POOL: "7038a9c29ef260e891a0c5ab7639f1917785c3867938a2d836b2bc827835b9c6",
    base.MAP_LUA: "fe874c9136a8061f6f2438d835901c8a6ef7a493e534ecaba0880d9d74c2e452",
}
UNTOUCHED = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/dc/pc_le/compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "exec/boot-options.json": "8bbac2bb2a522dfacf69c676e48665686f722289a44127518ae4e8ca299a0e92",
    base.RUNIC_LUA: "e9c77fbaa9ba8d678d0ade38f1016b83dd20ebda9d252189973490a1c73ff454",
    base.STANDARD_LUA: "7c4ebf9e2663d7891df9e95a1ec00fe6021d024d3e90b0baf590acff1d9a76b0",
    "dxgi.dll": "cc91a2ea4475c83085488c33bb0ece223f958054c1a4ac71d26d67a31a84f7b7",
}
COUNTS = {"artefact": 45, "lore_marker": 43, "legendary_chest": 37,
          "cipher_chest": 14, "wooden_chest": 99, "coffin": 109,
          "jotnar_shrine": 13, "realm_tear": 21, "treasure_map": 12,
          "treasure_dig": 12, "lore_scroll": 5}
REUSED_NATIVE_MARKERS = 3
KIND = "COLLECTIBLE_LOCATIONS_STOCK_BLUE_QUEST"
DOCK_HASH = 0x7f41f3489470173e
FAST_TRAVEL_HASH = 0xd83ce6fdb0a88e09
RAVEN_HASH = 0x584f31dc8bd6e738
FIGHT_HASH = 0xaf47b2f5edaed9c6
DEFAULT_POOL_ADDITIONS = (
    (base.STOCK_HASH, 2048),
    (RAVEN_HASH, 32),
    (DOCK_HASH, 32),
    (FAST_TRAVEL_HASH, 32),
    (FIGHT_HASH, 16),
)
HANDOFF_ANCHOR = b'  print("[CompletionistMapV105NornirNativeTest] installed rows="'
HANDOFF = b'''  -- Share the single native compass target with the location layer.
  _G.CompletionistMapV105HasNornirCompassTarget = function()
    return targetRow ~= nil
  end
  _G.CompletionistMapV105ReleaseNornirCompass = function()
    if targetRow ~= nil then
      local ok, result = pcall(game.Compass.HideMarker, targetRow.Name)
      if not ok or result == false then return false end
      targetRow = nil
    end
    return true
  end

'''


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def definitions() -> tuple[list[dict], dict, list[dict]]:
    config = json.loads(CATEGORIES.read_text(encoding="utf-8-sig"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8-sig"))["collectibles"]
    catalogue += json.loads(ADDITIONAL.read_text(encoding="utf-8-sig"))["collectibles"]
    categories = config["categories"]
    need(config["mode"] in {"all_known_locations", "hide_collected"} and
         (config["mode"] != "hide_collected" or config.get("unknown_state_policy") == "visible") and
         config["map_resource"] == base.STOCK_RESOURCE and config["compass_class"] == "SIDE",
         "location mode or stock artwork contract differs")
    families = {row["family"] for row in categories}
    filters = {row["filter"] for row in categories}
    need(families == set(COUNTS) and len(filters) == len(categories) == len(COUNTS) and
         filters == set(range(-104 - len(COUNTS), -104)), "location categories collide")
    wanted, excluded = [], []
    for row in catalogue:
        if row["family"] not in families:
            continue
        override = config.get("map_region_overrides", {}).get(row["catalogue_id"])
        if override is not None:
            need(row["realm"] == override["realm"] and row["region_id"] == row["realm_id"] and
                 int(override["region_id"], 16) == base.name_hash(override["region"]),
                 "map region override does not match Summary realm alias")
            row = {**row, "region": override["region"], "region_id": override["region_id"]}
        if row.get("native_classification") in config["excluded_native_classifications"]:
            excluded.append({"catalogue_id": row["catalogue_id"],
                             "reason": row["native_classification"]})
            continue
        marker = row["marker"]
        need(marker["position_world"] is not None and len(marker["position_world"]) == 3 and
             all(math.isfinite(value) for value in marker["position_world"]) and
             marker["coordinate_wad"] and row["realm_id"] and row["region_id"],
             f"missing native placement: {row['catalogue_id']}")
        need(int(marker["uid"], 16) == base.name_hash(marker["name"]),
             f"marker name/UID differs: {row['catalogue_id']}")
        wanted.append(row)
    need(Counter(row["family"] for row in wanted) == COUNTS and len(excluded) == 27,
         "location catalogue counts differ")
    need(len({row["marker"]["uid"] for row in wanted}) == len(wanted), "duplicate location UID")
    return sorted(wanted, key=lambda row: row["marker"]["uid"]), config, excluded


def build_pool(raw: bytes,
               additions: tuple[tuple[int, int], ...] | list[tuple[int, int]] | int | None = None
               ) -> tuple[bytes, dict]:
    if additions is None:
        additions = DEFAULT_POOL_ADDITIONS
    elif isinstance(additions, int):
        additions = [(base.STOCK_HASH, additions)]
    stage = base.stage
    chunk = stage.one_chunk(stage.parse_dcb_chunks(raw), 12)
    data = bytearray(raw[chunk["start"]:chunk["end"]])
    old_count, old_rows, end = stage.dcb_rows(data)
    need(old_count == 389 and any(row["uid"] == base.STOCK_HASH for row in old_rows),
         "Nornir v4 stock icon pool differs")
    total_count = sum(cnt for _, cnt in additions)
    addition = b"".join(struct.pack("<QH6x", uid, 1) * cnt for uid, cnt in additions)
    after = bytearray(data[:end] + addition + data[end:])
    struct.pack_into("<I", after, 8, old_count + total_count)
    for at in (16, 32):
        struct.pack_into("<q", after, at, struct.unpack_from("<q", data, at)[0] + len(addition))
    header = bytearray(raw[chunk["header"]:chunk["start"]])
    struct.pack_into("<I", header, 4, len(after))
    candidate = raw[:chunk["header"]] + header + after + raw[chunk["end"]:]
    newer = stage.one_chunk(stage.parse_dcb_chunks(candidate), 12)
    new_data = candidate[newer["start"]:newer["end"]]
    new_count, new_rows, new_end = stage.dcb_rows(new_data)
    expected_uids = [uid for uid, cnt in additions for _ in range(cnt)]
    need(new_count == old_count + total_count and
         [row["raw"] for row in new_rows[:old_count]] == [row["raw"] for row in old_rows] and
         [row["uid"] for row in new_rows[old_count:]] == expected_uids and
         all(row["capacity"] == 1 for row in new_rows[old_count:]),
         "stock pool preservation failed")
    inverse = bytearray(new_data[:end] + new_data[new_end:])
    inverse[8:12], inverse[16:24], inverse[32:40] = data[8:12], data[16:24], data[32:40]
    inverse_header = bytearray(candidate[newer["header"]:newer["start"]])
    struct.pack_into("<I", inverse_header, 4, len(inverse))
    need(candidate[:newer["header"]] + inverse_header + inverse + candidate[newer["end"]:] == raw,
         "pool inverse differs")
    return candidate, {"existing_rows_preserved": old_count, "added": total_count,
                       "capacities": {hex(uid): cnt for uid, cnt in additions},
                       "exact_inverse": True}


def render_runtime(rows: list[dict], config: dict, *, include_state: bool = True) -> bytes:
    def literal(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value) if isinstance(value, int) else json.dumps(value, ensure_ascii=True)

    def record(values):
        return "    {" + ",".join(key + "=" + literal(value) for key, value in values.items()) + "},"

    categories = [record({"Family": c["family"], "Filter": c["filter"],
                          "Label": c["label"], "Title": c["title"]}) for c in config["categories"]]
    entries = []
    for row in rows:
        uid = int(row["marker"]["uid"], 16)
        entries.append(record({"Name": row["marker"]["name"],
                               "IdString": str(uid if uid < 1 << 63 else uid - (1 << 64)),
                               "Family": row["family"], "Realm": row["realm"],
                               "CatalogueId": row["catalogue_id"],
                               "Native": row["marker"].get("existing_native", False)}))
    source = TEMPLATE.read_text(encoding="utf-8")
    for token, lines in (("-- @@LOCATION_CATEGORIES@@", categories), ("-- @@LOCATION_ROWS@@", entries)):
        need(source.count(token) == 1, f"runtime template token differs: {token}")
        source = source.replace(token, "\n".join(lines), 1)
    need(not any(word in source for word in
                 ("SetMarkerState", "SetToken", "IncrementQuestProgress", "StartQuest")),
         "location layer contains progression write")
    if include_state:
        import collectible_completion_adapters as adapters
        def lua_value(value):
            if value is None:
                return "nil"
            if isinstance(value, list):
                return "{" + ",".join(lua_value(v) for v in value) + "}"
            if isinstance(value, dict):
                return "{" + ",".join(k + "=" + lua_value(v) for k, v in value.items()) + "}"
            return literal(value)
        spec = importlib.util.spec_from_file_location("location_bindings", HERE / "build-collectible-completion-bindings.py")
        binding_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(binding_module)
        bindings = binding_module.build()
        ids = ",".join(json.dumps(b["catalogue_id"]) for b in bindings["bindings"])
        modules = "\n".join("local " + name + " = (function()\n" +
            (HERE / filename).read_text(encoding="utf-8") + "\nend)()"
            for name, filename in (("State", "collectible-state.lua"),
                                   ("Reader", "collectible-state-reader.lua"),
                                   ("Runtime", "collectible-state-runtime.lua"),
                                   ("Loaded", "collectible-loaded-reader.lua")))
        bootstrap = '''-- BEGIN COMPLETIONIST V0.10.5 LOCATION STATE
do
%s
  local ids = {%s}
  local store = State.New(ids)
  local epoch = _G.CompletionistMapV105Nornir.service.epoch
  store:BeginEpoch(epoch)
  local runtime
  local reader = Reader.New(ids, %s, function()
    return runtime and runtime.ready and runtime.restoreEpoch or nil
  end)
  runtime = Runtime.New(store, reader)
  runtime.loaded = Loaded.New(%s, runtime)
  reader:Reset(epoch)
  local timerOK, timerlib = pcall(require, "core.timer")
  local fsmOK, fsm = pcall(require, "ui.fsm")
  if timerOK and fsmOK and timerlib.Timer and fsm.runList then
    runtime.timer = timerlib.Timer.New(fsm.runList, 0.1, function(timer)
      local ok, reason = pcall(function() runtime:Tick(timer:GetElapsedTime()) end)
      if not ok and reason ~= runtime.lastPollError then
        print("[CompletionistLocations] poll_failed reason=" .. tostring(reason))
        runtime.lastPollError = reason
      end
    end)
    runtime.timer.autoreset = true
    runtime.timer:Start()
  end
  print("[CompletionistLocations] reader_enabled=" .. tostring(reader.transport ~= nil) ..
    " timer_enabled=" .. tostring(runtime.timer ~= nil) .. " clock=ui_elapsed")
  _G.CompletionistMapV105LocationState = store
  _G.CompletionistMapV105LocationRuntime = runtime
  _G.CompletionistMapV105LocationAuthorityReady = function(restore)
    return runtime:AuthorityReady(restore)
  end
  local ok, thunk = pcall(require, "core.thunk")
  if ok and type(thunk) == "table" and type(thunk.Install) == "function" then
    thunk.Install("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", function(...)
      for i=1,select('#',...) do
        local value=select(i,...)
        if type(value) == "string" then
          local level=value:match("^COLLECTIBLE_DIRTY_V1\\t([%%w_]+)$")
          if level then runtime.loaded:Poll(level:lower()) end
        end
      end
    end)
  end
end
-- END COMPLETIONIST V0.10.5 LOCATION STATE
''' % (modules, ids, json.dumps(bindings["contract"]), lua_value(adapters.loaded_bindings(rows)))
        source = bootstrap + source
    return source.encode("utf-8")


def build(game: Path = GAME, base_operation: Path | None = None,
          native_marker_capacity: int = 732) -> tuple[dict[str, bytes], dict]:
    rows, config, excluded = definitions()
    source_root = game if base_operation is None else base_operation.parent / "before"
    source = {name: (source_root / name).read_bytes() for name in FILES}
    for name, expected in SOURCE.items():
        need(sha(source[name]) == expected, f"Nornir v4 base differs: {name}")
    for name, expected in UNTOUCHED.items():
        need(sha((game / name).read_bytes()) == expected, f"preserved resource differs: {name}")
    regions = base.raven.map_regions(base.Dcb(source_root / base.MASTER))
    for override in config.get("map_region_overrides", {}).values():
        actual = [region for realm, region in regions if realm == base.name_hash(override["realm"])]
        need(actual == [int(override["region_id"], 16)], "map region override is not the sole native region")
    outputs, proof = {}, {}
    additions = [row for row in rows if not row["marker"].get("existing_native")]
    existing = [row for row in rows if row["marker"].get("existing_native")]
    need(len(existing) == REUSED_NATIVE_MARKERS, "native marker reuse count differs")
    original_markers = {row["uid"]: row for row in base.stage.marker_snapshot(base.Dcb(source_root / base.MASTER))}
    original_coords = {row["uid"]: row for row in base.stage.coordinate_snapshot(base.Dcb(source_root / base.COORDS))}
    for row in existing:
        marker = original_markers.get(row["marker"]["uid"])
        coordinate = original_coords.get(row["marker"]["uid"])
        need(marker is not None and coordinate is not None and
             marker["realm"] == row["realm_id"] and marker["region"] == row["region_id"] and
             marker["icon"] == base.STOCK_RESOURCE and
             coordinate["wad"].lower() == row["marker"]["coordinate_wad"].lower() and
             all(abs(a-b) < 2 for a,b in zip(coordinate["position"], row["marker"]["position_world"])),
             f"authored native marker binding differs: {row['catalogue_id']}")
    for name, coordinates in ((base.MASTER, False), (base.COORDS, True)):
        outputs[name], proof[name] = base.build_map(base.Dcb(source_root / name), additions, coordinates,
                                                  expected_count=len(additions))
    marker_ids = {row["uid"] for row in base.stage.marker_snapshot(base.parsed(outputs[base.MASTER], base.MASTER))}
    coordinate_ids = {row["uid"] for row in base.stage.coordinate_snapshot(base.parsed(outputs[base.COORDS], base.COORDS))}
    radius_count = len((marker_ids & coordinate_ids) - {"0000000000000000"})
    need(radius_count <= native_marker_capacity,
         f"native marker dictionary would overflow: {radius_count} > {native_marker_capacity}; "
         "build/install with recover-collectible-locations.py and its capacity bridge")
    need(len(coordinate_ids) <= 2926, "native coordinate dictionary capacity exceeded")
    outputs[base.POOL], proof[base.POOL] = build_pool(source[base.POOL])
    old_lua = source[base.MAP_LUA]
    need(old_lua.count(HANDOFF_ANCHOR) == 1 and HANDOFF not in old_lua,
         "Nornir compass handoff anchor differs")
    prefix = old_lua.replace(HANDOFF_ANCHOR, HANDOFF + HANDOFF_ANCHOR, 1)
    need(prefix.replace(HANDOFF, b"", 1) == old_lua, "existing Lua changed outside handoff")
    outputs[base.MAP_LUA] = prefix + b"\n" + render_runtime(rows, config)
    proof[base.MAP_LUA] = {"original_preserved_except_compass_handoff": True,
                           "exact_inverse": True, "rows": len(rows)}
    need(all((source_root / name).read_bytes() == value for name, value in source.items()),
         "game base changed during build")
    return outputs, {
        "schema": 1, "kind": KIND, "mode": config["mode"], "status": "OFFLINE_BUILT",
        "new_marker_count": len(additions), "location_count": len(rows),
        "native_marker_capacity": native_marker_capacity, "native_marker_entries": radius_count,
        "reused_native_markers": len(existing), "family_counts": COUNTS,
        "preserved_ravens": 53, "preserved_nornir": 88,
        "map_resource": config["map_resource"], "compass_class": config["compass_class"],
        "categories": config["categories"], "excluded": excluded,
        "map_region_overrides": config.get("map_region_overrides", {}),
        "catalogue_sha256": sha(CATALOGUE.read_bytes()),
        "additional_catalogue_sha256": sha(ADDITIONAL.read_bytes()),
        "categories_sha256": sha(CATEGORIES.read_bytes()),
        "source_sha256": SOURCE, "untouched_sha256": UNTOUCHED,
        "files": {name: {"before": SOURCE[name], "after": sha(raw), "bytes": len(raw)}
                  for name, raw in outputs.items()}, "proof": proof,
        "live_validation": "pending", "completion_suppression": "tri-state service via CompletionistMapV105LocationState",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--output", type=Path, default=BUILD)
    parser.add_argument("--base-operation", type=Path,
                        help="Use this operation's pinned v4 backups while an older location overlay is installed")
    args = parser.parse_args()
    outputs, report = build(args.game, args.base_operation)
    for name, raw in outputs.items():
        target = args.output / "candidate/game-root" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"COLLECTIBLE_LOCATIONS_BUILT locations={report['location_count']} "
          f"new_rows={report['new_marker_count']} categories={len(COUNTS)}")
    print(args.output / "report.json")


if __name__ == "__main__":
    main()
