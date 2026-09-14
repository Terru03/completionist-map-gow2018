"""Build a reusable, version-locked static research index for God of War (2018).

This replaces repeated whole-EXE micro-scans with one local SQLite index.  It
indexes the supported GoW.exe using Capstone, the extracted Lua source tree when
present, and a lightweight game-file manifest.  It also emits compact hot-path
reports that are safe to archive in Git for remote inspection.

Read-only with respect to the game install and saves.  The SQLite database is
local working data and is intentionally not committed by the runner.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import sys
import time

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
KNOWN_ANCHORS = {
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "restore_dispatch": 0x5AD4A0,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "canpickle": 0x5AA350,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "unpickle_driver": 0x5B1030,
    "userdata_serializer": 0x7E9190,
}
PROVEN_CLASS_FIELDS = {0x48: "parent", 0xA4: "asserted_byte", 0xB8: "persistence_callback"}
HOT_TERMS = (
    "GameObject", "ResolveGameObject", "GameObjectGUID", "GameObjectIDA", "GameObjectIDB",
    "CanPickle", "OnPickleInternal", "OnUnpickleInternal", "__PickleTable",
    "__SoftPickleTable", "__prevunpickle", "Serialize", "Deserialize", "Pickle", "Unpickle",
)
LUA_TERM_RE = re.compile(
    r"(?i)(pickle|unpickle|gameobject|serialize|deserialize|checkpoint|restore|save|wad|guid|refnode)"
)


def load_base():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pickle_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load dependency {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sections(name TEXT, rva INTEGER, vsize INTEGER, raw INTEGER, rawsize INTEGER, executable INTEGER);
        CREATE TABLE IF NOT EXISTS functions(begin INTEGER PRIMARY KEY, end INTEGER, size INTEGER, section TEXT);
        CREATE TABLE IF NOT EXISTS strings(rva INTEGER PRIMARY KEY, text TEXT);
        CREATE TABLE IF NOT EXISTS edges(site INTEGER, src_fn INTEGER, kind TEXT, dest INTEGER, target_fn INTEGER);
        CREATE TABLE IF NOT EXISTS indirect_calls(site INTEGER, src_fn INTEGER, kind TEXT, reg TEXT, base TEXT, idx TEXT, scale INTEGER, disp INTEGER);
        CREATE TABLE IF NOT EXISTS rip_refs(site INTEGER, src_fn INTEGER, mnemonic TEXT, target INTEGER, target_section TEXT, target_string TEXT);
        CREATE TABLE IF NOT EXISTS mem_refs(site INTEGER, src_fn INTEGER, mnemonic TEXT, operand_index INTEGER, base TEXT, idx TEXT, scale INTEGER, disp INTEGER, access INTEGER);
        CREATE TABLE IF NOT EXISTS imm_refs(site INTEGER, src_fn INTEGER, mnemonic TEXT, value_rva INTEGER, target_section TEXT);
        CREATE TABLE IF NOT EXISTS lua_files(path TEXT PRIMARY KEY, size INTEGER, sha256 TEXT, lines INTEGER);
        CREATE TABLE IF NOT EXISTS lua_hits(path TEXT, line INTEGER, text TEXT);
        CREATE TABLE IF NOT EXISTS game_files(path TEXT PRIMARY KEY, size INTEGER, ext TEXT);
        """
    )
    return con


def reset_tables(con: sqlite3.Connection):
    for table in (
        "meta", "sections", "functions", "strings", "edges", "indirect_calls",
        "rip_refs", "mem_refs", "imm_refs", "lua_files", "lua_hits", "game_files",
    ):
        con.execute(f"DELETE FROM {table}")
    con.commit()


def section_name(pe, rva: int | None) -> str | None:
    if rva is None:
        return None
    sec = pe.section_for_rva(rva)
    return sec["name"] if sec else None


def va_to_rva(pe, value: int) -> int | None:
    if pe.image_base <= value < pe.image_base + pe.size_of_image:
        return value - pe.image_base
    return None


def exact_string_or_none(strings: dict[int, str], target: int) -> str | None:
    return strings.get(target)


def index_native(con: sqlite3.Connection, pe, strings: dict[int, str], capstone_mod):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_WRITE
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    md.skipdata = True

    con.executemany(
        "INSERT INTO sections(name,rva,vsize,raw,rawsize,executable) VALUES(?,?,?,?,?,?)",
        [(s["name"], s["rva"], s["vsize"], s["raw"], s["rawsize"], 1 if s["exec"] else 0) for s in pe.sections],
    )
    con.executemany("INSERT INTO strings(rva,text) VALUES(?,?)", sorted(strings.items()))

    frows = []
    for fn in pe.runtime_functions:
        frows.append((fn["begin"], fn["end"], fn["end"] - fn["begin"], section_name(pe, fn["begin"])))
    con.executemany("INSERT INTO functions(begin,end,size,section) VALUES(?,?,?,?)", frows)
    con.commit()

    edge_rows = []
    indirect_rows = []
    rip_rows = []
    mem_rows = []
    imm_rows = []
    instruction_count = 0
    decoded_functions = 0

    for n, fn in enumerate(pe.runtime_functions, 1):
        blob = pe.bytes_for(fn)
        if not blob:
            continue
        decoded_functions += 1
        src_fn = fn["begin"]
        for insn in md.disasm(blob, pe.image_base + src_fn):
            instruction_count += 1
            site = insn.address - pe.image_base
            mnem = insn.mnemonic.lower()
            ops = list(insn.operands)

            if mnem in ("call", "jmp") and ops:
                op = ops[0]
                if op.type == X86_OP_IMM:
                    dest_rva = va_to_rva(pe, int(op.imm))
                    if dest_rva is not None:
                        tf = pe.function_for(dest_rva)
                        edge_rows.append((site, src_fn, mnem, dest_rva, tf["begin"] if tf else None))
                else:
                    reg = base = idx = None
                    scale = disp = None
                    if op.type == X86_OP_REG:
                        reg = insn.reg_name(op.reg)
                    elif op.type == X86_OP_MEM:
                        base = insn.reg_name(op.mem.base) if op.mem.base else None
                        idx = insn.reg_name(op.mem.index) if op.mem.index else None
                        scale = op.mem.scale
                        disp = int(op.mem.disp)
                    indirect_rows.append((site, src_fn, mnem, reg, base, idx, scale, disp))

            for oi, op in enumerate(ops):
                if op.type == X86_OP_MEM:
                    base = insn.reg_name(op.mem.base) if op.mem.base else None
                    idx = insn.reg_name(op.mem.index) if op.mem.index else None
                    disp = int(op.mem.disp)
                    scale = int(op.mem.scale)
                    access = int(getattr(op, "access", 0) or 0)
                    if op.mem.base == X86_REG_RIP:
                        target_va = insn.address + insn.size + disp
                        target = va_to_rva(pe, target_va)
                        if target is not None:
                            rip_rows.append((site, src_fn, mnem, target, section_name(pe, target), exact_string_or_none(strings, target)))
                    elif -0x4000 <= disp <= 0x4000:
                        mem_rows.append((site, src_fn, mnem, oi, base, idx, scale, disp, access))
                elif op.type == X86_OP_IMM:
                    rva = va_to_rva(pe, int(op.imm))
                    if rva is not None:
                        imm_rows.append((site, src_fn, mnem, rva, section_name(pe, rva)))

        if len(edge_rows) + len(indirect_rows) + len(rip_rows) + len(mem_rows) + len(imm_rows) >= 100000:
            con.executemany("INSERT INTO edges VALUES(?,?,?,?,?)", edge_rows); edge_rows.clear()
            con.executemany("INSERT INTO indirect_calls VALUES(?,?,?,?,?,?,?,?)", indirect_rows); indirect_rows.clear()
            con.executemany("INSERT INTO rip_refs VALUES(?,?,?,?,?,?)", rip_rows); rip_rows.clear()
            con.executemany("INSERT INTO mem_refs VALUES(?,?,?,?,?,?,?,?,?)", mem_rows); mem_rows.clear()
            con.executemany("INSERT INTO imm_refs VALUES(?,?,?,?,?)", imm_rows); imm_rows.clear()
            con.commit()
        if n % 10000 == 0:
            print(f"native_progress functions={n}/{len(pe.runtime_functions)} instructions={instruction_count}", flush=True)

    if edge_rows: con.executemany("INSERT INTO edges VALUES(?,?,?,?,?)", edge_rows)
    if indirect_rows: con.executemany("INSERT INTO indirect_calls VALUES(?,?,?,?,?,?,?,?)", indirect_rows)
    if rip_rows: con.executemany("INSERT INTO rip_refs VALUES(?,?,?,?,?,?)", rip_rows)
    if mem_rows: con.executemany("INSERT INTO mem_refs VALUES(?,?,?,?,?,?,?,?,?)", mem_rows)
    if imm_rows: con.executemany("INSERT INTO imm_refs VALUES(?,?,?,?,?)", imm_rows)
    con.commit()

    con.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_edges_dest ON edges(dest);
        CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_fn);
        CREATE INDEX IF NOT EXISTS idx_indirect_src ON indirect_calls(src_fn);
        CREATE INDEX IF NOT EXISTS idx_rip_target ON rip_refs(target);
        CREATE INDEX IF NOT EXISTS idx_rip_src ON rip_refs(src_fn);
        CREATE INDEX IF NOT EXISTS idx_rip_string ON rip_refs(target_string);
        CREATE INDEX IF NOT EXISTS idx_mem_disp ON mem_refs(disp);
        CREATE INDEX IF NOT EXISTS idx_mem_src ON mem_refs(src_fn);
        CREATE INDEX IF NOT EXISTS idx_imm_value ON imm_refs(value_rva);
        CREATE INDEX IF NOT EXISTS idx_lua_hits_path ON lua_hits(path);
        """
    )
    con.commit()
    return {"decoded_functions": decoded_functions, "instruction_count": instruction_count}


def index_lua(con: sqlite3.Connection, game_root: Path):
    root = game_root / "mods" / "lua_source"
    if not root.is_dir():
        return {"present": False, "files": 0, "hits": 0}
    files = hits = 0
    batch_files = []
    batch_hits = []
    for path in root.rglob("*.lua"):
        try:
            data = path.read_bytes()
            text = data.decode("utf-8", "replace")
        except OSError:
            continue
        rel = str(path.relative_to(game_root)).replace("\\", "/")
        lines = text.splitlines()
        batch_files.append((rel, len(data), hashlib.sha256(data).hexdigest(), len(lines)))
        files += 1
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and LUA_TERM_RE.search(stripped):
                batch_hits.append((rel, lineno, stripped[:2000]))
                hits += 1
        if len(batch_files) >= 500:
            con.executemany("INSERT INTO lua_files VALUES(?,?,?,?)", batch_files); batch_files.clear()
            con.executemany("INSERT INTO lua_hits VALUES(?,?,?)", batch_hits); batch_hits.clear()
            con.commit()
    if batch_files: con.executemany("INSERT INTO lua_files VALUES(?,?,?,?)", batch_files)
    if batch_hits: con.executemany("INSERT INTO lua_hits VALUES(?,?,?)", batch_hits)
    con.commit()
    return {"present": True, "files": files, "hits": hits}


def index_game_files(con: sqlite3.Connection, game_root: Path):
    rows = []
    count = 0
    total = 0
    for base, dirs, files in os.walk(game_root):
        dirs[:] = [d for d in dirs if d not in {".git", ".research-index"}]
        for name in files:
            path = Path(base) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            rel = str(path.relative_to(game_root)).replace("\\", "/")
            ext = path.suffix.lower()
            rows.append((rel, size, ext))
            count += 1
            total += size
            if len(rows) >= 5000:
                con.executemany("INSERT INTO game_files VALUES(?,?,?)", rows); rows.clear(); con.commit()
    if rows: con.executemany("INSERT INTO game_files VALUES(?,?,?)", rows)
    con.commit()
    return {"files": count, "bytes": total}


def table_count(con, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def function_window(pe, capstone_mod, begin: int, hot_sites: set[int], radius: int = 14):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True; md.skipdata = True
    fn = pe.function_for(begin)
    if not fn:
        return []
    insns = list(md.disasm(pe.bytes_for(fn), pe.image_base + fn["begin"]))
    by_idx = {ins.address - pe.image_base: i for i, ins in enumerate(insns)}
    out = []
    used = set()
    for site in sorted(hot_sites):
        idx = by_idx.get(site)
        if idx is None:
            continue
        lo, hi = max(0, idx-radius), min(len(insns), idx+radius+1)
        for j in range(lo, hi):
            ins = insns[j]
            rva = ins.address - pe.image_base
            if rva in used:
                continue
            used.add(rva)
            out.append({"rva": rva, "mnemonic": ins.mnemonic, "op_str": ins.op_str})
    out.sort(key=lambda x: x["rva"])
    return out


def hot_report(con: sqlite3.Connection, pe, capstone_mod):
    from capstone import CS_AC_WRITE
    exact_go = [r[0] for r in con.execute("SELECT rva FROM strings WHERE text='GameObject'")]
    go_rva = exact_go[0] if exact_go else None

    candidates = {}
    for disp, field in PROVEN_CLASS_FIELDS.items():
        for site, src_fn, mnem, access in con.execute(
            "SELECT site,src_fn,mnemonic,access FROM mem_refs WHERE disp=?", (disp,)
        ):
            c = candidates.setdefault(src_fn, {"begin": src_fn, "fields": set(), "sites": [], "writes_b8": [], "gameobject_refs": 0, "known_calls": []})
            c["fields"].add(disp)
            c["sites"].append(site)
            if disp == 0xB8 and (access & CS_AC_WRITE):
                c["writes_b8"].append(site)

    if go_rva is not None:
        for src_fn, cnt in con.execute("SELECT src_fn,COUNT(*) FROM rip_refs WHERE target=? GROUP BY src_fn", (go_rva,)):
            c = candidates.setdefault(src_fn, {"begin": src_fn, "fields": set(), "sites": [], "writes_b8": [], "gameobject_refs": 0, "known_calls": []})
            c["gameobject_refs"] = cnt

    anchor_by_rva = {v: k for k, v in KNOWN_ANCHORS.items()}
    for src_fn, dest in con.execute("SELECT src_fn,dest FROM edges"):
        if dest in anchor_by_rva and src_fn in candidates:
            candidates[src_fn]["known_calls"].append(anchor_by_rva[dest])

    ranked = []
    for c in candidates.values():
        if not c["writes_b8"]:
            continue
        score = 100 * len(c["writes_b8"])
        if 0x48 in c["fields"]: score += 80
        if 0xA4 in c["fields"]: score += 80
        if {0x48, 0xA4, 0xB8}.issubset(c["fields"]): score += 150
        score += 120 * c["gameobject_refs"]
        score += 100 * len(c["known_calls"])
        c["score"] = score
        c["fields"] = sorted(c["fields"])
        fn = pe.function_for(c["begin"])
        c["end"] = fn["end"] if fn else None
        c["window"] = function_window(pe, capstone_mod, c["begin"], set(c["writes_b8"] + c["sites"][:20]))
        ranked.append(c)
    ranked.sort(key=lambda x: (-x["score"], x["begin"]))

    anchors = {}
    for name, rva in KNOWN_ANCHORS.items():
        fn = pe.function_for(rva)
        anchors[name] = {
            "rva": rva,
            "function_begin": fn["begin"] if fn else None,
            "function_end": fn["end"] if fn else None,
            "callers": [dict(site=row[0], src_fn=row[1]) for row in con.execute("SELECT site,src_fn FROM edges WHERE dest=? ORDER BY site", (rva,))],
            "callees": [dict(site=row[0], dest=row[1], target_fn=row[2]) for row in con.execute("SELECT site,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (fn["begin"] if fn else rva,))],
        }

    term_refs = {}
    for term in HOT_TERMS:
        rows = list(con.execute("SELECT rva FROM strings WHERE text=?", (term,)))
        refs = []
        for (srva,) in rows:
            refs.extend({"string_rva": srva, "site": site, "src_fn": src_fn} for site, src_fn in con.execute("SELECT site,src_fn FROM rip_refs WHERE target=?", (srva,)))
        if rows or refs:
            term_refs[term] = refs

    return {"candidate_count": len(ranked), "ranked_candidates": ranked[:120], "anchors": anchors, "term_refs": term_refs}


def write_hot_text(path: Path, report: dict, counts: dict, digest: str, capstone_version: str, db_path: Path):
    lines = [
        "Completionist Map - reusable God of War static research index",
        f"gow_exe_sha256={digest}",
        f"capstone_version={capstone_version}",
        f"local_index={db_path}",
        f"functions={counts['functions']} strings={counts['strings']} edges={counts['edges']} indirect_calls={counts['indirect_calls']}",
        f"rip_refs={counts['rip_refs']} mem_refs={counts['mem_refs']} imm_refs={counts['imm_refs']}",
        f"lua_files={counts['lua_files']} lua_hits={counts['lua_hits']} game_files={counts['game_files']}",
        f"hot_candidate_count={report['candidate_count']}",
        "",
        "PROVEN CLASS LAYOUT: +0x48 parent, +0xA4 asserted byte, +0xB8 persistence callback",
        "",
        "TOP CAPSTONE-DECODED +0xB8 WRITE CANDIDATES",
    ]
    for i, c in enumerate(report["ranked_candidates"][:40], 1):
        lines.append(
            f"#{i} fn=0x{c['begin']:X}-0x{(c['end'] or 0):X} score={c['score']} "
            f"fields={[hex(x) for x in c['fields']]} b8_writes={len(c['writes_b8'])} "
            f"gameobject_refs={c['gameobject_refs']} known_calls={c['known_calls']}"
        )
        for w in c["writes_b8"][:12]:
            lines.append(f"  B8_WRITE 0x{w:X}")
        for ins in c["window"][:80]:
            marker = " *" if ins["rva"] in c["writes_b8"] else ""
            lines.append(f"    0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{marker}")
    lines += ["", "KNOWN ANCHORS"]
    for name, a in report["anchors"].items():
        lines.append(f"{name}=0x{a['rva']:X} fn=0x{(a['function_begin'] or 0):X} callers={len(a['callers'])} callees={len(a['callees'])}")
    lines += [
        "",
        "NOTE: this is a reusable static index. Candidate ranking is evidence, not proof of GameObject class ownership.",
        "NOTE: future static questions should query the local index instead of rescanning GoW.exe.",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--hot-json", required=True)
    ap.add_argument("--hot-text", required=True)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    try:
        import capstone
    except ImportError as exc:
        raise RuntimeError("Capstone is required. Run this through build-gow-research-index-with-log.ps1") from exc

    game_root = Path(args.game_root)
    exe = game_root / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"missing {exe}")
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")

    db_path = Path(args.db)
    manifest_path = Path(args.manifest)
    hot_json_path = Path(args.hot_json)
    hot_text_path = Path(args.hot_text)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    base = load_base()
    pe = base.PE(exe.read_bytes())
    strings = base.ascii_map(pe)

    con = connect_db(db_path)
    old = dict(con.execute("SELECT key,value FROM meta"))
    can_reuse = old.get("gow_exe_sha256") == digest and old.get("index_complete") == "1" and not args.rebuild
    if can_reuse:
        print("REUSING_EXISTING_NATIVE_INDEX", flush=True)
    else:
        reset_tables(con)
        native = index_native(con, pe, strings, capstone)
        lua = index_lua(con, game_root)
        files = index_game_files(con, game_root)
        meta = {
            "gow_exe_sha256": digest,
            "index_complete": "1",
            "capstone_version": getattr(capstone, "__version__", "unknown"),
            "native_decoded_functions": str(native["decoded_functions"]),
            "native_instruction_count": str(native["instruction_count"]),
            "lua_present": str(lua["present"]),
            "lua_files": str(lua["files"]),
            "lua_hits": str(lua["hits"]),
            "game_files": str(files["files"]),
            "game_bytes": str(files["bytes"]),
        }
        con.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", meta.items())
        con.commit()

    counts = {t: table_count(con, t) for t in (
        "functions", "strings", "edges", "indirect_calls", "rip_refs", "mem_refs",
        "imm_refs", "lua_files", "lua_hits", "game_files",
    )}
    report = hot_report(con, pe, capstone)
    cap_ver = getattr(capstone, "__version__", "unknown")
    manifest = {
        "schema": 1,
        "analysis": "gow_reusable_static_research_index",
        "gow_exe_sha256": digest,
        "capstone_version": cap_ver,
        "database_path": str(db_path),
        "database_bytes": db_path.stat().st_size if db_path.exists() else None,
        "counts": counts,
        "known_anchors": KNOWN_ANCHORS,
        "proven_class_fields": {hex(k): v for k, v in PROVEN_CLASS_FIELDS.items()},
        "hot_candidate_count": report["candidate_count"],
        "game_launched": False,
        "save_opened": False,
        "progression_written": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    hot_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_hot_text(hot_text_path, report, counts, digest, cap_ver, db_path)
    con.close()

    print("GOW_RESEARCH_INDEX_BUILD_PASSED")
    print(f"db={db_path} bytes={manifest['database_bytes']}")
    print("counts=" + json.dumps(counts, sort_keys=True))
    print(f"hot_candidates={report['candidate_count']}")


if __name__ == "__main__":
    main()
