-- BEGIN COMPLETIONIST V0.10.5 NORNIR NATIVE TEST
-- Each Nornir family has its own map resource and compass class.
do
  local rows = {
-- @@NORNIR_ROWS@@
  }
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
    thunk.Install("EVT_LoadSaveData", function()
      revealed, opened, solved = {}, {}, {}
      hideTarget()
      sync(activeMap)
    end)
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, ...)
    local result = createPins(self, ...)
    sync(self)
    return result
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
    " renderer=dedicated compass=dedicated children=after_locked_chest_attempt")
end
-- END COMPLETIONIST V0.10.5 NORNIR NATIVE TEST
