-- BEGIN COMPLETIONIST GENERIC NATIVE NAMESPACE INVENTORY
-- Read-only runtime enumeration. No native candidate calls and no progression writes.
do
  local prefix = "[CompletionistNamespaceProbe] "

  local function log(message)
    print(prefix .. message)
  end

  local interesting = {
    "counter", "quest", "objective", "progress", "region", "summary",
    "state", "ref", "save", "persist", "variable", "marker", "resolve",
    "hash", "collect", "complete", "discover", "open", "unlock"
  }

  local function isInteresting(name)
    local s = string.lower(tostring(name or ""))
    for _, needle in ipairs(interesting) do
      if string.find(s, needle, 1, true) then return true end
    end
    return false
  end

  -- Safely walk a Lua table/userdata using the iterator returned by pairs().
  -- Important: pairs() normally returns nil as the initial key; the iterator must
  -- be called once with that nil key to obtain the first entry.
  local function walkPairs(obj, limit, onEntry, label)
    local okPairs, iter, state, key = pcall(pairs, obj)
    if not okPairs then
      return false, 0, tostring(iter)
    end

    local count = 0
    while count < limit do
      local okNext, nextKey, value = pcall(iter, state, key)
      if not okNext then
        return false, count, tostring(nextKey)
      end
      if nextKey == nil then
        return true, count, nil
      end

      key = nextKey
      count = count + 1
      onEntry(nextKey, value)
    end

    log("LIMIT path=" .. tostring(label) .. " entries=" .. tostring(count))
    return true, count, nil
  end

  local function enumerate(label, obj, emitAll, limit)
    local t = type(obj)
    log("OBJECT path=" .. label .. " type=" .. t)
    if t ~= "table" and t ~= "userdata" then return end

    local emitted = 0
    local okWalk, count, walkErr = walkPairs(obj, limit, function(k, value)
      if emitAll or isInteresting(k) then
        emitted = emitted + 1
        log("ENTRY path=" .. label .. " key=" .. tostring(k) .. " type=" .. tostring(type(value)))
      end
    end, label)

    if okWalk then
      log("ENUM path=" .. label .. " count=" .. tostring(count) .. " emitted=" .. tostring(emitted))
    else
      log("ENUM_ERROR path=" .. label .. " count=" .. tostring(count) .. " error=" .. tostring(walkErr))
    end

    local okMt, mt = pcall(getmetatable, obj)
    if okMt then
      log("METATABLE path=" .. label .. " type=" .. tostring(type(mt)))
      if type(mt) == "table" then
        local okIndex, index = pcall(function() return rawget(mt, "__index") end)
        if okIndex then
          log("METAINDEX path=" .. label .. " type=" .. tostring(type(index)))
          if type(index) == "table" or type(index) == "userdata" then
            local metaEmitted = 0
            local okMeta, metaCount, metaErr = walkPairs(index, limit, function(k, value)
              if emitAll or isInteresting(k) then
                metaEmitted = metaEmitted + 1
                log("META_ENTRY path=" .. label .. " key=" .. tostring(k) .. " type=" .. tostring(type(value)))
              end
            end, label .. ".__index")
            if okMeta then
              log("META_ENUM path=" .. label .. " count=" .. tostring(metaCount) .. " emitted=" .. tostring(metaEmitted))
            else
              log("META_ENUM_ERROR path=" .. label .. " count=" .. tostring(metaCount) .. " error=" .. tostring(metaErr))
            end
          end
        end
      end
    else
      log("METATABLE_ERROR path=" .. label .. " error=" .. tostring(mt))
    end
  end

  local function collectChildTables(label, obj, maxChildren)
    local children = {}
    if type(obj) ~= "table" and type(obj) ~= "userdata" then return children end

    walkPairs(obj, 5000, function(k, v)
      if #children >= maxChildren then return end
      local vt = type(v)
      if vt == "table" or vt == "userdata" then
        children[#children + 1] = { label = label .. "." .. tostring(k), value = v }
      end
    end, label .. ".children")

    return children
  end

  local function run(reason)
    if rawget(_G, "CompletionistNamespaceProbeHasRun") then return end
    _G.CompletionistNamespaceProbeHasRun = true
    log("RUN reason=" .. tostring(reason) .. " progressionWrites=false nativeCalls=false iteratorFix=true")

    local roots = {
      { "_G", _G, true, 2500 },
      { "game", rawget(_G, "game"), true, 1600 },
      { "engine", rawget(_G, "engine"), true, 1600 },
      { "uiCalls", rawget(_G, "uiCalls"), true, 1600 },
    }

    if type(game) == "table" then
      roots[#roots + 1] = { "game.Level", rawget(game, "Level"), true, 1600 }
      roots[#roots + 1] = { "game.QuestManager", rawget(game, "QuestManager"), true, 1600 }
      roots[#roots + 1] = { "game.SubObject", rawget(game, "SubObject"), true, 1600 }
    end

    -- Emit all top-level names so hidden namespaces can be discovered.
    for _, root in ipairs(roots) do
      enumerate(root[1], root[2], root[3], root[4])
    end

    -- Inspect first-level namespaces, but only emit members whose names look
    -- relevant to state/progression/collectibles. Including _G lets us discover
    -- a native namespace that is not under game or engine.
    local seen = {}
    for _, root in ipairs(roots) do
      local maxChildren = root[1] == "_G" and 320 or 200
      local children = collectChildTables(root[1], root[2], maxChildren)
      for _, child in ipairs(children) do
        if not seen[child.value] then
          seen[child.value] = true
          enumerate(child.label, child.value, false, 1600)
        end
      end
    end

    log("DONE progressionWrites=false nativeCalls=false iteratorFix=true")
  end

  _G.CompletionistNamespaceProbe_Run = run

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler iteratorFix=true")
  else
    log("HOOK unavailable=true fallback=script_load iteratorFix=true")
    run("script_load_fallback")
  end
end
-- END COMPLETIONIST GENERIC NATIVE NAMESPACE INVENTORY
