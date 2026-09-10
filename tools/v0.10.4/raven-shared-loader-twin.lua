-- BEGIN COMPLETIONIST SHARED LOADER TWIN PROBE
-- Same resource, new marker UID. No token state or compass writes.
do
  local twinName = "Completionist_V104_Veithurgard_Raven_Twin_01"
  local createRaven = CompletionistMapV100_CreateMapPin
  local destroyRaven = CompletionistMapV100_DestroyMapPin
  local prefix = "[CompletionistMap shared-loader-twin] "

  local function log(text)
    print(prefix .. text)
  end

  local function clearTwin(self)
    local go = self.completionistSharedLoaderTwinGO
    if go ~= nil then
      local ok, err = pcall(function() Map.RecycleIcon(go) end)
      if not ok then
        log("CLEANUP_FAILED error=" .. tostring(err))
        return false
      end
      self.completionistSharedLoaderTwinGO = nil
      log("RECYCLED twin=true")
    end
    return true
  end

  CompletionistMapV100_DestroyMapPin = function(self)
    clearTwin(self)
    return destroyRaven(self)
  end

  CompletionistMapV100_CreateMapPin = function(self, currState)
    local result = createRaven(self, currState)
    if self.currRealmName ~= "Midgard" then return result end
    if self.completionistSharedLoaderTwinGO ~= nil then
      log("SKIP reason=prior_twin_not_recycled")
      return result
    end

    -- The Twin is a separate map marker instance that only shares the Raven visual
    -- resource. Its lifetime must not depend on a live production Raven UI object.
    local original = self.completionistMapV100MapIconGO
    local originalPresent = original ~= nil

    local ok, err = pcall(function()
      local info = Map.GetMarkerInfo(twinName)
      if info == nil or info.Id == nil then
        log("LOOKUP found=false")
        return
      end
      local found, region = Map.FindRegionFromMarker(info.Id)
      log("LOOKUP found=true uid=" .. tostring(info.Id) ..
          " state=" .. tostring(info.State) .. " regionFound=" .. tostring(found) ..
          " region=" .. tostring(region) .. " originalPresent=" .. tostring(originalPresent))
      if found ~= true or region == nil then return end
      local go = Map.CreateMarkerIcon(info.Id, region, "")
      if go == nil then
        log("CREATE success=false reason=nil_object originalPresent=" .. tostring(originalPresent))
        return
      end
      if originalPresent and go == original then
        log("CREATE success=false reason=original_object_reused originalPresent=true")
        return
      end
      self.completionistSharedLoaderTwinGO = go
      go:Show()

      if originalPresent then
        local a, z = original:GetWorldPosition(), go:GetWorldPosition()
        local dx, dy, dz = z.x-a.x, z.y-a.y, z.z-a.z
        log("CREATE success=true distinctObjects=true sharedLoader=goMapIconCompletionistRaven" ..
            " uid=" .. tostring(info.Id) .. " goName=" .. tostring(go:GetName()) ..
            " originalPresent=true originalGO=" .. tostring(original) .. " twinGO=" .. tostring(go) ..
            " originalPos=" .. tostring(a.x) .. "," .. tostring(a.y) .. "," .. tostring(a.z) ..
            " twinPos=" .. tostring(z.x) .. "," .. tostring(z.y) .. "," .. tostring(z.z) ..
            " mapSpaceDistance=" .. tostring(math.sqrt(dx*dx+dy*dy+dz*dz)) ..
            " stateWritten=false compassWritten=false")
      else
        local z = go:GetWorldPosition()
        log("CREATE success=true distinctObjects=not_applicable sharedLoader=goMapIconCompletionistRaven" ..
            " uid=" .. tostring(info.Id) .. " goName=" .. tostring(go:GetName()) ..
            " originalPresent=false twinGO=" .. tostring(go) ..
            " twinPos=" .. tostring(z.x) .. "," .. tostring(z.y) .. "," .. tostring(z.z) ..
            " stateWritten=false compassWritten=false")
      end
    end)
    if not ok then
      log("CREATE success=false error=" .. tostring(err) .. " originalPresent=" .. tostring(originalPresent))
      clearTwin(self)
    end
    return result
  end
  log("API installed=true resource=goMapIconCompletionistRaven expectedPoolCapacity=2 independentTwinLifetime=true")
end
-- END COMPLETIONIST SHARED LOADER TWIN PROBE
