"""Offline/read-only control analysis for duplicate God of War save-ring snapshots.

This probe scans frozen save copies outside the active save tree, extracts the
20 aligned ring slots used by the supported game.sav layout, fingerprints each
slot by its ordered sequence of validated zlib payload SHA-256 hashes, and finds
logical snapshots that occur more than once in different physical slots/files.

For duplicate logical snapshots it reports only hashes, slot/file labels, stream
counts, raw mismatch counts, and simple fixed-shift alignment scores. No raw save
payload bytes are emitted and source files are never modified.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")
PREFIX = 4160
STRIDE = 1677512
SLOTS = 20
TARGET_ALIVE_SLOT = 5
TARGET_DEAD_SLOT = 17
TARGET_SHIFT = 48


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slot_bytes(blob: bytes, index: int) -> bytes:
    start = PREFIX + index * STRIDE
    out = blob[start:start + STRIDE]
    if len(out) != STRIDE:
        raise RuntimeError(f"slot {index} extraction size mismatch")
    return out


def stream_signature(raw: bytes, slot_index: int) -> tuple[str, list[dict]]:
    streams = base.scan_slot(raw, slot_index)
    joined = "\n".join(x["sha256"] for x in streams).encode("ascii")
    return hashlib.sha256(joined).hexdigest(), streams


def mismatch_count(a: bytes, b: bytes, shift_start: int | None = None,
                   shift_end: int | None = None, shift: int = 0) -> int:
    bad = 0
    for bi in range(STRIDE):
        ai = bi
        if shift_start is not None and shift_end is not None and shift_start <= bi < shift_end:
            ai = bi + shift
        if ai < 0 or ai >= STRIDE or a[ai] != b[bi]:
            bad += 1
    return bad


def best_single_shift_window(a: bytes, b: bytes, shift: int = TARGET_SHIFT) -> dict:
    """Find a coarse contiguous region where +shift alignment beats same offset.

    This is a control metric only; it does not infer semantics.
    """
    window = 256
    winners: list[int] = []
    limit = STRIDE - max(0, shift)
    for s in range(0, limit, window):
        e = min(s + window, limit)
        same = 0
        shifted = 0
        total = e - s
        for bi in range(s, e):
            if a[bi] == b[bi]:
                same += 1
            if a[bi + shift] == b[bi]:
                shifted += 1
        if total and (shifted - same) >= max(8, int(total * 0.20)):
            winners.append(s)
    groups: list[tuple[int, int]] = []
    if winners:
        gs = gp = winners[0]
        for cur in winners[1:]:
            if cur == gp + window:
                gp = cur
            else:
                groups.append((gs, min(gp + window, limit)))
                gs = gp = cur
            gp = cur
        groups.append((gs, min(gp + window, limit)))
    if not groups:
        return {
            "found": False,
            "start": None,
            "end": None,
            "residual_changed_bytes": mismatch_count(a, b),
            "match_ratio": 1.0 - (mismatch_count(a, b) / STRIDE),
        }
    start, end = max(groups, key=lambda g: g[1] - g[0])
    residual = mismatch_count(a, b, start, end, shift)
    return {
        "found": True,
        "start": start,
        "end": end,
        "residual_changed_bytes": residual,
        "match_ratio": 1.0 - (residual / STRIDE),
    }


def safe_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True,
                    help="Folder containing frozen GodOfWar-* backup directories")
    ap.add_argument("--target-alive", type=Path, required=True)
    ap.add_argument("--target-dead", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    root = args.root.expanduser().resolve()
    target_alive = args.target_alive.expanduser().resolve()
    target_dead = args.target_dead.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()

    if not root.is_dir():
        raise RuntimeError(f"root missing: {root}")
    for p in (target_alive, target_dead):
        if not p.is_file():
            raise RuntimeError(f"target frozen save missing: {p}")
        try:
            p.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing active save tree: {p}")

    candidates: list[Path] = []
    for pattern in ("GodOfWar-SaveBackup-*", "GodOfWar-RavenAliveDead-*"):
        for directory in root.glob(pattern):
            if not directory.is_dir():
                continue
            for p in directory.rglob("game.sav"):
                try:
                    p.resolve().relative_to(active)
                except ValueError:
                    candidates.append(p.resolve())
                else:
                    continue
    for p in (target_alive, target_dead):
        if p not in candidates:
            candidates.append(p)
    candidates = sorted(set(candidates), key=lambda p: str(p).lower())

    before = {str(p): sha256_file(p) for p in candidates}
    records = []
    groups: dict[str, list[dict]] = defaultdict(list)
    cache: dict[tuple[str, int], bytes] = {}

    for path in candidates:
        blob = path.read_bytes()
        # Only accept the supported aligned layout.
        lay = base.layout(blob)
        if lay["prefix"] != PREFIX or lay["stride"] != STRIDE or lay["slot_count"] != SLOTS:
            continue
        file_label = safe_label(path, root)
        for slot in range(SLOTS):
            raw = slot_bytes(blob, slot)
            sig, streams = stream_signature(raw, slot)
            if not streams:
                continue
            row = {
                "file": file_label,
                "path": str(path),
                "slot": slot,
                "stream_count": len(streams),
                "stream_signature": sig,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }
            records.append(row)
            groups[sig].append(row)
            cache[(str(path), slot)] = raw

    duplicate_groups = []
    control_pairs = []
    for sig, rows in groups.items():
        if len(rows) < 2:
            continue
        # Ignore duplicate references to the exact same file/slot.
        uniq = {(r["path"], r["slot"]): r for r in rows}
        rows = list(uniq.values())
        if len(rows) < 2:
            continue
        duplicate_groups.append({
            "stream_signature": sig,
            "stream_count": rows[0]["stream_count"],
            "occurrence_count": len(rows),
            "occurrences": [
                {"file": r["file"], "slot": r["slot"], "raw_sha256": r["raw_sha256"]}
                for r in rows
            ],
        })
        # Compare up to the first 12 unique pairs per signature to keep output bounded.
        emitted = 0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                arow, brow = rows[i], rows[j]
                a = cache[(arow["path"], arow["slot"])]
                b = cache[(brow["path"], brow["slot"])]
                raw_bad = mismatch_count(a, b)
                shift_model = best_single_shift_window(a, b, TARGET_SHIFT)
                control_pairs.append({
                    "stream_signature": sig,
                    "stream_count": arow["stream_count"],
                    "a_file": arow["file"],
                    "a_slot": arow["slot"],
                    "b_file": brow["file"],
                    "b_slot": brow["slot"],
                    "raw_identical": raw_bad == 0,
                    "raw_changed_bytes": raw_bad,
                    "raw_match_ratio": 1.0 - (raw_bad / STRIDE),
                    "plus48_control": shift_model,
                })
                emitted += 1
                if emitted >= 12:
                    break
            if emitted >= 12:
                break

    # Target pair metrics, included explicitly for comparison with controls.
    ta_blob = target_alive.read_bytes()
    td_blob = target_dead.read_bytes()
    ta = slot_bytes(ta_blob, TARGET_ALIVE_SLOT)
    td = slot_bytes(td_blob, TARGET_DEAD_SLOT)
    ta_sig, ta_streams = stream_signature(ta, TARGET_ALIVE_SLOT)
    td_sig, td_streams = stream_signature(td, TARGET_DEAD_SLOT)
    target_raw_bad = mismatch_count(ta, td)
    target_shift = best_single_shift_window(ta, td, TARGET_SHIFT)

    after = {str(p): sha256_file(p) for p in candidates}
    if before != after:
        raise RuntimeError("source frozen save hash changed during read-only analysis")

    nonidentical_controls = [p for p in control_pairs if not p["raw_identical"]]
    same_stream_count_controls = [p for p in nonidentical_controls if p["stream_count"] == len(ta_streams)]
    report = {
        "schema": 1,
        "analysis": "save_ring_duplicate_controls",
        "frozen_file_count": len(candidates),
        "scanned_slot_count": len(records),
        "duplicate_signature_group_count": len(duplicate_groups),
        "control_pair_count": len(control_pairs),
        "nonidentical_control_pair_count": len(nonidentical_controls),
        "same_stream_count_nonidentical_control_count": len(same_stream_count_controls),
        "target": {
            "alive_slot": TARGET_ALIVE_SLOT,
            "dead_slot": TARGET_DEAD_SLOT,
            "alive_stream_count": len(ta_streams),
            "dead_stream_count": len(td_streams),
            "stream_signatures_equal": ta_sig == td_sig,
            "stream_signature": ta_sig,
            "raw_changed_bytes": target_raw_bad,
            "raw_match_ratio": 1.0 - (target_raw_bad / STRIDE),
            "plus48_control": target_shift,
        },
        "duplicate_groups": duplicate_groups,
        "control_pairs": sorted(
            control_pairs,
            key=lambda x: (x["raw_changed_bytes"], x["a_file"], x["a_slot"], x["b_file"], x["b_slot"]),
        ),
        "interpretation": {
            "duplicate_stream_signature_means_all_ordered_validated_zlib_payloads_equal": True,
            "raw_difference_is_completion_truth": False,
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

    lines = [
        "SAVE_RING_DUPLICATE_CONTROLS_COMPLETED",
        f"frozen_file_count={report['frozen_file_count']}",
        f"scanned_slot_count={report['scanned_slot_count']}",
        f"duplicate_signature_group_count={report['duplicate_signature_group_count']}",
        f"control_pair_count={report['control_pair_count']}",
        f"nonidentical_control_pair_count={report['nonidentical_control_pair_count']}",
        f"same_stream_count_nonidentical_control_count={report['same_stream_count_nonidentical_control_count']}",
        f"target_stream_signatures_equal={str(ta_sig == td_sig).lower()}",
        f"target_raw_changed_bytes={target_raw_bad}",
        f"target_plus48_found={str(target_shift['found']).lower()}",
        f"target_plus48_residual={target_shift['residual_changed_bytes']}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "raw_save_bytes_emitted=false",
    ]
    if nonidentical_controls:
        vals = sorted(p["raw_changed_bytes"] for p in nonidentical_controls)
        lines.append(f"control_raw_changed_min={vals[0]}")
        lines.append(f"control_raw_changed_median={vals[len(vals)//2]}")
        lines.append(f"control_raw_changed_max={vals[-1]}")
    if same_stream_count_controls:
        vals = sorted(p["raw_changed_bytes"] for p in same_stream_count_controls)
        lines.append(f"same81_raw_changed_min={vals[0]}")
        lines.append(f"same81_raw_changed_median={vals[len(vals)//2]}")
        lines.append(f"same81_raw_changed_max={vals[-1]}")
    args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
