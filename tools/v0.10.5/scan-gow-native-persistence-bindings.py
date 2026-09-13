"""Read-only targeted string scan of God of War native binaries for persistence/streaming bindings.

This helper is deliberately conservative. It scans only GoW.exe and root-level DLLs
inside the supplied game directory, extracts printable ASCII / UTF-16LE strings that
contain a small set of persistence, checkpoint, SubObject, object-loading, WAD, or
streaming keywords, and records short neighbouring-string context. It hashes every
binary before and after the scan and fails if any source file changes.

It never launches the game and never opens the user's active save directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
import re
import sys
from collections import Counter

ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")

# Keep the scan focused on names that could expose a read/load persistence path.
KEYWORDS = (
    "OnRestoreCheckpoint",
    "OnSaveCheckpoint",
    "RestoreCheckpoint",
    "SaveCheckpoint",
    "StoreCheckpoint",
    "SoftSave",
    "SubObject",
    "LoadWad",
    "UnloadWad",
    "LoadObject",
    "FindObject",
    "GetObjectState",
    "ObjectState",
    "LoadLevel",
    "RequestLevel",
    "Preload",
    "Streaming",
    "Persistence",
    "Persistent",
    "Serialize",
    "Deserialize",
    "Checkpoint",
    "ScriptBinding",
    "LuaBinding",
)
KEYWORDS_LOWER = tuple(k.lower() for k in KEYWORDS)
MAX_TEXT = 320
MAX_CONTEXT_STRINGS = 24
CONTEXT_RADIUS = 384
MAX_HITS_PER_FILE = 5000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_keywords(text: str) -> list[str]:
    low = text.lower()
    return [original for original, needle in zip(KEYWORDS, KEYWORDS_LOWER) if needle in low]


def clean_text(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 3] + "..."


def context_strings(window: bytes) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for match in ASCII_RE.finditer(window):
        value = clean_text(match.group(0).decode("ascii", "ignore"))
        if value and value not in seen:
            seen.add(value)
            values.append(value)
            if len(values) >= MAX_CONTEXT_STRINGS:
                return values

    for alignment in (0, 1):
        chunk = window[alignment:]
        for match in UTF16_RE.finditer(chunk):
            raw = match.group(0)
            value = clean_text(raw[::2].decode("ascii", "ignore"))
            if value and value not in seen:
                seen.add(value)
                values.append(value)
                if len(values) >= MAX_CONTEXT_STRINGS:
                    return values
    return values


def record_hit(mm: mmap.mmap, raw_offset: int, raw_len: int, encoding: str, text: str) -> dict:
    lo = max(0, raw_offset - CONTEXT_RADIUS)
    hi = min(len(mm), raw_offset + raw_len + CONTEXT_RADIUS)
    return {
        "offset": raw_offset,
        "offset_hex": hex(raw_offset),
        "encoding": encoding,
        "keywords": target_keywords(text),
        "text": clean_text(text),
        "nearby_strings": context_strings(mm[lo:hi]),
    }


def scan_file(path: Path) -> dict:
    hits: list[dict] = []
    truncated = False
    with path.open("rb") as f:
        if path.stat().st_size == 0:
            return {"hits": hits, "hits_truncated": False}
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for match in ASCII_RE.finditer(mm):
                text = match.group(0).decode("ascii", "ignore")
                if not target_keywords(text):
                    continue
                hits.append(record_hit(mm, match.start(), len(match.group(0)), "ascii", text))
                if len(hits) >= MAX_HITS_PER_FILE:
                    truncated = True
                    break

            if not truncated:
                # Try both byte alignments so odd-address UTF-16LE strings are not missed.
                for alignment in (0, 1):
                    data = mm[alignment:]
                    for match in UTF16_RE.finditer(data):
                        raw = match.group(0)
                        text = raw[::2].decode("ascii", "ignore")
                        if not target_keywords(text):
                            continue
                        raw_offset = alignment + match.start()
                        hits.append(record_hit(mm, raw_offset, len(raw), "utf16le", text))
                        if len(hits) >= MAX_HITS_PER_FILE:
                            truncated = True
                            break
                    if truncated:
                        break

    # Exact same string can sometimes be discovered through overlapping encodings; retain
    # distinct offsets/encodings but remove literal duplicate records.
    deduped: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for hit in sorted(hits, key=lambda h: (h["offset"], h["encoding"], h["text"])):
        key = (hit["offset"], hit["encoding"], hit["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return {"hits": deduped, "hits_truncated": truncated}


def discover_binaries(game_root: Path) -> list[Path]:
    candidates: dict[str, Path] = {}
    exe = game_root / "GoW.exe"
    if exe.is_file():
        candidates[str(exe.resolve()).lower()] = exe.resolve()
    for pattern in ("*.dll", "*.DLL"):
        for path in game_root.glob(pattern):
            if path.is_file():
                candidates[str(path.resolve()).lower()] = path.resolve()
    return sorted(candidates.values(), key=lambda p: (p.name.lower() != "gow.exe", p.name.lower()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.expanduser().resolve()
    if not game_root.is_dir():
        raise RuntimeError(f"Game root not found: {game_root}")

    active_save = (Path.home() / "Saved Games" / "God of War").resolve()
    binaries = discover_binaries(game_root)
    if not binaries:
        raise RuntimeError(f"No GoW.exe or root-level DLLs found under {game_root}")

    before = {str(path): sha256_file(path) for path in binaries}
    files: list[dict] = []
    keyword_counts: Counter[str] = Counter()

    for path in binaries:
        scanned = scan_file(path)
        for hit in scanned["hits"]:
            keyword_counts.update(hit["keywords"])
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": before[str(path)],
                "hit_count": len(scanned["hits"]),
                "hits_truncated": scanned["hits_truncated"],
                "hits": scanned["hits"],
            }
        )

    after = {str(path): sha256_file(path) for path in binaries}
    changed = [path for path in before if before[path] != after[path]]
    if changed:
        raise RuntimeError("Source binary hash changed during read-only scan: " + ", ".join(changed))

    report = {
        "schema": 1,
        "scan_kind": "read_only_native_persistence_binding_string_scan",
        "game_root": str(game_root),
        "active_save_directory": str(active_save),
        "active_save_opened": False,
        "binary_count": len(binaries),
        "keyword_counts": dict(sorted(keyword_counts.items(), key=lambda x: (-x[1], x[0].lower()))),
        "files": files,
        "safety": {
            "source_hashes_unchanged": True,
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "scan_only": True,
        },
    }

    lines = [
        "Completionist Map - native persistence/streaming binding string scan",
        f"game_root={game_root}",
        f"binaries={len(binaries)} total_hits={sum(x['hit_count'] for x in files)}",
        "source_hashes_unchanged=true active_save_opened=false game_launched=false",
        "",
        "Keyword counts:",
    ]
    if keyword_counts:
        for key, count in sorted(keyword_counts.items(), key=lambda x: (-x[1], x[0].lower())):
            lines.append(f"  {key}: {count}")
    else:
        lines.append("  none")

    for file in files:
        lines.append("")
        lines.append(
            f"=== {file['name']} bytes={file['bytes']} hits={file['hit_count']} "
            f"sha256={file['sha256']} truncated={str(file['hits_truncated']).lower()} ==="
        )
        for hit in file["hits"]:
            lines.append(
                f"{hit['offset_hex']} [{hit['encoding']}] [{','.join(hit['keywords'])}] {hit['text']}"
            )
            if hit["nearby_strings"]:
                lines.append("  nearby: " + " | ".join(hit["nearby_strings"][:12]))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "NATIVE_PERSISTENCE_BINDING_SCAN_PASSED "
        f"binaries={len(binaries)} hits={sum(x['hit_count'] for x in files)}"
    )
    print("source_hashes_unchanged=true active_save_opened=false game_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
