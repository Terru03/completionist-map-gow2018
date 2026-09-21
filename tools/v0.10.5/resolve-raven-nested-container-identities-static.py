#!/usr/bin/env python3
"""Resolve missing nested Raven-container identity elements from static WADs.

Read-only/static. Uses:
  * canonical 53-Raven catalogue;
  * archived packed Channel-A replay with exact Raven-state parent GameObject hashes;
  * shipped WAD files.

For WADs where the existing scene-record + final-prototype identity hash does
not match the live checkpoint object hashes, inspect the final Raven object's
parent prototype record (for example goProtoRavens/goProtoRaven_03), collect
referenced 16-byte WAD record IDs, derive raw and byte-12-decremented candidate
identity elements, and test every insertion position.

A solution is accepted only when the rebuilt hash equals an observed live
GameObject object_hash in the same WAD.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

MASK64 = 0xFFFFFFFFFFFFFFFF
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


def base_elements(row: dict) -> list[bytes]:
    scene = [
        adjusted_record_id(bytes.fromhex(item["record_id"]))
        for item in reversed(row["source"]["transform_chain"])
    ]
    return scene + [prototype_element(row)]


def identity_hash(elements: list[bytes]) -> int:
    value = 0
    for element in elements:
        if len(element) != 16:
            raise ValueError("identity element length changed")
        for byte in element:
            value = ((value + byte) * 0x401) & MASK64
            value ^= value >> 6
    return value


def normal_wad(value: str) -> str:
    return (Path(value).stem.lower() + ".wad")


def replay_live_hashes(report: dict) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for record in report.get("records", []):
        name = record.get("name")
        if not name:
            continue
        wad = normal_wad(name)
        for candidate in record.get("decode", {}).get("candidates", []):
            carrier = candidate.get("carrier", {})
            for parent in carrier.get("raven_state_parent_keys", []):
                go = parent.get("parsed_gameobject")
                if not go:
                    continue
                result.setdefault(wad, set()).add(int(go["object_hash_hex"], 16))
    return result


def record_references(record: dict, by_id: dict[bytes, list[dict]]) -> list[dict]:
    refs = []
    data = record["data"]
    for off in range(0, max(0, len(data) - 15)):
        value = data[off:off + 16]
        targets = by_id.get(value)
        if not targets:
            continue
        refs.append({
            "offset": off,
            "value": value,
            "targets": targets,
        })
    return refs


def candidate_elements(parent_record: dict, by_id: dict[bytes, list[dict]]) -> list[dict]:
    result = []
    seen = set()
    refs = record_references(parent_record, by_id)
    for ref in refs:
        for mode, element in (
            ("raw_record_id", ref["value"]),
            ("adjusted_record_id", adjusted_record_id(ref["value"])),
        ):
            key = (mode, element)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "mode": mode,
                "element": element,
                "source_offset": ref["offset"],
                "source_value": ref["value"],
                "target_names": sorted({x["name"] for x in ref["targets"]}),
                "target_ids": sorted({x["id"].hex() for x in ref["targets"]}),
            })
    return result


def solve_row(row: dict, wad_info: dict, live_hashes: set[int]) -> dict:
    base = base_elements(row)
    base_hash = identity_hash(base)
    if base_hash in live_hashes:
        return {
            "catalogue_id": row["catalogue_id"],
            "object_name": row["native"]["object_name"],
            "status": "base_hash_matches_live",
            "base_hash_hex": f"0x{base_hash:016X}",
            "solutions": [],
        }

    parent_id = bytes.fromhex(row["native"]["parent_prototype_id"])
    parent_records = wad_info["by_id"].get(parent_id, [])
    if not parent_records:
        return {
            "catalogue_id": row["catalogue_id"],
            "object_name": row["native"]["object_name"],
            "status": "parent_prototype_record_missing",
            "base_hash_hex": f"0x{base_hash:016X}",
            "parent_prototype_id": parent_id.hex(),
            "solutions": [],
        }

    solutions = []
    tested = 0
    for parent_record in parent_records:
        candidates = candidate_elements(parent_record, wad_info["by_id"])
        for candidate in candidates:
            element = candidate["element"]

            # Model A: parent metadata contributes an additional identity element.
            for pos in range(len(base) + 1):
                tested += 1
                trial = base[:pos] + [element] + base[pos:]
                got = identity_hash(trial)
                if got in live_hashes:
                    solutions.append({
                        "operation": "insert",
                        "live_object_hash_hex": f"0x{got:016X}",
                        "insert_position": pos,
                        "candidate_mode": candidate["mode"],
                        "candidate_element_hex": element.hex(),
                        "parent_prototype_record_name": parent_record["name"],
                        "parent_prototype_record_id": parent_record["id"].hex(),
                        "source_payload_offset": f"0x{candidate['source_offset']:X}",
                        "source_reference_hex": candidate["source_value"].hex(),
                        "target_record_names": candidate["target_names"],
                        "target_record_ids": candidate["target_ids"],
                        "identity_elements_hex": [x.hex() for x in trial],
                    })

            # Model B: an intermediate parent object's own object+0x40 identity
            # replaces the transform-record-derived element currently used by
            # the simplified catalogue reconstruction.
            for pos in range(len(base)):
                tested += 1
                trial = list(base)
                replaced = trial[pos]
                trial[pos] = element
                got = identity_hash(trial)
                if got in live_hashes:
                    solutions.append({
                        "operation": "replace",
                        "live_object_hash_hex": f"0x{got:016X}",
                        "replace_position": pos,
                        "replaced_element_hex": replaced.hex(),
                        "candidate_mode": candidate["mode"],
                        "candidate_element_hex": element.hex(),
                        "parent_prototype_record_name": parent_record["name"],
                        "parent_prototype_record_id": parent_record["id"].hex(),
                        "source_payload_offset": f"0x{candidate['source_offset']:X}",
                        "source_reference_hex": candidate["source_value"].hex(),
                        "target_record_names": candidate["target_names"],
                        "target_record_ids": candidate["target_ids"],
                        "identity_elements_hex": [x.hex() for x in trial],
                    })

    unique = {}
    for solution in solutions:
        key = (
            solution["operation"],
            solution["live_object_hash_hex"],
            solution.get("insert_position"),
            solution.get("replace_position"),
            solution["candidate_element_hex"],
        )
        unique[key] = solution
    solutions = list(unique.values())

    return {
        "catalogue_id": row["catalogue_id"],
        "object_name": row["native"]["object_name"],
        "status": "unique_solution" if len(solutions) == 1 else (
            "multiple_solutions" if solutions else "no_solution"
        ),
        "base_hash_hex": f"0x{base_hash:016X}",
        "parent_prototype_id": parent_id.hex(),
        "parent_prototype_records": [
            {
                "name": rec["name"],
                "id": rec["id"].hex(),
                "offset": f"0x{rec['offset']:X}",
                "kind": rec["kind"],
                "flags": rec["flags"],
                "size": rec["size"],
            }
            for rec in parent_records
        ],
        "candidate_trials": tested,
        "solutions": solutions,
    }


def main() -> int:
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

    wad_cache = {}
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
        info = {"records": records, "by_id": by_id}
        wad_cache[wad] = info
        solved = [solve_row(row, info, live_hashes) for row in catalogue_rows]
        result_wads.append({
            "wad": wad,
            "live_object_hashes_hex": [f"0x{x:016X}" for x in sorted(live_hashes)],
            "catalogue_raven_count": len(catalogue_rows),
            "rows": solved,
        })

    all_rows = [row for wad in result_wads for row in wad["rows"]]
    summary = {
        "catalogue_rows_with_live_wad": len(all_rows),
        "base_hash_matches_live": sum(row["status"] == "base_hash_matches_live" for row in all_rows),
        "unique_solution": sum(row["status"] == "unique_solution" for row in all_rows),
        "multiple_solutions": sum(row["status"] == "multiple_solutions" for row in all_rows),
        "no_solution": sum(row["status"] == "no_solution" for row in all_rows),
        "parent_prototype_record_missing": sum(
            row["status"] == "parent_prototype_record_missing" for row in all_rows
        ),
    }

    report = {
        "schema": 1,
        "analysis": "raven_nested_container_identity_static_resolution",
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
        "Raven nested-container identity static resolution",
        " ".join(f"{k}={v}" for k, v in summary.items()),
        "",
    ]
    for wad in result_wads:
        lines.append(
            f"WAD {wad['wad']} live={','.join(wad['live_object_hashes_hex'])} "
            f"catalogue_ravens={wad['catalogue_raven_count']}"
        )
        for row in wad["rows"]:
            lines.append(
                f"  {row['catalogue_id']} object={row['object_name']} "
                f"base={row['base_hash_hex']} status={row['status']}"
            )
            for solution in row.get("solutions", []):
                lines.append(
                    f"    MATCH operation={solution['operation']} live={solution['live_object_hash_hex']} "
                    f"pos={solution.get('insert_position', solution.get('replace_position'))} "
                    f"element={solution['candidate_element_hex']} mode={solution['candidate_mode']} "
                    f"parent={solution['parent_prototype_record_name']} "
                    f"source={solution['source_reference_hex']}@{solution['source_payload_offset']} "
                    f"targets={','.join(solution['target_record_names'])}"
                )
        lines.append("")
    lines += [
        "static_game_files_read_only=true",
        "game_process_accessed=false",
        "save_opened=false save_written=false progression_written=false",
    ]
    a.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_NESTED_CONTAINER_IDENTITY_STATIC_COMPLETE "
        + " ".join(f"{k}={v}" for k, v in summary.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
