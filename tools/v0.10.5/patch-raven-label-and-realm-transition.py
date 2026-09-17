#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path.name}: expected exactly one match for {label}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"PATCHED {path.name}: {label}")


runtime = HERE / "all-ravens-map-runtime.lua"
replace_once(
    runtime,
    '  local mapResource = "goMapIconCompletionistRaven"\n',
    '  local mapResource = "goMapIconCompletionistRaven"\n  local markerLabel = "Odin\'s Raven"\n',
    "give Raven map pins a visible caption",
)
replace_once(
    runtime,
    '    local realm = self.currRealmName\n    for name, go in pairs(icons) do\n',
    '    local realm = self.currRealmName\n'
    '    if self.completionistMapV105LastRealm ~= nil and self.completionistMapV105LastRealm ~= realm then\n'
    '      clearSelection(self, "realm_change")\n'
    '      log("REALM_CHANGE", "from=" .. tostring(self.completionistMapV105LastRealm) .. " to=" .. tostring(realm))\n'
    '    end\n'
    '    self.completionistMapV105LastRealm = realm\n'
    '    for name, go in pairs(icons) do\n',
    "disarm stale map selection on realm transition",
)
replace_once(
    runtime,
    '          return Map.CreateMarkerIcon(info.Id, region, ""), nil\n',
    '          return Map.CreateMarkerIcon(info.Id, region, markerLabel), nil\n',
    "pass the Raven caption to Map.CreateMarkerIcon",
)

build = HERE / "build-all-ravens-release-candidate.py"
replace_once(
    build,
    '    add = 45 - before_capacity\n',
    '    target_capacity = 53\n    add = target_capacity - before_capacity\n',
    "reserve the full 53-object Raven pool for realm-transition overlap",
)
replace_once(
    build,
    '    check(new_count == count + add and after_capacity == 45, "all-Raven pool capacity differs")\n',
    '    check(new_count == count + add and after_capacity == target_capacity, "all-Raven pool capacity differs")\n',
    "validate the 53-object Raven pool",
)

build_test = HERE / "test_all_ravens_build.py"
replace_once(
    build_test,
    '    def test_pool_capacity_matches_largest_realm(self):\n        self.assertEqual(self.proof["proofs"][build.POOL]["raven_capacity_after"], 45)\n',
    '    def test_pool_capacity_covers_full_catalogue_for_realm_transition(self):\n        self.assertEqual(self.proof["proofs"][build.POOL]["raven_capacity_after"], 53)\n',
    "test full-catalogue pool capacity instead of single-realm capacity",
)
replace_once(
    build_test,
    '            "CompletionistMapV105TrackedCatalogueId", "Map.RecycleIcon",\n',
    '            "CompletionistMapV105TrackedCatalogueId", "Map.RecycleIcon",\n'
    '            \'local markerLabel = "Odin\\\'s Raven"\',\n'
    '            "Map.CreateMarkerIcon(info.Id, region, markerLabel)",\n',
    "require visible Raven caption routing in the rendered Lua",
)

lua_test = HERE / "test_all_ravens_lua.py"
replace_once(
    lua_test,
    'calls={logs={},previousShow=0,recycled=0}\n',
    'calls={logs={},previousShow=0,recycled=0,labels={}}\n',
    "capture marker labels in the Lua harness",
)
replace_once(
    lua_test,
    'function Map.CreateMarkerIcon(id,region,label)\n  return {id=id,shown=false,Show=function(self) self.shown=true end}\nend\n',
    'function Map.CreateMarkerIcon(id,region,label)\n'
    '  calls.labels[#calls.labels+1]=label\n'
    '  return {id=id,shown=false,Show=function(self) self.shown=true end}\n'
    'end\n',
    "record Map.CreateMarkerIcon label arguments",
)
replace_once(
    lua_test,
    'function probe.iconCount()\n  local n=0\n  for _,_ in pairs(self.completionistMapV105RavenIcons or {}) do n=n+1 end\n  return n\nend\n',
    'function probe.iconCount()\n'
    '  local n=0\n'
    '  for _,_ in pairs(self.completionistMapV105RavenIcons or {}) do n=n+1 end\n'
    '  return n\n'
    'end\n'
    'function probe.lastLabel() return calls.labels[#calls.labels] end\n'
    'function probe.recycled() return calls.recycled end\n'
    'function probe.realm(name) self.currRealmName=name; return CompletionistMapV100_CreateMapPin(self,{}) end\n',
    "expose label and realm-transition probes",
)
replace_once(
    lua_test,
    '        self.probe.open()\n        self.assertEqual(self.probe.iconCount(), 2)\n        self.probe.publish(self.a["catalogue_id"], False)\n',
    '        self.probe.open()\n'
    '        self.assertEqual(self.probe.iconCount(), 2)\n'
    '        self.assertEqual(self.probe.lastLabel(), "Odin\'s Raven")\n'
    '        self.probe.publish(self.a["catalogue_id"], False)\n',
    "assert the visible Raven caption",
)
replace_once(
    lua_test,
    '    def test_persisted_kill_bootstrap_hides_only_confirmed_raven(self):\n',
    '    def test_realm_transition_recycles_old_realm_and_builds_midgard(self):\n'
    '        self.probe.open()\n'
    '        self.assertEqual(self.probe.iconCount(), 2)\n'
    '        self.probe.realm("Midgard")\n'
    '        self.assertEqual(self.probe.iconCount(), 45)\n'
    '        self.assertGreaterEqual(self.probe.recycled(), 2)\n'
    '        self.assertEqual(self.probe.lastLabel(), "Odin\'s Raven")\n'
    '\n'
    '    def test_persisted_kill_bootstrap_hides_only_confirmed_raven(self):\n',
    "cover cross-realm icon recycle and rebuild",
)

print("RAVEN_LABEL_AND_REALM_TRANSITION_PATCH_APPLIED")
