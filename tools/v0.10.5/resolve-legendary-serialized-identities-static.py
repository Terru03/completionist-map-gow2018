#!/usr/bin/env python3
"""Resolve Legendary Chest serialized GameObject identities statically.

This combines two already-proven ingredients without touching Raven runtime:
1. shipped WAD record graphs + the native 0x401 GameObject identity hash;
2. the archived staged checkpoint inventory, used only as a read-only hash oracle.

All 33 tracked Legendary Chests share one prototype loader ID. Candidate 16-byte
prototype/object identity elements are discovered from the static record graph
around that loader. For each candidate, several explicit scene-boundary grammars
are hashed and compared with the exact serialized parent GameObject hashes of the
simple {state=<scalar>} subobjects observed in the matching staged WAD.

No process access, active-save reads, writes, or game-file modifications.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPECTED_TRACKED = 33
EXPECTED_STAGED = 32
EXPECTED_PROTOTYPE = "966624c84fc6b8590179bfd6c72c2086"
SIMPLE_STATE_CLASS = "0x75E050AB149B4062"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


raven = load_module("_legendary_raven_catalogue", HERE / "raven_catalogue.py")
identity = load_module("_legendary_identity_helper", HERE / "legendary_chest_identity.py")


def find_all(data: bytes, needle: bytes) -> list[int]:
    out = []
    start = 0
    while True:
        at = data.find(needle, start)
        if at < 0:
            return out
        out.append(at)
        start = at + 1


def record_for_offset(records: list[dict], at: int):
    for rec in records:
        header_start = rec["offset"]
        payload_start = header_start + 96
        payload_end = payload_start + rec["size"]
        if header_start <= at < payload_start:
            return rec, "header", at - header_start
        if payload_start <= at < payload_end:
            return rec, "payload", at - header_start
    return None, None, None


def scene_variants(row: dict) -> dict[str, list[bytes]]:
    chain = row["source"]["transform_chain"]
    adjusted = [identity.adjusted_record_id(item["record_id"]) for item in chain]

    # Explicit hypotheses only. Nothing here is accepted without staged-hash proof.
    variants = {
        # root -> physical placement; nested legendary parent/script omitted
        "physical_placement": list(reversed(adjusted[2:])),
        # root -> physical -> reusable legendary parent; script omitted
        "include_legendary_parent": list(reversed(adjusted[1:])),
        # root -> physical -> legendary parent -> script
        "include_script_and_parent": list(reversed(adjusted)),
    }

    # Historical first attempt: include script but omit immediate self-prototype
    # parent when its adjusted ID exactly equals native.parent_prototype_id.
    parent_proto = str(row["native"]["parent_prototype_id"]).lower()
    old = []
    for original_index in range(len(adjusted) - 1, -1, -1):
        element = adjusted[original_index]
        if original_index == 1 and element.hex() == parent_proto:
            continue
        old.append(element)
    variants["historical_self_parent_omit"] = old
    return variants


def simple_state_oracle(staged_report: dict) -> tuple[dict[str, set[int]], dict]:
    oracle: dict[str, set[int]] = {}
    details = {}
    simple_total = 0

    for wad in staged_report.get("wads", []):
        name = str(wad.get("wad") or "").lower()
        if not name or not wad.get("capture_present"):
            continue
        hashes = set()
        states = {}
        class_keys = set()
        registry_hashes = set()

        for entry in wad.get("state_entries", []):
            signature = entry.get("field_signature") or []
            if signature != [{"name": "state", "value_tag": 1}]:
                continue
            parent = entry.get("parent") or {}
            go = parent.get("gameobject")
            if not go:
                continue
            class_key = parent.get("record_class_key_hex")
            if class_key:
                class_keys.add(class_key)
            registry_hashes.add(go["registry_hash_hex"])
            obj_hash = int(go["object_hash_hex"], 16)
            hashes.add(obj_hash)
            states[obj_hash] = {
                "state_raw_hex": entry["state"]["raw_hex"],
                "state_u32": entry["state"]["decoded"],
                "state_row": entry["state_row"],
                "subobj_table_row": entry["subobj_table_row"],
            }

        if not hashes:
            continue
        simple_total += len(hashes)
        expected_registry = f"0x{identity.registry_hash_for_wad(name):016X}"
        if class_keys != {SIMPLE_STATE_CLASS}:
            raise RuntimeError(
                f"{name}: simple state class keys changed: {sorted(class_keys)}"
            )
        if registry_hashes != {expected_registry}:
            raise RuntimeError(
                f"{name}: registry hash mismatch: {sorted(registry_hashes)} "
                f"!= {expected_registry}"
            )
        oracle[name] = hashes
        details[name] = states

    return oracle, {
        "simple_state_parent_count": simple_total,
        "wad_count": len(oracle),
        "states": details,
    }


def discover_prototype_candidates(game_root: Path, rows: list[dict]) -> dict:
    """Inventory candidate identity elements directly from parsed WAD record IDs.

    The previous implementation searched record payloads for references to other
    record IDs and followed two graph hops from the shared loader. That search
    was only a candidate-discovery heuristic: every value it could emit was
    already constrained to be an exact WAD record ID. Therefore scanning payload
    bytes adds no authority to the final 32/32 staged-hash proof.

    We now score the superset of every exact record ID in the 27 tracked WADs.
    This is both faster and more conservative: no true candidate accepted by the
    old graph walk can be lost, while the existing unique-exact staged binding
    remains the sole acceptance criterion.
    """
    prototype = bytes.fromhex(EXPECTED_PROTOTYPE)
    wad_root = game_root / "exec" / "wad" / "pc_le"
    if not wad_root.is_dir():
        raise RuntimeError(f"WAD root missing: {wad_root}")

    wad_names = sorted({row["source"]["wad"] for row in rows})
    support: dict[str, dict] = {}
    occurrences = []

    for wad_index, wad_name in enumerate(wad_names, start=1):
        print(
            f"STATIC_IDENTITY_SCAN wad={wad_index}/{len(wad_names)} name={wad_name}",
            flush=True,
        )
        path = wad_root / wad_name
        if not path.is_file():
            raise RuntimeError(f"missing tracked Legendary WAD: {path}")
        raw = path.read_bytes()
        records = raven.parse_wad(raw)

        for at in find_all(raw, prototype):
            rec, where, rel = record_for_offset(records, at)
            occurrences.append({
                "wad": wad_name,
                "absolute_offset": f"0x{at:X}",
                "where": where,
                "relative_to_record": f"0x{rel:X}" if rel is not None else None,
                "record_name": rec["name"] if rec else None,
                "record_id_hex": rec["id"].hex() if rec else None,
                "record_offset": f"0x{rec['offset']:X}" if rec else None,
            })

        for rec in records:
            raw_hex = rec["id"].hex()
            forms = (
                ("raw_record_id", raw_hex),
                ("adjusted_record_id", identity.adjusted_record_id(raw_hex).hex()),
            )
            for form_name, value_hex in forms:
                item = support.setdefault(value_hex, {
                    "value_hex": value_hex,
                    "wad_hits": set(),
                    "hits": 0,
                    "semantic_hits": 0,
                    "depths": [],
                    "target_names": set(),
                    "forms": set(),
                    "examples": [],
                })
                item["wad_hits"].add(wad_name)
                item["hits"] += 1
                item["target_names"].add(rec["name"])
                item["forms"].add(form_name)
                if any(
                    term in rec["name"].lower()
                    for term in ("chest", "legendary", "proto", "interact")
                ):
                    item["semantic_hits"] += 1
                if len(item["examples"]) < 12:
                    item["examples"].append({
                        "wad": wad_name,
                        "record_name": rec["name"],
                        "record_id_hex": raw_hex,
                        "candidate_form": form_name,
                        "candidate_value_hex": value_hex,
                        "record_offset": f"0x{rec['offset']:X}",
                        "record_kind": rec["kind"],
                    })

        print(
            f"STATIC_IDENTITY_SCAN_DONE wad={wad_index}/{len(wad_names)} "
            f"name={wad_name} candidates_so_far={len(support)}",
            flush=True,
        )

    # Runtime proof in xpl250_funeralinterior identified the exact own identity
    # element of the tracked Legendary chest GameObject. It is not a WAD record
    # ID, so inject it explicitly alongside the already-rejected record-ID
    # candidate space.
    runtime_value = identity.CHEST_OWN_IDENTITY_ELEMENT.hex()
    support.setdefault(runtime_value, {
        "value_hex": runtime_value,
        "wad_hits": {"xpl250_funeralinterior.wad"},
        "hits": 1,
        "semantic_hits": 1,
        "depths": [],
        "target_names": {"runtime_proven_legendary_chest_own_identity"},
        "forms": {"runtime_proven_live_identity"},
        "examples": [{
            "wad": "xpl250_funeralinterior.wad",
            "record_name": "runtime GameObject object+0x40 identity",
            "record_id_hex": None,
            "candidate_form": "runtime_proven_live_identity",
            "candidate_value_hex": runtime_value,
            "record_offset": None,
            "record_kind": "live_runtime_identity",
        }],
    })

    # Keep the loader itself as an explicit control even if a WAD parser change
    # were ever to stop exposing it as a record ID.
    support.setdefault(EXPECTED_PROTOTYPE, {
        "value_hex": EXPECTED_PROTOTYPE,
        "wad_hits": set(),
        "hits": 0,
        "semantic_hits": 0,
        "depths": [],
        "target_names": set(),
        "forms": {"raw_loader_control"},
        "examples": [],
    })

    candidates = []
    for item in support.values():
        candidates.append({
            "value_hex": item["value_hex"],
            "wad_hit_count": len(item["wad_hits"]),
            "wads": sorted(item["wad_hits"]),
            "hits": item["hits"],
            "semantic_hits": item["semantic_hits"],
            "depths": list(item["depths"]),
            "target_names": sorted(item["target_names"]),
            "forms": sorted(item.get("forms", [])),
            "examples": item["examples"],
        })
    candidates.sort(
        key=lambda item: (
            -item["semantic_hits"],
            -item["wad_hit_count"],
            -item["hits"],
            item["value_hex"],
        )
    )
    return {
        "prototype_occurrences": occurrences,
        "candidates": candidates,
    }


def continue_identity_hash(value: int, element: bytes) -> int:
    if len(element) != 16:
        raise ValueError("identity element length changed")
    for byte in element:
        value = ((value + byte) * 0x401) & identity.MASK64
        value ^= value >> 6
    return value & identity.MASK64


def score_candidates(rows: list[dict], oracle: dict[str, set[int]], candidates: list[dict]):
    represented_rows = [
        row for row in rows
        if row["source"]["wad"].lower() in oracle
    ]
    if len(represented_rows) != EXPECTED_STAGED:
        raise RuntimeError(
            f"expected {EXPECTED_STAGED} represented rows, got {len(represented_rows)}"
        )

    grammars = sorted(scene_variants(represented_rows[0]))
    if "historical_self_parent_omit" not in grammars:
        raise RuntimeError("runtime-proven Legendary scene grammar is missing")
    prefix_hashes = {
        grammar: [
            (
                row,
                identity.identity_hash(scene_variants(row)[grammar]),
                oracle[row["source"]["wad"].lower()],
            )
            for row in represented_rows
        ]
        for grammar in grammars
    }

    # Use the smallest staged candidate set as the first discriminator. Almost
    # every false prototype is rejected after one 16-byte continuation.
    for grammar in grammars:
        prefix_hashes[grammar].sort(key=lambda item: len(item[2]))

    scores = []
    total = len(candidates)
    for candidate_index, candidate in enumerate(candidates, start=1):
        if candidate_index == 1 or candidate_index % 5000 == 0 or candidate_index == total:
            print(
                f"STATIC_IDENTITY_SCORE candidate={candidate_index}/{total}",
                flush=True,
            )
        proto = bytes.fromhex(candidate["value_hex"])
        if len(proto) != 16:
            continue
        for grammar in grammars:
            probes = prefix_hashes[grammar]
            first_row, first_prefix, first_oracle = probes[0]
            first_hash = continue_identity_hash(first_prefix, proto)
            if first_hash not in first_oracle:
                scores.append({
                    "prototype_identity_hex": candidate["value_hex"],
                    "scene_grammar": grammar,
                    "match_count": 0,
                    "miss_count": EXPECTED_STAGED,
                    "candidate_static_evidence": {
                        "wad_hit_count": candidate["wad_hit_count"],
                        "hits": candidate["hits"],
                        "semantic_hits": candidate["semantic_hits"],
                        "depths": candidate["depths"],
                        "target_names": candidate["target_names"],
                        "forms": candidate.get("forms", []),
                    },
                    "matches": [],
                    "misses": [{
                        "catalogue_id": first_row["catalogue_id"],
                        "wad": first_row["source"]["wad"],
                        "object_hash_hex": f"0x{first_hash:016X}",
                    }],
                })
                continue

            matches = [{
                "catalogue_id": first_row["catalogue_id"],
                "wad": first_row["source"]["wad"],
                "object_hash_hex": f"0x{first_hash:016X}",
            }]
            misses = []
            for row, prefix_hash, row_oracle in probes[1:]:
                object_hash = continue_identity_hash(prefix_hash, proto)
                entry = {
                    "catalogue_id": row["catalogue_id"],
                    "wad": row["source"]["wad"],
                    "object_hash_hex": f"0x{object_hash:016X}",
                }
                if object_hash in row_oracle:
                    matches.append(entry)
                else:
                    misses.append(entry)
                    # Exact 32/32 is the only success condition. Once this
                    # candidate misses, further rows cannot change acceptance.
                    break

            scores.append({
                "prototype_identity_hex": candidate["value_hex"],
                "scene_grammar": grammar,
                "match_count": len(matches),
                "miss_count": EXPECTED_STAGED - len(matches),
                "candidate_static_evidence": {
                    "wad_hit_count": candidate["wad_hit_count"],
                    "hits": candidate["hits"],
                    "semantic_hits": candidate["semantic_hits"],
                    "depths": candidate["depths"],
                    "target_names": candidate["target_names"],
                },
                "matches": matches,
                "misses": misses,
            })

    scores.sort(
        key=lambda item: (
            -item["match_count"],
            -item["candidate_static_evidence"]["semantic_hits"],
            -item["candidate_static_evidence"]["wad_hit_count"],
            item["scene_grammar"],
            item["prototype_identity_hex"],
        )
    )
    return scores


def build_identity_rows(rows: list[dict], winner: dict, oracle_details: dict) -> list[dict]:
    proto = bytes.fromhex(winner["prototype_identity_hex"])
    grammar = winner["scene_grammar"]
    output = []
    for row in rows:
        scene = scene_variants(row)[grammar]
        object_hash = identity.identity_hash(scene + [proto])
        registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
        state = (
            oracle_details.get(row["source"]["wad"].lower(), {})
            .get(object_hash)
        )
        output.append({
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "instance_guid": row["native"]["instance_guid"],
            "state_instance_guid": row["native"]["state_instance_guid"],
            "scene_grammar": grammar,
            "scene_identity_elements_hex": [element.hex() for element in scene],
            "prototype_identity_element_hex": proto.hex(),
            "registry_hash_hex": f"0x{registry_hash:016X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "serialized_flag1_hex": identity.serialized_payload(
                registry_hash, object_hash
            ).hex(),
            "staged_simple_state_match": state is not None,
            "staged_state": state,
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-root",
        type=Path,
        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"),
    )
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--staged-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    rows = identity.tracked_rows(catalogue)
    if len(rows) != EXPECTED_TRACKED:
        raise RuntimeError(f"expected {EXPECTED_TRACKED} tracked rows, got {len(rows)}")
    prototypes = sorted({row["native"]["prototype_id"] for row in rows})
    if prototypes != [EXPECTED_PROTOTYPE]:
        raise RuntimeError(f"Legendary prototype set changed: {prototypes}")

    staged_report = json.loads(args.staged_report.read_text(encoding="utf-8"))
    oracle, oracle_meta = simple_state_oracle(staged_report)
    represented = sum(
        1 for row in rows if row["source"]["wad"].lower() in oracle
    )
    if represented != EXPECTED_STAGED:
        raise RuntimeError(
            f"expected {EXPECTED_STAGED} represented catalogue rows, got {represented}"
        )

    static = discover_prototype_candidates(args.game_root.resolve(), rows)
    scores = score_candidates(rows, oracle, static["candidates"])
    if not scores:
        raise RuntimeError("no prototype identity candidates discovered")

    best_count = scores[0]["match_count"]
    best = [score for score in scores if score["match_count"] == best_count]
    exact = [
        score for score in best
        if score["match_count"] == EXPECTED_STAGED
    ]
    unique_exact = len(exact) == 1

    winner = exact[0] if unique_exact else None
    identities = (
        build_identity_rows(rows, winner, oracle_meta["states"])
        if winner is not None
        else []
    )
    if winner is not None:
        staged_matches = sum(row["staged_simple_state_match"] for row in identities)
        if staged_matches != EXPECTED_STAGED:
            raise RuntimeError(
                f"winner rebuild matched {staged_matches}, expected {EXPECTED_STAGED}"
            )
        if len({row["object_hash_hex"] for row in identities}) != EXPECTED_TRACKED:
            raise RuntimeError("derived Legendary object hashes are not unique")
    else:
        staged_matches = 0

    status = (
        "EXACT_32_OF_32_STAGED_BINDING"
        if unique_exact
        else "NO_UNIQUE_EXACT_STAGED_BINDING"
    )
    report = {
        "schema": 1,
        "analysis": "legendary_serialized_gameobject_identity_static_resolution",
        "status": status,
        "tracked_catalogue_count": len(rows),
        "staged_represented_count": represented,
        "simple_state_oracle": {
            "class_key_hex": SIMPLE_STATE_CLASS,
            "parent_count": oracle_meta["simple_state_parent_count"],
            "wad_count": oracle_meta["wad_count"],
        },
        "prototype_loader_id": EXPECTED_PROTOTYPE,
        "prototype_occurrences": static["prototype_occurrences"],
        "prototype_candidate_count": len(static["candidates"]),
        "candidate_space_includes_adjusted_record_ids": True,
        "candidate_space_includes_runtime_proven_own_identity": True,
        "prototype_candidates": static["candidates"][:128],
        "score_count": len(scores),
        "top_scores": scores[:80],
        "best_match_count": best_count,
        "best_score_tie_count": len(best),
        "unique_exact_binding": unique_exact,
        "winner": winner,
        "identities": identities,
        "state_semantics_proven": False,
        "safety": {
            "static_game_files_read_only": True,
            "archived_checkpoint_only": True,
            "process_accessed": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_files_written": False,
            "raven_runtime_modified": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "Completionist Map - Legendary serialized GameObject identity resolution",
        f"status={status}",
        f"tracked={len(rows)} staged_represented={represented}",
        (
            f"prototype_candidates={len(static['candidates'])} "
            f"scores={len(scores)} best_match_count={best_count} "
            f"best_score_tie_count={len(best)}"
        ),
        f"simple_state_parents={oracle_meta['simple_state_parent_count']}",
        "state_semantics_proven=false",
        "",
        "TOP SCORES",
    ]
    for score in scores[:30]:
        ev = score["candidate_static_evidence"]
        lines.append(
            f"match={score['match_count']}/{EXPECTED_STAGED} "
            f"grammar={score['scene_grammar']} "
            f"proto={score['prototype_identity_hex']} "
            f"semantic_hits={ev['semantic_hits']} wad_hits={ev['wad_hit_count']} "
            f"forms={','.join(ev.get('forms', []))} "
            f"targets={','.join(ev['target_names'][:6])}"
        )
    if winner is not None:
        lines += [
            "",
            "WINNER",
            f"grammar={winner['scene_grammar']}",
            f"prototype_identity_hex={winner['prototype_identity_hex']}",
            f"staged_matches={staged_matches}/{EXPECTED_STAGED}",
            "",
            "IDENTITIES",
        ]
        for row in identities:
            state_text = (
                f" state_u32={row['staged_state']['state_u32']} "
                f"state_raw={row['staged_state']['state_raw_hex']}"
                if row["staged_state"] is not None
                else " state=absent_from_frozen_capture"
            )
            lines.append(
                f"{row['catalogue_id']} object_hash={row['object_hash_hex']} "
                f"payload={row['serialized_flag1_hex']} wad={row['wad']}{state_text}"
            )
    lines += [
        "",
        "SAFETY",
        "static_game_files_read_only=true",
        "archived_checkpoint_only=true",
        "process_accessed=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "LEGENDARY_SERIALIZED_IDENTITY_STATIC_RESOLUTION_COMPLETE "
        f"status={status} best={best_count}/{EXPECTED_STAGED} "
        f"ties={len(best)} candidates={len(static['candidates'])}"
    )
    print(
        "process_accessed=false active_save_opened=false "
        "save_or_progression_written=false raven_runtime_modified=false"
    )
    return 0 if unique_exact else 2


if __name__ == "__main__":
    raise SystemExit(main())
