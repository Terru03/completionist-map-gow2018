-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS
-- Data drives all Raven work. Catalogue Ravens are visible unless explicitly collected.
do
  local prefix = "[CompletionistMap v0.10.5-all-ravens] "
  local ravenClass = "CompletionistRaven"
  local mapResource = "goMapIconCompletionistRaven"
  local markerLabel = "Odin's Raven"
  local provenName = "Completionist_V103_Veithurgard_Raven_01"
  local rows = {
-- @@RAVEN_CATALOGUE_ROWS@@
  }
  local function compactIdentity(value)
    return string.gsub(string.lower(tostring(value or "")), "[^a-z0-9]", "")
  end

  local function compactWadIdentity(value)
    local text = string.lower(tostring(value or ""))
    text = string.gsub(text, "%.wad$", "")
    text = string.gsub(text, "^wad_", "")
    return string.gsub(text, "[^a-z0-9]", "")
  end

  local byName = {}
  local byCatalogueId = {}
  local byPersistedIdentity = {}
  local byPersistedIdentityNoGo = {}
  for _, row in ipairs(rows) do
    byName[row.Name] = row
    byCatalogueId[row.CatalogueId] = row
    local fullKey = row.WadKey .. "|" .. row.ObjectKey
    assert(byPersistedIdentity[fullKey] == nil, "Duplicate persisted Raven identity: " .. fullKey)
    byPersistedIdentity[fullKey] = row
    local noGoObject = string.gsub(row.ObjectKey, "^go", "")
    local noGoKey = row.WadKey .. "|" .. noGoObject
    assert(byPersistedIdentityNoGo[noGoKey] == nil, "Duplicate persisted Raven fallback identity: " .. noGoKey)
    byPersistedIdentityNoGo[noGoKey] = row
  end

  local byWad = {}
  local byParent = {}
  local unsafeParent = {}
  for _, row in ipairs(rows) do
    byWad[row.WadKey] = byWad[row.WadKey] or {}
    table.insert(byWad[row.WadKey], row)
    byParent[row.ParentQuest] = byParent[row.ParentQuest] or {}
    table.insert(byParent[row.ParentQuest], row)
    if row.AggregateSafe ~= true then unsafeParent[row.ParentQuest] = true end
  end

  local byMarkerId = {}

  local states = _G.CompletionistMapV105RavenState or {}
  _G.CompletionistMapV105RavenState = states
  local liveStatePublished = {}
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousCollision = MapOn.MapCollisionChangeHandler
  local lastMapOnSelf = nil
  local selectionGeneration = 0
  local hideExactTracked

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function isCollected(catalogueId)
    return states[catalogueId] == true
  end

  local function shouldShow(catalogueId)
    return byCatalogueId[catalogueId] ~= nil and not isCollected(catalogueId)
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
    clearSelection(self, reason)
  end

  local function syncIcons(self, reason)
    if self == nil then return end
    lastMapOnSelf = self
    clearLegacy(self)
    local icons = self.completionistMapV105RavenIcons or {}
    self.completionistMapV105RavenIcons = icons
    local realm = self.currRealmName
    if self.completionistMapV105LastRealm ~= nil and self.completionistMapV105LastRealm ~= realm then
      clearSelection(self, "realm_change")
      log("REALM_CHANGE", "from=" .. tostring(self.completionistMapV105LastRealm) .. " to=" .. tostring(realm))
    end
    self.completionistMapV105LastRealm = realm
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
          return Map.CreateMarkerIcon(info.Id, region, markerLabel), nil
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

  local function quotedIdentity(value)
    local text = tostring(value or "")
    return string.match(text, "'([^']+)'") or text
  end

  local function persistedRowForObject(object)
    if object == nil then return nil, "object_nil" end
    local levelOK, level = pcall(function() return object.Level end)
    if not levelOK or level == nil then return nil, "level_unavailable" end
    local wadKey = compactWadIdentity(quotedIdentity(level))
    if wadKey == "" then return nil, "level_identity_empty" end

    -- Native position is a stronger identity than the exposed Lua GameObject name:
    -- multiple Raven instances can intentionally share the same name/prototype.
    local positionOK, position = pcall(function() return object:GetWorldPosition() end)
    if positionOK and position ~= nil and
        tonumber(position.x) ~= nil and tonumber(position.y) ~= nil and tonumber(position.z) ~= nil then
      local positionHit = nil
      for _, row in ipairs(byWad[wadKey] or {}) do
        local dx = tonumber(position.x) - row.X
        local dy = tonumber(position.y) - row.Y
        local dz = tonumber(position.z) - row.Z
        if dx * dx + dy * dy + dz * dz <= 0.25 then
          if positionHit ~= nil and positionHit.CatalogueId ~= row.CatalogueId then
            return nil, "ambiguous_position"
          end
          positionHit = row
        end
      end
      if positionHit ~= nil then return positionHit, nil end
    end

    local candidates = {}
    local function addCandidate(value)
      if value == nil then return end
      local key = compactIdentity(quotedIdentity(value))
      if key ~= "" then candidates[#candidates + 1] = key end
    end
    addCandidate(object)
    local debugPathOK, debugPath = pcall(function() return object:GetDebugPath() end)
    if debugPathOK then addCandidate(debugPath) end
    local nameOK, objectName = pcall(function() return object:GetName() end)
    if nameOK then addCandidate(objectName) end

    local hit = nil
    for _, objectKey in ipairs(candidates) do
      local row = byPersistedIdentity[wadKey .. "|" .. objectKey]
      if row == nil then
        local noGoObject = string.gsub(objectKey, "^go", "")
        row = byPersistedIdentityNoGo[wadKey .. "|" .. noGoObject]
      end
      if row ~= nil then
        if hit ~= nil and hit.CatalogueId ~= row.CatalogueId then
          return nil, "ambiguous_identity"
        end
        hit = row
      end
    end
    if hit == nil then return nil, "no_catalogue_identity" end
    return hit, nil
  end

  local function bootstrapPersistedRavenState(source)
    if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then
      log("PERSISTED_SCAN_REFUSED", "source=" .. tostring(source) .. " reason=registry_unavailable")
      return false, 0, 0
    end
    local registryOK, registry = pcall(debug.getregistry)
    if not registryOK or type(registry) ~= "table" then
      log("PERSISTED_SCAN_REFUSED", "source=" .. tostring(source) .. " reason=registry_failed")
      return false, 0, 0
    end

    local seenPickles = {}
    local observed = {}
    local observedRank = {}
    local conflicted = {}
    local roots, records, matched, ambiguous = 0, 0, 0, 0
    for _, root in pairs(registry) do
      if type(root) == "table" then
        for _, pickleName in ipairs({"__PickleTable", "__SoftPickleTable"}) do
          local pickle = rawget(root, pickleName)
          if type(pickle) == "table" and not seenPickles[pickle] then
            seenPickles[pickle] = true
            roots = roots + 1
            local rank = pickleName == "__PickleTable" and 2 or 1
            local subobjects = rawget(pickle, "__subobjs")
            if type(subobjects) == "table" then
              for object, savedInfo in pairs(subobjects) do
                local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
                if type(killed) == "boolean" then
                  records = records + 1
                  local row = persistedRowForObject(object)
                  if row ~= nil then
                    matched = matched + 1
                    local id = row.CatalogueId
                    local previousRank = observedRank[id]
                    if previousRank == nil or rank > previousRank then
                      observed[id] = killed
                      observedRank[id] = rank
                      conflicted[id] = nil
                    elseif rank == previousRank and observed[id] ~= killed then
                      conflicted[id] = true
                    end
                  end
                end
              end
            end
          end
        end
      end
    end

    local killedCount, aliveCount = 0, 0
    for catalogueId, killed in pairs(observed) do
      if conflicted[catalogueId] then
        ambiguous = ambiguous + 1
      elseif not liveStatePublished[catalogueId] then
        states[catalogueId] = killed
        local row = byCatalogueId[catalogueId]
        if killed then
          killedCount = killedCount + 1
          hideExactTracked(row)
        else
          aliveCount = aliveCount + 1
        end
      end
    end
    log("PERSISTED_SCAN", "source=" .. tostring(source) ..
        " roots=" .. tostring(roots) .. " records=" .. tostring(records) ..
        " matched=" .. tostring(matched) .. " killed=" .. tostring(killedCount) ..
        " alive=" .. tostring(aliveCount) .. " ambiguous=" .. tostring(ambiguous) ..
        " liveOverrides=true progressionWrites=false")
    return roots > 0, killedCount, aliveCount
  end

  local aggregatePublished = {}

  local function bootstrapAggregateRavenState(source)
    -- Remove only state derived by the previous aggregate pass. Exact live/pickle
    -- observations remain authoritative and are applied separately.
    for catalogueId, _ in pairs(aggregatePublished) do
      if not liveStatePublished[catalogueId] then states[catalogueId] = nil end
      aggregatePublished[catalogueId] = nil
    end

    if type(game) ~= "table" or type(game.QuestManager) ~= "table" or
        type(game.QuestManager.GetQuestProgressAndGoal) ~= "function" then
      log("AGGREGATE_SCAN_REFUSED", "source=" .. tostring(source) .. " reason=quest_api_unavailable")
      return false, 0, 0, 0
    end

    local parents, completeParents, hidden, refused = 0, 0, 0, 0
    for parent, parentRows in pairs(byParent) do
      parents = parents + 1
      if unsafeParent[parent] then
        refused = refused + 1
        log("AGGREGATE_PARENT_SKIPPED", "parent=" .. tostring(parent) ..
            " reason=bonus_untracked_raven catalogueCount=" .. tostring(#parentRows))
      else
        local callOK, queryOK, progress, goal = pcall(
          game.QuestManager.GetQuestProgressAndGoal, parent
        )
        progress, goal = tonumber(progress), tonumber(goal)
        if callOK and queryOK == true and progress ~= nil and goal ~= nil and
            goal == #parentRows and progress >= goal then
          completeParents = completeParents + 1
          for _, row in ipairs(parentRows) do
            if not liveStatePublished[row.CatalogueId] then
              states[row.CatalogueId] = true
              aggregatePublished[row.CatalogueId] = true
              hidden = hidden + 1
              hideExactTracked(row)
            end
          end
        end
        log("AGGREGATE_PARENT", "parent=" .. tostring(parent) ..
            " callOK=" .. tostring(callOK) .. " queryOK=" .. tostring(queryOK) ..
            " progress=" .. tostring(progress) .. " goal=" .. tostring(goal) ..
            " catalogueCount=" .. tostring(#parentRows) ..
            " completeApplied=" .. tostring(
              callOK and queryOK == true and progress ~= nil and goal ~= nil and
              goal == #parentRows and progress >= goal
            ))
      end
    end

    log("AGGREGATE_SCAN", "source=" .. tostring(source) ..
        " parents=" .. tostring(parents) ..
        " completeParents=" .. tostring(completeParents) ..
        " hidden=" .. tostring(hidden) ..
        " unsafeParents=" .. tostring(refused) ..
        " partialUnknownVisible=true progressionWrites=false")
    return true, completeParents, hidden, refused
  end

  local function logUIStateBootstrap(source)
    local known, killed, alive = 0, 0, 0
    for catalogueId, value in pairs(states) do
      if byCatalogueId[catalogueId] ~= nil and type(value) == "boolean" then
        known = known + 1
        if value then killed = killed + 1 else alive = alive + 1 end
      end
    end
    log("UI_STATE_BOOTSTRAP", "source=" .. tostring(source) ..
        " known=" .. tostring(known) ..
        " killed=" .. tostring(killed) ..
        " alive=" .. tostring(alive) ..
        " generation=" .. tostring(_G.CompletionistMapV105RavenStateGeneration or 0) ..
        " progressionWrites=false")
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, currState)
    local result = createPins(self, currState)
    logUIStateBootstrap("map_create")
    bootstrapAggregateRavenState("map_create")
    bootstrapPersistedRavenState("map_create")
    syncIcons(self, "map_create")
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    assert(type(previous) == "function", "Missing map lifecycle method: " .. method)
    MapOn[method] = function(self, ...)
      clearIcons(self, "map_teardown:" .. method)
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

  local function promptText(selected)
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

  local function refreshPrompt(self, currState, selected, forcedLamsId, reason)
    if self == nil or selected == nil then return end
    local show = shouldShow(selected.CatalogueId)
    local text = show and actionText(forcedLamsId or lamsConsts.AddToCompass) or ""

    local cursorOK, cursorErr = pcall(function()
      local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
      if goMapCursorText == nil then return end
      goMapCursorText:Show()
      local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if top == nil then return end
      local handle = util.GetTextHandle(top, "CursorAction_Text")
      if handle ~= nil then
        UI.SetTextIsClickable(handle)
        UI.SetText(handle, text)
      end
      if show then top:Show() else top:Hide() end
    end)

    local menu = nil
    if type(currState) == "table" then menu = currState.menu end
    if menu == nil then menu = self.menu end
    local footerOK, footerErr = true, nil
    if menu ~= nil and type(menu.UpdateFooterButton) == "function" then
      footerOK, footerErr = pcall(function()
        menu:UpdateFooterButton("ShowOnCompass", show, text)
        if type(menu.UpdateFooterButtonText) == "function" then
          menu:UpdateFooterButtonText()
        end
      end)
    end

    log("PROMPT_REFRESH", "reason=" .. tostring(reason) ..
        " name=" .. selected.Name ..
        " uid=" .. selected.IdString ..
        " visible=" .. tostring(show) ..
        " text=" .. tostring(text) ..
        " cursorOK=" .. tostring(cursorOK) ..
        " cursorError=" .. tostring(cursorErr) ..
        " footerOK=" .. tostring(footerOK) ..
        " footerError=" .. tostring(footerErr))
  end

  function MapOn:MapCollisionChangeHandler(currState, collisionTable, realmName)
    lastMapOnSelf = self
    local selected = collisionSelection(self, collisionTable)
    if selected ~= nil then captureSelection(self, selected) end

    local result = previousCollision(self, currState, collisionTable, realmName)

    if selected ~= nil and type(MapOn.SetReticleInfo) == "function" then
      local ok, err = pcall(MapOn.SetReticleInfo, self, currState, markerLabel, "")
      if ok then
        log("RETICLE_TEXT", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
            " title=" .. markerLabel)
      else
        log("RETICLE_TEXT_FAILED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
            " error=" .. tostring(err))
      end
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
    local ids, queryOK = customIds()
    if not queryOK then return end
    if contains(ids, selected.IdString) then
      local ok = pcall(function() game.Compass.HideMarker(selected.Name) end)
      if ok then
        if _G.CompletionistMapV105TrackedCatalogueId == selected.CatalogueId then
          _G.CompletionistMapV105TrackedCatalogueId = nil
        end
        self.currShownMarkerID = nil
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshPrompt(self, currState, selected, lamsConsts.AddToCompass, "remove")
        log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString)
      end
      return
    end
    local customOK, customCount = hideCustom(selected.IdString, "raven_replace")
    local stockOK, stockCount = hideStock("raven_replace")
    if not customOK or not stockOK then return end
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    if not showOK then
      log("SHOW_FAILED", "name=" .. selected.Name .. " error=" .. tostring(showErr))
      return
    end
    _G.CompletionistMapV105TrackedCatalogueId = selected.CatalogueId
    self.currShownMarkerID = selected.Id
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshPrompt(self, currState, selected, lamsConsts.RemoveFromCompass, "show")
    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " replacedCustomCount=" .. tostring(customCount) ..
        " replacedStockCount=" .. tostring(stockCount))
  end

  hideExactTracked = function(row)
    if _G.CompletionistMapV105TrackedCatalogueId ~= row.CatalogueId then return end
    local info = markerInfo(row.Name)
    if info == nil then return end
    local ids, ok = customIds()
    if ok and contains(ids, tostring(info.Id)) then
      pcall(function() game.Compass.HideMarker(row.Name) end)
    end
    _G.CompletionistMapV105TrackedCatalogueId = nil
  end

  _G.CompletionistMapV105PublishRavenState = function(catalogueId, collected, source)
    local row = byCatalogueId[catalogueId]
    if row == nil or type(collected) ~= "boolean" then return false end
    liveStatePublished[catalogueId] = true
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
    for catalogueId, _ in pairs(liveStatePublished) do liveStatePublished[catalogueId] = nil end
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

  _G.CompletionistMapV105BootstrapAggregateRavenState = function(source)
    local ok, completeParents, hidden, refused =
      bootstrapAggregateRavenState(source or "api")
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "aggregate_scan:" .. tostring(source)) end
    return ok, completeParents, hidden, refused
  end

  _G.CompletionistMapV105BootstrapPersistedRavenState = function(source)
    local ok, killed, alive = bootstrapPersistedRavenState(source or "api")
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "persisted_scan:" .. tostring(source)) end
    return ok, killed, alive
  end

  _G.CompletionistMapV105ResetRavenStates = function(source)
    for catalogueId, _ in pairs(states) do states[catalogueId] = nil end
    for catalogueId, _ in pairs(liveStatePublished) do liveStatePublished[catalogueId] = nil end
    if lastMapOnSelf ~= nil then
      clearIcons(lastMapOnSelf, "state_reset:" .. tostring(source))
    end
    _G.CompletionistMapV105TrackedCatalogueId = nil
    log("STATE_RESET", "source=" .. tostring(source) ..
        " staleStateRetained=false catalogueDefaultVisible=true progressionWrites=false")
    return true
  end

  for catalogueId, value in pairs(_G.CompletionistMapV105PendingRavenState or {}) do
    _G.CompletionistMapV105PublishRavenState(catalogueId, value, "pending")
  end
  _G.CompletionistMapV105PendingRavenState = {}
  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " mapResource=" .. mapResource .. " compassClass=" .. ravenClass ..
      " exactCollisionRequired=true markerIdAloneInfersRaven=false" ..
      " polling=false progressionWrites=false catalogueDefaultVisible=true" ..
      " persistedKillBootstrap=automaticReadOnlyPickleScan" ..
      " persistedIdentity=wadPlusPositionThenGameObject" ..
      " aggregateCompletedRegionBootstrap=true aggregateSurplusParentsFailOpen=true" ..
      " liveOverridesPersisted=true")
end
-- END COMPLETIONIST V0.10.5 ALL RAVENS
