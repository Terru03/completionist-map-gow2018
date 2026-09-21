#!/usr/bin/env python3
"""Resolve exact GetRef* Lua handlers independent of PE runtime function entries.

Disassembles fixed windows at:
  GetRefString 0x8456A0
  GetRefInt    0x8456C0
  GetRefFloat  0x8456E0
  GetRefBool   0x845700

Then follows direct call/jmp targets narrowly (max depth 2) and checks every
visited instruction for the already-proven staged Raven authority globals,
WAD+0xEE18 binding access, and known staged owner/restore function targets.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
ENTRYPOINTS={
    "GetRefString":0x8456A0,
    "GetRefInt":0x8456C0,
    "GetRefFloat":0x8456E0,
    "GetRefBool":0x845700,
}
STAGED_GLOBALS={
    "record_count":0x22C696C,
    "record_base":0x22C7170,
    "record_end_or_cursor":0x22C7194,
    "staged_aux_0":0x22C6938,
    "staged_aux_1":0x22C6940,
}
KNOWN_STAGED_FUNCTIONS={
    "staged_lookup_or_writer":0x82C820,
    "staged_related":0x82CC0C,
    "staged_related_2":0x82B250,
    "staged_restore_rebuild":0x82CF00,
    "wad_bind":0x673A30,
    "wad_restore_load":0x673D00,
    "wad_unbind":0x676CC0,
    "record_append_by_name":0x67B830,
    "record_reset":0x671AD0,
}
WAD_BINDING_DISP=0xEE18

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("getref_exact_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def ascii_at(pe,rva,max_len=180):
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

def disasm_window(pe,md,rva,size,OP_IMM,OP_MEM,RIP,AC_WRITE):
    off=pe.rva_to_file(rva)
    if off is None:return []
    raw=pe.data[off:off+size]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+rva):
        imms=[];mem=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM:
                m={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "disp":op.mem.disp,"size":op.size,
                   "write":bool(getattr(op,"access",0)&AC_WRITE)}
                if op.mem.base==RIP:
                    m["rip_target"]=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                mem.append(m)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                     "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                     "imms":imms,"mem":mem})
        # Exact wrappers are tiny; stop on ret to avoid bleeding into neighbour.
        if ins.mnemonic in ("ret","retf"):break
    return rows

def classify(pe,rows):
    g=[];b=[];sc=[];strings=[];targets=[]
    for r in rows:
        for m in r["mem"]:
            if abs(int(m.get("disp",0)))==WAD_BINDING_DISP and m.get("base") not in (None,"rip","rsp","rbp"):
                b.append({"site":r["rva"],"write":m["write"],"base":m["base"],
                          "disp":m["disp"],"op":r["op_str"]})
            t=m.get("rip_target")
            if t is not None:
                for name,val in STAGED_GLOBALS.items():
                    if t==val:g.append({"name":name,"site":r["rva"],"write":m["write"],"op":r["op_str"]})
                s=ascii_at(pe,t)
                if s:strings.append({"site":r["rva"],"target":t,"ascii":s})
        if r["mnemonic"] in ("call","jmp") and r["imms"]:
            t=r["imms"][0]
            if isinstance(t,int):
                targets.append({"site":r["rva"],"kind":r["mnemonic"],"target":t})
                for name,val in KNOWN_STAGED_FUNCTIONS.items():
                    fn=pe.function_for(val)
                    if t==val or (fn and fn["begin"]<=t<fn["end"]):
                        sc.append({"name":name,"site":r["rva"],"target":t})
    return g,b,sc,strings,targets

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

    nodes={}
    any_touch=False
    entry_results={}
    for label,start in ENTRYPOINTS.items():
        q=deque([(start,0,"exact_entry")])
        seen=set()
        visited=[]
        while q:
            rva,depth,source=q.popleft()
            if rva in seen or depth>2:continue
            seen.add(rva)
            fn=pe.function_for(rva)
            if source=="exact_entry":
                begin=rva; size=0x20
            elif fn:
                begin=fn["begin"];size=min(fn["end"]-fn["begin"],0x500)
            else:
                begin=rva;size=0x80
            key=(begin,size)
            if key not in nodes:
                rows=disasm_window(pe,md,begin,size,OP_IMM,OP_MEM,RIP,AC_WRITE)
                g,b,sc,strings,targets=classify(pe,rows)
                nodes[key]={"begin":begin,"size":size,"runtime_function":fn,
                            "instructions":rows,"staged_global_hits":g,
                            "wad_binding_hits":b,"known_staged_calls":sc,
                            "strings":strings,"targets":targets,
                            "touches_staged":bool(g or b or sc)}
            n=nodes[key]
            visited.append({"begin":begin,"size":size,"depth":depth,"source":source})
            any_touch=any_touch or n["touches_staged"]
            if depth<2:
                for t in n["targets"]:
                    target=t["target"]
                    sec=pe.section_for_rva(target)
                    if sec and sec.get("exec"):
                        q.append((target,depth+1,f"{t['kind']}_from_0x{t['site']:X}"))
        entry_results[label]={"entry":start,"visited":visited}

    ordered=[]
    for (_, _),n in sorted(nodes.items(),key=lambda kv:kv[1]["begin"]):
        ordered.append(n)

    out={"schema":1,"analysis":"lua_getref_exact_handlers","exe_sha256":digest,
         "entrypoints":ENTRYPOINTS,"entry_results":entry_results,
         "any_staged_touch":any_touch,"nodes":ordered,
         "safety":{"static_exe_read_only":True,"game_launched":False,
                   "process_accessed":False,"save_opened":False,"save_written":False,
                   "progression_written":False,"game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - exact GetRef* Lua handler trace",
           f"exe_sha256={digest}",f"any_staged_touch={str(any_touch).lower()}",""]
    for label,r in entry_results.items():
        lines.append(f"ENTRY {label}=0x{r['entry']:X}")
        for v in r["visited"]:
            lines.append(f"  VISIT depth={v['depth']} begin=0x{v['begin']:X} size=0x{v['size']:X} source={v['source']}")
        lines.append("")
    for n in ordered:
        lines.append(f"NODE 0x{n['begin']:X} size=0x{n['size']:X} touches_staged={str(n['touches_staged']).lower()}")
        for x in n["staged_global_hits"]:
            lines.append(f"  STAGED_GLOBAL {'WRITE' if x['write'] else 'READ'} {x['name']} site=0x{x['site']:X} {x['op']}")
        for x in n["wad_binding_hits"]:
            lines.append(f"  WAD_BINDING {'WRITE' if x['write'] else 'READ'} site=0x{x['site']:X} base={x['base']} disp=0x{x['disp']:X} {x['op']}")
        for x in n["known_staged_calls"]:
            lines.append(f"  STAGED_CALL {x['name']} site=0x{x['site']:X} -> 0x{x['target']:X}")
        for s in n["strings"]:
            lines.append(f"  STRING 0x{s['site']:X} -> 0x{s['target']:X} {s['ascii']!r}")
        for t in n["targets"]:
            lines.append(f"  {t['kind'].upper()} 0x{t['site']:X} -> 0x{t['target']:X}")
        lines.append("  DISASM")
        for r in n["instructions"]:
            lines.append(f"    0x{r['rva']:08X} {r['bytes']:<22} {r['mnemonic']:<8} {r['op_str']}")
        lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"LUA_GETREF_EXACT_TRACE_COMPLETE nodes={len(ordered)} any_staged_touch={str(any_touch).lower()}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
