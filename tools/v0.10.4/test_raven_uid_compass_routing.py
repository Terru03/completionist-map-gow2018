"""Offline acceptance checks for the UID-aware shared-Raven compass probe."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location(
        "uid_routing", HERE / "build-raven-uid-compass-routing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RavenUidCompassRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load()
        cls.root = Path(
            os.environ.get(
                "COMPLETIONIST_RAVEN_ROOT",
                "G:/SteamLibrary/steamapps/common/GodOfWar",
            )
        )
        cls.files, cls.proof = cls.p.generate(cls.root)
        cls.shared_files, cls.shared_proof = cls.p.shared.generate(cls.root)
        cls.routing = cls.p.ROUTING_PATH.read_text(encoding="utf-8")

    def test_scope_is_exact_shared_loader_four_files(self):
        self.assertEqual(set(self.files), set(self.shared_files))
        self.assertEqual(len(self.files), 4)
        self.assertNotIn("exec/wad/pc_le/r_ui.wad", self.files)
        self.assertNotIn("exec/dc/pc_le/compassgraph.dcb", self.files)

    def test_binary_candidate_is_byte_identical_to_runtime_proven_shared_loader(self):
        for rel in (self.p.shared.MASTER, self.p.shared.COORDS, self.p.shared.UI):
            self.assertEqual(self.files[rel], self.shared_files[rel])

    def test_lua_is_append_only_on_shared_loader_candidate(self):
        before = self.shared_files[self.p.LUA]
        after = self.files[self.p.LUA]
        self.assertTrue(after.startswith(before))
        self.assertEqual(after[len(before):], self.p.routing_bytes())

    def test_two_native_marker_uids_remain_distinct_and_share_map_loader(self):
        ids = self.proof["identities"]
        self.assertNotEqual(ids["raven_uid"], ids["twin_uid"])
        self.assertEqual(ids["shared_map_loader"], "goMapIconCompletionistRaven")
        self.assertEqual(ids["compass_class"], "CompletionistRaven")

    def test_selection_uses_exact_live_object_references(self):
        required = (
            "collision == self.completionistSharedLoaderTwinGO",
            "collision == self.completionistMapV100MapIconGO",
            'return identity(twinName), "twin_object_reference"',
            'return identity(ravenName), "raven_object_reference"',
        )
        for token in required:
            self.assertIn(token, self.routing)

    def test_native_marker_identity_is_looked_up_after_object_disambiguation(self):
        self.assertIn("game.Map.GetMarkerInfo(name)", self.routing)
        self.assertIn("Id = info.Id", self.routing)
        self.assertIn("IdString = tostring(info.Id)", self.routing)

    def test_selected_native_name_is_routed_to_proven_custom_compass_class(self):
        self.assertIn("game.Compass.ShowMarker(selected.Name, ravenClass)", self.routing)
        self.assertIn("game.Compass.HideMarker(selected.Name)", self.routing)
        self.assertIn("game.Compass.FindMarkersByIconClass({ravenClass})", self.routing)

    def test_single_active_replacement_paths_are_present(self):
        self.assertIn('hideCustomTargets("raven_uid_replace", selected.IdString)', self.routing)
        self.assertIn('hideStockTargets("raven_uid_replace")', self.routing)
        self.assertIn('STOCK_REPLACE_TWIN', self.routing)
        self.assertEqual(self.proof["expected_runtime_matrix"]["maximum_active_user_target"], 1)

    def test_no_resource_identity_or_lifecycle_expansion(self):
        contract = self.proof["routing_contract"]
        self.assertFalse(contract["new_wad_resource_identity"])
        self.assertFalse(contract["compassgraph_changed"])
        self.assertFalse(contract["lifecycle_changes"])
        self.assertFalse(contract["synthetic_progression_writes"])
        for token in ("SetMarkerState", "challengeComplete", "OPENED", "SetToken", "SetProgress"):
            self.assertNotIn(token, self.routing)

    def test_deterministic_output(self):
        second, second_proof = self.p.generate(self.root)
        self.assertEqual(self.files, second)
        self.assertEqual(self.proof, second_proof)


if __name__ == "__main__":
    unittest.main()
