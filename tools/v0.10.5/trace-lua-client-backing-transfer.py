#!/usr/bin/env python3
"""Trace transfer between LuaClient live pickle buffers and durable backing state.

Proven:
- LuaLevelClient+0x68 = durable backing-state node, cached in LuaContext+0x178.
- LuaLevelClient+0x70 / +0x78 = live normal/soft pickle buffers.
- LuaLevelClient constructor 0x5A6DD0 stores r9 -> +0x68 and zeros +0x70/+0x78.
- LuaContext slot13 case2 calls 0x5A7720(client) immediately before detaching
  client+0x68 and caching it in +0x178.

This pass:
1. disassembles 0x5A7720 and all its direct callers;
2. dumps nearby Base LuaClient/LuaClient/LuaLevelClient vtable methods;
3. selects virtual methods that touch +0x68/+0x70/+0x78/+0x80 or call the known
   SoftPickle/checkpoint bridge family;
4. includes small one-hop callees of selected methods.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TRANSFER=0x5A7720
VTABLES={
    "BaseLuaClient":0xE03658,
    "LuaLevelClient":0xE03F18,
    "LuaClient":0xE04018,
}
OFFSETS=(0x68,0x70,0x78,0x80)
BRIDGES=(0x5AEC20,0x5AEC40,0x5AEC60,0x5AEF60,0x5AEF90,0x5AEFC0,0x5AF01C,0x5AF4E0,
         0x5B1030,0x5AD4A0,0x5AD8E0,0x5AC760,0x5AD4A0,0x463C60,0x464410,0x4654A0)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_client_transfer_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]

def decode_fn(pe,md,fn,OI,OM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[];imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OI:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OM:
                item={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                      "index":md.reg_name(op.mem.index) if op.mem.index else None,
                      "disp":op.mem.disp,"size":op.size}
                if op.mem.base==RIP:item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(item)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,
                     "op_str":ins.op_str,"mem":mem,"imms":imms})
    return rows

def classify(rows):
    hits=[]
    for row in rows:
        for m in row["mem"]:
            if m.get("base") not in (None,"rsp","rbp","rip") and m["disp"] in OFFSETS:
                hits.append({"site":row["rva"],"kind":"client_offset","offset":m["disp"],"base":m["base"],"op":row["op_str"]})
        if row["mnemonic"] in ("call","jmp") and row["imms"]:
            t=row["imms"][0]
            if t in BRIDGES:
                hits.append({"site":row["rva"],"kind":"bridge_call","target":t,"op":row["op_str"]})
            if t==TRANSFER:
                hits.append({"site":row["rva"],"kind":"transfer_call","target":t,"op":row["op_str"]})
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
    Cs,ARCH,MODE,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    fn_rows={}
    callers=defaultdict(list)
    for fn in pe.runtime_functions:
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        if not rows:continue
        fn_rows[fn["begin"]]=rows
        for row in rows:
            if row["mnemonic"]=="call" and row["imms"]:
                t=row["imms"][0]
                tf=pe.function_for(t) if isinstance(t,int) else None
                if tf:
                    callers[tf["begin"]].append({"caller":fn["begin"],"site":row["rva"]})

    transfer_fn=pe.function_for(TRANSFER)
    if not transfer_fn:raise RuntimeError("No runtime function for transfer")
    transfer_rows=fn_rows.get(transfer_fn["begin"]) or decode_fn(pe,md,transfer_fn,OI,OM,RIP)

    tables=[]
    virtual_targets=set()
    for name,base in VTABLES.items():
        slots=[]
        for idx in range(0,40):
            slot=base+idx*8
            val=u64(pe,slot)
            target=None
            if val is not None and IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
                cand=val-IMAGE_BASE
                sec=pe.section_for_rva(cand)
                if sec and sec.get("exec"):
                    target=cand;virtual_targets.add(cand)
            slots.append({"index":idx,"slot_rva":slot,"target_rva":target})
        tables.append({"name":name,"base":base,"slots":slots})

    selected=[]
    callee_seeds=set()
    seen_fn=set()
    for target in sorted(virtual_targets|{TRANSFER}):
        fn=pe.function_for(target)
        if not fn or fn["begin"] in seen_fn:continue
        rows=fn_rows.get(fn["begin"]) or decode_fn(pe,md,fn,OI,OM,RIP)
        hits=classify(rows)
        if target==TRANSFER or hits:
            seen_fn.add(fn["begin"])
            selected.append({"target":target,"begin":fn["begin"],"end":fn["end"],"hits":hits,
                             "callers":callers.get(fn["begin"],[]),"instructions":rows})
            for row in rows:
                if row["mnemonic"]=="call" and row["imms"]:
                    tf=pe.function_for(row["imms"][0])
                    if tf and tf["end"]-tf["begin"]<=0x280:
                        callee_seeds.add(tf["begin"])

    secondary=[]
    for b in sorted(callee_seeds):
        if b in seen_fn:continue
        fn=pe.function_for(b)
        if not fn:continue
        rows=fn_rows.get(b) or decode_fn(pe,md,fn,OI,OM,RIP)
        hits=classify(rows)
        secondary.append({"begin":b,"end":fn["end"],"hits":hits,"instructions":rows})

    report={"schema":1,"analysis":"lua_client_backing_transfer","exe_sha256":digest,
            "transfer":TRANSFER,"transfer_function":{"begin":transfer_fn["begin"],"end":transfer_fn["end"],
                                                     "callers":callers.get(transfer_fn["begin"],[]),
                                                     "instructions":transfer_rows},
            "vtables":tables,"selected_methods":selected,"secondary_callees":secondary,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - LuaClient backing-state transfer trace",f"exe_sha256={digest}",""]
    lines.append(f"TRANSFER 0x{transfer_fn['begin']:X}..0x{transfer_fn['end']:X}")
    lines.append("CALLERS "+",".join(f"0x{x['caller']:X}@0x{x['site']:X}" for x in callers.get(transfer_fn["begin"],[])))
    for row in transfer_rows:
        lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
    lines.append("")
    for table in tables:
        lines.append(f"VTABLE {table['name']} 0x{table['base']:X}")
        for s in table["slots"]:
            t="-" if s["target_rva"] is None else f"0x{s['target_rva']:X}"
            lines.append(f"  {s['index']:02d} 0x{s['slot_rva']:X} -> {t}")
        lines.append("")
    lines.append("SELECTED VIRTUAL METHODS")
    for f in selected:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} vtarget=0x{f['target']:X}")
        for h in f["hits"]:
            if h["kind"]=="client_offset":
                lines.append(f"  HIT 0x{h['site']:X} +0x{h['offset']:X} base={h['base']} {h['op']}")
            else:
                lines.append(f"  HIT 0x{h['site']:X} {h['kind']} -> 0x{h['target']:X} {h['op']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("SMALL ONE-HOP CALLEES")
    for f in secondary:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        for h in f["hits"]:
            if h["kind"]=="client_offset":
                lines.append(f"  HIT 0x{h['site']:X} +0x{h['offset']:X} base={h['base']} {h['op']}")
            else:
                lines.append(f"  HIT 0x{h['site']:X} {h['kind']} -> 0x{h['target']:X} {h['op']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_CLIENT_BACKING_TRANSFER_TRACE_COMPLETE selected={len(selected)} secondary={len(secondary)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
