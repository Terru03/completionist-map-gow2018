#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
START=0x66CB30
EXTRA=[0x769110,0x7690E0,0x7691D0]
TARGETS={
    "restore_caller_a":0x5AEC9E,
    "restore_caller_b":0x5B2280,
    "restore_root":0x7E9550,
    "carrier_descriptor":0x7E7660,
    "record_dispatch":0x7E7B60,
    "userdata_serializer":0x7E9190,
}

def sha256(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

class PE:
    def __init__(self,data):
        self.data=data
        pe=struct.unpack_from("<I",data,0x3c)[0]
        coff=pe+4; nsec=struct.unpack_from("<H",data,coff+2)[0]; optsz=struct.unpack_from("<H",data,coff+16)[0]
        opt=coff+20
        if struct.unpack_from("<H",data,opt)[0]!=0x20B: raise ValueError("expected PE32+")
        self.image_base=struct.unpack_from("<Q",data,opt+24)[0]
        sec=opt+optsz; self.sections=[]
        for i in range(nsec):
            off=sec+i*40
            name=data[off:off+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize,vaddr,rsize,roff=struct.unpack_from("<IIII",data,off+8)
            self.sections.append((name,vaddr,vsize,rsize,roff))
    def off(self,rva):
        for name,vaddr,vsize,rsize,roff in self.sections:
            if vaddr<=rva<vaddr+max(vsize,rsize): return roff+(rva-vaddr)
        raise KeyError(hex(rva))
    def read(self,rva,n):
        o=self.off(rva); return self.data[o:o+n]

def rows(cur):
    c=[d[0] for d in cur.description]
    return [dict(zip(c,r)) for r in cur.fetchall()]

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def build_graph(con):
    adj={}
    for s,t in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        adj.setdefault(s,set()).add(t)
    return adj

def shortest(adj,start,target,max_depth=12):
    if start==target: return [start]
    q=deque([(start,[start])]); seen={start}
    while q:
        n,p=q.popleft()
        if len(p)-1>=max_depth: continue
        for m in adj.get(n,()):
            if m==target: return p+[m]
            if m not in seen:
                seen.add(m); q.append((m,p+[m]))
    return None

def neighborhood(adj,start,depth=2,limit=250):
    out={start}; frontier={start}
    for _ in range(depth):
        nxt=set()
        for n in frontier: nxt.update(adj.get(n,()))
        nxt-=out
        out|=nxt
        frontier=nxt
        if len(out)>=limit: break
    return sorted(out)[:limit]

def disasm(md,pe,con,f):
    code=pe.read(f["begin"],f["end"]-f["begin"])
    insns=[]
    for ins in md.disasm(code,pe.image_base+f["begin"]):
        rva=ins.address-pe.image_base
        notes=[]
        refs=rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,)))
        for r in refs:
            if r["target_string"] is not None: notes.append("str="+repr(r["target_string"]))
            else: notes.append(f"rip=0x{r['target']:X} sec={r['target_section']}")
        if ins.mnemonic in ("call","jmp") and ins.operands and ins.operands[0].type==2:
            dest=ins.operands[0].imm-pe.image_base
            notes.append(f"target=0x{dest:X}")
        insns.append({"rva":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str,"notes":notes})
    return insns

def detail(con,md,pe,addr):
    f=fn_for(con,addr)
    if not f: return None
    return {
        "function":f,
        "callers":rows(con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(f["begin"],))),
        "callees":rows(con.execute("SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(f["begin"],))),
        "rip_refs":rows(con.execute("SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site",(f["begin"],))),
        "mem_refs":rows(con.execute("SELECT site,mnemonic,operand_index,base,idx,scale,disp,access FROM mem_refs WHERE src_fn=? ORDER BY site",(f["begin"],))),
        "instructions":disasm(md,pe,con,f) if f["size"]<=0x5000 else [],
    }

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
    if actual!=EXPECTED_SHA256: raise SystemExit(f"unsupported sha256 {actual}")
    sys.path.insert(0,a.capstone_path)
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
    pe=PE(exe.read_bytes())
    con=sqlite3.connect(a.db)
    adj=build_graph(con)
    start_fn=fn_for(con,START)
    if not start_fn: raise SystemExit("0x66CB30 not indexed as function")
    start=start_fn["begin"]

    paths={}
    interesting={start}
    for name,addr in TARGETS.items():
        tf=fn_for(con,addr)
        if not tf:
            paths[name]={"target":addr,"path":None,"reason":"target_function_not_indexed"}; continue
        p=shortest(adj,start,tf["begin"],14)
        paths[name]={"target":addr,"target_fn":tf["begin"],"path":p}
        if p: interesting.update(p)

    # Always include wrappers and two call layers from the physical-slot loader.
    for addr in EXTRA:
        f=fn_for(con,addr)
        if f: interesting.add(f["begin"])
    interesting.update(neighborhood(adj,start,depth=2,limit=180))

    details={}
    for fn in sorted(interesting):
        d=detail(con,md,pe,fn)
        if d: details[f"0x{fn:X}"]=d

    result={
        "schema":1,
        "analysis":"physical_slot_to_restore_trace",
        "exe_sha256":actual,
        "start_rva":START,
        "start_function":start,
        "paths":paths,
        "details":details,
        "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"game_files_written":False,"save_written":False,"progression_written":False}
    }
    con.close()
    Path(a.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    L=["Completionist Map - physical slot -> restore authority trace",f"exe_sha256={actual}","mode=static read-only",f"start=0x{start:X}",""]
    L.append("SHORTEST STATIC CALL PATHS")
    for name,p in paths.items():
        path=p.get("path")
        if path: L.append(f"{name}: "+" -> ".join(f"0x{x:X}" for x in path))
        else: L.append(f"{name}: NO_DIRECT_INDEXED_PATH target=0x{p['target']:X}")
    L.append("")
    for key,d in details.items():
        f=d["function"]
        L.append(f"FUNCTION {key} range=0x{f['begin']:X}-0x{f['end']:X} size={f['size']}")
        for r in d["rip_refs"]:
            if r["target_string"] is not None:
                L.append(f"  STR 0x{r['site']:X} {r['target_string']!r}")
            elif r["target_section"] in (".data",".rdata"):
                L.append(f"  RIP 0x{r['site']:X} -> 0x{r['target']:X} {r['target_section']}")
        for c in d["callees"][:80]:
            t=c["target_fn"] if c["target_fn"] is not None else c["dest"]
            L.append(f"  CALLEE 0x{c['site']:X} -> 0x{t:X}")
        for m in d["mem_refs"]:
            if m["base"] not in ("rsp","rbp"):
                L.append(f"  MEM 0x{m['site']:X} {m['mnemonic']} base={m['base']} idx={m['idx']} scale={m['scale']} disp={m['disp']} access={m['access']}")
        if d["instructions"]:
            L.append("  DISASM")
            for ins in d["instructions"]:
                note=(" ; "+"; ".join(ins["notes"])) if ins["notes"] else ""
                L.append(f"    0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{note}")
        L.append("")
    Path(a.output_text).write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"PHYSICAL_SLOT_TO_RESTORE_TRACE_COMPLETE functions={len(details)}")

if __name__=="__main__":
    main()
