-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST
-- Each Nornir family has its own map resource, compass class, and chest key.
do
  local rows = {
-- @@NORNIR_ROWS@@
  }
  local loadedPaths = {
-- @@NORNIR_LOADED_PATHS@@
  }
  local Saved = (function()
-- @@NORNIR_SAVED_READER@@
  end)()
  local savedContract = "@@NORNIR_SAVE_CONTRACT@@"
  local checkpointRows = {}
  for _, row in ipairs(rows) do
    if row.Family == "nornir_chest" then
      checkpointRows[#checkpointRows + 1] = {
        id = row.CatalogueId, family = row.Family,
      }
    end
  end
  local saved = Saved.New(checkpointRows, savedContract, nil, function()
    return tonumber(_G.CompletionistMapV105LastNativeRestoreEpoch)
  end)
  local byName, byKey, children = {}, {}, {}
  for _, row in ipairs(rows) do
    byName[row.Name] = row
    if row.EventKey then byKey[row.EventKey] = row end
    if row.ParentId then
      children[row.ParentId] = children[row.ParentId] or {}
      children[row.ParentId][string.lower(row.Reference)] = row
    end
  end
  local revealed, opened, solved = {}, {}, {}
  local activeMap = nil
  local targetRow = nil
  local captureReady = true
  local loadedReadFrames = 0
  local pendingSnapshots = {}

  local function hideTarget()
    if targetRow ~= nil then
      pcall(function() game.Compass.HideMarker(targetRow.Name) end)
      targetRow = nil
    end
  end

  local function filter(self)
    return self.filterButtonMapping and self.filterButtonMapping[self.filterIndex] or 1
  end

  local function visible(self, row)
    if self == nil or self.isOpenedForFastTravel then return false end
    local kind = filter(self)
    if kind ~= 1 and kind ~= -101 and
        not (kind == -103 and row.Family == "nornir_chest") and
        not (kind == -104 and row.Family ~= "nornir_chest") then
      return false
    end
    if kind == 1 then
      if _G.CompletionistMapV105ShowAll and not _G.CompletionistMapV105ShowAll() then return false end
    elseif kind < 0 then
      if _G.CompletionistMapV105ShowCategories and not _G.CompletionistMapV105ShowCategories() then return false end
    end
    if row.Family == "nornir_chest" then return not opened[row.CatalogueId] end
    return revealed[row.ParentId] == true and
      not opened[row.ParentId] and not solved[row.CatalogueId]
  end

  local function recycle(self)
    local icons = self.completionistMapV105NornirIdTestIcons or {}
    for name, icon in pairs(icons) do
      pcall(function() Map.RecycleIcon(icon) end)
      if self.mapIconCollision == icon then self.mapIconCollision = nil end
      icons[name] = nil
    end
    self.completionistMapV105NornirIdTestIcons = icons
    self.completionistMapV105NornirSelected = nil
  end

  local function sync(self)
    if self == nil then return end
    activeMap = self
    local icons = self.completionistMapV105NornirIdTestIcons or {}
    self.completionistMapV105NornirIdTestIcons = icons
    for name, icon in pairs(icons) do
      local row = byName[name]
      if row == nil or row.Realm ~= self.currRealmName or not visible(self, row) then
        pcall(function() Map.RecycleIcon(icon) end)
        if self.mapIconCollision == icon then self.mapIconCollision = nil end
        if self.completionistMapV105NornirSelected == row then
          self.completionistMapV105NornirSelected = nil
        end
        icons[name] = nil
      end
    end
    for _, row in ipairs(rows) do
      if row.Realm == self.currRealmName and visible(self, row) and
          icons[row.Name] == nil then
        local ok, icon = pcall(function()
          local info = game.Map.GetMarkerInfo(row.Name)
          if type(info) ~= "table" or info.Id == nil then return nil end
          if tostring(info.Id) ~= row.IdString then return nil end
          local found, region = Map.FindRegionFromMarker(info.Id)
          if found ~= true or region == nil then return nil end
          return Map.CreateMarkerIcon(info.Id, region, "")
        end)
        if ok and icon ~= nil then
          icons[row.Name] = icon
          pcall(function() icon:Show() end)
        else
          print("[CompletionistMapV105NornirIdTest] create_failed name=" .. row.Name)
        end
      end
    end
  end

  _G.CompletionistMapV105ResyncNornir = function(target)
    local map = target or activeMap
    if map ~= nil then
      sync(map)
    end
  end

  local function plainName(value)
    if type(value) ~= "string" then return nil end
    value = string.lower(value)
    if string.sub(value, 1, 2) == "go" then return string.sub(value, 3) end
    return value
  end

  local function exactPath(object, names)
    if object == nil or type(names) ~= "table" then return false end
    for _, expected in ipairs(names) do
      if object == nil or plainName(object:GetName()) ~= plainName(expected) then
        return false
      end
      object = object.Parent
    end
    return true
  end

  local function readLoadedParent(info)
    local level = game.FindLevel(info.Level)
    if level == nil then return nil end
    local placement = level:FindSingleGameObject(plainName(info.Path[1]))
    if not exactPath(placement, info.Path) then return nil end
    local script = placement:FindSingleGOByName(plainName(info.ScriptPath[1]))
    if not exactPath(script, info.ScriptPath) then return nil end
    local ancestor = script
    for _ = 1, #info.ScriptPath - #info.Path do
      ancestor = ancestor.Parent
    end
    if ancestor ~= placement then return nil end
    local owner = script
    if script.IsRefNode then
      owner = script.Child
      if owner == nil or owner.Parent ~= script then return nil end
    end
    return owner.LuaObjectScript.CompletionistNornirObserveSeals()
  end

  local function observeLoadedSeals()
    if type(game.FindLevel) ~= "function" then return false end
    local changed = false
    for _, parent in ipairs(rows) do
      local info = loadedPaths[parent.CatalogueId]
      if info ~= nil and not opened[parent.CatalogueId] then
        local ok, entries = pcall(readLoadedParent, info)
        if ok and type(entries) == "table" and #entries == 3 then
          local nextState, known = {}, true
          for _, entry in ipairs(entries) do
            local ref = type(entry.reference) == "string" and
              string.lower(entry.reference) or nil
            local child = ref and children[parent.CatalogueId] and
              children[parent.CatalogueId][ref]
            if child == nil or child.Family ~= "nornir_seal" or
                type(entry.broken) ~= "boolean" or
                nextState[child.CatalogueId] ~= nil then
              known = false
              break
            end
            nextState[child.CatalogueId] = entry.broken
          end
          if known then
            local count = 0
            local parentChanged = false
            for id, broken in pairs(nextState) do
              if broken then count = count + 1 end
              if (solved[id] == true) ~= broken then
                solved[id] = broken or nil
                changed = true
                parentChanged = true
              end
            end
            if parentChanged then
              print("[CompletionistMapV105Nornir] loaded_seals parent=" ..
                parent.CatalogueId .. " broken=" .. tostring(count))
            end
          end
        end
      end
    end
    if changed and targetRow ~= nil and solved[targetRow.CatalogueId] then
      hideTarget()
    end
    return changed
  end

  local function applySealSnapshot(parent, bits)
    if type(bits) ~= "string" or not string.match(bits, "^[01][01][01]$") then
      return false
    end
    local refs = {}
    for ref, child in pairs(children[parent.CatalogueId] or {}) do
      if child.Family == "nornir_seal" then refs[#refs + 1] = ref end
    end
    if #refs ~= 3 then return false end
    table.sort(refs)
    for index, ref in ipairs(refs) do
      local child = children[parent.CatalogueId][ref]
      solved[child.CatalogueId] =
        string.sub(bits, index, index) == "1" or nil
    end
    return true
  end

  local controller = {service = {epoch = 1}}
  function controller:BeginEpoch(epoch)
    if type(epoch) ~= "number" or epoch <= self.service.epoch then return false end
    self.service.epoch = epoch
    revealed, opened, solved = {}, {}, {}
    local snapshots = pendingSnapshots
    pendingSnapshots = {}
    for _, snapshot in pairs(snapshots) do
      applySealSnapshot(snapshot.parent, snapshot.bits)
    end
    saved:Reset(epoch)
    hideTarget()
    observeLoadedSeals()
    sync(activeMap)
    return true
  end
  controller.liveReader = {}
  function controller.liveReader:SetReady(ready)
    captureReady = ready == true
  end
  _G.CompletionistMapV105Nornir = controller
  saved:Reset(controller.service.epoch)

  local function acceptSaved()
    local snapshot = saved:Current(controller.service.epoch)
    if snapshot == nil then return end
    local changed = false
    for catalogueId, state in pairs(snapshot.states) do
      if state == 4 and not opened[catalogueId] then
        opened[catalogueId] = true
        revealed[catalogueId] = nil
        changed = true
      end
    end
    if not changed then return end
    if targetRow ~= nil and
        (opened[targetRow.CatalogueId] or
         (targetRow.ParentId and opened[targetRow.ParentId])) then
      hideTarget()
    end
    sync(activeMap)
    print("[CompletionistMapV105Nornir] checkpoint_opened epoch=" ..
      tostring(controller.service.epoch) .. " restoreEpoch=" ..
      tostring(snapshot.restoreEpoch))
  end

  local function accept(payload)
    if type(payload) ~= "string" then return end
    local action, key, ref = string.match(payload,
      "^NORNIR_V1\t([a-z]+)\t([^\t]+)\t(.*)$")
    local parent = key and byKey[key] or nil
    if parent == nil then return end
    if action == "attempt" and not opened[parent.CatalogueId] then
      revealed[parent.CatalogueId] = true
    elseif action == "opened" then
      opened[parent.CatalogueId] = true
      revealed[parent.CatalogueId] = nil
    elseif action == "seal" then
      local child = children[parent.CatalogueId] and
        children[parent.CatalogueId][ref]
      if child ~= nil and child.Family == "nornir_seal" then
        solved[child.CatalogueId] = true
      end
    elseif action == "snapshot" then
      if not applySealSnapshot(parent, ref) then return end
      pendingSnapshots[parent.CatalogueId] = {parent = parent, bits = ref}
    else
      return
    end
    print("[CompletionistMapV105Nornir] received=" .. action ..
      " key=" .. key .. " parent=" .. parent.CatalogueId)
    if targetRow ~= nil and
        (opened[targetRow.CatalogueId] or
        (targetRow.ParentId and (opened[targetRow.ParentId] or
        solved[targetRow.CatalogueId]))) then
      hideTarget()
    end
    sync(activeMap)
  end

  local hookOK, thunk = pcall(require, "core.thunk")
  if hookOK and type(thunk) == "table" and type(thunk.Install) == "function" then
    thunk.Install("COMPLETIONIST_NORNIR_EVENT_V1", function(...)
      for index = 1, select("#", ...) do
        local value = select(index, ...)
        if type(value) == "string" and
            string.sub(value, 1, 10) == "NORNIR_V1\t" then
          accept(value)
        end
      end
    end)
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, ...)
    local firstOpen = activeMap ~= self
    local result = createPins(self, ...)
    if firstOpen then
      local ok, status = false, "capture_not_ready"
      if captureReady then
        ok, status = saved:ReadOnce(controller.service.epoch)
        if ok then acceptSaved() end
      end
      print("[CompletionistMapV105Nornir] checkpoint_initial=" ..
        tostring(ok) .. " reason=" .. tostring(status) ..
        " epoch=" .. tostring(controller.service.epoch))
      loadedReadFrames = 0
    end
    observeLoadedSeals()
    sync(self)
    return result
  end

  local update = MapOn.Update
  if type(update) == "function" then
    MapOn.Update = function(self, ...)
      local result = update(self, ...)
      if captureReady and saved:Poll(controller.service.epoch) then
        acceptSaved()
      end
      if loadedReadFrames < 180 then
        loadedReadFrames = loadedReadFrames + 1
        if loadedReadFrames % 30 == 0 and observeLoadedSeals() then
          sync(self)
        end
      end
      return result
    end
  end

  local nextFilter = MapOn.Menu_Next_Filter
  if type(nextFilter) == "function" then
    MapOn.Menu_Next_Filter = function(self, ...)
      local result = nextFilter(self, ...)
      sync(self)
      return result
    end
  end

  local updateMapping = MapOn.UpdateFilterButtonMapping
  MapOn.UpdateFilterButtonMapping = function(self, ...)
    local selected = self.filterButtonMapping and
      self.filterButtonMapping[self.filterIndex]
    local result = updateMapping(self, ...)
    local realmHasNornir = false
    for _, row in ipairs(rows) do
      if row.Realm == self.currRealmName then realmHasNornir = true; break end
    end
    if realmHasNornir and type(self.filterButtonMapping) == "table" then
      local existing = {}
      for _, value in ipairs(self.filterButtonMapping) do existing[value] = true end
      if not existing[-103] then self.filterButtonMapping[#self.filterButtonMapping + 1] = -103 end
      if not existing[-104] then self.filterButtonMapping[#self.filterButtonMapping + 1] = -104 end
      if selected == -103 or selected == -104 then
        for index, value in ipairs(self.filterButtonMapping) do
          if value == selected then self.filterIndex = index; break end
        end
      end
      if type(self.UpdateFilterUI) == "function" then self:UpdateFilterUI() end
    end
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    if type(previous) == "function" then
      MapOn[method] = function(self, ...)
        recycle(self)
        if activeMap == self then activeMap = nil end
        return previous(self, ...)
      end
    end
  end

  local collision = MapOn.MapCollisionChangeHandler
  MapOn.MapCollisionChangeHandler = function(self, currState, hits, realmName)
    local result = collision(self, currState, hits, realmName)
    self.completionistMapV105NornirSelected = nil
    for name, icon in pairs(self.completionistMapV105NornirIdTestIcons or {}) do
      for _, hit in ipairs(hits or {}) do
        if hit == icon then
          local row = byName[name]
          local ok, info = pcall(game.Map.GetMarkerInfo, row.Name)
          if ok and info ~= nil and tostring(info.Id) == row.IdString and
              tostring(self.currMarkerID) == row.IdString then
            self.completionistMapV105NornirSelected = row
            local title = row.Family == "nornir_chest" and "Nornir Chest" or
              row.Family == "nornir_seal" and "Nornir Seal" or
              row.Family == "nornir_bell" and "Nornir Bell" or "Nornir Rune Mechanism"
            pcall(function() self:SetReticleInfo(currState, title, "Completionist Map") end)
            pcall(function() self:UpdateFooterButtonPrompt(currState.menu, false, false) end)
            print("[CompletionistMapV105NornirIdTest] selected name=" .. name ..
              " uid=" .. row.UidHex .. " family=" .. row.Family)
            return result
          end
        end
      end
    end
    return result
  end

  local previousPrompt = MapOn.GetShowOnCompassPrompt
  MapOn.GetShowOnCompassPrompt = function(self, ...)
    local row = self.completionistMapV105NornirSelected
    if row ~= nil then
      if self.isOpenedForFastTravel or not game.Compass.HaveCompass() or
          self.currRealmName ~= mapUtil.GetPlayerRealm() or
          tutorialUtil.CurrentlyShowingStep() then return false, nil end
      local label = lamsConsts.AddToCompass
      if targetRow == row then
        label = lamsConsts.RemoveFromCompass
      elseif targetRow ~= nil or self.currShownMarkerID ~= nil then
        label = lamsConsts.ReplaceInCompass
      end
      return true, "[AdvanceButton] " .. util.GetLAMSMsg(label)
    end
    return previousPrompt(self, ...)
  end
  local previousShow = MapOn.ShowOnCompass
  MapOn.ShowOnCompass = function(self, ...)
    local row = self.completionistMapV105NornirSelected
    if row ~= nil then
      if targetRow == row then
        hideTarget()
        pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass") end)
      else
        if type(_G.CompletionistMapV105ReleaseRavenCompass) == "function" and
            _G.CompletionistMapV105ReleaseRavenCompass() == false then return false end
        if self.currShownMarkerID ~= nil then
          pcall(function() game.Compass.HideMarker(self.currShownMarkerID) end)
          self.currShownMarkerID = nil
        end
        hideTarget()
        local ok, shown = pcall(game.Compass.ShowMarker, row.Name, row.Class)
        if not ok or shown == false then return false end
        targetRow = row
        local legacy = _G.CompletionistMapV100Target
        if legacy then legacy.active = false end
        pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass") end)
      end
      local currState = select(1, ...)
      if currState and currState.menu then
        pcall(function() self:UpdateFooterButtonPrompt(currState.menu, false, false) end)
      end
      return true
    end
    hideTarget()
    return previousShow(self, ...)
  end

  print("[CompletionistMapV105NornirNativeTest] installed rows=" .. tostring(#rows) ..
    " renderer=dedicated compass=dedicated checkpoint=exact_or_unknown")
end
-- END COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST
