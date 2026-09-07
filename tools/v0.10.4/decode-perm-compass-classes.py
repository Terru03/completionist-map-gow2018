"""Decode CompassIconClass exports from stock wad_r_perm.dcb, read-only.

This parser deliberately supports the extra kind-35 chunk present in wad_r_perm.
It decodes every type-0x11E export, then reads the 0x20-byte CompassIconClass
record using the RTTI layout recovered from the pinned GoW.exe build:

  +0x00 IconName (u64 hash)
  +0x08 RadiusIconName (u64 hash)
  +0x10 InWorld_tMPIcon_Name (u64 hash)
  +0x18 IconScale (float)
  +0x1C IsMainQuest (bool)

No game files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_native_markers", HERE.parent / "v0.10.3" / "inspect-native-markers.py"
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

EXPECTED = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
TYPE_ID = 0x11E
PRINTABLE = re.compile(rb"[ -~]{3,96}")

KNOWN_NAMES = [
    "MAIN", "SIDE", "VendorLocation", "VendorLocationNoTrack", "FastTravel",
    "FastTravelNoTrack", "AreaEntrance", "FightLocation", "FightLocationNoTrack",
    "DockPoint", "ChiselLocation", "ChiselLocationNoTrack", "InfoOnly", "Valkyrie",
    "goMapIconPrimaryQuest", "goMapIconSecondaryQuest", "goMapIconFastTravel",
    "goMapIconDock", "goMapIconVendor", "goMapIconAreaEntrance",
    "goMapIconFight_location", "goMapIconValkyrie_location", "goMapIconNoRender",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_chunks(raw: bytes) -> list[dict]:
    out = []
    off = 0
    index = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"Truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or end > len(raw):
            raise ValueError(f"Invalid chunk at {off:#x}")
        out.append({"index": index, "kind": kind, "flags": flags, "header": off,
                    "payload_start": start, "payload_end": end, "size": size})
        index += 1
        off = (end + 15) & ~15
    if off != len(raw):
        raise ValueError("Chunk walk did not end exactly at EOF")
    return out


def chunk(chunks: list[dict], kind: int) -> dict:
    matches = [x for x in chunks if x["kind"] == kind]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one chunk kind {kind}, found {len(matches)}")
    return matches[0]


def cstring(blob: bytes, start: int) -> str:
    if not 0 <= start < len(blob):
        raise ValueError(f"String offset outside chunk: {start:#x}")
    end = blob.find(b"\0", start)
    if end < 0:
        raise ValueError("Unterminated export string")
    return blob[start:end].decode("ascii")


def build_name_index(raw: bytes) -> dict[int, list[str]]:
    names = set(KNOWN_NAMES)
    for m in PRINTABLE.finditer(raw):
        try:
            value = m.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        # Avoid hashing long binary-ish printable runs as useful names.
        if 3 <= len(value) <= 96 and "\x00" not in value:
            names.add(value)
    result: dict[int, list[str]] = {}
    for name in names:
        try:
            h = native.name_hash(name)
        except UnicodeEncodeError:
            continue
        result.setdefault(h, []).append(name)
    for values in result.values():
        values.sort(key=lambda s: (len(s), s))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_bytes()
    digest = sha256(raw)
    if digest != EXPECTED:
        raise ValueError(f"Unexpected wad_r_perm.dcb SHA256: {digest}")

    chunks = parse_chunks(raw)
    data_chunk = chunk(chunks, 12)
    export_chunk = chunk(chunks, 13)
    data = raw[data_chunk["payload_start"]:data_chunk["payload_end"]]
    exports = raw[export_chunk["payload_start"]:export_chunk["payload_end"]]

    if len(exports) < 8:
        raise ValueError("Export chunk too short")
    count = struct.unpack_from("<I", exports, 0)[0]
    expected_min = 8 + count * 24
    if expected_min > len(exports):
        raise ValueError(f"Export count {count} exceeds chunk size")

    name_index = build_name_index(raw)
    rows = []
    all_export_uids = set()
    for i in range(count):
        entry = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", exports, entry)
        name = cstring(exports, string_offset)
        calc = native.name_hash(name)
        if calc != uid:
            raise ValueError(f"Export hash mismatch for {name!r}: {uid:016X} != {calc:016X}")
        all_export_uids.add(uid)
        if type_id != TYPE_ID:
            continue
        if root + 0x20 > len(data):
            raise ValueError(f"CompassIconClass root outside data chunk: {name} {root:#x}")
        icon_name, radius_name, inworld_name = struct.unpack_from("<QQQ", data, root)
        scale = struct.unpack_from("<f", data, root + 0x18)[0]
        is_main = data[root + 0x1C]
        tail = data[root + 0x1D:root + 0x20]
        if not math.isfinite(scale):
            raise ValueError(f"Non-finite IconScale for {name}")
        rows.append({
            "name": name,
            "uid": f"{uid:016X}",
            "export_index": i,
            "export_entry_file_offset": export_chunk["payload_start"] + entry,
            "root": f"0x{root:X}",
            "record_file_offset": data_chunk["payload_start"] + root,
            "record_size_from_rtti": 32,
            "IconName": f"{icon_name:016X}",
            "IconName_candidates": name_index.get(icon_name, []),
            "RadiusIconName": f"{radius_name:016X}",
            "RadiusIconName_candidates": name_index.get(radius_name, []),
            "InWorld_tMPIcon_Name": f"{inworld_name:016X}",
            "InWorld_tMPIcon_Name_candidates": name_index.get(inworld_name, []),
            "IconScale": scale,
            "IsMainQuest_raw": is_main,
            "tail_hex": tail.hex().upper(),
        })

    if not rows:
        raise ValueError("No CompassIconClass type-0x11E exports decoded")
    by_name = {row["name"]: row for row in rows}
    if "DockPoint" not in by_name:
        raise ValueError("DockPoint CompassIconClass export not found")

    roots = [int(row["root"], 16) for row in rows]
    root_unique = len(set(roots)) == len(roots)
    uid_unique = len({row["uid"] for row in rows}) == len(rows)
    alignment = sorted({root % 8 for root in roots})

    raven_name = "CompletionistRaven"
    raven_uid = native.name_hash(raven_name)
    collision = raven_uid in all_export_uids

    report = {
        "result": "READ_ONLY_DECODED_COMPASS_ICON_CLASSES",
        "game_files_written": False,
        "source": str(source),
        "sha256": digest,
        "chunk_kinds": [x["kind"] for x in chunks],
        "export_count": count,
        "compass_icon_class_count": len(rows),
        "compass_icon_class_type_id": "0x11E",
        "record_layout": {
            "size": 32,
            "fields": [
                {"offset": "0x00", "name": "IconName", "type": "u64 hash"},
                {"offset": "0x08", "name": "RadiusIconName", "type": "u64 hash"},
                {"offset": "0x10", "name": "InWorld_tMPIcon_Name", "type": "u64 hash"},
                {"offset": "0x18", "name": "IconScale", "type": "float"},
                {"offset": "0x1C", "name": "IsMainQuest", "type": "bool"},
            ],
        },
        "validation": {
            "roots_unique": root_unique,
            "uids_unique": uid_unique,
            "root_mod_8_values": alignment,
            "dockpoint_present": True,
        },
        "reserved_completionist_class": {
            "name": raven_name,
            "uid": f"{raven_uid:016X}",
            "export_uid_collision": collision,
        },
        "dockpoint": by_name["DockPoint"],
        "classes": rows,
        "next_gate": (
            "If DockPoint and peer records decode cleanly, build an OFFLINE copy that appends one "
            "CompletionistRaven 0x20 record and one type-0x11E export. Do not install it yet."
        ),
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("Output must stay outside game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {out}")
    print(f"CompassIconClass exports decoded: {len(rows)}")
    dock = by_name["DockPoint"]
    print("DockPoint:")
    print(f"  root={dock['root']} file=0x{dock['record_file_offset']:X}")
    print(f"  IconName={dock['IconName']} {dock['IconName_candidates']}")
    print(f"  RadiusIconName={dock['RadiusIconName']} {dock['RadiusIconName_candidates']}")
    print(f"  InWorld_tMPIcon_Name={dock['InWorld_tMPIcon_Name']} {dock['InWorld_tMPIcon_Name_candidates']}")
    print(f"  IconScale={dock['IconScale']} IsMainQuest={dock['IsMainQuest_raw']}")
    print(f"Reserved CompletionistRaven UID: {raven_uid:016X} collision={collision}")


if __name__ == "__main__":
    main()
