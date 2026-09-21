#!/usr/bin/env python3
"""Trace the native lifecycle of WAD+0xEE18 staged-record bindings.

Static/read-only analysis for the pinned God of War executable and existing
research index. The remaining Raven authority question is whether a WAD absent
from the current 0xA8 staged table can be proven never-persisted, or whether its
record was retired to another backing store.

This probe:
  * scans executable section bytes for the disp32 encodings of +/-0xEE18 and
    nearby WAD fields, then validates candidates with Capstone;
  * classifies exact +0xEE18 reads/writes from validated instructions;
  * emits full enclosing functions for every +0xEE18/-0xEE18 hit;
  * records callers/callees and staging-global references;
  * highlights direct writes to the binding field and functions that both touch
    the binding and the 0xA8 staged-record globals.

No game launch, process access, save access, or writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
BINDING=0xEE18
RELATED_DISPS=(-0xEE20,-0xEE18,0xEE10,0xEE18,0xEE20,0xEE28)
STAGING_GLOBALS={
    "record_count":0x22C696C,
    "record_base":0x22C7170,
    "record_key":0x22C7194,
    "payload_size":0x22C6938,
    "payload_base":0x22C6940,
}

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-checkpoint-restore-bridge.py")
    spec=importlib.util.spec_from_file_location("wad_binding_pe",p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def load_capstone(path:Path):
    sys.path.insert(0,str(path))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    md=Cs(CS_ARCH_X86,CS_MODE_64)
    md.detail=True
    return md,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def fn_for(con,addr:int):
    r=con.execute(
        "SELECT begin,end,size,section FROM functions "
        "WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)
    ).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def rows(cur):
    names=[x[0] for x in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]

def dis(md,pe,start,end,opimm,opmem,rip):
    out=[]
    for ins in md.disasm(pe.read(start,end-start),IMAGE_BASE+start):
        row={
            "rva":ins.address-IMAGE_BASE,
            "bytes":ins.bytes.hex(),
            "mnemonic":ins.mnemonic,
            "op_str":ins.op_str,
            "mem":[],
            "rip_targets":[],
            "immediates":[],
        }
        for idx,op in enumerate(ins.operands):
            if op.type==opimm:
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+0x80000000:
                    v-=IMAGE_BASE
                row["immediates"].append(v)
            elif op.type==opmem:
                m={
                    "operand_index":idx,
                    "base":int(op.mem.base),
                    "index":int(op.mem.index),
                    "scale":int(op.mem.scale),
                    "disp":int(op.mem.disp),
                    "access":int(getattr(op,"access",0)),
                }
                row["mem"].append(m)
                if op.mem.base==rip:
                    row["rip_targets"].append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
        out.append(row)
    return out

def is_write(access)->bool:
    try:
        return bool(int(access)&2)
    except Exception:
        return "w" in str(access).lower()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--capstone-path",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    digest=sha256_file(a.exe).lower()
    if digest!=EXPECTED_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {digest}")

    helper=load_pe()
    pe=helper.PE(a.exe.read_bytes())
    md,opimm,opmem,rip=load_capstone(a.capstone_path)
    con=sqlite3.connect(f"file:{a.db.as_posix()}?mode=ro",uri=True)
    try:
        # The research index deliberately omits many large structure
        # displacements from mem_refs. Locate candidate functions directly from
        # the executable bytes instead: every +/-0xEE18 memory operand uses a
        # disp32 encoding, so searching the executable sections for those
        # little-endian signed values is lossless for this field. Candidates are
        # then validated by full Capstone disassembly of the enclosing function.
        encoded={d:int(d & 0xffffffff).to_bytes(4,"little") for d in RELATED_DISPS}
        raw_hits=[]
        candidate_fns=set()
        for sec_name,vaddr,vsize,rsize,roff in pe.sections:
            if sec_name!=".text":
                continue
            blob=pe.data[roff:roff+rsize]
            for disp,needle in encoded.items():
                pos=0
                while True:
                    idx=blob.find(needle,pos)
                    if idx<0:
                        break
                    rva=vaddr+idx
                    fn=fn_for(con,rva)
                    raw_hits.append({
                        "section":sec_name,
                        "disp":disp,
                        "rva":rva,
                        "function":fn["begin"] if fn else None,
                    })
                    if fn:
                        candidate_fns.add(fn["begin"])
                    pos=idx+1

        refs=[]
        exact=[]
        functions=[]
        for begin in sorted(candidate_fns):
            fn=fn_for(con,begin)
            if not fn:
                continue
            instructions=dis(md,pe,fn["begin"],fn["end"],opimm,opmem,rip)
            related_ins=[]
            binding_ins=[]
            for x in instructions:
                for m in x["mem"]:
                    if m["disp"] in RELATED_DISPS:
                        row={
                            "site":x["rva"],
                            "src_fn":fn["begin"],
                            "mnemonic":x["mnemonic"],
                            "op_str":x["op_str"],
                            "operand_index":m["operand_index"],
                            "base":m["base"],
                            "idx":m["index"],
                            "scale":m["scale"],
                            "disp":m["disp"],
                            "access":m["access"],
                            "bytes":x["bytes"],
                        }
                        refs.append(row)
                        related_ins.append(x)
                        if m["disp"]==BINDING:
                            exact.append(row)
                    if m["disp"] in (-BINDING,BINDING):
                        binding_ins.append(x)
            if not related_ins:
                continue
            global_hits=[]
            for x in instructions:
                names=[
                    name for name,target in STAGING_GLOBALS.items()
                    if target in x["rip_targets"]
                ]
                if names:
                    global_hits.append({"instruction":x,"globals":names})
            callers=rows(con.execute(
                "SELECT site,src_fn,kind,dest,target_fn FROM edges "
                "WHERE target_fn=? ORDER BY site",(fn["begin"],)
            ))
            callees=rows(con.execute(
                "SELECT site,kind,dest,target_fn FROM edges "
                "WHERE src_fn=? ORDER BY site",(fn["begin"],)
            ))
            functions.append({
                "function":fn,
                "binding_instructions":binding_ins,
                "staging_global_hits":global_hits,
                "touches_staging_globals":bool(global_hits),
                "callers":callers,
                "callees":callees,
                "instructions":instructions,
            })

        write_refs=[r for r in exact if is_write(r["access"])]
        read_refs=[r for r in exact if not is_write(r["access"])]
        hit_fns=sorted(set(r["src_fn"] for r in refs))

        # Also list every indexed source function that references the main
        # staged globals. This helps identify a bind function even if it writes
        # +0xEE18 indirectly after taking the field address.
        global_refs={}
        global_fns=set()
        for name,target in STAGING_GLOBALS.items():
            rr=rows(con.execute(
                "SELECT site,src_fn,mnemonic,target FROM rip_refs "
                "WHERE target=? ORDER BY site",(target,)
            ))
            global_refs[name]=rr
            global_fns.update(x["src_fn"] for x in rr)

        overlap=sorted(set(hit_fns)&global_fns)
        result={
            "schema":1,
            "analysis":"staged_wad_record_binding",
            "exe_sha256":digest,
            "binding_offset":BINDING,
            "related_displacements":list(RELATED_DISPS),
            "raw_disp32_hit_count":len(raw_hits),
            "raw_disp32_hits":raw_hits,
            "validated_related_ref_count":len(refs),
            "exact_binding_ref_count":len(exact),
            "exact_binding_write_count":len(write_refs),
            "exact_binding_read_count":len(read_refs),
            "exact_binding_writes":write_refs,
            "exact_binding_reads":read_refs,
            "functions":functions,
            "staging_global_refs":global_refs,
            "binding_and_staging_overlap_functions":overlap,
            "safety":{
                "static_only":True,
                "game_launched":False,
                "process_opened":False,
                "save_opened":False,
                "process_memory_written":False,
                "save_written":False,
                "progression_written":False,
                "game_files_written":False,
            },
        }
    finally:
        con.close()

    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=[
        "Completionist Map - staged WAD record binding trace",
        f"exe_sha256={digest}",
        "mode=static read-only",
        f"binding_offset=0x{BINDING:X}",
        f"raw_disp32_hits={len(raw_hits)} validated_related_refs={len(refs)} "
        f"exact_binding_refs={len(exact)} "
        f"writes={len(write_refs)} reads={len(read_refs)}",
        "",
        "EXACT +0xEE18 WRITES",
    ]
    if not write_refs:
        L.append("  none validated")
    for r in write_refs:
        L.append(
            f"  site=0x{r['site']:X} fn=0x{r['src_fn']:X} "
            f"{r['mnemonic']} access={r['access']} base={r['base']} "
            f"index={r['idx']} scale={r['scale']}"
        )
    L+=["","EXACT +0xEE18 READS"]
    for r in read_refs:
        L.append(
            f"  site=0x{r['site']:X} fn=0x{r['src_fn']:X} "
            f"{r['mnemonic']} access={r['access']}"
        )
    L+=["","BINDING + STAGING GLOBAL OVERLAP"]
    for fn in overlap:
        L.append(f"  0x{fn:X}")

    L+=["","FULL HIT FUNCTIONS"]
    for item in functions:
        fn=item["function"]
        L.append(
            f"\nFUNCTION 0x{fn['begin']:X}..0x{fn['end']:X} size={fn['size']} "
            f"touchesStaging={str(item['touches_staging_globals']).lower()}"
        )
        if item["callers"]:
            L.append("  CALLERS")
            for x in item["callers"][:80]:
                L.append(
                    f"    site=0x{x['site']:X} src=0x{x['src_fn']:X} "
                    f"kind={x['kind']} dest={x['dest']} target={x['target_fn']}"
                )
        if item["callees"]:
            L.append("  CALLEES")
            for x in item["callees"][:120]:
                L.append(
                    f"    site=0x{x['site']:X} kind={x['kind']} "
                    f"dest={x['dest']} target={x['target_fn']}"
                )
        for ins in item["instructions"]:
            marks=[]
            for m in ins["mem"]:
                if m["disp"]==BINDING:
                    marks.append("BINDING+0xEE18")
                elif m["disp"]==-BINDING:
                    marks.append("LEA-0xEE18")
            for t in ins["rip_targets"]:
                for name,target in STAGING_GLOBALS.items():
                    if t==target:
                        marks.append("GLOBAL="+name)
            mark=(" ; "+" ".join(marks)) if marks else ""
            L.append(
                f"  0x{ins['rva']:08X} {ins['bytes']:<20} "
                f"{ins['mnemonic']:<8} {ins['op_str']}{mark}"
            )

    L+=["","STAGING GLOBAL REFS"]
    for name,target in STAGING_GLOBALS.items():
        rr=global_refs[name]
        L.append(f"  {name}=0x{target:X} refs={len(rr)}")
        for x in rr[:120]:
            L.append(
                f"    site=0x{x['site']:X} fn=0x{x['src_fn']:X} {x['mnemonic']}"
            )
    L+=["","SAFETY static_only=true game_launched=false process_opened=false "
        "save_opened=false process_memory_written=false save_written=false "
        "progression_written=false game_files_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")

    print(
        "STAGED_WAD_RECORD_BINDING_TRACE_COMPLETE "
        f"refs={len(exact)} writes={len(write_refs)} reads={len(read_refs)} "
        f"overlap={len(overlap)}"
    )
    return 0

if __name__=="__main__":
    raise SystemExit(main())
