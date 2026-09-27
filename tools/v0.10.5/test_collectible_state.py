"""Tri-state collection store: epoch isolation, collection terminal, snapshot validation."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT.parent / "completionist-map-gow2018/dist/re-tools"))
from lupa.lua51 import LuaRuntime

STATE_LUA = HERE / "collectible-state.lua"


def load_state(lua: LuaRuntime):
    """Load the State module into a Lua runtime and return the constructor table."""
    source = STATE_LUA.read_text(encoding="utf-8")
    return lua.execute(source)


class StateConstructionTest(unittest.TestCase):
    def test_new_creates_store_with_unknown_defaults(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")
        self.assertEqual(s.Revision(s), 0)

    def test_new_rejects_empty_list(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        with self.assertRaises(Exception):
            State.New(lua.table())

    def test_new_rejects_duplicate_ids(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        with self.assertRaises(Exception):
            State.New(lua.table("chest_a", "chest_a"))

    def test_new_rejects_non_string_ids(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        with self.assertRaises(Exception):
            State.New(lua.table(42))

    def test_new_rejects_empty_string_ids(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        with self.assertRaises(Exception):
            State.New(lua.table(""))


class StateObserveTest(unittest.TestCase):
    def test_repeated_zero_epoch_cannot_clear_collected(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        state = load_state(lua).New(lua.table("a"))
        state.BeginEpoch(state, 0)
        state.Observe(state, "a", "collected", 0)
        revision = state.Revision(state)
        state.BeginEpoch(state, 0)
        self.assertEqual(state.Get(state, "a"), "collected")
        self.assertEqual(state.Revision(state), revision)

    def test_observe_collected_within_epoch(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        s.BeginEpoch(s, 1)
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Get(s, "chest_a"), "collected")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")

    def test_observe_remaining(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertTrue(s.Observe(s, "chest_a", "remaining", 1))
        self.assertEqual(s.Get(s, "chest_a"), "remaining")

    def test_duplicate_observe_no_revision_increase(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        revision = s.Revision(s)
        # Same observation again: accepted but no revision bump
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Revision(s), revision)

    def test_collection_is_terminal_within_epoch(self):
        """Once collected, remaining observation cannot revert within same epoch."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        revision = s.Revision(s)
        # Remaining after collected: accepted but state stays collected
        self.assertTrue(s.Observe(s, "chest_a", "remaining", 1))
        self.assertEqual(s.Get(s, "chest_a"), "collected")
        self.assertEqual(s.Revision(s), revision)

    def test_observe_rejects_unknown_id(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertFalse(s.Observe(s, "not_in_catalogue", "collected", 1))

    def test_observe_rejects_invalid_state(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertFalse(s.Observe(s, "chest_a", "unknown", 1))
        self.assertFalse(s.Observe(s, "chest_a", "opened", 1))

    def test_observe_rejects_stale_epoch(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.BeginEpoch(s, 2)
        self.assertFalse(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")


class StateEpochTest(unittest.TestCase):
    def test_new_epoch_resets_all_states_to_unknown(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "collected", 1)
        s.Observe(s, "chest_b", "remaining", 1)
        self.assertEqual(s.Get(s, "chest_a"), "collected")
        s.BeginEpoch(s, 2)
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")

    def test_stale_epoch_observe_rejected_after_advance(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "collected", 1)
        s.BeginEpoch(s, 2)
        # Stale epoch 1 observation must not hide pin in epoch 2
        self.assertFalse(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")

    def test_epoch_revision_increases(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        rev1 = s.Revision(s)
        s.Observe(s, "chest_a", "collected", 1)
        rev2 = s.Revision(s)
        self.assertGreater(rev2, rev1)
        s.BeginEpoch(s, 2)
        rev3 = s.Revision(s)
        self.assertGreater(rev3, rev2)

    def test_begin_epoch_rejects_backward_epoch(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 2)
        with self.assertRaises(Exception):
            s.BeginEpoch(s, 1)

    def test_begin_epoch_rejects_same_epoch(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        with self.assertRaises(Exception):
            s.BeginEpoch(s, 1)


class StateSnapshotTest(unittest.TestCase):
    def test_snapshot_applies_remaining_to_unknown(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        s.BeginEpoch(s, 1)
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "remaining"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "remaining")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")

    def test_snapshot_cannot_override_collected(self):
        """A delayed snapshot saying 'remaining' cannot revive a pin collected later."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "collected", 1)
        # Snapshot says remaining, but live collection wins
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "remaining"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "collected")

    def test_snapshot_after_epoch_reset_applies_remaining(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "collected", 1)
        s.BeginEpoch(s, 2)
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "remaining"}), 2))
        self.assertEqual(s.Get(s, "chest_a"), "remaining")

    def test_snapshot_rejects_stale_epoch(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.BeginEpoch(s, 2)
        self.assertFalse(s.ApplySnapshot(s, lua.table_from({"chest_a": "collected"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")

    def test_snapshot_rejects_unknown_id(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertFalse(s.ApplySnapshot(s, lua.table_from({"not_real": "remaining"}), 1))
        # Partial mutations must not occur
        self.assertEqual(s.Get(s, "chest_a"), "unknown")

    def test_snapshot_rejects_invalid_state_value(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        self.assertFalse(s.ApplySnapshot(s, lua.table_from({"chest_a": "opened"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")

    def test_partial_snapshot_leaves_others_unchanged(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b", "chest_c"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "remaining", 1)
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_b": "collected"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "remaining")
        self.assertEqual(s.Get(s, "chest_b"), "collected")
        self.assertEqual(s.Get(s, "chest_c"), "unknown")

    def test_snapshot_with_unknown_does_not_erase_remaining(self):
        """A snapshot may send 'unknown' for unproved entries; it must not erase accepted remaining."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        s.BeginEpoch(s, 1)
        s.Observe(s, "chest_a", "remaining", 1)
        # Snapshot with unknown: must not downgrade remaining to unknown
        # Note: The spec says unknown in snapshot can be sent for unproved entries.
        # But the store should not downgrade. Let's check the implementation handles this.
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "unknown"}), 1))
        # Unknown snapshot should not override remaining (it's not "collected" terminal
        # rule, but semantic: unknown means "no info", not "definitely not collected")
        # Current implementation: ApplySnapshot skips if current == "collected" only.
        # For remaining -> unknown, the snapshot DOES apply since "remaining" != "collected".
        # This is actually correct behavior: a snapshot is the restored state authority.
        actual = s.Get(s, "chest_a")
        # The snapshot is authoritative: if it says unknown, it means unknown.
        self.assertEqual(actual, "remaining")

    def test_rejected_snapshot_leaves_no_partial_mutation(self):
        """If validation fails, no states should have changed."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        s.BeginEpoch(s, 1)
        # First item valid, second item invalid: whole snapshot rejected
        self.assertFalse(s.ApplySnapshot(s, lua.table_from({
            "chest_a": "remaining",
            "not_real": "collected"
        }), 1))
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")


class StateGetUnknownIdTest(unittest.TestCase):
    def test_get_returns_nil_for_unknown_id(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a"))
        self.assertIsNone(s.Get(s, "not_in_catalogue"))


class StateFullPlanScenarioTest(unittest.TestCase):
    """End-to-end scenario matching the plan's inline test code."""

    def test_plan_inline_scenario(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        State = load_state(lua)
        s = State.New(lua.table("chest_a", "chest_b"))
        s.BeginEpoch(s, 1)
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Get(s, "chest_a"), "collected")
        self.assertEqual(s.Get(s, "chest_b"), "unknown")
        revision = s.Revision(s)
        # Duplicate collected: accepted, no revision change
        self.assertTrue(s.Observe(s, "chest_a", "collected", 1))
        self.assertEqual(s.Revision(s), revision)
        # Snapshot with remaining cannot override collected
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "remaining"}), 1))
        self.assertEqual(s.Get(s, "chest_a"), "collected")
        # New epoch resets everything
        s.BeginEpoch(s, 2)
        self.assertEqual(s.Get(s, "chest_a"), "unknown")
        # Stale epoch 1 observation rejected
        self.assertFalse(s.Observe(s, "chest_a", "collected", 1))
        # Snapshot with current epoch works
        self.assertTrue(s.ApplySnapshot(s, lua.table_from({"chest_a": "remaining"}), 2))
        self.assertEqual(s.Get(s, "chest_a"), "remaining")
        # Unknown ID rejected
        self.assertFalse(s.Observe(s, "not_in_catalogue", "collected", 2))


if __name__ == "__main__":
    unittest.main()
