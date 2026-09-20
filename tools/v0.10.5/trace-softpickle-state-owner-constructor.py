#!/usr/bin/env python3
"""Trace constructors/owners of the GoW checkpoint-state vtable family.

Known from the previous pass:
  vtable A base ~0xE03F18, containing the four normal/soft pickle methods
  vtable B base ~0xE04018, sibling checkpoint-state implementation

This compact pass:
- decodes MSVC RTTI from vtable[-1] when present;
- searches all mapped non-exec data for qword pointers to either vtable base;
- disassembles only PE runtime functions and records RIP/immediate references
  to the vtable bases or pointer slots;
- adds one-hop callers of those functions;
- emits only the matched functions and nearby call graph.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path
from collections import defaultdict

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
VTABLES=(0xE03F18,0xE04018)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softpickle_owner_ctor_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP


def u32(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+4>len(pe.data):return None
    return struct.unpack_from("<I",pe.data,off)[0]


def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]


def cstr(pe,rva,max_len=400):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    z=raw.find(b"\0")
    if z<0:return None
    try:return raw[:z].decode("ascii")
    except Exception:return None


def rtti(pe,vt):
    ptr=u64(pe,vt-8)
    out={"vtable_rva":vt,"preceding_qword":ptr}
    if ptr is None or not (IMAGE_BASE<=ptr<IMAGE_BASE+pe.size_of_image):
        return out
    col=ptr-IMAGE_BASE
    off=pe.rva_to_file(col)
    out["col_rva"]=col
    if off is None or off+24>len(pe.data):return out
    sig,offset,cd,type_rva,chd_rva,self_rva=struct.unpack_from("<IIIIII",pe.data,off)
    out.update({"signature":sig,"offset":offset,"cdOffset":cd,"type_rva":type_rva,"chd_rva":chd_rva,"self_rva":self_rva})
    if 0<type_rva<pe.size_of_image:
        out["type_name"]=cstr(pe,type_rva+16)
    return out


def decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        refs=[];imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_MEM and op.mem.base==RIP:
                refs.append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
            elif op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"rip_refs":refs,"imms":imms})
    return rows


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
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    rtti_rows=[rtti(pe,vt) for vt in VTABLES]

    # Direct pointer slots containing absolute vtable addresses.
    pointer_slots=[]
    wanted_va={IMAGE_BASE+vt:vt for vt in VTABLES}
    for sec in pe.sections:
        if sec.get("exec") or sec["rawsize"]<=0:continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["rawsize"]]
        for off in range(0,max(0,len(raw)-7),8):
            val=struct.unpack_from("<Q",raw,off)[0]
            if val in wanted_va:
                pointer_slots.append({"slot_rva":sec["rva"]+off,"vtable_rva":wanted_va[val],"section":sec.get("name")})

    interesting=set(VTABLES)
    interesting.update(x["slot_rva"] for x in pointer_slots)
    # Also accept references into first 0x20 bytes of either table; constructors can use interior pointers.
    near=set()
    for vt in VTABLES:
        near.update(range(vt-0x10,vt+0x28,8))
    interesting.update(near)

    matched={}
    edges=[]
    callers=defaultdict(set)

    for fn in pe.runtime_functions:
        rows=decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows:continue
        hits=[]
        for row in rows:
            for rv in row["rip_refs"]:
                if rv in interesting:
                    hits.append({"site":row["rva"],"kind":"rip","target":rv,"mnemonic":row["mnemonic"],"op_str":row["op_str"]})
            for imm in row["imms"]:
                if imm in interesting:
                    hits.append({"site":row["rva"],"kind":"imm","target":imm,"mnemonic":row["mnemonic"],"op_str":row["op_str"]})
            if row["mnemonic"] in ("call","jmp") and row["imms"]:
                target=row["imms"][0]
                sec=pe.section_for_rva(target) if isinstance(target,int) else None
                if sec and sec.get("exec"):
                    e={"from":fn["begin"],"site":row["rva"],"kind":row["mnemonic"],"to":target}
                    edges.append(e)
                    tfn=pe.function_for(target)
                    if tfn:callers[tfn["begin"]].add(fn["begin"])
        if hits:
            matched[fn["begin"]]={"begin":fn["begin"],"end":fn["end"],"hits":hits,"instructions":rows}

    one_hop=set()
    for b in matched:
        one_hop.update(callers.get(b,set()))

    caller_rows=[]
    for b in sorted(one_hop):
        fn=pe.function_for(b)
        if not fn or b in matched:continue
        rows=decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        caller_rows.append({"begin":b,"end":fn["end"],"instructions":rows})

    report={
        "schema":1,"analysis":"softpickle_state_owner_constructor",
        "exe_sha256":digest,"vtables":list(VTABLES),
        "rtti":rtti_rows,"pointer_slots":pointer_slots,
        "matched_functions":[matched[k] for k in sorted(matched)],
        "one_hop_callers":caller_rows,
        "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,"save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False},
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
      "Completionist Map - SoftPickle state-owner constructor trace",
      f"exe_sha256={digest}",
      "vtables="+",".join(f"0x{x:X}" for x in VTABLES),
      f"pointer_slots={len(pointer_slots)} matched_functions={len(matched)} one_hop_callers={len(caller_rows)}",
      "",
      "RTTI",
    ]
    for x in rtti_rows:
        lines.append(" ".join(f"{k}={('0x%X'%v) if isinstance(v,int) else v}" for k,v in x.items()))

    lines.extend(["","POINTER SLOTS"])
    for x in pointer_slots:
        lines.append(f"0x{x['slot_rva']:X} -> vtable 0x{x['vtable_rva']:X} section={x['section']}")

    lines.extend(["","MATCHED FUNCTIONS"])
    for f in [matched[k] for k in sorted(matched)]:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} callers="+",".join(f"0x{x:X}" for x in sorted(callers.get(f["begin"],set()))))
        for h in f["hits"]:
            lines.append(f"  HIT 0x{h['site']:X} {h['kind']} -> 0x{h['target']:X} {h['mnemonic']} {h['op_str']}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")

    lines.extend(["ONE-HOP CALLERS"])
    for f in caller_rows:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")

    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"SOFTPICKLE_STATE_OWNER_CONSTRUCTOR_TRACE_COMPLETE pointerSlots={len(pointer_slots)} matched={len(matched)} callers={len(caller_rows)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
