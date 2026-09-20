#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from collections import defaultdict, deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

SOURCE_ADDRS={
    "checkpoint_sga":0x66ABD0,
    "active_slot_bind":0x66239D,
    "slot_load_driver":0x6626B0,
    "checkpoint_stage_a":0x6687F0,
    "checkpoint_stage_b":0x669300,
    "checkpoint_stage_c":0x669B00,
    "load_slot_core":0x66B650,
    "active_checkpoint_apply":0x66C080,
}
TARGET_ADDRS={
    "restore_caller_a":0x5AEC9E,
    "restore_caller_b":0x5B2280,
    "restore_root":0x7E9550,
    "carrier_descriptor":0x7E7660,
    "record_dispatch":0x7E7B60,
}
FOCUS_ADDRS=[0x661C00,0x661CC0,0x661E30,0x661BC0,0x66ABD0,0x6687F0,0x669300,0x669B00,0x5AEC9E,0x5B2280,0x7E9550]

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

class PE:
    def __init__(self,data:bytes):
        self.data=data
        pe=struct.unpack_from("<I",data,0x3c)[0]
        coff=pe+4
        nsec=struct.unpack_from("<H",data,coff+2)[0]
        optsz=struct.unpack_from("<H",data,coff+16)[0]
        opt=coff+20
        if struct.unpack_from("<H",data,opt)[0]!=0x20B: raise ValueError("expected PE32+")
        self.image_base=struct.unpack_from("<Q",data,opt+24)[0]
        sec=opt+optsz
        self.sections=[]
        for i in range(nsec):
            off=sec+i*40
            name=data[off:off+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize,vaddr,rsize,roff=struct.unpack_from("<IIII",data,off+8)
            self.sections.append((name,vaddr,vsize,rsize,roff))
    def off(self,rva:int)->int:
        for name,vaddr,vsize,rsize,roff in self.sections:
            if vaddr<=rva<vaddr+max(vsize,rsize):return roff+(rva-vaddr)
        raise KeyError(hex(rva))
    def read(self,rva:int,n:int)->bytes:
        o=self.off(rva);return self.data[o:o+n]

def rows(cur):
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def build_graph(con):
    adj=defaultdict(set); rev=defaultdict(set)
    for s,t in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        adj[s].add(t);rev[t].add(s)
    return adj,rev

def bfs_dist(graph,starts,max_depth):
    dist={}
    q=deque()
    for s in starts:
        dist[s]=0;q.append(s)
    while q:
        n=q.popleft();d=dist[n]
        if d>=max_depth:continue
        for m in graph.get(n,()):
            if m not in dist:
                dist[m]=d+1;q.append(m)
    return dist

def path_from_parent(parent,start_set,node):
    p=[node]
    while p[-1] not in start_set and p[-1] in parent:
        p.append(parent[p[-1]])
    p.reverse()
    return p

def bfs_parent(graph,starts,max_depth):
    dist={};parent={};q=deque()
    for s in starts:dist[s]=0;q.append(s)
    while q:
        n=q.popleft();d=dist[n]
        if d>=max_depth:continue
        for m in graph.get(n,()):
            if m not in dist:
                dist[m]=d+1;parent[m]=n;q.append(m)
    return dist,parent

def disasm(md,pe,con,f):
    out=[]
    code=pe.read(f["begin"],f["end"]-f["begin"])
    for ins in md.disasm(code,pe.image_base+f["begin"]):
        rva=ins.address-pe.image_base
        notes=[]
        for rr in rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,))):
            if rr["target_string"] is not None:notes.append("str="+repr(rr["target_string"]))
            else:notes.append(f"rip=0x{rr['target']:X} sec={rr['target_section']}")
        if ins.mnemonic=="call":
            if ins.operands and ins.operands[0].type==2:
                dest=ins.operands[0].imm-pe.image_base
                tf=fn_for(con,dest)
                notes.append(f"direct=0x{dest:X}"+(f" fn=0x{tf['begin']:X}" if tf else ""))
            else:
                notes.append("INDIRECT_CALL")
        out.append({"rva":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str,"notes":notes})
    return out

def collect_rip_targets(con,fnset,sections=(".data",".rdata")):
    acc=defaultdict(lambda:{"source_fns":set(),"refs":[]})
    if not fnset:return acc
    marks=",".join("?" for _ in fnset)
    q=f"SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn IN ({marks})"
    for r in rows(con.execute(q,tuple(fnset))):
        if r["target_section"] in sections and r["target_string"] is None:
            e=acc[r["target"]];e["source_fns"].add(r["src_fn"]);e["refs"].append(r)
    return acc

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",required=True)
    ap.add_argument("--db",required=True)
    ap.add_argument("--capstone-path",required=True)
    ap.add_argument("--output-json",required=True)
    ap.add_argument("--output-text",required=True)
    a=ap.parse_args()

    exe=Path(a.game_root)/"GoW.exe"
    actual=sha256(exe).lower()
    if actual!=EXPECTED_SHA256:raise SystemExit(f"unsupported sha256 {actual}")

    sys.path.insert(0,a.capstone_path)
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    pe=PE(exe.read_bytes())
    con=sqlite3.connect(a.db)
    adj,rev=build_graph(con)

    source_fns={}
    for name,addr in SOURCE_ADDRS.items():
        f=fn_for(con,addr)
        if f:source_fns[name]=f["begin"]
    target_fns={}
    for name,addr in TARGET_ADDRS.items():
        f=fn_for(con,addr)
        if f:target_fns[name]=f["begin"]

    fdist,fparent=bfs_parent(adj,set(source_fns.values()),7)
    rdist,rparent=bfs_parent(rev,set(target_fns.values()),7)

    common=set(fdist)&set(rdist)
    ranked_common=sorted(common,key=lambda x:(fdist[x]+rdist[x],fdist[x],x))[:200]
    common_rows=[]
    for fn in ranked_common:
        f=fn_for(con,fn)
        common_rows.append({
            "function":f,"forward_depth":fdist[fn],"reverse_depth":rdist[fn],
            "source_path":path_from_parent(fparent,set(source_fns.values()),fn),
            "target_reverse_path":path_from_parent(rparent,set(target_fns.values()),fn),
        })

    forward_set=set(fdist)
    reverse_set=set(rdist)
    fr=collect_rip_targets(con,forward_set)
    rr=collect_rip_targets(con,reverse_set)
    shared=[]
    for target in set(fr)&set(rr):
        score=len(fr[target]["source_fns"])*len(rr[target]["source_fns"])
        shared.append({
            "target":target,
            "forward_fn_count":len(fr[target]["source_fns"]),
            "reverse_fn_count":len(rr[target]["source_fns"]),
            "score":score,
            "forward_refs":fr[target]["refs"][:60],
            "reverse_refs":rr[target]["refs"][:60],
        })
    shared.sort(key=lambda x:(-x["score"],x["target"]))
    shared=shared[:250]

    focus={}
    seen=set()
    for addr in FOCUS_ADDRS:
        f=fn_for(con,addr)
        if not f or f["begin"] in seen:continue
        seen.add(f["begin"])
        ins=disasm(md,pe,con,f) if f["size"]<=0x7000 else []
        indirect=[x for x in ins if "INDIRECT_CALL" in x["notes"]]
        focus[f"0x{f['begin']:X}"]={
            "function":f,
            "strings":rows(con.execute("SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",(f["begin"],))),
            "callees":rows(con.execute("SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(f["begin"],))),
            "callers":rows(con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(f["begin"],))),
            "indirect_calls":indirect,
            "instructions":ins,
        }

    result={
        "schema":1,
        "analysis":"checkpoint_restore_bridge",
        "exe_sha256":actual,
        "source_functions":source_fns,
        "target_functions":target_fns,
        "forward_reachable_count":len(forward_set),
        "reverse_reachable_count":len(reverse_set),
        "common_functions":common_rows,
        "shared_native_targets":shared,
        "focus":focus,
        "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"save_written":False,"progression_written":False}
    }
    con.close()
    Path(a.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    L=[
        "Completionist Map - checkpoint.SGA -> restore bridge analysis",
        f"exe_sha256={actual}",
        "mode=static read-only",
        f"forward_reachable={len(forward_set)} reverse_reachable={len(reverse_set)} common={len(common_rows)}",
        ""
    ]
    L.append("SOURCE FUNCTIONS")
    for n,v in source_fns.items():L.append(f"  {n}=0x{v:X}")
    L.append("TARGET FUNCTIONS")
    for n,v in target_fns.items():L.append(f"  {n}=0x{v:X}")
    L.append("")
    L.append("COMMON DIRECT-CALL FUNCTIONS")
    if not common_rows:L.append("  none within depth 7")
    for x in common_rows:
        f=x["function"]
        L.append(f"  fn=0x{f['begin']:X}-0x{f['end']:X} fwd={x['forward_depth']} rev={x['reverse_depth']}")
        L.append("    source_path="+" -> ".join(f"0x{v:X}" for v in x["source_path"]))
        L.append("    target_reverse_path="+" -> ".join(f"0x{v:X}" for v in x["target_reverse_path"]))
    L.append("")
    L.append("TOP SHARED NATIVE DATA/RDATA TARGETS")
    for x in shared[:80]:
        L.append(f"  target=0x{x['target']:X} score={x['score']} fwd_fns={x['forward_fn_count']} rev_fns={x['reverse_fn_count']}")
        for r in x["forward_refs"][:8]:L.append(f"    F 0x{r['site']:X} fn=0x{r['src_fn']:X} {r['mnemonic']}")
        for r in x["reverse_refs"][:8]:L.append(f"    R 0x{r['site']:X} fn=0x{r['src_fn']:X} {r['mnemonic']}")
    L.append("")
    for key,d in focus.items():
        f=d["function"]
        L.append(f"FOCUS {key} range=0x{f['begin']:X}-0x{f['end']:X}")
        for s in d["strings"]:L.append(f"  STR 0x{s['site']:X} {s['target_string']!r}")
        for ic in d["indirect_calls"]:L.append(f"  INDIRECT 0x{ic['rva']:X}: {ic['mnemonic']} {ic['op_str']} {'; '.join(ic['notes'])}")
        for c in d["callees"][:80]:
            t=c["target_fn"] if c["target_fn"] is not None else c["dest"]
            L.append(f"  CALLEE 0x{c['site']:X} -> 0x{t:X}")
        L.append("")
    Path(a.output_text).write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"CHECKPOINT_RESTORE_BRIDGE_COMPLETE common={len(common_rows)} shared={len(shared)} focus={len(focus)}")

if __name__=="__main__":
    main()
