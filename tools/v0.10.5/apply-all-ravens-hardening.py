"""Apply the guarded offline hardening patch for the all-Ravens release candidate.

This helper only edits repository source/test/docs files. It never opens God of War
save data, never launches the game, and never writes the installed game directory.
All guards are validated in memory before any file is written.
"""
from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

RUNTIME = REPO / "tools/v0.10.5/all-ravens-map-runtime.lua"
LUA_TEST = REPO / "tools/v0.10.5/test_all_ravens_lua.py"
MODEL = REPO / "tools/v0.10.5/raven_runtime_model.py"
MODEL_TEST = REPO / "tools/v0.10.5/test_raven_runtime_model.py"
CATALOGUE = REPO / "catalogue/odins-ravens.json"
CATALOGUE_BUILDER = REPO / "tools/v0.10.5/raven_catalogue.py"
CATALOGUE_TEST = REPO / "tools/v0.10.5/test_raven_catalogue.py"
GATE = REPO / "docs/research/all-ravens-release-gate.md"

TARGETS = (
    RUNTIME,
    LUA_TEST,
    MODEL,
    MODEL_TEST,
    CATALOGUE,
    CATALOGUE_BUILDER,
    CATALOGUE_TEST,
    GATE,
)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def replace_guarded(text: str, old: str, new: str, *, path: Path, guard: str, expected: int = 1) -> str:
    if guard in text:
        return text
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} guarded occurrence(s), found {count}")
    return text.replace(old, new, expected)


def replace_token_count(text: str, old: str, new: str, *, path: Path, expected: int) -> str:
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == 0:
        if new_count != expected:
            raise RuntimeError(f"{path}: already-patched token count expected {expected}, found {new_count}")
        return text
    if old_count != expected or new_count != 0:
        raise RuntimeError(
            f"{path}: token guard failed old={old_count} new={new_count} expected_old={expected}"
        )
    return text.replace(old, new)


def patch_runtime(text: str) -> str:
    text = replace_guarded(
        text,
        '  local states = _G.CompletionistMapV105RavenState or {}\n',
        '  local byMarkerId = {}\n\n  local states = _G.CompletionistMapV105RavenState or {}\n',
        path=RUNTIME,
        guard='  local byMarkerId = {}\n',
    )
    old_marker = '''  local function markerInfo(name)\n    local ok, info = pcall(function() return game.Map.GetMarkerInfo(name) end)\n    if not ok or info == nil or info.Id == nil then return nil end\n    return info\n  end\n'''
    new_marker = '''  local function rememberMarkerId(name, info)\n    if type(name) ~= "string" or type(info) ~= "table" or info.Id == nil then return end\n    byMarkerId[tostring(info.Id)] = name\n  end\n\n  local function markerInfo(name)\n    local ok, info = pcall(function() return game.Map.GetMarkerInfo(name) end)\n    if not ok or type(info) ~= "table" or info.Id == nil then return nil end\n    rememberMarkerId(name, info)\n    return info\n  end\n\n  local function knownNameForId(id)\n    if id == nil then return nil end\n    local key = tostring(id)\n    local cached = byMarkerId[key]\n    if cached ~= nil then return cached end\n    for name, _ in pairs(byName) do\n      local info = markerInfo(name)\n      if info ~= nil and tostring(info.Id) == key then return name end\n    end\n    return nil\n  end\n'''
    text = replace_guarded(text, old_marker, new_marker, path=RUNTIME, guard='  local function knownNameForId(id)\n')
    text = replace_guarded(
        text,
        '          local info = game.Map.GetMarkerInfo(row.Name)\n          if info == nil or info.Id == nil then return nil, "marker_info" end\n',
        '          local info = markerInfo(row.Name)\n          if info == nil then return nil, "marker_info" end\n',
        path=RUNTIME,
        guard='          local info = markerInfo(row.Name)\n',
    )
    text = replace_guarded(
        text,
        '        local hideOK = pcall(function() game.Compass.HideMarker(id) end)\n',
        '        local target = knownNameForId(id) or id\n        local hideOK = pcall(function() game.Compass.HideMarker(target) end)\n',
        path=RUNTIME,
        guard='        local target = knownNameForId(id) or id\n',
    )
    for required in ('local function knownNameForId(id)', 'local function markerInfo(name)', 'knownNameForId(id) or id'):
        if required not in text:
            raise RuntimeError(f"{RUNTIME}: missing postcondition {required!r}")
    return text


def patch_lua_test(text: str) -> str:
    helper_old = 'customIds={}\nstockIds={}\nprint=function(s) calls.logs[#calls.logs+1]=s end\n'
    helper_new = '''customIds={}\nstockIds={}\nlocal markerIds={}\nlocal markerNamesById={}\nlocal nextMarkerId=10000\nlocal function markerId(name)\n  if markerIds[name]==nil then\n    markerIds[name]=nextMarkerId\n    markerNamesById[nextMarkerId]=name\n    nextMarkerId=nextMarkerId+1\n  end\n  return markerIds[name]\nend\nprint=function(s) calls.logs[#calls.logs+1]=s end\n'''
    text = replace_guarded(text, helper_old, helper_new, path=LUA_TEST, guard='local markerIds={}\n')
    text = replace_guarded(
        text,
        'function game.Map.GetMarkerInfo(name) return {Id=name,X=1,Y=2,Z=3} end\n',
        'function game.Map.GetMarkerInfo(name) return {Id=markerId(name),X=1,Y=2,Z=3} end\n',
        path=LUA_TEST,
        guard='function game.Map.GetMarkerInfo(name) return {Id=markerId(name),X=1,Y=2,Z=3} end\n',
    )
    old_compass = '''function game.Compass.ShowMarker(name,class) customIds={name}; calls.shown=name; calls.class=class end\nfunction game.Compass.HideMarker(target)\n  local next={}\n  for _,id in ipairs(customIds) do if tostring(id)~=tostring(target) then next[#next+1]=id end end\n  customIds=next\n  local nextStock={}\n  for _,id in ipairs(stockIds) do if tostring(id)~=tostring(target) then nextStock[#nextStock+1]=id end end\n  stockIds=nextStock\nend\n'''
    new_compass = '''function game.Compass.ShowMarker(name,class) customIds={markerId(name)}; calls.shown=name; calls.class=class end\nfunction game.Compass.HideMarker(target)\n  if type(target)=="number" and markerNamesById[target]~=nil then\n    error("raw custom numeric ID rejected")\n  end\n  local next={}\n  for _,id in ipairs(customIds) do\n    local customName=markerNamesById[id]\n    if tostring(id)~=tostring(target) and customName~=target then next[#next+1]=id end\n  end\n  customIds=next\n  local nextStock={}\n  for _,id in ipairs(stockIds) do if tostring(id)~=tostring(target) then nextStock[#nextStock+1]=id end end\n  stockIds=nextStock\nend\n'''
    text = replace_guarded(text, old_compass, new_compass, path=LUA_TEST, guard='error("raw custom numeric ID rejected")')
    text = replace_guarded(
        text,
        'function probe.customAt(i) return customIds[i] end\nfunction probe.tracked() return CompletionistMapV105TrackedCatalogueId end\n',
        'function probe.customAt(i) return customIds[i] end\nfunction probe.markerId(name) return markerId(name) end\nfunction probe.tracked() return CompletionistMapV105TrackedCatalogueId end\n',
        path=LUA_TEST,
        guard='function probe.markerId(name) return markerId(name) end\n',
    )
    text = replace_guarded(
        text,
        '        self.assertEqual(self.probe.customAt(1), self.a["marker"]["name"])\n',
        '        self.assertEqual(self.probe.customAt(1), self.probe.markerId(self.a["marker"]["name"]))\n',
        path=LUA_TEST,
        guard='self.probe.markerId(self.a["marker"]["name"])',
    )
    text = replace_guarded(
        text,
        '        self.assertEqual(self.probe.customAt(1), self.b["marker"]["name"])\n',
        '        self.assertEqual(self.probe.customAt(1), self.probe.markerId(self.b["marker"]["name"]))\n',
        path=LUA_TEST,
        guard='self.probe.markerId(self.b["marker"]["name"])',
    )
    if 'raw custom numeric ID rejected' not in text or 'probe.markerId' not in text:
        raise RuntimeError(f"{LUA_TEST}: realistic numeric marker mock postcondition failed")
    return text


def patch_model(text: str) -> str:
    old = '''    def collide(self, object_token: str):\n        row = self.by_object.get(object_token)\n        if row is None or row["catalogue_id"] not in self.map_icons:\n            self.selection = None\n            return None\n        self.selection = row["catalogue_id"]\n        return self.selection\n'''
    new = '''    def collide(self, object_token: str):\n        row = self.by_object.get(object_token)\n        if row is None:\n            # Incidental/non-custom collision callbacks do not replace an exact Raven\n            # candidate. Ownership is resolved later by the exact prompt UID.\n            return None\n        if row["catalogue_id"] not in self.map_icons:\n            self.selection = None\n            return None\n        self.selection = row["catalogue_id"]\n        return self.selection\n\n    def incidental_collision(self) -> None:\n        """Model collision noise that must not expire an exact Raven candidate."""\n        return None\n'''
    return replace_guarded(text, old, new, path=MODEL, guard='    def incidental_collision(self) -> None:\n')


def patch_model_test(text: str) -> str:
    anchor = '    def test_marker_id_alone_never_infers_raven(self):\n'
    new_test = '''    def test_incidental_collision_noise_preserves_exact_candidate_until_uid_resolution(self):\n        model = self.model()\n        model.observe(self.a["catalogue_id"], False)\n        model.open_map(self.a["realm"])\n        self.arm(model, self.a)\n\n        # Real map callbacks can contain unrelated collision churn between the exact\n        # Raven collision and the human click. There is deliberately no TTL.\n        for _ in range(5):\n            model.incidental_collision()\n            self.assertIsNone(model.collide("stock:incidental-noise"))\n            self.assertEqual(model.selection, self.a["catalogue_id"])\n\n        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "shown")\n        self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))\n\n        # A genuinely different prompt UID must disarm/delegate instead of letting a\n        # stale Raven candidate hijack a stock target.\n        self.arm(model, self.a)\n        model.incidental_collision()\n        self.assertEqual(model.click_raven("stock-uid"), "delegate")\n        self.assertIsNone(model.selection)\n        self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))\n\n'''
    return replace_guarded(
        text,
        anchor,
        new_test + anchor,
        path=MODEL_TEST,
        guard='    def test_incidental_collision_noise_preserves_exact_candidate_until_uid_resolution(self):\n',
    )


def patch_metadata(texts: dict[Path, str]) -> None:
    old = "parent_has_one_hidden_surplus_raven"
    new = "parent_contains_one_bonus_untracked_raven"
    texts[CATALOGUE] = replace_token_count(texts[CATALOGUE], old, new, path=CATALOGUE, expected=9)
    texts[CATALOGUE_BUILDER] = replace_token_count(
        texts[CATALOGUE_BUILDER], old, new, path=CATALOGUE_BUILDER, expected=1
    )
    texts[CATALOGUE_TEST] = replace_token_count(
        texts[CATALOGUE_TEST], old, new, path=CATALOGUE_TEST, expected=1
    )


def patch_gate(text: str) -> str:
    old = '''## Exact next runtime probe\n\nBuild a read-only diagnostic that receives one catalogue instance GUID and queries\nthe native checkpoint/object-state store without loading or mutating that Raven.\nRun it against two legitimate saves with opposite state for the same Raven. Prove:\n\n1. The unloaded Raven returns `false` on the uncollected save.\n2. The same unloaded Raven returns `true` on the collected save.\n3. The query works before visiting its region.\n4. Checkpoint restore changes the observed value back when expected.\n5. No save, quest, marker, collectible, or progression bytes change.\n\nOnly after this passes should the adapter populate all catalogue rows and the full\nhuman map/compass matrix begin.\n'''
    new = '''## Native Lua persistence investigation\n\nOffline PE registration-table analysis of the shipped PC executable proved that the\nLua-facing `game.SubObject` table exposes exactly these seven methods in the relevant\nregistration block:\n\n- `Sleep`\n- `Wake`\n- `SetRetainOnCheckpoint`\n- `SetForgetOnCheckpoint`\n- `SoftSave`\n- `SetEntityZoneHandler`\n- `SetUpdateDisableDistance`\n\n`LoadSubObject` exists as an internal engine string but is not registered as a Lua\nmethod. The registered object lookup APIs operate on loaded game objects; the scan\nfound no read/restore/GUID API for querying checkpoint state of an unloaded subobject.\nEvidence is archived under\n`archive/field-logs/source-scans/lua-registration-tables-20260914-065951/`.\n\nFor release purposes, the supported Lua/native API route is therefore considered\nclosed unless new concrete engine evidence appears. This does **not** prove that the\ncompiled engine lacks an internal mechanism; it means the mod has no proven callable,\nread-only Lua oracle for it. Unknown per-Raven state remains hidden/fail-closed.\n\n## Runtime gate remains closed\n\nDo not populate static Raven pins from aggregate regional counts, actor absence, map\ndiscovery, or synthetic completion state. `ready_for_runtime_test` remains `false`\nuntil an exact individual unloaded-state oracle is proven. Loaded Raven lifecycle\nobservation remains valid but cannot establish pre-install kills for all 53 entries.\n'''
    return replace_guarded(text, old, new, path=GATE, guard='## Native Lua persistence investigation\n')


def main() -> int:
    texts = {path: read(path) for path in TARGETS}
    original = dict(texts)

    texts[RUNTIME] = patch_runtime(texts[RUNTIME])
    texts[LUA_TEST] = patch_lua_test(texts[LUA_TEST])
    texts[MODEL] = patch_model(texts[MODEL])
    texts[MODEL_TEST] = patch_model_test(texts[MODEL_TEST])
    patch_metadata(texts)
    texts[GATE] = patch_gate(texts[GATE])

    catalogue = json.loads(texts[CATALOGUE])
    ravens = catalogue.get("ravens")
    if not isinstance(ravens, list) or len(ravens) != 53:
        raise RuntimeError(f"Catalogue row invariant failed: expected 53, got {len(ravens) if isinstance(ravens, list) else 'invalid'}")
    token = "parent_contains_one_bonus_untracked_raven"
    token_rows = sum(token in row.get("special_handling", []) for row in ravens)
    if token_rows != 9:
        raise RuntimeError(f"Catalogue bonus-parent metadata invariant failed: expected 9 tagged rows, got {token_rows}")
    if "Status: `ready_for_runtime_test=false`" not in texts[GATE]:
        raise RuntimeError("Release gate was accidentally opened")

    changed = [path for path in TARGETS if texts[path] != original[path]]
    # All guards and semantic postconditions passed. Only now write files.
    for path in changed:
        path.write_bytes(texts[path].encode("utf-8"))

    for path in TARGETS:
        rel = path.relative_to(REPO).as_posix()
        print(("CHANGED " if path in changed else "UNCHANGED ") + rel)
    print(f"ALL_RAVENS_HARDENING_PATCH_APPLIED changed={len(changed)} catalogue_rows={len(ravens)}")
    print("game_written=false save_or_progression_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
