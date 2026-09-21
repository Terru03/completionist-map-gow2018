#!/usr/bin/env python3
"""Resolve nested Raven GameObject identities with reversible native hashing.

Static/read-only. Uses:
  * canonical 53-Raven catalogue;
  * archived packed Channel-A replay with exact Raven-state GameObject hashes;
  * shipped WAD files.

For ordinary Raven chains, the existing static identity sequence already
matches live checkpoint hashes. Nested Raven containers are different: the
intermediate parent contributes a metadata identity vector that is not captured
by the simplified transform-record sequence.

The native byte hash is reversible. For each nested Raven, reverse the known
child-record + Raven-prototype suffix from every live hash in that WAD. Sibling
Ravens under the same parent must converge on one common post-parent hash state.
Then solve the parent contribution directly from 16-byte windows present in the
parent prototype record. One- and two-element vectors are tested with exact
64-bit equality only.

No process access, save access, or writes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

MASK64 = 0xFFFFFFFFFFFFFFFF
MOD64 = 1 << 64
MUL = 0x401
MUL_INV = pow(MUL, -1, MOD64)

PERCH_HOP_ELEMENT = bytes.fromhex("805b030bf339564cb157837c52906465")
HOVER_ELEMENT = bytes.fromhex("50dafefd65605b41a2aed011a5f4ce22")
PERCH_HOP_PROTOTYPES = {
    "408280c2887ca5d7cba94feea56888d0",
    "f4f22e4546b2194891ad7f9a7c5b6dc4",
}
HOVER_PROTOTYPES = {
    "0c397df6a1dcb23d8859241c3c713ac1",
    "3a519f6b5782fea73e617a71a7c726ce",
    "bd01be1157e065d6910e0c26c6fae6ab",
    "cbd08dc1fea41249375bb6b2fa795111",
}


def load_catalogue_helper():
    p = Path(__file__).with_name("raven_catalogue.py")
    spec = importlib.util.spec_from_file_location("raven_catalogue_nested_identity", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {p}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RC = load_catalogue_helper()


def adjusted_record_id(raw: bytes) -> bytes:
    if len(raw) != 16:
        raise ValueError("record ID is not 16 bytes")
    out = bytearray(raw)
    out[12] = (out[12] - 1) & 0xFF
    return bytes(out)


def prototype_element(row: dict) -> bytes:
    pid = row["native"]["prototype_id"]
    if pid in PERCH_HOP_PROTOTYPES:
        return PERCH_HOP_ELEMENT
    if pid in HOVER_PROTOTYPES:
        return HOVER_ELEMENT
    raise RuntimeError(f"unclassified Raven prototype {pid}")


def scene_elements(row: dict) -> list[bytes]:
    return [
        adjusted_record_id(bytes.fromhex(item["record_id"]))
        for item in reversed(row["source"]["transform_chain"])
    ]


def base_elements(row: dict) -> list[bytes]:
    return scene_elements(row) + [prototype_element(row)]


def hash_byte(state: int, byte: int) -> int:
    state = ((state + byte) * MUL) & MASK64
    return state ^ (state >> 6)


def hash_element(state: int, element: bytes) -> int:
    if len(element) != 16:
        raise ValueError("identity element length changed")
    for byte in element:
        state = hash_byte(state, byte)
    return state


def hash_elements(elements: list[bytes], state: int = 0) -> int:
    for element in elements:
        state = hash_element(state, element)
    return state


def undo_xorshift_right(value: int, shift: int = 6) -> int:
    result = value
    amount = shift
    while amount < 64:
        result ^= value >> amount
        amount += shift
    return result & MASK64


def reverse_byte(state: int, byte: int) -> int:
    mixed = undo_xorshift_right(state, 6)
    before_add = (mixed * MUL_INV) & MASK64
    return (before_add - byte) & MASK64


def reverse_element(state: int, element: bytes) -> int:
    if len(element) != 16:
        raise ValueError("identity element length changed")
    for byte in reversed(element):
        state = reverse_byte(state, byte)
    return state


def reverse_elements(state: int, elements: list[bytes]) -> int:
    for element in reversed(elements):
        state = reverse_element(state, element)
    return state


def normal_wad(value: str) -> str:
    return Path(value).stem.lower() + ".wad"


def replay_live_hashes(report: dict) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for record in report.get("records", []):
        name = record.get("name")
        if not name:
            continue
        wad = normal_wad(name)
        for candidate in record.get("decode", {}).get("candidates", []):
            for parent in candidate.get("carrier", {}).get("raven_state_parent_keys", []):
                go = parent.get("parsed_gameobject")
                if go:
                    result.setdefault(wad, set()).add(int(go["object_hash_hex"], 16))
    return result


def parent_split(row: dict) -> tuple[list[bytes], bytes, bytes]:
    """Return outer-prefix elements, simplified parent element, child element."""
    scene = scene_elements(row)
    if len(scene) < 2:
        raise RuntimeError(f"{row['catalogue_id']}: nested solve requires parent + child")
    return scene[:-2], scene[-2], scene[-1]


def suffix_for_row(row: dict) -> list[bytes]:
    _outer, _parent, child = parent_split(row)
    return [child, prototype_element(row)]


def required_parent_states(row: dict, live_hashes: set[int]) -> dict[int, int]:
    suffix = suffix_for_row(row)
    return {live: reverse_elements(live, suffix) for live in live_hashes}


def recover_common_parent_state(rows: list[dict], live_hashes: set[int]) -> dict:
    per_row = {}
    state_sets = []
    for row in rows:
        mapping = required_parent_states(row, live_hashes)
        reverse_map: dict[int, list[int]] = {}
        for live, state in mapping.items():
            reverse_map.setdefault(state, []).append(live)
        per_row[row["catalogue_id"]] = {
            "by_live_hash": {
                f"0x{live:016X}": f"0x{state:016X}" for live, state in mapping.items()
            },
            "by_parent_state": {
                f"0x{state:016X}": [f"0x{x:016X}" for x in sorted(values)]
                for state, values in reverse_map.items()
            },
        }
        state_sets.append(set(reverse_map))

    common = set.intersection(*state_sets) if state_sets else set()
    assignments = {}
    if len(common) == 1:
        target = next(iter(common))
        for row in rows:
            mapping = required_parent_states(row, live_hashes)
            matches = [live for live, state in mapping.items() if state == target]
            assignments[row["catalogue_id"]] = [f"0x{x:016X}" for x in sorted(matches)]
        target_hex = f"0x{target:016X}"
    else:
        target = None
        target_hex = None

    return {
        "common_parent_state_count": len(common),
        "common_parent_states_hex": [f"0x{x:016X}" for x in sorted(common)],
        "target_parent_state_hex": target_hex,
        "assignments": assignments,
        "per_row": per_row,
        "_target": target,
    }


def candidate_windows(parent_record: dict, simplified_parent: bytes) -> list[dict]:
    """All unique 16-byte payload windows plus explicit parent IDs.

    Exact 64-bit acceptance makes false positives vanishingly unlikely, so raw
    sliding windows are safe to consider. An adjusted-byte-12 variant is also
    included because scene-record identity elements use that transform.
    """
    data = parent_record["data"]
    result = []
    seen = set()

    def add(element: bytes, mode: str, offset: int | None, source: bytes):
        key = element
        if key in seen:
            return
        seen.add(key)
        result.append({
            "element": element,
            "mode": mode,
            "offset": offset,
            "source": source,
        })

    for off in range(0, max(0, len(data) - 15)):
        raw = data[off:off + 16]
        add(raw, "raw_payload_window", off, raw)
        add(adjusted_record_id(raw), "adjusted_payload_window", off, raw)

    add(parent_record["id"], "parent_record_id_raw", None, parent_record["id"])
    add(adjusted_record_id(parent_record["id"]), "parent_record_id_adjusted", None, parent_record["id"])
    add(simplified_parent, "catalogue_simplified_parent", None, simplified_parent)
    return result


def describe_candidate(candidate: dict) -> dict:
    return {
        "element_hex": candidate["element"].hex(),
        "mode": candidate["mode"],
        "source_payload_offset": (
            f"0x{candidate['offset']:X}" if candidate["offset"] is not None else None
        ),
        "source_hex": candidate["source"].hex(),
    }


def solve_parent_vector(
    start_state: int,
    target_state: int,
    parent_records: list[dict],
    simplified_parent: bytes,
) -> list[dict]:
    solutions = []
    for parent_record in parent_records:
        candidates = candidate_windows(parent_record, simplified_parent)

        # One-element vector.
        for candidate in candidates:
            got = hash_element(start_state, candidate["element"])
            if got == target_state:
                solutions.append({
                    "vector_length": 1,
                    "parent_prototype_record_name": parent_record["name"],
                    "parent_prototype_record_id": parent_record["id"].hex(),
                    "elements": [describe_candidate(candidate)],
                })

        # Two-element vector, meet in the middle:
        # start --A--> middle --B--> target.
        forward: dict[int, list[dict]] = {}
        for candidate in candidates:
            middle = hash_element(start_state, candidate["element"])
            forward.setdefault(middle, []).append(candidate)

        for second in candidates:
            needed_middle = reverse_element(target_state, second["element"])
            firsts = forward.get(needed_middle)
            if not firsts:
                continue
            for first in firsts:
                solutions.append({
                    "vector_length": 2,
                    "parent_prototype_record_name": parent_record["name"],
                    "parent_prototype_record_id": parent_record["id"].hex(),
                    "elements": [describe_candidate(first), describe_candidate(second)],
                })

    unique = {}
    for solution in solutions:
        key = tuple(x["element_hex"] for x in solution["elements"])
        unique[key] = solution
    return list(unique.values())


def solve_wad(
    wad: str,
    rows: list[dict],
    live_hashes: set[int],
    wad_info: dict,
) -> dict:
    base_rows = []
    mismatched = []
    for row in rows:
        got = hash_elements(base_elements(row))
        item = {
            "catalogue_id": row["catalogue_id"],
            "object_name": row["native"]["object_name"],
            "base_hash_hex": f"0x{got:016X}",
            "base_matches_live": got in live_hashes,
        }
        base_rows.append(item)
        if got not in live_hashes:
            mismatched.append(row)

    result = {
        "wad": wad,
        "live_object_hashes_hex": [f"0x{x:016X}" for x in sorted(live_hashes)],
        "catalogue_raven_count": len(rows),
        "base_match_count": sum(x["base_matches_live"] for x in base_rows),
        "rows": base_rows,
        "nested_resolution": None,
    }
    if not mismatched:
        result["status"] = "all_base_hashes_match_live"
        return result

    # A nested WAD should have all catalogue Ravens under one immediate parent.
    parent_ids = {row["native"]["parent_prototype_id"] for row in mismatched}
    if len(parent_ids) != 1:
        result["status"] = "multiple_nested_parent_ids"
        result["parent_ids"] = sorted(parent_ids)
        return result

    # Recover the exact common state after the parent contribution by reversing
    # each Raven's known child+prototype suffix from every observed live hash.
    recovered = recover_common_parent_state(mismatched, live_hashes)
    target = recovered.pop("_target")

    outer_states = {}
    simplified_parents = {}
    for row in mismatched:
        outer, simplified_parent, _child = parent_split(row)
        outer_states[row["catalogue_id"]] = hash_elements(outer)
        simplified_parents[row["catalogue_id"]] = simplified_parent

    unique_outer = set(outer_states.values())
    unique_parent = set(simplified_parents.values())
    nested = {
        "parent_prototype_id": next(iter(parent_ids)),
        "recovered_parent_state": recovered,
        "outer_prefix_states_hex": {
            cid: f"0x{state:016X}" for cid, state in outer_states.items()
        },
        "simplified_parent_elements_hex": {
            cid: value.hex() for cid, value in simplified_parents.items()
        },
        "common_outer_prefix_state": (
            f"0x{next(iter(unique_outer)):016X}" if len(unique_outer) == 1 else None
        ),
        "common_simplified_parent_element": (
            next(iter(unique_parent)).hex() if len(unique_parent) == 1 else None
        ),
        "parent_prototype_records": [],
        "vector_solutions": [],
    }

    parent_id = bytes.fromhex(next(iter(parent_ids)))
    parent_records = wad_info["by_id"].get(parent_id, [])
    nested["parent_prototype_records"] = [
        {
            "name": rec["name"],
            "id": rec["id"].hex(),
            "offset": f"0x{rec['offset']:X}",
            "kind": rec["kind"],
            "flags": rec["flags"],
            "size": rec["size"],
        }
        for rec in parent_records
    ]

    if target is None:
        result["status"] = "parent_state_not_unique"
    elif len(unique_outer) != 1 or len(unique_parent) != 1:
        result["status"] = "nested_prefix_not_common"
    elif not parent_records:
        result["status"] = "parent_prototype_record_missing"
    else:
        start = next(iter(unique_outer))
        simplified_parent = next(iter(unique_parent))
        solutions = solve_parent_vector(start, target, parent_records, simplified_parent)
        nested["vector_solutions"] = solutions
        if len(solutions) == 1:
            result["status"] = "unique_parent_vector"
        elif solutions:
            result["status"] = "multiple_parent_vectors"
        else:
            result["status"] = "parent_vector_not_found"

        # Build exact per-Raven reconstructed identities if the vector is unique.
        if len(solutions) == 1:
            vector = [bytes.fromhex(x["element_hex"]) for x in solutions[0]["elements"]]
            reconstructed = []
            for row in mismatched:
                outer, _parent, child = parent_split(row)
                elements = outer + vector + [child, prototype_element(row)]
                got = hash_elements(elements)
                expected = recovered["assignments"].get(row["catalogue_id"], [])
                reconstructed.append({
                    "catalogue_id": row["catalogue_id"],
                    "object_name": row["native"]["object_name"],
                    "object_hash_hex": f"0x{got:016X}",
                    "expected_live_hashes_hex": expected,
                    "exact_assignment_match": f"0x{got:016X}" in expected,
                    "identity_elements_hex": [x.hex() for x in elements],
                })
            nested["reconstructed_rows"] = reconstructed

    result["nested_resolution"] = nested
    return result


def self_test_hash_inverse() -> None:
    vectors = [
        [bytes.fromhex("6a40442bc7277743a15f2986a3279901")],
        [
            bytes.fromhex("6a40442bc7277743a15f2986a3279901"),
            bytes.fromhex("82bdafe150a9ea49ac27331f1525d1d5"),
            bytes.fromhex("160d2d64d4a5f04a93776e075d9a543c"),
            PERCH_HOP_ELEMENT,
        ],
    ]
    for elements in vectors:
        final = hash_elements(elements)
        recovered = reverse_elements(final, elements)
        if recovered != 0:
            raise RuntimeError(
                f"native hash inverse self-test failed: recovered 0x{recovered:016X}"
            )


def main() -> int:
    self_test_hash_inverse()

    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue", type=Path, required=True)
    ap.add_argument("--replay-report", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    a = ap.parse_args()

    catalogue = json.loads(a.catalogue.read_text(encoding="utf-8"))
    rows = catalogue["ravens"]
    if len(rows) != 53:
        raise RuntimeError(f"expected 53 Ravens, found {len(rows)}")

    replay = json.loads(a.replay_report.read_text(encoding="utf-8"))
    live_by_wad = replay_live_hashes(replay)
    rows_by_wad: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_wad.setdefault(normal_wad(row["source"]["wad"]), []).append(row)

    result_wads = []
    for wad, live_hashes in sorted(live_by_wad.items()):
        catalogue_rows = rows_by_wad.get(wad, [])
        if not catalogue_rows:
            continue
        path = a.game_root / "exec" / "wad" / "pc_le" / wad
        raw = path.read_bytes()
        records = RC.parse_wad(raw)
        by_id: dict[bytes, list[dict]] = {}
        for record in records:
            by_id.setdefault(record["id"], []).append(record)
        result_wads.append(
            solve_wad(wad, catalogue_rows, live_hashes, {"records": records, "by_id": by_id})
        )

    all_rows = [row for wad in result_wads for row in wad["rows"]]
    statuses = {}
    for wad in result_wads:
        statuses[wad["status"]] = statuses.get(wad["status"], 0) + 1

    summary = {
        "catalogue_rows_with_live_wad": len(all_rows),
        "base_hash_matches_live": sum(row["base_matches_live"] for row in all_rows),
        "base_hash_mismatches": sum(not row["base_matches_live"] for row in all_rows),
        "wad_status_counts": statuses,
        "unique_parent_vector_wads": sum(
            wad["status"] == "unique_parent_vector" for wad in result_wads
        ),
        "exact_nested_rows_reconstructed": sum(
            sum(
                row.get("exact_assignment_match", False)
                for row in (wad.get("nested_resolution") or {}).get("reconstructed_rows", [])
            )
            for wad in result_wads
        ),
    }

    report = {
        "schema": 2,
        "analysis": "raven_nested_container_identity_reversible_hash_resolution",
        "summary": summary,
        "wads": result_wads,
        "safety": {
            "static_game_files_read_only": True,
            "game_process_accessed": False,
            "save_opened": False,
            "save_written": False,
            "progression_written": False,
        },
    }
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Raven nested-container identity reversible-hash resolution",
        f"catalogue_rows_with_live_wad={summary['catalogue_rows_with_live_wad']} "
        f"base_hash_matches_live={summary['base_hash_matches_live']} "
        f"base_hash_mismatches={summary['base_hash_mismatches']} "
        f"unique_parent_vector_wads={summary['unique_parent_vector_wads']} "
        f"exact_nested_rows_reconstructed={summary['exact_nested_rows_reconstructed']}",
        f"wad_status_counts={summary['wad_status_counts']}",
        "",
    ]
    for wad in result_wads:
        lines.append(
            f"WAD {wad['wad']} status={wad['status']} "
            f"base_matches={wad['base_match_count']}/{wad['catalogue_raven_count']} "
            f"live={','.join(wad['live_object_hashes_hex'])}"
        )
        nested = wad.get("nested_resolution")
        if nested:
            recovered = nested["recovered_parent_state"]
            lines.append(
                f"  parent_id={nested['parent_prototype_id']} "
                f"common_parent_states={recovered['common_parent_state_count']} "
                f"target={recovered['target_parent_state_hex']} "
                f"outer={nested['common_outer_prefix_state']}"
            )
            for cid, live in recovered.get("assignments", {}).items():
                lines.append(f"  ASSIGN {cid} -> {','.join(live)}")
            for solution in nested.get("vector_solutions", []):
                desc = " | ".join(
                    f"{x['element_hex']} {x['mode']} @{x['source_payload_offset']}"
                    for x in solution["elements"]
                )
                lines.append(
                    f"  VECTOR length={solution['vector_length']} "
                    f"parent={solution['parent_prototype_record_name']} {desc}"
                )
            for row in nested.get("reconstructed_rows", []):
                lines.append(
                    f"  REBUILT {row['catalogue_id']} hash={row['object_hash_hex']} "
                    f"expected={','.join(row['expected_live_hashes_hex'])} "
                    f"exact={str(row['exact_assignment_match']).lower()}"
                )
        lines.append("")

    lines += [
        "static_game_files_read_only=true",
        "game_process_accessed=false",
        "save_opened=false save_written=false progression_written=false",
    ]
    a.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_NESTED_CONTAINER_REVERSIBLE_HASH_COMPLETE "
        f"base_matches={summary['base_hash_matches_live']} "
        f"mismatches={summary['base_hash_mismatches']} "
        f"unique_parent_vector_wads={summary['unique_parent_vector_wads']} "
        f"exact_nested_rows_reconstructed={summary['exact_nested_rows_reconstructed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
