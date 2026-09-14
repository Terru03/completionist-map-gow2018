-- BEGIN COMPLETIONIST RAVEN GAMEPLAY SAVESTATE PROBE
-- Read-only inspection from the Raven gameplay/subobject Lua context.
-- No save-state creation, mutation, quest writes, or progression writes.
do
  local prefix = "[CompletionistRavenSaveEnvProbe] "
  local attempts = 0
  local maxAttempts = 24
  local foundSaveRoot = false
  local visited = {}
  local nodeCount = 0
  local maxNodes = 50000
  local maxDepth = 10
  local ravenKilledHits = 0

  local function log(msg)
    print(prefix .. msg)
  end

  local function safeToString(v)
    local ok, s = pcall(tostring, v)
    if ok then return s end
    return "<tostring-error>"
  end

  local function objectDetail(v)
    local parts = { "type=" .. type(v), "text=" .. safeToString(v) }
    if v ~= nil then
      local okName, name = pcall(function()
        if type(v.GetName) == "function" then return v:GetName() end
        return v.name
      end)
      if okName and name ~= nil then parts[#parts + 1] = "name=" .. safeToString(name) end
      local okPos, pos = pcall(function()
        if type(v.GetWorldPosition) == "function" then return v:GetWorldPosition() end
        return nil
      end)
      if okPos and pos ~= nil then
        parts[#parts + 1] = "pos=" .. safeToString(pos.x) .. "," .. safeToString(pos.y) .. "," .. safeToString(pos.z)
      end
    end
    return table.concat(parts, " ")
  end

  local function keyText(k)
    local t = type(k)
    if t == "string" or t == "number" or t == "boolean" then return safeToString(k) end
    local name = nil
    local ok, value = pcall(function()
      if type(k.GetName) == "function" then return k:GetName() end
      return k.name
    end)
    if ok then name = value end
    if name ~= nil then return "<" .. t .. ":" .. safeToString(name) .. ":" .. safeToString(k) .. ">" end
    return "<" .. t .. ":" .. safeToString(k) .. ">"
  end

  local interesting = {
    ravenKilled = true,
    regionSummaryQuest = true,
    mapSummaryComplete = true,
    destroyed = true,
    collected = true,
    opened = true,
    runeEnabled = true,
    broken = true,
  }

  local function summarize(path, tbl)
    local parts = {}
    local count = 0
    local ok, err = pcall(function()
      for k, v in pairs(tbl) do
        count = count + 1
        if #parts < 32 then
          parts[#parts + 1] = keyText(k) .. ":" .. type(v) .. "=" .. (type(v) == "table" and "<table>" or safeToString(v))
        end
      end
    end)
    if ok then
      log("TABLE path=" .. path .. " entries=" .. tostring(count) .. " sample=" .. table.concat(parts, ","))
    else
      log("TABLE path=" .. path .. " ok=false error=" .. safeToString(err))
    end
  end

  local function walk(value, path, depth)
    if type(value) ~= "table" or depth > maxDepth or nodeCount >= maxNodes or visited[value] then return end
    visited[value] = true
    nodeCount = nodeCount + 1
    local ok, err = pcall(function()
      for k, v in pairs(value) do
        if nodeCount >= maxNodes then break end
        local kt = type(k)
        local ktxt = keyText(k)
        local child = path .. "/" .. ktxt
        if kt == "string" and interesting[k] then
          if k == "ravenKilled" then ravenKilledHits = ravenKilledHits + 1 end
          log("FIELD key=" .. k .. " valueType=" .. type(v) .. " value=" .. safeToString(v) .. " path=" .. child)
          summarize(path, value)
        end
        if kt == "string" then
          local lower = string.lower(k)
          if string.find(lower, "raven", 1, true) or string.find(lower, "regionsummary", 1, true) then
            log("STRING_KEY value=" .. safeToString(k) .. " path=" .. child)
          end
        end
        if type(v) == "string" then
          local lower = string.lower(v)
          if string.find(lower, "raven", 1, true) or string.find(lower, "regionsummary", 1, true) then
            log("STRING_VALUE value=" .. safeToString(v) .. " path=" .. child)
          end
        elseif type(v) == "table" then
          walk(v, child, depth + 1)
        end
      end
    end)
    if not ok then log("WALK_ERROR path=" .. path .. " error=" .. safeToString(err)) end
  end

  local function inspect(source, obj)
    if foundSaveRoot or attempts >= maxAttempts then return end
    attempts = attempts + 1
    visited = {}
    nodeCount = 0
    ravenKilledHits = 0

    log("RUN source=" .. tostring(source) .. " attempt=" .. tostring(attempts) .. " readOnly=true saveWrites=false progressionWrites=false")
    log("RAVEN localKilled=" .. tostring(ravenKilled) .. " regionSummaryQuest=" .. tostring(regionSummaryQuest) .. " obj=" .. objectDetail(obj or thisObj))

    if type(engine) == "table" then
      local curObjFn = engine.CurrentlyExecutingObject
      local curSubFn = engine.CurrentlyExecutingSubObject
      if type(curObjFn) == "function" then
        local ok, v = pcall(curObjFn)
        log("CURRENT_OBJECT ok=" .. tostring(ok) .. " " .. objectDetail(ok and v or nil))
      end
      if type(curSubFn) == "function" then
        local ok, v = pcall(curSubFn)
        log("CURRENT_SUBOBJECT ok=" .. tostring(ok) .. " " .. objectDetail(ok and v or nil))
      end
    end

    local direct = rawget(_G, "__object_savestate")
    log("DIRECT_ROOT type=" .. type(direct) .. " value=" .. safeToString(direct))
    if type(direct) == "table" then
      foundSaveRoot = true
      summarize("_G.__object_savestate", direct)
      walk(direct, "_G.__object_savestate", 0)
    end

    local envRoot = nil
    local envOK = false
    if type(engine) == "table" and type(engine.DebugGetSubObjectEnvironmentRoot) == "function" then
      envOK, envRoot = pcall(engine.DebugGetSubObjectEnvironmentRoot)
    end
    log("ENV_ROOT ok=" .. tostring(envOK) .. " type=" .. type(envRoot) .. " value=" .. safeToString(envRoot))
    if envOK and type(envRoot) == "table" then
      local envCount = 0
      pcall(function()
        for ek, env in pairs(envRoot) do
          envCount = envCount + 1
          if type(env) == "table" then
            local sr = rawget(env, "__object_savestate")
            if type(sr) == "table" then
              foundSaveRoot = true
              local p = "envRoot/" .. keyText(ek) .. "/__object_savestate"
              log("ENV_SAVE_ROOT envKey=" .. keyText(ek) .. " root=" .. safeToString(sr))
              summarize(p, sr)
              walk(sr, p, 0)
            end
          end
        end
      end)
      log("ENV_COUNT count=" .. tostring(envCount))
    end

    log("SUMMARY source=" .. tostring(source) .. " foundSaveRoot=" .. tostring(foundSaveRoot) .. " nodesVisited=" .. tostring(nodeCount) .. " ravenKilledHits=" .. tostring(ravenKilledHits))
  end

  local prevLoaded = OnScriptLoaded
  function OnScriptLoaded(level, obj, ...)
    local result = prevLoaded(level, obj, ...)
    inspect("OnScriptLoaded", obj)
    return result
  end

  local prevStart = OnStart
  function OnStart(level, obj, ...)
    local result = prevStart(level, obj, ...)
    inspect("OnStart", obj)
    return result
  end

  local prevRestore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(level, obj, savedInfo, ...)
    local result = prevRestore(level, obj, savedInfo, ...)
    inspect("OnRestoreCheckpoint", obj)
    return result
  end

  log("INSTALLED gameplayContext=true readOnly=true saveWrites=false progressionWrites=false")
end
-- END COMPLETIONIST RAVEN GAMEPLAY SAVESTATE PROBE
