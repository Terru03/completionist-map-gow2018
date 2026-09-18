#!/usr/bin/env python3
"""Discover the LuaClient vtable family and trace +0x70/+0x78 field provenance.

Static, read-only, version-locked analysis for God of War (2018).

The previous pass proved that +0x70/+0x78 are real LuaClient-owned heap buffers,
but only started from one one-slot interface vtable. This pass:
  1. finds every function that references the known LuaClient interface vtable
     at RVA 0xE04018;
  2. discovers sibling vtables assigned by those constructor/destructor sites;
  3. enumerates methods from that whole vtable family;
  4. propagates both the LuaClient root pointer and addresses of fields within
     it through direct helper calls;
  5. reports only accesses proven to resolve to root+0x70 or root+0x78.

No game launch, process access, save access, patching, or progression writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import struct
import sys
from collections import deque
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
KNOWN_VTABLE=0xE04018
TARGETS={0x70,0x78}
ARG_REGS=("rcx","rdx","r8","r9")
VOLATILE={"rax","rcx","rdx","r8","r9","r10","r11"}
MAX_DEPTH=5
MAX_STATES=1600
MAX_FN_SIZE=0x7000
MAX_VTABLE_SLOTS=160
MAX_ROOT_OFFSET=0x400

REG_CANON={
    "al":"rax","ah":"rax","ax":"rax","eax":"rax","rax":"rax",
    "bl":"rbx","bh":"rbx","bx":"rbx","ebx":"rbx","rbx":"rbx",
    "cl":"rcx","ch":"rcx","cx":"rcx","ecx":"rcx","rcx":"rcx",
    "dl":"rdx","dh":"rdx","dx":"rdx","edx":"rdx","rdx":"rdx",
    "sil":"rsi","si":"rsi","esi":"rsi","rsi":"rsi",
    "dil":"rdi","di":"rdi","edi":"rdi","rdi":"rdi",
    "bpl":"rbp","bp":"rbp","ebp":"rbp","rbp":"rbp",
    "spl":"rsp","sp":"rsp","esp":"rsp","rsp":"rsp",
}
for n in range(8,16):
    for suffix in ("b","w","d",""):
        REG_CANON[f"r{n}{suffix}"]=f"r{n}"

def canon(s):
    return REG_CANON.get(s,s) if s else None

def sha256(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("gow_luaclient_family_pe",p)
    if not spec or not spec.loader:raise RuntimeError("PE helper load failed")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def load_cs():
    root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
    if root.is_dir():sys.path.insert(0,str(root))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_READ,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_READ,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP

def fn_for(con,rva):
    row=con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? "
        "ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
    return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def all_functions(con):
    for row in con.execute("SELECT begin,end,size,section FROM functions ORDER BY begin"):
        yield {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def incoming(con,fn,limit=50):
    rows=con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site LIMIT ?",
        (fn,limit)).fetchall()
    return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]}
            for r in rows if r[1] is not None and r[1]!=fn]

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

def ptr_at(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]

def plausible_vtable(pe,con,rva):
    good=0
    for i in range(3):
        va=ptr_at(pe,rva+8*i)
        if va is None:break
        tr=va-IMAGE_BASE if IMAGE_BASE<=va<IMAGE_BASE+pe.size_of_image else None
        if tr is not None and fn_for(con,tr):good+=1
        else:break
    return good>=1

def enum_vtable(pe,con,rva):
    rows=[];bad=0;started=False
    for slot in range(MAX_VTABLE_SLOTS):
        va=ptr_at(pe,rva+8*slot)
        tr=va-IMAGE_BASE if va is not None and IMAGE_BASE<=va<IMAGE_BASE+pe.size_of_image else None
        meta=fn_for(con,tr) if tr is not None else None
        if meta:
            started=True;bad=0
            rows.append({"slot":slot,"entry_rva":rva+8*slot,"target_rva":tr,
                         "function":meta["begin"],"size":meta["size"]})
        else:
            bad+=1
            if started and bad>=4:break
            if not started:break
    return rows

def disasm_fn(pe,md,fn):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    return list(md.disasm(pe.data[off:off+fn["size"]],IMAGE_BASE+fn["begin"]))

def discover_anchor_functions(pe,con,md,X86_OP_MEM,X86_REG_RIP):
    out=[]
    for fn in all_functions(con):
        if fn["size"]<=0 or fn["size"]>MAX_FN_SIZE:continue
        for ins in disasm_fn(pe,md,fn):
            try:ops=list(ins.operands)
            except Exception:ops=[]
            found=False
            for op in ops:
                if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                    target=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
                    if target==KNOWN_VTABLE:
                        found=True;break
            if found:
                out.append({"function":fn,"site":ins.address-IMAGE_BASE,
                            "instruction":f"{ins.mnemonic} {ins.op_str}"})
                break
    return out

def discover_family(pe,con,md,anchors,X86_OP_MEM,X86_OP_REG,X86_REG_RIP):
    candidates={KNOWN_VTABLE:{"source":"known","refs":[],"root_offsets":set()}}
    anchor_details=[]
    for a in anchors:
        refs=[]; assignments=[]
        fn=a["function"]
        objprov={"rcx":0}
        vtreg={}
        for ins in disasm_fn(pe,md,fn):
            try:ops=list(ins.operands)
            except Exception:ops=[]

            # Record a proven vtable store before updating register provenance.
            if (ins.mnemonic=="mov" and len(ops)>=2 and
                ops[0].type==X86_OP_MEM and ops[1].type==X86_OP_REG):
                base=canon(md.reg_name(ops[0].mem.base)) if ops[0].mem.base else None
                idx=canon(md.reg_name(ops[0].mem.index)) if ops[0].mem.index else None
                src=canon(md.reg_name(ops[1].reg))
                if base in objprov and not idx and src in vtreg:
                    vt=vtreg[src]
                    root_off=objprov[base]+int(ops[0].mem.disp)
                    assignments.append({"site":ins.address-IMAGE_BASE,"rva":vt,
                                        "root_offset":root_off,
                                        "instruction":f"{ins.mnemonic} {ins.op_str}"})
                    candidates.setdefault(vt,{"source":f"anchor_0x{fn['begin']:X}",
                                              "refs":[],"root_offsets":set()})
                    candidates[vt]["root_offsets"].add(root_off)

            # Discover RIP-relative vtable candidates.
            for op in ops:
                if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                    target=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
                    if 0<=target<pe.size_of_image and plausible_vtable(pe,con,target):
                        refs.append({"site":ins.address-IMAGE_BASE,"rva":target,
                                     "instruction":f"{ins.mnemonic} {ins.op_str}"})
                        candidates.setdefault(target,{"source":f"anchor_0x{fn['begin']:X}",
                                                      "refs":[],"root_offsets":set()})
                        candidates[target]["refs"].append(
                            {"function":fn["begin"],"site":ins.address-IMAGE_BASE})

            # Track object-pointer and vtable-address registers.
            if len(ops)>=2 and ops[0].type==X86_OP_REG:
                dst=canon(md.reg_name(ops[0].reg))
                if ins.mnemonic=="mov" and ops[1].type==X86_OP_REG:
                    src=canon(md.reg_name(ops[1].reg))
                    if src in objprov:objprov[dst]=objprov[src]
                    else:objprov.pop(dst,None)
                    if src in vtreg:vtreg[dst]=vtreg[src]
                    else:vtreg.pop(dst,None)
                elif ins.mnemonic=="lea" and ops[1].type==X86_OP_MEM:
                    if ops[1].mem.base==X86_REG_RIP:
                        target=ins.address+ins.size+int(ops[1].mem.disp)-IMAGE_BASE
                        if 0<=target<pe.size_of_image and plausible_vtable(pe,con,target):
                            vtreg[dst]=target
                        else:
                            vtreg.pop(dst,None)
                        objprov.pop(dst,None)
                    else:
                        base=canon(md.reg_name(ops[1].mem.base)) if ops[1].mem.base else None
                        idx=canon(md.reg_name(ops[1].mem.index)) if ops[1].mem.index else None
                        if base in objprov and not idx:
                            objprov[dst]=objprov[base]+int(ops[1].mem.disp)
                        else:
                            objprov.pop(dst,None)
                        vtreg.pop(dst,None)
                elif ins.mnemonic not in ("cmp","test"):
                    objprov.pop(dst,None);vtreg.pop(dst,None)
            if ins.mnemonic=="call":
                for rr in VOLATILE:
                    objprov.pop(rr,None);vtreg.pop(rr,None)

        anchor_details.append({**a,"candidate_vtables":refs,"vtable_assignments":assignments})

    filtered={}
    for rva,v in candidates.items():
        near=abs(rva-KNOWN_VTABLE)<=0x20000
        referenced=(rva==KNOWN_VTABLE or len(v["refs"])>=1 or len(v["root_offsets"])>=1)
        if near and referenced:
            slots=enum_vtable(pe,con,rva)
            if slots:
                offsets=sorted(v["root_offsets"])
                if rva==KNOWN_VTABLE and not offsets:
                    offsets=[0]
                filtered[rva]={"source":v["source"],"refs":v["refs"],
                               "root_offsets":offsets,"slots":slots}
    return filtered,anchor_details

def rname(md,r):return canon(md.reg_name(r)) if r else None

def analyse_state(pe,con,md,consts,fnmeta,seedreg,seedoff,depth,path):
    CS_AC_READ,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP=consts
    insns=disasm_fn(pe,md,fnmeta)
    prov={seedreg:seedoff}
    hits=[];calls=[];strings=[]
    for ins in insns:
        rva=ins.address-IMAGE_BASE
        try:ops=list(ins.operands)
        except Exception:ops=[]

        for oi,op in enumerate(ops):
            if op.type!=X86_OP_MEM:continue
            if op.mem.base==X86_REG_RIP:
                t=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
                s=ascii_at(pe,t)
                if s:strings.append({"site":rva,"target":t,"string":s})
                continue
            base=rname(md,op.mem.base);idx=rname(md,op.mem.index)
            if base in prov and not idx:
                eff=prov[base]+int(op.mem.disp)
                if eff in TARGETS:
                    access=int(getattr(op,"access",0))
                    inferred_write=oi==0 and ins.mnemonic in {
                        "mov","add","sub","and","or","xor","inc","dec","xchg","cmpxchg"
                    }
                    wr=bool(access&CS_AC_WRITE) or inferred_write
                    rd=bool(access&CS_AC_READ)
                    kind="readwrite" if wr and rd else ("write" if wr else "read")
                    hits.append({
                        "site":rva,"field":eff,"kind":kind,
                        "instruction":f"{ins.mnemonic} {ins.op_str}",
                        "base_register":base,"base_offset":prov[base],
                        "memory_disp":int(op.mem.disp)
                    })

        if ins.mnemonic=="call" and ops and ops[0].type==X86_OP_IMM:
            va=int(ops[0].imm)
            if IMAGE_BASE<=va<IMAGE_BASE+pe.size_of_image:
                tr=va-IMAGE_BASE;meta=fn_for(con,tr)
                if meta and meta["size"]<=MAX_FN_SIZE:
                    args=[]
                    for ar in ARG_REGS:
                        if ar in prov and -MAX_ROOT_OFFSET<=prov[ar]<=MAX_ROOT_OFFSET:
                            args.append({"reg":ar,"offset":prov[ar]})
                    if args:calls.append({"site":rva,"target":meta["begin"],"args":args})

        # provenance update after examining current memory operands/call args
        if len(ops)>=2 and ops[0].type==X86_OP_REG:
            dst=rname(md,ops[0].reg)
            if dst:
                done=False
                if ins.mnemonic=="mov" and ops[1].type==X86_OP_REG:
                    src=rname(md,ops[1].reg)
                    if src in prov:prov[dst]=prov[src]
                    else:prov.pop(dst,None)
                    done=True
                elif ins.mnemonic=="lea" and ops[1].type==X86_OP_MEM:
                    base=rname(md,ops[1].mem.base);idx=rname(md,ops[1].mem.index)
                    if base in prov and not idx:
                        prov[dst]=prov[base]+int(ops[1].mem.disp)
                    else:prov.pop(dst,None)
                    done=True
                elif ins.mnemonic in ("add","sub") and ops[1].type==X86_OP_IMM and dst in prov:
                    d=int(ops[1].imm);prov[dst]+=d if ins.mnemonic=="add" else -d;done=True
                if not done and ins.mnemonic not in ("cmp","test"):
                    prov.pop(dst,None)
        elif ops and ops[0].type==X86_OP_REG:
            dst=rname(md,ops[0].reg)
            if dst and ins.mnemonic not in ("cmp","test","push"):
                prov.pop(dst,None)

        if ins.mnemonic=="call":
            for rr in VOLATILE:prov.pop(rr,None)

    slim=[{"rva":i.address-IMAGE_BASE,"hex":i.bytes.hex(),
           "mnemonic":i.mnemonic,"op_str":i.op_str} for i in insns]
    return {"function":fnmeta,"seed_register":seedreg,"seed_offset":seedoff,
            "depth":depth,"path":path,"hits":hits,"calls":calls,
            "strings":strings,"instructions":slim}

def snippet(insns,site,radius=9):
    ix=next((i for i,x in enumerate(insns) if x["rva"]==site),None)
    if ix is None:return []
    return insns[max(0,ix-radius):min(len(insns),ix+radius+1)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    actual=sha256(a.exe)
    if actual!=EXPECTED:raise RuntimeError(f"unsupported GoW.exe sha256={actual}")

    peh=load_pe();pe=peh.PE(a.exe.read_bytes())
    Cs,arch,mode,CS_AC_READ,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP=load_cs()
    md=Cs(arch,mode);md.detail=True
    consts=(CS_AC_READ,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP)

    con=sqlite3.connect(a.db)
    try:
        anchors=discover_anchor_functions(pe,con,md,X86_OP_MEM,X86_REG_RIP)
        family,anchor_details=discover_family(pe,con,md,anchors,X86_OP_MEM,X86_OP_REG,X86_REG_RIP)
        if not family:raise RuntimeError("no LuaClient vtable family discovered")

        queue=deque();best={}
        for vt,info in family.items():
            offsets=info.get("root_offsets") or ([0] if vt==KNOWN_VTABLE else [])
            for root_off in offsets:
                for slot in info["slots"]:
                    key=(slot["function"],"rcx",root_off)
                    if key not in best:
                        best[key]=0
                        queue.append((slot["function"],"rcx",root_off,0,
                            [f"vtable_0x{vt:X}@root{root_off:+#x}[{slot['slot']}]=>0x{slot['function']:X}"]))

        states=[];hits=[]
        while queue and len(states)<MAX_STATES:
            fn,reg,off,depth,path=queue.popleft()
            meta=fn_for(con,fn)
            if not meta or meta["size"]>MAX_FN_SIZE:continue
            st=analyse_state(pe,con,md,consts,meta,reg,off,depth,path)
            states.append(st)
            for h in st["hits"]:
                hits.append({**h,"function":fn,"seed_register":reg,"seed_offset":off,
                             "depth":depth,"path":path,"strings":st["strings"][:25],
                             "incoming":incoming(con,fn,25),
                             "snippet":snippet(st["instructions"],h["site"])})
            if depth>=MAX_DEPTH:continue
            for c in st["calls"]:
                for ar in c["args"]:
                    k=(c["target"],ar["reg"],ar["offset"]);nd=depth+1
                    if k in best and best[k]<=nd:continue
                    best[k]=nd
                    queue.append((c["target"],ar["reg"],ar["offset"],nd,
                        path+[f"0x{fn:X}@0x{c['site']:X}->{ar['reg']}({ar['offset']:+#x}):0x{c['target']:X}"]))

        hits.sort(key=lambda h:(h["field"],h["kind"],h["depth"],h["function"],h["site"]))
        writes=[h for h in hits if h["kind"] in ("write","readwrite")]
        indirect=[h for h in hits if h["seed_offset"] in TARGETS or h["base_offset"] in TARGETS]

        out={
            "schema":1,"analysis":"luaclient_vtable_family_field_address_lineage",
            "exe_sha256":EXPECTED,"known_vtable_rva":KNOWN_VTABLE,
            "anchor_functions":anchor_details,
            "vtable_family":{f"0x{k:X}":v for k,v in family.items()},
            "states_analysed":len(states),"state_limit_hit":len(states)>=MAX_STATES,
            "hits":hits,
            "summary":{"anchors":len(anchors),"vtables":len(family),
                       "methods":sum(len(v["slots"]) for v in family.values()),
                       "states":len(states),"hits":len(hits),"writes":len(writes),
                       "indirect_field_address_hits":len(indirect)},
            "safety":{"static_pe_only":True,"game_launched":False,"process_opened":False,
                      "save_opened":False,"exe_modified":False,"save_modified":False,
                      "progression_written":False}
        }
        a.output_json.parent.mkdir(parents=True,exist_ok=True)
        a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

        lines=[
            "Completionist Map - LuaClient vtable-family + field-address lineage",
            f"exe_sha256={EXPECTED}",
            f"known_vtable_rva=0x{KNOWN_VTABLE:X}",
            f"anchors={len(anchors)} vtables={len(family)} methods={out['summary']['methods']} states={len(states)} hits={len(hits)} writes={len(writes)} indirect={len(indirect)}",
            "game_launched=false process_opened=false save_opened=false exe_modified=false save_modified=false progression_written=false",
            "","ANCHORS"
        ]
        for a0 in anchor_details:
            lines.append(f"  fn=0x{a0['function']['begin']:X} site=0x{a0['site']:X} {a0['instruction']}")
            for vr in a0["candidate_vtables"]:
                lines.append(f"    candidate_vtable=0x{vr['rva']:X} site=0x{vr['site']:X} {vr['instruction']}")
        lines+=["","VTABLE_FAMILY"]
        for vt,info in sorted(family.items()):
            lines.append(f"  VTABLE 0x{vt:X} slots={len(info['slots'])} root_offsets={info.get('root_offsets',[])} source={info['source']}")
            for s in info["slots"]:
                lines.append(f"    slot={s['slot']:03d} fn=0x{s['function']:X} size=0x{s['size']:X}")
        lines+=["","FIELD_HITS"]
        if not hits:lines.append("  NONE")
        for h in hits:
            lines.append(
                f"  {h['kind'].upper()} field=0x{h['field']:X} fn=0x{h['function']:X} "
                f"site=0x{h['site']:X} depth={h['depth']} seed={h['seed_register']}({h['seed_offset']:+#x}) "
                f"base={h['base_register']}({h['base_offset']:+#x}) disp={h['memory_disp']:+#x} "
                f"op={h['instruction']}")
            lines.append("    path="+" | ".join(h["path"]))
            for s in h.get("strings",[])[:6]:
                lines.append(f"    string@0x{s['site']:X}={s['string']!r}")
            lines.append("    snippet:")
            for i in h["snippet"]:
                mark=">>" if i["rva"]==h["site"] else "  "
                lines.append(f"      {mark} 0x{i['rva']:X}: {i['hex']:<24} {i['mnemonic']} {i['op_str']}")
        a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

        print("LUACLIENT_VTABLE_FAMILY_FIELD_LINEAGE_COMPLETE "
              f"anchors={len(anchors)} vtables={len(family)} methods={out['summary']['methods']} "
              f"states={len(states)} hits={len(hits)} writes={len(writes)} indirect={len(indirect)}")
        for h in writes[:80]:
            print(f"WRITE field=0x{h['field']:X} fn=0x{h['function']:X} site=0x{h['site']:X} "
                  f"depth={h['depth']} seed={h['seed_register']}({h['seed_offset']:+#x}) "
                  f"op={h['instruction']}")
        if not writes:print("WRITE NONE")
        return 0
    finally:
        con.close()

if __name__=="__main__":
    raise SystemExit(main())
