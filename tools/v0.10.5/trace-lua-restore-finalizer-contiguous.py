#!/usr/bin/env python3
"""Trace the real contiguous control flow of the Lua restore finaliser.

Runtime-function metadata incorrectly splits the logic beginning at 0x5A4240,
even though that code branches forward into 0x5A4353. The surrounding restore
sequence is:

  0x5A4370  stages restore data and writes client+0x70
  0x5A4240  finalises/transforms that staged value
  virtual +0x58 eventually reaches the restore consumer
  0x5A6C10  consumes client+0x70 as [u32 size][payload...]

This pass disassembles the raw contiguous 0x5A4240..0x5A436F region rather than
trusting unwind boundaries, follows all local branch targets in that region,
records external calls and relevant memory accesses, and includes nearby
0x5A4370 staging instructions for comparison.

Static/read-only only. No game launch, process attach, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FINALIZER_START=0x5A4240
FINALIZER_END=0x5A4370
STAGER_START=0x5A4370
STAGER_PREVIEW_END=0x5A4450
INTERESTING_DISPS={0x28,0x30,0x38,0x40,0x58,0x60,0x68,0x70,0x78,0x80}

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_restore_finalizer_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def decode_range(pe,md,start,end,OP_IMM,OP_MEM,RIP,AC_WRITE):
    off=pe.rva_to_file(start)
    if off is None:raise RuntimeError(f"RVA 0x{start:X} not mapped")
    raw=pe.data[off:off+(end-start)]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+start):
        rva=ins.address-IMAGE_BASE
        if rva>=end:break
        mem=[];imms=[]
        for idx,op in enumerate(getattr(ins,"operands",[])):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                      "index":md.reg_name(op.mem.index) if op.mem.index else None,
                      "disp":op.mem.disp,"size":op.size,"operand_index":idx,
                      "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:
                    item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(item)
        rows.append({"rva":rva,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,
                     "op_str":ins.op_str,"imms":imms,"mem":mem})
    return rows

def ascii_at(pe,rva,max_len=128):
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

def annotate(pe,rows,start,end):
    out=[]
    for row in rows:
        x=dict(row)
        local_branches=[];external_calls=[];refs=[];hits=[]
        if row["mnemonic"].startswith("j") or row["mnemonic"]=="call":
            for imm in row["imms"]:
                if isinstance(imm,int):
                    if start<=imm<end:
                        local_branches.append(imm)
                    elif row["mnemonic"]=="call":
                        fn=pe.function_for(imm)
                        external_calls.append({
                            "target":imm,
                            "target_function":fn["begin"] if fn else None,
                        })
        for m in row["mem"]:
            if m.get("disp") in INTERESTING_DISPS and m.get("base") not in (None,"rsp","rbp","rip"):
                hits.append({
                    "base":m.get("base"),"disp":m.get("disp"),"size":m.get("size"),
                    "write":m.get("write"),"op":row["op_str"]
                })
            rt=m.get("rip_target")
            if rt is not None:
                refs.append({"target":rt,"ascii":ascii_at(pe,rt)})
        x["local_branches"]=local_branches
        x["external_calls"]=external_calls
        x["interesting_mem"]=hits
        x["rip_refs"]=refs
        out.append(x)
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
    helper=load_helper();pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,AC_WRITE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    finalizer=annotate(pe,decode_range(pe,md,FINALIZER_START,FINALIZER_END,OP_IMM,OP_MEM,RIP,AC_WRITE),
                       FINALIZER_START,FINALIZER_END)
    stager=annotate(pe,decode_range(pe,md,STAGER_START,STAGER_PREVIEW_END,OP_IMM,OP_MEM,RIP,AC_WRITE),
                    STAGER_START,STAGER_PREVIEW_END)

    branch_targets=sorted({t for r in finalizer for t in r["local_branches"]})
    calls=[]
    for r in finalizer:
        for c in r["external_calls"]:
            calls.append({"site":r["rva"],**c})
    writes=[]
    for r in finalizer:
        for h in r["interesting_mem"]:
            if h["write"]:
                writes.append({"site":r["rva"],**h})

    report={
        "schema":1,
        "analysis":"lua_restore_finalizer_contiguous",
        "exe_sha256":digest,
        "finalizer_range":{"start":FINALIZER_START,"end":FINALIZER_END},
        "stager_preview_range":{"start":STAGER_START,"end":STAGER_PREVIEW_END},
        "branch_targets":branch_targets,
        "external_calls":calls,
        "interesting_writes":writes,
        "finalizer":finalizer,
        "stager_preview":stager,
        "safety":{"static_exe_read_only":True,"game_launched":False,
                  "process_accessed":False,"save_opened":False,
                  "save_written":False,"progression_written":False,
                  "game_files_written":False},
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - Lua restore finalizer contiguous trace",
        f"exe_sha256={digest}",
        f"finalizer=0x{FINALIZER_START:X}..0x{FINALIZER_END:X}",
        f"stager_preview=0x{STAGER_START:X}..0x{STAGER_PREVIEW_END:X}",
        "runtime-function metadata intentionally ignored for finalizer region",
        "",
        "FINALIZER CONTIGUOUS DISASSEMBLY",
    ]
    for r in finalizer:
        tags=[]
        if r["local_branches"]:
            tags.append("LOCAL->"+",".join(f"0x{x:X}" for x in r["local_branches"]))
        if r["external_calls"]:
            tags.append("CALL->"+",".join(
                f"0x{c['target']:X}/fn={('-' if c['target_function'] is None else f'0x{c['target_function']:X}')}"
                for c in r["external_calls"]))
        for h in r["interesting_mem"]:
            tags.append(("W" if h["write"] else "R")+f"[{h['base']}+0x{h['disp']:X}]")
        for rr in r["rip_refs"]:
            if rr["ascii"]:tags.append(f"STR={rr['ascii']!r}")
        suffix=("  ; "+" | ".join(tags)) if tags else ""
        lines.append(f"0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}{suffix}")

    lines+=["","STAGER PREVIEW"]
    for r in stager:
        tags=[]
        for h in r["interesting_mem"]:
            tags.append(("W" if h["write"] else "R")+f"[{h['base']}+0x{h['disp']:X}]")
        for rr in r["rip_refs"]:
            if rr["ascii"]:tags.append(f"STR={rr['ascii']!r}")
        suffix=("  ; "+" | ".join(tags)) if tags else ""
        lines.append(f"0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}{suffix}")

    lines+=["","SUMMARY",
            "branch_targets="+(",".join(f"0x{x:X}" for x in branch_targets) or "-"),
            "external_calls="+str(len(calls)),
            "interesting_writes="+str(len(writes)),
            "SAFETY static_exe_read_only=true game_launched=false process_accessed=false "
            "save_opened=false save_written=false progression_written=false game_files_written=false"]
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print("LUA_RESTORE_FINALIZER_CONTIGUOUS_TRACE_COMPLETE "
          f"branches={len(branch_targets)} calls={len(calls)} writes={len(writes)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
