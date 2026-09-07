"""Build an OFFLINE wad_r_perm.dcb with a dedicated CompletionistRaven class.

This is a construction proof only. It never installs or writes into the God of
War directory. The new CompassIconClass is a byte-for-byte clone of DockPoint's
0x20-byte class record but is exported under the independent name
CompletionistRaven. That proves class separation without yet changing artwork.

The builder preserves all stock data bytes/exports, appends one aligned record
to chunk 12, inserts one type-0x11E export into chunk 13, adjusts export string
offsets, and leaves all other chunk payloads byte-identical.
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

EXPECTED = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
TYPE_ID = 0x11E
SOURCE_CLASS = "DockPoint"
NEW_CLASS = "CompletionistRaven"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


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
        padded_end = align(end, 16)
        if padded_end > len(raw):
            raise ValueError("Chunk padding exceeds EOF")
        chunks.append(
            {
                "kind": kind,
                "flags": flags,
                "header": raw[off:start],
                "payload": raw[start:end],
                "padding": raw[end:padded_end],
                "file_header_offset": off,
            }
        )
        off = padded_end
    if off != len(raw):
        raise ValueError("Chunk walk did not end exactly at EOF")
    kinds = [c["kind"] for c in chunks]
    if kinds != [11, 12, 13, 14, 35, 15]:
        raise ValueError(f"Unexpected wad_r_perm chunk order: {kinds}")
    return chunks


def only(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one chunk {kind}")
    return rows[0]


def cstring(blob: bytes, offset: int) -> str:
    if not 0 <= offset < len(blob):
        raise ValueError(f"String offset outside export chunk: {offset:#x}")
    end = blob.find(b"\0", offset)
    if end < 0:
        raise ValueError("Unterminated export name")
    return blob[offset:end].decode("ascii")


def parse_exports(payload: bytes) -> tuple[int, bytes, list[dict], bytes]:
    if len(payload) < 8:
        raise ValueError("Export chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    entries_end = 8 + count * 24
    if entries_end > len(payload):
        raise ValueError("Export count exceeds chunk payload")
    header8 = payload[:8]
    rows = []
    uids = set()
    for i in range(count):
        at = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", payload, at)
        name = cstring(payload, string_offset)
        if native.name_hash(name) != uid:
            raise ValueError(f"Export UID mismatch for {name}")
        if uid in uids:
            raise ValueError(f"Duplicate export UID {uid:016X}")
        uids.add(uid)
        rows.append(
            {
                "root": root,
                "type_id": type_id,
                "string_offset": string_offset,
                "uid": uid,
                "name": name,
            }
        )
    return count, header8, rows, payload[entries_end:]


def build_file(chunks: list[dict], replacements: dict[int, bytes]) -> bytes:
    out = bytearray()
    for c in chunks:
        payload = replacements.get(c["kind"], c["payload"])
        header = bytearray(c["header"])
        struct.pack_into("<I", header, 4, len(payload))
        out += header
        out += payload
        out += b"\0" * (align(len(out), 16) - len(out))
    return bytes(out)


def validate_patched(raw: bytes, stock_data: bytes, stock_exports: list[dict],
                     expected_root: int, expected_record: bytes) -> dict:
    chunks = parse_chunks(raw)
    data = only(chunks, 12)["payload"]
    exports_payload = only(chunks, 13)["payload"]
    count, _header8, rows, _tail = parse_exports(exports_payload)
    by_name = {r["name"]: r for r in rows}

    if count != len(stock_exports) + 1:
        raise ValueError("Patched export count mismatch")
    if NEW_CLASS not in by_name:
        raise ValueError("CompletionistRaven export missing")
    raven = by_name[NEW_CLASS]
    if raven["type_id"] != TYPE_ID or raven["root"] != expected_root:
        raise ValueError("CompletionistRaven export has wrong type/root")
    if data[expected_root:expected_root + 0x20] != expected_record:
        raise ValueError("CompletionistRaven record bytes differ from expected clone")
    if data[:len(stock_data)] != stock_data:
        raise ValueError("Stock data prefix changed")

    stock_by_name = {r["name"]: r for r in stock_exports}
    for name, original in stock_by_name.items():
        current = by_name.get(name)
        if current is None:
            raise ValueError(f"Stock export disappeared: {name}")
        for field in ("root", "type_id", "uid"):
            if current[field] != original[field]:
                raise ValueError(f"Stock export changed: {name} field={field}")

    return {
        "export_count": count,
        "completionist_uid": f"{raven['uid']:016X}",
        "completionist_root": f"0x{raven['root']:X}",
        "stock_export_semantics_unchanged": True,
        "stock_data_prefix_unchanged": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path,
                    default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)
    source_raw = source.read_bytes()
    source_hash = sha256(source_raw)
    if source_hash != EXPECTED:
        raise ValueError(f"Unexpected stock wad_r_perm.dcb SHA256: {source_hash}")

    output = args.output.resolve()
    report_path = args.report.resolve()
    if output.is_relative_to(game) or report_path.is_relative_to(game):
        raise ValueError("Offline build/report must stay outside the game directory")

    chunks = parse_chunks(source_raw)
    data_chunk = only(chunks, 12)
    export_chunk = only(chunks, 13)
    stock_data = data_chunk["payload"]
    count, export_header8, exports, export_tail = parse_exports(export_chunk["payload"])

    by_name = {row["name"]: row for row in exports}
    if NEW_CLASS in by_name:
        raise ValueError(f"{NEW_CLASS} already exists in stock exports")
    if SOURCE_CLASS not in by_name:
        raise ValueError(f"{SOURCE_CLASS} export not found")
    dock = by_name[SOURCE_CLASS]
    if dock["type_id"] != TYPE_ID:
        raise ValueError("DockPoint is not type 0x11E")
    if dock["root"] + 0x20 > len(stock_data):
        raise ValueError("DockPoint record outside data chunk")

    dock_record = stock_data[dock["root"]:dock["root"] + 0x20]
    new_root = align(len(stock_data), 8)
    data_pad = new_root - len(stock_data)
    patched_data = stock_data + (b"\0" * data_pad) + dock_record

    new_uid = native.name_hash(NEW_CLASS)
    if any(row["uid"] == new_uid for row in exports):
        raise ValueError(f"Reserved {NEW_CLASS} UID collides with stock export")

    # Inserting a new 24-byte entry before the export string area shifts every
    # existing string offset by 24. Roots and UIDs remain unchanged.
    shift = 24
    entries = bytearray()
    for row in exports:
        entries += struct.pack(
            "<IIQQ",
            row["root"], row["type_id"], row["string_offset"] + shift, row["uid"]
        )
    new_string_offset = 8 + (count + 1) * 24 + len(export_tail)
    entries += struct.pack("<IIQQ", new_root, TYPE_ID, new_string_offset, new_uid)

    patched_export_header = bytearray(export_header8)
    struct.pack_into("<I", patched_export_header, 0, count + 1)
    patched_exports = bytes(patched_export_header) + bytes(entries) + export_tail + NEW_CLASS.encode("ascii") + b"\0"

    replacements = {12: patched_data, 13: patched_exports}
    patched_raw = build_file(chunks, replacements)

    validation = validate_patched(patched_raw, stock_data, exports, new_root, dock_record)
    patched_chunks = parse_chunks(patched_raw)

    # Unchanged chunk payloads are required to remain byte-identical.
    unchanged_payloads = {}
    for kind in (11, 14, 35, 15):
        unchanged_payloads[str(kind)] = (
            only(chunks, kind)["payload"] == only(patched_chunks, kind)["payload"]
        )
    if not all(unchanged_payloads.values()):
        raise ValueError("An unrelated chunk payload changed")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched_raw)

    report = {
        "result": "OFFLINE_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT",
        "game_files_written": False,
        "installed": False,
        "source": str(source),
        "source_sha256": source_hash,
        "output": str(output),
        "output_sha256": sha256(patched_raw),
        "source_bytes": len(source_raw),
        "output_bytes": len(patched_raw),
        "chunk_kinds": [c["kind"] for c in patched_chunks],
        "stock_export_count": count,
        "patched_export_count": count + 1,
        "source_class": {
            "name": SOURCE_CLASS,
            "uid": f"{dock['uid']:016X}",
            "root": f"0x{dock['root']:X}",
        },
        "new_class": {
            "name": NEW_CLASS,
            "uid": f"{new_uid:016X}",
            "root": f"0x{new_root:X}",
            "type_id": "0x11E",
            "record_bytes_equal_dockpoint": True,
            "visuals_intentionally_still_clone_dockpoint": True,
        },
        "data_padding_before_new_record": data_pad,
        "unchanged_chunk_payloads": unchanged_payloads,
        "validation": validation,
        "next_gate": (
            "Runtime registration-only proof for CompletionistRaven, still using cloned DockPoint visuals. "
            "Do not change artwork until the independent native class resolves safely."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("OFFLINE_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT")
    print(f"  stock exports:   {count}")
    print(f"  patched exports: {count + 1}")
    print(f"  class:           {NEW_CLASS}")
    print(f"  uid:             {new_uid:016X}")
    print(f"  root:            0x{new_root:X}")
    print(f"  output:          {output}")
    print(f"  report:          {report_path}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
