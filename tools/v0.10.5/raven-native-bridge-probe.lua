-- BEGIN COMPLETIONIST V0.10.5 RAVEN NATIVE BRIDGE PROBE
do
  local prefix = "[CompletionistRavenNativeBridgeProbe] "
  local paths = {
    ".\\mods\\completionist_map\\completionist_raven_authority_probe.dll",
    "mods\\completionist_map\\completionist_raven_authority_probe.dll",
  }

  local function log(message)
    print(prefix .. message)
  end

  local function loadSymbol(symbol)
    if type(package) ~= "table" or type(package.loadlib) ~= "function" then
      return nil, nil, "package.loadlib_unavailable"
    end
    local errors = {}
    for _, path in ipairs(paths) do
      local ok, fn, err = pcall(package.loadlib, path, symbol)
      if ok and type(fn) == "function" then
        return fn, path, nil
      end
      errors[#errors + 1] = path .. ":" .. tostring(ok and err or fn)
    end
    return nil, nil, table.concat(errors, " | ")
  end

  local function callChunk(fn, expectedCount, offset)
    local packed = {pcall(fn)}
    if packed[1] ~= true then
      return nil, "pcall_failed:" .. tostring(packed[2])
    end
    if packed[2] ~= true then
      return nil, "native_success_flag_false"
    end
    if #packed ~= expectedCount + 2 then
      return nil, "result_count:" .. tostring(#packed - 2) .. ":expected:" .. tostring(expectedCount)
    end
    local values = {}
    for i = 1, expectedCount do
      local value = packed[i + 2]
      if type(value) ~= "boolean" then
        return nil, "non_boolean:" .. tostring(i) .. ":" .. type(value)
      end
      local expected = ((offset + i - 1) % 2) == 0
      if value ~= expected then
        return nil, "pattern_mismatch:" .. tostring(offset + i) ..
          ":got:" .. tostring(value) .. ":expected:" .. tostring(expected)
      end
      values[#values + 1] = value and "1" or "0"
    end
    return table.concat(values), nil
  end

  local a, pathA, errA = loadSymbol("completionist_raven_probe_a")
  local b, pathB, errB = loadSymbol("completionist_raven_probe_b")
  local c, pathC, errC = loadSymbol("completionist_raven_probe_c")
  if a == nil or b == nil or c == nil then
    log("BRIDGE_FAILED phase=load a=" .. tostring(errA) ..
      " b=" .. tostring(errB) .. " c=" .. tostring(errC))
    return
  end
  if pathA ~= pathB or pathA ~= pathC then
    log("BRIDGE_FAILED phase=path_mismatch a=" .. tostring(pathA) ..
      " b=" .. tostring(pathB) .. " c=" .. tostring(pathC))
    return
  end

  local aa, ea = callChunk(a, 18, 0)
  local bb, eb = callChunk(b, 18, 18)
  local cc, ec = callChunk(c, 17, 36)
  if aa == nil or bb == nil or cc == nil then
    log("BRIDGE_FAILED phase=call a=" .. tostring(ea) ..
      " b=" .. tostring(eb) .. " c=" .. tostring(ec))
    return
  end

  local bits = aa .. bb .. cc
  log("BRIDGE_OK path=" .. tostring(pathA) ..
      " chunks=18,18,17 total=" .. tostring(#bits) ..
      " bits=" .. bits ..
      " processMemoryWrites=false saveWrites=false progressionWrites=false")
end
-- END COMPLETIONIST V0.10.5 RAVEN NATIVE BRIDGE PROBE
