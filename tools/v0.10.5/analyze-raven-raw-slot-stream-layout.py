"""Classify raw ALIVE/DEAD slot differences against validated zlib stream layout.

Offline/read-only. It compares frozen God of War save copies only and emits hashes,
offsets, lengths, and aggregate byte-difference counts. It never writes source saves
or exports arbitrary save payload bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slot_bytes(blob: bytes, lay: dict, index: int) -> bytes:
    start = lay["prefix"] + index * lay["stride"]
    return blob[start : start + lay["stride"]]


def stream_spans(slot: bytes, slot_index: int) -> tuple[list[dict], list[tuple[int, int]]]:
    streams = base.scan_slot(slot, slot_index)
    spans = []
    for stream in streams:
        start = int(stream["relative_offset"])
        end = start + int(stream["compressed_bytes"])
        spans.append((start, end))
    return streams, spans


def in_any(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alive", type=Path, required=True)
    ap.add_argument("--dead", type=Path, required=True)
    ap.add_argument("--alive-slot", type=int, required=True)
    ap.add_argument("--dead-slot", type=int, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    alive = args.alive.expanduser().resolve()
    dead = args.dead.expanduser().resolve()
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for path in (alive, dead):
        if not path.is_file():
            raise RuntimeError(f"Frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing active save tree: {path}")

    source_before = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    a_blob = alive.read_bytes()
    b_blob = dead.read_bytes()
    a_lay = base.layout(a_blob)
    b_lay = base.layout(b_blob)
    if a_lay != b_lay:
        raise RuntimeError(f"Layout mismatch: alive={a_lay} dead={b_lay}")
    lay = a_lay

    a_slot = slot_bytes(a_blob, lay, args.alive_slot)
    b_slot = slot_bytes(b_blob, lay, args.dead_slot)
    a_streams, a_spans = stream_spans(a_slot, args.alive_slot)
    b_streams, b_spans = stream_spans(b_slot, args.dead_slot)

    if len(a_streams) != len(b_streams):
        raise RuntimeError(f"Stream count mismatch: alive={len(a_streams)} dead={len(b_streams)}")

    pairs = []
    same_decompressed = 0
    same_compressed = 0
    same_offset = 0
    moved = 0
    recompressed = 0
    for idx, (aa, bb) in enumerate(zip(a_streams, b_streams)):
        a_start = int(aa["relative_offset"])
        b_start = int(bb["relative_offset"])
        a_len = int(aa["compressed_bytes"])
        b_len = int(bb["compressed_bytes"])
        a_comp = a_slot[a_start:a_start + a_len]
        b_comp = b_slot[b_start:b_start + b_len]
        decomp_same = aa["sha256"] == bb["sha256"]
        comp_same = a_comp == b_comp
        offset_same = a_start == b_start
        if decomp_same:
            same_decompressed += 1
        if comp_same:
            same_compressed += 1
        if offset_same:
            same_offset += 1
        else:
            moved += 1
        if decomp_same and not comp_same:
            recompressed += 1
        pairs.append({
            "index": idx,
            "decompressed_sha256": aa["sha256"],
            "decompressed_equal": decomp_same,
            "alive_offset": a_start,
            "dead_offset": b_start,
            "offset_delta": b_start - a_start,
            "alive_compressed_bytes": a_len,
            "dead_compressed_bytes": b_len,
            "alive_compressed_sha256": sha256(a_comp),
            "dead_compressed_sha256": sha256(b_comp),
            "compressed_equal": comp_same,
            "target_fields": sorted(set(aa.get("target_fields", [])) | set(bb.get("target_fields", []))),
        })

    changed_positions = [i for i, (x, y) in enumerate(zip(a_slot, b_slot)) if x != y]
    both_stream = 0
    either_stream = 0
    neither_stream = 0
    a_only_stream = 0
    b_only_stream = 0
    for pos in changed_positions:
        ina = in_any(pos, a_spans)
        inb = in_any(pos, b_spans)
        if ina and inb:
            both_stream += 1
        elif ina or inb:
            either_stream += 1
            if ina:
                a_only_stream += 1
            if inb:
                b_only_stream += 1
        else:
            neither_stream += 1

    raven_pairs = [p for p in pairs if "ravenKilled" in p["target_fields"]]
    source_after = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    if source_before != source_after:
        raise RuntimeError("Frozen save changed during read-only analysis")

    report = {
        "schema": 1,
        "analysis": "raven_raw_slot_stream_layout",
        "layout": lay,
        "alive_slot": args.alive_slot,
        "dead_slot": args.dead_slot,
        "alive_slot_sha256": sha256(a_slot),
        "dead_slot_sha256": sha256(b_slot),
        "stream_count": len(pairs),
        "same_decompressed_streams": same_decompressed,
        "same_compressed_streams": same_compressed,
        "same_offset_streams": same_offset,
        "moved_streams": moved,
        "recompressed_streams": recompressed,
        "changed_byte_count": len(changed_positions),
        "changed_bytes_in_both_stream_spans": both_stream,
        "changed_bytes_in_one_stream_span_only": either_stream,
        "changed_bytes_in_alive_stream_span_only": a_only_stream,
        "changed_bytes_in_dead_stream_span_only": b_only_stream,
        "changed_bytes_outside_all_stream_spans": neither_stream,
        "raven_field_stream_pairs": raven_pairs,
        "stream_pairs": pairs,
        "source_hashes": source_before,
        "source_hashes_unchanged": True,
        "safety": {
            "active_save_opened": False,
            "source_files_written": False,
            "arbitrary_save_bytes_emitted": False,
            "process_memory_read": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "RAVEN_RAW_SLOT_STREAM_LAYOUT_COMPLETED",
        f"stream_count={len(pairs)}",
        f"same_decompressed_streams={same_decompressed}",
        f"same_compressed_streams={same_compressed}",
        f"same_offset_streams={same_offset}",
        f"moved_streams={moved}",
        f"recompressed_streams={recompressed}",
        f"changed_byte_count={len(changed_positions)}",
        f"changed_bytes_in_both_stream_spans={both_stream}",
        f"changed_bytes_in_one_stream_span_only={either_stream}",
        f"changed_bytes_outside_all_stream_spans={neither_stream}",
        f"raven_field_stream_pairs={len(raven_pairs)}",
        "active_save_opened=false",
        "source_files_written=false",
        "process_memory_read=false",
    ]
    args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
