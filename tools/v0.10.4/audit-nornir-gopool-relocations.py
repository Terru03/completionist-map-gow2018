#!/usr/bin/env python3
"""Read-only audit of WAD_R_UI GOPool growth vs DCB relocation semantics.

The failed Nornir runtime candidate grew the GOPool by two 16-byte rows. DCB
chunk 15 stores offsets of 64-bit relative-pointer fields inside chunk 12. Any
insertion into chunk 12 can therefore require BOTH relocation-field offsets and
relative deltas to move. This audit compares the frozen Raven production DCB
with the failed Nornir candidate and computes the exact relocation transform
that a structurally correct +32-byte insertion requires.

No game file is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_RAVEN_DCB = "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d"
RESULT = "NORNIR_GOPOOL_RELOCATION_AUDIT_READ_ONLY"
GOP_BASE = 0x90
GOP_ROW = 16
EXPECTED_OLD_ROWS = 257
EXPECTED_NEW_ROWS = 259
EXPECTED_INSERT_BYTES = (EXPECTED_NEW_ROWS - EXPECTED_OLD_ROWS) * GOP_ROW
NORNIR_MAP_HASH = 0xE14C66C3B90633E0
NORNIR_HUD_HASH = 0x7DDC11175EBD1E94


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def parse_chunks(raw: bytes) -> dict[int, dict]:
    chunks: dict[int, dict] = {}
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short DCB header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(flags == 0x10 and padded <= len(raw), f"invalid DCB chunk at {off:#x}")
        check(kind not in chunks, f"duplicate DCB chunk {kind}")
        chunks[kind] = {"kind": kind, "header": off, "start": start, "end": end, "padded": padded,
                        "payload": raw[start:end]}
        off = padded
    check(off == len(raw), "DCB chunk walk did not end at EOF")
    check(set(chunks) == {11, 12, 13, 14, 15}, f"unexpected DCB chunks: {sorted(chunks)}")
    return chunks


def parse_relocations(payload: bytes) -> list[int]:
    check(len(payload) >= 4, "relocation chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    check(len(payload) == 4 + count * 4,
          f"relocation payload size mismatch: count={count} bytes={len(payload)}")
    rows = list(struct.unpack_from(f"<{count}I", payload, 4)) if count else []
    check(len(set(rows)) == len(rows), "duplicate relocation field offset")
    return rows


def relative_pointer(data: bytes, field: int) -> tuple[int, int]:
    check(0 <= field <= len(data) - 8, f"relocation field outside data chunk: {field:#x}")
    delta = struct.unpack_from("<q", data, field)[0]
    target = field + delta
    check(0 <= target < len(data),
          f"relative pointer target outside data chunk: field={field:#x} delta={delta:#x} target={target:#x}")
    return delta, target


def gopool(data: bytes) -> tuple[int, list[dict], int]:
    check(len(data) >= GOP_BASE, "data chunk too short for GOPool")
    count = struct.unpack_from("<I", data, 8)[0]
    end = GOP_BASE + count * GOP_ROW
    check(end <= len(data), "GOPool exceeds data chunk")
    rows = []
    for index in range(count):
        at = GOP_BASE + index * GOP_ROW
        uid, capacity = struct.unpack_from("<QH", data, at)
        rows.append({"index": index, "uid": uid, "capacity": capacity})
    return count, rows, end


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-dcb", type=Path, required=True)
    ap.add_argument("--candidate-dcb", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raven_raw = args.raven_dcb.read_bytes()
    candidate_raw = args.candidate_dcb.read_bytes()
    check(sha(raven_raw) == EXPECTED_RAVEN_DCB,
          "baseline wad_r_ui.dcb is not frozen Raven production")

    raven_chunks = parse_chunks(raven_raw)
    candidate_chunks = parse_chunks(candidate_raw)
    raven_data = raven_chunks[12]["payload"]
    candidate_data = candidate_chunks[12]["payload"]
    raven_reloc_payload = raven_chunks[15]["payload"]
    candidate_reloc_payload = candidate_chunks[15]["payload"]
    raven_relocs = parse_relocations(raven_reloc_payload)
    candidate_relocs = parse_relocations(candidate_reloc_payload)

    old_count, old_rows, insert_at = gopool(raven_data)
    new_count, new_rows, new_pool_end = gopool(candidate_data)
    check(old_count == EXPECTED_OLD_ROWS, f"Raven GOPool row count changed: {old_count}")
    check(new_count == EXPECTED_NEW_ROWS, f"failed candidate GOPool row count changed: {new_count}")
    check(new_pool_end - insert_at == EXPECTED_INSERT_BYTES,
          f"unexpected GOPool growth: {new_pool_end-insert_at} bytes")
    check(len(candidate_data) == len(raven_data) + EXPECTED_INSERT_BYTES,
          "candidate data chunk is not exactly +32 bytes")
    check(candidate_data[GOP_BASE:insert_at] == raven_data[GOP_BASE:insert_at],
          "an existing GOPool row changed")
    check(candidate_data[new_pool_end:] == raven_data[insert_at:],
          "post-GOPool data tail was not shifted byte-for-byte")

    map_rows = [r for r in new_rows if r["uid"] == NORNIR_MAP_HASH]
    hud_rows = [r for r in new_rows if r["uid"] == NORNIR_HUD_HASH]
    check(len(map_rows) == 1 and map_rows[0]["index"] == 257 and map_rows[0]["capacity"] == 1,
          "failed candidate Nornir map GOPool row changed")
    check(len(hud_rows) == 1 and hud_rows[0]["index"] == 258 and hud_rows[0]["capacity"] == 2,
          "failed candidate Nornir HUD GOPool row changed")

    expected_relocs: list[int] = []
    pointer_rows = []
    for old_field in raven_relocs:
        old_delta, old_target = relative_pointer(raven_data, old_field)
        new_field = old_field + (EXPECTED_INSERT_BYTES if old_field >= insert_at else 0)
        new_target = old_target + (EXPECTED_INSERT_BYTES if old_target >= insert_at else 0)
        expected_delta = new_target - new_field
        expected_relocs.append(new_field)

        candidate_has_expected_reloc = new_field in set(candidate_relocs)
        actual_delta = None
        actual_target = None
        delta_matches = False
        if candidate_has_expected_reloc:
            actual_delta, actual_target = relative_pointer(candidate_data, new_field)
            delta_matches = actual_delta == expected_delta and actual_target == new_target

        if old_field < insert_at and old_target < insert_at:
            movement = "before_to_before"
        elif old_field < insert_at and old_target >= insert_at:
            movement = "before_to_after"
        elif old_field >= insert_at and old_target < insert_at:
            movement = "after_to_before"
        else:
            movement = "after_to_after"

        pointer_rows.append({
            "old_field": old_field,
            "old_delta": old_delta,
            "old_target": old_target,
            "expected_new_field": new_field,
            "expected_new_delta": expected_delta,
            "expected_new_target": new_target,
            "movement": movement,
            "candidate_has_expected_relocation": candidate_has_expected_reloc,
            "candidate_delta_at_expected_field": actual_delta,
            "candidate_target_at_expected_field": actual_target,
            "candidate_pointer_matches_expected": delta_matches,
        })

    expected_set = set(expected_relocs)
    candidate_set = set(candidate_relocs)
    raven_set = set(raven_relocs)
    shifted_field_rows = [r for r in pointer_rows if r["old_field"] >= insert_at]
    crossing_rows = [r for r in pointer_rows if r["movement"] in ("before_to_after", "after_to_before")]
    bad_rows = [r for r in pointer_rows if not r["candidate_pointer_matches_expected"]]
    missing_expected = sorted(expected_set - candidate_set)
    unexpected_actual = sorted(candidate_set - expected_set)

    report = {
        "schema": 1,
        "result": RESULT,
        "raven_sha256": sha(raven_raw),
        "candidate_sha256": sha(candidate_raw),
        "gopool": {
            "old_rows": old_count,
            "new_rows": new_count,
            "insert_at": insert_at,
            "insert_bytes": EXPECTED_INSERT_BYTES,
            "old_data_bytes": len(raven_data),
            "new_data_bytes": len(candidate_data),
        },
        "relocations": {
            "raven_count": len(raven_relocs),
            "candidate_count": len(candidate_relocs),
            "candidate_chunk15_byte_identical_to_raven": candidate_reloc_payload == raven_reloc_payload,
            "expected_relocation_set_equals_candidate": expected_set == candidate_set,
            "relocation_fields_at_or_after_insertion": len(shifted_field_rows),
            "cross_insertion_relative_pointers": len(crossing_rows),
            "bad_or_missing_pointer_relocations": len(bad_rows),
            "missing_expected_relocation_fields": missing_expected,
            "unexpected_candidate_relocation_fields": unexpected_actual,
            "pointer_rows": pointer_rows,
        },
        "diagnosis": {
            "chunk12_insertion_requires_relocation_transform": bool(shifted_field_rows or crossing_rows),
            "failed_candidate_left_chunk15_stale": candidate_reloc_payload == raven_reloc_payload and expected_set != candidate_set,
            "failed_candidate_has_runtime_unsafe_relocations": bool(bad_rows or missing_expected or unexpected_actual),
            "runtime_failure_consistent_with_relocation_corruption": bool(bad_rows or missing_expected or unexpected_actual),
            "wad_resource_aliasing_still_requires_separate_review": True,
            "root_cause_scope": "This proves or disproves DCB relocation corruption caused by GOPool growth; it does not by itself clear the WAD resource graph."
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  Raven DCB:     {report['raven_sha256']}")
    print(f"  candidate DCB: {report['candidate_sha256']}")
    print(f"  GOPool: {old_count} -> {new_count} rows; insertion=0x{insert_at:X} +{EXPECTED_INSERT_BYTES} bytes")
    print(f"  relocations: Raven={len(raven_relocs)} candidate={len(candidate_relocs)}")
    print(f"  candidate chunk15 byte-identical to Raven: {str(candidate_reloc_payload == raven_reloc_payload).lower()}")
    print(f"  relocation fields at/after insertion: {len(shifted_field_rows)}")
    print(f"  cross-insertion relative pointers: {len(crossing_rows)}")
    print(f"  missing expected relocation fields: {len(missing_expected)}")
    print(f"  unexpected/stale candidate relocation fields: {len(unexpected_actual)}")
    print(f"  bad or missing pointer relocations: {len(bad_rows)}")
    for row in bad_rows[:12]:
        print("    bad: oldField=0x{0:X} oldTarget=0x{1:X} expectedField=0x{2:X} expectedTarget=0x{3:X} movement={4}".format(
            row["old_field"], row["old_target"], row["expected_new_field"], row["expected_new_target"], row["movement"]))
    print(f"  relocation corruption proven: {str(report['diagnosis']['failed_candidate_has_runtime_unsafe_relocations']).lower()}")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
