"""Ship Head source integrity and fail-closed checks."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

import ship_head_static_gate as gate


class ShipHeadStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(gate.CATALOGUE.read_text(encoding="utf-8"))
        cls.audit = json.loads(gate.AUDIT.read_text(encoding="utf-8"))

    def assess_changed(self, change):
        catalogue = copy.deepcopy(self.catalogue)
        audit = copy.deepcopy(self.audit)
        row = next(row for row in catalogue["collectibles"]
                   if row["family"] == "artefact" and row.get("subtype") == "Ship Head")
        change(row, audit)
        audit["catalogue_sha256"] = hashlib.sha256(
            gate.canonical_json(catalogue).encode()).hexdigest()
        return gate.assess(catalogue, audit)

    def test_nine_source_rows_hold_runtime_off(self):
        report = gate.assess(self.catalogue, self.audit)
        self.assertEqual(report["physical_count"], 9)
        self.assertEqual(report["transform_path_count"], 13)
        self.assertEqual(report["proposed_instance_key_count"], 13)
        self.assertEqual([row["number"] for row in report["rows"]], list(range(1, 10)))
        self.assertFalse(report["runtime_generation_allowed"])
        with self.assertRaisesRegex(ValueError, "Ship Head generation blocked"):
            gate.require_generation_ready(report)

    def test_parent_literals_in_exact_shipped_wad_overrides(self):
        report = gate.assess(self.catalogue, self.audit)
        gate.verify_native_parent_attributes(self.catalogue, report)
        self.assertEqual(report["native_parent_attribute_count"], 9)

    def test_wad_check_rejects_invented_parent_literal(self):
        report = gate.assess(self.catalogue, self.audit)
        report["rows"][0]["parent_quest"] = "RegionSummary_Fake_Shiphead_Parent"
        with self.assertRaisesRegex(ValueError, "parent quest not on own script override"):
            gate.verify_native_parent_attributes(self.catalogue, report)

    def test_script_proves_acquired_three_and_cals_fixup_path(self):
        report = gate.assess(self.catalogue, self.audit)
        gate.verify_artifact_script(self.audit, report)
        self.assertEqual(report["acquired_state_numeric"], 3)
        self.assertTrue(report["scripted_cals_fixup_path_proven"])
        self.assertEqual(report["regional_target_delta"][
            "RegionSummary_BSW_Shiphead_Parent"], 1)
        self.assertEqual(report["regional_target_delta"][
            "RegionSummary_BW_Shiphead_Parent"], -1)
        self.assertFalse(report["runtime_generation_allowed"])

    def test_script_accounting_rejects_changed_region_target(self):
        audit = copy.deepcopy(self.audit)
        audit["tracked_summary_targets"]["RegionSummary_BW_Shiphead_Parent"]["target"] = 2
        report = gate.assess(self.catalogue, self.audit)
        with self.assertRaisesRegex(ValueError, "physical/target totals changed"):
            gate.verify_artifact_script(audit, report)

    def test_frozen_staged_keys_match_eight_and_leave_row_eight_blocked(self):
        report = gate.assess(self.catalogue, self.audit)
        gate.verify_frozen_staged_identity(self.catalogue, report)
        self.assertEqual(report["frozen_staged_identity_count"], 8)
        self.assertEqual(report["frozen_unresolved_numbers"], [8])
        self.assertEqual(sum(row["frozen_staged_identity_proven"]
                             for row in report["rows"]), 8)
        self.assertTrue(all(not row["serialized_save_lookup_proven"]
                            for row in report["rows"]))
        self.assertFalse(report["runtime_generation_allowed"])

    def test_frozen_identity_rejects_catalogue_wad_digest_change(self):
        catalogue = copy.deepcopy(self.catalogue)
        row = next(row for row in catalogue["collectibles"]
                   if row.get("subtype") == "Ship Head")
        row["source"]["wad_sha256"] = "0" * 64
        report = gate.assess(self.catalogue, self.audit)
        with self.assertRaisesRegex(ValueError, "catalogue WAD digest differs"):
            gate.verify_frozen_staged_identity(catalogue, report)

    def test_audit_digest_tamper_rejected(self):
        catalogue = copy.deepcopy(self.catalogue)
        catalogue["collectibles"][0]["display_name"] = "changed"
        with self.assertRaisesRegex(ValueError, "digest differs"):
            gate.assess(catalogue, self.audit)

    def test_parent_attribute_must_be_on_native_object(self):
        with self.assertRaisesRegex(ValueError, "native parent attribute missing"):
            self.assess_changed(lambda row, _audit:
                                row["native"]["attribute_values"].remove(
                                    row["progression"]["parent_quest"]))

    def test_proposed_key_must_follow_carrier_path(self):
        with self.assertRaisesRegex(ValueError, "proposed keys differ"):
            self.assess_changed(lambda row, _audit:
                                row["progression"]["instance_keys"].clear())

    def test_target_gap_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "native accounting differs"):
            self.assess_changed(lambda _row, audit:
                                audit["ship_head_accounting"].update(tracked_target=9))

    def test_unloaded_state_claim_cannot_be_promoted_without_proof(self):
        with self.assertRaisesRegex(ValueError, "state claim changed"):
            self.assess_changed(lambda row, _audit:
                                row["progression"].update(unloaded_query="proven"))

    def test_marker_world_point_must_match_native_transform(self):
        with self.assertRaisesRegex(ValueError, "transform path differs"):
            self.assess_changed(lambda row, _audit:
                                row["marker"].update(position_world=[0, 0, 0]))


if __name__ == "__main__":
    unittest.main()
