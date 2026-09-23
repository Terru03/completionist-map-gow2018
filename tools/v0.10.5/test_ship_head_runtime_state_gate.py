"""Fail-closed checks for the pinned live Ship Head staged-state capture."""
from __future__ import annotations

import copy
import json
import unittest

import ship_head_runtime_state_gate as gate


class ShipHeadRuntimeStateGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = json.loads(gate.CAPTURE.read_text(encoding="utf-8"))

    def test_pinned_capture_proves_eight_global_staged_lookups(self):
        report = gate.assess(self.capture)
        self.assertEqual(report["status"], "BLOCKED_HEAD08_UNRESOLVED")
        self.assertEqual(report["global_staged_lookup_proven_count"], 8)
        self.assertEqual(report["global_staged_lookup_proven_numbers"], [1, 2, 3, 4, 5, 6, 7, 9])
        self.assertEqual(report["unresolved_numbers"], [8])
        self.assertTrue(report["all_ship_head_wads_present"])
        self.assertTrue(report["head08_wad_present"])
        self.assertFalse(report["runtime_generation_allowed"])

    def test_missing_target_wad_is_rejected(self):
        capture = copy.deepcopy(self.capture)
        capture["scope"]["all_ship_head_wads_present"] = False
        capture["scope"]["target_wads_missing"] = ["cal100_hub.wad"]
        capture["scope"]["target_wads_present"].remove("cal100_hub.wad")
        with self.assertRaisesRegex(ValueError, "WAD coverage"):
            gate.assess(capture)

    def test_ambiguous_exact_state_is_rejected(self):
        capture = copy.deepcopy(self.capture)
        row = next(row for row in capture["ship_heads"] if row["number"] == 4)
        row["exact_state_match_count"] = 2
        with self.assertRaisesRegex(ValueError, "exact live state differs"):
            gate.assess(capture)

    def test_head08_presence_requires_new_transition_proof(self):
        capture = copy.deepcopy(self.capture)
        row = next(row for row in capture["ship_heads"] if row["number"] == 8)
        row["exact_state_match_count"] = 1
        row["state_values"] = [3.0]
        row["authority"] = "live_staged_exact_key"
        with self.assertRaisesRegex(ValueError, "Head 08 unexpectedly changed"):
            gate.assess(capture)

    def test_runtime_write_contract_is_rejected(self):
        capture = copy.deepcopy(self.capture)
        capture["safety"]["process_memory_written"] = True
        with self.assertRaisesRegex(ValueError, "safety contract"):
            gate.assess(capture)


if __name__ == "__main__":
    unittest.main()
