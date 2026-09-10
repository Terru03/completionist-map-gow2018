"""Run actual Twin hook with Lua 5.1 and a bounded two-object pool."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO/'dist/re-tools'))
from lupa.lua51 import LuaRuntime

PRELUDE = r'''
local calls = {create=0, recycle=0, oldCreate=0, oldDestroy=0, logs={}}
local options = {}
local live = {}
local serial = 0
local self = {currRealmName="Midgard"}
local function log(text) calls.logs[#calls.logs+1] = text end
print = log
local function object(id)
  serial = serial+1
  local go = {serial=serial, id=id, shown=false}
  function go:Show()
    if options.showError and self.id == "twin-uid" then error("show fail") end
    self.shown=true
  end
  function go:GetName() return "mapiconcompletionistraven" end
  function go:GetWorldPosition()
    return {x=self.id == "raven-uid" and 1 or 1.1,y=0,z=2}
  end
  live[go]=true
  return go
end
local Map = {}
function Map.GetMarkerInfo(name)
  assert(name == "Completionist_V104_Veithurgard_Raven_Twin_01")
  if options.lookupError then error("lookup fail") end
  if options.absent then return nil end
  return {Id="twin-uid",State=0}
end
function Map.FindRegionFromMarker(id)
  assert(id == "twin-uid")
  if options.regionMissing then return false,nil end
  return true,"veithurgard"
end
function Map.CreateMarkerIcon(id, region, label)
  assert(id == "twin-uid" and region == "veithurgard" and label == "")
  calls.create=calls.create+1
  if options.createError then error("create fail") end
  if options.reuseOriginal then return self.completionistMapV100MapIconGO end
  local count=0
  for _ in pairs(live) do count=count+1 end
  if count >= (options.capacity or 2) then return nil end
  return object(id)
end
function Map.RecycleIcon(go)
  assert(live[go], "double recycle")
  if options.recycleError and go.id == "twin-uid" then error("recycle fail") end
  live[go]=nil
  calls.recycle=calls.recycle+1
end
setmetatable(Map,{__index=function(_, key) error("forbidden Map API: "..key) end})
local function CompletionistMapV100_DestroyMapPin(s)
  calls.oldDestroy=calls.oldDestroy+1
  if s.completionistMapV100MapIconGO then Map.RecycleIcon(s.completionistMapV100MapIconGO) end
  s.completionistMapV100MapIconGO=nil
  return "old-destroy-result"
end
local function CompletionistMapV100_CreateMapPin(s, state)
  calls.oldCreate=calls.oldCreate+1
  if s.currRealmName ~= "Midgard" then return "old-create-result" end
  CompletionistMapV100_DestroyMapPin(s)
  if not options.noOriginal then s.completionistMapV100MapIconGO=object("raven-uid") end
  return "old-create-result"
end
'''
POSTLUDE = r'''
return {
 self=self, calls=calls, options=options,
 create=function() return CompletionistMapV100_CreateMapPin(self,{}) end,
 destroy=function() return CompletionistMapV100_DestroyMapPin(self) end,
 count=function() local n=0 for _ in pairs(live) do n=n+1 end return n end,
 logs=function() return table.concat(calls.logs,"\n") end
}
'''


class SharedLoaderLuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.probe = self.lua.execute(PRELUDE + (HERE/'raven-shared-loader-twin.lua').read_text() + POSTLUDE)

    def test_two_distinct_same_name_objects_and_cleanup(self):
        p = self.probe
        self.assertEqual(p.create(), 'old-create-result')
        self.assertEqual(p.count(), 2)
        self.assertIn('distinctObjects=true', p.logs())
        self.assertIn('state=0', p.logs())
        self.assertEqual(p.destroy(), 'old-destroy-result')
        self.assertEqual(p.count(), 0)
        self.assertEqual(p.calls.oldCreate, 1)

    def test_reopen_does_not_leak_pool(self):
        p = self.probe
        for _ in range(25):
            p.create()
            self.assertEqual(p.count(), 2)
        p.destroy()
        self.assertEqual(p.count(), 0)
        self.assertEqual(p.calls.create, 25)

    def test_capacity_one_is_discriminating_control(self):
        p = self.probe
        p.options.capacity = 1
        p.create()
        self.assertEqual(p.count(), 1)
        self.assertIn('reason=nil_object', p.logs())
        self.assertIsNone(p.self.completionistSharedLoaderTwinGO)

    def test_no_original_does_not_claim_twin_success(self):
        p = self.probe
        p.options.noOriginal = True
        p.create()
        self.assertEqual(p.count(), 0)
        self.assertEqual(p.calls.create, 0)

    def test_missing_lookup_or_region_keeps_original(self):
        for key in ('absent', 'regionMissing', 'lookupError'):
            with self.subTest(key=key):
                self.setUp()
                p = self.probe
                p.options[key] = True
                p.create()
                self.assertEqual(p.count(), 1)
                self.assertEqual(p.calls.create, 0)
                p.destroy()
                self.assertEqual(p.count(), 0)

    def test_create_and_show_errors_keep_original_and_release_twin(self):
        for key in ('createError', 'showError'):
            with self.subTest(key=key):
                self.setUp()
                p = self.probe
                p.options[key] = True
                p.create()
                self.assertEqual(p.count(), 1)
                self.assertIsNone(p.self.completionistSharedLoaderTwinGO)
                self.assertIn('success=false', p.logs())

    def test_same_object_never_counted_or_recycled_as_twin(self):
        p = self.probe
        p.options.reuseOriginal = True
        p.create()
        self.assertEqual(p.count(), 1)
        self.assertIsNone(p.self.completionistSharedLoaderTwinGO)
        self.assertIn('reason=original_object_reused', p.logs())
        p.destroy()
        self.assertEqual(p.count(), 0)

    def test_cleanup_error_keeps_handle_and_retries(self):
        p = self.probe
        p.create()
        p.options.recycleError = True
        p.create()
        self.assertEqual(p.count(), 2)
        self.assertEqual(p.calls.create, 1)
        self.assertIn('prior_twin_not_recycled', p.logs())
        p.options.recycleError = False
        p.destroy()
        self.assertEqual(p.count(), 0)

    def test_realm_switch_has_no_twin_request(self):
        p = self.probe
        p.create()
        p.destroy()
        p.self.currRealmName = 'Alfheim'
        p.create()
        self.assertEqual(p.count(), 0)
        self.assertEqual(p.calls.create, 1)

    def test_full_candidate_compiles_under_lua51(self):
        path = REPO/'build/v0.10.4-raven-shared-loader/offline/candidate/game-root/mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
        compiler = self.lua.eval('function(s) local f,e=loadstring(s); assert(f,e); return true end')
        self.assertTrue(compiler(path.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
