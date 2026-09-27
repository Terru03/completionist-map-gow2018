"""Native data preservation, Lua 5.1 filter/compass integration, and rollback."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("location_builder_tests", "build-collectible-locations.py")
installer = load("location_installer_tests", "install-collectible-locations.py")


class LocationDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.config, cls.excluded = builder.definitions()
        cls.outputs = {name: (builder.BUILD / "candidate/game-root" / name).read_bytes()
                       for name in builder.FILES}
        cls.report = json.loads((builder.BUILD / "report.json").read_text())

    def test_every_fixed_location_is_registered_in_its_native_region(self):
        master = builder.base.stage.marker_snapshot(builder.base.parsed(
            self.outputs[builder.base.MASTER], builder.base.MASTER))
        coords = builder.base.stage.coordinate_snapshot(builder.base.parsed(
            self.outputs[builder.base.COORDS], builder.base.COORDS))
        by_id = {row["uid"]: row for row in master}
        coordinate_ids = {row["uid"] for row in coords}
        marker_counts = Counter(row["uid"] for row in master)
        coordinate_counts = Counter(row["uid"] for row in coords)
        for row in self.rows:
            actual = by_id[row["marker"]["uid"]]
            self.assertEqual(marker_counts[actual["uid"]], 1)
            self.assertEqual(coordinate_counts[actual["uid"]], 1)
            self.assertEqual(actual["icon"], "goMapIconSecondaryQuest")
            self.assertEqual(actual["realm"], row["realm_id"])
            self.assertEqual(actual["region"], row["region_id"])
            self.assertIn(actual["uid"], coordinate_ids)
        self.assertEqual(Counter(row["family"] for row in self.rows), builder.COUNTS)
        self.assertEqual(len(self.excluded), 27)
        nif = [row for row in self.rows if row["realm"] == "Niflheim"]
        self.assertEqual(Counter(row["family"] for row in nif), {"lore_marker": 1, "realm_tear": 3})
        self.assertTrue(all(row["region"] == "NiflheimMain" for row in nif))
        self.assertEqual(sum(row["icon"] == "goMapIconCompletionistRaven" for row in master), 53)

    def test_lua51_compiles_and_old_code_is_preserved(self):
        raw = self.outputs[builder.base.MAP_LUA]
        prefix, appendix = raw.split(b"\n-- BEGIN COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS", 1)
        self.assertEqual(builder.sha(prefix.replace(builder.HANDOFF, b"", 1)),
                         builder.SOURCE[builder.base.MAP_LUA])
        lua = LuaRuntime()
        lua.globals().source = raw.decode("utf-8-sig")
        lua.execute("assert(loadstring(source))")
        self.assertNotIn(b"IncrementQuestProgress", appendix)
        self.assertEqual(set(self.outputs), set(builder.FILES))
        for name in builder.FILES:
            self.assertTrue(self.report["proof"][name]["exact_inverse"])

    def test_additional_catalogue_pairs_treasures_and_covers_shrine_variants(self):
        data = json.loads(builder.ADDITIONAL.read_text())
        rows = data["collectibles"]
        maps = [source["identity_label"][:-7] for row in rows if row["family"] == "treasure_map"
                for source in row["sources"]]
        digs = [source["identity_label"] for row in rows if row["family"] == "treasure_dig"
                for source in row["sources"]]
        self.assertEqual(len(maps), 12)
        self.assertEqual(len(set(maps)), 12)
        self.assertCountEqual(maps, digs)
        shrines = [row for row in rows if row["family"] == "jotnar_shrine"]
        self.assertEqual(sum(row["placement"]["name"] == "gotriptychbasic" for row in shrines), 2)
        self.assertEqual(sum(row["placement"]["name"] == "gotryptich" for row in shrines), 1)
        thamur = [row for row in shrines if row["placement"]["name"] == "gotriptych_thamur"]
        self.assertEqual(len(thamur), 1)
        self.assertEqual({source["wad"] for source in thamur[0]["sources"]},
                         {"stn105_chiselsite.wad", "stn905_chiselsite.wad"})
        for row in rows:
            self.assertTrue(all(source["root_complete"] for source in row["sources"]))
            if row["family"] in {"coffin", "wooden_chest", "cipher_chest"}:
                self.assertFalse(row["marker"]["coordinate_wad"].lower().startswith(("wad_nid", "wad_msp")))
                for source in row["sources"]:
                    self.assertNotIn("godirtpatch", [part["name"] for part in source["transform_chain"]])

    def test_shared_prefabs_do_not_duplicate_locations(self):
        rows = json.loads(builder.ADDITIONAL.read_text())["collectibles"]
        for index, row in enumerate(rows):
            for other in rows[index + 1:]:
                if row["realm"] == other["realm"]:
                    self.assertGreater(math.dist(row["marker"]["position_world"],
                                                 other["marker"]["position_world"]), 0.1,
                                       (row["catalogue_id"], other["catalogue_id"]))
        reused = [row for row in self.rows if row["marker"].get("existing_native")]
        self.assertEqual({row["marker"]["name"] for row in reused},
                         {f"Nif_400_RealmTear0{i}" for i in (1, 2, 3)})
        self.assertEqual(self.report["new_marker_count"], len(self.rows) - len(reused))

    def runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().print = lambda *args: None
        lua.execute('''
          hooks, markerIds, activeTargets = {}, {}, {}
          playerRealm, rejectHide, rejectShow = "Midgard", false, false
          package.preload["core.thunk"] = function()
            return {Install=function(name,fn) hooks[name]=fn end}
          end
          Map = {
            FindRegionFromMarker=function(id) return true,1 end,
            CreateMarkerIcon=function(id)
              return {id=id, visible=false, Show=function(self) self.visible=true end}
            end,
            RecycleIcon=function(icon) icon.visible=false end
          }
          game = {Map={GetMarkerInfo=function(name)
              return markerIds[name] and {Id=markerIds[name]} or nil end},
            Compass={HaveCompass=function() return true end,
              ShowMarker=function(name,class)
                if rejectShow then return false end
                activeTargets[name]=class; return true
              end,
              HideMarker=function(name)
                if rejectHide then return false end
                activeTargets[name]=nil; return true
              end}}
          mapUtil={GetPlayerRealm=function() return playerRealm end}
          tutorialUtil={CurrentlyShowingStep=function() return false end}
          util={GetLAMSMsg=function(value) return value end}
          lamsConsts={AddToCompass="Add",RemoveFromCompass="Remove",ReplaceInCompass="Replace"}
          Audio={PlaySound=function() end}
          CompletionistMapV105ReleaseRavenCompass=function()
            if rejectHide then return false end
            activeTargets.raven=nil
            CompletionistMapV105TrackedCatalogueId=nil
            return true
          end
          MapOn={Update=function() end, SubmenuExit=function() end,
            Exit=function() end, ClearIcons=function() end,
            GetRealmMarkerInfo=function(self)
              self.realmMarkerInfo=self.nativeRealmMarkers or {}
              self:UpdateFilterButtonMapping()
            end,
            GetMarkers=function(self) self.stockMarkers=true end,
            GetAlwaysOnMarkers=function(self) self.stockMarkers=true end,
            ClearMarkers=function(self) self.stockMarkers=false end,
            MapCollisionChangeHandler=function(self,state,hits)
              self.currMarkerID=hits[1] and hits[1].id or nil
            end,
            GetShowOnCompassPrompt=function() return true,"stock" end,
            ShowOnCompass=function(self)
              activeTargets.stock="SIDE"; self.currShownMarkerID="stock"; return true
            end}
          function MapOn:Menu_Next_Filter(direction)
            if self.isOpenedForFastTravel then return end
            self.filterIndex=(self.filterIndex+direction-1)%#self.filterButtonMapping+1
            self:UpdateFilterUI()
          end
          function MapOn:UpdateFilterButtonMapping()
            self.filterButtonMapping={1,2}; self.filterIndex=1
          end
          function MapOn:SetReticleInfo(state,title,description) self.title=title end
          function MapOn:UpdateFooterButtonPrompt() end
          CompletionistMapV100_CreateMapPin=function() end
          function makeMap(realm)
            return setmetatable({currRealmName=realm,filterIndex=1,
              filterButtonMapping={1,2}}, {__index=MapOn})
          end
          function iconCount(map)
            local count=0
            for _,icon in pairs(map.completionistMapV105LocationIcons or {}) do
              if icon.visible then count=count+1 end
            end
            return count
          end
          function targetCount()
            local count=0; for _ in pairs(activeTargets) do count=count+1 end; return count
          end
          function selectFilter(map,kind)
            for index,value in ipairs(map.filterButtonMapping) do
              if value==kind then map:Menu_Next_Filter(index-map.filterIndex); return end
            end
            error("missing category: " .. tostring(kind))
          end
          function selectIcon(map,name,nornir)
            local icons=nornir and map.completionistMapV105NornirIdTestIcons or
              map.completionistMapV105LocationIcons
            assert(icons[name],"no icon: "..name)
            map:MapCollisionChangeHandler({menu={}}, {icons[name]}, map.currRealmName)
          end
        ''')
        for row in self.rows + builder.base.rows():
            uid = int(row["marker"]["uid"], 16)
            lua.globals().markerIds[row["marker"]["name"]] = str(uid if uid < 1 << 63 else uid - (1 << 64))
        source = self.outputs[builder.base.MAP_LUA].decode("utf-8")
        source = source[source.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST"):]
        prelude = '''
          local completionistFilterLabels={[-101]="COMPLETIONIST",[-103]="NORNIR CHESTS",[-104]="NORNIR PUZZLE"}
          local markerFilters={{markerIncludeFlags=1},{markerIncludeFlags=2}}
          function MapOn:UpdateFilterUI()
            self.label=completionistFilterLabels[self.filterButtonMapping[self.filterIndex]] or "STOCK"
          end
        '''
        lua.execute(prelude + source)
        lua.execute("CompletionistMapV105Nornir.liveReader:SetReady(false)")
        return lua

    def test_categories_isolate_families_in_every_realm(self):
        lua = self.runtime()
        for realm in sorted({row["realm"] for row in self.rows}):
            ui = lua.globals().makeMap(realm)
            lua.globals().MapOn.UpdateFilterButtonMapping(ui)
            lua.globals().CompletionistMapV100_CreateMapPin(ui)
            expected = Counter(row["family"] for row in self.rows if row["realm"] == realm)
            self.assertEqual(lua.globals().iconCount(ui), sum(expected.values()))
            for category in self.config["categories"]:
                if expected[category["family"]] == 0:
                    self.assertNotIn(category["filter"], list(ui.filterButtonMapping.values()))
                    continue
                lua.globals().selectFilter(ui, category["filter"])
                self.assertEqual(ui.label, category["label"])
                self.assertEqual(lua.globals().iconCount(ui), expected[category["family"]])
                self.assertEqual(len(list(ui.completionistMapV105NornirIdTestIcons.values())), 0)
                lua.globals().MapOn.UpdateFilterButtonMapping(ui)
                self.assertEqual(ui.filterButtonMapping[ui.filterIndex], category["filter"])
                lua.globals().MapOn.GetAlwaysOnMarkers(ui)
                lua.globals().MapOn.GetMarkers(ui)
                self.assertFalse(ui.stockMarkers)
            mapping = list(ui.filterButtonMapping.values())
            self.assertEqual(len(mapping), len(set(mapping)))
            lua.globals().selectFilter(ui, -101)
            self.assertEqual(lua.globals().iconCount(ui), sum(expected.values()))
            lua.globals().selectFilter(ui, 2)
            self.assertEqual(lua.globals().iconCount(ui), 0)
            lua.globals().MapOn.GetMarkers(ui)
            self.assertTrue(ui.stockMarkers)
            lua.globals().MapOn.Exit(ui)

    def test_fast_travel_realm_change_and_teardown_clear_stale_selection(self):
        lua = self.runtime()
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        name = next(row["marker"]["name"] for row in self.rows if row["realm"] == "Midgard")
        lua.globals().selectIcon(ui, name, False)
        self.assertIsNotNone(ui.completionistMapV105LocationSelected)
        ui.isOpenedForFastTravel = True
        lua.globals().MapOn.Update(ui)
        lua.globals().MapOn.GetMarkers(ui)
        self.assertTrue(ui.stockMarkers)
        self.assertEqual(lua.globals().iconCount(ui), 0)
        self.assertIsNone(ui.completionistMapV105LocationSelected)
        ui.isOpenedForFastTravel = False
        ui.currRealmName = "Niflheim"
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui),
                         sum(row["realm"] == "Niflheim" for row in self.rows))
        lua.globals().MapOn.ClearIcons(ui)
        self.assertEqual(lua.globals().iconCount(ui), 0)

    def test_authored_rift_ids_have_one_icon_and_keep_fast_travel_enumeration(self):
        lua = self.runtime()
        ui = lua.globals().makeMap("Niflheim")
        native = [row for row in self.rows if row["marker"].get("existing_native")]
        native_infos = [lua.table_from({"Id": lua.globals().markerIds[row["marker"]["name"]],
                                        "iconGO": lua.table_from({"visible": True})}) for row in native]
        native_icons = [info.iconGO for info in native_infos]
        ui.nativeRealmMarkers = lua.table_from(native_infos + [lua.table_from({"Id": "stock_gateway"})])
        lua.globals().MapOn.GetRealmMarkerInfo(ui)
        self.assertEqual([info.Id for info in ui.realmMarkerInfo.values()], ["stock_gateway"])
        self.assertTrue(all(not icon.visible for icon in native_icons))
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        lua.globals().selectFilter(ui, -112)
        self.assertEqual(lua.globals().iconCount(ui), 3)
        self.assertEqual(set(ui.completionistMapV105LocationIcons.keys()),
                         {row["marker"]["name"] for row in native})
        ui.isOpenedForFastTravel = True
        lua.globals().MapOn.GetRealmMarkerInfo(ui)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(len(list(ui.realmMarkerInfo.values())), 4)
        self.assertEqual(lua.globals().iconCount(ui), 0)

    def test_compass_add_replace_remove_with_nornir_raven_and_stock(self):
        lua = self.runtime()
        ui = lua.globals().makeMap("Midgard")
        state = lua.table_from({"menu": lua.table()})
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        names = [row["marker"]["name"] for row in self.rows if row["realm"] == "Midgard"]
        chest = next(row["marker"]["name"] for row in builder.base.rows()
                     if row["realm"] == "Midgard" and row["family"] == "nornir_chest")
        for name, nornir in ((chest, True), (names[0], False), (names[1], False),
                             (chest, True), (names[0], False)):
            lua.globals().selectIcon(ui, name, nornir)
            self.assertTrue(lua.globals().MapOn.ShowOnCompass(ui, state))
            self.assertEqual(lua.globals().targetCount(), 1)
            self.assertEqual(lua.globals().activeTargets[name], "SIDE")
        self.assertEqual(lua.globals().MapOn.GetShowOnCompassPrompt(ui)[1], "[AdvanceButton] Remove")
        lua.globals().MapOn.ShowOnCompass(ui, state)
        self.assertEqual(lua.globals().targetCount(), 0)
        lua.execute('activeTargets.raven="CompletionistRaven"; CompletionistMapV105TrackedCatalogueId="raven"')
        self.assertEqual(lua.globals().MapOn.GetShowOnCompassPrompt(ui)[1], "[AdvanceButton] Replace")
        lua.globals().MapOn.ShowOnCompass(ui, state)
        self.assertEqual(lua.globals().targetCount(), 1)
        self.assertIsNone(lua.globals().activeTargets.raven)
        lua.globals().MapOn.MapCollisionChangeHandler(ui, state, lua.table(), "Midgard")
        lua.globals().MapOn.ShowOnCompass(ui, state)
        self.assertEqual(lua.globals().targetCount(), 1)
        self.assertEqual(lua.globals().activeTargets.stock, "SIDE")
        lua.globals().selectIcon(ui, names[0], False)
        lua.globals().MapOn.ShowOnCompass(ui, state)
        self.assertEqual(lua.globals().targetCount(), 1)
        controller = lua.globals().CompletionistMapV105Nornir
        controller.BeginEpoch(controller, 2)
        self.assertEqual(lua.globals().targetCount(), 0)

    def test_failed_compass_release_does_not_add_second_target(self):
        lua = self.runtime()
        ui = lua.globals().makeMap("Midgard")
        state = lua.table_from({"menu": lua.table()})
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        names = [row["marker"]["name"] for row in self.rows if row["realm"] == "Midgard"]
        lua.globals().selectIcon(ui, names[0], False)
        lua.globals().MapOn.ShowOnCompass(ui, state)
        lua.globals().selectIcon(ui, names[1], False)
        lua.globals().rejectHide = True
        self.assertFalse(lua.globals().MapOn.ShowOnCompass(ui, state))
        self.assertEqual(lua.globals().targetCount(), 1)
        lua.globals().rejectHide = False
        lua.globals().rejectShow = True
        self.assertFalse(lua.globals().MapOn.ShowOnCompass(ui, state))
        self.assertEqual(lua.globals().targetCount(), 0)


class LocationInstallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.game, self.build = root / "game", root / "build"
        before, untouched, files = {}, {}, {}
        for name in installer.FILES:
            old = ("old " + name).encode()
            new = ("new " + name).encode()
            target = self.game / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
            candidate = self.build / "candidate/game-root" / name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(new)
            before[name] = builder.sha(old)
            files[name] = {"before": before[name], "after": builder.sha(new)}
        for name in installer.builder.UNTOUCHED:
            target = self.game / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(name.encode())
            untouched[name] = builder.sha(name.encode())
        for name, value in (("SOURCE", before), ("UNTOUCHED", untouched)):
            patcher = patch.object(installer.builder, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        report = {"schema": 1, "kind": builder.KIND, "mode": "all_known_locations",
                  "family_counts": builder.COUNTS,
                  "location_count": sum(builder.COUNTS.values()),
                  "new_marker_count": sum(builder.COUNTS.values()) - builder.REUSED_NATIVE_MARKERS,
                  "reused_native_markers": builder.REUSED_NATIVE_MARKERS,
                  "files": files, "source_sha256": before, "untouched_sha256": untouched,
                  "proof": {name: {"exact_inverse": True} for name in files}}
        (self.build / "report.json").write_text(json.dumps(report))

    def test_install_verify_and_rollback_restore_all_four_files(self):
        operation = installer.install(self.game, self.build, lambda: None)
        installer.verify(operation, self.game, self.build, lambda: None)
        # Rollback remains possible even when the candidate has been rebuilt or removed.
        shutil.rmtree(self.build / "candidate")
        installer.rollback(operation, self.game, self.build, lambda: None)
        installer.rollback(operation, self.game, self.build, lambda: None)
        for name, digest in installer.builder.SOURCE.items():
            self.assertEqual(installer.base.sha(self.game / name), digest)

    def test_second_file_failure_restores_prior_files(self):
        original = installer.base.atomic_copy
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated write failure")
            return original(*args)

        with patch.object(installer.base, "atomic_copy", fail_once):
            with self.assertRaisesRegex(OSError, "simulated"):
                installer.install(self.game, self.build, lambda: None)
        for name, digest in installer.builder.SOURCE.items():
            self.assertEqual(installer.base.sha(self.game / name), digest)

    def test_running_game_and_modified_source_block_install(self):
        def running():
            raise ValueError("God of War is running")
        with self.assertRaisesRegex(ValueError, "running"):
            installer.install(self.game, self.build, running)
        name = next(iter(installer.FILES))
        (self.game / name).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "installed base differs"):
            installer.install(self.game, self.build, lambda: None)
        self.assertFalse((self.build / "backups").exists())

    def test_rollback_preflight_preserves_unrelated_changes(self):
        operation = installer.install(self.game, self.build, lambda: None)
        name = sorted(installer.FILES)[-1]
        (self.game / name).write_bytes(b"user edit")
        snapshot = {key: (self.game / key).read_bytes() for key in installer.FILES}
        with self.assertRaisesRegex(ValueError, "file changed after"):
            installer.rollback(operation, self.game, self.build, lambda: None)
        self.assertEqual(snapshot, {key: (self.game / key).read_bytes() for key in installer.FILES})


if __name__ == "__main__":
    unittest.main()
