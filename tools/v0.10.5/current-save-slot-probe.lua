-- Completionist Map v0.10.5 - current save slot persistence probe.
-- Read-only: calls only UI.GetCurrentSlot / UI.IsSlotValid and prints results.
if not _G.CompletionistMapV105CurrentSlotProbeInstallCount then
  _G.CompletionistMapV105CurrentSlotProbeInstallCount = 0
end
_G.CompletionistMapV105CurrentSlotProbeInstallCount =
  _G.CompletionistMapV105CurrentSlotProbeInstallCount + 1

local prefix = "[CompletionistCurrentSlotProbe] "
local install = _G.CompletionistMapV105CurrentSlotProbeInstallCount

local ui = type(game) == "table" and game.UI or nil
local uiType = type(ui)
local getType = (uiType == "table" or uiType == "userdata") and type(ui.GetCurrentSlot) or "nil"
local validType = (uiType == "table" or uiType == "userdata") and type(ui.IsSlotValid) or "nil"

local okGet, slot = false, nil
if getType == "function" then
  okGet, slot = pcall(ui.GetCurrentSlot)
end

local okValid, valid = false, nil
if okGet and validType == "function" then
  okValid, valid = pcall(ui.IsSlotValid, slot)
end

print(prefix ..
  "INSTALL count=" .. tostring(install) ..
  " uiType=" .. tostring(uiType) ..
  " getType=" .. tostring(getType) ..
  " getOk=" .. tostring(okGet) ..
  " slot=" .. tostring(slot) ..
  " isSlotValidType=" .. tostring(validType) ..
  " validOk=" .. tostring(okValid) ..
  " valid=" .. tostring(valid) ..
  " readOnly=true")
