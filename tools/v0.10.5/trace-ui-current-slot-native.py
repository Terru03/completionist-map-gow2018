#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path

TERMS = [
    "SetCurrentSlot",
    "GetCurrentSlot",
    "CurrentSlot",
    "LoadSaveGame",
    "LoadedIntoSaveSlot",
    "IsSlotValid",
    "GetFreeManualSlot",
    "MakeManualSaveGame",
]

def rows(cur):
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def function_for(con, rva):
    row=con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva,rva)).fetchone()
    if not row: return None
    return {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def refs_for_string(con, rva):
    out=rows(con.execute(
        "SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",
        (rva,)))
    for x in out:
        x["function"]=function_for(con,x["src_fn"])
    return out

def function_detail(con, fn):
    return {
        "function": function_for(con, fn),
        "callers": rows(con.execute(
            "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? OR dest=? ORDER BY site LIMIT 300",
            (fn,fn))),
        "callees": rows(con.execute(
            "SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site LIMIT 500",
            (fn,))),
        "rip_refs": rows(con.execute(
            "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site LIMIT 500",
            (fn,))),
        "mem_refs": rows(con.execute(
            "SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? ORDER BY site LIMIT 1200",
            (fn,))),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args=ap.parse_args()
    con=sqlite3.connect(args.db)

    exact={}
    functions=set()
    for term in TERMS:
        ss=rows(con.execute("SELECT rva,text FROM strings WHERE text=? ORDER BY rva",(term,)))
        refs=[]
        for s in ss:
            rr=refs_for_string(con,s["rva"])
            refs.extend(rr)
            functions.update(x["src_fn"] for x in rr)
        exact[term]={"strings":ss,"refs":refs}

    # Include the known LoadedIntoSaveSlot owner and its sole external caller.
    functions.update([0x533E30,0x7698BF])
    detail={f"0x{fn:X}":function_detail(con,fn) for fn in sorted(functions)}
    con.close()

    result={"schema":1,"analysis":"ui_current_slot_native_trace","exact":exact,"functions":detail}
    Path(args.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    lines=["Completionist Map - UI current save slot native trace",""]
    for term,data in exact.items():
        lines.append(f"{term}: strings={len(data['strings'])} refs={len(data['refs'])}")
        for r in data["refs"]:
            lines.append(f"  site=0x{r['site']:X} fn=0x{r['src_fn']:X} {r['mnemonic']}")
    lines += ["","FUNCTION DETAILS"]
    for k,d in detail.items():
        lines.append(k)
        fn=d["function"]
        if fn: lines.append(f"  range=0x{fn['begin']:X}-0x{fn['end']:X} size={fn['size']}")
        lines.append(f"  callers={len(d['callers'])} callees={len(d['callees'])} rip_refs={len(d['rip_refs'])} mem_refs={len(d['mem_refs'])}")
        for r in d["rip_refs"]:
            if r.get("target_string"):
                lines.append(f"  STR 0x{r['site']:X} {r['target_string']!r}")
        for c in d["callers"][:40]:
            lines.append(f"  CALLER fn=0x{c['src_fn']:X} site=0x{c['site']:X}")
        for c in d["callees"][:60]:
            t=c["target_fn"] if c["target_fn"] is not None else c["dest"]
            lines.append(f"  CALLEE site=0x{c['site']:X} target=0x{t:X}")
        # Keep likely state accesses: non-stack/non-frame memory refs.
        for m in d["mem_refs"]:
            if m.get("base") not in ("rsp","rbp") and m.get("base") is not None:
                lines.append(
                    f"  MEM 0x{m['site']:X} {m['mnemonic']} base={m['base']} idx={m['idx']} "
                    f"scale={m['scale']} disp={m['disp']} access={m['access']}"
                )
    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("UI_CURRENT_SLOT_NATIVE_TRACE_COMPLETE")

if __name__=="__main__":
    main()
