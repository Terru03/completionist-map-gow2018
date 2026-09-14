-- BEGIN COMPLETIONIST UNLOADED CHECKPOINT ORACLE PROBE
-- Read-only observer for the native __PickleTable.__subobjs restore source.
-- No save, progression, quest, marker, streaming, or object lifecycle writes.
do
  local prefix = "[CompletionistCheckpointOracle] "
  local ran = false
  local catalogue = {
-- @@RAVEN_ORACLE_ROWS@@
  }

  local function log(message)
    print(prefix .. message)
  end

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function normalizeWad(value)
    if type(value) ~= "string" then return nil end
    local name = string.match(value, "^Level 'WAD_(.-)'$") or
                 string.match(value, "^WAD_(.-)$") or
                 string.match(value, "^(.-)%.wad$")
    if name == nil or name == "" then return nil end
    return string.lower(name) .. ".wad"
  end

  local function exactObjectName(value)
    if value == nil then return nil end
    local attempts = {
      function() return value:GetDebugName() end,
      function() return value:GetName() end,
    }
    for _, attempt in ipairs(attempts) do
      local ok, name = pcall(attempt)
      if ok and type(name) == "string" and name ~= "" then return string.lower(name) end
    end
    return nil
  end

  local function safeCall(label, fn)
    local ok, value = pcall(fn)
    if ok then return label .. "=" .. safeToString(value) end
    return label .. "=<error:" .. safeToString(value) .. ">"
  end

  local function binaryHex(value, limit)
    if type(value) ~= "string" then return nil end
    local parts = {}
    local count = math.min(#value, limit)
    for i = 1, count do parts[#parts + 1] = string.format("%02x", string.byte(value, i)) end
    local suffix = #value > limit and "..." or ""
    return table.concat(parts) .. suffix .. ":bytes=" .. tostring(#value)
  end

  local function logObjectIdentity(value, killed)
    local fields = {
      "ravenKilled=" .. tostring(killed),
      "tostring=" .. safeToString(value),
      safeCall("GetName", function() return value:GetName() end),
      safeCall("GetDebugName", function() return value:GetDebugName() end),
      safeCall("GetDebugPath", function() return value:GetDebugPath() end),
      safeCall("Level", function() return value.Level end),
    }
    if type(engine) == "table" and type(engine.CanPickle) == "function" then
      fields[#fields + 1] = safeCall("CanPickle", function() return engine.CanPickle(value) end)
    end
    if type(cmsgpack) == "table" and type(cmsgpack.pack) == "function" then
      local ok, packed = pcall(cmsgpack.pack, value)
      fields[#fields + 1] = "cmsgpackOk=" .. tostring(ok)
      fields[#fields + 1] = "cmsgpack=" .. safeToString(binaryHex(packed, 128))
      if not ok then fields[#fields + 1] = "cmsgpackError=" .. safeToString(packed) end
    end
    if type(debug) == "table" and type(debug.getmetatable) == "function" then
      local ok, mt = pcall(debug.getmetatable, value)
      local names = {}
      if ok and type(mt) == "table" then
        for key, member in pairs(mt) do names[#names + 1] = safeToString(key) .. ":" .. type(member) end
        table.sort(names)
      end
      fields[#fields + 1] = "metatableOk=" .. tostring(ok)
      fields[#fields + 1] = "metatable=" .. table.concat(names, ",")
    end
    log("IDENTITY_DIAGNOSTIC " .. table.concat(fields, " "))
  end

  local function exactObjectWad(value)
    if value == nil then return nil end
    local attempts = {
      function() return value.Level end,
      function() return value:Level() end,
    }
    for _, attempt in ipairs(attempts) do
      local ok, level = pcall(attempt)
      if ok and level ~= nil then
        local wad = normalizeWad(safeToString(level))
        if wad ~= nil then return wad end
      end
    end
    return nil
  end

  local exactRows = {}
  for _, row in ipairs(catalogue) do
    local names = { row.ObjectName }
    if string.sub(row.ObjectName, 1, 2) == "go" then
      names[#names + 1] = string.sub(row.ObjectName, 3)
    end
    for _, name in ipairs(names) do
      local key = string.lower(row.Wad .. "|" .. name)
      if exactRows[key] ~= nil then error("duplicate exact Raven identity: " .. key) end
      exactRows[key] = row
    end
  end

  local function addRoot(roots, seen, label, value)
    if type(value) == "table" and not seen[value] then
      seen[value] = true
      roots[#roots + 1] = { Label = label, Value = value }
    end
  end

  local function roots()
    local result, seen = {}, {}
    addRoot(result, seen, "_G", _G)
    if type(getfenv) == "function" then
      for _, level in ipairs({ 0, 1, 2, 3 }) do
        local ok, value = pcall(getfenv, level)
        if ok then addRoot(result, seen, "getfenv(" .. tostring(level) .. ")", value) end
      end
    end
    if type(engine) == "table" and type(engine.DebugGetSubObjectEnvironmentRoot) == "function" then
      local ok, environmentRoot = pcall(engine.DebugGetSubObjectEnvironmentRoot)
      log("ENVIRONMENT_ROOT ok=" .. tostring(ok) .. " type=" .. type(environmentRoot) ..
          " value=" .. safeToString(environmentRoot))
      if ok and type(environmentRoot) == "table" then
        addRoot(result, seen, "DebugGetSubObjectEnvironmentRoot", environmentRoot)
        local count = 0
        for key, environment in pairs(environmentRoot) do
          count = count + 1
          if count > 10000 then
            log("ENVIRONMENT_ROOT_REFUSED reason=entry_limit")
            break
          end
          addRoot(result, seen, "DebugGetSubObjectEnvironmentRoot[" .. safeToString(key) .. "]", environment)
        end
        log("ENVIRONMENT_ROOT entries=" .. tostring(count) .. " roots=" .. tostring(#result))
      end
    end
    if type(debug) == "table" and type(debug.getfenv) == "function" then
      local candidates = {
        { "engine.CurrentlyExecutingObject", type(engine) == "table" and engine.CurrentlyExecutingObject or nil },
        { "engine.DebugGetSubObjectEnvironmentRoot", type(engine) == "table" and engine.DebugGetSubObjectEnvironmentRoot or nil },
        { "game.FindLevel", type(game) == "table" and game.FindLevel or nil },
      }
      for _, candidate in ipairs(candidates) do
        if type(candidate[2]) == "function" then
          local ok, value = pcall(debug.getfenv, candidate[2])
          log("DEBUG_GETFENV target=" .. candidate[1] .. " ok=" .. tostring(ok) ..
              " type=" .. type(value) .. " value=" .. safeToString(value))
          if ok then addRoot(result, seen, "debug.getfenv(" .. candidate[1] .. ")", value) end
        end
      end
    end
    if type(debug) == "table" and type(debug.getregistry) == "function" then
      local ok, registry = pcall(debug.getregistry)
      log("DEBUG_REGISTRY ok=" .. tostring(ok) .. " type=" .. type(registry) ..
          " value=" .. safeToString(registry))
      if ok and type(registry) == "table" then
        local queue = { { Label = "debug.registry", Value = registry, Depth = 0 } }
        local queued = { [registry] = true }
        local index, edges = 1, 0
        while index <= #queue and #queue < 20000 do
          local item = queue[index]
          index = index + 1
          addRoot(result, seen, item.Label, item.Value)
          if item.Depth < 3 then
            for key, value in pairs(item.Value) do
              edges = edges + 1
              if edges > 100000 then break end
              if type(value) == "table" and not queued[value] then
                queued[value] = true
                queue[#queue + 1] = {
                  Label = item.Label .. "[" .. safeToString(key) .. "]",
                  Value = value,
                  Depth = item.Depth + 1,
                }
              end
            end
          end
          if edges > 100000 then break end
        end
        log("DEBUG_REGISTRY_GRAPH tables=" .. tostring(#queue) .. " edges=" .. tostring(edges) ..
            " roots=" .. tostring(#result) .. " bounded=true")
      end
    end
    return result
  end

  local function availableWads()
    local result = { known = false, values = {} }
    if type(engine) ~= "table" or type(engine.GetAvailableWads) ~= "function" then return result end
    local ok, values = pcall(engine.GetAvailableWads)
    if not ok or type(values) ~= "table" then
      log("AVAILABLE_WADS ok=" .. tostring(ok) .. " type=" .. type(values) .. " value=" .. safeToString(values))
      return result
    end
    local count = 0
    for key, value in pairs(values) do
      count = count + 1
      for _, candidate in ipairs({ key, value }) do
        local wad = normalizeWad(safeToString(candidate))
        if wad ~= nil then result.values[wad] = true end
      end
    end
    local names = {}
    for wad in pairs(result.values) do names[#names + 1] = wad end
    table.sort(names)
    result.known = #names > 0
    log("AVAILABLE_WADS ok=true entries=" .. tostring(count) .. " normalized=" .. tostring(#names) ..
        " values=" .. table.concat(names, ","))
    return result
  end

  local function currentWad()
    if type(engine) ~= "table" or type(engine.CurrentlyExecutingObject) ~= "function" then return nil end
    local ok, value = pcall(engine.CurrentlyExecutingObject)
    if not ok then return nil end
    return normalizeWad(safeToString(value))
  end

  local function wadLevelName(wad)
    if type(wad) ~= "string" then return nil end
    local stem = string.match(wad, "^(.-)%.wad$")
    if stem == nil or stem == "" then return nil end
    return "WAD_" .. stem
  end

  local residencyCache = {}
  local function residentStatus(wad, active, executingWad)
    if wad == executingWad then return "true" end
    if active.known then return active.values[wad] and "true" or "false" end
    if residencyCache[wad] ~= nil then return residencyCache[wad] end
    local levelName = wadLevelName(wad)
    if levelName ~= nil and type(game) == "table" and type(game.FindLevel) == "function" then
      local ok, level = pcall(game.FindLevel, levelName)
      if ok then
        local result = level ~= nil and "true" or "false"
        residencyCache[wad] = result
        log("RESIDENCY wad=" .. wad .. " source=game.FindLevel level=" .. levelName ..
            " resident=" .. result .. " value=" .. safeToString(level))
        return result
      end
    end
    return "unknown"
  end

  local function aggregate(parent)
    if type(game) ~= "table" or type(game.QuestManager) ~= "table" or
       type(game.QuestManager.GetQuestProgressAndGoal) ~= "function" then return nil, nil end
    local ok, progress, goal = pcall(game.QuestManager.GetQuestProgressAndGoal, parent)
    if not ok then return nil, nil end
    return progress, goal
  end

  local function scan(reason, currentObject)
    if ran then return end
    ran = true
    local active = availableWads()
    local executingWad = currentWad()
    log("RUN reason=" .. safeToString(reason) .. " roots=" .. tostring(#roots()) ..
        " currentWad=" .. safeToString(executingWad) ..
        " readOnly=true progressionWrites=false saveWrites=false streamingWrites=false")

    local matchedById = {}
    local unknown = 0
    local pickleRoots = 0
    local subobjectRecords = 0
    local seenPickles = {}
    for _, root in ipairs(roots()) do
      for _, pickleName in ipairs({ "__PickleTable", "__SoftPickleTable" }) do
        local pickle = rawget(root.Value, pickleName)
        if type(pickle) == "table" and not seenPickles[pickle] then
          seenPickles[pickle] = true
          pickleRoots = pickleRoots + 1
          local subobjects = rawget(pickle, "__subobjs")
          log("PICKLE root=" .. root.Label .. " name=" .. pickleName ..
              " subobjectsType=" .. type(subobjects) .. " value=" .. safeToString(subobjects))
          if type(subobjects) == "table" then
            for object, savedInfo in pairs(subobjects) do
              subobjectRecords = subobjectRecords + 1
              local killed = nil
              if type(savedInfo) == "table" then killed = rawget(savedInfo, "ravenKilled") end
              if type(killed) == "boolean" then
                local wad = exactObjectWad(object)
                local objectName = exactObjectName(object)
                local lookup = wad ~= nil and objectName ~= nil and string.lower(wad .. "|" .. objectName) or nil
                local row = lookup ~= nil and exactRows[lookup] or nil
                local resident = residentStatus(wad, active, executingWad)
                if row ~= nil then
                  local old = matchedById[row.CatalogueId]
                  if old ~= nil and old ~= killed then
                    matchedById[row.CatalogueId] = nil
                    unknown = unknown + 1
                    log("STATE_REFUSED reason=conflicting_duplicate catalogueId=" .. row.CatalogueId)
                  elseif old == nil then
                    matchedById[row.CatalogueId] = killed
                    log("EXACT_STATE catalogueId=" .. row.CatalogueId ..
                        " wad=" .. row.Wad .. " object=" .. row.ObjectName ..
                        " parent=" .. row.ParentQuest .. " ravenKilled=" .. tostring(killed) ..
                        " resident=" .. resident .. " currentObject=" .. tostring(object == currentObject) ..
                        " identity=pickle_object_token_plus_exact_wad_object_name")
                  end
                else
                  unknown = unknown + 1
                  logObjectIdentity(object, killed)
                  log("STATE_UNKNOWN reason=exact_identity_unavailable wad=" .. safeToString(wad) ..
                      " object=" .. safeToString(objectName) .. " resident=" .. resident ..
                      " objectValue=" .. safeToString(object))
                end
              end
            end
          end
        end
      end
    end

    local groups = {}
    local matched = 0
    local unloaded = 0
    for _, row in ipairs(catalogue) do
      local value = matchedById[row.CatalogueId]
      if value ~= nil then
        matched = matched + 1
        local group = groups[row.ParentQuest] or { seen = 0, killed = 0 }
        group.seen = group.seen + 1
        if value then group.killed = group.killed + 1 end
        groups[row.ParentQuest] = group
        if residentStatus(row.Wad, active, executingWad) == "false" then unloaded = unloaded + 1 end
      end
    end
    for parent, group in pairs(groups) do
      local progress, goal = aggregate(parent)
      log("REGION_CHECK parent=" .. parent .. " exactSeen=" .. tostring(group.seen) ..
          " exactKilled=" .. tostring(group.killed) .. " aggregateProgress=" .. safeToString(progress) ..
          " aggregateGoal=" .. safeToString(goal) ..
          " agrees=" .. tostring(progress == group.killed and goal == group.seen))
    end
    log("SUMMARY pickleRoots=" .. tostring(pickleRoots) .. " subobjectRecords=" .. tostring(subobjectRecords) ..
        " exactRavens=" .. tostring(matched) .. " exactUnloadedRavens=" .. tostring(unloaded) ..
        " unknownRavenRecords=" .. tostring(unknown) .. " availableWadsKnown=" .. tostring(active.known) ..
        " gate=fail_closed_until_fixture_validation")
  end

  local previousRestore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(level, object, savedInfo, ...)
    scan("OnRestoreCheckpoint:before", object)
    return previousRestore(level, object, savedInfo, ...)
  end

  log("INSTALLED source=precisionchallenge.lua exactIdentity=pickle_object_token_plus_exact_wad_object_name " ..
      "coordinates=false ordering=false aggregateIdentity=false writes=false")
end
-- END COMPLETIONIST UNLOADED CHECKPOINT ORACLE PROBE
