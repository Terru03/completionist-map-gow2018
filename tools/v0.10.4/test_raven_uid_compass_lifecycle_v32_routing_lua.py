"""Lua 5.1 tests for v3.2 Raven prompt/action selection handoff."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "dist/re-tools"))
from lupa.lua51 import LuaRuntime

SOURCE = HERE / "raven-uid-compass-routing-v3.2.lua"

PRELUDE = r'''
local calls = {logs={}, previousShow=0, previousCollision=0, hidden={}, customShows=0}
local customIds, stockIds = {}, {}
local hideFailure=false
local promptAvailable=true
local autoPrompt=true
local ravenGO, twinGO, stockGO, nornirGO =
  {kind="raven"}, {kind="twin"}, {kind="stock"}, {kind="nornir"}
local self = {
  mapIconCollision=nil,
  completionistMapV100MapIconGO=ravenGO,
  completionistSharedLoaderTwinGO=twinGO,
  completionistMapV100Frame=0,
  completionistMapV100Selected=false,
  completionistMapV100NornirSelected=nil,
  completionistMapV100NornirChestSelected=nil,
  currShownMarkerID=nil,
  currMarkerID=nil,
  currRealmName="Midgard",
  menu=nil,
}
print=function(s) calls.logs[#calls.logs+1]=s end

MapOn = {}
function MapOn.GetShowOnCompassPrompt(s, menu)
  if not promptAvailable then return false, nil end
  if s.completionistMapV100NornirSelected ~= nil or
      s.completionistMapV100NornirChestSelected ~= nil or
      s.completionistMapV100Selected == true or s.currMarkerID ~= nil then
    return true, "previous-prompt"
  end
  return false, nil
end
function MapOn.ShowOnCompass(s, state)
  calls.previousShow=calls.previousShow+1
  stockIds={"native-stock-id"}
  return "previous-show"
end
function MapOn.Update(s)
  s.completionistMapV100Frame=(s.completionistMapV100Frame or 0)+1
  return "previous-update"
end
function MapOn.MapCollisionChangeHandler(s, state, collisions, realm)
  calls.previousCollision=calls.previousCollision+1
  local go=collisions and collisions[1] or nil
  if go==ravenGO or go==twinGO then
    s.completionistMapV100Selected=true
    s.completionistMapV100NornirSelected=nil
    s.completionistMapV100NornirChestSelected=nil
    s.currMarkerID=nil
    s.mapIconCollision=nil
    if autoPrompt then MapOn.GetShowOnCompassPrompt(s, state.menu or {}) end
  elseif go==stockGO then
    s.completionistMapV100Selected=false
    s.completionistMapV100NornirSelected=nil
    s.completionistMapV100NornirChestSelected=nil
    s.currMarkerID="dock-id"
    if autoPrompt then MapOn.GetShowOnCompassPrompt(s, state.menu or {}) end
  elseif go==nornirGO then
    s.completionistMapV100Selected=false
    s.completionistMapV100NornirSelected={registryKey="nornir"}
    s.completionistMapV100NornirChestSelected=nil
    s.currMarkerID=nil
    if autoPrompt then MapOn.GetShowOnCompassPrompt(s, state.menu or {}) end
  end
  -- Empty/noncustom callbacks model production debounce noise: no owner change.
  return "previous-collision"
end
function MapOn.SubmenuExit() return "submenu" end
function MapOn.Exit() return "exit" end
function MapOn.ClearIcons() return "clear" end

local markerInfo = {
  Completionist_V103_Veithurgard_Raven_01={Id="-2207208259907848386",X=1,Y=2,Z=3},
  Completionist_V104_Veithurgard_Raven_Twin_01={Id="3410085282531601808",X=4,Y=5,Z=6},
}
game={Map={},Compass={},QuestManager={}}
function game.Map.GetMarkerInfo(name) return markerInfo[name] end
function game.Compass.FindMarkersByIconClass(classes)
  if classes and classes[1]=="CompletionistRaven" then return customIds end
  return stockIds
end
function game.Compass.ShowMarker(name, class)
  calls.shownName, calls.shownClass=name, class
  calls.customShows=calls.customShows+1
  customIds={markerInfo[name].Id}
end
function game.Compass.HideMarker(target)
  if hideFailure then error("hide failed") end
  calls.hidden[#calls.hidden+1]=tostring(target)
  if tostring(target)=="Completionist_V103_Veithurgard_Raven_01" or tostring(target)=="-2207208259907848386" then
    if customIds[1]=="-2207208259907848386" then customIds={} end
  elseif tostring(target)=="Completionist_V104_Veithurgard_Raven_Twin_01" or tostring(target)=="3410085282531601808" then
    if customIds[1]=="3410085282531601808" then customIds={} end
  else
    stockIds={}
  end
end
function game.QuestManager.GetQuestState() return "Active" end

enabledShowOnCompassMarkerFlags={"DockPoint"}
lamsConsts={RemoveFromCompass="remove",ReplaceInCompass="replace",AddToCompass="add"}
util={GetLAMSMsg=function(id) return id end,GetUiObjByName=function() return nil end}
UI={}
Audio={PlaySound=function(name) calls.lastSound=name end}
local CompletionistMapV100_IsRavenCollected=function() return false end
_G.CompletionistMapV100TargetRavenKilled=false
'''

POSTLUDE = r'''
local function collide(go, withPrompt)
  autoPrompt=withPrompt~=false
  local list={}
  if go~=nil then list[1]=go end
  local result=MapOn.MapCollisionChangeHandler(self,{menu={}},list,"Midgard")
  autoPrompt=true
  return result
end
return {
  self=self,calls=calls,ravenGO=ravenGO,twinGO=twinGO,stockGO=stockGO,nornirGO=nornirGO,
  collide=function(go) return collide(go,true) end,
  capture=function(go) return collide(go,false) end,
  incidental=function() return collide(nil,true) end,
  prompt=function() return MapOn.GetShowOnCompassPrompt(self,{}) end,
  action=function() return MapOn.ShowOnCompass(self,{}) end,
  update=function() return MapOn.Update(self) end,
  teardown=function(which) return MapOn[which](self,{}) end,
  selectionName=function()
    local p=self.completionistMapV104RavenSelection
    return p and p.Name or nil
  end,
  selectionUid=function()
    local p=self.completionistMapV104RavenSelection
    return p and p.IdString or nil
  end,
  selectionState=function()
    local p=self.completionistMapV104RavenSelection
    return p and p.State or "none"
  end,
  customId=function() return customIds[1] end,
  stock=function() stockIds={"dock-id"}; self.currShownMarkerID="dock-id" end,
  stockId=function() return stockIds[1] end,
  activeCount=function() return #customIds + #stockIds end,
  failHide=function(v) hideFailure=v end,
  promptAvailable=function(v) promptAvailable=v end,
  collected=function(v) _G.CompletionistMapV100TargetRavenKilled=v end,
  loseOwner=function() self.completionistMapV100Selected=false; self.currMarkerID=nil end,
  logs=function() return table.concat(calls.logs,"\n") end,
}
'''


class RavenUidV32RoutingTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.p = self.lua.execute(PRELUDE + self.source + POSTLUDE)

    def advance(self, count):
        for _ in range(count):
            self.p.update()

    def test_exact_twin_collision_becomes_armed_from_production_prompt(self):
        self.p.collide(self.p.twinGO)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.assertEqual(self.p.selectionUid(), "3410085282531601808")
        self.assertIn("SELECT_CANDIDATE", self.p.logs())
        self.assertIn("SELECT_ARM", self.p.logs())

    def test_candidate_without_prompt_is_not_consumed(self):
        self.p.capture(self.p.twinGO)
        self.assertEqual(self.p.selectionState(), "candidate-custom")
        self.p.action()
        self.assertEqual(self.p.calls.previousShow, 1)
        self.assertNotIn("SELECT_CONSUME", self.p.logs())

    def test_twin_survives_301_update_frames_and_routes_exact_class(self):
        self.p.collide(self.p.twinGO)
        self.advance(31)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.advance(30)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.advance(240)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.p.action()
        self.assertEqual(self.p.calls.shownName, "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.assertEqual(self.p.calls.shownClass, "CompletionistRaven")
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.calls.previousShow, 0)

    def test_real_survives_301_update_frames_and_routes_exact_class(self):
        self.p.collide(self.p.ravenGO)
        self.advance(31)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.advance(30)
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.advance(240)
        self.p.action()
        self.assertEqual(self.p.calls.shownName, "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.p.customId(), "-2207208259907848386")

    def test_incidental_noncustom_callbacks_do_not_disarm_armed_twin(self):
        self.p.collide(self.p.twinGO)
        for _ in range(8):
            self.p.incidental()
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.p.action()
        self.assertEqual(self.p.customId(), "3410085282531601808")

    def test_different_exact_custom_replaces_and_arms(self):
        self.p.collide(self.p.twinGO)
        self.p.collide(self.p.ravenGO)
        self.assertEqual(self.p.selectionName(), "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.p.selectionState(), "armed-custom")
        self.assertIn("reason=exact_custom_replaced", self.p.logs())

    def test_genuine_stock_prompt_disarms_stale_twin(self):
        self.p.collide(self.p.twinGO)
        self.p.collide(self.p.stockGO)
        self.assertEqual(self.p.selectionState(), "none")
        self.assertIn("reason=confirmed_native_prompt:marker=dock-id", self.p.logs())
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.previousShow, 1)

    def test_stock_action_guard_disarms_when_prompt_callback_is_skipped(self):
        self.p.collide(self.p.twinGO)
        self.p.capture(self.p.stockGO)
        self.assertEqual(self.p.action(), "previous-show")
        self.assertIsNone(self.p.calls.shownName)
        self.assertIn("reason=confirmed_native_action:marker=dock-id", self.p.logs())

    def test_other_custom_prompt_disarms_stale_twin(self):
        self.p.collide(self.p.twinGO)
        self.p.collide(self.p.nornirGO)
        self.assertEqual(self.p.selectionState(), "none")
        self.assertIn("reason=confirmed_other_custom_prompt", self.p.logs())

    def test_custom_action_consumes_one_generation_once(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.assertEqual(self.p.selectionState(), "none")
        self.p.loseOwner()
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.customShows, 1)
        self.assertEqual(self.p.logs().count("SELECT_CONSUME"), 1)

    def test_prompt_unavailable_disarms(self):
        self.p.capture(self.p.twinGO)
        self.p.promptAvailable(False)
        self.p.prompt()
        self.assertEqual(self.p.selectionState(), "none")
        self.assertIn("reason=prompt_unavailable", self.p.logs())

    def test_each_map_teardown_disarms(self):
        for method in ("SubmenuExit", "Exit", "ClearIcons"):
            self.p.collide(self.p.twinGO)
            self.p.teardown(method)
            self.assertEqual(self.p.selectionState(), "none", method)

    def test_raven_collection_disarms_real_not_twin(self):
        self.p.collide(self.p.ravenGO)
        self.p.collected(True)
        self.p.update()
        self.assertEqual(self.p.selectionState(), "none")
        self.p.collide(self.p.twinGO)
        self.assertEqual(self.p.selectionState(), "armed-custom")

    def test_twin_after_real_completion_remains_routable(self):
        self.p.collected(True)
        self.p.collide(self.p.twinGO)
        self.advance(60)
        self.p.action()
        self.assertEqual(self.p.customId(), "3410085282531601808")

    def test_twin_to_stock_success_preserves_one_active_target(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.p.collide(self.p.stockGO)
        self.assertEqual(self.p.action(), "previous-show")
        self.assertIsNone(self.p.customId())
        self.assertEqual(self.p.stockId(), "native-stock-id")
        self.assertEqual(self.p.activeCount(), 1)

    def test_twin_to_stock_failed_hide_stays_fail_closed(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.p.collide(self.p.stockGO)
        self.p.failHide(True)
        self.p.action()
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.calls.previousShow, 0)
        self.assertEqual(self.p.activeCount(), 1)
        self.assertIn("STOCK_REPLACE_TWIN_REFUSED", self.p.logs())

    def test_stock_to_twin_uses_exact_custom_target(self):
        self.p.stock()
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.assertIsNone(self.p.stockId())
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.activeCount(), 1)

    def test_repeated_real_twin_switch_keeps_one_target(self):
        for go, uid in ((self.p.ravenGO, "-2207208259907848386"),
                        (self.p.twinGO, "3410085282531601808"),
                        (self.p.ravenGO, "-2207208259907848386"),
                        (self.p.twinGO, "3410085282531601808")):
            self.p.collide(go)
            self.p.action()
            self.assertEqual(self.p.customId(), uid)
            self.assertEqual(self.p.activeCount(), 1)

    def test_failed_custom_replacement_keeps_old_target(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.p.collide(self.p.ravenGO)
        self.p.failHide(True)
        self.p.action()
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.activeCount(), 1)

    def test_dock_native_behavior_unchanged(self):
        self.p.collide(self.p.stockGO)
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.previousShow, 1)
        self.assertIsNone(self.p.calls.shownClass)

    def test_exact_object_identity_and_no_selection_ttl(self):
        self.assertIn("collision == self.completionistSharedLoaderTwinGO", self.source)
        self.assertIn("collision == self.completionistMapV100MapIconGO", self.source)
        self.assertNotIn("selectionTTL", self.source)
        self.assertNotIn("ttl_expired", self.source)
        self.assertNotIn("GetName() ==", self.source)
        self.assertNotIn('kind == "DockPoint"', self.source)


if __name__ == "__main__":
    unittest.main()
