#!/usr/bin/env python3
"""Offline replay of archived staged Channel A Raven capture.

Reads an existing runtime capture directory only. Does not open the game process,
save files, or write progression. Re-runs the current staged_wad_bitstream
decoder against each archived Channel A slice using the cached native Lua length
already stored in the capture report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import staged_wad_bitstream as bits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", type=Path, required=True)
    args = ap.parse_args()

    capture = args.capture_dir.resolve()
    report_path = capture / "report.json"
    if not report_path.is_file():
        raise RuntimeError(f"missing capture report: {report_path}")

    original = json.loads(report_path.read_text(encoding="utf-8"))
    catalogue = json.loads((REPO / "catalogue/odins-ravens-save-identities.json").read_text(encoding="utf-8"))
    rows = catalogue["identities"]
    object_map = {int(row["object_hash_hex"], 16): row["catalogue_id"] for row in rows}
    registry = int(catalogue["registry_hash_hex"], 16)

    states = {row["catalogue_id"]: set() for row in rows}
    blocked = set()
    replay_records = []

    for record in original["records"]:
        item = {
            "index": record["index"],
            "name": record.get("name"),
            "key_hex": record.get("key_hex"),
            "native_slot_index": record.get("native_slot_index"),
            "size": record.get("size", 0),
            "cached_channel_a_lua_length": record.get("cached_channel_a_lua_length"),
            "payload_file": record.get("payload_file"),
        }
        payload_file = item["payload_file"]
        if not payload_file:
            item["status"] = "no_payload"
            replay_records.append(item)
            continue
        payload_path = capture / payload_file
        payload = payload_path.read_bytes()
        expected = item["cached_channel_a_lua_length"]
        decoded = bits.extract_channel_a(payload, registry, object_map, expected_lua_length=expected)
        item["decode"] = decoded
        for rid, state in decoded["raven_states"].items():
            if state is not None:
                states[rid].add(state)
        if decoded.get("ambiguity_reasons"):
            for candidate in decoded.get("candidates", []):
                for entry in candidate.get("raven_entries", []):
                    blocked.add(entry["catalogue_id"])
        replay_records.append(item)

    raven_states = []
    for row in rows:
        rid = row["catalogue_id"]
        values = states[rid]
        value = next(iter(values)) if len(values) == 1 and rid not in blocked else None
        raven_states.append({
            "catalogue_id": rid,
            "candidate_ravenKilled": value,
            "conflict": len(values) > 1,
            "ambiguous": rid in blocked,
            "region": row.get("region"),
            "wad": row.get("wad"),
            "authority": "unproven",
        })

    known = [row for row in raven_states if row["candidate_ravenKilled"] is not None]
    output = {
        "schema": 1,
        "analysis": "offline_replay_staged_wad_bitstream_raven_candidates",
        "source_capture": str(capture.relative_to(REPO)).replace("\\", "/"),
        "source_capture_process": original.get("process"),
        "source_snapshot": original.get("snapshot"),
        "decoder": {
            "native_cached_lua_length_required": True,
            "production_ready": False,
            "enclosing_field_traversal_validated": False,
        },
        "records": replay_records,
        "raven_states": raven_states,
        "candidate_state_count": len(known),
        "unknown_count": len(raven_states) - len(known),
        "production_ready": False,
        "remaining_gate": (
            "Prove exact prefix traversal/native Lua field position, active checkpoint freshness, "
            "and exact fixture coverage before map integration."
        ),
        "safety": {
            "game_process_opened": False,
            "save_opened": False,
            "save_written": False,
            "progression_written": False,
            "offline_only": True,
        },
    }

    json_path = capture / "replay-report.json"
    txt_path = capture / "replay-report.txt"
    json_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Offline staged Channel A bitstream replay",
        f"candidate_state_count={len(known)} unknown_count={len(raven_states)-len(known)} production_ready=false",
    ]
    for rec in replay_records:
        dec = rec.get("decode")
        if not dec:
            continue
        if dec["candidate_count"] or dec.get("ambiguity_reasons"):
            lines.append(
                f"record={rec['index']} name={rec['name']!r} luaBytes={rec['cached_channel_a_lua_length']} "
                f"candidates={dec['candidate_count']} ambiguity={dec.get('ambiguity_reasons', [])}"
            )
            for cand in dec.get("candidates", []):
                if cand.get("raven_entries"):
                    lines.append(
                        f"  bit_offset={cand['bit_offset']} length={cand['length']} ravens={cand['raven_entries']}"
                    )
                unmatched = cand.get("carrier", {}).get("unmatched_raven_state_entries", [])
                for entry in unmatched:
                    lines.append(
                        f"  UNMATCHED_RAVEN_STATE bit_offset={cand['bit_offset']} "
                        f"object_hash={entry['object_hash_hex']} payload={entry['record_payload_hex']} "
                        f"ravenKilled={entry['ravenKilled']} state_row={entry['state_row']}"
                    )
    for row in known:
        lines.append(
            f"CANDIDATE {row['catalogue_id']} ravenKilled={row['candidate_ravenKilled']} "
            f"region={row.get('region')} wad={row.get('wad')}"
        )
    lines.append("game_process_opened=false save_opened=false save_written=false progression_written=false")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"STAGED_BITSTREAM_REPLAY_COMPLETE candidate_states={len(known)} production_ready=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
