#!/usr/bin/env python3
"""Intersect live tracked Legendary WAD registries with staged state hashes.

Read-only diagnostic. It resolves the actual live WAD -> registry mapping from
GoW's proved 64-slot WAD-context table, then reconstructs native GameObject
identity hashes only inside the registries belonging to currently resident
tracked Legendary WADs.

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


native = load_module("_legendary_native_identity_intersection", NATIVE_PATH)
context_base = load_module("_legendary_live_context_intersection", CONTEXT_PATH)
identity = native.identity


def normalize_wad_name(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().replace("/", "\\")
    if not text:
        return None
    name = ntpath.basename(text).lower()
    if not name:
        return None
    marker = name.find(".wad")
    if marker >= 0:
        return name[:marker + 4]
    return name + ".wad"


def tracked_rows(catalogue: dict) -> list[dict]:
    rows = identity.tracked_rows(catalogue)
    if len(rows) != identity.EXPECTED_TRACKED:
        raise RuntimeError(
            f"expected {identity.EXPECTED_TRACKED} tracked Legendary rows, got {len(rows)}"
        )
    return rows


def build_staged_oracle(staged: dict):
    by_wad: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
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
            by_wad[wad_name][int(object_hash_hex, 16)].append({
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
    return by_wad, total


def build_catalogue_element_index(rows: list[dict]):
    index = defaultdict(list)
    by_wad = defaultdict(list)
    for row in rows:
        wad_name = row["source"]["wad"].lower()
        by_wad[wad_name].append(row["catalogue_id"])
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
    if len(by_wad) != 27:
        raise RuntimeError(f"expected 27 tracked Legendary WADs, got {len(by_wad)}")
    return index, by_wad


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


def live_tracked_contexts(pid: int, exe: Path, tracked_by_wad: dict[str, list[str]]):
    reader = context_base.Reader(pid)
    try:
        base, module_path = reader.module()
        if Path(module_path).resolve() != exe.resolve():
            raise RuntimeError(f"PID {pid} executable mismatch: {module_path}")
        contexts = context_base.wad_contexts(reader, base)
    finally:
        reader.close()

    matches = []
    for row in contexts:
        normalized = normalize_wad_name(row.get("wad_name"))
        if not normalized or normalized not in tracked_by_wad:
            continue
        registry_id = row.get("registry_id")
        if registry_id is None:
            continue
        matches.append({
            **row,
            "normalized_wad_name": normalized,
            "catalogue_ids": sorted(tracked_by_wad[normalized]),
        })
    return contexts, matches


def sweep_registry(
    k,
    process,
    base: int,
    registry: dict,
    wad_name: str,
    staged_oracle: dict[int, list[dict]],
    element_index: dict[str, list[dict]],
):
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
                if match["wad"].lower() != wad_name:
                    continue
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

        registry_id = registry["id"]
        hits.append({
            "live_wad": wad_name,
            "runtime_registry": registry_id,
            "slot": slot,
            "runtime_token_hex": (
                f"0x{(1 | (registry_id << 1) | (slot << 18)):016X}"
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
    rows = tracked_rows(catalogue)
    element_index, tracked_by_wad = build_catalogue_element_index(rows)
    staged_by_wad, staged_total = build_staged_oracle(staged)

    k = native.k32_api()
    pid, name = native.find_process(k)
    base, size, exe_text = native.main_module(k, pid, name)
    exe = Path(exe_text).resolve()
    exe_sha = native.sha256_file(exe)
    if exe_sha.lower() != native.EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    all_contexts, tracked_contexts = live_tracked_contexts(
        pid, exe, tracked_by_wad
    )
    if not tracked_contexts:
        raise RuntimeError(
            "no tracked Legendary WAD is currently resident; move/load near one "
            "tracked Legendary Chest and rerun"
        )

    # One live context per WAD is expected, but de-duplicate exact WAD/registry
    # pairs defensively before sweeping.
    live_pairs = []
    seen_pairs = set()
    for row in tracked_contexts:
        pair = (row["normalized_wad_name"], int(row["registry_id"]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        live_pairs.append({
            "wad": pair[0],
            "registry_id": pair[1],
            "context_index": row["context_index"],
            "catalogue_ids": row["catalogue_ids"],
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
            wad_name = live["wad"]
            registry_id = live["registry_id"]
            registry = find_registry(k, process, base, registry_id)
            wad_oracle = staged_by_wad.get(wad_name, {})
            stats, registry_hits = sweep_registry(
                k,
                process,
                base,
                registry,
                wad_name,
                wad_oracle,
                element_index,
            )
            registry_reports.append({
                **live,
                "registry_count": registry["count"],
                "staged_oracle_hash_count": len(wad_oracle),
                **stats,
                "hit_count": len(registry_hits),
            })
            hits.extend(registry_hits)
    finally:
        native.close(k, process)

    unique_runtime_hashes = sorted({row["object_hash_hex"] for row in hits})
    represented_wads = sorted({
        staged_match["wad"]
        for row in hits
        for staged_match in row["staged_matches"]
    })
    overlap_hits = [row for row in hits if row["catalogue_element_overlaps"]]

    report = {
        "schema": 2,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "analysis": "legendary_staged_runtime_identity_intersection_live_registries",
        "result": (
            "STAGED_RUNTIME_IDENTITY_INTERSECTION_FOUND"
            if hits else
            "NO_STAGED_RUNTIME_IDENTITY_INTERSECTION_IN_RESIDENT_TRACKED_WADS"
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
            "represented_wad_count": len(staged_by_wad),
            "class_key_hex": SIMPLE_CLASS,
            "tracked_rows": len(rows),
        },
        "live_context_count": len(all_contexts),
        "tracked_live_context_count": len(tracked_contexts),
        "tracked_live_wad_registry_pairs": live_pairs,
        "registry_reports": registry_reports,
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
            f"live_contexts={len(all_contexts)} "
            f"tracked_live_contexts={len(tracked_contexts)} "
            f"tracked_wad_registry_pairs={len(live_pairs)}"
        ),
        (
            f"staged_parents={staged_total} hits={len(hits)} "
            f"unique_runtime_hashes={len(unique_runtime_hashes)} "
            f"catalogue_overlap_hits={len(overlap_hits)}"
        ),
        "represented_wads="
        + (",".join(represented_wads) if represented_wads else "-"),
        "",
        "REGISTRIES",
    ]
    for row in registry_reports:
        lines.append(
            f"wad={row['wad']} registry={row['registry_id']} "
            f"count={row['registry_count']} staged_hashes={row['staged_oracle_hash_count']} "
            f"non_null={row['non_null']} built={row['built']} "
            f"failures={row['build_failures']} hits={row['hit_count']}"
        )

    lines += ["", "HITS"]
    for row in hits:
        staged_names = ",".join(
            f"{item['wad']}:{item['state_raw_hex']}"
            for item in row["staged_matches"]
        )
        lines.append(
            f"wad={row['live_wad']} registry={row['runtime_registry']} "
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
        f"tracked_pairs={len(live_pairs)} hits={len(hits)} "
        f"represented_wads={len(represented_wads)} "
        f"catalogue_overlap_hits={len(overlap_hits)}"
    )
    for row in registry_reports:
        print(
            f"LIVE_TRACKED_WAD wad={row['wad']} registry={row['registry_id']} "
            f"staged_hashes={row['staged_oracle_hash_count']} "
            f"built={row['built']} hits={row['hit_count']}"
        )
    print(
        "process_memory_written=false active_save_opened=false "
        "save_or_progression_written=false raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
