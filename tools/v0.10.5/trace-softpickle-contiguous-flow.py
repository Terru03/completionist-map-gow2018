#!/usr/bin/env python3
"""Trace real contiguous control flow for GoW __SoftPickleTable selector helpers.

PE runtime-function metadata splits these routines at incorrect unwind
boundaries. This pass ignores those artificial boundaries and recursively
decodes reachable x86-64 control flow from:
  0x5AEC60  (shared selector reached by __PickleTable/__SoftPickleTable wrappers)
  0x5AEFC0  (second shared selector reached by paired wrappers)

The exploration is restricted to the known contiguous code window
[0x5AEC60, 0x5AF01C), follows direct conditional/unconditional branches,
continues through calls, and stops at returns/indirect terminal jumps.

It records direct calls, RIP-relative strings/data, and highlights uses of the
soft/normal selector flags. Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
START=0x5AEC60
END=0x5AF01C
SEEDS=(0x5AEC60,0x5AEFC0)
KNOWN_STRINGS=("__PickleTable","__SoftPickleTable","__subobjs","OnSaveCheckpoint","OnRestoreCheckpoint")


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softpickle_contiguous_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_JUMP,CS_GRP_CALL,CS_GRP_RET
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_JUMP,CS_GRP_CALL,CS_GRP_RET,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def find_strings(pe):
    out={}
    for name in KNOWN_STRINGS:
        needle=name.encode("ascii")+b"\0";pos=0
        while True:
            off=pe.data.find(needle,pos)
            if off<0:break
            rva=pe.file_to_rva(off)
            if rva is not None:out[rva]=name
            pos=off+1
    return out


def ascii_at(pe,rva,max_len=180):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    z=raw.find(b"\0")
    if z<0:z=len(raw)
    raw=raw[:z]
    if len(raw)<3:return None
    if all(32<=b<127 for b in raw):
        try:return raw.decode("ascii")
        except Exception:return None
    return None


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
    (Cs,ARCH,MODE,GRP_JUMP,GRP_CALL,GRP_RET,OP_IMM,OP_MEM,RIP)=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True
    known_strings=find_strings(pe)

    def decode_one(rva):
        off=pe.rva_to_file(rva)
        if off is None:return None
        raw=pe.data[off:off+15]
        items=list(md.disasm(raw,IMAGE_BASE+rva,count=1))
        return items[0] if items else None

    queue=deque(SEEDS)
    visited=set()
    rows={}
    edges=[]
    calls=[]
    out_of_range=[]
    decode_errors=[]

    while queue and len(visited)<5000:
        rva=queue.popleft()
        if rva in visited:continue
        if not (START<=rva<END):
            out_of_range.append(rva);continue

        ins=decode_one(rva)
        if ins is None:
            decode_errors.append(rva);continue
        visited.add(rva)

        refs=[];imm_targets=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                val=op.imm
                if IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
                    val-=IMAGE_BASE
                imm_targets.append(val)
            elif op.type==OP_MEM and op.mem.base==RIP:
                rv=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                ref={"rva":rv}
                if rv in known_strings:ref["name"]=known_strings[rv]
                else:
                    s=ascii_at(pe,rv)
                    if s:ref["ascii"]=s
                refs.append(ref)

        row={
            "rva":rva,"size":ins.size,"bytes":ins.bytes.hex(),
            "mnemonic":ins.mnemonic,"op_str":ins.op_str,
            "rip_refs":refs,"imm_targets":imm_targets,
        }
        # Useful semantic tags for this specific pair.
        tags=[]
        op=ins.op_str.lower()
        if "[rsp + 0x68]" in op or "[rsp+0x68]" in op:tags.append("selector_flag_stack")
        if "0x16828" in op:tags.append("checkpoint_manager_flag")
        if "0x198" in op:tags.append("state_object_flag")
        if "0x10" in op and ins.mnemonic in ("test","and","or","cmp","mov"):tags.append("bit_or_scalar_0x10")
        if tags:row["tags"]=tags
        rows[rva]=row

        next_rva=rva+ins.size
        is_ret=ins.group(GRP_RET)
        is_call=ins.group(GRP_CALL)
        is_jump=ins.group(GRP_JUMP)

        if is_call:
            direct=None
            for val in imm_targets:
                if isinstance(val,int) and 0<=val<pe.size_of_image:
                    direct=val;break
            calls.append({"site":rva,"target":direct,"mnemonic":ins.mnemonic,"op_str":ins.op_str})
            # Calls return: always continue fallthrough.
            queue.append(next_rva)
            continue

        if is_ret:
            continue

        if is_jump:
            direct=None
            for val in imm_targets:
                if isinstance(val,int) and 0<=val<pe.size_of_image:
                    direct=val;break
            if direct is not None:
                edges.append({"from":rva,"to":direct,"kind":ins.mnemonic})
                queue.append(direct)
            # Conditional jumps also have fallthrough. jmp does not.
            if ins.mnemonic!="jmp":
                queue.append(next_rva)
            continue

        queue.append(next_rva)

    ordered=[rows[k] for k in sorted(rows)]

    # Split into basic blocks for easier reading.
    leaders=set(SEEDS)
    for e in edges:
        if START<=e["to"]<END:leaders.add(e["to"])
        srcrow=rows.get(e["from"])
        if srcrow and srcrow["mnemonic"]!="jmp":
            nr=e["from"]+srcrow["size"]
            if START<=nr<END:leaders.add(nr)
    for c in calls:
        if c["site"] in rows:
            nr=c["site"]+rows[c["site"]]["size"]
            if START<=nr<END:leaders.add(nr)

    blocks=[]
    current=None
    leader_set=set(leaders)
    for row in ordered:
        if current is None or row["rva"] in leader_set:
            if current is not None:blocks.append(current)
            current={"start":row["rva"],"instructions":[]}
        current["instructions"].append(row)
        if row["mnemonic"] in ("ret","jmp"):
            blocks.append(current);current=None
    if current is not None:blocks.append(current)

    report={
        "schema":1,
        "analysis":"softpickle_contiguous_control_flow",
        "exe_sha256":digest,
        "window":{"start":START,"end":END},
        "seeds":list(SEEDS),
        "instruction_count":len(ordered),
        "edge_count":len(edges),
        "call_count":len(calls),
        "decode_errors":decode_errors,
        "out_of_range_targets":sorted(set(out_of_range)),
        "instructions":ordered,
        "edges":edges,
        "calls":calls,
        "blocks":blocks,
        "safety":{
            "static_exe_read_only":True,"game_launched":False,"process_accessed":False,
            "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False,
        },
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - contiguous __SoftPickleTable selector flow",
        f"exe_sha256={digest}",
        f"window=0x{START:X}..0x{END:X}",
        "seeds="+",".join(f"0x{x:X}" for x in SEEDS),
        f"instructions={len(ordered)} edges={len(edges)} calls={len(calls)} decode_errors={len(decode_errors)}",
        "",
        "REACHABLE INSTRUCTIONS",
    ]
    for row in ordered:
        suffix=[]
        for ref in row["rip_refs"]:
            if "name" in ref:suffix.append(f"{ref['name']}@0x{ref['rva']:X}")
            elif "ascii" in ref:suffix.append(f"ascii={ref['ascii']!r}@0x{ref['rva']:X}")
            else:suffix.append(f"rip->0x{ref['rva']:X}")
        for tag in row.get("tags",[]):suffix.append(tag)
        lines.append(f"0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"+((" ; "+" | ".join(suffix)) if suffix else ""))

    lines.extend(["","DIRECT CALLS"])
    for c in calls:
        target="indirect" if c["target"] is None else f"0x{c['target']:X}"
        lines.append(f"0x{c['site']:X} {c['mnemonic']} -> {target} {c['op_str']}")

    lines.extend(["","CONTROL EDGES"])
    for e in edges:
        lines.append(f"0x{e['from']:X} {e['kind']} -> 0x{e['to']:X}")

    lines.extend(["","OUT-OF-RANGE TARGETS"])
    for x in sorted(set(out_of_range)):lines.append(f"0x{x:X}")

    lines.extend(["","SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false"])
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"SOFTPICKLE_CONTIGUOUS_FLOW_COMPLETE instructions={len(ordered)} calls={len(calls)} edges={len(edges)} errors={len(decode_errors)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
