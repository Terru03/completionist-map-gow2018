-- Observe reward chest opening. The runic puzzle parent can remain ENABLED.
do
  local function key()
    if thisLevel == nil or parentObj == nil or
        type(thisLevel.Name) ~= "string" then return nil end
    local refs = {}
    for index = 1, 3 do
      local ref = parentObj:FindLuaTableAttribute("sealBreakable0" .. tostring(index))
      if type(ref) ~= "string" or ref == "" or string.find(ref, "|", 1, true) then
        return nil
      end
      refs[index] = string.lower(ref)
    end
    table.sort(refs)
    return string.lower(thisLevel.Name) .. "|" .. table.concat(refs, "|")
  end

  local function publish()
    if chestType ~= "Runic_Axe" and chestType ~= "Runic_Blades" then return end
    local identity = key()
    if identity == nil then return end
    local payload = "NORNIR_V1\topened\t" .. identity .. "\t"
    local ok = pcall(function()
      engine.SendHook("COMPLETIONIST_NORNIR_EVENT_V1", engine.GetUIWad(), payload)
    end)
    print("[CompletionistMapV105Nornir] event=opened key=" .. identity ..
      " delivered=" .. tostring(ok))
  end

  local stockOpened = OnOpened
  function OnOpened(...)
    local result = stockOpened(...)
    publish()
    return result
  end

  local stockStart = OnStart
  function OnStart(...)
    local wasOpened = state == states.OPENED
    local result = stockStart(...)
    if wasOpened then publish() end
    return result
  end
end
