"""Behavior coverage for N-Raven routing and lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from raven_runtime_model import RavenRuntimeModel


class RavenRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads((REPO / "catalogue" / "odins-ravens.json").read_text(encoding="utf-8"))
        cls.a = cls.catalogue["ravens"][0]
        cls.b = next(row for row in cls.catalogue["ravens"] if row["realm"] == cls.a["realm"] and row != cls.a)
        cls.other_realm = next(row for row in cls.catalogue["ravens"] if row["realm"] != cls.a["realm"])

    def model(self):
        return RavenRuntimeModel(self.catalogue)

    def arm(self, model, row):
        self.assertEqual(model.collide(f"object:{row['catalogue_id']}"), row["catalogue_id"])

    def test_realm_filtering(self):
        model = self.model()
        for row in self.catalogue["ravens"]:
            model.observe(row["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        self.assertNotIn(self.other_realm["catalogue_id"], model.map_icons)
        self.assertTrue(all(model.rows[key]["realm"] == self.a["realm"] for key in model.map_icons))

    def test_collected_hidden_uncollected_shown_and_mixed_save(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], True)
        model.observe(self.b["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertIn(self.b["catalogue_id"], model.map_icons)

    def test_fully_collected_and_fresh_simulation(self):
        model = self.model()
        for row in self.catalogue["ravens"]:
            model.observe(row["catalogue_id"], True)
        model.open_map("Midgard")
        self.assertEqual(model.map_icons, set())
        for row in self.catalogue["ravens"]:
            model.observe(row["catalogue_id"], False)
        self.assertEqual(len(model.map_icons), 45)

    def test_unknown_state_fails_closed(self):
        model = self.model()
        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

    def test_a_b_and_b_a_replacement(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.observe(self.b["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "shown")
        self.arm(model, self.b)
        self.assertEqual(model.click_raven(self.b["marker"]["uid"]), "shown")
        self.assertEqual(model.active_target, ("raven", self.b["catalogue_id"]))
        self.arm(model, self.a)
        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "shown")
        self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))

    def test_stock_and_nornir_replacement_both_directions(self):
        for family in ("stock", "nornir"):
            model = self.model()
            model.observe(self.a["catalogue_id"], False)
            model.open_map(self.a["realm"])
            model.click_other(family, "x")
            self.arm(model, self.a)
            model.click_raven(self.a["marker"]["uid"])
            self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))
            model.click_other(family, "x")
            self.assertEqual(model.active_target, (family, "x"))

    def test_same_raven_second_click_removes(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        model.click_raven(self.a["marker"]["uid"])
        self.arm(model, self.a)
        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "removed")
        self.assertIsNone(model.active_target)

    def test_stale_selection_cannot_hijack_other_raven_or_stock(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.observe(self.b["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        self.assertEqual(model.click_raven(self.b["marker"]["uid"]), "delegate")
        self.assertIsNone(model.active_target)
        self.arm(model, self.a)
        self.assertEqual(model.click_raven("stock-uid"), "delegate")
        self.assertIsNone(model.active_target)

    def test_incidental_collision_noise_preserves_exact_candidate_until_uid_resolution(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)

        # Real map callbacks can contain unrelated collision churn between the exact
        # Raven collision and the human click. There is deliberately no TTL.
        for _ in range(5):
            model.incidental_collision()
            self.assertIsNone(model.collide("stock:incidental-noise"))
            self.assertEqual(model.selection, self.a["catalogue_id"])

        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "shown")
        self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))

        # A genuinely different prompt UID must disarm/delegate instead of letting a
        # stale Raven candidate hijack a stock target.
        self.arm(model, self.a)
        model.incidental_collision()
        self.assertEqual(model.click_raven("stock-uid"), "delegate")
        self.assertIsNone(model.selection)
        self.assertEqual(model.active_target, ("raven", self.a["catalogue_id"]))

    def test_marker_id_alone_never_infers_raven(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.assertEqual(model.click_raven(self.a["marker"]["uid"]), "delegate")

    def test_exact_uid_required_after_exact_collision(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        self.assertEqual(model.click_raven("wrong"), "delegate")

    def test_legacy_proven_bridge_is_only_nil_uid_exception(self):
        proven = next(row for row in self.catalogue["ravens"] if row["marker"]["name"] == "Completionist_V103_Veithurgard_Raven_01")
        other = next(row for row in self.catalogue["ravens"] if row != proven and row["realm"] == proven["realm"])
        model = self.model()
        model.observe(proven["catalogue_id"], False)
        model.observe(other["catalogue_id"], False)
        model.open_map(proven["realm"])
        self.arm(model, proven)
        self.assertEqual(model.click_raven(None, legacy_proven_bridge=True), "shown")
        self.arm(model, other)
        self.assertEqual(model.click_raven(None, legacy_proven_bridge=True), "delegate")

    def test_kill_tracked_a_removes_a_only(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        model.click_raven(self.a["marker"]["uid"])
        model.observe(self.a["catalogue_id"], True)
        self.assertIsNone(model.active_target)
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

    def test_killing_a_does_not_remove_b_or_stock(self):
        for target in (("raven", self.b["catalogue_id"]), ("stock", "dock")):
            model = self.model()
            model.observe(self.a["catalogue_id"], False)
            model.observe(self.b["catalogue_id"], False)
            model.open_map(self.a["realm"])
            model.active_target = target
            model.observe(self.a["catalogue_id"], True)
            self.assertEqual(model.active_target, target)

    def test_restore_uncollected_reappears_and_recollects(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], True)
        model.open_map(self.a["realm"])
        model.restore(self.a["catalogue_id"], False)
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        self.arm(model, self.a)
        model.click_raven(self.a["marker"]["uid"])
        model.observe(self.a["catalogue_id"], True)
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertIsNone(model.active_target)

    def test_teardown_cleans_ui_and_no_permanent_polling(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        model.teardown_map()
        self.assertEqual(model.map_icons, set())
        self.assertIsNone(model.selection)
        self.assertFalse(model.permanent_polling)

    def test_loading_other_save_clears_all_cached_state_fail_closed(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        model.click_raven(self.a["marker"]["uid"])
        model.load_save()
        self.assertTrue(all(value == "unknown" for value in model.state.values()))
        self.assertEqual(model.map_icons, set())
        self.assertIsNone(model.selection)
        self.assertIsNone(model.active_target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
