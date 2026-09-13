"""Read-only deep inspection of changed/compressed regions in two frozen GoW saves.

The tool only reads Desktop backup copies. It never opens the active save directory.
It compares the two 16 MiB banks over their shared byte range, exhaustively probes
zlib streams near changed 4 KiB blocks, groups mirrored/duplicate payloads, and
emits printable structure for small changed streams. It does not write or patch
any save data.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

BLOCK = 4096
HALF = 16 * 1024 * 1024
MAX_DECOMPRESSED = 4 * 1024 * 1024
WINDOW_PAD = 16 * 1024


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
    if len(saves) == 1:
        return saves[0]
    return None


def printable_strings(data: bytes, minimum: int = 4) -> list[dict]:
    out = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, data):
        try:
            text = m.group(0).decode("ascii")
        except UnicodeDecodeError:
            continue
        out.append({"offset": m.start(), "text": text})
    return out


def printable_excerpt(data: bytes, limit: int = 512) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data[:limit])


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) + flg) % 31 == 0


def try_zlib(data: bytes, offset: int, input_limit: int = 1024 * 1024) -> dict | None:
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset : min(len(data), offset + input_limit)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(raw) > MAX_DECOMPRESSED or not obj.eof:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2 or not raw:
            return None
    except zlib.error:
        return None
    strings = printable_strings(raw)
    terms = []
    lower = raw.lower()
    for term in (
        b"ravenkilled",
        b"raven",
        b"regionsummary",
        b"quest",
        b"checkpoint",
        b"mapsummarycomplete",
        b"__subobjs",
        b"progress",
        b"world",
    ):
        if term in lower:
            terms.append(term.decode("ascii"))
    return {
        "offset": offset,
        "half": offset // HALF,
        "relative_half_offset": offset % HALF,
        "compressed_bytes": consumed,
        "decompressed_bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "terms": terms,
        "strings": strings[:200],
        "printable_excerpt": printable_excerpt(raw),
        "hex": raw.hex() if len(raw) <= 4096 else None,
        "raw": raw,
    }


def changed_blocks(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise RuntimeError("Frozen saves differ in size")
    out = []
    for i in range((len(a) + BLOCK - 1) // BLOCK):
        lo = i * BLOCK
        hi = min(len(a), lo + BLOCK)
        if a[lo:hi] != b[lo:hi]:
            out.append(i)
    return out


def groups(blocks: list[int]) -> list[tuple[int, int]]:
    if not blocks:
        return []
    result = []
    start = prev = blocks[0]
    for value in blocks[1:]:
        if value == prev + 1:
            prev = value
            continue
        result.append((start, prev))
        start = prev = value
    result.append((start, prev))
    return result


def merge_windows(items: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    expanded = []
    for first, last in items:
        lo = max(0, first * BLOCK - WINDOW_PAD)
        hi = min(size, (last + 1) * BLOCK + WINDOW_PAD)
        expanded.append((lo, hi))
    expanded.sort()
    merged: list[list[int]] = []
    for lo, hi in expanded:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return [(lo, hi) for lo, hi in merged]


def scan_windows(data: bytes, windows: list[tuple[int, int]]) -> list[dict]:
    seen = set()
    streams = []
    for lo, hi in windows:
        for offset in range(lo, hi - 1):
            if offset in seen or data[offset] != 0x78:
                continue
            seen.add(offset)
            record = try_zlib(data, offset)
            if record is not None:
                streams.append(record)
    streams.sort(key=lambda x: x["offset"])
    return streams


def public_stream(record: dict) -> dict:
    return {k: v for k, v in record.items() if k != "raw"}


def byte_similarity(a: bytes, b: bytes) -> float:
    if not a and not b:
        return 1.0
    n = max(len(a), len(b))
    common = sum(x == y for x, y in zip(a, b))
    return round(common / n, 6)


def sequence_ratio(a: bytes, b: bytes) -> float:
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 6)


def stream_pair_candidates(sa: list[dict], sb: list[dict]) -> list[dict]:
    pairs = []
    for left in sa:
        nearest = sorted(
            sb,
            key=lambda right: (
                abs(left["relative_half_offset"] - right["relative_half_offset"]),
                abs(left["decompressed_bytes"] - right["decompressed_bytes"]),
            ),
        )[:3]
        for right in nearest:
            distance = abs(left["relative_half_offset"] - right["relative_half_offset"])
            if distance > 8192:
                continue
            pairs.append(
                {
                    "a_offset": left["offset"],
                    "b_offset": right["offset"],
                    "a_relative_half_offset": left["relative_half_offset"],
                    "b_relative_half_offset": right["relative_half_offset"],
                    "relative_offset_distance": distance,
                    "a_decompressed_bytes": left["decompressed_bytes"],
                    "b_decompressed_bytes": right["decompressed_bytes"],
                    "same_sha256": left["sha256"] == right["sha256"],
                    "byte_similarity": byte_similarity(left["raw"], right["raw"]),
                    "sequence_ratio": sequence_ratio(left["raw"], right["raw"]),
                    "a_terms": left["terms"],
                    "b_terms": right["terms"],
                }
            )
    unique = {}
    for pair in pairs:
        key = (pair["a_offset"], pair["b_offset"])
        unique[key] = pair
    return sorted(
        unique.values(),
        key=lambda p: (-p["sequence_ratio"], p["relative_offset_distance"], p["a_offset"], p["b_offset"]),
    )


def duplicate_groups(named_streams: dict[str, list[dict]]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for source, streams in named_streams.items():
        for s in streams:
            buckets.setdefault(s["sha256"], []).append(
                {
                    "source": source,
                    "offset": s["offset"],
                    "half": s["half"],
                    "relative_half_offset": s["relative_half_offset"],
                    "decompressed_bytes": s["decompressed_bytes"],
                    "terms": s["terms"],
                }
            )
    return [
        {"sha256": sha, "occurrences": occ}
        for sha, occ in buckets.items()
        if len(occ) > 1
    ]


def half_comparison(data: bytes) -> dict:
    first = data[:HALF]
    second = data[HALF:]
    overlap = min(len(first), len(second))
    if overlap <= 0:
        return {
            "comparable": False,
            "first_bytes": len(first),
            "second_bytes": len(second),
        }
    first_overlap = first[:overlap]
    second_overlap = second[:overlap]
    same = sum(a == b for a, b in zip(first_overlap, second_overlap))
    return {
        "comparable": True,
        "same_length": len(first) == len(second),
        "first_bytes": len(first),
        "second_bytes": len(second),
        "overlap_bytes": overlap,
        "trailing_shortfall_bytes": abs(len(first) - len(second)),
        "equal_bytes_in_overlap": same,
        "equal_fraction": round(same / overlap, 8),
        "first_overlap_sha256": sha256_bytes(first_overlap),
        "second_overlap_sha256": sha256_bytes(second_overlap),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    backups = candidate_backup_dirs(desktop)
    candidates = []
    for backup in backups:
        save = locate_game_save(backup)
        if save is not None:
            candidates.append((backup, save))
    if len(candidates) != 2:
        raise RuntimeError(f"Expected exactly two recognized frozen game.sav backups, found {len(candidates)}")

    before = {str(save): sha256_file(save) for _, save in candidates}
    data = [save.read_bytes() for _, save in candidates]
    # The observed PC game.sav is 33,554,400 bytes: exactly 32 bytes short of
    # 32 MiB. The +16 MiB mirrored offsets are still valid throughout the used
    # region, so compare the two banks over their shared range instead of
    # requiring two perfectly equal 16 MiB slices.
    if any(len(blob) <= HALF for blob in data):
        raise RuntimeError("Unexpected save size; need data beyond the 16 MiB bank boundary")

    diff_blocks = changed_blocks(data[0], data[1])
    block_groups = groups(diff_blocks)
    windows = merge_windows(block_groups, len(data[0]))
    scans = {
        "A": scan_windows(data[0], windows),
        "B": scan_windows(data[1], windows),
    }

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Source backup hash changed during read-only inspection")

    pair_candidates = stream_pair_candidates(scans["A"], scans["B"])
    duplicates = duplicate_groups(scans)

    report = {
        "schema": 2,
        "scan_kind": "read_only_changed_zlib_structure",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "files": {
            "A": {
                "backup": candidates[0][0].name,
                "path": str(candidates[0][1]),
                "sha256": before[str(candidates[0][1])],
                "bytes": len(data[0]),
                "half_comparison": half_comparison(data[0]),
            },
            "B": {
                "backup": candidates[1][0].name,
                "path": str(candidates[1][1]),
                "sha256": before[str(candidates[1][1])],
                "bytes": len(data[1]),
                "half_comparison": half_comparison(data[1]),
            },
        },
        "different_4k_blocks": diff_blocks,
        "changed_groups": [
            {"first": first, "last": last, "count": last - first + 1}
            for first, last in block_groups
        ],
        "scan_windows": [{"start": lo, "end": hi} for lo, hi in windows],
        "streams": {
            "A": [public_stream(s) for s in scans["A"]],
            "B": [public_stream(s) for s in scans["B"]],
        },
        "duplicate_payload_groups": duplicates,
        "cross_save_pair_candidates": pair_candidates[:200],
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - changed zlib payload deep inspection",
        f"A: {candidates[0][0].name} sha256={before[str(candidates[0][1])]}",
        f"B: {candidates[1][0].name} sha256={before[str(candidates[1][1])]}",
        f"Different 4 KiB blocks: {len(diff_blocks)}",
        f"Windows: {len(windows)}",
        f"Streams A={len(scans['A'])} B={len(scans['B'])}",
        f"Duplicate payload groups={len(duplicates)}",
        "",
        "Half comparison:",
        f"  A equal_fraction={report['files']['A']['half_comparison'].get('equal_fraction')} shortfall={report['files']['A']['half_comparison'].get('trailing_shortfall_bytes')}",
        f"  B equal_fraction={report['files']['B']['half_comparison'].get('equal_fraction')} shortfall={report['files']['B']['half_comparison'].get('trailing_shortfall_bytes')}",
        "",
        "Duplicate payloads across save/half:",
    ]
    for group in duplicates[:50]:
        occ = ", ".join(
            f"{x['source']}@{x['offset']} h{x['half']} rel={x['relative_half_offset']} bytes={x['decompressed_bytes']}"
            for x in group["occurrences"]
        )
        terms = sorted({term for x in group["occurrences"] for term in x["terms"]})
        lines.append(f"  {group['sha256'][:16]} terms={terms} :: {occ}")

    lines += ["", "Best changed-stream A/B structural matches:"]
    for pair in pair_candidates[:40]:
        lines.append(
            "  A@{a_offset} B@{b_offset} rel_delta={relative_offset_distance} "
            "len={a_decompressed_bytes}/{b_decompressed_bytes} shaSame={same_sha256} "
            "seq={sequence_ratio} byte={byte_similarity} terms={a_terms}/{b_terms}".format(**pair)
        )

    lines += ["", "Streams with relevant terms or 2-8 KiB decompressed payloads:"]
    for source in ("A", "B"):
        for s in scans[source]:
            if s["terms"] or 2048 <= s["decompressed_bytes"] <= 8192:
                lines.append(
                    f"  {source}@{s['offset']} h{s['half']} rel={s['relative_half_offset']} "
                    f"compressed={s['compressed_bytes']} decompressed={s['decompressed_bytes']} "
                    f"sha={s['sha256']} terms={s['terms']}"
                )
                if s["strings"]:
                    for item in s["strings"][:40]:
                        lines.append(f"    str+{item['offset']}: {item['text']}")
                else:
                    lines.append(f"    printable={s['printable_excerpt']}")
                if s["hex"] is not None:
                    lines.append(f"    hex={s['hex']}")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"CHANGED_ZLIB_INSPECTION_PASSED blocks={len(diff_blocks)} windows={len(windows)} "
        f"streamsA={len(scans['A'])} streamsB={len(scans['B'])} duplicates={len(duplicates)}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
