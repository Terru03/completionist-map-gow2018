#!/usr/bin/env python3
"""Discover God of War Lua map/marker enumeration APIs.

Static, read-only, version-locked analysis. Scans printable strings in GoW.exe,
clusters map/marker API names around known anchors, and resolves RIP-relative
code references back to containing functions using the existing research index.

No game launch, process access, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, sqlite3, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
ANCHORS=(
    "GetMarkerInfo","MarkerHasFlag","CreateMarkerIcon",
    "FindMarkersByIconClass","ShowMarker","HideMarker",
)
TERMS=("marker","map","compass","region","quest","icon","dock","objective")
MAX_NEAR=0x2000

def sha256(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("gow_marker_api_pe",p)
    if not spec or not spec.loader: raise RuntimeError("PE helper load failed")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def load_cs():
    root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
    if root.is_dir():sys.path.insert(0,str(root))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_MEM,X86_REG_RIP

def fn_for(con,rva):
    row=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
    return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def ascii_strings(data,minlen=4):
    out=[]
    start=None
    for i,b in enumerate(data):
        good=32<=b<=126
        if good and start is None:start=i
        if (not good or i==len(data)-1) and start is not None:
            end=i if not good else i+1
            if end-start>=minlen:
                try:s=data[start:end].decode("ascii")
                except Exception:s=""
                if s:out.append((start,s))
            start=None
    return out

def score_string(s):
    l=s.lower()
    score=0
    for t in TERMS:
        if t in l:score+=2
    if any(a.lower() in l for a in ANCHORS):score+=12
    if re.match(r"^[A-Za-z_][A-Za-z0-9_:.]{3,80}$",s):score+=2
    return score

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sha256(a.exe)!=EXPECTED:raise RuntimeError("unsupported GoW.exe")

    peh=load_pe();pe=peh.PE(a.exe.read_bytes())
    Cs,arch,mode,X86_OP_MEM,X86_REG_RIP=load_cs()
    md=Cs(arch,mode);md.detail=True
    con=sqlite3.connect(a.db)
    try:
        strings=[]
        for off,s in ascii_strings(pe.data):
            rva=pe.file_to_rva(off) if hasattr(pe,"file_to_rva") else None
            if rva is None:
                # Invert rva_to_file over sections if helper lacks file_to_rva.
                for sec in getattr(pe,"sections",[]):
                    raw=getattr(sec,"pointer_to_raw_data",getattr(sec,"raw_ptr",None))
                    rawsz=getattr(sec,"size_of_raw_data",getattr(sec,"raw_size",None))
                    va=getattr(sec,"virtual_address",getattr(sec,"rva",None))
                    if raw is not None and rawsz is not None and va is not None and raw<=off<raw+rawsz:
                        rva=va+(off-raw);break
            if rva is None:continue
            sc=score_string(s)
            if sc>0:strings.append({"rva":rva,"file_offset":off,"string":s,"score":sc})

        anchors=[x for x in strings if any(a0.lower() in x["string"].lower() for a0 in ANCHORS)]
        if not anchors:raise RuntimeError("known marker API strings not found")

        nearby={}
        for an in anchors:
            arr=[]
            for x in strings:
                d=abs(x["rva"]-an["rva"])
                if d<=MAX_NEAR and x["score"]>=2:
                    arr.append({**x,"distance":d})
            arr.sort(key=lambda x:(x["distance"],-x["score"],x["rva"]))
            nearby[f"0x{an['rva']:X}:{an['string']}"]=arr[:160]

        # Resolve RIP-relative xrefs to every interesting API-ish string.
        targets={x["rva"]:x for x in strings if x["score"]>=4}
        xrefs=[]
        for row in con.execute("SELECT begin,end,size,section FROM functions WHERE size>0 AND size<=16384 ORDER BY begin"):
            fn={"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}
            off=pe.rva_to_file(fn["begin"])
            if off is None:continue
            for ins in md.disasm(pe.data[off:off+fn["size"]],IMAGE_BASE+fn["begin"]):
                try:ops=list(ins.operands)
                except Exception:ops=[]
                for op in ops:
                    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                        t=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
                        if t in targets:
                            xrefs.append({
                                "function":fn["begin"],"site":ins.address-IMAGE_BASE,
                                "target_rva":t,"string":targets[t]["string"],
                                "instruction":f"{ins.mnemonic} {ins.op_str}",
                            })

        # Candidate enumeration-ish names.
        enum_words=("all","list","enum","enumer","find","getmarkers","markers","iterate","count")
        candidates=[]
        seen=set()
        for x in strings:
            l=x["string"].lower()
            if "marker" not in l:continue
            if any(w in l for w in enum_words):
                key=(x["rva"],x["string"])
                if key not in seen:
                    seen.add(key);candidates.append(x)
        candidates.sort(key=lambda x:(-x["score"],x["rva"]))

        out={
            "schema":1,"analysis":"map_marker_lua_api_discovery","exe_sha256":EXPECTED,
            "anchors":anchors,"nearby":nearby,"xrefs":xrefs,
            "enumeration_candidates":candidates[:300],
            "safety":{"static_pe_only":True,"game_launched":False,"process_opened":False,
                      "save_opened":False,"exe_modified":False}
        }
        a.output_json.parent.mkdir(parents=True,exist_ok=True)
        a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

        lines=[
            "Completionist Map - map/marker Lua API discovery",
            f"exe_sha256={EXPECTED}",
            f"anchors={len(anchors)} api_strings={len(strings)} xrefs={len(xrefs)} enum_candidates={len(candidates)}",
            "game_launched=false process_opened=false save_opened=false exe_modified=false","",
            "ENUMERATION_CANDIDATES"
        ]
        for x in candidates[:120]:
            lines.append(f"  0x{x['rva']:X} score={x['score']} {x['string']!r}")
        lines.append("")
        lines.append("ANCHOR_NEIGHBOURHOODS")
        for k,arr in nearby.items():
            lines.append(f"  ANCHOR {k}")
            for x in arr[:80]:
                lines.append(f"    d=0x{x['distance']:X} rva=0x{x['rva']:X} score={x['score']} {x['string']!r}")
        lines.append("")
        lines.append("XREFS")
        for x in xrefs[:500]:
            lines.append(f"  fn=0x{x['function']:X} site=0x{x['site']:X} -> 0x{x['target_rva']:X} {x['string']!r} | {x['instruction']}")
        a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

        print(f"MAP_MARKER_API_DISCOVERY_COMPLETE anchors={len(anchors)} api_strings={len(strings)} xrefs={len(xrefs)} enum_candidates={len(candidates)}")
        for x in candidates[:40]:
            print(f"CANDIDATE 0x{x['rva']:X} {x['string']}")
        return 0
    finally:
        con.close()

if __name__=="__main__":raise SystemExit(main())
