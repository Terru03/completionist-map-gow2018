#!/usr/bin/env python3
"""Prove Legendary Chest persisted state semantics from stock game script evidence.

Offline/read-only proof:
- verifies interact_chest_standard.lua defines OPENED = 4;
- verifies opening assigns state = states.OPENED;
- verifies Legendary opening updates RegionSummary_LegendaryChest;
- verifies accepted staged Legendary carriers serialize state as tag1 scalar;
- proves raw 0100008040 decodes to float32 4.0 and therefore OPENED.

No process, save, progression, or game-file writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct

EXPECTED_ENUM = {
    "ENABLED": 1,
    "DISABLED": 2,
    "LOCKED": 3,
    "OPENED": 4,
}
EXPECTED_OPENED_RAW = "0100008040"
STANDARD_SCRIPT = "gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua"


def extract_standard_script_evidence(text: str) -> dict:
    blocks = []
    current = []
    keep = False
    for line in text.splitlines():
        if line.startswith("=== "):
            if current and keep:
                blocks.append("\n".join(current))
            current = [line]
            keep = STANDARD_SCRIPT in line
        else:
            current.append(line)
    if current and keep:
        blocks.append("\n".join(current))
    joined = "\n".join(blocks)

    enum_values = {}
    for name in EXPECTED_ENUM:
        m = re.search(rf"\b{name}\s*=\s*(\d+)\b", joined)
        if m:
            enum_values[name] = int(m.group(1))

    evidence = {
        "enum_values": enum_values,
        "opened_assignment_present": "state = states.OPENED" in joined,
        "legendary_type_check_present": 'if chestType == "Legendary" then' in joined,
        "legendary_region_summary_update_present": (
            'UpdateRegionSummary(currentRegion, "LegendaryChest")' in joined
        ),
        "opened_restore_branch_present": (
            "elseif state == states.OPENED then" in joined
        ),
    }
    if enum_values != EXPECTED_ENUM:
        raise RuntimeError(f"standard chest enum mismatch: {enum_values}")
    if not all(
        evidence[key]
        for key in (
            "opened_assignment_present",
            "legendary_type_check_present",
            "legendary_region_summary_update_present",
            "opened_restore_branch_present",
        )
    ):
        raise RuntimeError(f"standard chest OPENED evidence incomplete: {evidence}")
    return evidence


def decode_tag1_float(raw_hex: str) -> float:
    raw = bytes.fromhex(raw_hex)
    if len(raw) != 5 or raw[0] != 1:
        raise RuntimeError(f"unexpected state scalar encoding: {raw_hex}")
    return struct.unpack("<f", raw[1:])[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script-scan", type=Path, required=True)
    parser.add_argument("--identity-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    scan = args.script_scan.read_text(encoding="utf-8-sig")
    script_evidence = extract_standard_script_evidence(scan)

    identity_report = json.loads(
        args.identity_report.read_text(encoding="utf-8")
    )
    if identity_report.get("status") != "EXACT_32_OF_32_STAGED_BINDING":
        raise RuntimeError("accepted Legendary identity report is not 32/32")

    represented = [
        row for row in identity_report.get("identities", [])
        if row.get("staged_represented")
    ]
    if len(represented) != 32:
        raise RuntimeError(f"expected 32 represented rows, got {len(represented)}")

    state_rows = [
        row for row in represented
        if row.get("staged_state") is not None
    ]
    raw_values = sorted({
        row["staged_state"]["state_raw_hex"]
        for row in state_rows
    })
    decoded_values = {
        raw: decode_tag1_float(raw)
        for raw in raw_values
    }
    if EXPECTED_OPENED_RAW not in decoded_values:
        raise RuntimeError("no staged Legendary state=4.0 evidence present")
    if decoded_values[EXPECTED_OPENED_RAW] != 4.0:
        raise RuntimeError("OPENED raw scalar does not decode to 4.0")

    opened_rows = [
        row for row in state_rows
        if row["staged_state"]["state_raw_hex"] == EXPECTED_OPENED_RAW
    ]
    if not opened_rows:
        raise RuntimeError("no staged Legendary rows carry OPENED scalar")

    report = {
        "schema": 1,
        "analysis": "legendary_opened_state_semantics",
        "status": "LEGENDARY_OPENED_STATE_SEMANTICS_PROVEN",
        "stock_standard_chest_script": {
            "path": STANDARD_SCRIPT,
            **script_evidence,
            "semantic_rule": "OPENED == 4",
            "opening_transition": "state = states.OPENED",
            "legendary_completion_side_effect": (
                'UpdateRegionSummary(currentRegion, "LegendaryChest")'
            ),
        },
        "checkpoint_carrier": {
            "field": "state",
            "value_tag": 1,
            "opened_raw_hex": EXPECTED_OPENED_RAW,
            "opened_u32": 0x40800000,
            "opened_float32": 4.0,
            "observed_raw_values": raw_values,
            "observed_float32_values": decoded_values,
            "represented_identity_count": len(represented),
            "opened_value_row_count": len(opened_rows),
            "opened_value_catalogue_ids": [
                row["catalogue_id"] for row in opened_rows
            ],
        },
        "conclusion": {
            "state_semantics_proven": True,
            "opened_state_numeric": 4,
            "opened_state_float32": 4.0,
            "opened_state_raw_hex": EXPECTED_OPENED_RAW,
            "production_rule": "hide marker iff exact persisted state == 4.0",
            "fail_closed_on_missing_or_ambiguous_state": True,
        },
        "safety": {
            "offline_only": True,
            "process_accessed": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
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
        "Completionist Map - Legendary OPENED state semantics",
        "status=LEGENDARY_OPENED_STATE_SEMANTICS_PROVEN",
        "stock_script=interact_chest_standard.lua",
        "stock_enum=ENABLED:1,DISABLED:2,LOCKED:3,OPENED:4",
        "opening_transition=state = states.OPENED",
        "legendary_region_summary_update=true",
        f"persisted_opened_raw={EXPECTED_OPENED_RAW}",
        "persisted_opened_u32=1082130432",
        "persisted_opened_float32=4.0",
        f"represented_identities={len(represented)}",
        f"opened_value_rows={len(opened_rows)}",
        "state_semantics_proven=true",
        "production_rule=hide marker iff exact persisted state == 4.0",
        "fail_closed_on_missing_or_ambiguous_state=true",
        "",
        "SAFETY",
        "offline_only=true",
        "process_accessed=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "LEGENDARY_OPENED_STATE_SEMANTICS_PROVEN "
        "OPENED=4 persisted_float32=4.0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
