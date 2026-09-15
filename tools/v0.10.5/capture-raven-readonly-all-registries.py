"""Read-only all-registry live probe for the canonical Alfheim Raven.

This probe deliberately avoids DebugActiveProcess, software breakpoints, thread
suspension, and process writes. It opens GoW.exe with QUERY_INFORMATION and
VM_READ only, enumerates every live GameObject registry bank, validates each
occupied bank slot against the GameObject's own token fields, and scores live
objects against exact canonical Raven evidence.

It is intentionally independent of the scheduler global-list root so a wrong
scheduler sentinel cannot suppress candidate discovery.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import importlib.util
import json
from pathlib import Path
import struct


BASE_SCRIPT = Path(__file__).with_name("capture-raven-readonly-registry.py")


def load_base():
    spec = importlib.util.spec_from_file_location("raven_readonly_registry_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def inspect_object_any_flavor(reader, obj: int, expected_registry: int, expected_slot: int,
                              payload: bytes, max_nodes: int = 24):
    root = reader.try_read(obj, 0x300)
    if root is None or len(root) < 0x288:
        return None
    flags = struct.unpack_from("<I", root, 0x278)[0]
    registry_id = struct.unpack_from("<I", root, 0x280)[0] & 0xFFFF
    slot = struct.unpack_from("<I", root, 0x284)[0] & 0xFFFFF
    flavor = (flags >> 3) & 1
    if registry_id != (expected_registry & 0xFFFF) or slot != expected_slot:
        return None

    labels: set[str] = set()
    hits: list[dict] = []
    queue: list[tuple[int, int]] = [(obj, 0)]
    seen: set[int] = set()
    nodes = 0
    while queue and nodes < max_nodes:
        address, depth = queue.pop(0)
        if address in seen:
            continue
        seen.add(address)
        size = 0x500 if depth else 0x300
        blob = reader.try_read(address, size)
        if blob is None:
            continue
        nodes += 1
        local = base.scan_blob(blob, payload)
        for label in sorted(local - labels):
            hits.append({"label": label, "address": f"0x{address:X}", "depth": depth})
        labels |= local
        if depth >= 2:
            continue
        pointer_region = blob[: min(len(blob), 0x300)]
        for off in range(0, len(pointer_region) - 7, 8):
            ptr = struct.unpack_from("<Q", pointer_region, off)[0]
            if base.plausible_ptr(ptr) and ptr not in seen:
                queue.append((ptr, depth + 1))
                if len(queue) + nodes >= max_nodes * 4:
                    break

    token = base.encode_token(registry_id, flavor, slot)
    return {
        "object": f"0x{obj:X}",
        "registry_id": registry_id,
        "flavor": flavor,
        "slot": slot,
        "token": token,
        "token_hex": f"0x{token:X}",
        "score": base.score_labels(labels, payload),
        "evidence": sorted(labels),
        "evidence_hits": hits,
        "graph_nodes_read": nodes,
    }


def inspect_registry(reader, row: dict, payload: bytes) -> dict:
    capacity = row["capacity"]
    bank = row["bank"]
    public = {
        "table_index": row["table_index"],
        "address": f"0x{row['address']:X}",
        "registry_id": row["registry_id"],
        "bank": f"0x{bank:X}",
        "cursor": row["cursor"],
        "live_count": row["live_count"],
        "capacity": capacity,
    }
    if capacity <= 1 or capacity > 0x10000 or not base.plausible_ptr(bank):
        public.update({"occupied_bank_slots": 0, "validated_objects": 0,
                       "scored_candidates": 0, "error": "invalid bank/capacity"})
        return {"summary": public, "candidates": []}
    raw = reader.try_read(bank, capacity * 8)
    if raw is None or len(raw) != capacity * 8:
        public.update({"occupied_bank_slots": 0, "validated_objects": 0,
                       "scored_candidates": 0, "error": "cannot read bank"})
        return {"summary": public, "candidates": []}

    occupied = 0
    validated = 0
    candidates = []
    flavor_counts = {0: 0, 1: 0}
    for slot in range(1, capacity):
        obj = struct.unpack_from("<Q", raw, slot * 8)[0]
        if not base.plausible_ptr(obj):
            continue
        occupied += 1
        item = inspect_object_any_flavor(reader, obj, row["registry_id"], slot, payload)
        if item is None:
            continue
        validated += 1
        flavor_counts[item["flavor"]] = flavor_counts.get(item["flavor"], 0) + 1
        if item["score"] > 0:
            candidates.append(item)
    candidates.sort(key=lambda x: (-x["score"], x["slot"]))
    public.update({
        "occupied_bank_slots": occupied,
        "validated_objects": validated,
        "flavor_0_objects": flavor_counts.get(0, 0),
        "flavor_1_objects": flavor_counts.get(1, 0),
        "scored_candidates": len(candidates),
    })
    return {"summary": public, "candidates": candidates}


def snapshot(pid: int, exe: Path, wad: Path) -> dict:
    if base.sha256_path(exe) != base.EXPECTED_EXE_SHA256:
        raise RuntimeError("GoW.exe SHA256 mismatch")
    payload = base.load_target_payload(wad)
    reader = base.Reader(pid)
    try:
        module_base, module_path = reader.module()
        if Path(module_path).resolve() != exe.resolve():
            raise RuntimeError(f"PID {pid} executable mismatch: {module_path}")

        registries = base.registry_rows(reader, module_base)
        all_candidates = []
        registry_summaries = []
        for row in registries:
            result = inspect_registry(reader, row, payload)
            registry_summaries.append(result["summary"])
            for candidate in result["candidates"]:
                all_candidates.append({**candidate, "table_index": row["table_index"]})
        all_candidates.sort(key=lambda x: (-x["score"], x["registry_id"], x["slot"]))

        # Keep scheduler traversal as diagnostic evidence only. Candidate discovery
        # does not depend on this path.
        try:
            outers = base.scheduler_outers(reader, module_base)
        except Exception:
            outers = []

        return {
            "schema": 2,
            "analysis": "gow_raven_readonly_all_registries",
            "pid": pid,
            "module_base": f"0x{module_base:X}",
            "module_path": module_path,
            "exe_sha256": base.EXPECTED_EXE_SHA256,
            "wad_sha256": base.EXPECTED_WAD_SHA256,
            "safety": {
                "debugger_attached": False,
                "breakpoints_installed": False,
                "process_writes": False,
                "thread_suspend_resume": False,
                "save_or_progression_writes": False,
                "access": "PROCESS_QUERY_INFORMATION|PROCESS_VM_READ",
            },
            "scheduler_outer_count_diagnostic_only": len(outers),
            "registry_table_live_entries": len(registries),
            "registry_summaries": registry_summaries,
            "validated_object_count": sum(x.get("validated_objects", 0) for x in registry_summaries),
            "candidate_count": len(all_candidates),
            "top_candidates": all_candidates[:50],
            "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
            "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        }
    finally:
        reader.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = snapshot(args.pid, args.exe, args.wad)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"READONLY_ALL_REGISTRIES_OK pid={args.pid}")
    print(f"registry_table_live_entries={report['registry_table_live_entries']}")
    print(f"validated_object_count={report['validated_object_count']}")
    print(f"candidate_count={report['candidate_count']}")
    for index, candidate in enumerate(report["top_candidates"][:10], 1):
        print(
            f"candidate_{index}=token={candidate['token_hex']} registry={candidate['registry_id']} "
            f"flavor={candidate['flavor']} slot={candidate['slot']} score={candidate['score']} "
            f"evidence={','.join(candidate['evidence'])}"
        )
    print("BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY")
    print("BLOCKED_EXACT_UNLOADED_STATE_ORACLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
