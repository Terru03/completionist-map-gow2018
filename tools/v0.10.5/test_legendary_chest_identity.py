#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

import legendary_chest_identity as identity


HERE = Path(__file__).resolve().parent
CATALOGUE = HERE.parents[1] / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"
RESOLVER_PATH = HERE / "resolve-legendary-serialized-identities-static.py"

_spec = importlib.util.spec_from_file_location("_legendary_static_resolver_test", RESOLVER_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"unable to load resolver: {RESOLVER_PATH}")
resolver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = resolver
_spec.loader.exec_module(resolver)


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
                self.assertGreaterEqual(len(skipped), 1)
                skipped_names = {
                    item["source_record_name"] for item in skipped
                }
                self.assertIn("gochest_legendary_parent", skipped_names)
                self.assertTrue(
                    all(
                        item["reason"] in {
                            "organizational_scene_wrapper",
                            "reusable_parent_container",
                        }
                        for item in skipped
                    )
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


    def test_runtime_proven_xpl250_identity_vector_and_hash(self):
        row = next(
            item for item in self.rows
            if item["catalogue_id"] == "legendary_chest_d6d6acfe444f2ad10b49cea2ba85a1eb"
        )
        scene, skipped = identity.scene_identity_elements(row)
        self.assertEqual(
            [item.hex() for item in scene],
            [
                "d507eb21a5b18f45bc5265b60f30fd1c",
                "8e825d9cee977f42b76892e6e4509f4d",
                "feacd6d6d12a4f44a2ce490beba185ba",
                "30c16eb3812d4240b49d3a1254d63108",
            ],
        )
        self.assertEqual(len(skipped), 1)
        self.assertEqual(
            identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
            "947a7c50b25f004ea3365dd8dc232ee1",
        )
        self.assertEqual(
            identity.identity_hash(scene + [identity.CHEST_OWN_IDENTITY_ELEMENT]),
            0x748BE60F37BAB846,
        )

    def test_structural_rule_omits_organizational_wrappers(self):
        row = next(
            item for item in self.rows
            if item["catalogue_id"] == "legendary_chest_c14a0f2b4559d859347854bccb307f63"
        )
        scene, skipped = identity.scene_identity_elements(row)
        expected_indices = [5, 4, 2, 0]
        expected = [
            identity.adjusted_record_id(
                row["source"]["transform_chain"][index]["record_id"]
            )
            for index in expected_indices
        ]
        self.assertEqual(scene, expected)
        self.assertIn(
            "goloot",
            {item["source_record_name"] for item in skipped},
        )

    def test_structural_rule_keeps_locked_chest_object_but_omits_parent(self):
        row = next(
            item for item in self.rows
            if item["catalogue_id"] == "legendary_chest_ace99ef5472abcbac29bd2b396a3fdf3"
        )
        scene, skipped = identity.scene_identity_elements(row)
        expected_indices = [7, 6, 4, 2, 0]
        expected = [
            identity.adjusted_record_id(
                row["source"]["transform_chain"][index]["record_id"]
            )
            for index in expected_indices
        ]
        self.assertEqual(scene, expected)
        skipped_names = {
            item["source_record_name"] for item in skipped
        }
        self.assertIn("gochest_legendary_locked_roots_parent", skipped_names)
        self.assertNotIn("gochestobj", skipped_names)

    def test_unstaged_xpl100_identity_is_structurally_deterministic(self):
        row = next(
            item for item in self.rows
            if item["catalogue_id"] == "legendary_chest_890a24d24d2864a1567af691c615870f"
        )
        scene, skipped = identity.scene_identity_elements(row)
        expected_indices = [5, 4, 2, 0]
        expected = [
            identity.adjusted_record_id(
                row["source"]["transform_chain"][index]["record_id"]
            )
            for index in expected_indices
        ]
        self.assertEqual(scene, expected)
        self.assertIn(
            "gocontainers",
            {item["source_record_name"] for item in skipped},
        )

    def test_structural_resolver_contract_is_pinned(self):
        self.assertEqual(resolver.EXPECTED_TRACKED, 33)
        self.assertEqual(resolver.EXPECTED_STAGED, 32)
        self.assertEqual(
            resolver.SIMPLE_STATE_CLASS,
            "0x75E050AB149B4062",
        )
        self.assertEqual(
            identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
            "947a7c50b25f004ea3365dd8dc232ee1",
        )

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
