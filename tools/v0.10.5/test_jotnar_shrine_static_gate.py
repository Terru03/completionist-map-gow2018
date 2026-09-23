"""Jotnar Shrine native Triptych evidence regression tests."""
from __future__ import annotations

import json
import unittest

import audit_jotnar_shrines_native as audit


class JotnarShrineStaticGateTests(unittest.TestCase):
    def test_archive_keeps_count_gap_and_fail_closed(self):
        report = json.loads((audit.REPO / "docs/research/jotnar-shrine-static-gate.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_FAIL_CLOSED")
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertEqual(report["native_objective"]["target"], 11)
        self.assertEqual(report["named_raw_placement_count"], 14)
        self.assertEqual(report["exact_duplicate_raw_placement_count"], 1)
        self.assertEqual(report["named_distinct_placement_count"], 13)
        self.assertEqual(report["quest_script_wad_placement_count"], 11)
        self.assertEqual(report["story_context_placement_count"], 2)
        self.assertFalse(report["exact_per_object_objective_membership_proven"])
        self.assertFalse(report["persistent_unloaded_completion_proven"])
        self.assertTrue(all(not row["marker_generation_ready"] for row in
                            report["distinct_placements"]))
        self.assertIn("gotryptich_overrideInst",
                      {row["override_name"] for row in report["raw_placements"]})
        self.assertNotIn("gotryptich_light_burst_overrideInst",
                         {row["override_name"] for row in report["raw_placements"]})

    def test_fresh_shipped_resource_scan_matches_archive(self):
        archived = json.loads((audit.REPO / "docs/research/jotnar-shrine-static-gate.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(audit.scan(), archived)


if __name__ == "__main__":
    unittest.main()
