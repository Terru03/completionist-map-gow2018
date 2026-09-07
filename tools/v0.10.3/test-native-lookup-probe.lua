local savedPrint = print
local log = {}
print = function(line) log[#log + 1] = line end
local calls = 0
local originalCalls = 0
MapOn = {GetRealmMarkerInfo = function() originalCalls = originalCalls + 1 end}
game = {
  Map = {GetMarkerInfo = function(name)
    assert(name == "Completionist_V103_Veithurgard_Raven_01")
    calls = calls + 1
    return nil
  end},
  Compass = setmetatable({}, {__index = function() error("Compass must stay untouched") end})
}
dofile("tools/v0.10.3/native-lookup-probe.lua")
local screen = setmetatable({currRealmName = "Alfheim", realmMarkerInfo = {}}, {__index = MapOn})
screen:GetRealmMarkerInfo()
assert(calls == 0)
screen.currRealmName = "Midgard"
screen:GetRealmMarkerInfo()
screen:GetRealmMarkerInfo()
assert(calls == 1 and originalCalls == 3)
assert(table.concat(log, "\n"):find("registered=false", 1, true))
game.Map.GetMarkerInfo = function() error("test lookup failure") end
screen.completionistV103LookupDone = false
screen:GetRealmMarkerInfo()
assert(table.concat(log, "\n"):find("NATIVE_COMPASS_ERROR", 1, true))
game.Map.GetMarkerInfo = function()
  return {Id = "new-id", Coordinates = {x = 1, y = 2, z = 3}, WadName = "WAD_Test", State = 1}
end
screen.completionistV103LookupDone = false
screen:GetRealmMarkerInfo()
assert(table.concat(log, "\n"):find("source=candidate x=1", 1, true))
print = savedPrint
print("Lua probe tests passed: realm gate, once-only, absent/present ID, error isolation; Compass untouched.")
