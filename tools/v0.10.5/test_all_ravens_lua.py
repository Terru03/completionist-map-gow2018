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
calls={logs={},previousShow=0,previousUpdate=0,recycled=0,nativeConnects=0,nativeRequests={},footerUpdates=0,baseOverwriteOnce=false,loadHooks={}}
customIds={}
stockIds={}
nativeResponse=nil
nativeBoundaryResponse=nil
local nativeSocket={}
function nativeSocket.tcp()
  local client={}
  function client:settimeout(value) calls.nativeTimeout=value; return 1 end
  function client:connect(host,port)
    calls.nativeConnects=calls.nativeConnects+1
    calls.nativeHost=host
    calls.nativePort=port
    if nativeResponse==nil and nativeBoundaryResponse==nil then return nil,"connection refused" end
    self.receiveIndex=1
    self.response=nil
    return 1
  end
  function client:send(request)
    calls.nativeRequests[#calls.nativeRequests+1]=request
    if string.sub(request,1,string.len("CAPTURE RAVEN_SNAPSHOT_V2 "))=="CAPTURE RAVEN_SNAPSHOT_V2 " then
      self.response=nativeBoundaryResponse
    else
      self.response=nativeResponse
    end
    if self.response==nil then return nil,"no response" end
    return string.len(request)
  end
  function client:receive(size)
    if size~=1 then error("unexpected receive size:" .. tostring(size)) end
    local value=string.sub(self.response,self.receiveIndex,self.receiveIndex)
    if value=="" then return nil,"closed" end
    self.receiveIndex=self.receiveIndex+1
    return value
  end
  function client:close() calls.nativeCloses=(calls.nativeCloses or 0)+1; return 1 end
  return client
end
local coreThunk={}
function coreThunk.Install(name,fn)
  calls.loadHooks[name]=fn
  return true
end
require=function(name)
  if name=="socket.core" then return nativeSocket end
  if name=="core.thunk" then return coreThunk end
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
function MapOn.SubmenuExit(s)
  -- Real-game regression: base teardown can reclaim HUD ownership after the
  -- Raven Update watchdog stops, leaving a stock/boat target.
  customIds={}
  stockIds={"boat"}
  calls.baseExitReassert=true
end
function MapOn.Exit(s) end
function MapOn.ClearIcons(s) end
CompletionistMapV100_CreateMapPin=function(s,state) return "base" end
Map={}
function Map.FindRegionFromMarker(id) return true,"region" end
function Map.CreateMarkerIcon(id,region,label)
  return {id=id,shown=false,Show=function(self) self.shown=true end}
end
function Map.RecycleIcon(go) calls.recycled=calls.recycled+1; go.recycled=true end
regionSummaryCompleted={}
game={Map={},Compass={},QuestManager={}}
function game.QuestManager.GetQuestProgressAndGoal(parent)
  return nil,regionSummaryCompleted[parent]
end
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
    stockIds={markerId(name),"boat"}
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
  for _,id in ipairs(stockIds) do
    local stockName=markerNamesById[id]
    if tostring(id)~=tostring(target) and stockName~=target then
      nextStock[#nextStock+1]=id
    end
  end
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
  if self.owner~=nil then
    local show,text=MapOn.GetShowOnCompassPrompt(self.owner,self)
    if show then calls.footerPrompt=text end
  end
end
self={currRealmName="Alfheim",currMarkerID=nil,currShownMarkerID=nil,
  completionistMapV100Selected=false,completionistMapV100NornirSelected=nil,
  completionistMapV100NornirChestSelected=nil,mapIconCollision=nil,menu=menu}
menu.owner=self
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
function probe.stockOtherCount(exceptId)
  local n=0
  for _,id in ipairs(stockIds) do
    if tostring(id)~=tostring(exceptId) then n=n+1 end
  end
  return n
end
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
function probe.submenuExit() return MapOn.SubmenuExit(self) end
function probe.shownClass() return calls.class end
function probe.legacyRavenHudActive() return CompletionistMapV100Target.active end
function probe.teardown() MapOn.ClearIcons(self) end
function probe.reset() return CompletionistMapV105ResetRavenStates("save_load") end
function probe.boundary() return CompletionistMapV105NotifyAuthorityBoundary("test_load") end
function probe.fireLoad(name)
  local fn=calls.loadHooks[name]
  if fn==nil then return false end
  fn()
  return true
end
function probe.setNativeResponse(value) nativeResponse=value end
function probe.setNativeBoundaryResponse(value) nativeBoundaryResponse=value end
function probe.setRegionSummaryCompleted(parent,value)
  regionSummaryCompleted[parent]=value
end
function probe.logs()
  return table.concat(calls.logs,"\n")
end
function probe.nativeConnects() return calls.nativeConnects end
function probe.nativeRequest(i) return calls.nativeRequests[i] end
function probe.nativeRequestCount() return #calls.nativeRequests end
function probe.lastNativeGeneration() return CompletionistMapV105LastNativeRavenGeneration end
function probe.boundaryEpoch() return CompletionistMapV105NativeBoundaryEpoch end
function probe.collectedCount()
  local n=0
  for _,value in pairs(CompletionistMapV105RavenState or {}) do if value==true then n=n+1 end end
  return n
end
function probe.state(id) return CompletionistMapV105RavenState[id] end
function probe.hasAuthority() return CompletionistMapV105HasAuthoritativeRavenState==true end
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
        # Most UI-routing tests assume the catalogue is already authorized.
        # Individual authority tests override this response explicitly.
        self.probe.setNativeResponse(self.response(1))

    def _set_region_counts(self, killed_rows=()):
        counts = {}
        for row in CATALOGUE["ravens"]:
            parent = row["progression"]["parent_quest"]
            counts.setdefault(parent, 0)
        for row in killed_rows:
            parent = row["progression"]["parent_quest"]
            counts[parent] = counts.get(parent, 0) + 1
        target_overrides = {
            "RegionSummary_CALS_Raven_Parent": 1,
            "RegionSummary_RP_Raven_Parent": 6,
        }
        for parent, count in counts.items():
            completed = min(count, target_overrides.get(parent, count))
            self.probe.setRegionSummaryCompleted(parent, completed)

    def response(self, generation: int, killed_rows=(), restore_epoch: int = 0):
        self._set_region_counts(killed_rows)
        killed_ids = [row["catalogue_id"] for row in killed_rows]
        killed = len(killed_ids)
        encoded = ",".join(killed_ids) if killed_ids else "-"
        return (
            "RAVEN_SNAPSHOT_V1 schema=1 "
            f"restoreEpoch={restore_epoch} generation={generation} "
            f"capturedTickMs={1000 + generation} "
            f"count=53 unknown=0 alive={53 - killed} killed={killed} "
            f"explicit={53 - killed} absentWadFalse={killed} killedIds={encoded}\n"
        )

    def boundary_response(self, epoch: int, generation: int, killed_rows=()):
        self._set_region_counts(killed_rows)
        killed_ids = [row["catalogue_id"] for row in killed_rows]
        killed = len(killed_ids)
        encoded = ",".join(killed_ids) if killed_ids else "-"
        return (
            "RAVEN_SNAPSHOT_V2 schema=2 "
            f"boundaryEpoch={epoch} generation={generation} "
            f"capturedTickMs={2000 + generation} "
            f"count=53 unknown=0 alive={53 - killed} killed={killed} "
            f"explicit={53 - killed} absentWadFalse={killed} killedIds={encoded}\n"
        )

    def partial_response(
        self,
        unknown_row,
        killed_rows=(),
        absence_rows=(),
        restore_epoch: int = 0,
        boundary_epoch=None,
    ):
        self._set_region_counts(killed_rows)
        killed_ids = [row["catalogue_id"] for row in killed_rows]
        absence_ids = [row["catalogue_id"] for row in absence_rows]
        unknown_ids = [] if unknown_row is None else [unknown_row["catalogue_id"]]
        killed = len(killed_ids)
        unknown = len(unknown_ids)
        absent = len(absence_ids)
        known = 53 - unknown
        explicit = known - absent
        encoded = ",".join(killed_ids) if killed_ids else "-"
        unknown_encoded = ",".join(unknown_ids) if unknown_ids else "-"
        absence_encoded = ",".join(absence_ids) if absence_ids else "-"
        header = (
            "RAVEN_SNAPSHOT_V1 PARTIAL schema=1 "
            f"restoreEpoch={restore_epoch} "
            if boundary_epoch is None
            else "RAVEN_SNAPSHOT_V2 PARTIAL schema=2 "
            f"boundaryEpoch={boundary_epoch} "
        )
        return (
            header
            + f"capturedTickMs=3000 count=53 unknown={unknown} "
            + f"alive={known - killed} killed={killed} explicit={explicit} "
            + f"absentWadFalse={absent} killedIds={encoded} "
            + f"unknownIds={unknown_encoded} absenceIds={absence_encoded}\n"
        )

    def test_confirmed_fresh_zero_does_not_require_region_summary(self):
        self.lua.execute("regionSummaryCompleted={}")
        self.probe.setNativeResponse(
            "RAVEN_SNAPSHOT_V1 schema=1 restoreEpoch=0 generation=8 "
            "capturedTickMs=1008 count=53 unknown=0 alive=53 killed=0 "
            "explicit=0 absentWadFalse=53 killedIds=-\n"
        )
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertEqual(self.probe.iconCount(), 2)

    def test_full_native_snapshot_conflicting_with_region_summary_is_refused(self):
        stale = self.response(9, [self.a, self.b])
        parent = self.a["progression"]["parent_quest"]
        self.probe.setRegionSummaryCompleted(parent, 0)
        self.probe.setNativeResponse(stale)
        self.probe.open()
        self.assertFalse(self.probe.hasAuthority())
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIn("NATIVE_AUTHORITY_REGION_REFUSED", self.probe.logs())

    def test_partial_wad_absence_is_resolved_by_region_summary_not_default_alive(self):
        absence = next(
            row
            for row in CATALOGUE["ravens"]
            if row["progression"]["parent_quest"] == "RegionSummary_FOR_Raven_Parent"
        )
        parent = absence["progression"]["parent_quest"]

        # Same native partial bytes can resolve differently only when the live
        # parent completed count differs. WAD absence itself is never authority.
        wire = self.partial_response(None, absence_rows=[absence])
        self.probe.setRegionSummaryCompleted(parent, 1)
        self.probe.setNativeResponse(wire)
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertTrue(self.probe.state(absence["catalogue_id"]))

    def test_partial_native_snapshot_resolves_single_alfheim_unknown_alive(self):
        parent = self.a["progression"]["parent_quest"]
        self.probe.setRegionSummaryCompleted(parent, 0)
        self.probe.setNativeResponse(self.partial_response(self.a))
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertFalse(self.probe.state(self.a["catalogue_id"]))
        self.assertFalse(self.probe.state(self.b["catalogue_id"]))
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertIsNone(self.probe.lastNativeGeneration())
        self.assertIn("NATIVE_AUTHORITY_DERIVED", self.probe.logs())

    def test_partial_native_snapshot_resolves_single_alfheim_unknown_killed(self):
        parent = self.a["progression"]["parent_quest"]
        self.probe.setRegionSummaryCompleted(parent, 1)
        self.probe.setNativeResponse(self.partial_response(self.a))
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertFalse(self.probe.state(self.b["catalogue_id"]))
        self.assertEqual(self.probe.iconCount(), 1)

    def test_partial_native_snapshot_refuses_bonus_parent(self):
        bonus = next(
            row
            for row in CATALOGUE["ravens"]
            if row["progression"]["parent_quest"] == "RegionSummary_RP_Raven_Parent"
        )
        self.probe.setRegionSummaryCompleted("RegionSummary_RP_Raven_Parent", 0)
        self.probe.setNativeResponse(self.partial_response(bonus))
        self.probe.open()
        self.assertFalse(self.probe.hasAuthority())
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIn("NATIVE_AUTHORITY_PARTIAL_REFUSED", self.probe.logs())

    def test_partial_boundary_snapshot_reestablishes_authority(self):
        parent = self.a["progression"]["parent_quest"]
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())

        self.probe.boundary()
        self.probe.setRegionSummaryCompleted(parent, 0)
        self.probe.setNativeBoundaryResponse(
            self.partial_response(self.a, boundary_epoch=1)
        )
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertEqual(self.probe.boundaryEpoch(), 1)
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertIn("authority=native_partial_plus_region_summary", self.probe.logs())

    def test_no_authority_bootstrap_hides_all_ravens(self):
        self.probe.setNativeResponse(None)
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertFalse(self.probe.hasAuthority())

        # Once an atomic fresh 53-state snapshot is available, the same map
        # context may reveal the catalogue normally.
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.assertTrue(self.probe.hasAuthority())
        self.assertEqual(self.probe.iconCount(), 2)

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
        self.assertEqual(
            self.probe.stockOtherCount(self.probe.markerId(self.a["marker"]["name"])), 0
        )
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.customCount(), 0)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertIsNotNone(self.probe.icon(self.b["marker"]["name"]))

    def test_rapid_readd_wins_delayed_native_remove(self):
        self.probe.open()
        name = self.a["marker"]["name"]
        self.probe.click(name)
        self.lua.execute("savedHide=game.Compass.HideMarker; game.Compass.HideMarker=function() end")
        self.probe.click(name)
        self.probe.click(name)
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.lua.execute("game.Compass.HideMarker=savedHide; customIds={}")
        self.probe.update()
        self.assertEqual(self.probe.customAt(1), self.probe.markerId(name))
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

    def test_late_base_update_cannot_revert_settled_prompt(self):
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.probe.update()
        self.lua.execute("calls.baseOverwriteOnce=true")
        self.probe.update()
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

    def test_pending_action_does_not_overwrite_other_raven_prompt(self):
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.lua.globals().hoverName = self.b["marker"]["name"]
        self.lua.execute("MapOn.MapCollisionChangeHandler(self,{}, {probe.icon(hoverName)},self.currRealmName)")
        self.probe.update()
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] replace")

    def test_settled_remove_keeps_prompt_without_owning_new_stock(self):
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.probe.click(self.a["marker"]["name"])
        for _ in range(4):
            self.probe.update()
        self.lua.execute("calls.baseOverwriteOnce=true")
        self.probe.update()
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] add")
        self.probe.injectStock("stock-after-settled-remove")
        self.probe.update()
        self.assertEqual(self.probe.stockCount(), 1)
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] replace")

    def test_kill_releases_owner_and_stale_prompt(self):
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.injectStock("legitimate-stock-after-kill")
        self.probe.update()
        self.assertEqual(self.probe.stockCount(), 1)
        self.assertEqual(self.probe.customCount(), 0)

    def test_boundary_disarms_pending_selection(self):
        self.probe.open()
        self.lua.globals().hoverName = self.a["marker"]["name"]
        self.lua.execute("MapOn.MapCollisionChangeHandler(self,{}, {probe.icon(hoverName)},self.currRealmName); MapOn.GetShowOnCompassPrompt(self,nil)")
        self.probe.boundary()
        self.lua.execute("self.currMarkerID='stock'; MapOn.ShowOnCompass(self,{})")
        self.assertEqual(self.probe.stockCount(), 1)

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
        self.assertEqual(
            self.probe.stockOtherCount(self.probe.markerId(self.a["marker"]["name"])), 0
        )
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.probe.update()
        self.assertEqual(self.probe.customCount(), 1)
        self.assertEqual(
            self.probe.stockOtherCount(self.probe.markerId(self.a["marker"]["name"])), 0
        )
        self.assertFalse(self.probe.legacyRavenHudActive())
        self.assertEqual(self.probe.footerPrompt(), "[AdvanceButton] remove")

    def test_map_exit_reasserts_custom_raven_after_base_boat_reclaim(self):
        self.probe.open()
        name = self.a["marker"]["name"]
        self.probe.click(name)
        self.assertEqual(self.probe.customCount(), 1)

        self.probe.submenuExit()

        self.assertEqual(self.probe.customCount(), 1)
        self.assertEqual(
            self.probe.stockOtherCount(self.probe.markerId(name)), 0
        )
        self.assertEqual(self.probe.shownClass(), "CompletionistRaven")
        self.assertFalse(self.probe.legacyRavenHudActive())

    def test_false_event_cannot_revive_and_postboundary_snapshot_can(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.iconCount(), 1)

        # Event-side false is explicitly non-authoritative.
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 1)
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        # A normal newer snapshot must preserve positive in-session kill
        # evidence; only a post-load/checkpoint atomic snapshot may clear it.
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 1)
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.boundary()
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 2))
        for _ in range(35):
            self.probe.update()
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)

        self.probe.teardown()
        self.assertEqual(self.probe.iconCount(), 0)

    def test_native_restore_epoch_forces_matching_v2_before_state_replacement(self):
        self.probe.setNativeResponse(self.response(1, [self.a], restore_epoch=0))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        # A bridge-owned restore epoch is process-wide and can be observed even
        # when the gameplay and map Lua sandboxes do not share _G.
        self.probe.setNativeResponse(self.response(2, [], restore_epoch=1))
        self.probe.setNativeBoundaryResponse(self.boundary_response(1, 3, [self.a, self.b]))
        self.probe.open()

        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertTrue(self.probe.state(self.b["catalogue_id"]))
        requests = [
            self.probe.nativeRequest(i)
            for i in range(1, self.probe.nativeRequestCount() + 1)
        ]
        self.assertIn("CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=1\n", requests)

    def test_first_nonzero_restore_epoch_requires_v2_capture(self):
        self.probe.setNativeResponse(self.response(10, [], restore_epoch=4))
        self.probe.setNativeBoundaryResponse(self.boundary_response(4, 11, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        requests = [
            self.probe.nativeRequest(i)
            for i in range(1, self.probe.nativeRequestCount() + 1)
        ]
        self.assertIn("CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=4\n", requests)

    def test_boundary_accepts_only_matching_postload_capture_not_newer_periodic_state(self):
        self.probe.setNativeResponse(self.response(10, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        # A load boundary is now active. The background V1 stream can continue
        # producing newer generations that still describe the old save. Those
        # generations must never settle the boundary.
        self.probe.setNativeResponse(self.response(11))
        self.probe.boundary()
        for _ in range(35):
            self.probe.update()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        # The authoritative post-load capture is requested explicitly after
        # the boundary and carries the boundary epoch echoed by the bridge.
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 12))
        for _ in range(35):
            self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))
        requests = [
            self.probe.nativeRequest(i)
            for i in range(1, self.probe.nativeRequestCount() + 1)
        ]
        self.assertTrue(any(
            request == f"CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch={epoch}\n"
            for request in requests
        ))

    def test_load_boundary_preserves_last_good_state_until_matching_capture(self):
        self.probe.setNativeResponse(self.response(4, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        self.probe.boundary()
        epoch = int(self.probe.boundaryEpoch())

        # Periodic V1 state is irrelevant while the boundary is pending.
        self.probe.setNativeResponse(self.response(50))
        for _ in range(35):
            self.probe.update()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 51))
        for _ in range(35):
            self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))

    def test_unavailable_boundary_capture_preserves_state_until_capture_succeeds(self):
        self.probe.setNativeResponse(self.response(4, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.boundary()
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeBoundaryResponse(None)
        for _ in range(35):
            self.probe.update()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 6))
        for _ in range(35):
            self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))

    def test_global_load_event_arms_authority_boundary(self):
        self.probe.setNativeResponse(self.response(8, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertTrue(self.probe.fireLoad("EVT_LoadSaveFile_Done"))
        epoch = int(self.probe.boundaryEpoch())

        self.probe.setNativeResponse(self.response(99))
        for _ in range(35):
            self.probe.update()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 100))
        for _ in range(35):
            self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)

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

    def test_fresh_native_snapshot_applies_zero_killed_after_load_boundary(self):
        self.probe.publish(self.a["catalogue_id"], True)

        # A true fresh-save/load transition explicitly authorizes replacement
        # of prior session event evidence.
        self.probe.setNativeResponse(self.response(1))
        self.probe.boundary()
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 2))
        self.probe.open()
        for _ in range(35):
            self.probe.update()

        self.assertEqual(self.probe.collectedCount(), 0)
        self.assertEqual(self.probe.iconCount(), 2)
        self.assertEqual(self.probe.lastNativeGeneration(), 2)

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

    def test_post_reset_bounded_recheck_accepts_new_generation(self):
        self.probe.setNativeResponse(self.response(7, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))

        self.probe.reset()
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeResponse(self.response(70, [self.b]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNot(self.probe.state(self.b["catalogue_id"]), True)

        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 71, [self.b]))
        self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertTrue(self.probe.state(self.b["catalogue_id"]))
        self.assertEqual(self.probe.lastNativeGeneration(), 71)

    def test_native_unavailable_preserves_immediate_event_state(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse(None)
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

    def test_immediate_event_kill_survives_newer_preboundary_snapshot(self):
        self.probe.setNativeResponse(self.response(1))
        self.probe.open()
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        # A newer periodic capture can still reflect pre-kill state. Without a
        # load boundary it must merge the positive event overlay, not revive.
        self.probe.teardown()
        self.probe.setNativeResponse(self.response(2))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        # After an explicit load boundary, a strictly newer atomic snapshot is
        # allowed to clear the session event overlay.
        self.probe.boundary()
        epoch = int(self.probe.boundaryEpoch())
        self.probe.setNativeBoundaryResponse(self.boundary_response(epoch, 3))
        for _ in range(35):
            self.probe.update()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))

    def test_new_native_generation_is_only_alive_clear_path(self):
        self.probe.setNativeResponse(self.response(1, [self.a]))
        self.probe.open()
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        self.probe.publish(self.a["catalogue_id"], False)
        self.assertTrue(self.probe.state(self.a["catalogue_id"]))
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))

        self.probe.teardown()
        self.probe.setNativeResponse(self.response(2))
        self.probe.open()
        self.assertIsNot(self.probe.state(self.a["catalogue_id"]), True)
        self.assertIsNotNone(self.probe.icon(self.a["marker"]["name"]))

    def test_malformed_native_snapshot_falls_back_without_state_clear(self):
        self.probe.publish(self.a["catalogue_id"], True)
        self.probe.setNativeResponse(
            "RAVEN_SNAPSHOT_V1 schema=1 restoreEpoch=0 generation=8 capturedTickMs=9 "
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
            "return {schema=1,restoreEpoch=0,generation=9,count=53,states={}} end"
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
calls={published={},timers=0,timerCallbacks={},boundaries={},notes={}}
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
local bridgeResponse=""
local bridgeIndex=1
local bridgeClient={}
function bridgeClient:settimeout(...) return true end
function bridgeClient:connect(host,port) return 1 end
function bridgeClient:send(request)
  calls.notes[#calls.notes+1]=request
  if string.sub(request,1,string.len("NOTE RAVEN_KILLED_V1 "))=="NOTE RAVEN_KILLED_V1 " then
    bridgeResponse="RAVEN_NOTE_V1 OK kind=killed restoreEpoch=0\n"
  else
    bridgeResponse="RAVEN_NOTE_V1 OK kind=boundary restoreEpoch=1 advanced=true\n"
  end
  bridgeIndex=1
  return string.len(request)
end
function bridgeClient:receive(size)
  local value=string.sub(bridgeResponse,bridgeIndex,bridgeIndex)
  if value=="" then return nil,"closed" end
  bridgeIndex=bridgeIndex+1
  return value
end
function bridgeClient:close() return true end
local socketCore={tcp=function() return bridgeClient end}
require=function(name)
  if name=="socket.core" then return socketCore end
  error("module unavailable: "..tostring(name))
end
game={Map={},Compass={}}
function game.Map.GetMarkerInfo(name) return {Id=name} end
function game.Compass.FindMarkersByIconClass(classes) return {} end
CompletionistMapV105PublishRavenState=function(id,value,source)
  calls.published[#calls.published+1]={id=id,value=value,source=source}
  return true
end
CompletionistMapV105NotifyAuthorityBoundary=function(source)
  calls.boundaries[#calls.boundaries+1]=source
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
function probe.boundaryCount() return #calls.boundaries end
function probe.boundary(i) return calls.boundaries[i] end
function probe.noteCount() return #calls.notes end
function probe.note(i) return calls.notes[i] end
function probe.bridgeOnly()
  CompletionistMapV105PublishRavenState=nil
  CompletionistMapV105NotifyAuthorityBoundary=nil
end
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
        self.assertEqual(probe.count(), 0)

        probe.hit()
        self.assertEqual(probe.id(1), row["catalogue_id"])
        self.assertTrue(probe.value(1))
        self.assertEqual(probe.timerCount(), 1)

        # Restore-time false is not authoritative. It must arm an atomic
        # authority boundary without publishing an "alive" state.
        probe.restore(False)
        self.assertEqual(probe.count(), 1)
        self.assertEqual(probe.boundaryCount(), 1)
        self.assertEqual(probe.boundary(1), "OnRestoreCheckpoint")
        self.assertGreaterEqual(probe.timerCount(), 2)

        # If ravenKilled settles true after restore, the bounded positive-only
        # retry may publish the kill. It may never publish false.
        probe.setKilled(True)
        self.assertTrue(probe.runNextTimer())
        self.assertTrue(probe.runNextTimer())
        self.assertEqual(probe.count(), 2)
        self.assertTrue(probe.value(2))

    def test_cross_context_kill_and_restore_use_native_bridge(self):
        row = CATALOGUE["ravens"][0]
        x, y, z = row["source"]["native_world_position"]
        lua = LuaRuntime(unpack_returned_tuples=True)
        globals_ = lua.globals()
        globals_.QUEST = row["progression"]["parent_quest"]
        globals_.PX, globals_.PY, globals_.PZ = x, y, z
        lua.execute(EVENT_PRELUDE)
        hook = build.render_lua(
            CATALOGUE,
            HERE / "all-ravens-gameplay-events.lua",
            "-- @@RAVEN_STATE_ROWS@@",
            True,
        )
        lua.execute(hook.decode("utf-8"))
        probe = lua.globals().probe
        probe.bridgeOnly()

        probe.hit()
        notes = [probe.note(i) for i in range(1, probe.noteCount() + 1)]
        self.assertIn(
            f"NOTE RAVEN_KILLED_V1 catalogueId={row['catalogue_id']}\n",
            notes,
        )

        before = probe.noteCount()
        probe.restore(False)
        notes = [probe.note(i) for i in range(before + 1, probe.noteCount() + 1)]
        self.assertIn("NOTE RAVEN_BOUNDARY_V1 source=checkpoint\n", notes)
        # A false restored state is never sent as an alive/revival note.
        self.assertFalse(any("RAVEN_KILLED" in note for note in notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
