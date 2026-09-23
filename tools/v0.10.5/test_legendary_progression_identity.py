"""Fail-closed checks for the current 33 Legendary native identity links."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "legendary_progression_identity", HERE / "audit-legendary-progression-identity.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Legendary progression identity audit tool missing")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class LegendaryProgressionIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report(audit.catalogue_tools.GAME)

    def test_current_tracked_set_and_frozen_observations(self) -> None:
        report = self.report
        self.assertEqual(report["tracked_count"], 33)
        self.assertEqual(report["proven_local_persisted_bridge_count"], 30)
        self.assertEqual(report["derived_unobserved_local_bridge_count"], 3)
        self.assertEqual(report["native_serialized_state_key_count"], 33)
        self.assertEqual(report["state_carrier_guid_count"], 1)
        self.assertFalse(report["runtime_delivery_ready"])
        self.assertEqual({row["wad"] for row in report["rows"]
                          if not row["staged_exact_match"]},
                         {"xpl100_httk.wad", "cal500_runevault.wad",
                          "cal740_leftwing.wad"})
        self.assertEqual(len(report["current_rows_missing_prior_identity_snapshot"]), 2)
        self.assertEqual(len(report["prior_identity_snapshot_rows_outside_current_tracked_set"]), 2)

    def test_native_state_path_is_exact_placement_record(self) -> None:
        catalogue = json.loads(audit.CATALOGUE.read_text(encoding="utf-8"))
        current = {row["catalogue_id"]: row for row in catalogue["collectibles"]
                   if row.get("family") == "legendary_chest"
                   and row.get("native_classification") == "tracked_legendary"}
        self.assertEqual(set(current), {row["catalogue_id"] for row in self.report["rows"]})
        mismatches = set()
        for row in self.report["rows"]:
            with self.subTest(row=row["catalogue_id"]):
                source = current[row["catalogue_id"]]
                self.assertEqual(row["physical_guid"], source["native"]["instance_guid"])
                self.assertEqual(row["physical_state_key"], source["progression"]["instance_key"])
                self.assertEqual(row["world_position"], source["marker"]["position_world"])
                self.assertEqual(len(row["native_state_path_hits"]), 1)
                hit = row["native_state_path_hits"][0]
                self.assertEqual(hit["source_file"], row["wad"])
                self.assertEqual(hit["record_id"], source["native"]["placement_override_record_id"])
                self.assertEqual(row["native_state_path"], row["override_evidence"]["native_state_path"])
                self.assertFalse(row["native_dcb_key_hits"])
                self.assertFalse(row["pristine_lua_key_hits"])
                self.assertFalse(row["native_wad_other_key_hits"])
                if not row["catalogue_key_matches_native_path"]:
                    mismatches.add(row["physical_guid"])
                    self.assertFalse(row["logical_key_native_hits"])
        self.assertEqual(mismatches,
                         {"ace99ef5-472a-bcba-c29b-d2b396a3fdf3",
                          "d63295f2-44f3-3021-9b00-3c913c0dab69"})
        self.assertEqual(self.report["catalogue_state_path_mismatch_count"], 2)

    def test_quest_counts_do_not_prove_membership(self) -> None:
        report = self.report
        self.assertEqual(report["quest_target_count"], 18)
        self.assertEqual(report["quest_target_goal_sum"], 33)
        self.assertEqual(report["proven_per_chest_region_membership_count"], 0)
        self.assertTrue(all(not row["region_quest_membership_proven"]
                            and row["event_or_objective_identity"] is None
                            and not row["runtime_delivery_ready"]
                            for row in report["rows"]))

    def test_local_bridge_rejects_missing_or_duplicate_native_path(self) -> None:
        exact_hit = [{"record_id": "known"}]
        self.assertEqual(audit.bridge_status(native_path_hits=exact_hit,
                                             staged_exact=True, staged_represented=True),
                         "PROVEN_LOCAL_PERSISTED_STATE_BRIDGE")
        for hits in ([], exact_hit * 2):
            self.assertEqual(audit.bridge_status(native_path_hits=hits,
                                                 staged_exact=True, staged_represented=True),
                             "UNRESOLVED_NATIVE_STATE_PATH_WAD_LINK")
        self.assertEqual(audit.bridge_status(native_path_hits=exact_hit,
                                             staged_exact=False, staged_represented=False),
                         "DERIVED_LOCAL_KEY_NO_FROZEN_STATE_OBSERVATION")
        self.assertEqual(audit.bridge_status(native_path_hits=exact_hit,
                                             staged_exact=False, staged_represented=True),
                         "UNRESOLVED_FROZEN_STATE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
