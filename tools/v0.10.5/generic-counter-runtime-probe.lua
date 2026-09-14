-- BEGIN COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
-- Read-only runtime introspection for native/QuestManager counter APIs. No progression writes.
do
  local prefix = "[CompletionistCounterProbe] "
  local ran = false

  local function log(message)
    print(prefix .. message)
  end

  local function safeLookup(label, fn)
    local ok, value = pcall(fn)
    if ok then
      log("TYPE path=" .. label .. " type=" .. tostring(type(value)))
      return value
    end
    log("TYPE path=" .. label .. " lookupOk=false error=" .. tostring(value))
    return nil
  end

  local function safeCall(label, fn)
    if type(fn) ~= "function" then
      log("CALL label=" .. label .. " skipped=not_function")
      return false, nil, nil, nil, nil
    end
    local ok, a, b, c, d = pcall(fn)
    if ok then
      log("CALL label=" .. label ..
          " ok=true" ..
          " ret1Type=" .. tostring(type(a)) .. " ret1=" .. tostring(a) ..
          " ret2Type=" .. tostring(type(b)) .. " ret2=" .. tostring(b) ..
          " ret3Type=" .. tostring(type(c)) .. " ret3=" .. tostring(c) ..
          " ret4Type=" .. tostring(type(d)) .. " ret4=" .. tostring(d))
      return true, a, b, c, d
    end
    log("CALL label=" .. label .. " ok=false error=" .. tostring(a))
    return false, nil, nil, nil, nil
  end

  local function inspectQuest(qm, questId)
    local stateFn = safeLookup("game.QuestManager.GetQuestState", function() return qm.GetQuestState end)
    local progressFn = safeLookup("game.QuestManager.GetQuestProgressAndGoal", function() return qm.GetQuestProgressAndGoal end)
    local childrenFn = safeLookup("game.QuestManager.GetChildrenQuestIds", function() return qm.GetChildrenQuestIds end)
    local rootFn = safeLookup("game.QuestManager.IsActiveRootQuestId", function() return qm.IsActiveRootQuestId end)

    log("QUEST_BEGIN id=" .. tostring(questId))

    safeCall("GetQuestState(" .. tostring(questId) .. ")", function()
      return stateFn(questId)
    end)

    safeCall("IsActiveRootQuestId(" .. tostring(questId) .. ")", function()
      return rootFn(questId)
    end)

    safeCall("GetQuestProgressAndGoal(" .. tostring(questId) .. ")", function()
      return progressFn(questId)
    end)

    local childrenOK, children = safeCall("GetChildrenQuestIds(" .. tostring(questId) .. ")", function()
      return childrenFn(questId)
    end)

    if childrenOK and type(children) == "table" then
      local count = #children
      log("CHILDREN parent=" .. tostring(questId) .. " count=" .. tostring(count))
      local limit = math.min(count, 64)
      for i = 1, limit do
        local child = children[i]
        local stateOK, state = safeCall("childState[" .. tostring(i) .. "]", function()
          return stateFn(child)
        end)
        local progressOK, a, b = safeCall("childProgress[" .. tostring(i) .. "]", function()
          return progressFn(child)
        end)
        log("CHILD parent=" .. tostring(questId) ..
            " index=" .. tostring(i) ..
            " id=" .. tostring(child) ..
            " stateOk=" .. tostring(stateOK) .. " state=" .. tostring(state) ..
            " progressOk=" .. tostring(progressOK) ..
            " ret1=" .. tostring(a) .. " ret2=" .. tostring(b))
      end
    else
      log("CHILDREN parent=" .. tostring(questId) .. " unavailable=true")
    end

    log("QUEST_END id=" .. tostring(questId))
  end

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. tostring(reason) .. " progressionWrites=false questWrites=false")

    local qm = nil
    if type(game) == "table" then
      qm = safeLookup("game.QuestManager", function() return game.QuestManager end)
    end

    if type(qm) ~= "table" then
      log("QUEST_MANAGER unavailable=true")
      log("DONE progressionWrites=false questWrites=false")
      return
    end

    -- Validation target: the exact Veithurgard Raven RegionSummary used by the
    -- already-proven Raven runtime lifecycle. Comparison target: global Raven labor.
    inspectQuest(qm, "RegionSummary_VF_Raven_Parent")
    inspectQuest(qm, "Quest_Labor_KillRavens")

    log("DONE progressionWrites=false questWrites=false")
  end

  _G.CompletionistCounterProbe_Run = run

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler questManagerApi=true")
  else
    log("HOOK unavailable=true fallback=script_load")
    run("script_load_fallback")
  end
end
-- END COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
