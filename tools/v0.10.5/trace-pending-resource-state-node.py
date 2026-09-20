#!/usr/bin/env python3
"""Trace lifecycle/layout of LuaContext pending per-resource state nodes.

Proven producer path:
- LuaContext slot13 case 2 (LuaLevelClient) reads backing state from client+0x68,
  calls 0x463C60(backing_state), inserts that object into LuaContext+0x178,
  then returns the LuaLevelClient to pool +0x190.
- LuaContext::CreateClient at 0x4654A0 later removes the matching node from
  +0x178 via 0x464410 and passes it as r9 to 0x5A6DD0 while constructing the
  replacement LuaLevelClient.

This pass traces both ends:
  0x463C60  pending-node finalizer/prepare-for-cache
  0x5A6DD0  common client constructor that receives pending node in r9

It records:
- full runtime-function disassembly for both;
- one-hop direct callees <= 0x300 bytes;
- memory offsets used from non-stack registers;
- direct calls into the known checkpoint/SoftPickle family.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGETS=(0x463C60,0x5A6DD0)
BRIDGES=(0x5AEC20,0x5AEC40,0x5AEC60,0x5AEF60,0x5AEF90,0x5AEFC0,0x5AF01C,0x5AF4E0,0x5B1030,0x5AD4A0,0x5AD8E0,0x464410,0x4654A0)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("pending_node_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def decode_fn(pe,md,fn,OI,OM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
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
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,
                     "op_str":ins.op_str,"mem":mem,"imms":imms})
    return rows

def summarize_offsets(rows):
    out=defaultdict(lambda:defaultdict(list))
    for row in rows:
        for m in row["mem"]:
            base=m.get("base")
            if base in (None,"rsp","rbp","rip"):continue
            disp=m.get("disp",0)
            if -0x10000 <= disp <= 0x20000:
                out[base][disp].append(row["rva"])
    return {base:{str(d):sites for d,sites in sorted(vals.items())} for base,vals in sorted(out.items())}

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
    Cs,ARCH,MODE,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    primary=[]
    callee_targets=set()
    for target in TARGETS:
        fn=pe.function_for(target)
        if not fn:raise RuntimeError(f"no runtime function for 0x{target:X}")
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        calls=[]
        for row in rows:
            if row["mnemonic"] in ("call","jmp") and row["imms"]:
                t=row["imms"][0]
                sec=pe.section_for_rva(t) if isinstance(t,int) else None
                if sec and sec.get("exec"):
                    calls.append({"site":row["rva"],"target":t,"op":row["op_str"],"bridge":t in BRIDGES})
                    tf=pe.function_for(t)
                    if tf and tf["end"]-tf["begin"]<=0x300:
                        callee_targets.add(tf["begin"])
        primary.append({"target":target,"begin":fn["begin"],"end":fn["end"],
                        "offsets":summarize_offsets(rows),"calls":calls,"instructions":rows})

    secondary=[]
    for b in sorted(callee_targets):
        if any(x["begin"]==b for x in primary):continue
        fn=pe.function_for(b)
        if not fn:continue
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        secondary.append({"begin":b,"end":fn["end"],"offsets":summarize_offsets(rows),"instructions":rows})

    report={"schema":1,"analysis":"lua_pending_resource_state_node","exe_sha256":digest,
            "targets":list(TARGETS),"primary":primary,"secondary":secondary,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - pending resource-state node lifecycle trace",
           f"exe_sha256={digest}",""]
    for f in primary:
        lines.append(f"PRIMARY 0x{f['begin']:X}..0x{f['end']:X} target=0x{f['target']:X}")
        lines.append("OFFSETS "+json.dumps(f["offsets"],sort_keys=True))
        for c in f["calls"]:
            mark=" BRIDGE" if c["bridge"] else ""
            lines.append(f"CALL 0x{c['site']:X} -> 0x{c['target']:X}{mark} {c['op']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("ONE-HOP SMALL CALLEES")
    for f in secondary:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        lines.append("OFFSETS "+json.dumps(f["offsets"],sort_keys=True))
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"PENDING_RESOURCE_STATE_NODE_TRACE_COMPLETE primary={len(primary)} secondary={len(secondary)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
