#!/usr/bin/env python3
"""Classify the two read-side Lua intersections with staged save globals.

Targets:
  GetAppMasterVersion 0x783880
  GetLevelId          0x847F10
and save-pipeline context:
  0x66B650

For each target plus direct callees, emit exact disassembly, calls, RIP-relative
globals/strings, and memory accesses through rcx/rdx/r8/r9 so we can decide
whether the Lua handler performs arbitrary staged-record selection or only
returns fixed metadata.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGETS={
    "GetAppMasterVersion":0x783880,
    "GetLevelId":0x847F10,
    "SavePipelineContext":0x66B650,
}
STAGED_GLOBALS={
    "record_count":0x22C696C,
    "record_base":0x22C7170,
    "record_end_or_cursor":0x22C7194,
    "staged_aux_0":0x22C6938,
    "staged_aux_1":0x22C6940,
}
ARG_REGS={"rcx","rdx","r8","r9"}

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_read_intersection_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def ascii_at(pe,rva,max_len=220):
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

def disasm_fn(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    size=min(fn["end"]-fn["begin"],0x1800)
    raw=pe.data[off:off+size]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        imms=[]; mem=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                m={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "disp":op.mem.disp,"size":op.size,
                   "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:
                    m["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(m)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                     "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                     "imms":imms,"mem":mem})
    return rows

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

    nodes={}
    entries={}
    for label,rva in TARGETS.items():
        fn=pe.function_for(rva)
        if not fn: raise RuntimeError(f"no runtime function for {label} 0x{rva:X}")
        entries[label]=fn["begin"]
        q=deque([(fn["begin"],0)])
        seen=set()
        while q:
            b,depth=q.popleft()
            if b in seen or depth>1:continue
            seen.add(b)
            fn2=pe.function_for(b)
            if not fn2:continue
            rows=disasm_fn(pe,md,fn2,OP_IMM,OP_MEM,RIP,AC_WRITE)
            calls=[]; globals_hits=[]; strings=[]; arg_mem=[]
            for r in rows:
                for m in r["mem"]:
                    if m.get("base") in ARG_REGS:
                        arg_mem.append({"site":r["rva"],"write":m["write"],"base":m["base"],
                                        "index":m.get("index"),"disp":m["disp"],"size":m["size"],
                                        "op":r["op_str"]})
                    t=m.get("rip_target")
                    if t is not None:
                        for gname,gaddr in STAGED_GLOBALS.items():
                            if t==gaddr:
                                globals_hits.append({"name":gname,"site":r["rva"],"write":m["write"],"op":r["op_str"]})
                        s=ascii_at(pe,t)
                        if s:strings.append({"site":r["rva"],"target":t,"ascii":s})
                if r["mnemonic"] in ("call","jmp") and r["imms"]:
                    t=r["imms"][0]
                    if isinstance(t,int):
                        tf=pe.function_for(t)
                        calls.append({"site":r["rva"],"kind":r["mnemonic"],"target":t,
                                      "target_function":tf["begin"] if tf else None})
                        if r["mnemonic"]=="call" and tf and depth<1:
                            q.append((tf["begin"],depth+1))
            nodes[b]={"begin":b,"end":fn2["end"],"depth_from_some_entry":depth,
                      "instructions":rows,"calls":calls,"staged_global_hits":globals_hits,
                      "strings":strings,"arg_memory_accesses":arg_mem}

    result={
        "schema":1,"analysis":"lua_read_staged_intersection_semantics",
        "exe_sha256":digest,"targets":TARGETS,"entry_functions":entries,
        "nodes":[nodes[k] for k in sorted(nodes)],
        "safety":{"static_exe_read_only":True,"game_launched":False,
                  "process_accessed":False,"save_opened":False,"save_written":False,
                  "progression_written":False,"game_files_written":False},
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - read-side staged intersection semantics",
           f"exe_sha256={digest}",""]
    for label,b in entries.items():
        lines.append(f"ENTRY {label}=0x{b:X}")
    lines.append("")
    for b in sorted(nodes):
        n=nodes[b]
        lines.append(f"FUNCTION 0x{b:X}..0x{n['end']:X} depth={n['depth_from_some_entry']}")
        for x in n["staged_global_hits"]:
            lines.append(f"  STAGED_GLOBAL {'WRITE' if x['write'] else 'READ'} {x['name']} site=0x{x['site']:X} {x['op']}")
        for x in n["arg_memory_accesses"]:
            lines.append(f"  ARG_MEM {'WRITE' if x['write'] else 'READ'} site=0x{x['site']:X} base={x['base']} index={x['index']} disp={x['disp']} size={x['size']} {x['op']}")
        for s in n["strings"]:
            lines.append(f"  STRING 0x{s['site']:X} -> 0x{s['target']:X} {s['ascii']!r}")
        for x in n["calls"]:
            tf=x.get("target_function")
            lines.append(f"  {x['kind'].upper()} 0x{x['site']:X} -> "+("-" if tf is None else f"0x{tf:X}")+f" raw=0x{x['target']:X}")
        lines.append("  DISASM")
        for r in n["instructions"]:
            lines.append(f"    0x{r['rva']:08X} {r['bytes']:<22} {r['mnemonic']:<8} {r['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_READ_STAGED_INTERSECTION_TRACE_COMPLETE nodes={len(nodes)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
