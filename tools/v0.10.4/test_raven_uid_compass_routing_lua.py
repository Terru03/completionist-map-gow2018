"""Lua 5.1 regression tests for UID-aware Raven compass routing scope."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "dist/re-tools"))
from lupa.lua51 import LuaRuntime

PRELUDE = r'''
local calls = {logs={}, previousShow=0, shownName=nil, shownClass=nil, hidden={}}
local customIds = {}
local stockIds = {}
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
  customIds = {info.Id}
end
function game.Compass.HideMarker(target)
  calls.hidden[#calls.hidden+1] = tostring(target)
  if tostring(target) == "raven-id" or tostring(target) == "Completionist_V103_Veithurgard_Raven_01" then
    if customIds[1] == "raven-id" then customIds = {} end
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
UI = {}
Audio = {PlaySound=function(name) calls.lastSound=name end}
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
  selectedName=function()
    local s=self.completionistMapV104SelectedRavenIdentity
    return s and s.Name or nil
  end,
  selectedId=function()
    local s=self.completionistMapV104SelectedRavenIdentity
    return s and s.IdString or nil
  end,
  customId=function() return customIds[1] end,
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

    def test_no_maprecordview_dependency_and_module_loads(self):
        self.assertNotIn("MapRecordView", self.source)
        self.assertTrue(self.lua.globals().CompletionistMapV104UidAwareRavenCompassRouting)
        self.assertIn("identitySource=MapOn.mapIconCollision_exact_object_reference", self.probe.logs())

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
        self.assertIn("source=raven_object_reference", self.probe.logs())


if __name__ == "__main__":
    unittest.main()
