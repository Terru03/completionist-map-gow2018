#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, struct, sys
from pathlib import Path

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
NAMES = ["GetCurrentSlot","SetCurrentSlot","LoadSaveGame","LoadedIntoSaveSlot"]

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

class PE:
    def __init__(self,data:bytes):
        self.data=data
        if data[:2]!=b"MZ": raise ValueError("not MZ")
        peoff=struct.unpack_from("<I",data,0x3C)[0]
        if data[peoff:peoff+4]!=b"PE\0\0": raise ValueError("not PE")
        coff=peoff+4
        nsec=struct.unpack_from("<H",data,coff+2)[0]
        optsz=struct.unpack_from("<H",data,coff+16)[0]
        opt=coff+20
        magic=struct.unpack_from("<H",data,opt)[0]
        if magic!=0x20B: raise ValueError("expected PE32+")
        self.image_base=struct.unpack_from("<Q",data,opt+24)[0]
        sec=opt+optsz
        self.sections=[]
        for i in range(nsec):
            off=sec+i*40
            name=data[off:off+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize,vaddr,rsize,roff=struct.unpack_from("<IIII",data,off+8)
            self.sections.append((name,vaddr,vsize,rsize,roff))
    def rva_to_off(self,rva:int)->int:
        for name,vaddr,vsize,rsize,roff in self.sections:
            span=max(vsize,rsize)
            if vaddr <= rva < vaddr+span:
                return roff+(rva-vaddr)
        raise KeyError(hex(rva))
    def read_rva(self,rva:int,size:int)->bytes:
        off=self.rva_to_off(rva)
        return self.data[off:off+size]

def rows(cur):
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def fn_for(con,rva):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
    if not r: return None
    return {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def string_map(con):
    return {r[0]:r[1] for r in con.execute("SELECT rva,text FROM strings")}

def disasm_range(md,pe,con,smap,begin,end):
    code=pe.read_rva(begin,end-begin)
    out=[]
    for ins in md.disasm(code, pe.image_base+begin):
        rva=ins.address-pe.image_base
        note=[]
        if ins.mnemonic in ("call","jmp") and ins.operands and ins.operands[0].type==2:
            target=ins.operands[0].imm-pe.image_base
            note.append(f"target=0x{target:X}")
        for op in ins.operands:
            if op.type==3 and op.mem.base==md.reg_name(41): # may vary; fallback below handles name
                pass
        # generic RIP-relative annotation from operand strings via SQLite row
        refs=rows(con.execute("SELECT target,target_section,target_string FROM rip_refs WHERE site=?",(rva,)))
        for ref in refs:
            if ref["target_string"] is not None:
                note.append(f"str={ref['target_string']!r}")
            else:
                note.append(f"rip=0x{ref['target']:X} sec={ref['target_section']}")
        out.append({
            "rva":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str,
            "note":"; ".join(note)
        })
    return out

def nearby_handler_candidates(con,site):
    lo,hi=site-96,site+32
    refs=rows(con.execute(
        "SELECT site,mnemonic,target,target_section,target_string FROM rip_refs WHERE site BETWEEN ? AND ? ORDER BY site",
        (lo,hi)))
    cands=[]
    for r in refs:
        if r["target_section"]==".text":
            fn=fn_for(con,r["target"])
            if fn:
                cands.append({"xref":r,"function":fn})
    # de-dup by function begin preserving order
    seen=set(); out=[]
    for c in cands:
        b=c["function"]["begin"]
        if b in seen: continue
        seen.add(b); out.append(c)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",required=True)
    ap.add_argument("--db",required=True)
    ap.add_argument("--capstone-path",required=True)
    ap.add_argument("--output-json",required=True)
    ap.add_argument("--output-text",required=True)
    args=ap.parse_args()

    game_root=Path(args.game_root); exe=game_root/"GoW.exe"
    actual=sha256(exe).lower()
    if actual!=EXPECTED_SHA256: raise SystemExit(f"unsupported GoW.exe SHA256 {actual}")

    sys.path.insert(0,args.capstone_path)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True

    pe=PE(exe.read_bytes())
    con=sqlite3.connect(args.db)
    smap=string_map(con)

    exact={}
    handler_fns={}
    for name in NAMES:
        strings=rows(con.execute("SELECT rva,text FROM strings WHERE text=?",(name,)))
        refs=[]
        for s in strings:
            rr=rows(con.execute("SELECT site,src_fn,mnemonic,target,target_section,target_string FROM rip_refs WHERE target=? ORDER BY site",(s["rva"],)))
            for x in rr:
                x["owner_function"]=fn_for(con,x["src_fn"])
                x["nearby_text_candidates"]=nearby_handler_candidates(con,x["site"])
                for c in x["nearby_text_candidates"]:
                    handler_fns[c["function"]["begin"]]=c["function"]
            refs.extend(rr)
        exact[name]={"strings":strings,"refs":refs}

    # Proven loaded-slot path.
    for addr in (0x533E30,0x7698BF):
        f=fn_for(con,addr)
        if f: handler_fns[f["begin"]]=f

    disassembly={}
    for begin,f in sorted(handler_fns.items()):
        # Avoid absurdly large registration functions; cap to exact target function size.
        if f["size"]>0x4000:
            continue
        disassembly[f"0x{begin:X}"]={
            "function":f,
            "instructions":disasm_range(md,pe,con,smap,f["begin"],f["end"])
        }

    # Also dump tight registration neighborhoods around the four names.
    neighborhoods={}
    for name,data in exact.items():
        for i,r in enumerate(data["refs"]):
            b=max(r["site"]-96,0); e=r["site"]+80
            neighborhoods[f"{name}#{i+1}"]={
                "site":r["site"],
                "instructions":disasm_range(md,pe,con,smap,b,e)
            }

    result={
        "schema":1,
        "analysis":"current_slot_native_disassembly",
        "exe_sha256":actual,
        "image_base":pe.image_base,
        "exact":exact,
        "disassembly":disassembly,
        "registration_neighborhoods":neighborhoods,
        "safety":{
            "game_launched":False,"process_opened":False,"active_save_opened":False,
            "game_files_written":False,"save_written":False,"progression_written":False
        }
    }
    con.close()
    Path(args.output_json).write_text(json.dumps(result,indent=2),encoding="utf-8")

    lines=[
        "Completionist Map - current slot native disassembly",
        f"exe_sha256={actual}",
        "mode=static read-only",
        ""
    ]
    for name,data in exact.items():
        lines.append(f"NAME {name}")
        for r in data["refs"]:
            lines.append(f"  xref site=0x{r['site']:X} owner=0x{r['src_fn']:X}")
            for c in r["nearby_text_candidates"]:
                f=c["function"]
                lines.append(f"    candidate xref=0x{c['xref']['site']:X}->0x{c['xref']['target']:X} fn=0x{f['begin']:X}-0x{f['end']:X}")
    lines.append("")
    for key,n in neighborhoods.items():
        lines.append(f"REGISTRATION {key} site=0x{n['site']:X}")
        for ins in n["instructions"]:
            extra=(" ; "+ins["note"]) if ins["note"] else ""
            lines.append(f"  0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{extra}")
        lines.append("")
    for key,d in disassembly.items():
        f=d["function"]
        lines.append(f"FUNCTION {key} range=0x{f['begin']:X}-0x{f['end']:X}")
        for ins in d["instructions"]:
            extra=(" ; "+ins["note"]) if ins["note"] else ""
            lines.append(f"  0x{ins['rva']:X}: {ins['mnemonic']} {ins['op_str']}{extra}")
        lines.append("")
    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"CURRENT_SLOT_NATIVE_DISASSEMBLY_COMPLETE functions={len(disassembly)} neighborhoods={len(neighborhoods)}")

if __name__=="__main__":
    main()
