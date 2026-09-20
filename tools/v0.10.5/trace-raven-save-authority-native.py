#!/usr/bin/env python3
"""Targeted static trace for the remaining Raven save-authority boundary.

Uses the already-built GoW SQLite research index plus extracted Lua sources.
No game launch, save access, process access, or game-file writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from collections import defaultdict

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

EXACT_NATIVE_TERMS = [
    "EVT_LoadSaveData",
    "EVT_LoadSaveFile_Done",
    "EVT_ManualSaveComplete",
    "EVT_AutoSave",
]

NATIVE_CONTAINS = [
    "LoadSave",
    "SaveFile",
    "SaveSlot",
    "ManualSave",
    "AutoSave",
    "SaveData",
    "LoadData",
    "checkpoint",
    "bookmark",
]

LUA_TERMS = [
    "currSaveSlotIndex",
    "GetSaveSlotList",
    "IsSlotValid",
    "LoadSave",
    "LoadGame",
    "LoadSlot",
    "SaveSlot",
    "GetSelectedItem",
    "RestartFromCheckpoint",
    "ManualSaveComplete",
    "ResetIntoNewGamePlus",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def function_row(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? "
        "ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if not row:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def graph_for_function(con: sqlite3.Connection, fn_begin: int):
    callers = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges "
        "WHERE dest BETWEEN ? AND ? OR target_fn=? ORDER BY site LIMIT 200",
        (fn_begin, fn_begin, fn_begin),
    ))
    callees = rows(con.execute(
        "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site LIMIT 300",
        (fn_begin,),
    ))
    strings = rows(con.execute(
        "SELECT site,mnemonic,target,target_string FROM rip_refs "
        "WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site LIMIT 300",
        (fn_begin,),
    ))
    return {"callers": callers, "callees": callees, "string_refs": strings}


def collect_exact_native(con: sqlite3.Connection):
    out = {}
    for term in EXACT_NATIVE_TERMS:
        strings = rows(con.execute(
            "SELECT rva,text FROM strings WHERE text=? ORDER BY rva", (term,)
        ))
        refs = []
        for s in strings:
            for ref in rows(con.execute(
                "SELECT site,src_fn,mnemonic,target,target_section,target_string "
                "FROM rip_refs WHERE target=? ORDER BY site",
                (s["rva"],),
            )):
                ref["function"] = function_row(con, ref["src_fn"])
                refs.append(ref)
        out[term] = {"strings": strings, "refs": refs}
    return out


def collect_save_load_native(con: sqlite3.Connection):
    by_fn: dict[int, dict] = {}
    seen = set()
    for term in NATIVE_CONTAINS:
        pattern = f"%{term}%"
        for ref in rows(con.execute(
            "SELECT site,src_fn,mnemonic,target,target_section,target_string "
            "FROM rip_refs WHERE target_string LIKE ? COLLATE NOCASE ORDER BY src_fn,site LIMIT 2500",
            (pattern,),
        )):
            key = (ref["site"], ref["target"])
            if key in seen:
                continue
            seen.add(key)
            fn = ref["src_fn"]
            bucket = by_fn.setdefault(fn, {
                "function": function_row(con, fn),
                "matches": [],
                "terms": set(),
            })
            bucket["matches"].append(ref)
            text = ref.get("target_string") or ""
            for candidate in NATIVE_CONTAINS + EXACT_NATIVE_TERMS:
                if candidate.lower() in text.lower():
                    bucket["terms"].add(candidate)

    ranked = []
    for fn, bucket in by_fn.items():
        graph = graph_for_function(con, fn)
        saveish = []
        for r in graph["string_refs"]:
            text = r.get("target_string") or ""
            if any(t.lower() in text.lower() for t in NATIVE_CONTAINS + EXACT_NATIVE_TERMS):
                saveish.append(r)
        score = len(bucket["matches"]) * 5 + len(bucket["terms"]) * 20
        exact_hits = sum(
            1 for m in bucket["matches"]
            if (m.get("target_string") or "") in EXACT_NATIVE_TERMS
        )
        score += exact_hits * 80
        ranked.append({
            "function_rva": fn,
            "score": score,
            "terms": sorted(bucket["terms"]),
            "matches": bucket["matches"],
            "save_load_string_refs": saveish,
            "callers": graph["callers"],
            "callees": graph["callees"],
            "function": bucket["function"],
        })
    ranked.sort(key=lambda x: (-x["score"], x["function_rva"]))
    return ranked[:120]


def scan_lua(game_root: Path):
    root = game_root / "mods" / "lua_source"
    result = []
    if not root.is_dir():
        return result

    likely = []
    settings = root / "gameart" / "ui" / "scripts" / "inworldmenu" / "settingsmenu.lua"
    if settings.is_file():
        likely.append(settings)

    for path in root.rglob("*.lua"):
        name = path.name.lower()
        pstr = str(path).lower()
        if path == settings:
            continue
        if "save" in name or "load" in name or "bookmark" in name or "ui" in pstr:
            likely.append(path)

    seen_files = set()
    for path in likely:
        if path in seen_files:
            continue
        seen_files.add(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        hit_lines = []
        for i, line in enumerate(lines):
            matched = [term for term in LUA_TERMS if term.lower() in line.lower()]
            if not matched:
                continue
            lo, hi = max(0, i - 12), min(len(lines), i + 13)
            hit_lines.append({
                "line": i + 1,
                "terms": matched,
                "text": line,
                "context_start": lo + 1,
                "context": [
                    f"{n+1:6d}: {lines[n]}" for n in range(lo, hi)
                ],
            })
        if hit_lines:
            result.append({
                "file": str(path.relative_to(game_root)).replace("\\", "/"),
                "hits": hit_lines,
            })
    return result


def format_hex(value):
    if value is None:
        return "NONE"
    return f"0x{int(value):X}"


def write_text(path: Path, result: dict):
    lines = [
        "Completionist Map - targeted Raven save authority trace",
        f"exe_sha256={result['exe_sha256']}",
        f"index={result['index']}",
        "mode=static read-only",
        "game_launched=false active_save_opened=false process_opened=false",
        "game_files_written=false save_written=false progression_written=false",
        "",
        "EXACT ENGINE EVENT STRING XREFS",
    ]
    for term, data in result["exact_native_terms"].items():
        lines.append(f"{term}: strings={len(data['strings'])} refs={len(data['refs'])}")
        for ref in data["refs"]:
            lines.append(
                f"  site={format_hex(ref['site'])} fn={format_hex(ref['src_fn'])} "
                f"{ref['mnemonic']} target={format_hex(ref['target'])}"
            )

    lines += ["", "TOP NATIVE SAVE/LOAD STRING OWNERS"]
    for rank, row in enumerate(result["ranked_native_functions"][:40], 1):
        fn = row["function"]
        fend = format_hex(fn["end"]) if fn else "NONE"
        lines.append(
            f"#{rank} fn={format_hex(row['function_rva'])}-{fend} "
            f"score={row['score']} terms={','.join(row['terms'])}"
        )
        for m in row["matches"][:24]:
            lines.append(
                f"  REF {format_hex(m['site'])} {m['mnemonic']} "
                f"{m.get('target_string')!r}"
            )
        for caller in row["callers"][:12]:
            lines.append(
                f"  CALLER fn={format_hex(caller['src_fn'])} site={format_hex(caller['site'])}"
            )
        for callee in row["callees"][:12]:
            target = callee.get("target_fn") or callee.get("dest")
            lines.append(
                f"  CALLEE site={format_hex(callee['site'])} target={format_hex(target)}"
            )

    lines += ["", "LUA SAVE/LOAD SELECTION SURFACE"]
    for file_row in result["lua_hits"]:
        lines.append(f"FILE {file_row['file']}")
        for hit in file_row["hits"]:
            lines.append(
                f"  HIT line={hit['line']} terms={','.join(hit['terms'])}: {hit['text'].strip()}"
            )
            lines.extend("    " + row for row in hit["context"])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    game_root = Path(args.game_root)
    exe = game_root / "GoW.exe"
    db = Path(args.db)
    if not exe.is_file():
        raise SystemExit(f"missing GoW.exe: {exe}")
    actual = sha256(exe).lower()
    if actual != EXPECTED_EXE_SHA256:
        raise SystemExit(f"unsupported GoW.exe SHA256: {actual}")
    if not db.is_file():
        raise SystemExit(f"missing research index: {db}")

    con = sqlite3.connect(db)
    result = {
        "schema": 1,
        "analysis": "raven_save_authority_native_trace",
        "exe_sha256": actual,
        "index": str(db),
        "exact_native_terms": collect_exact_native(con),
        "ranked_native_functions": collect_save_load_native(con),
        "lua_hits": scan_lua(game_root),
        "safety": {
            "game_launched": False,
            "active_save_opened": False,
            "process_opened": False,
            "game_files_written": False,
            "save_written": False,
            "progression_written": False,
        },
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_text(Path(args.output_text), result)

    exact_refs = sum(len(v["refs"]) for v in result["exact_native_terms"].values())
    print(
        "RAVEN_SAVE_AUTHORITY_NATIVE_TRACE_COMPLETE "
        f"exact_event_refs={exact_refs} "
        f"native_candidates={len(result['ranked_native_functions'])} "
        f"lua_files={len(result['lua_hits'])}"
    )


if __name__ == "__main__":
    main()
