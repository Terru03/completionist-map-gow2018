"""Analyze the already-built reusable GoW static index for userdata persistence.

No executable rescan is performed. This is pure SQLite analysis over the local
research index produced by build-gow-research-index.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

KNOWN = {
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
FOCUS_INITIALIZER = 0x406820
FOCUS_CALLBACK = 0x409FC0


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def function_for(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if not row:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def function_report(con: sqlite3.Connection, rva: int):
    fn = function_for(con, rva)
    if not fn:
        return {"query_rva": rva, "function": None}
    b = fn["begin"]
    return {
        "query_rva": rva,
        "function": fn,
        "callers": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest BETWEEN ? AND ? ORDER BY site",
            (fn["begin"], fn["end"] - 1),
        )),
        "callees": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (b,)
        )),
        "indirect_calls": rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (b,)
        )),
        "rip_refs": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site", (b,)
        )),
        "class_field_refs": rows(con.execute(
            "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? AND disp IN (72,164,184) ORDER BY site",
            (b,),
        )),
        "imm_refs": rows(con.execute(
            "SELECT site,mnemonic,value_rva,target_section FROM imm_refs WHERE src_fn=? ORDER BY site", (b,)
        )),
    }


def known_calls_for(con: sqlite3.Connection, fn_begin: int):
    out = []
    for name, rva in KNOWN.items():
        hit = con.execute(
            "SELECT 1 FROM edges WHERE src_fn=? AND (dest=? OR target_fn=?) LIMIT 1", (fn_begin, rva, rva)
        ).fetchone()
        if hit:
            out.append(name)
    return out


def executable_rip_sources_near(con: sqlite3.Connection, fn_begin: int, site: int, window: int = 0x100):
    return rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs "
        "WHERE src_fn=? AND site BETWEEN ? AND ? AND target_section='.text' ORDER BY site DESC",
        (fn_begin, max(fn_begin, site-window), site),
    ))


def rank_b8_functions(con: sqlite3.Connection):
    candidates = []
    fns = rows(con.execute(
        "SELECT DISTINCT src_fn FROM mem_refs WHERE disp=184 AND access LIKE '%W%' ORDER BY src_fn"
    ))
    for row in fns:
        fn = row["src_fn"]
        writes = rows(con.execute(
            "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs "
            "WHERE src_fn=? AND disp=184 AND access LIKE '%W%' ORDER BY site", (fn,)
        ))
        fields = {r[0] for r in con.execute(
            "SELECT DISTINCT disp FROM mem_refs WHERE src_fn=? AND disp IN (72,164,184)", (fn,)
        ).fetchall()}
        known = known_calls_for(con, fn)
        gameobject_refs = rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs "
            "WHERE src_fn=? AND target_string='GameObject' ORDER BY site", (fn,)
        ))
        exec_sources = []
        for w in writes:
            near = executable_rip_sources_near(con, fn, w["site"])
            for n in near:
                exec_sources.append({"write_site": w["site"], **n})
        # Collapse duplicate source tuples.
        seen = set()
        dedup = []
        for x in exec_sources:
            key = (x["write_site"], x["site"], x["target"])
            if key not in seen:
                seen.add(key); dedup.append(x)
        exec_sources = dedup
        score = 100 * len(known) + 80 * len(exec_sources) + 30 * len(gameobject_refs) + 10 * len(writes)
        if 0x48 in fields: score += 40
        if 0xA4 in fields: score += 40
        if {0x48,0xA4,0xB8}.issubset(fields): score += 80
        candidates.append({
            "function": fn,
            "score": score,
            "fields": sorted(fields),
            "b8_writes": writes,
            "near_exec_sources": exec_sources[:20],
            "known_calls": known,
            "gameobject_refs": gameobject_refs,
        })
    candidates.sort(key=lambda x: (-x["score"], x["function"]))
    return candidates


def graph_neighborhood(con: sqlite3.Connection, start: int, depth: int = 2):
    seen = {start}
    frontier = {start}
    levels = []
    for d in range(1, depth+1):
        nxt = set()
        edges = []
        for fn in sorted(frontier):
            for e in rows(con.execute(
                "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (fn,)
            )):
                tf = e["target_fn"]
                if tf is not None:
                    edges.append(e)
                    if tf not in seen:
                        nxt.add(tf)
        levels.append({"depth": d, "edges": edges})
        seen.update(nxt)
        frontier = nxt
        if not frontier:
            break
    return levels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing index: {db}")
    con = sqlite3.connect(db)
    con.row_factory = None

    ranked = rank_b8_functions(con)
    initializer = function_report(con, FOCUS_INITIALIZER)
    callback = function_report(con, FOCUS_CALLBACK)
    callback_callers = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? OR target_fn=? ORDER BY site",
        (FOCUS_CALLBACK, FOCUS_CALLBACK),
    ))
    callback_graph = graph_neighborhood(con, FOCUS_CALLBACK, 2)
    init_graph = graph_neighborhood(con, FOCUS_INITIALIZER, 2)

    result = {
        "schema": 1,
        "analysis": "persistence_index_followup",
        "database": str(db),
        "focus_initializer": initializer,
        "focus_callback": callback,
        "focus_callback_callers": callback_callers,
        "focus_initializer_graph": init_graph,
        "focus_callback_graph": callback_graph,
        "ranked_b8_functions": ranked[:100],
        "conclusion": "INDEX_QUERY_COMPLETE",
        "exe_rescanned": False,
        "game_launched": False,
        "save_opened": False,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - persistence analysis from reusable SQLite index",
        "exe_rescanned=false",
        f"focus_initializer=0x{FOCUS_INITIALIZER:X}",
        f"focus_callback=0x{FOCUS_CALLBACK:X}",
        "",
        "FOCUS INITIALIZER",
        json.dumps(initializer, indent=2),
        "",
        "FOCUS CALLBACK",
        json.dumps(callback, indent=2),
        "",
        "FOCUS CALLBACK CALLERS",
        json.dumps(callback_callers, indent=2),
        "",
        "TOP RANKED B8 FUNCTIONS",
    ]
    for i, c in enumerate(ranked[:40], 1):
        lines.append(
            f"#{i} fn=0x{c['function']:X} score={c['score']} fields={[hex(x) for x in c['fields']]} "
            f"b8_writes={len(c['b8_writes'])} exec_sources={len(c['near_exec_sources'])} "
            f"known_calls={c['known_calls']} gameobject_refs={len(c['gameobject_refs'])}"
        )
        for x in c["near_exec_sources"][:5]:
            lines.append(f"  EXEC_SOURCE write=0x{x['write_site']:X} load=0x{x['site']:X} -> 0x{x['target']:X}")
        for g in c["gameobject_refs"][:3]:
            lines.append(f"  GAMEOBJECT_REF 0x{g['site']:X}")
    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GOW_PERSISTENCE_INDEX_ANALYSIS_PASSED")
    print(f"ranked_b8_functions={len(ranked)}")
    print(f"focus_callback=0x{FOCUS_CALLBACK:X}")


if __name__ == "__main__":
    main()
