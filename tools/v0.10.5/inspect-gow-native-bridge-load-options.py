#!/usr/bin/env python3
"""Inspect GoW.exe imports for a clean-room native bridge load path.

Purpose:
- keep the existing unmodified Script Loader version.dll;
- find another DLL name already imported by GoW that can host a separate
  Completionist Map native bridge;
- rank common proxy candidates by imported symbol count.

Static/read-only only. No game launch, process attach, or writes.
"""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

CANDIDATES=[
    "dxgi.dll",
    "dinput8.dll",
    "winmm.dll",
    "xinput1_4.dll",
    "xinput9_1_0.dll",
    "dbghelp.dll",
    "dsound.dll",
    "winhttp.dll",
    "wininet.dll",
    "cryptsp.dll",
]
EXCLUDED={"version.dll":"already occupied by Nukem9 Script Loader"}

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def u16(b,o):return struct.unpack_from("<H",b,o)[0]
def u32(b,o):return struct.unpack_from("<I",b,o)[0]
def u64(b,o):return struct.unpack_from("<Q",b,o)[0]

class PE:
    def __init__(self,data:bytes):
        self.data=data
        if data[:2]!=b"MZ":raise RuntimeError("not MZ")
        peoff=u32(data,0x3C)
        if data[peoff:peoff+4]!=b"PE\0\0":raise RuntimeError("not PE")
        fh=peoff+4
        self.nsects=u16(data,fh+2)
        opt_size=u16(data,fh+16)
        opt=fh+20
        magic=u16(data,opt)
        if magic!=0x20B:raise RuntimeError(f"expected PE32+, got 0x{magic:X}")
        self.image_base=u64(data,opt+24)
        dd=opt+112
        self.import_rva=u32(data,dd+8)
        self.import_size=u32(data,dd+12)
        self.delay_rva=u32(data,dd+13*8)
        self.delay_size=u32(data,dd+13*8+4)
        sec=opt+opt_size
        self.sections=[]
        for i in range(self.nsects):
            o=sec+i*40
            name=data[o:o+8].split(b"\0",1)[0].decode("ascii","replace")
            vsize=u32(data,o+8); rva=u32(data,o+12)
            rawsize=u32(data,o+16); raw=u32(data,o+20)
            self.sections.append(dict(name=name,vsize=vsize,rva=rva,rawsize=rawsize,raw=raw))
    def rva_to_off(self,rva:int):
        for s in self.sections:
            span=max(s["vsize"],s["rawsize"])
            if s["rva"]<=rva<s["rva"]+span:
                d=rva-s["rva"]
                if d>=s["rawsize"]:return None
                return s["raw"]+d
        return None
    def cstr(self,rva:int):
        o=self.rva_to_off(rva)
        if o is None:return None
        z=self.data.find(b"\0",o)
        if z<0:z=min(len(self.data),o+4096)
        return self.data[o:z].decode("ascii","replace")

def parse_thunks(pe:PE, thunk_rva:int):
    out=[]
    off=pe.rva_to_off(thunk_rva)
    if off is None:return out
    i=0
    while True:
        if off+i*8+8>len(pe.data):break
        v=u64(pe.data,off+i*8)
        if v==0:break
        if v & (1<<63):
            out.append({"ordinal":v & 0xFFFF,"name":None})
        else:
            no=pe.rva_to_off(v)
            if no is None:
                out.append({"ordinal":None,"name":None})
            else:
                hint=u16(pe.data,no)
                z=pe.data.find(b"\0",no+2)
                if z<0:z=min(len(pe.data),no+258)
                name=pe.data[no+2:z].decode("ascii","replace")
                out.append({"ordinal":None,"hint":hint,"name":name})
        i+=1
        if i>65536:break
    return out

def parse_imports(pe:PE):
    imports=[]
    if pe.import_rva:
        off=pe.rva_to_off(pe.import_rva)
        if off is not None:
            i=0
            while True:
                o=off+i*20
                if o+20>len(pe.data):break
                oft=u32(pe.data,o); tds=u32(pe.data,o+4); fwd=u32(pe.data,o+8)
                name_rva=u32(pe.data,o+12); ft=u32(pe.data,o+16)
                if not (oft or tds or fwd or name_rva or ft):break
                dll=pe.cstr(name_rva) or "<bad-name>"
                syms=parse_thunks(pe,oft or ft)
                imports.append({"kind":"normal","dll":dll,"symbols":syms})
                i+=1
                if i>4096:break
    # PE delay-load descriptor is 32 bytes.
    delays=[]
    if pe.delay_rva:
        off=pe.rva_to_off(pe.delay_rva)
        if off is not None:
            i=0
            while True:
                o=off+i*32
                if o+32>len(pe.data):break
                attrs=u32(pe.data,o); namev=u32(pe.data,o+4); hmod=u32(pe.data,o+8)
                iat=u32(pe.data,o+12); intv=u32(pe.data,o+16)
                bound=u32(pe.data,o+20); unload=u32(pe.data,o+24); stamp=u32(pe.data,o+28)
                if not (attrs or namev or hmod or iat or intv or bound or unload or stamp):break
                # attrs bit0==1 => fields are RVAs. If not, convert VA to RVA.
                def torva(v):
                    return v if (attrs&1) else (v-pe.image_base if v>=pe.image_base else v)
                dll=pe.cstr(torva(namev)) or "<bad-name>"
                syms=parse_thunks(pe,torva(intv or iat))
                delays.append({"kind":"delay","dll":dll,"symbols":syms})
                i+=1
                if i>4096:break
    return imports+delays

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
    pe=PE(exe.read_bytes())
    rows=parse_imports(pe)

    by={}
    for r in rows:
        key=r["dll"].lower()
        e=by.setdefault(key,{"dll":r["dll"],"kinds":set(),"symbols":[]})
        e["kinds"].add(r["kind"])
        e["symbols"].extend(r["symbols"])

    normalized=[]
    for k,e in sorted(by.items()):
        names=sorted({s.get("name") for s in e["symbols"] if s.get("name")})
        ords=sorted({s.get("ordinal") for s in e["symbols"] if s.get("ordinal") is not None})
        normalized.append({
            "dll":e["dll"],
            "kinds":sorted(e["kinds"]),
            "import_count":len(e["symbols"]),
            "named_imports":names,
            "ordinals":ords,
        })

    ranked=[]
    for name in CANDIDATES:
        e=next((x for x in normalized if x["dll"].lower()==name),None)
        ranked.append({
            "dll":name,
            "imported":e is not None,
            "kinds":e["kinds"] if e else [],
            "import_count":e["import_count"] if e else 0,
            "named_imports":e["named_imports"] if e else [],
            "ordinals":e["ordinals"] if e else [],
            "already_occupied":False,
        })
    for name,why in EXCLUDED.items():
        e=next((x for x in normalized if x["dll"].lower()==name),None)
        ranked.append({
            "dll":name,"imported":e is not None,
            "kinds":e["kinds"] if e else [],
            "import_count":e["import_count"] if e else 0,
            "named_imports":e["named_imports"] if e else [],
            "ordinals":e["ordinals"] if e else [],
            "already_occupied":True,"reason":why,
        })

    viable=[x for x in ranked if x["imported"] and not x["already_occupied"]]
    viable.sort(key=lambda x:(x["import_count"],x["dll"]))

    result={
        "schema":1,
        "analysis":"gow_native_bridge_load_options",
        "exe_sha256":digest,
        "all_imports":normalized,
        "candidate_rankings":ranked,
        "viable_candidates":viable,
        "preferred_candidate":viable[0] if viable else None,
        "safety":{
            "static_exe_read_only":True,
            "game_launched":False,
            "process_accessed":False,
            "save_opened":False,
            "save_written":False,
            "progression_written":False,
            "game_files_written":False,
        },
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - GoW native bridge load options",
        f"exe_sha256={digest}",
        f"imported_dll_count={len(normalized)}",
        "",
        "PROXY_CANDIDATES",
    ]
    for x in sorted(ranked,key=lambda r:(not r["imported"],r["already_occupied"],r["import_count"],r["dll"])):
        lines.append(
            f"  {x['dll']}: imported={str(x['imported']).lower()} "
            f"kinds={','.join(x['kinds']) or '-'} imports={x['import_count']} "
            f"occupied={str(x['already_occupied']).lower()}"
        )
        if x.get("reason"):lines.append(f"    reason={x['reason']}")
        if x["named_imports"]:lines.append("    names="+", ".join(x["named_imports"]))
        if x["ordinals"]:lines.append("    ordinals="+", ".join(str(v) for v in x["ordinals"]))
    lines.append("")
    if viable:
        x=viable[0]
        lines.append(f"PREFERRED_STATIC_CANDIDATE {x['dll']} imports={x['import_count']} kinds={','.join(x['kinds'])}")
    else:
        lines.append("PREFERRED_STATIC_CANDIDATE NONE")
    lines.append("")
    lines.append("ALL_IMPORTED_DLLS")
    for x in normalized:
        lines.append(f"  {x['dll']} kinds={','.join(x['kinds'])} imports={x['import_count']}")
    lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    pref=viable[0]["dll"] if viable else "none"
    print(f"GOW_NATIVE_BRIDGE_LOAD_OPTIONS_COMPLETE imported_dlls={len(normalized)} preferred={pref}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
