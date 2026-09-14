-- BEGIN COMPLETIONIST OBJECT SAVESTATE RUNTIME PROBE
-- Read-only traversal of restored core.save graphs, including subobject Lua environments.
-- No save-state creation, mutation, quest writes, or progression writes.
do
  local prefix = "[CompletionistSaveStateProbe] "
  local ran = false

  local function log(message)
    print(prefix .. message)
  end

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function keyText(key)
    local t = type(key)
    if t == "string" then return key end
    if t == "number" or t == "boolean" then return tostring(key) end
    return "<" .. t .. ":" .. safeToString(key) .. ">"
  end

  local interestingKeys = {
    ravenKilled = true,
    mapSummaryComplete = true,
    destroyed = true,
    collected = true,
    opened = true,
    runeEnabled = true,
    broken = true,
    regionSummaryQuest = true,
  }

  local keyCounts = {}
  local interestingKeyCounts = {}
  local interestingStringCount = 0
  local ravenKilledHits = 0
  local maxNodes = 50000
  local maxDepth = 8
  local nodeCount = 0
  local visited = {}
  local rootsVisited = 0

  local function bump(tbl, key)
    tbl[key] = (tbl[key] or 0) + 1
  end

  local function stringInteresting(value)
    if type(value) ~= "string" then return false end
    local lower = string.lower(value)
    return string.find(lower, "raven", 1, true) ~= nil or
           string.find(lower, "regionsummary", 1, true) ~= nil or
           string.find(lower, "collectible", 1, true) ~= nil or
           string.find(lower, "nornir", 1, true) ~= nil
  end

  local function summarizeTable(path, tbl, limit)
    local parts = {}
    local n = 0
    local ok, err = pcall(function()
      for k, v in pairs(tbl) do
        n = n + 1
        if #parts < limit then
          parts[#parts + 1] = keyText(k) .. ":" .. type(v)
        end
      end
    end)
    if ok then
      log("TABLE_SUMMARY path=" .. path .. " entries=" .. tostring(n) .. " sample=" .. table.concat(parts, ","))
    else
      log("TABLE_SUMMARY path=" .. path .. " ok=false error=" .. safeToString(err))
    end
  end

  local function walk(value, path, depth, topKey)
    if nodeCount >= maxNodes then return end
    nodeCount = nodeCount + 1

    if type(value) ~= "table" then return end
    if visited[value] then return end
    visited[value] = true
    if depth > maxDepth then return end

    local ok, err = pcall(function()
      for k, v in pairs(value) do
        if nodeCount >= maxNodes then break end
        local kt = type(k)
        bump(keyCounts, kt)
        local ktext = keyText(k)
        local childPath = path .. "/" .. ktext

        if kt == "string" and interestingKeys[k] then
          bump(interestingKeyCounts, k)
          if k == "ravenKilled" then ravenKilledHits = ravenKilledHits + 1 end
          log("FIELD key=" .. k ..
              " valueType=" .. type(v) ..
              " value=" .. safeToString(v) ..
              " path=" .. childPath ..
              " topKey=" .. topKey)
          summarizeTable(path, value, 24)
        end

        if stringInteresting(k) then
          interestingStringCount = interestingStringCount + 1
          log("STRING_KEY value=" .. safeToString(k) .. " path=" .. childPath .. " topKey=" .. topKey)
        end
        if stringInteresting(v) then
          interestingStringCount = interestingStringCount + 1
          log("STRING_VALUE value=" .. safeToString(v) .. " path=" .. childPath .. " topKey=" .. topKey)
        end

        if type(v) == "table" then
          walk(v, childPath, depth + 1, topKey)
        end
      end
    end)
    if not ok then
      log("WALK_ERROR path=" .. path .. " error=" .. safeToString(err))
    end
  end

  local function inspectSaveRoot(root, label)
    if type(root) ~= "table" then return false end
    rootsVisited = rootsVisited + 1
    log("SAVE_ROOT label=" .. label .. " type=table value=" .. safeToString(root))
    summarizeTable(label, root, 32)
    walk(root, label, 0, label)
    return true
  end

  local function inspectEnvironment(envKey, env, index)
    if type(env) ~= "table" then return 0 end
    local label = "subenv[" .. tostring(index) .. "] key=" .. keyText(envKey)
    local found = 0

    local directState = rawget(env, "__object_savestate")
    if type(directState) == "table" then
      found = found + 1
      inspectSaveRoot(directState, label .. "/__object_savestate")
    end

    local envGlobal = rawget(env, "_G")
    if type(envGlobal) == "table" and envGlobal ~= env then
      local nestedState = rawget(envGlobal, "__object_savestate")
      if type(nestedState) == "table" then
        found = found + 1
        inspectSaveRoot(nestedState, label .. "/_G/__object_savestate")
      end
    end

    for key in pairs(interestingKeys) do
      local value = rawget(env, key)
      if value ~= nil then
        log("ENV_FIELD env=" .. label .. " key=" .. key .. " type=" .. type(value) .. " value=" .. safeToString(value))
      end
    end

    local thisObj = rawget(env, "thisObj")
    if thisObj ~= nil then
      log("ENV_THISOBJ env=" .. label .. " type=" .. type(thisObj) .. " value=" .. safeToString(thisObj))
    end

    return found
  end

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. safeToString(reason) .. " readOnly=true progressionWrites=false saveWrites=false subobjectScan=true")

    local directRoot = rawget(_G, "__object_savestate")
    log("ROOT type=" .. type(directRoot) .. " value=" .. safeToString(directRoot))
    if type(directRoot) == "table" then
      inspectSaveRoot(directRoot, "mapGlobal/__object_savestate")
    end

    local debugFn = nil
    if type(engine) == "table" then
      local ok, value = pcall(function() return engine.DebugGetSubObjectEnvironmentRoot end)
      if ok then debugFn = value end
    end
    log("DEBUG_ENV_ROOT_FN type=" .. type(debugFn))

    local envRoot = nil
    if type(debugFn) == "function" then
      local ok, value = pcall(debugFn)
      if ok then
        envRoot = value
        log("DEBUG_ENV_ROOT_CALL ok=true type=" .. type(value) .. " value=" .. safeToString(value))
      else
        log("DEBUG_ENV_ROOT_CALL ok=false error=" .. safeToString(value))
      end
    end

    local envCount = 0
    local envSaveRoots = 0
    local envTableCount = 0
    local envScanLimit = 10000
    if type(envRoot) == "table" then
      local ok, err = pcall(function()
        for envKey, env in pairs(envRoot) do
          envCount = envCount + 1
          if envCount > envScanLimit then break end
          if type(env) == "table" then
            envTableCount = envTableCount + 1
            envSaveRoots = envSaveRoots + inspectEnvironment(envKey, env, envCount)
          elseif envCount <= 64 then
            log("ENV_NON_TABLE index=" .. tostring(envCount) .. " key=" .. keyText(envKey) .. " type=" .. type(env) .. " value=" .. safeToString(env))
          end
        end
      end)
      if not ok then
        log("ENV_ENUM_ERROR error=" .. safeToString(err))
      end
    end

    local function emitCounts(label, tbl)
      local keys = {}
      for k in pairs(tbl) do keys[#keys + 1] = k end
      table.sort(keys)
      for _, k in ipairs(keys) do
        log(label .. " key=" .. tostring(k) .. " count=" .. tostring(tbl[k]))
      end
    end

    log("SUMMARY rootsVisited=" .. tostring(rootsVisited) ..
        " envCount=" .. tostring(envCount) ..
        " envTableCount=" .. tostring(envTableCount) ..
        " envSaveRoots=" .. tostring(envSaveRoots) ..
        " nodesVisited=" .. tostring(nodeCount) ..
        " ravenKilledHits=" .. tostring(ravenKilledHits) ..
        " interestingStringHits=" .. tostring(interestingStringCount) ..
        " maxNodes=" .. tostring(maxNodes) ..
        " maxDepth=" .. tostring(maxDepth))
    emitCounts("INTERESTING_FIELD_COUNT", interestingKeyCounts)
    log("DONE readOnly=true progressionWrites=false saveWrites=false subobjectScan=true")
  end

  _G.CompletionistSaveStateProbe_Run = run

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler subobjectScan=true")
  else
    log("HOOK unavailable=true fallback=script_load subobjectScan=true")
    run("script_load_fallback")
  end
end
-- END COMPLETIONIST OBJECT SAVESTATE RUNTIME PROBE
