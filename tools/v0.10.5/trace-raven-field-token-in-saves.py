"""Read-only trace of the serialized Raven `ravenKilled` field token in frozen saves.

This tool reads only Desktop backup copies. It decompresses the known Raven schema
zlib stream, derives its 25-byte field records (9-byte type prefix + 16-byte field
identifier), then searches raw save bytes and every valid zlib stream for those
identifiers. It never opens or writes the active God of War save directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zlib

KNOWN_SCHEMA_OFFSET = 43363
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
FIELD_RECORD_SIZE = 25
FIELD_PREFIX_SIZE = 9


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def parse_schema(raw: bytes) -> dict:
    # The known schema layout is N NUL-terminated ASCII field names followed by
    # one fixed 25-byte record per name. Infer N by trying every possible split
    # and requiring the binary tail length to equal N*25.
    candidates = []
    for split in range(1, len(raw) + 1):
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
        if "ravenKilled" not in names:
            continue
        records = [
            raw[split + i * FIELD_RECORD_SIZE : split + (i + 1) * FIELD_RECORD_SIZE]
            for i in range(n)
        ]
        prefixes = [r[:FIELD_PREFIX_SIZE] for r in records]
        ids = [r[FIELD_PREFIX_SIZE:] for r in records]
        candidates.append((split, names, records, prefixes, ids))
    if len(candidates) != 1:
        raise RuntimeError(f"Unable to infer unique Raven schema layout; candidates={len(candidates)}")
    split, names, records, prefixes, ids = candidates[0]
    return {
        "split": split,
        "names": names,
        "records": records,
        "prefixes": prefixes,
        "ids": ids,
    }


def find_all(data: bytes, needle: bytes, limit: int = 1000) -> list[int]:
    out = []
    start = 0
    while len(out) < limit:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def context_hex(data: bytes, at: int, radius: int = 48) -> str:
    lo = max(0, at - radius)
    hi = min(len(data), at + 16 + radius)
    return data[lo:hi].hex()


def scan_all_zlib(data: bytes, field_ids: dict[str, bytes], field_records: dict[str, bytes]) -> dict:
    stream_hits = []
    attempted = 0
    successful = 0
    cursor = 0
    seen = set()
    while True:
        at = data.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if at in seen or not valid_zlib_header(data, at):
            continue
        seen.add(at)
        attempted += 1
        result = decompress_stream(data, at)
        if result is None:
            continue
        raw, consumed = result
        successful += 1
        hits = []
        for name, fid in field_ids.items():
            for pos in find_all(raw, fid, 100):
                hits.append({
                    "kind": "field_id",
                    "name": name,
                    "offset": pos,
                    "context_hex": context_hex(raw, pos),
                })
        for name, record in field_records.items():
            for pos in find_all(raw, record, 100):
                hits.append({
                    "kind": "field_record",
                    "name": name,
                    "offset": pos,
                    "context_hex": context_hex(raw, pos),
                })
        if hits:
            stream_hits.append({
                "compressed_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "hits": hits,
            })
    return {
        "attempted": attempted,
        "successful": successful,
        "stream_hits": stream_hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    candidates = []
    for backup in candidate_backup_dirs(desktop):
        save = locate_game_save(backup)
        if save is not None:
            candidates.append((backup, save))
    if len(candidates) != 2:
        raise RuntimeError(f"Expected exactly two recognized frozen game.sav backups, found {len(candidates)}")

    before = {str(save): sha256_file(save) for _, save in candidates}
    blobs = [save.read_bytes() for _, save in candidates]

    known = decompress_stream(blobs[0], KNOWN_SCHEMA_OFFSET)
    if known is None:
        raise RuntimeError(f"Known Raven schema zlib stream did not decompress at {KNOWN_SCHEMA_OFFSET}")
    schema_raw, schema_consumed = known
    schema = parse_schema(schema_raw)

    field_ids = {name: fid for name, fid in zip(schema["names"], schema["ids"])}
    field_records = {name: rec for name, rec in zip(schema["names"], schema["records"])}
    raven_id = field_ids["ravenKilled"]
    raven_record = field_records["ravenKilled"]

    entries = []
    for (backup, save), data in zip(candidates, blobs):
        raw_id_hits = find_all(data, raven_id)
        raw_record_hits = find_all(data, raven_record)
        zscan = scan_all_zlib(data, field_ids, field_records)
        raven_stream_hits = []
        for stream in zscan["stream_hits"]:
            rh = [h for h in stream["hits"] if h["name"] == "ravenKilled"]
            if rh:
                raven_stream_hits.append({**stream, "hits": rh})
        entries.append({
            "backup": backup.name,
            "path": str(save),
            "sha256": before[str(save)],
            "raw_raven_field_id_hits": raw_id_hits,
            "raw_raven_field_record_hits": raw_record_hits,
            "zlib_attempted": zscan["attempted"],
            "zlib_successful": zscan["successful"],
            "all_field_stream_hits": zscan["stream_hits"],
            "raven_stream_hits": raven_stream_hits,
        })

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only trace")

    report = {
        "schema": 1,
        "scan_kind": "read_only_raven_field_token_trace",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "known_schema": {
            "compressed_offset": KNOWN_SCHEMA_OFFSET,
            "compressed_bytes": schema_consumed,
            "decompressed_bytes": len(schema_raw),
            "sha256": sha256_bytes(schema_raw),
            "names": schema["names"],
            "record_prefixes_hex": [x.hex() for x in schema["prefixes"]],
            "field_ids_hex": {name: fid.hex() for name, fid in field_ids.items()},
            "field_records_hex": {name: rec.hex() for name, rec in field_records.items()},
            "ravenKilled_field_id_hex": raven_id.hex(),
            "ravenKilled_field_record_hex": raven_record.hex(),
        },
        "files": entries,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - Raven field-token trace",
        f"Known schema offset={KNOWN_SCHEMA_OFFSET} compressed={schema_consumed} decompressed={len(schema_raw)}",
        f"Names={schema['names']}",
        f"ravenKilled field id={raven_id.hex()}",
        f"ravenKilled full record={raven_record.hex()}",
        "",
    ]
    for item in entries:
        lines.append(f"=== {item['backup']} ===")
        lines.append(f"sha256={item['sha256']}")
        lines.append(f"raw field-id hits={item['raw_raven_field_id_hits']}")
        lines.append(f"raw full-record hits={item['raw_raven_field_record_hits']}")
        lines.append(f"zlib attempted={item['zlib_attempted']} successful={item['zlib_successful']}")
        lines.append(f"raven zlib streams={len(item['raven_stream_hits'])}")
        for stream in item["raven_stream_hits"]:
            lines.append(
                f"  stream@{stream['compressed_offset']} compressed={stream['compressed_bytes']} "
                f"decompressed={stream['decompressed_bytes']} sha={stream['sha256']}"
            )
            for hit in stream["hits"]:
                lines.append(f"    {hit['kind']} +{hit['offset']} context={hit['context_hex']}")
        lines.append("")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_FIELD_TOKEN_TRACE_PASSED "
        f"fieldId={raven_id.hex()} "
        + " ".join(f"{x['backup']}:ravenStreams={len(x['raven_stream_hits'])}" for x in entries)
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
