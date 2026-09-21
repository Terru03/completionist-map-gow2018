#!/usr/bin/env python3
"""Resolve the native registry behind Lua VFSExec.

Static/read-only GoW.exe analysis only. Finds every code reference to the
VFSExec shared helper, registry count/entry globals, and dispatcher global,
then emits full enclosing functions plus one-hop call context and printable
RIP-relative strings. No process attach, game launch, save access or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FOCUS={"vfs_shared_helper":0x84FCC0,"hash_lookup_helper":0x431B90}
GLOBALS={
    "vfs_registry_count":0x2D481B4,
    "vfs_registry_entries":0x504C0A0,
    "vfs_dispatcher_ptr":0x123B680,
}
KEYWORDS=("vfs","save","checkpoint","wad","lua","restore","load","slot","state","pickle","raven")

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("vfs_registry_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

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

def decode(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        imms=[]; mem=[]
        for i,op in enumerate(getattr(ins,"operands",[])):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                m={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "disp":op.mem.disp,"size":op.size,"operand_index":i,
                   "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:
                    m["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(m)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                    "imms":imms,"mem":mem})
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
    Cs,ARCH,MODE,AC_WRITE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE); md.detail=True

    decoded={}; calls={}; callers=defaultdict(list)
    global_refs=defaultdict(list); helper_callers=defaultdict(list)
    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE)
        if not rows:continue
        b=fn["begin"]; decoded[b]=rows
        cs=direct_calls(pe,rows); calls[b]=cs
        for x in cs:
            tf=x.get("target_function")
            if tf is not None:callers[tf].append({"caller":b,"site":x["site"]})
            for name,target in FOCUS.items():
                ftarget=pe.function_for(target)
                if ftarget and tf==ftarget["begin"]:
                    helper_callers[name].append({"caller":b,"site":x["site"]})
        for r in rows:
            for m in r["mem"]:
                t=m.get("rip_target")
                if t is None:continue
                for name,g in GLOBALS.items():
                    if t==g:
                        global_refs[name].append({"function":b,"site":r["rva"],
                                                  "write":m["write"],"op":r["op_str"]})

    selected=set()
    for rva in FOCUS.values():
        fn=pe.function_for(rva)
        if fn:selected.add(fn["begin"])
    for refs in global_refs.values():
        selected.update(x["function"] for x in refs)
    for refs in helper_callers.values():
        selected.update(x["caller"] for x in refs)

    # One-hop call context from all directly relevant functions.
    first=list(selected)
    for b in first:
        for x in calls.get(b,[]):
            if x.get("target_function") is not None:selected.add(x["target_function"])
        for x in callers.get(b,[]):selected.add(x["caller"])

    functions=[]
    for b in sorted(selected):
        fn=pe.function_for(b)
        if not fn:continue
        rows=decoded.get(b,[])
        strings=[]; refs=[]
        for r in rows:
            for m in r["mem"]:
                t=m.get("rip_target")
                if t is None:continue
                s=ascii_at(pe,t)
                if s: strings.append({"site":r["rva"],"target":t,"ascii":s})
                for name,g in GLOBALS.items():
                    if t==g:
                        refs.append({"name":name,"site":r["rva"],"write":m["write"],
                                     "op":r["op_str"]})
        functions.append({"begin":b,"end":fn["end"],"calls":calls.get(b,[]),
                          "callers":callers.get(b,[]),"global_refs":refs,
                          "strings":strings,"instructions":rows})

    keyword_strings=[]
    # Search mapped non-executable image data for useful ASCII labels.
    for sec in pe.sections:
        if sec.get("exec"):continue
        start=sec["raw_ptr"]; end=start+sec["raw_size"]
        blob=pe.data[start:end]
        i=0
        while i<len(blob):
            if 32<=blob[i]<127:
                j=i
                while j<len(blob) and 32<=blob[j]<127:j+=1
                if j-i>=4:
                    try:s=blob[i:j].decode("ascii")
                    except Exception:s=""
                    if s and any(k in s.lower() for k in KEYWORDS):
                        rva=sec["rva"]+i
                        keyword_strings.append({"rva":rva,"text":s})
                i=j+1
            else:i+=1
    keyword_strings=keyword_strings[:4000]

    report={"schema":1,"analysis":"lua_vfs_registry","exe_sha256":digest,
            "focus":FOCUS,"globals":GLOBALS,"global_refs":global_refs,
            "helper_callers":helper_callers,"functions":functions,
            "keyword_strings":keyword_strings,
            "safety":{"static_exe_read_only":True,"game_launched":False,
                      "process_accessed":False,"save_opened":False,
                      "save_written":False,"progression_written":False,
                      "game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - Lua VFS registry static trace",
           f"exe_sha256={digest}",""]
    for name,refs in global_refs.items():
        lines.append(f"GLOBAL {name}=0x{GLOBALS[name]:X} refs={len(refs)}")
        for x in refs:
            lines.append(f"  {'WRITE' if x['write'] else 'READ '} fn=0x{x['function']:X} site=0x{x['site']:X} {x['op']}")
    for name,refs in helper_callers.items():
        lines.append(f"HELPER {name}=0x{FOCUS[name]:X} callers={len(refs)}")
        for x in refs:lines.append(f"  fn=0x{x['caller']:X} site=0x{x['site']:X}")
    lines.append("")
    for f in functions:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        for x in f["global_refs"]:
            lines.append(f"  GLOBAL {'WRITE' if x['write'] else 'READ'} {x['name']} site=0x{x['site']:X} {x['op']}")
        for s in f["strings"]:
            lines.append(f"  RIPSTR 0x{s['site']:X} -> 0x{s['target']:X} {s['ascii']!r}")
        for x in f["calls"]:
            tf=x.get("target_function")
            lines.append(f"  {x['kind'].upper()} 0x{x['site']:X} -> "+
                         ("-" if tf is None else f"0x{tf:X}")+f" raw=0x{x['target']:X}")
        lines.append("  DISASM")
        for r in f["instructions"]:
            lines.append(f"    0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        lines.append("")
    lines.append("KEYWORD_STRINGS")
    for x in keyword_strings:
        lines.append(f"  0x{x['rva']:X} {x['text']!r}")
    lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("LUA_VFS_REGISTRY_TRACE_COMPLETE")
    print(" ".join(f"{k}_refs={len(v)}" for k,v in global_refs.items()))
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
