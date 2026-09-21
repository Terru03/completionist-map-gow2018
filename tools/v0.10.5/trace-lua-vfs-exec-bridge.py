#!/usr/bin/env python3
"""Inspect the native Lua VFS helper cluster around 0x84AB50.

This is a bounded static/read-only GoW.exe analysis. It does not launch or
attach to the game, touch saves, or write game files. The goal is to determine
whether the Lua-exposed VFSExec helper is a real file/script execution bridge
or only a small VFS/config accessor before considering any custom native loader.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FOCUS={
    "VFSExec":0x84AB50,
    "VFSGetEnumIndex":0x84AB60,
    "VFSGetEnumName":0x84AB70,
    "VFSGetFloat":0x84AB90,
    "VFSGetInt":0x84ABB0,
    "VFSSetFloat":0x84ABD0,
    "VFSSetInt":0x84ABF0,
}

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("vfs_exec_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def ascii_at(pe,rva,max_len=240):
    off=pe.rva_to_file(rva)
    if off is None:return None
    b=pe.data[off:off+max_len]
    z=b.find(b"\x00")
    if z>=0:b=b[:z]
    if len(b)<3:return None
    try:s=b.decode("utf-8")
    except Exception:return None
    if not all(ch in "\r\n\t" or 32<=ord(ch)<127 for ch in s):return None
    return s

def decode(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        imms=[]; refs=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM and op.mem.base==RIP:
                t=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                refs.append({"target":t,"ascii":ascii_at(pe,t)})
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                    "imms":imms,"rip_refs":refs})
    return out

def direct_calls(pe,rows):
    out=[]
    for r in rows:
        if r["mnemonic"] not in ("call","jmp") or not r["imms"]:continue
        t=r["imms"][0]
        if not isinstance(t,int):continue
        sec=pe.section_for_rva(t)
        if not sec or not sec.get("exec"):continue
        fn=pe.function_for(t)
        out.append({"site":r["rva"],"kind":r["mnemonic"],"target":t,
                    "target_function":fn["begin"] if fn else None})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    exe=a.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"SHA mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper(); pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE); md.detail=True

    all_rows={}; all_calls={}; callers=defaultdict(list)
    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows:continue
        all_rows[fn["begin"]]=rows
        cs=direct_calls(pe,rows); all_calls[fn["begin"]]=cs
        for x in cs:
            tf=x.get("target_function")
            if tf is not None:callers[tf].append({"caller":fn["begin"],"site":x["site"]})

    selected=set()
    for rva in FOCUS.values():
        fn=pe.function_for(rva)
        if fn:selected.add(fn["begin"])
    first=list(selected)
    for begin in first:
        for x in all_calls.get(begin,[]):
            if x.get("target_function") is not None:selected.add(x["target_function"])
        for x in callers.get(begin,[]):selected.add(x["caller"])

    funcs=[]
    for begin in sorted(selected):
        fn=pe.function_for(begin)
        if not fn:continue
        rows=all_rows.get(begin,[])
        strings=[]
        for r in rows:
            for rr in r["rip_refs"]:
                if rr.get("ascii"):strings.append({"site":r["rva"],**rr})
        funcs.append({"begin":begin,"end":fn["end"],"calls":all_calls.get(begin,[]),
                      "callers":callers.get(begin,[]),"strings":strings,
                      "instructions":rows})

    report={"schema":1,"analysis":"lua_vfs_exec_bridge",
            "exe_sha256":digest,"focus":FOCUS,"functions":funcs,
            "safety":{"static_exe_read_only":True,"game_launched":False,
                      "process_accessed":False,"save_opened":False,
                      "save_written":False,"progression_written":False,
                      "game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    labels=defaultdict(list)
    for name,rva in FOCUS.items():
        fn=pe.function_for(rva)
        if fn:labels[fn["begin"]].append(name)
    lines=["Completionist Map - Lua VFSExec bridge static trace",
           f"exe_sha256={digest}",""]
    for f in funcs:
        labs=",".join(labels.get(f["begin"],[])) or "-"
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} labels={labs}")
        for x in f["callers"]:
            lines.append(f"  CALLER 0x{x['caller']:X} site=0x{x['site']:X}")
        for x in f["calls"]:
            tf=x.get("target_function")
            lines.append(f"  {x['kind'].upper()} 0x{x['site']:X} -> "+
                         ("-" if tf is None else f"0x{tf:X}")+f" raw=0x{x['target']:X}")
        for s in f["strings"]:
            lines.append(f"  RIPSTR 0x{s['site']:X} -> 0x{s['target']:X} {s['ascii']!r}")
        lines.append("  DISASM")
        for r in f["instructions"]:
            lines.append(f"    0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_VFS_EXEC_BRIDGE_TRACE_COMPLETE functions={len(funcs)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
