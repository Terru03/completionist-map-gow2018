-- Completionist Map helper snippet injected into pristine core.pickle.lua
-- The runner substitutes the exported Unpickle function with this wrapper.
local CompletionistOriginalUnpickle = unpickle

local function CompletionistSafeToString(value)
  local ok, text = pcall(tostring, value)
  if ok then return text end
  return "<tostring-error>"
end

local function CompletionistSafe(label, fn)
  local ok, value = pcall(fn)
  if ok then
    return label .. "=" .. CompletionistSafeToString(value)
  end
  return label .. "=<error:" .. CompletionistSafeToString(value) .. ">"
end

local function CompletionistDumpObject(object, savedInfo, index)
  local killed = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
  if type(killed) ~= "boolean" then return false end

  local fields = {
    "index=" .. tostring(index),
    "ravenKilled=" .. tostring(killed),
    "objectType=" .. type(object),
    "object=" .. CompletionistSafeToString(object),
    CompletionistSafe("GetName", function() return object:GetName() end),
    CompletionistSafe("GetDebugName", function() return object:GetDebugName() end),
    CompletionistSafe("GetDebugPath", function() return object:GetDebugPath() end),
    CompletionistSafe("Level", function() return object.Level end),
    CompletionistSafe("DebugMarkerIDs", function() return object.DebugMarkerIDs end),
    CompletionistSafe("LuaObjectScript", function() return object.LuaObjectScript end),
    CompletionistSafe("LevelObjectScript", function() return object.LevelObjectScript end),
    CompletionistSafe("IsRefNode", function() return object.IsRefNode end),
    CompletionistSafe("Parent", function() return object.Parent end),
    CompletionistSafe("Owner", function() return object.Owner end),
    CompletionistSafe("Transform", function() return object.Transform end),
    CompletionistSafe("Position", function() return object.Position end),
    CompletionistSafe("WorldPosition", function() return object.WorldPosition end),
    CompletionistSafe("Handle", function() return object.Handle end),
    CompletionistSafe("ID", function() return object.ID end),
    CompletionistSafe("UID", function() return object.UID end),
    CompletionistSafe("Guid", function() return object.Guid end),
    CompletionistSafe("GUID", function() return object.GUID end),
    CompletionistSafe("ObjectKey", function() return object.ObjectKey end),
  }

  if type(debug) == "table" and type(debug.getmetatable) == "function" then
    local ok, mt = pcall(debug.getmetatable, object)
    fields[#fields + 1] = "metatableOk=" .. tostring(ok)
    if ok and type(mt) == "table" then
      fields[#fields + 1] = "meta=" .. CompletionistSafeToString(mt)
      fields[#fields + 1] = "metaIdentity=" .. CompletionistSafeToString(rawget(mt, "__identity"))
      local indexer = rawget(mt, "__index")
      fields[#fields + 1] = "metaIndexType=" .. type(indexer)
      if type(indexer) == "function" then
        for _, key in ipairs({
          "__identity","ObjectKey","ID","UID","Guid","GUID","Handle","Position","WorldPosition",
          "DebugMarkerIDs","GetDebugPath","Level"
        }) do
          fields[#fields + 1] = CompletionistSafe("metaIndex[" .. key .. "]", function()
            return indexer(object, key)
          end)
        end
      end
    end
  end

  print("[CompletionistSoftPickleProbe] RAVEN " .. table.concat(fields, " "))
  return true
end

local function CompletionistInspectRoot(root, phase, softMatch, normalMatch)
  local rootType = type(root)
  local subobjects = rootType == "table" and rawget(root, "__subobjs") or nil
  local total = 0
  local ravens = 0
  local killed = 0
  local alive = 0

  if type(subobjects) == "table" then
    local ok, err = pcall(function()
      for object, savedInfo in pairs(subobjects) do
        total = total + 1
        local rk = type(savedInfo) == "table" and rawget(savedInfo, "ravenKilled") or nil
        if type(rk) == "boolean" then
          ravens = ravens + 1
          if rk then killed = killed + 1 else alive = alive + 1 end
          CompletionistDumpObject(object, savedInfo, ravens)
        end
      end
    end)
    if not ok then
      print("[CompletionistSoftPickleProbe] SCAN_ERROR phase=" .. phase .. " error=" .. CompletionistSafeToString(err))
    end
  end

  print("[CompletionistSoftPickleProbe] ROOT phase=" .. phase ..
    " rootType=" .. rootType ..
    " softMatch=" .. tostring(softMatch) ..
    " normalMatch=" .. tostring(normalMatch) ..
    " subobjectsType=" .. type(subobjects) ..
    " subobjectsTotal=" .. tostring(total) ..
    " ravenRecords=" .. tostring(ravens) ..
    " ravenKilledTrue=" .. tostring(killed) ..
    " ravenKilledFalse=" .. tostring(alive) ..
    " readOnly=true saveWrites=false progressionWrites=false")
end

local function CompletionistProbeUnpickle(P, root)
  local softBefore = rawequal(root, rawget(_G, "__SoftPickleTable"))
  local normalBefore = rawequal(root, rawget(_G, "__PickleTable"))
  print("[CompletionistSoftPickleProbe] UNPICKLE_BEGIN root=" .. CompletionistSafeToString(root) ..
    " softMatch=" .. tostring(softBefore) .. " normalMatch=" .. tostring(normalBefore))

  local result = CompletionistOriginalUnpickle(P, root)

  local softAfter = rawequal(root, rawget(_G, "__SoftPickleTable"))
  local normalAfter = rawequal(root, rawget(_G, "__PickleTable"))
  CompletionistInspectRoot(root, "after", softAfter, normalAfter)
  print("[CompletionistSoftPickleProbe] UNPICKLE_END root=" .. CompletionistSafeToString(root) ..
    " softMatch=" .. tostring(softAfter) .. " normalMatch=" .. tostring(normalAfter))
  return result
end
