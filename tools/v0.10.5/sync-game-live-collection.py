#!/usr/bin/env python3
"""Synchronize robust live collectible observation and compass clearing across all collectible families.

Ensures:
1. When interacting/looting in 3D world (Artefacts, Realm Tears, Chests, Shrines, Digs, Lore Runes/Scrolls),
   the active custom compass marker (class 'SIDE') is immediately cleared in real time without save reload.
2. The dirty event hook ('COMPLETIONIST_COLLECTIBLE_DIRTY_V1') triggers runtime:Poll() in mapmenu.lua
   to synchronize direct observations and clear the tracked target in UI state.
3. mapmenu.lua directly queries wallet resources and quests for all 45 Artefacts, hiding collected pins
   instantly from the 3D map menu.
4. Loaded reader provides fast direct script lookup and state extraction for Artefacts.
"""
from __future__ import annotations
from pathlib import Path
import sys
import lupa
from lupa.lua51 import LuaRuntime

GAME_ROOT = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar")
GAME_MAP = GAME_ROOT / "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
MODULES = GAME_ROOT / "mods/lua/gameart/scripts/levels/gameplaymodules"

def compile_lua(code: str, name: str) -> None:
    lua = LuaRuntime(unpack_returned_tuples=True)
    try:
        lua.compile(code)
    except Exception as exc:
        raise RuntimeError(f"Lua compilation failed for {name}: {exc}") from exc

def patch_mapmenu() -> bool:
    if not GAME_MAP.exists():
        print(f"Error: {GAME_MAP} does not exist.")
        return False

    text = GAME_MAP.read_text(encoding="utf-8")
    original = text

    # Backup
    bak = GAME_MAP.with_suffix(".lua.bak_live_collection")
    if not bak.exists():
        bak.write_text(original, encoding="utf-8")
        print(f"Created backup: {bak}")

    # 1. LOADED MODULE: observeScript artefact handling
    if "adapter == 'artefact'" not in text:
        target = "  elseif adapter == 'dig' then"
        replacement = """  elseif adapter == 'artefact' then
    if type(script.GetState) == 'function' then
      local ok, st = pcall(script.GetState)
      if ok and type(st) == 'number' then
        return st == 3 and 'collected' or 'remaining'
      end
    end
    if type(script.IsAcquired) == 'function' then
      local ok, acq = pcall(script.IsAcquired)
      if ok and type(acq) == 'boolean' then
        return acq and 'collected' or 'remaining'
      end
    end
  elseif adapter == 'dig' then"""
        if text.count(target) == 1:
            text = text.replace(target, replacement, 1)
            print("  [mapmenu] Injected observeScript for artefact")
        else:
            print("  [mapmenu] Warning: observeScript anchor not found or not unique")

    # 2. LOADED MODULE: read(row) owner fallback for artefact
    target_fallback = "if (row.adapter == 'chest' or row.adapter == 'rift') and #oMatches == 0 then"
    replacement_fallback = "if (row.adapter == 'chest' or row.adapter == 'rift' or row.adapter == 'artefact') and #oMatches == 0 then"
    if target_fallback in text:
        text = text.replace(target_fallback, replacement_fallback, 1)
        print("  [mapmenu] Injected owner fallback for artefact")

    # 3. LOADED MODULE: step 6 fast direct lookup for artefact scripts
    if "-- 6. Fast direct lookup for artefact scripts" not in text:
        target_step6 = "  -- 5. Fast direct lookup for rift scripts under placement or owner"
        # Find where step 5 finishes (return nil at end of read)
        # In mapmenu, step 5 ends with a return nil or another block
        target_end_step5 = """              if node.Child then
                st = observeScript(node.Child, row.adapter)
                if st ~= nil then return st end
              end
            end
          end
        end
      end
    end
  end

  return nil"""

        replacement_step6 = """              if node.Child then
                st = observeScript(node.Child, row.adapter)
                if st ~= nil then return st end
              end
            end
          end
        end
      end
    end
  end

  -- 6. Fast direct lookup for artefact scripts under placement or owner
  if row.adapter == 'artefact' then
    local containers = {owner, placement}
    if owner ~= nil and owner.Parent ~= nil then
      containers[#containers + 1] = owner.Parent
    end
    if placement ~= nil and placement.Parent ~= nil then
      containers[#containers + 1] = placement.Parent
    end
    for _, container in ipairs(containers) do
      if container ~= nil and type(container.FindSingleGOByName) == 'function' then
        for _, q in ipairs({'goartifactscript', 'artifactscript', '*artifact*'}) do
          local ok, node = pcall(container.FindSingleGOByName, container, q)
          if ok and node ~= nil then
            local st = observeScript(node, row.adapter)
            if st ~= nil then return st end
            if node.Child then
              st = observeScript(node.Child, row.adapter)
              if st ~= nil then return st end
            end
          end
        end
      end
      if container ~= nil and type(container.FindGOsByName) == 'function' then
        for _, q in ipairs({'goartifactscript', 'artifactscript', '*artifact*'}) do
          local ok, nodes = pcall(container.FindGOsByName, container, q)
          if ok and type(nodes) == 'table' then
            for _, node in ipairs(nodes) do
              local st = observeScript(node, row.adapter)
              if st ~= nil then return st end
              if node.Child then
                st = observeScript(node.Child, row.adapter)
                if st ~= nil then return st end
              end
            end
          end
        end
      end
    end
  end

  return nil"""
        if text.count(target_end_step5) == 1:
            text = text.replace(target_end_step5, replacement_step6, 1)
            print("  [mapmenu] Injected Step 6 fast direct lookup for artefact")
        else:
            print("  [mapmenu] Warning: step 5 end anchor not found or not unique")

    # 4. HOOK DISPATCH: update COMPLETIONIST_COLLECTIBLE_DIRTY_V1 handler to poll runtime
    target_hook = "if level then runtime.loaded:Poll(level:lower()) end"
    replacement_hook = "if level then if runtime.loaded then runtime.loaded:Poll(level:lower()) end; if runtime then runtime:Poll() end end"
    if target_hook in text:
        text = text.replace(target_hook, replacement_hook, 1)
        print("  [mapmenu] Updated dirty hook to invoke runtime:Poll()")

    # 5. LOCATION MAP: artefactResources table definition
    if "local artefactResources = {" not in text:
        target_art_tbl = "  local function isDirectlyCollected(row)"
        art_tbl_code = """  local artefactResources = {
    ["artefact_707ae0e24dc7bc9a56c19eb7ce17b351"] = "AlfheimArtifact01",
    ["artefact_56c4354a4141de7afc7f2e8447ab8767"] = "AlfheimArtifact02",
    ["artefact_5bf15dbc48613f5b548fd2a673d8f7bc"] = "AlfheimArtifact03",
    ["artefact_6e3739ea4ac8107c495a61af774a9b03"] = "AlfheimArtifact04",
    ["artefact_0d53040849957335c6db68809206f5d1"] = "AlfheimArtifact05",
    ["artefact_eb672a1647b1f7e64595e48f821670f5"] = "BroochRay",
    ["artefact_hel300mainbridgewad00c124ebae0bc24f8b64cc6305246b22"] = "BroochRuby",
    ["artefact_hel300mainbridgewadb5b33ffb0d723f44a135047d5a839e32"] = "BroochRuby",
    ["artefact_hel300mainbridgewade4b6326ae64d514490a45593d471478f"] = "BroochRuby",
    ["artefact_c7f91ac1447cff68599696bbbb58e7b7"] = "BroochAnimal",
    ["artefact_7d8a35dc4d6aabf8065e1ead0c470fcc"] = "ShipGoldHook2",
    ["artefact_5bb11ed5419b42caba813598d29ca473"] = "ShipTongue",
    ["artefact_01a8ba24409b5fb49a1c18b43669fe44"] = "ShipSeaHorse",
    ["artefact_379728fc47e4a966be1fc9926011184b"] = "ShipHook",
    ["artefact_6cffc9884efa77b424baf987adfdba6a"] = "ShipHook",
    ["artefact_4a3d314942f187f69ee5b78302e118fe"] = "ShipHook2",
    ["artefact_f7fbfc3f44991b3da37871879e6de737"] = "ShipHook2",
    ["artefact_989065ff4bde64f5ec957da2759037cb"] = "LostToyTroll",
    ["artefact_c9b7e23040c21e2da5fe8ba4be8ad415"] = "NorseMaskGoat",
    ["artefact_bd9a46a34b8fd4660be2129e27fa4004"] = "ShipGoldHook",
    ["artefact_a0588a9442f0118bdce0cda751b8605d"] = "LostToyBoat",
    ["artefact_ab662cc14c4a21327111dea1a34b96c3"] = "LostToyHorse",
    ["artefact_8916f55c4511b74ba8601ba7ef3d86bb"] = "LostToySpearGuy",
    ["artefact_fda837834b361579d4a29194810c3d09"] = "ShipDragon",
    ["artefact_fae85e594ef79ee2e204719767dd5287"] = "CupDragon",
    ["artefact_6f83c0ef48eda412050135a827d51a7a"] = "CupPintGlass",
    ["artefact_33f59ee746f63f40199e5f90cad3c236"] = "CupHandle",
    ["artefact_b52df62545c16741e6f2278f9e2ccc32"] = "CupGoblet",
    ["artefact_b18794364cc6b6a5c08596ab8699f35b"] = "CupFeet",
    ["artefact_f5bd8953457f9662d074d798a111abfc"] = "CupHolyGrail",
    ["artefact_0a43e4954d4fff46abb9ca8e34d875c0"] = "NorseMaskFlatBeard",
    ["artefact_85c29c2b420306564c28b5b09e22532c"] = "NorseMaskReptile",
    ["artefact_0da7cb9744da59cb80fe319d95cada55"] = "NorseMaskCurlyBeard",
    ["artefact_6fa420df406be3d033b7eea35a4d10fe"] = "NorseMaskTiki",
    ["artefact_468c195b480889e354742b876aef3a11"] = "NorseMaskMustache",
    ["artefact_28b7fe1349cdc49da573c6a0657f0a9d"] = "NorseMaskStoneFace",
    ["artefact_cf7627ad486711d9eab3339782e5a147"] = "NorseMaskStraightBeard",
    ["artefact_fa511e0a422421b7acc01fa5829c4fe3"] = "NorseMaskGhoul",
    ["artefact_xpl200funeralwad2768cb29f445634bb075f7a858cabcc3"] = "HornUShape",
    ["artefact_xpl200funeralwad52e9ebf8ef1b3343b5d025a73ad6fa91"] = "HornUShape",
    ["artefact_xpl200funeralwadb6e2b2a41a1b3e4c9ff1f8e5f877039a"] = "HornUShape",
    ["artefact_xpl200funeralwadbb9465a7407c9849bf891e0205dac801"] = "HornUShape",
    ["artefact_xpl250funeralinteriorwad3f176e49e0a0cd4f8cf59ada5fe9c2d8"] = "HornHorse",
    ["artefact_xpl250funeralinteriorwad4813767722fa414b9a3d4972dc8874e7"] = "HornHorse",
  }

  local function isDirectlyCollected(row)"""
        if text.count(target_art_tbl) == 1:
            text = text.replace(target_art_tbl, art_tbl_code, 1)
            print("  [mapmenu] Injected artefactResources mapping table")
        else:
            print("  [mapmenu] Warning: isDirectlyCollected header anchor not unique")

    # 6. LOCATION MAP: isDirectlyCollected artefact branch
    if 'fam == "artefact"' not in text:
        target_col_end = """      if (cid == "realm_tear_10374be1dacc7b5afc9b38ff1c50b3f5" or
          cid == "realm_tear_80a81219135f07ea1c0eb1948748fc58" or
          cid == "realm_tear_ad3009f9f80b31ab80419fd380e60c1c") and
         type(game.Wallets) == "table" then
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", "NiflheimTrophyTracker")
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", "NiflheimTrophyTracker")
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and res2 == true then return true end
        end
      end
    end
    return false"""

        replacement_col_end = """      if (cid == "realm_tear_10374be1dacc7b5afc9b38ff1c50b3f5" or
          cid == "realm_tear_80a81219135f07ea1c0eb1948748fc58" or
          cid == "realm_tear_ad3009f9f80b31ab80419fd380e60c1c") and
         type(game.Wallets) == "table" then
        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", "NiflheimTrophyTracker")
          if ok and type(val) == "number" and val > 0 then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and type(val2) == "number" and val2 > 0 then return true end
        end
        if type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", "NiflheimTrophyTracker")
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", "NiflheimTrophyTracker")
          if ok2 and res2 == true then return true end
        end
      end
    elseif fam == "artefact" then
      local ar = artefactResources[cid]
      if ar and type(game.Wallets) == "table" then
        local threshold = 1
        if ar == "HornUShape" then threshold = 4
        elseif ar == "BroochRuby" then threshold = 3
        elseif ar == "HornHorse" or ar == "ShipHook" or ar == "ShipHook2" then threshold = 2 end

        if type(game.Wallets.GetResourceValue) == "function" then
          local ok, val = pcall(game.Wallets.GetResourceValue, "HERO", ar)
          if ok and type(val) == "number" and val >= threshold then return true end
          local ok2, val2 = pcall(game.Wallets.GetResourceValue, "HERO_SAVEONLY", ar)
          if ok2 and type(val2) == "number" and val2 >= threshold then return true end
        end
        if threshold == 1 and type(game.Wallets.HasResource) == "function" then
          local ok, res = pcall(game.Wallets.HasResource, "HERO", ar)
          if ok and res == true then return true end
          local ok2, res2 = pcall(game.Wallets.HasResource, "HERO_SAVEONLY", ar)
          if ok2 and res2 == true then return true end
        end
      end
      if type(game.QuestManager) == "table" and type(game.QuestManager.GetQuestState) == "function" then
        local questMap = {
          Alfheim = "Quest_Artifacts_Alfheim",
          Brooch = "Quest_Artifacts_Brooches",
          Cup = "Quest_Artifacts_OrnateCups",
          Horn = "Quest_Artifacts_VikingHorns",
          Mask = "Quest_Artifacts_NorseMasks",
          Ship = "Quest_Artifacts_ShipHeads",
          Toy = "Quest_Artifacts_LostToys",
        }
        if ar then
          for prefix, qName in pairs(questMap) do
            if ar:find("^" .. prefix) or (prefix == "Ship" and ar:find("^Ship")) or (prefix == "Toy" and ar:find("^LostToy")) or (prefix == "Mask" and ar:find("^NorseMask")) then
              local ok, st = pcall(game.QuestManager.GetQuestState, qName)
              if ok and st == "Complete" then return true end
              local ok2, st2 = pcall(game.QuestManager.GetQuestState, qName .. "_Parent")
              if ok2 and st2 == "Complete" then return true end
            end
          end
        end
      end
    end
    return false"""
        if text.count(target_col_end) == 1:
            text = text.replace(target_col_end, replacement_col_end, 1)
            print("  [mapmenu] Injected fam == 'artefact' check in isDirectlyCollected")
        else:
            print("  [mapmenu] Warning: isDirectlyCollected end anchor not unique")

    compile_lua(text, "mapmenu.lua")
    GAME_MAP.write_text(text, encoding="utf-8")
    print(f"  [mapmenu] Successfully updated {GAME_MAP} ({len(text):,} bytes)")
    return True

def patch_gameplay_script(rel_path: str, block_replacement: str) -> bool:
    target_path = MODULES / rel_path
    if not target_path.exists():
        print(f"Error: {target_path} does not exist.")
        return False

    text = target_path.read_text(encoding="utf-8")
    obs_marker = "-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION"
    if obs_marker not in text:
        print(f"Error: {obs_marker} not found in {rel_path}")
        return False

    prefix = text.split(obs_marker, 1)[0]
    new_text = prefix + block_replacement.strip() + "\n"

    compile_lua(new_text, rel_path)
    target_path.write_text(new_text, encoding="utf-8")
    print(f"  [{rel_path}] Successfully updated ({len(new_text):,} bytes)")
    return True

# 1. ARTEFACT
ARTEFACT_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function GetState()
    return state
  end
  function IsAcquired()
    return state == states.ACQUIRED
  end
  function CompletionistCollectibleObserve()
    if type(state) ~= "number" or state < 1 or state > 3 or state ~= math.floor(state) then return nil end
    local collected = state == 3
    return "artefact", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    clearActiveCompassMarker()
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(LuaHook_GiveLoot) == "function" then LuaHook_GiveLoot = wrap(LuaHook_GiveLoot) end
  if type(IncrementCounter) == "function" then IncrementCounter = wrap(IncrementCounter) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 2. REALM TEAR (POCKET RIFT)
RIFT_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function GetState()
    return hasOpened and 4 or 0
  end
  function HasOpened()
    return hasOpened
  end
  function CompletionistCollectibleObserve()
    if type(hasOpened) ~= "boolean" then return nil end
    local collected = hasOpened
    return "rift", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if hasOpened then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(OnInteractFinish) == "function" then OnInteractFinish = wrap(OnInteractFinish) end
  if type(LuaHook_GivePockeRiftLoot) == "function" then LuaHook_GivePockeRiftLoot = wrap(LuaHook_GivePockeRiftLoot) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 3. CHEST (STANDARD, LEGENDARY, COFFIN, CIPHER, NORNIR OPEN)
CHEST_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function CompletionistCollectibleObserve()
    if type(state) ~= "number" or state < 1 or state > 4 or state ~= math.floor(state) then return nil end
    local collected = state == 4
    return "chest", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if state == states.OPENED then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(OnOpened) == "function" then OnOpened = wrap(OnOpened) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 4. JOTNAR SHRINE (TRIPTYCH)
SHRINE_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function IsTriptychCompleted()
    return triptychCompleted
  end
  function GetState()
    return triptychCompleted and 1 or 0
  end
  function CompletionistCollectibleObserve()
    if type(triptychCompleted) ~= "boolean" then return nil end
    local collected = triptychCompleted
    if collected then
      if type(journalUpdateID) ~= "string" or journalUpdateID == "" then return nil end
      collected = game.Wallets.HasResource("HERO", journalUpdateID) == true
    end
    return "shrine", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if triptychCompleted then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(UpdateJournal) == "function" then UpdateJournal = wrap(UpdateJournal) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 5. TREASURE DIG
DIG_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function GetState()
    return state
  end
  function CompletionistCollectibleObserve()
    if type(state) ~= "number" or state < 1 or state > 3 or state ~= math.floor(state) then return nil end
    local collected = state == 3
    if collected then
      if type(questName) ~= "string" or questName == "" then return nil end
      collected = game.QuestManager.GetQuestState(questName) == "Complete"
    end
    return "dig", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if state == states.ACQUIRED then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(UpdateQuest) == "function" then UpdateQuest = wrap(UpdateQuest) end
  if type(AwardLoot) == "function" then AwardLoot = wrap(AwardLoot) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 6. LORE MARKER (RUNE READ)
RUNE_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function IsComplete()
    return mapSummaryComplete
  end
  function CompletionistCollectibleObserve()
    if type(mapSummaryComplete) ~= "boolean" then return nil end
    local collected = mapSummaryComplete
    return "lore", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if mapSummaryComplete then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(UpdateJournal) == "function" then UpdateJournal = wrap(UpdateJournal) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

# 7. LANGUAGE SCROLL / TREASURE MAP PICKUP
PICKUP_BLOCK = """-- BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION
do
  function IsCollected()
    return collected
  end
  function CompletionistCollectibleObserve()
    if type(collected) ~= "boolean" then return nil end
    local collected = collected
    return "pickup", collected and "collected" or "remaining"
  end
  local function clearActiveCompassMarker()
    pcall(function()
      if type(game) == "table" and type(game.Compass) == "table" and type(game.Compass.FindMarkersByIconClass) == "function" then
        local markers = game.Compass.FindMarkersByIconClass({"SIDE"})
        if type(markers) == "table" then
          for _, id in ipairs(markers) do
            pcall(game.Compass.HideMarker, id)
          end
        end
      end
    end)
  end
  local function notify()
    if collected then
      clearActiveCompassMarker()
    end
    if thisLevel == nil or type(thisLevel.Name) ~= "string" then return end
    engine.SendHook("COMPLETIONIST_COLLECTIBLE_DIRTY_V1", engine.GetUIWad(),
      "COLLECTIBLE_DIRTY_V1\t" .. string.lower(thisLevel.Name))
  end
  local function pack(...) return {n=select('#',...), ...} end
  local unpackValues = unpack or table.unpack
  local function wrap(original)
    return function(...)
      local result = pack(original(...))
      pcall(notify)
      return unpackValues(result, 1, result.n)
    end
  end
  if type(InteractComplete) == "function" then InteractComplete = wrap(InteractComplete) end
  if type(UpdateJournal) == "function" then UpdateJournal = wrap(UpdateJournal) end
  if type(OnStart) == "function" then OnStart = wrap(OnStart) end
  if type(OnRestoreCheckpoint) == "function" then OnRestoreCheckpoint = wrap(OnRestoreCheckpoint) end
end
-- END COMPLETIONIST COLLECTIBLE OBSERVATION"""

def main():
    print("=== SYNCHRONIZING LIVE GAME COLLECTION FIXES ===")
    print(f"Target Game Root: {GAME_ROOT}")

    print("\n[1/8] Patching Map Menu (mapmenu.lua)...")
    patch_mapmenu()

    print("\n[2/8] Patching Artefact Interaction (interact_loot_artifact.lua)...")
    patch_gameplay_script("progression/interact_loot_artifact.lua", ARTEFACT_BLOCK)

    print("\n[3/8] Patching Realm Tear Interaction (interact_loot_pocketrift.lua)...")
    patch_gameplay_script("progression/interact_loot_pocketrift.lua", RIFT_BLOCK)

    print("\n[4/8] Patching Chest Interaction (interact_chest_standard.lua)...")
    patch_gameplay_script("progression/interact_chest_standard.lua", CHEST_BLOCK)

    print("\n[5/8] Patching Jotnar Shrine Interaction (interact_triptych.lua)...")
    patch_gameplay_script("interactive/triptychs/interact_triptych.lua", SHRINE_BLOCK)

    print("\n[6/8] Patching Treasure Dig Interaction (interact_loot_dirtdig.lua)...")
    patch_gameplay_script("progression/interact_loot_dirtdig.lua", DIG_BLOCK)

    print("\n[7/8] Patching Lore Marker Rune Read (langcheckruneread.lua)...")
    patch_gameplay_script("soninteracts/langcheckruneread.lua", RUNE_BLOCK)

    print("\n[8/8] Patching Language Scroll Pickup (sonlanguagepickup.lua)...")
    patch_gameplay_script("soninteracts/sonlanguagepickup.lua", PICKUP_BLOCK)

    print("\n=== ALL FILES SUCCESSFULLY PATCHED AND COMPILED ===")

if __name__ == "__main__":
    main()
