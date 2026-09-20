#!/usr/bin/env python3
"""Trace ownership/container of LuaLevelClient instances in GoW 2018.

Known:
- LuaLevelClient vtable: 0xE03F18
- LuaClient vtable:      0xE04018
- LuaLevelClient ctor-ish initializer: 0x5B13A0
- mixed client factory:  0x4654A0
- level owner pointer written at LuaLevelClient+0x16820

This pass finds:
1. all aligned runtime-function call/xrefs to 0x5B13A0 and 0x4654A0;
2. references to the LuaLevelClient vtable and RTTI type descriptor;
3. code touching offsets 0x188/0x190 in the factory owner around 0x4654A0,
   because those fields provide the LuaClient/LuaLevelClient allocation pools;
4. one-hop callers/callees of matched functions.

It emits only compact matched function disassembly.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
from collections import defaultdict

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGET_FUNCS=(0x5B13A0,0x4654A0)
VTABLE=0xE03F18
TYPE_DESC=0x11F9608
OWNER_OFFSETS=(0x178,0x188,0x190)


def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_level_client_owner_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def decode(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
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
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms})
    return rows


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
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    matched={}
    callers=defaultdict(set)
    edges=[]
    all_rows={}

    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows:continue
        all_rows[fn["begin"]]=rows
        hits=[]
        for row in rows:
            if row["mnemonic"] in ("call","jmp") and row["imms"]:
                target=row["imms"][0]
                sec=pe.section_for_rva(target) if isinstance(target,int) else None
                if sec and sec.get("exec"):
                    edges.append({"from":fn["begin"],"site":row["rva"],"kind":row["mnemonic"],"to":target})
                    tf=pe.function_for(target)
                    if tf:callers[tf["begin"]].add(fn["begin"])
                if target in TARGET_FUNCS:
                    hits.append({"site":row["rva"],"kind":"call_target","target":target,"op":row["op_str"]})
            for m in row["mem"]:
                rv=m.get("rip_target")
                if rv in (VTABLE,TYPE_DESC):
                    hits.append({"site":row["rva"],"kind":"rip_target","target":rv,"op":row["op_str"]})
                if m["disp"] in OWNER_OFFSETS and m["base"] not in ("rsp","rbp","rip",None):
                    hits.append({"site":row["rva"],"kind":"owner_offset","offset":m["disp"],"base":m["base"],"op":row["op_str"]})
        if hits:
            matched[fn["begin"]]={"begin":fn["begin"],"end":fn["end"],"hits":hits}

    seed=set(matched)
    expanded=set(seed)
    for b in list(seed):
        expanded.update(callers.get(b,set()))
        for e in edges:
            if e["from"]==b:
                tf=pe.function_for(e["to"])
                if tf:expanded.add(tf["begin"])

    functions=[]
    for b in sorted(expanded):
        fn=pe.function_for(b)
        if not fn:continue
        rows=all_rows.get(b) or decode(pe,md,fn,OP_IMM,OP_MEM,RIP)
        functions.append({"begin":b,"end":fn["end"],"primary":b in matched,
                          "hits":matched.get(b,{}).get("hits",[]),
                          "callers":sorted(callers.get(b,set())),
                          "instructions":rows})

    report={"schema":1,"analysis":"lua_level_client_owner",
            "exe_sha256":digest,"targets":list(TARGET_FUNCS),
            "vtable":VTABLE,"type_descriptor":TYPE_DESC,
            "matched_count":len(matched),"functions":functions,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
      "Completionist Map - LuaLevelClient owner/container trace",
      f"exe_sha256={digest}",
      f"matched={len(matched)} functions={len(functions)}",
      "",
      "FUNCTIONS",
    ]
    for f in functions:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} primary={str(f['primary']).lower()} callers="+",".join(f"0x{x:X}" for x in f["callers"]))
        for h in f["hits"]:
            tgt=h.get("target",h.get("offset"))
            lines.append(f"  HIT site=0x{h['site']:X} kind={h['kind']} value=0x{tgt:X} op={h['op']}")
        if f["primary"]:
            for row in f["instructions"]:
                lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_LEVEL_CLIENT_OWNER_TRACE_COMPLETE matched={len(matched)} functions={len(functions)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
