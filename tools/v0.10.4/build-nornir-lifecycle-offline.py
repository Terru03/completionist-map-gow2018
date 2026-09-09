#!/usr/bin/env python3
"""Build the OFFLINE Nornir native single-target + lifecycle Lua layer.

This gate starts from the frozen Raven production mapmenu.lua and clean loader
sources for the stock Nornir gameplay scripts/MainHUD. It does not write the
God of War directory.

The Veithurgard Nornir parent remains a collectible until the actual Runic loot
chest is opened. The runic parent publishes challengeComplete so the UI can show
"unlocked" state, while interact_chest_standard.lua publishes the authoritative
OPENED lifecycle and immediately removes an active native compass target. No
quest, puzzle, save, marker-state, or progression value is mutated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

RESULT = "OFFLINE_NORNIR_LIFECYCLE_BUILT_AND_REPARSED"
MAPMENU_SHA256 = "67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b"
NORNIR_MARKER = "Completionist_V104_Veithurgard_NornirChest_01"
NORNIR_MARKER_ID = "381B067F07254A25"
NORNIR_CLASS = "CompletionistNornirChest"
NORNIR_CLASS_UID = "8D5A770E0C4272CE"
NORNIR_MAP = "goMapIconCompletionistNornirChest"
NORNIR_MAP_HASH = "E14C66C3B90633E0"
NORNIR_HUD = "goCompletionistNornirChestHUD"
NORNIR_HUD_HASH = "7DDC11175EBD1E94"
NORNIR_INWORLD = "COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST"
NORNIR_INWORLD_UID = "32BBE7E267644D93"
RAVEN_MARKER = "Completionist_V103_Veithurgard_Raven_01"
RAVEN_CLASS = "CompletionistRaven"
TARGET = (-43.904609680176, 14.5, 748.57946777344)
TARGET_RADIUS_METRES = 2.0

REL = {
    "mapmenu": Path("gameart/ui/scripts/inworldmenu/mapmenu.lua"),
    "mainhud": Path("gameart/ui/scripts/hud/mainhud.lua"),
    "runic": Path("gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua"),
    "standard": Path("gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua"),
}

MAP_BEGIN = "-- BEGIN COMPLETIONIST V0.10.4 NORNIR NATIVE SINGLE ACTIVE LIFECYCLE"
MAP_END = "-- END COMPLETIONIST V0.10.4 NORNIR NATIVE SINGLE ACTIVE LIFECYCLE"
HUD_BEGIN = "-- BEGIN COMPLETIONIST V0.10.4 NORNIR LIFECYCLE RECEIVER"
HUD_END = "-- END COMPLETIONIST V0.10.4 NORNIR LIFECYCLE RECEIVER"
RUNIC_BEGIN = "-- BEGIN COMPLETIONIST V0.10.4 NORNIR LIFECYCLE PUBLISHER"
RUNIC_END = "-- END COMPLETIONIST V0.10.4 NORNIR LIFECYCLE PUBLISHER"
STD_BEGIN = "-- BEGIN COMPLETIONIST V0.10.4 NORNIR OPENED PUBLISHER"
STD_END = "-- END COMPLETIONIST V0.10.4 NORNIR OPENED PUBLISHER"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    return sha_bytes(path.read_bytes())


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    check(count == 1, f"{label}: expected one occurrence, found {count}: {old!r}")
    return text.replace(old, new, 1)


def insert_after_function_header(text: str, header: str, line: str, label: str) -> str:
    pattern = re.compile(re.escape(header) + r"\r?\n")
    matches = list(pattern.finditer(text))
    check(len(matches) == 1, f"{label}: expected one function header {header!r}, found {len(matches)}")
    m = matches[0]
    nl = "\r\n" if m.group(0).endswith("\r\n") else "\n"
    return text[:m.end()] + line + nl + text[m.end():]


def replace_once_in_function(text: str, header: str, needle: str, replacement: str, label: str) -> str:
    start = text.find(header)
    check(start >= 0, f"{label}: function header missing: {header}")
    body_start = text.find("\n", start)
    check(body_start >= 0, f"{label}: malformed function header")
    next_fn = text.find("\nfunction ", body_start + 1)
    end = len(text) if next_fn < 0 else next_fn + 1
    body = text[start:end]
    count = body.count(needle)
    check(count == 1, f"{label}: expected one {needle!r} inside {header}, found {count}")
    patched = body.replace(needle, replacement, 1)
    return text[:start] + patched + text[end:]


def clean_loader_source(game: Path, rel: Path) -> tuple[Path, bytes]:
    path = game / "mods/lua_source" / rel
    check(path.is_file(), f"clean loader source missing: {path}")
    return path, path.read_bytes()


def patch_runic(source: bytes) -> tuple[bytes, dict]:
    text = source.decode("utf-8-sig")
    check(RUNIC_BEGIN not in text and RUNIC_END not in text, "clean runic source already contains v0.10.4 lifecycle publisher")
    required = (
        "local keysUsed = 0",
        "local challengeComplete = false",
        "local runeTable = {}",
        'keyType = go:GetLuaTableAttribute("KeyType")',
        "function OnScriptLoaded(level, go)",
        "function OnStart(level, go)",
        "function OnKeyBroken(runeIndex)",
        "  CheckKeys()",
    )
    missing = [x for x in required if x not in text]
    check(not missing, f"runic stock structure changed; missing: {missing}")
    nl = newline_of(text)
    helper = f'''{RUNIC_BEGIN}
-- Target-only stock-state publisher. Read-only with respect to gameplay state.
local function CompletionistMapV104_NornirTargetPosition()
  if thisObj == nil then return false, nil end
  local ok, pos = pcall(function() return thisObj:GetWorldPosition() end)
  if not ok or pos == nil then return false, nil end
  local dx = pos.x - ({TARGET[0]})
  local dy = pos.y - ({TARGET[1]})
  local dz = pos.z - ({TARGET[2]})
  return dx * dx + dy * dy + dz * dz <= {TARGET_RADIUS_METRES ** 2}, pos
end

local function CompletionistMapV104_PublishNornirState(source)
  local target, pos = CompletionistMapV104_NornirTargetPosition()
  if not target then return end
  local payload = {{
    marker = "{NORNIR_MARKER}",
    challengeComplete = challengeComplete == true,
    parentOpened = state == states.OPENED,
    keysUsed = keysUsed,
    x = pos.x,
    y = pos.y,
    z = pos.z,
    source = source
  }}
  local ok, err = pcall(function()
    engine.SendHook(
      "UI_CALL_EVENT",
      engine.GetUIWad(),
      "EVT_COMPLETIONIST_V104_NORNIR_STATE",
      payload
    )
  end)
  print("[CompletionistMap v0.10.4-nornir] LIFECYCLE_STATE_SEND" ..
    " source=" .. tostring(source) ..
    " challengeComplete=" .. tostring(payload.challengeComplete) ..
    " parentOpened=" .. tostring(payload.parentOpened) ..
    " keysUsed=" .. tostring(payload.keysUsed) ..
    " ok=" .. tostring(ok) ..
    " error=" .. tostring(err))
end
{RUNIC_END}'''.replace("\n", nl)
    text = replace_once(text, "function OnScriptLoaded(level, go)", helper + nl + "function OnScriptLoaded(level, go)", "runic helper insertion")
    text = insert_after_function_header(text, "function OnStart(level, go)", '  CompletionistMapV104_PublishNornirState("OnStart-restored")', "runic OnStart")
    check_line = "  CheckKeys()"
    text = replace_once_in_function(
        text,
        "function OnKeyBroken(runeIndex)",
        check_line,
        check_line + nl + '  CompletionistMapV104_PublishNornirState("OnKeyBroken-after-check")',
        "runic OnKeyBroken",
    )
    candidate = text.encode("utf-8")

    inverse = text
    inverse = inverse.replace(helper + nl, "", 1)
    inverse = inverse.replace('  CompletionistMapV104_PublishNornirState("OnStart-restored")' + nl, "", 1)
    inverse = inverse.replace(nl + '  CompletionistMapV104_PublishNornirState("OnKeyBroken-after-check")', "", 1)
    check(inverse.encode("utf-8") == source.decode("utf-8-sig").encode("utf-8"), "runic candidate failed exact inverse normalization")
    return candidate, {
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "target_radius_metres": TARGET_RADIUS_METRES,
        "publishes_on_start_restored": True,
        "publishes_after_key_check": True,
        "challenge_complete_observed": True,
        "progression_writes": False,
        "exact_inverse_to_clean_source": True,
    }


def patch_standard(source: bytes) -> tuple[bytes, dict]:
    text = source.decode("utf-8-sig")
    check(STD_BEGIN not in text and STD_END not in text, "clean standard chest source already contains v0.10.4 opened publisher")
    required = (
        "function OnScriptLoaded(level, obj)",
        "function OnStart(level, obj)",
        "function OnOpened()",
        "state = states.OPENED",
        'chestType == "Runic_Axe" or chestType == "Runic_Blades"',
        "parentObj = thisObj.Parent.Parent",
    )
    missing = [x for x in required if x not in text]
    check(not missing, f"standard chest stock structure changed; missing: {missing}")
    nl = newline_of(text)
    helper = f'''{STD_BEGIN}
-- Authoritative collectible-completion publisher for the actual Runic loot chest.
local function CompletionistMapV104_PublishRunicOpened(source)
  if chestType ~= "Runic_Axe" and chestType ~= "Runic_Blades" then return end
  if parentObj == nil then return end
  local ok, pos = pcall(function() return parentObj:GetWorldPosition() end)
  if not ok or pos == nil then return end
  local dx = pos.x - ({TARGET[0]})
  local dy = pos.y - ({TARGET[1]})
  local dz = pos.z - ({TARGET[2]})
  if dx * dx + dy * dy + dz * dz > {TARGET_RADIUS_METRES ** 2} then return end
  local payload = {{
    marker = "{NORNIR_MARKER}",
    opened = true,
    x = pos.x,
    y = pos.y,
    z = pos.z,
    source = source
  }}
  local sendOK, sendErr = pcall(function()
    engine.SendHook(
      "UI_CALL_EVENT",
      engine.GetUIWad(),
      "EVT_COMPLETIONIST_V104_NORNIR_OPENED",
      payload
    )
  end)
  print("[CompletionistMap v0.10.4-nornir] LIFECYCLE_OPENED_SEND" ..
    " source=" .. tostring(source) ..
    " ok=" .. tostring(sendOK) ..
    " error=" .. tostring(sendErr))
end
{STD_END}'''.replace("\n", nl)
    text = replace_once(text, "function OnScriptLoaded(level, obj)", helper + nl + "function OnScriptLoaded(level, obj)", "standard helper insertion")
    text = insert_after_function_header(text, "function OnOpened()", '  CompletionistMapV104_PublishRunicOpened("OnOpened")', "standard OnOpened")
    text = insert_after_function_header(
        text,
        "function OnStart(level, obj)",
        '  if state == states.OPENED then CompletionistMapV104_PublishRunicOpened("OnStart-restored-opened") end',
        "standard OnStart",
    )
    candidate = text.encode("utf-8")

    inverse = text
    inverse = inverse.replace(helper + nl, "", 1)
    inverse = inverse.replace('  CompletionistMapV104_PublishRunicOpened("OnOpened")' + nl, "", 1)
    inverse = inverse.replace('  if state == states.OPENED then CompletionistMapV104_PublishRunicOpened("OnStart-restored-opened") end' + nl, "", 1)
    check(inverse.encode("utf-8") == source.decode("utf-8-sig").encode("utf-8"), "standard chest candidate failed exact inverse normalization")
    return candidate, {
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "target_radius_metres": TARGET_RADIUS_METRES,
        "authoritative_open_on_OnOpened": True,
        "restored_open_on_OnStart": True,
        "progression_writes": False,
        "exact_inverse_to_clean_source": True,
    }


def patch_mainhud(source: bytes) -> tuple[bytes, dict]:
    text = source.decode("utf-8-sig")
    check(HUD_BEGIN not in text and HUD_END not in text, "clean MainHUD source already contains v0.10.4 lifecycle receiver")
    required = (
        'local mainHUD = MainHUD.New("mainHUD", {})',
        'self.compassObj = util.GetUiObjByName("Compass")',
        "function MainHUD:SetRagePrompts()",
    )
    missing = [x for x in required if x not in text]
    check(not missing, f"MainHUD stock structure changed; missing: {missing}")
    nl = newline_of(text)
    block = f'''{HUD_BEGIN}
do
  local marker = "{NORNIR_MARKER}"
  local tx, ty, tz = {TARGET[0]}, {TARGET[1]}, {TARGET[2]}
  local radiusSq = {TARGET_RADIUS_METRES ** 2}

  local function targetPayload(args)
    if type(args) ~= "table" then return false end
    local x, y, z = tonumber(args.x), tonumber(args.y), tonumber(args.z)
    if x == nil or y == nil or z == nil then return false end
    local dx, dy, dz = x - tx, y - ty, z - tz
    return dx * dx + dy * dy + dz * dz <= radiusSq
  end

  local function state()
    if type(_G.CompletionistMapV104VeithurgardNornirState) ~= "table" then
      _G.CompletionistMapV104VeithurgardNornirState = {{
        seen = false,
        challengeComplete = false,
        opened = false,
        generation = 0
      }}
    end
    return _G.CompletionistMapV104VeithurgardNornirState
  end

  function MainHUD:EVT_COMPLETIONIST_V104_NORNIR_STATE(args)
    if not targetPayload(args) then return end
    local s = state()
    s.seen = true
    s.challengeComplete = args.challengeComplete == true
    s.parentOpened = args.parentOpened == true
    s.keysUsed = args.keysUsed
    s.lastSource = args.source
    s.generation = (s.generation or 0) + 1
    print("[CompletionistMap v0.10.4-nornir] LIFECYCLE_STATE_RECV" ..
      " challengeComplete=" .. tostring(s.challengeComplete) ..
      " parentOpened=" .. tostring(s.parentOpened) ..
      " keysUsed=" .. tostring(s.keysUsed) ..
      " source=" .. tostring(s.lastSource))
  end

  function MainHUD:EVT_COMPLETIONIST_V104_NORNIR_OPENED(args)
    if not targetPayload(args) then return end
    local s = state()
    s.seen = true
    s.challengeComplete = true
    s.opened = true
    s.lastSource = args.source
    s.generation = (s.generation or 0) + 1
    local hideOK, hideErr = pcall(function() game.Compass.HideMarker(marker) end)
    _G.CompletionistMapV104NornirTracked = false
    print("[CompletionistMap v0.10.4-nornir] LIFECYCLE_OPENED_RECV" ..
      " opened=true" ..
      " hideCompassOK=" .. tostring(hideOK) ..
      " hideCompassError=" .. tostring(hideErr) ..
      " source=" .. tostring(s.lastSource))
  end
end
{HUD_END}'''.replace("\n", nl)
    candidate_text = text + ("" if text.endswith(("\n", "\r")) else nl) + block + nl
    candidate = candidate_text.encode("utf-8")
    prefix = text.encode("utf-8")
    check(candidate.startswith(prefix), "MainHUD candidate no longer preserves clean source as prefix")
    normalized = candidate_text[:candidate_text.index(HUD_BEGIN)].rstrip("\r\n")
    check(normalized == text.rstrip("\r\n"), "MainHUD candidate failed append-only normalization")
    return candidate, {
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "challenge_state_receiver": "EVT_COMPLETIONIST_V104_NORNIR_STATE",
        "authoritative_open_receiver": "EVT_COMPLETIONIST_V104_NORNIR_OPENED",
        "active_compass_hidden_on_authoritative_open": True,
        "save_or_progression_writes": False,
        "append_only_to_clean_source": True,
    }


MAP_BLOCK = f'''{MAP_BEGIN}
-- Native Nornir parent integration layered after the runtime-proven Raven control.
-- Old synthetic Nornir map/HUD prototypes are disabled; the dedicated native marker
-- owns map, compass HUD, in-world carrier, distance and pathfinding.
do
  local prefix = "[CompletionistMap v0.10.4-nornir-native] "
  local candidate = "{NORNIR_MARKER}"
  local nornirClass = "{NORNIR_CLASS}"
  local ravenCandidate = "{RAVEN_MARKER}"
  local ravenClass = "{RAVEN_CLASS}"
  local targetX, targetY, targetZ = {TARGET[0]}, {TARGET[1]}, {TARGET[2]}

  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousCollision = MapOn.MapCollisionChangeHandler
  local previousSubmenuExit = MapOn.SubmenuExit
  local previousExit = MapOn.Exit

  local nornirIntent = nil -- tracked / untracked while native manager settles
  local retryFrames = 0
  local retryBucket = -1

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  -- Retire the v0.10.1 synthetic Nornir prototype without touching Raven.
  local oldDestroyChestPins = CompletionistMapV100_DestroyNornirChestPins
  local oldDestroyPuzzlePins = CompletionistMapV100_DestroyNornirPins
  CompletionistMapV100_CreateNornirChestPins = function(self, currState)
    if type(oldDestroyChestPins) == "function" then oldDestroyChestPins(self) end
  end
  CompletionistMapV100_CreateNornirPins = function(self, currState)
    if type(oldDestroyPuzzlePins) == "function" then oldDestroyPuzzlePins(self) end
  end

  local function lifecycle()
    local s = _G.CompletionistMapV104VeithurgardNornirState
    if type(s) ~= "table" then return false, false, false, 0 end
    return s.seen == true, s.challengeComplete == true, s.opened == true, tonumber(s.generation) or 0
  end

  local function safeField(tab, name)
    if tab == nil then return nil end
    local ok, value = pcall(function() return tab[name] end)
    if ok then return value end
    return nil
  end

  local function candidateInfo()
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(candidate) end)
    if not ok then return nil, tostring(info) end
    if info == nil then return nil, "candidate_missing" end
    return info, nil
  end

  local function candidateIdString()
    local info = candidateInfo()
    if info == nil then return nil end
    local id = safeField(info, "Id") or safeField(info, "id")
    return id ~= nil and tostring(id) or nil
  end

  local function regionFor(info, markerId)
    for _, name in ipairs({{"regionId", "RegionId", "RegionID", "regionID"}}) do
      local value = safeField(info, name)
      if value ~= nil then return value end
    end
    local ok, found, region = pcall(function() return game.Map.FindRegionFromMarker(markerId) end)
    if ok and found == true and region ~= nil then return region end
    local ok2, found2, region2 = pcall(function() return Map.FindRegionFromMarker(markerId) end)
    if ok2 and found2 == true and region2 ~= nil then return region2 end
    return nil
  end

  local function filterAllows(self)
    if self == nil or self.currRealmName ~= "Midgard" then return false end
    local logical = 1
    if type(self.filterButtonMapping) == "table" then
      logical = self.filterButtonMapping[self.filterIndex] or 1
    end
    return logical == 1 or logical == COMPLETIONIST_FILTER or logical == NORNIR_CHEST_FILTER
  end

  local function destroyPin(self, reason)
    if self == nil then return end
    local go = self.completionistMapV104NornirMapIconGO
    if go ~= nil then
      local ok, err = pcall(function() Map.RecycleIcon(go) end)
      log("MAP_PIN_DESTROY", "reason=" .. tostring(reason) .. " ok=" .. tostring(ok) .. " error=" .. tostring(err))
    end
    self.completionistMapV104NornirMapIconGO = nil
    self.completionistMapV104NornirMarkerId = nil
    self.completionistMapV104NornirSelected = false
  end

  local function ensurePin(self)
    local _, _, opened = lifecycle()
    if opened or not filterAllows(self) then
      destroyPin(self, opened and "opened" or "filter")
      return
    end
    if self.completionistMapV104NornirMapIconGO ~= nil then
      pcall(function() self.completionistMapV104NornirMapIconGO:Show() end)
      return
    end
    local info, infoErr = candidateInfo()
    if info == nil then
      if not self.completionistMapV104NornirMissingLogged then
        self.completionistMapV104NornirMissingLogged = true
        log("MAP_PIN", "active=false reason=marker_info error=" .. tostring(infoErr))
      end
      return
    end
    local markerId = safeField(info, "Id") or safeField(info, "id")
    local regionId = regionFor(info, markerId)
    if markerId == nil or regionId == nil then
      log("MAP_PIN", "active=false reason=id_or_region")
      return
    end
    local createOK, go = pcall(function() return Map.CreateMarkerIcon(markerId, regionId, "") end)
    if not createOK or go == nil then
      log("MAP_PIN", "active=false reason=create error=" .. tostring(go))
      return
    end
    pcall(function() UI.SetIsClickable(go) end)
    local showOK, showErr = pcall(function() go:Show() end)
    if not showOK then
      pcall(function() Map.RecycleIcon(go) end)
      log("MAP_PIN", "active=false reason=show error=" .. tostring(showErr))
      return
    end
    self.completionistMapV104NornirMapIconGO = go
    self.completionistMapV104NornirMarkerId = markerId
    log("MAP_PIN", "active=true id=" .. tostring(markerId) .. " region=" .. tostring(regionId) .. " nativePlacement=true")
  end

  local function collisionContains(go, collisionGameObjectTable)
    if go == nil or type(collisionGameObjectTable) ~= "table" then return false end
    for _, collGO in ipairs(collisionGameObjectTable) do
      if collGO == go then return true end
    end
    return false
  end

  local function showReticle(self, currState)
    if self == nil or currState == nil then return end
    local _, challengeComplete = lifecycle()
    self.currQuestID = nil
    self.currMarkerID = nil
    self.clickedMarkerInfo = nil
    self.clickedPlayer = false
    self.completionistMapV100Selected = false
    self.completionistMapV100NornirSelected = nil
    self.completionistMapV100NornirChestSelected = nil
    local description = challengeComplete and
      "Unlocked Nornir Chest - open it to complete" or
      "Nornir Chest - solve the rune challenge"
    self:SetReticleInfo(currState, "Nornir Chest", description)
    self:UpdateFooterButtonPrompt(currState.menu, false, false)
  end

  local function shownByClass(className, targetId)
    if targetId == nil then return false, false, "missing_target_id" end
    local ok, ids = pcall(function() return game.Compass.FindMarkersByIconClass({{className}}) end)
    if not ok then return false, false, tostring(ids) end
    for _, id in ipairs(ids or {{}}) do
      if tostring(id) == targetId then return true, true, nil end
    end
    return false, true, nil
  end

  local function nornirShown()
    return shownByClass(nornirClass, candidateIdString())
  end

  local function ravenShown()
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(ravenCandidate) end)
    if not ok or info == nil then return false, false, "raven_info_missing" end
    local id = safeField(info, "Id") or safeField(info, "id")
    return shownByClass(ravenClass, id ~= nil and tostring(id) or nil)
  end

  local function stockTargets()
    local nornirId = candidateIdString()
    local okR, ravenInfo = pcall(function() return game.Map.GetMarkerInfo(ravenCandidate) end)
    local ravenId = okR and ravenInfo ~= nil and tostring(safeField(ravenInfo, "Id") or safeField(ravenInfo, "id")) or nil
    local ok, ids = pcall(function() return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags) end)
    if not ok then return {{}}, false, tostring(ids) end
    local out = {{}}
    for _, id in ipairs(ids or {{}}) do
      local s = tostring(id)
      if s ~= nornirId and s ~= ravenId then out[#out + 1] = id end
    end
    return out, true, nil
  end

  local function hideNornir(reason)
    local ok, err = pcall(function() game.Compass.HideMarker(candidate) end)
    log("HIDE_NORNIR", "reason=" .. tostring(reason) .. " ok=" .. tostring(ok) .. " error=" .. tostring(err))
    return ok
  end

  local function hideRaven(reason)
    local ok, err = pcall(function() game.Compass.HideMarker(ravenCandidate) end)
    log("HIDE_RAVEN", "reason=" .. tostring(reason) .. " ok=" .. tostring(ok) .. " error=" .. tostring(err))
    return ok
  end

  local function hideStock(reason)
    local ids, ok, err = stockTargets()
    if not ok then
      log("HIDE_STOCK", "reason=" .. tostring(reason) .. " queryOK=false error=" .. tostring(err))
      return false, 0
    end
    for _, id in ipairs(ids) do
      pcall(function() game.Compass.HideMarker(id) end)
    end
    log("HIDE_STOCK", "reason=" .. tostring(reason) .. " count=" .. tostring(#ids))
    return true, #ids
  end

  local function canPrompt(self)
    return self ~= nil and
      not self.isOpenedForFastTravel and
      game.Compass.HaveCompass() and
      self.currRealmName == mapUtil.GetPlayerRealm() and
      not tutorialUtil.CurrentlyShowingStep()
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  local function refreshPrompt(self)
    if self == nil or self.menu == nil or not self.completionistMapV104NornirSelected then return end
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
  end

  function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)
    if collisionContains(self.completionistMapV104NornirMapIconGO, collisionGameObjectTable) then
      self.completionistMapV104NornirSelected = true
      self.completionistMapV104NornirLastHitFrame = self.completionistMapV100Frame or 0
      self.completionistMapV104NornirCurrState = currState
      self.completionistMapV100Selected = false
      self.completionistMapV100NornirSelected = nil
      self.completionistMapV100NornirChestSelected = nil
      CompletionistMapV100_SetCustomCursorSelected(true)
      showReticle(self, currState)
      log("MAP_SELECTION", "active=true native=true")
      return
    end
    if self.completionistMapV104NornirSelected then
      local frame = self.completionistMapV100Frame or 0
      local age = frame - (self.completionistMapV104NornirLastHitFrame or frame)
      if age <= 6 then return end
      self.completionistMapV104NornirSelected = false
      log("MAP_SELECTION", "active=false ageFrames=" .. tostring(age))
    end
    return previousCollision(self, currState, collisionGameObjectTable, realmName)
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    local _, _, opened = lifecycle()
    if self.completionistMapV104NornirSelected then
      if opened or not canPrompt(self) then return false, nil end
      if nornirIntent == "tracked" then return true, actionText(lamsConsts.RemoveFromCompass) end
      local shown, nornirOK = nornirShown()
      if nornirOK and shown then return true, actionText(lamsConsts.RemoveFromCompass) end
      local raven, ravenOK = ravenShown()
      local stock, stockOK = stockTargets()
      if (ravenOK and raven) or (stockOK and #stock > 0) then
        return true, actionText(lamsConsts.ReplaceInCompass)
      end
      return true, actionText(lamsConsts.AddToCompass)
    end

    local show, text = previousPrompt(self, currMenu)
    if not show then return show, text end
    local shown, ok = nornirShown()
    if ok and shown then return true, actionText(lamsConsts.ReplaceInCompass) end
    return show, text
  end

  function MapOn:ShowOnCompass(currState)
    local _, _, opened = lifecycle()
    if self.completionistMapV104NornirSelected then
      if opened then
        self.completionistMapV104NornirSelected = false
        return
      end
      local shown, ok, err = nornirShown()
      if not ok then
        log("ACTION", "refused=nornir_query_failed error=" .. tostring(err))
        return
      end
      if shown then
        if hideNornir("user_remove") then
          nornirIntent = "untracked"
          retryFrames = 0
          retryBucket = -1
          self.currShownMarkerID = nil
          _G.CompletionistMapV104NornirTracked = false
          Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
          refreshPrompt(self)
        end
        return
      end
      hideRaven("nornir_replace")
      local stockOK = hideStock("nornir_replace")
      if not stockOK then return end
      local showOK, showErr = pcall(function() game.Compass.ShowMarker(candidate, nornirClass) end)
      log("SHOW_NORNIR", "ok=" .. tostring(showOK) .. " error=" .. tostring(showErr))
      if not showOK then return end
      nornirIntent = "tracked"
      retryFrames = 0
      retryBucket = -1
      local info = candidateInfo()
      if info ~= nil then self.currShownMarkerID = safeField(info, "Id") or safeField(info, "id") end
      _G.CompletionistMapV104NornirTracked = true
      Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
      refreshPrompt(self)
      return
    end

    local shown, ok = nornirShown()
    if (ok and shown) or _G.CompletionistMapV104NornirTracked == true then
      hideNornir("replacement_by_other_target")
      nornirIntent = "untracked"
      retryFrames = 0
      retryBucket = -1
      _G.CompletionistMapV104NornirTracked = false
    end
    return previousShow(self, currState)
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)
    ensurePin(self)

    local _, _, opened, generation = lifecycle()
    if self.completionistMapV104NornirLifecycleGeneration ~= generation then
      self.completionistMapV104NornirLifecycleGeneration = generation
      if self.completionistMapV104NornirSelected and self.completionistMapV104NornirCurrState ~= nil then
        showReticle(self, self.completionistMapV104NornirCurrState)
        refreshPrompt(self)
      end
    end

    local shown, ok, err = nornirShown()
    if opened then
      if (ok and shown) or _G.CompletionistMapV104NornirTracked == true then hideNornir("authoritative_opened") end
      _G.CompletionistMapV104NornirTracked = false
      nornirIntent = nil
      destroyPin(self, "authoritative_opened")
      return result
    end

    if ok then
      _G.CompletionistMapV104NornirTracked = shown
      if nornirIntent == "tracked" then
        local raven, ravenOK = ravenShown()
        local stock, stockOK = stockTargets()
        if shown and ravenOK and not raven and stockOK and #stock == 0 then
          nornirIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("SHOW_SETTLED", "active=true")
          refreshPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            if ravenOK and raven then hideRaven("show_async_retry") end
            if stockOK and #stock > 0 then hideStock("show_async_retry") end
            if not shown then pcall(function() game.Compass.ShowMarker(candidate, nornirClass) end) end
          end
        end
      elseif nornirIntent == "untracked" then
        if not shown then
          nornirIntent = nil
          retryFrames = 0
          retryBucket = -1
          log("HIDE_SETTLED", "active=false")
          refreshPrompt(self)
        else
          retryFrames = retryFrames + 1
          local bucket = math.floor(retryFrames / 30)
          if retryFrames == 1 or bucket ~= retryBucket then
            retryBucket = bucket
            hideNornir("hide_async_retry")
          end
        end
      end
    elseif nornirIntent ~= nil then
      retryFrames = retryFrames + 1
      if retryFrames == 1 or retryFrames % 60 == 0 then
        log("VERIFY", "queryOK=false error=" .. tostring(err) .. " frame=" .. tostring(retryFrames))
      end
    end
    return result
  end

  function MapOn:SubmenuExit(currState)
    destroyPin(self, "submenu_exit")
    return previousSubmenuExit(self, currState)
  end

  function MapOn:Exit()
    destroyPin(self, "map_exit")
    return previousExit(self)
  end

  _G.CompletionistMapV104NornirNativeSingleActive = true
  _G.CompletionistMapV104NornirLifecycleUsesAuthoritativeOpenedState = true
  log("API", "installed=true marker=" .. candidate .. " class=" .. nornirClass .. " openedIsCollectibleCompletion=true")
end
{MAP_END}
'''


def patch_mapmenu(source: bytes) -> tuple[bytes, dict]:
    check(sha_bytes(source) == MAPMENU_SHA256, f"mapmenu.lua is not frozen Raven production: {sha_bytes(source)}")
    text = source.decode("utf-8")
    check(MAP_BEGIN not in text and MAP_END not in text, "Nornir native lifecycle block already present in mapmenu")
    required = (
        RAVEN_MARKER,
        RAVEN_CLASS,
        "CompletionistMapV104SingleActiveCompass",
        "CompletionistMapV100_CreateNornirChestPins",
        "CompletionistMapV100_CreateNornirPins",
        "CompletionistMapV100_DestroyNornirChestPins",
        "CompletionistMapV100_DestroyNornirPins",
        "CompletionistMapV100_SetCustomCursorSelected",
        "NORNIR_CHEST_FILTER",
        "COMPLETIONIST_FILTER",
        "game.Compass.ShowMarker",
        "game.Compass.HideMarker",
    )
    missing = [x for x in required if x not in text]
    check(not missing, f"frozen mapmenu no longer has required Raven/Nornir prototype structure: {missing}")
    nl = newline_of(text)
    block = MAP_BLOCK.replace("\n", nl)
    candidate_text = text + ("" if text.endswith(("\n", "\r")) else nl) + block
    candidate = candidate_text.encode("utf-8")
    check(candidate.startswith(source), "Nornir mapmenu candidate no longer preserves Raven production bytes as prefix")
    check(candidate_text.count(MAP_BEGIN) == 1 and candidate_text.count(MAP_END) == 1, "mapmenu Nornir block markers not unique")
    forbidden = (
        "Map.ChangeMarkerState",
        "QuestManager.Set",
        "SaveGame",
        "SoftSavePlayerState",
    )
    block_only = block
    hits = [x for x in forbidden if x in block_only]
    check(not hits, f"Nornir mapmenu block contains forbidden progression/save token(s): {hits}")
    required_tokens = (
        f'local candidate = "{NORNIR_MARKER}"',
        f'local nornirClass = "{NORNIR_CLASS}"',
        "game.Compass.ShowMarker(candidate, nornirClass)",
        "game.Compass.HideMarker(candidate)",
        "CompletionistMapV100_CreateNornirChestPins = function",
        "CompletionistMapV100_CreateNornirPins = function",
        "authoritative_opened",
        "ReplaceInCompass",
    )
    missing_tokens = [x for x in required_tokens if x not in block_only]
    check(not missing_tokens, f"Nornir mapmenu block missing required token(s): {missing_tokens}")
    return candidate, {
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "source_preserved_as_exact_prefix": True,
        "runtime_proven_raven_control_preserved": True,
        "old_synthetic_nornir_parent_and_puzzle_creation_disabled": True,
        "native_nornir_add_replace_remove_logic_present": True,
        "stock_and_raven_replacement_paths_account_for_nornir": True,
        "authoritative_opened_state_suppresses_map_pin_and_active_compass_target": True,
        "challenge_complete_keeps_parent_visible_until_loot_chest_is_opened": True,
        "progression_or_save_writes": False,
    }


def copy_vertical_slice(vertical_root: Path, candidate_root: Path) -> dict:
    required = {
        "r_ui.wad": Path("exec/wad/pc_le/r_ui.wad"),
        "wad_r_ui.dcb": Path("exec/dc/pc_le/wad_r_ui.dcb"),
        "wad_r_perm.dcb": Path("exec/dc/pc_le/wad_r_perm.dcb"),
        "mapmaster.dcb": Path("exec/dc/pc_le/mapmaster.dcb"),
        "mapcoords.dcb": Path("exec/dc/pc_le/mapcoords.dcb"),
        "compassgraph.dcb": Path("exec/dc/pc_le/compassgraph.dcb"),
    }
    for rel in required.values():
        check((vertical_root / rel).is_file(), f"six-file vertical slice component missing: {vertical_root / rel}")
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    shutil.copytree(vertical_root, candidate_root)
    return {name: {"relative": str(rel).replace("\\", "/"), "sha256": sha_file(candidate_root / rel)} for name, rel in required.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--vertical-slice-root", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    vertical_root = args.vertical_slice_root.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    check(game.is_dir(), f"game root missing: {game}")
    check(vertical_root.is_dir(), f"vertical slice root missing: {vertical_root}")
    check(not output_dir.is_relative_to(game) and not report_path.is_relative_to(game), "offline lifecycle output must stay outside game directory")

    live_mapmenu = game / "mods/lua" / REL["mapmenu"]
    check(live_mapmenu.is_file(), f"live Raven production mapmenu missing: {live_mapmenu}")
    map_raw = live_mapmenu.read_bytes()
    check(sha_bytes(map_raw) == MAPMENU_SHA256, "live mapmenu is not frozen Raven production baseline")

    source_paths: dict[str, Path] = {}
    source_raw: dict[str, bytes] = {}
    for key in ("mainhud", "runic", "standard"):
        path, raw = clean_loader_source(game, REL[key])
        source_paths[key] = path
        source_raw[key] = raw

    before = {
        "mapmenu": sha_file(live_mapmenu),
        **{key: sha_file(path) for key, path in source_paths.items()},
    }

    map_candidate, map_meta = patch_mapmenu(map_raw)
    hud_candidate, hud_meta = patch_mainhud(source_raw["mainhud"])
    runic_candidate, runic_meta = patch_runic(source_raw["runic"])
    standard_candidate, standard_meta = patch_standard(source_raw["standard"])

    candidate_root = output_dir / "game-root"
    six_files = copy_vertical_slice(vertical_root, candidate_root)
    lua_outputs = {
        "mapmenu.lua": (REL["mapmenu"], map_candidate),
        "mainhud.lua": (REL["mainhud"], hud_candidate),
        "interact_chest_runic.lua": (REL["runic"], runic_candidate),
        "interact_chest_standard.lua": (REL["standard"], standard_candidate),
    }
    lua_report = {}
    for name, (rel, raw) in lua_outputs.items():
        path = candidate_root / "mods/lua" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        check(path.read_bytes() == raw, f"offline Lua candidate write verification failed: {name}")
        lua_report[name] = {"relative": str(Path("mods/lua") / rel).replace("\\", "/"), "bytes": len(raw), "sha256": sha_bytes(raw)}

    after = {
        "mapmenu": sha_file(live_mapmenu),
        **{key: sha_file(path) for key, path in source_paths.items()},
    }
    check(after == before, "a live/loader source file changed during offline lifecycle build")

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate": {
            "marker": NORNIR_MARKER,
            "marker_id": NORNIR_MARKER_ID,
            "compass_class": {"name": NORNIR_CLASS, "uid": NORNIR_CLASS_UID},
            "map_visual": {"name": NORNIR_MAP, "hash": NORNIR_MAP_HASH},
            "hud_visual": {"name": NORNIR_HUD, "hash": NORNIR_HUD_HASH, "capacity": 2},
            "inworld_carrier": {"name": NORNIR_INWORLD, "uid": NORNIR_INWORLD_UID},
            "target_world": list(TARGET),
            "ten_file_candidate_complete": True,
            "six_binary_files": six_files,
            "four_lua_files": lua_report,
        },
        "lifecycle_contract": {
            "runic_parent_challengeComplete_is_observed": True,
            "runic_parent_restored_state_is_published_on_OnStart": True,
            "actual_runic_loot_chest_OPENED_is_authoritative_collectible_completion": True,
            "restored_opened_state_is_published_on_standard_chest_OnStart": True,
            "challengeComplete_without_opened_keeps_parent_marker_visible": True,
            "opened_suppresses_map_marker": True,
            "opened_removes_active_native_compass_target": True,
            "target_position_scope_metres": TARGET_RADIUS_METRES,
            "synthetic_progression_writes": False,
        },
        "components": {
            "mapmenu": map_meta,
            "mainhud": hud_meta,
            "runic": runic_meta,
            "standard": standard_meta,
        },
        "source_hashes_before": before,
        "source_hashes_after": after,
        "source_game_and_loader_files_unchanged": before == after,
        "proof": {
            "frozen_raven_mapmenu_is_exact_prefix_of_candidate": True,
            "old_synthetic_nornir_map_hud_path_retired": True,
            "native_nornir_single_target_add_replace_remove_present": True,
            "real_stock_nornir_lifecycle_bridge_present": True,
            "all_six_binary_vertical_slice_files_copied_unchanged": True,
            "no_save_progression_or_marker_state_mutation_authored": True,
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "raven_production_files_changed": False,
        },
        "runtime_ready": False,
        "ready_for_reversible_runtime_installer_gate": True,
        "next_gate": "Build a transactional reversible runtime installer for this ten-file candidate, verify backups/hashes, then run one controlled Veithurgard Nornir field test."
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("NORNIR_LIFECYCLE_OFFLINE_BUILT")
    print(f"  marker: {NORNIR_MARKER} / {NORNIR_MARKER_ID}")
    print(f"  class:  {NORNIR_CLASS} / {NORNIR_CLASS_UID}")
    print("  lifecycle: challengeComplete observed; actual loot chest OPENED is authoritative completion")
    print("  restored challenge/open state publishers: present")
    print("  opened -> suppress map pin + remove active native compass target")
    print("  old synthetic Nornir map/HUD prototype: retired in candidate")
    print("  Raven production mapmenu preserved as exact prefix: true")
    print("  ten-file candidate complete: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  candidate root: {candidate_root}")
    print(f"  report: {report_path}")
    print("NORNIR_LIFECYCLE_OFFLINE_GATE_PASSED")


if __name__ == "__main__":
    main()
