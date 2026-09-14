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
    result.known = true
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
              local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
              if type(killed) == "boolean" then
                local wad = exactObjectWad(object)
                local objectName = exactObjectName(object)
                local lookup = wad ~= nil and objectName ~= nil and string.lower(wad .. "|" .. objectName) or nil
                local row = lookup ~= nil and exactRows[lookup] or nil
                local resident = "unknown"
                if active.known and wad ~= nil then resident = active.values[wad] and "true" or "false" end
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
        if active.known and not active.values[row.Wad] then unloaded = unloaded + 1 end
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
