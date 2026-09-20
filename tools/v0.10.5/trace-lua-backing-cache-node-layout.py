#!/usr/bin/env python3
"""Recover the durable Lua backing-cache node layout and resource-key path.

Targets only the already-proven LuaContext/LuaLevelClient cache lifecycle:
- 0x463C60 backing-node retain/release/helper
- 0x464410 backing-node creator/lookup (return passed to LuaLevelClient ctor)
- 0x46538B detach -> LuaContext+0x178 cache insertion
- 0x4654A0 cache lookup / LuaClient creation
- 0x5A6DD0 LuaLevelClient constructor
- 0x5A7720 live -> durable backing transfer

Static/read-only. No game/save/process access.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from collections import defaultdict, deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
FOCUS=(0x463C60,0x464410,0x46538B,0x4654A0,0x5A6DD0,0x5A7720)
INTERESTING_DISPS={0,8,0x10,0x18,0x20,0x28,0x30,0x38,0x40,0x48,0x50,0x58,0x60,0x68,0x70,0x78,0x80,0x88,0x90,0x98,0x100,0x158,0x170,0x178,0x180,0x188,0x190,0x198,0x2C8}
ALLOCATORS={0x40BF10,0xD21A90,0xD21DD0,0x40C230}
BRIDGES={0x5A6DD0,0x5A7720,0x5A6C10,0x5A6270,0x463C60,0x464410}

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("backing_cache_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(repo):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def cstr_at(pe,rva,max_len=180):
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

def decode_fn(pe,md,fn,OI,OM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    rows=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        mem=[];imms=[];rip_strings=[]
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
                    target=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                    m["rip_target"]=target
                    s=cstr_at(pe,target)
                    if s:rip_strings.append({"target":target,"text":s})
                mem.append(m)
        rows.append({"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,
                     "op_str":ins.op_str,"mem":mem,"imms":imms,"rip_strings":rip_strings})
    return rows

def classify(rows):
    hits=[]
    for row in rows:
        for m in row["mem"]:
            if m.get("base") not in (None,"rsp","rbp","rip") and m["disp"] in INTERESTING_DISPS:
                hits.append({"site":row["rva"],"kind":"field","base":m["base"],"disp":m["disp"],
                             "size":m["size"],"op":row["op_str"]})
            if m.get("base")=="rip" and m.get("rip_target") is not None:
                hits.append({"site":row["rva"],"kind":"rip","target":m["rip_target"],"op":row["op_str"]})
        if row["mnemonic"] in ("call","jmp") and row["imms"]:
            t=row["imms"][0]
            if t in ALLOCATORS:
                hits.append({"site":row["rva"],"kind":"allocator_call","target":t,"op":row["op_str"]})
            elif t in BRIDGES:
                hits.append({"site":row["rva"],"kind":"bridge_call","target":t,"op":row["op_str"]})
    return hits

def direct_edges(pe,md,OI,OM,RIP):
    callers=defaultdict(list);callees=defaultdict(list);cache={}
    for fn in pe.runtime_functions:
        rows=decode_fn(pe,md,fn,OI,OM,RIP)
        cache[fn["begin"]]=rows
        for row in rows:
            if row["mnemonic"]=="call" and row["imms"]:
                t=row["imms"][0]
                tf=pe.function_for(t) if isinstance(t,int) else None
                if tf:
                    edge={"caller":fn["begin"],"site":row["rva"],"target":tf["begin"],"raw_target":t}
                    callers[tf["begin"]].append(edge);callees[fn["begin"]].append(edge)
    return callers,callees,cache

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
    callers,callees,cache=direct_edges(pe,md,OI,OM,RIP)

    focus=[]
    focus_begins=set()
    for addr in FOCUS:
        fn=pe.function_for(addr)
        if not fn:continue
        b=fn["begin"]
        if b in focus_begins:continue
        focus_begins.add(b)
        rows=cache.get(b) or decode_fn(pe,md,fn,OI,OM,RIP)
        focus.append({"anchor":addr,"begin":b,"end":fn["end"],"size":fn["end"]-b,
                      "hits":classify(rows),"callers":callers.get(b,[]),
                      "callees":callees.get(b,[]),"instructions":rows})

    # Two-hop direct neighbourhood around creator/helper and cache lifecycle.
    seeds=set(focus_begins)
    q=deque((s,0) for s in seeds);seen=set(seeds)
    while q:
        n,d=q.popleft()
        if d>=2:continue
        for e in callers.get(n,[])+callees.get(n,[]):
            m=e["caller"] if e["target"]==n else e["target"]
            if m not in seen:
                seen.add(m);q.append((m,d+1))
    neighborhood=[]
    for b in sorted(seen-focus_begins):
        fn=pe.function_for(b)
        if not fn or fn["end"]-fn["begin"]>0x1800:continue
        rows=cache.get(b) or decode_fn(pe,md,fn,OI,OM,RIP)
        hs=classify(rows)
        # keep only nodes with a useful struct field, allocator, bridge, or direct relation to creator
        useful=[h for h in hs if h["kind"] in ("field","allocator_call","bridge_call")]
        if useful:
            neighborhood.append({"begin":b,"end":fn["end"],"size":fn["end"]-b,
                                 "hits":useful,"callers":callers.get(b,[]),
                                 "callees":callees.get(b,[]),"instructions":rows})

    # Extract decisive cache-key sequences compactly from 0x4654A0 and insertion from 0x46538B.
    sequences={}
    for f in focus:
        rows=f["instructions"]
        if f["begin"]<=0x4654A0<f["end"]:
            sequences["cache_lookup"]=[r for r in rows if 0x465800<=r["rva"]<=0x4658A5]
        if f["begin"]<=0x46538B<f["end"]:
            sequences["cache_insert"]=[r for r in rows if 0x4653AA<=r["rva"]<=0x4653E5]
        if f["begin"]<=0x464410<f["end"]:
            sequences["backing_creator"]=[r for r in rows]
        if f["begin"]<=0x463C60<f["end"]:
            sequences["backing_helper"]=[r for r in rows]

    report={"schema":1,"analysis":"lua_backing_cache_node_layout","exe_sha256":digest,
            "focus":focus,"neighborhood":neighborhood,"sequences":sequences,
            "safety":{"static_exe_read_only":True,"game_launched":False,"process_accessed":False,
                      "save_opened":False,"save_written":False,"progression_written":False,"game_files_written":False}}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=["Completionist Map - LuaContext durable backing-cache node layout",f"exe_sha256={digest}",
       "mode=static read-only",""]
    def emit(label,f,full=True):
        L.append(f"{label} 0x{f['begin']:X}..0x{f['end']:X} size=0x{f['size']:X}")
        L.append("  CALLERS "+",".join(f"0x{x['caller']:X}@0x{x['site']:X}" for x in f["callers"]))
        for h in f["hits"]:
            if h["kind"]=="field":
                L.append(f"  FIELD 0x{h['site']:X} base={h['base']} +0x{h['disp']:X} size={h['size']} {h['op']}")
            elif h["kind"] in ("allocator_call","bridge_call"):
                L.append(f"  {h['kind'].upper()} 0x{h['site']:X} -> 0x{h['target']:X} {h['op']}")
        if full:
            for r in f["instructions"]:
                ss=" ".join(f"str@0x{s['target']:X}={s['text']!r}" for s in r["rip_strings"])
                L.append(f"  0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"+((" ; "+ss) if ss else ""))
        L.append("")
    for f in focus:emit("FOCUS",f,True)
    L.append("TWO-HOP USEFUL NEIGHBOURHOOD")
    for f in neighborhood:emit("FUNCTION",f,False)
    L.append("DECISIVE SEQUENCES")
    for name,rows in sequences.items():
        L.append(name)
        for r in rows:
            ss=" ".join(f"str@0x{s['target']:X}={s['text']!r}" for s in r["rip_strings"])
            L.append(f"  0x{r['rva']:08X} {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"+((" ; "+ss) if ss else ""))
        L.append("")
    L.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_CACHE_NODE_LAYOUT_COMPLETE focus={len(focus)} neighborhood={len(neighborhood)}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
