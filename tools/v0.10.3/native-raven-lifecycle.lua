-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE
-- Appended to the already-installed v0.10.1 precisionchallenge override.
-- Reuses the target-Raven position predicate and observational publisher.
-- The only native compass mutation is HideMarker on Completionist's dedicated ID.
do
  local prefix = "[CompletionistMap v0.10.3-native] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local originalPublish = CompletionistMapV100_PublishTargetState

  if type(originalPublish) ~= "function" or
      type(CompletionistMapV100_IsTargetRaven) ~= "function" then
    print(prefix .. "NATIVE_RAVEN_LIFECYCLE installed=false reason=v101_bridge_missing")
  else
    CompletionistMapV100_PublishTargetState = function(killed, source)
      local isTarget = false
      local targetOK, targetValue = pcall(function()
        local matched = CompletionistMapV100_IsTargetRaven()
        return matched == true
      end)
      if targetOK then
        isTarget = targetValue == true
      end

      originalPublish(killed, source)

      if isTarget and killed == true then
        local hideOK, hideErr = pcall(function()
          game.Compass.HideMarker(candidate)
        end)
        _G.CompletionistMapV103NativeRavenTracked = false
        print(prefix .. "NATIVE_RAVEN_LIFECYCLE" ..
          " source=" .. tostring(source) ..
          " collected=true" ..
          " hideOK=" .. tostring(hideOK) ..
          " error=" .. tostring(hideErr))
      end
    end

    print(prefix .. "NATIVE_RAVEN_LIFECYCLE installed=true calls_show=false")
  end
end
-- END COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE
