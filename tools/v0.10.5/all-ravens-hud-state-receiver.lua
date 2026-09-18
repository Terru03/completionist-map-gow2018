-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER
-- Receives read-only Raven state from gameplay Lua through the runtime-proven
-- UI_CALL_EVENT bridge. Stores state only in UI Lua memory; no save/progression writes.
do
  local prefix = "[CompletionistMap v0.10.5-raven-ui-bridge] "
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

    _G.CompletionistMapV105RavenState = _G.CompletionistMapV105RavenState or {}
    _G.CompletionistMapV105RavenState[row.CatalogueId] = args.killed == true

    _G.CompletionistMapV105RavenStateGeneration =
      (tonumber(_G.CompletionistMapV105RavenStateGeneration) or 0) + 1

    local publish = _G.CompletionistMapV105PublishRavenState
    local published = false
    if type(publish) == "function" then
      local ok, accepted = pcall(
        publish,
        row.CatalogueId,
        args.killed == true,
        "ui_bridge:" .. tostring(args.source)
      )
      published = ok and accepted == true
    end

    log("RECV", "catalogueId=" .. row.CatalogueId ..
        " marker=" .. row.Name ..
        " killed=" .. tostring(args.killed == true) ..
        " source=" .. tostring(args.source) ..
        " generation=" .. tostring(_G.CompletionistMapV105RavenStateGeneration) ..
        " mapRuntimePublished=" .. tostring(published) ..
        " progressionWrites=false")
  end


  function MainHUD:EVT_COMPLETIONIST_V105_RAVEN_CACHE_RESTORE(args)
    if type(args) ~= "table" then
      log("CACHE_RECV_REFUSED", "reason=payload_not_table")
      return
    end
    local row = byCatalogueId[tostring(args.catalogueId or "")]
    if row == nil then
      log("CACHE_RECV_REFUSED", "reason=unknown_catalogue_id catalogueId=" .. tostring(args.catalogueId))
      return
    end
    if type(args.killed) ~= "boolean" then
      log("CACHE_RECV_REFUSED", "reason=killed_not_boolean catalogueId=" .. row.CatalogueId)
      return
    end

    _G.CompletionistMapV105RavenState = _G.CompletionistMapV105RavenState or {}
    _G.CompletionistMapV105RavenState[row.CatalogueId] = args.killed
    _G.CompletionistMapV105RavenStateGeneration =
      (tonumber(_G.CompletionistMapV105RavenStateGeneration) or 0) + 1

    local publish = _G.CompletionistMapV105PublishRavenState
    local published = false
    if type(publish) == "function" then
      local ok, accepted = pcall(
        publish,
        row.CatalogueId,
        args.killed,
        "checkpoint_cache:" .. tostring(args.source)
      )
      published = ok and accepted == true
    end

    log("CACHE_RECV", "catalogueId=" .. row.CatalogueId ..
        " killed=" .. tostring(args.killed) ..
        " source=" .. tostring(args.source) ..
        " generation=" .. tostring(_G.CompletionistMapV105RavenStateGeneration) ..
        " mapRuntimePublished=" .. tostring(published) ..
        " progressionWrites=false")
  end

  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " transport=UI_CALL_EVENT stateScope=uiGlobal checkpointCacheReceiver=true progressionWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER
