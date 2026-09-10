-- BEGIN COMPLETIONIST V0.10.4 RAVEN LIFECYCLE V3 EVENTS
-- Read native Raven state after native callback. No save or quest writes.
do
  local generation = 0
  local function notify(source, attempt, ticket)
    if ticket ~= nil and ticket ~= generation then return end
    if attempt == nil then
      generation = generation + 1
      ticket, attempt = generation, 0
    end
    local target = CompletionistMapV100_IsTargetRaven()
    if not target then return end
    local observer = _G.CompletionistMapV104ObserveRavenCompletion
    if type(observer) ~= "function" then return end
    local ok, observed, retry = pcall(observer, source, ravenKilled == true)
    if not ok then
      print("[CompletionistMap uid-lifecycle-v3] OBSERVER_FAILED source=" .. source ..
        " error=" .. tostring(observed))
    end
    if (not ok or retry) and ravenKilled == true then
      if attempt < 20 then
        timers.StartLevelTimer(0.1, function()
          notify(source, attempt + 1, ticket)
        end)
      else
        print("[CompletionistMap uid-lifecycle-v3] CLEANUP_UNSETTLED attempts=20")
      end
    end
  end

  local hit = OnHitByWeapon
  function OnHitByWeapon(...)
    local result = hit(...)
    notify("OnHitByWeapon")
    return result
  end
  local restore = OnRestoreCheckpoint
  function OnRestoreCheckpoint(...)
    local result = restore(...)
    notify("OnRestoreCheckpoint")
    return result
  end
  local start = OnStart
  function OnStart(...)
    local result = start(...)
    notify("OnStart")
    return result
  end
end
-- END COMPLETIONIST V0.10.4 RAVEN LIFECYCLE V3 EVENTS
