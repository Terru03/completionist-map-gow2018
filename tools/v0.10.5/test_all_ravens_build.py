"""Offline binary/Lua build checks for all-Raven candidate."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
BUILD_PATH = HERE / "build-all-ravens-release-candidate.py"
spec = importlib.util.spec_from_file_location("all_ravens_build_test", BUILD_PATH)
build = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(GAME.is_dir(), "runtime-proven v3.3 source fixture not installed")
class AllRavensBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {relative: file_sha(GAME / relative) for relative in build.SOURCE_HASHES}
        cls.outputs, cls.proof = build.generate(GAME)
        cls.catalogue = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))
        cls.after = {relative: file_sha(GAME / relative) for relative in build.SOURCE_HASHES}

    def test_source_game_files_stay_unchanged(self):
        self.assertEqual(self.before, self.after)
        self.assertEqual(self.after, build.SOURCE_HASHES)

    def test_candidate_has_only_five_scoped_files(self):
        self.assertEqual(set(self.outputs), {build.MASTER, build.COORDS, build.POOL, build.MAP_LUA, build.EVENT_LUA})

    def test_candidate_has_53_real_ravens_and_no_twin(self):
        master = build.parse_candidate(self.outputs[build.MASTER], build.MASTER)
        coords = build.parse_candidate(self.outputs[build.COORDS], build.COORDS)
        wanted = {row["marker"]["uid"] for row in self.catalogue["ravens"]}
        master_ids = {row["uid"] for row in build.stage.marker_snapshot(master)}
        coord_ids = {row["uid"] for row in build.stage.coordinate_snapshot(coords)}
        self.assertTrue(wanted <= master_ids)
        self.assertTrue(wanted <= coord_ids)
        self.assertNotIn(f"{build.TWIN_UID:016X}", master_ids)
        self.assertNotIn(f"{build.TWIN_UID:016X}", coord_ids)

    def test_every_marker_uses_one_shared_raven_resource(self):
        master = build.parse_candidate(self.outputs[build.MASTER], build.MASTER)
        wanted = {row["marker"]["uid"] for row in self.catalogue["ravens"]}
        rows = [row for row in build.stage.marker_snapshot(master) if row["uid"] in wanted]
        self.assertEqual(len(rows), 53)
        self.assertEqual({row["icon"] for row in rows}, {"goMapIconCompletionistRaven"})

    def test_pool_capacity_covers_full_catalogue_for_realm_transition(self):
        self.assertEqual(self.proof["proofs"][build.POOL]["raven_capacity_after"], 53)

    def test_lua_has_53_data_rows_and_exact_router_contract(self):
        text = self.outputs[build.MAP_LUA].decode("utf-8")
        suffix = text[text.index("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS"):]
        self.assertEqual(suffix.count("{CatalogueId="), 53)
        self.assertEqual(suffix.count("WadKey="), 53)
        self.assertEqual(suffix.count("ObjectKey="), 53)
        for token in (
            "exact_collision_object", "currMarkerID", "CompletionistRaven",
            "goMapIconCompletionistRaven", "markerIdAloneInfersRaven=false",
            "CompletionistMapV105TrackedCatalogueId", "Map.RecycleIcon",
        ):
            self.assertIn(token, suffix)

    def test_gameplay_hook_has_53_exact_state_rows(self):
        text = self.outputs[build.EVENT_LUA].decode("utf-8")
        suffix = text[text.index("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS"):]
        self.assertEqual(suffix.count("{CatalogueId="), 53)
        self.assertIn("ravenKilled == true", suffix)
        self.assertIn("dx * dx + dy * dy + dz * dz <= 0.25", suffix)

    def test_hooks_add_no_progression_write(self):
        forbidden = ("SetMarkerState", "SetToken", "SetProgress", "IncrementQuestProgress", "StartQuest")
        for relative, marker in (
            (build.MAP_LUA, "-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS"),
            (build.EVENT_LUA, "-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS"),
        ):
            suffix = self.outputs[relative].decode("utf-8").split(marker, 1)[1]
            for token in forbidden:
                self.assertNotIn(token, suffix)

    def test_deterministic_generate(self):
        second, proof = build.generate(GAME)
        self.assertEqual(self.outputs, second)
        self.assertEqual(self.proof, proof)

    def test_lf_and_crlf_templates_render_same(self):
        source = (HERE / "all-ravens-map-runtime.lua").read_text(encoding="utf-8").replace("\r\n", "\n")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lf, crlf = root / "lf.lua", root / "crlf.lua"
            lf.write_bytes(source.encode("utf-8"))
            crlf.write_bytes(source.replace("\n", "\r\n").encode("utf-8"))
            a = build.render_lua(self.catalogue, lf, "-- @@RAVEN_CATALOGUE_ROWS@@")
            b = build.render_lua(self.catalogue, crlf, "-- @@RAVEN_CATALOGUE_ROWS@@")
            self.assertEqual(a, b)

    def test_release_gate_open_for_catalogue_first_runtime(self):
        self.assertTrue(self.proof["ready_for_runtime_test"])
        self.assertEqual(
            self.proof["state"]["unknown_state_policy"],
            "show catalogue marker unless confirmed killed",
        )
        self.assertTrue(self.proof["state"]["persisted_kill_bootstrap"])
        self.assertEqual(
            self.proof["state"]["persisted_identity_join"],
            "unique normalized WAD level plus GameObject name",
        )
        self.assertIn("__PickleTable", self.proof["state"]["persisted_source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
