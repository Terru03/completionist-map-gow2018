"""Read-only scan for the runtime Compass marker-type validation source/registry.

The packed CompletionistRaven CompassIconClass proof showed that a structurally
valid type-0x11E export is still rejected synchronously by the Lua wrapper:

    [string "local classlib = require(\"core.class\")..."]:4018:
    trying to set invalid type 'CompletionistRaven' on compass marker '<unknown>'

This probe searches recovered Lua/text sources and targeted executable/DLL bytes
for the wrapper, its stock CompassIconClass names, and likely validation tables.
It never writes into the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

RESULT = "READ_ONLY_COMPASS_TYPE_VALIDATION_SCAN"

TEXT_EXTS = {
    ".lua", ".txt", ".json", ".xml", ".ini", ".cfg", ".csv", ".log",
    ".md", ".py", ".ps1", ".bat", ".cmd", ".yaml", ".yml",
}

NEEDLES = [
    "trying to set invalid type",
    'local classlib = require("core.class")',
    "core.class",
    "CompassIconClass",
    "FindMarkersByIconClass",
    "game.Compass.ShowMarker",
    "Compass.ShowMarker",
    "DockPoint",
    "CompletionistRaven",
]

DISTINCTIVE_STOCK_CLASSES = [
    "VendorLocation",
    "Valkyrie",
    "DockPoint",
    "FastTravel",
    "AreaEntrance",
    "ChiselLocation",
    "FightLocation",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return str(path.resolve())


def printable_window(raw: bytes, center: int, radius: int = 384) -> str:
    start = max(0, center - radius)
    end = min(len(raw), center + radius)
    blob = raw[start:end]
    # Keep tabs/newlines; replace other control/non-ASCII bytes with dots.
    chars = []
    for b in blob:
        if b in (9, 10, 13) or 32 <= b <= 126:
            chars.append(chr(b))
        else:
            chars.append(".")
    return "".join(chars)


def text_context(text: str, match_start: int, match_end: int, radius_lines: int = 12) -> dict:
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())
    line = 1
    for i, start in enumerate(starts):
        if start > match_start:
            break
        line = i + 1
    lines = text.splitlines()
    lo = max(1, line - radius_lines)
    hi = min(len(lines), line + radius_lines)
    context = "\n".join(f"{n:05d}: {lines[n-1]}" for n in range(lo, hi + 1))
    return {"line": line, "context_start_line": lo, "context_end_line": hi, "context": context}


def scan_text_file(path: Path, source_root: Path) -> dict | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > 64 * 1024 * 1024:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            return None

    hits = []
    lower = text.lower()
    for needle in NEEDLES:
        pos = 0
        nlow = needle.lower()
        count = 0
        while True:
            idx = lower.find(nlow, pos)
            if idx < 0:
                break
            count += 1
            if len(hits) < 80:
                ctx = text_context(text, idx, idx + len(needle))
                hits.append({"needle": needle, "offset": idx, **ctx})
            pos = idx + max(1, len(needle))
        # Do not emit per-needle zero counts here.

    present_stock = [name for name in DISTINCTIVE_STOCK_CLASSES if name.lower() in lower]
    registry_like = len(present_stock) >= 3
    if not hits and not registry_like:
        return None

    return {
        "path": str(path.resolve()),
        "relative_to_source_root": safe_rel(path, source_root),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "hits": hits,
        "distinctive_stock_classes_present": present_stock,
        "registry_like_stock_class_cluster": registry_like,
    }


def scan_binary_file(path: Path, base: Path) -> dict | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    hits = []
    for needle in NEEDLES + DISTINCTIVE_STOCK_CLASSES:
        nb = needle.encode("ascii", "ignore")
        start = 0
        count = 0
        while nb:
            idx = raw.find(nb, start)
            if idx < 0:
                break
            count += 1
            if len(hits) < 120:
                hits.append({
                    "needle": needle,
                    "offset": f"0x{idx:X}",
                    "window": printable_window(raw, idx),
                })
            start = idx + max(1, len(nb))
        if count and len(hits) >= 120:
            break
    if not hits:
        return None
    return {
        "path": str(path.resolve()),
        "relative_to_game_root": safe_rel(path, base),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "hits": hits,
    }


def collect_text_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() in TEXT_EXTS:
                out.append(p)
        except OSError:
            pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("report must stay outside the game directory")

    source_roots = [
        game / "mods/lua_source",
        game / "mods/lua",
        repo / "dist/gowlua-src",
        repo / "tools",
        repo / "docs",
        repo / "archive/field-logs",
    ]

    text_results = []
    seen = set()
    scanned_text_files = 0
    for root in source_roots:
        for path in collect_text_files(root):
            rp = str(path.resolve()).lower()
            if rp in seen:
                continue
            seen.add(rp)
            scanned_text_files += 1
            row = scan_text_file(path, root)
            if row is not None:
                row["source_root"] = str(root.resolve())
                text_results.append(row)

    # Target binaries only. Avoid crawling huge game asset archives.
    binary_candidates = []
    for p in [game / "GoW.exe"]:
        if p.is_file():
            binary_candidates.append(p)
    for root in [game, game / "mods"]:
        if root.exists():
            for pattern in ("*.dll", "*.exe"):
                try:
                    binary_candidates.extend(p for p in root.glob(pattern) if p.is_file())
                except OSError:
                    pass

    # De-duplicate while preserving order.
    unique_bins = []
    bseen = set()
    for p in binary_candidates:
        key = str(p.resolve()).lower()
        if key not in bseen:
            bseen.add(key)
            unique_bins.append(p)

    binary_results = []
    for path in unique_bins:
        row = scan_binary_file(path, game)
        if row is not None:
            binary_results.append(row)

    exact_error_sources = []
    core_class_sources = []
    registry_candidates = []
    for row in text_results:
        needles = {h["needle"] for h in row["hits"]}
        if "trying to set invalid type" in needles:
            exact_error_sources.append(row["path"])
        if "core.class" in needles or 'local classlib = require("core.class")' in needles:
            core_class_sources.append(row["path"])
        if row["registry_like_stock_class_cluster"]:
            registry_candidates.append({
                "path": row["path"],
                "classes": row["distinctive_stock_classes_present"],
            })

    binary_exact_error = []
    binary_core_class = []
    for row in binary_results:
        needles = {h["needle"] for h in row["hits"]}
        if "trying to set invalid type" in needles:
            binary_exact_error.append(row["path"])
        if "core.class" in needles or 'local classlib = require("core.class")' in needles:
            binary_core_class.append(row["path"])

    conclusion = "VALIDATION_SOURCE_NOT_RECOVERED"
    if exact_error_sources or binary_exact_error:
        conclusion = "EXACT_INVALID_TYPE_VALIDATION_TEXT_LOCATED"
    elif core_class_sources or binary_core_class:
        conclusion = "CORE_CLASS_WRAPPER_SOURCE_OR_BINARY_LOCATED"
    elif registry_candidates:
        conclusion = "STOCK_COMPASS_TYPE_REGISTRY_CANDIDATE_LOCATED"

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "game_root": str(game),
        "repo_root": str(repo),
        "needles": NEEDLES,
        "distinctive_stock_classes": DISTINCTIVE_STOCK_CLASSES,
        "scanned_text_files": scanned_text_files,
        "scanned_target_binaries": len(unique_bins),
        "exact_error_sources": exact_error_sources,
        "core_class_sources": core_class_sources,
        "binary_exact_error_sources": binary_exact_error,
        "binary_core_class_sources": binary_core_class,
        "registry_candidates": registry_candidates,
        "text_results": text_results,
        "binary_results": binary_results,
        "conclusion": conclusion,
        "next_gate": (
            "If the exact wrapper/registry is located, decode the validation table or accepted-type lookup before any further DCB mutation. "
            "Do not retry CompletionistRaven runtime registration by changing only wad_r_perm.dcb storage."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(RESULT)
    print(f"  conclusion: {conclusion}")
    print(f"  text files scanned: {scanned_text_files}")
    print(f"  target binaries scanned: {len(unique_bins)}")
    print(f"  exact error sources: {len(exact_error_sources) + len(binary_exact_error)}")
    print(f"  core.class sources: {len(core_class_sources) + len(binary_core_class)}")
    print(f"  registry candidates: {len(registry_candidates)}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
