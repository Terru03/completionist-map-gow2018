"""Lua 5.1 regression tests for UID-aware Raven compass routing scope."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "dist/re-tools"))
from lupa.lua51 import LuaRuntime

PRELUDE = r'''
local calls = {logs={}, previousShow=0, shownName=nil, shownClass=nil, hidden={}, thread=nil}
local customIds = {}
local stockIds = {}
local delayedShow = nil
local delayShow = false
local hideFailure = false
local ravenCollected = false
local ravenGO = {kind="raven"}
local twinGO = {kind="twin"}
local stockGO = {kind="stock"}
local self = {
  mapIconCollision=twinGO,
  completionistMapV100MapIconGO=ravenGO,
  completionistSharedLoaderTwinGO=twinGO,
  currShownMarkerID=nil,
  menu=nil,
}

local function log(text) calls.logs[#calls.logs+1] = text end
print = log

MapOn = {}
function MapOn.GetShowOnCompassPrompt(s, menu)
  return true, "previous-prompt"
end
function MapOn.ShowOnCompass(s, state)
  calls.previousShow = calls.previousShow + 1
  return "previous-show"
end
function MapOn.Update(s, ...)
  return "previous-update"
end

local markerInfo = {
  Completionist_V103_Veithurgard_Raven_01 = {Id="raven-id", X=1, Y=2, Z=3},
  Completionist_V104_Veithurgard_Raven_Twin_01 = {Id="twin-id", X=4, Y=5, Z=6},
}

game = {Map={}, Compass={}}
function game.Map.GetMarkerInfo(name)
  return markerInfo[name]
end
function game.Compass.FindMarkersByIconClass(classes)
  if classes ~= nil and classes[1] == "CompletionistRaven" then
    return customIds
  end
  return stockIds
end
function game.Compass.ShowMarker(name, class)
  calls.shownName = name
  calls.shownClass = class
  local info = markerInfo[name]
  assert(info ~= nil, "unknown marker")
  if delayShow then delayedShow=info.Id else customIds = {info.Id} end
end
function game.Compass.HideMarker(target)
  if hideFailure then error("hide failed") end
  calls.hidden[#calls.hidden+1] = tostring(target)
  if tostring(target) == "raven-id" or tostring(target) == "Completionist_V103_Veithurgard_Raven_01" then
    if customIds[1] == "raven-id" then customIds = {} end
    if delayedShow == "raven-id" then delayedShow=nil end
  elseif tostring(target) == "twin-id" or tostring(target) == "Completionist_V104_Veithurgard_Raven_Twin_01" then
    if customIds[1] == "twin-id" then customIds = {} end
  else
    stockIds = {}
  end
end

enabledShowOnCompassMarkerFlags = {"DockPoint"}
lamsConsts = {
  RemoveFromCompass="remove",
  ReplaceInCompass="replace",
  AddToCompass="add",
}
util = {}
function util.GetLAMSMsg(id) return id end
function util.GetUiObjByName(name) return nil end
function util.create_thread(fn) calls.thread = fn end
function util.yield(seconds) calls.lastYield = seconds end
UI = {}
Audio = {PlaySound=function(name) calls.lastSound=name end}
local CompletionistMapV100_IsRavenCollected = function() return ravenCollected end
_G.CompletionistMapV100TargetRavenKilled = false
'''

POSTLUDE = r'''
return {
  self=self,
  calls=calls,
  ravenGO=ravenGO,
  twinGO=twinGO,
  stockGO=stockGO,
  prompt=function() return MapOn.GetShowOnCompassPrompt(self,{}) end,
  action=function() return MapOn.ShowOnCompass(self,{}) end,
  update=function() return MapOn.Update(self) end,
  setCollected=function(value) ravenCollected=value; _G.CompletionistMapV100TargetRavenKilled=value end,
  observe=function(reason) local observed = _G.CompletionistMapV104ObserveRavenCompletion(reason or "test"); return observed end,
  selectedName=function()
    local s=self.completionistMapV104SelectedRavenIdentity
    return s and s.Name or nil
  end,
  selectedId=function()
    local s=self.completionistMapV104SelectedRavenIdentity
    return s and s.IdString or nil
  end,
  customId=function() return customIds[1] end,
  stock=function() stockIds={"dock-id"}; self.currShownMarkerID="dock-id" end,
  delay=function() delayShow=true end,
  flush=function() if delayedShow then customIds={delayedShow}; delayedShow=nil end end,
  failHide=function(value) hideFailure=value end,
  stockId=function() return stockIds[1] end,
  trackedName=function() return _G.CompletionistMapV104UidRavenTrackedName end,
  logs=function() return table.concat(calls.logs,"\n") end,
}
'''


class RavenUidRoutingLuaTests(unittest.TestCase):
    def setUp(self):
        self.source = (HERE / "raven-uid-compass-routing.lua").read_text(encoding="utf-8")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        # Deliberately provide MapOn but no MapRecordView global. This matches the
        # runtime scope that exposed the original load-time failure.
        self.probe = self.lua.execute(PRELUDE + self.source + POSTLUDE)

    def test_no_maprecordview_dereference_and_module_loads(self):
        self.assertNotIn("MapRecordView.", self.source)
        self.assertNotIn("function MapRecordView:", self.source)
        self.assertTrue(self.lua.globals().CompletionistMapV104UidAwareRavenCompassRouting)
        self.assertIn("identitySource=MapOn.mapIconCollision_exact_object_reference", self.probe.logs())
        self.assertIsNone(self.probe.calls.thread)

    def test_twin_selection_routes_by_exact_object_reference(self):
        show, text = self.probe.prompt()
        self.assertTrue(show)
        self.assertIn("add", text)
        self.assertEqual(self.probe.selectedName(), "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.assertEqual(self.probe.selectedId(), "twin-id")
        self.assertIn("source=twin_object_reference", self.probe.logs())

    def test_action_survives_nil_collision_after_prompt_and_routes_twin(self):
        self.probe.prompt()
        self.probe.self.mapIconCollision = None
        self.probe.action()
        self.assertEqual(self.probe.calls.shownName, "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.assertEqual(self.probe.calls.shownClass, "CompletionistRaven")
        self.assertEqual(self.probe.customId(), "twin-id")
        self.assertEqual(self.probe.calls.previousShow, 0)

    def test_noncustom_collision_clears_custom_selection_and_delegates(self):
        self.probe.prompt()
        self.assertIsNotNone(self.probe.selectedName())
        self.probe.self.mapIconCollision = self.probe.stockGO
        self.probe.prompt()
        self.assertIsNone(self.probe.selectedName())
        result = self.probe.action()
        self.assertEqual(result, "previous-show")
        self.assertEqual(self.probe.calls.previousShow, 1)
        self.assertIn("SELECT_CLEAR", self.probe.logs())

    def test_original_raven_routes_separately(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.prompt()
        self.probe.action()
        self.assertEqual(self.probe.calls.shownName, "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.probe.customId(), "raven-id")
        self.assertEqual(self.probe.trackedName(), "Completionist_V103_Veithurgard_Raven_01")
        self.assertIn("source=raven_object_reference", self.probe.logs())

    def test_original_completion_clears_active_original_without_progression_write(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.prompt()
        self.probe.action()
        self.assertEqual(self.probe.customId(), "raven-id")
        self.probe.setCollected(True)
        self.assertTrue(self.probe.observe("test_completion"))
        self.assertIsNone(self.probe.customId())
        self.assertIsNone(self.probe.selectedName())
        self.assertIsNone(self.probe.trackedName())
        self.assertIn("LIFECYCLE_CLEAR", self.probe.logs())
        self.assertIn("twinTouched=false progressionWrites=false", self.probe.logs())

    def test_original_completion_does_not_clear_active_twin(self):
        self.probe.prompt()
        self.probe.action()
        self.assertEqual(self.probe.customId(), "twin-id")
        self.assertEqual(self.probe.trackedName(), "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.probe.setCollected(True)
        self.assertTrue(self.probe.observe("test_completion_with_twin"))
        self.assertEqual(self.probe.customId(), "twin-id")
        self.assertEqual(self.probe.trackedName(), "Completionist_V104_Veithurgard_Raven_Twin_01")

    def test_collected_original_is_not_reselected(self):
        self.probe.setCollected(True)
        self.probe.self.mapIconCollision = self.probe.ravenGO
        show, text = self.probe.prompt()
        self.assertFalse(show)
        self.assertIsNone(self.probe.selectedName())


    def test_closed_map_completion_uses_gameplay_callback(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.action()
        self.probe.setCollected(True)
        self.lua.globals().CompletionistMapV104ObserveRavenCompletion("OnHitByWeapon", True)
        self.assertIsNone(self.probe.customId())
        self.assertIsNone(self.probe.self.currShownMarkerID)

    def test_open_map_completion(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.action()
        self.probe.setCollected(True)
        self.probe.update()
        self.assertIsNone(self.probe.customId())

    def test_rearm_after_earlier_save_and_cleanup_once(self):
        for _ in range(2):
            self.probe.setCollected(False)
            self.probe.observe("OnRestoreCheckpoint")
            self.probe.self.mapIconCollision = self.probe.ravenGO
            self.probe.action()
            self.probe.setCollected(True)
            before = len(self.probe.calls.hidden)
            self.probe.observe("OnHitByWeapon")
            self.assertEqual(len(self.probe.calls.hidden), before + 1)
            self.probe.observe("repeat")
            self.assertEqual(len(self.probe.calls.hidden), before + 1)
            self.assertIsNone(self.probe.customId())

    def test_nil_collision_cannot_reuse_collected_real_selection(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.prompt()
        self.probe.self.mapIconCollision = None
        self.probe.setCollected(True)
        self.probe.action()
        self.assertIsNone(self.probe.calls.shownName)

    def test_no_target_completion_has_no_compass_mutation(self):
        self.probe.setCollected(True)
        self.probe.observe()
        self.assertEqual(len(self.probe.calls.hidden), 0)
        self.assertIsNone(self.probe.calls.shownName)


    def test_pending_real_show_is_cancelled_on_completion(self):
        self.probe.delay()
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.action()
        self.assertIsNone(self.probe.customId())
        self.probe.setCollected(True)
        self.probe.observe()
        self.probe.flush()
        self.assertIsNone(self.probe.customId())
        self.assertEqual(len(self.probe.calls.hidden), 1)

    def test_stock_dock_completion_does_not_mutate_native_target(self):
        self.probe.stock()
        self.probe.setCollected(True)
        self.probe.observe()
        self.assertEqual(self.probe.stockId(), "dock-id")
        self.assertEqual(self.probe.self.currShownMarkerID, "dock-id")
        self.assertEqual(len(self.probe.calls.hidden), 0)

    def test_failed_hide_can_retry_without_new_collection(self):
        self.probe.self.mapIconCollision = self.probe.ravenGO
        self.probe.action()
        self.probe.setCollected(True)
        self.probe.failHide(True)
        self.probe.observe()
        self.probe.failHide(False)
        self.probe.observe()
        self.assertIsNone(self.probe.customId())

    def test_stock_to_twin_and_back_preserves_native_dispatch(self):
        self.probe.stock()
        self.probe.action()
        self.assertIsNone(self.probe.stockId())
        self.assertEqual(self.probe.customId(), "twin-id")
        self.probe.self.mapIconCollision = self.probe.stockGO
        self.probe.action()
        self.assertIsNone(self.probe.customId())
        self.assertEqual(self.probe.calls.previousShow, 1)

    def test_real_twin_real_one_target(self):
        for go, uid in ((self.probe.ravenGO, "raven-id"), (self.probe.twinGO, "twin-id"), (self.probe.ravenGO, "raven-id")):
            self.probe.self.mapIconCollision = go
            self.probe.action()
            self.assertEqual(self.probe.customId(), uid)

if __name__ == "__main__":
    unittest.main()
