"""Run probes with stock lexical fields; callbacks keep stock contract."""
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parents[2] / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime, LuaError
from lupa.lua52 import LuaRuntime as Lua52Runtime, LuaError as Lua52Error
import collectible_completion_adapters as adapters

class ProbeTest(unittest.TestCase):
    runtime = LuaRuntime
    lua_error = LuaError
    def load(self, adapter, setup=""):
        lua=self.runtime(unpack_returned_tuples=True)
        lua.execute('''
          -- The game's restricted Lua VM omits environment introspection.
          getfenv, setfenv = nil, nil
          package.preload["design.LevelDesignLibrary"]=function() return {} end
          package.preload["level.timer"]=function() return {} end
          package.preload["level.MonitorLibrary"]=function() return {} end
          package.preload["ui.mpicon"]=function() return {} end
          package.preload["ai.coroutines"]=function() return {} end
          resource,quest=false,"Active"
          game={Wallets={HasResource=function() return resource end},
                QuestManager={GetQuestState=function() return quest end}}
          engine={GetUIWad=function() return {} end,SendHook=function() end}
        ''')
        source=(adapters.STOCK / adapters.PREFIX / adapters.SCRIPTS[adapter][0]).read_text(encoding="utf-8-sig")
        lua.execute(source + "\n" + setup + "\n" + adapters.render_probe(adapter))
        return lua
    def test_stock_restore_terminal_and_malformed_states(self):
        for adapter,field,remaining,terminal in (("chest","state",3,4),
                ("artefact","state",2,3),("lore","mapSummaryComplete",False,True),
                ("pickup","collected",False,True),("rift","hasOpened",False,True)):
            with self.subTest(adapter=adapter):
                lua=self.load(adapter)
                g=lua.globals()
                for value,want in ((remaining,"remaining"),(terminal,"collected"),("true",None)):
                    g.OnRestoreCheckpoint(None,None,lua.table_from({field:value}))
                    got=g.CompletionistCollectibleObserve()
                    self.assertEqual(got,None if want is None else (adapter,want))
    def test_shrine_started_without_reward_stays_visible(self):
        lua=self.load("shrine", 'triptychCompleted=true; journalUpdateID="Tryptich_Test"')
        g=lua.globals()
        self.assertEqual(g.CompletionistCollectibleObserve(),("shrine","remaining"))
        g.resource=True
        self.assertEqual(g.CompletionistCollectibleObserve(),("shrine","collected"))
    def test_dig_started_without_quest_reward_stays_visible(self):
        lua=self.load("dig", 'state=3; questName="Quest_Test"')
        g=lua.globals()
        self.assertEqual(g.CompletionistCollectibleObserve(),("dig","remaining"))
        g.quest="Complete"
        self.assertEqual(g.CompletionistCollectibleObserve(),("dig","collected"))
    def test_rift_combat_finish_without_loot_stays_visible(self):
        lua=self.load("rift", 'lootInProgress=false')
        lua.globals().OnInteractFinish(None,None,None)
        self.assertEqual(lua.globals().CompletionistCollectibleObserve(),("rift","remaining"))
    def test_wrappers_preserve_nil_returns_args_and_original_errors(self):
        lua=self.load("chest", '''
          thisLevel={Name="Test"}
          function OnOpened(...) return select("#",...), ... end
          function OnStart() error("stock failed") end
          engine.SendHook=function() error("notify failed") end
        ''')
        self.assertEqual(lua.globals().OnOpened("a",None,"c",None),(4,"a",None,"c",None))
        with self.assertRaisesRegex(self.lua_error,"stock failed"):
            lua.globals().OnStart()

class Lua52ProbeTest(ProbeTest):
    runtime = Lua52Runtime
    lua_error = Lua52Error

if __name__ == "__main__": unittest.main()
