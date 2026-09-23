"""Read-only proof for one forced Legendary pin on the frozen Raven release."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("legendary_live_test_builder", HERE / "build-legendary-live-test-marker.py")
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")


class LegendaryLiveTestProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs, cls.proof = BUILDER.generate(GAME)

    def test_target_state_is_enabled_not_opened(self):
        target = self.proof["target"]
        self.assertEqual(target["catalogue_id"], BUILDER.TARGET_ID)
        self.assertEqual(target["physical_guid"], BUILDER.TARGET_GUID)
        self.assertEqual(target["serialized_state_key_hex"], BUILDER.TARGET_SERIALIZED_KEY)
        self.assertEqual(struct.unpack("<f", bytes.fromhex(target["frozen_raw_state"])[1:])[0], 1.0)
        self.assertEqual(target["native_state_enum"], {"ENABLED": 1, "OPENED": 4})
        self.assertFalse(target["frozen_state_is_opened"])
        self.assertEqual(target["world_position"], list(BUILDER.TARGET_WORLD))

    def test_only_one_diagnostic_added_to_53_ravens(self):
        self.assertEqual(self.proof["proofs"]["mapmaster"]["candidate_marker_count"], 436)
        self.assertEqual(self.proof["proofs"]["mapcoords"]["candidate_coordinate_count"], 459)
        self.assertEqual(self.proof["proofs"]["ui_pool"]["rows_added"], 1)
        self.assertEqual(self.proof["proofs"]["map_lua"]["raven_authority_row_count_unchanged"], 53)
        self.assertEqual(self.outputs[BUILDER.raven.EVENT_LUA], BUILDER.release_sources()[BUILDER.raven.EVENT_LUA])

    def test_proven_map_and_compass_calls_remain(self):
        lua = self.outputs[BUILDER.raven.MAP_LUA].decode("utf-8")
        self.assertEqual(lua.count("local legendaryLiveTest ="), 1)
        for token in ("Map.FindRegionFromMarker(info.Id)", "Map.CreateMarkerIcon(info.Id, region, \"\")",
                      "MapOn.MapCollisionChangeHandler", 'local ravenClass = "CompletionistRaven"',
                      "game.Compass.ShowMarker(selected.Name, ravenClass)",
                      "Legendary Chest - LIVE TEST", "LEGENDARY_LIVE_TEST_MAP_PIN",
                      "LEGENDARY_LIVE_TEST_COMPASS"):
            self.assertIn(token, lua)
        self.assertNotIn("byCatalogueId[legendaryLiveTest.CatalogueId]", lua)
        self.assertTrue(self.proof["proofs"]["map_lua"]["diagnostic_forced_visible"])
        self.assertFalse(self.proof["proofs"]["map_lua"]["auto_route_on_map_open"])

    def test_float16_point_is_reconstructed_and_bounded(self):
        self.assertEqual(self.proof["map_point_delivered_float16"], [237.0, 0.9677734375, -30.203125])
        self.assertLess(max(abs(x) for x in self.proof["map_point_error_xyz"]), 0.05)

    def test_unsupported_source_fails_closed(self):
        original = BUILDER.SUPPORTED_INSTALLED[BUILDER.raven.MASTER]
        try:
            BUILDER.SUPPORTED_INSTALLED[BUILDER.raven.MASTER] = "0" * 64
            with self.assertRaisesRegex(ValueError, "unsupported installed native file"):
                BUILDER.generate(GAME)
        finally:
            BUILDER.SUPPORTED_INSTALLED[BUILDER.raven.MASTER] = original

    def test_archived_raven_bridge_matches_build_record(self):
        base = BUILDER.REPO / "archive/legendary-live-test/raven-bridge-base"
        manifest = json.loads((base / "bridge-build-manifest.json").read_text())
        self.assertEqual(BUILDER.sha((base / "Release/dxgi.dll").read_bytes()), manifest["dll_sha256"])
        self.assertEqual(manifest["supported_exe_sha256"], BUILDER.SUPPORTED_EXE_SHA)


if __name__ == "__main__":
    unittest.main()
