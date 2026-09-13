"""Read-only structural analysis of Desktop God of War save backups.

The tool compares recognized backup game.sav files, reports only structural
statistics, and probes common compressed-stream signatures for the already-known
Veithurgard Raven identifiers. It never writes save/game files and never scans the
active save directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import zlib

REFERENCE_PATTERNS = {
    "instance_guid_ascii": b"642d0d16-4af0-a5d4-076e-77933c549a5d",
    "instance_guid_compact": b"642d0d164af0a5d4076e77933c549a5d",
    "script_guid_ascii": b"2f0f1759-4a6c-864f-c4db-caa4bbc7ea61",
    "parent_quest": b"RegionSummary_VF_Raven_Parent",
    "marker_uid": b"E15E6BC82AE2773E",
    "raven_killed": b"ravenKilled",
}

MAGICS = {
    "gzip": bytes.fromhex("1f8b08"),
    "zstd": bytes.fromhex("28b52ffd"),
    "lz4_frame": bytes.fromhex("04224d18"),
    "xz": bytes.fromhex("fd377a585a00"),
    "bzip2": b"BZh",
    "zip_local": bytes.fromhex("504b0304"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    total = len(data)
    return -sum((c / total) * math.log2(c / total) for c in counts if c)


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


def save_file_for(backup: Path) -> Path | None:
    matches = [p for p in backup.rglob("game.sav") if p.is_file()]
    return matches[0] if len(matches) == 1 else None


def find_all(data: bytes, needle: bytes, limit: int = 10000) -> list[int]:
    out: list[int] = []
    pos = 0
    while len(out) < limit:
        at = data.find(needle, pos)
        if at < 0:
            break
        out.append(at)
        pos = at + 1
    return out


def page_stats(data: bytes, page_size: int) -> list[dict]:
    rows = []
    for idx, start in enumerate(range(0, len(data), page_size)):
        chunk = data[start:start + page_size]
        rows.append({
            "index": idx,
            "offset": start,
            "bytes": len(chunk),
            "sha256": hashlib.sha256(chunk).hexdigest(),
            "entropy": round(entropy(chunk), 4),
            "zero_fraction": round(chunk.count(0) / len(chunk), 6) if chunk else 0.0,
            "printable_fraction": round(sum(32 <= b < 127 for b in chunk) / len(chunk), 6) if chunk else 0.0,
        })
    return rows


def diff_runs(a: bytes, b: bytes) -> tuple[list[tuple[int, int]], int]:
    limit = min(len(a), len(b))
    runs: list[tuple[int, int]] = []
    start = None
    diff_bytes = 0
    for i in range(limit):
        different = a[i] != b[i]
        if different:
            diff_bytes += 1
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i - start))
            start = None
    if start is not None:
        runs.append((start, limit - start))
    if len(a) != len(b):
        runs.append((limit, abs(len(a) - len(b))))
        diff_bytes += abs(len(a) - len(b))
    return runs, diff_bytes


def common_prefix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a: bytes, b: bytes, prefix: int) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n - prefix and a[len(a) - 1 - i] == b[len(b) - 1 - i]:
        i += 1
    return i


def zlib_candidates(data: bytes) -> list[int]:
    # Valid zlib CMF/FLG combinations satisfy header % 31 == 0 and CM=8.
    out = []
    for i in range(len(data) - 2):
        cmf, flg = data[i], data[i + 1]
        if (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) | flg) % 31 == 0:
            out.append(i)
            if len(out) >= 2000:
                break
    return out


def probe_zlib(data: bytes, offsets: list[int]) -> dict:
    successful = []
    raven_hits = []
    attempted = 0
    for at in offsets[:500]:
        attempted += 1
        try:
            raw = zlib.decompress(data[at:])
        except Exception:
            continue
        if len(raw) < 32:
            continue
        successful.append({"offset": at, "decompressed_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        found = [name for name, needle in REFERENCE_PATTERNS.items() if needle in raw]
        if found:
            raven_hits.append({"offset": at, "patterns": found, "decompressed_bytes": len(raw)})
        if len(successful) >= 50:
            break
    return {
        "candidates_seen": len(offsets),
        "attempted": attempted,
        "successful_count": len(successful),
        "successful_streams": successful,
        "raven_hits": raven_hits,
    }


def structural_record(path: Path, data: bytes) -> dict:
    magic_hits = {name: find_all(data, magic, 1000) for name, magic in MAGICS.items()}
    zc = zlib_candidates(data)
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header_64_hex": data[:64].hex(),
        "tail_64_hex": data[-64:].hex(),
        "entropy": round(entropy(data[: min(len(data), 4 * 1024 * 1024)]), 4),
        "zero_fraction": round(data.count(0) / len(data), 6) if data else 0.0,
        "printable_fraction": round(sum(32 <= b < 127 for b in data) / len(data), 6) if data else 0.0,
        "magic_hits": magic_hits,
        "zlib_probe": probe_zlib(data, zc),
        "pages_1MiB": page_stats(data, 1024 * 1024),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    backups = candidate_backup_dirs(desktop)
    selected: list[tuple[Path, Path]] = []
    for backup in backups:
        try:
            backup.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing active-save overlap: {backup}")
        save = save_file_for(backup)
        if save is not None:
            selected.append((backup, save))

    if len(selected) < 2:
        print(f"SAVE_STRUCTURE_NEEDS_TWO_BACKUPS found={len(selected)}")
        return 2

    before = {str(save): sha256_file(save) for _, save in selected}
    records = []
    blobs = []
    for backup, save in selected:
        data = save.read_bytes()
        blobs.append((backup, save, data))
        rec = structural_record(save, data)
        rec["backup_name"] = backup.name
        rec["relative_save_path"] = str(save.relative_to(backup)).replace("\\", "/")
        records.append(rec)

    pairs = []
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            ba, _, a = blobs[i]
            bb, _, b = blobs[j]
            runs, diff_bytes = diff_runs(a, b)
            prefix = common_prefix(a, b)
            suffix = common_suffix(a, b, prefix)
            blocks_4k = max((max(len(a), len(b)) + 4095) // 4096, 1)
            same_4k = 0
            different_4k_indices = []
            for block in range(blocks_4k):
                sa = a[block * 4096:(block + 1) * 4096]
                sb = b[block * 4096:(block + 1) * 4096]
                if sa == sb:
                    same_4k += 1
                else:
                    different_4k_indices.append(block)
            pairs.append({
                "a": ba.name,
                "b": bb.name,
                "same_size": len(a) == len(b),
                "common_prefix_bytes": prefix,
                "common_suffix_bytes": suffix,
                "different_bytes": diff_bytes,
                "different_fraction": round(diff_bytes / max(len(a), len(b)), 8),
                "diff_run_count": len(runs),
                "diff_run_length_min": min((length for _, length in runs), default=0),
                "diff_run_length_max": max((length for _, length in runs), default=0),
                "diff_run_length_total": sum(length for _, length in runs),
                "first_50_diff_runs": [{"offset": off, "length": length} for off, length in runs[:50]],
                "blocks_4k_total": blocks_4k,
                "blocks_4k_same": same_4k,
                "blocks_4k_different": blocks_4k - same_4k,
                "different_4k_indices_first_200": different_4k_indices[:200],
            })

    after = {str(save): sha256_file(save) for _, save in selected}
    if before != after:
        raise RuntimeError("Backup source hash changed during structural scan")

    report = {
        "schema": 1,
        "scan_kind": "read_only_save_container_structure",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_files_modified": False,
        "backup_count": len(selected),
        "files": records,
        "pairwise": pairs,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - God of War save container structural analysis",
        f"Backups analyzed: {len(selected)}",
        "Active save directory not opened: true",
        "Source hashes unchanged: true",
        "",
    ]
    for rec in records:
        lines.append(f"=== {rec['backup_name']} ===")
        lines.append(f"bytes={rec['bytes']} sha256={rec['sha256']}")
        lines.append(f"entropy={rec['entropy']} zero_fraction={rec['zero_fraction']} printable_fraction={rec['printable_fraction']}")
        for name, offsets in rec["magic_hits"].items():
            if offsets:
                lines.append(f"{name}_signatures={len(offsets)} first={offsets[:20]}")
        zp = rec["zlib_probe"]
        lines.append(f"zlib_candidates={zp['candidates_seen']} attempted={zp['attempted']} successful={zp['successful_count']} raven_hits={len(zp['raven_hits'])}")
        lines.append("")
    for pair in pairs:
        lines.append(f"=== DIFF {pair['a']} <> {pair['b']} ===")
        lines.append(f"different_bytes={pair['different_bytes']} fraction={pair['different_fraction']}")
        lines.append(f"common_prefix={pair['common_prefix_bytes']} common_suffix={pair['common_suffix_bytes']}")
        lines.append(f"diff_runs={pair['diff_run_count']} max_run={pair['diff_run_length_max']}")
        lines.append(f"4k_blocks_same={pair['blocks_4k_same']} different={pair['blocks_4k_different']} total={pair['blocks_4k_total']}")
        lines.append("")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SAVE_CONTAINER_STRUCTURE_PASSED")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
