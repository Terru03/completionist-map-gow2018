#!/usr/bin/env python3
"""Read-only byte-level trace for CompassIconClass in-world resource hashes.

This does not patch or install anything. It finds references to the stock DockPoint
and SIDE in-world hashes across DCBs and likely UI/HUD WADs, and captures nearby
bytes/string hints so the next step can identify the actual runtime resource domain
before creating a dedicated Completionist Raven in-world marker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
from typing import Iterable

TARGETS = {
    "DockPoint.InWorld_tMPIcon_Name": 0x0E24C47DE2F769CA,
    "SIDE.InWorld_tMPIcon_Name": 0x0E24CF72E968ACF0,
    "CompletionistRaven.HUD_IconName_control": 0x45E5C7943749F81C,
    "DockPoint.HUD_IconName_control": 0x82F0296748C7393D,
}
ASCII_HINTS = (
    b"COMPASS_INWORLD",
    b"INWORLD_DOCK",
    b"INWORLD",
    b"CompassIconClass",
)
LIKELY_WAD_TERMS = ("ui", "hud", "compass", "menu", "perm", "common", "global")
MAX_HITS_PER_TOKEN_PER_FILE = 64


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_all(mm: mmap.mmap, needle: bytes, limit: int) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < limit:
        pos = mm.find(needle, start)
        if pos < 0:
            break
        out.append(pos)
        start = pos + 1
    return out


def context_hex(mm: mmap.mmap, offset: int, radius: int = 32) -> str:
    lo = max(0, offset - radius)
    hi = min(len(mm), offset + 8 + radius)
    return bytes(mm[lo:hi]).hex()


def ascii_context(mm: mmap.mmap, offset: int, radius: int = 96) -> str:
    lo = max(0, offset - radius)
    hi = min(len(mm), offset + radius)
    raw = bytes(mm[lo:hi])
    return "".join(chr(b) if 32 <= b < 127 else "." for b in raw)


def iter_candidate_files(game_root: Path, broad_wads: bool) -> Iterable[Path]:
    dc = game_root / "exec" / "dc" / "pc_le"
    wad = game_root / "exec" / "wad" / "pc_le"
    seen: set[Path] = set()

    if dc.is_dir():
        for p in sorted(dc.glob("*.dcb")):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p

    if wad.is_dir():
        for p in sorted(wad.glob("*.wad")):
            name = p.name.lower()
            selected = broad_wads or p.name.lower() == "r_ui.wad" or any(term in name for term in LIKELY_WAD_TERMS)
            if selected and p.is_file() and p not in seen:
                seen.add(p)
                yield p


def scan_file(path: Path) -> dict | None:
    size = path.stat().st_size
    if size == 0:
        return None
    target_hits: dict[str, list[dict]] = {}
    ascii_hits: dict[str, list[dict]] = {}
    with path.open("rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for label, value in TARGETS.items():
                needle = value.to_bytes(8, "little")
                hits = find_all(mm, needle, MAX_HITS_PER_TOKEN_PER_FILE)
                if hits:
                    target_hits[label] = [
                        {
                            "offset": off,
                            "offset_hex": f"0x{off:X}",
                            "context_hex": context_hex(mm, off),
                            "ascii_context": ascii_context(mm, off),
                        }
                        for off in hits
                    ]
            for hint in ASCII_HINTS:
                hits = find_all(mm, hint, 24)
                if hits:
                    key = hint.decode("ascii")
                    ascii_hits[key] = [
                        {
                            "offset": off,
                            "offset_hex": f"0x{off:X}",
                            "ascii_context": ascii_context(mm, off),
                        }
                        for off in hits
                    ]
    if not target_hits and not ascii_hits:
        return None
    return {
        "path": str(path),
        "bytes": size,
        "sha256": sha256(path),
        "target_hits": target_hits,
        "ascii_hits": ascii_hits,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--broad-wads", action="store_true", help="scan every WAD, not just likely UI/HUD WADs")
    args = ap.parse_args()

    game_root = args.game_root.resolve()
    if not game_root.is_dir():
        raise FileNotFoundError(f"game root not found: {game_root}")

    files = list(iter_candidate_files(game_root, args.broad_wads))
    findings: list[dict] = []
    counts = {label: 0 for label in TARGETS}
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}")
        row = scan_file(path)
        if row is not None:
            findings.append(row)
            for label, hits in row["target_hits"].items():
                counts[label] += len(hits)

    report = {
        "schema": 1,
        "result": "READ_ONLY_RAVEN_INWORLD_RESOURCE_TRACE",
        "game_root": str(game_root),
        "broad_wads": args.broad_wads,
        "files_scanned": len(files),
        "targets": {k: f"{v:016X}" for k, v in TARGETS.items()},
        "target_hit_counts": counts,
        "files_with_findings": findings,
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "interpretation_gate": (
            "Use the DockPoint/SIDE reference topology and string hints to identify the in-world "
            "resource domain. Do not bind a new Raven InWorld_tMPIcon_Name until its registration "
            "and physical resource requirements are understood."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("READ_ONLY_RAVEN_INWORLD_RESOURCE_TRACE")
    print(f"  files scanned: {len(files)}")
    for label, count in counts.items():
        print(f"  {label}: {count} hit(s)")
    print("  game files written: false")
    print(f"  output: {args.output}")


if __name__ == "__main__":
    main()
