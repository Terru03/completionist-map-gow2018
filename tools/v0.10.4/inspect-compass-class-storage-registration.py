"""Inspect how stock CompassIconClass objects are stored and registered in wad_r_perm.dcb.

Read-only. The first CompletionistRaven builder appended a cloned 0x20 record to
the end of the data chunk and added an export, but the game rejected the class
as an invalid compass type. Stock type-0x11E records are visibly clustered near
0x4E2B30, so this probe tests the stronger hypothesis that they belong to a
contiguous typed block and/or a parent array/metadata registration structure.

No game files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
TYPE_ID = 0x11E
RECORD_SIZE = 0x20


def align16(v: int) -> int:
    return (v + 15) & ~15


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def parse_chunks(raw: bytes) -> list[dict]:
    out = []
    off = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or end > len(raw):
            raise ValueError(f"invalid IFF chunk at {off:#x}")
        out.append({"kind": kind, "header": off, "start": start, "end": end, "size": size})
        off = align16(end)
    if off != len(raw):
        raise ValueError("chunk walk did not end at EOF")
    return out


def one(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    if len(rows) != 1:
        raise ValueError(f"expected one chunk {kind}, found {len(rows)}")
    return rows[0]


def cstring(blob: bytes, offset: int) -> str:
    if not 0 <= offset < len(blob):
        raise ValueError("string offset outside export chunk")
    end = blob.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated export name")
    return blob[offset:end].decode("ascii")


def parse_exports(payload: bytes) -> list[dict]:
    count = struct.unpack_from("<I", payload, 0)[0]
    if 8 + count * 24 > len(payload):
        raise ValueError("export table exceeds payload")
    rows = []
    for i in range(count):
        at = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", payload, at)
        name = cstring(payload, string_offset)
        if name_hash(name) != uid:
            raise ValueError(f"export UID mismatch for {name}")
        rows.append({"index": i, "root": root, "type_id": type_id, "uid": uid, "name": name})
    return rows


def parse_relocations(payload: bytes, data: bytes) -> list[dict]:
    if len(payload) < 4:
        raise ValueError("relocation chunk too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    if len(payload) != 4 + count * 4:
        raise ValueError("relocation chunk size/count mismatch")
    fields = struct.unpack_from(f"<{count}I", payload, 4) if count else ()
    rows = []
    for field in fields:
        if field + 8 > len(data):
            raise ValueError(f"relocation field outside data: {field:#x}")
        delta = struct.unpack_from("<q", data, field)[0]
        target = field + delta
        if not 0 <= target < len(data):
            raise ValueError(f"relocation target outside data: field={field:#x} target={target:#x}")
        rows.append({"field": field, "delta": delta, "target": target})
    return rows


def find_all(blob: bytes, needle: bytes, limit: int = 64) -> dict:
    offsets = []
    at = 0
    while True:
        i = blob.find(needle, at)
        if i < 0:
            break
        if len(offsets) < limit:
            offsets.append(i)
        at = i + 1
    return {"count": len(offsets) if at == 0 else None, "offsets": offsets}


def all_offsets(blob: bytes, needle: bytes, cap: int = 128) -> tuple[int, list[int]]:
    count = 0
    offsets = []
    at = 0
    while True:
        i = blob.find(needle, at)
        if i < 0:
            break
        count += 1
        if len(offsets) < cap:
            offsets.append(i)
        at = i + 1
    return count, offsets


def hex_window(blob: bytes, center: int, radius: int = 48) -> dict:
    start = max(0, center - radius)
    end = min(len(blob), center + radius)
    return {"start": f"0x{start:X}", "end": f"0x{end:X}", "hex": blob[start:end].hex().upper()}


def metadata_summary(blob: bytes, *, block_start: int, block_end: int,
                     roots: list[int], compass_uids: list[int]) -> dict:
    patterns = {
        "type_id_u32": struct.pack("<I", TYPE_ID),
        "count_9_u32": struct.pack("<I", len(roots)),
        "block_start_u32": struct.pack("<I", block_start),
        "block_end_u32": struct.pack("<I", block_end),
        "type_then_count": struct.pack("<II", TYPE_ID, len(roots)),
        "count_then_type": struct.pack("<II", len(roots), TYPE_ID),
    }
    hits = {}
    for label, needle in patterns.items():
        count, offsets = all_offsets(blob, needle, 32)
        hits[label] = {"count": count, "offsets": [f"0x{x:X}" for x in offsets]}

    root_hits = {}
    for root in roots:
        count, offsets = all_offsets(blob, struct.pack("<I", root), 8)
        if count:
            root_hits[f"0x{root:X}"] = {"count": count, "offsets": [f"0x{x:X}" for x in offsets]}

    uid_hits = {}
    for uid in compass_uids:
        count, offsets = all_offsets(blob, struct.pack("<Q", uid), 8)
        if count:
            uid_hits[f"{uid:016X}"] = {"count": count, "offsets": [f"0x{x:X}" for x in offsets]}

    interesting = []
    for off_hex in hits["type_id_u32"]["offsets"][:12]:
        off = int(off_hex, 16)
        interesting.append({"reason": "type_id", "offset": off_hex, "window": hex_window(blob, off)})
    return {
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "pattern_hits": hits,
        "compass_root_hits": root_hits,
        "compass_uid_hits": uid_hits,
        "type_id_windows": interesting,
    }


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
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED:
        raise ValueError(f"wad_r_perm.dcb is not the researched stock file: {digest}")

    chunks = parse_chunks(raw)
    if [c["kind"] for c in chunks] != [11, 12, 13, 14, 35, 15]:
        raise ValueError(f"unexpected chunk layout: {[c['kind'] for c in chunks]}")
    data_c = one(chunks, 12)
    exp_c = one(chunks, 13)
    rel_c = one(chunks, 15)
    data = raw[data_c["start"]:data_c["end"]]
    exports_blob = raw[exp_c["start"]:exp_c["end"]]
    rel_blob = raw[rel_c["start"]:rel_c["end"]]
    exports = parse_exports(exports_blob)
    relocs = parse_relocations(rel_blob, data)

    compass = [e for e in exports if e["type_id"] == TYPE_ID]
    if len(compass) != 9:
        raise ValueError(f"expected 9 stock CompassIconClass exports, found {len(compass)}")
    compass_sorted = sorted(compass, key=lambda e: e["root"])
    roots = [e["root"] for e in compass_sorted]
    expected_roots = list(range(min(roots), min(roots) + len(roots) * RECORD_SIZE, RECORD_SIZE))
    block_start = min(roots)
    block_end = block_start + len(roots) * RECORD_SIZE
    contiguous = roots == expected_roots

    # Find relocation pointers into the class block. If a parent array/header
    # owns these records, its pointer should normally resolve to block_start and
    # its +8 word often carries the array count in this DCB family.
    into_block = [r for r in relocs if block_start <= r["target"] < block_end]
    to_start = [r for r in relocs if r["target"] == block_start]
    relocation_contexts = []
    for r in to_start[:32]:
        f = r["field"]
        count_at_plus8 = struct.unpack_from("<I", data, f + 8)[0] if f + 12 <= len(data) else None
        u32_plus12 = struct.unpack_from("<I", data, f + 12)[0] if f + 16 <= len(data) else None
        relocation_contexts.append({
            "field": f"0x{f:X}",
            "target": f"0x{r['target']:X}",
            "delta": r["delta"],
            "u32_at_plus8": count_at_plus8,
            "u32_at_plus12": u32_plus12,
            "looks_like_array_header_count_9": count_at_plus8 == len(compass),
            "window": hex_window(data, f, 64),
        })

    by_root = {}
    for e in exports:
        by_root.setdefault(e["root"], []).append(e)
    compass_rows = []
    for e in compass_sorted:
        refs = [r for r in relocs if r["target"] == e["root"]]
        compass_rows.append({
            "name": e["name"],
            "uid": f"{e['uid']:016X}",
            "root": f"0x{e['root']:X}",
            "export_index": e["index"],
            "record_hex": data[e["root"]:e["root"] + RECORD_SIZE].hex().upper(),
            "relocation_refs_to_root": [f"0x{r['field']:X}" for r in refs],
        })

    # Nearest export roots around the typed block help distinguish a genuine
    # packed type block from a coincidental run of records.
    rooted = sorted((e for e in exports if 0 <= e["root"] < len(data)), key=lambda e: (e["root"], e["index"]))
    before = [e for e in rooted if e["root"] < block_start][-8:]
    after = [e for e in rooted if e["root"] >= block_end][:8]
    def compact_export(e: dict) -> dict:
        return {"name": e["name"], "root": f"0x{e['root']:X}", "type_id": f"0x{e['type_id']:X}", "index": e["index"]}

    metadata = {}
    for kind in (11, 14, 35):
        c = one(chunks, kind)
        payload = raw[c["start"]:c["end"]]
        metadata[str(kind)] = metadata_summary(
            payload,
            block_start=block_start,
            block_end=block_end,
            roots=roots,
            compass_uids=[e["uid"] for e in compass_sorted],
        )

    direct_registry_candidates = []
    for kind, m in metadata.items():
        uid_coverage = len(m["compass_uid_hits"])
        root_coverage = len(m["compass_root_hits"])
        if uid_coverage or root_coverage or m["pattern_hits"]["type_then_count"]["count"]:
            direct_registry_candidates.append({
                "chunk": int(kind),
                "uid_coverage": uid_coverage,
                "root_coverage": root_coverage,
                "type_then_count_hits": m["pattern_hits"]["type_then_count"]["count"],
            })

    array_headers = [x for x in relocation_contexts if x["looks_like_array_header_count_9"]]
    current_builder_root = (len(data) + 7) & ~7
    conclusion = "UNRESOLVED"
    if contiguous and array_headers:
        conclusion = "COMPASS_CLASSES_FORM_CONTIGUOUS_BLOCK_WITH_PARENT_ARRAY"
    elif contiguous:
        conclusion = "COMPASS_CLASSES_FORM_EXACT_CONTIGUOUS_TYPE_BLOCK"

    report = {
        "result": "READ_ONLY_COMPASS_CLASS_STORAGE_REGISTRATION",
        "game_files_written": False,
        "source": str(source),
        "source_sha256": digest,
        "chunk_sizes": {str(c["kind"]): c["size"] for c in chunks},
        "export_count": len(exports),
        "relocation_count": len(relocs),
        "compass_type_id": "0x11E",
        "record_size": RECORD_SIZE,
        "compass_block": {
            "count": len(compass_sorted),
            "start": f"0x{block_start:X}",
            "end_exclusive": f"0x{block_end:X}",
            "bytes": block_end - block_start,
            "roots_exact_0x20_stride": contiguous,
            "sorted_roots": [f"0x{x:X}" for x in roots],
            "stock_order": [e["name"] for e in compass_sorted],
            "data_before_hex": data[max(0, block_start - 96):block_start].hex().upper(),
            "data_after_hex": data[block_end:min(len(data), block_end + 96)].hex().upper(),
        },
        "classes": compass_rows,
        "relocations_into_compass_block": {
            "count": len(into_block),
            "fields": [{"field": f"0x{r['field']:X}", "target": f"0x{r['target']:X}"} for r in into_block[:64]],
            "to_block_start_count": len(to_start),
            "block_start_contexts": relocation_contexts,
            "array_header_count9_candidates": array_headers,
        },
        "neighbor_exports": {
            "before": [compact_export(e) for e in before],
            "after": [compact_export(e) for e in after],
        },
        "metadata_chunks": metadata,
        "direct_registry_candidates": direct_registry_candidates,
        "failed_builder_comparison": {
            "old_new_record_root": f"0x{current_builder_root:X}",
            "old_builder_appended_at_data_end": True,
            "old_root_inside_stock_compass_block": block_start <= current_builder_root <= block_end,
            "distance_from_compass_block_end": current_builder_root - block_end,
            "runtime_error": "trying to set invalid type 'CompletionistRaven' on compass marker '<unknown>'",
        },
        "conclusion": conclusion,
        "next_gate": (
            "If stock type-0x11E is confirmed as a packed block, do not append the Raven record at data EOF. "
            "Build a second offline candidate by inserting a DockPoint clone at the end of the stock 0x11E block, "
            "then shift affected export roots/relocations and any proven registration metadata. Runtime-test that "
            "registration-only candidate with Dock visuals before changing artwork."
        ),
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("output must stay outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "result": report["result"],
        "compass_block": report["compass_block"],
        "relocations_into_block": len(into_block),
        "array_headers_count9": len(array_headers),
        "direct_registry_candidates": direct_registry_candidates,
        "old_builder_root": f"0x{current_builder_root:X}",
        "conclusion": conclusion,
        "game_files_written": False,
    }, indent=2))
    print(f"Saved: {out}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
