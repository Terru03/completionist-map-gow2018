"""Decode the small stock wad_r_ui.dcb region that references map-icon resources.

Read-only v0.10.4 tool. This is intentionally narrow: it follows the single
WAD_R_UI export, decodes its non-empty relative-array fields, and annotates the
16-byte slots around known goMapIcon hashes. It also labels qwords that match
hashes from the already-extracted r_ui DDS filenames. The goal is to identify a
safe stock row/template for an offline goMapIconCompletionistRaven build without
changing the game or repeating the failed custom CompassIconClass experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

EXPECTED_R_UI = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
RAVEN_NAME = "goMapIconCompletionistRaven"
KNOWN_ICON_NAMES = [
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
ROOT_FIELDS = [
    ("GOPool", 0x00),
    ("MemoryPools", 0x10),
    ("MemoryLua", 0x20),
    ("RequiredPickups", 0x30),
    ("DependentResourceWads", 0x40),
    ("Varint", 0x50),
    ("Varbool", 0x60),
    ("Varfloat", 0x70),
    ("Varstring", 0x80),
]
HEX_SUFFIX = re.compile(r"_([0-9A-Fa-f]{16})\.dds$")


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def align16(value: int) -> int:
    return (value + 15) & ~15


def parse_chunks(raw: bytes) -> dict[int, dict]:
    chunks: dict[int, dict] = {}
    off = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or kind in chunks or end > len(raw):
            raise ValueError(f"invalid chunk at {off:#x}")
        chunks[kind] = {"header": off, "start": start, "end": end, "size": size}
        off = align16(end)
    if off != len(raw):
        raise ValueError("chunk walk did not end at EOF")
    return chunks


def parse_relocations(raw: bytes, chunks: dict[int, dict]) -> list[int]:
    c = chunks[15]
    payload = raw[c["start"]:c["end"]]
    count = struct.unpack_from("<I", payload, 0)[0]
    if len(payload) != 4 + count * 4:
        raise ValueError("invalid relocation chunk")
    return list(struct.unpack_from(f"<{count}I", payload, 4))


def cstring(blob: bytes, off: int) -> str:
    end = blob.find(b"\0", off)
    if off < 0 or end < off:
        raise ValueError("invalid C string")
    return blob[off:end].decode("ascii")


def parse_exports(raw: bytes, chunks: dict[int, dict]) -> list[dict]:
    c = chunks[13]
    p = raw[c["start"]:c["end"]]
    count = struct.unpack_from("<I", p, 0)[0]
    rows = []
    for i in range(count):
        at = 8 + 24 * i
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", p, at)
        rows.append({
            "name": cstring(p, string_offset),
            "root": root,
            "type_id": type_id,
            "uid": uid,
        })
    return rows


def extracted_dds_labels() -> tuple[str, dict[int, str]]:
    root = Path.home() / "AppData/Local/CompletionistMap/work/v0.10.2/r_ui-dds"
    labels: dict[int, str] = {}
    if root.is_dir():
        for path in root.iterdir():
            if not path.is_file():
                continue
            match = HEX_SUFFIX.search(path.name)
            if match:
                labels[int(match.group(1), 16)] = path.name
    return str(root), labels


def qword_label(value: int, known: dict[int, str], dds: dict[int, str]) -> list[str]:
    labels = []
    if value in known:
        labels.append(known[value])
    if value in dds:
        labels.append(dds[value])
    return labels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path,
                    default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    if not path.is_file():
        raise FileNotFoundError(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_R_UI:
        raise ValueError(f"unexpected wad_r_ui.dcb SHA256: {digest}")

    chunks = parse_chunks(raw)
    if set(chunks) != {11, 12, 13, 14, 15}:
        raise ValueError(f"unexpected chunk kinds: {sorted(chunks)}")
    data_chunk = chunks[12]
    blob = raw[data_chunk["start"]:data_chunk["end"]]
    relocs = parse_relocations(raw, chunks)
    reloc_set = set(relocs)
    exports = parse_exports(raw, chunks)
    if len(exports) != 1 or exports[0]["name"] != "WAD_R_UI" or exports[0]["type_id"] != 0x10F:
        raise ValueError("unexpected WAD_R_UI export layout")
    root = exports[0]["root"]

    known = {name_hash(name): name for name in KNOWN_ICON_NAMES}
    raven_uid = name_hash(RAVEN_NAME)
    known[raven_uid] = RAVEN_NAME
    dds_dir, dds = extracted_dds_labels()

    root_fields = []
    pointer_targets = []
    for name, rel in ROOT_FIELDS:
        field = root + rel
        qword = struct.unpack_from("<Q", blob, field)[0]
        count = struct.unpack_from("<I", blob, field + 8)[0]
        relocated = field in reloc_set
        target = None
        delta = None
        if relocated:
            delta = struct.unpack_from("<q", blob, field)[0]
            target = field + delta
            if not 0 <= target < len(blob):
                raise ValueError(f"{name} pointer target outside data chunk")
            pointer_targets.append(target)
        root_fields.append({
            "field": name,
            "offset": f"0x{field:X}",
            "relocated": relocated,
            "raw_qword": f"0x{qword:016X}",
            "count": count,
            "target": None if target is None else f"0x{target:X}",
            "signed_delta": delta,
        })

    relocation_rows = []
    for field in relocs:
        delta = struct.unpack_from("<q", blob, field)[0]
        target = field + delta
        relocation_rows.append({
            "field": f"0x{field:X}",
            "target": f"0x{target:X}",
            "signed_delta": delta,
            "root_relative": field - root,
        })

    # All stock goMapIcon hashes live very close together. Decode a narrow aligned
    # window around the first/last hit rather than dumping the DCB.
    icon_hits = []
    for uid, label in known.items():
        needle = struct.pack("<Q", uid)
        start = 0
        while True:
            at = blob.find(needle, start)
            if at < 0:
                break
            icon_hits.append((at, uid, label))
            start = at + 1
    stock_hits = [(o, u, l) for o, u, l in icon_hits if l != RAVEN_NAME]
    if not stock_hits:
        raise ValueError("known map-icon hashes were not found")
    first = min(o for o, _, _ in stock_hits)
    last = max(o for o, _, _ in stock_hits)
    window_start = max(0, (first - 0x40) & ~0xF)
    window_end = min(len(blob), align16(last + 0x50))

    slots = []
    for off in range(window_start, window_end, 0x10):
        a, b = struct.unpack_from("<QQ", blob, off)
        slots.append({
            "offset": f"0x{off:X}",
            "file_offset": f"0x{data_chunk['start'] + off:X}",
            "qword0": f"0x{a:016X}",
            "qword0_labels": qword_label(a, known, dds),
            "qword1": f"0x{b:016X}",
            "qword1_labels": qword_label(b, known, dds),
            "relocation_at_qword0": off in reloc_set,
            "relocation_at_qword1": (off + 8) in reloc_set,
        })

    # Annotate exact known hits with the surrounding 16-byte slot and neighbour
    # qwords. This makes DockPoint's template relationships easy to compare.
    hit_rows = []
    for off, uid, label in sorted(stock_hits):
        slot = off & ~0xF
        neighbour_start = max(0, slot - 0x10)
        neighbour_end = min(len(blob), slot + 0x20)
        qwords = []
        for qoff in range(neighbour_start, neighbour_end, 8):
            value = struct.unpack_from("<Q", blob, qoff)[0]
            qwords.append({
                "offset": f"0x{qoff:X}",
                "value": f"0x{value:016X}",
                "labels": qword_label(value, known, dds),
                "relocated": qoff in reloc_set,
            })
        hit_rows.append({
            "name": label,
            "uid": f"{uid:016X}",
            "offset": f"0x{off:X}",
            "slot_base": f"0x{slot:X}",
            "slot_delta": off - slot,
            "neighbour_qwords": qwords,
        })

    report = {
        "result": "READ_ONLY_R_UI_MAP_ICON_LAYOUT_DECODED",
        "game_files_written": False,
        "wad_r_ui": {
            "sha256": digest,
            "data_bytes": len(blob),
            "relocation_count": len(relocs),
            "export": {
                "name": exports[0]["name"],
                "type_id": f"0x{exports[0]['type_id']:X}",
                "root": f"0x{root:X}",
            },
        },
        "root_fields": root_fields,
        "relocations": relocation_rows,
        "map_icon_hash_window": {
            "start": f"0x{window_start:X}",
            "end": f"0x{window_end:X}",
            "slots_16_bytes": slots,
        },
        "known_icon_hits": hit_rows,
        "candidate": {
            "name": RAVEN_NAME,
            "uid": f"{raven_uid:016X}",
            "already_present": any(label == RAVEN_NAME for _, _, label in icon_hits),
        },
        "dds_hash_labels": {
            "directory": dds_dir,
            "count": len(dds),
        },
        "next_gate": (
            "If the DockPoint and neighbouring goMapIcon rows resolve into a repeatable fixed-size "
            "table/template, clone only the required stock row offline and substitute the Raven name/resource "
            "references. Reparse before any runtime installation."
        ),
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("output must remain outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {out}")
    print(f"WAD_R_UI relocations: {len(relocs)}")
    print(f"Known map-icon hits: {len(hit_rows)}")
    print(f"Icon window: 0x{window_start:X}-0x{window_end:X}")
    print("No game files were modified.")


if __name__ == "__main__":
    main()
