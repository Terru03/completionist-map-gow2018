"""Fail-closed tests for master collectible inventory policy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("master_inventory", HERE / "build-master-collectible-inventory.py")
assert SPEC and SPEC.loader
inv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inv)


class MasterCollectibleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(inv.DEFAULT_POLICY.read_text(encoding="utf-8"))

    def test_valkyrie_never_duplicates_native_marker(self):
        marker, source = inv.marker_policy(self.policy, "valkyrie", None)
        self.assertEqual(marker, "NATIVE_MARKER_NO_DUPLICATE")
        self.assertEqual(source, "family_policy")

    def test_gateway_and_shop_never_duplicate_native_markers(self):
        self.assertEqual(inv.marker_policy(self.policy, "mystic_gateway", None)[0], "NATIVE_MARKER_NO_DUPLICATE")
        self.assertEqual(inv.marker_policy(self.policy, "shop", None)[0], "NATIVE_MARKER_NO_DUPLICATE")

    def test_unknown_family_fails_closed(self):
        marker, source = inv.marker_policy(self.policy, "mystery_collectible", None)
        self.assertEqual(marker, "RESEARCH_REQUIRED")
        self.assertEqual(source, "default_fail_closed")

    def test_guide_count_never_authorizes_runtime_marker(self):
        row = {
            "catalogue_id": "raven_test",
            "family": "raven",
            "realm_id": "midgard",
            "region_id": "test",
            "native": {"instance_guid": "00000000-0000-0000-0000-000000000001"},
            "marker": {"position_world": [1, 2, 3]},
        }
        normalized = inv.normalize(row, Path("fixture.json"), self.policy)
        self.assertEqual(normalized["mod_marker_policy"], "CUSTOM_MARKER_CANDIDATE")
        self.assertFalse(normalized["mod_marker_allowed"])
        self.assertIn("never authorizes", normalized["marker_block_reason"])

    def test_ship_head_subtype_remains_candidate_but_not_authorized(self):
        row = {
            "catalogue_id": "artefact_test",
            "family": "artefact",
            "subtype": "Ship Head",
            "native": {"instance_guid": "00000000-0000-0000-0000-000000000002"},
        }
        normalized = inv.normalize(row, Path("fixture.json"), self.policy)
        self.assertEqual(normalized["mod_marker_policy"], "CUSTOM_MARKER_CANDIDATE")
        self.assertEqual(normalized["mod_marker_policy_source"], "subtype_override")
        self.assertFalse(normalized["mod_marker_allowed"])

    def test_conflicting_duplicate_physical_rows_are_rejected(self):
        a = {"catalogue_id": "x", "physical_id": "g", "family": "artefact", "source_row_sha256": "a"}
        b = {"catalogue_id": "x", "physical_id": "g", "family": "artefact", "source_row_sha256": "b"}
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            inv.dedupe([a, b])

    def test_external_expected_count_is_audit_only(self):
        audit = inv.discrepancy(self.policy, [])
        raven = next(x for x in audit if x["family"] == "odin_raven")
        self.assertEqual(raven["guide_expected"], 51)
        self.assertEqual(raven["inventory_rows"], 0)
        self.assertEqual(raven["status"], "NATIVE_INVENTORY_UNDER_GUIDE")

    def test_empty_catalogue_is_valid_incomplete_input(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.json"
            p.write_text("", encoding="utf-8")
            self.assertEqual(inv.load_catalogue(p), [])


if __name__ == "__main__":
    unittest.main()
