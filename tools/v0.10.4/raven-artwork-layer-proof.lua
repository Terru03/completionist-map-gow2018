-- BEGIN COMPLETIONIST V0.10.4 RAVEN ARTWORK LAYER PROOF
--
-- Visual-only diagnostic layered on the proven corrected registered class.
-- The custom Raven texpack is active and this bridge renders the dedicated
-- goMapIconCompletionistRaven map object directly. For this diagnostic only,
-- the map icon is allowed to render even when the tested Raven has already been
-- collected so artwork can still be inspected. No marker state, save state,
-- progression value, or native compass state is changed here.
do
  local prefix = "[CompletionistMap v0.10.4-raven-artwork] "
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

    local collected = false
    local collectedOK, collectedValue = pcall(function()
      return CompletionistMapV100_IsRavenCollected()
    end)
    if collectedOK then collected = collectedValue == true end

    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not infoOK or info == nil then
      log("ART_RESULT",
        "active=false reason=marker_info_failed error=" .. tostring(info) ..
        " diagnosticShowEvenIfCollected=true progressionWritten=false")
      return
    end

    local markerId = safeField(info, "Id") or safeField(info, "id")
    local markerState = safeField(info, "State") or safeField(info, "state")
    local regionId, regionSource = getRegionId(info, markerId)

    log("ART_PREFLIGHT",
      "candidate=" .. candidate ..
      " id=" .. tostring(markerId) ..
      " state=" .. tostring(markerState) ..
      " collected=" .. tostring(collected) ..
      " region=" .. tostring(regionId) ..
      " regionType=" .. tostring(type(regionId)) ..
      " regionSource=" .. tostring(regionSource) ..
      " expectedMapResource=" .. expectedMapResource ..
      " texpackLoaded=true" ..
      " diagnosticShowEvenIfCollected=true" ..
      " dockProxyUsed=false" ..
      " progressionWritten=false")

    if markerId == nil or regionId == nil then
      log("ART_RESULT", "active=false reason=id_or_region_unresolved progressionWritten=false")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(markerId, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("ART_RESULT",
        "active=false reason=CreateMarkerIcon_failed error=" .. tostring(newGO) ..
        " progressionWritten=false")
      return
    end

    local clickableOK, clickableErr = pcall(function() UI.SetIsClickable(newGO) end)
    local showOK, showErr = pcall(function() newGO:Show() end)
    if not showOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("ART_RESULT",
        "active=false reason=show_failed error=" .. tostring(showErr) ..
        " progressionWritten=false")
      return
    end

    self.completionistMapV100MapIconGO = newGO
    self.completionistMapV100MapIconFrames = 0
    CompletionistMapV100_LogIconCapabilities(newGO, "raven_artwork_layer")

    local goName = safeName(newGO)
    local posOK, pos = pcall(function() return newGO:GetWorldPosition() end)
    local dedicated = string.find(string.lower(goName), "completionistraven", 1, true) ~= nil

    log("ART_RESULT",
      "active=true" ..
      " candidate=" .. candidate ..
      " resourceExpected=" .. expectedMapResource ..
      " goName=" .. goName ..
      " dedicatedNameObserved=" .. tostring(dedicated) ..
      " collectedAtRender=" .. tostring(collected) ..
      " clickableOK=" .. tostring(clickableOK) ..
      " clickableError=" .. tostring(clickableErr) ..
      " nativePlacement=" .. tostring(posOK and pos ~= nil) ..
      " position=" .. (posOK and pos ~= nil and
        ("x=" .. tostring(pos.x) .. ",y=" .. tostring(pos.y) .. ",z=" .. tostring(pos.z)) or "<unavailable>") ..
      " texpackLoaded=true" ..
      " diagnosticShowEvenIfCollected=true" ..
      " dockProxyUsed=false" ..
      " progressionWritten=false")
  end

  _G.CompletionistMapV104RavenArtworkDiagnostic = true
  log("ART_API",
    "installed=true candidate=" .. candidate ..
    " mapResource=" .. expectedMapResource ..
    " texpackLoaded=true diagnosticShowEvenIfCollected=true" ..
    " compassType=DockPoint dockProxyUsed=false progressionWritten=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN ARTWORK LAYER PROOF
