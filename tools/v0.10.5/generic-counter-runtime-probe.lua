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

  local function inspectMapStateBindings(self)
    if self == nil then
      log("SELF_BINDINGS self_nil=true")
      return
    end

    local names = {
      "GetCounter", "GetCounterChild", "GetCounterChildrenCount",
      "GetCounterName", "GetRefBool", "GetRefInt", "GetRefFloat",
      "GetRefString", "LevelWads", "UIWads", "LoadCheck",
      "FindLevel", "EvaluateLoadZones", "ResolveGameObject",
      "GetCurrentSlot", "GetLatestSlot", "GetSlotCount",
      "StartTimer",
    }
    local funcs = {}
    for _, name in ipairs(names) do
      local ok, member = pcall(function() return self[name] end)
      funcs[name] = ok and member or nil
      log("SELF_TYPE name=" .. name .. " lookupOK=" .. tostring(ok) ..
          " type=" .. type(funcs[name]))
    end

    local parent = "RegionSummary_VF_Raven_Parent"
    local knownGuid = "642d0d16-4af0-a5d4-076e-77933c549a5d"
    local probes = {
      {"GetCounter(parent)", "GetCounter", {parent}},
      {"GetCounterChildrenCount(parent)", "GetCounterChildrenCount", {parent}},
      {"GetCounterChild(parent,0)", "GetCounterChild", {parent, 0}},
      {"GetCounterChild(parent,1)", "GetCounterChild", {parent, 1}},
      {"GetCounterChild(parent,2)", "GetCounterChild", {parent, 2}},
      {"GetCounterName(parent)", "GetCounterName", {parent}},
      {"GetRefBool(guid)", "GetRefBool", {knownGuid}},
      {"LevelWads()", "LevelWads", {}},
      {"UIWads()", "UIWads", {}},
      {"LoadCheck()", "LoadCheck", {}},
      {"ResolveGameObject(guid)", "ResolveGameObject", {knownGuid}},
      {"GetCurrentSlot()", "GetCurrentSlot", {}},
      {"GetLatestSlot()", "GetLatestSlot", {}},
      {"GetSlotCount()", "GetSlotCount", {}},
    }

    for _, probe in ipairs(probes) do
      local label, name, args = probe[1], probe[2], probe[3]
      local fn = funcs[name]
      if type(fn) == "function" then
        safeCall("SELF " .. label, function()
          return fn(self, table.unpack(args))
        end)
      else
        log("SELF_CALL label=" .. label .. " skipped=true type=" .. type(fn))
      end
    end

    log("SELF_BINDINGS_DONE progressionWrites=false questWrites=false")
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

  local function dumpTable(prefix, value, depth, seen)
    depth = depth or 0
    seen = seen or {}
    if type(value) ~= "table" then
      log(prefix .. " type=" .. type(value) .. " value=" .. tostring(value))
      return
    end
    if seen[value] then
      log(prefix .. " cycle=true")
      return
    end
    seen[value] = true
    local keys = {}
    for k, _ in pairs(value) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    log(prefix .. " tableKeys=" .. tostring(#keys))
    for _, k in ipairs(keys) do
      local v = value[k]
      local p = prefix .. "[" .. tostring(k) .. "]"
      if type(v) == "table" and depth < 3 then
        dumpTable(p, v, depth + 1, seen)
      else
        log(p .. " type=" .. type(v) .. " value=" .. tostring(v))
      end
    end
  end

  local function inspectGameNamespace()
    if type(game) ~= "table" then
      log("GAME_NAMESPACE unavailable=true")
      return
    end
    local interesting = {
      "save","pickle","persist","checkpoint","restore","wad","subobject",
      "level","world","object","quest","stream","load","resolve"
    }
    local function isInteresting(text)
      text = string.lower(tostring(text or ""))
      for _, needle in ipairs(interesting) do
        if string.find(text, needle, 1, true) then return true end
      end
      return false
    end
    local seen = {}
    local queue = {{value=game,path="game",depth=0}}
    local visited = 0
    while #queue > 0 and visited < 4000 do
      local item = table.remove(queue, 1)
      local value = item.value
      if type(value) == "table" and not seen[value] then
        seen[value] = true
        visited = visited + 1
        local ok, mt = pcall(getmetatable, value)
        log("GAME_TABLE path=" .. item.path .. " depth=" .. tostring(item.depth) ..
            " metatableType=" .. (ok and type(mt) or "error"))
        local count = 0
        for k, v in pairs(value) do
          count = count + 1
          if isInteresting(k) or isInteresting(item.path) then
            log("GAME_MEMBER path=" .. item.path .. "." .. tostring(k) ..
                " type=" .. type(v) .. " value=" .. tostring(v))
          end
          if item.depth < 3 and type(v) == "table" and not seen[v] then
            queue[#queue + 1] = {
              value=v,
              path=item.path .. "." .. tostring(k),
              depth=item.depth + 1,
            }
          end
        end
        if ok and type(mt) == "table" then
          local idx = rawget(mt, "__index")
          log("GAME_METATABLE path=" .. item.path ..
              " indexType=" .. type(idx) .. " identity=" .. tostring(rawget(mt, "__identity")))
          if item.depth < 3 and type(idx) == "table" and not seen[idx] then
            queue[#queue + 1] = {
              value=idx,
              path=item.path .. ".__index",
              depth=item.depth + 1,
            }
          end
        end
        log("GAME_TABLE_DONE path=" .. item.path .. " rawMembers=" .. tostring(count))
      end
    end
    log("GAME_NAMESPACE_DONE tables=" .. tostring(visited))
  end

  local function inspectQuestManagerClosureAddresses(qm)
    local names = {
      "GetQuestProgressAndGoal",
      "GetQuestState",
      "GetChildrenQuestIds",
      "GetTrackingInfo",
      "GetCompletionIndex",
    }
    for _, name in ipairs(names) do
      local fn = qm and qm[name] or nil
      log("QM_CLOSURE name=" .. name .. " type=" .. type(fn) .. " tostring=" .. tostring(fn))
      if type(fn) == "function" and type(debug) == "table" and type(debug.getinfo) == "function" then
        local ok, info = pcall(debug.getinfo, fn, "Snu")
        if ok and type(info) == "table" then
          log("QM_CLOSURE_INFO name=" .. name ..
              " what=" .. tostring(info.what) ..
              " source=" .. tostring(info.source) ..
              " short_src=" .. tostring(info.short_src) ..
              " linedefined=" .. tostring(info.linedefined) ..
              " lastlinedefined=" .. tostring(info.lastlinedefined) ..
              " nups=" .. tostring(info.nups))
        else
          log("QM_CLOSURE_INFO name=" .. name .. " ok=false value=" .. tostring(info))
        end
      end
    end
  end

  local function inspectQuestManagerSurface(qm)
    if type(qm) ~= "table" then
      log("QM_SURFACE unavailable=true")
      return
    end
    local rows = {}
    for k, v in pairs(qm) do
      rows[#rows + 1] = {key=tostring(k), typ=type(v), value=tostring(v)}
    end
    table.sort(rows, function(a,b) return a.key < b.key end)
    log("QM_SURFACE_BEGIN count=" .. tostring(#rows))
    for _, row in ipairs(rows) do
      log("QM_MEMBER key=" .. row.key .. " type=" .. row.typ .. " value=" .. row.value)
    end
    log("QM_SURFACE_END")

    local partialParents = {
      "RegionSummary_HSH_Raven_Parent",
      "RegionSummary_PP_Raven_Parent",
      "RegionSummary_RP_Raven_Parent",
      "RegionSummary_VF_Raven_Parent",
      "RegionSummary_FD_Raven_Parent",
      "RegionSummary_CALS_Raven_Parent",
    }
    local getTracking = qm.GetTrackingInfo
    local getCompletion = qm.GetCompletionIndex
    for _, parent in ipairs(partialParents) do
      if type(getTracking) == "function" then
        local ok, value = pcall(getTracking, parent)
        log("QM_TRACKING parent=" .. parent .. " ok=" .. tostring(ok) ..
            " type=" .. type(value) .. " value=" .. tostring(value))
        if ok and type(value) == "table" then
          dumpTable("QM_TRACKING_TABLE[" .. parent .. "]", value, 0, {})
        end
      end
      if type(getCompletion) == "function" then
        local ok, value = pcall(getCompletion, parent)
        log("QM_COMPLETION_INDEX parent=" .. parent .. " ok=" .. tostring(ok) ..
            " type=" .. type(value) .. " value=" .. tostring(value))
      end
    end
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

  local function run(reason, self)
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

    inspectQuestManagerClosureAddresses(qm)
    inspectGameNamespace()
    inspectQuestManagerSurface(qm)
    inspectMapStateBindings(self)
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
      run("MapCollisionChangeHandler", self)
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler questManagerApi=true childKeyEnumeration=true")
    if type(game) == "table" and type(game.QuestManager) == "table" then
      inspectQuestManagerClosureAddresses(game.QuestManager)
      log("QM_CLOSURE_IMMEDIATE_DONE trigger=mapmenu_load")
    end
  else
    log("HOOK unavailable=true fallback=script_load")
    run("script_load_fallback", nil)
  end
end
-- END COMPLETIONIST GENERIC COUNTER RUNTIME PROBE
