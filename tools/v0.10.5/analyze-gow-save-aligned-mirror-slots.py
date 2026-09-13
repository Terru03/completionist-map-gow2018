"""Read-only analysis of the correctly aligned fixed slots in God of War game.sav.

The container size is not an exact multiple of the stride stored in its header.
This analyzer treats the remainder as the global prefix, then compares all aligned
slots across two frozen Desktop backups and compares the two 10-slot banks.  It
never opens or writes the active God of War save directory.
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
    seen: set[str] = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        text = m.group(0).decode("ascii", "ignore")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def scan_streams(slot: bytes) -> list[dict]:
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
                "relative_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "raven": b"ravenKilled" in raw or RAVEN_FIELD_ID in raw,
                "strings": printable_strings(raw)[:100],
            }
        )
    return streams


def changed_positions(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise RuntimeError("Aligned slots differ in length")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


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


def slot_layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("Save too small")
    words = struct.unpack_from("<8I", blob, 0)
    stride = words[5]
    declared = words[6]
    header_size = words[4]
    if declared != len(blob):
        raise RuntimeError(f"Declared size mismatch header={declared} actual={len(blob)}")
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"Implausible stride {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0:
        raise RuntimeError("No aligned slots")
    if prefix < header_size:
        raise RuntimeError(f"Derived prefix {prefix} is smaller than header size {header_size}")
    return {
        "magic_u32": words[0],
        "header_size": header_size,
        "slot_stride": stride,
        "declared_file_size": declared,
        "global_prefix": prefix,
        "slot_count": count,
        "header_32_hex": blob[:32].hex(),
    }


def public_stream(s: dict) -> dict:
    return {**s, "strings": s["strings"][:50]}


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
    layouts = [slot_layout(x) for x in blobs]
    for key in ("slot_stride", "global_prefix", "slot_count"):
        if layouts[0][key] != layouts[1][key]:
            raise RuntimeError(f"Backups disagree on {key}")

    stride = layouts[0]["slot_stride"]
    prefix = layouts[0]["global_prefix"]
    count = layouts[0]["slot_count"]
    if count % 2 != 0:
        raise RuntimeError(f"Expected an even aligned slot count for bank comparison, got {count}")
    bank_width = count // 2

    slots: list[list[bytes]] = [[], []]
    for source, blob in enumerate(blobs):
        for i in range(count):
            start = prefix + i * stride
            slots[source].append(blob[start : start + stride])

    cross_backup = []
    changed_indices: list[int] = []
    changed_pos: dict[int, list[int]] = {}
    for i in range(count):
        pos = changed_positions(slots[0][i], slots[1][i])
        changed_pos[i] = pos
        if pos:
            changed_indices.append(i)
        cross_backup.append(
            {
                "index": i,
                "start": prefix + i * stride,
                "end": prefix + (i + 1) * stride,
                "changed_bytes": len(pos),
                "A_sha256": sha256_bytes(slots[0][i]),
                "B_sha256": sha256_bytes(slots[1][i]),
                "first_changed": pos[0] if pos else None,
                "last_changed": pos[-1] if pos else None,
                "changed_runs": [
                    {"offset": off, "length": length}
                    for off, length in runs_from_positions(pos)[:100]
                ],
            }
        )

    mirror_pairs = []
    for i in range(bank_width):
        j = i + bank_width
        row = {"left": i, "right": j}
        for source, name in ((0, "A"), (1, "B")):
            left = slots[source][i]
            right = slots[source][j]
            same = sum(x == y for x, y in zip(left, right))
            row[name] = {
                "equal_bytes": same,
                "equal_fraction": round(same / stride, 8),
                "left_sha256": sha256_bytes(left),
                "right_sha256": sha256_bytes(right),
                "exact_equal": left == right,
            }
        mirror_pairs.append(row)

    changed_mirror_analysis: dict[str, dict] = {}
    for i in changed_indices:
        mate = i + bank_width if i < bank_width else i - bank_width
        if mate not in changed_indices or i > mate:
            continue
        p1 = set(changed_pos[i])
        p2 = set(changed_pos[mate])
        both = sorted(p1 & p2)
        same_transition = 0
        same_before = 0
        same_after = 0
        for p in both:
            a1, b1 = slots[0][i][p], slots[1][i][p]
            a2, b2 = slots[0][mate][p], slots[1][mate][p]
            if a1 == a2:
                same_before += 1
            if b1 == b2:
                same_after += 1
            if a1 == a2 and b1 == b2:
                same_transition += 1
        changed_mirror_analysis[f"{i}<->{mate}"] = {
            "left_changed_bytes": len(p1),
            "right_changed_bytes": len(p2),
            "intersection_changed_bytes": len(both),
            "union_changed_bytes": len(p1 | p2),
            "same_before_in_intersection": same_before,
            "same_after_in_intersection": same_after,
            "same_transition_in_intersection": same_transition,
            "intersection_runs": [
                {"offset": off, "length": length}
                for off, length in runs_from_positions(both)[:100]
            ],
        }

    stream_scans: dict[str, dict] = {}
    for i in changed_indices:
        stream_scans[str(i)] = {}
        for source, name in ((0, "A"), (1, "B")):
            streams = scan_streams(slots[source][i])
            stream_scans[str(i)][name] = {
                "count": len(streams),
                "raven_streams": [public_stream(s) for s in streams if s["raven"]],
                "streams": [public_stream(s) for s in streams],
            }

    mirrored_streams: dict[str, dict] = {}
    for i in range(bank_width):
        j = i + bank_width
        for source, name in ((0, "A"), (1, "B")):
            left = scan_streams(slots[source][i])
            right = scan_streams(slots[source][j])
            left_map = {(s["relative_offset"], s["sha256"]): s for s in left}
            right_map = {(s["relative_offset"], s["sha256"]): s for s in right}
            shared = sorted(set(left_map) & set(right_map))
            if shared:
                mirrored_streams[f"{name}:{i}<->{j}"] = {
                    "shared_stream_count": len(shared),
                    "shared": [
                        {
                            "relative_offset": off,
                            "sha256": sha,
                            "decompressed_bytes": left_map[(off, sha)]["decompressed_bytes"],
                            "raven": left_map[(off, sha)]["raven"],
                            "strings": left_map[(off, sha)]["strings"][:30],
                        }
                        for off, sha in shared[:100]
                    ],
                }

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during aligned-slot analysis")

    report = {
        "schema": 1,
        "scan_kind": "read_only_aligned_mirror_slot_analysis",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "files": [
            {
                "backup": backup.name,
                "path": str(save),
                "sha256": before[str(save)],
                "layout": layout,
            }
            for (backup, save), layout in zip(candidates, layouts)
        ],
        "layout": {
            "global_prefix": prefix,
            "slot_stride": stride,
            "slot_count": count,
            "bank_width": bank_width,
            "size_formula": f"{prefix} + {count} * {stride} = {prefix + count * stride}",
        },
        "changed_slot_indices": changed_indices,
        "cross_backup_slots": cross_backup,
        "mirror_pairs": mirror_pairs,
        "changed_mirror_analysis": changed_mirror_analysis,
        "changed_slot_streams": stream_scans,
        "mirrored_streams": mirrored_streams,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - aligned/mirrored GoW save-slot analysis",
        f"layout: prefix={prefix} stride={stride} slots={count} bank_width={bank_width}",
        f"formula: {report['layout']['size_formula']}",
        f"changed aligned slots={changed_indices}",
        "",
    ]
    for i in changed_indices:
        row = cross_backup[i]
        lines.append(
            f"slot {i}: changed={row['changed_bytes']} first={row['first_changed']} last={row['last_changed']}"
        )
    lines.append("")
    for key, value in changed_mirror_analysis.items():
        lines.append(
            f"mirror {key}: left={value['left_changed_bytes']} right={value['right_changed_bytes']} "
            f"intersection={value['intersection_changed_bytes']} sameTransition={value['same_transition_in_intersection']}"
        )
    lines.append("")
    for pair in mirror_pairs:
        if pair["left"] in changed_indices or pair["right"] in changed_indices:
            lines.append(
                f"pair {pair['left']}<->{pair['right']}: "
                f"A_equal={pair['A']['equal_fraction']} B_equal={pair['B']['equal_fraction']}"
            )
    lines.append("")
    for i in changed_indices:
        for name in ("A", "B"):
            s = stream_scans[str(i)][name]
            lines.append(
                f"slot {i} {name}: zlib={s['count']} ravenStreams={len(s['raven_streams'])}"
            )
            for rv in s["raven_streams"]:
                lines.append(
                    f"  raven rel={rv['relative_offset']} bytes={rv['decompressed_bytes']} sha={rv['sha256'][:16]}"
                )
    lines.append("")
    for key, item in sorted(mirrored_streams.items()):
        if key.endswith("6<->16"):
            lines.append(f"{key}: sharedStreams={item['shared_stream_count']}")
            for s in item["shared"][:20]:
                strings = ", ".join(s["strings"][:8])
                lines.append(
                    f"  rel={s['relative_offset']} bytes={s['decompressed_bytes']} raven={s['raven']} "
                    f"sha={s['sha256'][:16]} strings={strings}"
                )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "GOW_ALIGNED_MIRROR_SLOT_ANALYSIS_PASSED "
        f"prefix={prefix} stride={stride} slots={count} "
        f"changed={','.join(map(str, changed_indices)) or 'none'}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
