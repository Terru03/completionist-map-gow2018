"""Inspect the stock resources needed to isolate Raven visuals from DockPoint.

Read-only v0.10.4 helper. The dedicated CompassIconClass experiment proved that
adding a type-0x11E export to wad_r_perm.dcb is not sufficient for the runtime
ShowMarker wrapper to accept a new marker type. We therefore keep the proven
DockPoint navigation type internally and investigate two independent visual
routes instead:

1. a dedicated map icon resource in wad_r_ui.dcb, and
2. the in-world/HUD visual referenced by DockPoint's CompassIconClass.

No game files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

EXPECTED_R_UI = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
EXPECTED_PERM = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
BASE = 0x140000000
ATTRS = 0x141082030

MAP_ICON_NAMES = [
    "goMapIconPrimaryQuest",
    "goMapIconSecondaryQuest",
    "goMapIconFastTravel",
    "goMapIconDock",
    "goMapIconVendor",
    "goMapIconAreaEntrance",
    "goMapIconFight_location",
    "goMapIconValkyrie_location",
    "goMapIconNoRender",
]

DOCK_COMPASS_CLASS = "DockPoint"
DOCK_COMPASS_UID = 0xA9FBE73C1DDFBBC5
DOCK_ICON_NAME = 0x82F0296748C7393D
DOCK_INWORLD_NAME = 0x0E24C47DE2F769CA
DOCK_INWORLD_LITERAL = "COMPASS_INWORLD_DOCK"
RAVEN_MAP_ICON_NAME = "goMapIconCompletionistRaven"
RAVEN_COMPASS_VISUAL_NAME = "COMPASS_INWORLD_COMPLETIONIST_RAVEN"
PRINTABLE = re.compile(rb"[ -~]{3,96}")


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def parse_chunks(raw: bytes) -> list[dict]:
    chunks = []
    off = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"Truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or end > len(raw):
            raise ValueError(f"Invalid chunk at {off:#x}")
        chunks.append({
            "kind": kind,
            "header": off,
            "start": start,
            "end": end,
            "size": size,
        })
        off = align16(end)
    if off != len(raw):
        raise ValueError("Chunk walk did not end at EOF")
    return chunks


def one(chunks: list[dict], kind: int) -> dict | None:
    rows = [c for c in chunks if c["kind"] == kind]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError(f"Expected one chunk {kind}, found {len(rows)}")
    return rows[0]


def cstring(blob: bytes, start: int) -> str:
    if not 0 <= start < len(blob):
        raise ValueError(f"String offset outside payload: {start:#x}")
    end = blob.find(b"\0", start)
    if end < 0:
        raise ValueError("Unterminated string")
    return blob[start:end].decode("ascii")


def parse_exports(raw: bytes, chunks: list[dict]) -> list[dict]:
    c = one(chunks, 13)
    if c is None:
        return []
    payload = raw[c["start"]:c["end"]]
    if len(payload) < 8:
        raise ValueError("Export chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    if 8 + count * 24 > len(payload):
        raise ValueError("Export count exceeds payload")
    rows = []
    for i in range(count):
        at = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", payload, at)
        name = cstring(payload, string_offset)
        rows.append({
            "index": i,
            "name": name,
            "uid": uid,
            "root": root,
            "type_id": type_id,
            "entry_file_offset": c["start"] + at,
        })
    return rows


def find_all(blob: bytes, needle: bytes) -> list[int]:
    out = []
    start = 0
    while True:
        at = blob.find(needle, start)
        if at < 0:
            return out
        out.append(at)
        start = at + 1


def chunk_for(chunks: list[dict], file_offset: int) -> dict | None:
    for c in chunks:
        if c["start"] <= file_offset < c["end"]:
            return {
                "kind": c["kind"],
                "payload_offset": file_offset - c["start"],
            }
    return None


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
                return raw[offset + rva - start: offset + rva - start + size]
        raise ValueError("Address outside file-backed PE section")

    def string(va: int) -> str:
        data = read(va, 256)
        return data.split(b"\0", 1)[0].decode("ascii")

    return read, string


def rtti_fields(exe: Path, type_ids: set[int]) -> dict[str, list[dict]]:
    raw = exe.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_EXE:
        return {f"0x{x:X}": [] for x in sorted(type_ids)}
    read, string = pe_reader(raw)
    result = {f"0x{x:X}": [] for x in sorted(type_ids)}
    for index in range(0x5000):
        try:
            field = read(ATTRS + index * 32, 32)
            name_ptr, _unused, offset, size, flags, _unused2, parent = struct.unpack_from(
                "<QQHHBBH", field
            )
            if parent not in type_ids or name_ptr == 0:
                continue
            name = string(name_ptr)
            if not name or any(ord(ch) < 32 or ord(ch) > 126 for ch in name):
                continue
            result[f"0x{parent:X}"].append({
                "attr_index": f"0x{index:X}",
                "field": name,
                "offset": f"0x{offset:X}",
                "size": size,
                "kind": flags >> 2,
            })
        except (ValueError, UnicodeDecodeError, struct.error):
            continue
    for rows in result.values():
        rows.sort(key=lambda x: int(x["offset"], 16))
    return result


def inspect_r_ui(path: Path, exe: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_R_UI:
        raise ValueError(f"Unexpected wad_r_ui.dcb SHA256: {digest}")
    chunks = parse_chunks(raw)
    exports = parse_exports(raw, chunks)
    data = one(chunks, 12)
    if data is None:
        raise ValueError("wad_r_ui.dcb has no data chunk")

    export_by_uid = {row["uid"]: row for row in exports}
    export_roots = sorted(exports, key=lambda row: row["root"])
    known = []
    type_ids = set()
    for name in MAP_ICON_NAMES:
        uid = name_hash(name)
        needle = struct.pack("<Q", uid)
        hits = find_all(raw, needle)
        export = export_by_uid.get(uid)
        if export is not None:
            type_ids.add(export["type_id"])
        hit_rows = []
        for hit in hits:
            where = chunk_for(chunks, hit)
            nearest = None
            if where and where["kind"] == 12:
                rel = where["payload_offset"]
                candidates = [row for row in export_roots if row["root"] <= rel]
                if candidates:
                    row = max(candidates, key=lambda x: x["root"])
                    nearest = {
                        "name": row["name"],
                        "type_id": f"0x{row['type_id']:X}",
                        "root": f"0x{row['root']:X}",
                        "delta": rel - row["root"],
                    }
                    type_ids.add(row["type_id"])
            hit_rows.append({
                "file_offset": hit,
                "chunk": where,
                "nearest_export_root": nearest,
            })
        known.append({
            "name": name,
            "uid": f"{uid:016X}",
            "direct_export": None if export is None else {
                "name": export["name"],
                "root": f"0x{export['root']:X}",
                "type_id": f"0x{export['type_id']:X}",
                "index": export["index"],
            },
            "occurrences": hit_rows,
        })

    candidate_uid = name_hash(RAVEN_MAP_ICON_NAME)
    return {
        "file": path.name,
        "sha256": digest,
        "bytes": len(raw),
        "chunk_kinds": [c["kind"] for c in chunks],
        "chunks": [{"kind": c["kind"], "size": c["size"]} for c in chunks],
        "export_count": len(exports),
        "export_type_counts": {
            f"0x{type_id:X}": sum(1 for row in exports if row["type_id"] == type_id)
            for type_id in sorted({row["type_id"] for row in exports})
        },
        "known_map_icons": known,
        "candidate": {
            "name": RAVEN_MAP_ICON_NAME,
            "uid": f"{candidate_uid:016X}",
            "export_uid_collision": candidate_uid in export_by_uid,
            "literal_present": RAVEN_MAP_ICON_NAME.encode("ascii") in raw,
        },
        "candidate_type_rtti": rtti_fields(exe, type_ids),
    }


def inspect_perm_visual_refs(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_PERM:
        raise ValueError(f"Unexpected wad_r_perm.dcb SHA256: {digest}")
    chunks = parse_chunks(raw)
    fields = {
        "DockPoint_class_uid": DOCK_COMPASS_UID,
        "DockPoint_IconName": DOCK_ICON_NAME,
        "DockPoint_InWorld_tMPIcon_Name": DOCK_INWORLD_NAME,
    }
    hits = {}
    for label, value in fields.items():
        hits[label] = [
            {"file_offset": off, "chunk": chunk_for(chunks, off)}
            for off in find_all(raw, struct.pack("<Q", value))
        ]
    literal_hits = find_all(raw, DOCK_INWORLD_LITERAL.encode("ascii"))
    candidate_uid = name_hash(RAVEN_COMPASS_VISUAL_NAME)
    return {
        "file": path.name,
        "sha256": digest,
        "field_hashes": {k: f"{v:016X}" for k, v in fields.items()},
        "hits": hits,
        "inworld_literal": DOCK_INWORLD_LITERAL,
        "inworld_literal_offsets": literal_hits,
        "candidate_visual": {
            "name": RAVEN_COMPASS_VISUAL_NAME,
            "uid": f"{candidate_uid:016X}",
            "hash_collision_in_perm": struct.pack("<Q", candidate_uid) in raw,
            "literal_present_in_perm": RAVEN_COMPASS_VISUAL_NAME.encode("ascii") in raw,
        },
    }


def scan_dcb_references(dc: Path) -> list[dict]:
    needles = {
        "DockPoint_IconName": struct.pack("<Q", DOCK_ICON_NAME),
        "DockPoint_InWorld_tMPIcon_Name": struct.pack("<Q", DOCK_INWORLD_NAME),
    }
    rows = []
    for path in sorted(dc.glob("*.dcb")):
        raw = path.read_bytes()
        item = {"file": path.name, "hits": {}}
        any_hit = False
        for label, needle in needles.items():
            offsets = find_all(raw, needle)
            if offsets:
                item["hits"][label] = offsets
                any_hit = True
        if any_hit:
            rows.append(item)
    return rows


def extracted_ui_candidates() -> dict:
    root = Path.home() / "AppData/Local/CompletionistMap/work/v0.10.2/r_ui-dds"
    if not root.is_dir():
        return {"directory": str(root), "present": False, "matching_files": []}
    keywords = ("compass", "dock", "marker", "mapicon", "inworld")
    names = []
    for path in sorted(root.iterdir()):
        if path.is_file() and any(k in path.name.lower() for k in keywords):
            names.append(path.name)
    return {"directory": str(root), "present": True, "matching_files": names}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path,
                    default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    dc = game / "exec/dc/pc_le"
    r_ui = dc / "wad_r_ui.dcb"
    perm = dc / "wad_r_perm.dcb"
    exe = game / "GoW.exe"
    for path in (r_ui, perm, exe):
        if not path.is_file():
            raise FileNotFoundError(path)

    report = {
        "result": "READ_ONLY_RAVEN_VISUAL_ISOLATION_ROUTE",
        "game_files_written": False,
        "decision_context": {
            "native_navigation_type": "DockPoint",
            "native_navigation_type_is_proven": True,
            "new_CompletionistRaven_compass_type_runtime_accepted": False,
            "reason": "ShowMarker rejected CompletionistRaven before queueing; do not repeat that class test.",
            "goal": "Keep DockPoint only as the internal proven navigation type while isolating Raven map/HUD artwork from real docks.",
        },
        "wad_r_ui": inspect_r_ui(r_ui, exe),
        "wad_r_perm_visual_refs": inspect_perm_visual_refs(perm),
        "cross_dcb_visual_hash_references": scan_dcb_references(dc),
        "extracted_r_ui_candidates": extracted_ui_candidates(),
        "next_gate": (
            "Use wad_r_ui export/type evidence to decide whether a dedicated goMapIconCompletionistRaven resource can be authored. "
            "Use the extracted r_ui candidates and DockPoint InWorld hash references to choose a per-Raven HUD visual route without globally reskinning DockPoint."
        ),
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("Report must stay outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {out}")
    print(f"wad_r_ui exports: {report['wad_r_ui']['export_count']}")
    print(f"wad_r_ui export types: {report['wad_r_ui']['export_type_counts']}")
    for row in report["wad_r_ui"]["known_map_icons"]:
        print(f"  {row['name']}: occurrences={len(row['occurrences'])} direct_export={row['direct_export'] is not None}")
    print(f"Reserved map icon: {RAVEN_MAP_ICON_NAME} / {report['wad_r_ui']['candidate']['uid']} collision={report['wad_r_ui']['candidate']['export_uid_collision']}")
    print(f"Extracted r_ui candidates: {len(report['extracted_r_ui_candidates']['matching_files'])}")
    print("No game files were modified.")


if __name__ == "__main__":
    main()
