-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER
-- Persistent UI owner for Raven state. Gameplay native state is authoritative.
-- Full session snapshots are cached in a sidecar file keyed by the save-point ID
-- embedded in GoW's checkpoint Lua state.
do
  local prefix = "[CompletionistMap v0.10.5-raven-ui-bridge] "
  local sidecarDir = "mods/completionist-map-cache/"
  local rows = {
-- @@RAVEN_RECEIVER_ROWS@@
  }
  local byCatalogueId = {}
  for _, row in ipairs(rows) do
    byCatalogueId[row.CatalogueId] = row
  end

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function stateTable()
    local states = _G.CompletionistMapV105RavenState
    if type(states) ~= "table" then
      states = {}
      _G.CompletionistMapV105RavenState = states
    end
    return states
  end

  local function clearState()
    local states = stateTable()
    for key in pairs(states) do
      states[key] = nil
    end
    _G.CompletionistMapV105RavenStateGeneration =
      (tonumber(_G.CompletionistMapV105RavenStateGeneration) or 0) + 1
  end

  local function publishOne(catalogueId, killed, source)
    local states = stateTable()
    states[catalogueId] = killed == true
    _G.CompletionistMapV105RavenStateGeneration =
      (tonumber(_G.CompletionistMapV105RavenStateGeneration) or 0) + 1

    local publish = _G.CompletionistMapV105PublishRavenState
    local published = false
    if type(publish) == "function" then
      local ok, accepted = pcall(
        publish,
        catalogueId,
        killed == true,
        source
      )
      published = ok and accepted == true
    end
    return published
  end

  local function sanitizeSavePointId(value)
    local id = tostring(value or ""):gsub("[^%w_-]", "")
    if #id > 160 then id = string.sub(id, 1, 160) end
    return id
  end

  local function sidecarPath(savePointId)
    return sidecarDir .. sanitizeSavePointId(savePointId) .. ".txt"
  end

  local function ioAvailable()
    return type(io) == "table" and type(io.open) == "function"
  end

  local function writeSidecar(savePointId, source)
    local id = sanitizeSavePointId(savePointId)
    if id == "" then
      log("SIDECAR_WRITE_REFUSED", "reason=empty_savepoint source=" .. tostring(source))
      return false
    end
    if not ioAvailable() then
      log("SIDECAR_WRITE_REFUSED", "reason=io_unavailable savePointId=" .. id)
      return false
    end

    local states = stateTable()
    local ids = {}
    local known, killed, alive = 0, 0, 0
    for catalogueId, value in pairs(states) do
      if byCatalogueId[catalogueId] ~= nil and type(value) == "boolean" then
        ids[#ids + 1] = catalogueId
        known = known + 1
        if value then killed = killed + 1 else alive = alive + 1 end
      end
    end
    table.sort(ids)

    local path = sidecarPath(id)
    local okOpen, fileOrErr = pcall(io.open, path, "w")
    if not okOpen or fileOrErr == nil then
      log("SIDECAR_WRITE_REFUSED", "reason=open_failed savePointId=" .. id ..
          " path=" .. path .. " error=" .. tostring(fileOrErr))
      return false
    end
    local file = fileOrErr
    local okWrite, writeErr = pcall(function()
      file:write("schema=1\n")
      file:write("savePointId=" .. id .. "\n")
      for _, catalogueId in ipairs(ids) do
        file:write(catalogueId .. "=" .. (states[catalogueId] and "1" or "0") .. "\n")
      end
      if type(file.flush) == "function" then file:flush() end
      file:close()
    end)
    if not okWrite then
      pcall(function() file:close() end)
      log("SIDECAR_WRITE_REFUSED", "reason=write_failed savePointId=" .. id ..
          " path=" .. path .. " error=" .. tostring(writeErr))
      return false
    end

    log("SIDECAR_WRITE", "savePointId=" .. id ..
        " source=" .. tostring(source) ..
        " known=" .. tostring(known) ..
        " killed=" .. tostring(killed) ..
        " alive=" .. tostring(alive) ..
        " path=" .. path ..
        " nativeProgressionTouched=false")
    return true
  end

  local function readSidecar(savePointId, source)
    local id = sanitizeSavePointId(savePointId)
    clearState()

    if id == "" then
      log("SIDECAR_LOAD", "savePointId=none source=" .. tostring(source) ..
          " result=uncached known=0 killed=0 alive=0")
      return false
    end
    if not ioAvailable() then
      log("SIDECAR_LOAD", "savePointId=" .. id ..
          " source=" .. tostring(source) ..
          " result=io_unavailable known=0 killed=0 alive=0")
      return false
    end

    local path = sidecarPath(id)
    local okOpen, fileOrErr = pcall(io.open, path, "r")
    if not okOpen or fileOrErr == nil then
      log("SIDECAR_LOAD", "savePointId=" .. id ..
          " source=" .. tostring(source) ..
          " result=missing path=" .. path ..
          " known=0 killed=0 alive=0")
      return false
    end

    local file = fileOrErr
    local parsed = {}
    local schemaOK = false
    local idOK = false
    local okRead, readErr = pcall(function()
      for line in file:lines() do
        if line == "schema=1" then
          schemaOK = true
        else
          local savedId = string.match(line, "^savePointId=(.+)$")
          if savedId ~= nil then
            idOK = sanitizeSavePointId(savedId) == id
          else
            local catalogueId, bit = string.match(line, "^(raven_[0-9a-f]+)=([01])$")
            if catalogueId ~= nil and byCatalogueId[catalogueId] ~= nil then
              parsed[catalogueId] = bit == "1"
            end
          end
        end
      end
      file:close()
    end)
    if not okRead then
      pcall(function() file:close() end)
      log("SIDECAR_LOAD", "savePointId=" .. id ..
          " source=" .. tostring(source) ..
          " result=read_failed error=" .. tostring(readErr) ..
          " known=0 killed=0 alive=0")
      return false
    end
    if not schemaOK or not idOK then
      log("SIDECAR_LOAD", "savePointId=" .. id ..
          " source=" .. tostring(source) ..
          " result=invalid_header known=0 killed=0 alive=0")
      return false
    end

    local known, killed, alive = 0, 0, 0
    for catalogueId, value in pairs(parsed) do
      known = known + 1
      if value then killed = killed + 1 else alive = alive + 1 end
      publishOne(catalogueId, value, "sidecar_restore:" .. id)
    end

    log("SIDECAR_LOAD", "savePointId=" .. id ..
        " source=" .. tostring(source) ..
        " result=loaded known=" .. tostring(known) ..
        " killed=" .. tostring(killed) ..
        " alive=" .. tostring(alive) ..
        " path=" .. path ..
        " nativeProgressionTouched=false")
    return true
  end

  local function validPayload(args)
    if type(args) ~= "table" then return nil, "payload_not_table" end
    local id = tostring(args.catalogueId or "")
    local row = byCatalogueId[id]
    if row == nil then return nil, "unknown_catalogue_id" end
    if tostring(args.marker or "") ~= row.Name then return nil, "marker_mismatch" end
    local x, y, z = tonumber(args.x), tonumber(args.y), tonumber(args.z)
    if x == nil or y == nil or z == nil then return nil, "position_missing" end
    local dx, dy, dz = x - row.X, y - row.Y, z - row.Z
    if dx * dx + dy * dy + dz * dz > 0.25 then return nil, "position_mismatch" end
    if type(args.killed) ~= "boolean" then return nil, "killed_not_boolean" end
    return row, nil
  end

  function MainHUD:EVT_COMPLETIONIST_V105_RAVEN_STATE(args)
    local row, err = validPayload(args)
    if row == nil then
      log("RECV_REFUSED", "reason=" .. tostring(err) ..
          " catalogueId=" .. tostring(type(args) == "table" and args.catalogueId or nil))
      return
    end

    local published = publishOne(
      row.CatalogueId,
      args.killed == true,
      "ui_bridge:" .. tostring(args.source)
    )

    log("RECV", "catalogueId=" .. row.CatalogueId ..
        " marker=" .. row.Name ..
        " killed=" .. tostring(args.killed == true) ..
        " source=" .. tostring(args.source) ..
        " generation=" .. tostring(_G.CompletionistMapV105RavenStateGeneration) ..
        " mapRuntimePublished=" .. tostring(published) ..
        " progressionWrites=false")
  end

  -- Compatibility receiver for earlier checkpoint-cache builds.
  function MainHUD:EVT_COMPLETIONIST_V105_RAVEN_CACHE_RESTORE(args)
    if type(args) ~= "table" then return end
    local row = byCatalogueId[tostring(args.catalogueId or "")]
    if row == nil or type(args.killed) ~= "boolean" then return end
    publishOne(
      row.CatalogueId,
      args.killed,
      "legacy_checkpoint_cache:" .. tostring(args.source)
    )
  end

  function MainHUD:EVT_COMPLETIONIST_V105_SAVEPOINT_CAPTURE(args)
    local id = type(args) == "table" and sanitizeSavePointId(args.savePointId) or ""
    writeSidecar(id, type(args) == "table" and args.source or "unknown")
  end

  function MainHUD:EVT_COMPLETIONIST_V105_SAVEPOINT_RESTORE(args)
    local id = type(args) == "table" and sanitizeSavePointId(args.savePointId) or ""
    readSidecar(id, type(args) == "table" and args.source or "unknown")
  end

  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " transport=UI_CALL_EVENT stateScope=uiGlobal" ..
      " sidecarIO=" .. tostring(ioAvailable()) ..
      " sidecarDir=" .. sidecarDir ..
      " progressionWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER
