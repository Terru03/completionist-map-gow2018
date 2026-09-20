#!/usr/bin/env python3
"""Trace LuaContext pending per-resource state producers.

Proven:
- LuaContext vtable = 0xDF2F50
- vtable slot 12 -> 0x4654A0 creates LuaClient/LuaLevelClient
- 0x464410 walks LuaContext+0x178, finds node where node+0x18 == resource key,
  unlinks the node, and returns it; the returned node is then passed into the
  new LuaLevelClient constructor.

Therefore +0x178 is a pending per-resource state list/cache. This pass traces
the LuaContext virtual methods around the factory to find who inserts/loads
those nodes and what fields the node owns.

It disassembles slots 0..13 and exact one-hop callees of methods that touch:
- LuaContext+0x178 / +0x188 / +0x190
- node linkage offsets +0 / +8
- node key offset +0x18
It also records direct calls among the known restore/save bridge family.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path
from collections import defaultdict

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
VTABLE=0xDF2F50
SLOT_FIRST=0
SLOT_LAST=13
OWNER_OFFSETS=(0x178,0x188,0x190,0x198)
NODE_OFFSETS=(0x0,0x8,0x18)
BRIDGE_TARGETS=(0x464410,0x5AEC20,0x5AEC40,0x5AEF60,0x5AEF90,0x5AEC60,0x5AEFC0,0x5AF01C,0x5AF4E0,0x5B1030)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_context_pending_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data): return None
    return struct.unpack_from("<Q",pe.data,off)[0]


def decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[];imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                      "index":md.reg_name(op.mem.index) if op.mem.index else None,
                      "disp":op.mem.disp,
                      "size":op.size}
                if op.mem.base==RIP:
                    item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(item)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                     "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                     "mem":mem,"imms":imms})
    return rows


def classify_rows(rows):
    hits=[]
    for row in rows:
        for m in row["mem"]:
            base=m.get("base")
            if base in ("rsp","rbp","rip",None):
                continue
            if m["disp"] in OWNER_OFFSETS:
                hits.append({"site":row["rva"],"kind":"owner_offset","offset":m["disp"],"base":base,"op":row["op_str"]})
            if m["disp"] in NODE_OFFSETS:
                # Keep node-offset evidence only for instructions that look list/pointer related.
                if row["mnemonic"] in ("mov","lea","cmp","xchg","test"):
                    hits.append({"site":row["rva"],"kind":"node_offset","offset":m["disp"],"base":base,"op":row["op_str"]})
        if row["mnemonic"] in ("call","jmp") and row["imms"]:
            target=row["imms"][0]
            if target in BRIDGE_TARGETS:
                hits.append({"site":row["rva"],"kind":"bridge_call","target":target,"op":row["op_str"]})
    return hits


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()

    exe=args.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"SHA mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper();pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    slots=[]
    vtargets=[]
    for idx in range(SLOT_FIRST,SLOT_LAST+1):
        slot=VTABLE+idx*8
        val=u64(pe,slot)
        target=None
        if val is not None and IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
            candidate=val-IMAGE_BASE
            sec=pe.section_for_rva(candidate)
            if sec and sec.get("exec"):
                target=candidate
                vtargets.append(candidate)
        slots.append({"index":idx,"slot_rva":slot,"target_rva":target})

    # Build exact direct-call graph once.
    callers=defaultdict(set)
    callees=defaultdict(set)
    fn_rows={}
    for fn in pe.runtime_functions:
        rows=decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows:continue
        fn_rows[fn["begin"]]=rows
        for row in rows:
            if row["mnemonic"] in ("call","jmp") and row["imms"]:
                target=row["imms"][0]
                if not isinstance(target,int):continue
                sec=pe.section_for_rva(target)
                if not(sec and sec.get("exec")):continue
                tf=pe.function_for(target)
                if tf:
                    callers[tf["begin"]].add(fn["begin"])
                    callees[fn["begin"]].add(tf["begin"])

    primary={}
    seed_callees=set()
    for target in vtargets:
        fn=pe.function_for(target)
        if not fn:continue
        rows=fn_rows.get(fn["begin"]) or decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        hits=classify_rows(rows)
        rec={"begin":fn["begin"],"end":fn["end"],"vtarget":target,"hits":hits,
             "callers":sorted(callers.get(fn["begin"],set())),"instructions":rows}
        primary[fn["begin"]]=rec
        if hits:
            seed_callees.update(callees.get(fn["begin"],set()))

    # One-hop callees only from virtual methods with list/bridge evidence.
    secondary=[]
    for b in sorted(seed_callees):
        if b in primary:continue
        fn=pe.function_for(b)
        if not fn:continue
        rows=fn_rows.get(b) or decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        hits=classify_rows(rows)
        # Keep only callees that themselves touch relevant offsets/bridges OR are small enough
        # to make call semantics inspectable.
        if hits or (fn["end"]-fn["begin"] <= 0x180):
            secondary.append({"begin":b,"end":fn["end"],"hits":hits,
                              "callers":sorted(callers.get(b,set())),"instructions":rows})

    report={
        "schema":1,"analysis":"lua_context_pending_state_producers",
        "exe_sha256":digest,"vtable":VTABLE,
        "slots":slots,
        "primary_methods":[primary[k] for k in sorted(primary)],
        "secondary_callees":secondary,
        "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                  "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
      "Completionist Map - LuaContext pending-state producer trace",
      f"exe_sha256={digest}",
      f"vtable=0x{VTABLE:X}",
      f"primary_methods={len(primary)} secondary_callees={len(secondary)}",
      "",
      "VTABLE SLOTS",
    ]
    for s in slots:
        target="-" if s["target_rva"] is None else f"0x{s['target_rva']:X}"
        lines.append(f"index={s['index']:>2} slot=0x{s['slot_rva']:X} target={target}")

    def emit_func(title,f):
        lines.append(f"{title} 0x{f['begin']:X}..0x{f['end']:X} callers="+",".join(f"0x{x:X}" for x in f["callers"]))
        for h in f["hits"]:
            if h["kind"]=="bridge_call":
                lines.append(f"  HIT 0x{h['site']:X} bridge_call -> 0x{h['target']:X} {h['op']}")
            else:
                lines.append(f"  HIT 0x{h['site']:X} {h['kind']} +0x{h['offset']:X} base={h['base']} {h['op']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")

    lines.extend(["","PRIMARY LUA CONTEXT METHODS"])
    for f in [primary[k] for k in sorted(primary)]:
        emit_func("FUNCTION",f)

    lines.extend(["SECONDARY ONE-HOP CALLEES"])
    for f in secondary:
        emit_func("FUNCTION",f)

    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_CONTEXT_PENDING_STATE_TRACE_COMPLETE primary={len(primary)} secondary={len(secondary)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
