-- BEGIN COMPLETIONIST RAVEN AUTHORITY CAPABILITY PROBE
-- Read-only probe. No save, progression, marker, streaming, or object-state writes.
do
  local prefix = "[CompletionistRavenAuthorityProbe] "
  local ran = false

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    return ok and text or "<tostring-error>"
  end

  local function log(message)
    print(prefix .. message)
  end

  local function binaryHex(value, limit)
    if type(value) ~= "string" then return "<not-string>" end
    local out = {}
    local n = math.min(#value, limit)
    for i = 1, n do out[#out + 1] = string.format("%02x", string.byte(value, i)) end
    if #value > limit then out[#out + 1] = "..." end
    return table.concat(out) .. ":bytes=" .. tostring(#value)
  end

  local function callable(container, key)
    return type(container) == "table" and type(container[key]) == "function"
  end

  local function matchingKeys(container)
    local out = {}
    if type(container) ~= "table" then return out end
    for key, value in pairs(container) do
      local name = safeToString(key)
      local lower = string.lower(name)
      if string.find(lower, "zlib", 1, true) or
         string.find(lower, "deflat", 1, true) or
         string.find(lower, "inflat", 1, true) or
         string.find(lower, "compress", 1, true) or
         string.find(lower, "file", 1, true) or
         string.find(lower, "stream", 1, true) then
        out[#out + 1] = name .. ":" .. type(value)
      end
    end
    table.sort(out)
    return out
  end

  local function probeCapabilities()
    log("CAP io=" .. type(io) ..
        " io.open=" .. tostring(callable(io, "open")) ..
        " io.popen=" .. tostring(callable(io, "popen")) ..
        " os=" .. type(os) ..
        " os.getenv=" .. tostring(callable(os, "getenv")) ..
        " package=" .. type(package) ..
        " package.loadlib=" .. tostring(callable(package, "loadlib")) ..
        " require=" .. type(require) ..
        " zlibGlobal=" .. type(rawget(_G, "zlib")))

    local source = nil
    if type(debug) == "table" and type(debug.getinfo) == "function" then
      local ok, info = pcall(debug.getinfo, 1, "S")
      if ok and type(info) == "table" and type(info.source) == "string" then source = info.source end
    end
    if type(source) == "string" and string.sub(source, 1, 1) == "@" and callable(io, "open") then
      local path = string.sub(source, 2)
      local ok, handle = pcall(io.open, path, "rb")
      local first = nil
      if ok and handle ~= nil then
        local readOK, byte = pcall(function() return handle:read(1) end)
        if readOK then first = byte end
        pcall(function() handle:close() end)
      end
      log("FILE_READ_SELF ok=" .. tostring(ok and handle ~= nil) ..
          " firstByte=" .. binaryHex(first or "", 4) ..
          " source=" .. path)
    else
      log("FILE_READ_SELF ok=false reason=no_source_or_io_open")
    end

    if type(require) == "function" then
      for _, moduleName in ipairs({"zlib", "deflate", "inflate"}) do
        local ok, value = pcall(require, moduleName)
        log("REQUIRE module=" .. moduleName .. " ok=" .. tostring(ok) ..
            " type=" .. type(value) .. " value=" .. safeToString(value))
      end
    end

    log("GLOBAL_CAP_KEYS " .. table.concat(matchingKeys(_G), ","))
    log("ENGINE_CAP_KEYS " .. table.concat(matchingKeys(engine), ","))
  end

  local function objectIdentity(object)
    if type(debug) ~= "table" or type(debug.getmetatable) ~= "function" then
      return "metatable_unavailable"
    end
    local ok, mt = pcall(debug.getmetatable, object)
    if not ok or type(mt) ~= "table" then return "metatable_unavailable" end
    local identity = rawget(mt, "__identity")
    return "identityType=" .. type(identity) ..
           " identityText=" .. safeToString(identity) ..
           " identityHex=" .. binaryHex(identity, 128)
  end

  local function objectName(object)
    local ok, value = pcall(function() return object:GetName() end)
    return ok and safeToString(value) or "<name-error>"
  end

  local function objectLevel(object)
    local ok, value = pcall(function() return object.Level end)
    return ok and safeToString(value) or "<level-error>"
  end

  local function inspectPickleRoots()
    if type(debug) ~= "table" or type(debug.getregistry) ~= "function" then
      log("PICKLE_SCAN unavailable=debug.getregistry")
      return
    end
    local ok, registry = pcall(debug.getregistry)
    if not ok or type(registry) ~= "table" then
      log("PICKLE_SCAN unavailable=registry")
      return
    end

    local queue = {{value=registry, depth=0, label="debug.registry"}}
    local seen = {[registry]=true}
    local index, tables, edges, pickleRoots, ravenRecords = 1, 0, 0, 0, 0
    while index <= #queue and tables < 20000 and edges < 100000 do
      local item = queue[index]
      index = index + 1
      tables = tables + 1

      for _, pickleName in ipairs({"__PickleTable", "__SoftPickleTable"}) do
        local pickle = rawget(item.value, pickleName)
        if type(pickle) == "table" then
          local subobjects = rawget(pickle, "__subobjs")
          if type(subobjects) == "table" then
            pickleRoots = pickleRoots + 1
            for object, savedInfo in pairs(subobjects) do
              local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
              if type(killed) == "boolean" then
                ravenRecords = ravenRecords + 1
                log("RAVEN_KEY pickle=" .. pickleName ..
                    " killed=" .. tostring(killed) ..
                    " name=" .. objectName(object) ..
                    " level=" .. objectLevel(object) ..
                    " tostring=" .. safeToString(object) ..
                    " " .. objectIdentity(object))
              end
            end
          end
        end
      end

      if item.depth < 3 then
        for key, value in pairs(item.value) do
          edges = edges + 1
          if edges >= 100000 then break end
          if type(value) == "table" and not seen[value] then
            seen[value] = true
            queue[#queue + 1] = {
              value=value,
              depth=item.depth + 1,
              label=item.label .. "[" .. safeToString(key) .. "]",
            }
          end
        end
      end
    end
    log("PICKLE_SUMMARY roots=" .. tostring(pickleRoots) ..
        " ravenRecords=" .. tostring(ravenRecords) ..
        " tables=" .. tostring(tables) ..
        " edges=" .. tostring(edges) ..
        " readOnly=true")
  end

  probeCapabilities()

  local previousRestore = OnRestoreCheckpoint
  if type(previousRestore) == "function" then
    function OnRestoreCheckpoint(...)
      if not ran then
        ran = true
        inspectPickleRoots()
      end
      return previousRestore(...)
    end
  else
    log("RESTORE_WRAP installed=false reason=OnRestoreCheckpoint_not_function")
  end

  log("INSTALLED readOnly=true saveWrites=false progressionWrites=false markerWrites=false streamingWrites=false")
end
-- END COMPLETIONIST RAVEN AUTHORITY CAPABILITY PROBE
