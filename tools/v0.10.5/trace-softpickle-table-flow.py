#!/usr/bin/env python3
"""Trace the exact __SoftPickleTable save/restore flow in supported GoW.exe.

Compact, read-only static pass. It finds every runtime-function-aligned RIP
reference to:
  __PickleTable
  __SoftPickleTable
  __subobjs
  OnSaveCheckpoint
  OnRestoreCheckpoint

and disassembles only those matching functions plus a small fixed set of known
save/restore bridge functions:
  0x5AF01C checkpoint table builder
  0x5AC760 SubObject save/SoftSave consumer
  0x5AD4A0 SubObject restore dispatch
  0x5AD8E0 pickle-table restore helper
  0x5B1030 unpickle driver
  0x5AFF84 restore caller
  0x5ABB60 restore caller
  0x5AD440 restore wrapper
  0x5AF4E0 builder helper
  0x5A3CE0 Lua callback dispatcher

The report intentionally omits unrelated functions and never emits a huge
whole-executable JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
NAMES=("__PickleTable","__SoftPickleTable","__subobjs","OnSaveCheckpoint","OnRestoreCheckpoint")
FIXED=(0x5AF01C,0x5AC760,0x5AD4A0,0x5AD8E0,0x5B1030,0x5AFF84,0x5ABB60,0x5AD440,0x5AF4E0,0x5A3CE0)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softpickle_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def find_strings(pe):
    out={}
    for name in NAMES:
        needle=name.encode("ascii")+b"\0"
        hits=[];pos=0
        while True:
            off=pe.data.find(needle,pos)
            if off<0:break
            rva=pe.file_to_rva(off)
            if rva is not None:hits.append(rva)
            pos=off+1
        out[name]=hits
    return out


def decode(pe,md,fn,OP_IMM,OP_MEM,RIP,string_by_rva):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        refs=[];targets=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:
                    targets.append(v-IMAGE_BASE)
            elif op.type==OP_MEM and op.mem.base==RIP:
                rv=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                ref={"rva":rv}
                if rv in string_by_rva:ref["name"]=string_by_rva[rv]
                refs.append(ref)
        rows.append({
            "rva":ins.address-IMAGE_BASE,
            "bytes":ins.bytes.hex(),
            "mnemonic":ins.mnemonic,
            "op_str":ins.op_str,
            "rip_refs":refs,
            "targets":targets,
        })
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()

    exe=args.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"GoW.exe SHA256 mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper();pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    strings=find_strings(pe)
    string_by_rva={rva:name for name,rvas in strings.items() for rva in rvas}

    # Pass 1: exact RIP xrefs from aligned runtime functions.
    xref_functions={}
    call_edges=[]
    callers={}
    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP,string_by_rva)
        if not rows:continue
        xrefs=[]
        for row in rows:
            for ref in row["rip_refs"]:
                if "name" in ref:
                    xrefs.append({"site":row["rva"],"name":ref["name"],"string_rva":ref["rva"],"mnemonic":row["mnemonic"],"op_str":row["op_str"]})
            if row["mnemonic"] in ("call","jmp"):
                for target in row["targets"][:1]:
                    sec=pe.section_for_rva(target)
                    if sec and sec.get("exec"):
                        edge={"from":fn["begin"],"site":row["rva"],"kind":row["mnemonic"],"to":target}
                        call_edges.append(edge)
                        tfn=pe.function_for(target)
                        if tfn:
                            callers.setdefault(tfn["begin"],set()).add(fn["begin"])
        if xrefs:
            xref_functions[fn["begin"]]={"begin":fn["begin"],"end":fn["end"],"xrefs":xrefs}

    selected=set(xref_functions)
    for target in FIXED:
        fn=pe.function_for(target)
        if fn:selected.add(fn["begin"])
    # Add direct callers/callees of selected functions, but only one hop.
    edge_by_from={}
    for e in call_edges:edge_by_from.setdefault(e["from"],[]).append(e)
    seeds=list(selected)
    for b in seeds:
        selected.update(callers.get(b,set()))
        for e in edge_by_from.get(b,[]):
            fn=pe.function_for(e["to"])
            if fn:selected.add(fn["begin"])

    functions=[]
    for begin in sorted(selected):
        fn=pe.function_for(begin)
        if not fn:continue
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP,string_by_rva)
        # Keep complete instructions only for primary xref/fixed functions.
        primary=begin in xref_functions or any(pe.function_for(x) and pe.function_for(x)["begin"]==begin for x in FIXED)
        functions.append({
            "begin":begin,"end":fn["end"],"primary":primary,
            "xrefs":xref_functions.get(begin,{}).get("xrefs",[]),
            "callers":sorted(callers.get(begin,set())),
            "edges":edge_by_from.get(begin,[]),
            "instructions":rows if primary else [],
        })

    report={
        "schema":1,
        "analysis":"softpickle_table_flow",
        "exe_sha256":digest,
        "strings":strings,
        "xref_functions":sorted(xref_functions),
        "functions":functions,
        "safety":{
            "static_exe_read_only":True,"game_launched":False,"process_accessed":False,
            "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False,
        },
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - __SoftPickleTable native flow trace",
        f"exe_sha256={digest}",
        "",
        "STRING RVAS",
    ]
    for name in NAMES:
        lines.append(f"{name}="+",".join(f"0x{x:X}" for x in strings[name]))
    lines.extend(["","XREF FUNCTIONS"])
    for begin in sorted(xref_functions):
        rec=xref_functions[begin]
        lines.append(f"FUNCTION 0x{begin:X}..0x{rec['end']:X}")
        for x in rec["xrefs"]:
            lines.append(f"  XREF 0x{x['site']:X} {x['mnemonic']} {x['op_str']} -> {x['name']}@0x{x['string_rva']:X}")

    lines.extend(["","PRIMARY FUNCTION DISASSEMBLY"])
    for rec in functions:
        if not rec["primary"]:continue
        lines.append(f"FUNCTION 0x{rec['begin']:X}..0x{rec['end']:X} callers="+",".join(f"0x{x:X}" for x in rec["callers"]))
        for row in rec["instructions"]:
            suffix=[]
            for ref in row["rip_refs"]:
                if "name" in ref:suffix.append(f"{ref['name']}@0x{ref['rva']:X}")
            for target in row["targets"]:
                sec=pe.section_for_rva(target)
                if sec and sec.get("exec"):suffix.append(f"code->0x{target:X}")
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"+((" ; "+" | ".join(suffix)) if suffix else ""))
        lines.append("")

    lines.extend(["ONE-HOP CALL GRAPH"])
    for rec in functions:
        labels=[]
        if rec["primary"]:labels.append("primary")
        if rec["xrefs"]:labels.append("string-xref")
        lines.append(f"0x{rec['begin']:X} labels={','.join(labels) or '-'} callers="+",".join(f"0x{x:X}" for x in rec["callers"]))
        for e in rec["edges"]:
            lines.append(f"  0x{e['site']:X} {e['kind']} -> 0x{e['to']:X}")

    lines.extend(["","SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"SOFTPICKLE_TABLE_FLOW_TRACE_COMPLETE xrefFunctions={len(xref_functions)} selectedFunctions={len(functions)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
