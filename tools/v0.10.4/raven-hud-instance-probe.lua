  -- BEGIN COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE
  -- Read-only runtime inventory. This does not show/hide/move/retexture markers,
  -- call Compass.ShowMarker, or write progression/save state.
  do
    local prefix = "[CompletionistMap v0.10.4-hud-probe] "
    local candidate = "Completionist_V103_Veithurgard_Raven_01"

    local function log(kind, fields)
      print(prefix .. tostring(kind) .. " " .. tostring(fields or ""))
    end

    local function safeName(go)
      if go == nil then return "<nil>" end
      local ok, value = pcall(function() return go:GetName() end)
      if ok and value ~= nil then return tostring(value) end
      return "<unavailable>"
    end

    local function safePosition(go)
      if go == nil then return "<nil>" end
      local ok, value = pcall(function() return go:GetWorldPosition() end)
      if ok and value ~= nil then
        return "x=" .. tostring(value.x) ..
          ",y=" .. tostring(value.y) ..
          ",z=" .. tostring(value.z)
      end
      return "<unavailable>"
    end

    local function safeParentName(go)
      if go == nil then return "<nil>" end
      local ok, parent = pcall(function() return go.Parent end)
      if not ok or parent == nil then return "<none>" end
      return safeName(parent)
    end

    local function callable(go, name)
      if go == nil then return false end
      local ok, value = pcall(function() return go[name] end)
      return ok and type(value) == "function"
    end

    local function idsContain(ids, wanted)
      if type(ids) ~= "table" or wanted == nil then return false end
      for _, id in ipairs(ids) do
        if tostring(id) == tostring(wanted) then return true end
      end
      return false
    end

    -- Do not trust the mapmenu _G flag here. mainhud.lua can run in a distinct
    -- script environment, so ask the native Compass manager directly.
    local function nativeTrackingState()
      local okInfo, info = pcall(function()
        return game.Map.GetMarkerInfo(candidate)
      end)
      if not okInfo or info == nil then
        log("TRACK_QUERY",
          "candidate=" .. candidate ..
          " infoOK=" .. tostring(okInfo) ..
          " registered=false error=" .. tostring(okInfo and "<none>" or info))
        return false
      end

      local candidateId = info.Id
      local anyQueryOK = false
      local tracked = false

      -- First use the exact flag set used by the production map bridge when it
      -- is visible in this script environment.
      local flags = enabledShowOnCompassMarkerFlags
      if flags ~= nil then
        local okIds, ids = pcall(function()
          return game.Compass.FindMarkersByIconClass(flags)
        end)
        anyQueryOK = anyQueryOK or okIds
        if okIds and idsContain(ids, candidateId) then tracked = true end
        log("TRACK_QUERY",
          "mode=enabledFlags candidateId=" .. tostring(candidateId) ..
          " ok=" .. tostring(okIds) ..
          " count=" .. tostring(okIds and type(ids) == "table" and #ids or -1) ..
          " tracked=" .. tostring(okIds and idsContain(ids, candidateId)) ..
          " error=" .. tostring(okIds and "<none>" or ids))
      else
        log("TRACK_QUERY",
          "mode=enabledFlags candidateId=" .. tostring(candidateId) ..
          " ok=false unavailable=true")
      end

      -- Fallback: DockPoint is the class actually passed to ShowMarker for the
      -- Raven. This is also read-only and gives mainhud a second independent
      -- way to observe the manager's active marker list.
      local markerType = consts ~= nil and consts.COMPASS_MARKER_TYPE_DOCK_POINT or nil
      if markerType ~= nil then
        local okDock, dockIds = pcall(function()
          return game.Compass.FindMarkersByIconClass({markerType})
        end)
        anyQueryOK = anyQueryOK or okDock
        if okDock and idsContain(dockIds, candidateId) then tracked = true end
        log("TRACK_QUERY",
          "mode=dockType candidateId=" .. tostring(candidateId) ..
          " markerType=" .. tostring(markerType) ..
          " ok=" .. tostring(okDock) ..
          " count=" .. tostring(okDock and type(dockIds) == "table" and #dockIds or -1) ..
          " tracked=" .. tostring(okDock and idsContain(dockIds, candidateId)) ..
          " error=" .. tostring(okDock and "<none>" or dockIds))
      else
        log("TRACK_QUERY",
          "mode=dockType candidateId=" .. tostring(candidateId) ..
          " ok=false unavailable=true")
      end

      log("TRACK_STATE",
        "candidateId=" .. tostring(candidateId) ..
        " queryOK=" .. tostring(anyQueryOK) ..
        " tracked=" .. tostring(tracked) ..
        " mapGlobal=" .. tostring(_G.CompletionistMapV103NativeRavenTracked == true))
      return tracked
    end

    local roots = {}
    local rootKeys = {}

    local function addRoot(label, go)
      if go == nil then
        log("ROOT", "label=" .. tostring(label) .. " nil=true")
        return
      end

      local key = tostring(go)
      if rootKeys[key] then
        log("ROOT_ALIAS",
          "label=" .. tostring(label) ..
          " goName=" .. safeName(go) ..
          " existing=" .. tostring(rootKeys[key]))
        return
      end

      rootKeys[key] = label
      roots[#roots + 1] = {label = label, go = go}
      log("ROOT",
        "label=" .. tostring(label) ..
        " goName=" .. safeName(go) ..
        " parent=" .. safeParentName(go) ..
        " world=" .. safePosition(go) ..
        " findSingle=" .. tostring(callable(go, "FindSingleGOByName")) ..
        " findMany=" .. tostring(callable(go, "FindGOsByName")) ..
        " materialSwap=" .. tostring(callable(go, "SetMaterialSwap")) ..
        " addChild=" .. tostring(callable(go, "AddChild")) ..
        " unparent=" .. tostring(callable(go, "Unparent")))
    end

    local function uiRoot(name)
      local ok, value = pcall(function() return util.GetUiObjByName(name) end)
      if not ok then
        log("UI_LOOKUP", "query=" .. tostring(name) .. " ok=false error=" .. tostring(value))
        return nil
      end
      if value ~= nil then
        log("UI_LOOKUP",
          "query=" .. tostring(name) ..
          " ok=true goName=" .. safeName(value) ..
          " world=" .. safePosition(value))
      else
        log("UI_LOOKUP", "query=" .. tostring(name) .. " ok=true nil=true")
      end
      return value
    end

    addRoot("self.compassObj", self.compassObj)
    addRoot("self.compassBase", self.compassBase)
    addRoot("self.compassRadius", self.compassRadius)
    addRoot("ui.Compass", uiRoot("Compass"))
    addRoot("ui.Compass_Base", uiRoot("Compass_Base"))
    addRoot("ui.Compass_Radius", uiRoot("Compass_Radius"))
    addRoot("ui.mainHUD", uiRoot("mainHUD"))
    addRoot("ui.UI_Elements", uiRoot("UI_Elements"))

    local candidates = {
      "boatdock", "BoatDock", "goboatdock", "goBoatDock",
      "dock", "Dock", "DockPoint", "dockpoint",
      "compass", "Compass", "compass_base", "Compass_Base",
      "compass_radius", "Compass_Radius", "compassmarker", "CompassMarker",
      "compass_marker", "Compass_Marker", "compassicon", "CompassIcon",
      "marker", "Marker", "marker_icon", "MarkerIcon",
      "diamond", "Diamond", "arrow", "Arrow", "radius", "Radius",
      "mainquest", "MainQuest", "sidequest", "SideQuest",
      "vendor", "Vendor", "fasttravel", "FastTravel",
      "fight", "Fight", "area", "Area", "valkyrie", "Valkyrie",
      "mainquestworld", "sidequestworld", "vendorworld", "fasttravelworld",
      "fightworld", "areaworld", "dockworld", "valkyrieworld"
    }

    local reportedHits = {}

    local function reportGO(reason, rootLabel, query, go, ordinal)
      if go == nil then return end
      local key = tostring(go) .. "|" .. tostring(reason) .. "|" .. tostring(query)
      if reportedHits[key] then return end
      reportedHits[key] = true
      log("HIT",
        "reason=" .. tostring(reason) ..
        " root=" .. tostring(rootLabel) ..
        " query=" .. tostring(query) ..
        " ordinal=" .. tostring(ordinal or 1) ..
        " goName=" .. safeName(go) ..
        " parent=" .. safeParentName(go) ..
        " world=" .. safePosition(go) ..
        " materialSwap=" .. tostring(callable(go, "SetMaterialSwap")) ..
        " findSingle=" .. tostring(callable(go, "FindSingleGOByName")) ..
        " findMany=" .. tostring(callable(go, "FindGOsByName")))
    end

    local function scan(reason)
      local tracked = nativeTrackingState()
      log("SCAN_BEGIN",
        "reason=" .. tostring(reason) ..
        " tracked=" .. tostring(tracked) ..
        " roots=" .. tostring(#roots))

      for _, root in ipairs(roots) do
        for _, query in ipairs(candidates) do
          if callable(root.go, "FindSingleGOByName") then
            local okSingle, single = pcall(function()
              return root.go:FindSingleGOByName(query)
            end)
            if okSingle and single ~= nil then
              reportGO("single", root.label, query, single, 1)
            end
          end

          if callable(root.go, "FindGOsByName") then
            local okMany, many = pcall(function()
              return root.go:FindGOsByName(query)
            end)
            if okMany and type(many) == "table" then
              for i, go in ipairs(many) do
                reportGO("many", root.label, query, go, i)
              end
            elseif okMany and many ~= nil and type(many) ~= "boolean" then
              reportGO("many_non_table", root.label, query, many, 1)
            end
          end
        end
      end

      log("SCAN_END",
        "reason=" .. tostring(reason) ..
        " tracked=" .. tostring(tracked))
    end

    -- mainhud.lua is instantiated again when returning from the map to gameplay.
    -- Scan immediately on script load. The native manager query above determines
    -- tracking state without relying on mapmenu globals crossing script contexts.
    scan("script_load")

    self.completionistMapV104HudProbeFrame = 0
    self.completionistMapV104HudProbeLastTracked = nil

    local completionistMapV104HudProbeOriginalUpdate = self.Update
    self.Update = function(...)
      if completionistMapV104HudProbeOriginalUpdate ~= nil then
        completionistMapV104HudProbeOriginalUpdate(...)
      end

      self.completionistMapV104HudProbeFrame =
        (self.completionistMapV104HudProbeFrame or 0) + 1

      local tracked = nativeTrackingState()
      local frame = self.completionistMapV104HudProbeFrame
      local reason = nil

      if frame == 1 then
        reason = "frame_1"
      elseif frame == 180 then
        reason = "frame_180"
      elseif frame == 600 then
        reason = "frame_600"
      elseif self.completionistMapV104HudProbeLastTracked == nil or
          tracked ~= self.completionistMapV104HudProbeLastTracked then
        reason = "tracked_change"
      end

      self.completionistMapV104HudProbeLastTracked = tracked
      if reason ~= nil then scan(reason) end
    end

    log("API",
      "installed=true readOnly=true callsShowMarker=false callsHideMarker=false" ..
      " movesGO=false hidesGO=false materialWrites=false saveWrites=false" ..
      " nativeTrackingQuery=true" ..
      " dockIconHash=82F0296748C7393D" ..
      " inWorldHash=0E24C47DE2F769CA")
  end
  -- END COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE