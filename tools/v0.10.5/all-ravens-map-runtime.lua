-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS
-- Data drives all Raven work. Raven markers stay hidden until atomic authority is established.
do
  local prefix = "[CompletionistMap v0.10.5-all-ravens] "
  local ravenClass = "CompletionistRaven"
  local mapResource = "goMapIconCompletionistRaven"
  local provenName = "Completionist_V103_Veithurgard_Raven_01"
  local rows = {
-- @@RAVEN_CATALOGUE_ROWS@@
  }
  local byName = {}
  local byCatalogueId = {}
  for _, row in ipairs(rows) do
    byName[row.Name] = row
    byCatalogueId[row.CatalogueId] = row
  end

  local byMarkerId = {}

  local states = _G.CompletionistMapV105RavenState or {}
  _G.CompletionistMapV105RavenState = states
  local eventKilled = _G.CompletionistMapV105EventKilled or {}
  _G.CompletionistMapV105EventKilled = eventKilled
  local hasAuthoritativeRavenState =
      _G.CompletionistMapV105HasAuthoritativeRavenState == true
  local previousPrompt = MapOn.GetShowOnCompassPrompt
  local previousShow = MapOn.ShowOnCompass
  local previousUpdate = MapOn.Update
  local previousCollision = MapOn.MapCollisionChangeHandler
  local lastMapOnSelf = nil
  local selectionGeneration = 0
  local promptIntent = nil
  local promptOverride = nil
  local promptSettleFrames = 0
  local promptSettleBucket = -1
  local customCompassOwnsTarget = false
  local nativeBoundaryPending = false
  local beginAuthorityBoundary = nil
  local hideStockExcept = nil
  local suppressLegacyRavenHud = nil
  local nativeBoundaryEpoch =
      tonumber(_G.CompletionistMapV105NativeBoundaryEpoch) or 0
  local nativeBoundaryCaptureReady = false
  local nativeBoundarySource = nil
  local nativeResetRecheckFrames = 0
  local nativeResetRecheckBucket = -1
  local nativeResetRecheckLimit = 360
  local nativePort = 43753
  local nativeRequest = "GET RAVEN_SNAPSHOT_V1\n"
  local nativeMaxResponseBytes = 4096
  local lastNativeGeneration = tonumber(_G.CompletionistMapV105LastNativeRavenGeneration)
  local lastNativeRestoreEpoch =
      tonumber(_G.CompletionistMapV105LastNativeRestoreEpoch)
  local lastNativeNotice = nil
  local lastRegionSummaryDiagnosticKey = nil
  local regionSummaryTargetCounts = {
    RegionSummary_CALS_Raven_Parent = 1,
    RegionSummary_RP_Raven_Parent = 6,
  }
  local regionSummaryBonusParents = {
    RegionSummary_CALS_Raven_Parent = true,
    RegionSummary_RP_Raven_Parent = true,
  }

  local function regionSummaryTargetCount(parent, physicalCount)
    return regionSummaryTargetCounts[parent] or physicalCount
  end

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function isCollected(catalogueId)
    return states[catalogueId] == true
  end

  local function shouldShow(catalogueId)
    return hasAuthoritativeRavenState and
        byCatalogueId[catalogueId] ~= nil and not isCollected(catalogueId)
  end

  local function nativeNotice(category, fields, key)
    if key == lastNativeNotice then return end
    lastNativeNotice = key
    log(category, fields)
  end

  local function buildRegionSummaryGroups()
    local groups = {}
    for _, row in ipairs(rows) do
      if type(row.ParentQuest) == "string" and row.ParentQuest ~= "" then
        local group = groups[row.ParentQuest]
        if group == nil then
          group = {count=0, realms={}, rows={}}
          groups[row.ParentQuest] = group
        end
        group.count = group.count + 1
        group.realms[row.Realm] = true
        group.rows[#group.rows + 1] = row
      end
    end
    return groups
  end

  local function readRegionSummaryCompleted(parent, physicalCount)
    if type(game) ~= "table" or type(game.QuestManager) ~= "table" or
        type(game.QuestManager.GetQuestProgressAndGoal) ~= "function" then
      return nil, "unavailable", nil, nil
    end
    local ok, progress, goal = pcall(
        game.QuestManager.GetQuestProgressAndGoal, parent)
    if not ok then return nil, "query_failed", nil, nil end

    local progressNumber = tonumber(progress)
    local goalNumber = tonumber(goal)
    local completed = nil
    local shape = "ambiguous"

    -- The PC runtime observed in field captures returns (nil, completed).
    -- Keep support for the conventional (progress, goal) shape when the goal
    -- exactly matches this one-to-one physical group.
    if progressNumber == nil and goalNumber ~= nil then
      completed = goalNumber
      shape = "second_only_completed"
    elseif progressNumber ~= nil and goalNumber == nil then
      completed = progressNumber
      shape = "first_only_completed"
    elseif progressNumber ~= nil and goalNumber ~= nil then
      if goalNumber == physicalCount and progressNumber >= 0 and
          progressNumber <= goalNumber then
        completed = progressNumber
        shape = "progress_goal"
      elseif progressNumber == physicalCount and goalNumber >= 0 and
          goalNumber <= progressNumber then
        completed = goalNumber
        shape = "goal_progress_reversed"
      end
    end

    if completed == nil or completed < 0 or completed > physicalCount or
        completed ~= math.floor(completed) then
      return nil, shape, progressNumber, goalNumber
    end
    return completed, shape, progressNumber, goalNumber
  end

  local function logRegionSummaryDiagnostics(source)
    if hasAuthoritativeRavenState then return end

    local groups = buildRegionSummaryGroups()
    local parents = {}
    for parent, _ in pairs(groups) do parents[#parents + 1] = parent end
    table.sort(parents)

    local records = {}
    local keyParts = {}
    for _, parent in ipairs(parents) do
      local group = groups[parent]
      local completed, shape, progressNumber, goalNumber =
          readRegionSummaryCompleted(
              parent, regionSummaryTargetCount(parent, group.count))
      local realmNames = {}
      for realm, _ in pairs(group.realms) do realmNames[#realmNames + 1] = realm end
      table.sort(realmNames)
      local realmText = table.concat(realmNames, ",")
      local constraintSafe =
          regionSummaryBonusParents[parent] ~= true and completed ~= nil
      local record =
          "parent=" .. parent ..
          " progress=" .. tostring(progressNumber) ..
          " goal=" .. tostring(goalNumber) ..
          " completed=" .. tostring(completed) ..
          " accessorShape=" .. tostring(shape) ..
          " catalogueCount=" .. tostring(group.count) ..
          " constraintSafe=" .. tostring(constraintSafe) ..
          " bonusParent=" .. tostring(regionSummaryBonusParents[parent] == true) ..
          " realms=" .. realmText
      records[#records + 1] = record
      keyParts[#keyParts + 1] = record
    end

    local key = table.concat(keyParts, "|")
    if key == lastRegionSummaryDiagnosticKey then return end
    lastRegionSummaryDiagnosticKey = key
    for _, record in ipairs(records) do
      log("REGION_SUMMARY_DIAGNOSTIC",
          "source=" .. tostring(source) .. " " .. record ..
          " readOnly=true progressionWrites=false")
    end
  end

  local function closeSocket(client)
    if client ~= nil then pcall(function() client:close() end) end
  end

  local function receiveNativeLine(client)
    local bytes = {}
    for index = 1, nativeMaxResponseBytes do
      local ok, value, err = pcall(function() return client:receive(1) end)
      if not ok or type(value) ~= "string" or string.len(value) ~= 1 then
        return nil, "receive:" .. tostring(ok and err or value)
      end
      if value == "\n" then return table.concat(bytes), nil end
      if value == "\r" then return nil, "response_cr" end
      bytes[index] = value
    end
    return nil, "response_too_large"
  end

  local function parseNativeSnapshot(line, expectedSchema, expectedBoundaryEpoch)
    local header = expectedSchema == 2 and "RAVEN_SNAPSHOT_V2 " or "RAVEN_SNAPSHOT_V1 "
    if expectedSchema == 1 and line == "RAVEN_SNAPSHOT_V1 UNAVAILABLE" then
      return nil, "snapshot_not_ready"
    end
    if expectedSchema == 2 and type(line) == "string" and
        string.sub(line, 1, string.len("RAVEN_SNAPSHOT_V2 UNAVAILABLE")) ==
            "RAVEN_SNAPSHOT_V2 UNAVAILABLE" then
      return nil, "boundary_snapshot_not_ready"
    end
    if type(line) ~= "string" or
        string.sub(line, 1, string.len(header)) ~= header then
      return nil, "response_header"
    end

    local partialHeader =
        expectedSchema == 2 and "RAVEN_SNAPSHOT_V2 PARTIAL " or
            "RAVEN_SNAPSHOT_V1 PARTIAL "
    local isPartial =
        string.sub(line, 1, string.len(partialHeader)) == partialHeader

    local fields = {}
    for key, value in string.gmatch(line, "([%a][%w]*)=([^%s]+)") do
      if fields[key] ~= nil then return nil, "duplicate_field:" .. key end
      fields[key] = value
    end

    local function integer(name)
      local value = tonumber(fields[name])
      if value == nil or value < 0 or value ~= math.floor(value) then
        return nil
      end
      return value
    end

    local schema = integer("schema")
    local generation = integer("generation")
    local capturedTickMs = integer("capturedTickMs")
    local count = integer("count")
    local unknown = integer("unknown")
    local alive = integer("alive")
    local killed = integer("killed")
    local explicit = integer("explicit")
    local absentWadFalse = integer("absentWadFalse")
    local restoreEpoch = expectedSchema == 1 and integer("restoreEpoch") or nil
    local boundaryEpoch = expectedSchema == 2 and integer("boundaryEpoch") or nil

    if schema ~= expectedSchema or capturedTickMs == nil or count ~= #rows or
        unknown == nil or alive == nil or killed == nil or
        explicit == nil or absentWadFalse == nil or
        fields.killedIds == nil or
        (expectedSchema == 1 and restoreEpoch == nil) then
      return nil, "response_counts"
    end
    if expectedSchema == 2 and
        (boundaryEpoch == nil or boundaryEpoch < 1 or
         boundaryEpoch ~= expectedBoundaryEpoch) then
      return nil, "boundary_epoch_mismatch"
    end

    if isPartial then
      if generation ~= nil or
          (unknown < 1 and absentWadFalse < 1) or
          alive + killed + unknown ~= #rows or
          explicit + absentWadFalse > alive + killed or
          fields.unknownIds == nil or fields.absenceIds == nil then
        return nil, "partial_counts"
      end

      local states = {}
      for catalogueId, _ in pairs(byCatalogueId) do states[catalogueId] = false end

      local unknownCatalogueIds = {}
      local unknownSeen = {}
      if fields.unknownIds ~= "-" then
        for catalogueId in string.gmatch(fields.unknownIds, "([^,]+)") do
          if byCatalogueId[catalogueId] == nil then
            return nil, "unknown_catalogue_id"
          end
          if unknownSeen[catalogueId] then
            return nil, "duplicate_unknown_catalogue_id"
          end
          unknownSeen[catalogueId] = true
          states[catalogueId] = nil
          unknownCatalogueIds[#unknownCatalogueIds + 1] = catalogueId
        end
      end
      if #unknownCatalogueIds ~= unknown then
        return nil, "partial_unknown_count"
      end

      local absenceCatalogueIds = {}
      local absenceSeen = {}
      if fields.absenceIds ~= "-" then
        for catalogueId in string.gmatch(fields.absenceIds, "([^,]+)") do
          if byCatalogueId[catalogueId] == nil then
            return nil, "unknown_catalogue_id"
          end
          if unknownSeen[catalogueId] or absenceSeen[catalogueId] then
            return nil, "partial_absence_overlap"
          end
          absenceSeen[catalogueId] = true
          absenceCatalogueIds[#absenceCatalogueIds + 1] = catalogueId
        end
      end
      if #absenceCatalogueIds ~= absentWadFalse then
        return nil, "partial_absence_count"
      end

      local killedCatalogueIds = {}
      local killedSeen = {}
      if fields.killedIds ~= "-" then
        for catalogueId in string.gmatch(fields.killedIds, "([^,]+)") do
          if byCatalogueId[catalogueId] == nil then
            return nil, "unknown_catalogue_id"
          end
          if unknownSeen[catalogueId] or absenceSeen[catalogueId] then
            return nil, "partial_overlap"
          end
          if killedSeen[catalogueId] then
            return nil, "duplicate_catalogue_id"
          end
          killedSeen[catalogueId] = true
          states[catalogueId] = true
          killedCatalogueIds[#killedCatalogueIds + 1] = catalogueId
        end
      end
      if #killedCatalogueIds ~= killed then return nil, "killed_count" end

      local inferredAlive = 0
      for catalogueId, _ in pairs(byCatalogueId) do
        if states[catalogueId] == false then inferredAlive = inferredAlive + 1 end
      end
      if inferredAlive ~= alive then return nil, "partial_alive_count" end

      return {
        partial = true,
        schema = schema, capturedTickMs = capturedTickMs,
        restoreEpoch = restoreEpoch, boundaryEpoch = boundaryEpoch,
        count = count, unknownCount = unknown,
        aliveCount = alive, killedCount = killed,
        explicitCount = explicit,
        absenceDefaultFalseCount = absentWadFalse,
        states = states,
        killedCatalogueIds = killedCatalogueIds,
        unknownCatalogueIds = unknownCatalogueIds,
        absenceCatalogueIds = absenceCatalogueIds,
      }, nil
    end

    -- A stable raw fresh-save image is all absence-default false rows.
    -- Process-local positive kill notes from the previous save can still be
    -- merged into that image before Lua sees it when no gameplay Raven exists
    -- to advance the bridge epoch. In that exact case the apparent killed rows
    -- are overlay-only: explicit remains zero and each overlay kill replaces
    -- one absence-default row. Preserve the shape for RegionSummary-guarded
    -- fresh-zero normalization instead of rejecting it as malformed.
    local freshZeroOverlayShape =
        explicit == 0 and alive + killed == #rows and
        absentWadFalse + killed == #rows
    if generation == nil or generation < 1 or unknown ~= 0 or
        alive + killed ~= #rows or
        (explicit + absentWadFalse ~= #rows and not freshZeroOverlayShape) then
      return nil, "response_counts"
    end

    local states = {}
    for catalogueId, _ in pairs(byCatalogueId) do states[catalogueId] = false end
    local killedCatalogueIds = {}
    if fields.killedIds ~= "-" then
      for catalogueId in string.gmatch(fields.killedIds, "([^,]+)") do
        if byCatalogueId[catalogueId] == nil then
          return nil, "unknown_catalogue_id"
        end
        if states[catalogueId] == true then
          return nil, "duplicate_catalogue_id"
        end
        states[catalogueId] = true
        killedCatalogueIds[#killedCatalogueIds + 1] = catalogueId
      end
    end
    if #killedCatalogueIds ~= killed then return nil, "killed_count" end

    return {
      partial = false,
      schema = schema, generation = generation, capturedTickMs = capturedTickMs,
      restoreEpoch = restoreEpoch, boundaryEpoch = boundaryEpoch,
      count = count, unknownCount = 0,
      aliveCount = alive, killedCount = killed,
      explicitCount = explicit,
      absenceDefaultFalseCount = absentWadFalse,
      states = states, killedCatalogueIds = killedCatalogueIds,
    }, nil
  end

  local function requestNativeSnapshot(request, schema, boundaryEpoch)
    local socketOK, socket = pcall(require, "socket.core")
    if not socketOK or type(socket) ~= "table" or type(socket.tcp) ~= "function" then
      return nil, "socket_core_unavailable"
    end
    local createOK, client = pcall(socket.tcp)
    if not createOK or client == nil then return nil, "socket_create" end
    pcall(function() client:settimeout(0.25) end)
    pcall(function() client:settimeout(0.25, "t") end)
    local connectOK, connected, connectError = pcall(function()
      return client:connect("127.0.0.1", nativePort)
    end)
    if not connectOK or connected == nil then
      closeSocket(client)
      return nil, "connect:" .. tostring(connectOK and connectError or connected)
    end
    local sendOK, sent, sendError = pcall(function()
      return client:send(request)
    end)
    if not sendOK or sent ~= string.len(request) then
      closeSocket(client)
      return nil, "send:" .. tostring(sendOK and sendError or sent)
    end
    local line, receiveError = receiveNativeLine(client)
    closeSocket(client)
    if line == nil then return nil, receiveError end
    return parseNativeSnapshot(line, schema, boundaryEpoch)
  end

  local function getRavenSnapshot()
    return requestNativeSnapshot(nativeRequest, 1, nil)
  end

  local function captureRavenBoundarySnapshot(boundaryEpoch)
    if type(boundaryEpoch) ~= "number" or boundaryEpoch < 1 or
        boundaryEpoch ~= math.floor(boundaryEpoch) then
      return nil, "invalid_boundary_epoch"
    end
    local request = "CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=" ..
        tostring(boundaryEpoch) .. "\n"
    return requestNativeSnapshot(request, 2, boundaryEpoch)
  end

  local nativeNamespace = rawget(_G, "CompletionistMapNative")
  if nativeNamespace == nil then
    nativeNamespace = {}
    rawset(_G, "CompletionistMapNative", nativeNamespace)
  end
  if type(nativeNamespace) == "table" then
    if rawget(nativeNamespace, "GetRavenSnapshot") == nil then
      nativeNamespace.GetRavenSnapshot = getRavenSnapshot
    elseif type(nativeNamespace.GetRavenSnapshot) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=api_collision:get", "api_collision:get")
    end

    if rawget(nativeNamespace, "CaptureRavenBoundarySnapshot") == nil then
      nativeNamespace.CaptureRavenBoundarySnapshot = captureRavenBoundarySnapshot
    elseif type(nativeNamespace.CaptureRavenBoundarySnapshot) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=api_collision:capture", "api_collision:capture")
    end
  else
    nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
        "reason=namespace_collision", "namespace_collision")
  end

  local function validateFullNativeAuthority(snapshot, source)
    if type(snapshot) ~= "table" or type(snapshot.states) ~= "table" then
      return false, "full_invalid"
    end

    local groups = buildRegionSummaryGroups()

    -- The native publication gate already requires the raw all-false image to
    -- remain stable for 750 ms. A fresh save can inherit process-local positive
    -- kill notes from the previous save if no Raven gameplay instance existed
    -- to advance the bridge epoch. Those overlay-only kills are recognizable:
    -- no state is explicit, and every apparent kill replaces one WAD-absence
    -- default row. RegionSummary is the independent veto before normalizing
    -- that exact shape back to the raw 0/53 fresh authority.
    local freshZeroBase =
        snapshot.explicitCount == 0 and
        snapshot.aliveCount + snapshot.killedCount == #rows and
        snapshot.absenceDefaultFalseCount + snapshot.killedCount == #rows
    if freshZeroBase then
      for parent, group in pairs(groups) do
        local targetCount = regionSummaryTargetCount(parent, group.count)
        local completed = readRegionSummaryCompleted(parent, targetCount)
        if completed ~= nil and completed > 0 then
          nativeNotice("NATIVE_AUTHORITY_REGION_REFUSED",
              "reason=fresh_zero_conflict parent=" .. tostring(parent) ..
              " completed=" .. tostring(completed) ..
              " overlayKilled=" .. tostring(snapshot.killedCount) ..
              " source=" .. tostring(source),
              "fresh_zero_conflict:" .. tostring(parent) .. ":" ..
              tostring(completed) .. ":" .. tostring(snapshot.killedCount))
          return false, "fresh_zero_region_summary_conflict", false
        end
      end
      if snapshot.killedCount > 0 then
        nativeNotice("NATIVE_AUTHORITY_FRESH_ZERO_NORMALIZED",
            "overlayKilled=" .. tostring(snapshot.killedCount) ..
            " source=" .. tostring(source) ..
            " readOnly=true progressionWrites=false",
            "fresh_zero_normalized:" .. tostring(snapshot.killedCount))
      end
      return true, nil, true
    end
    for parent, group in pairs(groups) do
      local targetCount = regionSummaryTargetCount(parent, group.count)
      local completed, shape =
          readRegionSummaryCompleted(parent, targetCount)
      if completed == nil then
        nativeNotice("NATIVE_AUTHORITY_REGION_REFUSED",
            "reason=region_summary_ambiguous parent=" .. tostring(parent) ..
            " accessorShape=" .. tostring(shape) ..
            " source=" .. tostring(source),
            "full_region_summary:" .. tostring(parent))
        return false, "region_summary_ambiguous"
      end

      local nativeKilled = 0
      for _, row in ipairs(group.rows) do
        if snapshot.states[row.CatalogueId] == true then
          nativeKilled = nativeKilled + 1
        end
      end

      local valid = nativeKilled == completed
      if regionSummaryBonusParents[parent] == true then
        valid = valid or nativeKilled == completed + 1
      end
      if not valid then
        nativeNotice("NATIVE_AUTHORITY_REGION_REFUSED",
            "reason=count_conflict parent=" .. tostring(parent) ..
            " completed=" .. tostring(completed) ..
            " nativeKilled=" .. tostring(nativeKilled) ..
            " physical=" .. tostring(group.count) ..
            " target=" .. tostring(targetCount) ..
            " bonusParent=" ..
            tostring(regionSummaryBonusParents[parent] == true) ..
            " source=" .. tostring(source),
            "full_count_conflict:" .. tostring(parent) .. ":" ..
            tostring(completed) .. ":" .. tostring(nativeKilled))
        return false, "region_summary_count_conflict"
      end
    end
    return true, nil
  end

  local function resolvePartialNativeAuthority(
      snapshot, source, boundaryApply, requestedBoundaryEpoch)
    if snapshot.partial ~= true or type(snapshot.states) ~= "table" or
        type(snapshot.unknownCount) ~= "number" or
        type(snapshot.absenceCatalogueIds) ~= "table" then
      return false, "partial_invalid"
    end
    if snapshot.unknownCount < 0 or snapshot.absenceDefaultFalseCount < 0 or
        snapshot.unknownCount + snapshot.absenceDefaultFalseCount < 1 then
      return false, "partial_invalid"
    end
    if boundaryApply and snapshot.boundaryEpoch ~= requestedBoundaryEpoch then
      return false, "partial_boundary_epoch_mismatch"
    end

    local groups = buildRegionSummaryGroups()
    local resolved = {}
    for catalogueId, _ in pairs(byCatalogueId) do
      resolved[catalogueId] = snapshot.states[catalogueId]
    end

    local absenceSeen = {}
    for _, catalogueId in ipairs(snapshot.absenceCatalogueIds) do
      if byCatalogueId[catalogueId] == nil or absenceSeen[catalogueId] then
        return false, "partial_absence_invalid"
      end
      absenceSeen[catalogueId] = true
      if resolved[catalogueId] ~= false then
        return false, "partial_absence_state"
      end
      resolved[catalogueId] = nil
    end

    local solvedUnresolved = 0
    local expectedUnresolved =
        snapshot.unknownCount + snapshot.absenceDefaultFalseCount

    for parent, group in pairs(groups) do
      local unresolvedRows = {}
      local knownKilled = 0
      for _, row in ipairs(group.rows) do
        local state = resolved[row.CatalogueId]
        if state == nil then
          unresolvedRows[#unresolvedRows + 1] = row
        elseif state == true then
          knownKilled = knownKilled + 1
        elseif state ~= false then
          return false, "partial_state_type"
        end
      end

      local targetCount = regionSummaryTargetCount(parent, group.count)
      local completed, shape =
          readRegionSummaryCompleted(parent, targetCount)
      if completed == nil then
        nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
            "reason=region_summary_ambiguous parent=" .. tostring(parent) ..
            " accessorShape=" .. tostring(shape),
            "partial_region_summary:" .. tostring(parent))
        return false, "partial_region_summary"
      end

      if regionSummaryBonusParents[parent] == true then
        if #unresolvedRows > 0 then
          nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
              "reason=bonus_parent_unresolved parent=" .. tostring(parent) ..
              " unknown=" .. tostring(#unresolvedRows),
              "partial_bonus_parent:" .. tostring(parent))
          return false, "partial_bonus_parent"
        end
        if knownKilled ~= completed and knownKilled ~= completed + 1 then
          nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
              "reason=bonus_count_conflict parent=" .. tostring(parent) ..
              " completed=" .. tostring(completed) ..
              " knownKilled=" .. tostring(knownKilled),
              "partial_bonus_conflict:" .. tostring(parent))
          return false, "partial_bonus_conflict"
        end
      else
        local remainingKilled = completed - knownKilled
        if remainingKilled < 0 or remainingKilled > #unresolvedRows then
          nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
              "reason=constraint_conflict parent=" .. tostring(parent) ..
              " completed=" .. tostring(completed) ..
              " knownKilled=" .. tostring(knownKilled) ..
              " unresolved=" .. tostring(#unresolvedRows),
              "partial_constraint_conflict:" .. tostring(parent))
          return false, "partial_constraint_conflict"
        end

        if #unresolvedRows == 0 then
          if remainingKilled ~= 0 then
            return false, "partial_constraint_conflict"
          end
        else
          local resolvedKilled = nil
          if remainingKilled == 0 then
            resolvedKilled = false
          elseif remainingKilled == #unresolvedRows then
            resolvedKilled = true
          else
            nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
                "reason=constraint_not_unique parent=" .. tostring(parent) ..
                " remainingKilled=" .. tostring(remainingKilled) ..
                " unresolved=" .. tostring(#unresolvedRows),
                "partial_constraint_not_unique:" .. tostring(parent))
            return false, "partial_constraint_not_unique"
          end

          for _, row in ipairs(unresolvedRows) do
            resolved[row.CatalogueId] = resolvedKilled
            solvedUnresolved = solvedUnresolved + 1
          end
        end
      end
    end

    if solvedUnresolved ~= expectedUnresolved then
      nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
          "reason=unmapped_unresolved solved=" .. tostring(solvedUnresolved) ..
          " expected=" .. tostring(expectedUnresolved),
          "partial_unmapped_unresolved")
      return false, "partial_unmapped_unresolved"
    end

    local killedIds = {}
    local aliveCount = 0
    for catalogueId, _ in pairs(byCatalogueId) do
      local value = resolved[catalogueId]
      if type(value) ~= "boolean" then
        nativeNotice("NATIVE_AUTHORITY_PARTIAL_REFUSED",
            "reason=incomplete_states catalogueId=" .. tostring(catalogueId),
            "partial_incomplete_states")
        return false, "partial_incomplete_states"
      end
      if value then
        killedIds[#killedIds + 1] = catalogueId
      else
        aliveCount = aliveCount + 1
      end
    end
    if #killedIds + aliveCount ~= #rows then
      return false, "partial_resolved_counts"
    end

    local apply = _G.CompletionistMapV105ApplyPersistedRavenKills
    if type(apply) ~= "function" then
      return false, "apply_api_unavailable"
    end
    local applied, accepted = apply(
        killedIds,
        "native_partial_region_summary:" .. tostring(source) ..
        (boundaryApply and ":boundaryEpoch:" ..
            tostring(requestedBoundaryEpoch) or ""),
        boundaryApply)
    if applied ~= true or accepted ~= #killedIds then
      return false, "partial_apply_refused"
    end

    if boundaryApply then
      lastNativeRestoreEpoch = requestedBoundaryEpoch
      _G.CompletionistMapV105LastNativeRestoreEpoch = requestedBoundaryEpoch
      nativeBoundaryPending = false
      nativeBoundaryCaptureReady = false
      nativeBoundarySource = nil
      nativeResetRecheckFrames = 0
      nativeResetRecheckBucket = -1
    elseif snapshot.restoreEpoch ~= nil then
      lastNativeRestoreEpoch = snapshot.restoreEpoch
      _G.CompletionistMapV105LastNativeRestoreEpoch = snapshot.restoreEpoch
    end

    lastNativeNotice = nil
    log("NATIVE_AUTHORITY_DERIVED",
        "knownKilled=" .. tostring(snapshot.killedCount) ..
        " knownAlive=" .. tostring(snapshot.aliveCount) ..
        " nativeUnknown=" .. tostring(snapshot.unknownCount) ..
        " absenceUnresolved=" ..
        tostring(snapshot.absenceDefaultFalseCount) ..
        " resolvedUnresolved=" .. tostring(expectedUnresolved) ..
        " finalKilled=" .. tostring(#killedIds) ..
        " finalAlive=" .. tostring(aliveCount) ..
        " postBoundary=" .. tostring(boundaryApply) ..
        " boundaryEpoch=" ..
        tostring(boundaryApply and requestedBoundaryEpoch or 0) ..
        " restoreEpoch=" ..
        tostring(boundaryApply and requestedBoundaryEpoch or
            snapshot.restoreEpoch or 0) ..
        " authority=native_partial_plus_region_summary" ..
        " readOnly=true progressionWrites=false")
    return true, nil
  end

  local function refreshNativeAuthority(source)
    local namespace = rawget(_G, "CompletionistMapNative")
    if type(namespace) ~= "table" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=namespace_unavailable", "namespace_unavailable")
      return false, "namespace_unavailable"
    end

    local boundaryApply = nativeBoundaryPending
    local requestedBoundaryEpoch = nil
    local accessor = nil
    if boundaryApply then
      if not nativeBoundaryCaptureReady then
        nativeNotice("NATIVE_AUTHORITY_BOUNDARY_WAIT",
            "epoch=" .. tostring(nativeBoundaryEpoch) ..
            " source=" .. tostring(nativeBoundarySource) ..
            " reason=load_not_complete",
            "boundary_not_ready:" .. tostring(nativeBoundaryEpoch))
        return false, "boundary_not_ready"
      end
      accessor = namespace.CaptureRavenBoundarySnapshot
      requestedBoundaryEpoch = nativeBoundaryEpoch
    else
      accessor = namespace.GetRavenSnapshot
    end

    if type(accessor) ~= "function" then
      local apiName = boundaryApply and "capture_api_unavailable" or "api_unavailable"
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=" .. apiName, apiName)
      return false, apiName
    end

    local ok, snapshot, reason
    if boundaryApply then
      ok, snapshot, reason = pcall(accessor, requestedBoundaryEpoch)
    else
      ok, snapshot, reason = pcall(accessor)
    end
    if not ok or type(snapshot) ~= "table" then
      local unavailable = ok and tostring(reason) or "call_failed:" .. tostring(snapshot)
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=" .. unavailable,
          "unavailable:" .. tostring(boundaryApply) .. ":" .. unavailable)
      return false, unavailable
    end

    if not boundaryApply then
      local restoreEpoch = tonumber(snapshot.restoreEpoch)
      if restoreEpoch == nil or restoreEpoch < 0 or
          restoreEpoch ~= math.floor(restoreEpoch) then
        nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
            "reason=invalid_restore_epoch", "invalid_restore_epoch")
        return false, "invalid_restore_epoch"
      end
      if lastNativeRestoreEpoch ~= nil and restoreEpoch < lastNativeRestoreEpoch then
        nativeNotice("NATIVE_AUTHORITY_STALE",
            "restoreEpoch=" .. tostring(restoreEpoch) ..
            " lastRestoreEpoch=" .. tostring(lastNativeRestoreEpoch),
            "stale_restore_epoch:" .. tostring(restoreEpoch))
        return false, "stale_restore_epoch"
      end
      if restoreEpoch > 0 and
          (lastNativeRestoreEpoch == nil or restoreEpoch > lastNativeRestoreEpoch) then
        if type(beginAuthorityBoundary) ~= "function" then
          return false, "boundary_api_unavailable"
        end
        beginAuthorityBoundary("native_restore_epoch", true, restoreEpoch)
        return refreshNativeAuthority(tostring(source) .. ":restore_epoch")
      end
    end

    if snapshot.partial == true then
      local resolved, partialReason = resolvePartialNativeAuthority(
          snapshot, source, boundaryApply, requestedBoundaryEpoch)
      if not resolved then
        nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
            "reason=" .. tostring(partialReason),
            "partial_unavailable:" .. tostring(partialReason))
      end
      return resolved, partialReason
    end

    local regionValid, regionReason, normalizeFreshZero =
        validateFullNativeAuthority(snapshot, source)
    if not regionValid then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=" .. tostring(regionReason),
          "full_region_unavailable:" .. tostring(regionReason))
      return false, regionReason
    end

    local generation = tonumber(snapshot.generation)
    if generation == nil or generation < 1 or generation ~= math.floor(generation) then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=invalid_generation", "invalid_generation")
      return false, "invalid_generation"
    end
    if lastNativeGeneration ~= nil and generation <= lastNativeGeneration then
      nativeNotice("NATIVE_AUTHORITY_STALE",
          "generation=" .. tostring(generation) ..
          " last=" .. tostring(lastNativeGeneration) ..
          " postBoundary=" .. tostring(boundaryApply),
          "stale:" .. tostring(generation) .. ":" .. tostring(lastNativeGeneration))
      return false, "stale"
    end

    local expectedSchema = boundaryApply and 2 or 1
    local freshZeroBase =
        normalizeFreshZero == true and
        snapshot.explicitCount == 0 and
        snapshot.aliveCount + snapshot.killedCount == #rows and
        snapshot.absenceDefaultFalseCount + snapshot.killedCount == #rows
    if type(snapshot.states) ~= "table" or snapshot.schema ~= expectedSchema or
        type(snapshot.count) ~= "number" or snapshot.count ~= #rows or
        type(snapshot.aliveCount) ~= "number" or
        type(snapshot.killedCount) ~= "number" or
        snapshot.aliveCount + snapshot.killedCount ~= #rows or
        type(snapshot.explicitCount) ~= "number" or
        type(snapshot.absenceDefaultFalseCount) ~= "number" or
        (snapshot.explicitCount + snapshot.absenceDefaultFalseCount ~= #rows and
         not freshZeroBase) then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=invalid_snapshot", "invalid_snapshot")
      return false, "invalid_snapshot"
    end

    if boundaryApply and snapshot.boundaryEpoch ~= requestedBoundaryEpoch then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=boundary_epoch_mismatch expected=" ..
          tostring(requestedBoundaryEpoch) .. " actual=" ..
          tostring(snapshot.boundaryEpoch),
          "boundary_epoch_mismatch:" .. tostring(requestedBoundaryEpoch) ..
          ":" .. tostring(snapshot.boundaryEpoch))
      return false, "boundary_epoch_mismatch"
    end

    local killedIds = {}
    for catalogueId, _ in pairs(byCatalogueId) do
      local value = snapshot.states[catalogueId]
      if type(value) ~= "boolean" then
        nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
            "reason=incomplete_states", "incomplete_states")
        return false, "incomplete_states"
      end
      if not freshZeroBase and value then
        killedIds[#killedIds + 1] = catalogueId
      end
    end
    if (not freshZeroBase and #killedIds ~= snapshot.killedCount) or
        (freshZeroBase and #killedIds ~= 0) then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=state_count_mismatch", "state_count_mismatch")
      return false, "state_count_mismatch"
    end

    local apply = _G.CompletionistMapV105ApplyPersistedRavenKills
    if type(apply) ~= "function" then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=apply_api_unavailable", "apply_api_unavailable")
      return false, "apply_api_unavailable"
    end

    local applied, accepted = apply(
        killedIds,
        "native:" .. tostring(source) ..
        ":generation:" .. tostring(generation) ..
        (boundaryApply and ":boundaryEpoch:" ..
            tostring(requestedBoundaryEpoch) or ""),
        boundaryApply)
    if applied ~= true or accepted ~= #killedIds then
      nativeNotice("NATIVE_AUTHORITY_UNAVAILABLE",
          "reason=apply_refused", "apply_refused")
      return false, "apply_refused"
    end

    lastNativeGeneration = generation
    _G.CompletionistMapV105LastNativeRavenGeneration = generation
    if boundaryApply then
      lastNativeRestoreEpoch = requestedBoundaryEpoch
      _G.CompletionistMapV105LastNativeRestoreEpoch = requestedBoundaryEpoch
      nativeBoundaryPending = false
      nativeBoundaryCaptureReady = false
      nativeBoundarySource = nil
      nativeResetRecheckFrames = 0
      nativeResetRecheckBucket = -1
    elseif snapshot.restoreEpoch ~= nil then
      lastNativeRestoreEpoch = snapshot.restoreEpoch
      _G.CompletionistMapV105LastNativeRestoreEpoch = snapshot.restoreEpoch
    end

    lastNativeNotice = nil
    log("NATIVE_AUTHORITY_APPLIED",
        "generation=" .. tostring(generation) ..
        " killed=" .. tostring(snapshot.killedCount) ..
        " alive=" .. tostring(snapshot.aliveCount) ..
        " explicit=" .. tostring(snapshot.explicitCount) ..
        " absentWadFalse=" .. tostring(snapshot.absenceDefaultFalseCount) ..
        " postBoundary=" .. tostring(boundaryApply) ..
        " boundaryEpoch=" ..
        tostring(boundaryApply and requestedBoundaryEpoch or 0) ..
        " restoreEpoch=" ..
        tostring(boundaryApply and requestedBoundaryEpoch or snapshot.restoreEpoch or 0) ..
        " authority=" .. (boundaryApply and "capture_v2" or "latest_v1"))
    return true, nil
  end

  local function rememberMarkerId(name, info)
    if type(name) ~= "string" or type(info) ~= "table" or info.Id == nil then return end
    byMarkerId[tostring(info.Id)] = name
  end

  local function markerInfo(name)
    local ok, info = pcall(function() return game.Map.GetMarkerInfo(name) end)
    if not ok or type(info) ~= "table" or info.Id == nil then return nil end
    rememberMarkerId(name, info)
    return info
  end

  local function knownNameForId(id)
    if id == nil then return nil end
    local key = tostring(id)
    local cached = byMarkerId[key]
    if cached ~= nil then return cached end
    for name, _ in pairs(byName) do
      local info = markerInfo(name)
      if info ~= nil and tostring(info.Id) == key then return name end
    end
    return nil
  end

  local function recycle(go)
    if go == nil then return true end
    local ok = pcall(function() Map.RecycleIcon(go) end)
    return ok
  end

  local function clearLegacy(self)
    if self.completionistSharedLoaderTwinGO ~= nil then
      recycle(self.completionistSharedLoaderTwinGO)
      self.completionistSharedLoaderTwinGO = nil
    end
    if self.completionistMapV100MapIconGO ~= nil then
      recycle(self.completionistMapV100MapIconGO)
      self.completionistMapV100MapIconGO = nil
    end
    self.completionistMapV100Selected = false
  end

  local function clearSelection(self, reason)
    local selected = self and self.completionistMapV105SelectedRaven or nil
    if selected ~= nil then
      log("SELECT_DISARM", "reason=" .. tostring(reason) ..
          " name=" .. selected.Name .. " uid=" .. selected.IdString)
    end
    selectionGeneration = selectionGeneration + 1
    if self ~= nil then self.completionistMapV105SelectedRaven = nil end
  end

  local function clearIcons(self, reason)
    local icons = self.completionistMapV105RavenIcons or {}
    for name, go in pairs(icons) do
      recycle(go)
      if self.mapIconCollision == go then self.mapIconCollision = nil end
      icons[name] = nil
    end
    self.completionistMapV105RavenIcons = icons
    self.completionistMapV105RavenVisibilityKey = nil
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    clearSelection(self, reason)
  end

  -- v0.10.1's pinned map source defines the custom filter contract as:
  --   1    = Show All
  --   -101 = Completionist
  --   -102 = Ravens
  -- The all-Ravens layer must follow that same contract and must never render
  -- collectible pins while the map is opened for Mystic Gateway fast travel.
  local function ravenFilterKind(self)
    if self == nil or type(self.filterButtonMapping) ~= "table" then return 1 end
    local index = tonumber(self.filterIndex) or 1
    return self.filterButtonMapping[index] or 1
  end

  local function ravenMapVisible(self)
    if self == nil or self.isOpenedForFastTravel == true then return false end
    local filter = ravenFilterKind(self)
    return filter == 1 or filter == -101 or filter == -102
  end

  local function ravenVisibilityKey(self)
    return tostring(self and self.currRealmName or "-") .. ":" ..
      tostring(self and self.isOpenedForFastTravel == true) .. ":" ..
      tostring(ravenFilterKind(self))
  end

  local function syncIcons(self, reason)
    if self == nil then return end
    lastMapOnSelf = self
    clearLegacy(self)
    local icons = self.completionistMapV105RavenIcons or {}
    self.completionistMapV105RavenIcons = icons
    local realm = self.currRealmName
    local mapVisible = ravenMapVisible(self)
    local filter = ravenFilterKind(self)
    local visibilityKey = ravenVisibilityKey(self)
    if self.completionistMapV105RavenVisibilityKey ~= visibilityKey then
      self.completionistMapV105RavenVisibilityKey = visibilityKey
      log("MAP_VISIBILITY",
          "reason=" .. tostring(reason) ..
          " realm=" .. tostring(realm) ..
          " fastTravel=" .. tostring(self.isOpenedForFastTravel == true) ..
          " filter=" .. tostring(filter) ..
          " ravensVisible=" .. tostring(mapVisible))
    end

    if not mapVisible then
      clearSelection(self, "raven_map_hidden_by_mode_or_filter")
    end

    for name, go in pairs(icons) do
      local row = byName[name]
      if row == nil or row.Realm ~= realm or isCollected(row.CatalogueId) then
        recycle(go)
        if self.mapIconCollision == go then self.mapIconCollision = nil end
        icons[name] = nil
      else
        pcall(function()
          if mapVisible then go:Show() else go:Hide() end
        end)
      end
    end
    if not mapVisible then return end

    for _, row in ipairs(rows) do
      if row.Realm == realm and shouldShow(row.CatalogueId) and icons[row.Name] == nil then
        local ok, value = pcall(function()
          local info = markerInfo(row.Name)
          if info == nil then return nil, "marker_info" end
          local found, region = Map.FindRegionFromMarker(info.Id)
          if found ~= true or region == nil then return nil, "region" end
          return Map.CreateMarkerIcon(info.Id, region, ""), nil
        end)
        local go = ok and value or nil
        if go ~= nil then
          icons[row.Name] = go
          go:Show()
        else
          log("ICON_CREATE_FAILED", "name=" .. row.Name .. " reason=" .. tostring(reason))
        end
      end
    end
  end

  local previousNextFilter = MapOn.Menu_Next_Filter
  if type(previousNextFilter) == "function" then
    MapOn.Menu_Next_Filter = function(self, ...)
      local result = previousNextFilter(self, ...)
      syncIcons(self, "filter_change")
      return result
    end
  end

  local previousUpdateFilterButtonMapping = MapOn.UpdateFilterButtonMapping
  if type(previousUpdateFilterButtonMapping) == "function" then
    MapOn.UpdateFilterButtonMapping = function(self, ...)
      local result = previousUpdateFilterButtonMapping(self, ...)
      local realmHasRavens = false
      for _, row in ipairs(rows) do
        if row.Realm == self.currRealmName then
          realmHasRavens = true
          break
        end
      end
      if realmHasRavens and type(self.filterButtonMapping) == "table" then
        local hasRavenFilter = false
        for _, logical in ipairs(self.filterButtonMapping) do
          if logical == -102 then
            hasRavenFilter = true
            break
          end
        end
        if not hasRavenFilter then
          self.filterButtonMapping[#self.filterButtonMapping + 1] = -102
          if type(self.UpdateFilterUI) == "function" then self:UpdateFilterUI() end
          log("RAVEN_FILTER_MAPPING",
              "realm=" .. tostring(self.currRealmName) ..
              " added=true logical=-102")
        end
      end
      return result
    end
  end

  local createPins = CompletionistMapV100_CreateMapPin
  CompletionistMapV100_CreateMapPin = function(self, currState)
    lastMapOnSelf = nil
    local refreshed, refreshReason = refreshNativeAuthority("map_create")
    log("NATIVE_AUTHORITY_REFRESH", "source=map_create result=" ..
        (refreshed and "applied" or tostring(refreshReason)) ..
        " lastGeneration=" .. tostring(lastNativeGeneration))
    if not refreshed and not hasAuthoritativeRavenState then
      logRegionSummaryDiagnostics("map_create")
    end
    local result = createPins(self, currState)
    syncIcons(self, "map_create")
    return result
  end

  for _, method in ipairs({"SubmenuExit", "Exit", "ClearIcons"}) do
    local previous = MapOn[method]
    assert(type(previous) == "function", "Missing map lifecycle method: " .. method)
    MapOn[method] = function(self, ...)
      local trackedCatalogueId =
          customCompassOwnsTarget and _G.CompletionistMapV105TrackedCatalogueId or nil
      clearIcons(self, "map_teardown:" .. method)
      local result = previous(self, ...)

      -- The stock map lifecycle may reclaim compass ownership after MapOn.Update
      -- has stopped running. If a custom Raven is still tracked, make the
      -- custom class the final writer and remove only foreign stock targets.
      local row = trackedCatalogueId and byCatalogueId[trackedCatalogueId] or nil
      if row ~= nil and shouldShow(row.CatalogueId) then
        local info = markerInfo(row.Name)
        if info ~= nil then
          suppressLegacyRavenHud()
          pcall(function() game.Compass.ShowMarker(row.Name, ravenClass) end)
          hideStockExcept(tostring(info.Id), "map_teardown_owner_guard")
          suppressLegacyRavenHud()
          self.currShownMarkerID = nil
          log("COMPASS_EXIT_REASSERT",
              "method=" .. method .. " name=" .. row.Name ..
              " uid=" .. tostring(info.Id) ..
              " customClass=" .. ravenClass)
        end
      end

      if lastMapOnSelf == self then lastMapOnSelf = nil end
      return result
    end
  end

  local function collisionSelection(self, collisionTable)
    local icons = self.completionistMapV105RavenIcons or {}
    for _, collision in ipairs(collisionTable or {}) do
      for name, go in pairs(icons) do
        if collision == go then
          local row = byName[name]
          if row ~= nil and shouldShow(row.CatalogueId) then
            local info = markerInfo(name)
            if info ~= nil then
              return {
                Family = "raven", Name = name, CatalogueId = row.CatalogueId,
                Id = info.Id, IdString = tostring(info.Id), ObjectRef = go,
                State = "candidate-custom", Source = "exact_collision_object",
              }
            end
          end
        end
      end
    end
    return nil
  end

  local function captureSelection(self, selected)
    selectionGeneration = selectionGeneration + 1
    selected.Generation = selectionGeneration
    self.completionistMapV105SelectedRaven = selected
    log("SELECT_CANDIDATE", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " source=" .. selected.Source)
  end

  local function currentSelection(self)
    local selected = self and self.completionistMapV105SelectedRaven or nil
    if selected == nil then return nil end
    if not ravenMapVisible(self) then
      clearSelection(self, "raven_map_hidden_by_mode_or_filter")
      return nil
    end
    local icons = self.completionistMapV105RavenIcons or {}
    if selected.Generation ~= selectionGeneration or
        icons[selected.Name] ~= selected.ObjectRef or
        not shouldShow(selected.CatalogueId) then
      clearSelection(self, "candidate_no_longer_exact")
      return nil
    end
    return selected
  end

  local function promptOwned(self, show, selected)
    if show ~= true or selected == nil then return false end
    if self.currMarkerID ~= nil then
      return tostring(self.currMarkerID) == selected.IdString
    end
    return selected.Name == provenName and self.completionistMapV100Selected == true and
      self.completionistMapV100NornirSelected == nil and
      self.completionistMapV100NornirChestSelected == nil
  end

  local function customIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass({ravenClass})
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function stockIds()
    local ok, ids = pcall(function()
      return game.Compass.FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)
    end)
    if not ok then return {}, false, tostring(ids) end
    return ids or {}, true, nil
  end

  local function contains(ids, idString)
    for _, id in ipairs(ids or {}) do
      if tostring(id) == idString then return true end
    end
    return false
  end

  local function hideCustom(exceptIdString, reason)
    local ids, ok, err = customIds()
    if not ok then return false, 0, err end
    local hidden = 0
    for _, id in ipairs(ids) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then
        local target = knownNameForId(id) or id
        local hideOK = pcall(function() game.Compass.HideMarker(target) end)
        if not hideOK then return false, hidden, "hide_failed:" .. tostring(id) end
        hidden = hidden + 1
      end
    end
    return true, hidden, nil
  end

  hideStockExcept = function(exceptIdString, reason)
    local ids, ok, err = stockIds()
    if not ok then return false, 0, err end
    local hidden = 0
    for _, id in ipairs(ids) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then
        local target = knownNameForId(id) or id
        local hideOK = pcall(function() game.Compass.HideMarker(target) end)
        if not hideOK then return false, hidden, "hide_failed:" .. tostring(id) end
        hidden = hidden + 1
      end
    end
    return true, hidden, nil
  end

  local function hideStock(reason)
    return hideStockExcept(nil, reason)
  end

  local function hasOther(ids, exceptIdString)
    for _, id in ipairs(ids or {}) do
      if exceptIdString == nil or tostring(id) ~= exceptIdString then return true end
    end
    return false
  end

  local function actionText(lamsId)
    return "[AdvanceButton] " .. util.GetLAMSMsg(lamsId)
  end

  suppressLegacyRavenHud = function()
    local target = _G.CompletionistMapV100Target
    if target ~= nil and target.type == "Raven" and target.active == true then
      target.active = false
      log("LEGACY_RAVEN_HUD_DISABLED", "reason=custom_raven_compass_owner")
    end
  end

  local function promptText(selected)
    if promptIntent ~= nil and promptIntent.IdString == selected.IdString then
      if promptIntent.State == "tracked" then
        return actionText(lamsConsts.RemoveFromCompass)
      elseif promptIntent.State == "untracked" then
        local ids, customOK = customIds()
        local hasOtherCustom = false
        if customOK then
          for _, id in ipairs(ids) do
            if tostring(id) ~= selected.IdString then
              hasOtherCustom = true
              break
            end
          end
        end
        local stock, stockOK = stockIds()
        if hasOtherCustom or (stockOK and hasOther(stock, selected.IdString)) then
          return actionText(lamsConsts.ReplaceInCompass)
        end
        return actionText(lamsConsts.AddToCompass)
      end
    end
    local ids, ok = customIds()
    if ok and contains(ids, selected.IdString) then
      return actionText(lamsConsts.RemoveFromCompass)
    end
    local stock = stockIds()
    if #ids > 0 or #stock > 0 then
      return actionText(lamsConsts.ReplaceInCompass)
    end
    return actionText(lamsConsts.AddToCompass)
  end

  local function refreshPrompt(self, selected)
    if self == nil or self.menu == nil or selected == nil then return end
    selected = currentSelection(self) or selected
    if not promptOwned(self, true, selected) then return end

    -- v0.10.4's proven footer path temporarily routes the menu's own prompt
    -- query through the exact Raven selection. Without this, the subsequent
    -- UpdateFooterButtonText() redraw can re-query the base map after the
    -- action selection has been consumed and overwrite Remove with Add.
    promptOverride = selected
    local show, text = MapOn.GetShowOnCompassPrompt(self, self.menu)
    if show ~= true then
      promptOverride = nil
      return
    end

    local goMapCursorText = util.GetUiObjByName("MapCursorInfo")
    if goMapCursorText ~= nil then
      goMapCursorText:Show()
      local top = goMapCursorText:FindSingleGOByName("CursorInfo_Top")
      if top ~= nil then
        local handle = util.GetTextHandle(top, "CursorAction_Text")
        if handle ~= nil then
          UI.SetTextIsClickable(handle)
          UI.SetText(handle, text)
        end
        top:Show()
      end
    end
    self.menu:UpdateFooterButton("ShowOnCompass", true, text)
    self.menu:UpdateFooterButtonText()
    promptOverride = nil
    log("PROMPT_REFRESH", "name=" .. selected.Name ..
        " state=" .. tostring(promptIntent and promptIntent.State or "observed") ..
        " text=" .. tostring(text))
  end

  local function showRavenReticle(self, currState, selected)
    if self == nil or currState == nil or selected == nil then return end
    local ok, err = pcall(function()
      self:SetReticleInfo(currState, "Odin's Raven", "Completionist Map")
    end)
    if ok then
      log("RETICLE", "name=" .. selected.Name ..
          " title=Odin's Raven subtitle=Completionist Map")
    else
      log("RETICLE_FAILED", "name=" .. selected.Name .. " error=" .. tostring(err))
    end
  end

  function MapOn:MapCollisionChangeHandler(currState, collisionTable, realmName)
    lastMapOnSelf = self
    local selected = collisionSelection(self, collisionTable)
    if selected ~= nil then captureSelection(self, selected) end
    local result = previousCollision(self, currState, collisionTable, realmName)
    if selected ~= nil and currentSelection(self) ~= nil then
      showRavenReticle(self, currState, selected)
    end
    return result
  end

  function MapOn:GetShowOnCompassPrompt(currMenu)
    lastMapOnSelf = self
    local show, text = previousPrompt(self, currMenu)
    if promptOverride ~= nil then
      return true, promptText(promptOverride)
    end
    local selected = currentSelection(self)
    if selected == nil then return show, text end
    if not promptOwned(self, show, selected) then
      clearSelection(self, "prompt_owner_mismatch")
      return show, text
    end
    selected.State = "armed-custom"
    log("SELECT_ARM", "name=" .. selected.Name .. " uid=" .. selected.IdString)
    return true, promptText(selected)
  end

  function MapOn:ShowOnCompass(currState)
    lastMapOnSelf = self
    local selected = currentSelection(self)
    if selected == nil then
      customCompassOwnsTarget = false
      promptIntent = nil
      local customOK = hideCustom(nil, "other_target_replace")
      if not customOK then return end
      _G.CompletionistMapV105TrackedCatalogueId = nil
      return previousShow(self, currState)
    end
    if selected.State ~= "armed-custom" or not promptOwned(self, true, selected) then
      clearSelection(self, "action_not_exact")
      return
    end
    clearSelection(self, "SELECT_CONSUME")
    if not shouldShow(selected.CatalogueId) then return end
    local ids, queryOK = customIds()
    if not queryOK then return end
    local wantsRemove = contains(ids, selected.IdString)
    if promptIntent ~= nil and promptIntent.IdString == selected.IdString then
      wantsRemove = promptIntent.State == "tracked"
    end
    if wantsRemove then
      customCompassOwnsTarget = true
      local ok = pcall(function() game.Compass.HideMarker(selected.Name) end)
      if ok then
        if _G.CompletionistMapV105TrackedCatalogueId == selected.CatalogueId then
          _G.CompletionistMapV105TrackedCatalogueId = nil
        end
        self.currShownMarkerID = nil
        promptIntent = {
          IdString=selected.IdString, State="untracked",
          Name=selected.Name, CatalogueId=selected.CatalogueId,
        }
        promptSettleFrames = 0
        promptSettleBucket = -1
        suppressLegacyRavenHud()
        hideStock("raven_remove_guard")
        Audio.PlaySound("SND_UX_Pause_Menu_Map_RemoveFromCompass")
        refreshPrompt(self, selected)
        log("REMOVE", "name=" .. selected.Name .. " uid=" .. selected.IdString)
      end
      return
    end
    local customOK, customCount = hideCustom(selected.IdString, "raven_replace")
    local stockOK, stockCount = hideStockExcept(selected.IdString, "raven_replace")
    if not customOK or not stockOK then return end
    suppressLegacyRavenHud()
    local showOK, showErr = pcall(function()
      game.Compass.ShowMarker(selected.Name, ravenClass)
    end)
    if not showOK then
      log("SHOW_FAILED", "name=" .. selected.Name .. " error=" .. tostring(showErr))
      return
    end
    customCompassOwnsTarget = true
    suppressLegacyRavenHud()
    hideStockExcept(selected.IdString, "raven_post_show_guard")
    _G.CompletionistMapV105TrackedCatalogueId = selected.CatalogueId
    self.currShownMarkerID = selected.Id
    promptIntent = {
      IdString=selected.IdString, State="tracked",
      Name=selected.Name, CatalogueId=selected.CatalogueId,
    }
    promptSettleFrames = 0
    promptSettleBucket = -1
    Audio.PlaySound("SND_UX_Pause_Menu_Map_AddToCompass")
    refreshPrompt(self, selected)
    log("SHOW", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
        " replacedCustomCount=" .. tostring(customCount) ..
        " replacedStockCount=" .. tostring(stockCount))
  end

  function MapOn:Update(...)
    local result = previousUpdate(self, ...)

    if self ~= nil and
        self.completionistMapV105RavenVisibilityKey ~= ravenVisibilityKey(self) then
      syncIcons(self, "map_mode_or_filter_change")
    end

    if customCompassOwnsTarget then
      suppressLegacyRavenHud()
      local exceptIdString = promptIntent and promptIntent.IdString or nil
      local trackedRow = byCatalogueId[_G.CompletionistMapV105TrackedCatalogueId]
      if trackedRow ~= nil then
        local trackedInfo = markerInfo(trackedRow.Name)
        if trackedInfo ~= nil then exceptIdString = tostring(trackedInfo.Id) end
      end
      local stock, stockOK = stockIds()
      if stockOK and hasOther(stock, exceptIdString) then
        hideStockExcept(exceptIdString, "custom_raven_owner_guard")
      end
    end

    if nativeResetRecheckFrames > 0 then
      nativeResetRecheckFrames = nativeResetRecheckFrames - 1
      local elapsed = nativeResetRecheckLimit - nativeResetRecheckFrames
      local bucket = math.floor(elapsed / 30)
      if elapsed == 1 or bucket ~= nativeResetRecheckBucket then
        nativeResetRecheckBucket = bucket
        local refreshed, reason = refreshNativeAuthority("post_reset_recheck")
        log("NATIVE_AUTHORITY_RECHECK", "frame=" .. tostring(elapsed) ..
            " result=" .. (refreshed and "applied" or tostring(reason)) ..
            " lastGeneration=" .. tostring(lastNativeGeneration))
      end
      if nativeResetRecheckFrames == 0 then
        nativeResetRecheckBucket = -1
        log("NATIVE_AUTHORITY_RECHECK_DONE",
            "lastGeneration=" .. tostring(lastNativeGeneration))
      end
    end

    if promptIntent == nil then return result end

    local intent = promptIntent
    local row = intent.Name and byName[intent.Name] or nil
    if row == nil or tostring(row.CatalogueId) ~= tostring(intent.CatalogueId) then
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=identity_missing id=" .. tostring(intent.IdString))
      return result
    end

    local info = markerInfo(row.Name)
    if info == nil or tostring(info.Id) ~= intent.IdString then
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=uid_changed name=" .. tostring(row.Name))
      return result
    end

    local selected = {
      Name=row.Name, CatalogueId=row.CatalogueId,
      Id=info.Id, IdString=tostring(info.Id),
    }
    local custom, customOK = customIds()
    local stock, stockOK = stockIds()
    suppressLegacyRavenHud()

    if intent.State == "tracked" then
      if customOK and not contains(custom, intent.IdString) and shouldShow(row.CatalogueId) then
        pcall(function() game.Compass.ShowMarker(row.Name, ravenClass) end)
        suppressLegacyRavenHud()
        custom, customOK = customIds()
        stock, stockOK = stockIds()
      end
      if stockOK and hasOther(stock, intent.IdString) then
        hideStockExcept(intent.IdString, "raven_replace_async_retry")
        stock = stockIds()
      end
      if customOK and contains(custom, intent.IdString) and
          not hasOther(stock, intent.IdString) then
        promptSettleFrames = 0
        promptSettleBucket = -1
        refreshPrompt(self, selected)
        if not intent.Settled then log("PROMPT_SETTLED", "state=tracked name=" .. row.Name) end
        intent.Settled = true
      else
        promptSettleFrames = promptSettleFrames + 1
        refreshPrompt(self, selected)
      end
    elseif intent.State == "untracked" then
      if intent.Settled then
        refreshPrompt(self, selected)
        return result
      end
      promptSettleFrames = promptSettleFrames + 1
      local bucket = math.floor(promptSettleFrames / 30)
      if customOK and contains(custom, intent.IdString) and
          (promptSettleFrames == 1 or bucket ~= promptSettleBucket) then
        promptSettleBucket = bucket
        pcall(function() game.Compass.HideMarker(row.Name) end)
      end
      if stockOK and hasOther(stock, intent.IdString) then
        hideStockExcept(intent.IdString, "raven_remove_async_retry")
      end
      local customAfter, customAfterOK = customIds()
      local stockAfter, stockAfterOK = stockIds()
      if promptSettleFrames >= 3 and customAfterOK and stockAfterOK and
          not contains(customAfter, intent.IdString) and
          not hasOther(stockAfter, intent.IdString) then
        intent.Settled = true
        promptSettleFrames = 0
        promptSettleBucket = -1
        customCompassOwnsTarget = false
        refreshPrompt(self, selected)
        log("PROMPT_SETTLED", "state=untracked name=" .. row.Name)
      else
        refreshPrompt(self, selected)
      end
    else
      promptIntent = nil
      promptSettleFrames = 0
      promptSettleBucket = -1
      log("PROMPT_SETTLE_ABORT", "reason=invalid_state state=" .. tostring(intent.State))
    end
    return result
  end

  local function hideExactTracked(row)
    if _G.CompletionistMapV105TrackedCatalogueId ~= row.CatalogueId then return end
    local info = markerInfo(row.Name)
    if info == nil then return end
    local ids, ok = customIds()
    if ok and contains(ids, tostring(info.Id)) then
      pcall(function() game.Compass.HideMarker(row.Name) end)
    end
    if customCompassOwnsTarget then
      suppressLegacyRavenHud()
      hideStock("tracked_raven_collected")
    end
    _G.CompletionistMapV105TrackedCatalogueId = nil
    customCompassOwnsTarget = false
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    if lastMapOnSelf ~= nil then lastMapOnSelf.currShownMarkerID = nil end
  end

  _G.CompletionistMapV105PublishRavenState = function(catalogueId, collected, source)
    local row = byCatalogueId[catalogueId]
    if row == nil or type(collected) ~= "boolean" then return false end
    if collected ~= true then
      log("STATE_DEFERRED", "catalogueId=" .. catalogueId ..
          " source=" .. tostring(source) ..
          " reason=alive_requires_atomic_authority progressionWrites=false")
      return true
    end
    eventKilled[catalogueId] = true
    states[catalogueId] = true
    hideExactTracked(row)
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "state:" .. tostring(source)) end
    log("STATE", "catalogueId=" .. catalogueId .. " collected=true" ..
        " source=" .. tostring(source) .. " progressionWrites=false")
    return true
  end

  _G.CompletionistMapV105ApplyPersistedRavenKills = function(
      catalogueIds, source, clearEventEvidence)
    if type(catalogueIds) ~= "table" then return false, 0 end

    if clearEventEvidence == true then
      for catalogueId, _ in pairs(eventKilled) do eventKilled[catalogueId] = nil end
    end

    for catalogueId, _ in pairs(states) do states[catalogueId] = nil end
    local accepted = 0
    for key, value in pairs(catalogueIds) do
      local catalogueId = nil
      if type(key) == "number" then
        catalogueId = value
      elseif value == true then
        catalogueId = key
      end
      local row = byCatalogueId[catalogueId]
      if row ~= nil and states[catalogueId] ~= true then
        states[catalogueId] = true
        accepted = accepted + 1
        hideExactTracked(row)
      end
    end

    local eventOverlayCount = 0
    for catalogueId, value in pairs(eventKilled) do
      local row = byCatalogueId[catalogueId]
      if value == true and row ~= nil then
        eventOverlayCount = eventOverlayCount + 1
        states[catalogueId] = true
        hideExactTracked(row)
      end
    end

    hasAuthoritativeRavenState = true
    _G.CompletionistMapV105HasAuthoritativeRavenState = true
    if lastMapOnSelf ~= nil then syncIcons(lastMapOnSelf, "persisted:" .. tostring(source)) end
    log("PERSISTED_KILLS", "source=" .. tostring(source) ..
        " accepted=" .. tostring(accepted) ..
        " eventOverlay=" .. tostring(eventOverlayCount) ..
        " clearEventEvidence=" .. tostring(clearEventEvidence == true) ..
        " authorityEstablished=true catalogueDefaultVisible=false progressionWrites=false")
    return true, accepted
  end

  beginAuthorityBoundary = function(source, captureReady, forcedEpoch)
    if forcedEpoch ~= nil then
      nativeBoundaryEpoch = forcedEpoch
    else
      nativeBoundaryEpoch = nativeBoundaryEpoch + 1
    end
    _G.CompletionistMapV105NativeBoundaryEpoch = nativeBoundaryEpoch
    nativeBoundaryPending = true
    nativeBoundaryCaptureReady = captureReady ~= false
    nativeBoundarySource = tostring(source)
    nativeResetRecheckFrames = nativeResetRecheckLimit
    nativeResetRecheckBucket = -1
    customCompassOwnsTarget = false
    promptIntent = nil
    promptSettleFrames = 0
    promptSettleBucket = -1
    _G.CompletionistMapV105TrackedCatalogueId = nil
    hideCustom(nil, "authority_boundary")
    if lastMapOnSelf ~= nil then
      clearSelection(lastMapOnSelf, "authority_boundary")
      lastMapOnSelf.currShownMarkerID = nil
    end
    log("AUTHORITY_BOUNDARY",
        "source=" .. tostring(source) ..
        " boundaryEpoch=" .. tostring(nativeBoundaryEpoch) ..
        " captureReady=" .. tostring(nativeBoundaryCaptureReady) ..
        " staleStateRetained=true atomicAuthorityRequired=true" ..
        " postBoundaryRecheckFrames=" .. tostring(nativeResetRecheckLimit) ..
        " progressionWrites=false")
    return true
  end

  _G.CompletionistMapV105NotifyAuthorityBoundary = beginAuthorityBoundary
  _G.CompletionistMapV105ResetRavenStates = beginAuthorityBoundary

  local pendingBoundary = rawget(_G, "CompletionistMapV105PendingAuthorityBoundary")
  if pendingBoundary ~= nil then
    _G.CompletionistMapV105PendingAuthorityBoundary = nil
    if type(pendingBoundary) == "table" then
      beginAuthorityBoundary(
          pendingBoundary.source or "pending",
          pendingBoundary.captureReady ~= false)
    else
      beginAuthorityBoundary(pendingBoundary, true)
    end
  end

  if not _G.CompletionistMapV105LoadBoundaryHooksInstalled then
    _G.CompletionistMapV105LoadBoundaryHooksInstalled = true
    local thunkOK, thunk = pcall(require, "core.thunk")
    if thunkOK and type(thunk) == "table" and type(thunk.Install) == "function" then
      local dataOK, dataErr = pcall(thunk.Install, "EVT_LoadSaveData", function(...)
        beginAuthorityBoundary("EVT_LoadSaveData", false)
      end)
      log("LOAD_BOUNDARY_HOOK", "event=EVT_LoadSaveData" ..
          " installed=" .. tostring(dataOK) ..
          (dataOK and "" or " error=" .. tostring(dataErr)))

      local doneOK, doneErr = pcall(thunk.Install, "EVT_LoadSaveFile_Done", function(...)
        beginAuthorityBoundary("EVT_LoadSaveFile_Done", true)
      end)
      log("LOAD_BOUNDARY_HOOK", "event=EVT_LoadSaveFile_Done" ..
          " installed=" .. tostring(doneOK) ..
          (doneOK and "" or " error=" .. tostring(doneErr)))
    else
      log("LOAD_BOUNDARY_HOOK", "installed=false reason=core_thunk_unavailable")
    end
  end

  for catalogueId, value in pairs(_G.CompletionistMapV105PendingRavenState or {}) do
    _G.CompletionistMapV105PublishRavenState(catalogueId, value, "pending")
  end
  _G.CompletionistMapV105PendingRavenState = {}
  log("API", "installed=true catalogueCount=" .. tostring(#rows) ..
      " mapResource=" .. mapResource .. " compassClass=" .. ravenClass ..
      " exactCollisionRequired=true markerIdAloneInfersRaven=false" ..
      " permanentPolling=false postLoadBoundedRefresh=true progressionWrites=false catalogueDefaultVisible=false" ..
      " positiveEventEvidenceOnly=true atomicAuthorityClearsState=true" ..
      " sessionKillOverlay=true loadBoundaryClearsOverlay=true" ..
      " boundaryEpochCapture=true loadDataCaptureReady=false loadDoneCaptureReady=true" ..
      " persistedKillBootstrap=true nativeAuthority=loopback_v2_boundary_capture" ..
      " nativePort=" .. tostring(nativePort) .. " staticDescriptorWrites=false")
end
-- END COMPLETIONIST V0.10.5 ALL RAVENS
