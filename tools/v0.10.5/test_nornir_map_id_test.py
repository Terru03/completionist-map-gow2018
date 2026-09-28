"""Exercise separate map IDs and locked-chest child reveal in Lua 5.1."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime

spec = importlib.util.spec_from_file_location("nornir_map_id_builder", HERE / "build-nornir-map-id-test.py")
builder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(builder)


class NornirMapIdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs, cls.report = builder.build()
        cls.definitions = builder.rows()

    def test_deterministic_raven_preserving_build(self):
        again, second = builder.build()
        self.assertEqual(self.outputs, again)
        self.assertEqual(self.report["files"], second["files"])
        self.assertEqual(self.report["new_marker_count"], 88)
        for proof in self.report["proof"].values():
            self.assertTrue(proof.get("exact_inverse", True))
        self.assertTrue(self.report["proof"][builder.MAP_LUA]["raven_lua_exact_prefix"])

    def test_lua_compiles(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        for path in (builder.MAP_LUA, builder.RUNIC_LUA, builder.STANDARD_LUA):
            lua.globals().source = self.outputs[path].decode("utf-8")
            lua.execute("assert(loadstring(source))")

    def test_map_chests_first_then_only_attempted_children(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('''
          hooks = {}
          package.preload["core.thunk"] = function()
            return {Install=function(name, fn) hooks[name]=fn end}
          end
          markerIds = {}
          Map = {
            FindRegionFromMarker=function(id) return true, 1 end,
            CreateMarkerIcon=function(id)
              local icon={id=id, visible=false}
              function icon:Show() self.visible=true end
              function icon:Hide() self.visible=false end
              return icon
            end,
            RecycleIcon=function(icon) icon.visible=false end
          }
          game = {Map={GetMarkerInfo=function(name)
            return markerIds[name] and {Id=markerIds[name]} or nil
          end}}
          MapOn = {
            Menu_Next_Filter=function() end,
            UpdateFilterButtonMapping=function() end,
            SubmenuExit=function() end, Exit=function() end,
            ClearIcons=function() end,
            MapCollisionChangeHandler=function() end,
            GetShowOnCompassPrompt=function() return true,"stock" end,
            ShowOnCompass=function() return true end
          }
          CompletionistMapV100_CreateMapPin=function() end
          function countIcons(map)
            local count=0
            for _, icon in pairs(map.completionistMapV105NornirIdTestIcons or {}) do
              if icon.visible then count=count+1 end
            end
            return count
          end
        ''')
        for row in self.definitions:
            uid = int(row["marker"]["uid"], 16)
            signed = uid if uid < 1 << 63 else uid - (1 << 64)
            lua.globals().markerIds[row["marker"]["name"]] = str(signed)
        source = self.outputs[builder.MAP_LUA].decode("utf-8")
        layer = source[source.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR ID TEST"):]
        lua.execute(layer)
        map_ui = lua.table_from({"currRealmName": "Midgard", "filterIndex": 1,
                                 "filterButtonMapping": lua.table_from([1, -101, -102]),
                                 "ravenIcons": lua.table_from(["raven-1", "raven-2"])})
        lua.globals().CompletionistMapV100_CreateMapPin(map_ui)
        count = lua.globals().countIcons
        self.assertEqual(count(map_ui), 17)
        self.assertEqual(len(map_ui.ravenIcons), 2)

        parent = next(row for row in self.definitions if row["catalogue_id"] ==
                      "nornir_chest_c190d59340706bb79925cb9f2d5867cf")
        siblings = [row for row in self.definitions if row["progression"].get("parent_catalogue_id") ==
                    parent["catalogue_id"]]
        refs = sorted(row["native"]["reference_name"].lower() for row in siblings)
        key = parent["marker"]["coordinate_wad"].lower() + "|" + "|".join(refs)
        event = lua.globals().hooks["COMPLETIONIST_NORNIR_EVENT_V1"]
        event("NORNIR_V1\tattempt\tother_wad|bad|refs\t")
        self.assertEqual(count(map_ui), 17)
        event("NORNIR_V1\tattempt\t" + key + "\t")
        self.assertEqual(count(map_ui), 20)
        event("NORNIR_V1\tseal\t" + key + "\t" + refs[0])
        self.assertEqual(count(map_ui), 19)
        map_ui.filterIndex = 3
        lua.globals().MapOn.Menu_Next_Filter(map_ui)
        self.assertEqual(count(map_ui), 0)
        map_ui.filterIndex = 1
        lua.globals().MapOn.Menu_Next_Filter(map_ui)
        self.assertEqual(count(map_ui), 19)
        event("NORNIR_V1\topened\t" + key + "\t")
        self.assertEqual(count(map_ui), 16)
        self.assertEqual(len(map_ui.ravenIcons), 2)
        lua.globals().hooks["EVT_LoadSaveData"]()
        self.assertEqual(count(map_ui), 17)

    def test_runic_hook_requires_locked_use_and_restores_attempt(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        stock = self.outputs[builder.RUNIC_LUA].decode("utf-8")
        snippet = stock[stock.index("-- Observe stock runic chest."):]
        lua.execute('''
          sent={}
          engine={GetUIWad=function() return "ui" end,
                  SendHook=function(name, wad, payload) sent[#sent+1]=payload end}
          local thisLevel={Name="WAD_xpl200_funeral"}
          local refs={sealBreakable01="RunicLock01",sealBreakable02="RunicLock02",
                      sealBreakable03="RunicLock03"}
          local thisObj={FindLuaTableAttribute=function(_, name) return refs[name] end}
          local canUse=false
          local frontInteractZone={PlayerCanInteract=function() return canUse end}
          local interactAvailable=true
          local challengeComplete=false
          local state=nil
          local states={LOCKED=3,OPENED=4}
          local keyType="Breakable"
          local keysUsed=0
          local runeTable={}
          function PerformKratosInteraction_Locked() state=states.LOCKED end
          function OnUseWorld()
            if frontInteractZone:PlayerCanInteract() then
              PerformKratosInteraction_Locked()
            end
          end
          function OnKeyBroken() end
          function OnInteractFinish() state=4 end
          function OnSaveCheckpoint() return {} end
          function OnRestoreCheckpoint() end
          function OnStart() end
        ''' + snippet + '''
          testCanUse=function(value) canUse=value end
          testSetChallenge=function(value) challengeComplete=value end
          testSetState=function(value) state=value end
        ''')
        g = lua.globals()
        g.OnUseWorld()
        self.assertEqual(len(g.sent), 0)
        g.testCanUse(True)
        g.testSetChallenge(True)
        g.OnUseWorld()
        self.assertEqual(len(g.sent), 0)
        g.testSetChallenge(False)
        g.OnUseWorld()
        self.assertEqual(len(g.sent), 1)
        self.assertIn("NORNIR_V1\tattempt\twad_xpl200_funeral|runiclock01|runiclock02|runiclock03", g.sent[1])
        self.assertTrue(g.OnSaveCheckpoint().completionistPuzzleAttempted)
        g.OnRestoreCheckpoint(None, None, lua.table_from({"completionistPuzzleAttempted": True}))
        g.OnStart()
        self.assertEqual(len(g.sent), 2)
        g.OnInteractFinish()
        self.assertIn("NORNIR_V1\topened\t", g.sent[3])

    def test_reward_open_event_uses_same_chest_key(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        stock = self.outputs[builder.STANDARD_LUA].decode("utf-8")
        snippet = stock[stock.index("-- Observe reward chest opening."):]
        lua.execute('''
          sent={}
          engine={GetUIWad=function() return "ui" end,
                  SendHook=function(name, wad, payload) sent[#sent+1]=payload end}
          local thisLevel={Name="WAD_xpl200_funeral"}
          local refs={sealBreakable01="RunicLock01",sealBreakable02="RunicLock02",
                      sealBreakable03="RunicLock03"}
          local parentObj={FindLuaTableAttribute=function(_, name) return refs[name] end}
          local chestType="Runic_Axe"
          local states={OPENED=4,DISABLED=2}
          local state=1
          function OnOpened() state=states.OPENED end
          function OnStart()
            if state==states.OPENED then state=states.DISABLED end
          end
        ''' + snippet + '''
          testSetState=function(value) state=value end
        ''')
        g = lua.globals()
        g.OnOpened()
        self.assertEqual(len(g.sent), 1)
        self.assertIn("NORNIR_V1\topened\twad_xpl200_funeral|runiclock01|runiclock02|runiclock03", g.sent[1])
        g.testSetState(4)
        g.OnStart()
        self.assertEqual(len(g.sent), 2)


if __name__ == "__main__":
    unittest.main()
