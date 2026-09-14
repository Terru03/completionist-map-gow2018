-- BEGIN COMPLETIONIST OBJECT SAVESTATE RUNTIME PROBE
-- Read-only traversal of the restored core.save graph published as _G.__object_savestate.
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
  local maxNodes = 25000
  local maxDepth = 8
  local nodeCount = 0
  local visited = {}

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

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. safeToString(reason) .. " readOnly=true progressionWrites=false saveWrites=false")

    local root = rawget(_G, "__object_savestate")
    log("ROOT type=" .. type(root) .. " value=" .. safeToString(root))
    if type(root) ~= "table" then
      log("DONE rootUnavailable=true")
      return
    end

    local topCount = 0
    local topKeyTypes = {}
    local topValueTypes = {}
    local topSamples = 0
    local ok, err = pcall(function()
      for k, v in pairs(root) do
        topCount = topCount + 1
        bump(topKeyTypes, type(k))
        bump(topValueTypes, type(v))
        local top = keyText(k)
        if topSamples < 96 then
          topSamples = topSamples + 1
          log("TOP index=" .. tostring(topCount) ..
              " keyType=" .. type(k) ..
              " key=" .. top ..
              " valueType=" .. type(v))
        end
        if stringInteresting(k) then
          log("TOP_INTERESTING_KEY key=" .. top .. " valueType=" .. type(v))
        end
        if type(v) == "table" then
          walk(v, "root/" .. top, 1, top)
        elseif stringInteresting(v) then
          log("TOP_INTERESTING_VALUE key=" .. top .. " value=" .. safeToString(v))
        end
      end
    end)

    if not ok then
      log("ROOT_ENUM_ERROR error=" .. safeToString(err))
    end

    local function emitCounts(label, tbl)
      local keys = {}
      for k in pairs(tbl) do keys[#keys + 1] = k end
      table.sort(keys)
      for _, k in ipairs(keys) do
        log(label .. " key=" .. tostring(k) .. " count=" .. tostring(tbl[k]))
      end
    end

    log("SUMMARY topCount=" .. tostring(topCount) ..
        " nodesVisited=" .. tostring(nodeCount) ..
        " ravenKilledHits=" .. tostring(ravenKilledHits) ..
        " interestingStringHits=" .. tostring(interestingStringCount) ..
        " maxNodes=" .. tostring(maxNodes) ..
        " maxDepth=" .. tostring(maxDepth))
    emitCounts("TOP_KEY_TYPE", topKeyTypes)
    emitCounts("TOP_VALUE_TYPE", topValueTypes)
    emitCounts("INTERESTING_FIELD_COUNT", interestingKeyCounts)
    log("DONE readOnly=true progressionWrites=false saveWrites=false")
  end

  _G.CompletionistSaveStateProbe_Run = run

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
-- END COMPLETIONIST OBJECT SAVESTATE RUNTIME PROBE
