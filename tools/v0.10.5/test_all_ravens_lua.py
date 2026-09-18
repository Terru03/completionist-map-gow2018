"""Lua 5.1 checks for all-Raven map and gameplay hooks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for candidate in (REPO / "dist/re-tools", REPO.parent / "completionist-map-gow2018/dist/re-tools"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None

spec = importlib.util.spec_from_file_location("all_ravens_lua_build", HERE / "build-all-ravens-release-candidate.py")
build = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build)
CATALOGUE = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))


MAP_PRELUDE = r'''
calls={logs={},previousShow=0,recycled=0,labels={},reticleTitle=nil,reticleDesc=nil,reticleCalls=0}
customIds={}
stockIds={}
persistedRegistry={}
debug=debug or {}
debug.getregistry=function() return persistedRegistry end
local markerIds={}
local markerNamesById={}
local nextMarkerId=10000
local function markerId(name)
  if markerIds[name]==nil then
    markerIds[name]=nextMarkerId
    markerNamesById[nextMarkerId]=name
    nextMarkerId=nextMarkerId+1
  end
  return markerIds[name]
end
print=function(s) calls.logs[#calls.logs+1]=s end
enabledShowOnCompassMarkerFlags={"stock"}
lamsConsts={RemoveFromCompass="remove",ReplaceInCompass="replace",AddToCompass="add"}
util={GetLAMSMsg=function(x) return x end}
Audio={PlaySound=function(x) calls.sound=x end}
MapOn={}
function MapOn.GetShowOnCompassPrompt(s,m) return s.currMarkerID~=nil,"base" end
function MapOn.ShowOnCompass(s,state) calls.previousShow=calls.previousShow+1; stockIds={"stock"} end
function MapOn.MapCollisionChangeHandler(s,state,collisions,realm)
  if collisions and collisions[1] then s.currMarkerID=collisions[1].id else s.currMarkerID=nil end
end
function MapOn.SetReticleInfo(s,state,title,desc)
  calls.reticleTitle=title
  calls.reticleDesc=desc
  calls.reticleCalls=calls.reticleCalls+1
end
function MapOn.SubmenuExit(s) end
function MapOn.Exit(s) end
function MapOn.ClearIcons(s) end
CompletionistMapV100_CreateMapPin=function(s,state) return "base" end
Map={}
function Map.FindRegionFromMarker(id) return true,"region" end
function Map.CreateMarkerIcon(id,region,label)
  calls.labels[#calls.labels+1]=label
  return {id=id,shown=false,Show=function(self) self.shown=true end}
end
function Map.RecycleIcon(go) calls.recycled=calls.recycled+1; go.recycled=true end
game={Map={},Compass={}}
function game.Map.GetMarkerInfo(name) return {Id=markerId(name),X=1,Y=2,Z=3} end
function game.Compass.FindMarkersByIconClass(classes)
  if classes[1]=="CompletionistRaven" then return customIds end
  return stockIds
end
function game.Compass.ShowMarker(name,class) customIds={markerId(name)}; calls.shown=name; calls.class=class end
function game.Compass.HideMarker(target)
  if type(target)=="number" and markerNamesById[target]~=nil then
    error("raw custom numeric ID rejected")
  end
  local next={}
  for _,id in ipairs(customIds) do
    local customName=markerNamesById[id]
    if tostring(id)~=tostring(target) and customName~=target then next[#next+1]=id end
  end
  customIds=next
  local nextStock={}
  for _,id in ipairs(stockIds) do if tostring(id)~=tostring(target) then nextStock[#nextStock+1]=id end end
  stockIds=nextStock
end
self={currRealmName="Alfheim",currMarkerID=nil,currShownMarkerID=nil,
  completionistMapV100Selected=false,completionistMapV100NornirSelected=nil,
  completionistMapV100NornirChestSelected=nil,mapIconCollision=nil}
probe={}
function probe.publish(id,value) return CompletionistMapV105PublishRavenState(id,value,"test") end
function probe.open() return CompletionistMapV100_CreateMapPin(self,{}) end
function probe.icon(name) return self.completionistMapV105RavenIcons[name] end
function probe.click(name)
  local go=probe.icon(name)
  MapOn.MapCollisionChangeHandler(self,{},go and {go} or {},self.currRealmName)
  local show,text=MapOn.GetShowOnCompassPrompt(self,nil)
  if show then MapOn.ShowOnCompass(self,{}) end
  return show,text
end
function probe.stock()
  self.currMarkerID="stock"
  MapOn.ShowOnCompass(self,{})
end
function probe.iconCount()
  local n=0
  for _,_ in pairs(self.completionistMapV105RavenIcons or {}) do n=n+1 end
  return n
end
function probe.lastLabel() return calls.labels[#calls.labels] end
function probe.reticleTitle() return calls.reticleTitle end
function probe.reticleDesc() return calls.reticleDesc end
function probe.reticleCalls() return calls.reticleCalls end
function probe.recycled() return calls.recycled end
function probe.realm(name) self.currRealmName=name; return CompletionistMapV100_CreateMapPin(self,{}) end
function probe.customCount() return #customIds end
function probe.stockCount() return #stockIds end
function probe.customAt(i) return customIds[i] end
function probe.markerId(name) return markerId(name) end
function probe.tracked() return CompletionistMapV105TrackedCatalogueId end
function probe.teardown() MapOn.ClearIcons(self) end
function probe.reset() return CompletionistMapV105ResetRavenStates("save_load") end
function probe.persistedOne(id)
  return CompletionistMapV105ApplyPersistedRavenKills({id},"test")
end
function probe.persistedRecord(wad,objectName,killed,soft)
  local levelName=string.gsub(wad,"%.wad$","")
  if string.sub(string.lower(levelName),1,4)~="wad_" then levelName="WAD_"..levelName end
  local level=setmetatable({}, {__tostring=function() return "Level '"..levelName.."'" end})
  local object=setmetatable({Level=level}, {__tostring=function() return "GameObject '"..objectName.."'" end})
  function object:GetName() return string.gsub(objectName,"^go","") end
  function object:GetDebugPath() return objectName end
  local root=persistedRegistry[2] or {}
  persistedRegistry[2]=root
  local pickleName=soft and "__SoftPickleTable" or "__PickleTable"
  local pickle=root[pickleName] or {__subobjs={}}
  root[pickleName]=pickle
  pickle.__subobjs[object]={ravenKilled=killed}
end
function probe.clearPersisted() persistedRegistry={} end
'''


@unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
class AllRavensMapLuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MAP_PRELUDE)
        hook = build.render_lua(CATALOGUE, HERE / "all-ravens-map-runtime.lua", "-- @@RAVEN_CATALOGUE_ROWS@@")
        self.lua.execute(hook.decode("utf-8"))
        alfheim = [row for row in CATALOGUE["ravens"] if row["realm"] == "Alfheim"]
        self.a, self.b = alfheim
        self.probe = self.lua.globals().probe

    def test_a_b_same_click_stock_and_kill_lifecycle(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.publish(self.b["catalogue_id"], False)
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.customAt(1), self.probe.markerId(self.a["marker"]["name"]))
        self.probe.click(self.b["marker"]["name"])
        self.assertEqual(self.probe.customAt(1), self.probe.markerId(self.b["marker"]["name"]))
        self.probe.click(self.b["marker"]["name"])
        self.assertEqual(self.probe.customCount(), 0)
        self.probe.click(self.a["marker"]["name"])
        self.probe.stock()
        self.assertEqual(self.probe.customCount(), 0)
        self.assertEqual(self.probe.stockCount(), 1)
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.stockCount(), 0)
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.customCount(), 0)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertIsNotNone(self.probe.icon(self.b["marker"]["name"]))

    def test_catalogue_visible_by_default_restore_and_teardown(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertEqual(self.probe.lastLabel(), "Odin's Raven")
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.iconCount(), 1)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.teardown()
        self.assertEqual(self.probe.iconCount(), 0)

    def test_exact_raven_collision_populates_stock_cursor_card(self):
        self.probe.open()
        show, _ = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(self.probe.reticleTitle(), "Odin's Raven")
        self.assertEqual(self.probe.reticleDesc(), "")
        self.assertGreaterEqual(self.probe.reticleCalls(), 1)

    def test_realm_transition_recycles_old_realm_and_builds_midgard(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.realm("Midgard")
        self.assertEqual(self.probe.iconCount(), 45)
        self.assertGreaterEqual(self.probe.recycled(), 2)
        self.assertEqual(self.probe.lastLabel(), "Odin's Raven")

    def test_persisted_kill_bootstrap_hides_only_confirmed_raven(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        ok, accepted = self.probe.persistedOne(self.a["catalogue_id"])
        self.assertTrue(ok)
        self.assertEqual(accepted, 1)
        self.assertEqual(self.probe.iconCount(), 1)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertIsNotNone(self.probe.icon(self.b["marker"]["name"]))

    def test_map_open_reconstructs_persisted_kill_from_exact_gameobject_identity(self):
        self.probe.persistedRecord(
            self.a["source"]["wad"], self.a["native"]["object_name"], True, False
        )
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 1)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertIsNotNone(self.probe.icon(self.b["marker"]["name"]))

    def test_live_state_overrides_older_persisted_snapshot(self):
        self.probe.persistedRecord(
            self.a["source"]["wad"], self.a["native"]["object_name"], True, False
        )
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))

    def test_save_load_reset_clears_state_and_target_catalogue_defaults_visible(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.reset()
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIsNone(self.probe.tracked())
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)


EVENT_PRELUDE = r'''
calls={sent={},timers=0,hides={}}
print=function(s) end
ravenKilled=false
regionSummaryQuest=QUEST
thisObj={GetWorldPosition=function(self) return {x=PX,y=PY,z=PZ} end}
timers={StartLevelTimer=function(delay,fn) calls.timers=calls.timers+1 end}
OnHitByWeapon=function(...) ravenKilled=true end
OnRestoreCheckpoint=function(...) end
OnStart=function(...) end
engine={}
function engine.GetUIWad() return "uiwad" end
function engine.SendHook(kind,wad,event,payload)
  calls.sent[#calls.sent+1]={kind=kind,wad=wad,event=event,payload=payload}
end
game={Map={},Compass={}}
function game.Map.GetMarkerInfo(name) return {Id=name} end
function game.Compass.FindMarkersByIconClass(classes)
  if ravenKilled then return {MARKER} end
  return {}
end
function game.Compass.HideMarker(name) calls.hides[#calls.hides+1]=name end
probe={}
function probe.start() OnStart() end
function probe.hit() OnHitByWeapon() end
function probe.restore(value) ravenKilled=value; OnRestoreCheckpoint() end
function probe.count() return #calls.sent end
function probe.id(i) return calls.sent[i].payload.catalogueId end
function probe.value(i) return calls.sent[i].payload.killed end
function probe.event(i) return calls.sent[i].event end
function probe.kind(i) return calls.sent[i].kind end
function probe.timerCount() return calls.timers end
function probe.hideCount() return #calls.hides end
function probe.hideName(i) return calls.hides[i] end
'''


@unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
class AllRavensEventLuaTests(unittest.TestCase):
    def test_exact_loaded_instance_publishes_native_bool_and_rearms(self):
        row = CATALOGUE["ravens"][0]
        x, y, z = row["source"]["native_world_position"]
        lua = LuaRuntime(unpack_returned_tuples=True)
        globals_ = lua.globals()
        globals_.QUEST = row["progression"]["parent_quest"]
        globals_.PX, globals_.PY, globals_.PZ = x, y, z
        globals_.MARKER = row["marker"]["name"]
        lua.execute(EVENT_PRELUDE)
        hook = build.render_lua(CATALOGUE, HERE / "all-ravens-gameplay-events.lua", "-- @@RAVEN_STATE_ROWS@@", True)
        lua.execute(hook.decode("utf-8"))
        probe = lua.globals().probe
        probe.start()
        self.assertEqual(probe.id(1), row["catalogue_id"])
        self.assertFalse(probe.value(1))
        self.assertEqual(probe.kind(1), "UI_CALL_EVENT")
        self.assertEqual(probe.event(1), "EVT_COMPLETIONIST_V105_RAVEN_STATE")
        probe.hit()
        self.assertTrue(probe.value(2))
        self.assertGreaterEqual(probe.hideCount(), 1)
        self.assertEqual(probe.hideName(1), row["marker"]["name"])
        self.assertEqual(probe.timerCount(), 1)
        before_restore = probe.count()
        probe.restore(False)
        self.assertEqual(probe.count(), before_restore + 1)
        self.assertFalse(probe.value(probe.count()))


HUD_PRELUDE = r'''
calls={logs={}}
files={}
print=function(s) calls.logs[#calls.logs+1]=s end
_G.CompletionistMapV105RavenState={}
_G.CompletionistMapV105PublishRavenState=function(id,killed,source)
  calls.published={id=id,killed=killed,source=source}
  return true
end
io={}
function io.open(path,mode)
  if mode=="w" then
    local f={buf=""}
    function f:write(value) self.buf=self.buf..tostring(value) end
    function f:flush() end
    function f:close() files[path]=self.buf end
    return f
  elseif mode=="r" then
    local value=files[path]
    if value==nil then return nil,"missing" end
    local f={buf=value}
    function f:lines() return string.gmatch(self.buf,"[^\\r\\n]+") end
    function f:close() end
    return f
  end
  return nil,"unsupported"
end
MainHUD={}
probe={}
function probe.recv(args) MainHUD:EVT_COMPLETIONIST_V105_RAVEN_STATE(args) end
function probe.capture(id) MainHUD:EVT_COMPLETIONIST_V105_SAVEPOINT_CAPTURE({savePointId=id,source="test"}) end
function probe.restoreId(id) MainHUD:EVT_COMPLETIONIST_V105_SAVEPOINT_RESTORE({savePointId=id,source="test"}) end
function probe.state(id) return _G.CompletionistMapV105RavenState[id] end
function probe.publishedId() return calls.published and calls.published.id or nil end
function probe.file(path) return files[path] end
'''


@unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
class AllRavensHudBridgeLuaTests(unittest.TestCase):
    def _runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(HUD_PRELUDE)
        hook = build.render_lua(
            CATALOGUE,
            HERE / "all-ravens-hud-state-receiver.lua",
            "-- @@RAVEN_RECEIVER_ROWS@@",
        )
        lua.execute(hook.decode("utf-8"))
        return lua, lua.globals().probe

    def test_valid_payload_crosses_ui_receiver_and_republishes_to_open_map(self):
        row = CATALOGUE["ravens"][0]
        x, y, z = row["source"]["native_world_position"]
        lua, probe = self._runtime()
        payload = lua.table_from({
            "catalogueId": row["catalogue_id"],
            "marker": row["marker"]["name"],
            "killed": True,
            "x": x,
            "y": y,
            "z": z,
            "source": "test",
        })
        probe.recv(payload)
        self.assertTrue(probe.state(row["catalogue_id"]))
        self.assertEqual(probe.publishedId(), row["catalogue_id"])

    def test_savepoint_sidecar_round_trip_restores_global_state(self):
        row = CATALOGUE["ravens"][0]
        x, y, z = row["source"]["native_world_position"]
        lua, probe = self._runtime()
        probe.recv(lua.table_from({
            "catalogueId": row["catalogue_id"],
            "marker": row["marker"]["name"],
            "killed": True,
            "x": x,
            "y": y,
            "z": z,
            "source": "test",
        }))
        savepoint = "sp_test_001"
        probe.capture(savepoint)
        self.assertIn(
            row["catalogue_id"] + "=1",
            probe.file("mods/completionist-map-cache/" + savepoint + ".txt"),
        )
        probe.restoreId("")
        self.assertIsNone(probe.state(row["catalogue_id"]))
        probe.restoreId(savepoint)
        self.assertTrue(probe.state(row["catalogue_id"]))

    def test_receiver_rejects_wrong_marker_identity(self):
        row = CATALOGUE["ravens"][0]
        x, y, z = row["source"]["native_world_position"]
        lua, probe = self._runtime()
        payload = lua.table_from({
            "catalogueId": row["catalogue_id"],
            "marker": "wrong",
            "killed": True,
            "x": x,
            "y": y,
            "z": z,
            "source": "test",
        })
        probe.recv(payload)
        self.assertIsNone(probe.state(row["catalogue_id"]))


CACHE_PRELUDE = r'''
calls={sent={},logs={}}
print=function(s) calls.logs[#calls.logs+1]=s end
object_savestate={existing={value=true}}
engine={}
function engine.GetUIWad() return "uiwad" end
function engine.SendHook(kind,wad,event,payload)
  calls.sent[#calls.sent+1]={kind=kind,wad=wad,event=event,payload=payload}
end
os={time=function() return 1234567890 end}
math={random=function(a,b) return 424242 end}
Save=function() return object_savestate end
Restore=function(savestate)
  if type(savestate)=="table" then object_savestate=savestate end
end
probe={}
function probe.save() return Save() end
function probe.snapshot() return object_savestate end
function probe.restore(value) Restore(value) end
function probe.sentCount() return #calls.sent end
function probe.sentEvent(i) return calls.sent[i].event end
function probe.sentSavePoint(i) return calls.sent[i].payload.savePointId end
function probe.savedId()
  local m=object_savestate["__CompletionistMapV105SavePoint"]
  return m and m.id or nil
end
'''


@unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
class AllRavensCheckpointCacheLuaTests(unittest.TestCase):
    def _runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(CACHE_PRELUDE)
        hook = (HERE / "all-ravens-save-cache-hook.lua").read_text(encoding="utf-8")
        lua.execute(hook)
        return lua, lua.globals().probe

    def test_savepoint_id_is_embedded_and_replayed(self):
        _, probe = self._runtime()
        snapshot = probe.save()
        savepoint = probe.savedId()
        self.assertIsNotNone(savepoint)
        self.assertTrue(str(savepoint).startswith("sp_"))
        self.assertEqual(probe.sentEvent(1), "EVT_COMPLETIONIST_V105_SAVEPOINT_CAPTURE")
        self.assertEqual(probe.sentSavePoint(1), savepoint)
        probe.restore(snapshot)
        self.assertEqual(probe.sentEvent(2), "EVT_COMPLETIONIST_V105_SAVEPOINT_RESTORE")
        self.assertEqual(probe.sentSavePoint(2), savepoint)



if __name__ == "__main__":
    unittest.main(verbosity=2)
