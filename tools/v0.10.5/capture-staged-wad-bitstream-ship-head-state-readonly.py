#!/usr/bin/env python3
"""Read-only live scan of all staged WAD state for the nine Ship Heads.

This does not hook or write the game process. It snapshots the native staged WAD
record table and Channel A pool twice, requires equal bytes, and searches exact
Ship Head serialized GameObject keys across every staged record. It therefore
covers every Ship Head WAD present in the native staged cache, not merely the
currently streamed world area.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import staged_state_graph as graph
import ship_head_staged_identity as ship

CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
EXPECTED_OBJECT_HASH = {
    1: 0xBECC6C40DB8D6DC5,
    2: 0x415D5E2E4B5CBC91,
    3: 0x0670C1234B277C01,
    4: 0x3607EBAE7B11E4AF,
    5: 0x5BF0302BD002420F,
    6: 0x1A5E4B6BD56B6B18,
    7: 0xC3373DF5E687D64B,
    8: 0x53A77B9EFA8D13CB,
    9: 0xE82841BEC7B6D5A9,
}
STATE_SIGNATURE = [{"name": "state", "value_tag": 1}]
FROZEN_STAGED_RECORD_COUNT = 425


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normal_wad_name(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value).stem.lower() + ".wad"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def state_float(entry: dict) -> float | None:
    raw_hex = entry.get("state", {}).get("raw_hex")
    if not isinstance(raw_hex, str):
        return None
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        return None
    if len(raw) < 5 or raw[0] != 1:
        return None
    return struct.unpack("<f", raw[1:5])[0]


def target_rows() -> list[dict]:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    rows = [row for row in catalogue["collectibles"]
            if row.get("subtype") == "Ship Head" and row.get("family") == "artefact"]
    require(len(rows) == 9, f"expected nine Ship Heads, found {len(rows)}")
    out = []
    seen = set()
    for row in rows:
        number = int(row["native"]["numbered_object_evidence"][0])
        require(number in EXPECTED_OBJECT_HASH, f"unexpected Ship Head number {number}")
        wad = row["source"]["wad"]
        registry = ship.name_hash(Path(wad).stem)
        canonical_hashes = {
            ship.hash_path_records(ship.canonical_subset(path))
            for path in row["native"]["carrier_transform_paths"]
        }
        expected = EXPECTED_OBJECT_HASH[number]
        require(expected in canonical_hashes,
                f"Ship Head {number:02d} expected key no longer matches authored carrier paths")
        key = (registry, expected)
        require(key not in seen, f"duplicate Ship Head key {key}")
        seen.add(key)
        out.append({
            "number": number,
            "catalogue_id": row["catalogue_id"],
            "wad": wad,
            "registry_hash": registry,
            "object_hash": expected,
            "serialized_flag1_hex": (b"\x01" + registry.to_bytes(8, "little") +
                                      expected.to_bytes(8, "little")).hex(),
            "canonical_path_hashes": [f"0x{x:016X}" for x in sorted(canonical_hashes)],
        })
    return sorted(out, key=lambda item: item["number"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    require(not any(out.iterdir()), "output folder must be empty")
    require(sys.platform == "win32" and ctypes.sizeof(ctypes.c_void_p) == 8,
            "64-bit Windows required")

    capture = load_module("capture-staged-wad-bitstream-raven-state-readonly.py", "staged_capture")
    obs = capture.load_observer()
    targets = target_rows()
    target_keys = {(row["registry_hash"], row["object_hash"]): row for row in targets}
    target_wads = {normal_wad_name(row["wad"]) for row in targets}

    kernel = obs.k32_api()
    pid, process_name = obs.find_process(kernel)
    base, exe = obs.main_module(kernel, pid, process_name)
    exe_sha = obs.sha256_file(Path(exe))
    require(exe_sha == obs.EXE_SHA, f"unsupported GoW.exe SHA-256: {exe_sha}")
    handle = kernel.OpenProcess(obs.PROCESS_VM_READ | obs.PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        raise obs.winerr("OpenProcess read-only failed")
    try:
        layout, table, pool = capture.snapshot(
            lambda address, length: obs.read(kernel, handle, address, length), base, obs)
    finally:
        obs.close(kernel, handle)

    records = capture.channel_a_records(layout, table, pool, obs)
    seen_wads: set[str] = set()
    target_record_status: list[dict] = []
    hits: dict[tuple[int, int], list[dict]] = {key: [] for key in target_keys}

    for record, payload in records:
        wad = normal_wad_name(record.get("name"))
        if wad:
            seen_wads.add(wad)
        if wad not in target_wads:
            continue
        status = {
            "record_index": record["index"],
            "wad": wad,
            "payload_bytes": len(payload),
            "cached_channel_a_lua_length": record["cached_channel_a_lua_length"],
            "payload_sha256": digest(payload) if payload else None,
            "carrier_count": 0,
            "state_entry_count": 0,
            "error": None,
        }
        if not payload:
            status["error"] = "target_wad_has_no_staged_payload"
            target_record_status.append(status)
            continue
        try:
            carriers = graph.carrier_with_tokens(
                payload, int(record["cached_channel_a_lua_length"]))
            status["carrier_count"] = len(carriers)
            for carrier_index, item in enumerate(carriers):
                entries = graph.extract_state_entries(item["raw"], item["decoded"], item["parsed"])
                status["state_entry_count"] += len(entries)
                for entry in entries:
                    parent = entry.get("parent", {}).get("gameobject")
                    if parent is None or entry.get("field_signature") != STATE_SIGNATURE:
                        continue
                    key = (int(parent["registry_hash_hex"], 16),
                           int(parent["object_hash_hex"], 16))
                    if key not in target_keys:
                        continue
                    hits[key].append({
                        "record_index": record["index"],
                        "wad": wad,
                        "carrier_index": carrier_index,
                        "alignment": item.get("alignment"),
                        "bit_offset": item.get("bit_offset"),
                        "subobj_table_row": entry.get("subobj_table_row"),
                        "state_row": entry.get("state_row"),
                        "state_raw_hex": entry["state"].get("raw_hex"),
                        "state_tag": entry["state"].get("tag"),
                        "state_scalar_bits": entry["state"].get("payload"),
                        "state_float": state_float(entry),
                    })
        except Exception as exc:
            status["error"] = f"{type(exc).__name__}: {exc}"
        target_record_status.append(status)

    result_rows = []
    for target in targets:
        key = (target["registry_hash"], target["object_hash"])
        matches = hits[key]
        values = sorted({m["state_float"] for m in matches if m["state_float"] is not None})
        result_rows.append({
            "number": target["number"],
            "catalogue_id": target["catalogue_id"],
            "wad": target["wad"],
            "registry_hash_hex": f"0x{target['registry_hash']:016X}",
            "object_hash_hex": f"0x{target['object_hash']:016X}",
            "serialized_flag1_hex": target["serialized_flag1_hex"],
            "wad_present_in_staged_table": normal_wad_name(target["wad"]) in seen_wads,
            "exact_state_match_count": len(matches),
            "state_values": values,
            "acquired_if_state_3": len(values) == 1 and values[0] == 3.0,
            "matches": matches,
            "authority": "live_staged_exact_key" if len(matches) == 1 else "unknown_fail_closed",
        })

    present_target_wads = sorted(target_wads & seen_wads)
    missing_target_wads = sorted(target_wads - seen_wads)
    exact_rows = sum(row["exact_state_match_count"] == 1 for row in result_rows)
    ambiguous_rows = sum(row["exact_state_match_count"] > 1 for row in result_rows)
    head08 = next(row for row in result_rows if row["number"] == 8)
    report = {
        "schema": 1,
        "analysis": "live_staged_wad_ship_head_state",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "process": {"pid": pid, "module_base": f"0x{base:X}", "exe_sha256": exe_sha},
        "snapshot": {
            "equal_reads": 2,
            "record_count": layout[2],
            "pool_size": layout[0],
            "table_sha256": digest(table),
            "pool_sha256": digest(pool),
            "matches_frozen_425_record_census": layout[2] == FROZEN_STAGED_RECORD_COUNT,
        },
        "scope": {
            "current_streamed_zone_not_required": True,
            "staged_wad_count": len(seen_wads),
            "target_wad_count": len(target_wads),
            "target_wads_present": present_target_wads,
            "target_wads_missing": missing_target_wads,
            "all_ship_head_wads_present": not missing_target_wads,
            "claim_limit": "Only WADs present in the native staged table are covered; missing target WADs remain unknown.",
        },
        "ship_heads": result_rows,
        "summary": {
            "physical_count": 9,
            "exact_state_rows": exact_rows,
            "ambiguous_state_rows": ambiguous_rows,
            "head08_exact_state_found": head08["exact_state_match_count"] == 1,
            "head08_state_values": head08["state_values"],
            "runtime_generation_allowed": False,
            "status": "EVIDENCE_ONLY_FAIL_CLOSED",
        },
        "target_record_status": target_record_status,
        "safety": {
            "open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "process_memory_written": False,
            "hook_installed": False,
            "debugger_attached": False,
            "save_opened_by_probe": False,
            "save_written_by_probe": False,
            "progression_written_by_probe": False,
        },
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "Live staged WAD Ship Head state",
        f"record_count={layout[2]} staged_wad_count={len(seen_wads)} target_wads_present={len(present_target_wads)}/{len(target_wads)}",
        f"all_ship_head_wads_present={str(not missing_target_wads).lower()} exact_state_rows={exact_rows}/9 ambiguous_rows={ambiguous_rows}",
        f"head08_exact_state_found={str(head08['exact_state_match_count'] == 1).lower()} head08_state_values={head08['state_values']}",
        "runtime_generation_allowed=false status=EVIDENCE_ONLY_FAIL_CLOSED",
    ]
    for row in result_rows:
        lines.append(
            f"HEAD {row['number']:02d} wad={row['wad']} object={row['object_hash_hex']} "
            f"wad_present={str(row['wad_present_in_staged_table']).lower()} matches={row['exact_state_match_count']} "
            f"states={row['state_values']} authority={row['authority']}"
        )
    if missing_target_wads:
        lines.append("MISSING_TARGET_WADS " + ",".join(missing_target_wads))
    lines.append("process_memory_written=false hook_installed=false save_written_by_probe=false")
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"SHIP_HEAD_STAGED_RUNTIME_CAPTURE_COMPLETE records={layout[2]} "
        f"target_wads={len(present_target_wads)}/{len(target_wads)} exact={exact_rows}/9 "
        f"head08={head08['exact_state_match_count']} production_ready=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
