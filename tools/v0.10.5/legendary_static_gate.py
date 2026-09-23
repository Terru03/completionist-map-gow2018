#!/usr/bin/env python3
"""Read only gate for Legendary Chest production data.

An exact GameObject save key does not prove map count membership. Keep output
off until each planned chest has a direct native ownership edge and asset IDs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import legendary_chest_identity as native_identity


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
AUDIT = REPO / "docs/research/all-collectibles-native-audit.json"
IDENTITIES = REPO / "archive/field-logs/source-scans/legendary-serialized-identities-static-20260922-152212/report.json"
SCOPE = REPO / "archive/field-logs/source-scans/legendary-map-counted-scope-20260922-165204/report.json"
SEMANTICS = REPO / "archive/field-logs/source-scans/legendary-opened-state-semantics-20260922-161151/report.json"
FROZEN_CAPTURE = REPO / "archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1"


def check(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def derived_key(row: dict) -> tuple[str, str]:
    scene, _skipped = native_identity.scene_identity_elements(row)
    elements = scene + [native_identity.CHEST_OWN_IDENTITY_ELEMENT]
    registry = native_identity.registry_hash_for_wad(row["source"]["wad"])
    obj = native_identity.identity_hash(elements)
    return f"0x{obj:016X}", native_identity.serialized_payload(registry, obj).hex()


def assess(catalogue: dict, audit: dict, identities: dict,
           scope: dict, semantics: dict) -> dict:
    rows = [r for r in catalogue["collectibles"] if r.get("family") == "legendary_chest"]
    by_id = {r["catalogue_id"]: r for r in rows}
    check(len(rows) == len(by_id) == 64, "Legendary raw census changed")
    classes = Counter(r["native_classification"] for r in rows)
    check(classes == {
        "tracked_legendary": 33, "trial_reward": 27,
        "non_map_counted_physical": 2, "unresolved_nontracked": 2,
    }, "Legendary class census changed")
    audit_rows = {r["catalogue_id"]: r for r in
                  audit["legendary_classification_evidence"]}
    check(set(audit_rows) == set(by_id), "audit and catalogue census differ")
    for cid, row in by_id.items():
        check(audit_rows[cid]["classification"] == row["native_classification"] and
              audit_rows[cid]["production_eligibility"] == row["production_eligibility"],
              f"{cid}: audit classification differs")
    check(semantics.get("status") == "LEGENDARY_OPENED_STATE_SEMANTICS_PROVEN",
          "OPENED scalar proof missing")
    check(identities.get("status") == "EXACT_32_OF_32_STAGED_BINDING",
          "serialized identity proof missing")
    check(scope.get("status") == "EXACT_33_MAP_COUNTED_SCOPE_RESOLVED",
          "scope evidence missing")

    candidates = {cid: r for cid, r in by_id.items()
                  if r["production_eligibility"] == "tracked_collectible"}
    check(len(candidates) == 33, "tracked candidate count changed")
    check(set(scope["production_catalogue_ids"]) == set(candidates),
          "scope and catalogue candidate sets differ")
    scope_rows = {r["catalogue_id"]: r for r in scope["production_rows"]}
    check(set(scope_rows) == set(candidates), "scope identity rows differ")
    old_state = {r["catalogue_id"]: r for r in identities["identities"]}
    recovered_state = {r["catalogue_id"]: r for r in scope["recovered_map_counted_rows"]}
    check(set(recovered_state) <= set(candidates), "recovered state outside candidates")
    state_tokens = {"010000803f", "0100000040", "0100004040", "0100008040"}

    seen_keys: set[str] = set()
    results = []
    for cid, row in sorted(candidates.items()):
        obj, payload = derived_key(row)
        expected = scope_rows[cid]
        check(obj == expected["object_hash_hex"] and
              payload == expected["serialized_flag1_hex"],
              f"{cid}: scope serialized identity differs")
        check(payload not in seen_keys, f"{cid}: serialized identity collision")
        seen_keys.add(payload)
        check(row["progression"]["state_adapter"] ==
              "interact_chest_standard_checkpoint_state" and
              row["progression"]["field"] == "state == OPENED",
              f"{cid}: state adapter differs")
        state_source = recovered_state.get(cid) or old_state.get(cid)
        check(state_source is not None, f"{cid}: no identity report row")
        check(state_source["object_hash_hex"] == obj and
              state_source["serialized_flag1_hex"] == payload,
              f"{cid}: state source identity differs")
        staged = state_source.get("staged_state")
        if staged:
            check(staged.get("state_raw_hex") in state_tokens,
                  f"{cid}: malformed staged state token")
        exact_state = bool(staged and
                           (staged.get("exact_match") or
                            old_state.get(cid, {}).get("staged_simple_state_match")))
        source = row["progression"].get("parent_quest_source")
        # No verifier for a direct chest-to-quest edge exists yet. An extra
        # catalogue field alone must never turn the production gate on.
        direct_binding = False
        results.append({
            "catalogue_id": cid,
            "object_hash_hex": obj,
            "serialized_flag1_hex": payload,
            "identity_proven": True,
            "staged_state_observed": exact_state,
            "parent_quest_source": source,
            "direct_native_binding_proven": direct_binding,
        })

    unresolved = sorted(cid for cid, row in by_id.items()
                        if row["native_classification"] == "unresolved_nontracked")
    check(len(unresolved) == 2, "unresolved census changed")
    binding_sources = Counter(r["parent_quest_source"] for r in results)
    check(binding_sources == {"unique_region_family_inference": 31,
                              "corrected_map_count_scope_proof": 2},
          "candidate binding source census changed")
    blockers = []
    if unresolved:
        blockers.append("two Legendary-path chests still lack positive native class evidence")
    blockers.append("two non-map-counted exclusions rest on scope reconciliation without direct native edges")
    if any(not r["direct_native_binding_proven"] for r in results):
        blockers.append("candidate chest-to-RegionSummary joins use inference, not direct native edges")
    if any(not r["staged_state_observed"] for r in results):
        blockers.append("one candidate lacks an observed exact staged state in the frozen capture")
    blockers.append("Legendary-specific map and world asset IDs and native suppression targets remain unproved")
    return {
        "schema": 1,
        "status": "BLOCKED_FAIL_CLOSED" if blockers else "READY_FOR_OFFLINE_BUILD",
        "runtime_generation_allowed": not blockers,
        "raw_count": len(rows),
        "candidate_count": len(results),
        "exact_identity_count": len(seen_keys),
        "observed_exact_staged_state_count": sum(r["staged_state_observed"] for r in results),
        "direct_native_binding_count": sum(r["direct_native_binding_proven"] for r in results),
        "binding_source_counts": dict(sorted(binding_sources.items())),
        "unresolved_catalogue_ids": unresolved,
        "candidate_rows": results,
        "blockers": blockers,
    }


def require_generation_ready(report: dict) -> None:
    if not report["runtime_generation_allowed"]:
        raise ValueError("Legendary generation blocked: " + "; ".join(report["blockers"]))


def diagnose_unresolved(catalogue: dict) -> list[dict]:
    """Recheck each unresolved key against its exact frozen WAD carrier."""
    path = Path(__file__).with_name("resolve-legendary-map-counted-scope-offline.py")
    spec = importlib.util.spec_from_file_location("_legendary_scope_for_gate", path)
    check(spec is not None and spec.loader is not None, "scope decoder missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    captured = json.loads((FROZEN_CAPTURE / "report.json").read_text(encoding="utf-8"))
    check(len(captured["records"]) == 425, "frozen staged carrier count changed")
    rows = [r for r in catalogue["collectibles"] if
            r.get("family") == "legendary_chest" and
            r.get("native_classification") == "unresolved_nontracked"]
    check(len(rows) == 2, "unresolved chest count changed")
    results = []
    for row in sorted(rows, key=lambda item: item["catalogue_id"]):
        derived = module.derive_identity(row)
        staged = module.exact_staged_state(
            FROZEN_CAPTURE, captured["records"], row, derived)
        check(staged["exact_match"],
              f"{row['catalogue_id']}: no exact frozen state")
        results.append({
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "object_hash_hex": derived["object_hash_hex"],
            "serialized_flag1_hex": derived["serialized_flag1_hex"],
            "state_raw_hex": staged["state_raw_hex"],
            "state_float32": staged["state_float32"],
            "capture_source": str(FROZEN_CAPTURE.relative_to(REPO)).replace("\\", "/"),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sources = [CATALOGUE, AUDIT, IDENTITIES, SCOPE, SEMANTICS]
    loaded = [json.loads(p.read_text(encoding="utf-8")) for p in sources]
    report = assess(*loaded)
    report["unresolved_state_diagnostics"] = diagnose_unresolved(loaded[0])
    report["source_sha256"] = {
        str(path.relative_to(REPO)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources + [FROZEN_CAPTURE / "report.json"]
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"LEGENDARY_STATIC_GATE {report['status']} "
          f"identities={report['exact_identity_count']}/33 "
          f"staged={report['observed_exact_staged_state_count']}/33 "
          f"direct_bindings={report['direct_native_binding_count']}/33")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
