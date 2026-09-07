-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE
-- Raven-only production candidate for the native compass path proven in the
-- v0.10.3 live field test. This maps the existing Completionist Raven map
-- selection to an independently-authored native map token and lets God of War
-- own compass position, distance and route behaviour.
--
-- No marker progression state is changed here. The native marker remains
-- InitState=0 in the authored DCB data and is addressed only by its dedicated ID.
do
  local prefix = "[CompletionistMap v0.10.3-native] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local markerType = consts.COMPASS_MARKER_TYPE_DOCK_POINT
  local originalPrompt = MapOn.GetShowOnCompassPrompt
  local originalShow = MapOn.ShowOnCompass
  local originalUpdate = MapOn.Update

  local verifyFrames = 0
  local verifyBucket = -1

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

  local function shownState()
    local info = candidateInfo()
    local candidateId = info ~= nil and tostring(info.Id) or nil
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then
      return false, {}, false, tostring(ids)
    end

    local found = false
    local others = {}
    for _, id in ipairs(ids or {}) do
      if candidateId ~= nil and tostring(id) == candidateId then
        found = true
      else
        others[#others + 1] = id
      end
    end
    return found, others, true, nil
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_R3L3_DISABLED", "reason=native_raven_tracking")
    end
  end

  local function updatePrompt(self, currState)
    if currState == nil or currState.menu == nil then return end
    local show, text = self:GetShowOnCompassPrompt(currState.menu)
    currState.menu:UpdateFooterButton("ShowOnCompass", show, text)
    currState.menu:UpdateFooterButtonText()
  end

  local function hideCandidate(reason)
    local info = candidateInfo()
    local id = info ~= nil and tostring(info.Id) or "<missing>"
    log("NATIVE_RAVEN_HIDE", "stage=before reason=" .. tostring(reason) .. " id=" .. id)
    local ok, err = pcall(function()
      game.Compass.HideMarker(candidate)
    end)
    log("NATIVE_RAVEN_HIDE",
      "stage=lua_return ok=" .. tostring(ok) ..
      " error=" .. tostring(err))
    if ok then
      _G.CompletionistMapV103NativeRavenTracked = false
    end
    return ok
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

      local shown, others, queryOK = shownState()
      local lamsId = lamsConsts.AddToCompass
      if queryOK and shown then
        lamsId = lamsConsts.RemoveFromCompass
      elseif queryOK and #others > 0 then
        lamsId = lamsConsts.ReplaceInCompass
      end
      return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
    end

    return originalPrompt(self, currMenu)
  end

  function MapOn:ShowOnCompass(currState)
    if not ravenSelected(self) then
      return originalShow(self, currState)
    end

    if CompletionistMapV100_IsRavenCollected() then
      hideCandidate("raven_already_collected")
      self.completionistMapV100Selected = false
      updatePrompt(self, currState)
      return
    end

    local info, lookupError = candidateInfo()
    if info == nil then
      log("NATIVE_RAVEN_RESULT", "refused=candidate_missing " .. tostring(lookupError))
      return
    end

    local p = info.Coordinates
    local flagOK, hasDockFlag = pcall(function()
      return Map.MarkerHasFlag(candidate, {markerType})
    end)
    if not flagOK or hasDockFlag ~= true or p == nil then
      log("NATIVE_RAVEN_RESULT",
        "refused=preflight_failed flagOK=" .. tostring(flagOK) ..
        " dockFlag=" .. tostring(flagOK and hasDockFlag == true) ..
        " coordinates=" .. tostring(p ~= nil))
      return
    end

    local shown, others, queryOK, queryErr = shownState()
    if not queryOK then
      log("NATIVE_RAVEN_RESULT",
        "refused=active_marker_query_failed error=" .. tostring(queryErr))
      return
    end

    if shown then
      if hideCandidate("user_remove") then
        self.currShownMarkerID = nil
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
      end
      updatePrompt(self, currState)
      return
    end

    -- Match stock Replace in Compass semantics without touching marker state.
    -- Hide only currently tracked compass targets returned by the native manager.
    for _, id in ipairs(others) do
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(id)
      end)
      log("NATIVE_RAVEN_REPLACE",
        "oldId=" .. tostring(id) ..
        " hideOK=" .. tostring(hideOK) ..
        " error=" .. tostring(hideErr))
    end

    suppressLegacyRavenHud()

    log("NATIVE_RAVEN_PREFLIGHT",
      "id=" .. tostring(info.Id) ..
      " state=" .. tostring(info.State) ..
      " wad=" .. tostring(info.WadName) ..
      " x=" .. tostring(p.x) ..
      " y=" .. tostring(p.y) ..
      " z=" .. tostring(p.z))
    log("NATIVE_RAVEN_SHOW",
      "stage=before id=" .. tostring(info.Id) ..
      " markerType=" .. tostring(markerType))

    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(candidate, markerType)
    end)
    log("NATIVE_RAVEN_SHOW",
      "stage=lua_return ok=" .. tostring(showOK) ..
      " error=" .. tostring(showErr))

    if not showOK then
      log("NATIVE_RAVEN_RESULT", "active=false reason=lua_wrapper_failed")
      return
    end

    self.currShownMarkerID = info.Id
    _G.CompletionistMapV103NativeRavenTracked = true
    verifyFrames = 0
    verifyBucket = -1
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    updatePrompt(self, currState)
    log("NATIVE_RAVEN_RESULT", "request_queued=true active=true")
  end

  function MapOn:Update(...)
    local result = originalUpdate(self, ...)

    local shown, _, queryOK = shownState()
    if queryOK and shown then
      _G.CompletionistMapV103NativeRavenTracked = true
      suppressLegacyRavenHud()

      if CompletionistMapV100_IsRavenCollected() then
        hideCandidate("raven_collected_map_update")
      else
        verifyFrames = verifyFrames + 1
        local bucket = math.floor(verifyFrames / 300)
        if bucket ~= verifyBucket then
          verifyBucket = bucket
          log("NATIVE_RAVEN_VERIFY",
            "active=true frame=" .. tostring(verifyFrames) ..
            " native_manager=true")
        end
      end
    elseif queryOK then
      _G.CompletionistMapV103NativeRavenTracked = false
    end

    return result
  end

  _G.CompletionistMapV103NativeRavenEnabled = true
  log("NATIVE_RAVEN_API",
    "installed=true candidate=" .. candidate ..
    " markerType=" .. tostring(markerType) ..
    " calls_on_load=false legacy_r3l3_for_raven=false")
end
-- END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE
