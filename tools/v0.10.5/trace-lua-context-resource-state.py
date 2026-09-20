#!/usr/bin/env python3
"""Trace LuaContext resource-state lookup at 0x464410 and nearby virtual methods.

Known:
- LuaContext vtable base: 0xDF2F50
- LuaContext::CreateClient-ish factory: vtable slot 0xDF2FB0 -> 0x4654A0
- LuaLevelClient factory branch:
    rbx = 0x464410(LuaContext, resource/context key)
    new LuaLevelClient(..., r9=rbx)
  This makes the 0x464410 return value a strong candidate for the per-resource
  backing/checkpoint state that can survive independently of a resident client.

This pass:
1. recursively disassembles real contiguous control flow from 0x464410 across
   PE runtime/unwind boundaries in a tight code window;
2. finds all direct executable xrefs to 0x464410;
3. dumps LuaContext vtable slots around 0xDF2F50, especially around the factory;
4. disassembles only nearby virtual methods that touch LuaContext+0x178/+0x188/
   +0x190 or call 0x464410.

Static/read-only, version locked.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
LOOKUP=0x464410
FACTORY=0x4654A0
VTABLE=0xDF2F50
WINDOW_START=0x464200
WINDOW_END=0x464800
OWNER_OFFSETS=(0x178,0x188,0x190)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_context_lookup_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]


def decode_one(pe,md,rva,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(rva)
    if off is None:return None
    insns=list(md.disasm(pe.data[off:off+15],IMAGE_BASE+rva,count=1))
    if not insns:return None
    ins=insns[0]
    mem=[];imms=[]
    for op in getattr(ins,"operands",[]):
        if op.type==OP_IMM:
            v=op.imm
            if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
            imms.append(v)
        elif op.type==OP_MEM:
            item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                  "index":md.reg_name(op.mem.index) if op.mem.index else None,
                  "disp":op.mem.disp,
                  "size":op.size}
            if op.mem.base==RIP:
                item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
            mem.append(item)
    return ins,{"rva":rva,"size":ins.size,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms}


def recursive_flow(pe,md,seeds,OP_IMM,OP_MEM,RIP,GRP_CALL,GRP_JUMP,GRP_RET):
    q=deque(seeds);rows={};edges=[];calls=[];outside=[];errors=[]
    while q and len(rows)<3000:
        rva=q.popleft()
        if rva in rows:continue
        if not (WINDOW_START<=rva<WINDOW_END):
            outside.append(rva);continue
        dec=decode_one(pe,md,rva,OP_IMM,OP_MEM,RIP)
        if not dec:
            errors.append(rva);continue
        ins,row=dec;rows[rva]=row
        next_rva=rva+ins.size

        if ins.group(GRP_CALL):
            target=None
            for v in row["imms"]:
                if isinstance(v,int) and 0<=v<pe.size_of_image:
                    target=v;break
            calls.append({"site":rva,"target":target,"op":ins.op_str})
            q.append(next_rva)
            continue
        if ins.group(GRP_RET):
            continue
        if ins.group(GRP_JUMP):
            target=None
            for v in row["imms"]:
                if isinstance(v,int) and 0<=v<pe.size_of_image:
                    target=v;break
            if target is not None:
                edges.append({"from":rva,"to":target,"kind":ins.mnemonic})
                q.append(target)
            if ins.mnemonic!="jmp":
                q.append(next_rva)
            continue
        q.append(next_rva)
    return [rows[k] for k in sorted(rows)],edges,calls,sorted(set(outside)),errors


def decode_runtime_fn(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[];imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                      "index":md.reg_name(op.mem.index) if op.mem.index else None,
                      "disp":op.mem.disp}
                if op.mem.base==RIP:
                    item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(item)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms})
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"SHA mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper();pe=helper.PE(exe.read_bytes())
    (Cs,ARCH,MODE,GRP_CALL,GRP_JUMP,GRP_RET,OP_IMM,OP_MEM,RIP)=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    lookup_rows,lookup_edges,lookup_calls,outside,errors=recursive_flow(
        pe,md,[LOOKUP],OP_IMM,OP_MEM,RIP,GRP_CALL,GRP_JUMP,GRP_RET)

    # Direct callers of lookup from aligned runtime functions.
    lookup_callers=[]
    for fn in pe.runtime_functions:
        rows=decode_runtime_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        sites=[]
        for row in rows:
            if row["mnemonic"]=="call" and LOOKUP in row["imms"]:
                sites.append(row["rva"])
        if sites:
            lookup_callers.append({"begin":fn["begin"],"end":fn["end"],"sites":sites})

    # LuaContext vtable neighborhood: -4 through +28 slots relative to base.
    slots=[]
    virtual_targets=set()
    for idx in range(-4,29):
        slot=VTABLE+idx*8
        val=u64(pe,slot)
        target=None
        if val is not None and IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
            target=val-IMAGE_BASE
            sec=pe.section_for_rva(target)
            if not(sec and sec.get("exec")):target=None
        slots.append({"index":idx,"slot_rva":slot,"target_rva":target})
        if target is not None:virtual_targets.add(target)

    # Inspect exact virtual methods touching owner fields/calling lookup.
    virtual_methods=[]
    for target in sorted(virtual_targets):
        fn=pe.function_for(target)
        if not fn:continue
        rows=decode_runtime_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        hits=[]
        for row in rows:
            if row["mnemonic"]=="call" and LOOKUP in row["imms"]:
                hits.append({"site":row["rva"],"kind":"calls_lookup"})
            for m in row["mem"]:
                if m["disp"] in OWNER_OFFSETS and m["base"] not in ("rsp","rbp","rip",None):
                    hits.append({"site":row["rva"],"kind":"owner_offset","offset":m["disp"],"base":m["base"],"op":row["op_str"]})
        if hits or fn["begin"] in (FACTORY,LOOKUP):
            virtual_methods.append({"target":target,"begin":fn["begin"],"end":fn["end"],"hits":hits,"instructions":rows})

    report={
        "schema":1,"analysis":"lua_context_resource_state_lookup",
        "exe_sha256":digest,"lookup":LOOKUP,"factory":FACTORY,"vtable":VTABLE,
        "lookup_flow":{"instructions":lookup_rows,"edges":lookup_edges,"calls":lookup_calls,"outside_targets":outside,"decode_errors":errors},
        "lookup_callers":lookup_callers,
        "vtable_slots":slots,
        "virtual_methods":virtual_methods,
        "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,"save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - LuaContext resource-state lookup trace",
        f"exe_sha256={digest}",
        f"lookup=0x{LOOKUP:X} factory=0x{FACTORY:X} vtable=0x{VTABLE:X}",
        f"lookup_instructions={len(lookup_rows)} callers={len(lookup_callers)} virtual_methods={len(virtual_methods)}",
        "",
        "LUA CONTEXT VTABLE",
    ]
    for s in slots:
        target="-" if s["target_rva"] is None else f"0x{s['target_rva']:X}"
        mark=" <FACTORY>" if s["target_rva"]==FACTORY else ""
        lines.append(f"index={s['index']:>3} slot=0x{s['slot_rva']:X} target={target}{mark}")

    lines.extend(["","LOOKUP 0x464410 REAL FLOW"])
    for row in lookup_rows:
        tags=[]
        for m in row["mem"]:
            if m["disp"] in OWNER_OFFSETS:tags.append(f"owner+0x{m['disp']:X}")
        lines.append(f"0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"+((" ; "+" | ".join(tags)) if tags else ""))

    lines.extend(["","LOOKUP DIRECT CALLS"])
    for c in lookup_calls:
        tgt="indirect" if c["target"] is None else f"0x{c['target']:X}"
        lines.append(f"0x{c['site']:X} -> {tgt} {c['op']}")

    lines.extend(["","LOOKUP CALLERS"])
    for c in lookup_callers:
        lines.append(f"FUNCTION 0x{c['begin']:X}..0x{c['end']:X} sites="+",".join(f"0x{x:X}" for x in c["sites"]))

    lines.extend(["","RELEVANT LUA CONTEXT VIRTUAL METHODS"])
    for f in virtual_methods:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} vtarget=0x{f['target']:X}")
        for h in f["hits"]:
            if h["kind"]=="owner_offset":
                lines.append(f"  HIT 0x{h['site']:X} owner+0x{h['offset']:X} base={h['base']} {h['op']}")
            else:
                lines.append(f"  HIT 0x{h['site']:X} calls 0x{LOOKUP:X}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")

    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_CONTEXT_RESOURCE_STATE_TRACE_COMPLETE lookupInstructions={len(lookup_rows)} callers={len(lookup_callers)} virtualMethods={len(virtual_methods)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
