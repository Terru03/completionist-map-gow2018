#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
GLOBALS={
    "active_meta_0x148":0x22C67D0,
    "active_buf_4m":0x22C67A8,
    "active_buf_desc":0x22C6788,
    "active_buf_20000_a":0x22C6928,
    "active_buf_10000":0x22C67B8,
    "active_buf_20000_b":0x22C67B0,
    "active_misc_6148":0x22C6148,
    "active_misc_6940":0x22C6940,
    "active_misc_67c0":0x22C67C0,
}
TARGETS={
    "restore_caller_a":0x5AEC9E,
    "restore_caller_b":0x5B2280,
    "restore_root":0x7E9550,
    "carrier_descriptor":0x7E7660,
    "record_dispatch":0x7E7B60,
    "userdata_serializer":0x7E9190,
    "decompress":0x9C6480,
}

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

class PE:
    def __init__(self,data:bytes):
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
    def off(self,rva:int)->int:
        for name,vaddr,vsize,rsize,roff in self.sections:
            if vaddr<=rva<vaddr+max(vsize,rsize): return roff+(rva-vaddr)
        raise KeyError(hex(rva))
    def read(self,rva:int,n:int)->bytes:
        o=self.off(rva); return self.data[o:o+n]

def rows(cur):
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def graph(con):
    adj={}; rev={}
    for s,t in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        adj.setdefault(s,set()).add(t); rev.setdefault(t,set()).add(s)
    return adj,rev

def shortest(adj,start,target,max_depth=16):
    if start==target:return [start]
    q=deque([(start,[start])]); seen={start}
    while q:
        n,p=q.popleft()
        if len(p)-1>=max_depth: continue
        for m in adj.get(n,()):
            if m==target:return p+[m]
            if m not in seen:
                seen.add(m); q.append((m,p+[m]))
    return None

def disasm(md,pe,con,f):
    out=[]
    for ins in md.disasm(pe.read(f["begin"],f["end"]-f["begin"]),pe.image_base+f["begin"]):
        rva=ins.address-pe.image_base
        notes=[]
        for r in rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,))):
            if r["target_string"] is not None: notes.append("str="+repr(r["target_string"]))
            else:
                gl=next((n for n,v in GLOBALS.items() if v==r["target"]),None)
                notes.append(f"rip=0x{r['target']:X} sec={r['target_section']}"+(f" global={gl}" if gl else ""))
        if (ins.mnemonic=="call" or ins.mnemonic.startswith("j")) and ins.operands and ins.operands[0].type==2:
            dest=ins.operands[0].imm-pe.image_base
            tf=fn_for(con,dest)
            notes.append(f"target=0x{dest:X}"+(f" fn=0x{tf['begin']:X}-0x{tf['end']:X}" if tf else ""))
        out.append({"rva":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str,"notes":notes})
    return out

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
    adj,rev=graph(con)

    target_fns={}
    for name,addr in TARGETS.items():
        f=fn_for(con,addr)
        if f: target_fns[name]=f["begin"]

    global_refs={}
    owner_to_globals={}
    owners={}
    for gname,gaddr in GLOBALS.items():
        refs=rows(con.execute("SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",(gaddr,)))
        for r in refs:
            f=fn_for(con,r["site"])
            r["owner_function"]=f
            if f:
                owners[f["begin"]]=f
                owner_to_globals.setdefault(f["begin"],set()).add(gname)
        global_refs[gname]={"address":gaddr,"refs":refs}

    # Focus full disassembly on owners that touch the 4 MiB descriptor/buffer or multiple active globals.
    priority=set()
    for begin,names in owner_to_globals.items():
        if "active_buf_4m" in names or "active_buf_desc" in names or len(names)>=2:
            priority.add(begin)

    details={}
    for begin,f in sorted(owners.items()):
        rip=rows(con.execute("SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site",(begin,)))
        callees=rows(con.execute("SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(begin,)))
        callers=rows(con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(begin,)))
        paths={name:shortest(adj,begin,tfn) for name,tfn in target_fns.items()}
        details[f"0x{begin:X}"]={
            "function":f,
            "globals":sorted(owner_to_globals.get(begin,())),
            "callers":callers,
            "callees":callees,
            "rip_refs":rip,
            "paths":paths,
            "instructions":disasm(md,pe,con,f) if begin in priority and f["size"]<=0x7000 else [],
        }

    result={
        "schema":1,
        "analysis":"active_save_buffers_xrefs",
        "exe_sha256":actual,
        "globals":global_refs,
        "owners":details,
        "priority_owners":[f"0x{x:X}" for x in sorted(priority)],
        "targets":TARGETS,
        "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"save_written":False,"progression_written":False}
    }
    con.close()
    Path(a.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    L=["Completionist Map - active save/checkpoint buffer xrefs",f"exe_sha256={actual}","mode=static read-only",""]
    L.append("GLOBAL SUMMARY")
    for name,g in global_refs.items():
        L.append(f"{name} 0x{g['address']:X}: refs={len(g['refs'])}")
        for r in g["refs"]:
            f=r["owner_function"]
            owner=f"0x{f['begin']:X}-0x{f['end']:X}" if f else "unknown"
            L.append(f"  site=0x{r['site']:X} owner={owner} {r['mnemonic']}")
    L.append("")
    L.append("PRIORITY OWNERS")
    for x in sorted(priority): L.append(f"  0x{x:X}")
    L.append("")
    for key,d in details.items():
        f=d["function"]
        L.append(f"FUNCTION {key} range=0x{f['begin']:X}-0x{f['end']:X} size={f['size']} globals={','.join(d['globals'])}")
        for name,p in d["paths"].items():
            if p: L.append(f"  PATH {name}: "+" -> ".join(f"0x{x:X}" for x in p))
        for r in d["rip_refs"]:
            if r["target_string"] is not None: L.append(f"  STR 0x{r['site']:X} {r['target_string']!r}")
        for c in d["callees"]:
            t=c["target_fn"] if c["target_fn"] is not None else c["dest"]
            L.append(f"  CALLEE 0x{c['site']:X} -> 0x{t:X}")
        if d["instructions"]:
            L.append("  DISASM")
            for ins in d["instructions"]:
                note=(" ; "+"; ".join(ins["notes"])) if ins["notes"] else ""
                L.append(f"    0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{note}")
        L.append("")
    Path(a.output_text).write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"ACTIVE_SAVE_BUFFERS_XREF_TRACE_COMPLETE globals={len(global_refs)} owners={len(details)} priority={len(priority)}")

if __name__=="__main__":
    main()
