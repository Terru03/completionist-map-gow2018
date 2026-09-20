-- Completionist Map v0.10.5 - early save/load event argument probe.
-- Read-only: observes event arguments only.
if not _G.CompletionistMapV105SaveLoadEventProbeInstalled then
  _G.CompletionistMapV105SaveLoadEventProbeInstalled = true

  local prefix = "[CompletionistSaveLoadEventProbe] "
  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function log(message)
    print(prefix .. message)
  end

  local function describeScalar(value)
    local kind = type(value)
    if kind == "string" then
      local clipped = value
      if #clipped > 512 then clipped = string.sub(clipped, 1, 512) .. "..." end
      return "type=string value=" .. clipped
    end
    return "type=" .. kind .. " value=" .. safeToString(value)
  end

  local function describeTable(label, value)
    local rows = {}
    local ok, err = pcall(function()
      local count = 0
      for key, member in pairs(value) do
        count = count + 1
        if count > 96 then
          rows[#rows + 1] = "<truncated>"
          break
        end
        local keyText = safeToString(key)
        local memberType = type(member)
        local memberText
        if memberType == "table" then
          memberText = "<table>"
        elseif memberType == "string" then
          memberText = member
          if #memberText > 256 then memberText = string.sub(memberText, 1, 256) .. "..." end
        else
          memberText = safeToString(member)
        end
        rows[#rows + 1] = keyText .. ":" .. memberType .. "=" .. memberText
      end
    end)
    table.sort(rows)
    log(label .. " tableOk=" .. tostring(ok) ..
        " entries=" .. table.concat(rows, "|") ..
        (ok and "" or " error=" .. safeToString(err)))
  end

  local function recordEvent(eventName, ...)
    local argc = select("#", ...)
    log("EVENT name=" .. eventName .. " argc=" .. tostring(argc))
    for index = 1, argc do
      local value = select(index, ...)
      local kind = type(value)
      log("ARG event=" .. eventName .. " index=" .. tostring(index) .. " " .. describeScalar(value))
      if kind == "table" then
        describeTable("TABLE event=" .. eventName .. " index=" .. tostring(index), value)
      end
    end
  end

  local okThunk, thunk = pcall(require, "core.thunk")
  log("THUNK requireOk=" .. tostring(okThunk) .. " type=" .. type(thunk))
  if okThunk and type(thunk) == "table" and type(thunk.Install) == "function" then
    for _, name in ipairs({
      "EVT_LoadSaveData",
      "EVT_LoadSaveFile_Done",
      "EVT_AutoSave",
      "EVT_ManualSaveComplete",
    }) do
      local eventName = name
      local ok, err = pcall(thunk.Install, eventName, function(...)
        recordEvent(eventName, ...)
      end)
      log("HOOK name=" .. eventName .. " installed=" .. tostring(ok) ..
          (ok and "" or " error=" .. safeToString(err)))
    end
  else
    log("HOOKS unavailable=true")
  end

  log("INSTALLED readOnly=true saveWrites=false progressionWrites=false")
end
