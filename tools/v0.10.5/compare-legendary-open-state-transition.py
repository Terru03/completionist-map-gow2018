#!/usr/bin/env python3
"""Compare controlled before/after exact Legendary state captures.

Acceptance requires exactly one tracked Legendary identity to change scalar state
while present in both captures. The user-provided gameplay action is opening
exactly one previously unopened tracked Legendary Chest between captures.

This comparator is offline and performs no process/save/game writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct


def state_float32(raw_hex: str | None):
    if not raw_hex:
        return None
    raw = bytes.fromhex(raw_hex)
    if len(raw) != 5 or raw[0] != 1:
        return None
    return struct.unpack("<f", raw[1:])[0]


def by_id(report: dict) -> dict[str, dict]:
    rows = report.get("states", [])
    result = {}
    for row in rows:
        cid = row["catalogue_id"]
        if cid in result:
            raise RuntimeError(f"duplicate catalogue id: {cid}")
        result[cid] = row
    if len(result) != 33:
        raise RuntimeError(f"expected 33 tracked states, got {len(result)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    before_report = json.loads(args.before.read_text(encoding="utf-8"))
    after_report = json.loads(args.after.read_text(encoding="utf-8"))
    before = by_id(before_report)
    after = by_id(after_report)

    changes = []
    presence_changes = []
    common_present = 0

    for cid in sorted(before):
        b = before[cid]
        a = after[cid]
        bp = b.get("present") is True
        ap = a.get("present") is True

        if bp and ap:
            common_present += 1
            old = (b.get("state_raw_hex"), b.get("state_u32"))
            new = (a.get("state_raw_hex"), a.get("state_u32"))
            if old != new:
                changes.append({
                    "catalogue_id": cid,
                    "wad": a["wad"],
                    "registry_hash_hex": a["registry_hash_hex"],
                    "object_hash_hex": a["object_hash_hex"],
                    "serialized_flag1_hex": a["serialized_flag1_hex"],
                    "before_state_raw_hex": b["state_raw_hex"],
                    "before_state_u32": b["state_u32"],
                    "before_state_float32": state_float32(
                        b["state_raw_hex"]
                    ),
                    "after_state_raw_hex": a["state_raw_hex"],
                    "after_state_u32": a["state_u32"],
                    "after_state_float32": state_float32(
                        a["state_raw_hex"]
                    ),
                })
        elif bp != ap:
            presence_changes.append({
                "catalogue_id": cid,
                "wad": a["wad"],
                "before_present": bp,
                "after_present": ap,
            })

    accepted = len(changes) == 1
    transition = changes[0] if accepted else None

    report = {
        "schema": 1,
        "analysis": "legendary_open_state_transition",
        "status": (
            "EXACT_ONE_LEGENDARY_STATE_TRANSITION"
            if accepted
            else "NO_UNIQUE_LEGENDARY_STATE_TRANSITION"
        ),
        "before_capture": str(args.before),
        "after_capture": str(args.after),
        "common_present_count": common_present,
        "changed_state_count": len(changes),
        "presence_change_count": len(presence_changes),
        "changes": changes,
        "presence_changes": presence_changes,
        "transition": transition,
        "opened_state_semantics_proven": accepted,
        "opened_state": (
            {
                "state_raw_hex": transition["after_state_raw_hex"],
                "state_u32": transition["after_state_u32"],
                "state_float32": transition["after_state_float32"],
                "proof_basis": (
                    "controlled normal gameplay: exactly one previously unopened "
                    "tracked Legendary Chest opened between exact identity captures"
                ),
            }
            if accepted
            else None
        ),
        "safety": {
            "offline_comparison_only": True,
            "process_accessed": False,
            "active_save_opened": False,
            "save_written_by_tooling": False,
            "progression_written_by_tooling": False,
            "game_files_written": False,
            "raven_runtime_modified": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "Completionist Map - Legendary open-state transition",
        f"status={report['status']}",
        (
            f"common_present={common_present} "
            f"changed_states={len(changes)} "
            f"presence_changes={len(presence_changes)}"
        ),
    ]
    for change in changes:
        lines.append(
            f"CHANGE {change['catalogue_id']} wad={change['wad']} "
            f"before_u32={change['before_state_u32']} "
            f"before_f32={change['before_state_float32']} "
            f"after_u32={change['after_state_u32']} "
            f"after_f32={change['after_state_float32']}"
        )
    if accepted:
        lines += [
            "",
            "OPENED SEMANTICS",
            f"state_raw_hex={transition['after_state_raw_hex']}",
            f"state_u32={transition['after_state_u32']}",
            f"state_float32={transition['after_state_float32']}",
            f"catalogue_id={transition['catalogue_id']}",
            f"object_hash={transition['object_hash_hex']}",
        ]
    lines += [
        "",
        "SAFETY",
        "offline_comparison_only=true",
        "save_written_by_tooling=false",
        "progression_written_by_tooling=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "LEGENDARY_OPEN_STATE_TRANSITION_COMPLETE "
        f"status={report['status']} changes={len(changes)}"
    )
    if accepted:
        print(
            "OPENED_STATE_PROVEN "
            f"raw={transition['after_state_raw_hex']} "
            f"u32={transition['after_state_u32']} "
            f"f32={transition['after_state_float32']}"
        )
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
