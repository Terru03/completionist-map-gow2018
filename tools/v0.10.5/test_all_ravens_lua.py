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
calls={logs={},previousShow=0,previousUpdate=0,recycled=0,nativeConnects=0,nativeRequests={},footerUpdates=0,baseOverwriteOnce=false}
customIds={}
stockIds={}
nativeResponse=nil
local nativeSocket={}
function nativeSocket.tcp()
  local client={}
  function client:settimeout(value) calls.nativeTimeout=value; return 1 end
  function client:connect(host,port)
    calls.nativeConnects=calls.nativeConnects+1
    calls.nativeHost=host
    calls.nativePort=port
    if nativeResponse==nil then return nil,"connection refused" end
    self.receiveIndex=1
    return 1
  end
  function client:send(request)
    calls.nativeRequests[#calls.nativeRequests+1]=request
    return string.len(request)
  end
  function client:receive(size)
    if size~=1 then error("unexpected receive size:" .. tostring(size)) end
    local value=string.sub(nativeResponse,self.receiveIndex,self.receiveIndex)
    if value=="" then return nil,"closed" end
    self.receiveIndex=self.receiveIndex+1
    return value
  end
  function client:close() calls.nativeCloses=(calls.nativeCloses or 0)+1; return 1 end
  return client
end
require=function(name)
  if name=="socket.core" then return nativeSocket end
  error("unexpected require:" .. tostring(name))
end
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
local cursorTop={shown=false}
function cursorTop:Show() self.shown=true; calls.cursorTopShown=true end
function cursorTop:Hide() self.shown=false; calls.cursorTopShown=false end
local mapCursorInfo={}
function mapCursorInfo:Show() calls.mapCursorShown=true end
function mapCursorInfo:FindSingleGOByName(name)
  if name=="CursorInfo_Top" then return cursorTop end
  return nil
end
local cursorHandle={}
util={
  GetLAMSMsg=function(x) return x end,
  GetUiObjByName=function(name)
    if name=="MapCursorInfo" then return mapCursorInfo end
    return nil
  end,
  GetTextHandle=function(go,name)
    if go==cursorTop and name=="CursorAction_Text" then return cursorHandle end
    return nil
  end,
}
UI={
  SetTextIsClickable=function(handle)
    if handle==cursorHandle then calls.cursorClickable=true end
  end,
  SetText=function(handle,text)
    if handle==cursorHandle then calls.cursorPrompt=text end
  end,
}
Audio={PlaySound=function(x) calls.sound=x end}
MapOn={}
function MapOn.GetShowOnCompassPrompt(s,m) return s.currMarkerID~=nil,"base" end
function MapOn.ShowOnCompass(s,state) calls.previousShow=calls.previousShow+1; stockIds={"stock"} end
function MapOn.Update(s,...)
  calls.previousUpdate=calls.previousUpdate+1
  if calls.baseOverwriteOnce then
    calls.baseOverwriteOnce=false
    calls.cursorPrompt="base-stale"
    calls.footerPrompt="base-stale"
  end
  return "base-update"
end
function MapOn.MapCollisionChangeHandler(s,state,collisions,realm)
  if collisions and collisions[1] then s.currMarkerID=collisions[1].id else s.currMarkerID=nil end
end
function MapOn.SubmenuExit(s) end
function MapOn.Exit(s) end
function MapOn.ClearIcons(s) end
CompletionistMapV100_CreateMapPin=function(s,state) return "base" end
Map={}
function Map.FindRegionFromMarker(id) return true,"region" end
function Map.CreateMarkerIcon(id,region,label)
  return {id=id,shown=false,Show=function(self) self.shown=true end}
end
function Map.RecycleIcon(go) calls.recycled=calls.recycled+1; go.recycled=true end
game={Map={},Compass={}}
function game.Map.GetMarkerInfo(name) return {Id=markerId(name),X=1,Y=2,Z=3} end
function game.Compass.FindMarkersByIconClass(classes)
  if classes[1]=="CompletionistRaven" then return customIds end
  return stockIds
end
CompletionistMapV100Target={type="Raven",active=true}
function game.Compass.ShowMarker(name,class)
  customIds={markerId(name)}
  calls.shown=name
  calls.class=class
  if calls.removedCustomOnce then
    stockIds={"boat"}
    CompletionistMapV100Target.active=true
    calls.removedCustomOnce=false
  end
  calls.baseOverwriteOnce=true
end
function game.Compass.HideMarker(target)
  if type(target)=="number" and markerNamesById[target]~=nil then
    error("raw custom numeric ID rejected")
  end
  local beforeCustom=#customIds
  local next={}
  for _,id in ipairs(customIds) do
    local customName=markerNamesById[id]
    if tostring(id)~=tostring(target) and customName~=target then next[#next+1]=id end
  end
  customIds=next
  if #customIds < beforeCustom then
    CompletionistMapV100Target.active=true
    calls.removedCustomOnce=true
    calls.baseOverwriteOnce=true
  end
  local nextStock={}
  for _,id in ipairs(stockIds) do if tostring(id)~=tostring(target) then nextStock[#nextStock+1]=id end end
  stockIds=nextStock
end
local menu={}
function menu:UpdateFooterButton(name,show,text)
  calls.footerName=name
  calls.footerShow=show
  calls.footerPrompt=text
end
function menu:UpdateFooterButtonText()
  calls.footerUpdates=calls.footerUpdates+1
end
self={currRealmName="Alfheim",currMarkerID=nil,currShownMarkerID=nil,
  completionistMapV100Selected=false,completionistMapV100NornirSelected=nil,
  completionistMapV100NornirChestSelected=nil,mapIconCollision=nil,menu=menu}
function self:SetReticleInfo(state,title,desc)
  calls.reticleTitle=title
  calls.reticleDescription=desc
end
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
function probe.customCount() return #customIds end
function probe.stockCount() return #stockIds end
function probe.injectStock(value) stockIds={value} end
function probe.customAt(i) return customIds[i] end
function probe.markerId(name) return markerId(name) end
function probe.tracked() return CompletionistMapV105TrackedCatalogueId end
function probe.reticleTitle() return calls.reticleTitle end
function probe.reticleDescription() return calls.reticleDescription end
function probe.cursorPrompt() return calls.cursorPrompt end
function probe.footerPrompt() return calls.footerPrompt end
function probe.footerUpdates() return calls.footerUpdates end
function probe.update() return MapOn.Update(self,0) end
function probe.legacyRavenHudActive() return CompletionistMapV100Target.active end
function probe.teardown() MapOn.ClearIcons(self) end
function probe.reset() return CompletionistMapV105ResetRavenStates("save_load") end
function probe.setNativeResponse(value) nativeResponse=value end
function probe.nativeConnects() return calls.nativeConnects end
function probe.lastNativeGeneration() return CompletionistMapV105LastNativeRavenGeneration end
function probe.collectedCount()
  local n=0
  for _,value in pairs(CompletionistMapV105RavenState or {}) do if value==true then n=n+1 end end
  return n
end
function probe.state(id) return CompletionistMapV105RavenState[id] end
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

    def response(self, generation: int, killed_rows=()):
        killed_ids = [row["catalogue_id"] for row in killed_rows]
        killed = len(killed_ids)
        encoded = ",".join(killed_ids) if killed_ids else "-"
        return (
            "RAVEN_SNAPSHOT_V1 schema=1 "
            f"generation={generation} capturedTickMs={1000 + generation} "
            f"count=53 unknown=0 alive={53 - killed} killed={killed} "
            f"explicit={53 - killed} absentWadFalse={killed} killedIds={encoded}\n"
        )

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

    def test_raven_reticle_and_compass_prompt_refresh_immediately(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.publish(self.b["catalogue_id"], False)
        self.probe.open()

        show, text = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] add")
        self.assertEqual(self.probe.reticleTitle(), "Odin's Raven")
        self.assertEqual(self.probe.reticleDescription(), "Completionist Map")
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] remove")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")
        self.assertFalse(self.probe.legacyRavenHudActive())

        # The stock/base update may overwrite the footer/cursor one frame after
        # the action. The v0.10.5 settlement watchdog must win after that update.
        self.probe.update()
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] remove")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")
        self.assertFalse(self.probe.legacyRavenHudActive())

        show, text = self.probe.click(self.b["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] replace")
        self.assertEqual(self.probe.reticleTitle(), "Odin's Raven")
        self.assertEqual(self.probe.reticleDescription(), "Completionist Map")
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] remove")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

        show, text = self.probe.click(self.b["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] remove")
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] add")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] add")
        self.assertFalse(self.probe.legacyRavenHudActive())

        # Removing the same Raven deliberately simulates the legacy Raven HUD
        # trying to reactivate plus one stale base-UI update. Neither may survive.
        self.probe.update()
        self.assertEqual(self.probe.customCount(), 0)
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] add")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] add")
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.assertGreaterEqual(self.probe.footerUpdates(), 5)

    def test_same_raven_add_remove_keeps_compass_empty_and_prompt_settled(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()

        show, text = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] add")
        self.assertEqual(self.probe.customCount(), 1)
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.probe.update()
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

        show, text = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] remove")
        self.assertEqual(self.probe.customCount(), 0)
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.probe.update()

        self.assertEqual(self.probe.customCount(), 0)
        self.assertEqual(self.probe.stockCount(), 0)
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.assertEqual(self.probe.cursorPrompt(), "[AdvanceButton] add")
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] add")

        # Re-adding the exact same Raven in the same map-open session used to
        # resurrect a legacy/stock boat HUD target. Simulate that race.
        show, text = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(text, "[AdvanceButton] add")
        self.assertEqual(self.probe.customCount(), 1)
        self.assertEqual(self.probe.stockCount(), 0)
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.probe.update()
        self.assertEqual(self.probe.customCount(), 1)
        self.assertEqual(self.probe.stockCount(), 0)
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

    def test_unknown_hidden_restore_and_teardown(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.iconCount(), 1)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.teardown()
        self.assertEqual(self.probe.iconCount(), 0)

    def test_save_load_reset_clears_state_and_target_fail_closed(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.reset()
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIsNone(self.probe.tracked())
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)

    def test_advanced_native_snapshot_applies_27_killed_before_icon_sync(self):
        killed = CATALOGUE["ravens"][:27]
        self.probe.setNativeResponse(self.response(2, killed))
        self.probe.open()
        self.assertEqual(self.probe.collectedCount(), 27)
        self.assertEqual(self.probe.lastNativeGeneration(), 2)
        self.assertEqual(self.probe.nativeConnects(), 1)
        expected_visible = sum(
            row["realm"] == "Alfheim" and row not in killed
            for row in CATALOGUE["ravens"]
        )
        self.assertEqual(self.probe.iconCount(), expected_visible)

    def test_fresh_native_snapshot_applies_zero_killed_and_53_visible_state(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.assertEqual(self.probe.collectedCount(), 0)
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertEqual(self.probe.lastNativeGeneration(), 1)

    def test_same_and_older_native_generations_do_not_churn(self):
        self.probe.setNativeResponse(self.response(3, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.probe.setNativeResponse(self.response(3, [self.b]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNot(self.probe.state(self.b["catalogue_id"]), True)
        self.probe.setNativeResponse(self.response(2))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

    def test_reset_releases_raven_compass_ownership(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.customCount(), 0)

        self.probe.reset()
        self.probe.injectStock("stock-after-reset")
        self.probe.update()
        self.assertEqual(self.probe.stockCount(), 1)

    def test_reset_reapplies_same_generation_authority_once(self):
        self.probe.setNativeResponse(self.response(5, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertEqual(self.probe.lastNativeGeneration(), 5)

        self.probe.reset()
        self.probe.setNativeResponse(self.response(5, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertEqual(self.probe.lastNativeGeneration(), 5)

    def test_post_reset_bounded_recheck_accepts_new_generation(self):
        self.probe.setNativeResponse(self.response(7, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.reset()
        self.probe.setNativeResponse(self.response(7, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.setNativeResponse(self.response(8, [self.b]))
        self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertTrue(self.probe.state(self.b["catalogue_id"]))
        self.assertEqual(self.probe.lastNativeGeneration(), 8)

    def test_native_unavailable_preserves_immediate_event_state(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse(None)
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

    def test_immediate_event_kill_survives_same_generation_map_reopen(self):
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.probe.teardown()
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

    def test_new_native_generation_reasserts_map_state_on_reopen(self):
        self.probe.setNativeResponse(self.response(1, [self.a]))
        self.probe.open()
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))
        self.probe.teardown()
        self.probe.setNativeResponse(self.response(2, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

    def test_malformed_native_snapshot_falls_back_without_state_clear(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse(
            "RAVEN_SNAPSHOT_V1 schema=1 generation=8 capturedTickMs=9 "
            "count=53 unknown=0 alive=53 killed=0 explicit=0 "
            "absentWadFalse=53 killedIds=not_a_raven"
        )
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.lastNativeGeneration())

    def test_colliding_native_accessor_with_incomplete_table_fails_closed(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.lua.execute(
            "CompletionistMapNative.GetRavenSnapshot=function() "
            "return {schema=1,generation=9,count=53,states={}} end"
        )
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.lastNativeGeneration())

    def test_oversized_native_response_fails_closed(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse("RAVEN_SNAPSHOT_V1 " + ("x" * 5000) + "\n")
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.lastNativeGeneration())


EVENT_PRELUDE = r'''
calls={published={},timers=0,timerCallbacks={}}
print=function(s) end
ravenKilled=false
regionSummaryQuest=QUEST
thisObj={GetWorldPosition=function(self) return {x=PX,y=PY,z=PZ} end}
timers={StartLevelTimer=function(delay,fn)
  calls.timers=calls.timers+1
  calls.timerCallbacks[#calls.timerCallbacks+1]=fn
end}
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
function probe.setKilled(value) ravenKilled=value end
function probe.runNextTimer()
  if #calls.timerCallbacks==0 then return false end
  local fn=table.remove(calls.timerCallbacks,1)
  fn()
  return true
end
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
        self.assertGreaterEqual(probe.timerCount(), 2)

        # OnRestoreCheckpoint can fire before ravenKilled has settled. The
        # bounded restore retry must re-read the field instead of pinning the
        # early false value.
        probe.setKilled(True)
        # The earlier hit retry is still queued but must self-cancel because
        # OnRestoreCheckpoint advanced the event generation. Drain it first,
        # then execute the checkpoint retry that re-reads ravenKilled.
        self.assertTrue(probe.runNextTimer())
        self.assertTrue(probe.runNextTimer())
        self.assertTrue(probe.value(4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
