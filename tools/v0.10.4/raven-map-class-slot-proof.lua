-- BEGIN COMPLETIONIST V0.10.4 RAVEN MAP CLASS SLOT PROOF
--
-- Proves a custom Completionist map-class name can occupy an existing dormant
-- WAD_R_UI GOPool slot without growing or replacing r_ui.wad.  The temporary
-- donor slot is stock goMapIconCube, renamed in wad_r_ui.dcb to
-- goMapIconCompletionistRaven.  The underlying stock WAD resource remains the
-- Cube/debug visual for this diagnostic.  There is no Dock map proxy.
do
  local prefix = "[CompletionistMap v0.10.4-map-class-slot] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local expectedMapResource = "goMapIconCompletionistRaven"
  local donorResource = "goMapIconCube"

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function safeField(tab, name)
    if tab == nil then return nil end
    local ok, value = pcall(function() return tab[name] end)
    if ok then return value end
    return nil
  end

  local function safeName(go)
    if go == nil then return "<nil>" end
    local ok, value = pcall(function() return go:GetName() end)
    if ok and value ~= nil then return tostring(value) end
    return "<name-unavailable>"
  end

  local function getRegionId(info, markerId)
    for _, name in ipairs({"regionId", "RegionId", "RegionID", "regionID"}) do
      local value = safeField(info, name)
      if value ~= nil then return value, "marker_info." .. name end
    end

    local callOK, found, region = pcall(function()
      return game.Map.FindRegionFromMarker(markerId)
    end)
    if not callOK then
      return nil, "FindRegionFromMarker.error=" .. tostring(found)
    end
    if found ~= true or region == nil then
      return nil, "FindRegionFromMarker.not_found"
    end
    return region, "FindRegionFromMarker.region"
  end

  CompletionistMapV100_CreateMapPin = function(self, currState)
    if self == nil or self.currRealmName ~= "Midgard" then return end

    CompletionistMapV100_DestroyMapPin(self)
    if CompletionistMapV100_IsRavenCollected() then
      log("SLOT_RESULT", "active=false reason=raven_collected dockProxyUsed=false")
      return
    end

    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not infoOK or info == nil then
      log("SLOT_RESULT", "active=false reason=marker_info_failed error=" .. tostring(info) .. " dockProxyUsed=false")
      return
    end

    local markerId = safeField(info, "Id") or safeField(info, "id")
    local markerState = safeField(info, "State") or safeField(info, "state")
    local regionId, regionSource = getRegionId(info, markerId)

    log("SLOT_PREFLIGHT",
      "candidate=" .. candidate ..
      " id=" .. tostring(markerId) ..
      " state=" .. tostring(markerState) ..
      " region=" .. tostring(regionId) ..
      " regionType=" .. tostring(type(regionId)) ..
      " regionSource=" .. tostring(regionSource) ..
      " expectedMapResource=" .. expectedMapResource ..
      " donorResource=" .. donorResource ..
      " compassType=DockPoint" ..
      " dockProxyUsed=false")

    if markerId == nil or regionId == nil then
      log("SLOT_RESULT", "active=false reason=id_or_region_unresolved dockProxyUsed=false")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(markerId, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("SLOT_RESULT", "active=false reason=CreateMarkerIcon_failed error=" .. tostring(newGO) .. " dockProxyUsed=false")
      return
    end

    local clickableOK, clickableErr = pcall(function() UI.SetIsClickable(newGO) end)
    local showOK, showErr = pcall(function() newGO:Show() end)
    if not showOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("SLOT_RESULT", "active=false reason=show_failed error=" .. tostring(showErr) .. " dockProxyUsed=false")
      return
    end

    self.completionistMapV100MapIconGO = newGO
    self.completionistMapV100MapIconFrames = 0
    CompletionistMapV100_LogIconCapabilities(newGO, "raven_map_class_slot")

    local posOK, pos = pcall(function() return newGO:GetWorldPosition() end)
    log("SLOT_RESULT",
      "active=true" ..
      " candidate=" .. candidate ..
      " resourceExpected=" .. expectedMapResource ..
      " donorResource=" .. donorResource ..
      " goName=" .. safeName(newGO) ..
      " clickableOK=" .. tostring(clickableOK) ..
      " clickableError=" .. tostring(clickableErr) ..
      " nativePlacement=" .. tostring(posOK and pos ~= nil) ..
      " position=" .. (posOK and pos ~= nil and
        ("x=" .. tostring(pos.x) .. ",y=" .. tostring(pos.y) .. ",z=" .. tostring(pos.z)) or "<unavailable>") ..
      " dockProxyUsed=false")
  end

  log("API",
    "installed=true candidate=" .. candidate ..
    " mapResource=" .. expectedMapResource ..
    " donorResource=" .. donorResource ..
    " compassType=DockPoint" ..
    " stockWadUnchanged=true" ..
    " dockProxyUsed=false" ..
    " callsOnLoad=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN MAP CLASS SLOT PROOF
