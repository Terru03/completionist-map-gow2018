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

  local function safePairs(obj)
    local ok, iter, state, first = pcall(pairs, obj)
    if not ok then return nil, tostring(iter) end
    return { iter = iter, state = state, key = first }, nil
  end

  local function enumerate(label, obj, emitAll, limit)
    local t = type(obj)
    log("OBJECT path=" .. label .. " type=" .. t)
    if t ~= "table" and t ~= "userdata" then return end

    local p, err = safePairs(obj)
    if p then
      local count = 0
      local emitted = 0
      local k = p.key
      while k ~= nil do
        local okValue, value = pcall(function() return obj[k] end)
        count = count + 1
        if okValue and (emitAll or isInteresting(k)) then
          emitted = emitted + 1
          log("ENTRY path=" .. label .. " key=" .. tostring(k) .. " type=" .. tostring(type(value)))
        end
        if count >= limit then
          log("LIMIT path=" .. label .. " entries=" .. tostring(count))
          break
        end
        local okNext, nk = pcall(p.iter, p.state, k)
        if not okNext then
          log("PAIR_ERROR path=" .. label .. " error=" .. tostring(nk))
          break
        end
        k = nk
      end
      log("ENUM path=" .. label .. " count=" .. tostring(count) .. " emitted=" .. tostring(emitted))
    else
      log("ENUM_UNAVAILABLE path=" .. label .. " error=" .. tostring(err))
    end

    local okMt, mt = pcall(getmetatable, obj)
    if okMt then
      log("METATABLE path=" .. label .. " type=" .. tostring(type(mt)))
      if type(mt) == "table" then
        local okIndex, index = pcall(function() return rawget(mt, "__index") end)
        if okIndex then
          log("METAINDEX path=" .. label .. " type=" .. tostring(type(index)))
          if type(index) == "table" then
            local ip, ierr = safePairs(index)
            if ip then
              local count = 0
              local emitted = 0
              local k = ip.key
              while k ~= nil do
                local okValue, value = pcall(function() return index[k] end)
                count = count + 1
                if okValue and (emitAll or isInteresting(k)) then
                  emitted = emitted + 1
                  log("META_ENTRY path=" .. label .. " key=" .. tostring(k) .. " type=" .. tostring(type(value)))
                end
                if count >= limit then break end
                local okNext, nk = pcall(ip.iter, ip.state, k)
                if not okNext then break end
                k = nk
              end
              log("META_ENUM path=" .. label .. " count=" .. tostring(count) .. " emitted=" .. tostring(emitted))
            else
              log("META_ENUM_UNAVAILABLE path=" .. label .. " error=" .. tostring(ierr))
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
    if type(obj) ~= "table" then return children end
    local n = 0
    for k, v in pairs(obj) do
      local vt = type(v)
      if vt == "table" or vt == "userdata" then
        n = n + 1
        children[#children + 1] = { label = label .. "." .. tostring(k), value = v }
        if n >= maxChildren then break end
      end
    end
    return children
  end

  local function run(reason)
    if rawget(_G, "CompletionistNamespaceProbeHasRun") then return end
    _G.CompletionistNamespaceProbeHasRun = true
    log("RUN reason=" .. tostring(reason) .. " progressionWrites=false nativeCalls=false")

    local roots = {
      { "game", rawget(_G, "game") },
      { "engine", rawget(_G, "engine") },
      { "uiCalls", rawget(_G, "uiCalls") },
    }

    if type(game) == "table" then
      roots[#roots + 1] = { "game.Level", rawget(game, "Level") }
      roots[#roots + 1] = { "game.QuestManager", rawget(game, "QuestManager") }
      roots[#roots + 1] = { "game.SubObject", rawget(game, "SubObject") }
    end

    -- Emit all top-level names so hidden namespaces can be discovered.
    for _, root in ipairs(roots) do
      enumerate(root[1], root[2], true, 1200)
    end

    -- Inspect first-level native/table namespaces, but only emit state-related members.
    local seen = {}
    for _, root in ipairs(roots) do
      local children = collectChildTables(root[1], root[2], 160)
      for _, child in ipairs(children) do
        if not seen[child.value] then
          seen[child.value] = true
          enumerate(child.label, child.value, false, 1200)
        end
      end
    end

    log("DONE progressionWrites=false nativeCalls=false")
  end

  _G.CompletionistNamespaceProbe_Run = run

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
-- END COMPLETIONIST GENERIC NATIVE NAMESPACE INVENTORY
