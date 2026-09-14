from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for candidate in (REPO / "dist/re-tools", REPO.parent / "completionist-map-gow2018/dist/re-tools"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None

MODULE = runpy.run_path(str(HERE / "build-unloaded-checkpoint-oracle-probe.py"))
build = MODULE["build"]
lua_quote = MODULE["lua_quote"]


class ProbeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (HERE / "unloaded-checkpoint-oracle-probe.lua").read_text(encoding="utf-8")
        cls.catalogue = json.loads(
            (HERE.parent.parent / "catalogue" / "odins-ravens.json").read_text(encoding="utf-8")
        )

    def test_embeds_all_exact_rows(self):
        output = build(self.template, self.catalogue)
        self.assertNotIn("@@RAVEN_ORACLE_ROWS@@", output)
        self.assertEqual(output.count("CatalogueId ="), 53)
        self.assertIn('Wad = "xpl200_funeral.wad"', output)
        self.assertIn('ObjectName = "goprecisionchallenge_raven_perch1"', output)

    def test_catalogue_wad_object_pairs_are_unique(self):
        pairs = [
            (row["source"]["wad"].lower(), row["native"]["object_name"].lower())
            for row in self.catalogue["ravens"]
        ]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_duplicate_identity_fails_closed(self):
        broken = json.loads(json.dumps(self.catalogue))
        broken["ravens"][1]["source"]["wad"] = broken["ravens"][0]["source"]["wad"]
        broken["ravens"][1]["native"]["object_name"] = broken["ravens"][0]["native"]["object_name"]
        with self.assertRaisesRegex(ValueError, "duplicate exact"):
            build(self.template, broken)

    def test_runtime_name_alias_collision_fails_closed(self):
        broken = json.loads(json.dumps(self.catalogue))
        broken["ravens"][1]["source"]["wad"] = broken["ravens"][0]["source"]["wad"]
        broken["ravens"][1]["native"]["object_name"] = (
            broken["ravens"][0]["native"]["object_name"][2:]
        )
        with self.assertRaisesRegex(ValueError, "duplicate runtime"):
            build(self.template, broken)

    @unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
    def test_generated_probe_compiles_as_lua_51(self):
        output = build(self.template, self.catalogue)
        lua = LuaRuntime(unpack_returned_tuples=True)
        loaded = lua.globals().loadstring(output)
        self.assertTrue(callable(loaded), loaded)

    @unittest.skipIf(LuaRuntime is None, "Lua 5.1 test runtime unavailable")
    def test_environment_root_yields_exact_cold_record_and_unknown_fails_closed(self):
        cold = next(
            row for row in self.catalogue["ravens"]
            if row["source"]["wad"].lower() != "xpl200_funeral.wad"
        )
        cold_wad = cold["source"]["wad"].lower()
        cold_name = cold["native"]["object_name"].lower()
        prelude = f'''\
logs = {{}}
function print(value) logs[#logs + 1] = tostring(value) end
local current = {{ Level = "Level 'WAD_Xpl200_Funeral'" }}
function current:GetDebugName() return "precisionchallenge_raven_perch" end
local cold = {{ Level = "Level 'WAD_{cold_wad[:-4]}'" }}
function cold:GetDebugName() return {lua_quote(cold_name[2:] if cold_name.startswith("go") else cold_name)} end
local unknown = {{}}
local environment = {{
  __PickleTable = {{ __subobjs = {{
    [current] = {{ ravenKilled = false }},
    [cold] = {{ ravenKilled = true }},
    [unknown] = {{ ravenKilled = true }},
  }} }},
}}
engine = {{
  CurrentlyExecutingObject = function() return current.Level end,
  GetAvailableWads = function() return {{}} end,
  DebugGetSubObjectEnvironmentRoot = function() return {{ environment }} end,
}}
game = {{
  FindLevel = function(name)
    if string.lower(name) == "wad_xpl200_funeral" then return current.Level end
    return nil
  end,
  QuestManager = {{ GetQuestProgressAndGoal = function() return nil, nil end }},
}}
function OnRestoreCheckpoint() return "previous-result" end
'''
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(prelude)
        lua.execute(build(self.template, self.catalogue))
        result = lua.eval("OnRestoreCheckpoint(nil, nil, nil)")
        log = lua.eval('table.concat(logs, "\\n")')
        self.assertEqual(result, "previous-result")
        self.assertIn("ENVIRONMENT_ROOT entries=1", log)
        self.assertIn(f"EXACT_STATE catalogueId={cold['catalogue_id']}", log)
        self.assertIn("resident=false", log)
        self.assertIn("STATE_UNKNOWN reason=exact_identity_unavailable", log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
