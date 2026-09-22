#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

import legendary_chest_identity as identity


HERE = Path(__file__).resolve().parent
CATALOGUE = HERE.parents[1] / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"


class LegendaryChestIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        cls.rows = identity.tracked_rows(cls.catalogue)

    def test_static_production_partition_is_pinned(self):
        contract = identity.static_contract(self.catalogue)
        self.assertEqual(contract["raw"], 64)
        self.assertEqual(contract["tracked"], 33)
        self.assertEqual(contract["trial_excluded"], 27)
        self.assertEqual(contract["unresolved"], 4)
        self.assertEqual(contract["unique_scene_identities"], 33)

    def test_tracked_rows_are_exact_opened_state_collectibles(self):
        for row in self.rows:
            with self.subTest(row=row["catalogue_id"]):
                self.assertEqual(row["native_classification"], "tracked_legendary")
                self.assertEqual(row["production_eligibility"], "tracked_collectible")
                self.assertEqual(
                    row["progression"]["state_adapter"],
                    "interact_chest_standard_checkpoint_state",
                )
                self.assertEqual(row["progression"]["field"], "state == OPENED")
                self.assertTrue(row["progression"]["read_only"])
                self.assertIsNotNone(row["progression"]["parent_quest"])

    def test_scene_identity_contract_is_unique_and_structural(self):
        seen = set()
        for row in self.rows:
            scene, skipped = identity.scene_identity_elements(row)
            with self.subTest(row=row["catalogue_id"]):
                self.assertGreaterEqual(len(scene), 2)
                self.assertEqual(len(skipped), 2)
                self.assertEqual(
                    {item["reason"] for item in skipped},
                    {
                        "nested_reusable_state_subobject",
                        "nested_reusable_legendary_parent",
                    },
                )
                self.assertNotIn(tuple(scene), seen)
                seen.add(tuple(scene))
        self.assertEqual(len(seen), 33)


    def test_physical_placement_anchor_may_repeat_but_full_scene_is_unique(self):
        anchors = {}
        scenes = {}
        for row in self.rows:
            placement = row["source"]["transform_chain"][2]
            anchor = identity.adjusted_record_id(
                placement["record_id"]
            ).hex()
            anchors.setdefault(anchor, []).append(row["catalogue_id"])
            scene, _ = identity.scene_identity_elements(row)
            scenes.setdefault(tuple(scene), []).append(row["catalogue_id"])

        repeated = {
            key: value for key, value in anchors.items()
            if len(value) > 1
        }
        self.assertEqual(len(anchors), 32)
        self.assertEqual(len(repeated), 1)
        self.assertEqual(
            sorted(next(iter(repeated.values()))),
            sorted([
                "legendary_chest_ace99ef5472abcbac29bd2b396a3fdf3",
                "legendary_chest_d63295f244f330219b003c913c0dab69",
            ]),
        )
        self.assertEqual(len(scenes), 33)
        self.assertTrue(all(len(value) == 1 for value in scenes.values()))

    def test_native_wad_name_hash_matches_known_algorithm(self):
        self.assertEqual(
            identity.registry_hash_for_wad("alf600_templeint.wad"),
            0x6EFCEDEEF433D3AF,
        )
        self.assertEqual(
            identity.registry_hash_for_wad("hel100_calderaheldressing.wad"),
            0x140093A4B32510D3,
        )

    def test_serialized_payload_is_flag_plus_two_hashes(self):
        payload = identity.serialized_payload(
            0x1122334455667788,
            0x99AABBCCDDEEFF00,
        )
        self.assertEqual(len(payload), 17)
        self.assertEqual(payload[0], 1)
        self.assertEqual(
            payload.hex(),
            "01887766554433221100ffeeddccbbaa99",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
