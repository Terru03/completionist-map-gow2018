#!/usr/bin/env python3
"""Trace LuaSubObjectClient SoftSave dirty-bit consumers in GoW 2018.

Read-only, version-locked static analysis. The proven game.SubObject.SoftSave
binding resolves the current native subobject client and executes:

    or byte ptr [client + 0x58], 0x10

This pass:
- disassembles the client resolver around RVA 0x5443E0 even if PE runtime
  function metadata is incomplete;
- scans executable sections for accesses to displacement +0x58;
- ranks functions that test/clear/set bit 0x10 at that offset;
- records nearby calls, branches, RIP strings/data, and direct xrefs to the
  client resolver.

No game launch, process access, save access, or game-file writes.
"""
from __future__ import annotations

import argparse, hashlib, importlib.util, json, sys, string
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
CLIENT_RESOLVER=0x5443E0
SOFTSAVE_BINDING=0x948280
TARGET_DISP=0x58
TARGET_BIT=0x10


def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softsave_flag_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def ascii_at(pe,rva,max_len=220):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    end=raw.find(b"\0")
    if end<0:end=len(raw)
    raw=raw[:end]
    if len(raw)<3:return None
    if all(32<=b<127 for b in raw):
        try:return raw.decode("ascii")
        except Exception:return None
    return None


def function_rows(pe,md,begin,end,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(begin)
    if off is None:return []
    raw=pe.data[off:off+(end-begin)]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+begin):
        row={"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str}
        refs=[]
        imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                item={"disp":op.mem.disp,"size":op.size}
                if op.mem.base==RIP:
                    rv=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                    item["rip_rva"]=rv
                    s=ascii_at(pe,rv)
                    if s:item["ascii"]=s
                refs.append(item)
        if refs:row["mem"]=refs
        if imms:row["immediates"]=imms
        out.append(row)
    return out


def contiguous(pe,md,start,size,OP_IMM,OP_MEM,RIP):
    return function_rows(pe,md,start,start+size,OP_IMM,OP_MEM,RIP)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()

    exe=args.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"SHA256 mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper(); pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE); md.detail=True

    resolver_fn=pe.function_for(CLIENT_RESOLVER)
    if resolver_fn:
        resolver={"begin":resolver_fn["begin"],"end":resolver_fn["end"]}
        resolver["instructions"]=function_rows(pe,md,resolver_fn["begin"],resolver_fn["end"],OP_IMM,OP_MEM,RIP)
    else:
        resolver={"begin":CLIENT_RESOLVER,"end":CLIENT_RESOLVER+0x500}
        resolver["instructions"]=contiguous(pe,md,CLIENT_RESOLVER,0x500,OP_IMM,OP_MEM,RIP)

    # Disassemble all executable sections once and collect +0x58 accesses.
    hits=[]
    direct_resolver_xrefs=[]
    by_function=defaultdict(list)

    for sec in pe.sections:
        if not sec.get("exec") or sec["rawsize"]<=0: continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["rawsize"]]
        for ins in md.disasm(raw,IMAGE_BASE+sec["rva"]):
            rva=ins.address-IMAGE_BASE
            target_mem=False
            imms=[]
            resolver_ref=False
            for op in getattr(ins,"operands",[]):
                if op.type==OP_MEM and op.mem.disp==TARGET_DISP and op.mem.base!=RIP:
                    target_mem=True
                elif op.type==OP_IMM:
                    val=op.imm
                    if IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
                        rv=val-IMAGE_BASE
                        imms.append(rv)
                        if rv==CLIENT_RESOLVER:resolver_ref=True
                    else:
                        imms.append(val)
            if resolver_ref and ins.mnemonic in ("call","jmp"):
                direct_resolver_xrefs.append({"site":rva,"mnemonic":ins.mnemonic,"op_str":ins.op_str})

            if not target_mem: continue
            fn=pe.function_for(rva)
            begin=fn["begin"] if fn else rva
            score=0
            text=(ins.mnemonic+" "+ins.op_str).lower()
            if TARGET_BIT in [x for x in imms if isinstance(x,int)]: score+=4
            if ins.mnemonic in ("test","and","or","xor","cmp"): score+=2
            if "0x10" in text: score+=5
            if ins.mnemonic in ("and","test") and "0x10" in text: score+=4
            if ins.mnemonic=="or" and "0x10" in text: score+=1
            row={"site":rva,"function":begin,"mnemonic":ins.mnemonic,"op_str":ins.op_str,"bytes":ins.bytes.hex(),"score":score}
            hits.append(row);by_function[begin].append(row)

    candidates=[]
    for begin,rows in by_function.items():
        fn=pe.function_for(begin)
        if fn is None:
            end=begin+0x180
        else:
            end=fn["end"]
        inst=function_rows(pe,md,begin,end,OP_IMM,OP_MEM,RIP)
        strings=[]
        calls=[]
        for row in inst:
            for mem in row.get("mem",[]):
                if "ascii" in mem:
                    strings.append({"rva":mem["rip_rva"],"text":mem["ascii"],"site":row["rva"]})
            if row["mnemonic"] in ("call","jmp") and row.get("immediates"):
                calls.append({"site":row["rva"],"kind":row["mnemonic"],"target":row["immediates"][0]})
        score=sum(x["score"] for x in rows)
        if begin==SOFTSAVE_BINDING: score-=3
        candidates.append({
            "function":begin,"end":end,"score":score,
            "flag_hits":rows,"strings":strings,"control_edges":calls,
            "instructions":inst,
        })
    candidates.sort(key=lambda x:(-x["score"],x["function"]))

    report={
        "schema":1,
        "analysis":"subobject_softsave_dirty_bit_consumers",
        "exe_sha256":digest,
        "client_resolver_rva":CLIENT_RESOLVER,
        "softsave_binding_rva":SOFTSAVE_BINDING,
        "dirty_field_offset":TARGET_DISP,
        "dirty_bit":TARGET_BIT,
        "resolver":resolver,
        "direct_client_resolver_xrefs":direct_resolver_xrefs,
        "flag_access_count":len(hits),
        "candidate_function_count":len(candidates),
        "candidates":candidates,
        "safety":{
            "static_exe_read_only":True,"game_launched":False,"process_accessed":False,
            "save_opened":False,"save_written":False,"progression_written":False,
            "game_files_written":False,
        }
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - SubObject SoftSave dirty-bit consumer trace",
        f"exe_sha256={digest}",
        f"client_resolver=0x{CLIENT_RESOLVER:X}",
        f"dirty_field=+0x{TARGET_DISP:X} dirty_bit=0x{TARGET_BIT:X}",
        f"flag_accesses={len(hits)} candidate_functions={len(candidates)} resolver_xrefs={len(direct_resolver_xrefs)}",
        "",
        "TOP DIRTY-BIT CANDIDATES",
    ]
    for c in candidates[:30]:
        lines.append(f"FUNCTION 0x{c['function']:X}..0x{c['end']:X} score={c['score']} hits={len(c['flag_hits'])}")
        for h in c["flag_hits"]:
            lines.append(f"  HIT 0x{h['site']:X} {h['bytes']:<20} {h['mnemonic']} {h['op_str']} score={h['score']}")
        for s in c["strings"][:12]:
            lines.append(f"  STR 0x{s['rva']:X} {s['text']}")
        for e in c["control_edges"][:30]:
            lines.append(f"  EDGE 0x{e['site']:X} {e['kind']} -> 0x{e['target']:X}")
        lines.append("")

    lines.extend(["CLIENT RESOLVER DISASSEMBLY"])
    for row in resolver["instructions"]:
        suffix=[]
        for mem in row.get("mem",[]):
            if "ascii" in mem:suffix.append(f"ascii={mem['ascii']!r}")
        lines.append(f"0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"+((" ; "+" | ".join(suffix)) if suffix else ""))

    lines.extend(["","DIRECT XREFS TO CLIENT RESOLVER"])
    for x in direct_resolver_xrefs:
        lines.append(f"0x{x['site']:X} {x['mnemonic']} {x['op_str']}")

    lines.extend(["","SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"SUBOBJECT_DIRTY_BIT_TRACE_COMPLETE flagAccesses={len(hits)} candidates={len(candidates)} resolverXrefs={len(direct_resolver_xrefs)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
