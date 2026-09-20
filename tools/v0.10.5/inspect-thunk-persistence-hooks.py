#!/usr/bin/env python3
"""Inspect extracted GoW Lua hook/thunk infrastructure for persistence interception.

Read-only local source scan. It does not launch the game, read saves, or modify
game files. It reports:
- the core.thunk implementation sites for Install/dispatch/registry logic;
- every thunk.Install(...) call name;
- restore/pickle/serialize/checkpoint-related hook registrations/usages;
- small source excerpts only.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

HOOK_TERMS=(
    "thunk.Install","engine.SendHook","RegisterListener","UnregisterListener",
    "SerializeHook","OnRestoreCheckpoint","OnSaveCheckpoint","OnUnpickle","Unpickle",
    "OnPickle","Pickle","SoftPickle","__PickleTable","__SoftPickleTable",
    "_SUBOBJECTS","_SUBOBJECT_CHUNKS","ravenKilled",
)
SEMANTIC=("restore","pickle","unpickle","serialize","deserialize","checkpoint","userdata","save")
CTX=5

INSTALL_RE=re.compile(r"""thunk\.Install\s*\(\s*["']([^"']+)["']""")
REQ_RE=re.compile(r"""require\s*\(\s*["']core\.thunk["']\s*\)""")

def excerpt(lines,i,ctx=CTX):
    lo=max(0,i-ctx);hi=min(len(lines),i+ctx+1)
    return [f"{n+1}: {lines[n]}" for n in range(lo,hi)]

def rel(root,p):
    try:return str(p.relative_to(root))
    except Exception:return str(p)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    roots=[a.game_root/"mods"/"lua_source",a.game_root/"mods"/"lua"]
    roots=[x for x in roots if x.is_dir()]
    if not roots:raise RuntimeError("No extracted Lua roots under game mods directory.")

    files=[]
    for root in roots:
        files.extend(root.rglob("*.lua"))
    # dedup by resolved path
    uniq={str(p.resolve()).lower():p for p in files}
    files=sorted(uniq.values(),key=lambda p:str(p).lower())

    thunk_impl=[]
    installs=[]
    related=[]
    requires=[]
    for p in files:
        try:text=p.read_text(encoding="utf-8",errors="replace")
        except OSError:continue
        lines=text.splitlines()
        root=next((r for r in roots if str(p).lower().startswith(str(r).lower())),roots[0])
        rp=rel(root,p)

        is_thunk_file=(p.name.lower()=="thunk.lua" or rp.lower().endswith("core\\thunk.lua") or rp.lower().endswith("core/thunk.lua"))
        for i,line in enumerate(lines):
            m=INSTALL_RE.search(line)
            if m:
                name=m.group(1)
                row={"file":rp,"line":i+1,"name":name,"excerpt":excerpt(lines,i)}
                installs.append(row)
                if any(t in name.lower() for t in SEMANTIC):
                    related.append({"kind":"thunk_install_semantic",**row})

            if REQ_RE.search(line):
                requires.append({"file":rp,"line":i+1,"excerpt":excerpt(lines,i,2)})

            low=line.lower()
            terms=[t for t in HOOK_TERMS if t.lower() in low]
            if terms:
                row={"file":rp,"line":i+1,"terms":terms,"excerpt":excerpt(lines,i)}
                if any(t in low for t in SEMANTIC) or any(t in terms for t in ("SerializeHook","OnRestoreCheckpoint","OnSaveCheckpoint","OnUnpickle","Unpickle","OnPickle","Pickle","SoftPickle","__PickleTable","__SoftPickleTable","_SUBOBJECTS","_SUBOBJECT_CHUNKS")):
                    related.append({"kind":"semantic_usage",**row})

            if is_thunk_file and (
                "install" in low or "sendhook" in low or "hook" in low or
                "registry" in low or "listener" in low or "call" in low
            ):
                thunk_impl.append({"file":rp,"line":i+1,"excerpt":excerpt(lines,i)})

    # Compact/dedup thunk excerpts by file+line.
    seen=set();thunk_impl2=[]
    for x in thunk_impl:
        k=(x["file"],x["line"])
        if k not in seen:seen.add(k);thunk_impl2.append(x)

    names=sorted({x["name"] for x in installs})
    semantic_names=sorted({x["name"] for x in installs if any(t in x["name"].lower() for t in SEMANTIC)})

    report={
      "schema":1,"analysis":"thunk_persistence_hook_inspection",
      "lua_files_scanned":len(files),
      "roots":[str(x) for x in roots],
      "thunk_impl_hits":thunk_impl2,
      "thunk_install_count":len(installs),
      "unique_thunk_install_names":names,
      "semantic_thunk_install_names":semantic_names,
      "thunk_installs":installs,
      "related_hits":related,
      "core_thunk_requires":requires,
      "safety":{"game_launched":False,"save_opened":False,"game_files_written":False,
                "save_or_progression_written":False}
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

    L=["Completionist Map - thunk/persistence hook inspection",
       f"lua_files_scanned={len(files)}",
       f"thunk_install_count={len(installs)} unique_names={len(names)}",
       f"semantic_thunk_install_names={len(semantic_names)}",
       ""]
    L.append("CORE.THUNK IMPLEMENTATION HITS")
    for x in thunk_impl2:
        L.append(f"FILE {x['file']} line={x['line']}")
        L.extend("  "+z for z in x["excerpt"]);L.append("")
    L.append("SEMANTIC THUNK INSTALL NAMES")
    for n in semantic_names:L.append(f"  {n}")
    if not semantic_names:L.append("  (none)")
    L.append("")
    L.append("RESTORE/PICKLE/SERIALIZE RELATED HITS")
    for x in related:
        L.append(f"{x['kind']} FILE {x['file']} line={x['line']}")
        if x.get("name"):L.append(f"  name={x['name']}")
        if x.get("terms"):L.append("  terms="+",".join(x["terms"]))
        L.extend("  "+z for z in x["excerpt"]);L.append("")
    L.append("ALL THUNK INSTALL NAMES")
    for n in names:L.append(f"  {n}")
    L += ["","SAFETY game_launched=false save_opened=false game_files_written=false save_or_progression_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"THUNK_PERSISTENCE_HOOK_INSPECTION_COMPLETE files={len(files)} installs={len(installs)} semantic={len(semantic_names)}")
    print("game_launched=false save_opened=false save_or_progression_written=false")

if __name__=="__main__":main()
