#!/usr/bin/env python3
"""Read-only collectible-family visibility resolution for Completionist Map v0.10.5.

The module deliberately has no game-process, filesystem-write, save-write, or
progression-write capability. It consumes a static catalogue plus authoritative
state snapshots and returns only markers whose incomplete state is positively
known. Missing/ambiguous state fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_ROLLOUT = REPO / "config/collectibles/v0.10.5/family-rollout.json"


class VisibilityError(ValueError):
    pass


@dataclass(frozen=True)
class StateDecision:
    visible: bool
    complete: bool | None
    authoritative: bool
    reason: str
    completion_key: str | None = None


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise VisibilityError(message)


def load_rollout(path: Path = DEFAULT_ROLLOUT) -> dict:
    _check(path.is_file(), f"rollout config missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_rollout(data)
    return data


def validate_rollout(data: Mapping[str, Any]) -> dict:
    _check(data.get("schema") == 1, "rollout schema changed")
    global_invariants = data.get("global_invariants")
    _check(isinstance(global_invariants, Mapping), "global invariants missing")
    required_false = ("save_writes", "progression_writes", "synthetic_completion_writes")
    for key in required_false:
        _check(global_invariants.get(key) is False, f"{key} must remain false")
    _check(global_invariants.get("unknown_state") == "hide", "unknown state must fail closed")
    _check(global_invariants.get("missing_catalogue_identity") == "exclude",
           "missing catalogue identity must be excluded")
    _check(global_invariants.get("procedural_templates_as_fixed_markers") is False,
           "procedural templates must never become fixed markers")

    families = data.get("families")
    _check(isinstance(families, Mapping) and families, "families missing")
    required = {
        "odins_raven", "artefact", "nornir_chest", "nornir_seal",
        "nornir_bell", "nornir_mechanism", "legendary_chest", "lore_marker",
    }
    _check(required.issubset(families), f"missing families: {sorted(required - set(families))}")

    orders = []
    for key, family in families.items():
        _check(isinstance(family, Mapping), f"{key}: family row must be object")
        order = family.get("implementation_order")
        _check(isinstance(order, int) and order >= 0, f"{key}: implementation_order invalid")
        orders.append((order, key))
        state = family.get("state")
        _check(isinstance(state, Mapping), f"{key}: state policy missing")
        bool_keys = state.get("completion_bool_keys", [])
        _check(isinstance(bool_keys, list) and all(isinstance(x, str) and x for x in bool_keys),
               f"{key}: completion_bool_keys invalid")
        runtime = family.get("runtime")
        _check(isinstance(runtime, Mapping) and isinstance(runtime.get("status"), str),
               f"{key}: runtime status missing")
        blockers = family.get("blockers")
        _check(isinstance(blockers, list), f"{key}: blockers must be list")

    _check(len({order for order, _ in orders}) == len(orders), "implementation_order values collide")

    artefact = families["artefact"]["catalogue"]["proved_subsets"]["ship_heads"]
    _check(artefact.get("fixed_count") == 9, "Ship Head proved count must stay 9")
    _check(artefact.get("fake_tenth_row_forbidden") is True, "fake Ship Head 10 must remain forbidden")

    legendary = families["legendary_chest"]["catalogue"]
    _check(legendary.get("raw_rows") == 64, "Legendary raw row count changed")
    _check(legendary.get("tracked_rows") == 33, "Legendary tracked count changed")
    _check(legendary.get("exact_trial_exclusions") == 27, "Legendary trial exclusion count changed")
    _check(legendary.get("unresolved_rows") == 4, "Legendary unresolved count changed")
    _check(legendary["tracked_rows"] + legendary["exact_trial_exclusions"] +
           legendary["unresolved_rows"] == legendary["raw_rows"],
           "Legendary classification no longer partitions all raw rows")

    return {
        "valid": True,
        "families": len(families),
        "implementation_order": [key for _, key in sorted(orders)],
        "fail_closed": True,
        "writes": False,
    }


def _explicit_bool(state: Mapping[str, Any], keys: Iterable[str]) -> tuple[bool | None, str | None]:
    found: list[tuple[str, bool]] = []
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            found.append((key, value))
    if not found:
        return None, None
    values = {value for _, value in found}
    if len(values) != 1:
        return None, "conflicting_completion_booleans"
    return found[0][1], found[0][0]


def decide_visibility(family_policy: Mapping[str, Any],
                      state: Mapping[str, Any] | None) -> StateDecision:
    """Resolve one collectible from authoritative state.

    A visible marker is emitted only when an explicit completion boolean exists
    and is false. Explicit true means completed/hidden. Missing, conflicting,
    inherited-only, or malformed state is hidden.
    """
    if state is None:
        return StateDecision(False, None, False, "missing_state")

    _check(isinstance(state, Mapping), "state snapshot must be mapping")
    state_policy = family_policy.get("state", {})
    keys = state_policy.get("completion_bool_keys", [])
    if not keys:
        return StateDecision(False, None, False, "no_authoritative_completion_key")

    complete, key = _explicit_bool(state, keys)
    if complete is None:
        reason = key or "authoritative_completion_boolean_missing"
        return StateDecision(False, None, False, reason)

    if complete:
        return StateDecision(False, True, True, "completed", key)
    return StateDecision(True, False, True, "incomplete", key)


def resolve_catalogue(family_key: str,
                      catalogue_rows: Iterable[Mapping[str, Any]],
                      state_by_key: Mapping[str, Mapping[str, Any]],
                      rollout: Mapping[str, Any],
                      *,
                      identity_field: str = "state_key") -> dict:
    """Resolve a family catalogue into visible and suppressed rows.

    Every fixed catalogue row must provide a stable state key. Rows with missing
    state or unresolved state are suppressed. The input rows and state mappings
    are never mutated.
    """
    families = rollout.get("families", {})
    _check(family_key in families, f"unknown family: {family_key}")
    policy = families[family_key]

    visible: list[dict] = []
    suppressed: list[dict] = []
    seen_keys: set[str] = set()

    for index, source_row in enumerate(catalogue_rows):
        _check(isinstance(source_row, Mapping), f"{family_key}[{index}]: catalogue row must be mapping")
        row = copy.deepcopy(dict(source_row))
        state_key = row.get(identity_field)
        if not isinstance(state_key, str) or not state_key:
            suppressed.append({
                "row": row,
                "decision": StateDecision(False, None, False, "missing_state_key").__dict__,
            })
            continue
        _check(state_key not in seen_keys, f"{family_key}: duplicate state key: {state_key}")
        seen_keys.add(state_key)

        snapshot = state_by_key.get(state_key)
        decision = decide_visibility(policy, snapshot)
        item = {"row": row, "decision": decision.__dict__}
        if decision.visible:
            visible.append(item)
        else:
            suppressed.append(item)

    return {
        "family": family_key,
        "visible": visible,
        "suppressed": suppressed,
        "visible_count": len(visible),
        "suppressed_count": len(suppressed),
        "input_count": len(visible) + len(suppressed),
        "fail_closed": True,
        "writes": False,
    }


def can_enable_runtime(family_policy: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Return whether a family has cleared catalogue + state + blocker gates.

    This is intentionally conservative. The reference Raven family remains an
    explicit exception while its persistence work is finalised.
    """
    blockers = [str(x) for x in family_policy.get("blockers", [])]
    catalogue_status = str(family_policy.get("catalogue", {}).get("status", ""))
    state_status = str(family_policy.get("state", {}).get("status", ""))
    runtime_status = str(family_policy.get("runtime", {}).get("status", ""))

    if runtime_status == "active_reference_family":
        return True, []
    reasons = list(blockers)
    if catalogue_status not in {"ready", "proved"}:
        reasons.append(f"catalogue_gate:{catalogue_status or 'missing'}")
    if state_status not in {"ready", "authoritative"}:
        reasons.append(f"state_gate:{state_status or 'missing'}")
    return len(reasons) == 0, reasons
