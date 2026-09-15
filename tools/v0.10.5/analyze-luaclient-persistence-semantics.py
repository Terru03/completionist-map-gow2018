"""Analyze the LuaClient persistence/lifecycle interface from the reusable GoW index.

Uses the persistent SQLite index (functions/calls/indirect calls/strings/memory refs,
static pointers and RTTI/vtables). It does not rescan GoW.exe. The goal is to
correlate the proven LuaClient vtable with save/restore helpers and identify the
native bridge around the serialized Lua table.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

VTABLE = 0xE04018
ANCHORS = {
    "restore_dispatch": 0x5AD4A0,
    "core_pickle_unpickle": 0x5AECC7,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "on_pickle_internal": 0x5B2130,
    "pickle_post_helper": 0x5B2171,
    "on_unpickle_thunk": 0x5B2280,
    "on_unpickle_internal": 0x5B2324,
    "byte_serializer": 0x7E7F10,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
    "gameobject_token_packer": 0x60B9C0,
}
INTERESTING = (
    "pickle", "unpickle", "save", "restore", "checkpoint", "lua", "gameobject",
    "serialize", "deserialize", "wad", "state", "subobj", "codesideluaclass",
)


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def function_for(con, rva):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if not row:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def summarize_fn(con, rva):
    fn = function_for(con, rva)
    b = fn["begin"] if fn else rva
    out = {"query_rva": rva, "function": fn}
    out["callers"] = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? OR dest=? ORDER BY site", (b, rva)
    ))
    out["callees"] = rows(con.execute(
        "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (b,)
    )) if fn else []
    out["indirect_calls"] = rows(con.execute(
        "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (b,)
    )) if fn else []
    refs = rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site", (b,)
    )) if fn else []
    out["strings"] = refs
    out["interesting_strings"] = [r for r in refs if any(t in (r["target_string"] or "").lower() for t in INTERESTING)]
    out["mem_refs"] = rows(con.execute(
        "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? AND disp BETWEEN 0 AND 512 ORDER BY site", (b,)
    )) if fn else []
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()
    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for needed in ("rtti_vtables", "rtti_vslots", "data_ptrs"):
        if needed not in tables:
            raise SystemExit(f"missing {needed}; build index extensions first")

    vt = con.execute(
        "SELECT vtable_rva,col_pointer_rva,col_rva,decorated_name,slot_count FROM rtti_vtables WHERE vtable_rva=?", (VTABLE,)
    ).fetchone()
    if not vt:
        raise SystemExit("LuaClient vtable 0xE04018 missing from RTTI index")
    vtable = {"vtable_rva":vt[0], "col_pointer_rva":vt[1], "col_rva":vt[2], "decorated_name":vt[3], "slot_count":vt[4]}
    slots = rows(con.execute(
        "SELECT slot_index,slot_rva,target_rva,target_function FROM rtti_vslots WHERE vtable_rva=? ORDER BY slot_index", (VTABLE,)
    ))
    for s in slots:
        s["summary"] = summarize_fn(con, s["target_rva"])

    anchor_summaries = {name: summarize_fn(con, rva) for name,rva in ANCHORS.items()}

    # Whole-program virtual call candidates for the two persistence slot offsets.
    virtual_calls = {}
    for label, disp in (("slot14_pickle", 0x70), ("slot16_unpickle", 0x80)):
        hits = rows(con.execute(
            "SELECT site,src_fn,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE disp=? ORDER BY src_fn,site", (disp,)
        ))
        enriched = []
        for h in hits:
            fn = h["src_fn"]
            strings = rows(con.execute(
                "SELECT site,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site", (fn,)
            ))
            interesting = [x for x in strings if any(t in (x["target_string"] or "").lower() for t in INTERESTING)]
            calls = rows(con.execute(
                "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (fn,)
            ))
            enriched.append({**h, "interesting_strings":interesting[:30], "calls":calls[:100]})
        virtual_calls[label] = enriched

    # The functions immediately around LuaClient's persistence methods are a
    # compact native subsystem even when they are not vtable entries themselves.
    neighborhood = []
    for (b,e,size,section) in con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin BETWEEN ? AND ? ORDER BY begin", (0x5B1E00, 0x5B2600)
    ):
        rec = summarize_fn(con, b)
        neighborhood.append(rec)

    # Cross-reference direct users of the byte serializer and unpickle wrapper.
    serializer_users = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? OR target_fn=? ORDER BY src_fn,site",
        (ANCHORS["byte_serializer"], ANCHORS["byte_serializer"]),
    ))
    unpickle_users = rows(con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? OR target_fn=? ORDER BY src_fn,site",
        (ANCHORS["core_pickle_unpickle"], ANCHORS["core_pickle_unpickle"]),
    ))

    result = {
        "schema":1,
        "analysis":"luaclient_persistence_semantics",
        "vtable":vtable,
        "slots":slots,
        "anchors":ANCHORS,
        "anchor_summaries":anchor_summaries,
        "virtual_call_candidates":virtual_calls,
        "luaclient_native_neighborhood":neighborhood,
        "byte_serializer_users":serializer_users,
        "core_pickle_unpickle_direct_users":unpickle_users,
        "exe_rescanned":False,
        "game_launched":False,
        "save_opened":False,
    }
    con.close()
    Path(args.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - LuaClient persistence semantic analysis",
        "exe_rescanned=false",
        f"class={vtable['decorated_name']}",
        f"vtable=0x{VTABLE:X} slots={vtable['slot_count']}",
        "",
        "VIRTUAL SLOTS",
    ]
    for s in slots:
        sm=s["summary"]
        labels=[k for k,v in ANCHORS.items() if v==s["target_rva"]]
        lines.append(f"- slot={s['slot_index']} offset=0x{s['slot_index']*8:X} target=0x{s['target_rva']:X} labels={labels} fn={'NONE' if not sm['function'] else f'0x{sm['function']['begin']:X}'}")
        for x in sm["interesting_strings"][:10]: lines.append(f"    STRING 0x{x['site']:X} {x['target_string']!r}")
        for c in sm["callees"][:12]: lines.append(f"    CALL 0x{c['site']:X} -> 0x{c['dest']:X}")
    lines += ["", "PERSISTENCE ANCHOR CALLERS"]
    for name in ("on_pickle_internal","pickle_post_helper","on_unpickle_thunk","on_unpickle_internal","byte_serializer","core_pickle_unpickle"):
        sm=anchor_summaries[name]
        lines.append(f"- {name} 0x{ANCHORS[name]:X}: callers={len(sm['callers'])} callees={len(sm['callees'])} indirect={len(sm['indirect_calls'])}")
        for c in sm["callers"][:30]: lines.append(f"    CALLER fn=0x{c['src_fn']:X} site=0x{c['site']:X} kind={c['kind']}")
        for x in sm["interesting_strings"][:15]: lines.append(f"    STRING 0x{x['site']:X} {x['target_string']!r}")
    lines += ["", "INDIRECT VIRTUAL CALL CANDIDATES"]
    for label,hits in virtual_calls.items():
        lines.append(f"- {label}: {len(hits)}")
        for h in hits[:80]:
            ss=[x['target_string'] for x in h['interesting_strings'][:8]]
            lines.append(f"    fn=0x{h['src_fn']:X} site=0x{h['site']:X} base={h['base']} reg={h['reg']} strings={ss}")
    lines += ["", "BYTE SERIALIZER USERS"]
    for r in serializer_users: lines.append(f"- fn=0x{r['src_fn']:X} site=0x{r['site']:X}")
    lines += ["", "CORE.PICKLE.UNPICKLE DIRECT USERS"]
    for r in unpickle_users: lines.append(f"- fn=0x{r['src_fn']:X} site=0x{r['site']:X} kind={r['kind']}")
    lines += ["", "NATIVE NEIGHBORHOOD 0x5B1E00-0x5B2600"]
    for sm in neighborhood:
        fn=sm["function"]
        if not fn: continue
        lines.append(f"- fn=0x{fn['begin']:X}-0x{fn['end']:X} size={fn['size']} callers={len(sm['callers'])} callees={len(sm['callees'])} indirect={len(sm['indirect_calls'])}")
        for x in sm["interesting_strings"][:10]: lines.append(f"    STRING 0x{x['site']:X} {x['target_string']!r}")
    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("LUACLIENT_PERSISTENCE_SEMANTICS_PASSED")
    print(f"class={vtable['decorated_name']}")
    print(f"slot14_indirect_calls={len(virtual_calls['slot14_pickle'])}")
    print(f"slot16_indirect_calls={len(virtual_calls['slot16_unpickle'])}")
    print(f"native_neighborhood_functions={len(neighborhood)}")

if __name__ == "__main__":
    main()
