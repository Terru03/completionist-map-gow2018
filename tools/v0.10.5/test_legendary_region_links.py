"""Static Legendary RegionSummary link checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "legendary_region_links", HERE / "audit-legendary-region-links.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Legendary region-link audit tool missing")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class LegendaryRegionLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report(audit.native.GAME)

    def test_all_33_stay_unresolved_from_native_sources(self) -> None:
        report = self.report
        self.assertEqual(report["status"], "BLOCKED_ARCHITECTURE_MISMATCH")
        self.assertEqual(report["tracked_count"], 33)
        self.assertEqual(report["proven_unique_link_count"], 0)
        self.assertEqual(report["unresolved_link_count"], 33)
        self.assertEqual(report["proposed_target_count"], 18)
        self.assertEqual(report["proposed_target_goal_sum"], 33)
        self.assertEqual(report["native_dcb_files_scanned"], 561)
        self.assertEqual(report["native_dcb_identity_reference_hit_count"], 0)
        self.assertEqual(report["map_side_point_count"], 0)
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertEqual(report["interaction_script"]["player_region_call_line"], 436)
        self.assertTrue(all(row["link_status"] == "UNRESOLVED_NO_UNIQUE_NATIVE_LINK"
                            and row["source_level_to_player_region_edge"] is None
                            and row["map_world_point"] is None
                            and row["world_point_comparison"] == "UNAVAILABLE_NO_PER_CHEST_MAP_POINT"
                            and not row["exact_chest_to_target_edges"]
                            and row["link_diagnostics"]["missing_direct_edge"]
                            and row["link_diagnostics"]["indirect_target_only"]
                            and row["link_diagnostics"]["unresolved"]
                            and not row["link_diagnostics"]["ambiguous_direct_edges"]
                            and not row["link_diagnostics"]["duplicated_direct_edges"]
                            and len(row["mapmaster_target_string_offsets"]) == 1
                            and len(row["quests_target_string_offsets"]) == 1
                            and row["quests_target_record_offset"]
                            for row in report["rows"]))

    def test_existing_placement_inputs_are_unchanged(self) -> None:
        placements = json.loads(audit.PLACEMENTS.read_text(encoding="utf-8"))
        by_id = {row["catalogue_id"]: row for row in placements["rows"]}
        self.assertEqual(set(by_id), {row["catalogue_id"] for row in self.report["rows"]})
        for row in self.report["rows"]:
            with self.subTest(row=row["catalogue_id"]):
                placed = by_id[row["catalogue_id"]]
                self.assertEqual(row["physical_guid"], placed["physical_guid"])
                self.assertEqual(row["physical_world_point"], placed["world_position"])
                self.assertEqual(row["placement_transform_chain"], placed["transform_chain"])

    def test_target_name_and_same_point_cannot_promote_link(self) -> None:
        kwargs = {"physical_guid": "a", "target": "RegionSummary_LegendaryChest_Parent_X",
                  "map_world_point": [1.0, 2.0, 3.0], "proposed_target_exists": True}
        self.assertEqual(audit.classify_link(exact_identity_to_target_edges=[], **kwargs),
                         "UNRESOLVED_NO_UNIQUE_NATIVE_LINK")
        wrong = {"physical_guid": "b", "target": kwargs["target"],
                 "native_record_path": "wad:record"}
        self.assertEqual(audit.classify_link(exact_identity_to_target_edges=[wrong], **kwargs),
                         "UNRESOLVED_NO_UNIQUE_NATIVE_LINK")
        exact = {"physical_guid": "a", "target": kwargs["target"],
                 "native_record_path": "wad:record"}
        self.assertEqual(audit.classify_link(exact_identity_to_target_edges=[exact, exact], **kwargs),
                         "UNRESOLVED_NO_UNIQUE_NATIVE_LINK")
        self.assertEqual(audit.classify_link(exact_identity_to_target_edges=[exact],
                                             **{**kwargs, "proposed_target_exists": False}),
                         "UNRESOLVED_NO_UNIQUE_NATIVE_LINK")
        self.assertEqual(audit.classify_link(exact_identity_to_target_edges=[exact], **kwargs),
                         "PROVEN_UNIQUE_NATIVE_LINK")


if __name__ == "__main__":
    unittest.main()
