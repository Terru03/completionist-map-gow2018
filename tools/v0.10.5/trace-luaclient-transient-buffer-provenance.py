#!/usr/bin/env python3
"""Trace provenance of GoW's transient LuaClient/checkpoint pickle buffers.

Static, read-only, version-locked analysis.

Focus:
- checkpoint table builder 0x5AF01C
- previous-soft-state merge 0x5AF4E0
- LuaClient save/restore 0x5B2130/0x5B2171/0x5B2280/0x5B2324
- direct callers of 0x5AF01C and 0x5AF4E0
- one caller hop above 0x5AF01C

For each function, dump only:
- full disassembly for these small selected functions;
- memory operands at +0x58/+0x60/+0x68/+0x70/+0x78;
- incoming/outgoing direct edges;
- simple entry-this register provenance (rcx-derived register copies).

No game launch, process access, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
SEEDS=[0x5AF01C,0x5AF4E0,0x5B2130,0x5B2171,0x5B2280,0x5B2324]
INTEREST={0x58,0x60,0x68,0x70,0x78}

def sha256(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    s=importlib.util.spec_from_file_location("gow_bufprov_pe",p)
    if not s or not s.loader: raise RuntimeError("PE helper load failed")
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def load_cs():
    root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
    if root.is_dir(): sys.path.insert(0,str(root))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP

def fn_for(con,rva):
    row=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
    return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def incoming(con,fn):
    rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(fn,)).fetchall()
    return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]} for r in rows if r[1] is not None and r[1]!=fn]

def outgoing(con,fn):
    rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(fn,)).fetchall()
    return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]} for r in rows if r[4] is not None and r[4]!=fn]

def ascii_at(pe,rva,maxlen=160):
    off=pe.rva_to_file(rva)
    if off is None:return None
    out=[]
    for b in pe.data[off:off+maxlen]:
        if b==0:break
        if 32<=b<=126:out.append(chr(b))
        else:return None
    s="".join(out)
    return s if len(s)>=4 else None

def reg_name(md,r):
    return md.reg_name(r) if r else None

def disasm(pe,md,fn,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return {}
    data=pe.data[off:off+fn["size"]]
    rows=[]; mem=[]; strings=[]; calls=[]
    # very small forward provenance: registers definitely copied from entry rcx
    # until overwritten. Good enough to distinguish [rsp+0x70] from [this+0x70].
    derived={"rcx":"entry_rcx"}
    for ins in md.disasm(data,IMAGE_BASE+fn["begin"]):
        rva=ins.address-IMAGE_BASE
        row={"rva":rva,"hex":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str}
        try: ops=list(ins.operands)
        except Exception: ops=[]
        annotations=[]
        # annotate memory operands before updating register provenance
        for oi,op in enumerate(ops):
            if op.type==X86_OP_MEM:
                base=reg_name(md,op.mem.base)
                disp=int(op.mem.disp)
                item={"site":rva,"operand":oi,"base":base,"disp":disp,"access":int(getattr(op,"access",0)),
                      "instruction":f"{ins.mnemonic} {ins.op_str}","base_provenance":derived.get(base)}
                if op.mem.base==X86_REG_RIP:
                    target=ins.address+ins.size+disp-IMAGE_BASE
                    st=ascii_at(pe,target)
                    if st: strings.append({"site":rva,"target":target,"string":st})
                elif disp in INTEREST or (base=="rsp" and disp in INTEREST):
                    mem.append(item)
                    annotations.append(f"mem[{base}+0x{disp:X}] prov={derived.get(base)}")
            elif op.type==X86_OP_IMM and ins.mnemonic in ("call","jmp"):
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:
                    calls.append({"site":rva,"kind":ins.mnemonic,"dest":v-IMAGE_BASE})
        if annotations: row["annotations"]=annotations
        rows.append(row)

        # Update simple provenance after instruction.
        if len(ops)>=2 and ops[0].type==X86_OP_REG:
            dst=reg_name(md,ops[0].reg)
            if ins.mnemonic=="mov" and ops[1].type==X86_OP_REG:
                src=reg_name(md,ops[1].reg)
                if src in derived: derived[dst]=derived[src]
                else: derived.pop(dst,None)
            elif ins.mnemonic=="lea" and ops[1].type==X86_OP_MEM and op.mem.disp==0:
                base=reg_name(md,ops[1].mem.base)
                if base in derived: derived[dst]=derived[base]
                else: derived.pop(dst,None)
            elif ins.mnemonic not in ("cmp","test"):
                derived.pop(dst,None)
        # calls clobber volatile rcx/rdx/r8/r9/rax
        if ins.mnemonic=="call":
            for rr in ("rax","rcx","rdx","r8","r9","r10","r11"): derived.pop(rr,None)

    return {"instructions":rows,"interesting_mem":mem,"strings":strings,"calls":calls}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sha256(a.exe)!=EXPECTED: raise RuntimeError("unsupported GoW.exe")
    peh=load_pe(); pe=peh.PE(a.exe.read_bytes())
    Cs,arch,mode,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP=load_cs()
    md=Cs(arch,mode); md.detail=True
    con=sqlite3.connect(a.db)
    try:
        selected=set()
        seed_fns={}
        for rva in SEEDS:
            fn=fn_for(con,rva)
            if not fn: raise RuntimeError(f"missing function for 0x{rva:X}")
            seed_fns[fn["begin"]]=f"seed_0x{rva:X}"
            selected.add(fn["begin"])

        checkpoint_fn=fn_for(con,0x5AF01C)["begin"]
        prev_fn=fn_for(con,0x5AF4E0)["begin"]
        caller1=set()
        for target in (checkpoint_fn,prev_fn):
            for e in incoming(con,target):
                caller1.add(e["src_fn"]); selected.add(e["src_fn"])
        caller2=set()
        for target in [checkpoint_fn]:
            for e in incoming(con,target):
                for e2 in incoming(con,e["src_fn"]):
                    caller2.add(e2["src_fn"]); selected.add(e2["src_fn"])

        reps={}
        for fnrva in sorted(selected):
            meta=fn_for(con,fnrva)
            if not meta:continue
            body=disasm(pe,md,meta,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP)
            tier="seed" if fnrva in seed_fns else ("caller1" if fnrva in caller1 else "caller2")
            reps[f"0x{fnrva:X}"]={
                "tier":tier,"function":meta,
                "incoming":incoming(con,fnrva),"outgoing":outgoing(con,fnrva),
                **body
            }

        out={
            "schema":1,"analysis":"luaclient_transient_pickle_buffer_provenance",
            "exe_sha256":EXPECTED,
            "seeds":[f"0x{x:X}" for x in SEEDS],
            "functions":reps,
            "safety":{"static_pe_only":True,"game_launched":False,"process_opened":False,
                      "save_opened":False,"exe_modified":False}
        }
        a.output_json.parent.mkdir(parents=True,exist_ok=True)
        a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

        lines=[
            "Completionist Map - LuaClient transient pickle-buffer provenance",
            f"exe_sha256={EXPECTED}",
            "game_launched=false process_opened=false save_opened=false exe_modified=false",
            ""
        ]
        for k,v in reps.items():
            lines.append(f"FUNCTION {k} tier={v['tier']} size={v['function']['size']}")
            for s in v["strings"]: lines.append(f"  STRING 0x{s['site']:X} {s['string']!r}")
            for m in v["interesting_mem"]:
                lines.append(
                    f"  FIELD 0x{m['site']:X} base={m['base']} disp=0x{m['disp']:X} "
                    f"prov={m.get('base_provenance')} access={m['access']} {m['instruction']}"
                )
            lines.append("  INCOMING")
            for e in v["incoming"]:
                lines.append(f"    fn=0x{e['src_fn']:X} site=0x{e['site']:X} kind={e['kind']}")
            lines.append("  OUTGOING")
            for e in v["outgoing"]:
                lines.append(f"    site=0x{e['site']:X} dest=0x{e['target_fn']:X} kind={e['kind']}")
            lines.append("  DISASM")
            for ins in v["instructions"]:
                ann=" ; "+" | ".join(ins.get("annotations",[])) if ins.get("annotations") else ""
                lines.append(f"    0x{ins['rva']:X}: {ins['hex']:<24} {ins['mnemonic']} {ins['op_str']}{ann}")
            lines.append("")
        a.output_text.write_text("\n".join(lines),encoding="utf-8")
        print(f"TRANSIENT_PICKLE_BUFFER_PROVENANCE_COMPLETE functions={len(reps)}")
        for k,v in reps.items():
            interesting=[m for m in v["interesting_mem"] if m["disp"] in (0x70,0x78)]
            if interesting:
                print(f"TARGET {k} tier={v['tier']} hits={len(interesting)}")
                for m in interesting:
                    print(f"  site=0x{m['site']:X} base={m['base']} prov={m.get('base_provenance')} disp=0x{m['disp']:X} access={m['access']} op={m['instruction']}")
    finally:
        con.close()
    return 0

if __name__=="__main__": raise SystemExit(main())
