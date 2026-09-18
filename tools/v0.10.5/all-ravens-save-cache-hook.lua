-- BEGIN COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE
-- Stores only an opaque Completionist save-point ID inside GoW's Lua checkpoint state.
-- The full Raven snapshot lives in the MainHUD sidecar cache keyed by this ID.
do
  local prefix = "[CompletionistMap v0.10.5-raven-cache] "
  local SAVEPOINT_KEY = "__CompletionistMapV105SavePoint"
  local sequence = 0

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function sanitize(value)
    return tostring(value or ""):gsub("[^%w_-]", "")
  end

  local function newSavePointId()
    sequence = sequence + 1
    local epoch = 0
    if type(os) == "table" and type(os.time) == "function" then
      local ok, value = pcall(os.time)
      if ok and type(value) == "number" then epoch = value end
    end
    local random = 0
    if type(math) == "table" and type(math.random) == "function" then
      local ok, value = pcall(math.random, 0, 2147483647)
      if ok and type(value) == "number" then random = value end
    end
    local pointer = sanitize(tostring({}))
    return sanitize(
      "sp_" .. tostring(epoch) .. "_" .. tostring(sequence) ..
      "_" .. tostring(random) .. "_" .. pointer
    )
  end

  local function sendEvent(eventName, savePointId, source)
    local ok, err = pcall(function()
      engine.SendHook(
        "UI_CALL_EVENT",
        engine.GetUIWad(),
        eventName,
        {
          savePointId = savePointId,
          source = source
        }
      )
    end)
    log("SAVEPOINT_EVENT", "event=" .. tostring(eventName) ..
        " savePointId=" .. tostring(savePointId) ..
        " source=" .. tostring(source) ..
        " ok=" .. tostring(ok) ..
        " error=" .. tostring(err) ..
        " nativeProgressionTouched=false")
    return ok
  end

  local baseSave = Save
  Save = function()
    local meta = object_savestate[SAVEPOINT_KEY]
    if type(meta) ~= "table" then
      meta = {}
      object_savestate[SAVEPOINT_KEY] = meta
    end
    meta.schema = 1
    meta.id = newSavePointId()

    sendEvent(
      "EVT_COMPLETIONIST_V105_SAVEPOINT_CAPTURE",
      meta.id,
      "core.save.Save"
    )

    return baseSave()
  end

  local baseRestore = Restore
  Restore = function(savestate)
    baseRestore(savestate)

    local meta = nil
    if type(object_savestate) == "table" then
      meta = object_savestate[SAVEPOINT_KEY]
    end
    local savePointId = type(meta) == "table" and sanitize(meta.id) or ""

    sendEvent(
      "EVT_COMPLETIONIST_V105_SAVEPOINT_RESTORE",
      savePointId,
      "core.save.Restore"
    )
  end

  log("API", "installed=true savePointKey=" .. SAVEPOINT_KEY ..
      " payload=opaqueIdOnly sidecarOwner=MainHUD nativeProgressionTouched=false")
end
-- END COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE
