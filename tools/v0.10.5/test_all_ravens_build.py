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


def exact_source_fixture_available() -> bool:
    if not GAME.is_dir():
        return False
    return all(
        (GAME / relative).is_file() and file_sha(GAME / relative) == expected
        for relative, expected in build.SOURCE_HASHES.items()
    )


class AllRavensTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))
        cls.map_hook = build.render_lua(
            cls.catalogue,
            HERE / "all-ravens-map-runtime.lua",
            "-- @@RAVEN_CATALOGUE_ROWS@@",
        ).decode("utf-8")
        cls.event_hook = build.render_lua(
            cls.catalogue,
            HERE / "all-ravens-gameplay-events.lua",
            "-- @@RAVEN_STATE_ROWS@@",
            True,
        ).decode("utf-8")

    def test_authority_metadata_helpers_match_final_contract(self):
        router = build.router_contract()
        state = build.state_contract()
        self.assertTrue(router["native_generation_is_capture_freshness"])
        self.assertEqual(
            state["event_false_policy"],
            "defer alive state to atomic 53-Raven authority",
        )
        self.assertEqual(
            state["event_kill_overlay"],
            "persists across normal newer snapshots until explicit load boundary",
        )
        self.assertEqual(
            state["event_overlay_clear_policy"],
            "first strictly newer post-boundary atomic snapshot",
        )
        self.assertEqual(
            state["unknown_boundary_baseline_policy"],
            "first later readable snapshot establishes baseline only; next newer snapshot may apply",
        )
        self.assertEqual(
            state["load_boundary_sources"],
            ["EVT_LoadSaveData", "EVT_LoadSaveFile_Done", "OnRestoreCheckpoint"],
        )

    def test_rendered_lua_has_53_rows_and_native_delivery_contract(self):
        self.assertEqual(self.map_hook.count("{CatalogueId="), 53)
        for token in (
            'require, "socket.core"', 'connect("127.0.0.1", nativePort)',
            "CompletionistMapNative", "GetRavenSnapshot",
            "CompletionistMapV105ApplyPersistedRavenKills",
            'refreshNativeAuthority("map_create")', "staticDescriptorWrites=false",
        ):
            self.assertIn(token, self.map_hook)

    def test_rendered_event_hook_keeps_immediate_kill_path(self):
        self.assertEqual(self.event_hook.count("{CatalogueId="), 53)
        self.assertIn("ravenKilled ~= true", self.event_hook)
        self.assertIn("fn(row.CatalogueId, true, source)", self.event_hook)
        self.assertIn("CompletionistMapV105PublishRavenState", self.event_hook)

    def test_hooks_have_no_progression_write_or_polling_loop(self):
        forbidden = (
            "SetMarkerState", "SetToken", "SetProgress",
            "IncrementQuestProgress", "StartQuest",
        )
        for text in (self.map_hook, self.event_hook):
            for token in forbidden:
                self.assertNotIn(token, text)
        self.assertIn("permanentPolling=false", self.map_hook)
        self.assertIn("postLoadBoundedRefresh=true", self.map_hook)
        self.assertIn("positiveEventEvidenceOnly=true", self.map_hook)
        self.assertIn("atomicAuthorityClearsState=true", self.map_hook)
        self.assertIn("sessionKillOverlay=true", self.map_hook)
        self.assertIn("loadBoundaryClearsOverlay=true", self.map_hook)
        self.assertIn("unknownBoundaryBaselineConsumesOneCapture=true", self.map_hook)
        self.assertIn("restoreBoundedRetry=", self.event_hook)
        self.assertIn("positiveEvidenceOnly=true", self.event_hook)
        self.assertIn("restoreAuthorityBoundary=true", self.event_hook)


@unittest.skipUnless(exact_source_fixture_available(), "exact runtime-proven v3.3 source fixture not installed")
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

    def test_pool_capacity_matches_largest_realm(self):
        self.assertEqual(self.proof["proofs"][build.POOL]["raven_capacity_after"], 45)

    def test_lua_has_53_data_rows_and_exact_router_contract(self):
        text = self.outputs[build.MAP_LUA].decode("utf-8")
        suffix = text[text.index("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS"):]
        self.assertEqual(suffix.count("{CatalogueId="), 53)
        for token in (
            "exact_collision_object", "currMarkerID", "CompletionistRaven",
            "goMapIconCompletionistRaven", "markerIdAloneInfersRaven=false",
            "CompletionistMapV105TrackedCatalogueId", "Map.RecycleIcon",
            "CompletionistMapNative", "GetRavenSnapshot",
            "CompletionistMapV105ApplyPersistedRavenKills",
            'refreshNativeAuthority("map_create")', "staticDescriptorWrites=false",
        ):
            self.assertIn(token, suffix)

    def test_gameplay_hook_has_53_exact_state_rows(self):
        text = self.outputs[build.EVENT_LUA].decode("utf-8")
        suffix = text[text.index("-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS"):]
        self.assertEqual(suffix.count("{CatalogueId="), 53)
        self.assertIn("ravenKilled ~= true", suffix)
        self.assertIn("fn(row.CatalogueId, true, source)", suffix)
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

    def test_release_gate_open_for_native_snapshot_delivery(self):
        self.assertTrue(self.proof["ready_for_runtime_test"])
        self.assertEqual(
            self.proof["state"]["unloaded_instance_query"],
            "atomic 53-state native Raven snapshot",
        )
        self.assertTrue(self.proof["router"]["native_refresh_before_icon_sync"])
        self.assertTrue(self.proof["router"]["native_generation_is_capture_freshness"])
        self.assertEqual(
            self.proof["state"]["event_false_policy"],
            "defer alive state to atomic 53-Raven authority",
        )
        self.assertIn("OnRestoreCheckpoint", self.proof["state"]["load_boundary_sources"])
        self.assertFalse(self.proof["router"]["native_static_descriptor_writes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
