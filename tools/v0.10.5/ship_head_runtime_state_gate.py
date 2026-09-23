#!/usr/bin/env python3
"""Validate the pinned live global staged-WAD Ship Head state capture.

This gate does not read a live process. It only validates already archived runtime
evidence and remains fail-closed until all nine Ship Heads have exact state proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAPTURE = REPO / "archive/field-logs/runtime-captures/staged-wad-bitstream-ship-head-20260923-055046-6340ad59/capture-data/report.json"
EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_CAPTURE_SHA256 = "19e1a5be1c63b73d1c0177b253e27a60e6622209"
EXPECTED_OBJECT_HASH = {
    1: "0xBECC6C40DB8D6DC5",
    2: "0x415D5E2E4B5CBC91",
    3: "0x0670C1234B277C01",
    4: "0x3607EBAE7B11E4AF",
    5: "0x5BF0302BD002420F",
    6: "0x1A5E4B6BD56B6B18",
    7: "0xC3373DF5E687D64B",
    8: "0x53A77B9EFA8D13CB",
    9: "0xE82841BEC7B6D5A9",
}
EXPECTED_STATE = {1: 3.0, 2: 3.0, 3: 3.0, 4: 1.0, 5: 3.0, 6: 3.0, 7: 3.0, 9: 3.0}
EXPECTED_WADS = {
    "cal100_hub.wad",
    "xpl910_islandshipwreck.wad",
    "xpl940_beachcave.wad",
    "xpl950_beachmaze.wad",
    "xpl960_beachship.wad",
    "xpl970_beachtower.wad",
    "xpl980_beachwaterfall.wad",
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def assess(capture: dict) -> dict:
    require(capture.get("analysis") == "live_staged_wad_ship_head_state",
            "capture analysis kind differs")
    process = capture.get("process", {})
    require(process.get("exe_sha256") == EXPECTED_EXE_SHA256,
            "GoW executable digest differs")
    safety = capture.get("safety", {})
    require(safety.get("open_process_access") == "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION" and
            safety.get("process_memory_written") is False and
            safety.get("hook_installed") is False and
            safety.get("save_opened_by_probe") is False and
            safety.get("save_written_by_probe") is False and
            safety.get("progression_written_by_probe") is False,
            "runtime capture safety contract differs")

    snapshot = capture.get("snapshot", {})
    require(snapshot.get("equal_reads") == 2 and snapshot.get("record_count") == 425 and
            snapshot.get("matches_frozen_425_record_census") is True,
            "global staged snapshot census differs")
    scope = capture.get("scope", {})
    require(scope.get("current_streamed_zone_not_required") is True and
            scope.get("all_ship_head_wads_present") is True and
            scope.get("target_wads_missing") == [] and
            set(scope.get("target_wads_present", [])) == EXPECTED_WADS,
            "global Ship Head WAD coverage differs")

    rows = capture.get("ship_heads", [])
    require(len(rows) == 9, "Ship Head runtime row census differs")
    by_number = {int(row["number"]): row for row in rows}
    require(set(by_number) == set(range(1, 10)), "Ship Head runtime numbering differs")
    proved = []
    unresolved = []
    for number in range(1, 10):
        row = by_number[number]
        require(row.get("object_hash_hex") == EXPECTED_OBJECT_HASH[number],
                f"Ship Head {number:02d} object hash differs")
        require(row.get("wad_present_in_staged_table") is True,
                f"Ship Head {number:02d} WAD absent from staged table")
        if number == 8:
            require(row.get("exact_state_match_count") == 0 and row.get("state_values") == [] and
                    row.get("authority") == "unknown_fail_closed",
                    "Ship Head 08 unexpectedly changed; transition proof required")
            unresolved.append(number)
        else:
            require(row.get("exact_state_match_count") == 1 and
                    row.get("state_values") == [EXPECTED_STATE[number]] and
                    row.get("authority") == "live_staged_exact_key",
                    f"Ship Head {number:02d} exact live state differs")
            proved.append(number)

    summary = capture.get("summary", {})
    require(summary.get("exact_state_rows") == 8 and
            summary.get("ambiguous_state_rows") == 0 and
            summary.get("head08_exact_state_found") is False and
            summary.get("runtime_generation_allowed") is False,
            "capture summary differs")
    return {
        "schema": 1,
        "status": "BLOCKED_HEAD08_UNRESOLVED",
        "runtime_generation_allowed": False,
        "global_staged_lookup_proven_count": len(proved),
        "global_staged_lookup_proven_numbers": proved,
        "unresolved_numbers": unresolved,
        "all_ship_head_wads_present": True,
        "staged_record_count": 425,
        "head08_wad_present": by_number[8]["wad_present_in_staged_table"],
        "head08_derived_object_hash_hex": EXPECTED_OBJECT_HASH[8],
        "head08_exact_state_found": False,
        "head08_next_proof": "observe the same exact key before/after acquiring physical Ship Head 08, or prove a different native key",
        "claim_limit": "This proves exact state visibility in the global native staged-WAD cache for 8/9 rows; it does not yet prove Head 08 or a generic save API.",
        "capture": str(CAPTURE.relative_to(REPO)).replace("\\", "/"),
        "capture_sha256": hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(CAPTURE.is_file(), f"pinned runtime capture missing: {CAPTURE}")
    require(hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == EXPECTED_CAPTURE_SHA256,
            "pinned runtime capture digest differs")
    report = assess(json.loads(CAPTURE.read_text(encoding="utf-8")))
    if args.output:
        target = args.output.resolve()
        require(REPO in target.parents, "output must stay inside repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(report), encoding="utf-8")
    print("SHIP_HEAD_RUNTIME_STATE_GATE BLOCKED_HEAD08_UNRESOLVED global_staged_lookup=8/9 head08=0/1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
