-- BEGIN COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING V3.1
-- Capture exact custom map identity at collision dispatch, before transient map
-- collision state can be cleared. Route only exact real/Twin objects and UIDs.
-- Keep stock actions owned by the proven single-active-v3 controller.
do
  local prefix = "[CompletionistMap v0.10.4-uid-lifecycle-v3.1] "
  local ravenName = "Completionist_V103_Veithurgard_Raven_01"
  local twinName = "Completionist_V104_Veithurgard_Raven_Twin_01"
  local ravenClass = "CompletionistRaven"
  local selectionTTL = 30
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousCollision = MapOn.MapCollisionChangeHandler
  local compassPending = nil
  local promptOverride = nil
  local lastMapOnSelf = nil
  local knownRavenIdentity = nil
  local completionObserved = nil
  local selectionTicket = 0
  local routeFrame = 0

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function markerInfo(name)
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(name) end)
    if not ok or info == nil or info.Id == nil then
      log("MARKER_INFO", "name=" .. tostring(name) .. " ok=" .. tostring(ok) ..
          " error=" .. tostring(info))
      return nil
    end
    return info
  end

  local function identity(name, kind)
    local info = markerInfo(name)
    if info == nil then return nil end
    local result = {
      Kind = kind,
      Name = name,
      Id = info.Id,
      IdString = tostring(info.Id),
      X = info.X,
      Y = info.Y,
      Z = info.Z,
    }
    if name == ravenName then knownRavenIdentity = result end
    return result
  end

  -- Production bridge publishes native Raven state. False from an older restored
  -- checkpoint must win over stale quest state. This is read-only for progression.
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
    if not ok or type(value) ~= "boolean" then return nil end
    return value
  end

  local function collisionIdentity(self, collision)
    if self == nil or collision == nil then return nil, nil end
    if self.completionistSharedLoaderTwinGO ~= nil and
        collision == self.completionistSharedLoaderTwinGO then
      return identity(twinName, "twin"), "twin_object_reference"
    end
    if self.completionistMapV100MapIconGO ~= nil and
        collision == self.completionistMapV100MapIconGO then
      if originalCollected() ~= false then return nil, "raven_collected" end
      return identity(ravenName, "real"), "raven_object_reference"
    end
    return nil, nil
  end

  local function clearSelection(self, reason)
    if self == nil then return end
    local old = self.completionistMapV104PendingRavenSelection
    self.completionistMapV104PendingRavenSelection = nil
    if old ~= nil then
      log("SELECT_INVALIDATE", "reason=" .. tostring(reason) ..
          " kind=" .. tostring(old.Kind) .. " name=" .. tostring(old.Name) ..
          " uid=" .. tostring(old.IdString) .. " ticket=" .. tostring(old.Ticket))
    end
  end

  local function captureSelection(self, selected, source)
    if self == nil or selected == nil then return nil end
    local old = self.completionistMapV104PendingRavenSelection
    local frame = routeFrame
    if old ~= nil and old.IdString == selected.IdString then
      old.CapturedFrame = frame
      old.Source = source
      return old
    end
    selectionTicket = selectionTicket + 1
    selected.Ticket = selectionTicket
    selected.CapturedFrame = frame
    selected.Source = source
    self.completionistMapV104PendingRavenSelection = selected
    log("SELECT_CAPTURE", "source=" .. tostring(source) ..
        " kind=" .. tostring(selected.Kind) .. " name=" .. selected.Name ..
        " uid=" .. selected.IdString .. " ticket=" .. tostring(selected.Ticket))
    return selected
  end

  local function pendingSelection(self)
    if self == nil then return nil end
    local selected = self.completionistMapV104PendingRavenSelection
    if selected == nil then return nil end
    local frame = routeFrame
    if frame - (selected.CapturedFrame or frame) > selectionTTL then
      clearSelection(self, "ttl_expired")
      return nil
    end
    if selected.Name == ravenName and originalCollected() ~= false then
      clearSelection(self, "raven_collected")
      return nil
    end
    return selected
  end

  local function liveSelection(self, source)
    -- A newer noncustom collision event disproves a stale custom field reference.
    if self ~= nil and self.completionistMapV104LiveCustomCollisionValid == false then
      return nil
    end
    local selected = collisionIdentity(self, self and self.mapIconCollision or nil)
    if selected ~= nil then return captureSelection(self, selected, source) end
    return nil
  end

  local function collisionTableSelection(self, collisions)
    if type(collisions) ~= "table" then return nil, false end
    local hasCollision = false
    local twin = nil
    for _, collision in ipairs(collisions) do
      hasCollision = true
      local selected, source = collisionIdentity(self, collision)
      if selected ~= nil and selected.Kind == "real" then return selected, source end
      if selected ~= nil and selected.Kind == "twin" then twin = selected end
    end
    if twin ~= nil then return twin, "twin_object_reference" end
    return nil, hasCollision
  end

  local function consumeSelection(self)
    local selected = pendingSelection(self)
    if selected == nil then return nil end
    self.completionistMapV104PendingRavenSelection = nil
    log("SELECT_CONSUME", "kind=" .. tostring(selected.Kind) ..
        " name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " ticket=" .. tostring(selected.Ticket))
    return selected
  end

  local function customTargetIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function containsId(ids, idString)
    for _, id in ipairs(ids or {}) do
      if tostring(id) == idString then return true end
    end
    return false
  end

  local function customShown(selected)
    if selected == nil then return false, false, "selection_missing" end
    local ids, ok, err = customTargetIds()
    if not ok then return false, false, err end
    return containsId(ids, selected.IdString), true, nil
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
    local real = markerInfo(ravenName)
    if real ~= nil and tostring(real.Id) == idString then return ravenName end
    local twin = markerInfo(twinName)
    if twin ~= nil and tostring(twin.Id) == idString then return twinName end
    return nil
  end

  local function hideCustomTargets(reason, exceptIdString)
    local ids, ok, err = customTargetIds()
    if not ok then
      log("HIDE_CUSTOM", "reason=" .. tostring(reason) ..
          " queryOK=false error=" .. tostring(err))
      return false, 0
    end
    local hidden = 0
    local allHidden = true
    for _, id in ipairs(ids) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then
        local name = knownNameForId(id)
        local target = name or id
        local hideOK, hideErr = pcall(function() game.Compass.HideMarker(target) end)
        log("HIDE_CUSTOM", "reason=" .. tostring(reason) .. " id=" .. tostring(id) ..
            " name=" .. tostring(name) .. " ok=" .. tostring(hideOK) ..
            " error=" .. tostring(hideErr))
        if hideOK then hidden = hidden + 1 end
        if not hideOK then allHidden = false end
      end
    end
    return allHidden, hidden
  end

  local function hideStockTargets(reason)
    local ids, ok, err = stockTargets()
    if not ok then
      log("HIDE_STOCK", "reason=" .. tostring(reason) ..
          " queryOK=false error=" .. tostring(err))
      return false, 0
    end
    local hidden = 0
    local allHidden = true
    for _, id in ipairs(ids) do
      local hideOK, hideErr = pcall(function() game.Compass.HideMarker(id) end)
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " id=" .. tostring(id) ..
          " ok=" .. tostring(hideOK) .. " error=" .. tostring(hideErr))
      if hideOK then hidden = hidden + 1 end
      if not hideOK then allHidden = false end
    end
    return allHidden, hidden
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

  local function promptForSelection(selected, show, previousText)
    if selected == nil or not show then return show, previousText end
    if compassPending ~= nil and compassPending.IdString == selected.IdString then
      if compassPending.State == "tracked" then
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
      log("PROMPT", "uid=" .. selected.IdString ..
          " queryOK=false error=" .. tostring(queryErr))
      return show, previousText
    end
    if shown then return true, actionText(lamsConsts.RemoveFromCompass) end
    local custom, customOK, customErr = customTargetIds()
    local stock, stockOK, stockErr = stockTargets()
    if not customOK or not stockOK then
      log("PROMPT", "uid=" .. selected.IdString ..
          " customOK=" .. tostring(customOK) .. " customError=" .. tostring(customErr) ..
          " stockOK=" .. tostring(stockOK) .. " stockError=" .. tostring(stockErr))
      return show, previousText
    end
    if #custom > 0 or #stock > 0 then
      return true, actionText(lamsConsts.ReplaceInCompass)
    end
    return true, actionText(lamsConsts.AddToCompass)
  end

  local function refreshPrompt(self, selected)
    if self == nil or self.menu == nil then return end
    promptOverride = selected
    local show, text = self:GetShowOnCompassPrompt(self.menu)
    promptOverride = nil
    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    if goMapCursorText ~= nil then
      goMapCursorText:Show()
      local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if top ~= nil then
        local handle = util.GetTextHandle(top, "CursorAction_Text")
        if handle ~= nil then
          UI.SetTextIsClickable(handle)
          UI.SetText(handle, show and text or "")
        end
        if show then top:Show() else top:Hide() end
      end
    end
    self.menu:UpdateFooterButton("ShowOnCompass", show, text)
    self.menu:UpdateFooterButtonText()
    log("PROMPT_REFRESH", "visible=" .. tostring(show) .. " text=" .. tostring(text))
  end

  function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)
    lastMapOnSelf = self
    local selected, source = collisionTableSelection(self, collisionGameObjectTable)
    if selected ~= nil then
      self.completionistMapV104LiveCustomCollisionValid = true
      captureSelection(self, selected, "collision_table:" .. tostring(source))
    elseif source == true then
      self.completionistMapV104LiveCustomCollisionValid = false
      clearSelection(self, "new_noncustom_collision")
    end
    return previousCollision(self, currState, collisionGameObjectTable, realmName)
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    lastMapOnSelf = self
    local selected = promptOverride or liveSelection(self, "prompt_live") or pendingSelection(self)
    local show, previousText = previousPrompt(self, currMenu)
    if selected ~= nil and not show then
      clearSelection(self, "prompt_unavailable")
      return show, previousText
    end
    return promptForSelection(selected, show, previousText)
  end

  function MapOn:ShowOnCompass(currState)
    lastMapOnSelf = self
    liveSelection(self, "action_live")
    local selected = consumeSelection(self)
    if selected == nil then
      -- Stock actions stay native. Hide only active Twin first because the older
      -- controller knows real Raven but predates Twin UID.
      local twin = identity(twinName, "twin")
      if twin ~= nil then
        local twinShown, queryOK = customShown(twin)
        if queryOK and twinShown then
          local ok, err = pcall(function() game.Compass.HideMarker(twinName) end)
          if not ok then
            log("STOCK_REPLACE_TWIN_REFUSED", "uid=" .. twin.IdString ..
                " reason=twin_hide_failed error=" .. tostring(err) ..
                " nativeDelegated=false")
            return
          end
          log("STOCK_REPLACE_TWIN", "uid=" .. twin.IdString ..
              " hideOK=true nativeDelegated=true")
        end
      end
      return previousShow(self, currState)
    end

    if selected.Name == ravenName and originalCollected() ~= false then
      log("ACTION_REFUSED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " reason=raven_collected")
      return
    end
    local shown, queryOK, queryErr = customShown(selected)
    if not queryOK then
      log("ACTION_REFUSED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " reason=custom_class_query_failed error=" .. tostring(queryErr))
      return
    end
    if shown then
      local hideOK, hideErr = pcall(function() game.Compass.HideMarker(selected.Name) end)
      log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
          " ok=" .. tostring(hideOK) .. " error=" .. tostring(hideErr))
      if hideOK then
        compassPending = {IdString=selected.IdString, State="untracked", Frames=0}
        self.currShownMarkerID = nil
        if _G.CompletionistMapV104UidRavenTrackedName == selected.Name then
          _G.CompletionistMapV104UidRavenTrackedName = nil
        end
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshPrompt(self, selected)
      end
      return
    end

    local customOK, customCount = hideCustomTargets("raven_uid_replace", selected.IdString)
    local stockOK, stockCount = hideStockTargets("raven_uid_replace")
    if not customOK or not stockOK then
      compassPending = nil
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
    if not showOK then compassPending = nil return end
    compassPending = {IdString=selected.IdString, State="tracked", Frames=0}
    self.currShownMarkerID = selected.Id
    _G.CompletionistMapV104UidRavenTrackedName = selected.Name
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshPrompt(self, selected)
  end

  local function observeMapCompletion(self)
    local collected = originalCollected()
    if collected == nil then return end
    if collected == false then
      if completionObserved == true then log("LIFECYCLE_REARM", "reason=MapOn.Update") end
      completionObserved = false
      return
    end
    if completionObserved == true then return end
    local real = identity(ravenName, "real") or knownRavenIdentity
    local shown, queryOK, queryErr = customShown(real)
    local hideAttempted, hideOK, hideErr = false, true, nil
    if shown then
      hideAttempted = true
      hideOK, hideErr = pcall(function() game.Compass.HideMarker(ravenName) end)
    end
    if self ~= nil then
      local selected = pendingSelection(self)
      if selected ~= nil and selected.Name == ravenName then clearSelection(self, "raven_collected") end
      if real ~= nil and self.currShownMarkerID ~= nil and
          tostring(self.currShownMarkerID) == real.IdString then
        self.currShownMarkerID = nil
      end
    end
    if real ~= nil and compassPending ~= nil and compassPending.IdString == real.IdString then
      compassPending = nil
    end
    if _G.CompletionistMapV104UidRavenTrackedName == ravenName then
      _G.CompletionistMapV104UidRavenTrackedName = nil
    end
    local settled = queryOK and not shown and not hideAttempted
    if hideAttempted or completionObserved ~= settled then
      log("LIFECYCLE_CLEAR", "reason=MapOn.Update originalCollected=true" ..
          " hideAttempted=" .. tostring(hideAttempted) ..
          " hideOK=" .. tostring(hideOK) ..
          " hideError=" .. tostring(hideErr or queryErr) ..
          " settled=" .. tostring(settled) ..
          " twinTouched=false progressionWrites=false")
    end
    completionObserved = settled
  end

  function MapOn:Update(...)
    routeFrame = routeFrame + 1
    lastMapOnSelf = self
    observeMapCompletion(self)
    local result = previousUpdate(self, ...)
    pendingSelection(self)
    if compassPending ~= nil then
      compassPending.Frames = compassPending.Frames + 1
      local ids, ok, err = customTargetIds()
      if ok then
        local shown = containsId(ids, compassPending.IdString)
        local settled = (compassPending.State == "tracked" and shown) or
                        (compassPending.State == "untracked" and not shown)
        if settled then
          log("SETTLED", "uid=" .. compassPending.IdString ..
              " state=" .. compassPending.State ..
              " frames=" .. tostring(compassPending.Frames))
          compassPending = nil
        elseif compassPending.Frames == 180 then
          log("VERIFY_TIMEOUT", "uid=" .. compassPending.IdString ..
              " state=" .. compassPending.State)
          compassPending = nil
        end
      elseif compassPending.Frames == 1 or compassPending.Frames % 60 == 0 then
        log("VERIFY", "uid=" .. compassPending.IdString ..
            " queryOK=false error=" .. tostring(err) ..
            " frame=" .. tostring(compassPending.Frames))
      end
    end
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    assert(type(previous) == "function", "Missing map lifecycle method: " .. method)
    MapOn[method] = function(self, ...)
      self.completionistMapV104LiveCustomCollisionValid = false
      clearSelection(self, "map_teardown:" .. method)
      compassPending = nil
      if lastMapOnSelf == self then lastMapOnSelf = nil end
      return previous(self, ...)
    end
  end

  _G.CompletionistMapV104UidAwareRavenCompassRouting = true
  _G.CompletionistMapV104UidAwareRavenCompassRoutingV31 = true
  log("API", "installed=true identitySource=MapOn.MapCollisionChangeHandler_collision_table" ..
      " fallback=exact_live_collision pendingTTLFrames=" .. tostring(selectionTTL) ..
      " markerIdentity=Map.GetMarkerInfo compassClass=" .. ravenClass ..
      " singleActive=true gameplayCleanup=persistent_precisionchallenge" ..
      " progressionWrites=false twinLifecycleIndependent=true")
end
-- END COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING V3.1
