#!/usr/bin/env python3
"""Resolve and trace LuaContext vtable slot 13 jump table at 0x465370.

The method dispatches on byte(type) for cases 0..5 using a relative jump table
at RVA 0x46547C. This pass resolves all six signed dword entries, then recursively
traces each case target inside [0x465360,0x4654A0).

Highlights:
- LuaContext+0x178/+0x188/+0x190/+0x198
- intrusive list writes/reads at node+0/node+8/node+0x18
- calls to 0x464410, 0x4654A0, and checkpoint/SoftPickle bridge functions

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
METHOD=0x465370
TABLE=0x46547C
CASE_COUNT=6
WINDOW=(0x465360,0x4654A0)
OWNER_OFFSETS=(0x178,0x188,0x190,0x198)
NODE_OFFSETS=(0x0,0x8,0x18)
ANCHORS=(0x464410,0x4654A0,0x5AEC20,0x5AEC40,0x5AEF60,0x5AEF90,0x5AEC60,0x5AEFC0,0x5AF01C,0x5AF4E0,0x5B1030,0x5AD4A0,0x5AD8E0)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_context_slot13_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def s32(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None:return None
    return struct.unpack_from("<i",pe.data,off)[0]

def decode_one(pe,md,rva,OI,OM,RIP):
    off=pe.rva_to_file(rva)
    if off is None:return None
    insns=list(md.disasm(pe.data[off:off+15],IMAGE_BASE+rva,count=1))
    if not insns:return None
    ins=insns[0]
    mem=[];imms=[]
    for op in getattr(ins,"operands",[]):
        if op.type==OI:
            v=op.imm
            if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
            imms.append(v)
        elif op.type==OM:
            item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                  "index":md.reg_name(op.mem.index) if op.mem.index else None,
                  "disp":op.mem.disp,"size":op.size}
            if op.mem.base==RIP:item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
            mem.append(item)
    return ins,{"rva":rva,"size":ins.size,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms}

def trace(pe,md,seeds,GC,GJ,GR,OI,OM,RIP):
    lo,hi=WINDOW
    q=deque(seeds);rows={};edges=[];calls=[];outside=[];errors=[]
    while q and len(rows)<2000:
        rva=q.popleft()
        if rva in rows:continue
        if not(lo<=rva<hi):
            outside.append(rva);continue
        dec=decode_one(pe,md,rva,OI,OM,RIP)
        if not dec:
            errors.append(rva);continue
        ins,row=dec;rows[rva]=row
        nxt=rva+ins.size
        if ins.group(GC):
            target=next((v for v in row["imms"] if isinstance(v,int) and 0<=v<pe.size_of_image),None)
            calls.append({"site":rva,"target":target,"op":ins.op_str});q.append(nxt);continue
        if ins.group(GR):continue
        if ins.group(GJ):
            target=next((v for v in row["imms"] if isinstance(v,int) and 0<=v<pe.size_of_image),None)
            if target is not None:
                edges.append({"from":rva,"to":target,"kind":ins.mnemonic});q.append(target)
            if ins.mnemonic!="jmp":q.append(nxt)
            continue
        q.append(nxt)
    return [rows[k] for k in sorted(rows)],edges,calls,sorted(set(outside)),errors

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
    Cs,ARCH,MODE,GC,GJ,GR,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    cases=[]
    seeds=[]
    for i in range(CASE_COUNT):
        rel=s32(pe,TABLE+i*4)
        if rel is None:raise RuntimeError(f"unable to read jump-table entry {i}")
        target=(rel & 0xffffffff)
        # Table entries are RVAs relative to image base because RCX was explicitly set to image base (RVA 0).
        target=rel if rel>=0 else (1<<32)+rel
        cases.append({"case":i,"entry_rva":TABLE+i*4,"raw_signed":rel,"target_rva":target})
        seeds.append(target)

    rows,edges,calls,outside,errors=trace(pe,md,seeds,GC,GJ,GR,OI,OM,RIP)
    for row in rows:
        tags=[]
        for m in row["mem"]:
            base=m.get("base")
            if base not in ("rsp","rbp","rip",None):
                if m["disp"] in OWNER_OFFSETS:tags.append(f"owner+0x{m['disp']:X}")
                if m["disp"] in NODE_OFFSETS:tags.append(f"node+0x{m['disp']:X}")
        for v in row["imms"]:
            if v in ANCHORS:tags.append(f"anchor->0x{v:X}")
        if tags:row["tags"]=sorted(set(tags))

    report={"schema":1,"analysis":"lua_context_slot13_jump_table","exe_sha256":digest,
            "method":METHOD,"table":TABLE,"cases":cases,
            "instructions":rows,"edges":edges,"calls":calls,
            "outside_targets":outside,"decode_errors":errors,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - LuaContext slot13 jump-table trace",f"exe_sha256={digest}","CASES"]
    for c in cases:
        lines.append(f"case={c['case']} table=0x{c['entry_rva']:X} raw={c['raw_signed']} target=0x{c['target_rva']:X}")
    lines.extend(["","REACHABLE CASE FLOW"])
    for row in rows:
        suffix=(" ; "+" | ".join(row.get("tags",[]))) if row.get("tags") else ""
        lines.append(f"0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}{suffix}")
    lines.extend(["","CALLS"])
    for c in calls:
        t="indirect" if c["target"] is None else f"0x{c['target']:X}"
        lines.append(f"0x{c['site']:X} -> {t} {c['op']}")
    lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print("LUA_CONTEXT_SLOT13_JUMP_TABLE_TRACE_COMPLETE "+" ".join(f"case{c['case']}=0x{c['target_rva']:X}" for c in cases))
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
