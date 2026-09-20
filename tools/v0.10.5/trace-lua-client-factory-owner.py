#!/usr/bin/env python3
"""Trace the Lua client factory owner and its resource-keyed client table.

Anchors proven by earlier passes:
- 0x4654A0: mixed LuaClient/LuaLevelClient factory method
- 0x464410: helper called by the LuaLevelClient branch
- factory-owner offsets:
    +0x178 resource-keyed linked/list structure
    +0x188 LuaClient allocator/pool
    +0x190 LuaLevelClient allocator/pool

This compact static pass:
1. finds qword vtable slots pointing at 0x4654A0 and decodes nearby MSVC RTTI;
2. finds constructors/factories that install the corresponding vtable base;
3. disassembles 0x464410 exactly and finds direct callers;
4. reports references from the factory-owner methods to +0x178/+0x188/+0x190;
5. includes one-hop callers of exact anchor/xref functions only.

No process/save/game access.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FACTORY=0x4654A0
LOOKUP=0x464410
OWNER_OFFSETS=(0x178,0x188,0x190)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_factory_owner_pe",p)
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


def decode_rtti(pe,vt):
    out={"vtable_rva":vt}
    ptr=u64(pe,vt-8)
    out["preceding_qword"]=ptr
    if ptr is None or not (IMAGE_BASE<=ptr<IMAGE_BASE+pe.size_of_image):return out
    col=ptr-IMAGE_BASE
    off=pe.rva_to_file(col)
    out["col_rva"]=col
    if off is None or off+24>len(pe.data):return out
    sig,offset,cd,type_rva,chd_rva,self_rva=struct.unpack_from("<IIIIII",pe.data,off)
    out.update({"signature":sig,"offset":offset,"cdOffset":cd,"type_rva":type_rva,"chd_rva":chd_rva,"self_rva":self_rva})
    if 0<type_rva<pe.size_of_image:out["type_name"]=cstr(pe,type_rva+16)
    return out


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
                      "disp":op.mem.disp}
                if op.mem.base==RIP:
                    item["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(item)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"mem":mem,"imms":imms})
    return rows


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

    # Exact qword references to factory function in non-exec data => vtable slots.
    factory_va=IMAGE_BASE+FACTORY
    slots=[]
    for sec in pe.sections:
        if sec.get("exec") or sec["rawsize"]<=0:continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["rawsize"]]
        for off in range(0,max(0,len(raw)-7),8):
            if struct.unpack_from("<Q",raw,off)[0]==factory_va:
                slots.append({"slot_rva":sec["rva"]+off,"section":sec.get("name")})

    vtable_candidates=[]
    for hit in slots:
        slot=hit["slot_rva"]
        # Search back up to 0x100 bytes for a valid x64 MSVC COL.
        for vt in range(max(8,slot-0x100),slot+1,8):
            r=decode_rtti(pe,vt)
            name=r.get("type_name")
            if name and name.startswith(".?AV"):
                # Validate that slot is inside a plausible table span.
                if vt<=slot<vt+0x200:
                    vtable_candidates.append({"slot_rva":slot,"vtable_rva":vt,"rtti":r})
    # Deduplicate by (slot, vtable).
    uniq={}
    for x in vtable_candidates:uniq[(x["slot_rva"],x["vtable_rva"])]=x
    vtable_candidates=list(uniq.values())

    interesting_vtables={x["vtable_rva"] for x in vtable_candidates}

    callers=defaultdict(set);edges=[];matched={}
    lookup_fn=pe.function_for(LOOKUP)
    factory_fn=pe.function_for(FACTORY)

    for fn in pe.runtime_functions:
        rows=decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows:continue
        hits=[]
        for row in rows:
            if row["mnemonic"] in ("call","jmp") and row["imms"]:
                target=row["imms"][0]
                sec=pe.section_for_rva(target) if isinstance(target,int) else None
                if sec and sec.get("exec"):
                    edges.append({"from":fn["begin"],"site":row["rva"],"kind":row["mnemonic"],"to":target})
                    tf=pe.function_for(target)
                    if tf:callers[tf["begin"]].add(fn["begin"])
                if target in (FACTORY,LOOKUP):
                    hits.append({"site":row["rva"],"kind":"direct_call","target":target,"op":row["op_str"]})
            for m in row["mem"]:
                rv=m.get("rip_target")
                if rv in interesting_vtables:
                    hits.append({"site":row["rva"],"kind":"vtable_ref","target":rv,"op":row["op_str"]})
        # Only owner-offset hits inside exact factory/lookup or vtable-referencing methods.
        if fn["begin"] in (factory_fn["begin"] if factory_fn else -1, lookup_fn["begin"] if lookup_fn else -1):
            for row in rows:
                for m in row["mem"]:
                    if m["disp"] in OWNER_OFFSETS and m["base"] not in ("rsp","rbp","rip",None):
                        hits.append({"site":row["rva"],"kind":"owner_offset","target":m["disp"],"base":m["base"],"op":row["op_str"]})
        if hits:
            matched[fn["begin"]]={"begin":fn["begin"],"end":fn["end"],"hits":hits,"instructions":rows}

    # Seed exact anchors even if no external xrefs.
    for target in (FACTORY,LOOKUP):
        fn=pe.function_for(target)
        if fn and fn["begin"] not in matched:
            matched[fn["begin"]]={"begin":fn["begin"],"end":fn["end"],"hits":[],"instructions":decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP)}

    one_hop=set()
    for b in matched:
        one_hop.update(callers.get(b,set()))
    functions=[]
    for b in sorted(set(matched)|one_hop):
        fn=pe.function_for(b)
        if not fn:continue
        primary=b in matched
        functions.append({
            "begin":b,"end":fn["end"],"primary":primary,
            "hits":matched.get(b,{}).get("hits",[]),
            "callers":sorted(callers.get(b,set())),
            "instructions":decode_fn(pe,md,fn,OP_IMM,OP_MEM,RIP) if primary else []
        })

    report={
        "schema":1,"analysis":"lua_client_factory_owner",
        "exe_sha256":digest,"factory":FACTORY,"lookup":LOOKUP,
        "factory_slots":slots,"vtable_candidates":vtable_candidates,
        "functions":functions,
        "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,"save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - Lua client factory owner trace",
        f"exe_sha256={digest}",
        f"factory=0x{FACTORY:X} lookup=0x{LOOKUP:X}",
        f"factory_slots={len(slots)} vtable_candidates={len(vtable_candidates)} functions={len(functions)}",
        "",
        "FACTORY VTABLE CANDIDATES",
    ]
    for x in vtable_candidates:
        r=x["rtti"]
        lines.append(f"slot=0x{x['slot_rva']:X} vtable=0x{x['vtable_rva']:X} type={r.get('type_name')} col=0x{r.get('col_rva',0):X} offset={r.get('offset')}")
    lines.extend(["","FUNCTIONS"])
    for f in functions:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X} primary={str(f['primary']).lower()} callers="+",".join(f"0x{x:X}" for x in f["callers"]))
        for h in f["hits"]:
            lines.append(f"  HIT 0x{h['site']:X} {h['kind']} value=0x{h['target']:X} {h.get('op','')}")
        if f["primary"]:
            for row in f["instructions"]:
                lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_CLIENT_FACTORY_OWNER_TRACE_COMPLETE slots={len(slots)} vtables={len(vtable_candidates)} functions={len(functions)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
