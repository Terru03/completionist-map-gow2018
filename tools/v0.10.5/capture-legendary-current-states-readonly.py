#!/usr/bin/env python3
"""Capture exact current states for the 33 tracked Legendary Chests.

Read-only live diagnostic:
- snapshots the proven staged-WAD Channel A table/pool with two equal reads;
- derives all 33 exact serialized Legendary identities from the accepted
  structural rule;
- decodes tracked WAD carriers only;
- reports only exact GameObject parent hashes belonging to those 33 identities.

No debugger, process write, save read/write, progression write, game-file write,
or Raven runtime modification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CAPTURE_PATH = HERE / "capture-staged-wad-bitstream-raven-state-readonly.py"
ANALYZE_PATH = HERE / "analyze-legendary-staged-state.py"
IDENTITY_PATH = HERE / "legendary_chest_identity.py"
SIMPLE_SIGNATURE = [{"name": "state", "value_tag": 1}]
SIMPLE_CLASS = "0x75E050AB149B4062"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


capture = load_module("_legendary_live_stage_capture", CAPTURE_PATH)
analyze = load_module("_legendary_live_stage_analyze", ANALYZE_PATH)
identity = load_module("_legendary_live_identity", IDENTITY_PATH)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def norm_wad(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value).stem.lower() + ".wad"


def derived_identities(catalogue: dict) -> tuple[list[dict], dict[tuple[int, int], dict]]:
    rows = identity.tracked_rows(catalogue)
    if len(rows) != 33:
        raise RuntimeError(f"expected 33 tracked Legendary rows, got {len(rows)}")

    out = []
    by_pair = {}
    for row in rows:
        scene, skipped = identity.scene_identity_elements(row)
        elements = scene + [identity.CHEST_OWN_IDENTITY_ELEMENT]
        registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
        object_hash = identity.identity_hash(elements)
        pair = (registry_hash, object_hash)
        if pair in by_pair:
            raise RuntimeError("derived Legendary serialized identity collision")
        item = {
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "registry_hash_hex": f"0x{registry_hash:016X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "serialized_flag1_hex": identity.serialized_payload(
                registry_hash, object_hash
            ).hex(),
            "scene_identity_elements_hex": [x.hex() for x in scene],
            "own_identity_element_hex": identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
            "skipped_transform_nodes": skipped,
        }
        out.append(item)
        by_pair[pair] = item
    return out, by_pair


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise RuntimeError("output folder must be empty")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    identities, identity_map = derived_identities(catalogue)
    tracked_wads = {row["wad"].lower() for row in identities}

    obs = capture.load_observer()
    kernel = obs.k32_api()
    pid, name = obs.find_process(kernel)
    base, exe = obs.main_module(kernel, pid, name)
    exe_sha = obs.sha256_file(Path(exe))
    if exe_sha != obs.EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    handle = kernel.OpenProcess(
        obs.PROCESS_VM_READ | obs.PROCESS_QUERY_INFORMATION,
        False,
        pid,
    )
    if not handle:
        raise obs.winerr("OpenProcess read-only failed")
    try:
        layout, table, pool = capture.snapshot(
            lambda address, length: obs.read(kernel, handle, address, length),
            base,
            obs,
        )
    finally:
        obs.close(kernel, handle)

    records = capture.channel_a_records(layout, table, pool, obs)
    payload_dir = out_dir / "tracked-channel-a"
    payload_dir.mkdir()

    observed: dict[str, list[dict]] = {
        row["catalogue_id"]: [] for row in identities
    }
    record_reports = []

    for record, payload in records:
        wad_name = norm_wad(record.get("name"))
        if wad_name not in tracked_wads:
            continue

        rec_report = {
            "index": record["index"],
            "name": record.get("name"),
            "wad": wad_name,
            "size": record["size"],
            "cached_channel_a_lua_length": record[
                "cached_channel_a_lua_length"
            ],
            "native_slot_index": record["native_slot_index"],
        }

        if not payload:
            rec_report["status"] = "tracked_wad_no_payload"
            record_reports.append(rec_report)
            continue

        relative = f"tracked-channel-a/{record['index']:04d}-{wad_name}.bin"
        (out_dir / relative).write_bytes(payload)
        rec_report["payload_file"] = relative
        rec_report["payload_sha256"] = sha256(payload)

        candidates = analyze.carrier_with_tokens(
            payload,
            int(record["cached_channel_a_lua_length"]),
        )
        rec_report["carrier_candidate_count"] = len(candidates)
        if len(candidates) != 1:
            rec_report["status"] = "carrier_not_uniquely_decoded"
            record_reports.append(rec_report)
            continue

        candidate = candidates[0]
        entries = analyze.extract_state_entries(
            candidate["raw"],
            candidate["decoded"],
            candidate["parsed"],
        )
        rec_report["state_entry_count"] = len(entries)
        exact_hits = []

        for entry in entries:
            if (entry.get("field_signature") or []) != SIMPLE_SIGNATURE:
                continue
            parent = entry.get("parent") or {}
            if parent.get("record_class_key_hex") != SIMPLE_CLASS:
                continue
            go = parent.get("gameobject") or {}
            if not go:
                continue
            pair = (
                int(go["registry_hash_hex"], 16),
                int(go["object_hash_hex"], 16),
            )
            known = identity_map.get(pair)
            if known is None:
                continue

            hit = {
                "catalogue_id": known["catalogue_id"],
                "wad": known["wad"],
                "registry_hash_hex": go["registry_hash_hex"],
                "object_hash_hex": go["object_hash_hex"],
                "state_raw_hex": entry["state"]["raw_hex"],
                "state_u32": entry["state"]["decoded"],
                "state_kind": entry["state"]["kind"],
                "state_row": entry.get("state_row"),
                "subobj_table_row": entry.get("subobj_table_row"),
                "source_record_index": record["index"],
            }
            observed[known["catalogue_id"]].append(hit)
            exact_hits.append(hit)

        rec_report["exact_legendary_hits"] = exact_hits
        rec_report["status"] = "decoded"
        record_reports.append(rec_report)

    states = []
    conflicts = []
    present_count = 0
    for known in identities:
        cid = known["catalogue_id"]
        hits = observed[cid]
        distinct = {
            (hit["state_raw_hex"], int(hit["state_u32"]))
            for hit in hits
        }
        conflict = len(distinct) > 1
        if conflict:
            conflicts.append(cid)
        if len(distinct) == 1:
            raw_hex, state_u32 = next(iter(distinct))
            present_count += 1
            state = {
                "present": True,
                "state_raw_hex": raw_hex,
                "state_u32": state_u32,
                "occurrence_count": len(hits),
                "hits": hits,
            }
        else:
            state = {
                "present": False if not hits else None,
                "state_raw_hex": None,
                "state_u32": None,
                "occurrence_count": len(hits),
                "hits": hits,
            }
        states.append({
            **known,
            **state,
            "conflict": conflict,
        })

    if conflicts:
        raise RuntimeError(
            "conflicting exact Legendary state values: " + ",".join(conflicts)
        )

    report = {
        "schema": 1,
        "analysis": "legendary_current_exact_states_readonly",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "process": {
            "pid": pid,
            "exe_name": name,
            "module_base": f"0x{base:X}",
            "exe_sha256": exe_sha,
        },
        "snapshot": {
            "equal_reads": 2,
            "pool_size": layout[0],
            "record_count": layout[2],
            "table_sha256": sha256(table),
            "pool_sha256": sha256(pool),
        },
        "tracked_identity_count": len(identities),
        "present_exact_state_count": present_count,
        "conflict_count": len(conflicts),
        "records": record_reports,
        "states": states,
        "safety": {
            "open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "debugger_attached": False,
            "process_memory_written": False,
            "active_save_opened": False,
            "save_written_by_tooling": False,
            "progression_written_by_tooling": False,
            "game_files_written": False,
            "raven_runtime_modified": False,
        },
    }

    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "Completionist Map - Legendary current exact states",
        (
            f"tracked=33 present_exact={present_count} "
            f"staged_records={layout[2]} conflicts={len(conflicts)}"
        ),
        "",
        "EXACT STATES",
    ]
    for row in states:
        if row["present"] is True:
            lines.append(
                f"{row['catalogue_id']} wad={row['wad']} "
                f"object_hash={row['object_hash_hex']} "
                f"state_u32={row['state_u32']} "
                f"state_raw={row['state_raw_hex']}"
            )
    lines += [
        "",
        "SAFETY",
        "OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
        "process_memory_written=false",
        "active_save_opened=false",
        "save_written_by_tooling=false",
        "progression_written_by_tooling=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    (out_dir / "report.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "LEGENDARY_CURRENT_STATE_CAPTURE_COMPLETE "
        f"present={present_count}/33 records={layout[2]}"
    )
    print(
        "process_memory_written=false active_save_opened=false "
        "save_written_by_tooling=false progression_written_by_tooling=false "
        "raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
