-- BEGIN COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
-- Read-only runtime introspection for native counter APIs. No progression writes.
do
  local prefix = "[CompletionistCounterProbe] "
  local ran = false

  local function log(message)
    print(prefix .. message)
  end

  local function typeOf(path, value)
    log("TYPE path=" .. path .. " type=" .. tostring(type(value)))
  end

  local names = {
    "GetCounter",
    "GetCounterChild",
    "GetCounterChildrenCount",
    "GetCounterName",
    "GetRefBool",
    "GetRefFloat",
    "GetRefInt",
    "GetRefString",
    "ResolveGameObject",
    "MarkerID",
    "GetRegionHash",
  }

  for _, name in ipairs(names) do
    typeOf("_G." .. name, rawget(_G, name))
  end

  if type(game) == "table" then
    for _, name in ipairs(names) do
      typeOf("game." .. name, rawget(game, name))
    end
    if type(game.Level) == "table" then
      for _, name in ipairs(names) do
        typeOf("game.Level." .. name, rawget(game.Level, name))
      end
    end
    if type(game.QuestManager) == "table" then
      for _, name in ipairs(names) do
        typeOf("game.QuestManager." .. name, rawget(game.QuestManager, name))
      end
    end
  end

  local function safeOne(label, fn)
    if type(fn) ~= "function" then
      log("CALL label=" .. label .. " skipped=not_function")
      return false, nil
    end
    local ok, value = pcall(fn)
    if ok then
      log("CALL label=" .. label .. " ok=true type=" .. tostring(type(value)) .. " value=" .. tostring(value))
      return true, value
    end
    log("CALL label=" .. label .. " ok=false error=" .. tostring(value))
    return false, nil
  end

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. tostring(reason) .. " progressionWrites=false")

    local getCounter = rawget(_G, "GetCounter")
    local getCounterChild = rawget(_G, "GetCounterChild")
    local getCounterChildrenCount = rawget(_G, "GetCounterChildrenCount")
    local getCounterName = rawget(_G, "GetCounterName")
    local parent = "RegionSummary_VF_Raven_Parent"

    local parentOK, parentValue = safeOne("GetCounter(parent)", function()
      return getCounter(parent)
    end)
    local countOK, childCount = safeOne("GetCounterChildrenCount(parent)", function()
      return getCounterChildrenCount(parent)
    end)

    if countOK and type(childCount) == "number" and childCount >= 0 and childCount <= 128 and
       type(getCounterChild) == "function" and type(getCounterName) == "function" and type(getCounter) == "function" then
      log("TREE parent=" .. parent .. " parentValue=" .. tostring(parentValue) .. " children=" .. tostring(childCount))
      local limit = math.min(childCount, 64)
      for i = 0, limit - 1 do
        local childOK, child = pcall(function() return getCounterChild(parent, i) end)
        if childOK then
          local nameOK, childName = pcall(function() return getCounterName(child) end)
          local valueOK, childValue = pcall(function() return getCounter(child) end)
          log("CHILD index=" .. tostring(i) ..
              " childOk=true id=" .. tostring(child) ..
              " nameOk=" .. tostring(nameOK) .. " name=" .. tostring(childName) ..
              " valueOk=" .. tostring(valueOK) .. " value=" .. tostring(childValue))
        else
          log("CHILD index=" .. tostring(i) .. " childOk=false error=" .. tostring(child))
        end
      end
    else
      log("TREE skipped=true reason=counter_api_unavailable_or_invalid_count" ..
          " parentOk=" .. tostring(parentOK) .. " countOk=" .. tostring(countOK) ..
          " count=" .. tostring(childCount))
    end

    if type(game) == "table" and type(game.QuestManager) == "table" and
       type(game.QuestManager.GetQuestState) == "function" then
      safeOne("QuestManager.GetQuestState(parent)", function()
        return game.QuestManager.GetQuestState(parent)
      end)
    else
      log("CALL label=QuestManager.GetQuestState(parent) skipped=not_function")
    end

    log("DONE progressionWrites=false")
  end

  _G.CompletionistCounterProbe_Run = run

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler")
  else
    log("HOOK unavailable=true fallback=script_load")
    run("script_load_fallback")
  end
end
-- END COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
