"""Check stock-family Nornir art, event routing, compass, and rollback."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("nornir_stock_builder_test", "build-nornir-stock-family-test.py")
wrapper = load("nornir_stock_installer_test", "install-nornir-stock-family-test.py")
old_tests = load("nornir_stock_installer_base_tests", "test_nornir_map_id_installer.py")


class StockBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live = builder.base.GAME
        prior = json.loads(builder.REPORT.read_text(encoding="utf-8"))
        if all(hashlib.sha256((live / relative).read_bytes()).hexdigest() == expected
               for relative, expected in prior["source_sha256"].items()):
            cls.source_game = live
        else:
            journals = sorted(builder.REPORT.parent.glob("backups/*/operation.json"))
            backups = [path.parent / "before" for path in journals]
            source = next((folder for folder in backups
                           if all((folder / relative).exists() and
                                  hashlib.sha256((folder / relative).read_bytes()).hexdigest() == expected
                                  for relative, expected in prior["source_sha256"].items())), None)
            if source is None:
                raise AssertionError("Raven source backup unavailable")
            temporary = tempfile.TemporaryDirectory()
            cls.addClassCleanup(temporary.cleanup)
            cls.source_game = Path(temporary.name)
            for relative in prior["source_sha256"]:
                target = cls.source_game / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, target)
            for relative in prior["untouched_sha256"]:
                target = cls.source_game / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(live / relative, target)
        cls.outputs, cls.report = builder.build(cls.source_game)

    def test_distinct_stock_icons_and_untouched_raven_art(self):
        outputs, report = builder.build(self.source_game)
        self.assertEqual(self.outputs, outputs)
        self.assertEqual(self.report, report)
        self.assertNotIn("exec/wad/pc_le/r_ui.wad", outputs)
        self.assertNotIn("exec/dc/pc_le/wad_r_perm.dcb", outputs)
        rows = builder.base.stage.marker_snapshot(
            builder.base.parsed(outputs[builder.base.MASTER], builder.base.MASTER))
        icons = Counter(row["icon"] for row in rows)
        self.assertEqual(icons["goMapIconCompletionistRaven"], 53)
        for family, resource in builder.ART.items():
            count = sum(row["family"] == family for row in builder.base.rows())
            self.assertEqual(icons[resource], count +
                             sum(row["icon"] == resource for row in
                                 builder.base.stage.marker_snapshot(
                                     builder.base.Dcb(self.source_game / builder.base.MASTER))))
        self.assertTrue(report["proof"][builder.base.POOL]["exact_inverse"])

    def test_lua_compiles_and_uses_stock_compass_class(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        for relative in (builder.base.MAP_LUA, builder.base.RUNIC_LUA,
                         builder.base.STANDARD_LUA):
            lua.globals().source = self.outputs[relative].decode("utf-8")
            lua.execute("assert(loadstring(source))")
        for family, compass_class in builder.COMPASS.items():
            self.assertIn(('Class="' + compass_class + '"').encode(),
                          self.outputs[builder.base.MAP_LUA], family)
        self.assertNotIn(b'Class="DockPoint"', self.outputs[builder.base.MAP_LUA])

    def test_locked_attempt_reveals_children_and_compass_releases_raven(self):
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
            Compass={HaveCompass=function() return true end,
              ShowMarker=function(name,class)
                shown[#shown+1]={name=name,class=class}; return true
              end,
              HideMarker=function(name) hidden[#hidden+1]=name; return true end}
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
          MapOn={Menu_Next_Filter=function() end,
            UpdateFilterButtonMapping=function() end,
            SubmenuExit=function() end, Exit=function() end,
            ClearIcons=function() end,
            MapCollisionChangeHandler=function() end,
            GetShowOnCompassPrompt=function() return true,"stock" end,
            ShowOnCompass=function() return true end}
          CompletionistMapV100_CreateMapPin=function() end
          function countIcons(map)
            local count=0
            for _, icon in pairs(map.completionistMapV105NornirIdTestIcons or {}) do
              if icon.visible then count=count+1 end
            end
            return count
          end
        ''')
        definitions = builder.base.rows()
        for row in definitions:
            uid = int(row["marker"]["uid"], 16)
            signed = uid if uid < 1 << 63 else uid - (1 << 64)
            lua.globals().markerIds[row["marker"]["name"]] = str(signed)
        source = self.outputs[builder.base.MAP_LUA].decode("utf-8")
        lua.execute(source[source.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR NATIVE TEST"):])
        map_ui = lua.table_from({"currRealmName": "Midgard", "filterIndex": 1,
                                 "filterButtonMapping": lua.table_from([1, -101, -102]),
                                 "SetReticleInfo": lambda *args: None,
                                 "UpdateFooterButtonPrompt": lambda *args: None})
        state = lua.table_from({"menu": lua.table_from({})})
        lua.globals().CompletionistMapV100_CreateMapPin(map_ui)
        self.assertEqual(lua.globals().countIcons(map_ui), 17)
        key = "wad_xpl200_funeral|runiclock01|runiclock02|runiclock03"
        event = lua.globals().hooks["COMPLETIONIST_NORNIR_EVENT_V1"]
        event("NORNIR_V1\tattempt\t" + key + "\t")
        self.assertEqual(lua.globals().countIcons(map_ui), 20)
        parent = next(row for row in definitions if row["catalogue_id"] ==
                      "nornir_chest_c190d59340706bb79925cb9f2d5867cf")
        name = parent["marker"]["name"]
        icon = map_ui.completionistMapV105NornirIdTestIcons[name]
        map_ui.currMarkerID = lua.globals().markerIds[name]
        lua.globals().MapOn.MapCollisionChangeHandler(
            map_ui, state, lua.table_from([icon]), "Midgard")
        self.assertTrue(lua.globals().MapOn.ShowOnCompass(map_ui, state))
        self.assertEqual(lua.globals().shown[1]["class"], "SIDE")
        self.assertEqual(lua.globals().released, 1)
        event("NORNIR_V1\topened\t" + key + "\t")
        self.assertEqual(lua.globals().countIcons(map_ui), 16)


class StockInstallerTest(old_tests.NornirMapIdInstallerTest):
    def setUp(self):
        previous = old_tests.installer
        old_tests.installer = wrapper.base
        self.addCleanup(lambda: setattr(old_tests, "installer", previous))
        super().setUp()
        untouched = {}
        for relative in (wrapper.base.WAD, wrapper.base.GRAPH,
                         "exec/dc/pc_le/wad_r_perm.dcb", "exec/boot-options.json"):
            path = self.game / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(("untouched " + relative).encode())
            untouched[relative] = wrapper.base.sha(path)
        pinned = patch.object(wrapper.base, "STOCK_UNTOUCHED", untouched)
        pinned.start()
        self.addCleanup(pinned.stop)
        path = self.build / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["kind"] = wrapper.base.EXPECTED_KIND
        report["renderer"] = "distinct_stock_family_icons"
        report["compass"] = builder.COMPASS
        report["stock_art"] = builder.ART
        report["untouched_sha256"] = untouched
        report["proof"]["exec/dc/pc_le/wad_r_ui.dcb"] = {
            "new_rows": 88, "raven_rows_unchanged": 45, "exact_inverse": True}
        path.write_text(json.dumps(report), encoding="utf-8")

    def test_missing_stock_proof_blocks_writes(self):
        path = self.build / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["proof"]["exec/dc/pc_le/wad_r_ui.dcb"].pop("exact_inverse")
        path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stock family preservation proof absent"):
            wrapper.base.install(self.build, self.game, lambda: None)
        self.assertFalse((self.game / wrapper.base.RUNIC).exists())


if __name__ == "__main__":
    unittest.main()
