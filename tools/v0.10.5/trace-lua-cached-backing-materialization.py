#!/usr/bin/env python3
"""Trace LuaClient cached-backing -> live pickle-buffer materialization.

Known:
- LuaClient/LuaLevelClient +0x68 = durable per-resource backing node.
- +0x70 / +0x78 = transient normal/soft serialized blobs.
- 0x5A6C10 consumes +0x70/+0x78 by calling virtual restore slots +0x80/+0x88,
  frees both blobs via allocator backing+0x28, then zeros the pointers.
- 0x5A6C10 calls 0x5A69F0 if client+0x58 is not initialized.
- 0x5A6CD0 is another direct caller of 0x5A7720 and sits adjacent to constructor/
  restore lifecycle code.

This compact pass disassembles:
  0x5A69F0
  0x5A6C10
  0x5A6CD0
and one-hop small callees, with memory-access tagging for offsets
+0x58/+0x60/+0x68/+0x70/+0x78/+0x80 and known checkpoint/SoftPickle bridges.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGETS=(0x5A69F0,0x5A6C10,0x5A6CD0)
OFFSETS=(0x58,0x60,0x68,0x70,0x78,0x80)
BRIDGES=(0x5A7720,0x5AEC20,0x5AEC40,0x5AEC60,0x5AEF60,0x5AEF90,0x5AEFC0,0x5AF01C,0x5AF4E0,
         0x5B1030,0x5AD4A0,0x5AD8E0,0x5AC760,0x463C60,0x464410,0x4654A0)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_materialize_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
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

def hits(rows):
    out=[]
    for row in rows:
        for m in row["mem"]:
            base=m.get("base")
            if base not in (None,"rsp","rbp","rip") and m["disp"] in OFFSETS:
                out.append({"site":row["rva"],"kind":"offset","offset":m["disp"],"base":base,"op":row["op_str"]})
        if row["mnemonic"] in ("call","jmp") and row["imms"]:
            t=row["imms"][0]
            if t in BRIDGES:
                out.append({"site":row["rva"],"kind":"bridge","target":t,"op":row["op_str"]})
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
    Cs,ARCH,MODE,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    primary=[];secondary=[];seen=set();small=set()
    for target in TARGETS:
        fn=pe.function_for(target)
        if not fn:raise RuntimeError(f"No runtime function for 0x{target:X}")
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        primary.append({"target":target,"begin":fn["begin"],"end":fn["end"],"hits":hits(rows),"instructions":rows})
        seen.add(fn["begin"])
        for row in rows:
            if row["mnemonic"]=="call" and row["imms"]:
                tf=pe.function_for(row["imms"][0])
                if tf and tf["end"]-tf["begin"]<=0x300:
                    small.add(tf["begin"])

    for b in sorted(small-seen):
        fn=pe.function_for(b)
        if not fn:continue
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        secondary.append({"begin":b,"end":fn["end"],"hits":hits(rows),"instructions":rows})

    report={"schema":1,"analysis":"lua_cached_backing_materialization","exe_sha256":digest,
            "targets":list(TARGETS),"primary":primary,"secondary":secondary,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - cached backing -> live pickle materialization trace",f"exe_sha256={digest}",""]
    def emit(label,f):
        lines.append(f"{label} 0x{f['begin']:X}..0x{f['end']:X}")
        for h in f["hits"]:
            if h["kind"]=="offset":
                lines.append(f"  HIT 0x{h['site']:X} +0x{h['offset']:X} base={h['base']} {h['op']}")
            else:
                lines.append(f"  HIT 0x{h['site']:X} bridge -> 0x{h['target']:X} {h['op']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    for f in primary:emit("PRIMARY",f)
    lines.append("SMALL ONE-HOP CALLEES")
    for f in secondary:emit("FUNCTION",f)
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_CACHED_BACKING_MATERIALIZATION_TRACE_COMPLETE primary={len(primary)} secondary={len(secondary)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
