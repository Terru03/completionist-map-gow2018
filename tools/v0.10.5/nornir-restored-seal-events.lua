-- Send all three rune flags after load and after each broken seal.
do
  local function publishSnapshot()
    if thisLevel == nil or thisObj == nil or
        type(thisLevel.Name) ~= "string" then return end
    local observed = CompletionistNornirObserveSeals()
    if type(observed) ~= "table" or #observed ~= 3 then return end
    local byRef, refs = {}, {}
    for _, entry in ipairs(observed) do
      local ref = entry.reference
      if type(ref) ~= "string" or ref == "" or
          string.find(ref, "|", 1, true) or
          byRef[ref] ~= nil or type(entry.broken) ~= "boolean" then return end
      byRef[ref] = entry.broken
      refs[#refs + 1] = ref
    end
    table.sort(refs)
    local bits = {}
    for index, ref in ipairs(refs) do
      bits[index] = byRef[ref] and "1" or "0"
    end
    local key = string.lower(thisLevel.Name) .. "|" ..
      table.concat(refs, "|")
    local payload = "NORNIR_V1\tsnapshot\t" .. key .. "\t" ..
      table.concat(bits)
    local ok = pcall(function()
      engine.SendHook("COMPLETIONIST_NORNIR_EVENT_V1",
        engine.GetUIWad(), payload)
    end)
    print("[CompletionistMapV105Nornir] event=snapshot key=" .. key ..
      " bits=" .. table.concat(bits) .. " delivered=" .. tostring(ok))
  end

  local start = OnStart
  function OnStart(...)
    local result = start(...)
    publishSnapshot()
    return result
  end

  local broken = OnKeyBroken
  function OnKeyBroken(...)
    local result = broken(...)
    publishSnapshot()
    return result
  end
end
