#!/usr/bin/env python3
"""Read-only GoW save-ring prefix/directory lineage probe.

The active game.sav layout is 4,160-byte prefix + 20 * 1,677,512-byte slots.
4,160 == 20 * 208, exactly the per-slot header size. This probe tests whether
that prefix is a 20-entry directory/index by comparing each 208-byte prefix
record to every 208-byte slot header and by tracing slot timestamps/indices.

No save or game files are written.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

PREFIX = 4160
SLOTS = 20
HEADER = 208
STRIDE = 1677512


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_save(root: Path) -> Path:
    saves = sorted(p.resolve() for p in root.expanduser().resolve().rglob("game.sav") if p.is_file())
    if len(saves) != 1:
        raise RuntimeError(f"expected exactly one active game.sav, found {len(saves)}")
    return saves[0]


def eq_stats(a: bytes, b: bytes) -> dict:
    if len(a) != len(b):
        raise RuntimeError("comparison size mismatch")
    same = sum(x == y for x, y in zip(a, b))
    runs = []
    start = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i - start))
            start = None
    if start is not None:
        runs.append((start, len(a) - start))
    best = max(runs, key=lambda x: x[1]) if runs else (None, 0)
    return {
        "equal_bytes": same,
        "equal_ratio": same / len(a),
        "longest_equal_run_start": best[0],
        "longest_equal_run_length": best[1],
    }


def all_hits(haystack: bytes, needle: bytes) -> list[int]:
    out = []
    pos = 0
    while True:
        at = haystack.find(needle, pos)
        if at < 0:
            return out
        out.append(at)
        pos = at + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    save = resolve_save(args.save_root)
    before = sha256_file(save)
    blob = save.read_bytes()
    if len(blob) != 33554400:
        raise RuntimeError(f"unexpected save length {len(blob)}")
    if PREFIX != SLOTS * HEADER:
        raise RuntimeError("prefix/header arithmetic contract broken")

    prefix = blob[:PREFIX]
    prefix_records = [prefix[i*HEADER:(i+1)*HEADER] for i in range(SLOTS)]
    slot_headers = [
        blob[PREFIX + i*STRIDE:PREFIX + i*STRIDE + HEADER]
        for i in range(SLOTS)
    ]

    # Physical slot timestamps are proven at header offset +0x00 (Unix seconds).
    slot_times = [struct.unpack_from("<I", h, 0)[0] for h in slot_headers]

    matrix = []
    best_by_prefix = []
    best_by_slot = []
    for pi, prec in enumerate(prefix_records):
        rows = []
        for si, sh in enumerate(slot_headers):
            stats = eq_stats(prec, sh)
            rows.append({"slot": si, **stats})
            matrix.append({"prefix_record": pi, "slot": si, **stats})
        rows.sort(key=lambda x: (-x["equal_bytes"], x["slot"]))
        best_by_prefix.append({"prefix_record": pi, "matches": rows[:5]})

    for si, sh in enumerate(slot_headers):
        rows = []
        for pi, prec in enumerate(prefix_records):
            stats = eq_stats(prec, sh)
            rows.append({"prefix_record": pi, **stats})
        rows.sort(key=lambda x: (-x["equal_bytes"], x["prefix_record"]))
        best_by_slot.append({"slot": si, "matches": rows[:5]})

    # Search the entire 4,160-byte prefix for every exact slot timestamp.
    timestamp_hits = {}
    for si, value in enumerate(slot_times):
        needle = struct.pack("<I", value)
        timestamp_hits[str(si)] = {
            "timestamp_u32": value,
            "hits": all_hits(prefix, needle),
        }

    # Search for raw slot numbers 0..19 as u16/u32 at aligned offsets in each
    # 208-byte prefix record. Rank fields whose 20-record vector resembles a
    # permutation or repeated mapping into the physical slot range.
    field_candidates = []
    for width, fmt in ((2, "<H"), (4, "<I")):
        for off in range(0, HEADER - width + 1, width):
            vals = [struct.unpack_from(fmt, rec, off)[0] for rec in prefix_records]
            in_range = [v for v in vals if 0 <= v < SLOTS]
            unique = len(set(in_range))
            if len(in_range) >= 8:
                field_candidates.append({
                    "width": width,
                    "offset": off,
                    "offset_hex": f"0x{off:X}",
                    "values": vals,
                    "in_slot_range_count": len(in_range),
                    "unique_in_slot_range": unique,
                    "is_permutation_0_19": sorted(vals) == list(range(SLOTS)),
                })
    field_candidates.sort(key=lambda r: (
        -int(r["is_permutation_0_19"]),
        -r["in_slot_range_count"],
        -r["unique_in_slot_range"],
        r["width"],
        r["offset"],
    ))

    # Find fields whose 20 values exactly match the physical slot timestamp
    # vector, possibly under a permutation. This is strong directory evidence.
    timestamp_field_candidates = []
    target_multiset = Counter(slot_times)
    for width, fmt in ((4, "<I"), (8, "<Q")):
        for off in range(0, HEADER - width + 1, width):
            vals = [struct.unpack_from(fmt, rec, off)[0] for rec in prefix_records]
            if width == 4:
                exact_order = vals == slot_times
                same_multiset = Counter(vals) == target_multiset
                if exact_order or same_multiset:
                    timestamp_field_candidates.append({
                        "width": width,
                        "offset": off,
                        "offset_hex": f"0x{off:X}",
                        "exact_physical_order": exact_order,
                        "same_timestamp_multiset": same_multiset,
                        "values": vals,
                    })

    # Compare prefix records against each other for obvious repeated structure.
    prefix_pair_similarity = []
    for a in range(SLOTS):
        for b in range(a + 1, SLOTS):
            stats = eq_stats(prefix_records[a], prefix_records[b])
            if stats["equal_ratio"] >= 0.75:
                prefix_pair_similarity.append({"a": a, "b": b, **stats})
    prefix_pair_similarity.sort(key=lambda r: (-r["equal_bytes"], r["a"], r["b"]))

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav changed during read-only prefix probe")

    report = {
        "schema": 1,
        "analysis": "gow_save_ring_prefix_directory_lineage",
        "save_path": str(save),
        "save_sha256": before,
        "layout": {
            "prefix": PREFIX,
            "slots": SLOTS,
            "header_bytes": HEADER,
            "slot_stride": STRIDE,
            "prefix_equals_slots_times_header": PREFIX == SLOTS * HEADER,
        },
        "slot_timestamps_u32": slot_times,
        "timestamp_hits_in_prefix": timestamp_hits,
        "best_prefix_record_to_slot_header_matches": best_by_prefix,
        "best_slot_header_to_prefix_record_matches": best_by_slot,
        "full_similarity_matrix": matrix,
        "slot_index_field_candidates": field_candidates[:80],
        "timestamp_field_candidates": timestamp_field_candidates,
        "high_prefix_record_similarity_pairs": prefix_pair_similarity[:100],
        "safety": {
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - GoW save-ring prefix directory/lineage probe",
        f"save_sha256={before}",
        f"layout=prefix:{PREFIX} slots:{SLOTS} header:{HEADER} stride:{STRIDE}",
        f"prefix_equals_20x208={str(PREFIX == SLOTS * HEADER).lower()}",
        "",
        "SLOT TIMESTAMP HITS IN PREFIX",
    ]
    for si in range(SLOTS):
        row = timestamp_hits[str(si)]
        lines.append(
            f"slot={si} timestamp={row['timestamp_u32']} hits="
            + (",".join(f"0x{x:X}" for x in row["hits"]) if row["hits"] else "none")
        )

    lines.extend(["", "BEST PREFIX-RECORD -> SLOT-HEADER MATCHES"])
    for row in best_by_prefix:
        m = row["matches"][0]
        lines.append(
            f"prefixRecord={row['prefix_record']} bestSlot={m['slot']} "
            f"equal={m['equal_bytes']}/{HEADER} ratio={m['equal_ratio']:.3f} "
            f"bestRun={m['longest_equal_run_length']}"
        )

    lines.extend(["", "SLOT-INDEX FIELD CANDIDATES"])
    for row in field_candidates[:30]:
        lines.append(
            f"offset={row['offset_hex']} width={row['width']} "
            f"inRange={row['in_slot_range_count']} unique={row['unique_in_slot_range']} "
            f"permutation={str(row['is_permutation_0_19']).lower()} values={row['values']}"
        )

    lines.extend(["", "TIMESTAMP FIELD CANDIDATES"])
    if not timestamp_field_candidates:
        lines.append("none")
    else:
        for row in timestamp_field_candidates:
            lines.append(
                f"offset={row['offset_hex']} width={row['width']} "
                f"exactOrder={str(row['exact_physical_order']).lower()} "
                f"sameMultiset={str(row['same_timestamp_multiset']).lower()}"
            )

    lines.extend([
        "",
        "SAFETY active_save_opened_read_only=true source_hash_unchanged=true "
        "save_written=false progression_written=false game_process_opened=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_ts_hits = sum(len(x["hits"]) for x in timestamp_hits.values())
    print(
        "GOW_SAVE_RING_PREFIX_DIRECTORY_PROBE_COMPLETE "
        f"timestampHits={total_ts_hits} slotFields={len(field_candidates)} "
        f"timestampFields={len(timestamp_field_candidates)}"
    )
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
