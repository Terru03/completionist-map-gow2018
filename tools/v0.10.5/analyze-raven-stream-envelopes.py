"""Read-only analysis of raw bytes surrounding Raven-related zlib streams in frozen GoW saves.

The save contains repeated compressed schema/state streams.  This tool anchors on
streams containing either the literal `ravenKilled` name or the known Raven field
identifier and compares the raw bytes immediately before/after identical streams.
The purpose is to find per-save value bytes that may live in the stream envelope
rather than in the repeated schema payload itself.

Only recognized Desktop backup copies are read.  The active God of War save
directory is never opened or written.
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
WINDOW = 4096
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
    seen: set[str] = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        text = m.group(0).decode("ascii", "ignore")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def scan_raven_streams(slot: bytes, slot_index: int) -> list[dict]:
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
        literal = b"ravenKilled" in raw
        field = RAVEN_FIELD_ID in raw
        if not literal and not field:
            continue
        lo = max(0, at - WINDOW)
        hi = min(len(slot), at + consumed + WINDOW)
        before = slot[lo:at]
        after = slot[at + consumed:hi]
        out.append({
            "slot": slot_index,
            "relative_offset": at,
            "compressed_bytes": consumed,
            "decompressed_bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "literal_ravenKilled": literal,
            "contains_field_id": field,
            "strings": printable_strings(raw)[:50],
            "before_sha256": sha256_bytes(before),
            "after_sha256": sha256_bytes(after),
            "before_len": len(before),
            "after_len": len(after),
            "_raw": raw,
            "_before": before,
            "_after": after,
        })
    return out


def changed_positions(a: bytes, b: bytes) -> list[int]:
    n = min(len(a), len(b))
    out = [i for i in range(n) if a[i] != b[i]]
    out.extend(range(n, max(len(a), len(b))))
    return out


def runs_from_positions(pos: list[int]) -> list[tuple[int, int]]:
    if not pos:
        return []
    runs: list[tuple[int, int]] = []
    start = prev = pos[0]
    for p in pos[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev - start + 1))
        start = prev = p
    runs.append((start, prev - start + 1))
    return runs


def ctx(data: bytes, pos: int, radius: int = 24) -> str:
    lo = max(0, pos - radius)
    hi = min(len(data), pos + radius)
    return data[lo:hi].hex()


def compare_envelope(a: dict, b: dict) -> dict:
    # Align before-windows by the stream start: offset -1 is the byte immediately
    # preceding the zlib stream.  Align after-windows by the end of the compressed
    # stream: offset +1 is the first byte after it.
    before_n = min(len(a["_before"]), len(b["_before"]))
    aa_before = a["_before"][-before_n:]
    bb_before = b["_before"][-before_n:]
    before_pos = changed_positions(aa_before, bb_before)
    before_rel = [p - before_n for p in before_pos]

    after_n = min(len(a["_after"]), len(b["_after"]))
    aa_after = a["_after"][:after_n]
    bb_after = b["_after"][:after_n]
    after_pos = changed_positions(aa_after, bb_after)
    after_rel = [p + 1 for p in after_pos]

    change_rows = []
    # Focus on the nearest changes to the stream on each side.
    ranked = sorted(
        [(abs(r), "before", p, r) for p, r in zip(before_pos, before_rel)]
        + [(abs(r), "after", p, r) for p, r in zip(after_pos, after_rel)],
        key=lambda x: x[0],
    )[:80]
    for _, side, p, rel in ranked:
        da = aa_before if side == "before" else aa_after
        db = bb_before if side == "before" else bb_after
        change_rows.append({
            "side": side,
            "relative_to_stream": rel,
            "A_byte": da[p] if p < len(da) else None,
            "B_byte": db[p] if p < len(db) else None,
            "A_context_hex": ctx(da, p),
            "B_context_hex": ctx(db, p),
        })

    # Look for aligned 32-bit words near the stream which transition between 0/1
    # or otherwise change.  These are only candidates, never interpreted as a
    # Boolean without further evidence.
    u32_candidates = []
    radius = min(512, before_n, after_n)
    merged_a = aa_before[-radius:] + aa_after[:radius]
    merged_b = bb_before[-radius:] + bb_after[:radius]
    origin = radius  # stream boundary between before and after portions
    for p in range(0, len(merged_a) - 3, 4):
        av = struct.unpack_from("<I", merged_a, p)[0]
        bv = struct.unpack_from("<I", merged_b, p)[0]
        if av == bv:
            continue
        rel = p - origin
        if rel >= 0:
            rel += 1
        u32_candidates.append({
            "relative_to_stream_boundary": rel,
            "A_u32": av,
            "B_u32": bv,
            "zero_one_transition": {av, bv}.issubset({0, 1}),
        })

    return {
        "A_relative_offset": a["relative_offset"],
        "B_relative_offset": b["relative_offset"],
        "same_stream_offset": a["relative_offset"] == b["relative_offset"],
        "before_changed_bytes": len(before_pos),
        "after_changed_bytes": len(after_pos),
        "nearest_changes": change_rows,
        "before_changed_runs": [
            {"relative_start": off - before_n, "length": length}
            for off, length in runs_from_positions(before_pos)[:100]
        ],
        "after_changed_runs": [
            {"relative_start": off + 1, "length": length}
            for off, length in runs_from_positions(after_pos)[:100]
        ],
        "u32_changed_near_stream": u32_candidates[:200],
        "u32_zero_one_candidates": [x for x in u32_candidates if x["zero_one_transition"]][:100],
    }


def public_stream(s: dict) -> dict:
    return {k: v for k, v in s.items() if not k.startswith("_")}


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
    layouts = [layout(x) for x in blobs]
    if layouts[0] != layouts[1]:
        raise RuntimeError(f"Frozen saves disagree on aligned layout: {layouts}")
    lay = layouts[0]

    source_streams: list[list[dict]] = []
    source_slots: list[list[bytes]] = []
    for blob in blobs:
        all_streams: list[dict] = []
        slots: list[bytes] = []
        for slot_index in range(lay["slot_count"]):
            start = lay["prefix"] + slot_index * lay["stride"]
            slot = blob[start:start + lay["stride"]]
            slots.append(slot)
            all_streams.extend(scan_raven_streams(slot, slot_index))
        source_streams.append(all_streams)
        source_slots.append(slots)

    # Pair same-slot streams with the same decompressed hash, preserving occurrence
    # order in case a slot contains more than one copy.
    pair_reports = []
    for slot_index in range(lay["slot_count"]):
        aa = [x for x in source_streams[0] if x["slot"] == slot_index]
        bb = [x for x in source_streams[1] if x["slot"] == slot_index]
        by_hash_a: dict[str, list[dict]] = {}
        by_hash_b: dict[str, list[dict]] = {}
        for x in aa:
            by_hash_a.setdefault(x["sha256"], []).append(x)
        for x in bb:
            by_hash_b.setdefault(x["sha256"], []).append(x)
        for sha in sorted(set(by_hash_a) & set(by_hash_b)):
            la = sorted(by_hash_a[sha], key=lambda x: x["relative_offset"])
            lb = sorted(by_hash_b[sha], key=lambda x: x["relative_offset"])
            for occurrence, (a, b) in enumerate(zip(la, lb)):
                comp = compare_envelope(a, b)
                pair_reports.append({
                    "slot": slot_index,
                    "occurrence": occurrence,
                    "stream_sha256": sha,
                    "decompressed_bytes": a["decompressed_bytes"],
                    "literal_ravenKilled": a["literal_ravenKilled"] or b["literal_ravenKilled"],
                    "contains_field_id": a["contains_field_id"] or b["contains_field_id"],
                    "strings": a["strings"][:30],
                    **comp,
                })

    # Group envelope hashes for identical decompressed Raven-related streams across
    # slots. This shows whether a static schema is surrounded by varying save data.
    groups = []
    all_shas = sorted({x["sha256"] for src in source_streams for x in src})
    for sha in all_shas:
        occs = []
        for source_index, ((backup, _), streams) in enumerate(zip(candidates, source_streams)):
            for x in streams:
                if x["sha256"] != sha:
                    continue
                occs.append({
                    "source": source_index,
                    "backup": backup.name,
                    "slot": x["slot"],
                    "relative_offset": x["relative_offset"],
                    "decompressed_bytes": x["decompressed_bytes"],
                    "before_sha256": x["before_sha256"],
                    "after_sha256": x["after_sha256"],
                    "literal_ravenKilled": x["literal_ravenKilled"],
                    "contains_field_id": x["contains_field_id"],
                    "strings": x["strings"][:25],
                })
        groups.append({
            "stream_sha256": sha,
            "occurrence_count": len(occs),
            "unique_before_envelopes": len({x["before_sha256"] for x in occs}),
            "unique_after_envelopes": len({x["after_sha256"] for x in occs}),
            "occurrences": occs,
        })

    after_hashes = {str(save): sha256_file(save) for _, save in candidates}
    if before_hashes != after_hashes:
        raise RuntimeError("Frozen backup hash changed during read-only Raven envelope analysis")

    report = {
        "schema": 1,
        "scan_kind": "read_only_raven_stream_envelope_analysis",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "layout": lay,
        "window_bytes_each_side": WINDOW,
        "files": [
            {
                "backup": backup.name,
                "path": str(save),
                "sha256": before_hashes[str(save)],
                "raven_related_stream_count": len(source_streams[i]),
                "streams": [public_stream(x) for x in source_streams[i]],
            }
            for i, (backup, save) in enumerate(candidates)
        ],
        "same_stream_cross_backup_envelopes": pair_reports,
        "stream_groups": groups,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - Raven stream envelope analysis",
        f"layout prefix={lay['prefix']} stride={lay['stride']} slots={lay['slot_count']} window={WINDOW}",
        "",
    ]
    for i, (backup, _) in enumerate(candidates):
        lines.append(f"{backup.name}: ravenRelatedStreams={len(source_streams[i])}")
    lines.append("")
    lines.append("Same decompressed Raven stream across the two frozen backups:")
    for row in pair_reports:
        if row["before_changed_bytes"] or row["after_changed_bytes"] or row["slot"] in (6, 16):
            lines.append(
                f"  slot={row['slot']} bytes={row['decompressed_bytes']} sha={row['stream_sha256'][:16]} "
                f"rel={row['A_relative_offset']}/{row['B_relative_offset']} "
                f"beforeChanged={row['before_changed_bytes']} afterChanged={row['after_changed_bytes']} "
                f"zeroOneU32={len(row['u32_zero_one_candidates'])}"
            )
            if row["u32_zero_one_candidates"]:
                lines.append(
                    "    zero/one candidates=" + ", ".join(
                        f"{x['relative_to_stream_boundary']}:{x['A_u32']}->{x['B_u32']}"
                        for x in row["u32_zero_one_candidates"][:20]
                    )
                )
    lines.append("")
    lines.append("Identical decompressed stream groups with varying envelopes:")
    for group in groups:
        if group["unique_before_envelopes"] > 1 or group["unique_after_envelopes"] > 1:
            sample = group["occurrences"][0] if group["occurrences"] else {}
            strings = ", ".join(sample.get("strings", [])[:8])
            lines.append(
                f"  bytes={sample.get('decompressed_bytes')} sha={group['stream_sha256'][:16]} "
                f"occ={group['occurrence_count']} beforeVariants={group['unique_before_envelopes']} "
                f"afterVariants={group['unique_after_envelopes']} strings={strings}"
            )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    changed_pairs = sum(1 for x in pair_reports if x["before_changed_bytes"] or x["after_changed_bytes"])
    print(
        "RAVEN_STREAM_ENVELOPE_ANALYSIS_PASSED "
        f"pairs={len(pair_reports)} changedEnvelopes={changed_pairs} groups={len(groups)}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
