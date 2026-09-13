"""Read-only trace of every serialized `ravenKilled` schema field ID in frozen GoW saves.

The scanner reads only recognized Desktop backup copies. It derives the aligned
20-slot layout from the container header, decompresses valid zlib streams inside
those slots, parses schema-style streams that contain the literal `ravenKilled`
name, derives their 25-byte field records (9-byte prefix + 16-byte ID), and then
searches both raw slot bytes and every decompressed stream for those IDs.

It never opens or writes the active God of War save directory.
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
FIELD_RECORD_SIZE = 25
FIELD_PREFIX_SIZE = 9


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_backup_dirs(desktop: Path) -> list[Path]:
    patterns = (
        "GodOfWar-SaveBackup-*",
        "GodOfWar-BeforeRestore-*",
        "GoW-TestSave-*",
        "GodOfWar-TestSave-*",
    )
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in desktop.glob(pattern):
            if path.is_dir():
                found[str(path.resolve()).lower()] = path.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())


def locate_game_save(backup: Path) -> Path | None:
    saves = [p for p in backup.rglob("game.sav") if p.is_file()]
    return saves[0] if len(saves) == 1 else None


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
        raise RuntimeError(f"Implausible slot stride {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0 or prefix < header_size:
        raise RuntimeError(f"Implausible aligned layout prefix={prefix} slots={count}")
    return {"prefix": prefix, "stride": stride, "slot_count": count, "header_size": header_size}


def printable_strings(raw: bytes, minimum: int = 4) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        text = m.group(0).decode("ascii", "ignore")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def parse_schema(raw: bytes) -> dict | None:
    """Infer a names-prefix + N*25-byte records schema layout.

    Some streams can admit more than one arithmetic split. Prefer candidates whose
    records share the same 9-byte type prefix, then the candidate with the most
    names. This is evidence extraction only; ambiguous results are reported.
    """
    candidates: list[dict] = []
    for split in range(1, len(raw)):
        tail = len(raw) - split
        if tail <= 0 or tail % FIELD_RECORD_SIZE:
            continue
        n = tail // FIELD_RECORD_SIZE
        names_blob = raw[:split]
        if not names_blob.endswith(b"\0"):
            continue
        parts = names_blob[:-1].split(b"\0")
        if len(parts) != n:
            continue
        try:
            names = [p.decode("ascii") for p in parts]
        except UnicodeDecodeError:
            continue
        if "ravenKilled" not in names or any(not x for x in names):
            continue
        records = [
            raw[split + i * FIELD_RECORD_SIZE : split + (i + 1) * FIELD_RECORD_SIZE]
            for i in range(n)
        ]
        prefixes = [r[:FIELD_PREFIX_SIZE] for r in records]
        ids = [r[FIELD_PREFIX_SIZE:] for r in records]
        common_prefix = len(set(prefixes)) == 1
        candidates.append(
            {
                "split": split,
                "names": names,
                "records": records,
                "prefixes": prefixes,
                "ids": ids,
                "common_record_prefix": common_prefix,
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (not c["common_record_prefix"], -len(c["names"]), c["split"]))
    best = candidates[0]
    best["candidate_count"] = len(candidates)
    return best


def find_all(data: bytes, needle: bytes, cap: int = 200) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < cap:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def scan_slot_streams(slot: bytes, slot_index: int) -> list[dict]:
    streams: list[dict] = []
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
        streams.append(
            {
                "slot": slot_index,
                "relative_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "raw": raw,
            }
        )
    return streams


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

    before = {str(save): sha256_file(save) for _, save in candidates}
    blobs = [save.read_bytes() for _, save in candidates]
    layouts = [layout(blob) for blob in blobs]
    if layouts[0] != layouts[1]:
        raise RuntimeError(f"Frozen saves disagree on aligned layout: {layouts}")
    lay = layouts[0]

    all_sources: list[dict] = []
    unique_ids: dict[str, dict] = {}
    stream_sets: list[list[dict]] = []
    slot_bytes_all: list[list[bytes]] = []

    for source_index, ((backup, save), blob) in enumerate(zip(candidates, blobs)):
        source_streams: list[dict] = []
        source_slots: list[bytes] = []
        schema_streams: list[dict] = []
        for slot_index in range(lay["slot_count"]):
            start = lay["prefix"] + slot_index * lay["stride"]
            slot = blob[start : start + lay["stride"]]
            source_slots.append(slot)
            streams = scan_slot_streams(slot, slot_index)
            source_streams.extend(streams)
            for stream in streams:
                raw = stream["raw"]
                if b"ravenKilled" not in raw:
                    continue
                parsed = parse_schema(raw)
                item = {
                    "slot": slot_index,
                    "relative_offset": stream["relative_offset"],
                    "compressed_bytes": stream["compressed_bytes"],
                    "decompressed_bytes": stream["decompressed_bytes"],
                    "sha256": stream["sha256"],
                    "strings": printable_strings(raw)[:80],
                    "parsed": parsed is not None,
                }
                if parsed is not None:
                    idx = parsed["names"].index("ravenKilled")
                    fid = parsed["ids"][idx]
                    rec = parsed["records"][idx]
                    item.update(
                        {
                            "schema_candidate_count": parsed["candidate_count"],
                            "common_record_prefix": parsed["common_record_prefix"],
                            "field_count": len(parsed["names"]),
                            "names": parsed["names"][:120],
                            "raven_record_prefix_hex": parsed["prefixes"][idx].hex(),
                            "raven_field_id_hex": fid.hex(),
                            "raven_full_record_hex": rec.hex(),
                        }
                    )
                    key = fid.hex()
                    meta = unique_ids.setdefault(
                        key,
                        {
                            "field_id_hex": key,
                            "record_prefixes": set(),
                            "schema_occurrences": [],
                        },
                    )
                    meta["record_prefixes"].add(parsed["prefixes"][idx].hex())
                    meta["schema_occurrences"].append(
                        {
                            "source": source_index,
                            "backup": backup.name,
                            "slot": slot_index,
                            "relative_offset": stream["relative_offset"],
                            "sha256": stream["sha256"],
                            "field_count": len(parsed["names"]),
                            "strings": printable_strings(raw)[:30],
                        }
                    )
                schema_streams.append(item)
        stream_sets.append(source_streams)
        slot_bytes_all.append(source_slots)
        all_sources.append(
            {
                "backup": backup.name,
                "path": str(save),
                "sha256": before[str(save)],
                "zlib_successful": len(source_streams),
                "raven_literal_schema_stream_count": len(schema_streams),
                "schema_streams": schema_streams,
            }
        )

    # Search each derived field ID outside its defining schemas, both raw and decompressed.
    id_reports: list[dict] = []
    for key in sorted(unique_ids):
        fid = bytes.fromhex(key)
        meta = unique_ids[key]
        per_source = []
        for source_index, ((backup, _), streams, slots) in enumerate(zip(candidates, stream_sets, slot_bytes_all)):
            raw_slot_hits = []
            for slot_index, slot in enumerate(slots):
                hits = find_all(slot, fid, 100)
                if hits:
                    raw_slot_hits.append({"slot": slot_index, "offsets": hits})
            decompressed_hits = []
            for stream in streams:
                hits = find_all(stream["raw"], fid, 100)
                if not hits:
                    continue
                decompressed_hits.append(
                    {
                        "slot": stream["slot"],
                        "relative_offset": stream["relative_offset"],
                        "sha256": stream["sha256"],
                        "offsets": hits,
                        "contains_literal_ravenKilled": b"ravenKilled" in stream["raw"],
                        "strings": printable_strings(stream["raw"])[:40],
                    }
                )
            per_source.append(
                {
                    "source": source_index,
                    "backup": backup.name,
                    "raw_slot_hits": raw_slot_hits,
                    "decompressed_hits": decompressed_hits,
                }
            )
        id_reports.append(
            {
                "field_id_hex": key,
                "record_prefixes": sorted(meta["record_prefixes"]),
                "schema_occurrences": meta["schema_occurrences"],
                "sources": per_source,
            }
        )

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only Raven schema trace")

    report = {
        "schema": 1,
        "scan_kind": "read_only_raven_schema_field_id_trace",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "layout": lay,
        "unique_raven_field_id_count": len(id_reports),
        "sources": all_sources,
        "field_ids": id_reports,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - Raven schema field-ID trace",
        f"layout prefix={lay['prefix']} stride={lay['stride']} slots={lay['slot_count']}",
        f"unique ravenKilled field IDs={len(id_reports)}",
        "",
    ]
    for source in all_sources:
        parsed = sum(1 for x in source["schema_streams"] if x["parsed"])
        lines.append(
            f"{source['backup']}: zlib={source['zlib_successful']} ravenLiteralStreams={source['raven_literal_schema_stream_count']} parsed={parsed}"
        )
    lines.append("")
    for item in id_reports:
        occ = item["schema_occurrences"]
        summary = ", ".join(
            f"{x['backup']} s{x['slot']}@{x['relative_offset']} fields={x['field_count']} sha={x['sha256'][:12]}"
            for x in occ[:12]
        )
        lines.append(f"ID {item['field_id_hex']} schemas={len(occ)} :: {summary}")
        for src in item["sources"]:
            outside = [
                h for h in src["decompressed_hits"]
                if not h["contains_literal_ravenKilled"]
            ]
            raw_count = sum(len(x["offsets"]) for x in src["raw_slot_hits"])
            lines.append(
                f"  {src['backup']}: rawHits={raw_count} decompressedHits={len(src['decompressed_hits'])} outsideLiteralSchema={len(outside)}"
            )
            for hit in outside[:20]:
                strings = ", ".join(hit["strings"][:12])
                lines.append(
                    f"    OUTSIDE slot={hit['slot']} rel={hit['relative_offset']} sha={hit['sha256'][:16]} offsets={hit['offsets'][:8]} strings={strings}"
                )
    lines.append("")
    lines.append("Schema streams with richer context:")
    for source in all_sources:
        for s in source["schema_streams"]:
            if s["parsed"] and s.get("field_count", 0) >= 8:
                lines.append(
                    f"  {source['backup']} slot={s['slot']} rel={s['relative_offset']} bytes={s['decompressed_bytes']} fields={s['field_count']} id={s['raven_field_id_hex']}"
                )
                lines.append("    names=" + ", ".join(s.get("names", [])[:40]))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_SCHEMA_FIELD_ID_TRACE_PASSED "
        f"uniqueIds={len(id_reports)} "
        + " ".join(
            f"{x['backup']}:schemas={x['raven_literal_schema_stream_count']}" for x in all_sources
        )
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
