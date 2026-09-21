#!/usr/bin/env python3
"""Trace existing Lua-native bindings against proven staged Raven authority.

Targets only the already-registered read/query candidates:
- ResolveGameObject
- GetRefBool/GetRefFloat/GetRefInt/GetRefString
- LoadCheck

For each handler and one-hop direct callees/callers, record:
- direct calls/jumps;
- RIP-relative references to the proven staged WAD globals;
- WAD +0xEE18 binding accesses;
- references/calls into the proven staged-record owner/restore functions;
- printable strings.

Static/read-only only: no game launch, process attach, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000

TARGETS={
    "ResolveGameObject":0x84F750,
    "GetRefBool":0x845700,
    "GetRefFloat":0x8456E0,
    "GetRefInt":0x8456C0,
    "GetRefString":0x8456A0,
    "LoadCheck":0x84E880,
}

STAGED_GLOBALS={
    "record_count":0x22C696C,
    "record_base":0x22C7170,
    "record_end_or_cursor":0x22C7194,
    "staged_aux_0":0x22C6938,
    "staged_aux_1":0x22C6940,
}

KNOWN_STAGED_FUNCTIONS={
    "staged_lookup_or_writer":0x82C820,
    "staged_related":0x82CC0C,
    "staged_related_2":0x82B250,
    "staged_restore_rebuild":0x82CF00,
    "wad_bind":0x673A30,
    "wad_restore_load":0x673D00,
    "wad_unbind":0x676CC0,
    "record_append_by_name":0x67B830,
    "record_reset":0x671AD0,
}

WAD_BINDING_DISP=0xEE18

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_persisted_ref_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def ascii_at(pe,rva,max_len=200):
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
                row={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                     "index":md.reg_name(op.mem.index) if op.mem.index else None,
                     "disp":op.mem.disp,"size":op.size,
                     "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:
                    row["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(row)
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
    for fn in pe.runtime_functions:
        rows=decode(pe,md,fn,OP_IMM,OP_MEM,RIP,AC_WRITE)
        if not rows:continue
        b=fn["begin"]; decoded[b]=rows
        cs=direct_calls(pe,rows); calls[b]=cs
        for x in cs:
            tf=x.get("target_function")
            if tf is not None:callers[tf].append({"caller":b,"site":x["site"]})

    selected=set()
    labels=defaultdict(list)
    for name,rva in TARGETS.items():
        fn=pe.function_for(rva)
        if fn:
            selected.add(fn["begin"]); labels[fn["begin"]].append(name)

    # one hop only
    roots=list(selected)
    for b in roots:
        for x in calls.get(b,[]):
            tf=x.get("target_function")
            if tf is not None:selected.add(tf)
        for x in callers.get(b,[]):selected.add(x["caller"])

    staged_fn_begins={}
    for name,rva in KNOWN_STAGED_FUNCTIONS.items():
        fn=pe.function_for(rva)
        staged_fn_begins[name]=fn["begin"] if fn else None

    functions=[]
    any_staged_touch=False
    for b in sorted(selected):
        fn=pe.function_for(b)
        if not fn:continue
        rows=decoded.get(b,[])
        globals_hits=[]; binding_hits=[]; strings=[]; staged_calls=[]
        for r in rows:
            for m in r["mem"]:
                if abs(int(m.get("disp",0)))==WAD_BINDING_DISP and m.get("base") not in (None,"rip","rsp","rbp"):
                    binding_hits.append({"site":r["rva"],"write":m["write"],"base":m["base"],
                                         "disp":m["disp"],"op":r["op_str"]})
                t=m.get("rip_target")
                if t is not None:
                    for name,g in STAGED_GLOBALS.items():
                        if t==g:
                            globals_hits.append({"name":name,"site":r["rva"],"write":m["write"],
                                                 "op":r["op_str"]})
                    s=ascii_at(pe,t)
                    if s:strings.append({"site":r["rva"],"target":t,"ascii":s})
            if r["mnemonic"] in ("call","jmp") and r["imms"]:
                t=r["imms"][0]
                tf=pe.function_for(t) if isinstance(t,int) else None
                tb=tf["begin"] if tf else None
                for name,kb in staged_fn_begins.items():
                    if kb is not None and tb==kb:
                        staged_calls.append({"name":name,"site":r["rva"],"target_function":tb})
        touch=bool(globals_hits or binding_hits or staged_calls)
        any_staged_touch=any_staged_touch or touch
        functions.append({
            "begin":b,"end":fn["end"],"labels":labels.get(b,[]),
            "calls":calls.get(b,[]),"callers":callers.get(b,[]),
            "staged_global_hits":globals_hits,"wad_binding_hits":binding_hits,
            "known_staged_calls":staged_calls,"strings":strings,
            "touches_proven_staged_authority":touch,
            "instructions":rows,
        })

    result={
        "schema":1,
        "analysis":"lua_persisted_reference_bindings",
        "exe_sha256":digest,
        "targets":TARGETS,
        "staged_globals":STAGED_GLOBALS,
        "known_staged_functions":KNOWN_STAGED_FUNCTIONS,
        "selected_function_count":len(functions),
        "any_staged_touch":any_staged_touch,
        "functions":functions,
        "safety":{"static_exe_read_only":True,"game_launched":False,
                  "process_accessed":False,"save_opened":False,"save_written":False,
                  "progression_written":False,"game_files_written":False},
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - Lua persisted reference binding trace",
        f"exe_sha256={digest}",
        f"selected_function_count={len(functions)}",
        f"any_staged_touch={str(any_staged_touch).lower()}",
        "",
    ]
    for f in functions:
        labs=",".join(f["labels"]) or "-"
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} labels={labs} touches_staged={str(f['touches_proven_staged_authority']).lower()}")
        for x in f["staged_global_hits"]:
            lines.append(f"  STAGED_GLOBAL {'WRITE' if x['write'] else 'READ'} {x['name']} site=0x{x['site']:X} {x['op']}")
        for x in f["wad_binding_hits"]:
            lines.append(f"  WAD_BINDING {'WRITE' if x['write'] else 'READ'} site=0x{x['site']:X} base={x['base']} disp=0x{x['disp']:X} {x['op']}")
        for x in f["known_staged_calls"]:
            lines.append(f"  STAGED_CALL {x['name']} site=0x{x['site']:X} -> 0x{x['target_function']:X}")
        for s in f["strings"]:
            lines.append(f"  STRING 0x{s['site']:X} -> 0x{s['target']:X} {s['ascii']!r}")
        for x in f["calls"]:
            tf=x.get("target_function")
            lines.append(f"  {x['kind'].upper()} 0x{x['site']:X} -> "+("-" if tf is None else f"0x{tf:X}")+f" raw=0x{x['target']:X}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_PERSISTED_REFERENCE_BINDINGS_TRACE_COMPLETE selected_functions={len(functions)} any_staged_touch={str(any_staged_touch).lower()}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
