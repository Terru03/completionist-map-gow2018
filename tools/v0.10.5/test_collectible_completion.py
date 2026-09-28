"""Composed completion tests: state service + location map visibility integration."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("completion_builder", "build-collectible-locations.py")
STATE_LUA = HERE / "collectible-state.lua"
LOCATION_LUA = HERE / "collectible-location-map.lua"


class CompletionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.config, cls.excluded = builder.definitions()
        cls.outputs = {name: (builder.BUILD / "candidate/game-root" / name).read_bytes()
                       for name in builder.FILES}

    def runtime(self, with_state=True, production=False):
        """Build a Lua test harness with the state service optionally wired up."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().print = lambda *args: None
        lua.execute('''
          hooks, markerIds, activeTargets = {}, {}, {}
          package.preload["ui.fsm"] = function() return {runList={}} end
          package.preload["core.timer"] = function()
            return {Timer={New=function(runList,period,callback)
              local timer={Start=function(self) self.running=true end,
                GetElapsedTime=function() return period end}
              backgroundTick=function() callback(timer) end
              return timer
            end}}
          end
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
          Camera={PointAtGO=function(go) Camera.pointed=go end}
          UI={
            GetEventSenderGameObject=function() return UI.sender end,
            SetIsClickable=function(go) go.clickable=true end,
            Anim=function(go,mode,name,rate,frame)
              go.anim={mode=mode,rate=rate,frame=frame}
            end
          }
          CompletionistMapV105ReleaseRavenCompass=function()
            if rejectHide then return false end
            activeTargets.raven=nil
            CompletionistMapV105TrackedCatalogueId=nil
            return true
          end
          MapOn={Update=function() end, SubmenuExit=function() end,
            Exit=function() end, ClearIcons=function() end,
            MouseClickHandler=function() end,
            UpdateMapMarkerHighlights=function() end,

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
          function MapOn:SetReticleInfo(state,title,description)
            self.title=title; self.description=description
          end
          function MapOn:UpdateFooterButtonPrompt() end
          CompletionistMapV100_CreateMapPin=function() end
          function makeMap(realm, enableShowAll)
            local m = setmetatable({currRealmName=realm,filterIndex=1,
              filterButtonMapping={1,2}}, {__index=MapOn})
            if type(CompletionistMapV105ShowAll) == "function" then
              CompletionistMapV105ShowAll(enableShowAll ~= false)
            end
            return m
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
        # Register marker IDs
        for row in self.rows + builder.base.rows():
            uid = int(row["marker"]["uid"], 16)
            lua.globals().markerIds[row["marker"]["name"]] = str(uid if uid < 1 << 63 else uid - (1 << 64))

        # Optionally wire up the state service
        if with_state and not production:
            state_source = STATE_LUA.read_text(encoding="utf-8")
            State = lua.execute(state_source)
            ids = [row["catalogue_id"] for row in self.rows]
            ids_table = lua.table(*ids)
            store = State.New(ids_table)
            lua.globals().CompletionistMapV105LocationState = store

        # Load the composed map Lua: Nornir/Raven prefix from built artifact + location layer from source
        base_lua = self.outputs[builder.base.MAP_LUA].decode("utf-8")
        # Get everything up to and including the location layer start marker
        prefix = base_lua[:base_lua.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST")]
        # The existing Nornir/Raven code from the built artifact
        nornir_source = base_lua[base_lua.index("-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST"):
                                  base_lua.index("-- END COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS")]
        # Strip out the old location layer from nornir_source
        if "-- BEGIN COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS" in nornir_source:
            nornir_source = nornir_source[:nornir_source.index(
                "-- BEGIN COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS")]
        # Render the location layer from the current template
        location_lua = builder.render_runtime(self.rows, self.config, include_state=production).decode("utf-8")

        prelude = '''
          local completionistFilterLabels={[-101]="COMPLETIONIST",[-103]="NORNIR CHESTS",[-104]="NORNIR PUZZLE"}
          local markerFilters={{markerIncludeFlags=1},{markerIncludeFlags=2}}
          function MapOn:UpdateFilterUI()
            self.label=completionistFilterLabels[self.filterButtonMapping[self.filterIndex]] or "STOCK"
          end
        '''
        lua.execute(prelude + nornir_source + "\n" + location_lua)
        lua.execute("CompletionistMapV105Nornir.liveReader:SetReady(false)")
        return lua

    def midgard_rows(self):
        return [row for row in self.rows if row["realm"] == "Midgard"]

    def test_production_bootstrap_and_real_controller_boundary(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        store = g.CompletionistMapV105LocationState
        self.assertEqual(store.Epoch(store), 1)
        cid = self.midgard_rows()[0]["catalogue_id"]
        self.assertFalse(g.CompletionistMapV105PublishLocationState(cid, "collected", 1))
        g.CompletionistMapV105LocationAuthorityReady(7)
        self.assertTrue(g.CompletionistMapV105PublishLocationState(cid, "collected", 1))
        controller = g.CompletionistMapV105Nornir
        self.assertTrue(controller.BeginEpoch(controller, 2))
        self.assertEqual(store.Get(store, cid), "unknown")
        self.assertFalse(g.CompletionistMapV105PublishLocationState(cid, "collected", 1))
        g.CompletionistMapV105LocationAuthorityReady(8)
        self.assertTrue(g.CompletionistMapV105PublishLocationState(cid, "remaining", 2))
        self.assertEqual(store.Get(store, cid), "remaining")

    def test_publisher_clears_target_with_map_closed(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = self.midgard_rows()[0]
        g.selectIcon(ui, row["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        self.assertEqual(g.targetCount(), 1)
        g.MapOn.Exit(ui)
        self.assertTrue(g.CompletionistMapV105PublishLocationState(row["catalogue_id"], "collected", 1))
        self.assertEqual(g.targetCount(), 0)

    def test_failed_hide_is_retried_after_collection(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = self.midgard_rows()[0]
        g.selectIcon(ui, row["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        g.rejectHide = True
        g.CompletionistMapV105PublishLocationState(row["catalogue_id"], "collected", 1)
        self.assertEqual(g.targetCount(), 1)
        g.rejectHide = False
        g.MapOn.Update(ui)
        self.assertEqual(g.targetCount(), 0)

    def test_mouse_click_selects_custom_marker_and_preserves_zoom(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = self.midgard_rows()[0]
        icon = ui.completionistMapV105LocationIcons[row["marker"]["name"]]
        self.assertTrue(icon.clickable)
        ui.mapIconCollision = icon
        g.UI.sender = icon
        menu_state = lua.table_from({"menu": lua.table()})
        g.MapOn.MouseClickHandler(ui, menu_state)
        self.assertIsNone(g.Camera.pointed)
        self.assertEqual(ui.completionistMapV105LocationSelected.Name, row["marker"]["name"])

    def test_mouse_click_empty_space_ignores_stale_sender_and_preserves_zoom(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = self.midgard_rows()[0]
        icon = ui.completionistMapV105LocationIcons[row["marker"]["name"]]
        g.UI.sender = icon
        ui.mapIconCollision = None
        ui.completionistMapV105LocationSelected = None
        ui.currMarkerID = None
        menu_state = lua.table_from({"menu": lua.table()})
        g.MapOn.MouseClickHandler(ui, menu_state)
        self.assertIsNone(g.Camera.pointed)
        self.assertIsNone(ui.completionistMapV105LocationSelected)

    def test_compass_marker_pulses_and_disallows_multiple_custom_markers(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row0 = self.midgard_rows()[0]
        row1 = self.midgard_rows()[1]
        icon0 = ui.completionistMapV105LocationIcons[row0["marker"]["name"]]
        icon1 = ui.completionistMapV105LocationIcons[row1["marker"]["name"]]

        # Select row0 and add to compass
        g.selectIcon(ui, row0["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        self.assertEqual(g.targetCount(), 1)
        self.assertEqual(icon0.anim.mode, 10)  # AS_ForwardCycle_NoReset (pulsing)

        # Select row1 and add to compass -> replaces row0, exactly one custom marker allowed
        g.selectIcon(ui, row1["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        self.assertEqual(g.targetCount(), 1)
        self.assertEqual(icon0.anim.mode, 0)   # AS_Forward (stopped pulsing)
        self.assertEqual(icon1.anim.mode, 10)  # AS_ForwardCycle_NoReset (pulsing)

        # Toggle row1 off compass -> 0 markers on compass, anim stopped
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        self.assertEqual(g.targetCount(), 0)
        self.assertEqual(icon1.anim.mode, 0)

    def test_compass_mutual_exclusion_between_stock_and_custom_markers(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row0 = self.midgard_rows()[0]
        icon0 = ui.completionistMapV105LocationIcons[row0["marker"]["name"]]

        # 1. Custom marker added -> tracked on compass, icon0 pulsing
        g.selectIcon(ui, row0["marker"]["name"])
        menu_state = lua.table_from({"menu": lua.table()})
        g.MapOn.ShowOnCompass(ui, menu_state)
        self.assertEqual(g.targetCount(), 1)
        self.assertEqual(g.activeTargets[row0["marker"]["name"]], "CompletionistArtefact")
        self.assertEqual(icon0.anim.mode, 10)

        # 2. Stock marker tracked -> custom marker must be released and pulsing stopped
        g.MapOn.MapCollisionChangeHandler(ui, menu_state, lua.table(), "Midgard")
        g.MapOn.ShowOnCompass(ui, menu_state)
        self.assertEqual(g.targetCount(), 1)
        self.assertEqual(g.activeTargets.stock, "SIDE")
        self.assertEqual(icon0.anim.mode, 0)

        # 3. Custom marker tracked again -> stock marker must be released, custom pulsing
        g.selectIcon(ui, row0["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, menu_state)
        self.assertEqual(g.targetCount(), 1)
        self.assertIsNone(g.activeTargets.stock)
        self.assertEqual(g.activeTargets[row0["marker"]["name"]], "CompletionistArtefact")
        self.assertEqual(icon0.anim.mode, 10)

    def test_background_tick_restores_authority_without_opening_map(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        lua.execute('''
          authorityRefreshes=0
          CompletionistMapV105RefreshLocationAuthority=function()
            authorityRefreshes=authorityRefreshes+1
            CompletionistMapV105LocationAuthorityReady(authorityRefreshes)
          end
        ''')
        runtime = g.CompletionistMapV105LocationRuntime
        self.assertFalse(runtime.ready)
        g.backgroundTick()
        self.assertTrue(runtime.ready)
        self.assertEqual(runtime.restoreEpoch, 1)
        controller = g.CompletionistMapV105Nornir
        controller.BeginEpoch(controller, 2)
        self.assertFalse(runtime.ready)
        g.backgroundTick()
        self.assertTrue(runtime.ready)
        self.assertEqual(runtime.restoreEpoch, 2)
        self.assertEqual(g.authorityRefreshes, 2)

    def test_full_native_response_reaches_generated_store_and_hides_pin(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        runtime = g.CompletionistMapV105LocationRuntime
        reader = runtime.reader
        lua.execute('''
          response=''
          local reader=CompletionistMapV105LocationRuntime.reader
          reader.transport={now=function() return reader.elapsed end,
            create=function()
              return {settimeout=function() return 1 end,connect=function() return 1 end,
                send=function(self,value) return #value end,close=function() end,
                receive=function()
                  if #response==0 then return nil,'timeout' end
                  local value=response:sub(1,1);response=response:sub(2);return value
                end}
            end}
        ''')
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap('Midgard')
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = next(row for row in self.midgard_rows() if row['family']=='legendary_chest')
        ids = [reader.ids[i] for i in range(1,411)]
        states = ''.join('2' if identity==row['catalogue_id'] else '0' for identity in ids)
        g.response = (f'COLLECTIBLE_SNAPSHOT_V1 nonce={int(reader.nonce)} restoreEpoch=1 '
                      f'contract={reader.contract} generation=1 states={states}\n')
        g.backgroundTick()
        self.assertEqual(runtime.store.Counts(runtime.store).collected, 0)
        g.backgroundTick()
        self.assertEqual(runtime.store.Get(runtime.store,row['catalogue_id']), 'collected')
        self.assertEqual(runtime.store.Counts(runtime.store).collected, 1)
        self.assertIsNone(ui.completionistMapV105LocationIcons[row['marker']['name']])
        self.assertEqual(g.iconCount(ui),len(self.midgard_rows())-1)

    def test_map_closed_background_tick_retries_failed_hide(self):
        lua = self.runtime(production=True)
        g = lua.globals()
        g.CompletionistMapV105LocationAuthorityReady(1)
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        row = self.midgard_rows()[0]
        g.selectIcon(ui, row["marker"]["name"])
        g.MapOn.ShowOnCompass(ui, lua.table_from({"menu": lua.table()}))
        g.MapOn.Exit(ui)
        g.rejectHide = True
        g.CompletionistMapV105PublishLocationState(row["catalogue_id"], "collected", 1)
        self.assertEqual(g.targetCount(), 1)
        g.rejectHide = False
        self.assertIsNotNone(g.backgroundTick, "No map-closed scheduler")
        g.backgroundTick()
        self.assertEqual(g.targetCount(), 0)

    def test_collected_pin_disappears_from_map(self):
        """Core test: observing collected state removes the pin at next sync."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        total = len(midgard)
        self.assertGreater(total, 1)
        self.assertEqual(lua.globals().iconCount(ui), total)

        # Collect one pin
        target = midgard[0]
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)

        # Trigger sync
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui), total - 1)
        # The collected pin's icon should be gone
        icon = (ui.completionistMapV105LocationIcons or {})[target["marker"]["name"]]
        self.assertTrue(icon is None or not icon.visible)

    def test_uncollected_pins_remain_after_collection(self):
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        # Collect first, mark second as remaining
        store.Observe(store, midgard[0]["catalogue_id"], "collected", 1)
        store.Observe(store, midgard[1]["catalogue_id"], "remaining", 1)
        lua.globals().MapOn.Update(ui)
        # Second pin should still be visible
        icon = ui.completionistMapV105LocationIcons[midgard[1]["marker"]["name"]]
        self.assertTrue(icon.visible)

    def test_collected_pin_hidden_in_all_filters(self):
        """Collected pin should be hidden in All, Completionist, and family filter."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)

        # Check "All" filter (kind=1)
        lua.globals().MapOn.Update(ui)
        icon = (ui.completionistMapV105LocationIcons or {})[target["marker"]["name"]]
        self.assertTrue(icon is None or not icon.visible)

        # Check "Completionist" filter (kind=-101)
        lua.globals().selectFilter(ui, -101)
        icon = (ui.completionistMapV105LocationIcons or {})[target["marker"]["name"]]
        self.assertTrue(icon is None or not icon.visible)

        # Check family filter
        family = target["family"]
        family_filter = next(c["filter"] for c in self.config["categories"]
                             if c["family"] == family)
        lua.globals().selectFilter(ui, family_filter)
        icon = (ui.completionistMapV105LocationIcons or {})[target["marker"]["name"]]
        self.assertTrue(icon is None or not icon.visible)

    def test_older_save_restores_collected_pin(self):
        """After epoch boundary (save switch), collected pins reappear if new save says remaining."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui), len(midgard) - 1)

        # Simulate loading an older save: new epoch
        store.BeginEpoch(store, 2)
        store.Observe(store, target["catalogue_id"], "remaining", 2)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui), len(midgard))

    def test_collected_target_clears_compass(self):
        """Tracking a pin that becomes collected should clear the compass target."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        state = lua.table_from({"menu": lua.table()})
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]

        # Track the target
        lua.globals().selectIcon(ui, target["marker"]["name"], False)
        lua.globals().MapOn.ShowOnCompass(ui, state)
        self.assertEqual(lua.globals().targetCount(), 1)

        # Collect it
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)

        # Update should clear compass target
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().targetCount(), 0)

    def test_selected_collected_pin_loses_selection(self):
        """If the selected pin becomes collected, selection should clear on sync."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]

        # Select the pin
        lua.globals().selectIcon(ui, target["marker"]["name"], False)
        self.assertIsNotNone(ui.completionistMapV105LocationSelected)

        # Collect it
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)

        # After sync, collected pin should be recycled and selection cleared
        icons = ui.completionistMapV105LocationIcons
        pin_icon = icons[target["marker"]["name"]] if icons else None
        self.assertTrue(pin_icon is None or not pin_icon.visible)

    def test_state_publish_global_function(self):
        """The global publish function should accept and route state observations."""
        lua = self.runtime(with_state=True)
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        midgard = self.midgard_rows()
        target = midgard[0]

        # Publish via global function
        result = lua.globals().CompletionistMapV105PublishLocationState(
            target["catalogue_id"], "collected", 1)
        self.assertTrue(result)
        self.assertEqual(store.Get(store, target["catalogue_id"]), "collected")

        # Unknown ID rejected
        result = lua.globals().CompletionistMapV105PublishLocationState(
            "not_real_id", "collected", 1)
        self.assertFalse(result)

    def test_duplicate_collection_no_effect(self):
        """Multiple collected events for the same pin should not cause issues."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)
        count1 = lua.globals().iconCount(ui)
        # Observe again
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui), count1)

    def test_delayed_snapshot_cannot_revive_collected(self):
        """A snapshot saying 'remaining' after live collection cannot bring pin back."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        # Live collection
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)
        count = lua.globals().iconCount(ui)
        # Delayed snapshot says remaining
        store.ApplySnapshot(store, lua.table_from({target["catalogue_id"]: "remaining"}), 1)
        lua.globals().MapOn.Update(ui)
        self.assertEqual(lua.globals().iconCount(ui), count)
        self.assertEqual(store.Get(store, target["catalogue_id"]), "collected")

    def test_without_state_service_all_pins_visible(self):
        """When no state service is wired, all pins should remain visible (backward compat)."""
        lua = self.runtime(with_state=False)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        self.assertEqual(lua.globals().iconCount(ui), len(midgard))

    def test_filter_cycling_does_not_revive_collected(self):
        """Cycling through filters cannot bring back a collected pin."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        target = midgard[0]
        family_filter = next(c["filter"] for c in self.config["categories"]
                             if c["family"] == target["family"])
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, target["catalogue_id"], "collected", 1)
        lua.globals().MapOn.Update(ui)

        # Cycle through All -> Completionist -> family -> back to All
        for kind in (1, -101, family_filter, 1):
            lua.globals().selectFilter(ui, kind)
            icon = (ui.completionistMapV105LocationIcons or {})[target["marker"]["name"]]
            self.assertTrue(icon is None or not icon.visible,
                            f"Collected pin visible after selecting filter {kind}")

    def test_reticle_caption_shows_not_collected(self):
        """Proved remaining pins should show 'Not collected' caption."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        store.Observe(store, midgard[0]["catalogue_id"], "remaining", 1)

        lua.globals().selectIcon(ui, midgard[0]["marker"]["name"], False)
        self.assertEqual(ui.description, "Not collected")

    def test_reticle_caption_shows_generic_for_unknown(self):
        """Unproved/unknown pins should show 'Collectible location' caption."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        # Don't set any state (stays unknown)
        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)
        lua.globals().selectIcon(ui, midgard[0]["marker"]["name"], False)
        self.assertEqual(ui.description, "Collectible location")

    def test_all_families_collected_leaves_empty_filter(self):
        """If all pins in a family are collected, that family filter shows nothing."""
        lua = self.runtime(with_state=True)
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)

        store = lua.globals().CompletionistMapV105LocationState
        store.BeginEpoch(store, 1)

        # Find a family with pins in Midgard and collect them all
        midgard = self.midgard_rows()
        families = Counter(row["family"] for row in midgard)
        # Pick the smallest family for efficiency
        target_family = min(families, key=families.get)
        family_rows = [r for r in midgard if r["family"] == target_family]
        for row in family_rows:
            store.Observe(store, row["catalogue_id"], "collected", 1)

        lua.globals().MapOn.Update(ui)
        family_filter = next(c["filter"] for c in self.config["categories"]
                             if c["family"] == target_family)
        lua.globals().selectFilter(ui, family_filter)
        self.assertEqual(lua.globals().iconCount(ui), 0)

    def test_direct_engine_observations_hide_pins(self):
        """Quests and Wallets in game engine directly hide finished/collected pins."""
        lua = self.runtime(with_state=True)
        lua.execute('''
          game.QuestManager = {
            GetQuestState = function(q)
              if q == "Quest_TreasureMap_BlackBreath" then return "Complete" end
              if q == "Quest_TreasureMap_IslandClimb_Parent" then return "Active" end
              return "Inactive"
            end
          }
          game.Wallets = {
            HasResource = function(wallet, res)
              if res == "Tryptich_Skadi" or res == "ForestChisel_Lore" or res == "CAL_250_Lore_02" then
                return true
              end
              return false
            end,
            GetResourceValue = function(wallet, res)
              if res == "Tryptich_Skadi" or res == "ForestChisel_Lore" or res == "CAL_250_Lore_02" then
                return 1
              end
              return 0
            end
          }
        ''')
        ui = lua.globals().makeMap("Midgard")
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)

        icons = ui.completionistMapV105LocationIcons or {}
        dig_icon = icons["Completionist_V105_TreasureDig_5f6d01b68cdf70a9"]
        self.assertTrue(dig_icon is None or not dig_icon.visible, "Completed dig pin must be hidden")

        map_icon = icons["Completionist_V105_TreasureMap_4011675d69434ff5"]
        self.assertTrue(map_icon is None or not map_icon.visible, "Acquired map pin must be hidden")

        shrine_icon = icons["Completionist_V105_JotnarShrine_4f54c8b2f4d92780"]
        self.assertTrue(shrine_icon is None or not shrine_icon.visible, "Read shrine pin must be hidden")

        scroll_icon = icons["Completionist_V105_LoreScroll_dc56801cbe1e7d3c"]
        self.assertTrue(scroll_icon is None or not scroll_icon.visible, "Read scroll pin must be hidden")

        marker_icon = icons["Completionist_V105_LoreMarker_91a1de27cf22bbaf"]
        self.assertTrue(marker_icon is None or not marker_icon.visible, "Read lore marker pin must be hidden")

    def test_show_all_clean_by_default_and_dpad_down_toggle(self):
        """SHOW ALL (kind==1) is clean by default, and D-Pad Down toggles completionist markers."""
        lua = self.runtime(with_state=True)
        # Create map with enableShowAll=False (clean default in actual game)
        ui = lua.globals().makeMap("Midgard", False)
        lua.globals().MapOn.UpdateFilterButtonMapping(ui)
        lua.globals().CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        total = len(midgard)

        # 1. Clean default on SHOW ALL
        self.assertEqual(lua.globals().iconCount(ui), 0)

        # 2. Press D-Pad Down (EVT_Down_Release) -> toggles SHOW ALL on
        ui.EVT_Down_Release(ui)
        self.assertEqual(lua.globals().iconCount(ui), total)

        # 3. Press D-Pad Down again -> toggles SHOW ALL off
        ui.EVT_Down_Release(ui)
        self.assertEqual(lua.globals().iconCount(ui), 0)

        # 4. Switch to category filter (-101 COMPLETIONIST) -> visible by default
        lua.globals().selectFilter(ui, -101)
        self.assertEqual(lua.globals().iconCount(ui), total)

        # 5. Press D-Pad Down on category filter -> toggles category markers off
        ui.EVT_Down_Release(ui)
        self.assertEqual(lua.globals().iconCount(ui), 0)

        # 6. Press D-Pad Down on category filter again -> toggles category markers back on
        ui.EVT_Down_Release(ui)
        self.assertEqual(lua.globals().iconCount(ui), total)

        # 7. Fast travel mode ignores D-Pad Down
        ui.isOpenedForFastTravel = True
        ui.EVT_Down_Release(ui)
        self.assertEqual(lua.globals().iconCount(ui), total)
        ui.isOpenedForFastTravel = False

        # 8. Closing the map preserves persistent toggles across map opens
        lua.globals().MapOn.Exit(ui)
        self.assertFalse(lua.globals().CompletionistMapV105ShowAll())
        self.assertTrue(lua.globals().CompletionistMapV105ShowCategories())

    def test_persistent_show_all_defaults_to_true_and_persists_across_map_opens(self):
        """Persistent ShowAll defaults to true so user does not have to show markers every time map opens."""
        lua = self.runtime(with_state=True)
        g = lua.globals()
        # Default initialization without enableShowAll=False defaults to true
        self.assertTrue(g.CompletionistMapV105ShowAll())
        self.assertTrue(g.CompletionistMapV105ShowCategories())

        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        g.CompletionistMapV100_CreateMapPin(ui)
        midgard = self.midgard_rows()
        # Markers are visible immediately upon opening the map
        self.assertEqual(g.iconCount(ui), len(midgard))

        # User closes the map
        g.MapOn.Exit(ui)
        # Setting remains persistent
        self.assertTrue(g.CompletionistMapV105ShowAll())

        # Next map open retains the user's setting
        ui2 = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui2)
        g.CompletionistMapV100_CreateMapPin(ui2)
        self.assertEqual(g.iconCount(ui2), len(midgard))

    def test_footer_button_prompt_shows_completionist_toggle(self):
        """Footer bar displays [DownButton] Show/Hide Markers on screen."""
        lua = self.runtime(production=True)
        g = lua.globals()
        ui = g.makeMap("Midgard")
        g.MapOn.UpdateFilterButtonMapping(ui)
        buttons = {}
        menu = lua.table_from({
            "buttons": lua.table(),
        })
        lua.execute('''
          testMenu = {buttons = {}, updated = false}
          function testMenu:UpdateFooterButton(name, show, text)
            self.buttons[name] = {show = show, text = text}
          end
          function testMenu:UpdateFooterButtonText()
            self.updated = true
          end
        ''')
        test_menu = lua.globals().testMenu

        # Filter 1 (SHOW ALL) with ShowAll=true
        g.CompletionistMapV105ShowAll(True)
        g.MapOn.UpdateFooterButtonPrompt(ui, test_menu, False, False)
        self.assertTrue(test_menu.buttons["ActiveMarkers"]["show"])
        self.assertEqual(test_menu.buttons["ActiveMarkers"]["text"], "[DownButton] Hide Markers")
        self.assertTrue(test_menu.updated)

        # Toggle to ShowAll=false
        g.CompletionistMapV105ShowAll(False)
        g.MapOn.UpdateFooterButtonPrompt(ui, test_menu, False, False)
        self.assertTrue(test_menu.buttons["ActiveMarkers"]["show"])
        self.assertEqual(test_menu.buttons["ActiveMarkers"]["text"], "[DownButton] Show Markers")

        # Category filter (-101) with ShowCategories=true
        g.selectFilter(ui, -101)
        g.CompletionistMapV105ShowCategories(True)
        g.MapOn.UpdateFooterButtonPrompt(ui, test_menu, False, False)
        self.assertTrue(test_menu.buttons["ActiveMarkers"]["show"])
        self.assertEqual(test_menu.buttons["ActiveMarkers"]["text"], "[DownButton] Hide Markers")

        # Fast travel hides the toggle prompt
        ui.isOpenedForFastTravel = True
        g.MapOn.UpdateFooterButtonPrompt(ui, test_menu, False, False)
        self.assertFalse(test_menu.buttons["ActiveMarkers"]["show"])



if __name__ == "__main__":
    unittest.main()
