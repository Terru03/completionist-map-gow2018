-- BEGIN COMPLETIONIST V0.10.3 NATIVE COMPASS SHOW PROBE
-- Raven-only native compass request proof.
-- Requires the v0.10.3 authored Raven DCB runtime copies to be installed first.
-- It never changes marker/progression state and never touches stock marker records.
do
  local prefix = "[CompletionistMap v0.10.3] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local markerType = consts.COMPASS_MARKER_TYPE_DOCK_POINT
  local originalPrompt = MapOn.GetShowOnCompassPrompt
  local originalShow = MapOn.ShowOnCompass
  local originalUpdate = MapOn.Update

  local active = false
  local candidateIdString = nil
  local verifyFrames = 0
  local verifyLogged = false

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function ravenSelected(self)
    return self ~= nil and self.completionistMapV100Selected == true
  end

  local function candidateInfo()
    local ok, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not ok then
      return nil, "lookup_error=" .. tostring(info)
    end
    if info == nil then
      return nil, "registered=false"
    end
    return info, nil
  end

  local function updatePrompt(self, currState)
    if currState == nil or currState.menu == nil then return end
    local show, text = self:GetShowOnCompassPrompt(currState.menu)
    currState.menu:UpdateFooterButton("ShowOnCompass", show, text)
    currState.menu:UpdateFooterButtonText()
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    if ravenSelected(self) then
      if CompletionistMapV100_IsRavenCollected() then
        return false, nil
      end
      if self.isOpenedForFastTravel or
          not game.Compass.HaveCompass() or
          self.currRealmName ~= mapUtil.GetPlayerRealm() or
          tutorialUtil.CurrentlyShowingStep() then
        return false, nil
      end
      local lamsId = active and lamsConsts.RemoveFromCompass or lamsConsts.AddToCompass
      return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
    end
    return originalPrompt(self, currMenu)
  end

  function MapOn:ShowOnCompass(currState)
    if not ravenSelected(self) then
      return originalShow(self, currState)
    end

    if CompletionistMapV100_IsRavenCollected() then
      log("NATIVE_COMPASS_RESULT", "refused=raven_collected")
      return
    end

    local info, lookupError = candidateInfo()
    if info == nil then
      log("NATIVE_COMPASS_RESULT", "refused=candidate_missing " .. tostring(lookupError))
      return
    end

    candidateIdString = tostring(info.Id)
    local p = info.Coordinates
    local flagOK, hasDockFlag = pcall(function()
      return Map.MarkerHasFlag(candidate, {markerType})
    end)

    log("NATIVE_COMPASS_PREFLIGHT",
      "id=" .. candidateIdString ..
      " state=" .. tostring(info.State) ..
      " wad=" .. tostring(info.WadName) ..
      " dockFlagOK=" .. tostring(flagOK) ..
      " dockFlag=" .. tostring(flagOK and hasDockFlag == true) ..
      " x=" .. tostring(p and p.x or "<nil>") ..
      " y=" .. tostring(p and p.y or "<nil>") ..
      " z=" .. tostring(p and p.z or "<nil>"))

    if not flagOK or hasDockFlag ~= true or p == nil then
      log("NATIVE_COMPASS_RESULT", "refused=preflight_failed")
      return
    end

    if active then
      log("NATIVE_COMPASS_HIDE", "stage=before id=" .. candidateIdString)
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(candidate)
      end)
      log("NATIVE_COMPASS_HIDE",
        "stage=lua_return ok=" .. tostring(hideOK) ..
        " error=" .. tostring(hideErr))
      if hideOK then
        active = false
        _G.CompletionistMapV103NativeCompassActive = false
        verifyFrames = 0
        verifyLogged = false
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
      end
      updatePrompt(self, currState)
      return
    end

    -- Do not silently replace a user's existing normal map target during this proof.
    local findOK, shown = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not findOK then
      log("NATIVE_COMPASS_RESULT", "refused=active_marker_query_failed error=" .. tostring(shown))
      return
    end

    local others = {}
    for _, id in ipairs(shown or {}) do
      if tostring(id) ~= candidateIdString then
        others[#others + 1] = tostring(id)
      end
    end
    if #others > 0 then
      log("NATIVE_COMPASS_RESULT",
        "refused=existing_map_target count=" .. tostring(#others) ..
        " ids=" .. table.concat(others, ","))
      return
    end

    -- Disable the old manual XYZ/R3_L3 surrogate before asking the native manager.
    if _G.CompletionistMapV100Target ~= nil then
      _G.CompletionistMapV100Target.active = false
    end

    log("NATIVE_COMPASS_SHOW",
      "stage=before name=" .. candidate ..
      " id=" .. candidateIdString ..
      " markerType=" .. tostring(markerType))

    -- pcall only reports the Lua wrapper return. The request is queued in native code,
    -- so a later C++ failure would still occur outside this pcall.
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(candidate, markerType)
    end)

    log("NATIVE_COMPASS_SHOW",
      "stage=lua_return ok=" .. tostring(showOK) ..
      " error=" .. tostring(showErr))

    if not showOK then
      log("NATIVE_COMPASS_RESULT", "active=false reason=lua_wrapper_failed")
      return
    end

    active = true
    _G.CompletionistMapV103NativeCompassActive = true
    verifyFrames = 0
    verifyLogged = false
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    updatePrompt(self, currState)
    log("NATIVE_COMPASS_RESULT", "request_queued=true active=true")
  end

  function MapOn:Update(...)
    local result = originalUpdate(self, ...)

    if active and not verifyLogged then
      verifyFrames = verifyFrames + 1
      if verifyFrames >= 30 then
        verifyLogged = true
        local ok, ids = pcall(function()
          return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
        end)
        local found = false
        local rendered = {}
        if ok then
          for _, id in ipairs(ids or {}) do
            rendered[#rendered + 1] = tostring(id)
            if tostring(id) == candidateIdString then
              found = true
            end
          end
        end
        log("NATIVE_COMPASS_VERIFY",
          "frame=" .. tostring(verifyFrames) ..
          " queryOK=" .. tostring(ok) ..
          " candidateFound=" .. tostring(found) ..
          " ids=" .. table.concat(rendered, ","))
      end
    end

    return result
  end

  log("NATIVE_COMPASS_API",
    "installed=true candidate=" .. candidate ..
    " markerType=" .. tostring(markerType) ..
    " calls_on_load=false")
end
-- END COMPLETIONIST V0.10.3 NATIVE COMPASS SHOW PROBE
