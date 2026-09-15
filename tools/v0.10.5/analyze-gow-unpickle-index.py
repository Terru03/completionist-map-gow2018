"""Trace the real native restore path from the reusable GoW SQLite index.

Read-only and index-only. This revision closes the false 0x5B1030 -> 0x7E6DC0
lead and anchors on the function directly proven to load
package.loaded['core.pickle'].Unpickle:

    core.pickle Unpickle wrapper: 0x5AECC7-0x5AEE8C

That wrapper receives Lua values that already exist on the Lua stack, therefore
the native checkpoint-byte decoder must be upstream of it. This analysis walks
callers/reverse-callers, inspects sibling calls around every call to 0x5AECC7,
and ranks functions that bridge restore/checkpoint code to native 0x7E... codec
functions or GameObject reconstruction anchors.

No GoW.exe rescan, no game launch, no save I/O.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sqlite3

TRUE_UNPICKLE = 0x5AECC7
CLOSED_FALSE_ROOT = 0x5B1030
CLOSED_POI_FUNCTION = 0x7E6DC0

ANCHORS = {
    "core_pickle_unpickle": TRUE_UNPICKLE,
    "restore_dispatch": 0x5AD4A0,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "on_unpickle_internal": 0x5B2324,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "byte_serializer": 0x7E7F10,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
}

INTERESTING_TERMS = tuple(x.lower() for x in (
    "GameObject", "ResolveGameObject", "__codesideluaclass", "__PickleTable",
    "__SoftPickleTable", "__SoftPickleTablePrev", "__prevunpickle",
    "Pickle", "Unpickle", "Serialize", "Deserialize", "checkpoint", "restore",
    "saved", "save", "tableref", "GameObjectGUID", "GameObjectIDA", "GameObjectIDB",
))


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def function_for(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if not row:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def fn_begin(con: sqlite3.Connection, rva: int):
    f = function_for(con, rva)
    return f["begin"] if f else None


def direct_graph(con: sqlite3.Connection):
    fwd, rev = defaultdict(set), defaultdict(set)
    for src, target in con.execute(
        "SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"
    ):
        fwd[src].add(target)
        rev[target].add(src)
    return fwd, rev


def bfs(graph, start: int | None, depth: int):
    if start is None:
        return {}
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        d = dist[cur]
        if d >= depth:
            continue
        for nxt in graph.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
    return dist


def function_summary(con: sqlite3.Connection, rva: int):
    fn = function_for(con, rva)
    if not fn:
        return {
            "query_rva": rva,
            "function": None,
            "exact_edges_to": rows(con.execute(
                "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? ORDER BY site", (rva,)
            )),
            "exact_rip_refs": rows(con.execute(
                "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site", (rva,)
            )),
            "exact_imm_refs": rows(con.execute(
                "SELECT site,src_fn,mnemonic,value_rva,target_section FROM imm_refs WHERE value_rva=? ORDER BY site", (rva,)
            )),
        }
    b, e = fn["begin"], fn["end"]
    return {
        "query_rva": rva,
        "function": fn,
        "callers": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE kind='call' AND (target_fn=? OR dest BETWEEN ? AND ?) ORDER BY site",
            (b, b, e - 1),
        )),
        "callees": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? AND kind='call' ORDER BY site", (b,)
        )),
        "indirect_calls": rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (b,)
        )),
        "strings": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
            (b,),
        )),
    }


def interesting_strings(con: sqlite3.Connection, fn: int):
    refs = rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
        (fn,),
    ))
    return [r for r in refs if any(t in (r["target_string"] or "").lower() for t in INTERESTING_TERMS)]


def exact_anchor_hits(con: sqlite3.Connection, fn: int):
    out = []
    for name, rva in ANCHORS.items():
        if rva == TRUE_UNPICKLE:
            continue
        hit = con.execute(
            "SELECT site FROM edges WHERE src_fn=? AND kind='call' AND (dest=? OR target_fn=?) ORDER BY site LIMIT 1",
            (fn, rva, rva),
        ).fetchone()
        if hit:
            out.append({"name": name, "rva": rva, "site": hit[0]})
    return out


def codec_calls(con: sqlite3.Connection, fn: int):
    return rows(con.execute(
        "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? AND kind='call' AND dest BETWEEN 0x7E0000 AND 0x7EFFFF ORDER BY site",
        (fn,),
    ))


def indirect_calls(con: sqlite3.Connection, fn: int):
    return rows(con.execute(
        "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (fn,)
    ))


def special_fields(con: sqlite3.Connection, fn: int):
    return rows(con.execute(
        "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs "
        "WHERE src_fn=? AND disp IN (40,48,72,164,184,632,640,644) ORDER BY site",
        (fn,),
    ))


def sibling_window(con: sqlite3.Connection, caller_fn: int, callsite: int, before=0x500, after=0x180):
    lo, hi = max(caller_fn, callsite - before), callsite + after
    return {
        "callsite": callsite,
        "caller_fn": caller_fn,
        "calls": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (caller_fn, lo, hi),
        )),
        "indirect_calls": rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (caller_fn, lo, hi),
        )),
        "strings": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND site BETWEEN ? AND ? AND target_string IS NOT NULL ORDER BY site",
            (caller_fn, lo, hi),
        )),
    }


def rank_upstream(con: sqlite3.Connection, upstream: dict[int, int]):
    ranked = []
    for fn, depth in upstream.items():
        if fn == TRUE_UNPICKLE:
            continue
        strings = interesting_strings(con, fn)
        codecs = codec_calls(con, fn)
        anchors = exact_anchor_hits(con, fn)
        indirect = indirect_calls(con, fn)
        fields = special_fields(con, fn)
        calls_root = rows(con.execute(
            "SELECT site FROM edges WHERE src_fn=? AND kind='call' AND (dest=? OR target_fn=?) ORDER BY site",
            (fn, TRUE_UNPICKLE, TRUE_UNPICKLE),
        ))
        score = max(0, 160 - depth * 25)
        score += 140 * len(calls_root)
        score += 100 * len(codecs)
        score += 80 * len(anchors)
        score += 30 * len(strings)
        score += min(80, len(indirect) * 16)
        score += min(60, len(fields) * 6)
        ranked.append({
            "function": fn,
            "reverse_depth": depth,
            "score": score,
            "calls_unpickle": calls_root,
            "codec_7e_calls": codecs,
            "anchor_calls": anchors,
            "interesting_strings": strings[:30],
            "indirect_calls": indirect[:30],
            "special_fields": fields[:40],
        })
    ranked.sort(key=lambda r: (-r["score"], r["reverse_depth"], r["function"]))
    return ranked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    ap.add_argument("--depth", type=int, default=6)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")
    con = sqlite3.connect(db)
    meta = dict(con.execute("SELECT key,value FROM meta").fetchall())
    graph, reverse = direct_graph(con)

    root_fn = fn_begin(con, TRUE_UNPICKLE)
    if root_fn != TRUE_UNPICKLE:
        raise SystemExit(f"expected 0x{TRUE_UNPICKLE:X} function row, got {root_fn}")

    upstream = bfs(reverse, root_fn, args.depth)
    ranked = rank_upstream(con, upstream)

    direct_callers = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE kind='call' AND (dest=? OR target_fn=?) ORDER BY src_fn,site",
        (TRUE_UNPICKLE, TRUE_UNPICKLE),
    ))
    windows = [sibling_window(con, r["src_fn"], r["site"]) for r in direct_callers]

    bridge_rows = []
    for r in direct_callers:
        bridge_rows.append({
            "caller_fn": r["src_fn"],
            "unpickle_callsite": r["site"],
            "codec_7e_calls": codec_calls(con, r["src_fn"]),
            "interesting_strings": interesting_strings(con, r["src_fn"]),
            "anchor_calls": exact_anchor_hits(con, r["src_fn"]),
            "indirect_calls": indirect_calls(con, r["src_fn"]),
        })

    save_serializer_callers = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE kind='call' AND (dest=? OR target_fn=?) ORDER BY src_fn,site",
        (ANCHORS["byte_serializer"], ANCHORS["byte_serializer"]),
    ))

    summaries = {name: function_summary(con, rva) for name, rva in ANCHORS.items()}
    false_summary = function_summary(con, CLOSED_POI_FUNCTION)

    result = {
        "schema": 2,
        "analysis": "gow_unpickle_upstream_decoder_index",
        "database": str(db),
        "index_meta": meta,
        "proven_unpickle_wrapper": TRUE_UNPICKLE,
        "graph_depth": args.depth,
        "direct_unpickle_callers": direct_callers,
        "direct_caller_windows": windows,
        "direct_caller_bridges": bridge_rows,
        "ranked_upstream_candidates": ranked[:150],
        "save_byte_serializer_callers": save_serializer_callers,
        "anchor_summaries": summaries,
        "closed_false_lead": {
            "old_root": CLOSED_FALSE_ROOT,
            "old_candidate": CLOSED_POI_FUNCTION,
            "reason": "0x7E6DC0 references POIDelete/client/sequence/activetrigger/triggers and is gameplay POI logic, not the checkpoint decoder",
            "summary": false_summary,
        },
        "proven": [
            "0x5AECC7-0x5AEE8C references core.pickle and Unpickle and invokes package.loaded['core.pickle']['Unpickle']",
            "0x5AECC7 copies existing Lua stack values as Unpickle arguments, so native bytes->Lua decoding is upstream of this wrapper",
            "0x7E9190 save-side userdata serialization walks CodeSideLuaClass parent +0x48 and invokes persistence callback +0xB8",
        ],
        "closed": ["0x5B1030 -> 0x7E6DC0 as checkpoint byte decoder"],
        "remaining": [
            "identify upstream native bytes->Lua decoder and userdata reconstruction dispatch",
            "identify exact GameObject persistent payload and map it to static/WAD identity",
        ],
        "exe_rescanned": False,
        "game_launched": False,
        "save_opened": False,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - corrected upstream Unpickle/decoder analysis",
        "exe_rescanned=false",
        f"proven_unpickle_wrapper=0x{TRUE_UNPICKLE:X}",
        f"reverse_depth={args.depth}",
        f"direct_unpickle_callers={len(direct_callers)}",
        "",
        "PROVEN",
        "- 0x5AECC7 references core.pickle + Unpickle and invokes package.loaded['core.pickle']['Unpickle'].",
        "- Its Unpickle arguments are pre-existing Lua stack values; bytes->Lua decoding must be upstream.",
        "- Save-side userdata dispatch remains 0x7E9190 -> CodeSideLuaClass +0xB8.",
        "",
        "CLOSED FALSE LEAD",
        "- 0x5B1030 -> 0x7E6DC0 is not the checkpoint decoder path.",
        "- 0x7E6DC0 references POIDelete/client/sequence/activetrigger/triggers and is gameplay POI logic.",
        "",
        "DIRECT CALLERS OF REAL UNPICKLE WRAPPER",
    ]
    for b in bridge_rows:
        lines.append(
            f"- fn=0x{b['caller_fn']:X} callsite=0x{b['unpickle_callsite']:X} "
            f"codec7e={len(b['codec_7e_calls'])} anchors={len(b['anchor_calls'])} "
            f"strings={len(b['interesting_strings'])} indirect={len(b['indirect_calls'])}"
        )
        for c in b["codec_7e_calls"][:20]:
            lines.append(f"    CODEC_CALL 0x{c['site']:X} -> 0x{c['dest']:X}")
        for a in b["anchor_calls"][:20]:
            lines.append(f"    ANCHOR 0x{a['site']:X} -> {a['name']} 0x{a['rva']:X}")
        for s in b["interesting_strings"][:10]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")

    lines += ["", "CALL-SITE SIBLING WINDOWS"]
    for w in windows:
        lines.append(f"CALLER 0x{w['caller_fn']:X} UNPICKLE_SITE 0x{w['callsite']:X}")
        for c in w["calls"]:
            lines.append(f"    CALL 0x{c['site']:X} -> 0x{c['dest']:X} target_fn={c['target_fn']}")
        for c in w["indirect_calls"]:
            lines.append(f"    INDIRECT 0x{c['site']:X} reg={c['reg']} base={c['base']} disp={c['disp']}")
        for s in w["strings"]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")

    lines += ["", "TOP UPSTREAM DECODER/BRIDGE CANDIDATES"]
    for i, r in enumerate(ranked[:80], 1):
        lines.append(
            f"#{i} fn=0x{r['function']:X} score={r['score']} reverse_depth={r['reverse_depth']} "
            f"calls_unpickle={len(r['calls_unpickle'])} codec7e={len(r['codec_7e_calls'])} "
            f"anchors={len(r['anchor_calls'])} strings={len(r['interesting_strings'])} "
            f"indirect={len(r['indirect_calls'])} fields={len(r['special_fields'])}"
        )
        for c in r["codec_7e_calls"][:8]:
            lines.append(f"    CODEC_CALL 0x{c['site']:X} -> 0x{c['dest']:X}")
        for a in r["anchor_calls"][:8]:
            lines.append(f"    ANCHOR 0x{a['site']:X} -> {a['name']} 0x{a['rva']:X}")
        for s in r["interesting_strings"][:6]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")

    lines += ["", "SAVE BYTE SERIALIZER CALLERS (SYMMETRY REFERENCE)"]
    for r in save_serializer_callers:
        lines.append(f"- site=0x{r['site']:X} src_fn=0x{r['src_fn']:X} -> 0x{r['dest']:X}")

    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GOW_UNPICKLE_INDEX_ANALYSIS_PASSED")
    print(f"proven_unpickle_wrapper=0x{TRUE_UNPICKLE:X}")
    print(f"direct_unpickle_callers={len(direct_callers)}")
    print(f"upstream_functions={len(upstream)}")


if __name__ == "__main__":
    main()
