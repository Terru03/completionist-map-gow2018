"""Check the live-failed Nornir key, child reveal, and compass path in Lua 5.1."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime

spec = importlib.util.spec_from_file_location(
    "native_builder", HERE / "build-nornir-native-test.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class NornirNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs, cls.report = builder.build()
        cls.definitions = builder.base.rows()

    def test_art_resources_and_raven_records(self):
        self.assertEqual(self.report["new_marker_count"], 88)
        self.assertEqual(self.report["child_marker_count"], 66)
        self.assertTrue(self.report["proof"][builder.WAD]["four_unique_material_keys"])
        self.assertGreater(
            self.report["proof"][builder.WAD]["original_non_accounting_records_preserved"],
            50000)
        dcb = builder.base.parsed(self.outputs[builder.base.MASTER], builder.base.MASTER)
        rows = builder.base.stage.marker_snapshot(dcb)
        self.assertEqual(sum(row["icon"] == "goMapIconCompletionistRaven"
                             for row in rows), 53)
        self.assertEqual(sum(row["icon"].startswith("goMapIconCompletionistNornir")
                             for row in rows), 88)

    def test_all_lua_compiles(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        for rel in (builder.base.MAP_LUA, builder.base.RUNIC_LUA,
                    builder.base.STANDARD_LUA):
            lua.globals().source = self.outputs[rel].decode("utf-8")
            lua.execute("assert(loadstring(source))")

    def test_exact_locked_attempt_reveals_children_and_compass_toggles(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('''
          hooks, markerIds, shown, hidden = {}, {}, {}, {}
          package.preload["core.thunk"] = function()
            return {Install=function(name, fn) hooks[name]=fn end}
          end
          Map = {
            FindRegionFromMarker=function(id) return true, 1 end,
            CreateMarkerIcon=function(id)
              local icon={id=id, visible=false}
              function icon:Show() self.visible=true end
              return icon
            end,
            RecycleIcon=function(icon) icon.visible=false end
          }
          game = {
            Map={GetMarkerInfo=function(name)
              return markerIds[name] and {Id=markerIds[name]} or nil
            end},
            Compass={
              HaveCompass=function() return true end,
              ShowMarker=function(name,class)
                shown[#shown+1]={name=name,class=class}; return true
              end,
              HideMarker=function(name) hidden[#hidden+1]=name; return true end
            }
          }
          mapUtil={GetPlayerRealm=function() return "Midgard" end}
          tutorialUtil={CurrentlyShowingStep=function() return false end}
          util={GetLAMSMsg=function(value) return value end}
          lamsConsts={AddToCompass="Add",RemoveFromCompass="Remove",
                      ReplaceInCompass="Replace"}
          Audio={PlaySound=function() end}
          released=0
          _G.CompletionistMapV105ReleaseRavenCompass=function()
            released=released+1; return true
          end
          MapOn={
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
        source = self.outputs[builder.base.MAP_LUA].decode("utf-8")
        layer = source[source.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR NATIVE TEST"):]
        lua.execute(layer)
        map_ui = lua.table_from({
            "currRealmName": "Midgard", "filterIndex": 1,
            "filterButtonMapping": lua.table_from([1, -101, -102]),
            "ravenIcons": lua.table_from(["raven-1", "raven-2"]),
            "SetReticleInfo": lambda *args: None,
            "UpdateFooterButtonPrompt": lambda *args: None,
        })
        state = lua.table_from({"menu": lua.table_from({})})
        lua.globals().CompletionistMapV100_CreateMapPin(map_ui)
        count = lua.globals().countIcons
        self.assertEqual(count(map_ui), 17)
        parent = next(row for row in self.definitions if row["catalogue_id"] ==
                      "nornir_chest_c190d59340706bb79925cb9f2d5867cf")
        children = [row for row in self.definitions if
                    row["progression"].get("parent_catalogue_id") ==
                    parent["catalogue_id"]]
        key = "wad_xpl200_funeral|runiclock01|runiclock02|runiclock03"
        event = lua.globals().hooks["COMPLETIONIST_NORNIR_EVENT_V1"]
        event("NORNIR_V1\tattempt\txpl200_funeral|runiclock01|runiclock02|runiclock03\t")
        self.assertEqual(count(map_ui), 17)
        event("NORNIR_V1\tattempt\t" + key + "\t")
        self.assertEqual(count(map_ui), 20)
        self.assertEqual(len(map_ui.ravenIcons), 2)
        name = parent["marker"]["name"]
        icon = map_ui.completionistMapV105NornirIdTestIcons[name]
        map_ui.currMarkerID = lua.globals().markerIds[name]
        lua.globals().MapOn.MapCollisionChangeHandler(
            map_ui, state, lua.table_from([icon]), "Midgard")
        visible, prompt = lua.globals().MapOn.GetShowOnCompassPrompt(map_ui)
        self.assertTrue(visible)
        self.assertIn("Add", prompt)
        self.assertTrue(lua.globals().MapOn.ShowOnCompass(map_ui, state))
        self.assertEqual(lua.globals().shown[1]["class"],
                         "CompletionistNornirChest")
        self.assertEqual(lua.globals().released, 1)
        visible, prompt = lua.globals().MapOn.GetShowOnCompassPrompt(map_ui)
        self.assertTrue(visible)
        self.assertIn("Remove", prompt)
        self.assertTrue(lua.globals().MapOn.ShowOnCompass(map_ui, state))
        self.assertEqual(lua.globals().hidden[1], name)
        event("NORNIR_V1\tseal\t" + key + "\t" +
              children[0]["native"]["reference_name"].lower())
        self.assertEqual(count(map_ui), 19)
        event("NORNIR_V1\topened\t" + key + "\t")
        self.assertEqual(count(map_ui), 16)


if __name__ == "__main__":
    unittest.main()
