-- BEGIN COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF
--
-- Field proof for the corrected, grown r_ui.wad candidate. The authored Raven
-- marker points directly at goMapIconCompletionistRaven. No Dock map proxy is
-- created. The visual payload still carries cloned stock Dock pixels at this
-- gate on purpose; custom Raven texpack artwork is a separate later variable.
do
  local prefix = "[CompletionistMap v0.10.4-raven-registered-runtime] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local expectedMapResource = "goMapIconCompletionistRaven"

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
      log("REGISTERED_RESULT", "active=false reason=raven_collected dockProxyUsed=false")
      return
    end

    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not infoOK or info == nil then
      log("REGISTERED_RESULT",
        "active=false reason=marker_info_failed dockProxyUsed=false error=" .. tostring(info))
      return
    end

    local markerId = safeField(info, "Id") or safeField(info, "id")
    local markerIcon = safeField(info, "Icon") or safeField(info, "icon") or
      safeField(info, "IconName") or safeField(info, "iconName")
    local markerState = safeField(info, "State") or safeField(info, "state")
    local regionId, regionSource = getRegionId(info, markerId)

    log("REGISTERED_PREFLIGHT",
      "candidate=" .. candidate ..
      " id=" .. tostring(markerId) ..
      " authoredIcon=" .. tostring(markerIcon) ..
      " state=" .. tostring(markerState) ..
      " region=" .. tostring(regionId) ..
      " regionType=" .. tostring(type(regionId)) ..
      " regionSource=" .. tostring(regionSource) ..
      " expectedMapResource=" .. expectedMapResource ..
      " compassType=DockPoint" ..
      " texpackLoaded=false" ..
      " dockProxyUsed=false")

    if markerId == nil or regionId == nil then
      log("REGISTERED_RESULT", "active=false reason=id_or_region_unresolved dockProxyUsed=false")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(markerId, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("REGISTERED_RESULT",
        "active=false reason=CreateMarkerIcon_failed regionSource=" .. tostring(regionSource) ..
        " dockProxyUsed=false error=" .. tostring(newGO))
      return
    end

    local clickableOK, clickableErr = pcall(function() UI.SetIsClickable(newGO) end)
    local showOK, showErr = pcall(function() newGO:Show() end)
    if not showOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("REGISTERED_RESULT",
        "active=false reason=show_failed dockProxyUsed=false error=" .. tostring(showErr))
      return
    end

    self.completionistMapV100MapIconGO = newGO
    self.completionistMapV100MapIconFrames = 0
    CompletionistMapV100_LogIconCapabilities(newGO, "raven_registered_class_runtime")

    local goName = safeName(newGO)
    local posOK, pos = pcall(function() return newGO:GetWorldPosition() end)
    local looksLikeDedicatedName = string.find(string.lower(goName), "completionistraven", 1, true) ~= nil
    local isDockGO = string.lower(goName) == "mapicondock"

    log("REGISTERED_RESULT",
      "active=true" ..
      " candidate=" .. candidate ..
      " resourceExpected=" .. expectedMapResource ..
      " goName=" .. goName ..
      " dedicatedNameObserved=" .. tostring(looksLikeDedicatedName) ..
      " dockGOObserved=" .. tostring(isDockGO) ..
      " clickableOK=" .. tostring(clickableOK) ..
      " clickableError=" .. tostring(clickableErr) ..
      " nativePlacement=" .. tostring(posOK and pos ~= nil) ..
      " position=" .. (posOK and pos ~= nil and
        ("x=" .. tostring(pos.x) .. ",y=" .. tostring(pos.y) .. ",z=" .. tostring(pos.z)) or "<unavailable>") ..
      " texpackLoaded=false" ..
      " dockProxyUsed=false")
  end

  log("REGISTERED_API",
    "installed=true candidate=" .. candidate ..
    " mapResource=" .. expectedMapResource ..
    " compassType=DockPoint" ..
    " texpackLoaded=false" ..
    " dockProxyUsed=false" ..
    " callsOnLoad=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF
