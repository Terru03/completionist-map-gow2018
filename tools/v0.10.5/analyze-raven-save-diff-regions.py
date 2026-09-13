"""Read-only deep diff analysis of the two frozen God of War save backups.

This tool targets the exact two save images already archived by the preceding
forensic pass. It never opens the active save directory and never writes to either
backup. It focuses on changed 4 KiB regions, mirrored-region structure, and zlib
streams located inside or near changed regions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import zlib

EXPECTED = {
    "617dc5867850dc14b6a4791bc116ace132a84a6a188d3165cec5276049d48438": "A",
    "d1d7b43780ad878e300507d71059347734f96515d2ae3d0cf40e9571216bc63d": "B",
}
BLOCK = 4096
MIRROR = 16 * 1024 * 1024
MAX_DECOMPRESSED = 16 * 1024 * 1024

PATTERNS = {
    "ravenKilled": b"ravenKilled",
    "veithurgard_instance_guid_ascii": b"642d0d16-4af0-a5d4-076e-77933c549a5d",
    "veithurgard_script_guid_ascii": b"2f0f1759-4a6c-864f-c4db-caa4bbc7ea61",
    "veithurgard_parent": b"RegionSummary_VF_Raven_Parent",
    "veithurgard_uid": b"E15E6BC82AE2773E",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_backups(desktop: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for pattern in ("GodOfWar-SaveBackup-*", "GodOfWar-BeforeRestore-*", "GoW-TestSave-*", "GodOfWar-TestSave-*"):
        for root in desktop.glob(pattern):
            if not root.is_dir():
                continue
            for save in root.rglob("game.sav"):
                digest = sha256_file(save)
                if digest in EXPECTED:
                    found[digest] = save.resolve()
    return found


def diff_blocks(a: bytes, b: bytes) -> list[int]:
    total = math.ceil(len(a) / BLOCK)
    out = []
    for i in range(total):
        s = i * BLOCK
        e = min(len(a), s + BLOCK)
        if a[s:e] != b[s:e]:
            out.append(i)
    return out


def groups(indices: list[int]) -> list[list[int]]:
    if not indices:
        return []
    result = [[indices[0]]]
    for i in indices[1:]:
        if i == result[-1][-1] + 1:
            result[-1].append(i)
        else:
            result.append([i])
    return result


def xor_delta(x: bytes, y: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(x, y))


def byte_equal_fraction(x: bytes, y: bytes) -> float:
    if len(x) != len(y) or not x:
        return 0.0
    same = sum(a == b for a, b in zip(x, y))
    return same / len(x)


def changed_positions(x: bytes, y: bytes) -> list[int]:
    return [i for i, (a, b) in enumerate(zip(x, y)) if a != b]


def plausible_zlib_header(data: bytes, pos: int) -> bool:
    if pos + 2 > len(data):
        return False
    cmf, flg = data[pos], data[pos + 1]
    if cmf & 0x0F != 8:
        return False
    if (cmf >> 4) > 7:
        return False
    return ((cmf << 8) + flg) % 31 == 0


def decompress_at(data: bytes, pos: int) -> bytes | None:
    try:
        obj = zlib.decompressobj()
        out = obj.decompress(data[pos:], MAX_DECOMPRESSED)
        if not obj.eof:
            return None
        out += obj.flush()
        if len(out) > MAX_DECOMPRESSED:
            return None
        return out
    except zlib.error:
        return None


def pattern_hits(blob: bytes) -> list[str]:
    return [name for name, needle in PATTERNS.items() if needle in blob]


def printable_excerpt(blob: bytes, needle: bytes, radius: int = 48) -> str | None:
    at = blob.find(needle)
    if at < 0:
        return None
    start = max(0, at - radius)
    end = min(len(blob), at + len(needle) + radius)
    return "".join(chr(c) if 32 <= c < 127 else "." for c in blob[start:end])


def scan_zlib_windows(data: bytes, windows: list[tuple[int, int]], max_attempts: int = 5000) -> dict[int, dict]:
    seen: set[int] = set()
    results: dict[int, dict] = {}
    attempts = 0
    for start, end in windows:
        start = max(0, start)
        end = min(len(data), end)
        for pos in range(start, max(start, end - 1)):
            if pos in seen or not plausible_zlib_header(data, pos):
                continue
            seen.add(pos)
            attempts += 1
            if attempts > max_attempts:
                return results
            dec = decompress_at(data, pos)
            if dec is None:
                continue
            results[pos] = {
                "compressed_offset": pos,
                "decompressed_bytes": len(dec),
                "sha256": sha256_bytes(dec),
                "pattern_hits": pattern_hits(dec),
                "ravenKilled_excerpt": printable_excerpt(dec, b"ravenKilled"),
            }
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    matched = find_backups(desktop)
    if set(matched) != set(EXPECTED):
        missing = sorted(set(EXPECTED) - set(matched))
        raise RuntimeError(f"Frozen save pair not found by expected SHA-256. Missing: {missing}")

    pa = matched[next(k for k, v in EXPECTED.items() if v == "A")]
    pb = matched[next(k for k, v in EXPECTED.items() if v == "B")]
    for p in (pa, pb):
        try:
            p.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing active-save overlap: {p}")

    before = {str(pa): sha256_file(pa), str(pb): sha256_file(pb)}
    a = pa.read_bytes()
    b = pb.read_bytes()
    if len(a) != len(b):
        raise RuntimeError("Frozen save pair has different file sizes")

    indices = diff_blocks(a, b)
    block_groups = groups(indices)

    per_block = []
    for i in indices:
        s = i * BLOCK
        aa = a[s:s + BLOCK]
        bb = b[s:s + BLOCK]
        pos = changed_positions(aa, bb)
        entry = {
            "index": i,
            "offset": s,
            "changed_bytes": len(pos),
            "first_changed_in_block": pos[0] if pos else None,
            "last_changed_in_block": pos[-1] if pos else None,
            "a_sha256": sha256_bytes(aa),
            "b_sha256": sha256_bytes(bb),
        }
        per_block.append(entry)

    mirror_pairs = []
    index_set = set(indices)
    for i in indices:
        j = i + MIRROR // BLOCK
        if j not in index_set:
            continue
        si, sj = i * BLOCK, j * BLOCK
        da = xor_delta(a[si:si + BLOCK], b[si:si + BLOCK])
        db = xor_delta(a[sj:sj + BLOCK], b[sj:sj + BLOCK])
        mirror_pairs.append({
            "block_a": i,
            "block_b": j,
            "offset_delta": sj - si,
            "delta_equal_fraction": round(byte_equal_fraction(da, db), 6),
            "delta_a_sha256": sha256_bytes(da),
            "delta_b_sha256": sha256_bytes(db),
        })

    windows: list[tuple[int, int]] = []
    for g in block_groups:
        start = g[0] * BLOCK - 64 * 1024
        end = (g[-1] + 1) * BLOCK + 64 * 1024
        windows.append((start, end))
    # Include the known schema-like zlib stream for exact comparison.
    windows.append((43363 - 256, 43363 + 256))

    za = scan_zlib_windows(a, windows)
    zb = scan_zlib_windows(b, windows)
    z_offsets = sorted(set(za) | set(zb))
    z_compare = []
    for off in z_offsets:
        ea, eb = za.get(off), zb.get(off)
        z_compare.append({
            "offset": off,
            "present_a": ea is not None,
            "present_b": eb is not None,
            "a": ea,
            "b": eb,
            "same_decompressed_sha256": bool(ea and eb and ea["sha256"] == eb["sha256"]),
        })

    after = {str(pa): sha256_file(pa), str(pb): sha256_file(pb)}
    if before != after:
        raise RuntimeError("Frozen save backup hash changed during read-only analysis")

    report = {
        "schema": 1,
        "scan_kind": "read_only_frozen_save_diff_regions",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "files": {
            "A": {"path": str(pa), "sha256": before[str(pa)], "bytes": len(a)},
            "B": {"path": str(pb), "sha256": before[str(pb)], "bytes": len(b)},
        },
        "block_size": BLOCK,
        "different_block_count": len(indices),
        "different_blocks": indices,
        "groups": [
            {
                "first_block": g[0],
                "last_block": g[-1],
                "block_count": len(g),
                "start_offset": g[0] * BLOCK,
                "end_offset_exclusive": min(len(a), (g[-1] + 1) * BLOCK),
            }
            for g in block_groups
        ],
        "per_block": per_block,
        "mirror_delta_bytes": MIRROR,
        "mirror_pairs": mirror_pairs,
        "zlib_changed_region_comparison": z_compare,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - frozen save changed-region analysis",
        f"A: {pa.parent.parent.parent.name} sha256={before[str(pa)]}",
        f"B: {pb.parent.parent.parent.name} sha256={before[str(pb)]}",
        f"Different 4 KiB blocks: {len(indices)}",
        f"Groups: {len(block_groups)}",
        f"Mirror pairs (+16 MiB): {len(mirror_pairs)}",
        "",
    ]
    for g in report["groups"]:
        lines.append(
            "group blocks={first_block}-{last_block} count={block_count} offsets={start_offset}-{end_offset_exclusive}".format(**g)
        )
    lines.append("")
    if mirror_pairs:
        best = sorted(mirror_pairs, key=lambda x: x["delta_equal_fraction"], reverse=True)[:20]
        lines.append("Top mirrored-delta similarities:")
        for p in best:
            lines.append(
                f"  {p['block_a']} -> {p['block_b']} delta={p['offset_delta']} equal_fraction={p['delta_equal_fraction']}"
            )
    lines.append("")
    lines.append(f"Zlib streams compared in changed-region windows: {len(z_compare)}")
    for z in z_compare:
        if z["offset"] == 43363 or not z["same_decompressed_sha256"] or (z.get("a") and z["a"].get("pattern_hits")) or (z.get("b") and z["b"].get("pattern_hits")):
            lines.append(
                f"  offset={z['offset']} presentA={z['present_a']} presentB={z['present_b']} same={z['same_decompressed_sha256']}"
            )
            for label in ("a", "b"):
                e = z.get(label)
                if e:
                    lines.append(
                        f"    {label.upper()}: bytes={e['decompressed_bytes']} sha256={e['sha256']} hits={e['pattern_hits']}"
                    )
                    if e.get("ravenKilled_excerpt"):
                        lines.append(f"      ravenKilled_excerpt={e['ravenKilled_excerpt']}")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"FROZEN_SAVE_DIFF_REGIONS_PASSED blocks={len(indices)} groups={len(block_groups)} mirror_pairs={len(mirror_pairs)} zlib={len(z_compare)}")
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
