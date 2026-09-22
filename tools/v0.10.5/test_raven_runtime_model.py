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
        model.open_map("Midgard")
        self.assertEqual(len(model.map_icons), 45)
        for row in self.catalogue["ravens"]:
            model.observe(row["catalogue_id"], True)
        self.assertEqual(model.map_icons, set())
        self.assertEqual(model.apply_persisted_kills([]), 0)
        self.assertEqual(len(model.map_icons), 45)

    def test_unknown_state_defaults_visible(self):
        model = self.model()
        model.open_map(self.a["realm"])
        self.assertIn(self.a["catalogue_id"], model.map_icons)

    def test_persisted_kill_bootstrap_hides_only_confirmed_ids(self):
        model = self.model()
        self.assertEqual(model.apply_persisted_kills([self.a["catalogue_id"]]), 1)
        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertIn(self.b["catalogue_id"], model.map_icons)
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")
        self.assertEqual(model.state[self.b["catalogue_id"]], "unknown")

    def test_persisted_kill_bootstrap_ignores_unknown_ids(self):
        model = self.model()
        self.assertEqual(model.apply_persisted_kills(["not-a-raven", self.a["catalogue_id"]]), 1)
        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertIn(self.b["catalogue_id"], model.map_icons)

    def test_native_generation_is_monotonic_and_same_generation_does_not_churn(self):
        model = self.model()
        self.assertEqual(model.apply_native_snapshot(2, [self.a["catalogue_id"]]), "applied")
        self.assertEqual(model.apply_native_snapshot(2, []), "stale")
        self.assertEqual(model.apply_native_snapshot(1, []), "stale")
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")
        self.assertEqual(model.apply_native_snapshot(3, []), "applied")
        self.assertEqual(model.state[self.a["catalogue_id"]], "unknown")

    def test_false_gameplay_event_never_clears_confirmed_kill(self):
        model = self.model()
        self.assertEqual(
            model.apply_native_snapshot(6, [self.a["catalogue_id"]]), "applied"
        )
        self.assertEqual(
            model.observe_event(self.a["catalogue_id"], False), "deferred"
        )
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")

    def test_immediate_event_survives_periodic_snapshot_until_epoch_capture(self):
        model = self.model()
        model.open_map(self.a["realm"])
        self.assertEqual(model.apply_native_snapshot(1, []), "applied")
        self.assertEqual(
            model.observe_event(self.a["catalogue_id"], True), "applied"
        )
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

        self.assertEqual(model.apply_native_snapshot(2, []), "applied")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

        epoch = model.notify_load_boundary()
        self.assertEqual(model.apply_native_snapshot(200, []), "boundary_wait")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertEqual(
            model.apply_boundary_snapshot(epoch, 201, []), "applied"
        )
        self.assertIn(self.a["catalogue_id"], model.map_icons)

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

    def test_boundary_rejects_periodic_and_wrong_epoch_even_when_newer(self):
        model = self.model()
        self.assertEqual(
            model.apply_native_snapshot(4, [self.a["catalogue_id"]]), "applied"
        )
        model.open_map(self.a["realm"])
        epoch = model.notify_load_boundary()

        self.assertEqual(model.apply_native_snapshot(500, []), "boundary_wait")
        self.assertEqual(
            model.apply_boundary_snapshot(epoch + 1, 501, []),
            "boundary_epoch_mismatch",
        )
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

        self.assertEqual(
            model.apply_boundary_snapshot(epoch, 502, []), "applied"
        )
        self.assertNotEqual(model.state[self.a["catalogue_id"]], "collected")
        self.assertIn(self.a["catalogue_id"], model.map_icons)

    def test_boundary_not_ready_refuses_even_matching_epoch(self):
        model = self.model()
        self.assertEqual(
            model.apply_native_snapshot(4, [self.a["catalogue_id"]]), "applied"
        )
        epoch = model.notify_load_boundary(capture_ready=False)
        self.assertEqual(
            model.apply_boundary_snapshot(epoch, 5, []), "boundary_not_ready"
        )
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")

    def test_restore_false_waits_for_fresh_atomic_authority(self):
        model = self.model()
        self.assertEqual(
            model.apply_native_snapshot(4, [self.a["catalogue_id"]]), "applied"
        )
        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

        self.assertEqual(model.restore(self.a["catalogue_id"], False), "deferred")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        epoch = model.authority_boundary_epoch
        self.assertEqual(model.apply_native_snapshot(50, []), "boundary_wait")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

        self.assertEqual(
            model.apply_boundary_snapshot(epoch, 51, []), "applied"
        )
        self.assertIn(self.a["catalogue_id"], model.map_icons)

    def test_restore_true_may_hide_immediately_while_boundary_reconciles(self):
        model = self.model()
        self.assertEqual(model.apply_native_snapshot(2, []), "applied")
        model.open_map(self.a["realm"])
        self.assertIn(self.a["catalogue_id"], model.map_icons)
        self.assertEqual(model.restore(self.a["catalogue_id"], True), "applied")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        epoch = model.authority_boundary_epoch
        self.assertEqual(
            model.apply_boundary_snapshot(
                epoch, 3, [self.a["catalogue_id"]]
            ),
            "applied",
        )
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)

    def test_teardown_cleans_ui_and_no_permanent_polling(self):
        model = self.model()
        model.observe(self.a["catalogue_id"], False)
        model.open_map(self.a["realm"])
        self.arm(model, self.a)
        model.teardown_map()
        self.assertEqual(model.map_icons, set())
        self.assertIsNone(model.selection)
        self.assertFalse(model.permanent_polling)

    def test_loading_other_save_preserves_last_good_state_until_fresh_snapshot(self):
        model = self.model()
        self.assertEqual(
            model.apply_native_snapshot(10, [self.a["catalogue_id"]]), "applied"
        )
        model.open_map(self.a["realm"])
        model.load_save()
        self.assertEqual(model.state[self.a["catalogue_id"]], "collected")
        self.assertEqual(model.map_icons, set())
        self.assertIsNone(model.selection)
        self.assertIsNone(model.active_target)

        model.open_map(self.a["realm"])
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        epoch = model.authority_boundary_epoch
        self.assertEqual(model.apply_native_snapshot(100, []), "boundary_wait")
        self.assertNotIn(self.a["catalogue_id"], model.map_icons)
        self.assertEqual(
            model.apply_boundary_snapshot(epoch, 101, []), "applied"
        )
        self.assertIn(self.a["catalogue_id"], model.map_icons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
