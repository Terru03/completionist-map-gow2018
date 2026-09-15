"""Offline/read-only chronological diff for the forced Raven manual-save pair.

The in-game manual-save timestamps establish the ordering:
  pre-kill  manual save: 2026-09-15 22:54:41
  post-kill manual save: 2026-09-15 22:55:12

The frozen ring capture shows the newly-written post-kill physical slot is 18,
and the immediately preceding physical slot is 17. This analyzer therefore
compares ALIVE slot 17 directly to DEAD slot 18 instead of choosing a predecessor
by content similarity. It emits semantic stream metadata/hashes only; no raw save
payload bytes are archived.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")
PREFIX = 4160
STRIDE = 1677512
PRE_SLOT = 17
POST_SLOT = 18


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def get_slot(blob: bytes, idx: int) -> bytes:
    start = PREFIX + idx * STRIDE
    out = blob[start:start + STRIDE]
    if len(out) != STRIDE:
        raise RuntimeError(f"slot {idx} extraction size mismatch: {len(out)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alive", type=Path, required=True)
    ap.add_argument("--dead", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    alive = args.alive.expanduser().resolve()
    dead = args.dead.expanduser().resolve()
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for p in (alive, dead):
        if not p.is_file():
            raise RuntimeError(f"frozen save missing: {p}")
        try:
            p.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing active save tree: {p}")

    before = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    alive_blob = alive.read_bytes()
    dead_blob = dead.read_bytes()

    pre_raw = get_slot(alive_blob, PRE_SLOT)
    post_raw = get_slot(dead_blob, POST_SLOT)
    pre_streams = base.scan_slot(pre_raw, PRE_SLOT)
    post_streams = base.scan_slot(post_raw, POST_SLOT)
    runs = base.changed_runs(pre_streams, post_streams, POST_SLOT)

    raven_runs = []
    for run in runs:
        a_raven = [s for s in run["a_streams"] if "ravenKilled" in s["target_fields"]]
        b_raven = [s for s in run["b_streams"] if "ravenKilled" in s["target_fields"]]
        if a_raven or b_raven:
            raven_runs.append({
                "run": run["run"],
                "opcode": run["opcode"],
                "a_index_range": run["a_index_range"],
                "b_index_range": run["b_index_range"],
                "pre_raven_streams": a_raven,
                "post_raven_streams": b_raven,
                "tokens_only_pre": run["tokens_only_a"],
                "tokens_only_post": run["tokens_only_b"],
                "tokens_shared": run["tokens_shared"],
            })

    changed_pre = sum(len(r["a_streams"]) for r in runs)
    changed_post = sum(len(r["b_streams"]) for r in runs)

    after = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    if before != after:
        raise RuntimeError("frozen source save changed during read-only analysis")

    report = {
        "schema": 1,
        "analysis": "raven_forced_manual_chronological",
        "status": "CHRONOLOGICAL_PAIR_DIFFED",
        "manual_save_order": {
            "pre_kill_timestamp": "2026-09-15T22:54:41+03:00",
            "post_kill_timestamp": "2026-09-15T22:55:12+03:00",
            "pre_slot": PRE_SLOT,
            "post_slot": POST_SLOT,
        },
        "source_hashes": before,
        "source_hashes_unchanged": True,
        "pre_stream_count": len(pre_streams),
        "post_stream_count": len(post_streams),
        "changed_run_count": len(runs),
        "changed_pre_stream_count": changed_pre,
        "changed_post_stream_count": changed_post,
        "changed_runs": runs,
        "raven_field_run_count": len(raven_runs),
        "raven_field_runs": raven_runs,
        "runtime_generation_allowed": False,
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
        "# Raven forced-manual chronological diff",
        "",
        "Pre-kill manual save: **22:54:41**, ALIVE slot **17**",
        "Post-kill manual save: **22:55:12**, DEAD slot **18**",
        "",
        f"- pre streams: {len(pre_streams)}",
        f"- post streams: {len(post_streams)}",
        f"- changed runs: {len(runs)}",
        f"- changed pre streams: {changed_pre}",
        f"- changed post streams: {changed_post}",
        f"- runs containing ravenKilled: {len(raven_runs)}",
        "",
    ]
    for run in runs:
        lines.append(
            f"- run {run['run']} {run['opcode']} A{run['a_index_range']} B{run['b_index_range']} "
            f"pre={len(run['a_streams'])} post={len(run['b_streams'])} "
            f"tokens_pre={run['tokens_only_a']} tokens_post={run['tokens_only_b']}"
        )
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = [
        "RAVEN_FORCED_MANUAL_CHRONOLOGICAL_COMPLETED",
        f"pre_slot={PRE_SLOT}",
        f"post_slot={POST_SLOT}",
        "pre_timestamp=2026-09-15T22:54:41+03:00",
        "post_timestamp=2026-09-15T22:55:12+03:00",
        f"pre_stream_count={len(pre_streams)}",
        f"post_stream_count={len(post_streams)}",
        f"changed_run_count={len(runs)}",
        f"changed_pre_stream_count={changed_pre}",
        f"changed_post_stream_count={changed_post}",
        f"raven_field_run_count={len(raven_runs)}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "raw_save_bytes_emitted=false",
    ]
    args.summary.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
