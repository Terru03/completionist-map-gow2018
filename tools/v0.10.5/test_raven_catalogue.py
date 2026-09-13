"""Tests for native Raven extraction and strict catalogue validation."""
from __future__ import annotations

import copy
from collections import Counter
import json
import math
from pathlib import Path
import sys
import unittest

import jsonschema


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import raven_catalogue as rc


GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")


class TransformTests(unittest.TestCase):
    def test_parent_transform_rebuilds_proven_veithurgard_point(self):
        local = rc.identity_transform()[0], (-122.306938, 17.487385, -78.850899)
        root = (0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0), (14.0, -4.5, 665.0)
        world = rc.transform_point(rc.compose(root, local), (0.0, 0.0, 0.0))
        self.assertLess(math.dist(world, rc.PROVEN_NATIVE_WORLD), 0.001)

    def test_hash_keeps_proven_uid(self):
        self.assertEqual(f"{rc.name_hash(rc.PROVEN_NAME):016X}", rc.PROVEN_UID)


@unittest.skipUnless(GAME.is_dir(), "native game fixture not installed")
class NativeCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue, cls.audit = rc.build_catalogue(GAME)

    def test_complete_native_object_count(self):
        self.assertEqual(len(self.catalogue["ravens"]), 53)
        self.assertEqual(self.audit["native_labor_target_count"], 51)
        self.assertEqual(self.audit["native_hidden_surplus_count"], 2)

    def test_catalogue_matches_json_schema(self):
        schema = json.loads((HERE.parent.parent / "catalogue" / "odins-ravens.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(self.catalogue)

    def test_unique_identities_and_uids(self):
        rows = self.catalogue["ravens"]
        for getter in (
            lambda row: row["catalogue_id"],
            lambda row: row["native"]["instance_guid"],
            lambda row: row["marker"]["uid"],
        ):
            values = [getter(row) for row in rows]
            self.assertEqual(len(values), len(set(values)))

    def test_expected_realm_distribution(self):
        self.assertEqual(self.audit["catalogue_validation"]["realms"], {"Alfheim": 2, "Helheim": 6, "Midgard": 45})

    def test_expected_native_region_distribution(self):
        expected = {
            "Alfheim": 2, "BeachCave": 2, "BeachMaze": 1, "BeachShipwreck": 1,
            "BeachTower": 1, "BeachWaterfall": 1, "CalderaShores": 2,
            "Foothills": 2, "Forest": 1, "ForestDungeon": 5, "HTTK": 5,
            "Helheim": 6, "HuldraMine01": 1, "HuldraMine02": 2,
            "HuldraStronghold": 2, "IslandArch": 1, "IslandShipwreck": 1,
            "MasonTrail": 1, "Peakspass": 4, "Riverpass": 7,
            "Stonemason": 2, "VikingFuneral": 3,
        }
        self.assertEqual(Counter(row["region"] for row in self.catalogue["ravens"]), expected)
        self.assertEqual(self.audit["catalogue_validation"]["regions"], expected)

    def test_surplus_native_parents_are_documented(self):
        surplus_parents = set(self.audit["parent_surplus"])
        for row in self.catalogue["ravens"]:
            if row["progression"]["parent_quest"] in surplus_parents:
                self.assertIn("parent_has_one_hidden_surplus_raven", row["special_handling"])

    def test_every_row_has_position_and_state_source(self):
        validation = self.audit["catalogue_validation"]
        self.assertTrue(validation["all_positions_valid"])
        self.assertTrue(validation["all_entries_have_state_oracle"])
        self.assertTrue(validation["all_entries_have_position_source"])

    def test_midgard_projection_is_plausible(self):
        for row in self.catalogue["ravens"]:
            if row["realm"] != "Midgard":
                continue
            x, _y, z = row["marker"]["position_world"]
            map_x = 0.004 * z + 0.0625431
            map_z = -0.004 * x + 0.6101961
            self.assertLess(abs(map_x), 10.0)
            self.assertLess(abs(map_z), 10.0)

    def test_proven_raven_stays_frozen(self):
        row, = [row for row in self.catalogue["ravens"] if row["marker"]["uid"] == rc.PROVEN_UID]
        self.assertEqual(row["marker"]["name"], rc.PROVEN_NAME)
        self.assertEqual(tuple(row["marker"]["position_world"]), rc.PROVEN_AUTHORED_WORLD)

    def test_duplicate_uid_rejected(self):
        broken = copy.deepcopy(self.catalogue)
        broken["ravens"][1]["marker"]["uid"] = broken["ravens"][0]["marker"]["uid"]
        with self.assertRaisesRegex(ValueError, "duplicate marker_uid"):
            rc.validate_catalogue(broken)

    def test_malformed_entry_rejected(self):
        broken = copy.deepcopy(self.catalogue)
        broken["ravens"][0]["marker"]["position_world"] = [0.0, 0.0, 0.0]
        with self.assertRaisesRegex(ValueError, "zero/default"):
            rc.validate_catalogue(broken)

    def test_release_gate_stays_closed_without_unloaded_state_query(self):
        self.assertFalse(self.audit["ready_for_runtime_test"])
        self.assertEqual(self.catalogue["state_oracle"]["unloaded_instance_query"], "unresolved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
