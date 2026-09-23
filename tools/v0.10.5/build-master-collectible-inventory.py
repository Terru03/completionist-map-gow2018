#!/usr/bin/env python3
"""Build a fail-closed master collectible inventory.

Native repository evidence is authoritative. External guide counts are audit
expectations only and can never create a physical row or authorize a marker.
The builder accepts one or more catalogue JSON files so family-specific
research branches can export evidence into one normalized inventory later.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_POLICY = REPO / "config/collectibles/v0.10.5/master-collectible-policy.json"
DEFAULT_CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"

ALIASES = {
    "raven": "odin_raven", "odins_raven": "odin_raven", "odin's raven": "odin_raven",
    "artefact": "artefact", "artifact": "artefact",
    "nornir": "nornir_chest", "nornir_chest": "nornir_chest", "runic_chest": "nornir_chest",
    "legendary": "legendary_chest", "legendary_chest": "legendary_chest",
    "lore": "lore_marker", "lore_marker": "lore_marker",
    "realm_tear": "realm_tear", "realm tear": "realm_tear",
    "jotnar_shrine": "jotnar_shrine", "jotnar shrine": "jotnar_shrine",
    "cipher_chest": "cipher_chest", "cipher chest": "cipher_chest",
    "treasure_map": "treasure_map", "treasure map": "treasure_map",
    "treasure_dig": "treasure_dig", "treasure dig": "treasure_dig",
    "hidden_chamber": "hidden_chamber", "hidden chamber": "hidden_chamber",
    "valkyrie": "valkyrie", "valkyrie_queen": "valkyrie_queen",
    "mystic_gateway": "mystic_gateway", "gateway": "mystic_gateway",
    "shop": "shop", "dragon": "dragon", "favor": "favor", "favour": "favor",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def family_key(row: dict) -> str:
    raw = row.get("family") or row.get("type") or row.get("category") or ""
    token = norm_token(raw)
    if token in ALIASES:
        return ALIASES[token]
    subtype = norm_token(row.get("subtype"))
    if subtype in ALIASES:
        return ALIASES[subtype]
    name = norm_token(row.get("display_name") or row.get("name"))
    for alias, canonical in ALIASES.items():
        if alias.replace(" ", "_") in name:
            return canonical
    return token or "unknown"


def first(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def physical_id(row: dict) -> str | None:
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return first(native, "instance_guid", "physical_instance_guid") or first(row, "physical_instance_guid", "instance_guid", "guid")


def world_xyz(row: dict) -> list | None:
    marker = row.get("marker") if isinstance(row.get("marker"), dict) else {}
    value = first(marker, "position_world", "world_xyz", "position") or first(row, "world_xyz", "position_world")
    if isinstance(value, list) and len(value) >= 3:
        return value[:3]
    return None


def state_identity(row: dict) -> dict:
    progress = row.get("progression") if isinstance(row.get("progression"), dict) else {}
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return {
        "instance_keys": progress.get("instance_keys") or [],
        "object_hash_hex": first(progress, "object_hash_hex", "static_derived_object_hash_hex") or first(native, "object_hash_hex"),
        "serialized_flag1_hex": first(progress, "serialized_flag1_hex", "static_derived_serialized_flag1_hex") or first(native, "serialized_flag1_hex"),
        "state_adapter": progress.get("state_adapter"),
        "completion_field": progress.get("field"),
        "unloaded_query": progress.get("unloaded_query"),
    }


def load_catalogue(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("collectibles", "ravens", "rows", "items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    raise ValueError(f"unsupported catalogue shape: {path}")


def policy_index(policy: dict) -> dict[str, dict]:
    return {row["key"]: row for row in policy["families"]}


def marker_policy(policy: dict, fam: str, subtype: str | None) -> tuple[str, str]:
    for override in policy.get("subtype_overrides", []):
        if override.get("family") == fam and norm_token(override.get("subtype")) == norm_token(subtype):
            return override["marker_policy"], "subtype_override"
    fam_policy = policy_index(policy).get(fam)
    if fam_policy:
        return fam_policy["marker_policy"], "family_policy"
    return policy["default_marker_policy"], "default_fail_closed"


def normalize(row: dict, source: Path, policy: dict) -> dict:
    fam = family_key(row)
    subtype = row.get("subtype")
    mp, mp_source = marker_policy(policy, fam, subtype)
    source_info = row.get("source") if isinstance(row.get("source"), dict) else {}
    progress = row.get("progression") if isinstance(row.get("progression"), dict) else {}
    native = row.get("native") if isinstance(row.get("native"), dict) else {}
    return {
        "catalogue_id": row.get("catalogue_id") or row.get("id"),
        "family": fam,
        "subtype": subtype,
        "display_name": row.get("display_name") or row.get("name") or subtype or fam,
        "realm_id": row.get("realm_id"),
        "region_id": row.get("region_id"),
        "wad": first(source_info, "wad", "source_file") or row.get("wad"),
        "physical_id": physical_id(row),
        "world_xyz": world_xyz(row),
        "parent_summary": first(progress, "parent_quest", "region_summary") or first(native, "parent_region_summary_target"),
        "state_identity": state_identity(row),
        "native_marker_present": None,
        "native_marker_evidence": None,
        "mod_marker_policy": mp,
        "mod_marker_policy_source": mp_source,
        "mod_marker_allowed": False,
        "marker_block_reason": "Inventory evidence alone never authorizes runtime marker generation.",
        "physical": True,
        "tracking_classification": "unclassified",
        "production_eligibility": "blocked_unclassified",
        "production_ready": False,
        "marker_generation_ready": False,
        "classification_evidence": [],
        "source_catalogue": str(source).replace("\\", "/"),
        "source_row_sha256": hashlib.sha256(canonical_json(row).encode()).hexdigest(),
    }


def dedupe(rows: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    by_physical: dict[str, str] = {}
    for row in rows:
        key = row.get("catalogue_id") or (f"physical:{row['physical_id']}" if row.get("physical_id") else None)
        if key is None:
            raise ValueError("physical collectible lacks catalogue and physical identity")
        if key in by_key:
            raise ValueError(f"conflicting duplicate collectible rows: catalogue_id {key}")
        physical = row.get("physical_id")
        if physical:
            # Instance identifiers can recur in separate WAD placements.
            physical_key = (str(row.get("wad") or "").lower(), str(physical).lower())
            if physical_key in by_physical:
                raise ValueError(f"conflicting duplicate physical identity: {physical} ({by_physical[physical_key]}, {key})")
            by_physical[physical_key] = key
        by_key[key] = row
    return sorted(by_key.values(), key=lambda r: (r["family"], str(r.get("realm_id")), str(r.get("region_id")), str(r.get("catalogue_id"))))


def reject_marker_authority(value: Any) -> None:
    """An imported evidence file cannot grant runtime marker permission."""
    if isinstance(value, dict):
        if value.get("mod_marker_allowed") is True or value.get("runtime_generation_allowed") is True:
            raise ValueError("evidence overlay attempts to authorize runtime marker generation")
        for child in value.values():
            reject_marker_authority(child)
    elif isinstance(value, list):
        for child in value:
            reject_marker_authority(child)


def source_record(entry: dict) -> dict:
    path = Path(entry["file"]).resolve()
    if not path.is_file() or sha(path) != entry["sha256"]:
        raise ValueError(f"missing or hash-mismatched pinned source: {path}")
    for key in ("role", "source_branch", "source_commit", "source_path"):
        if not entry.get(key):
            raise ValueError(f"pinned source lacks {key}: {path}")
    if len(entry["source_commit"]) != 40:
        raise ValueError(f"source commit is not a full SHA: {path}")
    return {"role": entry["role"], "family": entry.get("family"),
            "source_branch": entry["source_branch"], "source_commit": entry["source_commit"],
            "source_path": entry["source_path"], "source_sha256": entry["sha256"],
            "bytes": path.stat().st_size, "local_file": str(path)}


def load_pinned_sources(manifest_path: Path, policy: dict) -> tuple[list[dict], dict, list[dict]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["sources"]
    for entry in entries:
        entry["file"] = str((manifest_path.resolve().parent / entry["file"]).resolve())
    roles = Counter((e["role"], e.get("family")) for e in entries)
    if roles[("seed_catalogue", None)] != 1:
        raise ValueError("exactly one seed catalogue is required")
    family_sources = {e["family"]: e for e in entries if e["role"] == "family_catalogue"}
    gate_sources = {e["family"]: e for e in entries if e["role"] == "family_gate"}
    research_gates = {e["family"]: e for e in entries if e["role"] == "research_gate"}
    raven_audits = [e for e in entries if e["role"] == "family_audit" and e.get("family") == "odin_raven"]
    if len(raven_audits) != 1:
        raise ValueError("exactly one Raven native audit is required")
    for family in ("odin_raven", "nornir_chest", "legendary_chest", "artefact", "lore_marker"):
        if roles[("family_catalogue", family)] != 1:
            raise ValueError(f"exactly one authoritative catalogue required for {family}")
    for family in ("nornir_chest", "legendary_chest", "artefact", "lore_marker"):
        if roles[("family_gate", family)] != 1:
            raise ValueError(f"exactly one static gate required for {family}")
    if roles[("research_gate", "realm_tear")] != 1:
        raise ValueError("exactly one Realm Tear research gate required")
    provenance = [source_record(e) for e in entries]
    by_entry = {id(e): p for e, p in zip(entries, provenance)}
    seed = next(e for e in entries if e["role"] == "seed_catalogue")
    overridden = set(family_sources)
    inputs: list[tuple[dict, dict]] = []
    for row in load_catalogue(Path(seed["file"])):
        if family_key(row) not in overridden:
            inputs.append((row, by_entry[id(seed)]))
    catalogue_data = {}
    for family, entry in family_sources.items():
        path = Path(entry["file"])
        data = json.loads(path.read_text(encoding="utf-8"))
        reject_marker_authority(data)
        family_rows = [row for row in load_catalogue(path) if family_key(row) == family]
        if not family_rows:
            raise ValueError(f"family catalogue has no rows: {family}")
        catalogue_data[family] = data
        inputs.extend((row, by_entry[id(entry)]) for row in family_rows)
    rows = dedupe([normalize(raw, Path(src["source_path"]), policy) |
                   {"catalogue_provenance": src} for raw, src in inputs])
    by_id = {row["catalogue_id"]: row for row in rows}
    summary = {}
    raven = catalogue_data["odin_raven"]
    raven_rows = [r for r in rows if r["family"] == "odin_raven"]
    if len(raven_rows) != raven["expected_native_object_count"] or raven["native_labor_target_count"] > len(raven_rows):
        raise ValueError("Raven catalogue count conflicts with native census")
    raven_src = by_entry[id(family_sources["odin_raven"])]
    raven_audit_src = by_entry[id(raven_audits[0])]
    raven_audit = json.loads(Path(raven_audits[0]["file"]).read_text(encoding="utf-8"))
    reject_marker_authority(raven_audit)
    parent_counts = Counter(row["parent_summary"] for row in raven_rows)
    targets = raven_audit["parent_target_counts"]
    surplus = {parent: parent_counts[parent] - targets[parent] for parent in targets
               if parent_counts[parent] != targets[parent]}
    if (dict(parent_counts) != raven_audit["parent_object_counts"] or
            surplus != raven_audit["parent_surplus"] or
            sum(targets.values()) != raven["native_labor_target_count"] or
            sum(surplus.values()) != raven_audit["native_hidden_surplus_count"]):
        raise ValueError("Raven native parent audit conflicts with catalogue")
    special_by_id = {raw["catalogue_id"]: raw.get("special_handling", []) for raw in raven["ravens"]}
    for row in raven_rows:
        in_surplus_group = row["parent_summary"] in surplus
        flagged = "parent_contains_one_bonus_untracked_raven" in special_by_id[row["catalogue_id"]]
        if flagged != in_surplus_group:
            raise ValueError("Raven special handling conflicts with parent surplus audit")
        row["tracking_classification"] = ("accounting_membership_unresolved_surplus_group" if in_surplus_group
                                           else "accounting_group_matches_target")
        row["production_eligibility"] = "blocked_accounting_membership_and_state"
        row["classification_evidence"].extend([
            {"source": raven_src, "field": "progression.parent_quest; special_handling"},
            {"source": raven_audit_src, "field": "parent_object_counts; parent_target_counts; parent_surplus",
             "parent": row["parent_summary"], "group_surplus": surplus.get(row["parent_summary"], 0)},
        ])
    summary["odin_raven"] = {"native_accounting_target": raven["native_labor_target_count"],
                              "tracked_candidates": None, "explained_untracked": 0,
                              "unresolved": len(raven_rows) - raven["native_labor_target_count"],
                              "unresolved_scope": "two surplus parent groups; exact two identities unknown",
                              "unresolved_group_candidates": {parent: {"physical": parent_counts[parent],
                                                                        "native_target": targets[parent],
                                                                        "surplus": extra}
                                                              for parent, extra in sorted(surplus.items())},
                              "unresolved_candidate_objects": sum(parent_counts[parent] for parent in surplus)}

    for family, entry in gate_sources.items():
        gate = json.loads(Path(entry["file"]).read_text(encoding="utf-8"))
        reject_marker_authority(gate)
        cat_src = by_entry[id(family_sources[family])]
        expected_hash = gate.get("source_sha256", {}).get("config/collectibles/v0.10.5/all-collectibles.json")
        if not expected_hash:
            raise ValueError(f"{family} gate lacks source catalogue hash")
        catalogue_bytes = Path(family_sources[family]["file"]).read_bytes()
        declared_lf_hash = gate.get("source_lf_sha256", {}).get("config/collectibles/v0.10.5/all-collectibles.json")
        if declared_lf_hash is not None and declared_lf_hash != cat_src["source_sha256"]:
            raise ValueError(f"{family} gate LF content hash conflicts with pinned catalogue")
        crlf_hash = hashlib.sha256(catalogue_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest()
        if expected_hash == cat_src["source_sha256"]:
            hash_basis = "git_blob_bytes"
        elif expected_hash == crlf_hash:
            hash_basis = "windows_crlf_checkout_bytes"
        else:
            raise ValueError(f"{family} gate and family catalogue content conflict")
        gate_hash_note = {"gate_catalogue_sha256_at_generation": expected_hash,
                          "current_family_catalogue_sha256": cat_src["source_sha256"],
                          "gate_catalogue_hash_basis": hash_basis,
                          "catalogue_content_changed_since_gate": False}
        gate_src = by_entry[id(entry)]
        family_rows = {r["catalogue_id"]: r for r in rows if r["family"] == family}
        if family == "nornir_chest":
            gate_rows = gate["rows"]
            if len(gate_rows) != gate["physical_count"] or set(r["catalogue_id"] for r in gate_rows) != set(family_rows):
                raise ValueError("Nornir gate and physical catalogue identities conflict")
            classes = Counter()
            for evidence in gate_rows:
                row = family_rows[evidence["catalogue_id"]]
                if row["physical_id"].lower() != evidence["physical_guid"].lower():
                    raise ValueError("Nornir gate physical identity conflict")
                classification = evidence["tracking_classification"]
                if classification == "unresolved_tracked_candidate":
                    row["tracking_classification"] = "tracked_candidate"
                    row["production_eligibility"] = "blocked_direct_binding_and_state"
                elif classification == "level_scripted_untracked_triple_chest_reward":
                    row["tracking_classification"] = "explained_untracked"
                    row["production_eligibility"] = "excluded_from_map_accounting"
                else:
                    raise ValueError(f"unknown Nornir classification: {classification}")
                row["classification_evidence"].append({"source": gate_src, "field": "rows.tracking_classification", "value": classification})
                classes[row["tracking_classification"]] += 1
            if classes["tracked_candidate"] != gate["tracked_candidate_count"] or classes["explained_untracked"] != gate["explained_untracked_count"] or gate["linked_child_count"] != 66:
                raise ValueError("Nornir gate census conflicts with row classification")
            summary[family] = {"native_accounting_target": None, "tracked_candidates": classes["tracked_candidate"],
                               "explained_untracked": classes["explained_untracked"], "unresolved": 0,
                               "linked_child_objects": gate["linked_child_count"], "static_gate_status": gate["status"],
                               **gate_hash_note}
        elif family == "legendary_chest":
            if len(family_rows) != gate["raw_count"]:
                raise ValueError("Legendary gate raw count conflicts with catalogue")
            candidates = {r["catalogue_id"] for r in gate["candidate_rows"]}
            unresolved = set(gate["unresolved_catalogue_ids"])
            classes = Counter()
            raw_by_id = {r["catalogue_id"]: r for r in load_catalogue(Path(family_sources[family]["file"]))}
            for row in family_rows.values():
                # This family catalogue is pinned to the Legendary branch; its classes
                # come from its native audit, while the gate validates candidate IDs.
                raw = raw_by_id[row["catalogue_id"]]
                cls = raw["native_classification"]
                classes[cls] += 1
                if cls == "tracked_legendary":
                    row["tracking_classification"] = "tracked_candidate"
                    row["production_eligibility"] = "blocked_direct_binding_and_marker_path"
                elif cls in ("trial_reward", "non_map_counted_physical"):
                    row["tracking_classification"] = "explained_untracked"
                    row["production_eligibility"] = "excluded_from_map_accounting"
                elif cls == "unresolved_nontracked":
                    row["tracking_classification"] = "unresolved"
                    row["production_eligibility"] = "blocked_unresolved_classification"
                else:
                    raise ValueError(f"unknown Legendary classification: {cls}")
                row["classification_evidence"].append({"source": cat_src, "field": "native_classification", "value": cls})
            if classes != Counter({"tracked_legendary": 33, "trial_reward": 27, "non_map_counted_physical": 2, "unresolved_nontracked": 2}) or candidates != {r["catalogue_id"] for r in family_rows.values() if r["tracking_classification"] == "tracked_candidate"} or unresolved != {r["catalogue_id"] for r in family_rows.values() if r["tracking_classification"] == "unresolved"} or len(candidates) != gate["candidate_count"]:
                raise ValueError("Legendary gate and catalogue classifications conflict")
            for cid in candidates | unresolved:
                family_rows[cid]["classification_evidence"].append({"source": gate_src, "field": "candidate_rows or unresolved_catalogue_ids"})
            summary[family] = {"native_accounting_target": None, "tracked_candidates": len(candidates),
                               "explained_untracked": classes["trial_reward"] + classes["non_map_counted_physical"],
                               "unresolved": len(unresolved), "classification_counts": dict(sorted(classes.items())),
                               "static_gate_status": gate["status"], **gate_hash_note}
        elif family == "artefact":
            gate_rows = {item["catalogue_id"]: item for item in gate["rows"]}
            if len(family_rows) != gate["physical_count"] or set(gate_rows) != set(family_rows):
                raise ValueError("Artefact gate and physical catalogue identities conflict")
            if gate["status"] != "BLOCKED_FAIL_CLOSED" or gate["runtime_generation_allowed"] is not False or gate["direct_shiphead_parent_count"] != 9 or gate["other_artefact_unbound_count"] != 36 or gate["shiphead_native_target"] != 10:
                raise ValueError("Artefact gate census or readiness conflicts")
            classes = Counter()
            for cid, row in family_rows.items():
                proof = gate_rows[cid]
                if (proof["physical_id"].lower() != row["physical_id"].lower() or
                        proof["wad"].lower() != str(row["wad"]).lower() or
                        proof["parent_quest"] != row["parent_summary"] or
                        proof["production_ready"] is not False or
                        proof["marker_generation_ready"] is not False):
                    raise ValueError(f"Artefact row evidence conflicts: {cid}")
                cls = proof["region_binding"]
                if cls == "direct_native_shiphead_parent" and row["subtype"] == "Ship Head":
                    row["tracking_classification"] = "shiphead_direct_parent"
                    row["production_eligibility"] = "blocked_shiphead_target_and_state"
                elif cls == "no_region_summary_binding_proven" and row["subtype"] != "Ship Head":
                    row["tracking_classification"] = "accounting_unresolved"
                    row["production_eligibility"] = "blocked_accounting_and_state"
                else:
                    raise ValueError(f"Artefact subtype classification conflicts: {cid}")
                row["classification_evidence"].append({"source": gate_src, "field": "rows.region_binding", "value": cls})
                classes[row["tracking_classification"]] += 1
            if classes != Counter({"shiphead_direct_parent": 9, "accounting_unresolved": 36}):
                raise ValueError("Artefact subtype census conflicts")
            summary[family] = {"native_accounting_target": None, "tracked_candidates": None,
                               "explained_untracked": 0, "unresolved": 36,
                               "unresolved_scope": "non-Ship-Head RegionSummary ownership; other accounting unknown",
                               "direct_shiphead_parent_count": 9, "shiphead_native_target": 10,
                               "classification_counts": dict(sorted(classes.items())),
                               "static_gate_status": gate["status"], **gate_hash_note}
        elif family == "lore_marker":
            gate_rows = {item["catalogue_id"]: item for item in gate["rows"]}
            if len(family_rows) != gate["physical_count"] or set(gate_rows) != set(family_rows):
                raise ValueError("Lore gate and physical catalogue identities conflict")
            if (gate["status"] != "BLOCKED_FAIL_CLOSED" or
                    gate["runtime_generation_allowed"] is not False or
                    gate["physical_count"] != 43 or
                    gate["direct_object_parent_count"] != 40 or
                    gate["level_script_context_count"] != 3 or
                    gate["native_summary_target"] != 43 or
                    gate["persistent_unloaded_state_count"] != 0):
                raise ValueError("Lore gate census or readiness conflicts")
            classes = Counter()
            for cid, row in family_rows.items():
                proof = gate_rows[cid]
                if (proof["physical_id"].lower() != row["physical_id"].lower() or
                        proof["wad"].lower() != str(row["wad"]).lower() or
                        proof["parent_quest"] != row["parent_summary"] or
                        proof["world_position"] != row["world_xyz"] or
                        proof["production_ready"] is not False or
                        proof["marker_generation_ready"] is not False or
                        proof["persistent_unloaded_state_proven"] is not False):
                    raise ValueError(f"Lore row evidence conflicts: {cid}")
                cls = proof["region_binding"]
                if cls == "direct_object_attribute" and row["subtype"] == "native_lore_marker" and row["parent_summary"]:
                    row["tracking_classification"] = "direct_parent_state_blocked"
                    row["production_eligibility"] = "blocked_persistent_state_and_marker_path"
                elif (cls == "level_script_callback_object_link_unproved" and
                      row["subtype"] == "level_script_lore_marker" and
                      row["parent_summary"] is None and proof["proposed_script_parent"]):
                    row["tracking_classification"] = "accounting_object_link_unresolved"
                    row["production_eligibility"] = "blocked_exact_object_link_and_state"
                else:
                    raise ValueError(f"Lore subtype classification conflicts: {cid}")
                row["classification_evidence"].append({"source": gate_src, "field": "rows.region_binding", "value": cls})
                classes[row["tracking_classification"]] += 1
            if classes != Counter({"direct_parent_state_blocked": 40,
                                   "accounting_object_link_unresolved": 3}):
                raise ValueError("Lore subtype census conflicts")
            summary[family] = {"native_accounting_target": 43, "tracked_candidates": None,
                               "explained_untracked": 0, "unresolved": 3,
                               "unresolved_scope": "three level script callback-to-object links",
                               "direct_object_parent_count": 40,
                               "classification_counts": dict(sorted(classes.items())),
                               "static_gate_status": gate["status"], **gate_hash_note}
    realm_entry = research_gates["realm_tear"]
    realm_gate = json.loads(Path(realm_entry["file"]).read_text(encoding="utf-8"))
    reject_marker_authority(realm_gate)
    if (realm_gate["status"] != "BLOCKED_FAIL_CLOSED" or
            realm_gate["runtime_generation_allowed"] is not False or
            realm_gate["physical_encounter_census_proven"] is not False or
            realm_gate["physical_encounter_rows"] != [] or
            realm_gate["native_summary_target_sum"] != 19 or
            realm_gate["direct_parent_callback_carrier_count"] != 14 or
            realm_gate["native_marker_coverage_proven"] is not False or
            any(row["family"] == "realm_tear" for row in rows)):
        raise ValueError("Realm Tear research gate conflicts with physical inventory")
    summary["realm_tear"] = {"native_accounting_target": 19,
                             "tracked_candidates": None, "explained_untracked": 0,
                             "unresolved": 0,
                             "unresolved_scope": "physical encounter census not proved",
                             "direct_parent_callback_carrier_count": 14,
                             "static_gate_status": realm_gate["status"]}
    return rows, summary, provenance


def discrepancy(policy: dict, rows: list[dict], summary: dict | None = None) -> list[dict]:
    summary = summary or {}
    counts = Counter(row["family"] for row in rows)
    out = []
    for fam in policy["families"]:
        actual = counts.get(fam["key"], 0)
        expected = fam.get("guide_expected")
        detail = summary.get(fam["key"], {})
        target = detail.get("native_accounting_target")
        tracked = detail.get("tracked_candidates")
        if not actual:
            status = "NO_PHYSICAL_EVIDENCE"
        elif target is not None and expected == target:
            status = "GUIDE_MATCHES_NATIVE_ACCOUNTING_TARGET_MEMBERSHIP_UNRESOLVED" if detail.get("unresolved") else "GUIDE_MATCHES_NATIVE_ACCOUNTING_TARGET"
        elif target is not None and expected is not None and expected != target:
            status = "GUIDE_NATIVE_TARGET_DISAGREEMENT"
        elif tracked is not None and expected == tracked:
            status = "GUIDE_MATCHES_TRACKED_CANDIDATES"
        elif tracked is not None and expected != tracked:
            status = "GUIDE_TRACKED_CANDIDATE_DISAGREEMENT"
        elif expected is None:
            status = "NO_GUIDE_EXPECTATION"
        else:
            status = "ACCOUNTING_EVIDENCE_MISSING"
        out.append({
            "family": fam["key"], "display": fam["display"],
            "external_guide_expected": expected, "physical_rows": actual,
            "native_accounting_target": target, "tracked_candidates": tracked,
            "explained_untracked": detail.get("explained_untracked", 0),
            "unresolved": detail.get("unresolved", 0),
            "unresolved_scope": detail.get("unresolved_scope"),
            "unresolved_group_candidates": detail.get("unresolved_group_candidates"),
            "unresolved_candidate_objects": detail.get("unresolved_candidate_objects"),
            "production_ready": sum(r["production_ready"] for r in rows if r["family"] == fam["key"]),
            "marker_generation_ready": sum(r["marker_generation_ready"] for r in rows if r["family"] == fam["key"]),
            "audit_status": status, "marker_policy": fam["marker_policy"],
            "classification_counts": detail.get("classification_counts"),
            "linked_child_objects": detail.get("linked_child_objects"),
            "direct_shiphead_parent_count": detail.get("direct_shiphead_parent_count"),
            "shiphead_native_target": detail.get("shiphead_native_target"),
            "direct_object_parent_count": detail.get("direct_object_parent_count"),
            "direct_parent_callback_carrier_count": detail.get("direct_parent_callback_carrier_count"),
            "gate_catalogue_sha256_at_generation": detail.get("gate_catalogue_sha256_at_generation"),
            "current_family_catalogue_sha256": detail.get("current_family_catalogue_sha256"),
            "gate_catalogue_hash_basis": detail.get("gate_catalogue_hash_basis"),
            "catalogue_content_changed_since_gate": detail.get("catalogue_content_changed_since_gate"),
        })
    unknown = sorted(set(counts) - set(policy_index(policy)))
    for fam in unknown:
        out.append({"family": fam, "display": fam, "external_guide_expected": None,
                    "physical_rows": counts[fam], "native_accounting_target": None,
                    "tracked_candidates": None, "explained_untracked": 0, "unresolved": 0,
                    "production_ready": 0, "marker_generation_ready": 0,
                    "audit_status": "UNPOLICIED_NATIVE_FAMILY", "marker_policy": policy["default_marker_policy"]})
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["catalogue_id","family","subtype","display_name","realm_id","region_id","wad","physical_id","world_xyz","parent_summary","object_hash_hex","serialized_flag1_hex","unloaded_query","tracking_classification","production_eligibility","production_ready","marker_generation_ready","native_marker_present","mod_marker_policy","mod_marker_allowed","source_catalogue","source_branch","source_commit","source_sha256"]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            state = row["state_identity"]
            writer.writerow({
                **{k: row.get(k) for k in fields},
                "world_xyz": json.dumps(row.get("world_xyz"), separators=(",", ":")) if row.get("world_xyz") else "",
                "object_hash_hex": state.get("object_hash_hex"),
                "serialized_flag1_hex": state.get("serialized_flag1_hex"),
                "unloaded_query": state.get("unloaded_query"),
                "source_branch": row.get("catalogue_provenance", {}).get("source_branch"),
                "source_commit": row.get("catalogue_provenance", {}).get("source_commit"),
                "source_sha256": row.get("catalogue_provenance", {}).get("source_sha256"),
            })


def write_md(path: Path, report: dict) -> None:
    lines = ["# Master collectible inventory", "", f"Generated: `{report['generated_utc']}`", "",
             "Native game/repository evidence is authoritative. Guide counts are audit-only. Runtime marker generation is disabled by this report.", "",
             "## Family audit", "", "| Family | External guide | Physical | Native target | Tracked candidates | Explained untracked | Unresolved | Production ready | Audit status |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for row in report["family_audit"]:
        def shown(value: Any) -> str:
            return "" if value is None else str(value)
        lines.append(f"| {row['display']} | {shown(row['external_guide_expected'])} | {row['physical_rows']} | {shown(row['native_accounting_target'])} | {shown(row['tracked_candidates'])} | {row['explained_untracked']} | {row['unresolved']} | {row['production_ready']} | {row['audit_status']} |")
    lines += ["", "Raven native audit narrows two surplus objects to CalderaShores (2 physical / 1 target) and Riverpass (7 / 6). It does not name the two specific objects outside Labor accounting.", "", "Legendary tracked candidates are not a production allowlist. The external guide expects 34; native candidates remain 33.", "", "Artefacts have 45 physical objects. Nine Ship Heads have direct parent attributes against a target of ten. The other 36 lack proved RegionSummary ownership; guide count 45 does not settle accounting.", "", "Lore has 43 physical objects and a native Summary target of 43, versus external guide count 39. Forty object overrides hold direct parent names. Three level Lua callback clues lack exact callback-to-object links. No row was dropped to match a guide count.", "", "Realm Tear research gate pins 19 native PocketRift Summary targets and 14 direct callback carriers. Physical encounter census is unproved, so master has no Realm Tear row yet.", ""]
    for row in report["family_audit"]:
        if row.get("gate_catalogue_hash_basis") == "windows_crlf_checkout_bytes":
            lines.append(f"- {row['display']} gate catalogue hash `{row['gate_catalogue_sha256_at_generation']}` is for Windows CRLF checkout bytes. Pinned Git blob hash is `{row['current_family_catalogue_sha256']}`; normalized contents match.")
    lines += ["", "## Hard marker rules", ""]
    lines += [f"- {rule}" for rule in report["policy_hard_rules"]]
    lines += ["", "## Pinned evidence", ""]
    for source in report["source_catalogues"]:
        lines.append(f"- `{source['source_branch']}@{source['source_commit']}` `{source['source_path']}` SHA-256 `{source['source_sha256']}` ({source['role']})")
    lines += ["", "## Inventory rows", "", "| Family | Subtype | Realm | Region | WAD | Physical ID | Tracking class | Production |", "|---|---|---|---|---|---|---|---|"]
    for row in report["rows"]:
        lines.append(f"| {row['family']} | {row.get('subtype') or ''} | {row.get('realm_id') or ''} | {row.get('region_id') or ''} | {row.get('wad') or ''} | {row.get('physical_id') or ''} | {row['tracking_classification']} | {row['production_eligibility']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--catalogue", type=Path, action="append")
    ap.add_argument("--source-manifest", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if args.source_manifest:
        if args.catalogue:
            raise ValueError("source manifest and loose catalogues cannot be mixed")
        rows, summary, sources = load_pinned_sources(args.source_manifest, policy)
    else:
        catalogues = args.catalogue or [DEFAULT_CATALOGUE]
        normalized = []
        sources = []
        for path in catalogues:
            path = path.resolve()
            if path.exists():
                sources.append({"source_path": str(path), "source_sha256": sha(path), "bytes": path.stat().st_size,
                                "source_branch": "unversioned", "source_commit": "unversioned", "role": "loose_catalogue"})
            for row in load_catalogue(path):
                normalized.append(normalize(row, path, policy))
        rows, summary = dedupe(normalized), {}
    report = {
        "schema": 2,
        "analysis": "master_collectible_inventory",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": policy["source_of_truth"],
        "external_guides_are_audit_only": True,
        "runtime_generation_allowed": False,
        "source_catalogues": sources,
        "policy_sha256": sha(args.policy),
        "policy_hard_rules": policy["hard_rules"],
        "row_count": len(rows),
        "family_audit": discrepancy(policy, rows, summary),
        "rows": rows,
    }
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "master-collectible-inventory.json").write_text(canonical_json(report), encoding="utf-8")
    write_csv(out / "master-collectible-inventory.csv", rows)
    write_md(out / "master-collectible-inventory.md", report)
    disagreements = [r for r in report["family_audit"] if r["audit_status"] == "GUIDE_TRACKED_CANDIDATE_DISAGREEMENT"]
    print(f"MASTER_COLLECTIBLE_INVENTORY rows={len(rows)} guide_candidate_disagreements={len(disagreements)} runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
