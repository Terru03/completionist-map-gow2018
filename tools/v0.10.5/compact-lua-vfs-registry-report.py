#!/usr/bin/env python3
"""Compact an existing Lua VFS registry trace.

Consumes the already-generated report.json and emits only the direct
registry entry/count references, direct VFS shared-helper callers, and their
enclosing functions/calls/relevant strings. No GoW.exe scan is repeated.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

KEYWORDS=("vfs","save","checkpoint","wad","lua","restore","slot","state","pickle","raven")

def has_keyword(s:str)->bool:
    q=s.lower()
    return any(k in q for k in KEYWORDS)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    src=json.loads(a.input.read_text(encoding="utf-8"))
    grefs=src.get("global_refs",{})
    helper_callers=src.get("helper_callers",{})

    narrow_globals=("vfs_registry_entries","vfs_registry_count")
    selected=set()
    for name in narrow_globals:
        for x in grefs.get(name,[]):
            selected.add(int(x["function"]))
    for x in helper_callers.get("vfs_shared_helper",[]):
        selected.add(int(x["caller"]))

    funcs_by_begin={int(f["begin"]):f for f in src.get("functions",[])}
    funcs=[]
    for begin in sorted(selected):
        f=funcs_by_begin.get(begin)
        if not f:
            funcs.append({"begin":begin,"missing_from_raw_report":True})
            continue
        strings=[s for s in f.get("strings",[]) if has_keyword(str(s.get("ascii","")))]
        funcs.append({
            "begin":begin,
            "end":f.get("end"),
            "global_refs":[x for x in f.get("global_refs",[]) if x.get("name") in narrow_globals],
            "calls":f.get("calls",[]),
            "callers":f.get("callers",[]),
            "relevant_strings":strings,
        })

    compact_refs={}
    for name in narrow_globals:
        refs=grefs.get(name,[])
        compact_refs[name]={
            "count":len(refs),
            "reads":[x for x in refs if not x.get("write")],
            "writes":[x for x in refs if x.get("write")],
        }

    helper=helper_callers.get("vfs_shared_helper",[])
    result={
        "schema":1,
        "analysis":"lua_vfs_registry_compact",
        "source_report":str(a.input),
        "source_analysis":src.get("analysis"),
        "exe_sha256":src.get("exe_sha256"),
        "global_refs":compact_refs,
        "vfs_shared_helper_callers":helper,
        "selected_function_count":len(funcs),
        "functions":funcs,
        "safety":{
            "source_report_only":True,
            "gow_exe_rescanned":False,
            "game_launched":False,
            "process_accessed":False,
            "save_opened":False,
            "save_written":False,
            "progression_written":False,
            "game_files_written":False,
        },
    }

    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - compact Lua VFS registry evidence",
        f"source_report={a.input}",
        f"exe_sha256={src.get('exe_sha256')}",
        "",
    ]
    for name in narrow_globals:
        row=compact_refs[name]
        lines.append(f"GLOBAL {name} refs={row['count']} reads={len(row['reads'])} writes={len(row['writes'])}")
        for x in row["writes"]:
            lines.append(f"  WRITE fn=0x{int(x['function']):X} site=0x{int(x['site']):X} {x.get('op','')}")
        for x in row["reads"]:
            lines.append(f"  READ  fn=0x{int(x['function']):X} site=0x{int(x['site']):X} {x.get('op','')}")
        lines.append("")
    lines.append(f"VFS_SHARED_HELPER_CALLERS count={len(helper)}")
    for x in helper:
        lines.append(f"  fn=0x{int(x['caller']):X} site=0x{int(x['site']):X}")
    lines.append("")
    for f in funcs:
        b=int(f["begin"])
        if f.get("missing_from_raw_report"):
            lines.append(f"FUNCTION 0x{b:X} missing_from_raw_report=true")
            continue
        lines.append(f"FUNCTION 0x{b:X}..0x{int(f['end']):X}")
        for x in f["global_refs"]:
            lines.append(f"  GLOBAL {'WRITE' if x.get('write') else 'READ'} {x.get('name')} site=0x{int(x['site']):X} {x.get('op','')}")
        for s in f["relevant_strings"]:
            lines.append(f"  STRING 0x{int(s['site']):X} -> 0x{int(s['target']):X} {s.get('ascii')!r}")
        for x in f["calls"]:
            tf=x.get("target_function")
            target="-" if tf is None else f"0x{int(tf):X}"
            lines.append(f"  {str(x.get('kind','call')).upper()} 0x{int(x['site']):X} -> {target} raw=0x{int(x['target']):X}")
        lines.append("")
    lines.append("SAFETY source_report_only=true gow_exe_rescanned=false game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"LUA_VFS_REGISTRY_COMPACT_COMPLETE selected_functions={len(funcs)}")
    for name in narrow_globals:
        row=compact_refs[name]
        print(f"{name}_refs={row['count']} {name}_writes={len(row['writes'])}")
    print(f"vfs_shared_helper_callers={len(helper)}")
    print("gow_exe_rescanned=false save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":
    main()
