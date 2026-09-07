-- BEGIN COMPLETIONIST V0.10.4 RAVEN MAP CLASS CONTROL PROOF
--
-- Purpose: prove that an authored Completionist marker can render through its
-- own map Icon resource without creating or borrowing a Dock marker GO.
--
-- This control uses an EXISTING stock map resource (Valkyrie artwork) while
-- leaving the authored marker's compass/navigation flag as DockPoint.  If the
-- Raven appears as a Valkyrie marker and real docks remain docks, the map Icon
-- field is proven independent from the compass class.  There is intentionally
-- no Dock fallback: failure must produce no Raven pin rather than hiding the
-- failure behind a Dock proxy.
do
  local prefix = "[CompletionistMap v0.10.4-map-class-control] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local expectedMapResource = "goMapIconValkyrie_location"

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

  local function getRegionId(info)
    local names = {"regionId", "RegionId", "RegionID", "regionID"}
    for _, name in ipairs(names) do
      local value = safeField(info, name)
      if value ~= nil then return value, "marker_info." .. name end
    end

    local ok, region = pcall(function()
      return game.Map.FindRegionFromMarker(candidate)
    end)
    if not ok or region == nil then
      return nil, "unresolved"
    end
    if type(region) == "table" then
      for _, name in ipairs({"Id", "id", "regionId", "RegionId"}) do
        local value = safeField(region, name)
        if value ~= nil then return value, "FindRegionFromMarker." .. name end
      end
      return nil, "region_table_without_id"
    end
    return region, "FindRegionFromMarker.direct"
  end

  -- Do not retain the v0.10.1 Dock-backed creator as a fallback.  The entire
  -- point of this proof is to make success/failure of the authored map class
  -- unambiguous.
  CompletionistMapV100_CreateMapPin = function(self, currState)
    if self == nil or self.currRealmName ~= "Midgard" then
      return
    end

    CompletionistMapV100_DestroyMapPin(self)
    if CompletionistMapV100_IsRavenCollected() then
      log("DIRECT_RESULT", "active=false reason=raven_collected dockProxyUsed=false")
      return
    end

    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not infoOK or info == nil then
      log("DIRECT_RESULT",
        "active=false reason=marker_info_failed dockProxyUsed=false error=" .. tostring(info))
      return
    end

    local markerId = safeField(info, "Id") or safeField(info, "id")
    local markerIcon = safeField(info, "Icon") or safeField(info, "icon") or
      safeField(info, "IconName") or safeField(info, "iconName")
    local markerState = safeField(info, "State") or safeField(info, "state")
    local regionId, regionSource = getRegionId(info)

    log("PREFLIGHT",
      "candidate=" .. candidate ..
      " id=" .. tostring(markerId) ..
      " icon=" .. tostring(markerIcon) ..
      " state=" .. tostring(markerState) ..
      " region=" .. tostring(regionId) ..
      " regionSource=" .. tostring(regionSource) ..
      " expectedMapResource=" .. expectedMapResource ..
      " compassType=DockPoint" ..
      " dockProxyUsed=false")

    if markerId == nil or regionId == nil then
      log("DIRECT_RESULT", "active=false reason=id_or_region_unresolved dockProxyUsed=false")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(markerId, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("DIRECT_RESULT",
        "active=false reason=CreateMarkerIcon_failed dockProxyUsed=false error=" .. tostring(newGO))
      return
    end

    local clickableOK, clickableErr = pcall(function()
      UI.SetIsClickable(newGO)
    end)
    local showOK, showErr = pcall(function()
      newGO:Show()
    end)
    if not showOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("DIRECT_RESULT",
        "active=false reason=show_failed dockProxyUsed=false error=" .. tostring(showErr))
      return
    end

    self.completionistMapV100MapIconGO = newGO
    self.completionistMapV100MapIconFrames = 0
    CompletionistMapV100_LogIconCapabilities(newGO, "raven_map_class_control")

    local posOK, pos = pcall(function() return newGO:GetWorldPosition() end)
    log("DIRECT_RESULT",
      "active=true" ..
      " candidate=" .. candidate ..
      " resourceExpected=" .. expectedMapResource ..
      " goName=" .. safeName(newGO) ..
      " clickableOK=" .. tostring(clickableOK) ..
      " clickableError=" .. tostring(clickableErr) ..
      " nativePlacement=" .. tostring(posOK and pos ~= nil) ..
      " position=" .. (posOK and pos ~= nil and
        ("x=" .. tostring(pos.x) .. ",y=" .. tostring(pos.y) .. ",z=" .. tostring(pos.z))
        or "<unavailable>") ..
      " dockProxyUsed=false")
  end

  log("API",
    "installed=true candidate=" .. candidate ..
    " mapResourceControl=" .. expectedMapResource ..
    " compassType=DockPoint" ..
    " dockProxyUsed=false" ..
    " callsOnLoad=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN MAP CLASS CONTROL PROOF
