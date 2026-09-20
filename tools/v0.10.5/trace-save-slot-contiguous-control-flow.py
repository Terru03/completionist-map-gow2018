#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
RANGES=[
    ("load_slot_contiguous",0x66CB30,0x66D800),
    ("get_current_slot_handler",0x769110,0x769180),
]
GLOBALS={
    "ui_selected_slot":0x11BDB5C,
    "native_load_slot":0x1078F4C,
    "load_state_flag":0x2D375C6,
    "load_state_reset":0x2D3755E,
}
KNOWN={
    0x5AEC9E:"restore_caller_a",0x5B2280:"restore_caller_b",0x7E9550:"restore_root",
    0x7E7660:"carrier_descriptor",0x7E7B60:"record_dispatch",0x7E9190:"userdata_serializer",
    0x9C6480:"decompress",0x66CB30:"load_physical_slot",
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
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def raw_disasm(md,pe,con,start,end):
    out=[]
    code=pe.read(start,end-start)
    for ins in md.disasm(code,pe.image_base+start):
        rva=ins.address-pe.image_base
        notes=[]
        refs=rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,)))
        for r in refs:
            if r["target_string"] is not None: notes.append("str="+repr(r["target_string"]))
            else:
                label=next((k for k,v in GLOBALS.items() if v==r["target"]),None)
                notes.append(f"rip=0x{r['target']:X} sec={r['target_section']}"+(f" global={label}" if label else ""))
        if ins.mnemonic.startswith("j") or ins.mnemonic=="call":
            if ins.operands and ins.operands[0].type==2:
                dest=ins.operands[0].imm-pe.image_base
                lab=KNOWN.get(dest)
                f=fn_for(con,dest)
                s=f"target=0x{dest:X}"
                if lab: s+=f" known={lab}"
                if f: s+=f" fn=0x{f['begin']:X}-0x{f['end']:X}"
                notes.append(s)
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

    global_xrefs={}
    for name,target in GLOBALS.items():
        global_xrefs[name]={
            "target":target,
            "rip_refs":rows(con.execute("SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",(target,))),
            "immediate_refs":rows(con.execute("SELECT site,src_fn,mnemonic,imm FROM immediate_refs WHERE imm=? ORDER BY site",(target,))) if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='immediate_refs'").fetchone() else [],
        }
        for r in global_xrefs[name]["rip_refs"]:
            r["owner_function"]=fn_for(con,r["site"])

    ranges={}
    for name,start,end in RANGES:
        ranges[name]={"start":start,"end":end,"instructions":raw_disasm(md,pe,con,start,end)}

    # List indexed function starts overlapping the contiguous load range, useful when boundaries are wrong.
    overlaps=rows(con.execute("SELECT begin,end,size,section FROM functions WHERE begin<? AND end>? ORDER BY begin",(0x66D800,0x66CB30)))

    result={
        "schema":1,"analysis":"save_slot_contiguous_control_flow","exe_sha256":actual,
        "globals":global_xrefs,"ranges":ranges,"indexed_overlaps":overlaps,
        "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"save_written":False,"progression_written":False}
    }
    con.close()
    Path(a.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    L=["Completionist Map - save-slot contiguous control flow",f"exe_sha256={actual}","mode=static read-only",""]
    L.append("GLOBAL XREFS")
    for name,g in global_xrefs.items():
        L.append(f"{name} 0x{g['target']:X}: rip_refs={len(g['rip_refs'])}")
        for r in g["rip_refs"]:
            f=r["owner_function"]
            owner=f"0x{f['begin']:X}-0x{f['end']:X}" if f else "unknown"
            L.append(f"  site=0x{r['site']:X} owner={owner} {r['mnemonic']}")
    L.append("")
    L.append("INDEXED FUNCTIONS OVERLAPPING 0x66CB30-0x66D800")
    for f in overlaps: L.append(f"  0x{f['begin']:X}-0x{f['end']:X} size={f['size']}")
    L.append("")
    for name,r in ranges.items():
        L.append(f"RAW RANGE {name} 0x{r['start']:X}-0x{r['end']:X}")
        for ins in r["instructions"]:
            note=(" ; "+"; ".join(ins["notes"])) if ins["notes"] else ""
            L.append(f"  0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{note}")
        L.append("")
    Path(a.output_text).write_text("\n".join(L)+"\n",encoding="utf-8")
    print("SAVE_SLOT_CONTIGUOUS_CONTROL_FLOW_COMPLETE")

if __name__=="__main__":
    main()
