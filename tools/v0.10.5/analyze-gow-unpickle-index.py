"""Correlate the native unpickle/deserializer side using the reusable GoW index.

This tool does NOT rescan GoW.exe.  It queries the SQLite index produced by
build-gow-research-index.py and focuses on the inverse of the proven userdata
serializer:

    checkpoint bytes -> unpickle_driver 0x5B1030
                     -> native Lua C function 0x7E6DC0 (proven insertion)
                     -> reconstructed Lua userdata / GameObject

0x7E6DC0 is deliberately labelled a *candidate deserializer entry* until its
internal graph proves that role.  Likewise 0x7EABD0 is treated as a later
unpickle helper/finalizer, not assumed to be the byte decoder.

Read-only. No game launch, no save I/O, no executable rescan.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sqlite3

CS_AC_READ = 1
CS_AC_WRITE = 2

ROOTS = {
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
    "restore_dispatch": 0x5AD4A0,
    "unpickle_driver": 0x5B1030,
    "on_unpickle_internal": 0x5B2324,
    "candidate_native_deserializer": 0x7E6DC0,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
    "later_unpickle_helper": 0x7EABD0,
    "byte_serializer": 0x7E7F10,
}

INTERESTING_STRINGS = (
    "GameObject",
    "ResolveGameObject",
    "__codesideluaclass",
    "__PickleTable",
    "__SoftPickleTable",
    "__prevunpickle",
    "Pickle",
    "Unpickle",
    "Serialize",
    "Deserialize",
    "tableref",
    "GameObjectGUID",
    "GameObjectIDA",
    "GameObjectIDB",
)


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


def function_summary(con: sqlite3.Connection, rva: int):
    fn = function_for(con, rva)
    if not fn:
        return {
            "query_rva": rva,
            "function": None,
            "exact_rip_refs": rows(con.execute(
                "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",
                (rva,),
            )),
            "exact_imm_refs": rows(con.execute(
                "SELECT site,src_fn,mnemonic,value_rva,target_section FROM imm_refs WHERE value_rva=? ORDER BY site",
                (rva,),
            )),
            "note": "No .pdata/runtime-function row covers this RVA; standalone leaf body is not present in the current index.",
        }
    b = fn["begin"]
    return {
        "query_rva": rva,
        "function": fn,
        "callers": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? OR dest BETWEEN ? AND ? ORDER BY site",
            (b, fn["begin"], fn["end"] - 1),
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
        "classish_mem_refs": rows(con.execute(
            "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs "
            "WHERE src_fn=? AND disp BETWEEN 0 AND 512 ORDER BY site", (b,)
        )),
    }


def all_direct_graph(con: sqlite3.Connection):
    out = defaultdict(set)
    rev = defaultdict(set)
    for src, target in con.execute(
        "SELECT src_fn,target_fn FROM edges WHERE target_fn IS NOT NULL AND kind='call'"
    ):
        out[src].add(target)
        rev[target].add(src)
    return out, rev


def bfs(graph, start: int, max_depth: int):
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        d = dist[cur]
        if d >= max_depth:
            continue
        for nxt in graph.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
    return dist


def fn_begin_for(con: sqlite3.Connection, rva: int):
    fn = function_for(con, rva)
    return fn["begin"] if fn else None


def interesting_string_refs(con: sqlite3.Connection, fns: set[int]):
    if not fns:
        return []
    placeholders = ",".join("?" for _ in fns)
    params = list(sorted(fns))
    result = rows(con.execute(
        f"SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs "
        f"WHERE src_fn IN ({placeholders}) AND target_string IS NOT NULL ORDER BY src_fn,site",
        params,
    ))
    terms = tuple(x.lower() for x in INTERESTING_STRINGS)
    return [r for r in result if any(t in (r["target_string"] or "").lower() for t in terms)]


def class_offset_histogram(con: sqlite3.Connection, fns: set[int]):
    if not fns:
        return []
    placeholders = ",".join("?" for _ in fns)
    data = rows(con.execute(
        f"SELECT disp,access,COUNT(*) AS n FROM mem_refs WHERE src_fn IN ({placeholders}) "
        f"AND disp BETWEEN 0 AND 512 GROUP BY disp,access ORDER BY n DESC,disp",
        list(sorted(fns)),
    ))
    return data[:200]


def rank_inverse_candidates(con, forward: dict[int, int], target_reverse: dict[str, dict[int, int]]):
    candidates = []
    for fn, fd in forward.items():
        if fn == fn_begin_for(con, ROOTS["unpickle_driver"]):
            continue
        reverse_hits = {}
        for name, rdist in target_reverse.items():
            if fn in rdist:
                reverse_hits[name] = rdist[fn]
        refs = rows(con.execute(
            "SELECT site,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
            (fn,),
        ))
        text_hits = [r for r in refs if any(
            term.lower() in (r["target_string"] or "").lower()
            for term in INTERESTING_STRINGS
        )]
        indirect = rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site",
            (fn,),
        ))
        mem = rows(con.execute(
            "SELECT site,mnemonic,base,idx,scale,disp,access FROM mem_refs "
            "WHERE src_fn=? AND disp BETWEEN 0 AND 512 ORDER BY site", (fn,),
        ))
        special_fields = [r for r in mem if r["disp"] in (0x30,0x48,0xA4,0xB8)]
        score = 0
        score += max(0, 80 - 12 * fd)
        score += 90 * len(reverse_hits)
        score += 25 * len(text_hits)
        score += min(50, 10 * len(indirect))
        score += min(40, 8 * len(special_fields))
        if reverse_hits or text_hits or special_fields:
            candidates.append({
                "function": fn,
                "forward_depth": fd,
                "reverse_hits": reverse_hits,
                "score": score,
                "interesting_strings": text_hits[:20],
                "indirect_calls": indirect[:20],
                "special_field_refs": special_fields[:30],
            })
    candidates.sort(key=lambda x: (-x["score"], x["forward_depth"], x["function"]))
    return candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    ap.add_argument("--depth", type=int, default=4)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")
    con = sqlite3.connect(db)
    con.row_factory = None

    meta = dict(con.execute("SELECT key,value FROM meta").fetchall())
    graph, reverse = all_direct_graph(con)

    summaries = {name: function_summary(con, rva) for name, rva in ROOTS.items()}
    fn_roots = {name: fn_begin_for(con, rva) for name, rva in ROOTS.items()}

    unpickle_fn = fn_roots["unpickle_driver"]
    candidate_fn = fn_roots["candidate_native_deserializer"]

    # The candidate function is the preferred graph root if it has .pdata. If
    # it is a leaf without a runtime-function row, fall back to unpickle_driver
    # and retain exact RIP/IMM references to 0x7E6DC0 as evidence.
    graph_root = candidate_fn or unpickle_fn
    forward = bfs(graph, graph_root, args.depth) if graph_root is not None else {}

    target_names = ("gameobject_token_resolver", "lua_gameobject_unbox", "gameobject_token_packer", "on_unpickle_internal")
    target_reverse = {}
    for name in target_names:
        fb = fn_roots[name]
        target_reverse[name] = bfs(reverse, fb, args.depth) if fb is not None else {}

    intersection = {}
    for name, rdist in target_reverse.items():
        rows_hit = []
        for fn, fd in forward.items():
            if fn in rdist:
                rows_hit.append({"function": fn, "from_candidate": fd, "to_target": rdist[fn]})
        rows_hit.sort(key=lambda x: (x["from_candidate"] + x["to_target"], x["function"]))
        intersection[name] = rows_hit

    reachable = set(forward)
    string_refs = interesting_string_refs(con, reachable)
    offset_hist = class_offset_histogram(con, reachable)
    ranked = rank_inverse_candidates(con, forward, target_reverse)

    codeclass_refs = rows(con.execute(
        "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs "
        "WHERE lower(target_string)=lower('__codesideluaclass') ORDER BY src_fn,site"
    ))
    gameobject_refs = rows(con.execute(
        "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs "
        "WHERE target_string='GameObject' ORDER BY src_fn,site"
    ))

    result = {
        "schema": 1,
        "analysis": "gow_unpickle_inverse_index",
        "database": str(db),
        "index_meta": meta,
        "roots": ROOTS,
        "root_functions": fn_roots,
        "summaries": summaries,
        "graph_root": graph_root,
        "graph_depth": args.depth,
        "forward_reachable": [{"function": fn, "depth": d} for fn, d in sorted(forward.items(), key=lambda x:(x[1],x[0]))],
        "forward_reverse_intersections": intersection,
        "reachable_interesting_string_refs": string_refs,
        "reachable_small_offset_histogram": offset_hist,
        "ranked_inverse_candidates": ranked[:100],
        "all_codesideluaclass_refs": codeclass_refs,
        "all_gameobject_refs": gameobject_refs,
        "proven": [
            "unpickle_driver 0x5B1030 inserts native address 0x7E6DC0 as a Lua C function before later unpickle table handling (proved from archived exact disassembly)",
            "userdata serializer 0x7E9190 walks CodeSideLuaClass parent +0x48 and invokes first non-null persistence callback +0xB8",
        ],
        "not_yet_proven": [
            "0x7E6DC0 is the byte-to-Lua deserializer entry (highest-priority hypothesis; insertion as Lua C function is proven, semantics are not)",
            "the exact GameObject CodeSideLuaClass +0xB8 encoder callback",
            "the stable payload field that maps to static/WAD identity",
        ],
        "exe_rescanned": False,
        "game_launched": False,
        "save_opened": False,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - inverse/unpickle analysis from reusable SQLite index",
        "exe_rescanned=false",
        f"graph_depth={args.depth}",
        f"graph_root={'NONE' if graph_root is None else f'0x{graph_root:X}'}",
        f"candidate_0x7E6DC0_function={'NONE' if candidate_fn is None else f'0x{candidate_fn:X}'}",
        "",
        "PROVEN",
        "- 0x5B1030 inserts 0x7E6DC0 as a native Lua C function before later unpickle-table handling.",
        "- 0x7E9190 userdata serialization walks CodeSideLuaClass +0x48 and invokes persistence callback +0xB8.",
        "",
        "NOT YET PROVEN",
        "- 0x7E6DC0 semantics as the actual byte-to-Lua decoder (highest-priority hypothesis).",
        "- exact GameObject +0xB8 encoder callback and stable static/WAD identity payload.",
        "",
        "ROOT COVERAGE",
    ]
    for name in ROOTS:
        fb = fn_roots[name]
        lines.append(f"- {name}: rva=0x{ROOTS[name]:X} function={'NONE' if fb is None else f'0x{fb:X}'}")

    lines += ["", "FORWARD/REVERSE INTERSECTIONS"]
    for name, hits in intersection.items():
        lines.append(f"- {name}: {len(hits)} intersection(s)")
        for hit in hits[:20]:
            lines.append(
                f"    fn=0x{hit['function']:X} from_candidate={hit['from_candidate']} to_target={hit['to_target']}"
            )

    lines += ["", "TOP INVERSE CANDIDATES"]
    for i, row in enumerate(ranked[:50], 1):
        lines.append(
            f"#{i} fn=0x{row['function']:X} score={row['score']} forward_depth={row['forward_depth']} "
            f"reverse_hits={row['reverse_hits']} strings={len(row['interesting_strings'])} "
            f"indirect={len(row['indirect_calls'])} special_fields={len(row['special_field_refs'])}"
        )
        for s in row["interesting_strings"][:5]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")
        for x in row["special_field_refs"][:5]:
            lines.append(f"    FIELD 0x{x['site']:X} disp=0x{x['disp']:X} access={x['access']}")

    lines += [
        "",
        f"reachable_functions={len(forward)}",
        f"reachable_interesting_strings={len(string_refs)}",
        f"global_codesideluaclass_refs={len(codeclass_refs)}",
        f"global_gameobject_refs={len(gameobject_refs)}",
        "game_launched=false",
        "save_opened=false",
    ]
    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("GOW_UNPICKLE_INDEX_ANALYSIS_PASSED")
    print(f"candidate_0x7E6DC0_function={'NONE' if candidate_fn is None else hex(candidate_fn)}")
    print(f"reachable_functions={len(forward)} ranked_inverse_candidates={len(ranked)}")


if __name__ == "__main__":
    main()
