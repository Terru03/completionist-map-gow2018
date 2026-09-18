#!/usr/bin/env python3
"""Deterministic offline tests for v0.10.5 collectible family visibility."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODULE_PATH = HERE / "collectible-family-visibility.py"
ROLLOUT_PATH = REPO / "config/collectibles/v0.10.5/family-rollout.json"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load_module():
    spec = importlib.util.spec_from_file_location("collectible_family_visibility", MODULE_PATH)
    check(spec is not None and spec.loader is not None, "could not load visibility module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    vis = load_module()
    rollout = vis.load_rollout(ROLLOUT_PATH)
    validation = vis.validate_rollout(rollout)

    check(validation["valid"] is True, "rollout validation failed")
    check(validation["families"] == 8, "family count changed")
    check(validation["fail_closed"] is True, "fail-closed invariant changed")
    check(validation["writes"] is False, "visibility core gained write capability")

    raven_rows = [
        {"state_key": "raven-alive", "name": "alive"},
        {"state_key": "raven-dead", "name": "dead"},
        {"state_key": "raven-unknown", "name": "unknown"},
    ]
    raven_states = {
        "raven-alive": {"killed": False},
        "raven-dead": {"killed": True},
    }
    raven_rows_before = copy.deepcopy(raven_rows)
    raven_states_before = copy.deepcopy(raven_states)
    raven = vis.resolve_catalogue("odins_raven", raven_rows, raven_states, rollout)
    check(raven["visible_count"] == 1, "alive Raven should be visible")
    check(raven["visible"][0]["row"]["state_key"] == "raven-alive", "wrong Raven visible")
    check(raven["suppressed_count"] == 2, "dead + unknown Raven must be suppressed")
    check(raven_rows == raven_rows_before and raven_states == raven_states_before,
          "resolver mutated Raven inputs")

    ship_heads = [{"state_key": f"ship-head-{i:02d}"} for i in range(1, 10)]
    ship_states = {
        row["state_key"]: {"collected": row["state_key"] == "ship-head-09"}
        for row in ship_heads
    }
    artefact = vis.resolve_catalogue("artefact", ship_heads, ship_states, rollout)
    check(artefact["input_count"] == 9, "Ship Head proved subset must remain 9")
    check(artefact["visible_count"] == 8, "one collected Ship Head should leave eight visible")
    check(artefact["suppressed_count"] == 1, "collected Ship Head not suppressed")

    missing_identity = vis.resolve_catalogue(
        "artefact",
        [{"name": "no-key"}],
        {},
        rollout,
    )
    check(missing_identity["visible_count"] == 0, "missing state key must fail closed")
    check(missing_identity["suppressed"][0]["decision"]["reason"] == "missing_state_key",
          "wrong missing-key reason")

    lore_policy = rollout["families"]["lore_marker"]
    conflicting = vis.decide_visibility(lore_policy, {"read": False, "completed": True})
    check(conflicting.visible is False and conflicting.authoritative is False,
          "conflicting Lore state must fail closed")
    check(conflicting.reason == "conflicting_completion_booleans",
          "wrong conflicting-state reason")

    bell_policy = rollout["families"]["nornir_bell"]
    bell = vis.decide_visibility(bell_policy, {"completed": False})
    check(bell.visible is False and bell.authoritative is False,
          "Bell must stay parent-gated without an exact child completion key")

    raven_allowed, raven_reasons = vis.can_enable_runtime(rollout["families"]["odins_raven"])
    check(raven_allowed is True and raven_reasons == [], "reference Raven family unexpectedly blocked")
    for key, policy in rollout["families"].items():
        if key == "odins_raven":
            continue
        allowed, reasons = vis.can_enable_runtime(policy)
        check(allowed is False and reasons, f"{key}: unresolved family was enabled")

    legendary = rollout["families"]["legendary_chest"]["catalogue"]
    check(legendary["tracked_rows"] + legendary["exact_trial_exclusions"] +
          legendary["unresolved_rows"] == legendary["raw_rows"] == 64,
          "Legendary classification partition changed")

    result = {
        "result": "COLLECTIBLE_FAMILY_VISIBILITY_TESTS_PASS",
        "families": validation["families"],
        "raven_visible": raven["visible_count"],
        "ship_heads_proved_subset": artefact["input_count"],
        "ship_heads_visible_in_fixture": artefact["visible_count"],
        "legendary_raw_rows_partitioned": legendary["raw_rows"],
        "unknown_state_hidden": True,
        "conflicting_state_hidden": True,
        "unresolved_families_runtime_blocked": True,
        "writes": False,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
