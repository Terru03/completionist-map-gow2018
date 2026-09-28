-- Read the saved locked-chest try after runic load.
do
  local start = OnStart
  function OnStart(...)
    local result = start(...)
    if thisLevel == nil or thisObj == nil or
        type(thisLevel.Name) ~= "string" then return result end
    local refs = {}
    for index = 1, 3 do
      local ref = thisObj:FindLuaTableAttribute(
        "sealBreakable0" .. tostring(index))
      if type(ref) ~= "string" or ref == "" or
          string.find(ref, "|", 1, true) then return result end
      refs[index] = string.lower(ref)
    end
    table.sort(refs)
    local key = string.lower(thisLevel.Name) .. "|" ..
      table.concat(refs, "|")
    local ok, saved = pcall(OnSaveCheckpoint, thisLevel, thisObj)
    if not ok or type(saved) ~= "table" or
        type(saved.completionistPuzzleAttempted) ~= "boolean" then
      return result
    end
    local attempted = saved.completionistPuzzleAttempted
    local payload = "NORNIR_V1\trestore\t" .. key .. "\t" ..
      (attempted and "1" or "0")
    local delivered = pcall(function()
      engine.SendHook("COMPLETIONIST_NORNIR_EVENT_V1",
        engine.GetUIWad(), payload)
    end)
    print("[CompletionistMapV105Nornir] event=restore key=" .. key ..
      " attempted=" .. tostring(attempted) ..
      " delivered=" .. tostring(delivered))
    return result
  end
end
