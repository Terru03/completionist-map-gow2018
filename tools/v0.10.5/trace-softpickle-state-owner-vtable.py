#!/usr/bin/env python3
"""Identify the native class owning GoW checkpoint normal/soft pickle buffers.

Anchors:
  0x5AEC20 / 0x5AEC40  normal/soft Unpickle wrappers
  0x5AEF60 / 0x5AEF90  soft/normal save wrappers
  0x5AEC60 / 0x5AEFC0  shared implementations

The shared save implementation uses the object passed in RCX and later
0x5AF4E0 selects [object+0x70] vs [object+0x78] for normal vs soft serialized
buffers.

This static pass:
- searches read-only data for qword function pointers to the anchor methods;
- groups nearby pointers into likely vtables;
- attempts MSVC CompleteObjectLocator / TypeDescriptor RTTI decoding;
- scans runtime functions for RIP-relative references to candidate vtables,
  which commonly identifies constructors/destructors/registration code;
- emits compact disassembly for those xref functions only.

Read-only and version locked.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
ANCHORS=(0x5AEC20,0x5AEC40,0x5AEC60,0x5AEF60,0x5AEF90,0x5AEFC0,0x5AF01C,0x5AF4E0)


def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("softpickle_vtable_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
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


def u32(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+4>len(pe.data):return None
    return struct.unpack_from("<I",pe.data,off)[0]


def u64(pe,rva):
    off=pe.rva_to_file(rva)
    if off is None or off+8>len(pe.data):return None
    return struct.unpack_from("<Q",pe.data,off)[0]


def section_name(pe,rva):
    sec=pe.section_for_rva(rva)
    return sec.get("name") if sec else None


def decode_rtti(pe,vtable_rva):
    # MSVC x64: qword immediately before vftable points to CompleteObjectLocator.
    col_va=u64(pe,vtable_rva-8)
    if col_va is None or not (IMAGE_BASE<=col_va<IMAGE_BASE+pe.size_of_image):
        return None
    col_rva=col_va-IMAGE_BASE
    off=pe.rva_to_file(col_rva)
    if off is None or off+24>len(pe.data):return None
    sig,offset,cd,p_type,p_chd,p_self=struct.unpack_from("<IIIIII",pe.data,off)
    # x64 RTTI pointers are image-relative RVAs.
    type_rva=p_type
    name=read_cstr(pe,type_rva+16) if 0<type_rva<pe.size_of_image else None
    if not name or not (name.startswith(".?A") or "@@" in name):
        return {
            "col_rva":col_rva,"signature":sig,"offset":offset,"cdOffset":cd,
            "type_rva":type_rva,"chd_rva":p_chd,"self_rva":p_self,"type_name":name
        }
    return {
        "col_rva":col_rva,"signature":sig,"offset":offset,"cdOffset":cd,
        "type_rva":type_rva,"chd_rva":p_chd,"self_rva":p_self,"type_name":name
    }


def decode_function(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        refs=[];targets=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_MEM and op.mem.base==RIP:
                refs.append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
            elif op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:targets.append(v-IMAGE_BASE)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"rip_refs":refs,"targets":targets})
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

    # Search all non-exec mapped sections for qword pointers to anchor VAs.
    hits=[]
    anchor_vas={IMAGE_BASE+x:x for x in ANCHORS}
    for sec in pe.sections:
        if sec.get("exec") or sec["rawsize"]<=0:continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["rawsize"]]
        for off in range(0,max(0,len(raw)-7),8):
            val=struct.unpack_from("<Q",raw,off)[0]
            if val in anchor_vas:
                rva=sec["rva"]+off
                hits.append({"entry_rva":rva,"anchor_rva":anchor_vas[val],"section":sec.get("name")})

    # Group close entries into candidate pointer tables.
    sorted_rvas=sorted({h["entry_rva"] for h in hits})
    groups=[]
    cur=[]
    for rva in sorted_rvas:
        if not cur or rva-cur[-1]<=0x80:
            cur.append(rva)
        else:
            groups.append(cur);cur=[rva]
    if cur:groups.append(cur)

    candidates=[]
    for g in groups:
        start=max(0,g[0]-0x80)
        # align start to 8
        start=(start+7)&~7
        end=min(pe.size_of_image,g[-1]+0x100)
        entries=[]
        for rva in range(start,end,8):
            val=u64(pe,rva)
            if val is None:continue
            if IMAGE_BASE<=val<IMAGE_BASE+pe.size_of_image:
                trva=val-IMAGE_BASE
                sec=pe.section_for_rva(trva)
                if sec and sec.get("exec"):
                    entries.append({"slot_rva":rva,"target_rva":trva})
        # Test plausible vtable starts near first anchor entry.
        starts=[]
        for maybe in range(max(start,g[0]-0x40),g[0]+1,8):
            rtti=decode_rtti(pe,maybe)
            if rtti:
                starts.append({"vtable_rva":maybe,"rtti":rtti})
        candidates.append({"anchor_entries":g,"window":{"start":start,"end":end},"code_entries":entries,"possible_starts":starts})

    candidate_vtables=set()
    for c in candidates:
        for s in c["possible_starts"]:
            candidate_vtables.add(s["vtable_rva"])
    # Even without RTTI, include anchor-entry-aligned neighborhood starts.
    for h in hits:
        candidate_vtables.add(h["entry_rva"])

    # Scan runtime functions for RIP refs to candidate vtable addresses or their nearby anchor slots.
    interesting_data=set(candidate_vtables)
    interesting_data.update(h["entry_rva"] for h in hits)
    xref_functions=[]
    for fn in pe.runtime_functions:
        rows=decode_function(pe,md,fn,OP_IMM,OP_MEM,RIP)
        matched=[]
        for row in rows:
            refs=[rv for rv in row["rip_refs"] if rv in interesting_data]
            if refs:
                matched.append({"site":row["rva"],"refs":refs,"mnemonic":row["mnemonic"],"op_str":row["op_str"]})
        if matched:
            xref_functions.append({
                "begin":fn["begin"],"end":fn["end"],"matches":matched,
                "instructions":rows,
            })

    report={
        "schema":1,"analysis":"softpickle_state_owner_vtable",
        "exe_sha256":digest,"anchors":list(ANCHORS),
        "pointer_hits":hits,"candidate_tables":candidates,
        "xref_functions":xref_functions,
        "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,"save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False},
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - SoftPickle state-owner vtable/RTTI trace",
        f"exe_sha256={digest}",
        "anchors="+",".join(f"0x{x:X}" for x in ANCHORS),
        f"pointer_hits={len(hits)} candidate_groups={len(candidates)} xref_functions={len(xref_functions)}",
        "",
        "ANCHOR POINTER HITS",
    ]
    for h in hits:
        lines.append(f"0x{h['entry_rva']:X} -> 0x{h['anchor_rva']:X} section={h['section']}")

    lines.extend(["","CANDIDATE TABLES"])
    for i,c in enumerate(candidates):
        lines.append(f"GROUP {i} anchors="+",".join(f"0x{x:X}" for x in c["anchor_entries"]))
        for s in c["possible_starts"]:
            r=s["rtti"]
            lines.append(f"  VTABLE 0x{s['vtable_rva']:X} RTTI type={r.get('type_name')} col=0x{r.get('col_rva',0):X} offset={r.get('offset')}")
        for e in c["code_entries"]:
            mark="*" if e["target_rva"] in ANCHORS else " "
            lines.append(f" {mark}slot 0x{e['slot_rva']:X} -> 0x{e['target_rva']:X}")

    lines.extend(["","XREF FUNCTIONS"])
    for f in xref_functions:
        lines.append(f"FUNCTION 0x{f['begin']:X}..0x{f['end']:X}")
        for m in f["matches"]:
            lines.append(f"  MATCH 0x{m['site']:X} {m['mnemonic']} {m['op_str']} -> "+",".join(f"0x{x:X}" for x in m["refs"]))
        for row in f["instructions"]:
            lines.append(f"  0x{row['rva']:08X} {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}")
        lines.append("")

    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"SOFTPICKLE_STATE_OWNER_VTABLE_TRACE_COMPLETE pointerHits={len(hits)} groups={len(candidates)} xrefs={len(xref_functions)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
