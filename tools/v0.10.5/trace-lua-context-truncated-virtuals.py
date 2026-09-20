#!/usr/bin/env python3
"""Trace real contiguous flow for truncated LuaContext virtual methods.

Seeds:
  0x464140 (LuaContext vtable slot 9)
  0x465370 (LuaContext vtable slot 13)

Both PE runtime-function entries end mid-control-flow. These slots bracket the
save/restore/client factory methods and are prime candidates for the producer
that queues per-resource state into LuaContext+0x178.

The recursive pass follows direct branches/fallthrough across unwind boundaries
inside tight windows and highlights:
- LuaContext offsets +0x178/+0x188/+0x190/+0x198
- intrusive-list/node offsets +0/+8/+0x18
- calls to known checkpoint/SoftPickle bridge functions
- calls to 0x464410 / 0x4654A0

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
SEEDS=(0x464140,0x465370)
WINDOWS=((0x464100,0x4644C0),(0x465360,0x4654A0))
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
    spec=importlib.util.spec_from_file_location("lua_context_truncated_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_CALL,CS_GRP_JUMP,CS_GRP_RET,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


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
                  "disp":op.mem.disp,"size":op.size}
            if op.mem.base==RIP:item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
            mem.append(item)
    return ins,{"rva":rva,"size":ins.size,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms}


def trace(pe,md,seed,window,GRP_CALL,GRP_JUMP,GRP_RET,OP_IMM,OP_MEM,RIP):
    q=deque([seed]);rows={};edges=[];calls=[];outside=[];errors=[]
    lo,hi=window
    while q and len(rows)<4000:
        rva=q.popleft()
        if rva in rows:continue
        if not(lo<=rva<hi):
            outside.append(rva);continue
        dec=decode_one(pe,md,rva,OP_IMM,OP_MEM,RIP)
        if not dec:
            errors.append(rva);continue
        ins,row=dec;rows[rva]=row
        nxt=rva+ins.size
        if ins.group(GRP_CALL):
            target=next((v for v in row["imms"] if isinstance(v,int) and 0<=v<pe.size_of_image),None)
            calls.append({"site":rva,"target":target,"op":ins.op_str})
            q.append(nxt);continue
        if ins.group(GRP_RET):continue
        if ins.group(GRP_JUMP):
            target=next((v for v in row["imms"] if isinstance(v,int) and 0<=v<pe.size_of_image),None)
            if target is not None:
                edges.append({"from":rva,"to":target,"kind":ins.mnemonic});q.append(target)
            if ins.mnemonic!="jmp":q.append(nxt)
            continue
        q.append(nxt)
    ordered=[rows[k] for k in sorted(rows)]
    return ordered,edges,calls,sorted(set(outside)),errors


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

    traces=[]
    for seed,window in zip(SEEDS,WINDOWS):
        rows,edges,calls,outside,errors=trace(pe,md,seed,window,GC,GJ,GR,OI,OM,RIP)
        tagged=[]
        for row in rows:
            tags=[]
            for m in row["mem"]:
                if m["disp"] in OWNER_OFFSETS:tags.append(f"owner+0x{m['disp']:X}")
                if m["disp"] in NODE_OFFSETS and m.get("base") not in ("rsp","rbp","rip",None):tags.append(f"node+0x{m['disp']:X}")
            for target in row["imms"]:
                if target in ANCHORS:tags.append(f"anchor->0x{target:X}")
            if tags:row["tags"]=sorted(set(tags))
            tagged.append(row)
        traces.append({"seed":seed,"window":{"start":window[0],"end":window[1]},
                       "instructions":tagged,"edges":edges,"calls":calls,
                       "outside_targets":outside,"decode_errors":errors})

    report={"schema":1,"analysis":"lua_context_truncated_virtuals","exe_sha256":digest,
            "traces":traces,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - contiguous LuaContext virtual trace",f"exe_sha256={digest}",""]
    for t in traces:
        lines.append(f"SEED 0x{t['seed']:X} window=0x{t['window']['start']:X}..0x{t['window']['end']:X} instructions={len(t['instructions'])}")
        for row in t["instructions"]:
            suffix=(" ; "+" | ".join(row.get("tags",[]))) if row.get("tags") else ""
            lines.append(f"0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}{suffix}")
        lines.append("CALLS")
        for c in t["calls"]:
            target="indirect" if c["target"] is None else f"0x{c['target']:X}"
            lines.append(f"  0x{c['site']:X} -> {target} {c['op']}")
        lines.append("OUTSIDE "+",".join(f"0x{x:X}" for x in t["outside_targets"]))
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("LUA_CONTEXT_TRUNCATED_VIRTUAL_TRACE_COMPLETE "+ " ".join(f"seed0x{t['seed']:X}={len(t['instructions'])}" for t in traces))
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
