#!/usr/bin/env python3
"""Trace allocator primitives behind Lua backing-node +0x28.

Static/read-only. Targets only the allocation/free/preparation family needed to
enumerate live normal/soft checkpoint blobs:
- 0xD21A90
- 0xD1F7F0
- 0xD21DD0
- 0x5AB340
plus small direct callees and field-access summaries.

No game/process/save access.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGETS=(0xD21A90,0xD1F7F0,0xD21DD0,0x5AB340)
RAW_FALLBACK={
    0xD21A90:(0xD21A90,0xD22080),
    0xD1F7F0:(0xD1F7F0,0xD1FD00),
    0xD21DD0:(0xD21DD0,0xD22100),
    0x5AB340:(0x5AB340,0x5AB700),
}
INTERESTING_DISPS=set(range(0,0x101,8))|{0x110,0x118,0x120,0x128,0x130,0x138,0x140,0x148,0x150,0x158,0x160,0x168,0x170,0x178,0x180,0x188,0x190,0x198,0x1A0,0x1B0,0x1C0,0x200,0x208,0x210,0x218,0x220}

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("alloc_pe",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir():sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def cstr(pe,rva,max_len=180):
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
    if fn and fn["begin"]==addr and fn["end"]-fn["begin"]>=0x20:
        return {"begin":fn["begin"],"end":fn["end"],"synthetic":False}
    if addr in RAW_FALLBACK:
        b,e=RAW_FALLBACK[addr]
        return {"begin":b,"end":e,"synthetic":True}
    if fn:return {"begin":fn["begin"],"end":fn["end"],"synthetic":False}
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
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OM:
                m={"base":md.reg_name(op.mem.base) if op.mem.base else None,
                   "index":md.reg_name(op.mem.index) if op.mem.index else None,
                   "scale":op.mem.scale,"disp":int(op.mem.disp),"size":op.size}
                if op.mem.base==RIP:
                    t=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                    m["rip_target"]=t
                    s=cstr(pe,t)
                    if s:strings.append({"target":t,"text":s})
                mem.append(m)
        out.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),
                    "mnemonic":ins.mnemonic,"op_str":ins.op_str,
                    "mem":mem,"imms":imms,"rip_strings":strings})
    return out

def summarize(pe,rows):
    fields=[];calls=[];jumps=[]
    for r in rows:
        for m in r["mem"]:
            if m.get("base") not in (None,"rip","rsp","rbp") and m["disp"] in INTERESTING_DISPS:
                fields.append({"site":r["rva"],"base":m["base"],"index":m["index"],"scale":m["scale"],
                               "disp":m["disp"],"size":m["size"],"mnemonic":r["mnemonic"],"op":r["op_str"]})
        if r["mnemonic"]=="call" and r["imms"]:
            t=r["imms"][0];tf=pe.function_for(t) if isinstance(t,int) else None
            calls.append({"site":r["rva"],"target":t,"function_begin":tf["begin"] if tf else None,
                          "function_end":tf["end"] if tf else None})
        elif r["mnemonic"].startswith("j") and r["imms"]:
            jumps.append({"site":r["rva"],"target":r["imms"][0],"mnemonic":r["mnemonic"]})
    return fields,calls,jumps

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

    targets=[];small=set();seen=set()
    for addr in TARGETS:
        fn=resolve_fn(pe,addr)
        if not fn:raise RuntimeError(f"No function/range for 0x{addr:X}")
        rows=decode(pe,md,fn,OI,OM,RIP)
        fields,calls,jumps=summarize(pe,rows)
        targets.append({"anchor":addr,"begin":fn["begin"],"end":fn["end"],"synthetic":fn["synthetic"],
                        "field_hits":fields,"calls":calls,"jumps":jumps,"instructions":rows})
        seen.add(fn["begin"])
        for c in calls:
            fb=c["function_begin"];fe=c["function_end"]
            if fb is not None and fe is not None and 0<fe-fb<=0x300:small.add(fb)

    secondary=[]
    for b in sorted(small-seen):
        fn=pe.function_for(b)
        if not fn:continue
        rows=decode(pe,md,fn,OI,OM,RIP)
        fields,calls,jumps=summarize(pe,rows)
        if fields or any(r["rip_strings"] for r in rows):
            secondary.append({"begin":fn["begin"],"end":fn["end"],"field_hits":fields,
                              "calls":calls,"jumps":jumps,"instructions":rows})

    report={"schema":1,"analysis":"lua_backing_allocator_primitives","exe_sha256":digest,
            "targets":targets,"secondary":secondary,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=["Completionist Map - Lua backing allocator primitive trace",f"exe_sha256={digest}","mode=static read-only",""]
    def emit(label,f):
        L.append(f"{label} 0x{f['begin']:X}..0x{f['end']:X}"+(f" anchor=0x{f['anchor']:X}" if 'anchor' in f else "")+f" synthetic={f.get('synthetic',False)}")
        for h in f["field_hits"]:
            L.append(f"  FIELD 0x{h['site']:X} {h['mnemonic']} base={h['base']} index={h['index']} scale={h['scale']} +0x{h['disp']:X} size={h['size']} {h['op']}")
        for c in f["calls"]:
            t=c["target"];fb=c["function_begin"]
            L.append(f"  CALL 0x{c['site']:X} -> 0x{t:X}"+(f" fn=0x{fb:X}" if fb is not None else ""))
        for r in f["instructions"]:
            ss=" ".join(f"str@0x{s['target']:X}={s['text']!r}" for s in r["rip_strings"])
            L.append(f"  0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"+((" ; "+ss) if ss else ""))
        L.append("")
    for f in targets:emit("TARGET",f)
    L.append("SMALL DIRECT CALLEES")
    for f in secondary:emit("CALLEE",f)
    L.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_ALLOCATOR_PRIMITIVES_COMPLETE targets={len(targets)} secondary={len(secondary)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
