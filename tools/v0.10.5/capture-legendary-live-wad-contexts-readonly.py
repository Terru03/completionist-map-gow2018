#!/usr/bin/env python3
"""Inventory live WAD contexts and intersect them with tracked Legendary WADs.

Read-only diagnostic using the already-proven 64-slot WAD context table.
No debugger, breakpoints, process writes, save writes, progression writes, or
Raven runtime changes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import ntpath
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "capture-raven-readonly-registry.py"
EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_module("_legendary_live_wad_context_base", BASE_PATH)


def normalize_wad_name(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().replace("/", "\\")
    if not text:
        return None
    name = ntpath.basename(text).lower()
    if not name:
        return None
    if not name.endswith(".wad"):
        marker = name.lower().find(".wad")
        if marker >= 0:
            name = name[:marker + 4]
        else:
            # The proved live WAD context commonly stores only the WAD stem,
            # e.g. "Xpl250_FuneralInterior". Shipped catalogue paths add .wad.
            name = name + ".wad"
    return name


def tracked_rows(catalogue: dict) -> list[dict]:
    return [
        row for row in catalogue.get("collectibles", [])
        if row.get("family") == "legendary_chest"
        and row.get("production_eligibility") == "tracked_collectible"
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    if sys.platform != "win32":
        raise RuntimeError("64-bit Windows required")

    exe = args.exe.resolve()
    exe_sha = BASE.sha256_path(exe)
    if exe_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    rows = tracked_rows(catalogue)
    if len(rows) != 33:
        raise RuntimeError(f"expected 33 tracked Legendary rows, got {len(rows)}")

    tracked = {}
    for row in rows:
        wad = row["source"]["wad"].lower()
        tracked.setdefault(wad, []).append(row["catalogue_id"])
    if len(tracked) != 27:
        raise RuntimeError(f"expected 27 tracked Legendary WADs, got {len(tracked)}")

    reader = BASE.Reader(args.pid)
    try:
        base, module_path = reader.module()
        if Path(module_path).resolve() != exe:
            raise RuntimeError(
                f"PID {args.pid} executable mismatch: {module_path}"
            )
        contexts = BASE.wad_contexts(reader, base)
    finally:
        reader.close()

    public_contexts = []
    tracked_matches = []
    decoded_name_count = 0
    for context in contexts:
        raw_name = context.get("wad_name")
        normalized = normalize_wad_name(raw_name)
        if normalized:
            decoded_name_count += 1
        item = {
            **context,
            "normalized_wad_name": normalized,
            "tracked_legendary_wad": normalized in tracked if normalized else False,
        }
        public_contexts.append(item)
        if normalized in tracked:
            tracked_matches.append({
                **item,
                "catalogue_ids": sorted(tracked[normalized]),
            })

    unique_live_names = sorted({
        item["normalized_wad_name"]
        for item in public_contexts
        if item["normalized_wad_name"]
    })
    unique_tracked_names = sorted({
        item["normalized_wad_name"]
        for item in tracked_matches
    })

    report = {
        "schema": 1,
        "analysis": "legendary_live_wad_context_inventory",
        "pid": args.pid,
        "module_base": f"0x{base:X}",
        "module_path": module_path,
        "exe_sha256": exe_sha,
        "tracked_catalogue_count": len(rows),
        "tracked_wad_count": len(tracked),
        "live_context_count": len(contexts),
        "decoded_name_count": decoded_name_count,
        "unique_live_wad_names": unique_live_names,
        "tracked_live_context_count": len(tracked_matches),
        "tracked_live_wad_count": len(unique_tracked_names),
        "tracked_live_wad_names": unique_tracked_names,
        "tracked_live_contexts": tracked_matches,
        "live_contexts": public_contexts,
        "result": (
            "TRACKED_LEGENDARY_WAD_CONTEXTS_PRESENT"
            if tracked_matches
            else "NO_TRACKED_LEGENDARY_WAD_CONTEXT_PRESENT"
        ),
        "safety": {
            "access": "PROCESS_QUERY_INFORMATION|PROCESS_VM_READ",
            "debugger_attached": False,
            "breakpoints_installed": False,
            "process_writes": False,
            "save_writes": False,
            "progression_writes": False,
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
        "Completionist Map - Legendary live WAD context inventory",
        f"result={report['result']}",
        (
            f"live_contexts={len(contexts)} decoded_names={decoded_name_count} "
            f"tracked_live_contexts={len(tracked_matches)} "
            f"tracked_live_wads={len(unique_tracked_names)}"
        ),
        "tracked_live_wad_names="
        + (",".join(unique_tracked_names) if unique_tracked_names else "-"),
        "",
        "TRACKED LIVE CONTEXTS",
    ]
    for item in tracked_matches:
        lines.append(
            f"index={item['context_index']} registry={item['registry_id']} "
            f"wad={item['normalized_wad_name']} "
            f"catalogue_ids={','.join(item['catalogue_ids'])}"
        )
    lines += [
        "",
        "ALL DECODED LIVE WADS",
        *unique_live_names,
        "",
        "SAFETY",
        "PROCESS_QUERY_INFORMATION|PROCESS_VM_READ",
        "process_writes=false",
        "save_writes=false",
        "progression_writes=false",
        "game_files_written=false",
        "raven_runtime_modified=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "LEGENDARY_LIVE_WAD_CONTEXT_INVENTORY_COMPLETE "
        f"live={len(contexts)} decoded={decoded_name_count} "
        f"tracked_contexts={len(tracked_matches)} "
        f"tracked_wads={len(unique_tracked_names)}"
    )
    print(
        "tracked_live_wad_names="
        + (",".join(unique_tracked_names) if unique_tracked_names else "-")
    )
    print(
        "process_writes=false save_writes=false progression_writes=false "
        "raven_runtime_modified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
