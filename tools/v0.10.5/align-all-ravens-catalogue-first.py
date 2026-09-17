#!/usr/bin/env python3
"""Align stale all-Ravens release tests/proof with catalogue-first runtime semantics.

This intentionally does not touch game files. It updates only the offline builder,
its Lua/build tests, and the fake-game transaction test. Every replacement is
exactly guarded so unexpected source drift aborts instead of silently editing the
wrong code.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path.name}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"PATCHED {path.name}: {label}")


def main() -> None:
    build = HERE / "build-all-ravens-release-candidate.py"
    build_test = HERE / "test_all_ravens_build.py"
    lua_test = HERE / "test_all_ravens_lua.py"
    transaction = HERE / "test-all-ravens-transaction.ps1"

    replace_once(
        build,
        '''        "result": "ALL_RAVENS_OFFLINE_CANDIDATE_BUILT_STATE_GATE_BLOCKED",
        "branch": "codex/all-ravens-release-candidate",''',
        '''        "result": "ALL_RAVENS_OFFLINE_CANDIDATE_READY_FOR_RUNTIME_TEST",
        "branch": "codex/all-collectibles-production-research",''',
        "open runtime-test result and record active research branch",
    )

    replace_once(
        build,
        '''        "state": {
            "native_field": "ravenKilled",
            "loaded_instance_match": "exact parent quest plus unique native world position",
            "writes_progression": False,
            "unloaded_instance_query": "unresolved",
            "unknown_state_policy": "hide marker fail-closed",
        },
        "ready_for_runtime_test": False,
        "blocking_issue": "No proven read-only API can query ravenKilled for an unloaded Raven WAD instance.",''',
        '''        "state": {
            "native_field": "ravenKilled",
            "loaded_instance_match": "exact parent quest plus unique native world position",
            "writes_progression": False,
            "unloaded_instance_query": "not required for catalogue-first baseline",
            "unknown_state_policy": "show catalogue marker unless confirmed killed",
            "persisted_kill_bootstrap": True,
            "loaded_runtime_events_override": True,
        },
        "ready_for_runtime_test": True,
        "blocking_issue": None,
        "known_limitation": (
            "Persisted killed-Raven IDs are not yet automatically sourced from the loaded save; "
            "until that bridge is wired, an existing save initially shows catalogue Ravens not "
            "yet confirmed killed by the runtime event bridge."
        ),''',
        "align release proof with catalogue-first runtime semantics",
    )

    replace_once(
        build,
        '''    print("ready_for_runtime_test=false")''',
        '''    print("ready_for_runtime_test=true")''',
        "print open runtime-test gate",
    )

    replace_once(
        build_test,
        '''    def test_release_gate_closed_for_unloaded_state(self):
        self.assertFalse(self.proof["ready_for_runtime_test"])
        self.assertEqual(self.proof["state"]["unloaded_instance_query"], "unresolved")''',
        '''    def test_release_gate_open_for_catalogue_first_runtime(self):
        self.assertTrue(self.proof["ready_for_runtime_test"])
        self.assertEqual(
            self.proof["state"]["unknown_state_policy"],
            "show catalogue marker unless confirmed killed",
        )
        self.assertTrue(self.proof["state"]["persisted_kill_bootstrap"])''',
        "align build test with catalogue-first gate",
    )

    replace_once(
        lua_test,
        '''function probe.reset() return CompletionistMapV105ResetRavenStates("save_load") end
''',
        '''function probe.reset() return CompletionistMapV105ResetRavenStates("save_load") end
function probe.persistedOne(id)
  return CompletionistMapV105ApplyPersistedRavenKills({id},"test")
end
''',
        "expose persisted-kill bootstrap to Lua test",
    )

    replace_once(
        lua_test,
        '''    def test_unknown_hidden_restore_and_teardown(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 0)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 1)
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.iconCount(), 0)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 1)
        self.probe.teardown()
        self.assertEqual(self.probe.iconCount(), 0)

    def test_save_load_reset_clears_state_and_target_fail_closed(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.reset()
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIsNone(self.probe.tracked())
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 0)
''',
        '''    def test_catalogue_visible_by_default_restore_and_teardown(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.publish(self.a["catalogue_id"], True)
        self.assertEqual(self.probe.iconCount(), 1)
        self.probe.publish(self.a["catalogue_id"], False)
        self.assertEqual(self.probe.iconCount(), 2)
        self.probe.teardown()
        self.assertEqual(self.probe.iconCount(), 0)

    def test_persisted_kill_bootstrap_hides_only_confirmed_raven(self):
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
        ok, accepted = self.probe.persistedOne(self.a["catalogue_id"])
        self.assertTrue(ok)
        self.assertEqual(accepted, 1)
        self.assertEqual(self.probe.iconCount(), 1)
        self.assertIsNone(self.probe.icon(self.a["marker"]["name"]))
        self.assertIsNotNone(self.probe.icon(self.b["marker"]["name"]))

    def test_save_load_reset_clears_state_and_target_catalogue_defaults_visible(self):
        self.probe.publish(self.a["catalogue_id"], False)
        self.probe.open()
        self.probe.click(self.a["marker"]["name"])
        self.assertEqual(self.probe.tracked(), self.a["catalogue_id"])
        self.probe.reset()
        self.assertEqual(self.probe.iconCount(), 0)
        self.assertIsNone(self.probe.tracked())
        self.probe.open()
        self.assertEqual(self.probe.iconCount(), 2)
''',
        "align Lua lifecycle tests and cover persisted kills",
    )

    replace_once(
        transaction,
        "Assert-True (-not [bool]$proof.ready_for_runtime_test) 'Release gate unexpectedly open.'",
        "Assert-True ([bool]$proof.ready_for_runtime_test) 'Release gate is not open.'",
        "require open release gate in fake-game transaction test",
    )

    replace_once(
        transaction,
        "    $branch = 'codex/all-ravens-release-candidate'",
        "    $branch = 'codex/all-collectibles-production-research'",
        "record active research branch in transaction manifest",
    )

    replace_once(
        transaction,
        '''            release_gate_closed = $true''',
        '''            release_gate_open = $true''',
        "record open gate in transaction proof",
    )

    print("ALL_RAVENS_CATALOGUE_FIRST_ALIGNMENT_APPLIED")


if __name__ == "__main__":
    main()
