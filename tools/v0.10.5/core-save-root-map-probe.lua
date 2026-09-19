-- BEGIN COMPLETIONIST CORE SAVE ROOT MAP PROBE
-- Read-only inspection of core.save's restored object_savestate table from map UI.
-- No GetSaveState/CreateSaveState/Save calls and no progression writes.
do
  local prefix = "[CompletionistCoreSaveRootProbe] "
  local ran = false
  local maxNodes = 100000
  local maxDepth = 12

  local function log(msg)
    print(prefix .. msg)
  end

  local function safeToString(v)
    local ok, s = pcall(tostring, v)
    return ok and s or "<tostring-error>"
  end

  local function keyText(k)
    local t = type(k)
    if t == "string" or t == "number" or t == "boolean" then
      return safeToString(k)
    end
    local name = nil
    pcall(function()
      if type(k.GetName) == "function" then
        name = k:GetName()
      elseif k.name ~= nil then
        name = k.name
      end
    end)
    return "<" .. t .. ":" .. (name and safeToString(name) .. ":" or "") .. safeToString(k) .. ">"
  end

  local function run(reason)
    if ran then return end
    ran = true
    log("RUN reason=" .. safeToString(reason) .. " readOnly=true saveWrites=false progressionWrites=false")

    local okRequire, savelib = pcall(require, "core.save")
    log("CORE_SAVE_REQUIRE ok=" .. tostring(okRequire) .. " type=" .. type(savelib))
    if not okRequire or type(savelib) ~= "table" then
      log("DONE rootAvailable=false")
      return
    end

    local peek = savelib.PeekSaveStateRoot
    log("PEEK_FUNCTION type=" .. type(peek))
    if type(peek) ~= "function" then
      log("DONE rootAvailable=false")
      return
    end

    local okRoot, root = pcall(peek)
    log("PEEK_CALL ok=" .. tostring(okRoot) .. " rootType=" .. type(root) .. " root=" .. safeToString(root))
    if not okRoot or type(root) ~= "table" then
      log("DONE rootAvailable=false")
      return
    end

    local visited = {}
    local nodes = 0
    local tables = 0
    local ravenKilledHits = 0
    local ravenTrue = 0
    local ravenFalse = 0
    local topEntries = 0

    local function walk(v, path, depth)
      if type(v) ~= "table" or depth > maxDepth or nodes >= maxNodes or visited[v] then return end
      visited[v] = true
      nodes = nodes + 1
      tables = tables + 1

      local ok, err = pcall(function()
        for k, child in pairs(v) do
          if depth == 0 then topEntries = topEntries + 1 end
          local kp = keyText(k)
          local childPath = path .. "/" .. kp

          if type(k) == "string" and k == "ravenKilled" then
            ravenKilledHits = ravenKilledHits + 1
            if child == true then ravenTrue = ravenTrue + 1 end
            if child == false then ravenFalse = ravenFalse + 1 end
            log("RAVEN_FIELD valueType=" .. type(child) ..
                " value=" .. safeToString(child) ..
                " path=" .. childPath)
          end

          if type(child) == "table" then
            walk(child, childPath, depth + 1)
          end
          if nodes >= maxNodes then break end
        end
      end)
      if not ok then
        log("WALK_ERROR path=" .. path .. " error=" .. safeToString(err))
      end
    end

    walk(root, "object_savestate", 0)

    log("SUMMARY topEntries=" .. tostring(topEntries) ..
        " tables=" .. tostring(tables) ..
        " nodes=" .. tostring(nodes) ..
        " ravenKilledHits=" .. tostring(ravenKilledHits) ..
        " ravenTrue=" .. tostring(ravenTrue) ..
        " ravenFalse=" .. tostring(ravenFalse) ..
        " maxNodes=" .. tostring(maxNodes) ..
        " maxDepth=" .. tostring(maxDepth))
    log("DONE rootAvailable=true readOnly=true saveWrites=false progressionWrites=false")
  end

  _G.CompletionistCoreSaveRootProbe_Run = run

  -- mapmenu.lua itself loads only when the UI context is available. Run once
  -- immediately so this does not depend on a specific collision callback firing.
  run("mapmenu_script_load")

  if type(MapOn) == "table" and type(MapOn.MapCollisionChangeHandler) == "function" then
    local previous = MapOn.MapCollisionChangeHandler
    MapOn.MapCollisionChangeHandler = function(self, ...)
      run("MapCollisionChangeHandler")
      return previous(self, ...)
    end
    log("HOOK installed=MapOn.MapCollisionChangeHandler")
  else
    log("HOOK unavailable=true")
  end
end
-- END COMPLETIONIST CORE SAVE ROOT MAP PROBE
