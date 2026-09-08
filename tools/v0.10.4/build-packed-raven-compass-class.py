"""Build an OFFLINE packed CompletionistRaven CompassIconClass candidate.

The first v0.10.4 class experiment appended a cloned DockPoint record at the end
of wad_r_perm.dcb's data chunk. Runtime rejected the export as an invalid compass
class. A later read-only storage scan proved that all nine stock type-0x11E
CompassIconClass records form one exact contiguous 0x20-byte block ending at
0x4E2C50, immediately before COMPASS_GLOBALS.

This builder tests the packed-type-block hypothesis without touching the game:
- insert a DockPoint clone at 0x4E2C50, extending the stock 0x11E block to 10;
- shift every existing export root at/after the insertion by +0x20;
- preserve every stock relocation semantically by shifting relocation fields and
  targets across the insertion and rewriting only the affected relative deltas;
- add the independent CompletionistRaven type-0x11E export;
- leave chunks 11, 14 and 35 byte-identical.

Artwork intentionally remains a byte-for-byte DockPoint clone. This is only a
registration/runtime gate. No game, save, progression, map-marker state, or Lua
files are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
TYPE_ID = 0x11E
SOURCE_CLASS = "DockPoint"
NEW_CLASS = "CompletionistRaven"
RECORD_SIZE = 0x20
BLOCK_START = 0x4E2B30
INSERT_AT = 0x4E2C50
EXPECTED_STOCK_CLASS_ROOTS = [BLOCK_START + i * RECORD_SIZE for i in range(9)]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def parse_chunks(raw: bytes) -> list[dict]:
    chunks = []
    off = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        if flags != 0x10 or padded > len(raw):
            raise ValueError(f"invalid IFF chunk at {off:#x}")
        chunks.append({
            "kind": kind,
            "flags": flags,
            "header": raw[off:start],
            "payload": raw[start:end],
            "padding": raw[end:padded],
            "header_offset": off,
        })
        off = padded
    if off != len(raw):
        raise ValueError("chunk walk did not end at EOF")
    kinds = [c["kind"] for c in chunks]
    if kinds != [11, 12, 13, 14, 35, 15]:
        raise ValueError(f"unexpected wad_r_perm chunk layout: {kinds}")
    return chunks


def one(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    if len(rows) != 1:
        raise ValueError(f"expected one chunk {kind}, found {len(rows)}")
    return rows[0]


def cstring(blob: bytes, offset: int) -> str:
    if not 0 <= offset < len(blob):
        raise ValueError(f"string offset outside export chunk: {offset:#x}")
    end = blob.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated export name")
    return blob[offset:end].decode("ascii")


def parse_exports(payload: bytes) -> tuple[bytes, list[dict], bytes]:
    if len(payload) < 8:
        raise ValueError("export chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    entries_end = 8 + count * 24
    if entries_end > len(payload):
        raise ValueError("export table exceeds payload")
    rows = []
    seen_uids = set()
    for i in range(count):
        at = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", payload, at)
        name = cstring(payload, string_offset)
        if name_hash(name) != uid:
            raise ValueError(f"export UID mismatch for {name}")
        if uid in seen_uids:
            raise ValueError(f"duplicate export UID {uid:016X}")
        seen_uids.add(uid)
        rows.append({
            "index": i,
            "root": root,
            "type_id": type_id,
            "string_offset": string_offset,
            "uid": uid,
            "name": name,
        })
    return payload[:8], rows, payload[entries_end:]


def parse_relocations(payload: bytes, data: bytes) -> list[dict]:
    if len(payload) < 4:
        raise ValueError("relocation chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    if len(payload) != 4 + count * 4:
        raise ValueError("relocation chunk size/count mismatch")
    fields = struct.unpack_from(f"<{count}I", payload, 4) if count else ()

    # Important: wad_r_perm.dcb's stock relocation table is not guaranteed to
    # be sorted or unique. The earlier packed builder incorrectly imposed that
    # invariant and rejected the untouched stock file. Preserve the exact table
    # sequence (including any duplicate entries) and validate semantics instead.
    rows = []
    for field in fields:
        if field + 8 > len(data):
            raise ValueError(f"relocation field outside data: {field:#x}")
        delta = struct.unpack_from("<q", data, field)[0]
        target = field + delta
        if not 0 <= target < len(data):
            raise ValueError(f"relocation target outside data: {field:#x}->{target:#x}")
        rows.append({"field": field, "delta": delta, "target": target})
    return rows


def build_file(chunks: list[dict], replacements: dict[int, bytes]) -> bytes:
    out = bytearray()
    for chunk in chunks:
        payload = replacements.get(chunk["kind"], chunk["payload"])
        header = bytearray(chunk["header"])
        struct.pack_into("<I", header, 4, len(payload))
        out += header
        out += payload
        out += b"\0" * (align16(len(out)) - len(out))
    return bytes(out)


def shifted(offset: int) -> int:
    return offset + RECORD_SIZE if offset >= INSERT_AT else offset


def build_candidate(stock_raw: bytes) -> tuple[bytes, dict]:
    chunks = parse_chunks(stock_raw)
    data_chunk = one(chunks, 12)
    export_chunk = one(chunks, 13)
    reloc_chunk = one(chunks, 15)
    stock_data = bytes(data_chunk["payload"])
    export_header8, exports, export_tail = parse_exports(export_chunk["payload"])
    stock_relocs = parse_relocations(reloc_chunk["payload"], stock_data)
    stock_fields = [row["field"] for row in stock_relocs]
    stock_fields_sorted = stock_fields == sorted(stock_fields)
    stock_duplicate_field_entries = len(stock_fields) - len(set(stock_fields))

    if INSERT_AT + RECORD_SIZE > len(stock_data):
        raise ValueError("packed-class insertion point outside stock data")

    by_name = {e["name"]: e for e in exports}
    if SOURCE_CLASS not in by_name:
        raise ValueError("DockPoint export missing")
    if NEW_CLASS in by_name:
        raise ValueError("CompletionistRaven already exists")
    dock = by_name[SOURCE_CLASS]
    if dock["type_id"] != TYPE_ID or dock["root"] != 0x4E2BB0:
        raise ValueError("DockPoint type/root differs from researched layout")

    stock_compass = sorted((e for e in exports if e["type_id"] == TYPE_ID), key=lambda e: e["root"])
    stock_roots = [e["root"] for e in stock_compass]
    if stock_roots != EXPECTED_STOCK_CLASS_ROOTS:
        raise ValueError(f"stock CompassIconClass roots changed: {[hex(x) for x in stock_roots]}")

    # COMPASS_GLOBALS intentionally starts exactly at INSERT_AT in stock and is
    # the object that will move by +0x20 when the tenth CompassIconClass is
    # inserted. Reject only any *other* export occupying the new class span.
    unexpected_occupants = [
        e for e in exports
        if INSERT_AT <= e["root"] < INSERT_AT + RECORD_SIZE
        and not (
            e["name"] == "COMPASS_GLOBALS"
            and e["root"] == INSERT_AT
            and e["type_id"] == 0x11F
        )
    ]
    if unexpected_occupants:
        details = ", ".join(
            f"{e['name']}@0x{e['root']:X}/type=0x{e['type_id']:X}"
            for e in unexpected_occupants
        )
        raise ValueError(f"unexpected stock export occupies proposed Raven class slot: {details}")

    globals_exports = [e for e in exports if e["name"] == "COMPASS_GLOBALS"]
    if len(globals_exports) != 1 or globals_exports[0]["root"] != INSERT_AT or globals_exports[0]["type_id"] != 0x11F:
        raise ValueError("COMPASS_GLOBALS does not begin exactly at packed block end")

    dock_record = stock_data[dock["root"]:dock["root"] + RECORD_SIZE]
    if len(dock_record) != RECORD_SIZE:
        raise ValueError("short DockPoint record")

    # Insert the tenth 0x20-byte class into the packed stock type block.
    patched_data = bytearray(stock_data[:INSERT_AT] + dock_record + stock_data[INSERT_AT:])

    # Preserve all existing relative pointers semantically. The relocation list
    # stores the field locations; the pointed-to target is field + signed delta.
    # Inserting bytes can move the field, target, or both. Keep the relocation
    # entry ordering and duplicate-entry multiplicity exactly as stock authored it.
    patched_fields = []
    crossing_forward = 0
    crossing_backward = 0
    rewritten_deltas = 0
    for row in stock_relocs:
        old_field = row["field"]
        old_target = row["target"]
        new_field = shifted(old_field)
        new_target = shifted(old_target)
        new_delta = new_target - new_field
        if old_field < INSERT_AT <= old_target:
            crossing_forward += 1
        if old_target < INSERT_AT <= old_field:
            crossing_backward += 1
        if new_delta != row["delta"]:
            rewritten_deltas += 1
        struct.pack_into("<q", patched_data, new_field, new_delta)
        patched_fields.append(new_field)

    if len(patched_fields) != len(stock_fields):
        raise ValueError("patched relocation count changed before serialization")
    patched_reloc_payload = struct.pack("<I", len(patched_fields)) + (
        struct.pack(f"<{len(patched_fields)}I", *patched_fields) if patched_fields else b""
    )

    # Shift roots for every pre-existing exported object that moved in chunk 12.
    # Adding one 24-byte export entry before the existing string tail shifts every
    # existing export string offset by 24 bytes.
    new_uid = name_hash(NEW_CLASS)
    if any(e["uid"] == new_uid for e in exports):
        raise ValueError(f"CompletionistRaven UID collision: {new_uid:016X}")

    entry_shift = 24
    entries = bytearray()
    for e in exports:
        entries += struct.pack(
            "<IIQQ",
            shifted(e["root"]),
            e["type_id"],
            e["string_offset"] + entry_shift,
            e["uid"],
        )

    new_string_offset = 8 + (len(exports) + 1) * 24 + len(export_tail)
    entries += struct.pack("<IIQQ", INSERT_AT, TYPE_ID, new_string_offset, new_uid)
    patched_header8 = bytearray(export_header8)
    struct.pack_into("<I", patched_header8, 0, len(exports) + 1)
    patched_export_payload = (
        bytes(patched_header8)
        + bytes(entries)
        + export_tail
        + NEW_CLASS.encode("ascii")
        + b"\0"
    )

    replacements = {
        12: bytes(patched_data),
        13: patched_export_payload,
        15: patched_reloc_payload,
    }
    candidate = build_file(chunks, replacements)

    # Full structural/semantic validation after serialization.
    out_chunks = parse_chunks(candidate)
    out_data = one(out_chunks, 12)["payload"]
    _out_header8, out_exports, _out_tail = parse_exports(one(out_chunks, 13)["payload"])
    out_relocs = parse_relocations(one(out_chunks, 15)["payload"], out_data)
    out_by_name = {e["name"]: e for e in out_exports}

    raven = out_by_name.get(NEW_CLASS)
    if raven is None or raven["type_id"] != TYPE_ID or raven["root"] != INSERT_AT:
        raise ValueError("CompletionistRaven export failed validation")
    if out_data[INSERT_AT:INSERT_AT + RECORD_SIZE] != dock_record:
        raise ValueError("packed Raven record is not byte-identical to DockPoint")

    candidate_compass = sorted((e for e in out_exports if e["type_id"] == TYPE_ID), key=lambda e: e["root"])
    expected_candidate_roots = EXPECTED_STOCK_CLASS_ROOTS + [INSERT_AT]
    if [e["root"] for e in candidate_compass] != expected_candidate_roots:
        raise ValueError("candidate CompassIconClass block is not exact 10x0x20 stride")

    for e in exports:
        cur = out_by_name.get(e["name"])
        if cur is None:
            raise ValueError(f"stock export disappeared: {e['name']}")
        if cur["uid"] != e["uid"] or cur["type_id"] != e["type_id"] or cur["root"] != shifted(e["root"]):
            raise ValueError(f"stock export semantics changed: {e['name']}")

    if len(out_relocs) != len(stock_relocs):
        raise ValueError("relocation count changed")
    if [r["field"] for r in out_relocs] != patched_fields:
        raise ValueError("relocation entry sequence/multiplicity changed")
    for old, new in zip(stock_relocs, out_relocs):
        if new["field"] != shifted(old["field"]) or new["target"] != shifted(old["target"]):
            raise ValueError(
                f"relocation semantic mismatch: {old['field']:#x}->{old['target']:#x} "
                f"became {new['field']:#x}->{new['target']:#x}"
            )

    unchanged_payloads = {}
    for kind in (11, 14, 35):
        unchanged_payloads[str(kind)] = one(chunks, kind)["payload"] == one(out_chunks, kind)["payload"]
    if not all(unchanged_payloads.values()):
        raise ValueError("metadata chunk 11/14/35 changed")

    if out_data[:INSERT_AT] != stock_data[:INSERT_AT]:
        raise ValueError("data prefix before packed insertion changed")

    globals_after = out_by_name["COMPASS_GLOBALS"]
    if globals_after["root"] != INSERT_AT + RECORD_SIZE:
        raise ValueError("COMPASS_GLOBALS did not shift to 0x4E2C70")

    report = {
        "result": "OFFLINE_PACKED_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT",
        "game_files_written": False,
        "installed": False,
        "source_sha256": EXPECTED,
        "candidate_sha256": sha256(candidate),
        "source_bytes": len(stock_raw),
        "candidate_bytes": len(candidate),
        "architecture": {
            "hypothesis": "CompassIconClass runtime registration depends on membership in the packed type-0x11E storage block rather than export presence alone.",
            "type_id": "0x11E",
            "record_size": RECORD_SIZE,
            "stock_block_start": f"0x{BLOCK_START:X}",
            "stock_block_end_exclusive": f"0x{INSERT_AT:X}",
            "stock_class_count": 9,
            "candidate_class_count": 10,
            "candidate_block_end_exclusive": f"0x{INSERT_AT + RECORD_SIZE:X}",
            "new_class_root": f"0x{INSERT_AT:X}",
            "next_stock_object_before": "COMPASS_GLOBALS",
            "next_stock_object_root_before": f"0x{INSERT_AT:X}",
            "next_stock_object_root_after": f"0x{INSERT_AT + RECORD_SIZE:X}",
        },
        "new_class": {
            "name": NEW_CLASS,
            "uid": f"{new_uid:016X}",
            "root": f"0x{INSERT_AT:X}",
            "record_bytes_equal_dockpoint": True,
            "visuals_intentionally_clone_dockpoint": True,
        },
        "exports": {
            "before": len(exports),
            "after": len(out_exports),
            "all_stock_semantics_preserved_with_root_shift": True,
        },
        "relocations": {
            "count": len(stock_relocs),
            "count_unchanged": True,
            "stock_fields_sorted": stock_fields_sorted,
            "stock_duplicate_field_entries": stock_duplicate_field_entries,
            "entry_sequence_and_multiplicity_preserved": True,
            "fields_shifted_at_or_after_insertion": sum(1 for r in stock_relocs if r["field"] >= INSERT_AT),
            "targets_shifted_at_or_after_insertion": sum(1 for r in stock_relocs if r["target"] >= INSERT_AT),
            "forward_crossing_pointers": crossing_forward,
            "backward_crossing_pointers": crossing_backward,
            "relative_deltas_rewritten": rewritten_deltas,
            "all_targets_semantically_preserved": True,
        },
        "unchanged_metadata_chunk_payloads": unchanged_payloads,
        "validation": {
            "source_compass_roots": [f"0x{x:X}" for x in EXPECTED_STOCK_CLASS_ROOTS],
            "candidate_compass_roots": [f"0x{x:X}" for x in expected_candidate_roots],
            "candidate_exact_0x20_stride": True,
            "COMPASS_GLOBALS_shifted_to": f"0x{globals_after['root']:X}",
            "stock_data_prefix_before_insertion_byte_identical": True,
            "all_stock_exports_preserved": True,
            "all_stock_relocations_preserved_semantically": True,
        },
        "safety": {
            "save_state_written": False,
            "progression_state_written": False,
            "map_marker_state_written": False,
            "game_directory_written": False,
            "lua_written": False,
            "map_raven_artwork_touched": False,
            "real_dock_visuals_touched": False,
        },
        "next_gate": (
            "Run a registration-only runtime proof with CompletionistRaven still cloning DockPoint visuals. "
            "If ShowMarker accepts the class and native direction/distance remain correct, then clone the "
            "HUD and in-world visual resources for Raven artwork without changing real DockPoint resources."
        ),
    }
    return candidate, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)
    stock_raw = source.read_bytes()
    digest = sha256(stock_raw)
    if digest != EXPECTED:
        raise ValueError(f"wad_r_perm.dcb is not the researched stock file: {digest}")

    output = args.output.resolve()
    report_path = args.report.resolve()
    if output.is_relative_to(game) or report_path.is_relative_to(game):
        raise ValueError("offline candidate/report must stay outside the game directory")

    candidate, report = build_candidate(stock_raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if source.read_bytes() != stock_raw:
        raise ValueError("source wad_r_perm.dcb changed during offline build")

    print("OFFLINE_PACKED_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT")
    print(f"  class:            {NEW_CLASS}")
    print(f"  uid:              {name_hash(NEW_CLASS):016X}")
    print(f"  packed root:      0x{INSERT_AT:X}")
    print(f"  candidate SHA256: {sha256(candidate)}")
    print(f"  output:           {output}")
    print(f"  report:           {report_path}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
