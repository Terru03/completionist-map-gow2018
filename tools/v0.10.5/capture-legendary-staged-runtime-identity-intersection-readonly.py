#!/usr/bin/env python3
"""Intersect resident native GameObject identities with staged Legendary state hashes.

Read-only diagnostic. Reuses the already-proven registry-238 identity builder and
compares each resident native identity hash directly with the archived staged-WAD
parents having the exact dominant schema {state=<tag1 scalar>}.

No debugger, game-code call, process write, save read/write, progression write,
or game-file write.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / "capture-legendary-chest-gameobject-identities-readonly.py"
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


native = load_module("_legendary_native_identity_intersection", CAPTURE)
identity = native.identity


def build_staged_oracle(staged: dict):
    by_hash = defaultdict(list)
    total = 0
    for wad in staged.get("wads", []):
        wad_name = str(wad.get("wad") or "").lower()
        if not wad_name or not wad.get("capture_present"):
            continue
        for entry in wad.get("state_entries", []):
            if (entry.get("field_signature") or []) != SIMPLE_SIGNATURE:
                continue
            parent = entry.get("parent") or {}
            if parent.get("record_class_key_hex") != SIMPLE_CLASS:
                continue
            go = parent.get("gameobject") or {}
            object_hash_hex = go.get("object_hash_hex")
            registry_hash_hex = go.get("registry_hash_hex")
            if not object_hash_hex or not registry_hash_hex:
                continue
            total += 1
            by_hash[int(object_hash_hex, 16)].append({
                "wad": wad_name,
                "staged_name": wad.get("staged_name"),
                "staged_index": wad.get("staged_index"),
                "registry_hash_hex": registry_hash_hex,
                "object_hash_hex": object_hash_hex,
                "state_raw_hex": entry["state"]["raw_hex"],
                "state_u32": entry["state"]["decoded"],
                "state_row": entry.get("state_row"),
                "subobj_table_row": entry.get("subobj_table_row"),
            })
    if total != 206:
        raise RuntimeError(f"expected 206 dominant staged parents, got {total}")
    return by_hash, total


def build_catalogue_element_index(catalogue: dict):
    rows = identity.tracked_rows(catalogue)
    if len(rows) != identity.EXPECTED_TRACKED:
        raise RuntimeError(
            f"expected {identity.EXPECTED_TRACKED} tracked Legendary rows, got {len(rows)}"
        )
    index = defaultdict(list)
    for row in rows:
        for chain_index, item in enumerate(row["source"]["transform_chain"]):
            raw_hex = item["record_id"].lower()
            adjusted_hex = identity.adjusted_record_id(raw_hex).hex()
            for mode, value_hex in (
                ("raw_record_id", raw_hex),
                ("adjusted_identity", adjusted_hex),
            ):
                index[value_hex].append({
                    "catalogue_id": row["catalogue_id"],
                    "wad": row["source"]["wad"],
                    "chain_index": chain_index,
                    "record_name": item["name"],
                    "mode": mode,
                })
    return rows, index


def sweep(k, process, base, registry, staged_oracle, element_index):
    count = registry["count"]
    array = registry["array_ptr"]
    raw = native.read(k, process, array, count * 8) if count else b""
    objects = struct.unpack(f"<{count}Q", raw) if count else ()
    expected_method = base + native.IDENTITY_METHOD_RVA
    stats = {
        "non_null": 0,
        "identity_method": 0,
        "built": 0,
        "build_failures": 0,
        "staged_hash_hits": 0,
    }
    hits = []

    for slot, obj in enumerate(objects):
        if not obj:
            continue
        stats["non_null"] += 1
        vtable_raw = native.safe_read(k, process, obj, 8)
        if vtable_raw is None:
            continue
        vtable = struct.unpack("<Q", vtable_raw)[0]
        method_raw = native.safe_read(k, process, vtable + 0x38, 8)
        if (
            method_raw is None
            or struct.unpack("<Q", method_raw)[0] != expected_method
        ):
            continue
        stats["identity_method"] += 1

        reader = native.Reader(k, process)
        try:
            elements, builder = native.build_identity(reader, obj)
            stats["built"] += 1
        except Exception:
            stats["build_failures"] += 1
            continue

        object_hash = identity.identity_hash(elements)
        staged_matches = staged_oracle.get(object_hash)
        if not staged_matches:
            continue

        stats["staged_hash_hits"] += 1
        element_hex = [item.hex() for item in elements]
        overlaps = []
        catalogue_scores = defaultdict(int)
        for position, value_hex in enumerate(element_hex):
            for match in element_index.get(value_hex, []):
                overlaps.append({
                    "position": position,
                    "element_hex": value_hex,
                    **match,
                })
                catalogue_scores[match["catalogue_id"]] += 1

        ranked_catalogue_overlap = [
            {"catalogue_id": cid, "overlap_count": score}
            for cid, score in sorted(
                catalogue_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

        hits.append({
            "runtime_registry": native.REGISTRY_ID,
            "slot": slot,
            "runtime_token_hex": (
                f"0x{(1 | (native.REGISTRY_ID << 1) | (slot << 18)):016X}"
            ),
            "object_ptr": f"0x{obj:X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "identity_elements_hex": element_hex,
            "identity_element_count": len(elements),
            "builder": builder,
            "read_process_memory_calls": reader.read_count,
            "staged_matches": staged_matches,
            "catalogue_element_overlaps": overlaps,
            "ranked_catalogue_overlap": ranked_catalogue_overlap[:16],
        })

    return stats, hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-root",
        type=Path,
        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"),
    )
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--staged-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    if sys.platform != "win32":
        raise RuntimeError("64-bit Windows required")

    game_root = args.game_root.resolve()
    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    staged = json.loads(args.staged_report.read_text(encoding="utf-8"))
    staged_oracle, staged_total = build_staged_oracle(staged)
    rows, element_index = build_catalogue_element_index(catalogue)

    k = native.k32_api()
    pid, name = native.find_process(k)
    base, size, exe = native.main_module(k, pid, name)
    exe_sha = native.sha256_file(exe)
    if exe_sha.lower() != native.EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    process = k.OpenProcess(
        native.PROCESS_VM_READ | native.PROCESS_QUERY_INFORMATION,
        False,
        pid,
    )
    if not process:
        raise native.winerr("OpenProcess read-only failed")
    try:
        registry = native.find_registry(k, process, base)
        stats, hits = sweep(
            k,
            process,
            base,
            registry,
            staged_oracle,
            element_index,
        )
    finally:
        native.close(k, process)

    unique_runtime_hashes = sorted({row["object_hash_hex"] for row in hits})
    represented_wads = sorted({
        staged_match["wad"]
        for row in hits
        for staged_match in row["staged_matches"]
    })
    overlap_hits = [
        row for row in hits if row["catalogue_element_overlaps"]
    ]

    report = {
        "schema": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "analysis": "legendary_staged_runtime_identity_intersection",
        "result": (
            "STAGED_RUNTIME_IDENTITY_INTERSECTION_FOUND"
            if hits else
            "NO_STAGED_RUNTIME_IDENTITY_INTERSECTION"
        ),
        "process": {
            "pid": pid,
            "exe_name": name,
            "module_base": f"0x{base:X}",
            "module_size": size,
            "exe_sha256": exe_sha,
        },
        "staged_oracle": {
            "dominant_parent_count": staged_total,
            "unique_object_hashes": len(staged_oracle),
            "class_key_hex": SIMPLE_CLASS,
            "tracked_rows": len(rows),
        },
        "registry": {
            "id": native.REGISTRY_ID,
            "count": registry["count"],
            **stats,
        },
        "hit_count": len(hits),
        "unique_runtime_hash_count": len(unique_runtime_hashes),
        "represented_wads": represented_wads,
        "catalogue_overlap_hit_count": len(overlap_hits),
        "hits": hits,
        "safety": {
            "open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "debugger_attached": False,
            "remote_game_code_called": False,
            "process_memory_written": False,
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
        "Completionist Map - Legendary staged/runtime identity intersection",
        f"result={report['result']}",
        (
            f"registry={native.REGISTRY_ID} count={registry['count']} "
            f"non_null={stats['non_null']} identity_method={stats['identity_method']} "
            f"built={stats['built']} failures={stats['build_failures']}"
        ),
        (
            f"staged_parents={staged_total} hits={len(hits)} "
            f"unique_runtime_hashes={len(unique_runtime_hashes)} "
            f"catalogue_overlap_hits={len(overlap_hits)}"
        ),
        "represented_wads=" + (",".join(represented_wads) if represented_wads else "-"),
        "",
        "HITS",
    ]
    for row in hits:
        staged_names = ",".join(
            f"{item['wad']}:{item['state_raw_hex']}"
            for item in row["staged_matches"]
        )
        lines.append(
            f"slot={row['slot']} hash={row['object_hash_hex']} "
            f"elements={row['identity_element_count']} staged={staged_names} "
            f"catalogue_overlaps={len(row['catalogue_element_overlaps'])}"
        )
    lines += [
        "",
        "SAFETY",
        "OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
        "process_memory_written=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "LEGENDARY_STAGED_RUNTIME_INTERSECTION_COMPLETE "
        f"hits={len(hits)} represented_wads={len(represented_wads)} "
        f"catalogue_overlap_hits={len(overlap_hits)}"
    )
    print(
        "process_memory_written=false active_save_opened=false "
        "save_or_progression_written=false raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
