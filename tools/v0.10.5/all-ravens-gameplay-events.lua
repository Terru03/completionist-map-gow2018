-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS
-- Read own Raven bool. Match one native quest and static world point.
do
  local prefix = "[CompletionistMap v0.10.5-raven-events] "
  local ravenClass = "CompletionistRaven"
  local retryLimit = 20
  local restoreRetryLimit = 20
  local generation = 0
  local nativePort = 43753
  local noteMaxResponseBytes = 256
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
    return hit, nil
  end

  local function sendBridgeNote(request)
    local socketOK, socket = pcall(require, "socket.core")
    if not socketOK or type(socket) ~= "table" or type(socket.tcp) ~= "function" then
      return false, "socket_core_unavailable"
    end
    local createOK, client = pcall(socket.tcp)
    if not createOK or client == nil then return false, "socket_create" end
    local function close()
      pcall(function() client:close() end)
    end
    pcall(function() client:settimeout(0.25) end)
    pcall(function() client:settimeout(0.25, "t") end)
    local connectOK, connected, connectError = pcall(function()
      return client:connect("127.0.0.1", nativePort)
    end)
    if not connectOK or connected == nil then
      close()
      return false, "connect:" .. tostring(connectOK and connectError or connected)
    end
    local sendOK, sent, sendError = pcall(function() return client:send(request) end)
    if not sendOK or sent ~= string.len(request) then
      close()
      return false, "send:" .. tostring(sendOK and sendError or sent)
    end

    local bytes = {}
    for _ = 1, noteMaxResponseBytes do
      local receiveOK, value, receiveError = pcall(function()
        return client:receive(1)
      end)
      if not receiveOK or value == nil then
        close()
        return false, "receive:" .. tostring(receiveOK and receiveError or value)
      end
      if value == "\n" then
        local response = table.concat(bytes)
        close()
        if string.sub(response, 1, string.len("RAVEN_NOTE_V1 OK ")) ==
            "RAVEN_NOTE_V1 OK " then
          return true, response
        end
        return false, "response:" .. response
      end
      bytes[#bytes + 1] = value
    end
    close()
    return false, "response_too_large"
  end

  local function noteKilled(row, source)
    if row == nil then return false end
    local ok, detail = sendBridgeNote(
        "NOTE RAVEN_KILLED_V1 catalogueId=" .. row.CatalogueId .. "\n")
    log("BRIDGE_KILL_NOTE",
        "source=" .. tostring(source) ..
        " catalogueId=" .. row.CatalogueId ..
        " delivered=" .. tostring(ok) ..
        " detail=" .. tostring(detail) ..
        " progressionWrites=false")
    return ok
  end

  local function noteBoundary(source)
    local ok, detail = sendBridgeNote(
        "NOTE RAVEN_BOUNDARY_V1 source=checkpoint\n")
    log("BRIDGE_BOUNDARY_NOTE",
        "source=" .. tostring(source) ..
        " delivered=" .. tostring(ok) ..
        " detail=" .. tostring(detail) ..
        " progressionWrites=false")
    return ok
  end

  local function notifyAuthorityBoundary(source)
    local bridgeDelivered = noteBoundary(source)
    local fn = _G.CompletionistMapV105NotifyAuthorityBoundary
    if type(fn) == "function" then
      local ok, result = pcall(fn, source, true)
      log("AUTHORITY_BOUNDARY_NOTIFY", "source=" .. tostring(source) ..
          " captureReady=true delivered=" .. tostring(ok and result == true) ..
          " bridgeDelivered=" .. tostring(bridgeDelivered))
      return
    end
    _G.CompletionistMapV105PendingAuthorityBoundary = {
      source = source,
      captureReady = true,
    }
    log("AUTHORITY_BOUNDARY_NOTIFY", "source=" .. tostring(source) ..
        " captureReady=true delivered=false pending=true" ..
        " bridgeDelivered=" .. tostring(bridgeDelivered))
  end

  local function publish(source)
    local row, err = identify()
    if row == nil then
      log("STATE_REFUSED", "source=" .. tostring(source) .. " reason=" .. tostring(err))
      return nil
    end
    if ravenKilled ~= true then
      log("STATE_DEFERRED", "source=" .. tostring(source) ..
          " catalogueId=" .. row.CatalogueId ..
          " reason=alive_requires_atomic_authority")
      return row
    end
    local bridgeDelivered = noteKilled(row, source)
    local fn = _G.CompletionistMapV105PublishRavenState
    if type(fn) == "function" then
      fn(row.CatalogueId, true, source)
      log("STATE_DELIVERY", "source=" .. tostring(source) ..
          " catalogueId=" .. row.CatalogueId ..
          " direct=true bridge=" .. tostring(bridgeDelivered))
      return row
    end
    _G.CompletionistMapV105PendingRavenState = _G.CompletionistMapV105PendingRavenState or {}
    _G.CompletionistMapV105PendingRavenState[row.CatalogueId] = true
    log("STATE_DELIVERY", "source=" .. tostring(source) ..
        " catalogueId=" .. row.CatalogueId ..
        " direct=false pendingLocal=true bridge=" .. tostring(bridgeDelivered))
    return row
  end

  local function exactShown(row)
    if row == nil then return false, false end
    local infoOK, info = pcall(function() return game.Map.GetMarkerInfo(row.Name) end)
    if not infoOK or info == nil or info.Id == nil then return false, false end
    local queryOK, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not queryOK then return false, false end
    for _, id in ipairs(ids or {}) do
      if tostring(id) == tostring(info.Id) then return true, true end
    end
    return false, true
  end

  local function schedule(source, attempt, ticket, sawExact)
    local ok, err = pcall(function()
      timers.StartLevelTimer(0.1, function()
        if ticket ~= generation or ravenKilled ~= true then return end
        local row = publish(source .. ":retry:" .. tostring(attempt))
        local shown, queryOK = exactShown(row)
        local saw = sawExact or shown
        if saw and queryOK and not shown then return end
        if attempt < retryLimit then schedule(source, attempt + 1, ticket, saw) end
      end)
    end)
    if not ok then log("SCHEDULE_FAILED", "source=" .. tostring(source) .. " error=" .. tostring(err)) end
  end

  local function scheduleRestore(source, attempt, ticket)
    local ok, err = pcall(function()
      timers.StartLevelTimer(0.1, function()
        if ticket ~= generation then return end
        publish(source .. ":retry:" .. tostring(attempt))
        if attempt < restoreRetryLimit then
          scheduleRestore(source, attempt + 1, ticket)
        end
      end)
    end)
    if not ok then
      log("RESTORE_SCHEDULE_FAILED",
          "source=" .. tostring(source) .. " error=" .. tostring(err))
    end
  end

  local hit = OnHitByWeapon
  function OnHitByWeapon(...)
    local result = hit(...)
    generation = generation + 1
    local row = publish("OnHitByWeapon")
    local shown = exactShown(row)
    schedule("OnHitByWeapon", 1, generation, shown)
    return result
  end

  local restore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(...)
    local result = restore(...)
    generation = generation + 1
    local ticket = generation
    notifyAuthorityBoundary("OnRestoreCheckpoint")
    publish("OnRestoreCheckpoint")
    scheduleRestore("OnRestoreCheckpoint", 1, ticket)
    return result
  end

  local start = OnStart
  function OnStart(...)
    local result = start(...)
    generation = generation + 1
    publish("OnStart")
    return result
  end

  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " nativeField=ravenKilled exactQuestAndPosition=true boundedRetry=" .. tostring(retryLimit) ..
      " restoreBoundedRetry=" .. tostring(restoreRetryLimit) ..
      " positiveEvidenceOnly=true restoreAuthorityBoundary=true" ..
      " restoreBoundaryCaptureReadyAfterReturn=true" ..
      " crossContextBridge=true nativePort=" .. tostring(nativePort) ..
      " permanentPolling=false progressionWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVEN EVENTS
