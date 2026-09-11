"""Lua 5.1 gameplay-only tests for v3.1 Raven completion cleanup."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "dist/re-tools"))
from lupa.lua51 import LuaRuntime

PRODUCTION = REPO / "build/v0.10.4-raven-uid-compass-lifecycle-v3/source/game-root/mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"
EVENTS = HERE / "raven-uid-compass-lifecycle-v3.1-events.lua"

PRELUDE = r'''
local calls={logs={},hidden={},progress=0,saves=0}
local customIds, stockIds, queue = {}, {}, {}
local delayedReal=false
local hideFailure=false
local position={x=-64.850898742676,y=12.987384796143,z=787.30694580078}
local obj={}
function obj:GetWorldPosition() return position end
function obj:FindLuaTableAttribute() return nil end
function obj:FindSingleGOByName() return nil end
function obj:FindSingleSoundEmitterByName() return {} end
function obj:GetName() return "raven" end
function obj:Hide() end
print=function(s) calls.logs[#calls.logs+1]=s end
package.preload["design.LevelDesignLibrary"]=function() return {
  CallFunctionAfterDelay=function() end,PlayRestartableSoundLoop=function() end,
  StopRestartableSoundLoop=function() end,PlaySound=function() end,
  ExtractAndExecuteCallbacksForEvent=function() end,ActivateAndIncrementQuest=function() end,
} end
package.preload["level.timer"]=function() return {StartLevelTimer=function(period,fn)
  if period==0.1 then queue[#queue+1]=fn end
end} end
game={Map={},Compass={},QuestManager={},SubObject={},FX={}}
function game.Map.GetMarkerInfo(name)
  if name=="Completionist_V103_Veithurgard_Raven_01" then
    return {Id="-2207208259907848386"}
  elseif name=="Completionist_V104_Veithurgard_Raven_Twin_01" then
    return {Id="3410085282531601808"}
  end
end
function game.Compass.FindMarkersByIconClass(classes) return customIds end
function game.Compass.HideMarker(target)
  if hideFailure then error("hide failed") end
  calls.hidden[#calls.hidden+1]=tostring(target)
  if tostring(target)=="Completionist_V103_Veithurgard_Raven_01" and customIds[1]=="-2207208259907848386" then
    customIds={}
  end
end
function game.QuestManager.GetQuestState() return "Active" end
function game.QuestManager.IncrementQuestProgress() calls.progress=calls.progress+1 end
function game.QuestManager.StartQuest() error("unexpected StartQuest") end
game.SubObject.Sleep=function() end
game.SubObject.SoftSave=function() calls.saves=calls.saves+1 end
game.FX.Spawn=function() return {SetWorldPosition=function() end} end
'''

POSTLUDE = r'''
OnScriptLoaded(nil,obj)
OnStart(nil,obj)
local productionHit=OnHitByWeapon
return {
  calls=calls,
  hit=function() return productionHit(nil,obj,nil,nil) end,
  restore=function(killed) return OnRestoreCheckpoint(nil,obj,{ravenKilled=killed}) end,
  start=function() return OnStart(nil,obj) end,
  real=function() customIds={"-2207208259907848386"} end,
  twin=function() customIds={"3410085282531601808"} end,
  stock=function() stockIds={"dock-id"} end,
  none=function() customIds={} end,
  queueReal=function() delayedReal=true end,
  settleReal=function() if delayedReal then customIds={"-2207208259907848386"}; delayedReal=false end end,
  customId=function() return customIds[1] end,
  stockId=function() return stockIds[1] end,
  failHide=function(v) hideFailure=v end,
  tick=function() local batch=queue;queue={};for _,fn in ipairs(batch) do fn() end end,
  queueCount=function() return #queue end,
  logs=function() return table.concat(calls.logs,"\n") end,
}
'''


class RavenGameplayV31EventsTests(unittest.TestCase):
    def setUp(self):
        self.source = EVENTS.read_text(encoding="utf-8")
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.p = lua.execute(PRELUDE + PRODUCTION.read_text(encoding="utf-8") + self.source + POSTLUDE)

    def drain(self, limit=30):
        for _ in range(limit):
            if self.p.queueCount() == 0:
                break
            self.p.tick()

    def test_map_closed_real_active_hit_hides_exact_real_without_mapmenu_observer(self):
        self.p.real()
        self.p.hit()
        self.assertIsNone(self.p.customId())
        self.assertEqual(list(self.p.calls.hidden.values()), ["Completionist_V103_Veithurgard_Raven_01"])
        self.assertEqual(self.p.calls.progress, 3)

    def test_map_open_real_active_uses_same_gameplay_cleanup(self):
        self.p.real()
        self.p.hit()
        self.assertIsNone(self.p.customId())

    def test_twin_active_real_completion_leaves_twin_untouched(self):
        self.p.twin()
        self.p.hit()
        self.assertEqual(self.p.customId(), "3410085282531601808")
        self.assertEqual(len(self.p.calls.hidden), 0)

    def test_stock_active_real_completion_leaves_stock_untouched(self):
        self.p.stock()
        self.p.hit()
        self.assertEqual(self.p.stockId(), "dock-id")
        self.assertEqual(len(self.p.calls.hidden), 0)

    def test_no_active_target_causes_no_compass_mutation(self):
        self.p.none()
        self.p.hit()
        self.drain()
        self.assertEqual(len(self.p.calls.hidden), 0)

    def test_queued_real_show_is_neutralized_by_bounded_event_ticket(self):
        self.p.queueReal()
        self.p.hit()
        self.p.settleReal()
        self.p.tick()
        self.assertIsNone(self.p.customId())
        self.assertEqual(len(self.p.calls.hidden), 1)
        self.drain()
        self.assertEqual(self.p.queueCount(), 0)

    def test_failed_real_hide_gets_bounded_retry(self):
        self.p.real()
        self.p.failHide(True)
        self.p.hit()
        self.assertEqual(self.p.customId(), "-2207208259907848386")
        self.assertEqual(self.p.queueCount(), 1)
        self.p.failHide(False)
        self.p.tick()
        self.assertIsNone(self.p.customId())
        self.drain()
        self.assertEqual(self.p.queueCount(), 0)

    def test_repeated_true_does_not_repeat_cleanup(self):
        self.p.real()
        self.p.hit()
        self.p.start()
        self.p.start()
        self.drain()
        self.assertEqual(len(self.p.calls.hidden), 1)

    def test_true_false_restore_rearms_next_collection(self):
        for _ in range(2):
            self.p.real()
            self.p.hit()
            self.assertIsNone(self.p.customId())
            self.p.restore(False)
        self.assertEqual(len(self.p.calls.hidden), 2)

    def test_restore_false_cancels_stale_cleanup_ticket(self):
        self.p.none()
        self.p.hit()
        self.assertEqual(self.p.queueCount(), 1)
        self.p.restore(False)
        self.p.real()
        self.p.tick()
        self.assertEqual(self.p.customId(), "-2207208259907848386")
        self.assertEqual(self.p.queueCount(), 0)

    def test_start_after_false_restore_keeps_stale_ticket_cancelled(self):
        self.p.none()
        self.p.hit()
        self.p.restore(False)
        self.p.start()
        self.p.real()
        self.p.tick()
        self.assertEqual(self.p.customId(), "-2207208259907848386")

    def test_cleanup_has_no_mapmenu_global_dependency_or_poll_loop(self):
        for token in ("CompletionistMapV104ObserveRavenCompletion",
                      "CompletionistMapV104UidRavenTrackedName",
                      "mapIconCollision", "MapOn.Update", "util.create_thread"):
            self.assertNotIn(token, self.source)
        self.assertIn('FindMarkersByIconClass({ravenClass})', self.source)
        self.assertIn('game.Compass.HideMarker(ravenName)', self.source)


if __name__ == "__main__":
    unittest.main()
