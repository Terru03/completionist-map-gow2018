"""Inspect fully extracted r_ui.wad files for the per-Raven map/HUD visual route.

Read-only with respect to the game. GOWTool extracts r_ui.wad buffers into a
LocalAppData work directory; this script inventories those extracted buffers and
looks for the stock map-icon/DockPoint identities and texture/material hashes we
already proved. The goal is to identify the actual prefab/material resource that
must be cloned for a synthetic Raven-only visual instead of globally reskinning
DockPoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

KEYWORDS = (
    "mapicon", "map_icon", "mapmarker", "map_marker", "dock", "compass",
    "inworld", "marker", "material", "matswap", "ui",
)

NAMES = [
    "goMapIconPrimaryQuest",
    "goMapIconSecondaryQuest",
    "goMapIconFastTravel",
    "goMapIconDock",
    "goMapIconVendor",
    "goMapIconAreaEntrance",
    "goMapIconFight_location",
    "goMapIconValkyrie_location",
    "goMapIconNoRender",
    "DockPoint",
    "COMPASS_INWORLD_DOCK",
    "goMapIconCompletionistRaven",
    "COMPASS_INWORLD_COMPLETIONIST_RAVEN",
]

# Proven/observed r_ui texture identities from the earlier v0.10.2 extraction.
HASH_LABELS = {
    0x982BF904AB84F2CC: "TX_mapmarker_docklocation_diffuse",
    0xFCC664130951154C: "TX_mapmarker_docklocation_emissive",
    0x3639B2A1D4F1992D: "TX_dockicon_01",
    0xEF72E29D32F14FD7: "TX_docks_01_diffuse",
    0x449809F1E1BEECAF: "TX_docks_01_gloss",
    0xF672D863A2E2C4C9: "TX_docks_01_normal",
    0xACC406FACA794B13: "TX_compassdiamond",
    0xEA39C7AABB680C0F: "TX_compassradius",
}

PRINTABLE = re.compile(rb"[ -~]{4,120}")


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_all(blob: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        at = blob.find(needle, start)
        if at < 0:
            return out
        out.append(at)
        start = at + 1


def inspect_file(path: Path, name_hashes: dict[int, str]) -> dict | None:
    blob = path.read_bytes()
    low_name = path.name.lower()
    filename_keywords = sorted({k for k in KEYWORDS if k in low_name})

    literal_hits: list[dict] = []
    for name in NAMES:
        for off in find_all(blob, name.encode("ascii")):
            literal_hits.append({"name": name, "offset": off})

    hash_hits: list[dict] = []
    for value, label in {**name_hashes, **HASH_LABELS}.items():
        for off in find_all(blob, struct.pack("<Q", value)):
            hash_hits.append({"label": label, "hash": f"{value:016X}", "offset": off})

    if not filename_keywords and not literal_hits and not hash_hits:
        return None

    printable = []
    # Keep only strings that are themselves visually relevant to avoid dumping
    # arbitrary game data into the report.
    for match in PRINTABLE.finditer(blob):
        text = match.group().decode("ascii", errors="ignore")
        low = text.lower()
        if any(k in low for k in KEYWORDS) or any(n.lower() in low for n in NAMES):
            printable.append({"offset": match.start(), "text": text})
            if len(printable) >= 40:
                break

    return {
        "file": path.name,
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "filename_keywords": filename_keywords,
        "literal_hits": sorted(literal_hits, key=lambda x: (x["offset"], x["name"])),
        "hash_hits": sorted(hash_hits, key=lambda x: (x["offset"], x["label"])),
        "relevant_printable_strings": printable,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extracted", type=Path, required=True)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    extracted = args.extracted.resolve()
    wad = args.wad.resolve()
    out = args.output.resolve()
    if not extracted.is_dir():
        raise FileNotFoundError(extracted)
    if not wad.is_file():
        raise FileNotFoundError(wad)

    files = sorted(p for p in extracted.rglob("*") if p.is_file())
    if not files:
        raise ValueError("GOWTool extraction directory is empty")

    name_hashes = {name_hash(name): name for name in NAMES}
    interesting = []
    for path in files:
        row = inspect_file(path, name_hashes)
        if row is not None:
            interesting.append(row)

    exact_name_candidates = [
        p.name for p in files
        if any(token in p.name.lower() for token in (
            "gomapicon", "mapicon", "mapmarker", "dock", "compass", "inworld"
        ))
    ]

    report = {
        "result": "READ_ONLY_R_UI_PREFAB_EXTRACTION_INSPECTED",
        "game_files_written": False,
        "source_wad": {
            "path": str(wad),
            "bytes": wad.stat().st_size,
            "sha256": sha256(wad),
        },
        "extraction": {
            "directory": str(extracted),
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
        },
        "known_hashes": {
            name: f"{value:016X}" for value, name in sorted(name_hashes.items())
        },
        "texture_hashes": {
            label: f"{value:016X}" for value, label in sorted(HASH_LABELS.items())
        },
        "filename_candidates": exact_name_candidates,
        "interesting_files": interesting,
        "decision_note": (
            "The decoded wad_r_ui.dcb goMapIcon rows are GOPool entries: its GOPool starts at 0x90, "
            "contains 255 fixed 16-byte rows, and ends exactly at 0x1080 where MemoryPools begins. "
            "A GOPool clone alone therefore cannot define new Raven artwork. This extraction targets "
            "the actual r_ui.wad prefab/material resources before any offline or runtime patch is built."
        ),
        "next_gate": (
            "Identify the concrete DockPoint map-icon prefab/material buffer and its texture references. "
            "Only then clone/retarget that resource for a Raven-only map visual; do not restore the global "
            "DockPoint texture override."
        ),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Extracted files inspected: {len(files)}")
    print(f"Interesting files: {len(interesting)}")
    print(f"Filename candidates: {len(exact_name_candidates)}")
    print(f"Saved: {out}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
