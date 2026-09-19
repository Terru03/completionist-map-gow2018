-- BEGIN COMPLETIONIST SUBOBJECT API INVENTORY PROBE
-- Read-only runtime inventory of game.SubObject. No function is invoked.
do
  local prefix = "[CompletionistSubObjectApiProbe] "
  local function log(msg) print(prefix .. msg) end
  local sub = type(game) == "table" and game.SubObject or nil
  log("RUN gameType=" .. type(game) .. " subObjectType=" .. type(sub) ..
      " readOnly=true saveWrites=false progressionWrites=false")
  if type(sub) == "table" then
    local rows = {}
    local ok, err = pcall(function()
      for k, v in pairs(sub) do
        rows[#rows + 1] = {k=tostring(k), t=type(v), v=tostring(v)}
      end
    end)
    if not ok then
      log("ENUM ok=false error=" .. tostring(err))
    else
      table.sort(rows, function(a,b) return a.k < b.k end)
      log("ENUM ok=true count=" .. tostring(#rows))
      for _, row in ipairs(rows) do
        log("MEMBER name=" .. row.k .. " type=" .. row.t .. " value=" .. row.v)
      end
    end
  else
    local candidates = {
      "GetSaveState","GetSavedState","GetSoftSave","GetSoftSaveState","PeekSoftSave",
      "GetCheckpointState","GetRestoreState","GetSavedInfo","Restore","SoftRestore",
      "FindSavedState","GetSubObjectState","GetState","GetPickleTable","GetSavedSubObjects"
    }
    for _, name in ipairs(candidates) do
      local ok, value = pcall(function() return sub and sub[name] or nil end)
      log("CANDIDATE name=" .. name .. " ok=" .. tostring(ok) ..
          " type=" .. type(value) .. " value=" .. tostring(value))
    end
  end
  log("DONE readOnly=true saveWrites=false progressionWrites=false")
end
-- END COMPLETIONIST SUBOBJECT API INVENTORY PROBE
