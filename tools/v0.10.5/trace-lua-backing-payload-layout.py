#!/usr/bin/env python3
"""Trace exact durable Lua backing-node payload placement.

Targets only:
- 0x464410 backing-node creator/lookup
- 0x5A6430 normal/soft blob placement
- 0x5A5230 sibling +0x80 blob placement
plus small direct callees.

Static/read-only only.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGETS=(0x464410,0x5A6430,0x5A5230)
RAW_FALLBACK_RANGES={
    0x464410:(0x464410,0x464A50),
    0x5A6430:(0x5A6430,0x5A6500),
}
INTERESTING={0,8,0x10,0x18,0x20,0x28,0x30,0x38,0x40,0x48,0x50,0x58,0x60,0x68,0x70,0x78,0x80,0x88,0x90,0x98,0x100,0x158,0x170,0x178,0x188,0x190,0x198,0x2C8,0x390,0x410}

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("backing_payload_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def cstr_at(pe,rva,max_len=160):
    off=pe.rva_to_file(rva)
    if off is None:return None
    raw=pe.data[off:off+max_len]
    z=raw.find(b"\0")
    if z<0:z=len(raw)
    s=raw[:z]
    if len(s)<4:return None
    if not all((32<=b<127) or b in (9,10,13) for b in s):return None
    try:return s.decode("ascii")
    except Exception:return None

def resolve_fn(pe,addr):
    fn=pe.function_for(addr)
    if fn:
        return {"begin":fn["begin"],"end":fn["end"],"synthetic":False}
    if addr in RAW_FALLBACK_RANGES:
        b,e=RAW_FALLBACK_RANGES[addr]
        return {"begin":b,"end":e,"synthetic":True}
    return None

def decode(pe,md,fn,OI,OM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[];imms=[];strings=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OI:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OM:
                m={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "scale":op.mem.scale,"disp":op.mem.disp,"size":op.size}
                if op.mem.base==RIP:
                    t=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                    m["rip_target"]=t
                    s=cstr_at(pe,t)
                    if s:strings.append({"target":t,"text":s})
                mem.append(m)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                    "mem":mem,"imms":imms,"rip_strings":strings})
    return out

def field_hits(rows):
    out=[]
    for r in rows:
        for m in r["mem"]:
            if m.get("base") not in (None,"rsp","rbp","rip") and m["disp"] in INTERESTING:
                out.append({"site":r["rva"],"base":m["base"],"index":m["index"],
                            "scale":m["scale"],"disp":m["disp"],"size":m["size"],
                            "mnemonic":r["mnemonic"],"op":r["op_str"]})
    return out

def direct_calls(pe,rows):
    out=[]
    for r in rows:
        if r["mnemonic"]=="call" and r["imms"]:
            t=r["imms"][0]
            tf=resolve_fn(pe,t) if isinstance(t,int) else None
            out.append({"site":r["rva"],"target":t,
                        "function_begin":tf["begin"] if tf else None,
                        "function_end":tf["end"] if tf else None})
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
    Cs,ARCH,MODE,OI,OM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE);md.detail=True

    targets=[]
    small=set()
    seen=set()
    for addr in TARGETS:
        fn=resolve_fn(pe,addr)
        if not fn:raise RuntimeError(f"No runtime function or raw fallback for 0x{addr:X}")
        b=fn["begin"]
        if b in seen:continue
        seen.add(b)
        rows=decode(pe,md,fn,OI,OM,RIP)
        calls=direct_calls(pe,rows)
        targets.append({"anchor":addr,"begin":b,"end":fn["end"],"size":fn["end"]-b,
                        "synthetic_range":bool(fn.get("synthetic",False)),
                        "field_hits":field_hits(rows),"calls":calls,"instructions":rows})
        for c in calls:
            fb=c["function_begin"];fe=c["function_end"]
            if fb is not None and fe is not None and fe-fb<=0x260:
                small.add(fb)

    small_rows=[]
    for b in sorted(small-seen):
        fn=pe.function_for(b)
        if not fn:continue
        rows=decode(pe,md,fn,OI,OM,RIP)
        # only keep callees with useful memory fields or strings
        fh=field_hits(rows)
        strings=[s for r in rows for s in r["rip_strings"]]
        if fh or strings:
            small_rows.append({"begin":b,"end":fn["end"],"size":fn["end"]-b,
                               "field_hits":fh,"calls":direct_calls(pe,rows),
                               "strings":strings,"instructions":rows})

    report={"schema":1,"analysis":"lua_backing_payload_layout","exe_sha256":digest,
            "targets":targets,"small_callees":small_rows,
            "safety":{"static_exe_read_only":True,"game_launched":False,
                      "process_accessed":False,"save_opened":False,"save_written":False,
                      "progression_written":False,"game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=["Completionist Map - durable Lua backing payload layout",f"exe_sha256={digest}","mode=static read-only",""]
    def emit(label,f):
        L.append(f"{label} 0x{f['begin']:X}..0x{f['end']:X} anchor="+(f"0x{f['anchor']:X}" if "anchor" in f else "-"))
        for h in f.get("field_hits",[]):
            L.append(f"  FIELD 0x{h['site']:X} {h['mnemonic']} base={h['base']} index={h['index']} scale={h['scale']} +0x{h['disp']:X} size={h['size']} {h['op']}")
        for c in f.get("calls",[]):
            fb=c["function_begin"]
            L.append(f"  CALL 0x{c['site']:X} -> 0x{c['target']:X}"+(f" fn=0x{fb:X}" if fb is not None else ""))
        for s in f.get("strings",[]):
            L.append(f"  STR 0x{s['target']:X} {s['text']!r}")
        L.append("  DISASM")
        for r in f["instructions"]:
            ss=" ".join(f"str@0x{s['target']:X}={s['text']!r}" for s in r["rip_strings"])
            L.append(f"    0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"+((" ; "+ss) if ss else ""))
        L.append("")
    for f in targets:emit("TARGET",f)
    L.append("SMALL DIRECT CALLEES")
    for f in small_rows:emit("CALLEE",f)
    L.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_PAYLOAD_LAYOUT_COMPLETE targets={len(targets)} small={len(small_rows)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
