#!/usr/bin/env python3
"""Read-only active-save Raven ring/state authority probe.

Purpose:
- decode the 20 aligned God of War save-ring snapshots;
- recover killed Raven catalogue IDs from proven custom-userdata carriers using
  catalogue/odins-ravens-gameobject-identities.json;
- inspect only the fixed 208-byte slot headers for sequence/timestamp fields;
- identify strong candidates for the authoritative/latest snapshot without
  assuming that the highest physical slot number is newest.

The active game.sav is read only and SHA-256 verified unchanged afterwards.
No arbitrary save payload bytes are archived.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENTITIES = REPO / "catalogue" / "odins-ravens-gameobject-identities.json"
HEADER_BYTES = 208
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
RAVEN_FIELD = b"ravenKilled"
MASK64 = 0xFFFFFFFFFFFFFFFF


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("game.sav is too short")
    words = struct.unpack_from("<8I", blob, 0)
    stride = int(words[5])
    declared = int(words[6])
    header_size = int(words[4])
    if declared != len(blob):
        raise RuntimeError(f"declared file size mismatch: {declared} != {len(blob)}")
    if stride <= HEADER_BYTES or stride >= len(blob):
        raise RuntimeError(f"implausible slot stride: {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count != 20:
        raise RuntimeError(f"expected 20 aligned ring slots, found {count}")
    if prefix < header_size:
        raise RuntimeError(f"global prefix {prefix} smaller than declared header {header_size}")
    return {
        "magic_u32": words[0],
        "header_size": header_size,
        "slot_stride": stride,
        "declared_file_size": declared,
        "global_prefix": prefix,
        "slot_count": count,
    }


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and (((cmf << 8) | flg) % 31) == 0
    )


def decompress_stream(data: bytes, offset: int):
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset:min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj(15)
        decoded = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(decoded) > MAX_DECOMPRESSED or not obj.eof or not decoded:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return decoded, consumed
    except zlib.error:
        return None


def scanner_args(start: int, end: int):
    import argparse as _argparse
    return _argparse.Namespace(
        start_offset=start,
        end_offset=end,
        max_hits=16,
        max_tag_solutions=256,
        include_raw_deflate=False,
        require_valid_records=True,
        max_compressed_length=0xFFFF,
        max_record_count=2048,
        max_record_blob_length=0xFFFF,
        max_decompressed_length=0x20000,
        max_section0_words=8192,
        max_metadata_pairs=8192,
        max_rows=8192,
    )


def parse_gameobject_payload(payload: bytes):
    if len(payload) != 17 or payload[0] != 1:
        return None
    return {
        "registry_hash": int.from_bytes(payload[1:9], "little"),
        "object_hash": int.from_bytes(payload[9:17], "little"),
    }


def scan_slot(slot: bytes, slot_index: int, scanner, parser, object_map: dict[int, str], registry_hash: int) -> dict:
    stream_count = 0
    raven_stream_count = 0
    parsed_carriers = 0
    unresolved_raven_streams = 0
    killed: set[str] = set()
    carrier_rows = []
    seen_carriers: set[tuple[int, int]] = set()

    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        got = decompress_stream(slot, at)
        if got is None:
            continue
        decoded, consumed = got
        stream_count += 1
        if RAVEN_FIELD not in decoded:
            continue
        raven_stream_count += 1
        if at < 16:
            unresolved_raven_streams += 1
            continue

        header_start = at - 16
        try:
            words = struct.unpack_from("<8H", slot, header_start)
        except struct.error:
            unresolved_raven_streams += 1
            continue
        if words[7] != consumed or words[1] + words[5] != len(decoded):
            unresolved_raven_streams += 1
            continue

        scan_end = min(len(slot), at + consumed + 0x10000)
        matches, _, _ = scanner.scan_bytes(
            slot, scanner_args(header_start, scan_end), parser
        )
        exact = [
            m for m in matches
            if m["offset"] == header_start
            and m["header"]["compressed_length"] == consumed
        ]
        if not exact:
            unresolved_raven_streams += 1
            continue
        exact.sort(key=lambda m: m["length"])
        match = exact[0]
        key = (match["offset"], match["end_offset"])
        if key in seen_carriers:
            continue
        seen_carriers.add(key)

        report = parser.inspect_carrier(slot[match["offset"]:match["end_offset"]], 256)
        prefix_hex = report.get("decompressed_prefix_hex")
        prefix = bytes.fromhex(prefix_hex) if prefix_hex else b""
        if RAVEN_FIELD not in prefix:
            unresolved_raven_streams += 1
            continue

        parsed_carriers += 1
        matched_ids = []
        candidate_gameobjects = 0
        for rec in report.get("records", []):
            if not rec.get("valid"):
                continue
            payload_hex = rec.get("payload_hex")
            if not isinstance(payload_hex, str):
                continue
            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError:
                continue
            parsed = parse_gameobject_payload(payload)
            if parsed is None:
                continue
            if parsed["registry_hash"] != registry_hash:
                continue
            candidate_gameobjects += 1
            catalogue_id = object_map.get(parsed["object_hash"])
            if catalogue_id is not None:
                killed.add(catalogue_id)
                matched_ids.append(catalogue_id)

        carrier_rows.append({
            "relative_offset": match["offset"],
            "length": match["length"],
            "record_count": len(report.get("records", [])),
            "candidate_gameobject_records": candidate_gameobjects,
            "matched_raven_catalogue_ids": sorted(set(matched_ids)),
        })

    return {
        "slot_index": slot_index,
        "slot_sha256": sha256_bytes(slot),
        "stream_count": stream_count,
        "raven_stream_count": raven_stream_count,
        "parsed_raven_carrier_count": parsed_carriers,
        "unresolved_raven_stream_count": unresolved_raven_streams,
        "killed_raven_count": len(killed),
        "killed_raven_catalogue_ids": sorted(killed),
        "raven_carriers": carrier_rows,
    }


def plausible_datetime(value: int):
    candidates = []
    def add(kind: str, seconds: float):
        try:
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return
        if datetime(2010, 1, 1, tzinfo=timezone.utc) <= dt <= datetime(2035, 12, 31, 23, 59, 59, tzinfo=timezone.utc):
            candidates.append((kind, dt.isoformat()))

    add("unix_s", value)
    add("unix_ms", value / 1_000)
    add("unix_us", value / 1_000_000)
    add("unix_ns", value / 1_000_000_000)
    add("windows_filetime", value / 10_000_000 - 11644473600)
    add("dotnet_ticks", value / 10_000_000 - 62135596800)
    return candidates


def header_fields(slot_headers: list[bytes], occupied: list[int]) -> dict:
    timestamp_fields = []
    for width, fmt in ((4, "<I"), (8, "<Q")):
        for off in range(0, HEADER_BYTES - width + 1, width):
            values = {idx: struct.unpack_from(fmt, slot_headers[idx], off)[0] for idx in occupied}
            decoded = {}
            for idx, value in values.items():
                cands = plausible_datetime(int(value))
                if cands:
                    decoded[idx] = cands
            if len(decoded) >= max(2, len(occupied) // 2):
                # Prefer a single encoding that works across the most slots.
                kind_counts = Counter(kind for rows in decoded.values() for kind, _ in rows)
                kind, count = kind_counts.most_common(1)[0]
                if count >= max(2, len(occupied) // 2):
                    selected = {}
                    for idx, rows in decoded.items():
                        for k, text in rows:
                            if k == kind:
                                selected[idx] = text
                                break
                    if selected:
                        latest_slot = max(selected, key=lambda i: selected[i])
                        timestamp_fields.append({
                            "width": width,
                            "offset": off,
                            "offset_hex": f"0x{off:X}",
                            "encoding": kind,
                            "decoded_slots": {str(k): v for k, v in sorted(selected.items())},
                            "decoded_count": len(selected),
                            "latest_slot": latest_slot,
                            "latest_utc": selected[latest_slot],
                        })

    sequence_fields = []
    for width, fmt in ((4, "<I"), (8, "<Q")):
        for off in range(0, HEADER_BYTES - width + 1, width):
            values = {idx: int(struct.unpack_from(fmt, slot_headers[idx], off)[0]) for idx in occupied}
            nonzero = {idx: value for idx, value in values.items() if value != 0}
            if len(nonzero) < max(4, len(occupied) // 2):
                continue
            unique = len(set(nonzero.values()))
            if unique < len(nonzero) - 1:
                continue
            ordered = sorted(set(nonzero.values()))
            if len(ordered) < 4:
                continue
            diffs = [b - a for a, b in zip(ordered, ordered[1:])]
            exact_one_ratio = sum(d == 1 for d in diffs) / len(diffs)
            median_diff = statistics.median(diffs)
            value_range = ordered[-1] - ordered[0]
            if exact_one_ratio < 0.70 and not (median_diff <= 16 and value_range <= 100000):
                continue
            max_value = max(nonzero.values())
            latest_slots = [idx for idx, value in nonzero.items() if value == max_value]
            if len(latest_slots) != 1:
                continue
            sequence_fields.append({
                "width": width,
                "offset": off,
                "offset_hex": f"0x{off:X}",
                "values": {str(k): v for k, v in sorted(nonzero.items())},
                "unique_count": unique,
                "exact_increment_one_ratio": exact_one_ratio,
                "median_sorted_increment": median_diff,
                "value_range": value_range,
                "latest_slot": latest_slots[0],
                "latest_value": max_value,
            })

    sequence_fields.sort(
        key=lambda row: (
            -row["exact_increment_one_ratio"],
            row["median_sorted_increment"],
            row["value_range"],
            row["offset"],
        )
    )
    timestamp_fields.sort(key=lambda row: (-row["decoded_count"], row["offset"]))

    seq_votes = Counter(row["latest_slot"] for row in sequence_fields[:20])
    time_votes = Counter(row["latest_slot"] for row in timestamp_fields[:20])
    strong_seq = seq_votes.most_common(1)[0] if seq_votes else None
    strong_time = time_votes.most_common(1)[0] if time_votes else None

    consensus = None
    reason = None
    if strong_time and strong_time[1] >= 2:
        if strong_seq is None or strong_seq[0] == strong_time[0]:
            consensus = strong_time[0]
            reason = f"timestamp_consensus={strong_time[1]} sequence_votes={strong_seq[1] if strong_seq else 0}"
    if consensus is None and strong_seq and strong_seq[1] >= 2:
        consensus = strong_seq[0]
        reason = f"sequence_consensus={strong_seq[1]}"

    return {
        "timestamp_fields": timestamp_fields[:40],
        "sequence_fields": sequence_fields[:40],
        "timestamp_latest_votes": {str(k): v for k, v in sorted(time_votes.items())},
        "sequence_latest_votes": {str(k): v for k, v in sorted(seq_votes.items())},
        "consensus_latest_slot": consensus,
        "consensus_reason": reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", type=Path)
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--identities", type=Path, default=IDENTITIES)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    if args.save is not None:
        save = args.save.expanduser().resolve()
    else:
        root = args.save_root.expanduser().resolve()
        saves = sorted(p.resolve() for p in root.rglob("game.sav") if p.is_file())
        if len(saves) != 1:
            raise RuntimeError(f"expected exactly one active game.sav under {root}, found {len(saves)}")
        save = saves[0]
    if not save.is_file():
        raise RuntimeError(f"save not found: {save}")

    identities = json.loads(args.identities.read_text(encoding="utf-8"))
    if identities.get("count") != 53:
        raise RuntimeError("Raven serialized GameObject identity catalogue is incomplete")
    if identities.get("unique_object_hashes") != 53:
        raise RuntimeError("Raven serialized GameObject hashes are not unique")
    registry_hash = int(identities["registry_hash_hex"], 16)
    object_map = {
        int(row["object_hash_hex"], 16): row["catalogue_id"]
        for row in identities["ravens"]
    }
    if len(object_map) != 53:
        raise RuntimeError("Raven object-hash map is not one-to-one")

    scanner = load_module("gow_carrier_scan_active_raven", HERE / "gow-custom-userdata-carrier-scan.py")
    parser = load_module("gow_carrier_active_raven", HERE / "gow-custom-userdata-carrier.py")

    before = sha256_file(save)
    blob = save.read_bytes()
    lay = layout(blob)
    prefix = lay["global_prefix"]
    stride = lay["slot_stride"]

    slots = []
    headers = []
    occupied = []
    for idx in range(lay["slot_count"]):
        start = prefix + idx * stride
        raw = blob[start:start + stride]
        if len(raw) != stride:
            raise RuntimeError(f"slot {idx} extraction failed")
        headers.append(raw[:HEADER_BYTES])
        row = scan_slot(raw, idx, scanner, parser, object_map, registry_hash)
        # Validated streams are a strong occupancy signal.
        row["occupied"] = row["stream_count"] > 0
        if row["occupied"]:
            occupied.append(idx)
        slots.append(row)

    header_analysis = header_fields(headers, occupied)
    authoritative = header_analysis["consensus_latest_slot"]
    authoritative_kills = None
    if authoritative is not None:
        authoritative_kills = slots[authoritative]["killed_raven_catalogue_ids"]

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav SHA-256 changed during read-only probe")

    report = {
        "schema": 1,
        "analysis": "active_save_raven_ring_authority",
        "save_path": str(save),
        "save_sha256": before,
        "layout": lay,
        "occupied_slots": occupied,
        "slots": slots,
        "slot_header_analysis": header_analysis,
        "authoritative_slot_candidate": authoritative,
        "authoritative_killed_raven_count": len(authoritative_kills) if authoritative_kills is not None else None,
        "authoritative_killed_raven_catalogue_ids": authoritative_kills,
        "identity_catalogue_sha256": sha256_file(args.identities),
        "safety": {
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - active save Raven ring authority probe",
        f"save_sha256={before}",
        f"layout=prefix:{prefix} stride:{stride} slots:{lay['slot_count']}",
        f"occupied_slots={','.join(map(str, occupied))}",
        f"authoritative_slot_candidate={authoritative}",
        f"consensus_reason={header_analysis['consensus_reason']}",
        "",
        "SLOTS",
    ]
    for row in slots:
        if not row["occupied"]:
            continue
        lines.append(
            f"slot={row['slot_index']} streams={row['stream_count']} ravenStreams={row['raven_stream_count']} "
            f"carriers={row['parsed_raven_carrier_count']} unresolved={row['unresolved_raven_stream_count']} "
            f"killed={row['killed_raven_count']}"
        )
        if row["killed_raven_catalogue_ids"]:
            lines.append("  killed=" + ",".join(row["killed_raven_catalogue_ids"]))

    lines.extend(["", "TOP TIMESTAMP FIELDS"])
    for row in header_analysis["timestamp_fields"][:12]:
        lines.append(
            f"offset={row['offset_hex']} width={row['width']} encoding={row['encoding']} "
            f"decoded={row['decoded_count']} latest_slot={row['latest_slot']} latest={row['latest_utc']}"
        )
    lines.extend(["", "TOP SEQUENCE FIELDS"])
    for row in header_analysis["sequence_fields"][:12]:
        lines.append(
            f"offset={row['offset_hex']} width={row['width']} latest_slot={row['latest_slot']} "
            f"latest_value={row['latest_value']} inc1={row['exact_increment_one_ratio']:.3f} "
            f"median_inc={row['median_sorted_increment']} range={row['value_range']}"
        )
    if authoritative_kills is not None:
        lines.extend([
            "",
            f"AUTHORITATIVE CANDIDATE killed_count={len(authoritative_kills)}",
            *["  " + item for item in authoritative_kills],
        ])
    lines.extend([
        "",
        "SAFETY active_save_opened_read_only=true source_hash_unchanged=true "
        "save_written=false progression_written=false game_process_opened=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "ACTIVE_SAVE_RAVEN_RING_AUTHORITY_PROBE_COMPLETE "
        f"occupied={len(occupied)} authoritative={authoritative} "
        f"killed={len(authoritative_kills) if authoritative_kills is not None else 'unresolved'}"
    )
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
