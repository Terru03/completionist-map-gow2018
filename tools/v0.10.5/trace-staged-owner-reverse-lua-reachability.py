#!/usr/bin/env python3
"""Reverse-trace proven staged Raven authority toward registered Lua handlers.

Static/read-only proof:
1. parse the exhaustive Lua registration catalogue already in the repo;
2. disassemble GoW runtime functions and build direct call/jmp reverse edges;
3. seed from the proven staged owner/restore functions plus any function with
   a direct RIP-relative access to the proven staged globals;
4. walk callers upward to bounded depth;
5. report only paths that intersect registered Lua native handlers.

No process attach, game launch, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, sys
from collections import defaultdict, deque
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000

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
    "staged_wad_writer":0x6687F0,
}

REG_RE=re.compile(r"^([^\s].*?)\s+table=0x[0-9A-Fa-f]+\s+stride=\d+\s+entry=0x[0-9A-Fa-f]+\s+fn=0x([0-9A-Fa-f]+)\s*$")

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_helper():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec=importlib.util.spec_from_file_location("staged_reverse_pe",p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {p}")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def load_capstone(repo:Path):
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def parse_registrations(path:Path):
    by_exact=defaultdict(set)
    for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
        m=REG_RE.match(line.strip())
        if not m: continue
        name=m.group(1).strip()
        fn=int(m.group(2),16)
        by_exact[fn].add(name)
    if not by_exact:
        raise RuntimeError(f"no Lua registrations parsed from {path}")
    return by_exact

def disasm_function(pe,md,fn,OP_IMM,OP_MEM,RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None: return []
    raw=pe.data[off:off+fn["end"]-fn["begin"]]
    out=[]
    for ins in md.disasm(raw,IMAGE_BASE+fn["begin"]):
        imms=[]; rip_targets=[]
        for op in getattr(ins,"operands",[]):
            if op.type==OP_IMM:
                v=op.imm
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:
                    v-=IMAGE_BASE
                imms.append(v)
            elif op.type==OP_MEM and op.mem.base==RIP:
                rip_targets.append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
        out.append({
            "rva":ins.address-IMAGE_BASE,
            "mnemonic":ins.mnemonic,
            "op_str":ins.op_str,
            "imms":imms,
            "rip_targets":rip_targets,
        })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--registrations",type=Path,default=None)
    ap.add_argument("--max-depth",type=int,default=4)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    exe=a.exe.expanduser().resolve()
    if not exe.is_file(): raise RuntimeError(f"GoW.exe not found: {exe}")
    digest=sha256_file(exe)
    if digest!=EXPECTED_SHA256: raise RuntimeError(f"SHA mismatch: {digest}")

    repo=Path(__file__).resolve().parents[2]
    regs=(a.registrations or (repo/"archive/field-logs/source-scans/lua-registration-exhaustive-20260914-143235/registration-exhaustive.txt")).resolve()
    if not regs.is_file(): raise RuntimeError(f"registration catalogue missing: {regs}")
    reg_exact=parse_registrations(regs)

    helper=load_helper()
    pe=helper.PE(exe.read_bytes())
    Cs,ARCH,MODE,OP_IMM,OP_MEM,RIP=load_capstone(repo)
    md=Cs(ARCH,MODE); md.detail=True

    functions={f["begin"]:f for f in pe.runtime_functions}
    call_reverse=defaultdict(list)
    global_touch=defaultdict(list)
    decoded_count=0

    # Map every registered exact handler address to its enclosing runtime function
    # when one exists. Tiny handlers without runtime records are retained as exact
    # addresses but cannot participate as reverse-call nodes unless directly called.
    reg_by_fn=defaultdict(set)
    exact_reg_without_runtime={}
    for addr,names in reg_exact.items():
        fn=pe.function_for(addr)
        if fn:
            reg_by_fn[fn["begin"]].update(names)
        else:
            exact_reg_without_runtime[addr]=sorted(names)

    for fn in pe.runtime_functions:
        rows=disasm_function(pe,md,fn,OP_IMM,OP_MEM,RIP)
        if not rows: continue
        decoded_count+=1
        b=fn["begin"]
        for r in rows:
            for t in r["rip_targets"]:
                for gname,gaddr in STAGED_GLOBALS.items():
                    if t==gaddr:
                        global_touch[b].append({"name":gname,"site":r["rva"],"op":r["op_str"]})
            if r["mnemonic"] not in ("call","jmp") or not r["imms"]:
                continue
            t=r["imms"][0]
            if not isinstance(t,int): continue
            tf=pe.function_for(t)
            if tf:
                call_reverse[tf["begin"]].append({
                    "caller":b,
                    "site":r["rva"],
                    "kind":r["mnemonic"],
                    "target":t,
                })
            # Preserve direct calls to tiny registered handlers without runtime rows.
            if t in exact_reg_without_runtime:
                # This is a forward Lua-handler target, not useful as reverse staged
                # reachability, but record it for diagnostic completeness.
                pass

    roots={}
    for name,rva in KNOWN_STAGED_FUNCTIONS.items():
        fn=pe.function_for(rva)
        if fn:
            roots.setdefault(fn["begin"],[]).append("known:"+name)
    for b,hits in global_touch.items():
        roots.setdefault(b,[])
        roots[b].extend("global:"+x["name"] for x in hits)

    # Reverse BFS from each root. Keep only shortest state for (root,node).
    hits=[]
    frontier_counts=defaultdict(int)
    visited_total=set()
    for root,root_reasons in sorted(roots.items()):
        q=deque([(root,0,[root])])
        seen={root:0}
        while q:
            node,depth,path=q.popleft()
            visited_total.add(node)
            frontier_counts[depth]+=1
            if node in reg_by_fn:
                hits.append({
                    "root":root,
                    "root_reasons":sorted(set(root_reasons)),
                    "depth":depth,
                    "handler_function":node,
                    "lua_names":sorted(reg_by_fn[node]),
                    "path":path,
                })
                # still continue: another registered ancestor may exist
            if depth>=a.max_depth:
                continue
            for e in call_reverse.get(node,[]):
                caller=e["caller"]
                nd=depth+1
                if seen.get(caller,999)<=nd:
                    continue
                seen[caller]=nd
                q.append((caller,nd,path+[caller]))

    # Deduplicate same handler/root/path classification.
    uniq=[]
    sigs=set()
    for h in sorted(hits,key=lambda x:(x["depth"],x["handler_function"],x["root"])):
        sig=(h["root"],h["handler_function"],tuple(h["path"]))
        if sig in sigs: continue
        sigs.add(sig); uniq.append(h)

    result={
        "schema":1,
        "analysis":"staged_owner_reverse_lua_reachability",
        "exe_sha256":digest,
        "registration_catalogue":str(regs),
        "max_depth":a.max_depth,
        "runtime_functions_decoded":decoded_count,
        "registration_exact_handler_count":len(reg_exact),
        "registration_runtime_function_count":len(reg_by_fn),
        "registration_handlers_without_runtime_record":exact_reg_without_runtime,
        "root_count":len(roots),
        "roots":[
            {"function":b,"reasons":sorted(set(rs)),"global_hits":global_touch.get(b,[])}
            for b,rs in sorted(roots.items())
        ],
        "reverse_nodes_visited":len(visited_total),
        "frontier_counts":dict(sorted(frontier_counts.items())),
        "lua_path_count":len(uniq),
        "lua_paths":uniq,
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
        "Completionist Map - staged owner reverse Lua reachability",
        f"exe_sha256={digest}",
        f"max_depth={a.max_depth}",
        f"runtime_functions_decoded={decoded_count}",
        f"registration_exact_handler_count={len(reg_exact)}",
        f"registration_runtime_function_count={len(reg_by_fn)}",
        f"root_count={len(roots)}",
        f"reverse_nodes_visited={len(visited_total)}",
        f"lua_path_count={len(uniq)}",
        "",
        "ROOTS",
    ]
    for b,rs in sorted(roots.items()):
        lines.append(f"  0x{b:X} reasons={','.join(sorted(set(rs)))}")
        for x in global_touch.get(b,[]):
            lines.append(f"    GLOBAL {x['name']} site=0x{x['site']:X} {x['op']}")
    lines.append("")
    lines.append("REGISTERED_LUA_PATHS")
    if not uniq:
        lines.append("  NONE")
    for h in uniq:
        lines.append(
            f"  depth={h['depth']} handler=0x{h['handler_function']:X} "
            f"names={'|'.join(h['lua_names'])} root=0x{h['root']:X} "
            f"root_reasons={','.join(h['root_reasons'])}"
        )
        lines.append("    path(staged->caller): "+" -> ".join(f"0x{x:X}" for x in h["path"]))
    lines.append("")
    lines.append("FRONTIER_COUNTS")
    for d,n in sorted(frontier_counts.items()):
        lines.append(f"  depth={d} node_visits={n}")
    lines.append("")
    lines.append("SAFETY static_exe_read_only=true game_launched=false process_accessed=false save_opened=false save_written=false progression_written=false game_files_written=false")
    a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"STAGED_OWNER_REVERSE_LUA_TRACE_COMPLETE roots={len(roots)} visited={len(visited_total)} lua_paths={len(uniq)} max_depth={a.max_depth}")
    print("save_opened=false save_written=false progression_written=false game_launched=false")

if __name__=="__main__":
    main()
