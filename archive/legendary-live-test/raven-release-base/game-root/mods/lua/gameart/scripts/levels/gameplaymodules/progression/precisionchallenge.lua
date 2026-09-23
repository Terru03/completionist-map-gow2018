local LD = require("design.LevelDesignLibrary")
local timers = require("level.timer")
local bIsAnimated, thisObj
local ravenKilled = false
local BirdMesh, OnKilledCallbacks, regionSummaryQuest
-- Completionist Map v0.10.1 Raven lifecycle bridge.
-- Read-only with respect to progression: it only observes the script's own
-- ravenKilled state and publishes it to the custom map/HUD prototype.
local function CompletionistMapV100_IsTargetRaven()
  if thisObj == nil then
    return false, nil
  end

  local posOK, pos = pcall(function()
    return thisObj:GetWorldPosition()
  end)

  if not posOK or pos == nil then
    return false, nil
  end

  local dx = pos.x - (-64.850898742676)
  local dy = pos.y - 12.987384796143
  local dz = pos.z - 787.30694580078
  local distanceSq = dx * dx + dy * dy + dz * dz

  return distanceSq <= 0.25, pos
end

local function CompletionistMapV100_PublishTargetState(killed, source)
  local isTarget, pos = CompletionistMapV100_IsTargetRaven()
  if not isTarget then
    return
  end

  local collected = killed == true
  _G.CompletionistMapV100TargetRavenKilled = collected

  if _G.CompletionistMapV100Target ~= nil and
      _G.CompletionistMapV100Target.type == "Raven" then
    _G.CompletionistMapV100Target.collected = collected
    if collected then
      _G.CompletionistMapV100Target.active = false
    end
  end

  print("[CompletionistMap v0.10.1] RAVEN_STATE" ..
    " target=true" ..
    " source=" .. tostring(source) ..
    " killed=" .. tostring(collected) ..
    " regionQuest=" .. tostring(regionSummaryQuest) ..
    " x=" .. tostring(pos and pos.x or "<nil>") ..
    " y=" .. tostring(pos and pos.y or "<nil>") ..
    " z=" .. tostring(pos and pos.z or "<nil>"))
end
function OnScriptLoaded(level, obj)
  thisObj = obj
  OnKilledCallbacks = thisObj:FindLuaTableAttribute("OnKilledEvent")
  bIsAnimated = thisObj:FindLuaTableAttribute("IsAnimated")
  regionSummaryQuest = thisObj:FindLuaTableAttribute("regionSummaryQuest")
  BirdMesh = thisObj:FindSingleGOByName("BirdMesh")
  SoundInit()
  game.SubObject.Sleep(obj)
end
function OnStart(level, obj)
  CompletionistMapV100_PublishTargetState(ravenKilled, "OnStart")
  if ravenKilled == true then
    HideBird()
    return
  elseif BirdMesh ~= nil then
    BirdMesh:PlayAnimCycle()
    thisObj:PlayAnimCycle()
    SoundOnStart()
  end
end
function OnHitByWeapon(level, obj, attacker, weapon)
  CompletionistMapV100_PublishTargetState(true, "OnHitByWeapon")
  timers.StartLevelTimer(1.5, HideBird())
  local questState = game.QuestManager.GetQuestState("Quest_Labor_KillRavens_Parent")
  if questState == "Inactive" then
    game.QuestManager.StartQuest("Quest_Labor_KillRavens_Parent")
  end
  game.QuestManager.IncrementQuestProgress("Quest_Labor_KillRavens", 1)
  game.QuestManager.IncrementQuestProgress("Quest_Labor_KillRavens_25", 1)
  game.QuestManager.IncrementQuestProgress("Quest_Labor_KillRavens_50", 1)
  if game.QuestManager.GetQuestState("Quest_Labor_KillRavens") == "Complete" then
    game.UnlockTrophy(25)
  end
  ravenKilled = true
  SpawnFX()
  PlayDeathSound()
  OnKilledCallback(level, obj)
  ActivateRegionSummaryQuest()
  timers.StartLevelTimer(1, SoftSave)
end
function OnKilledCallback(level, obj)
  if OnKilledCallbacks ~= nil or OnKilledCallbacks ~= "" then
    LD.ExtractAndExecuteCallbacksForEvent(level, obj, OnKilledCallbacks, "On Killed Event")
  end
end
function ActivateRegionSummaryQuest()
  if regionSummaryQuest ~= nil and regionSummaryQuest ~= "" then
    regionSummaryQuest = string.gsub(regionSummaryQuest, "%s+", "")
    LD.ActivateAndIncrementQuest(regionSummaryQuest)
  end
end
function HideBird()
  thisObj:Hide()
end
function SpawnFX()
  if BirdMesh ~= nil then
    local spawnJoint = BirdMesh:GetJointIndex("synchJoint")
    local spawnJointPos = BirdMesh:GetWorldJointPosition(spawnJoint)
    local deathFX = game.FX.Spawn("Raven_Death_FX", BirdMesh, {AutoDelete = true})
    deathFX:SetWorldPosition(spawnJointPos)
  elseif bIsAnimated ~= nil then
    local spawnJoint = thisObj:GetJointIndex("synchJoint")
    local spawnJointPos = thisObj:GetWorldJointPosition(spawnJoint)
    local deathFX = game.FX.Spawn("Raven_Death_FX", thisObj, {AutoDelete = true})
    deathFX:SetWorldPosition(spawnJointPos)
  else
    local deathFX = game.FX.Spawn("Raven_Death_FX", thisObj, {AutoDelete = true})
    deathFX:SetWorldPosition(thisObj:GetWorldPosition())
  end
end
function SoftSave(level, obj)
  game.SubObject.SoftSave(thisObj)
end
function OnSaveCheckpoint(level, obj)
  return {ravenKilled = ravenKilled}
end
function OnRestoreCheckpoint(level, obj, tab)
  ravenKilled = tab.ravenKilled
  CompletionistMapV100_PublishTargetState(ravenKilled, "OnRestoreCheckpoint")
end
local emitter
function SoundInit()
  print(string.upper(thisObj:GetName()))
  if BirdMesh ~= nil then
    emitter = BirdMesh:FindSingleSoundEmitterByName("SNDRaven")
  else
    emitter = thisObj:FindSingleSoundEmitterByName("SNDRaven")
  end
end
local soundEvents = {
  IdleLoop = "SND_LOOT_Odins_Ravens_Magic_LP",
  Death = "SND_LOOT_Odins_Ravens_Explode"
}
function SoundOnStart()
  LD.CallFunctionAfterDelay(PlayIdleLoop, 0.1)
end
function DisableIdleLoop()
  LD.StopRestartableSoundLoop(emitter, soundEvents.IdleLoop)
end
function PlayIdleLoop()
  LD.PlayRestartableSoundLoop(emitter, soundEvents.IdleLoop)
end
function PlayDeathSound()
  LD.PlaySound(emitter, soundEvents.Death)
  LD.StopRestartableSoundLoop(emitter, soundEvents.IdleLoop)
end

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
    local scheduleOK, scheduleErr = pcall(function()
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
    end)
    if not scheduleOK then
      log("SCHEDULE_FAILED", "source=" .. tostring(source) ..
          " attempt=" .. tostring(attempt) .. " error=" .. tostring(scheduleErr))
    end
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
    {CatalogueId="raven_95b9c6444d479ac68207b1829d02909b",Name="Completionist_V105_Raven_95b9c6444d479ac6",ParentQuest="RegionSummary_ALF_Raven_Parent",X=355.902670263393,Y=-13.4251546010282,Z=150.087953932125},
    {CatalogueId="raven_63f2a1a74274de6df3962490fb6552e9",Name="Completionist_V105_Raven_63f2a1a74274de6d",ParentQuest="RegionSummary_ALF_Raven_Parent",X=330.212471220837,Y=9.57608189725386,Z=298.500278896071},
    {CatalogueId="raven_a824e12946c803e8511da79bc52a193f",Name="Completionist_V105_Raven_a824e12946c803e8",ParentQuest="RegionSummary_HEL_Raven_Parent",X=100.37760925293,Y=13.2656946182251,Z=50.1039047241211},
    {CatalogueId="raven_2811daa04ce30f079ff758b3bf04369d",Name="Completionist_V105_Raven_2811daa04ce30f07",ParentQuest="RegionSummary_HEL_Raven_Parent",X=356.888793945312,Y=-4.4595308303833,Z=31.5798797607422},
    {CatalogueId="raven_595d8539488753c54fa471a46631e8c7",Name="Completionist_V105_Raven_595d8539488753c5",ParentQuest="RegionSummary_HEL_Raven_Parent",X=321.863159179688,Y=13.952938079834,Z=79.7303237915039},
    {CatalogueId="raven_69a8e9f3434cd84b48c7c688094ed2e4",Name="Completionist_V105_Raven_69a8e9f3434cd84b",ParentQuest="RegionSummary_HEL_Raven_Parent",X=349.126617431641,Y=13.6133966445923,Z=12.3349018096924},
    {CatalogueId="raven_7ffab2af4d6e2c7e7a9d42a58943bdf1",Name="Completionist_V105_Raven_7ffab2af4d6e2c7e",ParentQuest="RegionSummary_HEL_Raven_Parent",X=314.640655517578,Y=-27.4914531707764,Z=58.8981285095215},
    {CatalogueId="raven_b13e52024ecc5909d1fe478ee2c54e8c",Name="Completionist_V105_Raven_b13e52024ecc5909",ParentQuest="RegionSummary_HEL_Raven_Parent",X=346.504669189453,Y=-2.00611925125122,Z=-74.6015243530273},
    {CatalogueId="raven_7ffe9f6e4e18734cebadc892d24801e4",Name="Completionist_V105_Raven_7ffe9f6e4e18734c",ParentQuest="RegionSummary_BC_Raven_Parent",X=130.001189981692,Y=0.936963081359863,Z=-141.655430069183},
    {CatalogueId="raven_bc9c2cea4b7e1feaf09bb58f1b691035",Name="Completionist_V105_Raven_bc9c2cea4b7e1fea",ParentQuest="RegionSummary_BC_Raven_Parent",X=63.2450691865632,Y=7.60876417160034,Z=-191.514320076015},
    {CatalogueId="raven_2b86b2ad4f6c006d5f6db0af57a190a4",Name="Completionist_V105_Raven_2b86b2ad4f6c006d",ParentQuest="RegionSummary_BM_Raven_Parent",X=-178.000001018187,Y=1.7838077545166,Z=303.99999980491},
    {CatalogueId="raven_73ac895445d967756cbf34ac591ac205",Name="Completionist_V105_Raven_73ac895445d96775",ParentQuest="RegionSummary_BSW_Raven_Parent",X=-258.990280144897,Y=5.33059692382812,Z=-285.298244761827},
    {CatalogueId="raven_11d083554dd320d5e23ccca24f339acd",Name="Completionist_V105_Raven_11d083554dd320d5",ParentQuest="RegionSummary_BT_Raven_Parent",X=-247.521129680852,Y=15.334071401711,Z=174.190121041686},
    {CatalogueId="raven_ef8568004bd6283b79b4819bb3e5cb0f",Name="Completionist_V105_Raven_ef8568004bd6283b",ParentQuest="RegionSummary_BW_Raven_Parent",X=112.027648567456,Y=14.0519285202026,Z=355.299636271641},
    {CatalogueId="raven_4b8990ee4053cd00d13299928da1a9fc",Name="Completionist_V105_Raven_4b8990ee4053cd00",ParentQuest="RegionSummary_CALS_Raven_Parent",X=-250.723768859096,Y=-3.53147229364686,Z=-89.2099558240422},
    {CatalogueId="raven_df5a6f7543fa157f4cd630a19c038deb",Name="Completionist_V105_Raven_df5a6f7543fa157f",ParentQuest="RegionSummary_CALS_Raven_Parent",X=294.915357133406,Y=-8.76826047897339,Z=-174.666727587869},
    {CatalogueId="raven_e4d9b53e4e0330fc07421d8fea348f1d",Name="Completionist_V105_Raven_e4d9b53e4e0330fc",ParentQuest="RegionSummary_FOOT_Raven_Parent",X=-482.668668137819,Y=11.7049910724163,Z=246.15424006169},
    {CatalogueId="raven_2862a927444bf9df95a605b6a1cfec2b",Name="Completionist_V105_Raven_2862a927444bf9df",ParentQuest="RegionSummary_FOOT_Raven_Parent",X=-364.428009033203,Y=60.9643630981445,Z=378.847961425781},
    {CatalogueId="raven_528d332048f734d84b2f8ca26b3abafc",Name="Completionist_V105_Raven_528d332048f734d8",ParentQuest="RegionSummary_FOR_Raven_Parent",X=-207.533752441406,Y=27.4933643341064,Z=-891.698852539063},
    {CatalogueId="raven_3f0baac6405889c7478896801b6a637c",Name="Completionist_V105_Raven_3f0baac6405889c7",ParentQuest="RegionSummary_FD_Raven_Parent",X=10.2952669007519,Y=14.497296333313,Z=-585.053234791918},
    {CatalogueId="raven_ad56521740c745076417e99ddf1dd7a4",Name="Completionist_V105_Raven_ad56521740c74507",ParentQuest="RegionSummary_FD_Raven_Parent",X=55.46050852298,Y=12.5715627670288,Z=-560.252033876615},
    {CatalogueId="raven_b5ec8398449f573b8a70b7a4fb1154af",Name="Completionist_V105_Raven_b5ec8398449f573b",ParentQuest="RegionSummary_FD_Raven_Parent",X=78.1437570857584,Y=-0.150186061859131,Z=-512.011643855323},
    {CatalogueId="raven_14a87a63401390815b4e4ab2b4e619d0",Name="Completionist_V105_Raven_14a87a6340139081",ParentQuest="RegionSummary_FD_Raven_Parent",X=68.9712214782494,Y=7.0696337223053,Z=-385.6933954276},
    {CatalogueId="raven_97b753a94e069b45a5e031b81a5b9f91",Name="Completionist_V105_Raven_97b753a94e069b45",ParentQuest="RegionSummary_FD_Raven_Parent",X=70.7724436862145,Y=7.99884366989136,Z=-452.414581433755},
    {CatalogueId="raven_09c20f1b44476543307d8d8a444401f7",Name="Completionist_V105_Raven_09c20f1b44476543",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=213.200271606445,Y=-19.5986442565918,Z=-465.167449951172},
    {CatalogueId="raven_93bb416243c6d7afd0dadf824507fcb6",Name="Completionist_V105_Raven_93bb416243c6d7af",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=299.866455078125,Y=-29.7612724304199,Z=-386.324096679688},
    {CatalogueId="raven_b65148ce40189997a7ee6abb05551d95",Name="Completionist_V105_Raven_b65148ce40189997",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=395.121004104614,Y=-45.5068912506104,Z=-352.832214355469},
    {CatalogueId="raven_4f3ed8604f52329654cb89a77cb7b227",Name="Completionist_V105_Raven_4f3ed8604f523296",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=352.256092071533,Y=-30.1093330383301,Z=-475.425933837891},
    {CatalogueId="raven_ce4340a84992a449844e0394671c59eb",Name="Completionist_V105_Raven_ce4340a84992a449",ParentQuest="RegionSummary_HTTK_Raven_Parent",X=432.142700195312,Y=-45.9899129867554,Z=-479.911163330078},
    {CatalogueId="raven_0b07c75f438ce0cfe8b6feb7731ffc9c",Name="Completionist_V105_Raven_0b07c75f438ce0cf",ParentQuest="RegionSummary_HM01_Raven_Parent",X=-234.014747619629,Y=7.71115684509277,Z=430.845436096191},
    {CatalogueId="raven_d869e60744104a9e8865428d5fc2f63a",Name="Completionist_V105_Raven_d869e60744104a9e",ParentQuest="RegionSummary_HM02_Raven_Parent",X=-484.709909439087,Y=-18.9620180130005,Z=-81.9476470947266},
    {CatalogueId="raven_349cc1eb4752a6149cf89f9f94644092",Name="Completionist_V105_Raven_349cc1eb4752a614",ParentQuest="RegionSummary_HM02_Raven_Parent",X=-499.053089618683,Y=-8.97603130340576,Z=-174.698647499084},
    {CatalogueId="raven_7ea7fe24483df9d884fd4790840bf692",Name="Completionist_V105_Raven_7ea7fe24483df9d8",ParentQuest="RegionSummary_HSH_Raven_Parent",X=742.055877685547,Y=-4.87457370758057,Z=-261.06355381012},
    {CatalogueId="raven_e01f95a84dd1e99dde0952856855399d",Name="Completionist_V105_Raven_e01f95a84dd1e99d",ParentQuest="RegionSummary_HSH_Raven_Parent",X=613.454071044922,Y=-14.4896502494812,Z=-131.025337219238},
    {CatalogueId="raven_9deba5114d8045898dafc5be9add793b",Name="Completionist_V105_Raven_9deba5114d804589",ParentQuest="RegionSummary_ISA_Raven_Parent",X=99.3590496837271,Y=-8.7858304977417,Z=278.658577850248},
    {CatalogueId="raven_62fbf37c443c70aeca40ac840f6084b1",Name="Completionist_V105_Raven_62fbf37c443c70ae",ParentQuest="RegionSummary_ISW_Raven_Parent",X=-195.024169302108,Y=-19.6607341372529,Z=-199.392995631803},
    {CatalogueId="raven_fa8d596f445ba456bc5b11905aa4af07",Name="Completionist_V105_Raven_fa8d596f445ba456",ParentQuest="RegionSummary_MT_Raven_Parent",X=176.968307495117,Y=3.7605185508728,Z=163.654830932617},
    {CatalogueId="raven_4532135740478ac108377e8b1c51a501",Name="Completionist_V105_Raven_4532135740478ac1",ParentQuest="RegionSummary_PP_Raven_Parent",X=-456.389038085938,Y=100.450210571289,Z=616.507263183594},
    {CatalogueId="raven_fb1ebb004216311e237c36b23a10707b",Name="Completionist_V105_Raven_fb1ebb004216311e",ParentQuest="RegionSummary_PP_Raven_Parent",X=-477.010528564453,Y=115.406867980957,Z=894.953552246094},
    {CatalogueId="raven_b88e14b5413082e98c4d9cadcbf6ad10",Name="Completionist_V105_Raven_b88e14b5413082e9",ParentQuest="RegionSummary_PP_Raven_Parent",X=-278.19970703125,Y=142.471649169922,Z=781.201049804688},
    {CatalogueId="raven_5a498384495d58916e944883eb2c90bb",Name="Completionist_V105_Raven_5a498384495d5891",ParentQuest="RegionSummary_PP_Raven_Parent",X=-336.435485839844,Y=140.173431396484,Z=856.341857910156},
    {CatalogueId="raven_100bb5c44d6b69eba68eb895d005f956",Name="Completionist_V105_Raven_100bb5c44d6b69eb",ParentQuest="RegionSummary_RP_Raven_Parent",X=-242.808197021484,Y=92.5402984619141,Z=-455.935913085938},
    {CatalogueId="raven_d9db91914694cfe73fa5b9abb208d25d",Name="Completionist_V105_Raven_d9db91914694cfe7",ParentQuest="RegionSummary_RP_Raven_Parent",X=-273.784545898438,Y=89.4121856689453,Z=-547.946472167969},
    {CatalogueId="raven_97e41c48491b177e804019a649735e58",Name="Completionist_V105_Raven_97e41c48491b177e",ParentQuest="RegionSummary_RP_Raven_Parent",X=-358.776885986328,Y=108.650001525879,Z=-393.233367919922},
    {CatalogueId="raven_ccbc62d64eb0f79bbf76e9a08401a137",Name="Completionist_V105_Raven_ccbc62d64eb0f79b",ParentQuest="RegionSummary_RP_Raven_Parent",X=-346.471710205078,Y=99.9208984375,Z=-328.121917724609},
    {CatalogueId="raven_f8fdd3a4438c9697f8aa308323b2465e",Name="Completionist_V105_Raven_f8fdd3a4438c9697",ParentQuest="RegionSummary_RP_Raven_Parent",X=-383.799987792969,Y=75.8000030517578,Z=-276.899993896484},
    {CatalogueId="raven_ac45261c43ee745cd2e20a9cf61a817d",Name="Completionist_V105_Raven_ac45261c43ee745c",ParentQuest="RegionSummary_RP_Raven_Parent",X=-405.134735107422,Y=69.8000030517578,Z=0.886073529720306},
    {CatalogueId="raven_5a652cfb4af86af517b33c8676dbbfc5",Name="Completionist_V105_Raven_5a652cfb4af86af5",ParentQuest="RegionSummary_RP_Raven_Parent",X=-503.480834960938,Y=25.3998031616211,Z=145.937606811523},
    {CatalogueId="raven_8ca357c445d32c015159d6b93e173686",Name="Completionist_V105_Raven_8ca357c445d32c01",ParentQuest="RegionSummary_SM_Raven_Parent",X=456.662017822266,Y=-2.57212233543396,Z=133.628570556641},
    {CatalogueId="raven_a70cd386408985c8bedbc98a7aaed456",Name="Completionist_V105_Raven_a70cd386408985c8",ParentQuest="RegionSummary_SM_Raven_Parent",X=574.245178222656,Y=-34.8896942138672,Z=151.699478149414},
    {CatalogueId="raven_642d0d164af0a5d4076e77933c549a5d",Name="Completionist_V103_Veithurgard_Raven_01",ParentQuest="RegionSummary_VF_Raven_Parent",X=-64.8508987426758,Y=12.9873847961426,Z=787.306938171387},
    {CatalogueId="raven_c945cb53465b58decfcbd4a221cb5326",Name="Completionist_V105_Raven_c945cb53465b58de",ParentQuest="RegionSummary_VF_Raven_Parent",X=122.604850769043,Y=17.3742713928223,Z=679.211616516113},
    {CatalogueId="raven_e32f7bab42fd7298890f6aa56a734562",Name="Completionist_V105_Raven_e32f7bab42fd7298",ParentQuest="RegionSummary_VF_Raven_Parent",X=-127.960754394531,Y=15.5776290893555,Z=690.075782775879},
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
