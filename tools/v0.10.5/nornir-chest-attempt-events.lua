-- Observe stock runic chest. Only real locked use reveals its children.
do
  local attempted = false
  local hook = "COMPLETIONIST_NORNIR_EVENT_V1"

  local function identity()
    if thisLevel == nil or thisObj == nil or type(thisLevel.Name) ~= "string" then
      return nil
    end
    local refs = {}
    for index = 1, 3 do
      local ref = thisObj:FindLuaTableAttribute("sealBreakable0" .. tostring(index))
      if type(ref) ~= "string" or ref == "" or string.find(ref, "|", 1, true) then
        return nil
      end
      refs[index] = string.lower(ref)
    end
    table.sort(refs)
    return string.lower(thisLevel.Name) .. "|" .. table.concat(refs, "|")
  end

  local function publish(action, reference)
    local key = identity()
    if key == nil then return end
    local payload = "NORNIR_V1\t" .. action .. "\t" .. key .. "\t" ..
      string.lower(reference or "")
    local ok = pcall(function()
      engine.SendHook(hook, engine.GetUIWad(), payload)
    end)
    print("[CompletionistMapV105Nornir] event=" .. action ..
      " key=" .. key .. " delivered=" .. tostring(ok))
  end

  local stockLocked = PerformKratosInteraction_Locked
  function PerformKratosInteraction_Locked(...)
    local locked = interactAvailable == true and
      challengeComplete ~= true and state ~= states.OPENED
    local result = stockLocked(...)
    if locked then
      attempted = true
      publish("attempt")
    end
    return result
  end

  local stockBroken = OnKeyBroken
  function OnKeyBroken(index, ...)
    local result = stockBroken(index, ...)
    if keyType == "Breakable" and type(index) == "number" and
        index >= 1 and index <= 3 then
      local ref = thisObj:FindLuaTableAttribute("sealBreakable0" .. tostring(index))
      if type(ref) == "string" then publish("seal", ref) end
    end
    return result
  end

  local stockFinish = OnInteractFinish
  function OnInteractFinish(...)
    local result = stockFinish(...)
    if state == states.OPENED then publish("opened") end
    return result
  end

  local stockSave = OnSaveCheckpoint
  function OnSaveCheckpoint(...)
    local saved = stockSave(...)
    if type(saved) == "table" then
      saved.completionistPuzzleAttempted = attempted
    end
    return saved
  end

  local stockRestore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(level, go, saved)
    local result = stockRestore(level, go, saved)
    attempted = type(saved) == "table" and
      saved.completionistPuzzleAttempted == true
    return result
  end

  local stockStart = OnStart
  function OnStart(...)
    local wasOpened = state == states.OPENED
    local result = stockStart(...)
    local rewardOpened = false
    if chestScript ~= nil then
      local ok, value = pcall(function() return chestScript.GetState() end)
      rewardOpened = ok and value == states.OPENED
    end
    if wasOpened or rewardOpened then
      publish("opened")
    elseif attempted then
      publish("attempt")
    end
    if keyType == "Breakable" and type(keysUsed) == "number" then
      local disabled = 0
      local known = true
      local resolved = {}
      for index = 1, 3 do
        local rune = runeTable[index]
        local ok, enabled = pcall(function()
          return rune.runeVisual.LuaObjectScript.IsEnabled()
        end)
        if not ok or type(enabled) ~= "boolean" then
          known = false
          break
        end
        if not enabled then
          disabled = disabled + 1
          resolved[#resolved + 1] = index
        end
      end
      if known and disabled == keysUsed then
        for _, index in ipairs(resolved) do
          local ref = thisObj:FindLuaTableAttribute(
            "sealBreakable0" .. tostring(index))
          if type(ref) == "string" then publish("seal", ref) end
        end
      end
    end
    return result
  end
end
