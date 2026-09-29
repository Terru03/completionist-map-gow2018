#!/usr/bin/env python3
"""Synchronize compass highlight glow and rapid toggle prompt synchronization into game mapmenu.lua."""
from pathlib import Path
import shutil
import sys

GAME_MAP = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua")

def sync():
    if not GAME_MAP.exists():
        print(f"Error: {GAME_MAP} does not exist.")
        sys.exit(1)

    text = GAME_MAP.read_text(encoding="utf-8")
    original_text = text

    # Backup
    backup_path = GAME_MAP.with_suffix(".lua.bak_glow_prompt")
    if not backup_path.exists():
        backup_path.write_text(original_text, encoding="utf-8")
        print(f"Created backup at {backup_path}")

    # =========================================================================
    # 1. ALL RAVENS BLOCK
    # =========================================================================
    
    # 1a. Forward declaration
    t1_old = "  local suppressLegacyRavenHud = nil\n  local nativeBoundaryEpoch ="
    t1_new = "  local suppressLegacyRavenHud = nil\n  local updateHighlights = nil\n  local nativeBoundaryEpoch ="
    assert text.count(t1_old) == 1, f"Raven 1a anchor count: {text.count(t1_old)}"
    text = text.replace(t1_old, t1_new, 1)

    # 1b. Export Raven target query & release functions
    t1b_old = "  local function collisionSelection(self, collisionTable)"
    t1b_new = """  _G.CompletionistMapV105GetRavenTargetName = function()
    local id = _G.CompletionistMapV105TrackedCatalogueId
    local row = id and byCatalogueId[id]
    return row and row.Name or nil
  end
  _G.CompletionistMapV105HasRavenCompassTarget = function()
    return _G.CompletionistMapV105TrackedCatalogueId ~= nil
  end
  _G.CompletionistMapV105ReleaseRavenCompass = function()
    if _G.CompletionistMapV105TrackedCatalogueId ~= nil then
      local row = byCatalogueId[_G.CompletionistMapV105TrackedCatalogueId]
      if row ~= nil then
        pcall(function() game.Compass.HideMarker(row.Name) end)
      end
      _G.CompletionistMapV105TrackedCatalogueId = nil
      promptIntent = nil
      customCompassOwnsTarget = false
      if lastMapOnSelf and type(lastMapOnSelf.UpdateMapMarkerHighlights) == "function" then
        pcall(lastMapOnSelf.UpdateMapMarkerHighlights, lastMapOnSelf)
      end
    end
    return true
  end

  local function collisionSelection(self, collisionTable)"""
    assert text.count(t1b_old) == 1, f"Raven 1b anchor count: {text.count(t1b_old)}"
    text = text.replace(t1b_old, t1b_new, 1)

    # 1c. updateHighlights definition and promptText update
    t1c_old = """  local function promptText(selected)
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
        if hasOtherCustom or (stockOK and hasOther(stock, selected.IdString)) then
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
  end"""

    t1c_new = """  updateHighlights = function(targetMap)
    local target = targetMap or lastMapOnSelf
    if target == nil or type(UI) ~= "table" or type(UI.Anim) ~= "function" then return end
    local trackedId = _G.CompletionistMapV105TrackedCatalogueId
    local trackedRow = trackedId and byCatalogueId[trackedId]
    local trackedName = trackedRow and trackedRow.Name or nil
    for name, icon in pairs(target.completionistMapV105RavenIcons or {}) do
      if trackedName ~= nil and name == trackedName then
        pcall(UI.Anim, icon, 10, "", 1)
      else
        pcall(UI.Anim, icon, 0, "", 0, 0)
      end
    end
  end

  local function promptText(selected)
    if selected == nil then return actionText(lamsConsts.AddToCompass) end
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
        if hasOtherCustom or (stockOK and hasOther(stock, selected.IdString)) or
            (_G.CompletionistMapV105HasLocationCompassTarget and _G.CompletionistMapV105HasLocationCompassTarget()) or
            (_G.CompletionistMapV105HasNornirCompassTarget and _G.CompletionistMapV105HasNornirCompassTarget()) then
          return actionText(lamsConsts.ReplaceInCompass)
        end
        return actionText(lamsConsts.AddToCompass)
      end
    end
    if _G.CompletionistMapV105TrackedCatalogueId == selected.CatalogueId then
      return actionText(lamsConsts.RemoveFromCompass)
    end
    local ids, ok = customIds()
    if ok and contains(ids, selected.IdString) then
      return actionText(lamsConsts.RemoveFromCompass)
    end
    local hasOther = false
    if _G.CompletionistMapV105TrackedCatalogueId ~= nil then
      hasOther = true
    elseif type(_G.CompletionistMapV105HasLocationCompassTarget) == "function" and _G.CompletionistMapV105HasLocationCompassTarget() then
      hasOther = true
    elseif type(_G.CompletionistMapV105HasNornirCompassTarget) == "function" and _G.CompletionistMapV105HasNornirCompassTarget() then
      hasOther = true
    elseif lastMapOnSelf and lastMapOnSelf.currShownMarkerID ~= nil then
      hasOther = true
    else
      local stock = stockIds()
      if (ok and #ids > 0) or #stock > 0 then hasOther = true end
    end
    if hasOther then
      return actionText(lamsConsts.ReplaceInCompass)
    end
    return actionText(lamsConsts.AddToCompass)
  end"""
    assert text.count(t1c_old) == 1, f"Raven 1c anchor count: {text.count(t1c_old)}"
    text = text.replace(t1c_old, t1c_new, 1)

    # 1d. refreshPrompt
    t1d_old = """  local function refreshPrompt(self, selected)
    if self == nil or self.menu == nil or selected == nil then return end
    selected = currentSelection(self) or selected
    if not promptOwned(self, true, selected) then return end

    -- v0.10.4's proven footer path temporarily routes the menu's own prompt
    -- query through the exact Raven selection. Without this, the subsequent
    -- UpdateFooterButtonText() redraw can re-query the base map after the
    -- action selection has been consumed and overwrite Remove with Add.
    promptOverride = selected
    local show, text = MapOn.GetShowOnCompassPrompt(self, self.menu)
    if show ~= true then
      promptOverride = nil
      return
    end

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
    promptOverride = nil
    log("PROMPT_REFRESH", "name=" .. selected.Name ..
        " state=" .. tostring(promptIntent and promptIntent.State or "observed") ..
        " text=" .. tostring(text))
  end"""

    t1d_new = """  local function refreshPrompt(self, selected)
    if self == nil or selected == nil then return end
    selected = currentSelection(self) or selected
    local menu = self.menu or (activeMap and activeMap.menu)
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
    if menu ~= nil and type(menu.UpdateFooterButton) == "function" then
      menu:UpdateFooterButton("ShowOnCompass", true, text)
      if type(menu.UpdateFooterButtonText) == "function" then
        menu:UpdateFooterButtonText()
      end
    end
    if menu ~= nil and type(self.UpdateFooterButtonPrompt) == "function" then
      pcall(self.UpdateFooterButtonPrompt, self, menu, false, false)
    end
    log("PROMPT_REFRESH", "name=" .. selected.Name ..
        " state=" .. tostring(promptIntent and promptIntent.State or "observed") ..
        " text=" .. tostring(text))
  end"""
    assert text.count(t1d_old) == 1, f"Raven 1d anchor count: {text.count(t1d_old)}"
    text = text.replace(t1d_old, t1d_new, 1)

    # 1e. showRavenReticle calls refreshPrompt
    t1e_old = """    if ok then
      log("RETICLE", "name=" .. selected.Name ..
          " title=Odin's Raven subtitle=Completionist Map")
    else
      log("RETICLE_FAILED", "name=" .. selected.Name .. " error=" .. tostring(err))
    end
  end

  function MapOn:MapCollisionChangeHandler"""

    t1e_new = """    if ok then
      log("RETICLE", "name=" .. selected.Name ..
          " title=Odin's Raven subtitle=Completionist Map")
    else
      log("RETICLE_FAILED", "name=" .. selected.Name .. " error=" .. tostring(err))
    end
    refreshPrompt(self, selected)
  end

  function MapOn:MapCollisionChangeHandler"""
    assert text.count(t1e_old) == 1, f"Raven 1e anchor count: {text.count(t1e_old)}"
    text = text.replace(t1e_old, t1e_new, 1)

    # 1f. GetShowOnCompassPrompt preserves selection
    t1f_old = """    local selected = currentSelection(self)
    if selected == nil then return show, text end
    if not promptOwned(self, show, selected) then
      clearSelection(self, "prompt_owner_mismatch")
      return show, text
    end
    selected.State = "armed-custom" """

    t1f_new = """    local selected = currentSelection(self)
    if selected == nil then return show, text end
    selected.State = "armed-custom" """
    # strip trailing space if needed
    t1f_old_stripped = """    local selected = currentSelection(self)
    if selected == nil then return show, text end
    if not promptOwned(self, show, selected) then
      clearSelection(self, "prompt_owner_mismatch")
      return show, text
    end
    selected.State = "armed-custom" """
    if text.count(t1f_old.strip()) == 1:
        text = text.replace(t1f_old.strip(), t1f_new.strip(), 1)
    else:
        assert False, f"Raven 1f anchor not found"

    # 1g. ShowOnCompass and MapOn.UpdateMapMarkerHighlights hook
    t1g_old = """  function MapOn:ShowOnCompass(currState)
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
    local ids, queryOK = customIds()
    if not queryOK then return end
    local wantsRemove = contains(ids, selected.IdString)
    if promptIntent ~= nil and promptIntent.IdString == selected.IdString then
      wantsRemove = promptIntent.State == "tracked"
    end
    if wantsRemove then
      customCompassOwnsTarget = true
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
    local stockOK, stockCount = hideStockExcept(selected.IdString, "raven_replace")
    if not customOK or not stockOK then return end
    suppressLegacyRavenHud()
    if type(_G.CompletionistMapV105ReleaseLocationCompass) == "function" then
      pcall(_G.CompletionistMapV105ReleaseLocationCompass)
    end
    if type(_G.CompletionistMapV105ReleaseNornirCompass) == "function" then
      pcall(_G.CompletionistMapV105ReleaseNornirCompass)
    end
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    if not showOK then
      log("SHOW_FAILED", "name=" .. selected.Name .. " error=" .. tostring(showErr))
      return
    end
    customCompassOwnsTarget = true
    suppressLegacyRavenHud()
    hideStockExcept(selected.IdString, "raven_post_show_guard")
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
  end"""

    t1g_new = """  function MapOn:ShowOnCompass(currState)
    lastMapOnSelf = self
    local selected = currentSelection(self)
    if selected == nil then
      customCompassOwnsTarget = false
      promptIntent = nil
      local customOK = hideCustom(nil, "other_target_replace")
      if not customOK then return end
      _G.CompletionistMapV105TrackedCatalogueId = nil
      pcall(function() self:UpdateMapMarkerHighlights() end)
      return previousShow(self, currState)
    end
    selected.State = "armed-custom"
    if not shouldShow(selected.CatalogueId) then return end
    local ids, queryOK = customIds()
    local wantsRemove = contains(ids, selected.IdString) or (_G.CompletionistMapV105TrackedCatalogueId == selected.CatalogueId)
    if promptIntent ~= nil and promptIntent.IdString == selected.IdString then
      wantsRemove = promptIntent.State == "tracked"
    end
    if wantsRemove then
      customCompassOwnsTarget = true
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
        pcall(function() self:UpdateMapMarkerHighlights() end)
        updateHighlights(self)
        refreshPrompt(self, selected)
        log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString)
      end
      return true
    end
    local customOK, customCount = hideCustom(selected.IdString, "raven_replace")
    local stockOK, stockCount = hideStockExcept(selected.IdString, "raven_replace")
    if not customOK or not stockOK then return end
    suppressLegacyRavenHud()
    if type(_G.CompletionistMapV105ReleaseLocationCompass) == "function" then
      pcall(_G.CompletionistMapV105ReleaseLocationCompass)
    end
    if type(_G.CompletionistMapV105ReleaseNornirCompass) == "function" then
      pcall(_G.CompletionistMapV105ReleaseNornirCompass)
    end
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    if not showOK then
      log("SHOW_FAILED", "name=" .. selected.Name .. " error=" .. tostring(showErr))
      return
    end
    customCompassOwnsTarget = true
    suppressLegacyRavenHud()
    hideStockExcept(selected.IdString, "raven_post_show_guard")
    _G.CompletionistMapV105TrackedCatalogueId = selected.CatalogueId
    self.currShownMarkerID = selected.Id
    promptIntent = {
      IdString=selected.IdString, State="tracked",
      Name=selected.Name, CatalogueId=selected.CatalogueId,
    }
    promptSettleFrames = 0
    promptSettleBucket = -1
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    pcall(function() self:UpdateMapMarkerHighlights() end)
    updateHighlights(self)
    refreshPrompt(self, selected)
    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " replacedCustomCount=" .. tostring(customCount) ..
        " replacedStockCount=" .. tostring(stockCount))
    return true
  end

  local previousHighlights = MapOn.UpdateMapMarkerHighlights
  function MapOn:UpdateMapMarkerHighlights(...)
    if previousHighlights then previousHighlights(self, ...) end
    updateHighlights(self)
  end"""
    assert text.count(t1g_old) == 1, f"Raven 1g anchor count: {text.count(t1g_old)}"
    text = text.replace(t1g_old, t1g_new, 1)

    # =========================================================================
    # 2. NORNIR SAVED STATE TEST BLOCK
    # =========================================================================

    # 2a. In hideTarget: update highlights and export GetNornirTargetName
    t2a_old = """  local function hideTarget()
    if targetRow ~= nil then
      pcall(function() game.Compass.HideMarker(targetRow.Name) end)
      targetRow = nil
    end
  end

  local function filter(self)"""

    t2a_new = """  local function hideTarget()
    if targetRow ~= nil then
      pcall(function() game.Compass.HideMarker(targetRow.Name) end)
      targetRow = nil
      if activeMap and type(activeMap.UpdateMapMarkerHighlights) == "function" then
        pcall(activeMap.UpdateMapMarkerHighlights, activeMap)
      end
    end
  end

  _G.CompletionistMapV105GetNornirTargetName = function()
    return targetRow and targetRow.Name or nil
  end
  _G.CompletionistMapV105HasNornirCompassTarget = function()
    return targetRow ~= nil
  end
  _G.CompletionistMapV105ReleaseNornirCompass = function()
    hideTarget()
    if activeMap and type(activeMap.UpdateMapMarkerHighlights) == "function" then
      pcall(activeMap.UpdateMapMarkerHighlights, activeMap)
    end
    return true
  end

  local function filter(self)"""
    assert text.count(t2a_old) == 1, f"Nornir 2a anchor count: {text.count(t2a_old)}"
    text = text.replace(t2a_old, t2a_new, 1)

    # 2b. MapCollisionChangeHandler
    t2b_old = """            local title = row.Family == "nornir_chest" and "Nornir Chest" or
              row.Family == "nornir_seal" and "Nornir Seal" or
              row.Family == "nornir_bell" and "Nornir Bell" or "Nornir Rune Mechanism"
            pcall(function() self:SetReticleInfo(currState, title, "Completionist Map") end)
            pcall(function() self:UpdateFooterButtonPrompt(currState.menu, false, false) end)
            print("[CompletionistMapV105NornirIdTest] selected name=" .. name .."""

    t2b_new = """            local title = row.Family == "nornir_chest" and "Nornir Chest" or
              row.Family == "nornir_seal" and "Nornir Seal" or
              row.Family == "nornir_bell" and "Nornir Bell" or "Nornir Rune Mechanism"
            pcall(function() self:SetReticleInfo(currState, title, "Completionist Map") end)
            local menu = currState and currState.menu or self.menu
            local show, promptStr = self:GetShowOnCompassPrompt(menu)
            if show and promptStr and type(util) == "table" and type(util.GetUiObjByName) == "function" then
              pcall(function()
                local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
                if goMapCursorText ~= nil then
                  goMapCursorText:Show()
                  local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
                  if top ~= nil then
                    local handle = util.GetTextHandle(top, "CursorAction_Text")
                    if handle ~= nil then
                      if type(UI) == "table" and type(UI.SetTextIsClickable) == "function" then
                        UI.SetTextIsClickable(handle)
                      end
                      if type(UI) == "table" and type(UI.SetText) == "function" then
                        UI.SetText(handle, promptStr)
                      end
                    end
                    top:Show()
                  end
                end
              end)
            end
            if menu and type(menu.UpdateFooterButton) == "function" and show and promptStr then
              pcall(function()
                menu:UpdateFooterButton("ShowOnCompass", true, promptStr)
                if type(menu.UpdateFooterButtonText) == "function" then
                  menu:UpdateFooterButtonText()
                end
              end)
            end
            if menu and type(self.UpdateFooterButtonPrompt) == "function" then
              pcall(self.UpdateFooterButtonPrompt, self, menu, false, false)
            end
            print("[CompletionistMapV105NornirIdTest] selected name=" .. name .."""
    assert text.count(t2b_old) == 1, f"Nornir 2b anchor count: {text.count(t2b_old)}"
    text = text.replace(t2b_old, t2b_new, 1)

    # 2c. Hook MapOn.UpdateMapMarkerHighlights for Nornir
    t2c_old = """    return result
  end

  local previousPrompt = MapOn.GetShowOnCompassPrompt"""

    t2c_new = """    return result
  end

  local previousHighlights = MapOn.UpdateMapMarkerHighlights
  MapOn.UpdateMapMarkerHighlights = function(self, ...)
    if previousHighlights then previousHighlights(self, ...) end
    local target = self or activeMap
    if target and type(UI) == "table" and type(UI.Anim) == "function" then
      for name, icon in pairs(target.completionistMapV105NornirIdTestIcons or {}) do
        local row = byName[name]
        if targetRow ~= nil and targetRow == row then
          pcall(UI.Anim, icon, 10, "", 1)
        else
          pcall(UI.Anim, icon, 0, "", 0, 0)
        end
      end
    end
  end

  local previousPrompt = MapOn.GetShowOnCompassPrompt"""
    assert text.count(t2c_old) == 1, f"Nornir 2c anchor count: {text.count(t2c_old)}"
    text = text.replace(t2c_old, t2c_new, 1)

    # 2d. ShowOnCompass in Nornir
    t2d_old = """        local legacy = _G.CompletionistMapV100Target
        if legacy then legacy.active = false end
        pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass") end)
      end
      local currState = select(1, ...)
      if currState and currState.menu then
        pcall(function() self:UpdateFooterButtonPrompt(currState.menu, false, false) end)
      end
      return true
    end"""

    t2d_new = """        local legacy = _G.CompletionistMapV100Target
        if legacy then legacy.active = false end
        pcall(function() Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass") end)
      end
      pcall(function() self:UpdateMapMarkerHighlights() end)
      local currState = select(1, ...)
      local menu = currState and currState.menu or self.menu
      local show, text = self:GetShowOnCompassPrompt(menu)
      if show and text then
        if type(util) == "table" and type(util.GetUiObjByName) == "function" then
          pcall(function()
            local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
            if goMapCursorText ~= nil then
              goMapCursorText:Show()
              local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
              if top ~= nil then
                local handle = util.GetTextHandle(top, "CursorAction_Text")
                if handle ~= nil then
                  if type(UI) == "table" and type(UI.SetTextIsClickable) == "function" then
                    UI.SetTextIsClickable(handle)
                  end
                  if type(UI) == "table" and type(UI.SetText) == "function" then
                    UI.SetText(handle, text)
                  end
                end
                top:Show()
              end
            end
          end)
        end
        if menu and type(menu.UpdateFooterButton) == "function" then
          pcall(function()
            menu:UpdateFooterButton("ShowOnCompass", true, text)
            if type(menu.UpdateFooterButtonText) == "function" then
              menu:UpdateFooterButtonText()
            end
          end)
        end
      end
      if menu and type(self.UpdateFooterButtonPrompt) == "function" then
        pcall(self.UpdateFooterButtonPrompt, self, menu, false, false)
      end
      return true
    end"""
    assert text.count(t2d_old) == 1, f"Nornir 2d anchor count: {text.count(t2d_old)}"
    text = text.replace(t2d_old, t2d_new, 1)

    # Clean up the redundant handoff at end of Nornir block if needed
    redundant_handoff = """  -- Share the single native compass target with the location layer.
  _G.CompletionistMapV105HasNornirCompassTarget = function()
    return targetRow ~= nil
  end
  _G.CompletionistMapV105ReleaseNornirCompass = function()
    if targetRow ~= nil then
      local ok, result = pcall(game.Compass.HideMarker, targetRow.Name)
      if not ok or result == false then return false end
      targetRow = nil
    end
    return true
  end"""
    if text.count(redundant_handoff) == 1:
        # Replace it with comment or keep it in sync with highlights
        better_handoff = """  -- Share the single native compass target with the location layer.
  _G.CompletionistMapV105GetNornirTargetName = function()
    return targetRow and targetRow.Name or nil
  end
  _G.CompletionistMapV105HasNornirCompassTarget = function()
    return targetRow ~= nil
  end
  _G.CompletionistMapV105ReleaseNornirCompass = function()
    hideTarget()
    if activeMap and type(activeMap.UpdateMapMarkerHighlights) == "function" then
      pcall(activeMap.UpdateMapMarkerHighlights, activeMap)
    end
    return true
  end"""
        text = text.replace(redundant_handoff, better_handoff, 1)

    # =========================================================================
    # 3. COLLECTIBLE LOCATIONS BLOCK
    # =========================================================================

    # 3a. updateHighlights in locations block
    t3a_old = """  local function updateHighlights(self)
    local target = self or activeMap
    if target == nil or type(UI) ~= "table" or type(UI.Anim) ~= "function" then return end
    for name, icon in pairs(target.completionistMapV105LocationIcons or {}) do
      local row = byName[name]
      if targetRow ~= nil and targetRow == row then
        pcall(UI.Anim, icon, AS_ForwardCycle_NoReset, "", 1)
      else
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
    end
  end"""

    t3a_new = """  local function updateHighlights(self)
    local target = self or activeMap
    if target == nil or type(UI) ~= "table" or type(UI.Anim) ~= "function" then return end
    for name, icon in pairs(target.completionistMapV105LocationIcons or {}) do
      local row = byName[name]
      if targetRow ~= nil and targetRow == row then
        pcall(UI.Anim, icon, AS_ForwardCycle_NoReset, "", 1)
      else
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
    end
    local nornirTargetName = (type(_G.CompletionistMapV105GetNornirTargetName) == "function") and
      _G.CompletionistMapV105GetNornirTargetName() or nil
    for name, icon in pairs(target.completionistMapV105NornirIdTestIcons or {}) do
      if nornirTargetName ~= nil and nornirTargetName == name then
        pcall(UI.Anim, icon, AS_ForwardCycle_NoReset, "", 1)
      else
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
    end
    local ravenTargetName = (type(_G.CompletionistMapV105GetRavenTargetName) == "function") and
      _G.CompletionistMapV105GetRavenTargetName() or nil
    for name, icon in pairs(target.completionistMapV105RavenIcons or {}) do
      if ravenTargetName ~= nil and ravenTargetName == name then
        pcall(UI.Anim, icon, AS_ForwardCycle_NoReset, "", 1)
      else
        pcall(UI.Anim, icon, AS_Forward, "", 0, 0)
      end
    end
  end"""
    assert text.count(t3a_old) == 1, f"Locations 3a anchor count: {text.count(t3a_old)}"
    text = text.replace(t3a_old, t3a_new, 1)

    # 3b. Export Location target name and UpdateHighlights
    t3b_old = """  _G.CompletionistMapV105HasLocationCompassTarget = function()
    return targetRow ~= nil
  end"""

    t3b_new = """  _G.CompletionistMapV105HasLocationCompassTarget = function()
    return targetRow ~= nil
  end
  _G.CompletionistMapV105GetLocationTargetName = function()
    return targetRow and targetRow.Name or nil
  end
  _G.CompletionistMapV105UpdateHighlights = updateHighlights"""
    assert text.count(t3b_old) == 1, f"Locations 3b anchor count: {text.count(t3b_old)}"
    text = text.replace(t3b_old, t3b_new, 1)

    # 3c. ShowOnCompass when row == nil
    t3c_old = """      if not hideTarget() then return false end
      local res = previousShow and previousShow(self, ...)
      updateHighlights(self)
      return res"""

    t3c_new = """      if not hideTarget() then return false end
      local res = previousShow and previousShow(self, ...)
      updateHighlights(self)
      local currState = select(1, ...)
      if refreshCompassPromptUI then
        refreshCompassPromptUI(self, currState and currState.menu)
      end
      return res"""
    assert text.count(t3c_old) == 1, f"Locations 3c anchor count: {text.count(t3c_old)}"
    text = text.replace(t3c_old, t3c_new, 1)

    GAME_MAP.write_text(text, encoding="utf-8")
    print(f"Successfully synchronized {GAME_MAP}!")

if __name__ == "__main__":
    sync()
