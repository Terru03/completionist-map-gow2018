-- BEGIN COMPLETIONIST RAVEN GAMEOBJECT IDENTITY PROBE
-- Read-only diagnostics for persisted Raven GameObject identity surfaces.
-- No save, progression, quest, marker, streaming, or object lifecycle writes.
do
  local prefix = "[CompletionistIdentityProbe] "
  local ran = false

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function log(message)
    print(prefix .. message)
  end

  local function safeValue(fn)
    local ok, value = pcall(fn)
    if ok then return true, value end
    return false, value
  end

  local function summarize(value, limit)
    limit = limit or 16
    if type(value) ~= "table" then return safeToString(value) end
    local parts, count = {}, 0
    local ok, err = pcall(function()
      for key, member in pairs(value) do
        count = count + 1
        if count <= limit then
          parts[#parts + 1] = safeToString(key) .. "=" .. safeToString(member)
        end
      end
    end)
    if not ok then return "<table-error:" .. safeToString(err) .. ">" end
    table.sort(parts)
    local suffix = count > limit and ",..." or ""
    return "{" .. table.concat(parts, ",") .. suffix .. "}:count=" .. tostring(count)
  end

  local function field(label, fn)
    local ok, value = safeValue(fn)
    if ok then return label .. "=" .. summarize(value) end
    return label .. "=<error:" .. safeToString(value) .. ">"
  end

  local function dumpObject(object, killed)
    local fields = {
      "ravenKilled=" .. tostring(killed),
      "object=" .. safeToString(object),
      field("GetName", function() return object:GetName() end),
      field("GetDebugName", function() return object:GetDebugName() end),
      field("GetDebugPath", function() return object:GetDebugPath() end),
      field("Level", function() return object.Level end),
      field("DebugMarkerIDs", function() return object.DebugMarkerIDs end),
      field("IsRefNodeProperty", function() return object.IsRefNode end),
      field("IsRefNodeCall", function() return object:IsRefNode() end),
      field("LuaObjectScript", function() return object.LuaObjectScript end),
      field("LevelObjectScript", function() return object.LevelObjectScript end),
    }

    if type(debug) == "table" and type(debug.getmetatable) == "function" then
      local ok, mt = safeValue(function() return debug.getmetatable(object) end)
      fields[#fields + 1] = "metatableOk=" .. tostring(ok)
      if ok and type(mt) == "table" then
        fields[#fields + 1] = "metatable=" .. safeToString(mt)
        fields[#fields + 1] = "metaIdentity=" .. summarize(rawget(mt, "__identity"))
        local debuggerString = rawget(mt, "__tostring_debugger")
        fields[#fields + 1] = "metaDebuggerType=" .. type(debuggerString)
        if type(debuggerString) == "function" then
          fields[#fields + 1] = field("metaDebugger", function() return debuggerString(object) end)
        end
        local indexer = rawget(mt, "__index")
        fields[#fields + 1] = "metaIndexType=" .. type(indexer)
        if type(indexer) == "function" then
          fields[#fields + 1] = field("metaIndexIdentity", function() return indexer(object, "__identity") end)
          fields[#fields + 1] = field("metaIndexDebugMarkerIDs", function() return indexer(object, "DebugMarkerIDs") end)
        end
      end
    end

    log("OBJECT " .. table.concat(fields, " "))
  end

  local function scan()
    if ran then return end
    ran = true
    if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then
      log("RESULT registry_unavailable")
      return
    end
    local ok, registry = pcall(debug.getregistry)
    if not ok or type(registry) ~= "table" then
      log("RESULT registry_failed value=" .. safeToString(registry))
      return
    end

    local pickleRoots, ravenRecords = 0, 0
    local seen = {}
    for rootKey, root in pairs(registry) do
      if type(root) == "table" then
        for _, pickleName in ipairs({ "__PickleTable", "__SoftPickleTable" }) do
          local pickle = rawget(root, pickleName)
          if type(pickle) == "table" and not seen[pickle] then
            seen[pickle] = true
            pickleRoots = pickleRoots + 1
            local subobjects = rawget(pickle, "__subobjs")
            log("PICKLE rootKey=" .. safeToString(rootKey) .. " name=" .. pickleName ..
                " subobjectsType=" .. type(subobjects))
            if type(subobjects) == "table" then
              for object, savedInfo in pairs(subobjects) do
                local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
                if type(killed) == "boolean" then
                  ravenRecords = ravenRecords + 1
                  dumpObject(object, killed)
                end
              end
            end
          end
        end
      end
    end
    log("SUMMARY pickleRoots=" .. tostring(pickleRoots) .. " ravenRecords=" .. tostring(ravenRecords) ..
        " readOnly=true saveWrites=false progressionWrites=false streamingWrites=false")
  end

  local previousRestore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(level, object, savedInfo, ...)
    scan()
    return previousRestore(level, object, savedInfo, ...)
  end

  log("INSTALLED readOnly=true")
end
-- END COMPLETIONIST RAVEN GAMEOBJECT IDENTITY PROBE
