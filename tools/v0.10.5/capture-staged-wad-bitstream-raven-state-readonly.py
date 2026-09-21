#!/usr/bin/env python3
"""Read proven Channel A pool; archive bytes and decode bitstream candidates."""
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
import staged_wad_bitstream as bits

def normal_wad_name(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value).stem.lower() + ".wad"




def load_observer():
    spec = importlib.util.spec_from_file_location("staged_rpm", HERE / "capture-staged-wad-raven-state-readonly.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(read, base, obs):
    """Two equal bounded reads; reject changed table or payload bytes."""
    def header():
        size = obs.u32(read(base + obs.PAYLOAD_SIZE_RVA, 4))
        pointer = obs.u64(read(base + obs.PAYLOAD_BASE_RVA, 8))
        count = obs.u32(read(base + obs.RECORD_COUNT_RVA, 4))
        if not 0 < count <= obs.MAX_RECORDS:
            raise RuntimeError(f"invalid staged record count: {count}")
        if not 0 < size <= obs.MAX_POOL_SIZE:
            raise RuntimeError(f"invalid staged pool size: {size}")
        if not 0x10000 <= pointer < 0x0000800000000000 or pointer + size > 0x0000800000000000:
            raise RuntimeError("invalid staged pool pointer")
        return size, pointer, count

    before = header()
    size, pointer, count = before
    table_address = base + obs.RECORD_BASE_RVA
    table_size = count * obs.RECORD_STRIDE
    table = read(table_address, table_size)
    pool = read(pointer, size)
    if header() != before:
        raise RuntimeError("staged header changed; keep game paused and retry")
    table2 = read(table_address, table_size)
    pool2 = read(pointer, size)
    if table2 != table or pool2 != pool or header() != before:
        raise RuntimeError("staged snapshot changed; keep game paused and retry")
    return before, table, pool


def channel_a_records(layout, table, pool, obs):
    size, pointer, count = layout
    if len(table) != count * obs.RECORD_STRIDE or len(pool) != size:
        raise RuntimeError("snapshot lengths disagree")
    records = []
    for index in range(count):
        raw = table[index * obs.RECORD_STRIDE:(index + 1) * obs.RECORD_STRIDE]
        pa = obs.u64(raw, 0x30)
        cursor = obs.u64(raw, 0x38)
        length = obs.u32(raw, 0x40)
        slot = struct.unpack_from("<h", raw, 0x28)[0]
        lua_length = obs.u32(raw, 0x60)
        if slot < -1 or slot >= 64:
            raise RuntimeError(f"record {index}: invalid native slot {slot}")
        if lua_length > bits.MAX_CARRIER_BYTES:
            raise RuntimeError(f"record {index}: cached Channel A Lua length exceeds bounded inline capacity")
        record = {"index": index, "key_hex": f"0x{obs.u32(raw, 0x24):X}",
                  "flags_hex": f"0x{obs.u32(raw, 0x20):X}", "native_slot_index": slot,
                  "cached_channel_a_lua_length": lua_length,
                  "name": obs.printable_name(raw[0x84:0xA8]), "size": length,
                  "pointer": f"0x{pa:X}", "cursor": f"0x{cursor:X}",
                  "staged_record_hex": raw.hex()}
        if length:
            offset = pa - pointer
            if length > 0x10001 or offset < 0 or offset + length > size:
                raise RuntimeError(f"record {index}: Channel A outside pinned pool or u16 envelope cap")
            if not pa <= cursor <= pa + length:
                raise RuntimeError(f"record {index}: cursor outside Channel A")
            payload = pool[offset:offset + length]
        else:
            payload = b""
        records.append((record, payload))
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise RuntimeError("output folder must be empty")
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("64-bit Windows required")
    rows = json.loads((REPO / "catalogue/odins-ravens-gameobject-identities.json").read_text(encoding="utf-8"))["ravens"]
    object_map = {
        (int(row["registry_hash_hex"], 16), int(row["object_hash_hex"], 16)): row["catalogue_id"]
        for row in rows
    }
    if len(rows) != 53 or len(object_map) != 53 or len(set(object_map.values())) != 53:
        raise RuntimeError("expected 53 unique Raven (registry, object) identities")
    registry = None
    obs = load_observer()
    kernel = obs.k32_api()
    pid, name = obs.find_process(kernel)
    base, exe = obs.main_module(kernel, pid, name)
    exe_sha = obs.sha256_file(Path(exe))
    if exe_sha != obs.EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")
    handle = kernel.OpenProcess(obs.PROCESS_VM_READ | obs.PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        raise obs.winerr("OpenProcess read-only failed")
    try:
        layout, table, pool = snapshot(lambda address, length: obs.read(kernel, handle, address, length), base, obs)
    finally:
        obs.close(kernel, handle)
    records = channel_a_records(layout, table, pool, obs)
    payload_dir = out / "channel-a"
    payload_dir.mkdir()
    states = {row["catalogue_id"]: set() for row in rows}
    blocked_ids = set()
    report_records = []
    staged_wads = set()
    for record, payload in records:
        wad_name = normal_wad_name(record.get("name"))
        if wad_name:
            staged_wads.add(wad_name)
        if not payload:
            record["status"] = "no_staged_payload_unknown"
            report_records.append(record)
            continue
        relative = f"channel-a/{record['index']:04d}.bin"
        (out / relative).write_bytes(payload)
        record["payload_file"] = relative
        record["sha256"] = digest(payload)
        decoded = bits.extract_channel_a(
            payload, registry, object_map,
            expected_lua_length=record["cached_channel_a_lua_length"],
        )
        record["decode"] = decoded
        for rid, state in decoded["raven_states"].items():
            if state is not None:
                states[rid].add(state)
        if decoded.get("ambiguity_reasons"):
            for candidate in decoded.get("candidates", []):
                for entry in candidate.get("raven_entries", []):
                    blocked_ids.add(entry["catalogue_id"])
        report_records.append(record)
    result_states = []
    for row in rows:
        rid = row["catalogue_id"]
        values = states[rid]
        conflict = len(values) > 1
        ambiguous = rid in blocked_ids
        row_wad = normal_wad_name(row.get("wad"))
        if len(values) == 1 and not ambiguous:
            value = next(iter(values))
            authority = "explicit_ravenKilled_from_staged_channel_a"
        elif not conflict and not ambiguous and row_wad not in staged_wads:
            value = False
            authority = "native_absent_wad_default_false"
        else:
            value = None
            authority = "unknown_fail_closed"
        result_states.append({
            "catalogue_id": rid,
            "candidate_ravenKilled": value,
            "conflict": conflict,
            "ambiguous": ambiguous,
            "authority": authority,
            "region": row.get("region"),
            "wad": row.get("wad"),
        })
    report = {"schema": 1, "analysis": "staged_wad_bitstream_raven_candidates",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "process": {"pid": pid, "module_base": f"0x{base:X}", "exe_sha256": exe_sha},
              "snapshot": {"equal_reads": 2, "atomic": False, "pool_size": layout[0],
                           "record_count": layout[2], "table_sha256": digest(table), "pool_sha256": digest(pool)},
              "records": report_records, "raven_states": result_states,
              "staged_wad_count": len(staged_wads),
              "absence_default_false_count": sum(
                  row["authority"] == "native_absent_wad_default_false" for row in result_states
              ),
              "production_ready": False,
              "remaining_gate": "Integrate complete 53-Raven authority into runtime map path and validate acceptance fixtures.",
              "safety": {"open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                         "game_launched": False, "process_memory_written": False, "save_opened": False,
                         "save_written": False, "progression_written": False, "debugger_attached": False}}
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    known = [row for row in result_states if row["candidate_ravenKilled"] is not None]
    lines = ["Staged Channel A bitstream Raven candidates", f"record_count={layout[2]} pool_size={layout[0]}",
             f"candidate_state_count={len(known)} unknown_count={53 - len(known)} "
             f"absence_default_false_count={sum(row['authority']=='native_absent_wad_default_false' for row in result_states)} "
             "production_ready=false",
             "Equal reads passed. Absent-WAD false uses proven native staged-record retention semantics; runtime integration remains pending."]
    for record in report_records:
        if "decode" in record:
            decoded = record["decode"]
            lines.append(f"record={record['index']} name={record['name']!r} slot={record['native_slot_index']} "
                         f"bytes={record['size']} luaBytes={record['cached_channel_a_lua_length']} "
                         f"candidates={len(decoded['candidates'])} "
                         f"ambiguity={decoded.get('ambiguity_reasons', [])}")
    for row in known:
        lines.append(
            f"CANDIDATE {row['catalogue_id']} ravenKilled={row['candidate_ravenKilled']} "
            f"region={row['region']} wad={row.get('wad')} authority={row['authority']}"
        )
    lines.append("process_memory_written=false save_opened=false save_written=false progression_written=false")
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"STAGED_BITSTREAM_CAPTURE_COMPLETE records={layout[2]} candidate_states={len(known)} production_ready=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
