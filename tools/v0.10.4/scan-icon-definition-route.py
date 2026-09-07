"""Locate stock map/compass icon definition data without modifying the game.

The first v0.10.4 scan proved DockPoint is heavily shared, so a Raven cannot keep
using a global DockPoint texture replacement. This follow-up searches the small
DCB set by both literal names and the engine's 64-bit name hash, inventories any
CompassIconClass (type 0x11E) exports, and reads the executable RTTI attribute
layout for type 0x11E. The result is evidence for cloning a dedicated Raven icon
class instead of hijacking a stock class.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_native_markers", HERE.parent / "v0.10.3" / "inspect-native-markers.py"
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

EXPECTED_EXE = "caebcb027980d7eac9203d190f9eebc549f8defce138e2114dc91f40452"
# Correct hash is checked after normalising below. Kept separate so a typo cannot
# silently authorise writes; this tool is read-only regardless.
EXPECTED_EXE_FULL = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
BASE = 0x140000000
ATTRS = 0x141082030
COMPASS_ICON_CLASS_TYPE = 0x11E

COMPASS_CLASSES = [
    "MAIN", "SIDE", "VendorLocation", "VendorLocationNoTrack", "FastTravel",
    "FastTravelNoTrack", "AreaEntrance", "FightLocation", "FightLocationNoTrack",
    "DockPoint", "ChiselLocation", "ChiselLocationNoTrack", "InfoOnly", "Valkyrie",
]

MAP_ICONS = [
    "goMapIconDock", "goMapIconFastTravel", "goMapIconAreaEntrance",
    "goMapIconFight_location", "goMapIconSecondaryQuest", "goMapIconPrimaryQuest",
    "goMapIconValkyrie_location", "goMapIconVendor", "goMapIconNoRender",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_all(blob: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        at = blob.find(needle, start)
        if at < 0:
            return out
        out.append(at)
        start = at + 1


def pe_reader(raw: bytes):
    pe, = struct.unpack_from("<I", raw, 0x3C)
    count, = struct.unpack_from("<H", raw, pe + 6)
    optional_size, = struct.unpack_from("<H", raw, pe + 20)
    sections = []
    for i in range(count):
        o = pe + 24 + optional_size + 40 * i
        virtual_size, rva, raw_size, file_offset = struct.unpack_from("<4I", raw, o + 8)
        length = min(virtual_size or raw_size, raw_size) if raw_size else virtual_size
        sections.append((rva, length, file_offset))

    def read(va: int, size: int) -> bytes:
        rva = va - BASE
        for start, length, offset in sections:
            if start <= rva and rva + size <= start + length:
                return raw[offset + rva - start : offset + rva - start + size]
        raise ValueError("Address outside file-backed PE section")

    def string(va: int) -> str:
        data = read(va, 256)
        return data.split(b"\0", 1)[0].decode("ascii")

    return read, string


def compass_rtti(exe: Path) -> dict:
    raw = exe.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_EXE_FULL:
        return {"sha256": digest, "supported_build": False, "attributes": []}

    read, string = pe_reader(raw)
    attrs = []
    # Existing researched marker attributes sit near 0x459A. Scan the complete
    # plausible TypeAttribute table range and keep only parent type 0x11E.
    for index in range(0x0000, 0x5000):
        try:
            field = read(ATTRS + index * 32, 32)
            name_ptr, _unused, offset, size, flags, _unused2, parent = struct.unpack_from(
                "<QQHHBBH", field
            )
            if parent != COMPASS_ICON_CLASS_TYPE or name_ptr == 0:
                continue
            name = string(name_ptr)
            if not name or any(ord(ch) < 32 or ord(ch) > 126 for ch in name):
                continue
            attrs.append(
                {
                    "attr_index": f"0x{index:X}",
                    "field": name,
                    "offset": f"0x{offset:X}",
                    "size": size,
                    "kind": flags >> 2,
                }
            )
        except (ValueError, UnicodeDecodeError, struct.error):
            continue
    return {"sha256": digest, "supported_build": True, "attributes": attrs}


def scan_dcb(path: Path) -> dict | None:
    raw = path.read_bytes()
    literal_hits = []
    hash_hits = []

    for category, names in (("compass_class", COMPASS_CLASSES), ("map_icon", MAP_ICONS)):
        for name in names:
            offsets = find_all(raw, name.encode("ascii"))
            if offsets:
                literal_hits.append({"category": category, "name": name, "offsets": offsets})

            hashed = native.name_hash(name)
            offsets = find_all(raw, struct.pack("<Q", hashed))
            if offsets:
                hash_hits.append(
                    {
                        "category": category,
                        "name": name,
                        "hash": f"{hashed:016X}",
                        "offsets": offsets,
                    }
                )

    exports_11e = []
    exports_nearby = []
    try:
        dcb = native.Dcb(path)
        for name, (root, type_id) in sorted(dcb.exports.items()):
            if type_id == COMPASS_ICON_CLASS_TYPE:
                exports_11e.append({"name": name, "root": f"0x{root:X}", "type_id": "0x11E"})
            if type_id in range(COMPASS_ICON_CLASS_TYPE - 4, COMPASS_ICON_CLASS_TYPE + 5):
                exports_nearby.append({"name": name, "root": f"0x{root:X}", "type_id": f"0x{type_id:X}"})
    except Exception as exc:  # inventory evidence only; do not abort the whole scan
        dcb_error = str(exc)
    else:
        dcb_error = None

    if not (literal_hits or hash_hits or exports_11e or exports_nearby):
        return None

    return {
        "file": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "literal_hits": literal_hits,
        "hash_hits": hash_hits,
        "exports_type_0x11e": exports_11e,
        "exports_near_0x11e": exports_nearby,
        "dcb_parse_error": dcb_error,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--game-root", type=Path,
        default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"),
    )
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    dc = game / "exec/dc/pc_le"
    exe = game / "GoW.exe"
    if not dc.is_dir():
        raise FileNotFoundError(dc)
    if not exe.is_file():
        raise FileNotFoundError(exe)

    files = []
    for path in sorted(dc.glob("*.dcb")):
        hit = scan_dcb(path)
        if hit is not None:
            files.append(hit)

    report = {
        "result": "READ_ONLY_ICON_DEFINITION_ROUTE_SCAN",
        "game_files_written": False,
        "stock_dcb_count": len(list(dc.glob("*.dcb"))),
        "compass_icon_class_type_id": "0x11E",
        "compass_rtti": compass_rtti(exe),
        "files_with_evidence": files,
        "dockpoint_is_safe_as_global_raven_visual": False,
        "next_goal": "Clone/author a dedicated Raven map icon and CompassIconClass; do not globally replace DockPoint.",
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("Report must stay outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    if out.stat().st_size == 0:
        raise RuntimeError("Scanner produced an empty report")

    print(f"Saved: {out}")
    print(f"DCB files with icon-definition evidence: {len(files)}")
    print(f"CompassIconClass RTTI fields: {len(report['compass_rtti']['attributes'])}")
    for row in files:
        labels = [x["name"] for x in row["literal_hits"] + row["hash_hits"]]
        print(f"  {row['file']}: {', '.join(sorted(set(labels)))}")


if __name__ == "__main__":
    main()
