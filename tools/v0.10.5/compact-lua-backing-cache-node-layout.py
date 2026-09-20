#!/usr/bin/env python3
"""Compact an existing lua-backing-cache-node-layout report.

Reads the latest (or supplied) report.json produced by
trace-lua-backing-cache-node-layout.py and emits only:
- focus functions
- decisive cache sequences
- one-hop/two-hop neighbourhood entries directly related to the creator/helper
- concise inferred field-access inventory

No executable scan, game launch, process access, or save access.
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from pathlib import Path

CREATOR=0x464410
HELPER=0x463C60
CACHE_INSERT=0x46538B
CACHE_LOOKUP=0x4654A0
CTOR=0x5A6DD0
TRANSFER=0x5A7720
FOCUS={CREATOR,HELPER,CACHE_INSERT,CACHE_LOOKUP,CTOR,TRANSFER}

def hx(v):
    return "-" if v is None else f"0x{int(v):X}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--report-json",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    src=a.report_json.resolve()
    data=json.loads(src.read_text(encoding="utf-8"))

    focus=data.get("focus",[])
    sequences=data.get("sequences",{})
    neighbourhood=data.get("neighborhood",[])

    # Directly useful neighbours: any function whose callers/callees touch one of
    # the known focus functions or whose hits reference the bridge/allocator family.
    focus_begins={int(f.get("begin",0)) for f in focus}
    useful=[]
    for f in neighbourhood:
        related=False
        for e in f.get("callers",[]):
            if int(e.get("caller",0)) in focus_begins or int(e.get("target",0)) in focus_begins:
                related=True
        for e in f.get("callees",[]):
            if int(e.get("caller",0)) in focus_begins or int(e.get("target",0)) in focus_begins:
                related=True
        for h in f.get("hits",[]):
            if h.get("kind") in ("bridge_call","allocator_call"):
                t=int(h.get("target",0))
                if t in FOCUS or t in {0x40BF10,0xD21A90,0xD21DD0,0x40C230,0x5A6C10,0x5A6270}:
                    related=True
        if related:
            useful.append(f)

    # Field inventory across focus only.
    fields=defaultdict(list)
    for f in focus:
        for h in f.get("hits",[]):
            if h.get("kind")=="field":
                k=(h.get("base"),int(h.get("disp",0)),int(h.get("size",0)))
                fields[k].append((int(f.get("begin",0)),int(h.get("site",0)),h.get("op","")))

    out={
      "schema":1,
      "analysis":"lua_backing_cache_node_layout_compact",
      "source_report":str(src),
      "exe_sha256":data.get("exe_sha256"),
      "focus":focus,
      "sequences":sequences,
      "useful_neighborhood":useful,
      "field_inventory":[
        {"base":k[0],"disp":k[1],"size":k[2],
         "uses":[{"function":x[0],"site":x[1],"op":x[2]} for x in v]}
        for k,v in sorted(fields.items(),key=lambda kv:(str(kv[0][0]),kv[0][1],kv[0][2]))
      ],
      "safety":{
        "postprocess_only":True,"game_launched":False,"process_accessed":False,
        "save_opened":False,"save_written":False,"progression_written":False,
        "game_files_written":False
      }
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    L=[
      "Completionist Map - compact durable Lua backing-cache node result",
      f"source={src}",
      f"exe_sha256={data.get('exe_sha256')}",
      f"focus_count={len(focus)} useful_neighborhood={len(useful)}",
      ""
    ]
    for f in focus:
        L.append(f"FOCUS 0x{int(f.get('begin',0)):X}..0x{int(f.get('end',0)):X} anchor={hx(f.get('anchor'))} size=0x{int(f.get('size',0)):X}")
        callers=f.get("callers",[])
        if callers:
            L.append("  callers="+",".join(f"0x{int(e.get('caller',0)):X}@0x{int(e.get('site',0)):X}" for e in callers))
        for h in f.get("hits",[]):
            kind=h.get("kind")
            if kind=="field":
                L.append(f"  FIELD site=0x{int(h.get('site',0)):X} base={h.get('base')} +0x{int(h.get('disp',0)):X} size={h.get('size')} op={h.get('op')}")
            elif kind in ("allocator_call","bridge_call"):
                L.append(f"  {kind.upper()} site=0x{int(h.get('site',0)):X} -> 0x{int(h.get('target',0)):X} op={h.get('op')}")
        L.append("  DISASM")
        for r in f.get("instructions",[]):
            ss=" ".join(f"str@0x{int(s.get('target',0)):X}={s.get('text')!r}" for s in r.get("rip_strings",[]))
            L.append(f"    0x{int(r.get('rva',0)):08X} {r.get('bytes',''):<24} {r.get('mnemonic',''):<8} {r.get('op_str','')}"+((" ; "+ss) if ss else ""))
        L.append("")

    L.append("DECISIVE SEQUENCES")
    for name,rows in sequences.items():
        L.append(name)
        for r in rows:
            ss=" ".join(f"str@0x{int(s.get('target',0)):X}={s.get('text')!r}" for s in r.get("rip_strings",[]))
            L.append(f"  0x{int(r.get('rva',0)):08X} {r.get('bytes',''):<24} {r.get('mnemonic',''):<8} {r.get('op_str','')}"+((" ; "+ss) if ss else ""))
        L.append("")

    L.append("USEFUL NEIGHBOURHOOD")
    for f in useful:
        L.append(f"FUNCTION 0x{int(f.get('begin',0)):X}..0x{int(f.get('end',0)):X}")
        for h in f.get("hits",[]):
            if h.get("kind")=="field":
                L.append(f"  FIELD 0x{int(h.get('site',0)):X} base={h.get('base')} +0x{int(h.get('disp',0)):X} size={h.get('size')} {h.get('op')}")
            elif h.get("kind") in ("allocator_call","bridge_call"):
                L.append(f"  {h.get('kind').upper()} 0x{int(h.get('site',0)):X} -> 0x{int(h.get('target',0)):X} {h.get('op')}")
        L.append("")

    L.append("FIELD INVENTORY")
    for x in out["field_inventory"]:
        L.append(f"base={x['base']} +0x{x['disp']:X} size={x['size']} uses={len(x['uses'])}")
        for u in x["uses"]:
            L.append(f"  fn=0x{u['function']:X} site=0x{u['site']:X} {u['op']}")
    L.append("")
    L.append("SAFETY postprocess_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"LUA_BACKING_CACHE_NODE_COMPACT_COMPLETE focus={len(focus)} useful={len(useful)}")
    print("postprocess_only=true save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":main()
