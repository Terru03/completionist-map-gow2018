#!/usr/bin/env python3
"""Trace the restore pre-dispatch helpers around 0x4652B0.

The prior slot-11 scan identified 0x4652B0 as the closest restore-side
dispatcher in the Lua resource/client path. Immediately before its virtual
+0x58 call it invokes:
  0x5A4370(rdi, ..., r9=rbx)
  0x5A4240(rdi)

This static pass disassembles those helpers, their direct callers/callees,
captures client-like field accesses and RIP-relative data/string references,
and records the 0x4652B0 sequence in full.

No process attach, no game launch, no save access and no writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FOCUS={
    "restore_dispatch_candidate":0x4652B0,
    "pre_restore_helper_a":0x5A4370,
    "pre_restore_helper_b":0x5A4240,
    "base_slot11_restore":0x5A6C10,
    "client_ctor":0x5A6DD0,
    "backing_transfer":0x5A7720,
    "backing_pack":0x5A6270,
    "create_client":0x4654A0,
}
CLIENT_OFFSETS={0x58,0x60,0x68,0x70,0x78,0x80,0x88,0x90}

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("restore_predispatch_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def decode(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[]; imms=[]
        for i,op in enumerate(getattr(ins,"operands",[])):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                x={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "disp":op.mem.disp,"size":op.size,"operand_index":i,
                   "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:x["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(x)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms})
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

def ascii_at(pe,rva,max_len=160):
    off=pe.rva_to_file(rva)
    if off is None:return None
    b=pe.data[off:off+max_len]
    z=b.find(b"\x00")
    if z>=0:b=b[:z]
    if len(b)<4:return None
    try:s=b.decode("utf-8")
    except Exception:return None
    if not all(ch in "\r\n\t" or 32<=ord(ch)<127 for ch in s):return None
    return s

def field_hits(rows):
    out=[]
    for r in rows:
        for m in r["mem"]:
            if m.get("base") in (None,"rsp","rbp","rip"):continue
            if m.get("disp") not in CLIENT_OFFSETS:continue
            out.append({"site":r["rva"],"offset":m["disp"],"base":m["base"],
                        "size":m["size"],"write":m["write"],"op":r["op_str"]})
    return out

def rip_refs(pe,rows):
    out=[]
    for r in rows:
        for m in r["mem"]:
            t=m.get("rip_target")
            if t is None:continue
            out.append({"site":r["rva"],"target":t,"op":r["op_str"],
                        "ascii":ascii_at(pe,t)})
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
    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE)
        if not rows:continue
        decoded[fn["begin"]]=rows
        cs=direct_calls(pe,rows); calls[fn["begin"]]=cs
        for c in cs:
            tf=c.get("target_function")
            if tf is not None:callers[tf].append({"caller":fn["begin"],"site":c["site"]})

    selected=set()
    for rva in FOCUS.values():
        fn=pe.function_for(rva)
        if fn:selected.add(fn["begin"])
    for rva in (0x5A4370,0x5A4240,0x4652B0):
        fn=pe.function_for(rva)
        if not fn:continue
        b=fn["begin"]
        for c in calls.get(b,[]):
            if c.get("target_function") is not None:selected.add(c["target_function"])
        for c in callers.get(b,[]):selected.add(c["caller"])

    funcs=[]
    for begin in sorted(selected):
        fn=pe.function_for(begin)
        if not fn:continue
        rows=decoded.get(begin,[])
        funcs.append({"begin":begin,"end":fn["end"],"calls":calls.get(begin,[]),
                      "callers":callers.get(begin,[]),"field_hits":field_hits(rows),
                      "rip_refs":rip_refs(pe,rows),"instructions":rows})

    report={"schema":1,"analysis":"lua_restore_pre_dispatch_helpers",
            "exe_sha256":digest,"focus":FOCUS,"functions":funcs,
            "safety":{"static_exe_read_only":True,"game_launched":False,
                      "process_accessed":False,"save_opened":False,
                      "save_written":False,"progression_written":False,
                      "game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    names=defaultdict(list)
    for name,rva in FOCUS.items():
        fn=pe.function_for(rva)
        if fn:names[fn["begin"]].append(name)
    lines=["Completionist Map - Lua restore pre-dispatch helper trace",
           f"exe_sha256={digest}",""]
    for f in funcs:
        labs=",".join(names.get(f["begin"],[])) or "-"
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} labels={labs}")
        for c in f["callers"]:
            lines.append(f"  CALLER 0x{c['caller']:X} site=0x{c['site']:X}")
        for c in f["calls"]:
            tf=c.get("target_function")
            lines.append(f"  {c['kind'].upper()} 0x{c['site']:X} -> "
                         f"{'-' if tf is None else f'0x{tf:X}'} raw=0x{c['target']:X}")
        for h in f["field_hits"]:
            mode="WRITE" if h["write"] else "READ"
            lines.append(f"  {mode} 0x{h['site']:X} +0x{h['offset']:X} size={h['size']} "
                         f"base={h['base']} {h['op']}")
        for rr in f["rip_refs"]:
            if rr["ascii"]:
                lines.append(f"  RIPSTR 0x{rr['site']:X} -> 0x{rr['target']:X} {rr['ascii']!r}")
        lines.append("  DISASM")
        for r in f["instructions"]:
            lines.append(f"    0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false "
                 "save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_RESTORE_PRE_DISPATCH_HELPERS_TRACE_COMPLETE functions={len(funcs)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
