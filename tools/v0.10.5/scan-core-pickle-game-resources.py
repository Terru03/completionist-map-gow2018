"""Locate core.pickle outside GoW.exe in installed game resources.

Read-only, version-locked scan of the God of War installation directory. The
native checkpoint driver loads package.loaded["core.pickle"], but no static
native registration table was found. This scanner checks whether the module or
its characteristic symbols are stored as Lua/bytecode/resource data elsewhere
in the install (including WADs).

No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
CONTEXT_BYTES = 96
MAX_MATCHES_PER_PATTERN_PER_FILE = 16

# These file types cannot plausibly contain the Lua persistence module and can
# account for a large amount of installation data. WAD/pack/bin/dat/dll/exe and
# unknown extensions are intentionally NOT skipped.
SKIP_EXTENSIONS = {
    ".wem", ".wav", ".ogg", ".flac", ".mp3", ".m4a",
    ".bik", ".bk2", ".mp4", ".avi", ".mov", ".webm",
    ".dds", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp",
}

NEEDLE_TEXTS = (
    "core.pickle",
    "OnPickleInternal",
    "OnUnpickleInternal",
    "__PickleTable",
    "__SoftPickleTable",
    "__prevunpickle",
    "function Pickle",
    "function Unpickle",
    "CanPickle",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def printable_context(data: bytes) -> str:
    chars = []
    for b in data:
        if 0x20 <= b <= 0x7E:
            chars.append(chr(b))
        elif b in (9, 10, 13):
            chars.append(" ")
        else:
            chars.append(".")
    return "".join(chars)


def patterns():
    out = []
    for text in NEEDLE_TEXTS:
        out.append({"text": text, "encoding": "ascii", "bytes": text.encode("ascii")})
        out.append({"text": text, "encoding": "utf-16le", "bytes": text.encode("utf-16le")})
    return out


def scan_file(path: Path, root: Path, pats):
    stat = path.stat()
    size = stat.st_size
    if size <= 0:
        return [], size

    hits = []
    with path.open("rb") as f:
        try:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except (ValueError, OSError):
            return [], size
        try:
            for pat in pats:
                pos = 0
                count = 0
                needle = pat["bytes"]
                while count < MAX_MATCHES_PER_PATTERN_PER_FILE:
                    idx = mm.find(needle, pos)
                    if idx < 0:
                        break
                    lo = max(0, idx - CONTEXT_BYTES)
                    hi = min(size, idx + len(needle) + CONTEXT_BYTES)
                    ctx = bytes(mm[lo:hi])
                    hits.append({
                        "file": str(path.relative_to(root)),
                        "file_size": size,
                        "offset": idx,
                        "offset_hex": f"0x{idx:X}",
                        "needle": pat["text"],
                        "encoding": pat["encoding"],
                        "context_ascii": printable_context(ctx),
                        "context_hex": ctx.hex(),
                    })
                    count += 1
                    pos = idx + max(1, len(needle))
        finally:
            mm.close()
    return hits, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    root = Path(args.game_root).resolve()
    if not root.is_dir():
        raise RuntimeError(f"game root not found: {root}")

    exe = root / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"missing {exe}")
    exe_hash = sha256(exe)
    if exe_hash.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {exe_hash}")

    pats = patterns()
    files_scanned = 0
    bytes_scanned = 0
    files_skipped_media = 0
    bytes_skipped_media = 0
    unreadable = []
    hits = []

    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p).lower()):
        try:
            size = path.stat().st_size
        except OSError as exc:
            unreadable.append({"file": str(path.relative_to(root)), "error": str(exc)})
            continue

        if path.suffix.lower() in SKIP_EXTENSIONS:
            files_skipped_media += 1
            bytes_skipped_media += size
            continue

        try:
            file_hits, scanned_size = scan_file(path, root, pats)
        except (OSError, PermissionError) as exc:
            unreadable.append({"file": str(path.relative_to(root)), "error": str(exc)})
            continue

        files_scanned += 1
        bytes_scanned += scanned_size
        hits.extend(file_hits)

    exe_rel = str(exe.relative_to(root)).lower()
    exe_hits = [h for h in hits if h["file"].lower() == exe_rel]
    non_exe_hits = [h for h in hits if h["file"].lower() != exe_rel]

    # Stronger candidates are files carrying several module-specific terms.
    by_file = {}
    for h in non_exe_hits:
        row = by_file.setdefault(h["file"], {"file": h["file"], "terms": set(), "hits": 0})
        row["terms"].add(h["needle"])
        row["hits"] += 1
    candidate_files = [
        {"file": row["file"], "distinct_terms": sorted(row["terms"]), "hit_count": row["hits"]}
        for row in by_file.values()
    ]
    candidate_files.sort(key=lambda r: (-len(r["distinct_terms"]), -r["hit_count"], r["file"].lower()))

    if candidate_files:
        conclusion = "NON_EXE_CORE_PICKLE_RESOURCE_CANDIDATES_FOUND"
    else:
        conclusion = "NO_NON_EXE_RAW_CORE_PICKLE_HITS"

    result = {
        "schema": 1,
        "analysis": "core_pickle_game_resource_scan",
        "game_root": str(root),
        "gow_exe_sha256": exe_hash,
        "needles": list(NEEDLE_TEXTS),
        "files_scanned": files_scanned,
        "bytes_scanned": bytes_scanned,
        "files_skipped_media": files_skipped_media,
        "bytes_skipped_media": bytes_skipped_media,
        "unreadable_files": unreadable,
        "hit_count": len(hits),
        "gow_exe_hit_count": len(exe_hits),
        "non_exe_hit_count": len(non_exe_hits),
        "candidate_files": candidate_files,
        "non_exe_hits": non_exe_hits,
        "gow_exe_hits": exe_hits,
        "conclusion": conclusion,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - core.pickle installed game resource scan",
        f"game_root={root}",
        f"gow_exe_sha256={exe_hash}",
        f"files_scanned={files_scanned}",
        f"bytes_scanned={bytes_scanned}",
        f"files_skipped_media={files_skipped_media}",
        f"bytes_skipped_media={bytes_skipped_media}",
        f"unreadable_files={len(unreadable)}",
        f"hit_count={len(hits)}",
        f"gow_exe_hit_count={len(exe_hits)}",
        f"non_exe_hit_count={len(non_exe_hits)}",
        f"conclusion={conclusion}",
        "",
        "CANDIDATE FILES",
    ]
    if not candidate_files:
        lines.append("  (none)")
    for row in candidate_files:
        lines.append(
            f"  {row['file']} distinct_terms={len(row['distinct_terms'])} hits={row['hit_count']} "
            f"terms={','.join(row['distinct_terms'])}"
        )

    lines.extend(["", "NON-EXE HITS"])
    if not non_exe_hits:
        lines.append("  (none)")
    for h in non_exe_hits:
        lines.append(
            f"  file={h['file']} offset={h['offset_hex']} needle={h['needle']!r} encoding={h['encoding']}"
        )
        lines.append(f"    ascii={h['context_ascii']}")
        lines.append(f"    hex={h['context_hex']}")

    lines.extend(["", "GOW.EXE HITS (expected native string references)"])
    if not exe_hits:
        lines.append("  (none)")
    for h in exe_hits:
        lines.append(
            f"  offset={h['offset_hex']} needle={h['needle']!r} encoding={h['encoding']}"
        )

    if unreadable:
        lines.extend(["", "UNREADABLE FILES"])
        for row in unreadable:
            lines.append(f"  {row['file']}: {row['error']}")

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("CORE_PICKLE_GAME_RESOURCE_SCAN_PASSED")
    print(f"conclusion={conclusion}")
    print(f"non_exe_hit_count={len(non_exe_hits)} candidate_files={len(candidate_files)}")


if __name__ == "__main__":
    main()
