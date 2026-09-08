"""Build the corrected offline Completionist Raven map-class candidate.

This is the successor to the historical grown-WAD visual-clone experiment.  It
reuses that experiment only to construct the physical Raven resource chain, then
repairs the two static faults now proved by the v0.10.4 bookkeeping probes:

* WAD type-table rows are keyed by serialized resource type signatures, not by
  physical payload index ranges.  The eight new physical payloads contribute
  only six typed objects.
* A 0x20001 final-instance payload contains its own 56-byte resource name at
  +0x1C.  The Raven final must therefore contain
  ``gomapiconcompletionistraven`` internally as well as in its WAD header.

The output remains OFFLINE ONLY.  No God of War file, save, boot option or
progression state is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"

RAVEN_WAD_NAME = "gomapiconcompletionistraven"
RAVEN_DCB_NAME = "goMapIconCompletionistRaven"
RAVEN_FINAL_ID = bytes.fromhex("3d8f7153809e6db191c2d5e354f1e88c")

# Proved by completionist-v104-wad-type-signatures.json.  The stock physical
# cohorts match these type-table rows exactly when the listed transform/header
# rules are applied.
STOCK_TYPED_COUNTS = {
    0x0000000A: 1479,   # material, raw32, kind 1 / flags 0x14
    0x00010001: 1724,   # Rig prototype, raw32, kind 1 / flags 0x3D
    0x00020001: 2072,   # Rig final instance, raw32, kind 1 / flags 0x3D
    0x0002000C: 990,    # model, low28 of 0x1002000C, kind 1 / flags 0x8E
    0x00010015: 1445,   # texture definition, raw32, kind 1 / flags 0x8021
}
TYPE_DELTAS = {
    0x0000000A: 1,
    0x00010001: 1,
    0x00020001: 1,
    0x0002000C: 1,
    0x00010015: 2,
}
EXPECTED_PHYSICAL_PAYLOAD_DELTA = 8
EXPECTED_TYPED_DELTA = sum(TYPE_DELTAS.values())  # 6


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def first_dword(record: dict) -> int | None:
    if len(record["data"]) < 4:
        return None
    return struct.unpack_from("<I", record["data"])[0]


def internal_final_name(record: dict) -> str:
    check(record["flags"] == 0x3D and len(record["data"]) == 164,
          f"not a 164-byte final instance: {record['name']}")
    raw = bytes(record["data"])
    end = raw.find(b"\0", 0x1C, 0x54)
    check(end >= 0, f"unterminated final-instance name: {record['name']}")
    return raw[0x1C:end].decode("ascii")


def set_internal_final_name(record: dict, name: str) -> None:
    encoded = name.encode("ascii")
    check(len(encoded) <= 55, "final-instance internal name exceeds 55 bytes")
    record["data"][0x1C:0x54] = encoded + bytes(56 - len(encoded))


def typed_cohort_counts(records: list[dict]) -> dict[int, int]:
    out = {key: 0 for key in STOCK_TYPED_COUNTS}
    for record in records:
        if not record["data"]:
            continue
        word = first_dword(record)
        if word is None:
            continue
        if record["kind"] == 1 and record["flags"] == 0x14 and word == 0xA:
            out[0xA] += 1
        if record["kind"] == 1 and record["flags"] == 0x3D and word == 0x10001:
            out[0x10001] += 1
        if record["kind"] == 1 and record["flags"] == 0x3D and word == 0x20001:
            out[0x20001] += 1
        if record["kind"] == 1 and record["flags"] == 0x8E and (word & 0x0FFFFFFF) == 0x2000C:
            out[0x2000C] += 1
        if record["kind"] == 1 and record["flags"] == 0x8021 and word == 0x10015:
            out[0x10015] += 1
    return out


def patch_type_accounting(candidate_raw: bytes, stock_raw: bytes, logical) -> tuple[bytes, dict]:
    stock_records = logical.parse_wad(stock_raw)
    candidate_records = logical.parse_wad(candidate_raw)
    stock_payloads = logical.payload_records(stock_records)
    candidate_payloads = logical.payload_records(candidate_records)
    check(len(candidate_payloads) == len(stock_payloads) + EXPECTED_PHYSICAL_PAYLOAD_DELTA,
          "physical Raven payload delta is no longer eight")

    stock_rows = logical.read_type_table(stock_payloads[1]["data"])
    candidate_rows = logical.read_type_table(candidate_payloads[1]["data"])
    check([r["key"] for r in candidate_rows] == [r["key"] for r in stock_rows],
          "candidate WAD type-row key order changed")

    stock_table = {r["key"]: r for r in stock_rows}
    for key, expected in STOCK_TYPED_COUNTS.items():
        check(stock_table[key]["count"] == expected,
              f"stock type count changed for {key:#x}: {stock_table[key]['count']}")

    stock_cohorts = typed_cohort_counts(stock_records)
    check(stock_cohorts == STOCK_TYPED_COUNTS,
          f"stock serialized type cohorts changed: {stock_cohorts}")

    # Ignore the historical candidate's range-based bookkeeping and rebuild the
    # entire table from the pinned stock rows plus the proven serialized deltas.
    new_base = 0
    expected_rows = {}
    for stock_row, candidate_row in zip(stock_rows, candidate_rows):
        key = stock_row["key"]
        count = stock_row["count"] + TYPE_DELTAS.get(key, 0)
        struct.pack_into("<III", candidate_payloads[1]["data"], candidate_row["offset"],
                         key, new_base, count)
        expected_rows[key] = {"base": new_base, "count": count}
        new_base += count

    stock_total = sum(r["count"] for r in stock_rows)
    check(stock_total == 16796, f"stock typed total changed: {stock_total}")
    check(new_base == stock_total + EXPECTED_TYPED_DELTA,
          "corrected typed total does not equal stock + 6")
    struct.pack_into("<I", candidate_payloads[1]["data"], 0x1C, new_base)
    struct.pack_into("<I", candidate_payloads[0]["data"], 4, new_base)

    # The historical visual clone changed only the outer WAD header name for the
    # new 0x20001 final.  Repair its embedded resource name as well.
    raven_finals = [
        r for r in candidate_records
        if r["data"] and r["id"] == RAVEN_FINAL_ID and r["name"].lower() == RAVEN_WAD_NAME.lower()
    ]
    check(len(raven_finals) == 1, f"expected one Raven final, found {len(raven_finals)}")
    raven_final = raven_finals[0]
    old_internal = internal_final_name(raven_final)
    check(old_internal == "gomapicondock" or old_internal == RAVEN_WAD_NAME,
          f"unexpected inherited final name: {old_internal}")
    set_internal_final_name(raven_final, RAVEN_WAD_NAME)

    corrected = logical.serialize_wad(candidate_records)
    reparsed = logical.parse_wad(corrected)
    reparsed_payloads = logical.payload_records(reparsed)
    rows = logical.read_type_table(reparsed_payloads[1]["data"])
    check(sum(r["count"] for r in rows) == new_base, "corrected type-row sum changed")
    check(struct.unpack_from("<I", reparsed_payloads[0]["data"], 4)[0] == new_base,
          "corrected heap total changed")
    check(struct.unpack_from("<I", reparsed_payloads[1]["data"], 0x1C)[0] == new_base,
          "corrected root total changed")
    for row in rows:
        expected = expected_rows[row["key"]]
        check((row["base"], row["count"]) == (expected["base"], expected["count"]),
              f"corrected row changed for {row['key']:#x}")

    candidate_cohorts = typed_cohort_counts(reparsed)
    expected_cohorts = {key: STOCK_TYPED_COUNTS[key] + TYPE_DELTAS[key] for key in STOCK_TYPED_COUNTS}
    check(candidate_cohorts == expected_cohorts,
          f"candidate serialized cohorts do not match corrected table deltas: {candidate_cohorts}")

    final_after = [r for r in reparsed if r["data"] and r["id"] == RAVEN_FINAL_ID]
    check(len(final_after) == 1, "Raven final did not reparse uniquely after correction")
    check(final_after[0]["name"] == RAVEN_WAD_NAME, "Raven final WAD header name changed")
    check(internal_final_name(final_after[0]) == RAVEN_WAD_NAME,
          "Raven final embedded name still differs from its WAD header")

    changed_rows = []
    for stock_row, row in zip(stock_rows, rows):
        if stock_row["base"] != row["base"] or stock_row["count"] != row["count"]:
            changed_rows.append({
                "key": f"0x{row['key']:X}",
                "stock_base": stock_row["base"],
                "candidate_base": row["base"],
                "stock_count": stock_row["count"],
                "candidate_count": row["count"],
                "count_delta": row["count"] - stock_row["count"],
            })

    return corrected, {
        "physical_payload_count_stock": len(stock_payloads),
        "physical_payload_count_candidate": len(reparsed_payloads),
        "physical_payload_delta": len(reparsed_payloads) - len(stock_payloads),
        "typed_total_stock": stock_total,
        "typed_total_candidate": new_base,
        "typed_total_delta": new_base - stock_total,
        "typed_delta_is_smaller_than_physical_delta": EXPECTED_TYPED_DELTA < EXPECTED_PHYSICAL_PAYLOAD_DELTA,
        "proven_type_count_deltas": {f"0x{k:X}": v for k, v in TYPE_DELTAS.items()},
        "stock_typed_cohorts": {f"0x{k:X}": v for k, v in stock_cohorts.items()},
        "candidate_typed_cohorts": {f"0x{k:X}": v for k, v in candidate_cohorts.items()},
        "changed_type_rows": changed_rows,
        "final_embedded_name_before_fix": old_internal,
        "final_header_name_after_fix": final_after[0]["name"],
        "final_embedded_name_after_fix": internal_final_name(final_after[0]),
        "final_header_payload_name_consistent": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--work-dir", type=Path,
                    default=Path(os.environ.get("LOCALAPPDATA", ".")) /
                            "CompletionistMap/work/v0.10.4/raven-ui-registered-class")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    work = args.work_dir.resolve()
    output = args.output.resolve()
    check(not work.is_relative_to(game), "work directory must stay outside game tree")
    check(not output.is_relative_to(game), "report must stay outside game tree")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    wad_raw = wad_path.read_bytes()
    dcb_raw = dcb_path.read_bytes()
    check(sha(wad_raw) == EXPECTED_WAD, "r_ui.wad is not the pinned stock file")
    check(sha(dcb_raw) == EXPECTED_DCB, "wad_r_ui.dcb is not the pinned stock file")

    logical = load_module("completionist_logical", HERE / "build-raven-ui-logical-clone.py")
    historical = load_module("completionist_visual_history", HERE / "build-raven-ui-visual-clone.py")

    historical_candidate, historical_report = historical.build_wad(wad_raw, logical)
    corrected_candidate, accounting = patch_type_accounting(historical_candidate, wad_raw, logical)
    dcb_candidate, dcb_report = logical.build_dcb(dcb_raw)

    work.mkdir(parents=True, exist_ok=True)
    wad_out = work / "r_ui.wad"
    dcb_out = work / "wad_r_ui.dcb"
    wad_out.write_bytes(corrected_candidate)
    dcb_out.write_bytes(dcb_candidate)

    check(wad_path.read_bytes() == wad_raw and dcb_path.read_bytes() == dcb_raw,
          "source game files changed during offline build")

    report = {
        "result": "OFFLINE_RAVEN_UI_REGISTERED_CLASS_CANDIDATE_BUILT",
        "game_files_written": False,
        "save_files_written": False,
        "runtime_test_ready": False,
        "source_hashes_unchanged_after_build": True,
        "source_hashes": {
            "r_ui.wad": sha(wad_raw),
            "wad_r_ui.dcb": sha(dcb_raw),
        },
        "candidate": {
            "directory": str(work),
            "r_ui_wad": {
                "path": str(wad_out),
                "bytes": len(corrected_candidate),
                "sha256": sha(corrected_candidate),
            },
            "wad_r_ui_dcb": {
                "path": str(dcb_out),
                "bytes": len(dcb_candidate),
                "sha256": sha(dcb_candidate),
            },
        },
        "map_class": {
            "dcb_name": RAVEN_DCB_NAME,
            "wad_final_name": RAVEN_WAD_NAME,
            "wad_final_id": RAVEN_FINAL_ID.hex(),
            "dedicated_completionist_identity": True,
            "stock_dock_identity_reused": False,
            "stock_dock_visual_resources_modified": False,
        },
        "corrected_bookkeeping": accounting,
        "historical_builder_resource_chain_validation": historical_report,
        "dcb_validation": dcb_report,
        "gates": {
            "serialized_type_cohorts_match_corrected_counts": True,
            "type_table_rebuilt_from_stock_plus_proven_deltas": True,
            "heap_and_root_totals_equal_type_row_sum": True,
            "final_header_payload_name_consistent": True,
            "dedicated_gopool_entry_built": True,
            "runtime_loader_name_resolution_still_requires_field_proof": True,
            "new_runtime_candidate_allowed": False,
        },
        "next_gate": (
            "Statically audit the corrected candidate through the resource-name lookup path and "
            "GOWTool parser before allowing any reversible runtime install."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "result": report["result"],
        "physical_payload_delta": accounting["physical_payload_delta"],
        "typed_total_delta": accounting["typed_total_delta"],
        "final_name_consistent": accounting["final_header_payload_name_consistent"],
        "runtime_test_ready": False,
        "candidate_wad": str(wad_out),
        "output": str(output),
    }, indent=2))
    print("No God of War files, saves, boot options, or progression state were modified.")


if __name__ == "__main__":
    main()
