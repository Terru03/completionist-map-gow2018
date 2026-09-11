-- BEGIN COMPLETIONIST V0.10.4 RAVEN LIFECYCLE V3.1 EVENTS
-- Runs inside persistent Raven gameplay script. Read native ravenKilled only.
-- Clean exact real CompletionistRaven compass target. Never touch Twin or stock.
do
  local prefix = "[CompletionistMap uid-lifecycle-v3.1] "
  local ravenName = "Completionist_V103_Veithurgard_Raven_01"
  local ravenClass = "CompletionistRaven"
  local retryLimit = 20
  local generation = 0
  local observedKilled = nil

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function realIdentity()
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(ravenName) end)
    if not ok or info == nil or info.Id == nil then
      return nil, "marker_lookup_failed:" .. tostring(info)
    end
    return tostring(info.Id), nil
  end

  local function realShown()
    local realId, identityErr = realIdentity()
    if realId == nil then return false, false, identityErr, nil end
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then return false, false, tostring(ids), realId end
    for _, id in ipairs(ids or {}) do
      if tostring(id) == realId then return true, true, nil, realId end
    end
    return false, true, nil, realId
  end

  local function schedule(source, attempt, ticket, sawReal)
    timers.StartLevelTimer(0.1, function()
      if ticket ~= generation or ravenKilled ~= true then return end
      local shown, queryOK, queryErr, realId = realShown()
      local nextSawReal = sawReal or shown
      if shown then
        local hideOK, hideErr = pcall(function() game.Compass.HideMarker(ravenName) end)
        log("REAL_HIDE", "source=" .. tostring(source) ..
            " attempt=" .. tostring(attempt) .. " uid=" .. tostring(realId) ..
            " ok=" .. tostring(hideOK) .. " error=" .. tostring(hideErr) ..
            " twinTouched=false stockTouched=false")
        nextSawReal = true
      elseif not queryOK and (attempt == 1 or attempt == retryLimit) then
        log("QUERY_RETRY", "source=" .. tostring(source) ..
            " attempt=" .. tostring(attempt) .. " error=" .. tostring(queryErr))
      end

      if nextSawReal and queryOK and not shown then
        log("CLEANUP_SETTLED", "source=" .. tostring(source) ..
            " attempts=" .. tostring(attempt) .. " exactRealAbsent=true")
        return
      end
      if attempt >= retryLimit then
        log("CLEANUP_BOUNDED_END", "source=" .. tostring(source) ..
            " attempts=" .. tostring(attempt) ..
            " realSeen=" .. tostring(nextSawReal) ..
            " queryOK=" .. tostring(queryOK))
        return
      end
      schedule(source, attempt + 1, ticket, nextSawReal)
    end)
  end

  local function observe(source)
    local target = CompletionistMapV100_IsTargetRaven()
    if not target then return end
    local killed = ravenKilled == true
    if not killed then
      generation = generation + 1
      if observedKilled == true then
        log("LIFECYCLE_REARM", "source=" .. tostring(source) ..
            " staleTicketCancelled=true")
      end
      observedKilled = false
      return
    end
    if observedKilled == true then return end

    observedKilled = true
    generation = generation + 1
    local ticket = generation
    local shown, queryOK, queryErr, realId = realShown()
    local sawReal = shown
    if shown then
      local hideOK, hideErr = pcall(function() game.Compass.HideMarker(ravenName) end)
      log("REAL_HIDE", "source=" .. tostring(source) ..
          " attempt=0 uid=" .. tostring(realId) .. " ok=" .. tostring(hideOK) ..
          " error=" .. tostring(hideErr) ..
          " twinTouched=false stockTouched=false")
    elseif not queryOK then
      log("QUERY_RETRY", "source=" .. tostring(source) ..
          " attempt=0 error=" .. tostring(queryErr))
    end

    -- One bounded event-local ticket verifies async hide and catches a real show
    -- queued just before collection. No idle or permanent polling exists.
    schedule(source, 1, ticket, sawReal)
  end

  local hit = OnHitByWeapon
  function OnHitByWeapon(...)
    local result = hit(...)
    observe("OnHitByWeapon")
    return result
  end

  local restore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(...)
    local result = restore(...)
    observe("OnRestoreCheckpoint")
    return result
  end

  local start = OnStart
  function OnStart(...)
    local result = start(...)
    observe("OnStart")
    return result
  end

  log("API", "installed=true cleanupOwner=precisionchallenge" ..
      " exactMarker=" .. ravenName .. " compassClass=" .. ravenClass ..
      " boundedRetry=" .. tostring(retryLimit) ..
      " mapmenuDependency=false progressionWrites=false")
end
-- END COMPLETIONIST V0.10.4 RAVEN LIFECYCLE V3.1 EVENTS
