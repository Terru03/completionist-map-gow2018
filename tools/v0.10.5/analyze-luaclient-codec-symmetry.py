"""Analyze LuaClient save/restore codec symmetry from the reusable GoW SQLite index.

Pure SQLite analysis. No GoW.exe rescan, game launch, or save access.

Proven native shape entering this pass:
  save:    LuaClient slot14 -> 0x5B2130 -> 0x5B2171 -> 0x7E7F10
  restore: LuaClient slot16 -> 0x5B2280 -> 0x7E9550 -> 0x5B2324

The goal is to determine whether 0x7E9550 is the native inverse byte/Lua codec
partner of 0x7E7F10 and where userdata / CodeSideLuaClass reconstruction occurs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sqlite3

ROOTS = {
    "save_virtual": 0x5B2130,
    "save_post_helper": 0x5B2171,
    "restore_virtual": 0x5B2280,
    "restore_pre_helper": 0x7E9550,
    "restore_bridge_helper": 0x5B22EF,
    "on_unpickle_internal": 0x5B2324,
    "byte_serializer": 0x7E7F10,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
}
INTERESTING_TERMS = (
    "gameobject", "pickle", "unpickle", "serialize", "deserialize", "userdata",
    "codesideluaclass", "table", "ref", "checkpoint", "save", "restore", "lua",
)
SPECIAL_DISPS = {0x30, 0x48, 0xA4, 0xB8}


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


def summarize(con: sqlite3.Connection, rva: int):
    fn = function_for(con, rva)
    b = fn["begin"] if fn else rva
    result = {"query_rva": rva, "function": fn}
    result["callers"] = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? OR dest=? ORDER BY src_fn,site",
        (b, rva),
    ))
    if not fn:
        result.update({"callees": [], "indirect_calls": [], "strings": [], "mem_refs": [], "special_mem_refs": []})
        return result
    result["callees"] = rows(con.execute(
        "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (b,)
    ))
    result["indirect_calls"] = rows(con.execute(
        "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (b,)
    ))
    string_rows = rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
        (b,),
    ))
    result["strings"] = [r for r in string_rows if any(t in (r["target_string"] or "").lower() for t in INTERESTING_TERMS)]
    mem = rows(con.execute(
        "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? ORDER BY site", (b,)
    ))
    result["mem_refs"] = [r for r in mem if -0x100 <= r["disp"] <= 0x200][:1000]
    result["special_mem_refs"] = [r for r in mem if r["disp"] in SPECIAL_DISPS]
    return result


def graph(con: sqlite3.Connection):
    out = defaultdict(set)
    rev = defaultdict(set)
    for src, dst in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        out[src].add(dst)
        rev[dst].add(src)
    return out, rev


def bfs(g, start, depth):
    if start is None:
        return {}
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if dist[cur] >= depth:
            continue
        for nxt in g.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                q.append(nxt)
    return dist


def fn_begin(con, rva):
    f = function_for(con, rva)
    return f["begin"] if f else None


def local_codec_functions(con):
    result = []
    for b,e,size,section in con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin BETWEEN 0x7E7000 AND 0x7EA500 ORDER BY begin"
    ):
        sm = summarize(con, b)
        score = 0
        score += 25 * len(sm["indirect_calls"])
        score += 20 * len(sm["special_mem_refs"])
        score += 15 * len(sm["strings"])
        calls = {x["dest"] for x in sm["callees"]}
        if ROOTS["byte_serializer"] in calls: score += 80
        if ROOTS["userdata_serializer"] in calls: score += 80
        if ROOTS["restore_pre_helper"] in calls: score += 80
        result.append({"function": b, "end": e, "size": size, "score": score, "summary": sm})
    result.sort(key=lambda x: (-x["score"], x["function"]))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    ap.add_argument("--depth", type=int, default=5)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")
    con = sqlite3.connect(db)
    summaries = {name: summarize(con, rva) for name,rva in ROOTS.items()}
    fn_roots = {name: fn_begin(con, rva) for name,rva in ROOTS.items()}
    out, rev = graph(con)

    restore_root = fn_roots["restore_pre_helper"]
    serializer_root = fn_roots["byte_serializer"]
    userdata_root = fn_roots["userdata_serializer"]
    go_root = fn_roots["gameobject_token_resolver"]
    unbox_root = fn_roots["lua_gameobject_unbox"]

    restore_forward = bfs(out, restore_root, args.depth)
    serializer_forward = bfs(out, serializer_root, args.depth)
    userdata_forward = bfs(out, userdata_root, args.depth)
    go_reverse = bfs(rev, go_root, args.depth)
    unbox_reverse = bfs(rev, unbox_root, args.depth)

    intersections = {
        "restore_to_gameobject_resolver": [],
        "restore_to_lua_gameobject_unbox": [],
        "restore_serializer_overlap": [],
        "restore_userdata_serializer_overlap": [],
    }
    for fn, d in restore_forward.items():
        if fn in go_reverse:
            intersections["restore_to_gameobject_resolver"].append({"function":fn,"from_restore":d,"to_target":go_reverse[fn]})
        if fn in unbox_reverse:
            intersections["restore_to_lua_gameobject_unbox"].append({"function":fn,"from_restore":d,"to_target":unbox_reverse[fn]})
        if fn in serializer_forward:
            intersections["restore_serializer_overlap"].append({"function":fn,"restore_depth":d,"serializer_depth":serializer_forward[fn]})
        if fn in userdata_forward:
            intersections["restore_userdata_serializer_overlap"].append({"function":fn,"restore_depth":d,"userdata_depth":userdata_forward[fn]})
    for key in intersections:
        intersections[key].sort(key=lambda x: (sum(v for k,v in x.items() if k != "function"), x["function"]))

    local = local_codec_functions(con)
    indirect_special = []
    for rec in local:
        sm = rec["summary"]
        if sm["indirect_calls"] or sm["special_mem_refs"]:
            indirect_special.append({
                "function": rec["function"], "score": rec["score"],
                "indirect_calls": sm["indirect_calls"],
                "special_mem_refs": sm["special_mem_refs"],
                "strings": sm["strings"],
                "callees": sm["callees"],
            })

    result = {
        "schema": 1,
        "analysis": "luaclient_codec_symmetry",
        "roots": ROOTS,
        "root_functions": fn_roots,
        "summaries": summaries,
        "graph_depth": args.depth,
        "intersections": intersections,
        "local_codec_ranked": local[:100],
        "local_indirect_or_classfield_functions": indirect_special[:100],
        "proven_input_shape": {
            "save": "LuaClient slot14 -> 0x5B2130 -> 0x5B2171 -> 0x7E7F10",
            "restore": "LuaClient slot16 -> 0x5B2280 -> 0x7E9550 -> 0x5B2324",
        },
        "exe_rescanned": False,
        "game_launched": False,
        "save_opened": False,
    }
    con.close()
    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - LuaClient codec symmetry analysis",
        "exe_rescanned=false",
        "",
        "PROVEN INPUT SHAPE",
        "save:    LuaClient slot14 -> 0x5B2130 -> 0x5B2171 -> 0x7E7F10",
        "restore: LuaClient slot16 -> 0x5B2280 -> 0x7E9550 -> 0x5B2324",
        "",
        "ROOT SUMMARIES",
    ]
    for name in ROOTS:
        sm = summaries[name]
        fn = sm["function"]
        fn_text = "NONE" if not fn else f"0x{fn['begin']:X}-0x{fn['end']:X}"
        lines.append(f"- {name} rva=0x{ROOTS[name]:X} fn={fn_text} callers={len(sm['callers'])} callees={len(sm['callees'])} indirect={len(sm['indirect_calls'])} special_fields={len(sm['special_mem_refs'])}")
        for s in sm["strings"][:12]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")
        for c in sm["callees"][:20]:
            lines.append(f"    CALL 0x{c['site']:X} -> 0x{c['dest']:X}")
        for i in sm["indirect_calls"][:20]:
            lines.append(f"    INDIRECT 0x{i['site']:X} base={i['base']} reg={i['reg']} disp={i['disp']}")
        for m in sm["special_mem_refs"][:20]:
            lines.append(f"    FIELD 0x{m['site']:X} disp=0x{m['disp']:X} access={m['access']} base={m['base']}")

    lines += ["", "GRAPH INTERSECTIONS"]
    for name, hits in intersections.items():
        lines.append(f"- {name}: {len(hits)}")
        for h in hits[:30]:
            lines.append("    " + " ".join(f"{k}=0x{v:X}" if k=="function" else f"{k}={v}" for k,v in h.items()))

    lines += ["", "TOP LOCAL CODEC FUNCTIONS 0x7E7000-0x7EA500"]
    for i, rec in enumerate(local[:50], 1):
        sm = rec["summary"]
        lines.append(f"#{i} fn=0x{rec['function']:X}-0x{rec['end']:X} score={rec['score']} indirect={len(sm['indirect_calls'])} special_fields={len(sm['special_mem_refs'])} strings={len(sm['strings'])}")
        for s in sm["strings"][:6]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")
        for c in sm["callees"][:10]:
            lines.append(f"    CALL 0x{c['site']:X} -> 0x{c['dest']:X}")
        for x in sm["indirect_calls"][:8]:
            lines.append(f"    INDIRECT 0x{x['site']:X} base={x['base']} reg={x['reg']} disp={x['disp']}")
        for m in sm["special_mem_refs"][:8]:
            lines.append(f"    FIELD 0x{m['site']:X} disp=0x{m['disp']:X} access={m['access']} base={m['base']}")

    Path(args.output_text).write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("LUACLIENT_CODEC_SYMMETRY_PASSED")
    pre = summaries["restore_pre_helper"]
    pre_fn = pre["function"]
    pre_fn_text = "NONE" if not pre_fn else f"0x{pre_fn['begin']:X}"
    print(f"restore_0x7E9550_function={pre_fn_text}")
    print(f"restore_0x7E9550_callees={len(pre['callees'])}")
    print(f"restore_0x7E9550_indirect_calls={len(pre['indirect_calls'])}")
    print(f"restore_0x7E9550_special_fields={len(pre['special_mem_refs'])}")


if __name__ == "__main__":
    main()
