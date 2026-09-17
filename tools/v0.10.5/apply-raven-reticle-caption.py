#!/usr/bin/env python3
"""Guarded source/test patch for the v0.10.5 Raven map reticle caption."""
from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "all-ravens-map-runtime.lua"
TESTS = HERE / "test_all_ravens_lua.py"


def normalize(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one old block, found {count}")
    if new in text:
        raise RuntimeError(f"{label}: new block is already present while old block also exists")
    return text.replace(old, new, 1)


runtime_old = '''  function MapOn:MapCollisionChangeHandler(currState, collisionTable, realmName)
    lastMapOnSelf = self
    local selected = collisionSelection(self, collisionTable)
    if selected ~= nil then captureSelection(self, selected) end
    return previousCollision(self, currState, collisionTable, realmName)
  end
'''

runtime_new = '''  function MapOn:MapCollisionChangeHandler(currState, collisionTable, realmName)
    lastMapOnSelf = self
    local selected = collisionSelection(self, collisionTable)
    if selected ~= nil then captureSelection(self, selected) end

    local result = previousCollision(self, currState, collisionTable, realmName)

    if selected ~= nil and type(MapOn.SetReticleInfo) == "function" then
      local ok, err = pcall(MapOn.SetReticleInfo, self, currState, markerLabel, "")
      if ok then
        log("RETICLE_TEXT", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
            " title=" .. markerLabel)
      else
        log("RETICLE_TEXT_FAILED", "name=" .. selected.Name .. " uid=" .. selected.IdString ..
            " error=" .. tostring(err))
      end
    end

    return result
  end
'''

test_calls_old = 'calls={logs={},previousShow=0,recycled=0,labels={}}'
test_calls_new = 'calls={logs={},previousShow=0,recycled=0,labels={},reticleTitle=nil,reticleDesc=nil,reticleCalls=0}'

test_collision_old = '''function MapOn.MapCollisionChangeHandler(s,state,collisions,realm)
  if collisions and collisions[1] then s.currMarkerID=collisions[1].id else s.currMarkerID=nil end
end
function MapOn.SubmenuExit(s) end
'''

test_collision_new = '''function MapOn.MapCollisionChangeHandler(s,state,collisions,realm)
  if collisions and collisions[1] then s.currMarkerID=collisions[1].id else s.currMarkerID=nil end
end
function MapOn.SetReticleInfo(s,state,title,desc)
  calls.reticleTitle=title
  calls.reticleDesc=desc
  calls.reticleCalls=calls.reticleCalls+1
end
function MapOn.SubmenuExit(s) end
'''

test_probe_old = '''function probe.lastLabel() return calls.labels[#calls.labels] end
function probe.recycled() return calls.recycled end
'''

test_probe_new = '''function probe.lastLabel() return calls.labels[#calls.labels] end
function probe.reticleTitle() return calls.reticleTitle end
function probe.reticleDesc() return calls.reticleDesc end
function probe.reticleCalls() return calls.reticleCalls end
function probe.recycled() return calls.recycled end
'''

test_method_anchor = '''    def test_realm_transition_recycles_old_realm_and_builds_midgard(self):
'''

test_method_new = '''    def test_exact_raven_collision_populates_stock_cursor_card(self):
        self.probe.open()
        show, _ = self.probe.click(self.a["marker"]["name"])
        self.assertTrue(show)
        self.assertEqual(self.probe.reticleTitle(), "Odin's Raven")
        self.assertEqual(self.probe.reticleDesc(), "")
        self.assertGreaterEqual(self.probe.reticleCalls(), 1)

    def test_realm_transition_recycles_old_realm_and_builds_midgard(self):
'''

runtime = normalize(RUNTIME)
tests = normalize(TESTS)

runtime_already = runtime_new in runtime
runtime_old_present = runtime_old in runtime
if runtime_already and not runtime_old_present:
    pass
elif runtime_old_present and not runtime_already:
    runtime = replace_once(runtime, runtime_old, runtime_new, "runtime collision caption")
else:
    raise RuntimeError("runtime collision caption guard failed")

patches = [
    (test_calls_old, test_calls_new, "test calls state"),
    (test_collision_old, test_collision_new, "test SetReticleInfo stub"),
    (test_probe_old, test_probe_new, "test reticle probes"),
]
for old, new, label in patches:
    if new in tests:
        if old in tests:
            raise RuntimeError(f"{label}: old and new blocks are both present")
        continue
    tests = replace_once(tests, old, new, label)

if test_method_new not in tests:
    tests = replace_once(tests, test_method_anchor, test_method_new, "test reticle regression")

RUNTIME.write_text(runtime, encoding="utf-8", newline="\n")
TESTS.write_text(tests, encoding="utf-8", newline="\n")
print("RAVEN_RETICLE_CAPTION_PATCH_APPLIED")
