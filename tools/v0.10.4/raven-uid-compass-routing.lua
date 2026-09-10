-- BEGIN COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING
-- Runtime hypothesis probe layered on the proven shared-loader Twin.
--
-- Both map pins intentionally share goMapIconCompletionistRaven. Therefore GO name
-- cannot identify which marker was clicked. The shared-loader keeps the exact live
-- GO references on the map view, so the globally available MapOn prompt/action path
-- can distinguish original and Twin from mapIconCollision without depending on the
-- lexical MapRecordView class. Native marker Id/Name then comes from Map.GetMarkerInfo
-- and the selected marker Name is routed through CompletionistRaven.
--
-- V2 also observes the already-proven production Raven completion oracle. It never
-- writes progression or marker state: completion only clears an active original-Raven
-- compass target and local routing selection. The independent Twin remains untouched.
do
  local prefix = "[CompletionistMap v0.10.4-uid-lifecycle-v3] "
  local ravenName = "Completionist_V103_Veithurgard_Raven_01"
  local twinName = "Completionist_V104_Veithurgard_Raven_Twin_01"
  local ravenClass = "CompletionistRaven"
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local pending = nil
  local lastMapOnSelf = nil
  local completionObserved = nil
  local completionHideRequested = false
  local completionNeedsHide = false

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function markerInfo(name)
    local ok, info = pcall(function()
      return game.Map.GetMarkerInfo(name)
    end)
    if not ok or info == nil or info.Id == nil then
      log("MARKER_INFO", "name=" .. tostring(name) .. " ok=" .. tostring(ok) ..
          " error=" .. tostring(info))
      return nil
    end
    return info
  end

  local function identity(name)
    local info = markerInfo(name)
    if info == nil then return nil end
    return {
      Name = name,
      Id = info.Id,
      IdString = tostring(info.Id),
      X = info.X,
      Y = info.Y,
      Z = info.Z,
    }
  end

  -- Production bridge publishes real script state on hit/start/restore.
  -- False from restore must win over stale quest/cache state.
  CompletionistMapV100_IsRavenCollected = function()
    local state = _G.CompletionistMapV100TargetRavenKilled
    if type(state) == "boolean" then return state end
    local ok, quest = pcall(function()
      return game.QuestManager.GetQuestState("RegionSummary_VF_Raven_Parent")
    end)
    if not ok or quest == nil then return nil end
    return tostring(quest) == "Complete"
  end

  local function originalCollected()
    local ok, value = pcall(CompletionistMapV100_IsRavenCollected)
    if not ok or type(value) ~= "boolean" then return nil, "oracle_unavailable" end
    return value, nil
  end

  local function selectedIdentity(self)
    return self ~= nil and self.completionistMapV104SelectedRavenIdentity or nil
  end

  local function collisionIdentity(self, collision)
    if self == nil or collision == nil then return nil end
    -- Exact object-reference matching is deliberate. The two objects have the same
    -- resource/GO name, but the proven shared-loader created and retained two distinct
    -- objects: completionistMapV100MapIconGO and completionistSharedLoaderTwinGO.
    if self.completionistSharedLoaderTwinGO ~= nil and collision == self.completionistSharedLoaderTwinGO then
      return identity(twinName), "twin_object_reference"
    end
    if self.completionistMapV100MapIconGO ~= nil and collision == self.completionistMapV100MapIconGO then
      local collected = originalCollected()
      if collected ~= false then return nil, "raven_collected" end
      return identity(ravenName), "raven_object_reference"
    end
    return nil, nil
  end

  local function refreshSelectedIdentity(self, reason)
    if self == nil then return nil end
    lastMapOnSelf = self
    local collision = self.mapIconCollision
    if collision == nil then
      -- Footer/action dispatch can occur after the collision frame. Preserve the last
      -- custom identity only while there is no newer non-custom collision to disprove it.
      local selected = selectedIdentity(self)
      if selected ~= nil and selected.Name == ravenName and originalCollected() ~= false then
        self.completionistMapV104SelectedRavenIdentity = nil
        return nil
      end
      return selected
    end

    local routed, source = collisionIdentity(self, collision)
    if routed ~= nil then
      local previous = selectedIdentity(self)
      self.completionistMapV104SelectedRavenIdentity = routed
      if previous == nil or previous.IdString ~= routed.IdString then
        log("SELECT", "reason=" .. tostring(reason) .. " source=" .. tostring(source) ..
            " name=" .. routed.Name .. " uid=" .. routed.IdString ..
            " collisionGO=" .. tostring(collision))
      end
      return routed
    end

    if selectedIdentity(self) ~= nil then
      log("SELECT_CLEAR", "reason=" .. tostring(reason) ..
          " collisionGO=" .. tostring(collision) .. " source=" .. tostring(source))
    end
    self.completionistMapV104SelectedRavenIdentity = nil
    return nil
  end

  local function customTargetIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then
      return {}, false, tostring(ids)
    end
    return ids or {}, true, nil
  end

  local function containsId(ids, idString)
    for _, id in ipairs(ids or {}) do
      if tostring(id) == idString then return true end
    end
    return false
  end

  local function customShown(which)
    if which == nil then return false, false, "selection_missing" end
    local ids, ok, err = customTargetIds()
    if not ok then return false, false, err end
    return containsId(ids, which.IdString), true, nil
  end

  local function stockTargets()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function knownNameForId(id)
    local idString = tostring(id)
    local r = markerInfo(ravenName)
    if r ~= nil and tostring(r.Id) == idString then return ravenName end
    local t = markerInfo(twinName)
    if t ~= nil and tostring(t.Id) == idString then return twinName end
    return nil
  end

  local function hideCustomTargets(reason, exceptIdString)
    local ids, ok, err = customTargetIds()
    if not ok then
      log("HIDE_CUSTOM", "reason=" .. tostring(reason) .. " queryOK=false error=" .. tostring(err))
      return false, 0
    end
    local hidden = 0
    for _, id in ipairs(ids) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then
        local name = knownNameForId(id)
        local target = name or id
        local hideOK, hideErr = pcall(function()
          game.Compass.HideMarker(target)
        end)
        log("HIDE_CUSTOM", "reason=" .. tostring(reason) .. " id=" .. tostring(id) ..
            " name=" .. tostring(name) .. " ok=" .. tostring(hideOK) ..
            " error=" .. tostring(hideErr))
        if hideOK then hidden = hidden + 1 end
      end
    end
    return true, hidden
  end

  local function hideStockTargets(reason)
    local ids, ok, err = stockTargets()
    if not ok then
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " queryOK=false error=" .. tostring(err))
      return false, 0
    end
    local hidden = 0
    for _, id in ipairs(ids) do
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(id)
      end)
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " id=" .. tostring(id) ..
          " ok=" .. tostring(hideOK) .. " error=" .. tostring(hideErr))
      if hideOK then hidden = hidden + 1 end
    end
    return true, hidden
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_R3L3_DISABLED", "reason=uid_routed_native_custom_tracking")
    end
  end

  local function refreshPrompt(self)
    if self == nil or self.menu == nil or selectedIdentity(self) == nil then return end
    local show, text = self:GetShowOnCompassPrompt(self.menu)
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
        if show then goCursorInfoTop:Show() else goCursorInfoTop:Hide() end
      end
    end
    self.menu:UpdateFooterButton("ShowOnCompass", show, text)
    self.menu:UpdateFooterButtonText()
    log("PROMPT_REFRESH", "visible=" .. tostring(show) .. " text=" .. tostring(text))
  end

  local function observeOriginalCompletion(reason, liveState)
    local collected = originalCollected()
    if type(liveState) == "boolean" then collected = liveState end
    if collected == nil then return false, false end
    if collected == false then
      if completionObserved == true then log("LIFECYCLE_REARM", "reason=" .. tostring(reason)) end
      completionObserved = false
      completionHideRequested = false
      completionNeedsHide = false
      return false, false
    end
    if completionObserved == true then return true, false end

    local original = identity(ravenName)
    local trackedReal = _G.CompletionistMapV104UidRavenTrackedName == ravenName
    local queuedReal = original ~= nil and pending ~= nil and
      pending.IdString == original.IdString and pending.State == "tracked"
    completionNeedsHide = completionNeedsHide or trackedReal or queuedReal
    local shown, queryOK, queryErr = customShown(original)
    local hideAttempted, hideOK, hideErr = false, true, nil
    if (shown or completionNeedsHide) and not completionHideRequested then
      hideAttempted = true
      hideOK, hideErr = pcall(function() game.Compass.HideMarker(ravenName) end)
      completionHideRequested = hideOK
    end

    if original ~= nil and pending ~= nil and pending.IdString == original.IdString then
      pending = nil
    end
    if lastMapOnSelf ~= nil then
      local selected = selectedIdentity(lastMapOnSelf)
      if selected ~= nil and selected.Name == ravenName then
        lastMapOnSelf.completionistMapV104SelectedRavenIdentity = nil
      end
      if original ~= nil and lastMapOnSelf.currShownMarkerID ~= nil and
        tostring(lastMapOnSelf.currShownMarkerID) == original.IdString then
        lastMapOnSelf.currShownMarkerID = nil
      end
    end
    if trackedReal then _G.CompletionistMapV104UidRavenTrackedName = nil end

    -- Verify queued hide on next event-local check. Never reissue successful hide.
    completionObserved = queryOK and not shown and not hideAttempted and
      (not completionNeedsHide or completionHideRequested)
    log("LIFECYCLE_CLEAR", "reason=" .. tostring(reason) ..
      " originalCollected=true hideAttempted=" .. tostring(hideAttempted) ..
      " hideOK=" .. tostring(hideOK) .. " hideError=" .. tostring(hideErr or queryErr) ..
      " settled=" .. tostring(completionObserved) ..
      " twinTouched=false progressionWrites=false")
    return true, not completionObserved
  end

  local function blockedRealSelection(self)
    local selected = selectedIdentity(self)
    local realCollision = self.mapIconCollision ~= nil and
      self.mapIconCollision == self.completionistMapV100MapIconGO
    local retainedReal = self.mapIconCollision == nil and selected ~= nil and selected.Name == ravenName
    return (realCollision or retainedReal) and originalCollected() ~= false
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    if blockedRealSelection(self) then
      self.completionistMapV104SelectedRavenIdentity = nil
      return false, nil
    end
    local selected = refreshSelectedIdentity(self, "prompt")
    local show, previousText = previousPrompt(self, currMenu)
    if selected == nil or not show then return show, previousText end

    if pending ~= nil and pending.IdString == selected.IdString then
      if pending.State == "tracked" then
        return true, actionText(lamsConsts.RemoveFromCompass)
      end
      local custom = customTargetIds()
      local stock = stockTargets()
      if #custom > 0 or #stock > 0 then
        return true, actionText(lamsConsts.ReplaceInCompass)
      end
      return true, actionText(lamsConsts.AddToCompass)
    end

    local shown, queryOK, queryErr = customShown(selected)
    if not queryOK then
      log("PROMPT", "uid=" .. selected.IdString .. " queryOK=false error=" .. tostring(queryErr))
      return show, previousText
    end
    if shown then return true, actionText(lamsConsts.RemoveFromCompass) end

    local custom, customOK, customErr = customTargetIds()
    local stock, stockOK, stockErr = stockTargets()
    if not customOK or not stockOK then
      log("PROMPT", "uid=" .. selected.IdString .. " customOK=" .. tostring(customOK) ..
          " customError=" .. tostring(customErr) .. " stockOK=" .. tostring(stockOK) ..
          " stockError=" .. tostring(stockErr))
      return show, previousText
    end
    if #custom > 0 or #stock > 0 then
      return true, actionText(lamsConsts.ReplaceInCompass)
    end
    return true, actionText(lamsConsts.AddToCompass)
  end

  function MapOn:ShowOnCompass(currState)
    if blockedRealSelection(self) then
      lastMapOnSelf = self
      observeOriginalCompletion("action_guard")
      self.completionistMapV104SelectedRavenIdentity = nil
      return
    end
    local selected = refreshSelectedIdentity(self, "action")
    if selected == nil then
      -- The preceding production controller already knows how to replace the original
      -- Raven with stock targets. Its only blind spot is the new Twin, so remove the
      -- Twin first if it is the active custom target, then delegate unchanged stock flow.
      local twin = identity(twinName)
      if twin ~= nil then
        local twinShown, queryOK = customShown(twin)
        if queryOK and twinShown then
          local ok, err = pcall(function() game.Compass.HideMarker(twinName) end)
          log("STOCK_REPLACE_TWIN", "uid=" .. twin.IdString .. " hideOK=" .. tostring(ok) ..
              " error=" .. tostring(err))
        end
      end
      return previousShow(self, currState)
    end

    local shown, queryOK, queryErr = customShown(selected)
    if not queryOK then
      log("ACTION_REFUSED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " reason=custom_class_query_failed error=" .. tostring(queryErr))
      return
    end

    if shown then
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(selected.Name)
      end)
      log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " ok=" .. tostring(hideOK) .. " error=" .. tostring(hideErr))
      if hideOK then
        pending = {IdString=selected.IdString, State="untracked", Frames=0}
        self.currShownMarkerID = nil
        if _G.CompletionistMapV104UidRavenTrackedName == selected.Name then
          _G.CompletionistMapV104UidRavenTrackedName = nil
        end
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshPrompt(self)
      end
      return
    end

    local customOK, customCount = hideCustomTargets("raven_uid_replace", selected.IdString)
    local stockOK, stockCount = hideStockTargets("raven_uid_replace")
    if not customOK or not stockOK then
      pending = nil
      log("ACTION_REFUSED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " reason=replace_query_failed")
      return
    end

    suppressLegacyRavenHud()
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " ok=" .. tostring(showOK) .. " error=" .. tostring(showErr) ..
        " replacedCustomCount=" .. tostring(customCount) ..
        " replacedStockCount=" .. tostring(stockCount))
    if not showOK then
      pending = nil
      return
    end

    pending = {IdString=selected.IdString, State="tracked", Frames=0}
    self.currShownMarkerID = selected.Id
    _G.CompletionistMapV104UidRavenTrackedName = selected.Name
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshPrompt(self)
  end

  function MapOn:Update(...)
    lastMapOnSelf = self
    observeOriginalCompletion("MapOn.Update")
    local result = previousUpdate(self, ...)
    if pending ~= nil then
      pending.Frames = pending.Frames + 1
      local ids, ok, err = customTargetIds()
      if ok then
        local shown = containsId(ids, pending.IdString)
        local settled = (pending.State == "tracked" and shown) or
                        (pending.State == "untracked" and not shown)
        if settled then
          log("SETTLED", "uid=" .. pending.IdString .. " state=" .. pending.State ..
              " frames=" .. tostring(pending.Frames))
          pending = nil
          refreshPrompt(self)
        elseif pending.Frames == 180 then
          log("VERIFY_TIMEOUT", "uid=" .. pending.IdString .. " state=" .. pending.State)
          pending = nil
          refreshPrompt(self)
        end
      elseif pending.Frames == 1 or pending.Frames % 60 == 0 then
        log("VERIFY", "uid=" .. pending.IdString .. " queryOK=false error=" .. tostring(err) ..
            " frame=" .. tostring(pending.Frames))
      end
    end
    return result
  end

  _G.CompletionistMapV104ObserveRavenCompletion = observeOriginalCompletion
  -- Gameplay bridge calls observer after native hit/start/restore.
  -- Map update is fallback for load order and retry; no worker thread.
  observeOriginalCompletion("mapmenu_load")

  _G.CompletionistMapV104UidAwareRavenCompassRouting = true
  log("API", "installed=true identitySource=MapOn.mapIconCollision_exact_object_reference" ..
      " markerIdentity=Map.GetMarkerInfo compassClass=" .. ravenClass ..
      " singleActive=true completionOracle=CompletionistMapV100_IsRavenCollected" ..
      " progressionWrites=false twinLifecycleIndependent=true")
end
-- END COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING
