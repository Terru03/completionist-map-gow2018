"""Gameplay hook integration. Execute production callback bodies with Lua 5.1."""
import os
from pathlib import Path
import unittest
from test_raven_uid_compass_routing_lua import PRELUDE, POSTLUDE, LuaRuntime, HERE

REL = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
ROOT = HERE.parents[1] / 'build/v0.10.4-raven-uid-compass-lifecycle-v3/source/game-root'
BRIDGE = HERE / 'raven-uid-compass-lifecycle-v3-events.lua'
GAME_STUB = r'''
local nativeCalls = {progress=0, saves=0, hitFinished=false}
local queue = {}
local position = {x=-64.850898742676,y=12.987384796143,z=787.30694580078}
local obj = {}
function obj:GetWorldPosition() return position end
function obj:FindLuaTableAttribute(key) return nil end
function obj:FindSingleGOByName(key) return nil end
function obj:FindSingleSoundEmitterByName(key) return {} end
function obj:GetName() return "raven" end
function obj:Hide() end
package.preload["design.LevelDesignLibrary"] = function() return {
  CallFunctionAfterDelay=function() end, PlayRestartableSoundLoop=function() end,
  StopRestartableSoundLoop=function() end, PlaySound=function() end,
  ExtractAndExecuteCallbacksForEvent=function() end,
  ActivateAndIncrementQuest=function() end,
} end
package.preload["level.timer"] = function() return {StartLevelTimer=function(period, callback) if period == 0.1 then queue[#queue+1]=callback end end} end
game.QuestManager = {
 GetQuestState=function() return "Active" end,
 IncrementQuestProgress=function() nativeCalls.progress=nativeCalls.progress+1 end,
 StartQuest=function() error("unexpected StartQuest") end,
}
game.SubObject={Sleep=function() end,SoftSave=function() nativeCalls.saves=nativeCalls.saves+1 end}
game.FX={Spawn=function() return {SetWorldPosition=function() end} end}
'''

class RavenLifecycleEventsTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get('COMPLETIONIST_RAVEN_ROOT', ROOT))
        source = (root/REL).read_text()
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        bridge = BRIDGE.read_text() if BRIDGE.exists() else ''
        self.p = self.lua.execute(PRELUDE + GAME_STUB + source + bridge +
            (HERE/'raven-uid-compass-routing.lua').read_text() + r'''
OnScriptLoaded(nil,obj)
OnStart(nil,obj)
local productionHit = OnHitByWeapon
_G.testHit=function() productionHit(nil,obj,nil,nil) end
_G.testRestore=function(killed) OnRestoreCheckpoint(nil,obj,{ravenKilled=killed}) end
_G.testOther=function() position.x=0 end
_G.testNative=nativeCalls
_G.testTick=function() local batch=queue; queue={}; for _,fn in ipairs(batch) do fn() end end
_G.testQueue=function() return #queue end
''' + POSTLUDE)

    def test_closed_map_real_hit_clears_compass_after_native_state(self):
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.lua.globals().testHit()
        self.assertIsNone(self.p.customId())
        self.assertIsNone(self.p.trackedName())
        self.assertEqual(self.lua.globals().testNative.progress, 3)
        self.assertIn('reason=OnHitByWeapon', self.p.logs())

    def test_twin_hit_survives_and_remains_selectable(self):
        self.p.action()
        self.lua.globals().testHit()
        self.assertEqual(self.p.customId(), 'twin-id')
        self.assertEqual(len(self.p.calls.hidden), 0)
        self.assertEqual(self.p.self.currShownMarkerID, 'twin-id')
        self.assertIn('remove', self.p.prompt()[1])

    def test_restore_rearms_second_natural_hit(self):
        for _ in range(2):
            self.lua.globals().testRestore(False)
            self.p.self.mapIconCollision = self.p.ravenGO
            self.p.action()
            self.assertEqual(self.p.customId(), 'raven-id')
            self.lua.globals().testHit()
            self.assertIsNone(self.p.customId())
        self.assertEqual(len(self.p.calls.hidden), 2)
        self.assertEqual(self.lua.globals().testNative.progress, 6)

    def test_other_raven_does_not_notify_target_observer(self):
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.lua.globals().testOther()
        self.lua.globals().testHit()
        self.assertEqual(self.p.customId(), 'raven-id')

    def test_observer_failure_does_not_break_native_hit(self):
        self.lua.execute('CompletionistMapV104ObserveRavenCompletion=function() error("observer fail") end')
        self.lua.globals().testHit()
        self.assertEqual(self.lua.globals().testNative.progress, 3)
        self.assertIn('OBSERVER_FAILED', self.p.logs())


    def test_failed_hide_retried_while_map_closed(self):
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.p.failHide(True)
        self.lua.globals().testHit()
        self.assertEqual(self.lua.globals().testQueue(), 1)
        self.p.failHide(False)
        self.lua.globals().testTick()
        self.assertIsNone(self.p.customId())
        self.lua.globals().testTick()
        self.assertEqual(self.lua.globals().testQueue(), 0)

    def test_restore_cancels_queued_completion_check(self):
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.lua.globals().testHit()
        self.lua.globals().testRestore(False)
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.lua.globals().testTick()
        self.assertEqual(self.p.customId(), 'raven-id')
        self.assertEqual(self.lua.globals().testQueue(), 0)

    def test_retry_budget_is_bounded_and_logs_unsettled(self):
        self.lua.execute('CompletionistMapV104ObserveRavenCompletion=function() error("observer fail") end')
        self.lua.globals().testHit()
        for _ in range(20):
            self.lua.globals().testTick()
        self.assertEqual(self.lua.globals().testQueue(), 0)
        self.assertIn('CLEANUP_UNSETTLED attempts=20', self.p.logs())

    def test_pending_show_cancelled_by_real_gameplay_hit(self):
        self.p.delay()
        self.p.self.mapIconCollision = self.p.ravenGO
        self.p.action()
        self.lua.globals().testHit()
        self.p.flush()
        self.assertIsNone(self.p.customId())
        self.lua.globals().testTick()
        self.assertEqual(self.lua.globals().testQueue(), 0)

if __name__ == '__main__':
    unittest.main()
