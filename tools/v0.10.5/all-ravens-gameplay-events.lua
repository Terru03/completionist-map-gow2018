-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS
-- Read authoritative native ravenKilled state. Match one Raven by exact parent quest
-- plus native world position. Publish through the runtime-proven UI_CALL_EVENT bridge.
do
  local prefix = "[CompletionistMap v0.10.5-raven-events] "
  local ravenClass = "CompletionistRaven"
  local retryLimit = 20
  local generation = 0
  local rows = {
-- @@RAVEN_STATE_ROWS@@
  }

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function identify()
    if thisObj == nil then return nil, "object_nil" end
    local ok, pos = pcall(function() return thisObj:GetWorldPosition() end)
    if not ok or pos == nil then return nil, "position_nil" end
    local quest = string.gsub(tostring(regionSummaryQuest or ""), "%s+", "")
    local hit = nil
    for _, row in ipairs(rows) do
      if row.ParentQuest == quest then
        local dx, dy, dz = pos.x - row.X, pos.y - row.Y, pos.z - row.Z
        if dx * dx + dy * dy + dz * dz <= 0.25 then
          if hit ~= nil then return nil, "ambiguous" end
          hit = row
        end
      end
    end
    if hit == nil then return nil, "no_exact_static_match" end
    return hit, nil, pos
  end

  local function sendState(row, pos, killed, source)
    local payload = {
      catalogueId = row.CatalogueId,
      marker = row.Name,
      parentQuest = row.ParentQuest,
      killed = killed == true,
      x = pos.x,
      y = pos.y,
      z = pos.z,
      source = source
    }
    local ok, err = pcall(function()
      engine.SendHook(
        "UI_CALL_EVENT",
        engine.GetUIWad(),
        "EVT_COMPLETIONIST_V105_RAVEN_STATE",
        payload
      )
    end)
    log("STATE_SEND", "catalogueId=" .. row.CatalogueId ..
        " marker=" .. row.Name ..
        " killed=" .. tostring(payload.killed) ..
        " source=" .. tostring(source) ..
        " ok=" .. tostring(ok) ..
        " error=" .. tostring(err) ..
        " progressionWrites=false")
    return ok
  end

  local function publish(source)
    local row, err, pos = identify()
    if row == nil then
      log("STATE_REFUSED", "source=" .. tostring(source) .. " reason=" .. tostring(err))
      return nil
    end
    sendState(row, pos, ravenKilled == true, source)
    return row
  end

  local function exactShown(row)
    if row == nil then return false, false, "row_nil" end
    local infoOK, info = pcall(function() return game.Map.GetMarkerInfo(row.Name) end)
    if not infoOK or info == nil or info.Id == nil then
      return false, false, "marker_info"
    end
    local queryOK, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not queryOK then return false, false, tostring(ids) end
    for _, id in ipairs(ids or {}) do
      if tostring(id) == tostring(info.Id) then return true, true, nil end
    end
    return false, true, nil
  end

  local function hideExact(row, source, attempt)
    local shown, queryOK, queryErr = exactShown(row)
    if shown then
      local ok, err = pcall(function() game.Compass.HideMarker(row.Name) end)
      log("EXACT_HIDE", "catalogueId=" .. row.CatalogueId ..
          " marker=" .. row.Name ..
          " source=" .. tostring(source) ..
          " attempt=" .. tostring(attempt) ..
          " ok=" .. tostring(ok) ..
          " error=" .. tostring(err) ..
          " stockTouched=false progressionWrites=false")
      return ok, true, queryOK
    end
    return false, false, queryOK, queryErr
  end

  local function scheduleCleanup(row, source, attempt, ticket, sawExact)
    local ok, err = pcall(function()
      timers.StartLevelTimer(0.1, function()
        if ticket ~= generation or ravenKilled ~= true then return end
        local hidden, shown, queryOK, queryErr = hideExact(row, source, attempt)
        local saw = sawExact or shown or hidden
        if saw and queryOK and not shown and not hidden then
          log("CLEANUP_SETTLED", "catalogueId=" .. row.CatalogueId ..
              " source=" .. tostring(source) ..
              " attempts=" .. tostring(attempt) ..
              " exactAbsent=true")
          return
        end
        if not queryOK and (attempt == 1 or attempt == retryLimit) then
          log("QUERY_RETRY", "catalogueId=" .. row.CatalogueId ..
              " source=" .. tostring(source) ..
              " attempt=" .. tostring(attempt) ..
              " error=" .. tostring(queryErr))
        end
        if attempt < retryLimit then
          scheduleCleanup(row, source, attempt + 1, ticket, saw)
        else
          log("CLEANUP_BOUNDED_END", "catalogueId=" .. row.CatalogueId ..
              " source=" .. tostring(source) ..
              " attempts=" .. tostring(attempt) ..
              " realSeen=" .. tostring(saw) ..
              " queryOK=" .. tostring(queryOK))
        end
      end)
    end)
    if not ok then
      log("SCHEDULE_FAILED", "source=" .. tostring(source) .. " error=" .. tostring(err))
    end
  end

  local hit = OnHitByWeapon
  function OnHitByWeapon(...)
    local result = hit(...)
    generation = generation + 1
    local row = publish("OnHitByWeapon")
    if row ~= nil and ravenKilled == true then
      local _, shown = hideExact(row, "OnHitByWeapon", 0)
      scheduleCleanup(row, "OnHitByWeapon", 1, generation, shown)
    end
    return result
  end

  local restore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(...)
    local result = restore(...)
    generation = generation + 1
    local row = publish("OnRestoreCheckpoint")
    if row ~= nil and ravenKilled == true then
      local _, shown = hideExact(row, "OnRestoreCheckpoint", 0)
      scheduleCleanup(row, "OnRestoreCheckpoint", 1, generation, shown)
    end
    return result
  end

  local start = OnStart
  function OnStart(...)
    local result = start(...)
    generation = generation + 1
    local row = publish("OnStart")
    if row ~= nil and ravenKilled == true then
      local _, shown = hideExact(row, "OnStart", 0)
      scheduleCleanup(row, "OnStart", 1, generation, shown)
    end
    return result
  end

  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " nativeField=ravenKilled exactQuestAndPosition=true" ..
      " transport=UI_CALL_EVENT exactGameplayCleanup=true boundedRetry=" .. tostring(retryLimit) ..
      " polling=false progressionWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVEN EVENTS
