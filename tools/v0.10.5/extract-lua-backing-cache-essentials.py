#!/usr/bin/env python3
"""Extract only decisive durable Lua backing-cache facts from an existing report.

Post-processes trace-lua-backing-cache-node-layout.py output.
No executable scan, game launch, process access, or save access.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

KEEP_BEGINS={0x463C60,0x464410,0x46538B,0x4654A0,0x5A6DD0,0x5A7720}
FULL_INSN_BEGINS={0x463C60,0x464410}
KEEP_SEQS={"cache_insert","cache_lookup","backing_creator","backing_helper"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--report-json",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    data=json.loads(a.report_json.read_text(encoding="utf-8"))

    focus=[]
    for f in data.get("focus",[]):
        b=int(f.get("begin",0))
        if b not in KEEP_BEGINS: continue
        row={
            "anchor":f.get("anchor"),"begin":b,"end":f.get("end"),"size":f.get("size"),
            "hits":f.get("hits",[]),"callers":f.get("callers",[]),"callees":f.get("callees",[])
        }
        if b in FULL_INSN_BEGINS:
            row["instructions"]=f.get("instructions",[])
        focus.append(row)

    seqs={k:v for k,v in data.get("sequences",{}).items() if k in KEEP_SEQS}

    # Cache-node-specific field uses only. Ignore generic context/client offsets except
    # where they are part of the decisive lifecycle functions.
    field_uses=[]
    for f in focus:
        for h in f.get("hits",[]):
            if h.get("kind")=="field":
                field_uses.append({
                    "function":f["begin"],"site":h.get("site"),"base":h.get("base"),
                    "disp":h.get("disp"),"size":h.get("size"),"op":h.get("op")
                })

    out={
        "schema":1,"analysis":"lua_backing_cache_essentials",
        "source_report":str(a.report_json.resolve()),
        "exe_sha256":data.get("exe_sha256"),
        "focus":focus,"sequences":seqs,"field_uses":field_uses,
        "safety":{"postprocess_only":True,"game_launched":False,"process_accessed":False,
                  "save_opened":False,"save_written":False,"progression_written":False,
                  "game_files_written":False}
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=[
      "Completionist Map - durable Lua backing-cache essentials",
      f"exe_sha256={data.get('exe_sha256')}",
      f"focus={len(focus)} sequences={len(seqs)} field_uses={len(field_uses)}",
      ""
    ]
    for f in focus:
        L.append(f"FOCUS 0x{f['begin']:X}..0x{int(f.get('end',0)):X} anchor=0x{int(f.get('anchor',0)):X}")
        if f.get("callers"):
            L.append("  CALLERS "+",".join(f"0x{int(e.get('caller',0)):X}@0x{int(e.get('site',0)):X}" for e in f["callers"]))
        if f.get("callees"):
            L.append("  CALLEES "+",".join(f"0x{int(e.get('target',0)):X}@0x{int(e.get('site',0)):X}" for e in f["callees"]))
        for h in f.get("hits",[]):
            k=h.get("kind")
            if k=="field":
                L.append(f"  FIELD 0x{int(h.get('site',0)):X} base={h.get('base')} +0x{int(h.get('disp',0)):X} size={h.get('size')} {h.get('op')}")
            elif k in ("allocator_call","bridge_call"):
                L.append(f"  {k.upper()} 0x{int(h.get('site',0)):X} -> 0x{int(h.get('target',0)):X} {h.get('op')}")
        if f.get("instructions"):
            L.append("  DISASM")
            for r in f["instructions"]:
                ss=" ".join(f"str@0x{int(s.get('target',0)):X}={s.get('text')!r}" for s in r.get("rip_strings",[]))
                L.append(f"    0x{int(r.get('rva',0)):08X} {r.get('bytes',''):<24} {r.get('mnemonic',''):<8} {r.get('op_str','')}"+((" ; "+ss) if ss else ""))
        L.append("")

    L.append("DECISIVE SEQUENCES")
    for name,rows in seqs.items():
        L.append(name)
        for r in rows:
            ss=" ".join(f"str@0x{int(s.get('target',0)):X}={s.get('text')!r}" for s in r.get("rip_strings",[]))
            L.append(f"  0x{int(r.get('rva',0)):08X} {r.get('bytes',''):<24} {r.get('mnemonic',''):<8} {r.get('op_str','')}"+((" ; "+ss) if ss else ""))
        L.append("")

    L.append("FIELD USES")
    for x in field_uses:
        L.append(f"fn=0x{x['function']:X} site=0x{int(x.get('site',0)):X} base={x.get('base')} +0x{int(x.get('disp',0)):X} size={x.get('size')} {x.get('op')}")
    L.append("")
    L.append("SAFETY postprocess_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_CACHE_ESSENTIALS_COMPLETE focus={len(focus)} sequences={len(seqs)} fields={len(field_uses)}")
    print("postprocess_only=true save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
