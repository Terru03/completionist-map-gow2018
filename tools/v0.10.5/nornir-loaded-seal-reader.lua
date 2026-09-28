-- Read live rune state. Check all three refs and parent count first.
do
  function CompletionistNornirObserveSeals()
    if keyType ~= "Breakable" or type(keysUsed) ~= "number" or
        keysUsed < 0 or keysUsed > 3 then return nil end
    local entries, broken = {}, 0
    for index = 1, 3 do
      local ref = thisObj:FindLuaTableAttribute(
        "sealBreakable0" .. tostring(index))
      local rune = runeTable[index]
      if type(ref) ~= "string" or ref == "" or
          string.find(ref, "|", 1, true) or rune == nil or
          rune.runeVisual == nil or
          thisObj:FindSingleGOByName("keyRune0" .. tostring(index)) ~=
          rune.runeVisual then return nil end
      local ok, enabled = pcall(function()
        return rune.runeVisual.LuaObjectScript.IsEnabled()
      end)
      if not ok or type(enabled) ~= "boolean" then return nil end
      entries[index] = {reference = string.lower(ref), broken = not enabled}
      if not enabled then broken = broken + 1 end
    end
    if broken ~= keysUsed then return nil end
    return entries
  end
end
