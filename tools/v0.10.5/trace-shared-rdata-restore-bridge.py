#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
OBJECTS={
    "shared_rdata_A":0xD9E6B0,
    "shared_rdata_B":0xD9E4E8,
}
FOCUS=[
    0x9ECF00,0x9EC6C0,0x9ECE90,0x9EDFC0,0x9E44B0,0x9E8190,0x9ED450,0x9ED520,
    0x7E9550,0x7E7660,0x5B2280,0x5A3CE0,0x782FE0
]

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
        self.nsec=struct.unpack_from("<H",data,coff+2)[0]
        optsz=struct.unpack_from("<H",data,coff+16)[0]
        opt=coff+20
        if struct.unpack_from("<H",data,opt)[0]!=0x20B:raise ValueError("expected PE32+")
        self.image_base=struct.unpack_from("<Q",data,opt+24)[0]
        self.size_image=struct.unpack_from("<I",data,opt+56)[0]
        sec=opt+optsz
        self.sections=[]
        for i in range(self.nsec):
            off=sec+i*40
            name=data[off:off+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize,vaddr,rsize,roff=struct.unpack_from("<IIII",data,off+8)
            self.sections.append({"name":name,"vaddr":vaddr,"vsize":vsize,"rsize":rsize,"roff":roff})
    def off(self,rva:int)->int:
        for s in self.sections:
            if s["vaddr"]<=rva<s["vaddr"]+max(s["vsize"],s["rsize"]):
                return s["roff"]+(rva-s["vaddr"])
        raise KeyError(hex(rva))
    def read(self,rva:int,n:int)->bytes:
        o=self.off(rva);return self.data[o:o+n]
    def section_for_rva(self,rva:int):
        for s in self.sections:
            if s["vaddr"]<=rva<s["vaddr"]+max(s["vsize"],s["rsize"]):return s["name"]
        return None
    def ptr_info(self,q:int):
        # MSVC image pointers are usually absolute VAs in this build.
        if self.image_base<=q<self.image_base+self.size_image:
            rva=q-self.image_base
            return {"kind":"va","rva":rva,"section":self.section_for_rva(rva)}
        if 0<=q<self.size_image:
            return {"kind":"rva","rva":q,"section":self.section_for_rva(q)}
        return None

def rows(cur):
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def disasm(md,pe,con,f):
    out=[]
    for ins in md.disasm(pe.read(f["begin"],f["end"]-f["begin"]),pe.image_base+f["begin"]):
        rva=ins.address-pe.image_base
        notes=[]
        for rr in rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,))):
            if rr["target_string"] is not None:notes.append("str="+repr(rr["target_string"]))
            else:
                obj=next((n for n,a in OBJECTS.items() if a==rr["target"]),None)
                notes.append(f"rip=0x{rr['target']:X} sec={rr['target_section']}"+(f" object={obj}" if obj else ""))
        if ins.mnemonic=="call":
            if ins.operands and ins.operands[0].type==2:
                dest=ins.operands[0].imm-pe.image_base
                tf=fn_for(con,dest)
                notes.append(f"direct=0x{dest:X}"+(f" fn=0x{tf['begin']:X}-0x{tf['end']:X}" if tf else ""))
            else:
                notes.append("INDIRECT_CALL")
        out.append({"rva":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str,"notes":notes})
    return out

def qwords(pe,start,count):
    out=[]
    for i in range(count):
        rva=start+i*8
        try:q=struct.unpack("<Q",pe.read(rva,8))[0]
        except Exception:break
        pi=pe.ptr_info(q)
        out.append({"rva":rva,"value":q,"pointer":pi})
    return out

def ascii_near(pe,start,end):
    b=pe.read(start,end-start)
    found=[];i=0
    while i<len(b):
        if 32<=b[i]<127:
            j=i
            while j<len(b) and 32<=b[j]<127:j+=1
            if j-i>=4:
                found.append({"rva":start+i,"text":b[i:j].decode("ascii","replace")})
            i=j+1
        else:i+=1
    return found

def classify_table(entries):
    ptrs=[e for e in entries if e["pointer"]]
    text=[e for e in ptrs if e["pointer"]["section"]==".text"]
    rdata=[e for e in ptrs if e["pointer"]["section"]==".rdata"]
    if len(text)>=3 and len(text)>=len(entries[:12])//2:return "probable_vftable_or_function_table"
    if rdata and not text:return "probable_descriptor_table"
    if ptrs:return "mixed_pointer_structure"
    return "opaque_data"

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

    objs={}
    for name,addr in OBJECTS.items():
        before=qwords(pe,addr-0x40,8)
        at=qwords(pe,addr,24)
        exact=rows(con.execute("SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",(addr,)))
        near=rows(con.execute("SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target BETWEEN ? AND ? ORDER BY target,site",(addr-0x40,addr+0x100)))
        for r in exact:
            r["owner_function"]=fn_for(con,r["site"])
        for r in near:
            r["owner_function"]=fn_for(con,r["site"])
        # identify possible COL at slot -1 if absolute pointer into rdata
        col=None
        prev=before[-1] if before else None
        if prev and prev["pointer"] and prev["pointer"]["section"]==".rdata":
            col_rva=prev["pointer"]["rva"]
            try:
                raw=pe.read(col_rva,0x40)
                col={"rva":col_rva,"hex":raw.hex(),"ascii":ascii_near(pe,max(0,col_rva-0x40),col_rva+0x100)}
            except Exception:pass
        objs[name]={
            "address":addr,
            "classification":classify_table(at),
            "qwords_before":before,
            "qwords_at":at,
            "exact_xrefs":exact,
            "near_xrefs":near,
            "possible_col":col,
            "ascii_near":ascii_near(pe,addr-0x100,addr+0x180),
        }

    focus={}
    seen=set()
    for addr in FOCUS:
        f=fn_for(con,addr)
        if not f or f["begin"] in seen:continue
        seen.add(f["begin"])
        ins=disasm(md,pe,con,f) if f["size"]<=0x8000 else []
        focus[f"0x{f['begin']:X}"]={
            "function":f,
            "callers":rows(con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(f["begin"],))),
            "callees":rows(con.execute("SELECT site,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(f["begin"],))),
            "rip_refs":rows(con.execute("SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE src_fn=? ORDER BY site",(f["begin"],))),
            "indirect_calls":[x for x in ins if "INDIRECT_CALL" in x["notes"]],
            "instructions":ins,
        }

    # Cross-reference all .text qword entries in the shared structures to indexed functions.
    table_functions=[]
    for oname,o in objs.items():
        for e in o["qwords_at"]:
            pi=e["pointer"]
            if pi and pi["section"]==".text":
                tf=fn_for(con,pi["rva"])
                table_functions.append({"object":oname,"slot_rva":e["rva"],"target_rva":pi["rva"],"function":tf})

    result={
        "schema":1,"analysis":"shared_rdata_restore_bridge",
        "exe_sha256":actual,"image_base":pe.image_base,
        "objects":objs,"focus":focus,"table_functions":table_functions,
        "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"save_written":False,"progression_written":False}
    }
    con.close()
    Path(a.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    L=["Completionist Map - shared rdata checkpoint/restore bridge",f"exe_sha256={actual}","mode=static read-only",""]
    for name,o in objs.items():
        L.append(f"OBJECT {name} addr=0x{o['address']:X} class={o['classification']}")
        L.append("  QWORDS BEFORE")
        for e in o["qwords_before"]:
            p=e["pointer"]
            ps=(f" -> {p['kind']} 0x{p['rva']:X} {p['section']}" if p else "")
            L.append(f"    0x{e['rva']:X}: 0x{e['value']:016X}{ps}")
        L.append("  QWORDS AT")
        for e in o["qwords_at"]:
            p=e["pointer"]
            ps=(f" -> {p['kind']} 0x{p['rva']:X} {p['section']}" if p else "")
            L.append(f"    0x{e['rva']:X}: 0x{e['value']:016X}{ps}")
        L.append(f"  EXACT_XREFS {len(o['exact_xrefs'])}")
        for r in o["exact_xrefs"]:
            f=r["owner_function"];owner=f"0x{f['begin']:X}-0x{f['end']:X}" if f else "unknown"
            L.append(f"    0x{r['site']:X} owner={owner} {r['mnemonic']}")
        if o["possible_col"]:
            L.append(f"  POSSIBLE_COL rva=0x{o['possible_col']['rva']:X}")
        for s in o["ascii_near"][:20]:L.append(f"  ASCII 0x{s['rva']:X} {s['text']!r}")
        L.append("")
    L.append("TABLE TEXT POINTERS")
    for t in table_functions:
        f=t["function"]
        fs=f" fn=0x{f['begin']:X}-0x{f['end']:X}" if f else ""
        L.append(f"  {t['object']} slot=0x{t['slot_rva']:X} -> 0x{t['target_rva']:X}{fs}")
    L.append("")
    for key,d in focus.items():
        f=d["function"]
        L.append(f"FOCUS {key} range=0x{f['begin']:X}-0x{f['end']:X} size={f['size']}")
        for r in d["rip_refs"]:
            if r["target_string"] is not None:L.append(f"  STR 0x{r['site']:X} {r['target_string']!r}")
            elif r["target"] in OBJECTS.values():L.append(f"  SHARED 0x{r['site']:X} -> 0x{r['target']:X}")
        for ic in d["indirect_calls"]:L.append(f"  INDIRECT 0x{ic['rva']:X}: {ic['op_str']}")
        for c in d["callees"][:100]:
            t=c["target_fn"] if c["target_fn"] is not None else c["dest"]
            L.append(f"  CALLEE 0x{c['site']:X} -> 0x{t:X}")
        L.append("")
    Path(a.output_text).write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"SHARED_RDATA_RESTORE_BRIDGE_COMPLETE objects={len(objs)} focus={len(focus)} table_functions={len(table_functions)}")

if __name__=="__main__":
    main()
