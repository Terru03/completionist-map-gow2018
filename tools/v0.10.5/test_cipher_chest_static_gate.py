"""Cipher Chest source audit and fail-closed tests."""
from __future__ import annotations

import json
import unittest

import audit_cipher_chests_native as audit


class CipherChestStaticGateTests(unittest.TestCase):
    def test_archived_gate_keeps_quest_targets_apart_from_chest_count(self):
        report = json.loads((audit.REPO / "docs/research/cipher-chest-static-gate.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_FAIL_CLOSED")
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertEqual(report["native_language_piece_target_sum"], 8)
        self.assertEqual(report["external_guide_chest_count_user_baseline"], 13)
        self.assertEqual({x["target"] for x in
                          report["native_language_quest_targets"].values()}, {4})
        self.assertEqual(report["matching_wad_count"], 123)
        self.assertEqual(report["shared_standard_chest_script_wad_count"], 119)
        self.assertEqual(report["non_script_cipher_literal_records"], [])
        self.assertFalse(report["physical_cipher_chest_census_proven"])
        self.assertEqual(report["physical_cipher_chest_rows"], [])
        self.assertFalse(report["per_object_cipher_reward_identity_proven"])

    def test_fresh_native_scan_matches_archive(self):
        report = json.loads((audit.REPO / "docs/research/cipher-chest-static-gate.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(audit.scan(), report)


if __name__ == "__main__":
    unittest.main()
