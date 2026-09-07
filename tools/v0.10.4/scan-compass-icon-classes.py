"""Scan stock God of War DCB files for compass icon-class evidence.

Read-only helper for v0.10.4 Raven-vs-Dock visual separation. It searches the
small exec/dc/pc_le DCB set for known CompassIconClass names and reports which
files contain them, plus nearby printable strings. It never writes game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

KNOWN = [
    "MAIN",
    "SIDE",
    "VendorLocation",
    "VendorLocationNoTrack",
    "FastTravel",
    "FastTravelNoTrack",
    "AreaEntrance",
    "FightLocation",
    "FightLocationNoTrack",
    "DockPoint",
    "ChiselLocation",
    "ChiselLocationNoTrack",
    "InfoOnly",
    "Valkyrie",
]

PRINTABLE = re.compile(rb"[ -~]{4,}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strings(blob: bytes) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for match in PRINTABLE.finditer(blob):
        try:
            out.append((match.start(), match.group().decode("ascii")))
        except UnicodeDecodeError:
            pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--game-root",
        type=Path,
        default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"),
    )
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    game = args.game_root.resolve()
    dc = game / "exec/dc/pc_le"
    if not dc.is_dir():
        raise FileNotFoundError(dc)

    hits = []
    for path in sorted(dc.glob("*.dcb")):
        blob = path.read_bytes()
        ascii_strings = strings(blob)
        matched = []
        for name in KNOWN:
            needle = name.encode("ascii")
            start = 0
            offsets = []
            while True:
                pos = blob.find(needle, start)
                if pos < 0:
                    break
                offsets.append(pos)
                start = pos + 1
            if offsets:
                matched.append({"name": name, "offsets": offsets})
        if not matched:
            continue

        interesting_offsets = [o for row in matched for o in row["offsets"]]
        nearby = []
        for off, value in ascii_strings:
            distance = min(abs(off - x) for x in interesting_offsets)
            if distance <= 512:
                nearby.append({"offset": off, "value": value})

        hits.append(
            {
                "file": path.name,
                "bytes": len(blob),
                "sha256": sha256(path),
                "matches": matched,
                "nearby_strings": nearby,
            }
        )

    report = {
        "result": "READ_ONLY_COMPASS_ICON_CLASS_SCAN",
        "game_files_written": False,
        "known_classes": KNOWN,
        "files_with_hits": hits,
    }

    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Saved: {out}")
    else:
        print(text, end="")

    print(f"DCB files with known CompassIconClass strings: {len(hits)}")
    for hit in hits:
        names = ", ".join(row["name"] for row in hit["matches"])
        print(f"  {hit['file']}: {names}")


if __name__ == "__main__":
    main()
