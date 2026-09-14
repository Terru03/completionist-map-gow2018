-- BEGIN COMPLETIONIST RAVEN PREVUNPICKLE IDENTITY PROBE
-- Read-only reverse-reference probe for the native __prevunpickle bookkeeping table.
-- Goal: find a stable serialized identity associated with exact Raven GameObject keys.
-- No save, progression, quest, marker, streaming, or object lifecycle writes.
do
  local prefix = "[CompletionistPrevUnpickleProbe] "
  local scanned = false
  local MAX_TABLES = 20000
  local MAX_EDGES = 120000
  local MAX_DEPTH = 5
  local MAX_MATCHES = 200

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function log(message)
    print(prefix .. message)
  end

  local function scalar(value)
    local t = type(value)
    return t == "string" or t == "number" or t == "boolean" or t == "nil"
  end

  local function same(a, b)
    local ok, result = pcall(rawequal, a, b)
    return ok and result == true
  end

  local function objectLabel(object)
    local parts = { safeToString(object) }
    local okName, name = pcall(function() return object:GetName() end)
    if okName then parts[#parts + 1] = "name=" .. safeToString(name) end
    local okLevel, level = pcall(function() return object.Level end)
    if okLevel then parts[#parts + 1] = "level=" .. safeToString(level) end
    return table.concat(parts, " ")
  end

  local function scalarSiblings(tab, skipKey, limit)
    local parts, count = {}, 0
    local ok = pcall(function()
      for key, value in pairs(tab) do
        if key ~= skipKey and scalar(key) and scalar(value) then
          count = count + 1
          if count <= limit then
            parts[#parts + 1] = safeToString(key) .. "=" .. safeToString(value)
          end
        elseif key ~= skipKey and scalar(key) and type(value) ~= "table" and type(value) ~= "function" then
          count = count + 1
          if count <= limit then
            parts[#parts + 1] = safeToString(key) .. "=<" .. type(value) .. ":" .. safeToString(value) .. ">"
          end
        end
      end
    end)
    if not ok then return "<siblings-error>" end
    table.sort(parts)
    return "{" .. table.concat(parts, ",") .. (count > limit and ",..." or "") .. "}:count=" .. tostring(count)
  end

  local function collectRavens(root)
    local result = {}
    local seenPickles = {}
    for _, pickleName in ipairs({ "__PickleTable", "__SoftPickleTable" }) do
      local pickle = rawget(root, pickleName)
      if type(pickle) == "table" and not seenPickles[pickle] then
        seenPickles[pickle] = true
        local subobjects = rawget(pickle, "__subobjs")
        if type(subobjects) == "table" then
          for object, savedInfo in pairs(subobjects) do
            local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
            if type(killed) == "boolean" then
              result[#result + 1] = { Object = object, Killed = killed, Pickle = pickleName }
            end
          end
        end
      end
    end
    return result
  end

  local function targetIndex(targets, value)
    for i, target in ipairs(targets) do
      if same(target.Object, value) then return i end
    end
    return nil
  end

  local function inspectPrev(prev, targets, label)
    local queue = { { Value = prev, Path = label, Depth = 0 } }
    local seen = { [prev] = true }
    local index, tables, edges, matches = 1, 0, 0, 0
    local typeCounts = {}

    while index <= #queue and tables < MAX_TABLES and edges < MAX_EDGES do
      local item = queue[index]
      index = index + 1
      tables = tables + 1
      local ok, err = pcall(function()
        for key, value in pairs(item.Value) do
          edges = edges + 1
          if edges > MAX_EDGES then break end
          local kt, vt = type(key), type(value)
          typeCounts[kt .. "->" .. vt] = (typeCounts[kt .. "->" .. vt] or 0) + 1

          local keyTarget = targetIndex(targets, key)
          local valueTarget = targetIndex(targets, value)
          if (keyTarget or valueTarget) and matches < MAX_MATCHES then
            matches = matches + 1
            local target = targets[keyTarget or valueTarget]
            log("MATCH path=" .. item.Path ..
                " depth=" .. tostring(item.Depth) ..
                " relation=" .. (keyTarget and "target_is_key" or "target_is_value") ..
                " ravenKilled=" .. tostring(target.Killed) ..
                " pickle=" .. target.Pickle ..
                " keyType=" .. kt .. " key=" .. safeToString(key) ..
                " valueType=" .. vt .. " value=" .. safeToString(value) ..
                " siblings=" .. scalarSiblings(item.Value, key, 24) ..
                " object=" .. objectLabel(target.Object))
          end

          if item.Depth < MAX_DEPTH and type(value) == "table" and not seen[value] then
            seen[value] = true
            queue[#queue + 1] = {
              Value = value,
              Path = item.Path .. "[" .. safeToString(key) .. "]",
              Depth = item.Depth + 1,
            }
          end
          if item.Depth < MAX_DEPTH and type(key) == "table" and not seen[key] then
            seen[key] = true
            queue[#queue + 1] = {
              Value = key,
              Path = item.Path .. "{key:" .. safeToString(key) .. "}",
              Depth = item.Depth + 1,
            }
          end
        end
      end)
      if not ok then log("TABLE_ERROR path=" .. item.Path .. " error=" .. safeToString(err)) end
    end

    local counts = {}
    for key, value in pairs(typeCounts) do counts[#counts + 1] = key .. "=" .. tostring(value) end
    table.sort(counts)
    log("PREV_SUMMARY label=" .. label ..
        " tables=" .. tostring(tables) ..
        " edges=" .. tostring(edges) ..
        " matches=" .. tostring(matches) ..
        " queued=" .. tostring(#queue) ..
        " typeCounts=" .. table.concat(counts, ",") ..
        " bounded=true")
    return matches
  end

  local function scan(currentObject, savedInfo)
    if scanned then return end
    scanned = true
    if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then
      log("RESULT registry_unavailable")
      return
    end
    local ok, registry = pcall(debug.getregistry)
    if not ok or type(registry) ~= "table" then
      log("RESULT registry_failed value=" .. safeToString(registry))
      return
    end

    local roots, prevTables, totalRavens, totalMatches = 0, 0, 0, 0
    local seenPrev = {}
    for rootKey, root in pairs(registry) do
      if type(root) == "table" then
        local targets = collectRavens(root)
        if #targets > 0 then
          roots = roots + 1
          totalRavens = totalRavens + #targets
          log("ROOT key=" .. safeToString(rootKey) .. " ravens=" .. tostring(#targets) ..
              " currentObject=" .. objectLabel(currentObject) ..
              " currentSavedInfoType=" .. type(savedInfo))
          for i, target in ipairs(targets) do
            log("TARGET index=" .. tostring(i) ..
                " ravenKilled=" .. tostring(target.Killed) ..
                " pickle=" .. target.Pickle ..
                " object=" .. objectLabel(target.Object))
          end

          for _, name in ipairs({ "__prevunpickle", "__PrevUnpickle", "__prevUnpickle", "__SoftPickleTablePrev" }) do
            local prev = rawget(root, name)
            log("ROOT_FIELD rootKey=" .. safeToString(rootKey) .. " name=" .. name ..
                " type=" .. type(prev) .. " value=" .. safeToString(prev))
            if type(prev) == "table" and not seenPrev[prev] then
              seenPrev[prev] = true
              prevTables = prevTables + 1
              totalMatches = totalMatches + inspectPrev(prev, targets,
                "registry[" .. safeToString(rootKey) .. "]." .. name)
            end
          end
        end
      end
    end

    log("SUMMARY roots=" .. tostring(roots) ..
        " ravenTargets=" .. tostring(totalRavens) ..
        " prevTables=" .. tostring(prevTables) ..
        " matches=" .. tostring(totalMatches) ..
        " readOnly=true saveWrites=false progressionWrites=false streamingWrites=false")
  end

  local previousRestore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(level, object, savedInfo, ...)
    scan(object, savedInfo)
    return previousRestore(level, object, savedInfo, ...)
  end

  log("INSTALLED readOnly=true")
end
-- END COMPLETIONIST RAVEN PREVUNPICKLE IDENTITY PROBE
