"""Behavior tests for fail-closed multi-family UI model."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from collectible_runtime_model import CollectibleRuntimeModel, normalize_uid


class CollectibleRuntimeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads((REPO / "config" / "collectibles" / "v0.10.5" /
                                    "all-collectibles.json").read_text(encoding="utf-8"))
        rows = cls.catalogue["collectibles"]
        cls.parent = next(row for row in rows if row["family"] == "nornir_chest"
                          and row["realm"] == "Midgard")
        cls.children = [row for row in rows
                        if row["progression"].get("parent_catalogue_id") == cls.parent["catalogue_id"]]
        cls.seal_parent = next(row for row in rows if row["family"] == "nornir_chest"
                               and any(child["family"] == "nornir_seal" for child in rows
                                       if child["progression"].get("parent_catalogue_id") == row["catalogue_id"]))
        cls.seals = [row for row in rows
                     if row["progression"].get("parent_catalogue_id") == cls.seal_parent["catalogue_id"]]
        cls.a = next(row for row in rows if row["family"] == "artefact" and row["realm"] == "Midgard")
        cls.b = next(row for row in rows if row["family"] == "legendary_chest"
                     and row["realm"] == cls.a["realm"]
                     and row.get("production_eligibility") == "tracked_collectible")
        cls.excluded_legendary = next(
            row for row in rows
            if row["family"] == "legendary_chest"
            and row.get("production_eligibility", "").startswith("exclude_"))
        cls.unresolved_legendary = next(
            row for row in rows
            if row["family"] == "legendary_chest"
            and row.get("production_eligibility") == "unresolved")
        cls.rollout = json.loads(
            (REPO / "config" / "collectibles" / "v0.10.5" /
             "family-rollout.json").read_text(encoding="utf-8"))

    def model(self, enabled_families=None):
        return CollectibleRuntimeModel(self.catalogue, enabled_families=enabled_families)

    def test_unknown_state_hides_every_parent(self):
        model = self.model()
        model.open_map("Midgard")
        self.assertEqual(model.map_icons, set())

    def test_exact_remaining_and_complete(self):
        model = self.model()
        model.open_map(self.a["realm"])
        model.observe(self.a["catalogue_id"], False)
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        model.observe(self.a["catalogue_id"], True)
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

    def test_realm_and_family_filters(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.observe(self.b["catalogue_id"], False)
        model.open_map(self.a["realm"], {self.a["family"]})
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        self.assertNotIn(self.b["catalogue_id"], model.map_icons)

    def test_nornir_children_need_known_unopened_parent(self):
        model = self.model()
        model.open_map(self.parent["realm"])
        for child in self.children:
            model.observe(child["catalogue_id"], False)
            self.assertNotIn(child["catalogue_id"], model.map_icons)
        model.observe(self.parent["catalogue_id"], False)
        self.assertTrue(any(child["catalogue_id"] in model.map_icons for child in self.children))
        model.observe(self.parent["catalogue_id"], True)
        self.assertTrue(all(child["catalogue_id"] not in model.map_icons for child in self.children))

    def test_seal_needs_exact_individual_loaded_state(self):
        model = self.model()
        model.open_map(self.seal_parent["realm"])
        model.observe(self.seal_parent["catalogue_id"], False)
        self.assertTrue(all(row["catalogue_id"] not in model.map_icons for row in self.seals))
        model.observe(self.seals[0]["catalogue_id"], False)
        self.assertIn(self.seals[0]["catalogue_id"], model.map_icons)
        model.observe(self.seals[0]["catalogue_id"], True)
        self.assertNotIn(self.seals[0]["catalogue_id"], model.map_icons)


    def test_non_collectible_legendary_rows_never_render(self):
        model = self.model()
        for row in (self.excluded_legendary, self.unresolved_legendary):
            model.observe(row["catalogue_id"], False)
            model.open_map(row["realm"])
            self.assertNotIn(row["catalogue_id"], model.map_icons)
            self.assertIsNone(model.collide(row["catalogue_id"]))

    def test_runtime_family_gate_is_independent_from_user_filter(self):
        model = self.model(enabled_families={"artefact"})
        model.observe(self.a["catalogue_id"], False)
        model.observe(self.b["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        self.assertNotIn(self.b["catalogue_id"], model.map_icons)

    def test_rollout_contract_matches_static_catalogue(self):
        families = self.rollout["families"]
        counts = {}
        for row in self.catalogue["collectibles"]:
            counts[row["family"]] = counts.get(row["family"], 0) + 1
        for family in (
            "artefact", "lore_marker", "legendary_chest", "nornir_chest",
            "nornir_seal", "nornir_bell", "nornir_mechanism",
        ):
            self.assertEqual(families[family]["static_rows"], counts[family])
            self.assertFalse(families[family]["runtime_enabled"])
        self.assertEqual(self.rollout["catalogue_rows"], sum(counts.values()))
        self.assertEqual(families["legendary_chest"]["tracked_collectible_rows"], 33)
        self.assertEqual(families["legendary_chest"]["excluded_trial_reward_rows"], 27)
        self.assertEqual(families["legendary_chest"]["unresolved_rows"], 4)
        self.assertEqual(families["nornir_chest"]["tracked_native_target"], 21)
        self.assertEqual(families["nornir_chest"]["exact_binding_pass_rows"], 0)
        self.assertEqual(families["nornir_chest"]["blocked_exact_binding_rows"], 22)

    def test_numeric_marker_id_normalization(self):
        uid = self.a["marker"]["uid"]
        self.assertEqual(normalize_uid(uid.lower()), uid)
        self.assertEqual(normalize_uid(int(uid, 16)), uid)
        self.assertEqual(normalize_uid(f"0x{uid}"), uid)
        self.assertIsNone(normalize_uid("not-an-id"))

    def test_exact_collision_then_uid_owns_click(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertEqual(model.collide(self.a["catalogue_id"]), self.a["catalogue_id"])
        self.assertEqual(model.click(self.a["marker"]["uid"]), "shown")
        self.assertEqual(model.active_target, ("custom", self.a["catalogue_id"]))

    def test_wrong_or_uid_only_click_delegates(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertEqual(model.click(self.a["marker"]["uid"]), "delegate")
        model.collide(self.a["catalogue_id"])
        self.assertEqual(model.click(self.b["marker"]["uid"]), "delegate")

    def test_custom_stock_and_custom_custom_replacement(self):
        model = self.model()
        for row in (self.a, self.b):
            model.observe(row["catalogue_id"], False)
        model.open_map(self.a["realm"])
        model.click_other("stock", "dock")
        model.collide(self.a["catalogue_id"])
        model.click(self.a["marker"]["uid"])
        self.assertEqual(model.active_target, ("custom", self.a["catalogue_id"]))
        model.collide(self.b["catalogue_id"])
        model.click(self.b["marker"]["uid"])
        self.assertEqual(model.active_target, ("custom", self.b["catalogue_id"]))
        model.click_other("stock", "dock")
        self.assertEqual(model.active_target, ("stock", "dock"))

    def test_second_same_click_removes_only_same_target(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        for expected in ("shown", "removed"):
            model.collide(self.a["catalogue_id"])
            self.assertEqual(model.click(self.a["marker"]["uid"]), expected)
        self.assertIsNone(model.active_target)

    def test_completion_removes_only_owned_active_target(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        model.active_target = ("stock", "dock")
        model.observe(self.a["catalogue_id"], True)
        self.assertEqual(model.active_target, ("stock", "dock"))
        model.observe(self.a["catalogue_id"], False)
        model.collide(self.a["catalogue_id"])
        model.click(self.a["marker"]["uid"])
        model.observe(self.a["catalogue_id"], True)
        self.assertIsNone(model.active_target)

    def test_save_change_clears_cache_and_ui(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        model.load_save()
        self.assertTrue(all(value == "unknown" for value in model.state.values()))
        self.assertEqual(model.map_icons, set())
        self.assertIsNone(model.active_target)

    def test_teardown_and_bounded_retry(self):
        model = self.model()
        self.assertEqual([model.retry("x") for _ in range(4)], [True, True, True, False])
        model.open_map("Midgard")
        model.teardown()
        self.assertEqual(model.map_icons, set())
        self.assertFalse(model.permanent_polling)


if __name__ == "__main__":
    unittest.main(verbosity=2)
