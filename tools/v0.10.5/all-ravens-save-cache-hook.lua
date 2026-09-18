-- BEGIN COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE
-- Mod-owned checkpoint cache only. Native Raven progression remains authoritative.
do
  local prefix = "[CompletionistMap v0.10.5-raven-cache] "
  local CACHE_KEY = "__CompletionistMapV105Cache"
  local valid = {
-- @@RAVEN_CACHE_IDS@@
  }

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function getCache(create)
    local cache = object_savestate[CACHE_KEY]
    if type(cache) ~= "table" and create then
      cache = {schema = 1, ravens = {}}
      object_savestate[CACHE_KEY] = cache
    end
    if type(cache) == "table" then
      if type(cache.ravens) ~= "table" then cache.ravens = {} end
      cache.schema = 1
    end
    return cache
  end

  _G.CompletionistMapV105CacheRavenState = function(catalogueId, killed, source)
    if valid[catalogueId] ~= true then
      log("UPDATE_REFUSED", "reason=unknown_catalogue_id catalogueId=" .. tostring(catalogueId))
      return false
    end
    if type(killed) ~= "boolean" then
      log("UPDATE_REFUSED", "reason=killed_not_boolean catalogueId=" .. tostring(catalogueId))
      return false
    end
    local cache = getCache(true)
    cache.ravens[catalogueId] = killed
    log("UPDATE", "catalogueId=" .. catalogueId ..
        " killed=" .. tostring(killed) ..
        " source=" .. tostring(source) ..
        " nativeProgressionTouched=false")
    return true
  end

  local function replayCache(source)
    local cache = getCache(false)
    local known, killed, alive, sent = 0, 0, 0, 0
    if type(cache) == "table" and type(cache.ravens) == "table" then
      for catalogueId, value in pairs(cache.ravens) do
        if valid[catalogueId] == true and type(value) == "boolean" then
          known = known + 1
          if value then killed = killed + 1 else alive = alive + 1 end
          local ok = pcall(function()
            engine.SendHook(
              "UI_CALL_EVENT",
              engine.GetUIWad(),
              "EVT_COMPLETIONIST_V105_RAVEN_CACHE_RESTORE",
              {
                catalogueId = catalogueId,
                killed = value,
                source = source
              }
            )
          end)
          if ok then sent = sent + 1 end
        end
      end
    end
    log("RESTORE_REPLAY", "source=" .. tostring(source) ..
        " known=" .. tostring(known) ..
        " killed=" .. tostring(killed) ..
        " alive=" .. tostring(alive) ..
        " sent=" .. tostring(sent) ..
        " nativeProgressionTouched=false")
  end

  local baseRestore = Restore
  Restore = function(savestate)
    baseRestore(savestate)

    local restoredCache = nil
    if type(savestate) == "table" then
      restoredCache = savestate[CACHE_KEY]
    end
    if type(restoredCache) ~= "table" then
      object_savestate[CACHE_KEY] = nil
    end

    replayCache("core.save.Restore")
  end

  _G.CompletionistMapV105ReplayRavenCache = function(source)
    replayCache(source or "manual")
  end

  log("API", "installed=true cacheKey=" .. CACHE_KEY ..
      " scope=checkpointLuaState nativeProgressionTouched=false")
end
-- END COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE
