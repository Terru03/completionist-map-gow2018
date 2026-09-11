"""Lua 5.1 tests for v3.1 pending Raven selection identity."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "dist/re-tools"))
from lupa.lua51 import LuaRuntime

SOURCE = HERE / "raven-uid-compass-routing-v3.1.lua"

PRELUDE = r'''
local calls = {logs={}, previousShow=0, previousCollision=0, hidden={}}
local customIds, stockIds = {}, {}
local hideFailure=false
local ravenGO, twinGO, stockGO = {kind="raven"}, {kind="twin"}, {kind="stock"}
local self = {
  mapIconCollision=nil,
  completionistMapV100MapIconGO=ravenGO,
  completionistSharedLoaderTwinGO=twinGO,
  completionistMapV100Frame=0,
  currShownMarkerID=nil,
  currRealmName="Midgard",
  menu=nil,
}
print=function(s) calls.logs[#calls.logs+1]=s end

MapOn = {}
function MapOn.GetShowOnCompassPrompt(s, menu) return true, "previous-prompt" end
function MapOn.ShowOnCompass(s, state)
  calls.previousShow=calls.previousShow+1
  return "previous-show"
end
function MapOn.Update(s)
  s.completionistMapV100Frame=(s.completionistMapV100Frame or 0)+1
  return "previous-update"
end
function MapOn.MapCollisionChangeHandler(s, state, collisions, realm)
  calls.previousCollision=calls.previousCollision+1
  -- Runtime evidence: transient collision field can be gone before footer action.
  s.mapIconCollision=nil
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
return {
  self=self,calls=calls,ravenGO=ravenGO,twinGO=twinGO,stockGO=stockGO,
  collide=function(go)
    local list={}
    if go~=nil then list[1]=go end
    return MapOn.MapCollisionChangeHandler(self,{},list,"Midgard")
  end,
  collideBoth=function()
    return MapOn.MapCollisionChangeHandler(self,{}, {twinGO,ravenGO}, "Midgard")
  end,
  prompt=function() return MapOn.GetShowOnCompassPrompt(self,{}) end,
  action=function() return MapOn.ShowOnCompass(self,{}) end,
  update=function() return MapOn.Update(self) end,
  teardown=function(which) return MapOn[which](self,{}) end,
  pendingName=function()
    local p=self.completionistMapV104PendingRavenSelection
    return p and p.Name or nil
  end,
  pendingUid=function()
    local p=self.completionistMapV104PendingRavenSelection
    return p and p.IdString or nil
  end,
  customId=function() return customIds[1] end,
  stock=function() stockIds={"dock-id"}; self.currShownMarkerID="dock-id" end,
  stockId=function() return stockIds[1] end,
  failHide=function(v) hideFailure=v end,
  logs=function() return table.concat(calls.logs,"\n") end,
}
'''


class RavenUidV31RoutingTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.p = self.lua.execute(PRELUDE + self.source + POSTLUDE)

    def test_twin_collision_prompt_then_nil_field_routes_exact_custom_class(self):
        self.p.collide(self.p.twinGO)
        self.p.prompt()
        self.assertIsNone(self.p.self.mapIconCollision)
        self.p.action()
        self.assertEqual(self.p.calls.shownName, "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.assertEqual(self.p.calls.shownClass, "CompletionistRaven")
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.calls.previousShow, 0)

    def test_real_collision_prompt_then_nil_field_routes_exact_custom_class(self):
        self.p.collide(self.p.ravenGO)
        self.p.prompt()
        self.p.action()
        self.assertEqual(self.p.calls.shownName, "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.p.customId(), "-2207208259907848386")

    def test_stock_selection_invalidates_cached_twin_and_delegates_native(self):
        self.p.collide(self.p.twinGO)
        self.assertEqual(self.p.pendingName(), "Completionist_V104_Veithurgard_Raven_Twin_01")
        self.p.collide(self.p.stockGO)
        # Model disproven v3 assumption: transient field can remain stale too.
        self.p.self.mapIconCollision = self.p.twinGO
        self.assertIsNone(self.p.pendingName())
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.previousShow, 1)

    def test_different_custom_selection_replaces_pending_identity(self):
        self.p.collide(self.p.twinGO)
        self.p.collide(self.p.ravenGO)
        self.assertEqual(self.p.pendingName(), "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.p.pendingUid(), "-2207208259907848386")
        self.p.action()
        self.assertEqual(self.p.calls.shownName, "Completionist_V103_Veithurgard_Raven_01")

    def test_real_priority_matches_base_map_when_both_objects_collide(self):
        self.p.collideBoth()
        self.assertEqual(self.p.pendingName(), "Completionist_V103_Veithurgard_Raven_01")

    def test_each_map_teardown_invalidates_pending_identity(self):
        for method in ("SubmenuExit", "Exit", "ClearIcons"):
            self.p.collide(self.p.twinGO)
            self.p.teardown(method)
            self.assertIsNone(self.p.pendingName(), method)

    def test_action_consumes_pending_identity_once(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.assertIsNone(self.p.pendingName())
        self.p.self.mapIconCollision = None
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.previousShow, 1)

    def test_stale_custom_identity_cannot_replay_on_later_stock_action(self):
        self.p.collide(self.p.twinGO)
        self.p.collide(self.p.stockGO)
        self.p.stock()
        self.p.action()
        self.assertIsNone(self.p.calls.shownName)
        self.assertEqual(self.p.stockId(), "dock-id")
        self.assertEqual(self.p.calls.previousShow, 1)

    def test_exact_names_and_runtime_uid_strings_are_cached(self):
        self.p.collide(self.p.twinGO)
        self.assertEqual(self.p.pendingUid(), "3410085282531601808")
        self.p.collide(self.p.ravenGO)
        self.assertEqual(self.p.pendingName(), "Completionist_V103_Veithurgard_Raven_01")
        self.assertEqual(self.p.pendingUid(), "-2207208259907848386")

    def test_dock_action_stays_native(self):
        self.p.collide(self.p.stockGO)
        self.assertEqual(self.p.action(), "previous-show")
        self.assertEqual(self.p.calls.previousShow, 1)
        self.assertIsNone(self.p.calls.shownClass)

    def test_real_twin_switch_keeps_one_custom_target(self):
        for go, uid in ((self.p.ravenGO, "-2207208259907848386"),
                        (self.p.twinGO, "3410085282531601808"),
                        (self.p.ravenGO, "-2207208259907848386")):
            self.p.collide(go)
            self.p.action()
            self.assertEqual(self.p.customId(), uid)

    def test_failed_custom_hide_refuses_replace_and_keeps_one_target(self):
        self.p.collide(self.p.twinGO)
        self.p.action()
        self.p.collide(self.p.ravenGO)
        self.p.failHide(True)
        self.p.action()
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(self.p.calls.shownName, "Completionist_V104_Veithurgard_Raven_Twin_01")

    def test_failed_stock_hide_refuses_custom_show(self):
        self.p.stock()
        self.p.collide(self.p.twinGO)
        self.p.failHide(True)
        self.p.action()
        self.assertEqual(self.p.stockId(), "dock-id")
        self.assertIsNone(self.p.calls.shownName)

    def test_pending_identity_expires_after_bounded_frames(self):
        self.p.collide(self.p.twinGO)
        for _ in range(31):
            self.p.update()
        self.assertIsNone(self.p.pendingName())
        self.assertEqual(self.p.action(), "previous-show")

    def test_capture_uses_collision_table_not_resource_name(self):
        self.assertIn("MapOn.MapCollisionChangeHandler", self.source)
        self.assertNotIn("GetName() ==", self.source)
        self.assertNotIn('kind == "DockPoint"', self.source)


if __name__ == "__main__":
    unittest.main()
