"""Offline structural-shift analysis for the frozen Raven alive/dead save pair.

The prior cross-slot and stream-layout analyses proved that DEAD slot 17 and
ALIVE slot 5 contain the same 81 zlib streams, with identical compressed and
decompressed bytes. 49 streams move while 32 remain at their original offsets.
This tool characterizes that movement and tests whether the raw-slot delta is
consistent with fixed-size structural record movement rather than changed zlib
payloads.

It is read-only and emits only hashes, offsets, sizes, counts, and structural
classification statistics. No raw save payload is written to the repository.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def slot_bytes(blob: bytes, lay: dict, slot: int) -> bytes:
    start = lay["prefix"] + slot * lay["stride"]
    return blob[start:start + lay["stride"]]


def stream_pairs(alive_slot: bytes, dead_slot: bytes) -> list[dict]:
    aa = base.scan_slot(alive_slot, 5)
    bb = base.scan_slot(dead_slot, 17)
    if len(aa) != len(bb):
        raise RuntimeError(f"stream count mismatch alive={len(aa)} dead={len(bb)}")
    out = []
    for i, (a, b) in enumerate(zip(aa, bb)):
        if a["sha256"] != b["sha256"]:
            raise RuntimeError(f"decompressed stream {i} differs")
        ar = alive_slot[a["relative_offset"]:a["relative_offset"] + a["compressed_bytes"]]
        br = dead_slot[b["relative_offset"]:b["relative_offset"] + b["compressed_bytes"]]
        if hashlib.sha256(ar).digest() != hashlib.sha256(br).digest():
            raise RuntimeError(f"compressed stream {i} differs")
        out.append({
            "index": i,
            "alive_offset": a["relative_offset"],
            "dead_offset": b["relative_offset"],
            "offset_delta": b["relative_offset"] - a["relative_offset"],
            "compressed_bytes": a["compressed_bytes"],
            "target_fields": a["target_fields"],
        })
    return out


def delta_runs(pairs: list[dict]) -> list[dict]:
    if not pairs:
        return []
    runs = []
    start = 0
    delta = pairs[0]["offset_delta"]
    for i in range(1, len(pairs)):
        if pairs[i]["offset_delta"] != delta:
            runs.append({
                "start_index": start,
                "end_index": i - 1,
                "count": i - start,
                "delta": delta,
                "alive_first_offset": pairs[start]["alive_offset"],
                "alive_last_offset": pairs[i - 1]["alive_offset"],
                "dead_first_offset": pairs[start]["dead_offset"],
                "dead_last_offset": pairs[i - 1]["dead_offset"],
            })
            start = i
            delta = pairs[i]["offset_delta"]
    runs.append({
        "start_index": start,
        "end_index": len(pairs) - 1,
        "count": len(pairs) - start,
        "delta": delta,
        "alive_first_offset": pairs[start]["alive_offset"],
        "alive_last_offset": pairs[-1]["alive_offset"],
        "dead_first_offset": pairs[start]["dead_offset"],
        "dead_last_offset": pairs[-1]["dead_offset"],
    })
    return runs


def span_mask(size: int, pairs: list[dict], side: str) -> bytearray:
    mask = bytearray(size)
    for p in pairs:
        start = p[f"{side}_offset"]
        end = min(size, start + p["compressed_bytes"])
        if start < 0 or start >= size:
            continue
        mask[start:end] = b"\x01" * (end - start)
    return mask


def changed_offsets(a: bytes, b: bytes) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def changed_runs(offsets: list[int]) -> list[tuple[int, int]]:
    if not offsets:
        return []
    runs = []
    s = p = offsets[0]
    for x in offsets[1:]:
        if x != p + 1:
            runs.append((s, p))
            s = x
        p = x
    runs.append((s, p))
    return runs


def u32(buf: bytes, off: int) -> int | None:
    if off < 0 or off + 4 > len(buf):
        return None
    return struct.unpack_from("<I", buf, off)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alive", type=Path, required=True)
    ap.add_argument("--dead", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    alive = args.alive.expanduser().resolve()
    dead = args.dead.expanduser().resolve()
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for path in (alive, dead):
        if not path.is_file():
            raise RuntimeError(f"frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing active save tree: {path}")

    before = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    ab = alive.read_bytes()
    db = dead.read_bytes()
    la = base.layout(ab)
    ld = base.layout(db)
    if la != ld:
        raise RuntimeError(f"layout mismatch: {la} vs {ld}")

    a = slot_bytes(ab, la, 5)
    b = slot_bytes(db, la, 17)
    pairs = stream_pairs(a, b)
    runs = delta_runs(pairs)
    delta_counts = Counter(p["offset_delta"] for p in pairs)

    am = span_mask(len(a), pairs, "alive")
    dm = span_mask(len(b), pairs, "dead")
    changed = changed_offsets(a, b)
    outside = [i for i in changed if not am[i] and not dm[i]]
    outside_runs = changed_runs(outside)

    # Classify aligned 32-bit changes outside stream payloads. A very common
    # relocation-table pattern is an offset value changing by exactly one of
    # the observed stream deltas (notably -48 here).
    observed_deltas = set(delta_counts)
    offset_like_words = 0
    exact_stream_offset_pairs = 0
    small_delta_words = 0
    changed_aligned_words = 0
    alive_to_dead_offsets = {p["alive_offset"]: p["dead_offset"] for p in pairs}
    for off in range(0, len(a) - 3, 4):
        if any(am[off:off+4]) or any(dm[off:off+4]):
            continue
        av = u32(a, off)
        bv = u32(b, off)
        if av == bv:
            continue
        changed_aligned_words += 1
        if av in alive_to_dead_offsets and alive_to_dead_offsets[av] == bv:
            exact_stream_offset_pairs += 1
            offset_like_words += 1
            continue
        diff = (bv - av) if av is not None and bv is not None else None
        if diff in observed_deltas and 0 <= av < len(a) and 0 <= bv < len(b):
            offset_like_words += 1
        if diff is not None and abs(diff) <= 0x100 and 0 <= av < len(a) and 0 <= bv < len(b):
            small_delta_words += 1

    # Quantify the conspicuous 48-byte cadence seen in the raw-diff archive.
    run_starts = [s for s, _ in outside_runs]
    mod48 = Counter(x % 48 for x in run_starts)
    top_mod48 = [{"mod": m, "count": c} for m, c in mod48.most_common(8)]
    len_counts = Counter((e - s + 1) for s, e in outside_runs)
    top_lengths = [{"length": n, "count": c} for n, c in len_counts.most_common(12)]

    transition = []
    for left, right in zip(runs, runs[1:]):
        transition.append({
            "after_stream_index": left["end_index"],
            "before_stream_index": right["start_index"],
            "delta_before": left["delta"],
            "delta_after": right["delta"],
            "alive_gap_start": pairs[left["end_index"]]["alive_offset"] + pairs[left["end_index"]]["compressed_bytes"],
            "alive_gap_end": pairs[right["start_index"]]["alive_offset"],
            "dead_gap_start": pairs[left["end_index"]]["dead_offset"] + pairs[left["end_index"]]["compressed_bytes"],
            "dead_gap_end": pairs[right["start_index"]]["dead_offset"],
        })

    after = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    if before != after:
        raise RuntimeError("frozen save hashes changed during analysis")

    report = {
        "schema": 1,
        "analysis": "raven_raw_slot_structural_shift",
        "source_hashes": before,
        "source_hashes_unchanged": True,
        "layout": la,
        "alive_slot": 5,
        "dead_slot": 17,
        "stream_count": len(pairs),
        "stream_offset_delta_counts": {str(k): v for k, v in sorted(delta_counts.items())},
        "stream_delta_runs": runs,
        "delta_transitions": transition,
        "raw_changed_byte_count": len(changed),
        "outside_all_streams_changed_byte_count": len(outside),
        "outside_all_streams_changed_run_count": len(outside_runs),
        "changed_aligned_u32_words_outside_streams": changed_aligned_words,
        "exact_stream_offset_pair_words": exact_stream_offset_pairs,
        "offset_like_u32_words": offset_like_words,
        "small_delta_u32_words": small_delta_words,
        "outside_run_start_mod48_top": top_mod48,
        "outside_run_length_top": top_lengths,
        "raven_field_streams": [
            p for p in pairs if "ravenKilled" in p["target_fields"]
        ],
        "interpretation": {
            "all_stream_payloads_identical": True,
            "observed_fixed_shift": (-48 in delta_counts),
            "fixed_shift_stream_count": delta_counts.get(-48, 0),
            "unchanged_offset_stream_count": delta_counts.get(0, 0),
            "raw_residual_requires_semantic_binding": True,
            "runtime_generation_allowed": False,
        },
        "safety": {
            "active_save_opened": False,
            "source_files_written": False,
            "raw_save_bytes_emitted": False,
            "process_memory_read": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = [
        "RAVEN_RAW_SLOT_STRUCTURAL_SHIFT_COMPLETED",
        f"stream_count={len(pairs)}",
        "stream_offset_delta_counts=" + ",".join(f"{k}:{v}" for k, v in sorted(delta_counts.items())),
        f"stream_delta_runs={len(runs)}",
        f"delta_transitions={len(transition)}",
        f"raw_changed_bytes={len(changed)}",
        f"outside_stream_changed_bytes={len(outside)}",
        f"outside_stream_changed_runs={len(outside_runs)}",
        f"changed_aligned_u32_words={changed_aligned_words}",
        f"exact_stream_offset_pair_words={exact_stream_offset_pairs}",
        f"offset_like_u32_words={offset_like_words}",
        f"small_delta_u32_words={small_delta_words}",
        f"raven_field_streams={sum(1 for p in pairs if 'ravenKilled' in p['target_fields'])}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "raw_save_bytes_emitted=false",
    ]
    for i, r in enumerate(runs, 1):
        summary.append(
            f"delta_run_{i}=streams_{r['start_index']}-{r['end_index']} count={r['count']} delta={r['delta']}"
        )
    for i, t in enumerate(transition, 1):
        summary.append(
            f"transition_{i}=after_stream_{t['after_stream_index']} delta_{t['delta_before']}_to_{t['delta_after']} "
            f"alive_gap={t['alive_gap_start']}-{t['alive_gap_end']} dead_gap={t['dead_gap_start']}-{t['dead_gap_end']}"
        )
    args.summary.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
