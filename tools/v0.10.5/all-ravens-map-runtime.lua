-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS
-- Data drives all Raven work. Catalogue Ravens are visible unless explicitly collected.
do
  local prefix = "[CompletionistMap v0.10.5-all-ravens] "
  local ravenClass = "CompletionistRaven"
  local mapResource = "goMapIconCompletionistRaven"
  local provenName = "Completionist_V103_Veithurgard_Raven_01"
  local rows = {
-- @@RAVEN_CATALOGUE_ROWS@@
  }
  local byName = {}
  local byCatalogueId = {}
  for _, row in ipairs(rows) do
    byName[row.Name] = row
    byCatalogueId[row.CatalogueId] = row
  end

  local byMarkerId = {}

  local states = _G.CompletionistMapV105RavenState or {}
  _G.CompletionistMapV105RavenState = states
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousCollision = MapOn.MapCollisionChangeHandler
  local lastMapOnSelf = nil
  local selectionGeneration = 0
  local promptIntent = nil
  local promptSettleFrames = 0
  local promptSettleBucket = -1
  local customCompassOwnsTarget = false
  local nativeAllowSameGenerationOnce = false
  local nativeResetRecheckFrames = 0
  local nativeResetRecheckBucket = -1
  local nativeResetRecheckLimit = 180
  local nativePort = 43753
  local nativeRequest = "GET RAVEN_SNAPSHOT_V1\n"
  local nativeMaxResponseBytes = 4096
  local lastNativeGeneration = tonumber(_G.CompletionistMapV105LastNativeRavenGeneration)
  local lastNativeNotice = nil

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function isCollected(catalogueId)
    return states[catalogueId] == true
  end

  local function shouldShow(catalogueId)
    return byCatalogueId[catalogueId] ~= nil and not isCollected(catalogueId)
  end

  local function nativeNotice(category, fields, key)
    if key == lastNativeNotice then return end
    lastNativeNotice = key
    log(category, fields)
  end

  local function closeSocket(client)
    if client ~= nil then pcall(function() client:close() end) end
  end

  local function receiveNativeLine(client)
    local bytes = {}
    for index = 1, nativeMaxResponseBytes do
      local ok, value, err = pcall(function() return client:receive(1) end)
      if not ok or type(value) ~= "string" or string.len(value) ~= 1 then
        return nil, "receive:" .. tostring(ok and err or value)
      end
      if value == "\n" then return table.concat(bytes), nil end
      if value == "\r" then return nil, "response_cr" end
      bytes[index] = value
    end
    return nil, "response_too_large"
  end

  local function parseNativeSnapshot(line)
    if line == "RAVEN_SNAPSHOT_V1 UNAVAILABLE" then
      return nil, "snapshot_not_ready"
    end
    if type(line) ~= "string" or
        string.sub(line, 1, string.len("RAVEN_SNAPSHOT_V1 ")) ~= "RAVEN_SNAPSHOT_V1 " then
      return nil, "response_header"
    end
    local fields = {}
    for key, value in string.gmatch(line, "([%a][%w]*)=([^%s]+)") do
      if fields[key] ~= nil then return nil, "duplicate_field:" .. key end
      fields[key] = value
    end
    local function integer(name)
      local value = tonumber(fields[name])
      if value == nil or value < 0 or value ~= math.floor(value) then
        return nil
      end
      return value
    end
    local schema = integer("schema")
    local generation = integer("generation")
    local capturedTickMs = integer("capturedTickMs")
    local count = integer("count")
    local unknown = integer("unknown")
    local alive = integer("alive")
    local killed = integer("killed")
    local explicit = integer("explicit")
    local absentWadFalse = integer("absentWadFalse")
    if schema ~= 1 or generation == nil or generation < 1 or
        capturedTickMs == nil or count ~= #rows or unknown ~= 0 or
        alive == nil or killed == nil or alive + killed ~= #rows or
        explicit == nil or absentWadFalse == nil or
        explicit + absentWadFalse ~= #rows or fields.killedIds == nil then
      return nil, "response_counts"
    end
    local states = {}
    for catalogueId, _ in pairs(byCatalogueId) do states[catalogueId] = false end
    local killedCatalogueIds = {}
    if fields.killedIds ~= "-" then
      for catalogueId in string.gmatch(fields.killedIds, "([^,]+)") do
        if byCatalogueId[catalogueId] == nil then
          return nil, "unknown_catalogue_id"
        end
        if states[catalogueId] == true then
          return nil, "duplicate_catalogue_id"
        end
        states[catalogueId] = true
        killedCatalogueIds[#killedCatalogueIds + 1] = catalogueId
      end
    end
    if #killedCatalogueIds ~= killed then return nil, "killed_count" end
    return {
      schema = schema, generation = generation, capturedTickMs = capturedTickMs,
      count = count, aliveCount = alive, killedCount = killed,
      explicitCount = explicit,
      absenceDefaultFalseCount = absentWadFalse,
      states = states, killedCatalogueIds = killedCatalogueIds,
    }, nil
  end

  local function getRavenSnapshot()
    local socketOK, socket = pcall(require, "socket.core")
    if not socketOK or type(socket) ~= "table" or type(socket.tcp) ~= "function" then
      return nil, "socket_core_unavailable"
    end
    local createOK, client = pcall(socket.tcp)
    if not createOK or client == nil then return nil, "socket_create" end
    pcall(function() client:settimeout(0.25) end)
    pcall(function() client:settimeout(0.25, "t") end)
    local connectOK, connected, connectError = pcall(function()
      return client:connect("127.0.0.1", nativePort)
    end)
    if not connectOK or connected == nil then
      closeSocket(client)
      return nil, "connect:" .. tostring(connectOK and connectError or connected)
    end
    local sendOK, sent, sendError = pcall(function()
      return client:send(nativeRequest)
    end)
    if not sendOK or sent ~= string.len(nativeRequest) then
      closeSocket(client)
      return nil, "send:" .. tostring(sendOK and sendError or sent)
    end
    local line, receiveError = receiveNativeLine(client)
    closeSocket(client)
    if line == nil then return nil, receiveError end
    return parseNativeSnapshot(line)
  end

  local nativeNamespace = rawget(_G, "CompletionistMapNative")
  if nativeNamespace == nil then
    nativeNamespace = {}
    rawset(_G, "CompletionistMapNative", nativeNamespace)
  end
  if type(nativeNamespace) == "table" then
    if rawget(nativeNamespace, "GetRavenSnapshot") == nil then
      nativeNamespace.GetRavenSnapshot = getRavenSnapshot
    elseif type(nativeNamespace.GetRavenSnapshot) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=api_collision", "api_collision")
    end
  else
    nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=namespace_collision", "namespace_collision")
  end

  local function refreshNativeAuthority(source)
    local namespace = rawget(_G, "CompletionistMapNative")
    local accessor = type(namespace) == "table" and namespace.GetRavenSnapshot or nil
    if type(accessor) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=api_unavailable", "api_unavailable")
      return false, "api_unavailable"
    end
    local ok, snapshot, reason = pcall(accessor)
    if not ok or type(snapshot) ~= "table" then
      local unavailable = ok and tostring(reason) or "call_failed:" .. tostring(snapshot)
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=" .. unavailable,
          "unavailable:" .. unavailable)
      return false, unavailable
    end
    local generation = tonumber(snapshot.generation)
    if generation == nil or generation < 1 or generation ~= math.floor(generation) then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=invalid_generation", "invalid_generation")
      return false, "invalid_generation"
    end
    if lastNativeGeneration ~= nil and generation < lastNativeGeneration then
      nativeNotice("NATIVE_AUTHORITY_STALE", "generation=" .. tostring(generation) ..
          " last=" .. tostring(lastNativeGeneration),
          "stale:" .. tostring(generation) .. ":" .. tostring(lastNativeGeneration))
      return false, "stale"
    end
    if lastNativeGeneration ~= nil and generation == lastNativeGeneration and
        not nativeAllowSameGenerationOnce then
      nativeNotice("NATIVE_AUTHORITY_STALE", "generation=" .. tostring(generation) ..
          " last=" .. tostring(lastNativeGeneration),
          "stale:" .. tostring(generation) .. ":" .. tostring(lastNativeGeneration))
      return false, "stale"
    end
    local sameGenerationReapply =
        lastNativeGeneration ~= nil and generation == lastNativeGeneration
    if type(snapshot.states) ~= "table" or snapshot.schema ~= 1 or
        type(snapshot.count) ~= "number" or snapshot.count ~= #rows or
        type(snapshot.aliveCount) ~= "number" or
        type(snapshot.killedCount) ~= "number" or
        snapshot.aliveCount + snapshot.killedCount ~= #rows or
        type(snapshot.explicitCount) ~= "number" or
        type(snapshot.absenceDefaultFalseCount) ~= "number" or
        snapshot.explicitCount + snapshot.absenceDefaultFalseCount ~= #rows then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=invalid_snapshot", "invalid_snapshot")
      return false, "invalid_snapshot"
    end
    local killedIds = {}
    for catalogueId, _ in pairs(byCatalogueId) do
      local value = snapshot.states[catalogueId]
      if type(value) ~= "boolean" then
        nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=incomplete_states", "incomplete_states")
        return false, "incomplete_states"
      end
      if value then killedIds[#killedIds + 1] = catalogueId end
    end
    if #killedIds ~= snapshot.killedCount then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=state_count_mismatch", "state_count_mismatch")
      return false, "state_count_mismatch"
    end
    local apply = _G.CompletionistMapV105ApplyPersistedRavenKills
    if type(apply) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=apply_api_unavailable", "apply_api_unavailable")
      return false, "apply_api_unavailable"
    end
    local applied, accepted = apply(killedIds, "native:" .. tostring(source) ..
        ":generation:" .. tostring(generation))
    if applied ~= true or accepted ~= #killedIds then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE", "reason=apply_refused", "apply_refused")
      return false, "apply_refused"
    end
    lastNativeGeneration = generation
    _G.CompletionistMapV105LastNativeRavenGeneration = generation
    nativeAllowSameGenerationOnce = false
    lastNativeNotice = nil
    log("NATIVE_AUTHORITY_APPLIED", "generation=" .. tostring(generation) ..
        " killed=" .. tostring(snapshot.killedCount) ..
        " alive=" .. tostring(snapshot.aliveCount) ..
        " explicit=" .. tostring(snapshot.explicitCount) ..
        " absentWadFalse=" .. tostring(snapshot.absenceDefaultFalseCount) ..
        " sameGenerationResetReapply=" .. tostring(sameGenerationReapply))
    return true, nil
  end

  local function rememberMarkerId(name, info)
    if type(name) ~= "string" or type(info) ~= "table" or info.Id == nil then return end
    byMarkerId[tostring(info.Id)] = name
  end

  local function markerInfo(name)
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(name) end)
    if not ok or type(info) ~= "table" or info.Id == nil then return nil end
    rememberMarkerId(name, info)
    return info
  end

  local function knownNameForId(id)
    if id == nil then return nil end
    local key = tostring(id)
    local cached = byMarkerId[key]
    if cached ~= nil then return cached end
    for name, _ in pairs(byName) do
      local info = markerInfo(name)
      if info ~= nil and tostring(info.Id) == key then return name end
    end
    return nil
  end

  local function recycle(go)
    if go == nil then return true end
    local ok = pcall(function() Map.RecycleIcon(go) end)
    return ok
  end

  local function clearLegacy(self)
    if self.completionistSharedLoaderTwinGO ~= nil then
      recycle(self.completionistSharedLoaderTwinGO)
      self.completionistSharedLoaderTwinGO = nil
    end
    if self.completionistMapV100MapIconGO ~= nil then
      recycle(self.completionistMapV100MapIconGO)
      self.completionistMapV100MapIconGO = nil
    end
    self.completionistMapV100Selected = false
  end

  local function clearSelection(self, reason)
    local selected = self and self.completionistMapV105SelectedRaven or nil
    if selected ~= nil then
      log("SELECT_DISARM", "reason=" .. tostring(reason) ..
          " name=" .. selected.Name .. " uid=" .. selected.IdString)
    end
    selectionGeneration = selectionGeneration + 1
    if self ~= nil then self.completionistMapV105SelectedRaven = nil end
  end

  local function clearIcons(self, reason)
    local icons = self.completionistMapV105RavenIcons or {}
    for name, go in pairs(icons) do
      recycle(go)
      if self.mapIconCollision == go then self.mapIconCollision = nil end
      icons[name] = nil
    end
    self.completionistMapV105RavenIcons = icons
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    clearSelection(self, reason)
  end

  local function syncIcons(self, reason)
    if self == nil then return end
    lastMapOnSelf = self
    clearLegacy(self)
    local icons = self.completionistMapV105RavenIcons or {}
    self.completionistMapV105RavenIcons = icons
    local realm = self.currRealmName
    for name, go in pairs(icons) do
      local row = byName[name]
      if row == nil or row.Realm ~= realm or isCollected(row.CatalogueId) then
        recycle(go)
        if self.mapIconCollision == go then self.mapIconCollision = nil end
        icons[name] = nil
      end
    end
    for _, row in ipairs(rows) do
      if row.Realm == realm and shouldShow(row.CatalogueId) and icons[row.Name] == nil then
        local ok, value = pcall(function()
          local info = markerInfo(row.Name)
          if info == nil then return nil, "marker_info" end
          local found, region = Map.FindRegionFromMarker(info.Id)
          if found ~= true or region == nil then return nil, "region" end
          return Map.CreateMarkerIcon(info.Id, region, ""), nil
        end)
        local go = ok and value or nil
        if go ~= nil then
          icons[row.Name] = go
          go:Show()
        else
          log("ICON_CREATE_FAILED", "name=" .. row.Name .. " reason=" .. tostring(reason))
        end
      end
    end
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, currState)
    lastMapOnSelf = nil
    local refreshed, refreshReason = refreshNativeAuthority("map_create")
    log("NATIVE_AUTHORITY_REFRESH", "source=map_create result=" ..
        (refreshed and "applied" or tostring(refreshReason)) ..
        " lastGeneration=" .. tostring(lastNativeGeneration))
    local result = createPins(self, currState)
    syncIcons(self, "map_create")
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    assert(type(previous) == "function", "Missing map lifecycle method: " .. method)
    MapOn[method] = function(self, ...)
      clearIcons(self, "map_teardown:" .. method)
      if lastMapOnSelf == self then lastMapOnSelf = nil end
      return previous(self, ...)
    end
  end

  local function collisionSelection(self, collisionTable)
    local icons = self.completionistMapV105RavenIcons or {}
    for _, collision in ipairs(collisionTable or {}) do
      for name, go in pairs(icons) do
        if collision == go then
          local row = byName[name]
          if row ~= nil and shouldShow(row.CatalogueId) then
            local info = markerInfo(name)
            if info ~= nil then
              return {
                Family = "raven", Name = name, CatalogueId = row.CatalogueId,
                Id = info.Id, IdString = tostring(info.Id), ObjectRef = go,
                State = "candidate-custom", Source = "exact_collision_object",
              }
            end
          end
        end
      end
    end
    return nil
  end

  local function captureSelection(self, selected)
    selectionGeneration = selectionGeneration + 1
    selected.Generation = selectionGeneration
    self.completionistMapV105SelectedRaven = selected
    log("SELECT_CANDIDATE", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " source=" .. selected.Source)
  end

  local function currentSelection(self)
    local selected = self and self.completionistMapV105SelectedRaven or nil
    if selected == nil then return nil end
    local icons = self.completionistMapV105RavenIcons or {}
    if selected.Generation ~= selectionGeneration or
        icons[selected.Name] ~= selected.ObjectRef or
        not shouldShow(selected.CatalogueId) then
      clearSelection(self, "candidate_no_longer_exact")
      return nil
    end
    return selected
  end

  local function promptOwned(self, show, selected)
    if show ~= true or selected == nil then return false end
    if self.currMarkerID ~= nil then
      return tostring(self.currMarkerID) == selected.IdString
    end
    return selected.Name == provenName and self.completionistMapV100Selected == true and
      self.completionistMapV100NornirSelected == nil and
      self.completionistMapV100NornirChestSelected == nil
  end

  local function customIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function stockIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function contains(ids, idString)
    for _, id in ipairs(ids or {}) do
      if tostring(id) == idString then return true end
    end
    return false
  end

  local function hideCustom(exceptIdString, reason)
    local ids, ok, err = customIds()
    if not ok then return false, 0, err end
    local hidden = 0
    for _, id in ipairs(ids) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then
        local target = knownNameForId(id) or id
        local hideOK = pcall(function() game.Compass.HideMarker(target) end)
        if not hideOK then return false, hidden, "hide_failed:" .. tostring(id) end
        hidden = hidden + 1
      end
    end
    return true, hidden, nil
  end

  local function hideStock(reason)
    local ids, ok, err = stockIds()
    if not ok then return false, 0, err end
    local hidden = 0
    for _, id in ipairs(ids) do
      local hideOK = pcall(function() game.Compass.HideMarker(id) end)
      if not hideOK then return false, hidden, "hide_failed:" .. tostring(id) end
      hidden = hidden + 1
    end
    return true, hidden, nil
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_RAVEN_HUD_DISABLED", "reason=custom_raven_compass_owner")
    end
  end

  local function promptText(selected)
    if promptIntent ~= nil and promptIntent.IdString == selected.IdString then
      if promptIntent.State == "tracked" then
        return actionText(lamsConsts.RemoveFromCompass)
      elseif promptIntent.State == "untracked" then
        local ids, customOK = customIds()
        local hasOtherCustom = false
        if customOK then
          for _, id in ipairs(ids) do
            if tostring(id) ~= selected.IdString then
              hasOtherCustom = true
              break
            end
          end
        end
        local stock, stockOK = stockIds()
        if hasOtherCustom or (stockOK and #stock > 0) then
          return actionText(lamsConsts.ReplaceInCompass)
        end
        return actionText(lamsConsts.AddToCompass)
      end
    end
    local ids, ok = customIds()
    if ok and contains(ids, selected.IdString) then
      return actionText(lamsConsts.RemoveFromCompass)
    end
    local stock = stockIds()
    if #ids > 0 or #stock > 0 then
      return actionText(lamsConsts.ReplaceInCompass)
    end
    return actionText(lamsConsts.AddToCompass)
  end

  local function refreshPrompt(self, selected)
    if self == nil or self.menu == nil or selected == nil then return end
    local text = promptText(selected)
    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    if goMapCursorText ~= nil then
      goMapCursorText:Show()
      local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if top ~= nil then
        local handle = util.GetTextHandle(top, "CursorAction_Text")
        if handle ~= nil then
          UI.SetTextIsClickable(handle)
          UI.SetText(handle, text)
        end
        top:Show()
      end
    end
    self.menu:UpdateFooterButton("ShowOnCompass", true, text)
    self.menu:UpdateFooterButtonText()
    log("PROMPT_REFRESH", "name=" .. selected.Name ..
        " state=" .. tostring(promptIntent and promptIntent.State or "observed") ..
        " text=" .. tostring(text))
  end

  local function showRavenReticle(self, currState, selected)
    if self == nil or currState == nil or selected == nil then return end
    local ok, err = pcall(function()
      self:SetReticleInfo(currState, "Odin's Raven", "Completionist Map")
    end)
    if ok then
      log("RETICLE", "name=" .. selected.Name ..
          " title=Odin's Raven subtitle=Completionist Map")
    else
      log("RETICLE_FAILED", "name=" .. selected.Name .. " error=" .. tostring(err))
    end
  end

  function MapOn:MapCollisionChangeHandler(currState, collisionTable, realmName)
    lastMapOnSelf = self
    local selected = collisionSelection(self, collisionTable)
    if selected ~= nil then captureSelection(self, selected) end
    local result = previousCollision(self, currState, collisionTable, realmName)
    if selected ~= nil and currentSelection(self) ~= nil then
      showRavenReticle(self, currState, selected)
    end
    return result
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    lastMapOnSelf = self
    local show, text = previousPrompt(self, currMenu)
    local selected = currentSelection(self)
    if selected == nil then return show, text end
    if not promptOwned(self, show, selected) then
      clearSelection(self, "prompt_owner_mismatch")
      return show, text
    end
    selected.State = "armed-custom"
    log("SELECT_ARM", "name=" .. selected.Name .. " uid=" .. selected.IdString)
    return true, promptText(selected)
  end

  function MapOn:ShowOnCompass(currState)
    lastMapOnSelf = self
    local selected = currentSelection(self)
    if selected == nil then
      customCompassOwnsTarget = false
      promptIntent = nil
      local customOK = hideCustom(nil, "other_target_replace")
      if not customOK then return end
      _G.CompletionistMapV105TrackedCatalogueId = nil
      return previousShow(self, currState)
    end
    if selected.State ~= "armed-custom" or not promptOwned(self, true, selected) then
      clearSelection(self, "action_not_exact")
      return
    end
    clearSelection(self, "SELECT_CONSUME")
    if not shouldShow(selected.CatalogueId) then return end
    customCompassOwnsTarget = true
    local ids, queryOK = customIds()
    if not queryOK then return end
    if contains(ids, selected.IdString) then
      local ok = pcall(function() game.Compass.HideMarker(selected.Name) end)
      if ok then
        if _G.CompletionistMapV105TrackedCatalogueId == selected.CatalogueId then
          _G.CompletionistMapV105TrackedCatalogueId = nil
        end
        self.currShownMarkerID = nil
        promptIntent = {
          IdString=selected.IdString, State="untracked",
          Name=selected.Name, CatalogueId=selected.CatalogueId,
        }
        promptSettleFrames = 0
        promptSettleBucket = -1
        suppressLegacyRavenHud()
        hideStock("raven_remove_guard")
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshPrompt(self, selected)
        log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString)
      end
      return
    end
    local customOK, customCount = hideCustom(selected.IdString, "raven_replace")
    local stockOK, stockCount = hideStock("raven_replace")
    if not customOK or not stockOK then return end
    suppressLegacyRavenHud()
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    if not showOK then
      log("SHOW_FAILED", "name=" .. selected.Name .. " error=" .. tostring(showErr))
      return
    end
    suppressLegacyRavenHud()
    hideStock("raven_post_show_guard")
    _G.CompletionistMapV105TrackedCatalogueId = selected.CatalogueId
    self.currShownMarkerID = selected.Id
    promptIntent = {
      IdString=selected.IdString, State="tracked",
      Name=selected.Name, CatalogueId=selected.CatalogueId,
    }
    promptSettleFrames = 0
    promptSettleBucket = -1
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshPrompt(self, selected)
    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " replacedCustomCount=" .. tostring(customCount) ..
        " replacedStockCount=" .. tostring(stockCount))
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)

    if customCompassOwnsTarget then
      suppressLegacyRavenHud()
      local stock, stockOK = stockIds()
      if stockOK and #stock > 0 then
        hideStock("custom_raven_owner_guard")
      end
    end

    if nativeResetRecheckFrames > 0 then
      nativeResetRecheckFrames = nativeResetRecheckFrames - 1
      local elapsed = nativeResetRecheckLimit - nativeResetRecheckFrames
      local bucket = math.floor(elapsed / 30)
      if elapsed == 1 or bucket ~= nativeResetRecheckBucket then
        nativeResetRecheckBucket = bucket
        local refreshed, reason = refreshNativeAuthority("post_reset_recheck")
        log("NATIVE_AUTHORITY_RECHECK", "frame=" .. tostring(elapsed) ..
            " result=" .. (refreshed and "applied" or tostring(reason)) ..
            " lastGeneration=" .. tostring(lastNativeGeneration))
      end
      if nativeResetRecheckFrames == 0 then
        nativeResetRecheckBucket = -1
        log("NATIVE_AUTHORITY_RECHECK_DONE",
            "lastGeneration=" .. tostring(lastNativeGeneration))
      end
    end

    if promptIntent == nil then return result end

    local intent = promptIntent
    local row = intent.Name and byName[intent.Name] or nil
    if row == nil or tostring(row.CatalogueId) ~= tostring(intent.CatalogueId) then
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=identity_missing id=" .. tostring(intent.IdString))
      return result
    end

    local info = markerInfo(row.Name)
    if info == nil or tostring(info.Id) ~= intent.IdString then
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=uid_changed name=" .. tostring(row.Name))
      return result
    end

    local selected = {
      Name=row.Name, CatalogueId=row.CatalogueId,
      Id=info.Id, IdString=tostring(info.Id),
    }
    local custom, customOK = customIds()
    local stock, stockOK = stockIds()
    suppressLegacyRavenHud()

    if intent.State == "tracked" then
      if customOK and stockOK and contains(custom, intent.IdString) and #stock == 0 then
        promptIntent = nil
        promptSettleFrames = 0
        promptSettleBucket = -1
        refreshPrompt(self, selected)
        log("PROMPT_SETTLED", "state=tracked name=" .. row.Name)
      else
        promptSettleFrames = promptSettleFrames + 1
        local bucket = math.floor(promptSettleFrames / 30)
        if stockOK and #stock > 0 and
            (promptSettleFrames == 1 or bucket ~= promptSettleBucket) then
          promptSettleBucket = bucket
          hideStock("raven_replace_async_retry")
        end
        refreshPrompt(self, selected)
      end
    elseif intent.State == "untracked" then
      if customOK and not contains(custom, intent.IdString) then
        promptIntent = nil
        promptSettleFrames = 0
        promptSettleBucket = -1
        refreshPrompt(self, selected)
        log("PROMPT_SETTLED", "state=untracked name=" .. row.Name)
      else
        promptSettleFrames = promptSettleFrames + 1
        local bucket = math.floor(promptSettleFrames / 30)
        if customOK and contains(custom, intent.IdString) and
            (promptSettleFrames == 1 or bucket ~= promptSettleBucket) then
          promptSettleBucket = bucket
          pcall(function() game.Compass.HideMarker(row.Name) end)
        end
        refreshPrompt(self, selected)
      end
    else
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=invalid_state state=" .. tostring(intent.State))
    end
    return result
  end

  local function hideExactTracked(row)
    if _G.CompletionistMapV105TrackedCatalogueId ~= row.CatalogueId then return end
    local info = markerInfo(row.Name)
    if info == nil then return end
    local ids, ok = customIds()
    if ok and contains(ids, tostring(info.Id)) then
      pcall(function() game.Compass.HideMarker(row.Name) end)
    end
    if customCompassOwnsTarget then
      suppressLegacyRavenHud()
      hideStock("tracked_raven_collected")
    end
    _G.CompletionistMapV105TrackedCatalogueId = nil
  end

  _G.CompletionistMapV105PublishRavenState = function(catalogueId, collected, source)
    local row = byCatalogueId[catalogueId]
    if row == nil or type(collected) ~= "boolean" then return false end
    states[catalogueId] = collected
    if collected then hideExactTracked(row) end
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "state:" .. tostring(source)) end
    log("STATE", "catalogueId=" .. catalogueId .. " collected=" .. tostring(collected) ..
        " source=" .. tostring(source) .. " progressionWrites=false")
    return true
  end

  _G.CompletionistMapV105ApplyPersistedRavenKills = function(catalogueIds, source)
    if type(catalogueIds) ~= "table" then return false, 0 end
    for catalogueId, _ in pairs(states) do states[catalogueId] = nil end
    local accepted = 0
    for key, value in pairs(catalogueIds) do
      local catalogueId = nil
      if type(key) == "number" then
        catalogueId = value
      elseif value == true then
        catalogueId = key
      end
      local row = byCatalogueId[catalogueId]
      if row ~= nil and states[catalogueId] ~= true then
        states[catalogueId] = true
        accepted = accepted + 1
        hideExactTracked(row)
      end
    end
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "persisted:" .. tostring(source)) end
    log("PERSISTED_KILLS", "source=" .. tostring(source) ..
        " accepted=" .. tostring(accepted) .. " catalogueDefaultVisible=true progressionWrites=false")
    return true, accepted
  end

  _G.CompletionistMapV105ResetRavenStates = function(source)
    for catalogueId, _ in pairs(states) do states[catalogueId] = nil end
    if lastMapOnSelf ~= nil then
      clearIcons(lastMapOnSelf, "state_reset:" .. tostring(source))
    end
    _G.CompletionistMapV105TrackedCatalogueId = nil
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    nativeAllowSameGenerationOnce = true
    nativeResetRecheckFrames = nativeResetRecheckLimit
    nativeResetRecheckBucket = -1
    log("STATE_RESET", "source=" .. tostring(source) ..
        " staleStateRetained=false catalogueDefaultVisible=true progressionWrites=false" ..
        " sameGenerationNativeReapplyOnce=true postResetRecheckFrames=" ..
        tostring(nativeResetRecheckLimit))
    return true
  end

  for catalogueId, value in pairs(_G.CompletionistMapV105PendingRavenState or {}) do
    _G.CompletionistMapV105PublishRavenState(catalogueId, value, "pending")
  end
  _G.CompletionistMapV105PendingRavenState = {}
  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " mapResource=" .. mapResource .. " compassClass=" .. ravenClass ..
      " exactCollisionRequired=true markerIdAloneInfersRaven=false" ..
      " permanentPolling=false postResetBoundedRefresh=true progressionWrites=false catalogueDefaultVisible=true" ..
      " persistedKillBootstrap=true nativeAuthority=loopback_map_open" ..
      " nativePort=" .. tostring(nativePort) .. " staticDescriptorWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVENS
