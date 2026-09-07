-- BEGIN COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS
-- One-Raven field proof for the independent CompletionistRaven CompassIconClass.
-- The authored map token is still the tested Raven token and still carries the
-- stock DockPoint map flag. Only the native compass icon class is changed here.
-- No map-marker progression state is modified.
do
  local prefix = "[CompletionistMap v0.10.4-class] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local markerType = "CompletionistRaven"
  local authoredMapFlag = consts.COMPASS_MARKER_TYPE_DOCK_POINT
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

  local function idsForClass(className)
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({className})
    end)
    if not ok then
      return {}, false, tostring(ids)
    end
    return ids or {}, true, nil
  end

  local function candidateShown()
    local info = candidateInfo()
    local wanted = info ~= nil and tostring(info.Id) or nil
    local ids, ok, err = idsForClass(markerType)
    if not ok then
      return false, false, err
    end
    for _, id in ipairs(ids) do
      if wanted ~= nil and tostring(id) == wanted then
        return true, true, nil
      end
    end
    return false, true, nil
  end

  local function stockTrackedMarkers()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then
      return {}, false, tostring(ids)
    end
    return ids or {}, true, nil
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_R3L3_DISABLED", "reason=dedicated_native_raven_tracking")
    end
  end

  local function updatePrompt(self, currState)
    if currState == nil or currState.menu == nil then return end
    local show, text = self:GetShowOnCompassPrompt(currState.menu)

    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    if goMapCursorText ~= nil then
      goMapCursorText:Show()
      local goCursorInfoTop = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if goCursorInfoTop ~= nil then
        local thPrompt = util.GetTextHandle(goCursorInfoTop, "CursorAction_Text")
        if thPrompt ~= nil then
          UI.SetTextIsClickable(thPrompt)
          UI.SetText(thPrompt, show and text or "")
        end
      end
    end

    currState.menu:UpdateFooterButton("ShowOnCompass", show, text)
    currState.menu:UpdateFooterButtonText()
    log("PROMPT_REFRESH", "cursor=true footer=true visible=" .. tostring(show) .. " text=" .. tostring(text))
  end

  local function hideCandidate(reason)
    local info = candidateInfo()
    local id = info ~= nil and tostring(info.Id) or "<missing>"
    log("HIDE", "stage=before reason=" .. tostring(reason) .. " id=" .. id)
    local ok, err = pcall(function()
      game.Compass.HideMarker(candidate)
    end)
    log("HIDE", "stage=lua_return ok=" .. tostring(ok) .. " error=" .. tostring(err))
    if ok then
      _G.CompletionistMapV104DedicatedRavenTracked = false
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

      local shown, queryOK = candidateShown()
      local lamsId = lamsConsts.AddToCompass
      if queryOK and shown then
        lamsId = lamsConsts.RemoveFromCompass
      else
        local others, othersOK = stockTrackedMarkers()
        if othersOK and #others > 0 then
          lamsId = lamsConsts.ReplaceInCompass
        end
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
      log("RESULT", "refused=candidate_missing " .. tostring(lookupError))
      return
    end

    local p = info.Coordinates
    local flagOK, hasCarrier = pcall(function()
      return Map.MarkerHasFlag(candidate, {authoredMapFlag})
    end)
    if not flagOK or hasCarrier ~= true or p == nil then
      log("RESULT",
        "refused=preflight_failed flagOK=" .. tostring(flagOK) ..
        " authoredDockCarrier=" .. tostring(flagOK and hasCarrier == true) ..
        " coordinates=" .. tostring(p ~= nil))
      return
    end

    local shown, shownOK, shownErr = candidateShown()
    if not shownOK then
      log("RESULT", "refused=custom_class_query_failed error=" .. tostring(shownErr))
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

    local others, othersOK, othersErr = stockTrackedMarkers()
    if not othersOK then
      log("RESULT", "refused=stock_marker_query_failed error=" .. tostring(othersErr))
      return
    end
    for _, id in ipairs(others) do
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(id)
      end)
      log("REPLACE", "oldId=" .. tostring(id) .. " hideOK=" .. tostring(hideOK) .. " error=" .. tostring(hideErr))
    end

    suppressLegacyRavenHud()

    log("PREFLIGHT",
      "id=" .. tostring(info.Id) ..
      " state=" .. tostring(info.State) ..
      " wad=" .. tostring(info.WadName) ..
      " x=" .. tostring(p.x) ..
      " y=" .. tostring(p.y) ..
      " z=" .. tostring(p.z) ..
      " authoredMapFlag=" .. tostring(authoredMapFlag) ..
      " compassClass=" .. markerType)
    log("SHOW", "stage=before id=" .. tostring(info.Id) .. " markerType=" .. markerType)

    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(candidate, markerType)
    end)
    log("SHOW", "stage=lua_return ok=" .. tostring(showOK) .. " error=" .. tostring(showErr))

    if not showOK then
      log("RESULT", "request_queued=false active=false reason=lua_wrapper_failed")
      return
    end

    self.currShownMarkerID = info.Id
    _G.CompletionistMapV104DedicatedRavenTracked = true
    verifyFrames = 0
    verifyBucket = -1
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    updatePrompt(self, currState)
    log("RESULT", "request_queued=true active=true class=CompletionistRaven")
  end

  function MapOn:Update(...)
    local result = originalUpdate(self, ...)

    local shown, queryOK, queryErr = candidateShown()
    if queryOK and shown then
      _G.CompletionistMapV104DedicatedRavenTracked = true
      suppressLegacyRavenHud()
      if CompletionistMapV100_IsRavenCollected() then
        hideCandidate("raven_collected_map_update")
      else
        verifyFrames = verifyFrames + 1
        local bucket = math.floor(verifyFrames / 300)
        if bucket ~= verifyBucket then
          verifyBucket = bucket
          log("VERIFY", "active=true frame=" .. tostring(verifyFrames) .. " customClassManager=true")
        end
      end
    elseif queryOK then
      _G.CompletionistMapV104DedicatedRavenTracked = false
    elseif verifyBucket < 0 then
      log("VERIFY", "active=false queryOK=false error=" .. tostring(queryErr))
      verifyBucket = 0
    end

    return result
  end

  _G.CompletionistMapV104DedicatedRavenClassEnabled = true
  log("API",
    "installed=true candidate=" .. candidate ..
    " compassClass=" .. markerType ..
    " authoredMapFlag=" .. tostring(authoredMapFlag) ..
    " calls_on_load=false legacy_r3l3_for_raven=false")
end
-- END COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS
