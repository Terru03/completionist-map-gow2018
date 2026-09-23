"""Read-only Realm Tear evidence gate tests."""
from __future__ import annotations

from collections import Counter
import json
import unittest

import audit_realm_tear_native as audit


class RealmTearStaticGateTests(unittest.TestCase):
    def test_archived_gate_retains_count_split_and_fail_closed_state(self):
        path = audit.REPO / "docs/research/realm-tear-static-gate.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_FAIL_CLOSED")
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertFalse(report["physical_encounter_census_proven"])
        self.assertEqual(report["physical_encounter_rows"], [])
        self.assertEqual(report["native_summary_target_sum"], 19)
        self.assertEqual(report["direct_parent_callback_carrier_count"], 14)
        self.assertEqual(sum(report["unlocated_target_slots_by_summary"].values()), 5)
        self.assertEqual(Counter(row["parent_summary"] for row in
                                 report["parent_callback_carriers"])[
                                     "RegionSummary_CALS_PocketRift_Parent"], 4)
        self.assertTrue(report["native_marker_call_clues"])
        self.assertFalse(report["native_marker_coverage_proven"])

    def test_fresh_shipped_resource_scan_matches_archive(self):
        path = audit.REPO / "docs/research/realm-tear-static-gate.json"
        archived = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(audit.scan(), archived)


if __name__ == "__main__":
    unittest.main()
