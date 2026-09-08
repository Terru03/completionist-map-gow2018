  -- BEGIN COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE
  -- Read-only runtime inventory. This does not show/hide/move/retexture markers,
  -- call Compass.ShowMarker, or write progression/save state.
  do
    local prefix = "[CompletionistMap v0.10.4-hud-probe] "

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
      local tracked = _G.CompletionistMapV103NativeRavenTracked == true
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
    -- Scan immediately on script load so the second instance can observe the Raven
    -- after MapOn.ShowOnCompass has set the native tracked flag.
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

      local tracked = _G.CompletionistMapV103NativeRavenTracked == true
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
      " dockIconHash=82F0296748C7393D" ..
      " inWorldHash=0E24C47DE2F769CA")
  end
  -- END COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE