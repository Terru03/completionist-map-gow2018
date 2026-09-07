-- BEGIN COMPLETIONIST V0.10.4 RAVEN MAP VISUAL PROOF
-- Replaces only the v0.10.1 synthetic Raven map pin after it has been created.
-- The native authored Raven marker supplies the dedicated map icon resource.
-- Compass navigation remains v0.10.3 DockPoint internally.
do
  local prefix = "[CompletionistMap v0.10.4-raven-map-visual] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local originalCreateMapPin = CompletionistMapV100_CreateMapPin

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function getRegionId(info)
    if info ~= nil then
      local direct = info.regionId or info.RegionId or info.RegionID or info.regionID
      if direct ~= nil then return direct, "marker_info" end
    end

    local ok, region = pcall(function()
      return game.Map.FindRegionFromMarker(candidate)
    end)
    if ok and region ~= nil then
      if type(region) == "table" then
        local id = region.Id or region.id or region.regionId or region.RegionId
        if id ~= nil then return id, "find_region_table" end
      end
      return region, "find_region_direct"
    end
    return nil, "unresolved"
  end

  CompletionistMapV100_CreateMapPin = function(self, currState)
    originalCreateMapPin(self, currState)

    if self == nil or self.currRealmName ~= "Midgard" then return end
    if CompletionistMapV100_IsRavenCollected() then return end

    local oldGO = self.completionistMapV100MapIconGO
    if oldGO == nil then
      log("MAP_VISUAL_RESULT", "active=false reason=stock_completionist_pin_missing")
      return
    end

    local okInfo, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not okInfo or info == nil then
      log("MAP_VISUAL_RESULT", "active=false reason=native_candidate_missing error=" .. tostring(info))
      return
    end

    local regionId, regionSource = getRegionId(info)
    if regionId == nil then
      log("MAP_VISUAL_RESULT", "active=false reason=region_unresolved")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(info.Id, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("MAP_VISUAL_RESULT",
        "active=false reason=create_failed regionSource=" .. tostring(regionSource) ..
        " error=" .. tostring(newGO))
      return
    end

    local posOK, pos = pcall(function() return oldGO:GetWorldPosition() end)
    local scaleOK, scale = pcall(function() return oldGO:GetWorldScale() end)
    if not posOK or pos == nil then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("MAP_VISUAL_RESULT", "active=false reason=old_pin_position_unavailable")
      return
    end

    local setOK, setErr = pcall(function()
      newGO:SetWorldPosition(pos)
      if scaleOK and scale ~= nil then
        newGO:SetWorldScale(scale)
      end
      newGO:Show()
    end)
    if not setOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("MAP_VISUAL_RESULT", "active=false reason=placement_failed error=" .. tostring(setErr))
      return
    end

    pcall(function() Map.RecycleIcon(oldGO) end)
    self.completionistMapV100MapIconGO = newGO

    CompletionistMapV100_LogIconCapabilities(newGO, "raven_v104_dedicated")
    log("MAP_VISUAL_RESULT",
      "active=true candidate=" .. candidate ..
      " id=" .. tostring(info.Id) ..
      " regionSource=" .. tostring(regionSource) ..
      " resource=goMapIconCompletionistRaven" ..
      " oldDockProxyRecycled=true")
  end

  log("MAP_VISUAL_API",
    "installed=true candidate=" .. candidate ..
    " mapResource=goMapIconCompletionistRaven" ..
    " compassType=DockPoint")
end
-- END COMPLETIONIST V0.10.4 RAVEN MAP VISUAL PROOF
