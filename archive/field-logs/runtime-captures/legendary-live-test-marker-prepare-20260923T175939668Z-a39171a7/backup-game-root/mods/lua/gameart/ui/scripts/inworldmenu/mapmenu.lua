local classlib = require("core.class")
local tablex = require("core.tablex")
local animationUtil = require("ui.animationUtil")
local buttonUtil = require("ui.buttonUtil")
local colors = require("ui.colors")
local consts = require("ui.consts")
local fsm = require("ui.fsm")
local lamsConsts = require("ui.lamsConsts")
local list = require("ui.list")
local mapConsts = require("ui.mapConsts")
local mapSummaryCard = require("ui.mapSummaryCard")
local mapUtil = require("ui.mapUtil")
local menu = require("ui.menu")
local pickupUtil = require("ui.pickupUtil")
local questConsts = require("ui.questConsts")
local questUtil = require("ui.questUtil")
local util = require("ui.util")
local tutorialUtil = require("ui.tutorialUtil")
local tutorials = require("ui.tutorials")
local Audio = game.Audio
local Camera = game.Camera
local Level = game.Level
local Map = game.Map
local Player = game.Player
local UI = game.UI
local CALDERA_MAP_POSITION = engine.Vector.New(-0.336, 0, 0.921)
local enabledShowOnCompassMarkerFlags = {
  consts.COMPASS_MARKER_TYPE_VENDOR,
  consts.COMPASS_MARKER_TYPE_FAST_TRAVEL,
  consts.COMPASS_MARKER_TYPE_AREA_ENTRANCE,
  consts.COMPASS_MARKER_TYPE_FIGHT_LOCATION,
  consts.COMPASS_MARKER_TYPE_CHISEL_ENTRANCE,
  consts.COMPASS_MARKER_TYPE_DOCK_POINT,
  consts.COMPASS_MARKER_TYPE_VALKYRIE
}
local markerStates = {
  tweaks.eTokenState.kDiscovered,
  tweaks.eTokenState.kDiscoveredButLocked
}
-- Completionist Map v0.10.1
--
-- Map side:
--   Create a genuinely separate duplicate of a SAFE DISCOVERED DockPoint icon,
--   move the duplicate ROOT to the Raven map coordinate, and intercept only
--   collision with that exact duplicate. This gives us boat artwork without
--   hijacking the original dock.
--
-- HUD side:
--   While the map is open and Add to Compass is pressed, create a SECOND safe
--   DockPoint duplicate, detach it from the map hierarchy, and hand it to the
--   MainHUD script. MainHUD reparents that visual beneath Compass and moves it
--   across the strip using the already-proven Raven bearing math.
--
-- No marker state, quest state, collectible state, or save data is changed.
_G.CompletionistMapV100NornirRegistry = _G.CompletionistMapV100NornirRegistry or {}

print("[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED")

if _G.CompletionistMapV100PlayerMarkerVisible == nil then
  _G.CompletionistMapV100PlayerMarkerVisible = true
end

_G.CompletionistMapV100Target = _G.CompletionistMapV100Target or {
  active = false,
  collected = false,
  type = "Raven",
  realm = "Midgard",
  regionQuest = "RegionSummary_VF_Raven_Parent",
  x = -64.850898742676,
  y = 12.987384796143,
  z = 787.30694580078,
  mapX = 3.2117712497711,
  mapZ = 0.8695997595787
}

local CompletionistMapV100_GetNornirRegistry
local CompletionistMapV100_ApplyZoomAdaptiveIconScale

local COMPLETIONIST_RAVEN_WORLD_X = -64.850898742676
local COMPLETIONIST_RAVEN_WORLD_Y = 12.987384796143
local COMPLETIONIST_RAVEN_WORLD_Z = 787.30694580078
local COMPLETIONIST_RAVEN_MAP_X = 3.2117712497711
local COMPLETIONIST_RAVEN_MAP_Z = 0.8695997595787

local COMPLETIONIST_ICON_ROOT = "G:/SteamLibrary/steamapps/common/GodOfWar/mods/completionist-map/icons/generated"
local completionistMapV100IconApiLogged = {}

local function CompletionistMapV100_IconPath(family, size)
  return COMPLETIONIST_ICON_ROOT .. "/" .. tostring(size) .. "/" ..
    tostring(family) .. ".png"
end

local function CompletionistMapV100_GetCallable(container, name)
  if container == nil then return nil end
  local ok, value = pcall(function() return container[name] end)
  if ok and type(value) == "function" then
    return value
  end
  return nil
end

local function CompletionistMapV100_LogIconCapabilities(go, family)
  if go == nil then return end
  if completionistMapV100IconApiLogged[family] then return end
  completionistMapV100IconApiLogged[family] = true

  local goMethods = {
    "SetTexture",
    "SetTextureName",
    "SetImage",
    "SetImagePath",
    "SetSprite",
    "SetMaterialSwap"
  }
  local uiMethods = {
    "SetTexture",
    "SetTextureName",
    "SetImage",
    "SetImagePath",
    "SetSprite"
  }

  local goCaps = {}
  for _, name in ipairs(goMethods) do
    goCaps[#goCaps + 1] = name .. "=" .. tostring(
      CompletionistMapV100_GetCallable(go, name) ~= nil
    )
  end

  local uiCaps = {}
  for _, name in ipairs(uiMethods) do
    uiCaps[#uiCaps + 1] = name .. "=" .. tostring(
      CompletionistMapV100_GetCallable(UI, name) ~= nil
    )
  end

  print("[CompletionistMap v0.10.1] ICON_CAPS" ..
    " family=" .. tostring(family) ..
    " go={" .. table.concat(goCaps, ",") .. "}" ..
    " ui={" .. table.concat(uiCaps, ",") .. "}" ..
    " path=" .. CompletionistMapV100_IconPath(family, 32))
end

local function CompletionistMapV100_TryDirectIconBind(go, family)
  if go == nil then return false end
  CompletionistMapV100_LogIconCapabilities(go, family)

  local path = CompletionistMapV100_IconPath(family, 32)
  local attempts = {
    {owner = go, ownerName = "GO", name = "SetTexture"},
    {owner = go, ownerName = "GO", name = "SetTextureName"},
    {owner = go, ownerName = "GO", name = "SetImage"},
    {owner = go, ownerName = "GO", name = "SetImagePath"},
    {owner = UI, ownerName = "UI", name = "SetTexture", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetTextureName", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetImage", passGO = true},
    {owner = UI, ownerName = "UI", name = "SetImagePath", passGO = true}
  }

  for _, attempt in ipairs(attempts) do
    local fn = CompletionistMapV100_GetCallable(attempt.owner, attempt.name)
    if fn ~= nil then
      local ok, err = pcall(function()
        if attempt.passGO then
          fn(go, path)
        else
          fn(go, path)
        end
      end)

      print("[CompletionistMap v0.10.1] ICON_BIND_ATTEMPT" ..
        " family=" .. tostring(family) ..
        " api=" .. tostring(attempt.ownerName) .. "." .. tostring(attempt.name) ..
        " ok=" .. tostring(ok) ..
        " error=" .. tostring(err) ..
        " path=" .. tostring(path))

      if ok then
        return true
      end
    end
  end

  print("[CompletionistMap v0.10.1] ICON_BIND_RESULT" ..
    " family=" .. tostring(family) ..
    " direct=false" ..
    " fallback=DockPointProxy")
  return false
end

local function CompletionistMapV100_NornirIconFamily(keyType)
  if keyType == "Breakable" then return "nornir_seal" end
  if keyType == "Bell" then return "nornir_bell" end
  if keyType == "MemoryChest" then return "nornir_mechanism" end
  return "remaining_collectible"
end

local function CompletionistMapV100_IsRavenCollected()
  if _G.CompletionistMapV100TargetRavenKilled == true then
    return true
  end

  local stateOK, state = pcall(function()
    return game.QuestManager.GetQuestState(
      "RegionSummary_VF_Raven_Parent"
    )
  end)

  if stateOK and tostring(state) == "Complete" then
    _G.CompletionistMapV100TargetRavenKilled = true
    return true
  end

  return false
end

local function CompletionistMapV100_IsTargetCollected()
  local target = _G.CompletionistMapV100Target
  if target == nil then return false end

  if target.type == "NornirPuzzle" or target.type == "NornirChest" then
    if not _G.CompletionistMapV100TargetCollectedNornirLogged then
      _G.CompletionistMapV100TargetCollectedNornirLogged = true
      print("[CompletionistMap v0.10.1] NORNIR_TARGET_STATE_CHECK" ..
        " type=" .. tostring(target.type) ..
        " registryKey=" .. tostring(target.registryKey) ..
        " helperScope=local_forward_declared")
    end

    local registry = CompletionistMapV100_GetNornirRegistry()
    local entry = registry and registry[target.registryKey] or nil
    if entry ~= nil then
      if target.type == "NornirChest" then
        target.collected = entry.opened == true
      else
        local key = entry.keys and entry.keys[target.keyIndex] or nil
        if entry.challengeComplete == true or entry.opened == true then
          target.collected = true
        elseif entry.keyType == "Breakable" then
          target.collected = key ~= nil and key.broken == true
        else
          target.collected = false
        end
      end
    end
    if target.collected then target.active = false end
    return target.collected == true
  end

  if _G.CompletionistMapV100TargetRavenKilled == true then
    target.collected = true
  end
  if not target.collected and target.regionQuest ~= nil then
    local stateOK, state = pcall(function()
      return game.QuestManager.GetQuestState(target.regionQuest)
    end)
    if stateOK and tostring(state) == "Complete" then
      target.collected = true
      _G.CompletionistMapV100TargetRavenKilled = true
    end
  end
  if target.collected then target.active = false end
  return target.collected
end

local function CompletionistMapV100_LogMapCalibration(self)
  if self.currRealmName ~= "Midgard" or self.playerIconGO == nil then
    return
  end

  local player = game.Player.FindPlayer()
  if player == nil then
    return
  end

  local worldOK, worldPos = pcall(function()
    return player:GetWorldPosition()
  end)

  local mapOK, mapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)

  if not worldOK or worldPos == nil or
      not mapOK or mapPos == nil then
    return
  end

  local last = _G.CompletionistMapV100LastCalibration
  local shouldLog = last == nil

  if last ~= nil then
    local dx = worldPos.x - last.x
    local dz = worldPos.z - last.z
    shouldLog = dx * dx + dz * dz >= 400
  end

  if not shouldLog then
    return
  end

  _G.CompletionistMapV100LastCalibration = {
    x = worldPos.x,
    z = worldPos.z
  }

  print("[CompletionistMap v0.10.1] MAP_CALIBRATION" ..
    " realm=" .. tostring(self.currRealmName) ..
    " worldX=" .. tostring(worldPos.x) ..
    " worldY=" .. tostring(worldPos.y) ..
    " worldZ=" .. tostring(worldPos.z) ..
    " mapX=" .. tostring(mapPos.x) ..
    " mapY=" .. tostring(mapPos.y) ..
    " mapZ=" .. tostring(mapPos.z))
end

local completionistMapV100PreferredDockIds = {
  "2924516555722838670",
  "3015224018432851104",
  "-8580963607903916635",
  "-8580963607903813648",
  "-8580963607903819882",
  "-8580963607903820923",
  "-8580963607903817804",
  "-8580963607903818837",
  "-8580963607903824038",
  "3665597207158594306",
  "-7682859529157234129",
  "2012662071676473320",
  "-1367314585613671475",
  "-5774578489664548484",
  "1998313177983296660",
  "674850249950444597"
}

local function CompletionistMapV100_BuildBackingDockPool(self)
  if type(self.completionistMapV100BackingDockPool) == "table" and
      #self.completionistMapV100BackingDockPool > 0 then
    return self.completionistMapV100BackingDockPool
  end

  local byId = {}
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    local safeOK, safe = pcall(function()
      return markerInfo.State == tweaks.eTokenState.kDiscovered and
        Map.MarkerHasAnyFlag(
          markerInfo.Id,
          {consts.COMPASS_MARKER_TYPE_DOCK_POINT}
        )
    end)

    if safeOK and safe then
      markerInfo.regionId = markerInfo.regionId or
        select(2, Map.FindRegionFromMarker(markerInfo.Id))
      byId[tostring(markerInfo.Id)] = markerInfo
    end
  end

  local pool = {}
  local used = {}

  for _, idString in ipairs(completionistMapV100PreferredDockIds) do
    local markerInfo = byId[idString]
    if markerInfo ~= nil and not used[idString] then
      pool[#pool + 1] = markerInfo
      used[idString] = true
    end
  end

  local remaining = {}
  for idString, markerInfo in pairs(byId) do
    if not used[idString] then
      remaining[#remaining + 1] = markerInfo
    end
  end

  table.sort(remaining, function(a, b)
    return tostring(a.Id) < tostring(b.Id)
  end)

  for _, markerInfo in ipairs(remaining) do
    pool[#pool + 1] = markerInfo
  end

  self.completionistMapV100BackingDockPool = pool

  local ids = {}
  for i = 1, math.min(#pool, 12) do
    ids[#ids + 1] = tostring(pool[i].Id)
  end

  print("[CompletionistMap v0.10.1] BACKING_POOL" ..
    " count=" .. tostring(#pool) ..
    " first=" .. table.concat(ids, ","))

  return pool
end

local function CompletionistMapV100_FindBackingDock(self, slot)
  local pool = CompletionistMapV100_BuildBackingDockPool(self)
  if type(pool) ~= "table" or #pool == 0 then
    return nil
  end

  slot = math.max(1, tonumber(slot) or 1)
  local index = ((slot - 1) % #pool) + 1
  local markerInfo = pool[index]

  self.completionistMapV100BackingSlotLog =
    self.completionistMapV100BackingSlotLog or {}

  if not self.completionistMapV100BackingSlotLog[slot] then
    self.completionistMapV100BackingSlotLog[slot] = true
    print("[CompletionistMap v0.10.1] BACKING_ASSIGN" ..
      " slot=" .. tostring(slot) ..
      " id=" .. tostring(markerInfo.Id) ..
      " region=" .. tostring(markerInfo.regionId))
  end

  return markerInfo
end


local function CompletionistMapV100_WorldToMidgardMap(x, z)
  return
    0.004 * z + 0.0625431,
    -0.004 * x + 0.6101961
end

CompletionistMapV100_GetNornirRegistry = function()
  local uiRegistry = _G.CompletionistMapV100NornirRegistry
  if type(uiRegistry) == "table" and next(uiRegistry) ~= nil then
    if not _G.CompletionistMapV100RegistryLogged then
      _G.CompletionistMapV100RegistryLogged = true
      print("[CompletionistMap v0.10.1] NORNIR_REGISTRY" ..
        " source=ui_call_event")
    end
    return uiRegistry, "ui_call_event"
  end

  -- One verified parent location remains as a bootstrap so the known chest
  -- can appear before its gameplay script publishes live state. Puzzle child
  -- pins are deliberately NOT created from this fallback because persisted
  -- per-seal state would be unknown.
  local registryKey =
    "known_breakable|-43.904609680176|748.57946777344"
  local fallback = {}
  fallback[registryKey] = {
    registryKey = registryKey,
    name = "chest_locked_parent",
    keyType = "Breakable",
    opened = false,
    challengeComplete = false,
    keysUsed = nil,
    x = -43.904609680176,
    y = 14.5,
    z = 748.57946777344,
    source = "verified_parent_fallback",
    keys = {}
  }

  if not _G.CompletionistMapV100FallbackLogged then
    _G.CompletionistMapV100FallbackLogged = true
    print("[CompletionistMap v0.10.1] NORNIR_FALLBACK" ..
      " parentOnly=true chest=chest_locked_parent" ..
      " ignoresStockSummary=true")
  end

  return fallback, "verified_parent_fallback"
end

local function CompletionistMapV100_IsNornirKeyRemaining(pin)
  if pin == nil then
    return false
  end

  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  if entry == nil or entry.opened == true or entry.challengeComplete == true then
    return false
  end

  local key = entry.keys and entry.keys[pin.keyIndex] or nil
  if key == nil then
    return false
  end

  if entry.keyType == "Breakable" then
    return key.broken ~= true
  end

  -- Bell and MemoryChest actors remain relevant until the whole timed/rotator
  -- challenge completes. Their transient runeVisual disabled state is not a
  -- collected state.
  return true
end

local function CompletionistMapV100_DestroyNornirPins(self)
  if self.completionistMapV100NornirPins ~= nil then
    for _, pin in ipairs(self.completionistMapV100NornirPins) do
      if pin.iconGO ~= nil then
        pcall(function()
          Map.RecycleIcon(pin.iconGO)
        end)
      end
    end
  end

  self.completionistMapV100NornirPins = {}
  self.completionistMapV100NornirSelected = nil
  self.completionistMapV100NornirLastHitFrame = nil
end

local function CompletionistMapV100_NornirReticle(self, currState, pin)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  self.completionistMapV100Selected = false
  self.completionistMapV100NornirChestSelected = nil

  local title = "Nornir Puzzle " .. tostring(pin.keyIndex)
  local description = "Nornir puzzle element - Completionist Map"
  if pin.keyType == "Breakable" then
    title = "Nornir Seal " .. tostring(pin.keyIndex)
    description = "Unbroken rune seal - Completionist Map"
  elseif pin.keyType == "Bell" then
    title = "Nornir Bell " .. tostring(pin.keyIndex)
    description = "Timed Nornir bell - Completionist Map"
  elseif pin.keyType == "MemoryChest" then
    title = "Nornir Rune Mechanism " .. tostring(pin.keyIndex)
    description = "Rune rotator - Completionist Map"
  end

  local target = _G.CompletionistMapV100Target
  if target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex and
      target.active then
    description = description .. " - tracked"
  end

  self:SetReticleInfo(currState, title, description)
  self:UpdateFooterButtonPrompt(currState.menu, false, false)
end

local function CompletionistMapV100_DestroyNornirChestPins(self)
  if type(self.completionistMapV100NornirChestPins) == "table" then
    for _, pin in ipairs(self.completionistMapV100NornirChestPins) do
      if pin.iconGO ~= nil then
        pcall(function() Map.RecycleIcon(pin.iconGO) end)
      end
    end
  end
  self.completionistMapV100NornirChestPins = {}
  self.completionistMapV100NornirChestSelected = nil
end

local function CompletionistMapV100_IsNornirChestRemaining(pin)
  if pin == nil then return false end
  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  return entry ~= nil and entry.opened ~= true
end

local function CompletionistMapV100_NornirChestReticle(self, currState, pin)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  self.completionistMapV100Selected = false
  self.completionistMapV100NornirSelected = nil

  local registry = CompletionistMapV100_GetNornirRegistry()
  local entry = registry and registry[pin.registryKey] or nil
  local title = "Nornir Chest"
  local description = "Incomplete Nornir Chest - Completionist Map"
  if entry ~= nil then
    if entry.challengeComplete == true and entry.opened ~= true then
      description = "Unlocked Nornir Chest - open it to complete"
    elseif entry.keyType == "Breakable" then
      description = "Nornir Chest - break the remaining rune seals"
    elseif entry.keyType == "Bell" then
      description = "Nornir Chest - ring the three timed bells"
    elseif entry.keyType == "MemoryChest" then
      description = "Nornir Chest - solve the rune mechanisms"
    end
  end

  self:SetReticleInfo(currState, title, description)
  self:UpdateFooterButtonPrompt(currState.menu, false, false)
end

local function CompletionistMapV100_CreateNornirChestPins(self, currState)
  CompletionistMapV100_DestroyNornirChestPins(self)
  if self.currRealmName ~= "Midgard" then return end

  local registry, registrySource = CompletionistMapV100_GetNornirRegistry()

  local mapY = 0
  local playerYOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerMapPos ~= nil then mapY = playerMapPos.y end

  local chestOrdinal = 0
  for registryKey, entry in pairs(registry or {}) do
    if entry ~= nil and entry.opened ~= true and
        entry.x ~= nil and entry.z ~= nil then
      chestOrdinal = chestOrdinal + 1
      local backing =
        CompletionistMapV100_FindBackingDock(self, 2 + chestOrdinal - 1)
      if backing == nil then
        print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN" ..
          " ok=false reason=safe_dock_not_found" ..
          " registryKey=" .. tostring(registryKey))
      else
        local mapX, mapZ =
          CompletionistMapV100_WorldToMidgardMap(entry.x, entry.z)
        local createOK, iconOrErr = pcall(function()
          return Map.CreateMarkerIcon(backing.Id, backing.regionId, "")
        end)
      if createOK and iconOrErr ~= nil then
        local pin = {
          registryKey = registryKey,
          keyType = entry.keyType,
          worldX = entry.x, worldY = entry.y, worldZ = entry.z,
          mapX = mapX, mapY = mapY, mapZ = mapZ,
          iconGO = iconOrErr, frames = 0
        }
        local ok = pcall(function()
          pin.iconGO:SetWorldPosition(engine.Vector.New(mapX, mapY, mapZ))
          pin.iconGO:Show()
          UI.SetIsClickable(pin.iconGO)
          CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
          CompletionistMapV100_TryDirectIconBind(pin.iconGO, "nornir_chest")
        end)
        if ok then
          table.insert(self.completionistMapV100NornirChestPins, pin)
          print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN" ..
            " ok=true source=" .. tostring(registrySource) ..
            " registryKey=" .. tostring(registryKey) ..
            " backingId=" .. tostring(backing.Id) ..
            " mapX=" .. tostring(mapX) ..
            " mapZ=" .. tostring(mapZ))
        else
          pcall(function() Map.RecycleIcon(pin.iconGO) end)
        end
      end
      end
    end
  end
end

local function CompletionistMapV100_FindNornirChestCollision(self, collisionGameObjectTable)
  if type(collisionGameObjectTable) ~= "table" or
      type(self.completionistMapV100NornirChestPins) ~= "table" then
    return nil
  end
  for _, collGO in ipairs(collisionGameObjectTable) do
    for _, pin in ipairs(self.completionistMapV100NornirChestPins) do
      if pin.iconGO == collGO and
          CompletionistMapV100_IsNornirChestRemaining(pin) then
        return pin
      end
    end
  end
  return nil
end

local function CompletionistMapV100_RefreshNornirChestPins(self)
  if type(self.completionistMapV100NornirChestPins) ~= "table" then return end
  for i = #self.completionistMapV100NornirChestPins, 1, -1 do
    local pin = self.completionistMapV100NornirChestPins[i]
    pin.frames = (pin.frames or 0) + 1
    if pin.frames <= 60 and pin.iconGO ~= nil then
      pcall(function()
        pin.iconGO:SetWorldPosition(
          engine.Vector.New(pin.mapX, pin.mapY or 0, pin.mapZ)
        )
        UI.SetIsClickable(pin.iconGO)
      end)
    end
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      if pin.iconGO ~= nil then
        pcall(function() Map.RecycleIcon(pin.iconGO) end)
      end
      if self.completionistMapV100NornirChestSelected == pin then
        self.completionistMapV100NornirChestSelected = nil
      end
      table.remove(self.completionistMapV100NornirChestPins, i)
      print("[CompletionistMap v0.10.1] NORNIR_CHEST_PIN_REMOVE" ..
        " registryKey=" .. tostring(pin.registryKey))
    end
  end
end

local function CompletionistMapV100_CreateNornirPins(self, currState)
  CompletionistMapV100_DestroyNornirPins(self)

  if self.currRealmName ~= "Midgard" then
    return
  end

  local registry, registrySource =
    CompletionistMapV100_GetNornirRegistry()

  if registrySource ~= "ui_call_event" then
    print("[CompletionistMap v0.10.1] NORNIR_MAP" ..
      " count=0 reason=live_state_required")
    return
  end

  local mapY = 0
  local playerYOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerMapPos ~= nil then
    mapY = playerMapPos.y
  end

  local created = 0
  for registryKey, entry in pairs(registry) do
    if entry ~= nil and
        entry.opened ~= true and
        entry.challengeComplete ~= true and
        type(entry.keys) == "table" then
      for i = 1, 3 do
        local key = entry.keys[i]
        local shouldCreate = key ~= nil and
          key.x ~= nil and key.z ~= nil

        if shouldCreate and entry.keyType == "Breakable" then
          shouldCreate = key.broken ~= true
        end

        if shouldCreate then
          local backing =
            CompletionistMapV100_FindBackingDock(self, 10 + created)
          if backing == nil then
            print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
              " ok=false index=" .. tostring(i) ..
              " reason=safe_dock_not_found")
          else
            local mapX, mapZ =
              CompletionistMapV100_WorldToMidgardMap(key.x, key.z)
            local createOK, iconOrErr = pcall(function()
              return Map.CreateMarkerIcon(backing.Id, backing.regionId, "")
            end)

            if createOK and iconOrErr ~= nil then
            local pin = {
              registryKey = registryKey,
              keyIndex = i,
              keyType = entry.keyType,
              worldX = key.x,
              worldY = key.y,
              worldZ = key.z,
              mapX = mapX,
              mapY = mapY,
              mapZ = mapZ,
              iconGO = iconOrErr,
              frames = 0,
              broken = key.broken == true
            }
            local setOK, setErr = pcall(function()
              pin.iconGO:SetWorldPosition(
                engine.Vector.New(mapX, mapY, mapZ)
              )
              pin.iconGO:Show()
              UI.SetIsClickable(pin.iconGO)
              CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
              CompletionistMapV100_TryDirectIconBind(
                pin.iconGO,
                CompletionistMapV100_NornirIconFamily(entry.keyType)
              )
            end)
            if setOK then
              table.insert(self.completionistMapV100NornirPins, pin)
              created = created + 1
              print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
                " ok=true registryKey=" .. tostring(registryKey) ..
                " keyType=" .. tostring(entry.keyType) ..
                " index=" .. tostring(i) ..
                " backingId=" .. tostring(backing.Id) ..
                " mapX=" .. tostring(mapX) ..
                " mapZ=" .. tostring(mapZ))
            else
              pcall(function() Map.RecycleIcon(pin.iconGO) end)
              print("[CompletionistMap v0.10.1] NORNIR_PIN_CREATE" ..
                " ok=false index=" .. tostring(i) ..
                " error=" .. tostring(setErr))
            end
            end
          end
        end
      end
    end
  end

  print("[CompletionistMap v0.10.1] NORNIR_MAP" ..
    " count=" .. tostring(created) ..
    " source=" .. tostring(registrySource))
end

local function CompletionistMapV100_FindNornirCollision(
  self,
  collisionGameObjectTable
)
  if type(collisionGameObjectTable) ~= "table" or
      type(self.completionistMapV100NornirPins) ~= "table" then
    return nil
  end

  for _, collGO in ipairs(collisionGameObjectTable) do
    for _, pin in ipairs(self.completionistMapV100NornirPins) do
      if pin.iconGO == collGO and
          CompletionistMapV100_IsNornirKeyRemaining(pin) then
        return pin
      end
    end
  end

  return nil
end

local function CompletionistMapV100_RefreshNornirPins(self)
  if type(self.completionistMapV100NornirPins) ~= "table" then
    return
  end

  for i = #self.completionistMapV100NornirPins, 1, -1 do
    local pin = self.completionistMapV100NornirPins[i]

    pin.frames = (pin.frames or 0) + 1
    if pin.frames <= 60 and pin.iconGO ~= nil then
      pcall(function()
        pin.iconGO:SetWorldPosition(
          engine.Vector.New(
            pin.mapX,
            pin.mapY or 0,
            pin.mapZ
          )
        )
        pin.iconGO:Show()
        UI.SetIsClickable(pin.iconGO)
      end)
    end

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      if pin.iconGO ~= nil then
        pcall(function()
          Map.RecycleIcon(pin.iconGO)
        end)
      end

      if self.completionistMapV100NornirSelected == pin then
        self.completionistMapV100NornirSelected = nil
      end

      table.remove(self.completionistMapV100NornirPins, i)

      print("[CompletionistMap v0.10.1] NORNIR_PIN_REMOVE" ..
        " registryKey=" .. tostring(pin.registryKey) ..
        " index=" .. tostring(pin.keyIndex))
    elseif pin.frames == 30 and pin.iconGO ~= nil then
      local posOK, actual = pcall(function()
        return pin.iconGO:GetWorldPosition()
      end)

      print("[CompletionistMap v0.10.1] NORNIR_PIN_VERIFY" ..
        " index=" .. tostring(pin.keyIndex) ..
        " expectedX=" .. tostring(pin.mapX) ..
        " expectedZ=" .. tostring(pin.mapZ) ..
        " actual=" .. (
          posOK and actual ~= nil and
          ("x=" .. tostring(actual.x) ..
           ",y=" .. tostring(actual.y) ..
           ",z=" .. tostring(actual.z))
          or "<unavailable>"
        ))
    end
  end
end

local function CompletionistMapV100_Description()
  local target = _G.CompletionistMapV100Target
  if target ~= nil and target.type == "Raven" and target.active then
    return "Remaining collectible - tracked on custom compass"
  end
  return "Remaining collectible - Completionist Map"
end

local function CompletionistMapV100_ClearStockCompass(self, reason)
  if self.currShownMarkerID == nil then
    return
  end

  local oldId = self.currShownMarkerID
  local hideOK, hideErr = pcall(function()
    game.Compass.HideMarker(oldId)
  end)

  self.currShownMarkerID = nil

  print("[CompletionistMap v0.10.1] STOCK_COMPASS_CLEAR" ..
    " reason=" .. tostring(reason) ..
    " id=" .. tostring(oldId) ..
    " ok=" .. tostring(hideOK) ..
    " error=" .. tostring(hideErr))
end

local function CompletionistMapV100_ShowReticle(self, currState)
  self.currQuestID = nil
  self.currMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false

  self:SetReticleInfo(
    currState,
    "Odin's Raven",
    CompletionistMapV100_Description()
  )

  self:UpdateFooterButtonPrompt(
    currState.menu,
    false,
    false
  )
end

local function CompletionistMapV100_DestroyMapPin(self)
  if self.completionistMapV100MapIconGO ~= nil then
    pcall(function()
      Map.RecycleIcon(self.completionistMapV100MapIconGO)
    end)
  end

  self.completionistMapV100MapIconGO = nil
  self.completionistMapV100BackingMarker = nil
  self.completionistMapV100Selected = false
  self.completionistMapV100Frame = 0
  self.completionistMapV100CurrState = nil
  self.completionistMapV100LastHitFrame = nil
  self.completionistMapV100LastSnapFrame = nil
  self.completionistMapV100CollisionState = false
end

local function CompletionistMapV100_CreateMapPin(self, currState)
  if self.currRealmName ~= "Midgard" then
    return
  end

  CompletionistMapV100_DestroyMapPin(self)

  if CompletionistMapV100_IsRavenCollected() then
    print("[CompletionistMap v0.10.1] MAP_PIN_SKIP reason=raven_collected")
    return
  end

  local backing = CompletionistMapV100_FindBackingDock(self, 1)
  if backing == nil then
    print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
      " ok=false reason=safe_dock_not_found")
    return
  end

  local createOK, iconOrErr = pcall(function()
    return Map.CreateMarkerIcon(
      backing.Id,
      backing.regionId,
      ""
    )
  end)

  if not createOK or iconOrErr == nil then
    print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
      " ok=false reason=duplicate_create_failed" ..
      " error=" .. tostring(iconOrErr))
    return
  end

  local iconGO = iconOrErr
  self.completionistMapV100MapIconGO = iconGO
  self.completionistMapV100BackingMarker = backing
  self.completionistMapV100CurrState = currState
  self.completionistMapV100Frame = 0
  self.completionistMapV100Selected = false
  self.completionistMapV100LastHitFrame = 0
  self.completionistMapV100LastSnapFrame = -9999
  self.completionistMapV100CollisionState = false

  local originalOK, original = pcall(function()
    return iconGO:GetWorldPosition()
  end)

  local mapY = originalOK and original ~= nil and original.y or 0

  local playerYOK, playerPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerYOK and playerPos ~= nil then
    mapY = playerPos.y
  end

  local setOK, setErr = pcall(function()
    iconGO:SetWorldPosition(
      engine.Vector.New(
        COMPLETIONIST_RAVEN_MAP_X,
        mapY,
        COMPLETIONIST_RAVEN_MAP_Z
      )
    )
    iconGO:Show()
    UI.SetIsClickable(iconGO)
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(iconGO)
    CompletionistMapV100_TryDirectIconBind(iconGO, "raven")
  end)

  local afterOK, after = pcall(function()
    return iconGO:GetWorldPosition()
  end)

  print("[CompletionistMap v0.10.1] MAP_PIN_CREATE" ..
    " ok=" .. tostring(setOK) ..
    " error=" .. tostring(setErr) ..
    " backingId=" .. tostring(backing.Id) ..
    " region=" .. tostring(backing.regionId) ..
    " visual=DockPointRoot" ..
    " actual=" .. (afterOK and after ~= nil and
      ("x=" .. tostring(after.x) ..
       ",y=" .. tostring(after.y) ..
       ",z=" .. tostring(after.z))
      or "<error>"))

end

local function CompletionistMapV100_GetZoomAdaptiveIconScale()
  -- Keep temporary DockPoint-backed custom markers at native marker scale.
  -- Magnetic attraction is handled separately at the map-camera level.
  return 1.0, 1.0
end

CompletionistMapV100_ApplyZoomAdaptiveIconScale = function(go)
  if go == nil then return end
  local iconScale = CompletionistMapV100_GetZoomAdaptiveIconScale()
  pcall(function()
    UI.SetGOScale(
      go,
      engine.Vector.New(iconScale, iconScale, iconScale)
    )
  end)
end

local function CompletionistMapV100_UpdateSnapTuning(self)
  local iconScale, cursorScale =
    CompletionistMapV100_GetZoomAdaptiveIconScale()

  local bucket = math.floor(iconScale * 10 + 0.5)
  if self.completionistMapV100SnapScaleBucket ~= bucket then
    self.completionistMapV100SnapScaleBucket = bucket
    print("[CompletionistMap v0.10.1] SNAP_TUNING" ..
      " mode=native_scale_no_camera_snap" ..
      " customIconScale=" .. tostring(iconScale))
  end

  CompletionistMapV100_ApplyZoomAdaptiveIconScale(
    self.completionistMapV100MapIconGO
  )

  for _, pin in ipairs(self.completionistMapV100NornirChestPins or {}) do
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
  end

  for _, pin in ipairs(self.completionistMapV100NornirPins or {}) do
    CompletionistMapV100_ApplyZoomAdaptiveIconScale(pin.iconGO)
  end
end

local function CompletionistMapV100_SetCustomCursorSelected(selected)
  local goCursorRefnode = util.GetUiObjByName("MapCursor")
  if goCursorRefnode ~= nil then
    animationUtil.SetCursorSelected(goCursorRefnode, selected == true)
  end

  if selected then
    Audio.PlaySound("SND_UX_Pause_Menu_Screen_Map_Region_Hover_Tick")
  end
end

local function CompletionistMapV100_ReinforceRavenPin(self)
  local go = self.completionistMapV100MapIconGO
  if go == nil or CompletionistMapV100_IsRavenCollected() then
    return
  end

  local mapY = 0
  local playerOK, playerMapPos = pcall(function()
    return self.playerIconGO:GetWorldPosition()
  end)
  if playerOK and playerMapPos ~= nil then
    mapY = playerMapPos.y
  end

  pcall(function()
    go:SetWorldPosition(
      engine.Vector.New(
        COMPLETIONIST_RAVEN_MAP_X,
        mapY,
        COMPLETIONIST_RAVEN_MAP_Z
      )
    )
    go:Show()
    UI.SetIsClickable(go)
  end)

  self.completionistMapV100RavenPinFrames =
    (self.completionistMapV100RavenPinFrames or 0) + 1

  local activeTarget = _G.CompletionistMapV100Target
  if activeTarget ~= nil and
      activeTarget.active == true and
      activeTarget.type ~= "Raven" and
      self.completionistMapV100RavenIndependentTargetType ~= activeTarget.type then
    self.completionistMapV100RavenIndependentTargetType = activeTarget.type
    print("[CompletionistMap v0.10.1] RAVEN_PIN_INDEPENDENT" ..
      " activeTargetType=" .. tostring(activeTarget.type) ..
      " mapX=" .. tostring(COMPLETIONIST_RAVEN_MAP_X) ..
      " mapZ=" .. tostring(COMPLETIONIST_RAVEN_MAP_Z))
  end

  if self.completionistMapV100RavenPinFrames == 30 then
    local ok, actual = pcall(function() return go:GetWorldPosition() end)
    print("[CompletionistMap v0.10.1] RAVEN_PIN_VERIFY" ..
      " expectedX=" .. tostring(COMPLETIONIST_RAVEN_MAP_X) ..
      " expectedZ=" .. tostring(COMPLETIONIST_RAVEN_MAP_Z) ..
      " activeTargetType=" .. tostring(
        _G.CompletionistMapV100Target and
        _G.CompletionistMapV100Target.type or "<nil>"
      ) ..
      " actual=" .. (
        ok and actual ~= nil and
        ("x=" .. tostring(actual.x) ..
         ",y=" .. tostring(actual.y) ..
         ",z=" .. tostring(actual.z))
        or "<unavailable>"
      ))
  end
end

local COMPLETIONIST_FILTER = -101
local RAVEN_FILTER = -102
local NORNIR_CHEST_FILTER = -103
local NORNIR_PUZZLE_FILTER = -104

local completionistFilterLabels = {
  [COMPLETIONIST_FILTER] = "COMPLETIONIST",
  [RAVEN_FILTER] = "RAVENS",
  [NORNIR_CHEST_FILTER] = "NORNIR CHESTS",
  [NORNIR_PUZZLE_FILTER] = "NORNIR PUZZLE"
}

local function CompletionistMapV100_GetFilterKind(self)
  if self.filterButtonMapping == nil then return 1 end
  return self.filterButtonMapping[self.filterIndex] or 1
end

local function CompletionistMapV100_SetGOVisible(go, visible)
  if go == nil then return end
  pcall(function()
    if visible then go:Show() else go:Hide() end
  end)
end

local function CompletionistMapV100_RefreshCustomPins(self)
  CompletionistMapV100_UpdateSnapTuning(self)

  local filter = CompletionistMapV100_GetFilterKind(self)
  local showRaven = filter == 1 or
    filter == COMPLETIONIST_FILTER or filter == RAVEN_FILTER
  local showChest = filter == 1 or
    filter == COMPLETIONIST_FILTER or filter == NORNIR_CHEST_FILTER
  local showPuzzle = filter == NORNIR_PUZZLE_FILTER
  local registry = CompletionistMapV100_GetNornirRegistry()

  CompletionistMapV100_ReinforceRavenPin(self)

  CompletionistMapV100_SetGOVisible(
    self.completionistMapV100MapIconGO,
    showRaven and not CompletionistMapV100_IsRavenCollected()
  )

  for _, pin in ipairs(self.completionistMapV100NornirChestPins or {}) do
    CompletionistMapV100_SetGOVisible(pin.iconGO, showChest)
  end

  if not self.completionistMapV100AliasCheckLogged then
    self.completionistMapV100AliasCheckLogged = true
    local raven = self.completionistMapV100MapIconGO

    for _, chestPin in ipairs(self.completionistMapV100NornirChestPins or {}) do
      print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
        " pair=raven_chest" ..
        " sameGO=" .. tostring(
          raven ~= nil and raven == chestPin.iconGO
        ))
    end

    local pins = self.completionistMapV100NornirPins or {}
    for i = 1, #pins do
      if raven ~= nil then
        print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
          " pair=raven_puzzle" ..
          " index=" .. tostring(pins[i].keyIndex) ..
          " sameGO=" .. tostring(raven == pins[i].iconGO))
      end

      for j = i + 1, #pins do
        print("[CompletionistMap v0.10.1] ALIAS_CHECK" ..
          " pair=puzzle_puzzle" ..
          " a=" .. tostring(pins[i].keyIndex) ..
          " b=" .. tostring(pins[j].keyIndex) ..
          " sameGO=" .. tostring(pins[i].iconGO == pins[j].iconGO))
      end
    end
  end

  for _, pin in ipairs(self.completionistMapV100NornirPins or {}) do
    local entry = registry and registry[pin.registryKey] or nil
    local revealInShowAll =
      filter == 1 and
      entry ~= nil and
      entry.puzzleRevealed == true and
      entry.challengeComplete ~= true and
      entry.opened ~= true

    CompletionistMapV100_SetGOVisible(
      pin.iconGO,
      showPuzzle or revealInShowAll
    )
  end

  if not showRaven then self.completionistMapV100Selected = false end
  if not showChest then self.completionistMapV100NornirChestSelected = nil end

  if self.completionistMapV100NornirSelected ~= nil then
    local selectedPin = self.completionistMapV100NornirSelected
    local selectedEntry =
      registry and registry[selectedPin.registryKey] or nil

    local selectedPuzzleVisible =
      showPuzzle or
      (
        filter == 1 and
        selectedEntry ~= nil and
        selectedEntry.puzzleRevealed == true and
        selectedEntry.challengeComplete ~= true and
        selectedEntry.opened ~= true
      )

    if not selectedPuzzleVisible then
      self.completionistMapV100NornirSelected = nil
    end
  end

  if self.completionistMapV100LastVisibilityFilter ~= filter then
    self.completionistMapV100LastVisibilityFilter = filter
    print("[CompletionistMap v0.10.1] FILTER_CUSTOM_VISIBILITY" ..
      " filter=" .. tostring(filter) ..
      " raven=" .. tostring(showRaven) ..
      " chest=" .. tostring(showChest) ..
      " puzzleFilter=" .. tostring(showPuzzle) ..
      " puzzleAfterAttempt=" .. tostring(filter == 1))
  end
end

local function CompletionistMapV100_CollisionContainsPin(
  self,
  collisionGameObjectTable
)
  if type(collisionGameObjectTable) ~= "table" or
      self.completionistMapV100MapIconGO == nil then
    return false
  end

  for _, collGO in ipairs(collisionGameObjectTable) do
    if collGO == self.completionistMapV100MapIconGO then
      return true
    end
  end

  return false
end
local alwaysOnMarkerFlags = {
  "PrimaryQuest",
  "SecondaryQuest"
}
local fastTravelMarkerFlags = {
  consts.COMPASS_MARKER_TYPE_FAST_TRAVEL,
  consts.COMPASS_MARKER_TYPE_FAST_TRAVEL_NO_TRACK
}
local markerFilters = {
  {
    name = 44102,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_VENDOR,
      consts.COMPASS_MARKER_TYPE_VENDOR_NO_TRACK,
      consts.COMPASS_MARKER_TYPE_FAST_TRAVEL,
      consts.COMPASS_MARKER_TYPE_FAST_TRAVEL_NO_TRACK,
      consts.COMPASS_MARKER_TYPE_DOCK_POINT,
      consts.COMPASS_MARKER_TYPE_AREA_ENTRANCE,
      consts.COMPASS_MARKER_TYPE_CHISEL_ENTRANCE,
      consts.COMPASS_MARKER_TYPE_CHISEL_ENTRANCE_NO_TRACK,
      consts.COMPASS_MARKER_TYPE_FIGHT_LOCATION,
      consts.COMPASS_MARKER_TYPE_FIGHT_LOCATION_NO_TRACK,
      consts.COMPASS_MARKER_TYPE_INFO_ONLY,
      consts.COMPASS_MARKER_TYPE_VALKYRIE
    }
  },
  {
    name = 44103,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_VENDOR,
      consts.COMPASS_MARKER_TYPE_VENDOR_NO_TRACK
    }
  },
  {name = 44104, markerIncludeFlags = fastTravelMarkerFlags},
  {
    name = 44105,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_DOCK_POINT
    }
  },
  {
    name = 44101,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_AREA_ENTRANCE,
      consts.COMPASS_MARKER_TYPE_CHISEL_ENTRANCE,
      consts.COMPASS_MARKER_TYPE_CHISEL_ENTRANCE_NO_TRACK
    }
  },
  {
    name = 44106,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_FIGHT_LOCATION,
      consts.COMPASS_MARKER_TYPE_FIGHT_LOCATION_NO_TRACK
    }
  },
  {
    name = 37166,
    markerIncludeFlags = {
      consts.COMPASS_MARKER_TYPE_VALKYRIE
    }
  }
}
local map_camera
map_camera = tweaks.tMapCamera.New({
  Name = "MapMenuCam",
  CollisionRoot = "Midgard_collision",
  OnSkillTree = false,
  HorizontalControlSpeed = 0.1,
  VerticalControlSpeed = 0.1,
  ZoomControlSpeed = 3.2,
  ZoomSpeedScale = 3,
  HorizontalPosition = 0,
  VerticalPosition = 0,
  ZoomPosition = 5,
  Pitch = 35,
  Yaw = 0,
  Roll = 0,
  MaxLeft = -4.9,
  MaxRight = 4,
  MaxUp = -3.7,
  MaxDown = 4.5,
  MaxIn = 2.5,
  MaxOut = 10,
  CursorSnap_Enabled = 0,
  CursorSnap_Strength = 0.0,
  CursorGOName = "MapCursor",
  ScaleMapCursorBasedOnZoom = true,
  CursorScale_Min = 0.05,
  CursorScale_Max = 0.85,
  Tofu = "never"
})
local MapMenu = classlib.Class("MapMenu", fsm.UIState)
local MapOff = MapMenu:StateClass("MapOff", fsm.UIState)
local MapOn = MapMenu:StateClass("MapOn", fsm.UIState)
local Midgard = MapMenu:StateClass("Midgard", fsm.UIState)
local Alfheim = MapMenu:StateClass("Alfheim", fsm.UIState)
local Helheim = MapMenu:StateClass("Helheim", fsm.UIState)
local Jotunheim = MapMenu:StateClass("Jotunheim", fsm.UIState)
local Niflheim = MapMenu:StateClass("Niflheim", fsm.UIState)
local Muspelheim = MapMenu:StateClass("Muspelheim", fsm.UIState)
local Svartalheim = MapMenu:StateClass("Svartalheim", fsm.UIState)
local Vanaheim = MapMenu:StateClass("Vanaheim", fsm.UIState)
local Asgard = MapMenu:StateClass("Asgard", fsm.UIState)
local mapMenu = MapMenu.New("mapMenu", {
  MapOff,
  MapOn,
  {
    Midgard,
    Alfheim,
    Helheim,
    Jotunheim,
    Niflheim,
    Muspelheim,
    Svartalheim,
    Vanaheim,
    Asgard
  }
})
function MapMenu:Enter()
  self:WantPadEvents(true)
  self:turnoff()
end
function MapMenu:Exit()
end
function MapMenu:turnoff()
  self:Goto("MapOff")
end
MapMenu.EVT_GAME_OVER = MapMenu.turnoff
MapMenu.EVT_Restart = MapMenu.turnoff
function MapOff:Setup()
  self.mapOn = self:GetState("MapOn")
end
function MapOff:Enter()
end
function MapOff:Exit()
end
function MapOff:EVT_TURN_ON_MAP_MENU(instructionEntries, instructionArgs)
  self.mapOn.menu:set_instructionEntries(instructionEntries)
  self.mapOn.menu:set_instructionArgs(instructionArgs)
  if #instructionEntries == 0 then
    self.mapOn.menu:AddInstructionEntry({
      StateName = "MapOn",
      ListName = consts.inworldMenu_SubmenuList,
      Item = mapUtil.GetPlayerRealm()
    })
  end
  self:Goto("MapOn")
end
function MapOn:Setup()
  self.mapOff = self:GetState("MapOff")
  self.currRealmName = nil
  self.currQuestID = nil
  self.currMarkerID = nil
  self.currShownMarkerID = nil
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  self.currMarkerPlayerIcon = false
  self.fastTravelPointSelected = false
  self.fastTravelCancelled = false
  self.realmMarkerInfo = {}
  self.filterIndex = 1
  self.filterButtonMapping = {1}
  self.alwaysOnMarkers = {}
  self.markers = {}
  util.ShowRecursive("mapScene")
  self:HideAllMaps()
  util.Hide("AllMaps")
  self.goFilter = util.GetUiObjByName("SortList")
  self.goFilterList = self.goFilter:FindSingleGOByName("list")
  self.goFilterLabelContainer = self.goFilter:FindSingleGOByName("LabelContainer")
  self.goFilterLabel = self.goFilterLabelContainer:FindSingleGOByName("Label")
  self.thFilterLabel = UI.TextObject(self.goFilterLabel)
  self.goFilterIndicatorPrev = self.goFilter:FindSingleGOByName("IndicatorPrev")
  UI.SetTextIsClickable(util.GetTextHandle(self.goFilterIndicatorPrev))
  self.goFilterIndicatorNext = self.goFilter:FindSingleGOByName("IndicatorNext")
  UI.SetTextIsClickable(util.GetTextHandle(self.goFilterIndicatorNext))
  self.goFilterButtons = {
    1,
    2,
    3,
    4,
    5,
    6,
    7
  }
  self.goFilterButtonPositions = {
    engine.Vector.New(-13.939, -48.295, 1.351),
    engine.Vector.New(-13.539, -48.295, 1.351),
    engine.Vector.New(-13.139, -48.295, 1.351),
    engine.Vector.New(-12.739, -48.295, 1.351),
    engine.Vector.New(-12.339, -48.295, 1.351),
    engine.Vector.New(-11.939, -48.295, 1.351),
    engine.Vector.New(-11.539, -48.295, 1.351)
  }
  for i = 1, 7 do
    self.goFilterButtons[i] = self.goFilterList:FindSingleGOByName("Button" .. tostring(i)):FindSingleGOByName("button")
    UI.SetIsClickable(self.goFilterButtons[i])
  end
  self.menu = menu.Menu.New(self, {})
  self.menu:SetupSubmenuList(consts.inworldMenu_SubmenuList, {
    "EVT_Left_Release"
  }, {
    "EVT_Right_Release"
  })
  local goRefnode = util.GetUiObjByName("MapCursor")
  local goRefnodeChild = goRefnode:FindSingleGOByName("Root")
  goRefnode:Show()
  goRefnodeChild:Show()
  local goRegionSummaryCard = util.GetUiObjByName("mapSummary_Region")
  self.mapSummaryCard_Region = mapSummaryCard.MapSummaryCard.New(goRegionSummaryCard)
  self.mapSummaryCard_Region:Init("Region")
  local goRealmSummaryCard = util.GetUiObjByName("mapSummary_Realm")
  self.mapSummaryCard_Realm = mapSummaryCard.MapSummaryCard.New(goRealmSummaryCard)
  self.mapSummaryCard_Realm:Init("Realm")
  local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
  self._goCursorTextGroup_Top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
  self._goCursorTextGroup_Bottom = goMapCursorText:FindSingleGOByName("CursorInfo_Bottom")
  self.playerIconGO = util.GetUiObjByName("MapIconPlayer")
  UI.SetIsClickable(self.playerIconGO)
  assert(self.playerIconGO ~= nil, "The player indicator gameObject was not found.")
  tutorialUtil.RegisterDesaturationObject("MapSortList", self.goFilter)
  tutorialUtil.RegisterDesaturationObject("MapCursor", goRefnode)
  tutorialUtil.RegisterDesaturationObject("MapCursorInfo", goMapCursorText)
end
function MapOn:UpdateAccessibilityScaling()
  self.mapSummaryCard_Realm:UpdateAccessibilityScaling()
  self.mapSummaryCard_Region:UpdateAccessibilityScaling()
end
function MapOn:Enter()
  local instructionArgs = self.menu:get_instructionArgs()
  self.markerIdHashToSelectOnOpen = instructionArgs.markerIdHashToSelectOnOpen
  self.isOpenedForFastTravel = instructionArgs.openForFastTravel
  self.menu:Activate()
  self:UpdateAccessibilityScaling()
  self.fastTravelPointSelected = false
  self.fastTravelCancelled = false
  self.clickedMarkerInfo = nil
  self.clickedPlayer = false
  util.Show("AllMaps", "Map", "MapCursor", "mapDepthBlur")
  self:HideSummary()
  Audio.PlaySound("SND_UX_Pause_Menu_Map_Cursor_LP")
  local submenuList = self.menu:GetList(consts.inworldMenu_SubmenuList)
  local newItemArray = self:GetSubStateNames()
  local showList = true
  local useOnGainFocus = not self.menu:HasInstructionEntryForMenuState()
  local itemDetermineFocusabilityFunc, getDisplayNameFunc
  self.menu:RefreshSubmenuList(submenuList, newItemArray, showList, useOnGainFocus, itemDetermineFocusabilityFunc, getDisplayNameFunc)
  self.filterIndex = 1
  self.jumpToMarkerIndex = 0
  self:ClearMarkers(true)
  self:GetRealmMarkerInfo()
  if self.isOpenedForFastTravel then
    local hideList = true
    local clearButtons = false
    submenuList:Deactivate(hideList, clearButtons)
    self.markerIncludeFlags = fastTravelMarkerFlags
    self:GetAlwaysOnMarkers()
    self:GetMarkers()
  else
    self.markerIncludeFlags = markerFilters[self.filterIndex].markerIncludeFlags
    self:GetAlwaysOnMarkers()
    self:GetMarkers()
    util.Show("XPandHS")
    self.goFilter:Show()
    self.goFilterList:Show()
    self.goFilterLabelContainer:Show()
    self.goFilterLabel:Show()
    self.goFilterIndicatorPrev:Show()
    self.goFilterIndicatorNext:Show()
    local instant = true
    self.mapSummaryCard_Region:ShowCard()
    self.mapSummaryCard_Region:SetOnScreen(false, instant)
    self.mapSummaryCard_Realm:ShowCard()
    self.mapSummaryCard_Realm:SetOnScreen(true, instant)
    self:CheckForTutorial()
  end
  self:UpdateIcons()
  local compassMarkers = game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
  if 0 < #compassMarkers then
    self.currShownMarkerID = compassMarkers[1]
    if 1 < #compassMarkers then
      for i = 2, #compassMarkers do
        game.Compass.HideMarker(compassMarkers[i])
      end
    end
  else
    self.currShownMarkerID = nil
  end
  for _, realmName in ipairs(mapConsts.REALM_NAMES) do
    self:EnableAllFog(realmName)
  end
  self.menu:ExecuteInstructions()
end
function MapOn:Exit()
  CompletionistMapV100_DestroyNornirChestPins(self)
  CompletionistMapV100_DestroyNornirPins(self)
  CompletionistMapV100_DestroyMapPin(self)
  self.menu:Deactivate(true)
  Audio.StopSound("SND_UX_Pause_Menu_Map_Cursor_LP")
  util.Hide("AllMaps", "Map", "MapCursor", "mapDepthBlur")
  self:HideSummary()
  self.mapSummaryCard_Region:HideCard()
  self.mapSummaryCard_Realm:HideCard()
  self.goFilter:Hide()
  self.goFilterList:Hide()
  self.goFilterLabelContainer:Hide()
  self.goFilterLabel:Hide()
  self.goFilterIndicatorPrev:Hide()
  self.goFilterIndicatorNext:Hide()
  util.Hide("overviewOutline_Selected", "overviewOutline_Unselected")
  self:ClearMarkers(true)
  self:ClearReticleInfo()
  self.markerIdHashToSelectOnOpen = nil
  self.openedAtMarker = nil
  self.currRealmName = nil
  self:ClearIcons()
  self.realmMarkerInfo = {}
  self.filterButtonMapping = {1}
  self.currQuestID = nil
  self.currMarkerID = nil
  self.currMarkerPlayerIcon = false
  self.fastTravelPointSelected = false
  self.fastTravelCancelled = false
  self.isOpenForFastTravel = false
  for _, realmName in ipairs(mapConsts.REALM_NAMES) do
    self:EnableAllFog(realmName)
  end
  if self.playingMoveToActiveMarker then
    Audio.StopSound("SND_UX_Pause_Menu_Map_MoveTo_Active_Marker_LP")
    self.playingMoveToActiveMarker = false
  end
end
function MapOn:EVT_TouchPad_Release()
  if tutorialUtil.CurrentlyShowingStep() then
    return
  end
  if game.IsMapAvailable then
    if not game.IsMapAvailable() then
      return
    end
  elseif game.build.GOLD_VERSION == 0 then
    return
  end
  if not self.fastTravelPointSelected then
    self.fastTravelCancelled = true
    util.CallScriptOnCurrentInteractObject("TriggerFastTravelCancel")
  end
  self:SendEventToUIFsm("globalMenu", "EVT_TURN_OFF_GLOBAL_MENU")
end
function MapOn:GetSubStateNames()
  return mapUtil.GetDiscoveredRealmNames()
end
function MapOn:SubmenuList_Button_Update(button)
  local alphaValue = 1
  local fadeTime = 0
  button:AlphaFade(alphaValue, fadeTime)
  button:SetIcon(button:get_item())
  button:UpdateNewIcon(function(button)
    return buttonUtil.ShowNotification(button, "Map")
  end)
end
function MapOn:SubmenuList_Button_OnLoseFocus(button)
  local realmName = button:get_item()
  if button._MapMenu_ManuallySelected and realmName ~= nil then
    UI.ClearNotification("Map", realmName)
    button:UpdateNewIcon(function(button)
      return buttonUtil.ShowNotification(button, "Map")
    end)
    button._MapMenu_ManuallySelected = nil
  end
  self:SendEventToUIFsm("inWorldMenu", "EVT_REFRESH_NOTIFICATIONS")
end
function MapOn:SubmenuList_Button_OnGainFocus(button)
  local currentItem = button:get_item()
  self.menu:SetSubmenuListLabelText(consts.inworldMenu_SubmenuList, util.GetLAMSMsg(lamsConsts[currentItem]))
  local subState = self:GetState(currentItem)
  subState.menu:set_instructionEntries(self.menu:get_instructionEntries())
  button._MapMenu_ManuallySelected = true
  self:Goto(currentItem)
end
function MapOn:GetShowOnCompassPrompt(currMenu)
  if self.completionistMapV100NornirChestSelected ~= nil then
    local pin = self.completionistMapV100NornirChestSelected
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      return false, nil
    end
    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end
    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and
      target.type == "NornirChest" and
      target.registryKey == pin.registryKey
    local lamsId = sameTarget and target.active and
      lamsConsts.RemoveFromCompass or lamsConsts.AddToCompass
    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  if self.completionistMapV100NornirSelected ~= nil then
    local pin = self.completionistMapV100NornirSelected

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      return false, nil
    end

    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget =
      target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex

    local lamsId =
      sameTarget and target.active and
      lamsConsts.RemoveFromCompass or
      lamsConsts.AddToCompass

    if self.completionistMapV100NornirPromptLogged ~= pin.keyIndex then
      self.completionistMapV100NornirPromptLogged = pin.keyIndex
      print("[CompletionistMap v0.10.1] NORNIR_PROMPT" ..
        " visible=true" ..
        " index=" .. tostring(pin.keyIndex) ..
        " active=" .. tostring(sameTarget and target.active == true))
    end

    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  if self.completionistMapV100Selected then
    if CompletionistMapV100_IsRavenCollected() then
      return false, nil
    end

    if self.isOpenedForFastTravel or
        not game.Compass.HaveCompass() or
        self.currRealmName ~= mapUtil.GetPlayerRealm() or
        tutorialUtil.CurrentlyShowingStep() then
      return false, nil
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and target.type == "Raven"
    local lamsId =
      sameTarget and target.active and
      lamsConsts.RemoveFromCompass or
      lamsConsts.AddToCompass

    return true, "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end  if not (not self.isOpenedForFastTravel and game.Compass.HaveCompass()) or self.currRealmName ~= mapUtil.GetPlayerRealm() or self.currMarkerID == nil or tutorialUtil.CurrentlyShowingStep() or not Map.MarkerHasAnyFlag(self.currMarkerID, enabledShowOnCompassMarkerFlags) then
    return false, nil
  end
  local showOnCompassText = lamsConsts.AddToCompass
  if self.currMarkerID == nil and self.currShownMarkerID ~= nil or self.currMarkerID == self.currShownMarkerID then
    showOnCompassText = lamsConsts.RemoveFromCompass
  elseif self.currShownMarkerID ~= nil and self.currMarkerID ~= self.currShownMarkerID then
    showOnCompassText = lamsConsts.ReplaceInCompass
  end
  return true, "[AdvanceButton] " .. util.GetLAMSMsg(showOnCompassText)
end
function MapOn:UpdateFooterButtonPrompt(currMenu, showConfirmFastTravel, showGoToJournal)
  local showShowOnCompass, showOnCompassText = self:GetShowOnCompassPrompt(currMenu)
  currMenu:UpdateFooterButton("ShowOnCompass", showShowOnCompass, showOnCompassText)
  currMenu:UpdateFooterButton("ConfirmFastTravel", showConfirmFastTravel and self.isOpenedForFastTravel)
  local showPlayerToggle =
    not showGoToJournal and
    not self.isOpenedForFastTravel and
    mapUtil.GetPlayerRealm() == self.currRealmName

  if showPlayerToggle then
    local playerToggleText =
      _G.CompletionistMapV100PlayerMarkerVisible == false and
      "[SquareButton] Show Kratos" or
      "[SquareButton] Hide Kratos"

    currMenu:UpdateFooterButton(
      "GoToJournal",
      true,
      playerToggleText
    )
  else
    currMenu:UpdateFooterButton(
      "GoToJournal",
      showGoToJournal and not self.isOpenedForFastTravel
    )
  end
  currMenu:UpdateFooterButton("ActiveMarkers", not self.isOpenedForFastTravel)
  currMenu:UpdateFooterButton("Move", true)
  currMenu:UpdateFooterButton("Zoom", true)
  currMenu:UpdateFooterButton("Settings", not self.isOpenedForFastTravel)
  currMenu:UpdateFooterButton("Exit", true)
  currMenu:UpdateFooterButton("Weapon", true)
  currMenu:UpdateFooterButton("Skill", true)
  currMenu:UpdateFooterButton("Quest", true)
  currMenu:UpdateFooterButton("Close", true)
  currMenu:UpdateFooterButtonText()
end
function MapOn:HideAllMaps()
  for _, realmName in ipairs(mapConsts.REALM_NAMES) do
    util.Hide(mapUtil.GetRealmCollisionGOName(realmName))
    util.Hide(realmName)
  end
end
function MapOn:ShowMap(realmName)
  self:HideAllMaps()
  util.Show(mapUtil.GetRealmCollisionGOName(realmName))
  util.Show(realmName)
end
function MapOn:UpdateMapState()
  local GetGlobalVar = game.Level.GetVariable
  local completedCineNumber = GetGlobalVar("CompletedCineNumber")
  local hammerFallCineNumber = 355
  local stonemasonFallCineNumber = 570
  local peaksPassSummitRevealedCineNumber = 310
  local afterLightChangeCineNumber = 242
  local jotunheimRevealed = GetGlobalVar("_GBL_JotTowerRevealed")
  local goMap = util.GetUiObjByName("mapScene")
  local goAlfheim = goMap:FindSingleGOByName("Alfheim")
  local jid_red = goAlfheim:GetJointIndex("emit_map_alfheim_beam_red")
  local jid_white = goAlfheim:GetJointIndex("emit_map_alfheim_beam")
  if completedCineNumber >= afterLightChangeCineNumber then
    goAlfheim:ShowJoint(jid_white)
    goAlfheim:HideJoint(jid_red)
  else
    goAlfheim:ShowJoint(jid_red)
    goAlfheim:HideJoint(jid_white)
  end
  local goJotunheimTower = util.GetUiObjByName("RealmTower4")
  local goJotunheimTowerCollision = util.GetUiObjByName("towercollision_jotunheim")
  local goJotunheimTowerInAlfheim = goAlfheim:FindSingleGOByName("RealmTower9")
  local goNiflheim = goMap:FindSingleGOByName("Niflheim")
  local goJotunheimTowerInNiflheim = goNiflheim:FindSingleGOByName("RealmTower9")
  if jotunheimRevealed then
    goJotunheimTower:Show()
    goJotunheimTowerCollision:Show()
    goJotunheimTowerInAlfheim:Show()
    goJotunheimTowerInNiflheim:Show()
  else
    goJotunheimTower:Hide()
    goJotunheimTowerCollision:Hide()
    goJotunheimTowerInAlfheim:Hide()
    goJotunheimTowerInNiflheim:Hide()
  end
  local goAlfWaterGroup = util.GetUiObjByName("Alfheim_Water")
  local jid_AlfWater1 = goAlfWaterGroup:GetJointIndex("AlfWater1")
  if GetGlobalVar("ALF_TrenchOpen") then
    goAlfWaterGroup:HideJoint(jid_AlfWater1)
  else
    goAlfWaterGroup:ShowJoint(jid_AlfWater1)
  end
  local goHammerStatesGroup = util.GetUiObjByName("Hammer_map_states")
  local goHammer = goHammerStatesGroup:FindSingleGOByName("hammer_stonemason_map")
  goHammerStatesGroup:Show()
  goHammer:Show()
  if completedCineNumber >= hammerFallCineNumber then
    animationUtil.SetTransform(goHammer, goHammerStatesGroup, "hammer_down")
  else
    animationUtil.SetTransform(goHammer, goHammerStatesGroup, "hammer_up")
  end
  local goStonemason = util.GetUiObjByName("map_stonemason_giant")
  goStonemason:Show()
  if completedCineNumber <= stonemasonFallCineNumber then
    local targetTimelinePos = 0.1
    local animRate = 0
    UI.Anim(goStonemason, consts.AS_Forward, "", animRate, targetTimelinePos)
  else
    local targetTimelinePos = 0.2
    local animRate = 0
    UI.Anim(goStonemason, consts.AS_Forward, "", animRate, targetTimelinePos)
  end
  local goSummit_gateTree = util.GetUiObjByName("Summit_gateTree")
  if completedCineNumber >= peaksPassSummitRevealedCineNumber then
    goSummit_gateTree:Show()
  else
    goSummit_gateTree:Hide()
  end
  local goThorStatue1 = util.GetUiObjByName("thorStatue1")
  if 340 <= completedCineNumber then
    goThorStatue1:Hide()
  else
    goThorStatue1:Show()
  end
  local goMidgard = goMap:FindSingleGOByName("Midgard")
  local jid_smallThorStatue = goMidgard:GetJointIndex("smallThorStatue")
  if GetGlobalVar("ThorStatueBroken") or game.QuestManager.GetQuestState("Quest_UnfinishedBusiness03_Objective_01") == questConsts.QUEST_STATE_COMPLETE then
    goMidgard:HideJoint(jid_smallThorStatue)
  else
    goMidgard:ShowJoint(jid_smallThorStatue)
  end
  self:UpdateSnakeState(completedCineNumber)
  self:UpdateHelheimBoat()
  self:UpdateWaterLevel()
  self:AnimateFog()
end
function MapOn:CheckForTutorial()
  local resourceValue = game.Wallets.GetResourceValue("HERO", "MapTutorial")
  local hasResource = -1 < resourceValue
  if not hasResource and game.Level.GetVariable("CompletedCineNumber") >= 180 then
    self:SendEventToUIFsm("inWorldMenu", "EVT_ATTEMPT_TUTORIAL", "Map", "MapTutorial", "MapFilterTutorial")
  end
end
function MapOn:UpdateSnakeState(completedCineNumber)
  local currentSnakeState = mapConsts.snakeState_1
  for _, table in ipairs(mapConsts.snakeIdleTable) do
    if completedCineNumber >= table.MinCine and completedCineNumber < table.MaxCine then
      currentSnakeState = table.State
      break
    end
  end
  local goSnake = util.GetUiObjByName("worldSnake")
  local targetTimelinePos = currentSnakeState * 0.1
  local animRate = 0
  UI.Anim(goSnake, consts.AS_Forward, "", animRate, targetTimelinePos)
end
function MapOn:SetupCameraForMap(realmName)
  if tweaks.tMapCamera and realmName ~= nil then
    map_camera.CollisionRoot = mapUtil.GetRealmCollisionGOName(realmName)
    Camera.SetMapCamera(nil)
    Camera.SetMapCamera(map_camera)
  end
end
function MapOn:UpdateHelheimBoat()
  local GetGlobalVar = game.Level.GetVariable
  local boatState = GetGlobalVar("Hel_MapState")
  local goMapBoat = util.GetUiObjByName("map_helheim_boat")
  goMapBoat:Show()
  local targetTimelinePos = 0
  if boatState == 1 then
    targetTimelinePos = 0.1
  elseif boatState == 2 then
    targetTimelinePos = 0.2
  elseif boatState == 3 then
    targetTimelinePos = 0.3
  elseif boatState == 4 then
    targetTimelinePos = 0.4
  end
  local animRate = 0
  UI.Anim(goMapBoat, consts.AS_Forward, "", animRate, targetTimelinePos)
end
function MapOn:UpdateWaterLevel()
  local targetTimelinePos = 0.3
  local animRate = 0
  local goWaterGroup = util.GetUiObjByName("Midgard_Water")
  local jid_waterLevel0 = goWaterGroup:GetJointIndex("WaterLevel0")
  local jid_waterLevel1 = goWaterGroup:GetJointIndex("WaterLevel1")
  if game.Level.GetVariable("_GBL_WaterDrop01Triggered") == false then
    goWaterGroup:ShowJoint(jid_waterLevel0)
    goWaterGroup:HideJoint(jid_waterLevel1)
    targetTimelinePos = 0.3
  elseif game.Level.GetVariable("_GBL_WaterDrop02Triggered") == false then
    goWaterGroup:ShowJoint(jid_waterLevel1)
    goWaterGroup:HideJoint(jid_waterLevel0)
    targetTimelinePos = 0.2
  else
    goWaterGroup:HideJoint(jid_waterLevel1)
    goWaterGroup:HideJoint(jid_waterLevel0)
    targetTimelinePos = 0.1
  end
  local goLakeText = util.GetUiObjByName("CalderaLake")
  local calderaShoresARegionInfo = mapUtil.GetRegionInfo(mapConsts.REGION_CALDERASHORESA)
  local calderaShoresDiscovered = mapUtil.RegionInfo_IsDiscovered(calderaShoresARegionInfo)
  if calderaShoresDiscovered then
    goLakeText:Show()
    UI.Anim(goLakeText, consts.AS_Forward, "", animRate, targetTimelinePos)
  else
    goLakeText:Hide()
  end
end
function MapOn:UpdateTempleRotation(realmName)
  mapUtil.UpdateTempleRotation(realmName)
end
function MapOn:AnimateFog()
  local goFogAnimated = util.GetUiObjByName("fogNoise_Animated")
  local targetTimelinePos = 1
  local animRate = 0.01
  UI.Anim(goFogAnimated, consts.AS_ForwardCycle, "", animRate, targetTimelinePos)
  local goRenderLayer = util.GetUiObjByName("mapRenderLayer")
  goRenderLayer:Show()
  animRate = 0.01
  UI.Anim(goRenderLayer, consts.AS_ForwardCycle, "", animRate, targetTimelinePos)
  local goMidgardWaterGroup = util.GetUiObjByName("Midgard_Water")
  animRate = 0.01
  UI.Anim(goMidgardWaterGroup, consts.AS_ForwardCycle, "", animRate, targetTimelinePos)
  local goAlfWaterGroup = util.GetUiObjByName("Alfheim_Water")
  animRate = 0.01
  UI.Anim(goAlfWaterGroup, consts.AS_ForwardCycle, "", animRate, targetTimelinePos)
end
function MapOn:EnableAllFog(realmName)
  local fogTable = mapConsts.MAP_FOG_GAMEOBJECTS
  local allRegionInfo = mapUtil.GetAllRegionInfoInRealm(realmName)
  local goMapVis = util.GetUiObjByName("Maps")
  for _, regionInfo in ipairs(allRegionInfo) do
    local regionName = mapUtil.RegionInfo_GetName(regionInfo)
    local regionID = mapUtil.RegionInfo_GetID(regionInfo)
    local isInvertFogRegion = mapUtil.Region_HasFlags(regionID, {
      mapConsts.REGION_FLAG_INVERT_FOG
    })
    local fogObjectName = fogTable[regionName]
    if isInvertFogRegion then
      util.Show(fogObjectName)
    else
      util.Hide(fogObjectName)
    end
    local goRealm = goMapVis:FindSingleGOByName(realmName)
    if goRealm ~= nil then
      local goRealmTextHolder = goRealm:FindSingleGOByName("text")
      if goRealmTextHolder ~= nil then
        local jointName = mapConsts.MAP_TEXT_GAMEOBJECTS[regionName]
        if jointName ~= nil then
          local iJoint = goRealmTextHolder:GetJointIndex(jointName)
          goRealmTextHolder:HideJoint(iJoint)
        end
      end
    end
  end
end
function MapOn:SetupVisibilityOfRegions(realmName)
  local fogTable = mapConsts.MAP_FOG_GAMEOBJECTS
  local allRegionInfo = mapUtil.GetAllRegionInfoInRealm(realmName)
  for _, regionInfo in ipairs(allRegionInfo) do
    local regionName = mapUtil.RegionInfo_GetName(regionInfo)
    local regionID = mapUtil.RegionInfo_GetID(regionInfo)
    local isRegionDiscovered = mapUtil.RegionInfo_IsDiscovered(regionInfo)
    local isInvertFogRegion = mapUtil.Region_HasFlags(regionID, {
      mapConsts.REGION_FLAG_INVERT_FOG
    })
    local fogObjectName = fogTable[regionName]
    local shouldShowFog = isRegionDiscovered
    if isInvertFogRegion then
      shouldShowFog = not shouldShowFog
    end
    if shouldShowFog then
      util.Show(fogObjectName)
    else
      util.Hide(fogObjectName)
    end
    local goMapVis = util.GetUiObjByName("Maps")
    local goRealm = goMapVis:FindSingleGOByName(realmName)
    local goRealmTextHolder = goRealm:FindSingleGOByName("text")
    if goRealmTextHolder ~= nil then
      local jointName = mapConsts.MAP_TEXT_GAMEOBJECTS[regionName]
      if jointName ~= nil then
        local iJoint = goRealmTextHolder:GetJointIndex(jointName)
        if isRegionDiscovered then
          goRealmTextHolder:ShowJoint(iJoint)
        else
          goRealmTextHolder:HideJoint(iJoint)
        end
      end
    end
  end
end
function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)
  -- Child puzzle actors take priority over their parent chest when their
  -- clickable roots overlap at high zoom.
  local completionistMapV100NornirPin =
    CompletionistMapV100_FindNornirCollision(
      self,
      collisionGameObjectTable
    )

  if completionistMapV100NornirPin ~= nil then
    self.completionistMapV100NornirSelected =
      completionistMapV100NornirPin
    self.completionistMapV100NornirLastHitFrame =
      self.completionistMapV100Frame or 0
    self.completionistMapV100NornirChestSelected = nil
    self.completionistMapV100Selected = false

    CompletionistMapV100_SetCustomCursorSelected(true)

    CompletionistMapV100_NornirReticle(
      self,
      currState,
      completionistMapV100NornirPin
    )

    print("[CompletionistMap v0.10.1] NORNIR_SELECTION" ..
      " active=true" ..
      " registryKey=" ..
        tostring(completionistMapV100NornirPin.registryKey) ..
      " index=" ..
        tostring(completionistMapV100NornirPin.keyIndex) ..
      " priority=child" ..
      " snapMode=native_cursor" ..
      " preservesZoom=true")
    return
  end

  if self.completionistMapV100NornirSelected ~= nil then
    local frame = self.completionistMapV100Frame or 0
    local lastHit =
      self.completionistMapV100NornirLastHitFrame or frame

    if frame - lastHit <= 12 then
      return
    end

    self.completionistMapV100NornirSelected = nil
    print("[CompletionistMap v0.10.1] NORNIR_SELECTION cleared=true" ..
      " latchFrames=12")
  end

  local completionistMapV100ChestPin =
    CompletionistMapV100_FindNornirChestCollision(
      self, collisionGameObjectTable
    )

  if completionistMapV100ChestPin ~= nil then
    self.completionistMapV100NornirChestSelected = completionistMapV100ChestPin
    self.completionistMapV100NornirSelected = nil
    self.completionistMapV100Selected = false
    CompletionistMapV100_SetCustomCursorSelected(true)
    CompletionistMapV100_NornirChestReticle(
      self, currState, completionistMapV100ChestPin
    )
    print("[CompletionistMap v0.10.1] NORNIR_CHEST_SELECTION" ..
      " active=true registryKey=" ..
        tostring(completionistMapV100ChestPin.registryKey) ..
      " priority=parent" ..
      " snapMode=native_cursor" ..
      " preservesZoom=true")
    return
  end

  self.completionistMapV100NornirChestSelected = nil

  local completionistMapV100IsCustom =
    CompletionistMapV100_CollisionContainsPin(
      self,
      collisionGameObjectTable
    )

  if completionistMapV100IsCustom then
    local frame = self.completionistMapV100Frame or 0
    self.completionistMapV100LastHitFrame = frame

    if not self.completionistMapV100CollisionState then
      print("[CompletionistMap v0.10.1] MAP_COLLISION hit=true")
    end
    self.completionistMapV100CollisionState = true

    if not self.completionistMapV100Selected then
      self.completionistMapV100Selected = true
      print("[CompletionistMap v0.10.1] MAP_SELECTION active=true")
    end

    CompletionistMapV100_SetCustomCursorSelected(true)
    CompletionistMapV100_ShowReticle(self, currState)

    if not self.completionistMapV100NativeSnapLogged then
      self.completionistMapV100NativeSnapLogged = true
      print("[CompletionistMap v0.10.1] MAP_SNAP" ..
        " mode=native_cursor" ..
        " preservesZoom=true" ..
        " frame=" .. tostring(frame))
    end
    return
  end

  if self.completionistMapV100CollisionState then
    print("[CompletionistMap v0.10.1] MAP_COLLISION hit=false_debounced")
  end
  self.completionistMapV100CollisionState = false

  if self.completionistMapV100Selected then
    local frame = self.completionistMapV100Frame or 0
    local lastHit = self.completionistMapV100LastHitFrame or 0
    local age = frame - lastHit

    if age <= 6 then
      return
    end

    self.completionistMapV100Selected = false
    print("[CompletionistMap v0.10.1] MAP_SELECTION cleared=true" ..
      " ageFrames=" .. tostring(age))
  end  local iconCollInfo, terrainCollInfo = mapUtil.GetPrioritizedIconAndTerrain(collisionGameObjectTable)
  local showConfirmFastTravel = false
  local showGoToJournal = false
  local setReticleSelected = false
  self.currQuestID = nil
  self.currMarkerID = nil
  self.currMarkerPlayerIcon = false
  if self.isOpenedForFastTravel and Camera.HasTarget ~= nil and Camera.HasTarget() then
    local fastTravelList = currState.menu:GetList("FastTravelList")
    local currFastTravelMarkerInfo
    if self.clickedMarkerInfo ~= nil then
      currFastTravelMarkerInfo = self.clickedMarkerInfo
    else
      currFastTravelMarkerInfo = fastTravelList:GetSelectedItem()
    end
    if self.clickedPlayer then
      self.currMarkerPlayerIcon = true
    end
    if currFastTravelMarkerInfo == nil then
      Camera.PointAt(CALDERA_MAP_POSITION, true)
    else
      self.currMarkerID = currFastTravelMarkerInfo.Id
      if iconCollInfo ~= nil then
        local collisionType = mapUtil.GetMapCollisionInfoType(iconCollInfo)
        local markerInfo = mapUtil.GetMapCollisionInfoInfo(iconCollInfo)
        if self.clickedPlayer or markerInfo ~= nil and markerInfo.Id == self.currMarkerID then
          setReticleSelected = true
        end
      end
      local isDiscoveredButLocked = currFastTravelMarkerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
      showConfirmFastTravel = self.clickedMarkerInfo == nil and not self.clickedPlayer and not isDiscoveredButLocked and not self:IsPlayerAtMarker(currFastTravelMarkerInfo)
    end
    if self.clickedPlayer then
      currFastTravelMarkerInfo = nil
    end
    self:UpdateReticleInfo(currState, currFastTravelMarkerInfo)
  else
    self.clickedMarkerInfo = nil
    self.clickedPlayer = false
    if iconCollInfo == nil then
      self:ClearReticleInfo()
      local cineNumberAfterWhichTowerInfoIsDisplayed = 200
      if cineNumberAfterWhichTowerInfoIsDisplayed <= game.Level.GetVariable("CompletedCineNumber") then
        for i = 1, #collisionGameObjectTable do
          local collGO = collisionGameObjectTable[i]
          if collGO ~= nil and collGO.GetName ~= nil then
            local name = collGO:GetName()
            if string.sub(name, 1, 15) == "towercollision_" then
              local towerName = string.sub(name, 16)
              local title = util.GetLAMSMsg(lamsConsts.towerDesc[towerName], towerName)
              self:SetReticleInfo(currState, title, "")
            end
          end
        end
      end
    else
      local collisionType = mapUtil.GetMapCollisionInfoType(iconCollInfo)
      local markerInfo = mapUtil.GetMapCollisionInfoInfo(iconCollInfo)
      if markerInfo ~= nil then
        if collisionType == mapConsts.MAP_COLL_ICON then
          local markerID = markerInfo.Id
          self.currMarkerID = markerID
          local hasQuest, questName = questUtil.FindQuestForMarker(markerID)
          self.currQuestID = hasQuest and questName or nil
          showGoToJournal = hasQuest
        end
        if Map.MarkerHasAnyFlag(markerInfo.Id, fastTravelMarkerFlags) then
          local isDiscoveredButLocked = markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
          showConfirmFastTravel = not isDiscoveredButLocked and not self:IsPlayerAtMarker(markerInfo)
        end
      elseif collisionType == mapConsts.MAP_COLL_PLAYER_ICON then
        self.currMarkerPlayerIcon = true
      end
      self:UpdateReticleInfo(currState, markerInfo)
      setReticleSelected = true
    end
  end
  if terrainCollInfo == nil then
    self:HideSummary()
  else
    self:UpdateSummary(realmName, terrainCollInfo)
  end
  local goCursorRefnode = util.GetUiObjByName("MapCursor")
  animationUtil.SetCursorSelected(goCursorRefnode, setReticleSelected)
  if setReticleSelected then
    Audio.PlaySound("SND_UX_Pause_Menu_Screen_Map_Region_Hover_Tick")
  end
  self:UpdateFooterButtonPrompt(currState.menu, showConfirmFastTravel, showGoToJournal)
end
function MapOn:GetMapMarkerTrackingState(markerID)
  local trackingState = questConsts.TRACKING_STATE_NONE
  local hasQuest, questID = questUtil.FindQuestForMarker(markerID)
  if hasQuest then
    local trackingInfo = questUtil.GetTrackingInfo(questID)
    trackingState = questUtil.TrackingInfo_GetTrackingState(trackingInfo, questID)
  end
  if self.currShownMarkerID ~= nil and markerID == self.currShownMarkerID then
    trackingState = questConsts.TRACKING_STATE_TRACKED
  end
  return trackingState
end
function MapOn:GetMapMarkerTrackingStateFromIconGO(goIcon)
  local trackingState = questConsts.TRACKING_STATE_NONE
  local markerInfo = Map.FindInfoFromIcon(goIcon)
  if markerInfo ~= nil then
    trackingState = self:GetMapMarkerTrackingState(markerInfo.Id)
  end
  return trackingState
end
function MapOn:UpdateMapMarkerHighlights()
  for i = 1, #self.markers do
    local markerInfo = self.markers[i]
    local goIcon = markerInfo.iconGO
    local goIconTracked = goIcon:FindSingleGOByName("MapIconAreaMainQuest_area")
    local goIconTrackedSide = goIcon:FindSingleGOByName("MapIconAreaSideQuest_area")
    local goIconUntracked = goIcon:FindSingleGOByName("untracked")
    local goIconLock = goIcon:FindSingleGOByName("lock")
    local trackingState = self:GetMapMarkerTrackingStateFromIconGO(goIcon)
    local isRadiusMarker = Map.MarkerHasAnyFlag(markerInfo.Id, {"RadiusType"})
    local isDiscoveredButLocked = markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
    local goMarkerLockIcon = goIcon:FindSingleGOByName("lock")
    if goIconLock ~= nil then
      if isDiscoveredButLocked == true then
        goIconLock:Show()
      else
        goIconLock:Hide()
      end
    end
    if isRadiusMarker and goIconUntracked then
      local offset = engine.Vector.New(markerInfo.OffsetX, 0, markerInfo.OffsetY)
      goIconUntracked:SetLocalPosition(offset)
      goIconUntracked:Show()
      if trackingState == questConsts.TRACKING_STATE_TRACKED then
        UI.Anim(goIconUntracked, consts.AS_ForwardCycle_NoReset, "", 1)
      else
        UI.Anim(goIconUntracked, consts.AS_Forward, "", 0, 0)
      end
    end
    if trackingState == questConsts.TRACKING_STATE_TRACKED then
      if isRadiusMarker and goIconTracked then
        goIconTracked:Show()
      elseif isRadiusMarker and goIconTrackedSide then
        goIconTrackedSide:Show()
      end
      UI.Anim(goIcon, consts.AS_ForwardCycle_NoReset, "", 1)
    else
      if isRadiusMarker and goIconTracked then
        goIconTracked:Hide()
      elseif isRadiusMarker and goIconTrackedSide then
        goIconTrackedSide:Hide()
      end
      UI.Anim(goIcon, consts.AS_Forward, "", 0, 0)
    end
  end
end
function MapOn:IsPlayerAtMarker(markerInfo)
  return self.openedAtMarker ~= nil and markerInfo ~= nil and markerInfo.Id == self.openedAtMarker
end
function MapOn:FastTravel_Button_Update(button)
  local markerInfo = button:get_item()
  local isPlayerAtMarker = self:IsPlayerAtMarker(markerInfo)
  local isLocked = markerInfo ~= nil and markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
  local textColor = (isPlayerAtMarker or isLocked) and colors.GRAY or colors.WHITE
  button:SetTextColor(textColor)
end
function MapOn:FastTravel_Button_OnGainFocus(currState, button)
  local markerInfo = button:get_item()
  if markerInfo ~= nil then
    Camera.PointAtGO(markerInfo.iconGO)
    Audio.PlaySound("SND_UX_Pause_Menu_Map_MoveTo_Active_Marker_LP")
    self.playingMoveToActiveMarker = true
  end
  local isDiscoveredButLocked = markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
  local showConfirmFastTravel = not isDiscoveredButLocked and not self:IsPlayerAtMarker(markerInfo)
  local showGoToJournal = false
  self:UpdateFooterButtonPrompt(currState.menu, showConfirmFastTravel, showGoToJournal)
end
function MapOn:FastTravel_Button_ItemCompare(item, otherItem)
  return item ~= nil and otherItem ~= nil and item.Id == otherItem.Id
end
function MapOn:UpdateFastTravelList(currState)
  local fastTravelList = currState.menu:GetList("FastTravelList")
  if self.isOpenedForFastTravel then
    local unlockedFastTravelMarkers = {}
    for i = 1, #self.markers do
      local markerInfo = self.markers[i]
      if (markerInfo.State == tweaks.eTokenState.kDiscovered or markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked) and Map.MarkerHasAnyFlag(markerInfo.Id, fastTravelMarkerFlags) then
        unlockedFastTravelMarkers[#unlockedFastTravelMarkers + 1] = markerInfo
      end
    end
    fastTravelList:Refresh(unlockedFastTravelMarkers, true, true, nil, function(item)
      return util.GetLAMSMsg(item.LamsDescriptionId, item.Id)
    end)
    fastTravelList:HideLabel()
  else
    local hideList = true
    local clearButtons = false
    fastTravelList:Deactivate(hideList, clearButtons)
    self:UpdateFooterButtonPrompt(currState.menu, false, false)
  end
end
function MapOn:SelectFastTravelButtonByMarkerInfo(currState, markerInfoToSelect)
  local fastTravelList = currState.menu:GetList("FastTravelList")
  if not self:FastTravel_Button_ItemCompare(fastTravelList:GetSelectedItem(), markerInfoToSelect) then
    fastTravelList:SelectItem(markerInfoToSelect, true)
  end
end
function MapOn:ClearReticleInfo()
  local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
  goMapCursorText:Hide()
  self._goCursorTextGroup_Top:Hide()
  self._goCursorTextGroup_Bottom:Hide()
end
function MapOn:Update()
  self.completionistMapV100Frame =
    (self.completionistMapV100Frame or 0) + 1

  CompletionistMapV100_RefreshNornirPins(self)
  CompletionistMapV100_RefreshNornirChestPins(self)
  CompletionistMapV100_IsTargetCollected()
  CompletionistMapV100_RefreshCustomPins(self)

  if CompletionistMapV100_IsRavenCollected() then
    if self.completionistMapV100MapIconGO ~= nil then
      CompletionistMapV100_DestroyMapPin(self)
      print("[CompletionistMap v0.10.1] MAP_PIN_REMOVE reason=raven_collected")
    end
  end  if Camera.GetCursorScaleValue then
    local cursorScaleValue = Camera.GetCursorScaleValue() * 0.5
    local goTop = self._goCursorTextGroup_Top
    local vTargetPos = engine.Vector.New(0, cursorScaleValue, 0)
    local translationTime = 0
    local useWorldSpace = false
    UI.SetGOTransformInterpolated(goTop, vTargetPos, translationTime, useWorldSpace)
    local goBottom = self._goCursorTextGroup_Bottom
    vTargetPos = engine.Vector.New(0, -cursorScaleValue, 0)
    UI.SetGOTransformInterpolated(goBottom, vTargetPos, translationTime, useWorldSpace)
  end
end
function MapOn:UpdateReticleInfo(currState, markerInfo)
  local title = ""
  local desc = ""
  if markerInfo ~= nil then
    local isFastTravelMarker = Map.MarkerHasAnyFlag(markerInfo.Id, fastTravelMarkerFlags)
    local isDiscoveredButLocked = markerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
    title = util.GetLAMSMsg(markerInfo.LamsNameId, markerInfo.Id)
    desc = util.GetLAMSMsg(markerInfo.LamsDescriptionId, markerInfo.Id)
    if isDiscoveredButLocked then
      desc = isFastTravelMarker and util.GetLAMSMsg(lamsConsts.LockedFastTravelMarker) or util.GetLAMSMsg(lamsConsts.LockedMarker)
    end
    if self.isOpenedForFastTravel and Map.MarkerHasAnyFlag(markerInfo.Id, fastTravelMarkerFlags) then
      self:SelectFastTravelButtonByMarkerInfo(currState, markerInfo)
    end
  elseif self.currMarkerPlayerIcon then
    title = "[MSG:" .. lamsConsts.Kratos .. "]"
  end
  self:SetReticleInfo(currState, title, desc)
end
function MapOn:SetReticleInfo(currState, title, desc)
  local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
  goMapCursorText:Show()
  local goTitle = goMapCursorText:FindSingleGOByName("CursorInfo_Bottom")
  local thTitle = util.GetTextHandle(goTitle, "CursorTitle_Text")
  if not util.IsStringNilOrEmpty(title) then
    UI.SetText(thTitle, title)
    goTitle:Show()
  else
    UI.SetText(thTitle, "")
    goTitle:Hide()
  end
  local thDescription = util.GetTextHandle(goTitle, "CursorDescription_Text")
  if not util.IsStringNilOrEmpty(desc) then
    UI.SetText(thDescription, desc)
  else
    UI.SetText(thDescription, "")
  end
  local goCursorInfo_Top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
  local thPrompt = util.GetTextHandle(goCursorInfo_Top, "CursorAction_Text")
  UI.SetTextIsClickable(thPrompt)
  if self.isOpenedForFastTravel then
    UI.SetText(thPrompt, "")
    goCursorInfo_Top:Hide()
  elseif self.currQuestID ~= nil then
    UI.SetText(thPrompt, "[SquareButton] " .. util.GetLAMSMsg(lamsConsts.GoToJournal))
    goCursorInfo_Top:Show()
  else
    local showShowOnCompass, promptText = self:GetShowOnCompassPrompt(currState.menu)
    if showShowOnCompass then
      UI.SetText(thPrompt, promptText)
      goCursorInfo_Top:Show()
    else
      UI.SetText(thPrompt, "")
      goCursorInfo_Top:Hide()
    end
  end
end
function MapOn:ShowRegionSummary()
  local onScreen = true
  self.mapSummaryCard_Region:SetOnScreen(onScreen)
end
function MapOn:HideSummary()
  local onScreen = false
  self.currentRegionId = nil
  self.mapSummaryCard_Region:SetOnScreen(onScreen)
end
function MapOn:UpdateRealmSummary(realmName)
  local realmInfo = game.Map.GetRealmInfo(realmName)
  self.mapSummaryCard_Realm:SetProperty("RealmInfo", realmInfo)
  local doTransitionAnim = true
  self.mapSummaryCard_Realm:Update(doTransitionAnim)
  if self.isOpenedForFastTravel or self.mapSummaryCard_Realm:GetProperty("numActiveRows") <= 0 then
    self.mapSummaryCard_Realm:HideCard()
  else
    self.mapSummaryCard_Realm:ShowCard()
  end
end
function MapOn:UpdateSummary(realmName, terrainCollInfo)
  local regionIsDifferentFromLastTime = false
  if terrainCollInfo ~= nil then
    local goTerrainCollision = mapUtil.GetMapCollisionInfoGameObject(terrainCollInfo)
    local wadName = goTerrainCollision:GetName()
    local wadRegionInfo = mapUtil.RegionInfo_GetRegionInfoFromWadName(wadName)
    local regionInfo
    if wadRegionInfo ~= nil then
      local allRegionInfo = mapUtil.GetAllRegionInfoInRealm(realmName)
      for i = 1, #allRegionInfo do
        if allRegionInfo[i].Id == wadRegionInfo.Id then
          regionInfo = wadRegionInfo
          break
        end
      end
    end
    if regionInfo ~= nil then
      local isRegionDiscovered = mapUtil.RegionInfo_IsDiscovered(regionInfo)
      local neverShowSummary = mapUtil.Region_HasFlags(regionInfo.Id, {
        "NeverShowSummary"
      })
      if isRegionDiscovered and not neverShowSummary then
        local regionSummaryInfo = Map.GetRegionSummaryInfo(regionInfo.Id)
        self.mapSummaryCard_Region:SetProperty("RegionInfo", regionInfo)
        self.mapSummaryCard_Region:SetProperty("RegionSummaryInfo", regionSummaryInfo)
        if self._previousRegionID ~= regionInfo.Id then
          self._previousRegionID = regionInfo.Id
          regionIsDifferentFromLastTime = true
        end
        if self.currentRegionId == nil or regionInfo.Id ~= self.currentRegionId then
          self:ShowRegionSummary()
        end
        self.currentRegionId = regionInfo.Id
      else
        self:HideSummary()
      end
    else
      self:HideSummary()
    end
  end
  local doTransitionAnim = regionIsDifferentFromLastTime
  self.mapSummaryCard_Region:Update(false)
end
function MapOn:SubmenuSetup(currState)
  currState.menu = menu.Menu.New(currState, {
    FooterButtonInfo = {
      {
        Item = "ConfirmFastTravel",
        Text = "[AdvanceButton] " .. util.GetLAMSMsg(lamsConsts.Confirm)
      },
      {
        Item = "ShowOnCompass",
        Text = "",
        EventHandlers = {
          {
            Events = {
              "EVT_Advance_Release"
            },
            Handler = function()
              self:ShowOnCompass(currState)
            end
          }
        }
      },
      {
        Item = "GoToJournal",
        Text = "[SquareButton] " .. util.GetLAMSMsg(lamsConsts.GoToJournal),
        EventHandlers = {
          {
            Events = {
              "EVT_Square_Release"
            },
            Handler = function()
              self:Menu_Square_ReleaseHandler()
            end
          }
        }
      },
      {
        Item = "ActiveMarkers",
        Text = "[R3] " .. util.GetLAMSMsg(lamsConsts.ActiveMarkers)
      },
      {
        Item = "Move",
        Text = "[JoystickL] " .. util.GetLAMSMsg(lamsConsts.Move)
      },
      {
        Item = "Zoom",
        Text = "[JoystickRY] " .. util.GetLAMSMsg(lamsConsts.Zoom)
      },
      {
        Item = "Settings",
        Text = "[TriangleButton] " .. util.GetLAMSMsg(lamsConsts.Options),
        EventHandlers = {
          {
            Events = {
              "EVT_Triangle_Release"
            },
            Handler = function()
              self:Menu_Triangle_ReleaseHandler()
            end
          }
        }
      },
      {
        Item = "Weapon",
        Text = "",
        EventHandlers = {
          {
            Events = {
              "EVT_GO_TO_WEAPON_MENU"
            },
            Handler = function()
              if not self.isOpenedForFastTravel then
                self:SendEventToUIFsm("globalMenu", "EVT_GO_TO_WEAPON")
              end
            end
          }
        }
      },
      {
        Item = "Skill",
        Text = "",
        EventHandlers = {
          {
            Events = {
              "EVT_GO_TO_SKILL_TREE_MENU"
            },
            Handler = function()
              self:SendEventToUIFsm("globalMenu", "EVT_GO_TO_SKILL_TREE")
            end
          }
        }
      },
      {
        Item = "Quest",
        Text = "",
        EventHandlers = {
          {
            Events = {
              "EVT_GO_TO_QUEST_MENU"
            },
            Handler = function()
              self:SendEventToUIFsm("globalMenu", "EVT_GO_TO_QUEST")
            end
          }
        }
      },
      {
        Item = "Exit",
        Text = "[BackButton] " .. util.GetLAMSMsg(lamsConsts.Exit),
        EventHandlers = {
          {
            Events = {
              "EVT_Back_Release"
            },
            Handler = function()
              self:Menu_Back_ReleaseHandler()
            end
          }
        }
      },
      {
        Item = "Close",
        Text = "",
        EventHandlers = {
          {
            Events = {
              "EVT_Options_Release"
            },
            Handler = function()
              self:Menu_Options_ReleaseHandler()
            end
          }
        }
      }
    }
  })
  local fastTravelList = list.List.New(currState, {
    MaxFocusableObjectCount = 10,
    ListObjectName = "FastTravelList",
    EmptyTextLamsID = lamsConsts.NoFastTravelPointsAvailable,
    NextEvents = {
      "EVT_Down_Release"
    },
    PreviousEvents = {
      "EVT_Up_Release"
    },
    EventHandlers = {
      {
        Events = {
          "EVT_Advance_Release"
        },
        Handler = function()
          self:ConfirmFastTravel(currState)
        end
      }
    },
    Button_Update = function(button)
      self:FastTravel_Button_Update(button)
    end,
    Button_OnGainFocus = function(button)
      self:FastTravel_Button_OnGainFocus(currState, button)
    end,
    Button_ItemCompare = function(item, otherItem)
      return self:FastTravel_Button_ItemCompare(item, otherItem)
    end
  })
  fastTravelList:SetSelectedButton(1, false)
  currState.menu:SetList("FastTravelList", fastTravelList)
  fastTravelList:SetHeaderText(util.GetLAMSMsg(lamsConsts.FastTravelPoints))
end
function MapOn:ClearMarkers(clear_all)
  local first = clear_all == true and 1 or #self.alwaysOnMarkers + 1
  for index = #self.markers, first, -1 do
    self.markers[index].shown = false
    self.markers[index] = nil
  end
  if clear_all then
    self.alwaysOnMarkers = {}
  end
end
function MapOn:ClearIcons()
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if markerInfo.iconGO ~= nil then
      Map.RecycleIcon(markerInfo.iconGO)
      markerInfo.iconGO = nil
    end
  end
end
function MapOn:UpdateIcons()
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if markerInfo.shown and markerInfo.iconGO == nil then
      markerInfo.iconGO = Map.CreateMarkerIcon(markerInfo.Id, markerInfo.regionId, "")
    elseif markerInfo.iconGO ~= nil then
      if markerInfo.shown then
        markerInfo.iconGO:Show()
      else
        markerInfo.iconGO:Hide()
      end
    end
    if markerInfo.iconGO ~= nil then
      UI.SetIsClickable(markerInfo.iconGO)
    end
  end
end
function MapOn:GetRealmMarkerInfo()
  self:ClearIcons()
  self.realmMarkerInfo = {}
  if self.currRealmName == nil then
    return
  end
  local regionInfoTable = mapUtil.GetAllRegionInfoInRealm(self.currRealmName)
  for _, regionInfo in ipairs(regionInfoTable) do
    local regionMarkerInfoTable = Map.GetMarkersInfoTable(regionInfo.Id)
    for i = 1, #regionMarkerInfoTable do
      local markerInfo = regionMarkerInfoTable[i]
      local hasQuest, questName = questUtil.FindQuestForMarker(markerInfo.Id)
      if not hasQuest or game.QuestManager.GetQuestState(questName) ~= questConsts.QUEST_STATE_COMPLETE then
        markerInfo.regionId = regionInfo.Id
        self.realmMarkerInfo[#self.realmMarkerInfo + 1] = regionMarkerInfoTable[i]
      end
    end
  end
  self:UpdateFilterButtonMapping()
end
function MapOn:GetAlwaysOnMarkers()
  self:ClearMarkers(true)
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if Map.MarkerHasAnyFlag(markerInfo.Id, alwaysOnMarkerFlags) and mapUtil.MapMarkerInfoHasStates(markerInfo, markerStates) then
      markerInfo.shown = true
      tablex.FastInsert(self.alwaysOnMarkers, markerInfo, #self.alwaysOnMarkers + 1)
      tablex.FastInsert(self.markers, markerInfo, #self.markers + 1)
    end
  end
end
function MapOn:GetMarkers()
  self:ClearMarkers()
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if Map.MarkerHasAnyFlag(markerInfo.Id, self.markerIncludeFlags) and mapUtil.MapMarkerInfoHasStates(markerInfo, markerStates) then
      markerInfo.shown = true
      tablex.FastInsert(self.markers, markerInfo, #self.markers + 1)
    end
  end
end
function MapOn:ShouldShowPlayerMarker()
  local playerRealm = mapUtil.GetPlayerRealm()
  local showPlayerMarker =
    playerRealm == self.currRealmName and
    self.playerIconGO ~= nil and
    _G.CompletionistMapV100PlayerMarkerVisible ~= false
  local Hel_MapState = game.Level.GetVariable("Hel_MapState")
  local inTheLight = game.Level.GetVariable("CompletedCineNumber") == 240
  local onBoat = 2 <= Hel_MapState and Hel_MapState < 5 and playerRealm == mapConsts.REALM_HELHEIM
  local fastTraveling = Player.FindPlayer().CurrentLevelWadName == "Gbl000_FastTravel"
  if onBoat or fastTraveling or inTheLight then
    showPlayerMarker = false
  end
  return showPlayerMarker
end
function MapOn:SubmenuEnter(currState, realmName)
  currState.menu:Activate()
  self.completionistMapV100Menu = currState.menu
  util.GetUiObjByName("MapCursorInfo"):Hide()
  local prevRealmName = self.currRealmName
  self.currRealmName = realmName
  self:UpdateTempleRotation(realmName)
  self:UpdateRealmSummary(realmName)
  self:HideSummary()
  self:ShowMap(realmName)
  self:SetupCameraForMap(realmName)
  self:StartTimer("FogShowDelayTimer", 0.25, function()
    self:SetupVisibilityOfRegions(realmName)
  end)
  self:UpdateMapState()
  if self.isOpenedForFastTravel then
    self:GetRealmMarkerInfo()
    self:GetAlwaysOnMarkers()
    self.markerIncludeFlags = fastTravelMarkerFlags
  elseif prevRealmName ~= self.currRealmName then
    self:GetRealmMarkerInfo()
    self:GetAlwaysOnMarkers()
  end
  self:GetMarkers()
  self:UpdateIcons()
  self:UpdateMapMarkerHighlights()
  self:UpdateFilterUI()
  if self.playerIconGO ~= nil then
    Map.SetPlayerMapMarkerToPlayerMapTransform(self.playerIconGO, "facingJoint", "arrowJoint")
    CompletionistMapV100_LogMapCalibration(self)
  end
  local showPlayerMarker = self:ShouldShowPlayerMarker()
  if showPlayerMarker then
    self.playerIconGO:Show()
  else
    self.playerIconGO:Hide()
  end
  local selectMarker
  if self.markerIdHashToSelectOnOpen ~= nil then
    self.openedAtMarker = self.markerIdHashToSelectOnOpen
    self.markerIdHashToSelectOnOpen = nil
    for i = 1, #self.markers do
      local marker = self.markers[i]
      if marker.Id == self.openedAtMarker then
        selectMarker = marker
        local instant = true
        Camera.PointAtGO(marker.iconGO, instant)
        break
      end
    end
  elseif showPlayerMarker then
    local instant = true
    Camera.PointAtGO(self.playerIconGO, instant)
  elseif _G.CompletionistMapV100PlayerMarkerVisible == false and
      mapUtil.GetPlayerRealm() == self.currRealmName and
      self.playerIconGO ~= nil then
    local instant = true
    Camera.PointAtGO(self.playerIconGO, instant)
    print("[CompletionistMap v0.10.1] PLAYER_HIDDEN_CENTER" ..
      " centered=true realm=" .. tostring(self.currRealmName))
  elseif Camera.PointAt ~= nil then
    local instant = true
    Camera.PointAt(CALDERA_MAP_POSITION, instant)
  end
  self:UpdateFastTravelList(currState)
  if self.isOpenedForFastTravel and selectMarker ~= nil then
    self:SelectFastTravelButtonByMarkerInfo(currState, selectMarker)
  end
  CompletionistMapV100_CreateMapPin(self, currState)
  CompletionistMapV100_CreateNornirChestPins(self, currState)
  CompletionistMapV100_CreateNornirPins(self, currState)
  CompletionistMapV100_RefreshCustomPins(self)
  UI.WorldUIRender(map_camera.Name)
  currState.menu:ExecuteInstructions()
end
function MapOn:SubmenuExit(currState)
  CompletionistMapV100_DestroyNornirChestPins(self)
  CompletionistMapV100_DestroyNornirPins(self)
  CompletionistMapV100_DestroyMapPin(self)
  currState.menu:Deactivate(true)
  self:ClearMarkers(true)
  if self.playerIconGO ~= nil then
    self.playerIconGO:Hide()
  end
  if tweaks.tMapCamera then
    Camera.SetMapCamera()
  end
  self:HideAllMaps()
end
function MapOn:ConfirmFastTravel(currState)
  local fastTravelList = currState.menu:GetList("FastTravelList")
  local currFastTravelMarkerInfo = fastTravelList:GetSelectedItem()
  local isDiscoveredButLocked = currFastTravelMarkerInfo.State == tweaks.eTokenState.kDiscoveredButLocked
  if self.currMarkerID ~= nil and Map.MarkerHasAnyFlag(self.currMarkerID, fastTravelMarkerFlags) and self:IsPlayerAtMarker(currFastTravelMarkerInfo) == false and self.fastTravelCancelled == false and not isDiscoveredButLocked then
    self.fastTravelPointSelected = true
    util.CallScriptOnCurrentInteractObject("TriggerFastTravelPointSelected", currFastTravelMarkerInfo.Id)
    self:Menu_Options_ReleaseHandler(false)
  end
end
function MapOn:Menu_Back_ReleaseHandler()
  if self.isOpenedForFastTravel == true and self.fastTravelPointSelected == false then
    self.fastTravelCancelled = true
    util.CallScriptOnCurrentInteractObject("TriggerFastTravelCancel")
  end
  self:SendEventToUIFsm("globalMenu", "EVT_TURN_OFF_GLOBAL_MENU")
end
function MapOn:Menu_Square_ReleaseHandler()
  local currRootQuestID = questUtil.GetRootQuestID(self.currQuestID)

  if not questUtil.IsValidID(currRootQuestID) then
    _G.CompletionistMapV100PlayerMarkerVisible =
      not (_G.CompletionistMapV100PlayerMarkerVisible ~= false)

    local visible =
      _G.CompletionistMapV100PlayerMarkerVisible ~= false

    if self.playerIconGO ~= nil then
      if visible and self:ShouldShowPlayerMarker() then
        self.playerIconGO:Show()
      else
        self.playerIconGO:Hide()
      end
    end

    if self.completionistMapV100Menu ~= nil then
      local text =
        visible and
        "[SquareButton] Hide Kratos" or
        "[SquareButton] Show Kratos"

      self.completionistMapV100Menu:UpdateFooterButton(
        "GoToJournal",
        true,
        text
      )
      self.completionistMapV100Menu:UpdateFooterButtonText()
    end

    print("[CompletionistMap v0.10.1] PLAYER_MARKER_TOGGLE" ..
      " visible=" .. tostring(visible))
    Audio.PlaySound("SND_UX_Pause_Menu_Map_Region_Hover_Tick")
    return
  end  local currRootQuestID = questUtil.GetRootQuestID(self.currQuestID)
  if questUtil.IsValidID(currRootQuestID) then
    local goFlourish = util.GetUiObjByName("CursorInfo_Top")
    goFlourish:Show()
    local animRate = 1
    local animStartTime = 0
    local animEndTime = 1
    UI.Anim(goFlourish, consts.AS_Forward, "", animRate, animStartTime, animEndTime)
    self:SendEventToUIFsm("globalMenu", "EVT_GO_TO_QUEST", currRootQuestID)
    Audio.PlaySound("SND_UX_Pause_Menu_Map_Jump_To_Journal")
  end
end
function MapOn:Menu_Triangle_ReleaseHandler()
  self:SendEventToUIFsm("globalMenu", "EVT_OPEN_SETTINGS_MENU")
end
function MapOn:Menu_Options_ReleaseHandler()
  self:Menu_Back_ReleaseHandler()
end
function MapOn:FindNextMarker(direction)
  local startIndex = self.jumpToMarkerIndex
  local trackedMarker = false
  local cursorAtMarker = false
  repeat
    self.jumpToMarkerIndex = self.jumpToMarkerIndex + direction
    if self.jumpToMarkerIndex < 0 then
      self.jumpToMarkerIndex = #self.markers
    end
    if self.jumpToMarkerIndex > #self.markers then
      self.jumpToMarkerIndex = 0
    end
    trackedMarker = self.jumpToMarkerIndex == 0 or self:GetMapMarkerTrackingState(self.markers[self.jumpToMarkerIndex].Id) == questConsts.TRACKING_STATE_TRACKED
    cursorAtMarker = self.jumpToMarkerIndex == 0 and self.currMarkerPlayerIcon or self.jumpToMarkerIndex ~= 0 and self.currMarkerID ~= nil and self.markers[self.jumpToMarkerIndex].Id == self.currMarkerID
  until not (not trackedMarker or cursorAtMarker) or startIndex == self.jumpToMarkerIndex
  if self.jumpToMarkerIndex == 0 and not self:ShouldShowPlayerMarker() and mapUtil.GetPlayerRealm() == self.currRealmName and self.markers[1] ~= nil and self:GetMapMarkerTrackingState(self.markers[1].Id) == questConsts.TRACKING_STATE_TRACKED then
    self.jumpToMarkerIndex = 1
  end
end
function MapOn:JumpToMarker()
  if self.jumpToMarkerIndex == 0 and self:ShouldShowPlayerMarker() then
    Camera.PointAtGO(self.playerIconGO)
  elseif self.markers[self.jumpToMarkerIndex] ~= nil then
    Camera.PointAtGO(self.markers[self.jumpToMarkerIndex].iconGO)
  end
end
function MapOn:EVT_R2_Release()
  if self.isOpenedForFastTravel or not tutorialUtil.AreEventsAllowed({
    "EVT_R2_Release"
  }) then
    return true
  end
  self:Menu_Next_Filter(1)
end
function MapOn:EVT_L2_Release()
  if self.isOpenedForFastTravel or not tutorialUtil.AreEventsAllowed({
    "EVT_L2_Release"
  }) then
    return true
  end
  self:Menu_Next_Filter(-1)
end
function MapOn:EVT_R3_Release()
  if self.isOpenedForFastTravel or not tutorialUtil.AreEventsAllowed({
    "EVT_R3_Release"
  }) then
    return true
  end
  if #self.markers == 0 and self.currMarkerPlayerIcon then
    return
  end
  self:FindNextMarker(1)
  self:JumpToMarker()
  Audio.PlaySound("SND_UX_Pause_Menu_Map_MoveTo_Active_Marker_LP")
  self.playingMoveToActiveMarker = true
end
function MapOn:EVT_MAPCURSOR_ARRIVED_AT_TARGET()
  if self.playingMoveToActiveMarker then
    Audio.StopSound("SND_UX_Pause_Menu_Map_MoveTo_Active_Marker_LP")
    self.playingMoveToActiveMarker = false
  end
end
function MapOn:MouseClickHandler(currState)
  for key, button in ipairs(self.goFilterButtons) do
    if UI.GetEventSenderGameObject() == button then
      local first = self.completionistMapV100FilterWindowFirst or 1
      local desired = first + key - 1
      if desired <= #self.filterButtonMapping then
        self:Menu_Next_Filter(desired - self.filterIndex)
      end
      return
    end
  end
  for i = 1, #self.realmMarkerInfo do
    local markerInfo = self.realmMarkerInfo[i]
    if markerInfo.iconGO ~= nil and UI.GetEventSenderGameObject() == markerInfo.iconGO then
      if self.isOpenedForFastTravel and Map.MarkerHasAnyFlag(markerInfo.Id, fastTravelMarkerFlags) then
        local fastTravelList = currState.menu:GetList("FastTravelList")
        if markerInfo == fastTravelList:GetSelectedItem() then
          Camera.PointAtGO(markerInfo.iconGO)
        else
          self:SelectFastTravelButtonByMarkerInfo(currState, markerInfo)
        end
        self.clickedMarkerInfo = nil
        self.clickedPlayer = false
      else
        Camera.PointAtGO(markerInfo.iconGO)
        self.clickedMarkerInfo = markerInfo
        self.clickedPlayer = false
      end
    end
  end
  if UI.GetEventSenderGameObject() == self.playerIconGO then
    Camera.PointAtGO(self.playerIconGO)
    if self.isOpenedForFastTravel then
      self.clickedMarkerInfo = nil
      self.clickedPlayer = true
    end
  end
end
function MapOn:Menu_Next_Filter(direction)
  if self.isOpenedForFastTravel then return end
  self.filterIndex =
    (self.filterIndex + direction - 1) % #self.filterButtonMapping + 1

  local logical = self.filterButtonMapping[self.filterIndex]
  if logical ~= nil and logical > 0 then
    self.markerIncludeFlags = markerFilters[logical].markerIncludeFlags
    self:GetAlwaysOnMarkers()
    self:GetMarkers()
  else
    self:ClearMarkers(true)
  end

  self:UpdateIcons()
  CompletionistMapV100_RefreshCustomPins(self)
  self:UpdateFilterUI()
  self.jumpToMarkerIndex = 0
  self:UpdateMapMarkerHighlights()
  Audio.PlaySound("SND_UX_Pause_Menu_Map_Filters_Tick")
  print("[CompletionistMap v0.10.1] FILTER_CHANGE" ..
    " logical=" .. tostring(logical) ..
    " index=" .. tostring(self.filterIndex))
end

function MapOn:UpdateFilterButtonMapping()
  self.filterButtonMapping = {1}
  self.filterIndex = 1
  self.markerIncludeFlags = markerFilters[1].markerIncludeFlags

  for filterIndex = 2, #markerFilters do
    local markerIncludeFlags = markerFilters[filterIndex].markerIncludeFlags
    for i = 1, #self.realmMarkerInfo do
      local markerInfo = self.realmMarkerInfo[i]
      if Map.MarkerHasAnyFlag(markerInfo.Id, markerIncludeFlags) and
          mapUtil.MapMarkerInfoHasStates(markerInfo, markerStates) then
        self.filterButtonMapping[#self.filterButtonMapping + 1] = filterIndex
        break
      end
    end
  end

  if self.currRealmName == "Midgard" then
    self.filterButtonMapping[#self.filterButtonMapping + 1] = COMPLETIONIST_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = RAVEN_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = NORNIR_CHEST_FILTER
    self.filterButtonMapping[#self.filterButtonMapping + 1] = NORNIR_PUZZLE_FILTER

    print("[CompletionistMap v0.10.1] FILTER_MAPPING" ..
      " total=" .. tostring(#self.filterButtonMapping) ..
      " completionist=true")
  end

  self:UpdateFilterUI()
end

function MapOn:UpdateFilterUI()
  local logical = self.filterButtonMapping[self.filterIndex] or 1
  local label = completionistFilterLabels[logical]
  if label ~= nil then
    UI.SetText(self.thFilterLabel, label)
  else
    UI.SetText(self.thFilterLabel, util.GetLAMSMsg(markerFilters[logical].name))
  end

  local total = #self.filterButtonMapping
  local visible = math.min(#self.goFilterButtons, total)
  local first = 1
  if total > visible then
    first = self.filterIndex - math.floor(visible / 2)
    if first < 1 then first = 1 end
    local maxFirst = total - visible + 1
    if first > maxFirst then first = maxFirst end
  end
  self.completionistMapV100FilterWindowFirst = first

  local posOffset = (#self.goFilterButtons - visible) * 0.2
  for slot = 1, #self.goFilterButtons do
    local button = self.goFilterButtons[slot]
    if slot <= visible then
      local logicalIndex = first + slot - 1
      local pos = engine.Vector.New(
        self.goFilterButtonPositions[slot].x + posOffset,
        self.goFilterButtonPositions[slot].y,
        self.goFilterButtonPositions[slot].z
      )
      button:SetWorldPosition(pos)
      button:Show()
      local selected = logicalIndex == self.filterIndex
      UI.Anim(
        button,
        consts.AS_Forward,
        "",
        consts.DEFAULT_BUTTON_ANIM_RATE,
        selected and 0 or 0.5,
        selected and 0.5 or 1
      )
    else
      UI.Anim(button, consts.AS_Reset, "", 0, 0)
      button:Hide()
    end
  end
end
function MapOn:ShowOnCompass(currState)
  if self.completionistMapV100NornirChestSelected ~= nil then
    CompletionistMapV100_ClearStockCompass(self, "custom_nornir_chest")
    local pin = self.completionistMapV100NornirChestSelected
    if not CompletionistMapV100_IsNornirChestRemaining(pin) then
      self.completionistMapV100NornirChestSelected = nil
      return
    end
    local target = _G.CompletionistMapV100Target
    local sameTarget = target ~= nil and
      target.type == "NornirChest" and
      target.registryKey == pin.registryKey
    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "NornirChest"
      target.realm = "Midgard"
      target.registryKey = pin.registryKey
      target.keyIndex = nil
      target.regionQuest = nil
      target.x = pin.worldX
      target.y = pin.worldY
      target.z = pin.worldZ
      target.mapX = pin.mapX
      target.mapZ = pin.mapZ
      target.collected = false
      target.active = true
      _G.CompletionistMapV100TargetCollectedNornirLogged = false
      _G.CompletionistMapV100NornirTargetGeneration =
        (_G.CompletionistMapV100NornirTargetGeneration or 0) + 1
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end
    CompletionistMapV100_NornirChestReticle(self, currState, pin)
    print("[CompletionistMap v0.10.1] NORNIR_CHEST_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " registryKey=" .. tostring(pin.registryKey) ..
      " x=" .. tostring(pin.worldX) ..
      " y=" .. tostring(pin.worldY) ..
      " z=" .. tostring(pin.worldZ))
    return
  end

  if self.completionistMapV100NornirSelected ~= nil then
    CompletionistMapV100_ClearStockCompass(self, "custom_nornir_puzzle")
    local pin = self.completionistMapV100NornirSelected

    if not CompletionistMapV100_IsNornirKeyRemaining(pin) then
      self.completionistMapV100NornirSelected = nil
      return
    end

    local target = _G.CompletionistMapV100Target
    local sameTarget =
      target ~= nil and
      target.type == "NornirPuzzle" and
      target.registryKey == pin.registryKey and
      target.keyIndex == pin.keyIndex

    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "NornirPuzzle"
      target.realm = "Midgard"
      target.registryKey = pin.registryKey
      target.keyIndex = pin.keyIndex
      target.keyType = pin.keyType
      target.regionQuest = nil
      target.x = pin.worldX
      target.y = pin.worldY
      target.z = pin.worldZ
      target.mapX = pin.mapX
      target.mapZ = pin.mapZ
      target.collected = false
      target.active = true
      _G.CompletionistMapV100NornirTargetGeneration =
        (_G.CompletionistMapV100NornirTargetGeneration or 0) + 1
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end

    CompletionistMapV100_NornirReticle(self, currState, pin)

    print("[CompletionistMap v0.10.1] NORNIR_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " registryKey=" .. tostring(pin.registryKey) ..
      " index=" .. tostring(pin.keyIndex) ..
      " x=" .. tostring(pin.worldX) ..
      " y=" .. tostring(pin.worldY) ..
      " z=" .. tostring(pin.worldZ))
    return
  end

  if self.completionistMapV100Selected then
    CompletionistMapV100_ClearStockCompass(self, "custom_raven")
    local target = _G.CompletionistMapV100Target

    if CompletionistMapV100_IsRavenCollected() then
      if target ~= nil and target.type == "Raven" then
        target.active = false
        target.collected = true
      end
      self.completionistMapV100Selected = false
      print("[CompletionistMap v0.10.1] CUSTOM_COMPASS refused=raven_collected")
      return
    end

    local sameTarget = target ~= nil and target.type == "Raven"

    if sameTarget and target.active then
      target.active = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
    else
      target.type = "Raven"
      target.realm = "Midgard"
      target.regionQuest = "RegionSummary_VF_Raven_Parent"
      target.registryKey = nil
      target.keyIndex = nil
      target.x = COMPLETIONIST_RAVEN_WORLD_X
      target.y = COMPLETIONIST_RAVEN_WORLD_Y
      target.z = COMPLETIONIST_RAVEN_WORLD_Z
      target.mapX = COMPLETIONIST_RAVEN_MAP_X
      target.mapZ = COMPLETIONIST_RAVEN_MAP_Z
      target.collected = false
      target.active = true
      _G.CompletionistMapV100TargetCollectedNornirLogged = false
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    end

    CompletionistMapV100_ShowReticle(self, currState)

    print("[CompletionistMap v0.10.1] CUSTOM_COMPASS" ..
      " active=" .. tostring(target.active) ..
      " mode=hud_native_visual_proof" ..
      " x=" .. tostring(target.x) ..
      " y=" .. tostring(target.y) ..
      " z=" .. tostring(target.z))
    return
  end
  local completionistTarget = _G.CompletionistMapV100Target
  if completionistTarget ~= nil and
      completionistTarget.active == true and
      self.currMarkerID ~= nil then
    completionistTarget.active = false
    print("[CompletionistMap v0.10.1] CUSTOM_COMPASS_CLEAR" ..
      " reason=stock_marker_selected" ..
      " type=" .. tostring(completionistTarget.type))
  end
  local updatePrompt = false
  if self.currMarkerID ~= nil then
    if not Map.MarkerHasAnyFlag(self.currMarkerID, enabledShowOnCompassMarkerFlags) then
      return
    end
    updatePrompt = true
    if self.currMarkerID == self.currShownMarkerID then
      game.Compass.HideMarker(self.currShownMarkerID)
      Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
      self.currShownMarkerID = nil
    else
      if self.currShownMarkerID ~= nil then
        game.Compass.HideMarker(self.currShownMarkerID)
      end
      local markerType
      for i = 1, #enabledShowOnCompassMarkerFlags do
        local enabledMarkerFlag = enabledShowOnCompassMarkerFlags[i]
        if Map.MarkerHasFlag(self.currMarkerID, {enabledMarkerFlag}) then
          markerType = enabledMarkerFlag
          break
        end
      end
      assert(markerType ~= nil, "unable to find ShowOnCompass marker type")
      game.Compass.ShowMarker(self.currMarkerID, markerType)
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
      self.currShownMarkerID = self.currMarkerID
    end
  elseif self.currShownMarkerID ~= nil then
    updatePrompt = true
    game.Compass.HideMarker(self.currShownMarkerID)
    self.currShownMarkerID = nil
  end
  if updatePrompt then
    local currMenu = currState.menu
    local showShowOnCompass, text = self:GetShowOnCompassPrompt(currMenu)
    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    goMapCursorText:Show()
    local goCursorInfo_Top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
    local thPrompt = util.GetTextHandle(goCursorInfo_Top, "CursorAction_Text")
    UI.SetTextIsClickable(thPrompt)
    UI.SetText(thPrompt, showShowOnCompass and text or "")
    self:UpdateMapMarkerHighlights()
    currMenu:UpdateFooterButton("ShowOnCompass", showShowOnCompass, text)
    currMenu:UpdateFooterButtonText()
  end
end
function MapOn:EVT_TURN_OFF_MAP_MENU()
  self:Goto("MapOff")
end
function Midgard:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Midgard:Enter()
  self.mapOn:SubmenuEnter(self, "Midgard")
end
function Midgard:Exit()
  self.mapOn:SubmenuExit(self)
end
function Midgard:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Midgard")
end
function Midgard:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Alfheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Alfheim:Enter()
  self.mapOn:SubmenuEnter(self, "Alfheim")
end
function Alfheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Alfheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Alfheim")
end
function Alfheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Helheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Helheim:Enter()
  self.mapOn:SubmenuEnter(self, "Helheim")
end
function Helheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Helheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Helheim")
end
function Helheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Jotunheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Jotunheim:Enter()
  self.mapOn:SubmenuEnter(self, "Jotunheim")
end
function Jotunheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Jotunheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Jotunheim")
end
function Jotunheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Niflheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Niflheim:Enter()
  self.mapOn:SubmenuEnter(self, "Niflheim")
end
function Niflheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Niflheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Niflheim")
end
function Niflheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Muspelheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Muspelheim:Enter()
  self.mapOn:SubmenuEnter(self, "Muspelheim")
end
function Muspelheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Muspelheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Muspelheim")
end
function Muspelheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Svartalheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Svartalheim:Enter()
  self.mapOn:SubmenuEnter(self, "Svartalheim")
end
function Svartalheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Svartalheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Svartalheim")
end
function Svartalheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Vanaheim:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Vanaheim:Enter()
  self.mapOn:SubmenuEnter(self, "Vanaheim")
end
function Vanaheim:Exit()
  self.mapOn:SubmenuExit(self)
end
function Vanaheim:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Vanaheim")
end
function Vanaheim:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function Asgard:Setup()
  self.mapOn = self:GetState("MapOn")
  self.mapOn:SubmenuSetup(self)
end
function Asgard:Enter()
  self.mapOn:SubmenuEnter(self, "Asgard")
end
function Asgard:Exit()
  self.mapOn:SubmenuExit(self)
end
function Asgard:EVT_HandleMapCollisionChangeHook(collisionGameObjectTable)
  self.mapOn:MapCollisionChangeHandler(self, collisionGameObjectTable, "Asgard")
end
function Asgard:EVT_MOUSE_CLICKED()
  self.mapOn:MouseClickHandler(self)
end
function MapMenu:OnSaveCheckpoint(tab)
end
function MapMenu:OnRestoreCheckpoint(tab)
end



-- BEGIN COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF
--
-- Field proof for the corrected, grown r_ui.wad candidate. The authored Raven
-- marker points directly at goMapIconCompletionistRaven. No Dock map proxy is
-- created. The visual payload still carries cloned stock Dock pixels at this
-- gate on purpose; custom Raven texpack artwork is a separate later variable.
do
  local prefix = "[CompletionistMap v0.10.4-raven-registered-runtime] "
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
    if CompletionistMapV100_IsRavenCollected() then
      log("REGISTERED_RESULT", "active=false reason=raven_collected dockProxyUsed=false")
      return
    end

    local infoOK, info = pcall(function()
      return game.Map.GetMarkerInfo(candidate)
    end)
    if not infoOK or info == nil then
      log("REGISTERED_RESULT",
        "active=false reason=marker_info_failed dockProxyUsed=false error=" .. tostring(info))
      return
    end

    local markerId = safeField(info, "Id") or safeField(info, "id")
    local markerIcon = safeField(info, "Icon") or safeField(info, "icon") or
      safeField(info, "IconName") or safeField(info, "iconName")
    local markerState = safeField(info, "State") or safeField(info, "state")
    local regionId, regionSource = getRegionId(info, markerId)

    log("REGISTERED_PREFLIGHT",
      "candidate=" .. candidate ..
      " id=" .. tostring(markerId) ..
      " authoredIcon=" .. tostring(markerIcon) ..
      " state=" .. tostring(markerState) ..
      " region=" .. tostring(regionId) ..
      " regionType=" .. tostring(type(regionId)) ..
      " regionSource=" .. tostring(regionSource) ..
      " expectedMapResource=" .. expectedMapResource ..
      " compassType=DockPoint" ..
      " texpackLoaded=false" ..
      " dockProxyUsed=false")

    if markerId == nil or regionId == nil then
      log("REGISTERED_RESULT", "active=false reason=id_or_region_unresolved dockProxyUsed=false")
      return
    end

    local createOK, newGO = pcall(function()
      return Map.CreateMarkerIcon(markerId, regionId, "")
    end)
    if not createOK or newGO == nil then
      log("REGISTERED_RESULT",
        "active=false reason=CreateMarkerIcon_failed regionSource=" .. tostring(regionSource) ..
        " dockProxyUsed=false error=" .. tostring(newGO))
      return
    end

    local clickableOK, clickableErr = pcall(function() UI.SetIsClickable(newGO) end)
    local showOK, showErr = pcall(function() newGO:Show() end)
    if not showOK then
      pcall(function() Map.RecycleIcon(newGO) end)
      log("REGISTERED_RESULT",
        "active=false reason=show_failed dockProxyUsed=false error=" .. tostring(showErr))
      return
    end

    self.completionistMapV100MapIconGO = newGO
    self.completionistMapV100MapIconFrames = 0
    CompletionistMapV100_LogIconCapabilities(newGO, "raven_registered_class_runtime")

    local goName = safeName(newGO)
    local posOK, pos = pcall(function() return newGO:GetWorldPosition() end)
    local looksLikeDedicatedName = string.find(string.lower(goName), "completionistraven", 1, true) ~= nil
    local isDockGO = string.lower(goName) == "mapicondock"

    log("REGISTERED_RESULT",
      "active=true" ..
      " candidate=" .. candidate ..
      " resourceExpected=" .. expectedMapResource ..
      " goName=" .. goName ..
      " dedicatedNameObserved=" .. tostring(looksLikeDedicatedName) ..
      " dockGOObserved=" .. tostring(isDockGO) ..
      " clickableOK=" .. tostring(clickableOK) ..
      " clickableError=" .. tostring(clickableErr) ..
      " nativePlacement=" .. tostring(posOK and pos ~= nil) ..
      " position=" .. (posOK and pos ~= nil and
        ("x=" .. tostring(pos.x) .. ",y=" .. tostring(pos.y) .. ",z=" .. tostring(pos.z)) or "<unavailable>") ..
      " texpackLoaded=false" ..
      " dockProxyUsed=false")
  end

  log("REGISTERED_API",
    "installed=true candidate=" .. candidate ..
    " mapResource=" .. expectedMapResource ..
    " compassType=DockPoint" ..
    " texpackLoaded=false" ..
    " dockProxyUsed=false" ..
    " callsOnLoad=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF
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
  local markerType = "CompletionistRaven"
  local originalPrompt = MapOn.GetShowOnCompassPrompt
  local originalShow = MapOn.ShowOnCompass
  local originalUpdate = MapOn.Update

  local verifyFrames = 0
  local verifyBucket = -1
  local promptIntent = nil
  local lastManagerShown = nil

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

    -- Keep the cursor-card copy and footer copy in sync. The native compass
    -- manager commits ShowMarker/HideMarker asynchronously, so GetShowOnCompassPrompt
    -- also honours promptIntent until the manager reports the requested state.
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
        if show then
          goCursorInfoTop:Show()
        else
          goCursorInfoTop:Hide()
        end
      end
    end

    currState.menu:UpdateFooterButton("ShowOnCompass", show, text)
    currState.menu:UpdateFooterButtonText()

    log("NATIVE_RAVEN_PROMPT_REFRESH",
      "cursor=true footer=true visible=" .. tostring(show) ..
      " intent=" .. tostring(promptIntent) ..
      " text=" .. tostring(text))
  end

  local function refreshPromptFromLiveMap(self)
    if self ~= nil and self.menu ~= nil and ravenSelected(self) then
      updatePrompt(self, {menu = self.menu})
    end
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

      -- Show/Hide is asynchronous in the native compass manager. Keep the UI
      -- on the user's requested state until shownState catches up, otherwise
      -- stock reticle refreshes can overwrite the prompt with the old text.
      if promptIntent == "tracked" then
        lamsId = lamsConsts.RemoveFromCompass
      elseif promptIntent == "untracked" then
        if queryOK and #others > 0 then
          lamsId = lamsConsts.ReplaceInCompass
        else
          lamsId = lamsConsts.AddToCompass
        end
      elseif queryOK and shown then
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
      promptIntent = nil
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
        promptIntent = "untracked"
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
      promptIntent = nil
      log("NATIVE_RAVEN_RESULT", "active=false reason=lua_wrapper_failed")
      return
    end

    promptIntent = "tracked"
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
    if queryOK then
      local settledIntent = false
      if promptIntent == "tracked" and shown then
        promptIntent = nil
        settledIntent = true
        log("NATIVE_RAVEN_PROMPT_SETTLED", "state=tracked")
      elseif promptIntent == "untracked" and not shown then
        promptIntent = nil
        settledIntent = true
        log("NATIVE_RAVEN_PROMPT_SETTLED", "state=untracked")
      end

      if ravenSelected(self) and
          (settledIntent or lastManagerShown == nil or shown ~= lastManagerShown) then
        refreshPromptFromLiveMap(self)
      end
      lastManagerShown = shown
    end

    if queryOK and shown then
      _G.CompletionistMapV103NativeRavenTracked = true
      suppressLegacyRavenHud()

      if CompletionistMapV100_IsRavenCollected() then
        promptIntent = nil
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
    " calls_on_load=false legacy_r3l3_for_raven=false prompt_async_guard=true")
end
-- END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE
-- BEGIN COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL
-- Final Raven-only manager bridge for v0.10.4 testing.
--
-- Why this wrapper owns Raven-origin actions:
-- the older Raven bridge's shownState() queries enabledShowOnCompassMarkerFlags,
-- which contains stock classes but not CompletionistRaven. Once the Raven uses its
-- custom class, delegating Remove from Compass to that older bridge can re-show the
-- Raven instead of hiding it. This layer uses FindMarkersByIconClass({CompletionistRaven})
-- for the Raven and the stock class list for ordinary targets.
do
  local prefix = "[CompletionistMap v0.10.4-single-active-v3] "
  local ravenCandidate = "Completionist_V103_Veithurgard_Raven_01"
  local ravenClass = "CompletionistRaven"
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousPrompt = MapOn.GetShowOnCompassPrompt

  local stockReplacePending = false
  local ravenIntent = nil -- "tracked" / "untracked" while native manager settles
  local retryFrames = 0
  local retryBucket = -1

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function ravenSelected(self)
    return self ~= nil and self.completionistMapV100Selected == true
  end

  local function candidateInfo()
    local ok, info = pcall(function()
      return game.Map.GetMarkerInfo(ravenCandidate)
    end)
    if not ok then
      return nil, tostring(info)
    end
    if info == nil then
      return nil, "candidate_missing"
    end
    return info, nil
  end

  local function candidateIdString()
    local info = candidateInfo()
    return info ~= nil and tostring(info.Id) or nil
  end

  local function ravenShown()
    local candidateId = candidateIdString()
    if candidateId == nil then
      return false, false, "candidate_lookup_failed"
    end

    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then
      return false, false, tostring(ids)
    end

    for _, id in ipairs(ids or {}) do
      if tostring(id) == candidateId then
        return true, true, nil
      end
    end
    return false, true, nil
  end

  local function stockTargets()
    local ravenId = candidateIdString()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then
      return {}, false, tostring(ids)
    end

    local out = {}
    for _, id in ipairs(ids or {}) do
      if ravenId == nil or tostring(id) ~= ravenId then
        out[#out + 1] = id
      end
    end
    return out, true, nil
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  local function hideRaven(reason)
    local ok, err = pcall(function()
      game.Compass.HideMarker(ravenCandidate)
    end)
    log("HIDE_RAVEN",
      "reason=" .. tostring(reason) ..
      " ok=" .. tostring(ok) ..
      " error=" .. tostring(err))
    return ok
  end

  local function hideStockTargets(reason)
    local ids, ok, err = stockTargets()
    if not ok then
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " queryOK=false error=" .. tostring(err))
      return false, 0
    end

    for _, id in ipairs(ids) do
      local hideOK, hideErr = pcall(function()
        game.Compass.HideMarker(id)
      end)
      log("HIDE_STOCK",
        "reason=" .. tostring(reason) ..
        " id=" .. tostring(id) ..
        " ok=" .. tostring(hideOK) ..
        " error=" .. tostring(hideErr))
    end
    return true, #ids
  end

  local function suppressLegacyRavenHud()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_R3L3_DISABLED", "reason=native_custom_raven_tracking")
    end
  end

  local function refreshRavenPrompt(self)
    if self == nil or self.menu == nil or not ravenSelected(self) then return end
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
    log("PROMPT_REFRESH",
      "visible=" .. tostring(show) ..
      " intent=" .. tostring(ravenIntent) ..
      " text=" .. tostring(text))
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    local show, previousText = previousPrompt(self, currMenu)
    if not ravenSelected(self) or not show then
      return show, previousText
    end

    -- During an asynchronous user action, reflect the requested state immediately.
    if ravenIntent == "tracked" then
      return true, actionText(lamsConsts.RemoveFromCompass)
    elseif ravenIntent == "untracked" then
      local others, stockOK = stockTargets()
      if stockOK and #others > 0 then
        return true, actionText(lamsConsts.ReplaceInCompass)
      end
      return true, actionText(lamsConsts.AddToCompass)
    end

    local shown, ravenOK, ravenErr = ravenShown()
    if not ravenOK then
      log("PROMPT_LIVE_QUERY", "ravenQueryOK=false error=" .. tostring(ravenErr) .. " fallback=previous")
      return show, previousText
    end
    if shown then
      return true, actionText(lamsConsts.RemoveFromCompass)
    end

    local others, stockOK, stockErr = stockTargets()
    if not stockOK then
      log("PROMPT_LIVE_QUERY", "stockQueryOK=false error=" .. tostring(stockErr) .. " fallback=previous")
      return show, previousText
    end
    if #others > 0 then
      return true, actionText(lamsConsts.ReplaceInCompass)
    end
    return true, actionText(lamsConsts.AddToCompass)
  end

  function MapOn:ShowOnCompass(currState)
    if not ravenSelected(self) then
      local shown, queryOK, queryErr = ravenShown()
      local trackedHint = _G.CompletionistMapV103NativeRavenTracked == true

      if shown or trackedHint then
        stockReplacePending = true
        ravenIntent = "untracked"
        retryFrames = 0
        retryBucket = -1
        log("STOCK_REPLACE_BEGIN",
          "ravenShown=" .. tostring(shown) ..
          " trackedHint=" .. tostring(trackedHint) ..
          " queryOK=" .. tostring(queryOK) ..
          " queryError=" .. tostring(queryErr))
        hideRaven("stock_marker_selected")
      else
        stockReplacePending = false
      end

      -- Stock-origin actions stay game-owned.
      return previousShow(self, currState)
    end

    stockReplacePending = false
    retryFrames = 0
    retryBucket = -1

    local info, infoErr = candidateInfo()
    if info == nil then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=candidate_missing error=" .. tostring(infoErr))
      return
    end

    local shown, queryOK, queryErr = ravenShown()
    if not queryOK then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=custom_class_query_failed error=" .. tostring(queryErr))
      return
    end

    if shown then
      if hideRaven("user_remove") then
        ravenIntent = "untracked"
        self.currShownMarkerID = nil
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshRavenPrompt(self)
        log("RAVEN_REMOVE", "request_queued=true")
      end
      return
    end

    local stockOK, stockCount = hideStockTargets("raven_replace")
    if not stockOK then
      ravenIntent = nil
      log("RAVEN_ACTION", "refused=stock_target_query_failed")
      return
    end

    suppressLegacyRavenHud()
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(ravenCandidate, ravenClass)
    end)
    log("RAVEN_SHOW",
      "ok=" .. tostring(showOK) ..
      " error=" .. tostring(showErr) ..
      " replacedStockCount=" .. tostring(stockCount))

    if not showOK then
      ravenIntent = nil
      return
    end

    ravenIntent = "tracked"
    self.currShownMarkerID = info.Id
    _G.CompletionistMapV103NativeRavenTracked = true
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshRavenPrompt(self)
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)

    local shown, ravenOK, ravenErr = ravenShown()
    if ravenOK then
      _G.CompletionistMapV103NativeRavenTracked = shown
      if shown then suppressLegacyRavenHud() end

      if stockReplacePending then
        if not shown then
          stockReplacePending = false
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("STOCK_REPLACE_SETTLED", "ravenActive=false")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideRaven("stock_replace_async_retry")
          end
        end
      elseif ravenIntent == "untracked" then
        if not shown then
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("RAVEN_REMOVE_SETTLED", "ravenActive=false")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideRaven("raven_remove_async_retry")
          end
        end
      elseif ravenIntent == "tracked" then
        local others, stockOK = stockTargets()
        if shown and stockOK and #others == 0 then
          ravenIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("RAVEN_SHOW_SETTLED", "ravenActive=true stockTargets=0")
          refreshRavenPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if stockOK and #others > 0 and (retryFrames == 1 or bucket ~= retryBucket) then
            retryBucket = bucket
            hideStockTargets("raven_replace_async_retry")
          end
        end
      end
    elseif stockReplacePending or ravenIntent ~= nil then
      retryFrames = retryFrames + 1
      if retryFrames == 1 or retryFrames % 60 == 0 then
        log("VERIFY", "ravenQueryOK=false error=" .. tostring(ravenErr) .. " frame=" .. tostring(retryFrames))
      end
    end

    return result
  end

  _G.CompletionistMapV104SingleActiveCompass = true
  _G.CompletionistMapV104SingleActivePromptLiveSync = true
  _G.CompletionistMapV104RavenActionsUseCustomClassManager = true
  log("API",
    "installed=true ravenClass=" .. ravenClass ..
    " invariant=single_active_compass_target raven_actions=custom_class_manager prompt=live_manager")
end
-- END COMPLETIONIST V0.10.4 SINGLE ACTIVE COMPASS CONTROL

-- BEGIN COMPLETIONIST SHARED LOADER TWIN PROBE
-- Same resource, new marker UID. No token state or compass writes.
do
  local twinName = "Completionist_V104_Veithurgard_Raven_Twin_01"
  local createRaven = CompletionistMapV100_CreateMapPin
  local prefix = "[CompletionistMap shared-loader-twin] "

  local function log(text)
    print(prefix .. text)
  end

  local function clearTwin(self)
    local go = self.completionistSharedLoaderTwinGO
    if go ~= nil then
      local ok, err = pcall(function() Map.RecycleIcon(go) end)
      if not ok then
        log("CLEANUP_FAILED error=" .. tostring(err))
        return false
      end
      if self.mapIconCollision == go then self.mapIconCollision = nil end
      self.completionistSharedLoaderTwinGO = nil
      local selected = self.completionistMapV104SelectedRavenIdentity
      if selected ~= nil and selected.Name == twinName then
        self.completionistMapV104SelectedRavenIdentity = nil
      end
      log("RECYCLED twin=true")
    end
    return true
  end

  -- Map view owns Twin. Raven completion owns only real pin.
  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    assert(type(previous) == "function", "Missing map lifecycle method: " .. method)
    MapOn[method] = function(self, ...)
      clearTwin(self)
      return previous(self, ...)
    end
  end

  CompletionistMapV100_CreateMapPin = function(self, currState)
    local result = createRaven(self, currState)
    if self.currRealmName ~= "Midgard" then return result end
    if self.completionistSharedLoaderTwinGO ~= nil then
      log("SKIP reason=prior_twin_not_recycled")
      return result
    end

    -- The Twin is a separate map marker instance that only shares the Raven visual
    -- resource. Its lifetime must not depend on a live production Raven UI object.
    local original = self.completionistMapV100MapIconGO
    local originalPresent = original ~= nil

    local ok, err = pcall(function()
      local info = Map.GetMarkerInfo(twinName)
      if info == nil or info.Id == nil then
        log("LOOKUP found=false")
        return
      end
      local found, region = Map.FindRegionFromMarker(info.Id)
      log("LOOKUP found=true uid=" .. tostring(info.Id) ..
          " state=" .. tostring(info.State) .. " regionFound=" .. tostring(found) ..
          " region=" .. tostring(region) .. " originalPresent=" .. tostring(originalPresent))
      if found ~= true or region == nil then return end
      local go = Map.CreateMarkerIcon(info.Id, region, "")
      if go == nil then
        log("CREATE success=false reason=nil_object originalPresent=" .. tostring(originalPresent))
        return
      end
      if originalPresent and go == original then
        log("CREATE success=false reason=original_object_reused originalPresent=true")
        return
      end
      self.completionistSharedLoaderTwinGO = go
      go:Show()

      if originalPresent then
        local a, z = original:GetWorldPosition(), go:GetWorldPosition()
        local dx, dy, dz = z.x-a.x, z.y-a.y, z.z-a.z
        log("CREATE success=true distinctObjects=true sharedLoader=goMapIconCompletionistRaven" ..
            " uid=" .. tostring(info.Id) .. " goName=" .. tostring(go:GetName()) ..
            " originalPresent=true originalGO=" .. tostring(original) .. " twinGO=" .. tostring(go) ..
            " originalPos=" .. tostring(a.x) .. "," .. tostring(a.y) .. "," .. tostring(a.z) ..
            " twinPos=" .. tostring(z.x) .. "," .. tostring(z.y) .. "," .. tostring(z.z) ..
            " mapSpaceDistance=" .. tostring(math.sqrt(dx*dx+dy*dy+dz*dz)) ..
            " stateWritten=false compassWritten=false")
      else
        local z = go:GetWorldPosition()
        log("CREATE success=true distinctObjects=not_applicable sharedLoader=goMapIconCompletionistRaven" ..
            " uid=" .. tostring(info.Id) .. " goName=" .. tostring(go:GetName()) ..
            " originalPresent=false twinGO=" .. tostring(go) ..
            " twinPos=" .. tostring(z.x) .. "," .. tostring(z.y) .. "," .. tostring(z.z) ..
            " stateWritten=false compassWritten=false")
      end
    end)
    if not ok then
      log("CREATE success=false error=" .. tostring(err) .. " originalPresent=" .. tostring(originalPresent))
      clearTwin(self)
    end
    return result
  end
  log("API installed=true resource=goMapIconCompletionistRaven expectedPoolCapacity=2 independentTwinLifetime=true")
end
-- END COMPLETIONIST SHARED LOADER TWIN PROBE

-- BEGIN COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING V3.3
-- Capture exact custom map identity at collision dispatch, then bind it to the
-- compass action only when the matching real/Twin prompt is offered.
-- Keep armed identity through human delay and incidental collision callbacks.
-- Keep stock actions owned by the proven single-active-v3 controller.
do
  local prefix = "[CompletionistMap v0.10.4-uid-lifecycle-v3.3] "
  local ravenName = "Completionist_V103_Veithurgard_Raven_01"
  local twinName = "Completionist_V104_Veithurgard_Raven_Twin_01"
  local ravenClass = "CompletionistRaven"
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousCollision = MapOn.MapCollisionChangeHandler
  local compassPending = nil
  local promptOverride = nil
  local lastMapOnSelf = nil
  local knownRavenIdentity = nil
  local completionObserved = nil
  local selectionGeneration = 0

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
    local old = self.completionistMapV104RavenSelection
    self.completionistMapV104RavenSelection = nil
    if old ~= nil then
      log("SELECT_DISARM", "reason=" .. tostring(reason) ..
          " state=" .. tostring(old.State) ..
          " kind=" .. tostring(old.Kind) .. " name=" .. tostring(old.Name) ..
          " uid=" .. tostring(old.IdString) ..
          " generation=" .. tostring(old.Generation))
    end
  end

  local function captureSelection(self, selected, source)
    if self == nil or selected == nil then return nil end
    local old = self.completionistMapV104RavenSelection
    if old ~= nil and old.IdString == selected.IdString then
      old.Source = source
      return old
    end
    if old ~= nil then clearSelection(self, "exact_custom_replaced") end
    selectionGeneration = selectionGeneration + 1
    selected.Generation = selectionGeneration
    selected.State = "candidate-custom"
    selected.Source = source
    self.completionistMapV104RavenSelection = selected
    log("SELECT_CANDIDATE", "source=" .. tostring(source) ..
        " kind=" .. tostring(selected.Kind) .. " name=" .. selected.Name ..
        " uid=" .. selected.IdString ..
        " generation=" .. tostring(selected.Generation))
    return selected
  end

  local function currentSelection(self)
    if self == nil then return nil end
    local selected = self.completionistMapV104RavenSelection
    if selected == nil then return nil end
    if selected.Name == ravenName and originalCollected() ~= false then
      clearSelection(self, "raven_collected")
      return nil
    end
    return selected
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

  local function armSelection(self, selected)
    if self == nil or selected == nil then return nil end
    if selected.State == "armed-custom" then return selected end
    if selected.State ~= "candidate-custom" then
      clearSelection(self, "invalid_state_before_arm")
      return nil
    end
    selected.State = "armed-custom"
    log("SELECT_ARM", "source=GetShowOnCompassPrompt_custom_raven_owner" ..
        " kind=" .. tostring(selected.Kind) .. " name=" .. selected.Name ..
        " uid=" .. selected.IdString ..
        " generation=" .. tostring(selected.Generation))
    return selected
  end

  local function consumeSelection(self)
    local selected = currentSelection(self)
    if selected == nil or selected.State ~= "armed-custom" then return nil end
    self.completionistMapV104RavenSelection = nil
    log("SELECT_CONSUME", "kind=" .. tostring(selected.Kind) ..
        " name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " generation=" .. tostring(selected.Generation))
    return selected
  end

  local function exactTwinCollisionSelection(selected)
    return selected ~= nil and
      selected.Kind == "twin" and
      selected.Name == twinName and
      selected.Source == "collision_table:twin_object_reference"
  end

  local function customRavenOwnsPrompt(self, show, selected)
    if show ~= true or self == nil or selected == nil then return false end
    if exactTwinCollisionSelection(selected) then
      return self.currMarkerID ~= nil and
        tostring(self.currMarkerID) == selected.IdString
    end
    -- Keep the human-proven real Raven prompt bridge unchanged.
    return selected.Kind == "real" and selected.Name == ravenName and
      self.completionistMapV100Selected == true and
      self.completionistMapV100NornirSelected == nil and
      self.completionistMapV100NornirChestSelected == nil and
      self.currMarkerID == nil
  end

  local function customRavenOwnsAction(self, selected)
    if self == nil or selected == nil then return false end
    if exactTwinCollisionSelection(selected) then
      return self.currMarkerID ~= nil and
        tostring(self.currMarkerID) == selected.IdString
    end
    return selected.Kind == "real" and selected.Name == ravenName and
      self.completionistMapV100Selected == true and self.currMarkerID == nil
  end

  local function currentMarkerDiffersFromSelection(self, selected)
    return self ~= nil and selected ~= nil and self.currMarkerID ~= nil and
      tostring(self.currMarkerID) ~= selected.IdString
  end

  local function confirmedDifferentPromptReason(self, selected)
    if currentMarkerDiffersFromSelection(self, selected) then
      return "confirmed_native_prompt:marker=" .. tostring(self.currMarkerID)
    end
    return "confirmed_other_custom_prompt"
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
      captureSelection(self, selected, "collision_table:" .. tostring(source))
    end
    -- Noncustom callbacks alone prove nothing. The base handler debounces them
    -- and can emit several while the custom prompt remains the current action.
    return previousCollision(self, currState, collisionGameObjectTable, realmName)
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    lastMapOnSelf = self
    local show, previousText = previousPrompt(self, currMenu)
    if promptOverride ~= nil then
      return promptForSelection(promptOverride, show, previousText)
    end
    local selected = currentSelection(self)
    if selected ~= nil and not show then
      clearSelection(self, "prompt_unavailable")
      return show, previousText
    end
    if selected ~= nil and not customRavenOwnsPrompt(self, show, selected) then
      clearSelection(self, confirmedDifferentPromptReason(self, selected))
      return show, previousText
    end
    selected = armSelection(self, selected)
    return promptForSelection(selected, show, previousText)
  end

  function MapOn:ShowOnCompass(currState)
    lastMapOnSelf = self
    local current = currentSelection(self)
    if currentMarkerDiffersFromSelection(self, current) then
      clearSelection(self, "confirmed_native_action:marker=" .. tostring(self.currMarkerID))
    elseif current ~= nil and not customRavenOwnsAction(self, current) then
      clearSelection(self, "custom_prompt_owner_lost_before_action")
    elseif current ~= nil and current.State ~= "armed-custom" then
      clearSelection(self, "action_without_prompt_arm")
    end
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
        " class=" .. ravenClass ..
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
      local selected = currentSelection(self)
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
    lastMapOnSelf = self
    observeMapCompletion(self)
    local result = previousUpdate(self, ...)
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
      clearSelection(self, "map_teardown:" .. method)
      compassPending = nil
      if lastMapOnSelf == self then lastMapOnSelf = nil end
      return previous(self, ...)
    end
  end

  _G.CompletionistMapV104UidAwareRavenCompassRouting = true
  _G.CompletionistMapV104UidAwareRavenCompassRoutingV33 = true
  log("API", "installed=true identitySource=MapOn.MapCollisionChangeHandler_collision_table" ..
      " selectionStateMachine=none,candidate-custom,armed-custom" ..
      " armedSelectionExpiry=ui_lifecycle_only" ..
      " armSignal=GetShowOnCompassPrompt_exact_real_or_same_uid_exact_twin" ..
      " stockSignal=currMarkerID_differs_from_exact_custom_candidate" ..
      " markerIdentity=Map.GetMarkerInfo compassClass=" .. ravenClass ..
      " singleActive=true gameplayCleanup=persistent_precisionchallenge" ..
      " progressionWrites=false twinLifecycleIndependent=true")
end
-- END COMPLETIONIST V0.10.4 UID-AWARE RAVEN COMPASS ROUTING V3.3

-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS
-- Data drives all Raven work. Catalogue Ravens are visible unless explicitly collected.
do
  local prefix = "[CompletionistMap v0.10.5-all-ravens] "
  local ravenClass = "CompletionistRaven"
  local mapResource = "goMapIconCompletionistRaven"
  local markerLabel = "Odin's Raven"
  local provenName = "Completionist_V103_Veithurgard_Raven_01"
  local rows = {
    {CatalogueId="raven_95b9c6444d479ac68207b1829d02909b",Name="Completionist_V105_Raven_95b9c6444d479ac6",UidHex="0664D1B9E406D64D",Realm="Alfheim",RegionId="25B5C98A27101CB7",WadKey="alf355chiseldungeon",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_ALF_Raven_Parent",X=355.902670263393,Y=-13.4251546010282,Z=150.087953932125,AggregateSafe=true},
    {CatalogueId="raven_63f2a1a74274de6df3962490fb6552e9",Name="Completionist_V105_Raven_63f2a1a74274de6d",UidHex="15E7B235887EA0C2",Realm="Alfheim",RegionId="25B5C98A27101CB7",WadKey="alfdgn210main",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_ALF_Raven_Parent",X=330.212471220837,Y=9.57608189725386,Z=298.500278896071,AggregateSafe=true},
    {CatalogueId="raven_a824e12946c803e8511da79bc52a193f",Name="Completionist_V105_Raven_a824e12946c803e8",UidHex="1FC01FAB6070DDFB",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel100calderaheldressing",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HEL_Raven_Parent",X=100.37760925293,Y=13.2656946182251,Z=50.1039047241211,AggregateSafe=true},
    {CatalogueId="raven_2811daa04ce30f079ff758b3bf04369d",Name="Completionist_V105_Raven_2811daa04ce30f07",UidHex="01CDC544ACC956C9",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel300mainbridge",ObjectKey="goprecisionchallengeravenperch3",ParentQuest="RegionSummary_HEL_Raven_Parent",X=356.888793945312,Y=-4.4595308303833,Z=31.5798797607422,AggregateSafe=true},
    {CatalogueId="raven_595d8539488753c54fa471a46631e8c7",Name="Completionist_V105_Raven_595d8539488753c5",UidHex="C00ADDF537A535BD",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel300mainbridge",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HEL_Raven_Parent",X=321.863159179688,Y=13.952938079834,Z=79.7303237915039,AggregateSafe=true},
    {CatalogueId="raven_69a8e9f3434cd84b48c7c688094ed2e4",Name="Completionist_V105_Raven_69a8e9f3434cd84b",UidHex="97EF09F410C2506A",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel300mainbridge",ObjectKey="goprecisionchallengeravenperch2",ParentQuest="RegionSummary_HEL_Raven_Parent",X=349.126617431641,Y=13.6133966445923,Z=12.3349018096924,AggregateSafe=true},
    {CatalogueId="raven_7ffab2af4d6e2c7e7a9d42a58943bdf1",Name="Completionist_V105_Raven_7ffab2af4d6e2c7e",UidHex="F6A541CF3949609C",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel300mainbridge",ObjectKey="goprecisionchallengeravenhover2",ParentQuest="RegionSummary_HEL_Raven_Parent",X=314.640655517578,Y=-27.4914531707764,Z=58.8981285095215,AggregateSafe=true},
    {CatalogueId="raven_b13e52024ecc5909d1fe478ee2c54e8c",Name="Completionist_V105_Raven_b13e52024ecc5909",UidHex="59ED7C538496830E",Realm="Helheim",RegionId="FE4E39694E7F6B29",WadKey="hel350chiselarena",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HEL_Raven_Parent",X=346.504669189453,Y=-2.00611925125122,Z=-74.6015243530273,AggregateSafe=true},
    {CatalogueId="raven_7ffe9f6e4e18734cebadc892d24801e4",Name="Completionist_V105_Raven_7ffe9f6e4e18734c",UidHex="11944D04B7464701",Realm="Midgard",RegionId="018E0CE2EAEAA53D",WadKey="xpl940beachcave",ObjectKey="goprecisionchallengeravenperch04",ParentQuest="RegionSummary_BC_Raven_Parent",X=130.001189981692,Y=0.936963081359863,Z=-141.655430069183,AggregateSafe=true},
    {CatalogueId="raven_bc9c2cea4b7e1feaf09bb58f1b691035",Name="Completionist_V105_Raven_bc9c2cea4b7e1fea",UidHex="911828CAFC2703E5",Realm="Midgard",RegionId="018E0CE2EAEAA53D",WadKey="xpl940beachcave",ObjectKey="goprecisionchallengeravenperch03",ParentQuest="RegionSummary_BC_Raven_Parent",X=63.2450691865632,Y=7.60876417160034,Z=-191.514320076015,AggregateSafe=true},
    {CatalogueId="raven_2b86b2ad4f6c006d5f6db0af57a190a4",Name="Completionist_V105_Raven_2b86b2ad4f6c006d",UidHex="2D469D999E0FB832",Realm="Midgard",RegionId="018E325B7D1CFC3B",WadKey="xpl950beachmaze",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_BM_Raven_Parent",X=-178.000001018187,Y=1.7838077545166,Z=303.99999980491,AggregateSafe=true},
    {CatalogueId="raven_73ac895445d967756cbf34ac591ac205",Name="Completionist_V105_Raven_73ac895445d96775",UidHex="55970A556AFFD664",Realm="Midgard",RegionId="9391E1AF5C0C0C70",WadKey="xpl960beachship",ObjectKey="goprecisionchallengeravenhoop",ParentQuest="RegionSummary_BSW_Raven_Parent",X=-258.990280144897,Y=5.33059692382812,Z=-285.298244761827,AggregateSafe=true},
    {CatalogueId="raven_11d083554dd320d5e23ccca24f339acd",Name="Completionist_V105_Raven_11d083554dd320d5",UidHex="AF13DC156ACA6E78",Realm="Midgard",RegionId="3A9BFC89F5AB6FE3",WadKey="xpl970beachtower",ObjectKey="goprecisionchallengeravenhover02001",ParentQuest="RegionSummary_BT_Raven_Parent",X=-247.521129680852,Y=15.334071401711,Z=174.190121041686,AggregateSafe=true},
    {CatalogueId="raven_ef8568004bd6283b79b4819bb3e5cb0f",Name="Completionist_V105_Raven_ef8568004bd6283b",UidHex="16B1C4AD5F7DA2D2",Realm="Midgard",RegionId="6732D984CAA9285A",WadKey="xpl980beachwaterfall",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_BW_Raven_Parent",X=112.027648567456,Y=14.0519285202026,Z=355.299636271641,AggregateSafe=true},
    {CatalogueId="raven_4b8990ee4053cd00d13299928da1a9fc",Name="Completionist_V105_Raven_4b8990ee4053cd00",UidHex="A67E934E2EECBD5C",Realm="Midgard",RegionId="7B7F0B522FFA9124",WadKey="xpl910islandshipwreck",ObjectKey="goprecisionchallengeravenperch1",ParentQuest="RegionSummary_CALS_Raven_Parent",X=-250.723768859096,Y=-3.53147229364686,Z=-89.2099558240422,AggregateSafe=false},
    {CatalogueId="raven_df5a6f7543fa157f4cd630a19c038deb",Name="Completionist_V105_Raven_df5a6f7543fa157f",UidHex="BB9DBFCB8C866AEB",Realm="Midgard",RegionId="7B7F0B522FFA9124",WadKey="xpl930beachruins",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_CALS_Raven_Parent",X=294.915357133406,Y=-8.76826047897339,Z=-174.666727587869,AggregateSafe=false},
    {CatalogueId="raven_e4d9b53e4e0330fc07421d8fea348f1d",Name="Completionist_V105_Raven_e4d9b53e4e0330fc",UidHex="190618C0A60E79EE",Realm="Midgard",RegionId="62F2A92841484ABF",WadKey="foot250chiselarena",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_FOOT_Raven_Parent",X=-482.668668137819,Y=11.7049910724163,Z=246.15424006169,AggregateSafe=true},
    {CatalogueId="raven_2862a927444bf9df95a605b6a1cfec2b",Name="Completionist_V105_Raven_2862a927444bf9df",UidHex="76F941DA1362135A",Realm="Midgard",RegionId="62F2A92841484ABF",WadKey="foot500top",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_FOOT_Raven_Parent",X=-364.428009033203,Y=60.9643630981445,Z=378.847961425781,AggregateSafe=true},
    {CatalogueId="raven_528d332048f734d84b2f8ca26b3abafc",Name="Completionist_V105_Raven_528d332048f734d8",UidHex="CF93AD9D203E63CC",Realm="Midgard",RegionId="7AF9D3D169EFE9B7",WadKey="for260chiseldungeon",ObjectKey="goprecisionchallengeravenhover03",ParentQuest="RegionSummary_FOR_Raven_Parent",X=-207.533752441406,Y=27.4933643341064,Z=-891.698852539063,AggregateSafe=true},
    {CatalogueId="raven_3f0baac6405889c7478896801b6a637c",Name="Completionist_V105_Raven_3f0baac6405889c7",UidHex="08451787929A6E02",Realm="Midgard",RegionId="7880D593C85F2451",WadKey="xpl850dungeonforest",ObjectKey="goprecisionchallengeravenhover1",ParentQuest="RegionSummary_FD_Raven_Parent",X=10.2952669007519,Y=14.497296333313,Z=-585.053234791918,AggregateSafe=true},
    {CatalogueId="raven_ad56521740c745076417e99ddf1dd7a4",Name="Completionist_V105_Raven_ad56521740c74507",UidHex="3E555E8FCCD523B7",Realm="Midgard",RegionId="7880D593C85F2451",WadKey="xpl850dungeonforest",ObjectKey="goprecisionchallengeravenperch1",ParentQuest="RegionSummary_FD_Raven_Parent",X=55.46050852298,Y=12.5715627670288,Z=-560.252033876615,AggregateSafe=true},
    {CatalogueId="raven_b5ec8398449f573b8a70b7a4fb1154af",Name="Completionist_V105_Raven_b5ec8398449f573b",UidHex="5CDB7378D8D67D98",Realm="Midgard",RegionId="7880D593C85F2451",WadKey="xpl850dungeonforest",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_FD_Raven_Parent",X=78.1437570857584,Y=-0.150186061859131,Z=-512.011643855323,AggregateSafe=true},
    {CatalogueId="raven_14a87a63401390815b4e4ab2b4e619d0",Name="Completionist_V105_Raven_14a87a6340139081",UidHex="E24448E356FE718F",Realm="Midgard",RegionId="7880D593C85F2451",WadKey="xpl875dungeonforestlh",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_FD_Raven_Parent",X=68.9712214782494,Y=7.0696337223053,Z=-385.6933954276,AggregateSafe=true},
    {CatalogueId="raven_97b753a94e069b45a5e031b81a5b9f91",Name="Completionist_V105_Raven_97b753a94e069b45",UidHex="E7EFC86FCBAF98BB",Realm="Midgard",RegionId="7880D593C85F2451",WadKey="xpl875dungeonforestlh",ObjectKey="goprecisionchallengeravenhover",ParentQuest="RegionSummary_FD_Raven_Parent",X=70.7724436862145,Y=7.99884366989136,Z=-452.414581433755,AggregateSafe=true},
    {CatalogueId="raven_09c20f1b44476543307d8d8a444401f7",Name="Completionist_V105_Raven_09c20f1b44476543",UidHex="C80BFF3879136CFA",Realm="Midgard",RegionId="0000489975E7755D",WadKey="xpl100httk",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=213.200271606445,Y=-19.5986442565918,Z=-465.167449951172,AggregateSafe=true},
    {CatalogueId="raven_93bb416243c6d7afd0dadf824507fcb6",Name="Completionist_V105_Raven_93bb416243c6d7af",UidHex="4C9D0C42D69BEC28",Realm="Midgard",RegionId="0000489975E7755D",WadKey="xpl100httk",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=299.866455078125,Y=-29.7612724304199,Z=-386.324096679688,AggregateSafe=true},
    {CatalogueId="raven_b65148ce40189997a7ee6abb05551d95",Name="Completionist_V105_Raven_b65148ce40189997",UidHex="175DE4FF10D771FD",Realm="Midgard",RegionId="0000489975E7755D",WadKey="xpl100httk",ObjectKey="goprecisionchallengeravenperch1",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=395.121004104614,Y=-45.5068912506104,Z=-352.832214355469,AggregateSafe=true},
    {CatalogueId="raven_4f3ed8604f52329654cb89a77cb7b227",Name="Completionist_V105_Raven_4f3ed8604f523296",UidHex="5BDFDCC40708B704",Realm="Midgard",RegionId="0000489975E7755D",WadKey="xpl150httktemple",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=352.256092071533,Y=-30.1093330383301,Z=-475.425933837891,AggregateSafe=true},
    {CatalogueId="raven_ce4340a84992a449844e0394671c59eb",Name="Completionist_V105_Raven_ce4340a84992a449",UidHex="A9BA3AD986C6062D",Realm="Midgard",RegionId="0000489975E7755D",WadKey="xpl170httkcaver",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=432.142700195312,Y=-45.9899129867554,Z=-479.911163330078,AggregateSafe=true},
    {CatalogueId="raven_0b07c75f438ce0cfe8b6feb7731ffc9c",Name="Completionist_V105_Raven_0b07c75f438ce0cf",UidHex="5B764018874C3076",Realm="Midgard",RegionId="3E2B34150449C3E7",WadKey="xpl425huldramineslh",ObjectKey="goprecisionchallengeravenhover",ParentQuest="RegionSummary_HM01_Raven_Parent",X=-234.014747619629,Y=7.71115684509277,Z=430.845436096191,AggregateSafe=true},
    {CatalogueId="raven_d869e60744104a9e8865428d5fc2f63a",Name="Completionist_V105_Raven_d869e60744104a9e",UidHex="6C3689A3012B1F35",Realm="Midgard",RegionId="3E2B34150449C7F6",WadKey="xpl450huldramines",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HM02_Raven_Parent",X=-484.709909439087,Y=-18.9620180130005,Z=-81.9476470947266,AggregateSafe=true},
    {CatalogueId="raven_349cc1eb4752a6149cf89f9f94644092",Name="Completionist_V105_Raven_349cc1eb4752a614",UidHex="C14EFF68E72A3957",Realm="Midgard",RegionId="3E2B34150449C7F6",WadKey="xpl475huldramineslh",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HM02_Raven_Parent",X=-499.053089618683,Y=-8.97603130340576,Z=-174.698647499084,AggregateSafe=true},
    {CatalogueId="raven_7ea7fe24483df9d884fd4790840bf692",Name="Completionist_V105_Raven_7ea7fe24483df9d8",UidHex="E61370AF12127058",Realm="Midgard",RegionId="7071EB6E695042F0",WadKey="xpl300stronghold",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_HSH_Raven_Parent",X=742.055877685547,Y=-4.87457370758057,Z=-261.06355381012,AggregateSafe=true},
    {CatalogueId="raven_e01f95a84dd1e99dde0952856855399d",Name="Completionist_V105_Raven_e01f95a84dd1e99d",UidHex="68320FC1AD1F583D",Realm="Midgard",RegionId="7071EB6E695042F0",WadKey="xpl300stronghold",ObjectKey="goprecisionchallengeravenperch1",ParentQuest="RegionSummary_HSH_Raven_Parent",X=613.454071044922,Y=-14.4896502494812,Z=-131.025337219238,AggregateSafe=true},
    {CatalogueId="raven_9deba5114d8045898dafc5be9add793b",Name="Completionist_V105_Raven_9deba5114d804589",UidHex="E3D252337EAF420F",Realm="Midgard",RegionId="0B6DF6C03C11EAB1",WadKey="xpl900islandarch",ObjectKey="goprecisionchallengeravenhop1",ParentQuest="RegionSummary_ISA_Raven_Parent",X=99.3590496837271,Y=-8.7858304977417,Z=278.658577850248,AggregateSafe=true},
    {CatalogueId="raven_62fbf37c443c70aeca40ac840f6084b1",Name="Completionist_V105_Raven_62fbf37c443c70ae",UidHex="899396E22A253632",Realm="Midgard",RegionId="2FDD4E80C774CB0E",WadKey="xpl910islandshipwreck",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_ISW_Raven_Parent",X=-195.024169302108,Y=-19.6607341372529,Z=-199.392995631803,AggregateSafe=true},
    {CatalogueId="raven_fa8d596f445ba456bc5b11905aa4af07",Name="Completionist_V105_Raven_fa8d596f445ba456",UidHex="8013FD7D4DD7B426",Realm="Midgard",RegionId="254A1280A3285151",WadKey="cal270stonemasonlh",ObjectKey="goodinsravin03",ParentQuest="RegionSummary_MT_Raven_Parent",X=176.968307495117,Y=3.7605185508728,Z=163.654830932617,AggregateSafe=true},
    {CatalogueId="raven_4532135740478ac108377e8b1c51a501",Name="Completionist_V105_Raven_4532135740478ac1",UidHex="7F019D16F7C2A561",Realm="Midgard",RegionId="ED623FA0A76B2934",WadKey="peak140caverndark",ObjectKey="goprecisionchallengeravenhover",ParentQuest="RegionSummary_PP_Raven_Parent",X=-456.389038085938,Y=100.450210571289,Z=616.507263183594,AggregateSafe=true},
    {CatalogueId="raven_fb1ebb004216311e237c36b23a10707b",Name="Completionist_V105_Raven_fb1ebb004216311e",UidHex="5871B7E2287D2A6C",Realm="Midgard",RegionId="ED623FA0A76B2934",WadKey="peak205chiselarena",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_PP_Raven_Parent",X=-477.010528564453,Y=115.406867980957,Z=894.953552246094,AggregateSafe=true},
    {CatalogueId="raven_b88e14b5413082e98c4d9cadcbf6ad10",Name="Completionist_V105_Raven_b88e14b5413082e9",UidHex="8034B66C18AF4433",Realm="Midgard",RegionId="ED623FA0A76B2934",WadKey="peak210rollerroomlh",ObjectKey="goraven",ParentQuest="RegionSummary_PP_Raven_Parent",X=-278.19970703125,Y=142.471649169922,Z=781.201049804688,AggregateSafe=true},
    {CatalogueId="raven_5a498384495d58916e944883eb2c90bb",Name="Completionist_V105_Raven_5a498384495d5891",UidHex="FFA0150372875D11",Realm="Midgard",RegionId="ED623FA0A76B2934",WadKey="peak260chimneylowhall",ObjectKey="goprecisionchallengeravenhover",ParentQuest="RegionSummary_PP_Raven_Parent",X=-336.435485839844,Y=140.173431396484,Z=856.341857910156,AggregateSafe=true},
    {CatalogueId="raven_100bb5c44d6b69eba68eb895d005f956",Name="Completionist_V105_Raven_100bb5c44d6b69eb",UidHex="B3CCC54892477D07",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv200dangersmain",ObjectKey="goravenperch1",ParentQuest="RegionSummary_RP_Raven_Parent",X=-242.808197021484,Y=92.5402984619141,Z=-455.935913085938,AggregateSafe=false},
    {CatalogueId="raven_d9db91914694cfe73fa5b9abb208d25d",Name="Completionist_V105_Raven_d9db91914694cfe7",UidHex="F3859EDE52A924C6",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv200dangersmain",ObjectKey="goravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-273.784545898438,Y=89.4121856689453,Z=-547.946472167969,AggregateSafe=false},
    {CatalogueId="raven_97e41c48491b177e804019a649735e58",Name="Completionist_V105_Raven_97e41c48491b177e",UidHex="22E45B129D98FF0C",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv400forestintro",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-358.776885986328,Y=108.650001525879,Z=-393.233367919922,AggregateSafe=false},
    {CatalogueId="raven_ccbc62d64eb0f79bbf76e9a08401a137",Name="Completionist_V105_Raven_ccbc62d64eb0f79b",UidHex="3B3AA9A54985EEAD",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv420forestboarstart",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-346.471710205078,Y=99.9208984375,Z=-328.121917724609,AggregateSafe=false},
    {CatalogueId="raven_f8fdd3a4438c9697f8aa308323b2465e",Name="Completionist_V105_Raven_f8fdd3a4438c9697",UidHex="4F3249151CC9571C",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv430forestboartrack",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-383.799987792969,Y=75.8000030517578,Z=-276.899993896484,AggregateSafe=false},
    {CatalogueId="raven_ac45261c43ee745cd2e20a9cf61a817d",Name="Completionist_V105_Raven_ac45261c43ee745c",UidHex="BDBD4A14BF88FC2A",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv475freyahouseext",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-405.134735107422,Y=69.8000030517578,Z=0.886073529720306,AggregateSafe=false},
    {CatalogueId="raven_5a652cfb4af86af517b33c8676dbbfc5",Name="Completionist_V105_Raven_5a652cfb4af86af5",UidHex="4585940C8A61F596",Realm="Midgard",RegionId="4EFD98E8E80E1239",WadKey="riv975chiselarena",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_RP_Raven_Parent",X=-503.480834960938,Y=25.3998031616211,Z=145.937606811523,AggregateSafe=false},
    {CatalogueId="raven_8ca357c445d32c015159d6b93e173686",Name="Completionist_V105_Raven_8ca357c445d32c01",UidHex="D54F2CA5440A5C1D",Realm="Midgard",RegionId="848BB2D584D32E1B",WadKey="stn090lakevista",ObjectKey="goprecisionchallengeravenhop",ParentQuest="RegionSummary_SM_Raven_Parent",X=456.662017822266,Y=-2.57212233543396,Z=133.628570556641,AggregateSafe=true},
    {CatalogueId="raven_a70cd386408985c8bedbc98a7aaed456",Name="Completionist_V105_Raven_a70cd386408985c8",UidHex="D01919CCDEE91096",Realm="Midgard",RegionId="848BB2D584D32E1B",WadKey="stn110chiselarena",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_SM_Raven_Parent",X=574.245178222656,Y=-34.8896942138672,Z=151.699478149414,AggregateSafe=true},
    {CatalogueId="raven_642d0d164af0a5d4076e77933c549a5d",Name="Completionist_V103_Veithurgard_Raven_01",UidHex="E15E6BC82AE2773E",Realm="Midgard",RegionId="A1845BEF17F0E7BB",WadKey="xpl200funeral",ObjectKey="goprecisionchallengeravenperch",ParentQuest="RegionSummary_VF_Raven_Parent",X=-64.8508987426758,Y=12.9873847961426,Z=787.306938171387,AggregateSafe=true},
    {CatalogueId="raven_c945cb53465b58decfcbd4a221cb5326",Name="Completionist_V105_Raven_c945cb53465b58de",UidHex="C9C31EE99E7E4339",Realm="Midgard",RegionId="A1845BEF17F0E7BB",WadKey="xpl200funeral",ObjectKey="goprecisionchallengeravenhover",ParentQuest="RegionSummary_VF_Raven_Parent",X=122.604850769043,Y=17.3742713928223,Z=679.211616516113,AggregateSafe=true},
    {CatalogueId="raven_e32f7bab42fd7298890f6aa56a734562",Name="Completionist_V105_Raven_e32f7bab42fd7298",UidHex="ED1B8C2B562EE253",Realm="Midgard",RegionId="A1845BEF17F0E7BB",WadKey="xpl200funeral",ObjectKey="goprecisionchallengeravenperch1",ParentQuest="RegionSummary_VF_Raven_Parent",X=-127.960754394531,Y=15.5776290893555,Z=690.075782775879,AggregateSafe=true},
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
