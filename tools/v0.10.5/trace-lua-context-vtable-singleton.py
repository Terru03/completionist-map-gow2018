#!/usr/bin/env python3
"""Locate the live LuaContext owner/singleton from the native method at 0x4654A0.

Static/read-only and version locked.

Steps:
- find non-exec qword pointers to VA(0x4654A0);
- classify nearby MSVC vftables/RTTI;
- disassemble functions that reference candidate vtables (constructors/destructors);
- include direct callers of those functions so stable RIP-relative/global ownership
  can be identified without runtime guessing.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, struct, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
ANCHOR=0x4654A0

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("lua_context_locator_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def read_cstr(pe,rva,max_len=300):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    z=raw.find(b"\0")
    if z<0:return None
    try:return raw[:z].decode("ascii")
    except Exception:return None

def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]

def decode_rtti(pe,vtable_rva):
    col_va=u64(pe,vtable_rva-8)
    if col_va is None or not (IMAGE_BASE<=col_va<IMAGE_BASE+pe.size_of_image):return None
    col_rva=col_va-IMAGE_BASE
    off=pe.rva_to_file(col_rva)
    if off is None or off+24>len(pe.data):return None
    sig,offset,cd,p_type,p_chd,p_self=struct.unpack_from("<IIIIII",pe.data,off)
    name=read_cstr(pe,p_type+16) if 0<p_type<pe.size_of_image else None
    return {"col_rva":col_rva,"signature":sig,"offset":offset,"cdOffset":cd,
            "type_rva":p_type,"chd_rva":p_chd,"self_rva":p_self,"type_name":name}

def decode_function(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        refs=[];imms=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_MEM and op.mem.base==RIP:
                refs.append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
            elif op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                    "rip_refs":refs,"imms":imms})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--db",type=Path,default=None)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    exe=a.exe.expanduser().resolve()
    if not exe.is_file():raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"SHA mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    helper=load_helper();pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    anchor_va=IMAGE_BASE+ANCHOR
    hits=[]
    for sec in pe.sections:
        if sec.get("exec") or sec["rawsize"]<=0:continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["rawsize"]]
        for off in range(0,max(0,len(raw)-7),8):
            if struct.unpack_from("<Q",raw,off)[0]==anchor_va:
                hits.append({"entry_rva":sec["rva"]+off,"section":sec.get("name")})

    starts=[]
    for h in hits:
        e=h["entry_rva"]
        for maybe in range(max(8,e-0x100),e+1,8):
            rtti=decode_rtti(pe,maybe)
            if rtti:
                starts.append({"vtable_rva":maybe,"anchor_slot_rva":e,
                               "slot_index":(e-maybe)//8,"rtti":rtti})
    # dedup
    uniq={}
    for s in starts:uniq[(s["vtable_rva"],s["anchor_slot_rva"])]=s
    starts=list(uniq.values())

    interesting={x["vtable_rva"] for x in starts}
    interesting.update(x["anchor_slot_rva"] for x in starts)
    xrefs=[]
    for fn in pe.runtime_functions:
        rows=decode_function(pe,md,fn,OI,OM,RIP)
        matched=[]
        for row in rows:
            refs=[r for r in row["rip_refs"] if r in interesting]
            if refs:
                matched.append({"site":row["rva"],"refs":refs,
                                "mnemonic":row["mnemonic"],"op_str":row["op_str"]})
        if matched:
            xrefs.append({"begin":fn["begin"],"end":fn["end"],
                          "matches":matched,"instructions":rows})

    # direct callers via reusable index when available
    db=a.db
    if db is None:db=repo/".research-index"/"gow-caebcb027980.sqlite"
    caller_fns={}
    if db.is_file():
        con=sqlite3.connect(str(db))
        for xf in xrefs:
            b=xf["begin"]
            rows=con.execute(
                "SELECT site,src_fn,dest,target_fn FROM edges WHERE kind='call' AND target_fn=? ORDER BY site",
                (b,)
            ).fetchall()
            for site,src,dest,target in rows:
                caller_fns[src]={"site_to":site,"target":b}
        con.close()

    callers=[]
    for b,meta in sorted(caller_fns.items()):
        fn=pe.function_for(b)
        if not fn or fn["end"]-fn["begin"]>0x3000:continue
        rows=decode_function(pe,md,fn,OI,OM,RIP)
        callers.append({"begin":fn["begin"],"end":fn["end"],"call_meta":meta,
                        "instructions":rows})

    report={
        "schema":1,"analysis":"lua_context_vtable_singleton_locator",
        "exe_sha256":digest,"anchor":ANCHOR,
        "anchor_pointer_hits":hits,"candidate_vtables":starts,
        "vtable_xref_functions":xrefs,"direct_callers":callers,
        "safety":{"static_exe_read_only":True,"game_launched":False,
                  "process_accessed":False,"save_opened":False,"save_written":False,
                  "progression_written":False,"game_files_written":False}
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=["Completionist Map - LuaContext vtable/singleton locator",f"exe_sha256={digest}",
       f"anchor=0x{ANCHOR:X}",f"pointer_hits={len(hits)} candidates={len(starts)} xrefs={len(xrefs)} callers={len(callers)}",""]
    L.append("ANCHOR POINTER HITS")
    for h in hits:L.append(f"  0x{h['entry_rva']:X} section={h['section']} -> 0x{ANCHOR:X}")
    L.append("")
    L.append("CANDIDATE VTABLES / RTTI")
    for s in starts:
        r=s["rtti"]
        L.append(f"  vtable=0x{s['vtable_rva']:X} anchor_slot=0x{s['anchor_slot_rva']:X} slot_index={s['slot_index']} type={r.get('type_name')} col=0x{r.get('col_rva',0):X}")
    L.append("")
    L.append("VTABLE XREF FUNCTIONS")
    for f in xrefs:
        L.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        for m in f["matches"]:
            L.append(f"  MATCH 0x{m['site']:X} {m['mnemonic']} {m['op_str']} refs="+",".join(f"0x{x:X}" for x in m["refs"]))
        for r in f["instructions"]:
            L.append(f"  0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        L.append("")
    L.append("DIRECT CALLERS OF VTABLE-XREF FUNCTIONS")
    for f in callers:
        L.append(f"CALLER 0x{f['begin']:X}..0x{f['end']:X} call_site=0x{f['call_meta']['site_to']:X} target=0x{f['call_meta']['target']:X}")
        for r in f["instructions"]:
            L.append(f"  0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        L.append("")
    L.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_CONTEXT_VTABLE_SINGLETON_LOCATOR_COMPLETE hits={len(hits)} candidates={len(starts)} xrefs={len(xrefs)} callers={len(callers)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
