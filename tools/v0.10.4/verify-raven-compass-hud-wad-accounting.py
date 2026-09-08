"""Verify r_ui.wad bookkeeping for the minimal three-payload Raven HUD clone.

Read-only gate. This does not build or install a candidate. It proves which of
DockPoint's three cloned HUD payloads participate in WAD_R_UI's Rig type table.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

EXPECTED_WAD = "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3"
HELPER = "build-raven-ui-logical-clone.py"
HELPER_SHA256_LF = "d5f7c5b77166b3e9ba46dec17174fc1f30ca5e3bab492527636cdf63c8b41b03"
RESULT = "READ_ONLY_RAVEN_COMPASS_HUD_WAD_ACCOUNTING"

SOURCE_ROOT = "goboatdock"
SOURCE_PROTO = "goProtoBoatDock"
SOURCE_MODEL = "MDL_boatdock"

NEW_ROOT = "gocompletionistravenhud"
NEW_PROTO = "goProtoCompletionistRavenHUD"
NEW_MODEL = "MDL_completionistravenhud"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_helper():
    path = Path(__file__).with_name(HELPER)
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    check(sha256(raw) == HELPER_SHA256_LF, f"pinned helper changed: {HELPER}")
    spec = importlib.util.spec_from_file_location("completionist_hud_accounting_wad", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def one_payload(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"].lower() == name.lower() and len(r["data"]) > 0]
    check(len(rows) == 1, f"expected one payload {name!r}, found {len(rows)}")
    return rows[0]


def first_dword(record: dict) -> int:
    check(len(record["data"]) >= 4, f"short payload: {record['name']}")
    return struct.unpack_from("<I", record["data"], 0)[0]


def row_summary(row: dict) -> dict:
    return {
        "key": f"0x{int(row['key']):X}",
        "base": int(row["base"]),
        "count": int(row["count"]),
    }


def payload_summary(record: dict) -> dict:
    return {
        "name": record["name"],
        "id": record["id"].hex(),
        "kind": int(record["kind"]),
        "flags": f"0x{int(record['flags']):X}",
        "bytes": len(record["data"]),
        "payload_index": record["payload_index"],
        "first_dword": f"0x{first_dword(record):X}",
    }


def verify(raw: bytes) -> dict:
    check(sha256(raw) == EXPECTED_WAD, "r_ui.wad is not the current proven Raven state")
    helper = load_helper()
    records = helper.parse_wad(raw)
    check(helper.serialize_wad(records) == raw, "current r_ui.wad does not round-trip byte-exactly")
    payloads = helper.payload_records(records)
    check(len(payloads) >= 2, "WAD has fewer than two payloads")

    heap = payloads[0]
    root = payloads[1]
    check(heap["name"].upper() == "WAD_R_UI" and root["name"].upper() == "WAD_R_UI",
          "first two WAD payloads are not WAD_R_UI accounting records")
    check(len(heap["data"]) >= 8 and len(root["data"]) >= 0x28, "short WAD accounting payload")

    heap_total = struct.unpack_from("<I", heap["data"], 4)[0]
    root_total = struct.unpack_from("<I", root["data"], 0x1C)[0]
    rows = helper.read_type_table(root["data"])
    check(heap_total == root_total, "heap/root type totals disagree")
    check(sum(int(row["count"]) for row in rows) == root_total, "type-row counts do not sum to root total")

    dock_root = one_payload(records, SOURCE_ROOT)
    dock_proto = one_payload(records, SOURCE_PROTO)
    dock_model = one_payload(records, SOURCE_MODEL)
    sources = [dock_root, dock_proto, dock_model]
    source_keys = {record["name"]: first_dword(record) for record in sources}

    check(int(dock_root["flags"]) == 0x3D and len(dock_root["data"]) == 164,
          "goboatdock payload shape changed")
    check(int(dock_proto["flags"]) == 0x3D and len(dock_proto["data"]) == 1184,
          "goProtoBoatDock payload shape changed")
    check(int(dock_model["flags"]) == 0x8E and len(dock_model["data"]) == 80,
          "MDL_boatdock payload shape changed")
    check(source_keys[SOURCE_PROTO] == 0x10001, "Dock prototype is not Rig type 0x10001")
    check(source_keys[SOURCE_ROOT] == 0x20001, "Dock root is not Rig type 0x20001")

    rows_by_key = {int(row["key"]): row for row in rows}
    check(0x10001 in rows_by_key and 0x20001 in rows_by_key, "required Rig type rows are missing")
    check(source_keys[SOURCE_MODEL] not in rows_by_key,
          "Dock model unexpectedly participates in WAD_R_UI root type table")

    relevant = {}
    for key in (0x10001, 0x20001):
        all_hits = [r for r in payloads if len(r["data"]) >= 4 and first_dword(r) == key]
        rig_hits = [r for r in all_hits if int(r["flags"]) == 0x3D]
        row = rows_by_key[key]
        check(len(all_hits) == int(row["count"]),
              f"type row {key:#x} count does not equal current payload first-dword count")
        check(len(rig_hits) == int(row["count"]),
              f"type row {key:#x} contains non-0x3D payloads or misses Rig payloads")
        relevant[f"0x{key:X}"] = {
            "row": row_summary(row),
            "payloads_with_first_dword": len(all_hits),
            "payloads_with_first_dword_and_flags_0x3D": len(rig_hits),
            "count_contract_exact": True,
        }

    increments = {0x10001: 1, 0x20001: 1}
    next_base = 0
    simulated_rows = []
    for row in rows:
        key = int(row["key"])
        amount = int(row["count"]) + increments.get(key, 0)
        simulated_rows.append({
            "key": f"0x{key:X}",
            "base": next_base,
            "count": amount,
            "delta": increments.get(key, 0),
        })
        next_base += amount
    check(next_base == root_total + 2, "simulated type total is not current total + 2")

    # This is deliberately +2, not +3: model payloads are outside this Rig table.
    new_payload_plan = [
        {"name": NEW_PROTO, "source": SOURCE_PROTO, "type_key": "0x10001", "root_table_delta": 1},
        {"name": NEW_ROOT, "source": SOURCE_ROOT, "type_key": "0x20001", "root_table_delta": 1},
        {"name": NEW_MODEL, "source": SOURCE_MODEL,
         "type_key": f"0x{source_keys[SOURCE_MODEL]:X}", "root_table_delta": 0},
    ]

    return {
        "result": RESULT,
        "game_files_read": True,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "source_wad_sha256": sha256(raw),
        "source_round_trip_byte_exact": True,
        "physical_record_count": len(records),
        "payload_count": len(payloads),
        "accounting": {
            "heap_total": heap_total,
            "root_total": root_total,
            "type_row_count": len(rows),
            "type_row_count_sum": sum(int(row["count"]) for row in rows),
            "relevant_rig_rows": relevant,
        },
        "dock_sources": {
            "root": payload_summary(dock_root),
            "prototype": payload_summary(dock_proto),
            "model": payload_summary(dock_model),
        },
        "three_payload_clone_plan": {
            "physical_payload_delta": 3,
            "root_type_accounting_delta": 2,
            "payloads": new_payload_plan,
            "simulated_heap_total": heap_total + 2,
            "simulated_root_total": root_total + 2,
            "simulated_type_rows": simulated_rows,
        },
        "proof": {
            "prototype_type_row_is_exact_first_dword_population": True,
            "root_type_row_is_exact_first_dword_population": True,
            "model_first_dword_absent_from_root_type_table": True,
            "clone_requires_0x10001_delta": 1,
            "clone_requires_0x20001_delta": 1,
            "clone_requires_model_type_delta": 0,
            "ready_for_offline_three_payload_builder": True,
        },
        "conclusion": "THREE_PAYLOAD_RAVEN_HUD_WAD_ACCOUNTING_PROVEN",
        "next_gate": (
            "Build the three-payload HUD clone offline. Update only WAD_R_UI heap/root totals and "
            "the 0x10001/0x20001 row counts/bases implied by this report; then reparse and prove "
            "all stock Dock and existing Raven resources remain byte-identical."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    game = args.game_root.resolve()
    wad = game / "exec/wad/pc_le/r_ui.wad"
    check(wad.is_file(), f"missing {wad}")
    output = args.output.resolve()
    check(not output.is_relative_to(game), "report must stay outside game directory")
    before = wad.read_bytes()
    report = verify(before)
    check(wad.read_bytes() == before, "r_ui.wad changed during read-only verification")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["result"])
    print(f"  root/prototype type delta: +{report['three_payload_clone_plan']['root_type_accounting_delta']}")
    print("  model type delta:          +0")
    print(f"  conclusion:                {report['conclusion']}")
    print(f"  report:                    {output}")
    print("  game files written:        false")


if __name__ == "__main__":
    main()
