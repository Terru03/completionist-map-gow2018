"""Match newly-written DEAD save slots to their nearest ALIVE predecessor.

This is an offline/read-only follow-up to the Raven alive/dead frozen-save
capture. God of War stores multiple logical save snapshots in aligned ring
slots, so a normal save can populate a previously empty physical slot. A
same-index diff then looks like an 0->N stream insertion even when the logical
change is small.

For each physically changed DEAD slot, this tool compares its validated zlib
stream-hash sequence against every ALIVE slot, selects the nearest predecessor,
and runs the existing changed-stream semantic fingerprint between those logical
slots. It emits only hashes, stream metadata, allowlisted tokens, and known
checkpoint-field labels; no arbitrary save payload is exported.
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
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


def slot_streams(blob: bytes, lay: dict) -> tuple[list[bytes], list[list[dict]]]:
    raw_slots: list[bytes] = []
    streams: list[list[dict]] = []
    for slot in range(lay["slot_count"]):
        start = lay["prefix"] + slot * lay["stride"]
        raw = blob[start : start + lay["stride"]]
        raw_slots.append(raw)
        streams.append(base.scan_slot(raw, slot))
    return raw_slots, streams


def similarity(a: list[dict], b: list[dict]) -> dict:
    ah = [x["sha256"] for x in a]
    bh = [x["sha256"] for x in b]
    seq = SequenceMatcher(a=ah, b=bh, autojunk=False).ratio() if (ah or bh) else 1.0
    aset, bset = set(ah), set(bh)
    union = aset | bset
    shared = aset & bset
    jaccard = (len(shared) / len(union)) if union else 1.0
    containment = (len(shared) / min(len(aset), len(bset))) if aset and bset else (1.0 if not aset and not bset else 0.0)
    return {
        "sequence_ratio": seq,
        "jaccard": jaccard,
        "containment": containment,
        "shared_hashes": len(shared),
        "a_streams": len(a),
        "b_streams": len(b),
        "score": (seq * 0.60) + (jaccard * 0.25) + (containment * 0.15),
    }


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
    for path in (alive, dead):
        if not path.is_file():
            raise RuntimeError(f"Frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing active save tree: {path}")

    before = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    blobs = {"alive": alive.read_bytes(), "dead": dead.read_bytes()}
    layouts = {k: base.layout(v) for k, v in blobs.items()}
    if layouts["alive"] != layouts["dead"]:
        raise RuntimeError(f"Frozen saves disagree on layout: {layouts}")
    lay = layouts["alive"]

    alive_raw, alive_streams = slot_streams(blobs["alive"], lay)
    dead_raw, dead_streams = slot_streams(blobs["dead"], lay)
    changed_physical = [
        i for i in range(lay["slot_count"])
        if base.sha256_bytes(alive_raw[i]) != base.sha256_bytes(dead_raw[i])
    ]

    matches = []
    for dead_slot in changed_physical:
        ranked = []
        for alive_slot in range(lay["slot_count"]):
            sim = similarity(alive_streams[alive_slot], dead_streams[dead_slot])
            ranked.append({"alive_slot": alive_slot, "dead_slot": dead_slot, **sim})
        ranked.sort(key=lambda x: (-x["score"], -x["shared_hashes"], x["alive_slot"]))
        best = ranked[0]
        runs = base.changed_runs(alive_streams[best["alive_slot"]], dead_streams[dead_slot], dead_slot)
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
                    "alive_raven_streams": a_raven,
                    "dead_raven_streams": b_raven,
                    "tokens_only_alive": run["tokens_only_a"],
                    "tokens_only_dead": run["tokens_only_b"],
                    "tokens_shared": run["tokens_shared"],
                })
        matches.append({
            "dead_slot": dead_slot,
            "best_alive_slot": best["alive_slot"],
            "best_similarity": best,
            "top_matches": ranked[:5],
            "logical_changed_run_count": len(runs),
            "logical_changed_runs": runs,
            "raven_field_run_count": len(raven_runs),
            "raven_field_runs": raven_runs,
        })

    after = {"alive": base.sha256_file(alive), "dead": base.sha256_file(dead)}
    if before != after:
        raise RuntimeError("Frozen save hash changed during read-only scan")

    report = {
        "schema": 1,
        "analysis": "raven_alive_dead_cross_slot",
        "status": "CROSS_SLOT_MATCHED" if matches else "NO_PHYSICAL_SLOT_CHANGE",
        "layout": lay,
        "source_hashes": before,
        "source_hashes_unchanged": True,
        "changed_physical_slots": changed_physical,
        "matches": matches,
        "runtime_generation_allowed": False,
        "safety": {
            "active_save_opened": False,
            "source_files_written": False,
            "arbitrary_save_bytes_emitted": False,
            "process_memory_read": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Raven alive/dead cross-slot match",
        "",
        f"Status: **{report['status']}**",
        f"Physical changed slots: {', '.join(map(str, changed_physical)) or 'none'}",
        "",
    ]
    for item in matches:
        sim = item["best_similarity"]
        lines.extend([
            f"## DEAD slot {item['dead_slot']} -> ALIVE slot {item['best_alive_slot']}",
            "",
            f"- score={sim['score']:.6f}",
            f"- sequence_ratio={sim['sequence_ratio']:.6f}",
            f"- jaccard={sim['jaccard']:.6f}",
            f"- containment={sim['containment']:.6f}",
            f"- shared_hashes={sim['shared_hashes']}",
            f"- streams alive={sim['a_streams']} dead={sim['b_streams']}",
            f"- logical changed runs={item['logical_changed_run_count']}",
            f"- changed runs containing ravenKilled={item['raven_field_run_count']}",
            "",
        ])
        for rr in item["raven_field_runs"]:
            lines.append(
                f"- raven run {rr['run']} {rr['opcode']} A{rr['a_index_range']} B{rr['b_index_range']} "
                f"alive_raven={len(rr['alive_raven_streams'])} dead_raven={len(rr['dead_raven_streams'])}"
            )
        lines.append("")
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    summary = [
        "RAVEN_ALIVE_DEAD_CROSS_SLOT_COMPLETED",
        f"status={report['status']}",
        f"changed_physical_slots={','.join(map(str, changed_physical))}",
        f"matches={len(matches)}",
        f"raven_field_runs_total={sum(x['raven_field_run_count'] for x in matches)}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "source_files_written=false",
        "process_memory_read=false",
    ]
    for item in matches:
        sim = item["best_similarity"]
        summary.append(
            f"dead_slot_{item['dead_slot']}_best_alive_slot={item['best_alive_slot']} score={sim['score']:.6f} "
            f"shared={sim['shared_hashes']} logical_runs={item['logical_changed_run_count']} "
            f"raven_runs={item['raven_field_run_count']}"
        )
    args.summary.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
