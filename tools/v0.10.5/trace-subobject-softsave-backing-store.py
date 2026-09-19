#!/usr/bin/env python3
"""Trace GoW 2018 game.SubObject.SoftSave native backing-store flow.

Version-locked, read-only static analysis of the supported GoW.exe.
Starts at the proven Lua binding RVA 0x948280, disassembles its runtime
function, follows direct executable callees to depth 2, and records:
- calls/jumps;
- RIP-relative data/string references;
- references to known persistence strings and Lua callbacks;
- likely global/static state addresses touched by the call tree.

No game launch, process access, save access, or writes to game files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import string
import sys

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
ROOT_RVA=0x948280
MAX_DEPTH=2
MAX_FUNCTIONS=80


def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softsave_pe_helper",p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper {p}")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():
        sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def ascii_at(pe,rva:int,max_len:int=240):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    end=raw.find(b"\0")
    if end<0:end=len(raw)
    chunk=raw[:end]
    if len(chunk)<3:return None
    if all(chr(b) in string.printable and b not in (10,13,9,11,12) for b in chunk):
        try:return chunk.decode("ascii")
        except Exception:return None
    return None


def utf16_at(pe,rva:int,max_chars:int=120):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_chars*2]
    end=None
    for i in range(0,len(raw)-1,2):
        if raw[i:i+2]==b"\0\0":
            end=i;break
    if end is None:end=len(raw)//2*2
    if end<6:return None
    try:
        s=raw[:end].decode("utf-16le")
    except Exception:return None
    if all(ch in string.printable for ch in s):
        return s
    return None


def main()->int:
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
    helper=load_helper()
    pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    queue=[(ROOT_RVA,0,"SoftSave")]
    visited=set()
    functions=[]
    globals_touched={}
    strings_found={}
    edges=[]

    while queue and len(functions)<MAX_FUNCTIONS:
        target,depth,via=queue.pop(0)
        fn=pe.function_for(target)
        if fn is None:
            continue
        begin=fn["begin"]
        if begin in visited:continue
        visited.add(begin)
        off=pe.rva_to_file(begin)
        if off is None:continue
        raw=pe.data[off:off+fn["end"]-begin]
        rows=[]
        callees=[]
        for ins in md.disasm(raw,IMAGE_BASE+begin):
            row={
                "rva":ins.address-IMAGE_BASE,
                "bytes":ins.bytes.hex(),
                "mnemonic":ins.mnemonic,
                "op_str":ins.op_str,
            }
            refs=[]
            for op in getattr(ins,"operands",[]):
                if op.type==OP_IMM:
                    val=op.imm
                    if IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
                        rv=val-IMAGE_BASE
                        refs.append({"kind":"imm","rva":rv})
                        if ins.mnemonic in ("call","jmp"):
                            sec=pe.section_for_rva(rv)
                            if sec and sec.get("exec"):
                                callees.append(rv)
                                edges.append({"from_function":begin,"site":row["rva"],"kind":ins.mnemonic,"to":rv})
                elif op.type==OP_MEM and op.mem.base==RIP:
                    rv=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                    item={"kind":"rip","rva":rv}
                    s=ascii_at(pe,rv)
                    u=utf16_at(pe,rv)
                    if s is not None:
                        item["ascii"]=s
                        strings_found[f"0x{rv:X}"]=s
                    if u is not None:
                        item["utf16"]=u
                        strings_found[f"0x{rv:X}"]=u
                    refs.append(item)
                    globals_touched.setdefault(f"0x{rv:X}",[]).append({
                        "function":begin,"site":row["rva"],"mnemonic":ins.mnemonic,"op_str":ins.op_str
                    })
            if refs:row["refs"]=refs
            rows.append(row)

        functions.append({
            "begin":begin,"end":fn["end"],"size":fn["end"]-begin,
            "depth":depth,"via":via,"instructions":rows,
            "direct_callees":sorted(set(callees)),
        })
        if depth<MAX_DEPTH:
            for callee in sorted(set(callees)):
                if pe.function_for(callee) is not None:
                    queue.append((callee,depth+1,f"call_from_0x{begin:X}"))

    terms=("save","soft","checkpoint","restore","subobject","pickle","serialize","lua","wad","level","object")
    interesting_strings={k:v for k,v in strings_found.items() if any(t in v.lower() for t in terms)}

    report={
        "schema":1,
        "analysis":"subobject_softsave_backing_store_trace",
        "exe_sha256":digest,
        "root_rva":ROOT_RVA,
        "max_depth":MAX_DEPTH,
        "function_count":len(functions),
        "functions":functions,
        "control_edges":edges,
        "rip_globals":globals_touched,
        "interesting_strings":interesting_strings,
        "safety":{
            "static_exe_read_only":True,
            "game_launched":False,
            "process_accessed":False,
            "save_opened":False,
            "save_written":False,
            "progression_written":False,
            "game_files_written":False,
        },
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - SubObject SoftSave backing-store trace",
        f"exe_sha256={digest}",
        f"root=0x{ROOT_RVA:X}",
        f"functions={len(functions)} depth={MAX_DEPTH}",
        "",
        "INTERESTING STRINGS",
    ]
    if interesting_strings:
        for k,v in sorted(interesting_strings.items()):
            lines.append(f"{k} {v}")
    else:
        lines.append("none")

    lines.extend(["","FUNCTIONS"])
    for fn in functions:
        lines.append(f"FUNCTION 0x{fn['begin']:X}..0x{fn['end']:X} depth={fn['depth']} via={fn['via']}")
        for row in fn["instructions"]:
            suffix=""
            refs=row.get("refs",[])
            if refs:
                bits=[]
                for ref in refs:
                    bit=f"{ref['kind']}->0x{ref['rva']:X}"
                    if "ascii" in ref:bit+=f" ascii={ref['ascii']!r}"
                    if "utf16" in ref:bit+=f" utf16={ref['utf16']!r}"
                    bits.append(bit)
                suffix=" ; "+" | ".join(bits)
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}{suffix}")
        lines.append("")

    lines.extend(["CONTROL EDGES"])
    for e in edges:
        lines.append(f"0x{e['from_function']:X}+ site=0x{e['site']:X} {e['kind']} -> 0x{e['to']:X}")

    lines.extend(["","RIP/GLOBAL REFERENCES"])
    for addr,uses in sorted(globals_touched.items()):
        lines.append(f"{addr} uses={len(uses)}")
        for u in uses[:20]:
            lines.append(f"  fn=0x{u['function']:X} site=0x{u['site']:X} {u['mnemonic']} {u['op_str']}")

    lines.extend([
        "",
        "SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false "
        "save_written=false progression_written=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"SUBOBJECT_SOFTSAVE_BACKING_STORE_TRACE_COMPLETE functions={len(functions)} edges={len(edges)} globals={len(globals_touched)} strings={len(interesting_strings)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
