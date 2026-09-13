"""Read-only forensic analysis of richer Raven-related GoW save schemas.

Reads only recognized Desktop backup copies.  It derives the aligned fixed-slot
layout, decompresses valid zlib streams, locates richer streams containing the
literal `ravenKilled`, extracts candidate 25-byte serializer records using the
known 9-byte field-record prefix, and traces the resulting 16-byte IDs through
all decompressed streams and through the changed aligned slot(s).

The active God of War save directory is never opened or written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
RECORD_PREFIX = bytes.fromhex("62409b14ab50e07501")
RECORD_SIZE = 25
ID_SIZE = 16


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_backup_dirs(desktop: Path) -> list[Path]:
    pats = (
        "GodOfWar-SaveBackup-*",
        "GodOfWar-BeforeRestore-*",
        "GoW-TestSave-*",
        "GodOfWar-TestSave-*",
    )
    found: dict[str, Path] = {}
    for pat in pats:
        for p in desktop.glob(pat):
            if p.is_dir():
                found[str(p.resolve()).lower()] = p.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())


def locate_game_save(backup: Path) -> Path | None:
    saves = [p for p in backup.rglob("game.sav") if p.is_file()]
    return saves[0] if len(saves) == 1 else None


def layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("Save too small for header")
    words = struct.unpack_from("<8I", blob, 0)
    stride = words[5]
    declared = words[6]
    header_size = words[4]
    if declared != len(blob):
        raise RuntimeError(f"Declared size mismatch header={declared} actual={len(blob)}")
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"Implausible slot stride: {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0 or prefix < header_size:
        raise RuntimeError(f"Implausible aligned layout prefix={prefix} slots={count}")
    return {"prefix": prefix, "stride": stride, "slot_count": count, "header_size": header_size}


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) + flg) % 31 == 0


def decompress_stream(data: bytes, offset: int) -> tuple[bytes, int] | None:
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset : min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(raw) > MAX_DECOMPRESSED or not obj.eof or not raw:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return raw, consumed
    except zlib.error:
        return None


def scan_streams(slot: bytes, slot_index: int) -> list[dict]:
    out: list[dict] = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(slot, at):
            continue
        result = decompress_stream(slot, at)
        if result is None:
            continue
        raw, consumed = result
        out.append({
            "slot": slot_index,
            "relative_offset": at,
            "compressed_bytes": consumed,
            "decompressed_bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "raw": raw,
        })
    return out


def printable_strings_with_offsets(raw: bytes, minimum: int = 3) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        out.append((m.start(), m.group(0).decode("ascii", "ignore")))
    return out


def find_all(data: bytes, needle: bytes, cap: int = 1000) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < cap:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def nearest_strings(strings: list[tuple[int, str]], pos: int, radius: int = 160) -> dict:
    before = [(off, s) for off, s in strings if off <= pos and pos - off <= radius]
    after = [(off, s) for off, s in strings if off > pos and off - pos <= radius]
    return {
        "before": [{"offset": off, "text": s} for off, s in before[-5:]],
        "after": [{"offset": off, "text": s} for off, s in after[:5]],
    }


def extract_records(raw: bytes) -> list[dict]:
    strings = printable_strings_with_offsets(raw)
    rows: list[dict] = []
    for at in find_all(raw, RECORD_PREFIX, 500):
        if at + RECORD_SIZE > len(raw):
            continue
        fid = raw[at + len(RECORD_PREFIX) : at + RECORD_SIZE]
        if len(fid) != ID_SIZE:
            continue
        rows.append({
            "offset": at,
            "field_id_hex": fid.hex(),
            "record_hex": raw[at : at + RECORD_SIZE].hex(),
            "nearby_strings": nearest_strings(strings, at),
        })
    return rows


def changed_positions(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise RuntimeError("Aligned slots differ in size")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def public_stream(stream: dict) -> dict:
    return {k: v for k, v in stream.items() if k != "raw"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    candidates: list[tuple[Path, Path]] = []
    for backup in candidate_backup_dirs(desktop):
        save = locate_game_save(backup)
        if save is not None:
            candidates.append((backup, save))
    if len(candidates) != 2:
        raise RuntimeError(f"Expected exactly two recognized frozen game.sav backups, found {len(candidates)}")

    before_hashes = {str(save): sha256_file(save) for _, save in candidates}
    blobs = [save.read_bytes() for _, save in candidates]
    layouts = [layout(blob) for blob in blobs]
    if layouts[0] != layouts[1]:
        raise RuntimeError(f"Backups disagree on layout: {layouts}")
    lay = layouts[0]

    slots_all: list[list[bytes]] = []
    streams_all: list[list[dict]] = []
    for blob in blobs:
        slots: list[bytes] = []
        streams: list[dict] = []
        for i in range(lay["slot_count"]):
            start = lay["prefix"] + i * lay["stride"]
            slot = blob[start : start + lay["stride"]]
            slots.append(slot)
            streams.extend(scan_streams(slot, i))
        slots_all.append(slots)
        streams_all.append(streams)

    changed_slots: list[int] = []
    changed_pos_by_slot: dict[int, list[int]] = {}
    for i in range(lay["slot_count"]):
        pos = changed_positions(slots_all[0][i], slots_all[1][i])
        changed_pos_by_slot[i] = pos
        if pos:
            changed_slots.append(i)

    rich_schemas: list[dict] = []
    candidate_ids: dict[str, dict] = {}
    for source_index, streams in enumerate(streams_all):
        backup = candidates[source_index][0].name
        for s in streams:
            raw = s["raw"]
            if b"ravenKilled" not in raw or len(raw) < 200:
                continue
            records = extract_records(raw)
            literal_at = find_all(raw, b"ravenKilled", 20)
            row = public_stream(s) | {
                "source": source_index,
                "backup": backup,
                "literal_offsets": literal_at,
                "record_count": len(records),
                "records": records,
                "strings": [text for _, text in printable_strings_with_offsets(raw, 4)[:100]],
            }
            rich_schemas.append(row)
            for rec in records:
                fid = rec["field_id_hex"]
                meta = candidate_ids.setdefault(fid, {
                    "field_id_hex": fid,
                    "defining_occurrences": [],
                })
                meta["defining_occurrences"].append({
                    "source": source_index,
                    "backup": backup,
                    "slot": s["slot"],
                    "relative_offset": s["relative_offset"],
                    "stream_sha256": s["sha256"],
                    "record_offset": rec["offset"],
                    "nearby_strings": rec["nearby_strings"],
                })

    id_traces: list[dict] = []
    for fid_hex in sorted(candidate_ids):
        needle = bytes.fromhex(fid_hex)
        per_source = []
        for source_index, streams in enumerate(streams_all):
            hits = []
            for s in streams:
                offsets = find_all(s["raw"], needle, 100)
                if offsets:
                    hits.append({
                        "slot": s["slot"],
                        "relative_offset": s["relative_offset"],
                        "decompressed_bytes": s["decompressed_bytes"],
                        "sha256": s["sha256"],
                        "offsets": offsets,
                        "contains_literal_ravenKilled": b"ravenKilled" in s["raw"],
                        "strings": [text for _, text in printable_strings_with_offsets(s["raw"], 4)[:40]],
                    })
            per_source.append({
                "source": source_index,
                "backup": candidates[source_index][0].name,
                "decompressed_hits": hits,
            })
        id_traces.append(candidate_ids[fid_hex] | {"sources": per_source})

    # Focused changed-slot summary: candidate IDs present in streams whose compressed
    # envelope intersects actual A/B changed bytes.
    changed_stream_hits = []
    for slot_index in changed_slots:
        changed = set(changed_pos_by_slot[slot_index])
        for source_index, streams in enumerate(streams_all):
            for s in streams:
                if s["slot"] != slot_index:
                    continue
                start = s["relative_offset"]
                end = start + s["compressed_bytes"]
                envelope_changed = any(p in changed for p in range(max(0, start - 64), min(lay["stride"], end + 64)))
                if not envelope_changed:
                    continue
                matched = []
                for fid_hex in candidate_ids:
                    offs = find_all(s["raw"], bytes.fromhex(fid_hex), 20)
                    if offs:
                        matched.append({"field_id_hex": fid_hex, "offsets": offs})
                changed_stream_hits.append({
                    "source": source_index,
                    "backup": candidates[source_index][0].name,
                    "slot": slot_index,
                    "relative_offset": start,
                    "compressed_bytes": s["compressed_bytes"],
                    "decompressed_bytes": s["decompressed_bytes"],
                    "sha256": s["sha256"],
                    "candidate_id_hits": matched,
                    "strings": [text for _, text in printable_strings_with_offsets(s["raw"], 4)[:60]],
                })

    after_hashes = {str(save): sha256_file(save) for _, save in candidates}
    if before_hashes != after_hashes:
        raise RuntimeError("Frozen backup source hash changed during rich-schema analysis")

    report = {
        "schema": 1,
        "scan_kind": "read_only_rich_raven_schema_record_trace",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "layout": lay,
        "changed_slots": changed_slots,
        "rich_schema_count": len(rich_schemas),
        "unique_candidate_field_id_count": len(candidate_ids),
        "rich_schemas": rich_schemas,
        "field_id_traces": id_traces,
        "changed_stream_hits": changed_stream_hits,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - rich Raven schema record trace",
        f"layout prefix={lay['prefix']} stride={lay['stride']} slots={lay['slot_count']}",
        f"changed slots={changed_slots}",
        f"rich Raven schemas={len(rich_schemas)} candidateFieldIds={len(candidate_ids)}",
        "",
    ]
    for row in rich_schemas[:30]:
        lines.append(
            f"schema {row['backup']} slot={row['slot']} rel={row['relative_offset']} bytes={row['decompressed_bytes']} "
            f"sha={row['sha256'][:16]} literalAt={row['literal_offsets']} records={row['record_count']}"
        )
        for rec in row["records"][:20]:
            before = ", ".join(x["text"] for x in rec["nearby_strings"]["before"][-3:])
            after = ", ".join(x["text"] for x in rec["nearby_strings"]["after"][:3])
            lines.append(f"  rec@{rec['offset']} id={rec['field_id_hex']} before=[{before}] after=[{after}]")
    lines.append("")
    lines.append("Candidate field-ID traces:")
    for item in id_traces[:100]:
        counts = []
        outside = 0
        for src in item["sources"]:
            counts.append(f"{src['backup']}={len(src['decompressed_hits'])}")
            outside += sum(1 for h in src["decompressed_hits"] if not h["contains_literal_ravenKilled"])
        lines.append(f"  {item['field_id_hex']} hits({' '.join(counts)}) outsideRavenLiteral={outside}")
    lines.append("")
    lines.append(f"Changed-envelope zlib streams={len(changed_stream_hits)}")
    for hit in changed_stream_hits[:80]:
        names = ", ".join(x["field_id_hex"] for x in hit["candidate_id_hits"][:8]) or "none"
        strings = ", ".join(hit["strings"][:12])
        lines.append(
            f"  {hit['backup']} slot={hit['slot']} rel={hit['relative_offset']} bytes={hit['decompressed_bytes']} "
            f"ids={names} strings={strings}"
        )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RICH_RAVEN_SCHEMA_RECORD_TRACE_PASSED "
        f"richSchemas={len(rich_schemas)} candidateIds={len(candidate_ids)} changedSlots={','.join(map(str, changed_slots)) or 'none'}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
