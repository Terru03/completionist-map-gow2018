"""Decode the concrete r_ui.wad resource neighbourhood around stock map icons.

Read-only. Requires the full r_ui.wad extraction produced by
extract-r-ui-prefab-inventory.ps1. GOWTool names extracted buffers as
<ResourceName>.<wad-entry-index>.bin, which lets us inspect the complete local
resource chain around goProtoMapIconDock and compare it with other stock map
icons. The goal is to identify the exact prefab/material entries that differ per
icon before authoring a Raven-only resource. No game files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

INDEX_RE = re.compile(r"\.(\d+)\.bin$", re.IGNORECASE)
PRINTABLE = re.compile(rb"[ -~]{4,160}")

FAMILIES = {
    "dock": "mapicondock",
    "vendor": "mapiconvendor",
    "fight_location": "mapiconfight_location",
    "valkyrie_location": "mapiconvalkyrie_location",
    "area_entrance": "mapiconareaentrance",
    "fast_travel": "mapiconfasttravel",
    "primary_quest": "mapiconprimaryquest",
    "secondary_quest": "mapiconsecondaryquest",
}

KNOWN_TEXTURES = {
    0x982BF904AB84F2CC: "TX_mapmarker_docklocation_diffuse",
    0xFCC664130951154C: "TX_mapmarker_docklocation_emissive",
    0x3639B2A1D4F1992D: "TX_dockicon_01",
    0xEF72E29D32F14FD7: "TX_docks_01_diffuse",
    0x449809F1E1BEECAF: "TX_docks_01_gloss",
    0xF672D863A2E2C4C9: "TX_docks_01_normal",
    0xACC406FACA794B13: "TX_compassdiamond",
    0xEA39C7AABB680C0F: "TX_compassradius",
}


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def entry_index(path: Path) -> int | None:
    m = INDEX_RE.search(path.name)
    return int(m.group(1)) if m else None


def useful_strings(blob: bytes) -> list[dict]:
    rows = []
    for m in PRINTABLE.finditer(blob):
        text = m.group().decode("ascii", errors="ignore")
        low = text.lower()
        if any(token in low for token in (
            "mapicon", "mapmarker", "material", "shader", "texture", "dock",
            "vendor", "fight", "valkyr", "quest", "travel", "entrance",
            "gameart/", "gameart\\", ".mb", "scr_", "scp_", "mdl_", "anm_",
        )):
            rows.append({"offset": m.start(), "text": text})
            if len(rows) >= 32:
                break
    return rows


def matching_index_refs(blob: bytes, valid_indices: set[int], own: int) -> list[dict]:
    refs = []
    seen = set()
    # Resource references in these buffers may be 32-bit entry indices. Search
    # every byte offset because packed structures need not be naturally aligned.
    if len(blob) >= 4:
        for off in range(0, len(blob) - 3):
            value = struct.unpack_from("<I", blob, off)[0]
            if value == own or value not in valid_indices:
                continue
            key = (off, value)
            if key not in seen:
                refs.append({"offset": off, "index": value})
                seen.add(key)
            if len(refs) >= 80:
                break
    return refs


def texture_hash_refs(blob: bytes) -> list[dict]:
    rows = []
    for value, label in KNOWN_TEXTURES.items():
        needle = struct.pack("<Q", value)
        start = 0
        while True:
            at = blob.find(needle, start)
            if at < 0:
                break
            rows.append({"offset": at, "hash": f"{value:016X}", "label": label})
            start = at + 1
    return sorted(rows, key=lambda x: (x["offset"], x["label"]))


def inspect(path: Path, index_to_name: dict[int, str], valid_indices: set[int]) -> dict:
    blob = path.read_bytes()
    idx = entry_index(path)
    assert idx is not None
    refs = matching_index_refs(blob, valid_indices, idx)
    for row in refs:
        row["target_file"] = index_to_name.get(row["index"])
    return {
        "index": idx,
        "file": path.name,
        "bytes": len(blob),
        "sha256": sha256(blob),
        "index_refs": refs,
        "known_texture_hash_refs": texture_hash_refs(blob),
        "relevant_printable_strings": useful_strings(blob),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extracted", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--radius", type=int, default=6)
    args = ap.parse_args()

    root = args.extracted.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)

    files = []
    by_index: dict[int, Path] = {}
    for p in sorted(root.rglob("*.bin")):
        idx = entry_index(p)
        if idx is None:
            continue
        if idx in by_index:
            raise ValueError(f"duplicate extracted WAD entry index {idx}: {p} and {by_index[idx]}")
        by_index[idx] = p
        files.append(p)
    if not files:
        raise ValueError("no indexed .bin files found in extracted r_ui.wad directory")

    valid_indices = set(by_index)
    index_to_name = {idx: p.name for idx, p in by_index.items()}

    families = {}
    all_selected: set[int] = set()
    for family, token in FAMILIES.items():
        hits = [p for p in files if token in p.name.lower()]
        if not hits:
            families[family] = {"token": token, "family_files": [], "window": []}
            continue
        hit_indices = sorted(entry_index(p) for p in hits if entry_index(p) is not None)
        lo = max(min(valid_indices), min(hit_indices) - args.radius)
        hi = min(max(valid_indices), max(hit_indices) + args.radius)
        window_indices = [idx for idx in range(lo, hi + 1) if idx in by_index]
        all_selected.update(window_indices)
        families[family] = {
            "token": token,
            "family_files": [
                {"index": entry_index(p), "file": p.name} for p in hits
            ],
            "window_range": [lo, hi],
            "window_indices": window_indices,
        }

    decoded = {
        str(idx): inspect(by_index[idx], index_to_name, valid_indices)
        for idx in sorted(all_selected)
    }

    # Highlight the tight Dock chain separately because this is the resource we
    # intend to clone. The neighbouring indices often expose material/script or
    # instance buffers that filename-keyword scans miss.
    dock_family = families.get("dock", {})
    dock_indices = dock_family.get("window_indices", [])
    dock_neighbourhood = [decoded[str(idx)] for idx in dock_indices]

    report = {
        "result": "READ_ONLY_MAP_ICON_RESOURCE_NEIGHBOURHOOD_DECODED",
        "game_files_written": False,
        "extracted_directory": str(root),
        "indexed_entries": len(by_index),
        "radius": args.radius,
        "families": families,
        "dock_neighbourhood": dock_neighbourhood,
        "decoded_entries": decoded,
        "interpretation": (
            "GOWTool's numeric filename suffix is the r_ui.wad entry index. By comparing the complete "
            "Dock neighbourhood with Vendor/Fight/Valkyrie/etc., this report is intended to reveal the "
            "otherwise unnamed material/prefab entries and any direct entry-index references between them."
        ),
        "next_gate": (
            "Identify the smallest complete Dock map-icon resource chain that can be cloned without altering "
            "stock DockPoint. Then build the Raven-only clone offline and validate every internal reference "
            "before any runtime install."
        ),
    }

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Indexed extracted entries: {len(by_index)}")
    print(f"Decoded selected entries: {len(decoded)}")
    print(f"Dock neighbourhood entries: {len(dock_neighbourhood)}")
    print(f"Saved: {out}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
