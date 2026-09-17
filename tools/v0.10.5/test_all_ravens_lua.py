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
calls={published={},timers=0}
print=function(s) end
ravenKilled=false
regionSummaryQuest=QUEST
thisObj={GetWorldPosition=function(self) return {x=PX,y=PY,z=PZ} end}
timers={StartLevelTimer=function(delay,fn) calls.timers=calls.timers+1 end}
OnHitByWeapon=function(...) ravenKilled=true end
OnRestoreCheckpoint=function(...) end
OnStart=function(...) end
game={Map={},Compass={}}
function game.Map.GetMarkerInfo(name) return {Id=name} end
function game.Compass.FindMarkersByIconClass(classes) return {} end
CompletionistMapV105PublishRavenState=function(id,value,source)
  calls.published[#calls.published+1]={id=id,value=value,source=source}
  return true
end
probe={}
function probe.start() OnStart() end
function probe.hit() OnHitByWeapon() end
function probe.restore(value) ravenKilled=value; OnRestoreCheckpoint() end
function probe.count() return #calls.published end
function probe.id(i) return calls.published[i].id end
function probe.value(i) return calls.published[i].value end
function probe.timerCount() return calls.timers end
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
        lua.execute(EVENT_PRELUDE)
        hook = build.render_lua(CATALOGUE, HERE / "all-ravens-gameplay-events.lua", "-- @@RAVEN_STATE_ROWS@@", True)
        lua.execute(hook.decode("utf-8"))
        probe = lua.globals().probe
        probe.start()
        self.assertEqual(probe.id(1), row["catalogue_id"])
        self.assertFalse(probe.value(1))
        probe.hit()
        self.assertTrue(probe.value(2))
        self.assertEqual(probe.timerCount(), 1)
        probe.restore(False)
        self.assertFalse(probe.value(3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
