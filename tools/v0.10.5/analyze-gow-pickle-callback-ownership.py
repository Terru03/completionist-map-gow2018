"""Find ownership/registration of native pickle/unpickle wrapper callbacks.

Pure SQLite analysis. No GoW.exe rescan, game launch, or save access.

The key problem is that the proven core.pickle.Unpickle wrapper at 0x5AECC7
has zero direct callers.  This tool therefore searches address references and
registration symmetry against the save/restore wrappers instead of walking
only direct-call edges.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

TARGETS = {
    "core_pickle_unpickle": 0x5AECC7,
    "pickle_table_builder": 0x5AF01C,
    "pickle_driver": 0x5AF8AD,
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "restore_dispatch": 0x5AD4A0,
    "byte_serializer": 0x7E7F10,
    "userdata_serializer": 0x7E9190,
}

INTERESTING = (
    "Pickle", "Unpickle", "OnPickleInternal", "OnUnpickleInternal",
    "__PickleTable", "__SoftPickleTable", "__codesideluaclass",
    "GameObject", "ResolveGameObject", "Serialize", "Deserialize",
)


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def function_for(con, rva):
    r = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}


def exact_refs(con, rva):
    return {
        "direct_edges": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE dest=? OR target_fn=? ORDER BY site",
            (rva, rva),
        )),
        "rip_refs": rows(con.execute(
            "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",
            (rva,),
        )),
        "imm_refs": rows(con.execute(
            "SELECT site,src_fn,mnemonic,value_rva,target_section FROM imm_refs WHERE value_rva=? ORDER BY site",
            (rva,),
        )),
    }


def fn_summary(con, fn):
    f = function_for(con, fn)
    if not f:
        return {"function":fn,"pdata":None}
    b = f["begin"]
    strings = rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",
        (b,),
    ))
    strings = [x for x in strings if any(t.lower() in (x["target_string"] or "").lower() for t in INTERESTING)]
    return {
        "function": b,
        "pdata": f,
        "callees": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site", (b,)
        )),
        "indirect_calls": rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? ORDER BY site", (b,)
        )),
        "strings": strings,
        "rip_text_refs": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_section='.text' ORDER BY site",
            (b,),
        )),
        "image_immediates": rows(con.execute(
            "SELECT site,mnemonic,value_rva,target_section FROM imm_refs WHERE src_fn=? ORDER BY site", (b,)
        )),
    }


def local_window(con, src_fn, site, radius=0x100):
    lo, hi = site-radius, site+radius
    return {
        "edges": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (src_fn,lo,hi),
        )),
        "rip_refs": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (src_fn,lo,hi),
        )),
        "imm_refs": rows(con.execute(
            "SELECT site,mnemonic,value_rva,target_section FROM imm_refs WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (src_fn,lo,hi),
        )),
        "mem_refs": rows(con.execute(
            "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (src_fn,lo,hi),
        )),
        "indirect_calls": rows(con.execute(
            "SELECT site,kind,reg,base,idx,scale,disp FROM indirect_calls WHERE src_fn=? AND site BETWEEN ? AND ? ORDER BY site",
            (src_fn,lo,hi),
        )),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',required=True)
    ap.add_argument('--output-json',required=True)
    ap.add_argument('--output-text',required=True)
    args=ap.parse_args()

    con=sqlite3.connect(Path(args.db))
    refs={name:exact_refs(con,rva) for name,rva in TARGETS.items()}

    # Collect every source function that takes the address of any target rather
    # than merely calling it.  Shared ownership of Pickle/Unpickle wrappers is
    # especially valuable because it reveals registration tables/objects.
    owners={}
    for name, rr in refs.items():
        for kind in ('rip_refs','imm_refs'):
            for r in rr[kind]:
                fn=r['src_fn']
                owners.setdefault(fn, {"targets":set(),"sites":[]})
                owners[fn]['targets'].add(name)
                owners[fn]['sites'].append({"target":name,"kind":kind,**r})

    owner_rows=[]
    for fn,v in owners.items():
        summary=fn_summary(con,fn)
        windows=[]
        for site in sorted({x['site'] for x in v['sites']}):
            windows.append({"site":site,"window":local_window(con,fn,site)})
        score=100*len(v['targets']) + 20*len(summary.get('strings',[])) + 10*len(summary.get('indirect_calls',[]))
        owner_rows.append({
            "function":fn,
            "score":score,
            "targets":sorted(v['targets']),
            "reference_sites":sorted(v['sites'], key=lambda x:x['site']),
            "summary":summary,
            "windows":windows,
        })
    owner_rows.sort(key=lambda x:(-x['score'],x['function']))

    # Find functions containing references to >=2 members of the callback
    # family even if one member is referenced through a direct call.
    family_sources={}
    for name,rr in refs.items():
        for kind in ('direct_edges','rip_refs','imm_refs'):
            for r in rr[kind]:
                fn=r['src_fn']
                family_sources.setdefault(fn,set()).add(name)
    family=[{"function":fn,"targets":sorted(ts),"summary":fn_summary(con,fn)} for fn,ts in family_sources.items() if len(ts)>=2]
    family.sort(key=lambda x:(-len(x['targets']),x['function']))

    result={
        "schema":1,
        "analysis":"pickle_callback_ownership",
        "targets":TARGETS,
        "exact_refs":refs,
        "address_owner_functions":owner_rows[:100],
        "multi_target_family_functions":family[:100],
        "proven": [
            "0x5AECC7 is the native wrapper that resolves package.loaded['core.pickle']['Unpickle']",
            "0x5AECC7 has zero indexed direct callers",
            "save-side userdata persistence dispatch is 0x7E9190 -> CodeSideLuaClass +0xB8",
        ],
        "goal":"recover address-taking registration owner / callback slot for 0x5AECC7 and symmetric pickle callbacks",
        "exe_rescanned":False,
        "game_launched":False,
        "save_opened":False,
    }
    con.close()
    Path(args.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding='utf-8')

    lines=[
        "Completionist Map - pickle/unpickle callback ownership from reusable SQLite index",
        "exe_rescanned=false",
        "",
        "EXACT TARGET REFERENCES",
    ]
    for name,rva in TARGETS.items():
        rr=refs[name]
        lines.append(f"- {name} 0x{rva:X}: direct={len(rr['direct_edges'])} rip={len(rr['rip_refs'])} imm={len(rr['imm_refs'])}")
        for k in ('rip_refs','imm_refs'):
            for x in rr[k][:20]:
                lines.append(f"    {k[:-1].upper()} site=0x{x['site']:X} src_fn=0x{x['src_fn']:X}")
    lines += ["", "TOP ADDRESS-OWNER FUNCTIONS"]
    for i,o in enumerate(owner_rows[:40],1):
        lines.append(f"#{i} fn=0x{o['function']:X} score={o['score']} targets={o['targets']}")
        for s in o['reference_sites'][:20]:
            lines.append(f"    {s['kind']} site=0x{s['site']:X} target={s['target']}")
        for s in o['summary'].get('strings',[])[:10]:
            lines.append(f"    STRING 0x{s['site']:X} {s['target_string']!r}")
        for ic in o['summary'].get('indirect_calls',[])[:10]:
            lines.append(f"    INDIRECT 0x{ic['site']:X} reg={ic['reg']} base={ic['base']} disp={ic['disp']}")
    lines += ["", "MULTI-TARGET CALLBACK-FAMILY FUNCTIONS"]
    for i,o in enumerate(family[:40],1):
        lines.append(f"#{i} fn=0x{o['function']:X} targets={o['targets']}")
    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding='utf-8')
    print('PICKLE_CALLBACK_OWNERSHIP_ANALYSIS_PASSED')
    print(f"address_owner_functions={len(owner_rows)}")
    print(f"multi_target_family_functions={len(family)}")

if __name__=='__main__':
    main()
