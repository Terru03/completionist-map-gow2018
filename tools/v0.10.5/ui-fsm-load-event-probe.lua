-- Completionist Map v0.10.5 - UI FSM load-event logger helper.
-- Read-only helper. The capture runner injects one call into ui/fsm.lua::HandleEvent.
if not _G.CompletionistMapV105UIEventProbe then
  local prefix = "[CompletionistUIEventProbe] "
  local targets = {
    EVT_LoadSaveData = true,
    EVT_LoadSaveFile_Done = true,
    EVT_AutoSave = true,
    EVT_ManualSaveComplete = true,
  }

  local function safeToString(value)
    local ok, text = pcall(tostring, value)
    if ok then return text end
    return "<tostring-error>"
  end

  local function oneLine(value, limit)
    local text = safeToString(value):gsub("[\r\n]+", " ")
    if #text > limit then text = string.sub(text, 1, limit) .. "..." end
    return text
  end

  local function targetName(name)
    if targets[name] then return name end
    local events = rawget(_G, "EngineEvents")
    if type(events) == "table" then
      local numeric = tonumber(name)
      if numeric ~= nil then
        for eventName in pairs(targets) do
          if events[eventName] == numeric then return eventName end
        end
      end
    end
    return nil
  end

  local function describeTable(eventName, index, value)
    local rows = {}
    local ok, err = pcall(function()
      local count = 0
      for key, member in pairs(value) do
        count = count + 1
        if count > 128 then
          rows[#rows + 1] = "<truncated>"
          break
        end
        local mt = type(member)
        local rendered = mt == "table" and "<table>" or oneLine(member, 320)
        rows[#rows + 1] = oneLine(key, 160) .. ":" .. mt .. "=" .. rendered
      end
    end)
    table.sort(rows)
    print(prefix .. "TABLE event=" .. eventName .. " index=" .. tostring(index) ..
      " ok=" .. tostring(ok) .. " entries=" .. table.concat(rows, "|") ..
      (ok and "" or " error=" .. oneLine(err, 320)))
  end

  _G.CompletionistMapV105UIEventProbe = function(name, ...)
    local eventName = targetName(name)
    if not eventName then return end
    local argc = select("#", ...)
    print(prefix .. "EVENT rawName=" .. oneLine(name, 160) ..
      " resolvedName=" .. eventName .. " argc=" .. tostring(argc))
    for index = 1, argc do
      local value = select(index, ...)
      local kind = type(value)
      print(prefix .. "ARG event=" .. eventName .. " index=" .. tostring(index) ..
        " type=" .. kind .. " value=" .. oneLine(value, 512))
      if kind == "table" then
        describeTable(eventName, index, value)
      end
    end
  end

  print(prefix .. "HELPER installed=true readOnly=true")
end
