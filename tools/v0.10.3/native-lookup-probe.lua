-- BEGIN COMPLETIONIST V0.10.3 NATIVE LOOKUP PROBE
-- Read-only lookup. No compass request, marker write, or save write.
do
  local prefix = "[CompletionistMap v0.10.3] "
  local candidate = "Completionist_V103_Veithurgard_Raven_01"
  local original = MapOn.GetRealmMarkerInfo
  assert(type(original) == "function", "v0.10.3: GetRealmMarkerInfo hook missing")

  local function log(category, fields)
    print(prefix .. category .. " " .. fields)
  end

  local function describe(info, source)
    if info == nil then
      log("NATIVE_MARKER_LOOKUP", "source=" .. source .. " registered=false")
      return
    end
    log("NATIVE_MARKER_INFO", "source=" .. source ..
      " id=" .. tostring(info.Id) .. " state=" .. tostring(info.State) ..
      " wad=" .. tostring(info.WadName))
    local p = info.Coordinates
    if p ~= nil then
      log("NATIVE_MARKER_POSITION", "source=" .. source ..
        " x=" .. tostring(p.x) .. " y=" .. tostring(p.y) .. " z=" .. tostring(p.z))
    end
  end

  function MapOn:GetRealmMarkerInfo(...)
    local result = original(self, ...)
    if self.currRealmName ~= "Midgard" or self.completionistV103LookupDone then
      return result
    end
    self.completionistV103LookupDone = true
    local ok, err = pcall(function()
      log("NATIVE_MARKER_LOOKUP", "begin=true target=VeithurgardRaven name=" .. candidate)
      log("NATIVE_MARKER_CREATE", "attempted=false mode=read_only")
      -- Native GetMarkerInfo returns no value for absent ID. ShowMarker never runs.
      describe(game.Map.GetMarkerInfo(candidate), "candidate")
      local seen = {}
      local count = 0
      for _, info in ipairs(self.realmMarkerInfo or {}) do
        local id = tostring(info.Id)
        if not seen[id] and (info.WadName == "WAD_Xpl200_Funeral" or id == "2924516555722838670") then
          seen[id] = true
          count = count + 1
          if count <= 8 then
            describe(info, "stock_baseline")
            log("NATIVE_MARKER_REGION", "id=" .. id .. " region=" .. tostring(info.regionId))
          end
        end
      end
      log("NATIVE_COMPASS_RESULT", "show_attempted=false hide_attempted=false" ..
        " route_verified=false baseline_count=" .. tostring(count))
    end)
    if not ok then
      log("NATIVE_COMPASS_ERROR", "stage=read_only_lookup error=" .. tostring(err))
    end
    return result
  end
  log("NATIVE_MARKER_API", "hook=GetRealmMarkerInfo installed=true mode=read_only")
end
-- END COMPLETIONIST V0.10.3 NATIVE LOOKUP PROBE
