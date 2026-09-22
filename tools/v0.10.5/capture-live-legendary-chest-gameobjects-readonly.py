#!/usr/bin/env python3
"""Capture exact live GameObject IDs for tracked Legendary Chests.

Read-only runtime proof:
- resolves the live WAD->registry mapping from the proved WAD-context table;
- derives all 33 accepted Legendary serialized object hashes from the catalogue;
- sweeps only currently resident tracked Legendary WAD registries;
- records exact registry/slot/token/object pointer/identity vectors for matches.

No debugger, game-code call, process write, save read/write, progression write,
game-file write, or Raven runtime modification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import json
import ntpath
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
NATIVE_PATH = HERE / "capture-legendary-chest-gameobject-identities-readonly.py"
CONTEXT_PATH = HERE / "capture-raven-readonly-registry.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


native = load_module("_live_legendary_native", NATIVE_PATH)
context_base = load_module("_live_legendary_context", CONTEXT_PATH)
identity = native.identity


def normalize_wad_name(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().replace("/", "\")
    if not text:
        return None
    name = ntpath.basename(text).lower()
    marker = name.find(".wad")
    if marker >= 0:
        return name[:marker + 4]
    return name + ".wad"


def derive_expected(catalogue: dict):
    rows = identity.tracked_rows(catalogue)
    if len(rows) != 33:
        raise RuntimeError(f"expected 33 tracked Legendary rows, got {len(rows)}")

    by_wad: dict[str, dict[int, dict]] = defaultdict(dict)
    all_rows = []
    for row in rows:
        scene, skipped = identity.scene_identity_elements(row)
        elements = scene + [identity.CHEST_OWN_IDENTITY_ELEMENT]
        object_hash = identity.identity_hash(elements)
        registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
        wad = row["source"]["wad"].lower()
        if object_hash in by_wad[wad]:
            raise RuntimeError(f"{wad}: duplicate derived object hash")
        item = {
            "catalogue_id": row["catalogue_id"],
            "realm": row.get("realm"),
            "region": row.get("region"),
            "wad": row["source"]["wad"],
            "registry_hash_hex": f"0x{registry_hash:016X}",
            "object_hash_hex": f"0x{object_hash:016X}",
            "serialized_flag1_hex": identity.serialized_payload(
                registry_hash, object_hash
            ).hex(),
            "identity_elements_hex": [x.hex() for x in elements],
            "scene_identity_elements_hex": [x.hex() for x in scene],
            "own_identity_element_hex": identity.CHEST_OWN_IDENTITY_ELEMENT.hex(),
            "skipped_transform_nodes": skipped,
            "world_position": row.get("marker", {}).get("position_world"),
            "marker_name": row.get("marker", {}).get("name"),
        }
        by_wad[wad][object_hash] = item
        all_rows.append(item)
    return rows, all_rows, by_wad


def find_registry(k, process, base: int, registry_id: int) -> dict:
    matches = []
    for entry in range(base + native.TABLE_BEGIN, base + native.TABLE_END, 8):
        raw = native.safe_read(k, process, entry, 8)
        if raw is None:
            continue
        descriptor = struct.unpack("<Q", raw)[0]
        if not descriptor:
            continue
        rid = native.safe_read(k, process, descriptor, 4)
        if rid is None or struct.unpack("<I", rid)[0] != registry_id:
            continue
        head = native.read(k, process, descriptor + 8, 0x18)
        array = struct.unpack_from("<Q", head, 0)[0]
        count = struct.unpack_from("<I", head, 0x10)[0]
        matches.append((descriptor, entry, array, count))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one registry {registry_id}, found {len(matches)}"
        )
    descriptor, entry, array, count = matches[0]
    if count > 1048576:
        raise RuntimeError(f"implausible registry {registry_id} count {count}")
    return {
        "id": registry_id,
        "descriptor": descriptor,
        "table_entry": entry,
        "array_ptr": array,
        "count": count,
    }


def live_contexts(pid: int, exe: Path, tracked_wads: set[str]):
    reader = context_base.Reader(pid)
    try:
        base, module_path = reader.module()
        if Path(module_path).resolve() != exe.resolve():
            raise RuntimeError(f"PID {pid} executable mismatch: {module_path}")
        contexts = context_base.wad_contexts(reader, base)
    finally:
        reader.close()

    matched = []
    for row in contexts:
        wad = normalize_wad_name(row.get("wad_name"))
        if not wad or wad not in tracked_wads:
            continue
        registry_id = row.get("registry_id")
        if registry_id is None:
            continue
        matched.append({
            **row,
            "normalized_wad_name": wad,
        })
    return contexts, matched


def sweep_registry(k, process, base, registry, wad, expected):
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
        "exact_chest_hits": 0,
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
        known = expected.get(object_hash)
        if known is None:
            continue

        # Exact vector equality is stronger than hash equality and is required.
        element_hex = [x.hex() for x in elements]
        if element_hex != known["identity_elements_hex"]:
            continue

        registry_id = registry["id"]
        stats["exact_chest_hits"] += 1
        hits.append({
            **known,
            "live_wad": wad,
            "runtime_registry": registry_id,
            "runtime_slot": slot,
            "runtime_token_hex": (
                f"0x{(1 | (registry_id << 1) | (slot << 18)):016X}"
            ),
            "object_ptr": f"0x{obj:X}",
            "identity_elements_live_hex": element_hex,
            "identity_element_count": len(elements),
            "builder": builder,
            "read_process_memory_calls": reader.read_count,
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
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    if sys.platform != "win32":
        raise RuntimeError("64-bit Windows required")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    _, expected_rows, expected_by_wad = derive_expected(catalogue)
    tracked_wads = set(expected_by_wad)

    k = native.k32_api()
    pid, name = native.find_process(k)
    base, size, exe_text = native.main_module(k, pid, name)
    exe = Path(exe_text).resolve()
    exe_sha = native.sha256_file(exe)
    if exe_sha.lower() != native.EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    all_contexts, tracked_contexts = live_contexts(
        pid, exe, tracked_wads
    )

    live_pairs = []
    seen = set()
    for row in tracked_contexts:
        pair = (
            row["normalized_wad_name"],
            int(row["registry_id"]),
        )
        if pair in seen:
            continue
        seen.add(pair)
        live_pairs.append({
            "wad": pair[0],
            "registry_id": pair[1],
            "context_index": row["context_index"],
        })

    process = k.OpenProcess(
        native.PROCESS_VM_READ | native.PROCESS_QUERY_INFORMATION,
        False,
        pid,
    )
    if not process:
        raise native.winerr("OpenProcess read-only failed")

    registry_reports = []
    hits = []
    try:
        for live in live_pairs:
            wad = live["wad"]
            registry = find_registry(
                k, process, base, live["registry_id"]
            )
            stats, chest_hits = sweep_registry(
                k,
                process,
                base,
                registry,
                wad,
                expected_by_wad[wad],
            )
            registry_reports.append({
                **live,
                "registry_count": registry["count"],
                "expected_chest_count_in_wad": len(expected_by_wad[wad]),
                **stats,
                "hit_count": len(chest_hits),
            })
            hits.extend(chest_hits)
    finally:
        native.close(k, process)

    mountain_hits = [
        row for row in hits
        if str(row.get("region") or "").lower() in {
            "peakspass",
            "mountain",
        }
        or str(row.get("wad") or "").lower().startswith("peak")
    ]

    expected_live_catalogue_ids = sorted({
        item["catalogue_id"]
        for live in live_pairs
        for item in expected_by_wad[live["wad"]].values()
    })
    exact_live_catalogue_ids = sorted({
        row["catalogue_id"] for row in hits
    })

    report = {
        "schema": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "analysis": "live_exact_legendary_chest_gameobjects",
        "result": (
            "LIVE_LEGENDARY_CHEST_GAMEOBJECTS_FOUND"
            if hits else
            "NO_EXACT_TRACKED_LEGENDARY_CHEST_GAMEOBJECTS_RESIDENT"
        ),
        "process": {
            "pid": pid,
            "exe_name": name,
            "module_base": f"0x{base:X}",
            "module_size": size,
            "exe_sha256": exe_sha,
        },
        "tracked_catalogue_count": len(expected_rows),
        "tracked_wad_count": len(tracked_wads),
        "live_context_count": len(all_contexts),
        "tracked_live_context_count": len(tracked_contexts),
        "tracked_live_wad_registry_pairs": live_pairs,
        "registry_reports": registry_reports,
        "expected_catalogue_ids_in_live_tracked_wads": expected_live_catalogue_ids,
        "exact_live_catalogue_ids": exact_live_catalogue_ids,
        "exact_live_chest_count": len(hits),
        "mountain_exact_live_chest_count": len(mountain_hits),
        "mountain_hits": mountain_hits,
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
        "Completionist Map - live exact Legendary Chest GameObjects",
        f"result={report['result']}",
        (
            f"tracked_live_wads={len(live_pairs)} "
            f"exact_live_chests={len(hits)} "
            f"mountain_exact_live_chests={len(mountain_hits)}"
        ),
        "",
        "LIVE TRACKED WADS",
    ]
    for row in registry_reports:
        lines.append(
            f"wad={row['wad']} registry={row['registry_id']} "
            f"count={row['registry_count']} expected_chests={row['expected_chest_count_in_wad']} "
            f"built={row['built']} exact_hits={row['hit_count']}"
        )

    lines += ["", "EXACT LIVE CHESTS"]
    for row in hits:
        lines.append(
            f"{row['catalogue_id']} region={row.get('region')} wad={row['wad']} "
            f"registry={row['runtime_registry']} slot={row['runtime_slot']} "
            f"token={row['runtime_token_hex']} object={row['object_ptr']} "
            f"hash={row['object_hash_hex']}"
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
    args.output_text.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "LIVE_LEGENDARY_GAMEOBJECT_CAPTURE_COMPLETE "
        f"tracked_live_wads={len(live_pairs)} exact_hits={len(hits)} "
        f"mountain_hits={len(mountain_hits)}"
    )
    for row in mountain_hits:
        print(
            "MOUNTAIN_CHEST "
            f"id={row['catalogue_id']} wad={row['wad']} "
            f"registry={row['runtime_registry']} slot={row['runtime_slot']} "
            f"token={row['runtime_token_hex']} object={row['object_ptr']} "
            f"hash={row['object_hash_hex']}"
        )
    print(
        "process_memory_written=false save_or_progression_written=false "
        "raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
