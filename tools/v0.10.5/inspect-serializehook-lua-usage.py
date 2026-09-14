from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
TERMS = ("SerializeHook", "__serialized_hook_queue")
CONTEXT = 3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    root = Path(args.game_root).resolve()
    exe = root / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"missing {exe}")
    digest = sha256(exe)
    if digest.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")

    source_root = root / "mods" / "lua_source"
    if not source_root.is_dir():
        raise RuntimeError(f"missing extracted Lua source tree: {source_root}")

    hits = []
    files_scanned = 0
    for p in sorted(source_root.rglob("*.lua"), key=lambda x: str(x).lower()):
        files_scanned += 1
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            matched = [t for t in TERMS if t in line]
            if not matched:
                continue
            lo = max(0, i - CONTEXT)
            hi = min(len(lines), i + CONTEXT + 1)
            hits.append({
                "file": str(p.relative_to(root)),
                "line": i + 1,
                "terms": matched,
                "context": [f"{n+1}: {lines[n]}" for n in range(lo, hi)],
            })

    result = {
        "schema": 1,
        "analysis": "serializehook_lua_usage",
        "gow_exe_sha256": digest,
        "files_scanned": files_scanned,
        "hit_count": len(hits),
        "hits": hits,
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }
    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")

    out = [
        "Completionist Map - SerializeHook Lua usage inspection",
        f"gow_exe_sha256={digest}",
        f"files_scanned={files_scanned}",
        f"hit_count={len(hits)}",
        "",
    ]
    if not hits:
        out.append("(no Lua call sites found)")
    for h in hits:
        out.append(f"FILE {h['file']} line={h['line']} terms={','.join(h['terms'])}")
        out.extend("  " + x for x in h["context"])
        out.append("")
    out.extend(["game_launched=false", "save_opened=false", "progression_written=false"])
    Path(args.output_text).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("SERIALIZEHOOK_LUA_USAGE_SCAN_PASSED")
    print(f"files_scanned={files_scanned} hit_count={len(hits)}")


if __name__ == "__main__":
    main()
