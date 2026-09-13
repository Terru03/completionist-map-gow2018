"""Read-only structural analyzer for the fixed-slot God of War game.sav container.

The tool reads only recognized Desktop backup copies. It derives the container
header fields, verifies the repeated slot stride, identifies slots that contain
Raven checkpoint schema streams, compares the same fixed slots across two frozen
backups, and reports the changed save slot separately from the trailing metadata
area. It never opens or writes the active save directory.
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
RAVEN_FIELD_ID = bytes.fromhex("b0b227342530c24ea0a803505c2eb7ad")


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


def printable_strings(raw: bytes, minimum: int = 4) -> list[str]:
    out: list[str] = []
    seen = set()
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        text = match.group(0).decode("ascii", "ignore")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def scan_slot(slot: bytes, global_start: int) -> dict:
    attempted = successful = 0
    raven_streams = []
    streams = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(slot, at):
            continue
        attempted += 1
        result = decompress_stream(slot, at)
        if result is None:
            continue
        raw, consumed = result
        successful += 1
        record = {
            "relative_offset": at,
            "global_offset": global_start + at,
            "compressed_bytes": consumed,
            "decompressed_bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "strings": printable_strings(raw)[:100],
        }
        if b"ravenKilled" in raw or RAVEN_FIELD_ID in raw:
            raven_streams.append(record)
        streams.append(record)
    return {
        "zlib_attempted": attempted,
        "zlib_successful": successful,
        "raven_streams": raven_streams,
        "streams": streams,
    }


def changed_bytes(a: bytes, b: bytes) -> int:
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(x != y for x, y in zip(a, b))


def common_prefix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def header_record(data: bytes) -> dict:
    if len(data) < 32:
        raise RuntimeError("Save is too small for the fixed header")
    words = struct.unpack_from("<8I", data, 0)
    return {
        "magic_u32": words[0],
        "word_04": words[1],
        "word_08": words[2],
        "word_0c": words[3],
        "header_size": words[4],
        "slot_stride": words[5],
        "declared_file_size": words[6],
        "word_1c": words[7],
        "header_32_hex": data[:32].hex(),
    }


def stream_signature_map(streams: list[dict]) -> dict[tuple[int, str], dict]:
    return {(s["relative_offset"], s["sha256"]): s for s in streams}


def unique_changed_stream_strings(a_scan: dict, b_scan: dict) -> dict:
    a_map = stream_signature_map(a_scan["streams"])
    b_map = stream_signature_map(b_scan["streams"])
    a_unique = [s for key, s in a_map.items() if key not in b_map]
    b_unique = [s for key, s in b_map.items() if key not in a_map]
    return {
        "A_unique_streams": [
            {k: v for k, v in s.items() if k != "strings"} | {"strings": s["strings"][:80]}
            for s in a_unique[:80]
        ],
        "B_unique_streams": [
            {k: v for k, v in s.items() if k != "strings"} | {"strings": s["strings"][:80]}
            for s in b_unique[:80]
        ],
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
    headers = [header_record(blob) for blob in blobs]

    if headers[0]["slot_stride"] != headers[1]["slot_stride"]:
        raise RuntimeError("Frozen saves disagree on slot stride")
    stride = headers[0]["slot_stride"]
    if stride <= 0 or stride > len(blobs[0]):
        raise RuntimeError(f"Implausible slot stride: {stride}")
    for blob, hdr in zip(blobs, headers):
        if hdr["declared_file_size"] != len(blob):
            raise RuntimeError(
                f"Declared file size mismatch: header={hdr['declared_file_size']} actual={len(blob)}"
            )

    max_slots = min(len(blob) // stride for blob in blobs)
    slot_scans: list[list[dict]] = [[], []]
    raven_indices: list[list[int]] = [[], []]
    for source_index, blob in enumerate(blobs):
        for index in range(max_slots):
            start = index * stride
            end = start + stride
            scan = scan_slot(blob[start:end], start)
            entry = {
                "index": index,
                "start": start,
                "end": end,
                "sha256": sha256_bytes(blob[start:end]),
                "zlib_attempted": scan["zlib_attempted"],
                "zlib_successful": scan["zlib_successful"],
                "raven_stream_count": len(scan["raven_streams"]),
                "raven_stream_offsets": [s["relative_offset"] for s in scan["raven_streams"]],
                "scan": scan,
            }
            slot_scans[source_index].append(entry)
            if scan["raven_streams"]:
                raven_indices[source_index].append(index)

    common_raven = sorted(set(raven_indices[0]) & set(raven_indices[1]))
    contiguous = []
    for index in common_raven:
        if index == len(contiguous):
            contiguous.append(index)
        else:
            break
    if not contiguous:
        raise RuntimeError("Could not infer any contiguous Raven-bearing save slots")
    save_slot_count = len(contiguous)
    save_area_end = save_slot_count * stride

    slot_diffs = []
    for index in range(save_slot_count):
        start = index * stride
        end = start + stride
        a = blobs[0][start:end]
        b = blobs[1][start:end]
        count = changed_bytes(a, b)
        slot_diffs.append({
            "index": index,
            "start": start,
            "end": end,
            "changed_bytes": count,
            "same": count == 0,
            "common_prefix": common_prefix(a, b),
            "common_suffix": common_suffix(a, b),
            "A_sha256": sha256_bytes(a),
            "B_sha256": sha256_bytes(b),
            "A_raven_stream_count": slot_scans[0][index]["raven_stream_count"],
            "B_raven_stream_count": slot_scans[1][index]["raven_stream_count"],
        })

    changed_save_slots = [x for x in slot_diffs if not x["same"]]
    tail_a = blobs[0][save_area_end:]
    tail_b = blobs[1][save_area_end:]
    tail_changed = changed_bytes(tail_a, tail_b)

    changed_slot_streams = {}
    for diff in changed_save_slots:
        i = diff["index"]
        changed_slot_streams[str(i)] = unique_changed_stream_strings(
            slot_scans[0][i]["scan"], slot_scans[1][i]["scan"]
        )

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only slot analysis")

    report = {
        "schema": 1,
        "scan_kind": "read_only_fixed_save_slot_analysis",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "files": [
            {
                "backup": backup.name,
                "path": str(save),
                "sha256": before[str(save)],
                "header": hdr,
                "raven_bearing_slot_indices": raven_indices[i],
            }
            for i, ((backup, save), hdr) in enumerate(zip(candidates, headers))
        ],
        "slot_stride": stride,
        "slot_stride_hex": hex(stride),
        "max_whole_stride_regions": max_slots,
        "inferred_save_slot_count": save_slot_count,
        "inferred_save_area_end": save_area_end,
        "inferred_save_area_end_hex": hex(save_area_end),
        "slot_diffs": slot_diffs,
        "changed_save_slots": changed_save_slots,
        "tail": {
            "start": save_area_end,
            "bytes": len(tail_a),
            "changed_bytes": tail_changed,
            "A_sha256": sha256_bytes(tail_a),
            "B_sha256": sha256_bytes(tail_b),
        },
        "changed_slot_streams": changed_slot_streams,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - God of War fixed save-slot analysis",
        f"header_size={headers[0]['header_size']} slot_stride={stride} ({hex(stride)}) declared_size={headers[0]['declared_file_size']}",
        f"raven-bearing slots A={raven_indices[0]}",
        f"raven-bearing slots B={raven_indices[1]}",
        f"inferred save slots={save_slot_count} save_area_end={save_area_end} ({hex(save_area_end)})",
        f"changed save slots={[x['index'] for x in changed_save_slots]}",
        f"tail bytes={len(tail_a)} changed_bytes={tail_changed}",
        "",
    ]
    for diff in slot_diffs:
        if diff["changed_bytes"]:
            lines.append(
                f"slot {diff['index']}: changed_bytes={diff['changed_bytes']} "
                f"prefix={diff['common_prefix']} suffix={diff['common_suffix']} "
                f"ravenStreams={diff['A_raven_stream_count']}/{diff['B_raven_stream_count']}"
            )
    for index, pair in changed_slot_streams.items():
        lines.append("")
        lines.append(f"slot {index} unique decompressed streams:")
        for label in ("A_unique_streams", "B_unique_streams"):
            lines.append(f"  {label}={len(pair[label])}")
            for stream in pair[label][:20]:
                strings = ", ".join(stream["strings"][:20])
                lines.append(
                    f"    rel={stream['relative_offset']} bytes={stream['decompressed_bytes']} "
                    f"sha={stream['sha256'][:16]} strings={strings}"
                )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "GOW_SAVE_SLOT_ANALYSIS_PASSED "
        f"stride={stride} saveSlots={save_slot_count} "
        f"changedSlots={','.join(str(x['index']) for x in changed_save_slots) or 'none'} "
        f"tailChangedBytes={tail_changed}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
