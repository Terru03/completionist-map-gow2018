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

  local function inspectChildTable(parent, children, stateFn, progressFn)
    local seqCount = #children
    local rawLength = nil
    if type(rawlen) == "function" then
      local okRaw, v = pcall(rawlen, children)
      if okRaw then rawLength = v end
    end
    log("CHILDREN_TABLE parent=" .. tostring(parent) ..
        " seqCount=" .. tostring(seqCount) ..
        " rawlen=" .. tostring(rawLength))

    local keyCount = 0
    local numericCount = 0
    local emitted = 0
    local okPairs, iter, state, initial = pcall(pairs, children)
    if not okPairs then
      log("CHILDREN_ENUM parent=" .. tostring(parent) .. " ok=false error=" .. tostring(iter))
      return
    end

    local k = initial
    while true do
      local okNext, nk, nv = pcall(iter, state, k)
      if not okNext then
        log("CHILDREN_ENUM parent=" .. tostring(parent) .. " nextOk=false error=" .. tostring(nk))
        break
      end
      if nk == nil then break end
      k = nk
      keyCount = keyCount + 1
      if type(nk) == "number" then numericCount = numericCount + 1 end

      if emitted < 64 then
        emitted = emitted + 1
        local child = nv
        local stateOK, childState = safeCall("childState[key=" .. tostring(nk) .. "]", function()
          return stateFn(child)
        end)
        local progressOK, a, b, c = safeCall("childProgress[key=" .. tostring(nk) .. "]", function()
          return progressFn(child)
        end)
        log("CHILD_KEY parent=" .. tostring(parent) ..
            " keyType=" .. tostring(type(nk)) .. " key=" .. tostring(nk) ..
            " valueType=" .. tostring(type(child)) .. " id=" .. tostring(child) ..
            " stateOk=" .. tostring(stateOK) .. " state=" .. tostring(childState) ..
            " progressOk=" .. tostring(progressOK) ..
            " ret1=" .. tostring(a) .. " ret2=" .. tostring(b) .. " ret3=" .. tostring(c))
      end
    end

    log("CHILDREN_ENUM parent=" .. tostring(parent) ..
        " ok=true keys=" .. tostring(keyCount) ..
        " numericKeys=" .. tostring(numericCount) ..
        " emitted=" .. tostring(emitted))
  end

  local function inspectGlobalBindings()
    local names = {
      "GetCounter", "GetCounterChild", "GetCounterChildrenCount",
      "GetCounterName", "GetRefBool", "GetRefInt", "GetRefFloat",
      "GetRefString", "LevelWads", "UIWads", "LoadCheck",
      "FindLevel", "EvaluateLoadZones", "JumpToWad", "ResolveGameObject",
      "GetCurrentSlot", "GetLatestSlot", "GetSlotCount",
    }
    local funcs = {}
    for _, name in ipairs(names) do
      funcs[name] = rawget(_G, name)
      log("GLOBAL_TYPE name=" .. name .. " type=" .. type(funcs[name]))
    end

    local parent = "RegionSummary_VF_Raven_Parent"
    local knownGuid = "642d0d16-4af0-a5d4-076e-77933c549a5d"
    local probes = {
      {"GetCounter(parent)", "GetCounter", {parent}},
      {"GetCounterChildrenCount(parent)", "GetCounterChildrenCount", {parent}},
      {"GetCounterChild(parent,0)", "GetCounterChild", {parent, 0}},
      {"GetCounterChild(parent,1)", "GetCounterChild", {parent, 1}},
      {"GetCounterName(parent)", "GetCounterName", {parent}},
      {"GetRefBool(guid)", "GetRefBool", {knownGuid}},
      {"LevelWads()", "LevelWads", {}},
      {"UIWads()", "UIWads", {}},
      {"LoadCheck()", "LoadCheck", {}},
      {"FindLevel()", "FindLevel", {}},
      {"ResolveGameObject(guid)", "ResolveGameObject", {knownGuid}},
      {"GetCurrentSlot()", "GetCurrentSlot", {}},
      {"GetLatestSlot()", "GetLatestSlot", {}},
      {"GetSlotCount()", "GetSlotCount", {}},
    }

    for _, probe in ipairs(probes) do
      local label, name, args = probe[1], probe[2], probe[3]
      local fn = funcs[name]
      if type(fn) == "function" then
        safeCall("GLOBAL " .. label, function()
          return fn(table.unpack(args))
        end)
      else
        log("GLOBAL_CALL label=" .. label .. " skipped=true type=" .. type(fn))
      end
    end

    local rawRandom = rawget(_G, "Random")
    log("GLOBAL_CONTROL name=Random type=" .. type(rawRandom))
    if type(rawRandom) == "function" then
      safeCall("GLOBAL Random(1,1)", function() return rawRandom(1, 1) end)
    end

    log("GLOBAL_BINDINGS_DONE progressionWrites=false questWrites=false")
  end

  local function inspectDirectGameBindings()
    if type(game) ~= "table" then
      log("DIRECT_BINDINGS game_unavailable=true")
      return
    end

    local names = {
      "GetCounter", "GetCounterChild", "GetCounterChildrenCount",
      "GetCounterName", "GetCounterThreshold", "GetCounterThresholdCount",
      "GetCounterThresholdName", "GetRefBool", "GetRefInt",
      "GetRefFloat", "GetRefString", "GetVariable",
    }
    local funcs = {}
    for _, name in ipairs(names) do
      funcs[name] = safeLookup("game." .. name, function() return game[name] end)
    end

    local parent = "RegionSummary_VF_Raven_Parent"
    local knownGuid = "642d0d16-4af0-a5d4-076e-77933c549a5d"
    local knownObject = "goprecisionchallenge_raven_perch"
    local probes = {
      {"GetCounter()", "GetCounter", {}},
      {"GetCounter(parent)", "GetCounter", {parent}},
      {"GetCounterChildrenCount(parent)", "GetCounterChildrenCount", {parent}},
      {"GetCounterChild(parent,0)", "GetCounterChild", {parent, 0}},
      {"GetCounterChild(parent,1)", "GetCounterChild", {parent, 1}},
      {"GetCounterName(parent)", "GetCounterName", {parent}},
      {"GetCounterThresholdCount(parent)", "GetCounterThresholdCount", {parent}},
      {"GetRefBool(guid)", "GetRefBool", {knownGuid}},
      {"GetRefBool(parent,guid)", "GetRefBool", {parent, knownGuid}},
      {"GetRefBool(object)", "GetRefBool", {knownObject}},
      {"GetVariable(guid)", "GetVariable", {knownGuid}},
      {"GetVariable(parent,guid)", "GetVariable", {parent, knownGuid}},
    }

    for _, probe in ipairs(probes) do
      local label, name, args = probe[1], probe[2], probe[3]
      local fn = funcs[name]
      safeCall(label, function()
        return fn(table.unpack(args))
      end)
    end

    log("DIRECT_BINDINGS_DONE parent=" .. parent .. " guid=" .. knownGuid ..
        " writes=false")
  end

  local function inspectRegistryOwners()
    if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then
      log("OWNER_SCAN unavailable=true")
      return
    end
    local ok, registry = pcall(debug.getregistry)
    if not ok or type(registry) ~= "table" then
      log("OWNER_SCAN registryOk=false")
      return
    end

    local wanted = {
      GetCounter=true, GetCounterChild=true, GetCounterChildrenCount=true,
      GetRefBool=true, GetRefInt=true, GetRefFloat=true, GetRefString=true,
      GetVariable=true,
    }
    local queue = {{value=registry, path="debug.registry", depth=0}}
    local seen = {}
    local emitted = 0
    local maxTables = 2000
    local visited = 0
    while #queue > 0 and visited < maxTables do
      local item = table.remove(queue)
      local value = item.value
      if type(value) == "table" and not seen[value] then
        seen[value] = true
        visited = visited + 1
        local hits = {}
        for key, member in pairs(value) do
          if type(key) == "string" and wanted[key] then
            hits[#hits + 1] = key .. ":" .. type(member)
          end
        end
        if #hits > 0 then
          table.sort(hits)
          emitted = emitted + 1
          local identity = rawget(value, "__identity")
          log("OWNER_TABLE path=" .. item.path ..
              " identity=" .. tostring(identity) ..
              " methods=" .. table.concat(hits, ","))
        end
        if item.depth < 4 then
          local childCount = 0
          for key, child in pairs(value) do
            if type(child) == "table" and not seen[child] and childCount < 96 then
              childCount = childCount + 1
              queue[#queue + 1] = {
                value=child,
                path=item.path .. "[" .. tostring(key) .. "]",
                depth=item.depth + 1,
              }
            end
          end
        end
      end
    end
    log("OWNER_SCAN_DONE tables=" .. tostring(visited) .. " owners=" .. tostring(emitted))
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
      inspectChildTable(questId, children, stateFn, progressFn)
    else
      log("CHILDREN parent=" .. tostring(questId) .. " unavailable=true")
    end

    log("QUEST_END id=" .. tostring(questId))
  end

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. tostring(reason) .. " progressionWrites=false questWrites=false childKeyEnumeration=true")

    local qm = nil
    if type(game) == "table" then
      qm = safeLookup("game.QuestManager", function() return game.QuestManager end)
    end

    if type(qm) ~= "table" then
      log("QUEST_MANAGER unavailable=true")
      log("DONE progressionWrites=false questWrites=false")
      return
    end

    inspectGlobalBindings()
    inspectDirectGameBindings()
    inspectRegistryOwners()
    inspectQuest(qm, "RegionSummary_VF_Raven_Parent")
    inspectQuest(qm, "Quest_Labor_KillRavens")

    log("DONE progressionWrites=false questWrites=false directGetterProbe=true")
  end

  _G.CompletionistCounterProbe_Run = run

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler questManagerApi=true childKeyEnumeration=true")
  else
    log("HOOK unavailable=true fallback=script_load")
    run("script_load_fallback")
  end
end
-- END COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
