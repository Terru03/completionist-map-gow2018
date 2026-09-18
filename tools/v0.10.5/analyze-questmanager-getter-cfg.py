#!/usr/bin/env python3
"""Read-only static CFG analysis for authoritative QuestManager getters.

Live Lua closure capture on the supported GoW.exe resolved these working
QuestManager methods to native RVAs:
  GetQuestProgressAndGoal 0x94A0A0
  GetQuestState           0x94A580
  GetChildrenQuestIds     0x948FC0
  GetTrackingInfo         0x9487C0
  GetCompletionIndex      0x949AD0

This follows bounded direct CALL/JMP edges, records RIP-relative data/global
references and disassembly, and never launches or writes to the game.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
TARGETS={
    "GetQuestProgressAndGoal":{"rva":0x94A0A0},
    "GetQuestState":{"rva":0x94A580},
    "GetChildrenQuestIds":{"rva":0x948FC0},
    "GetTrackingInfo":{"rva":0x9487C0},
    "GetCompletionIndex":{"rva":0x949AD0},
}
MAX_DEPTH=4
MAX_FUNCTIONS=160
MAX_INSNS=1536

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def load_helper():
    path=Path(__file__).with_name("analyze-gameobject-token-resolver.py")
    spec=importlib.util.spec_from_file_location("gow_pe_qm",path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {path}")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def load_capstone():
    repo=Path(__file__).resolve().parents[2]
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def printable_at(pe,rva:int):
    try:return pe.ascii_at_rva(rva)
    except Exception:return None

def disasm_fn(pe,md,fn,op_imm,op_mem,reg_rip):
    blob=pe.bytes_for(fn); rows=[]; calls=[]; refs=[]; imms=[]
    for n,ins in enumerate(md.disasm(blob,pe.image_base+fn["begin"])):
        if n>=MAX_INSNS:break
        rva=ins.address-pe.image_base
        rows.append({"rva":rva,"rva_hex":f"0x{rva:X}","bytes":ins.bytes.hex(),
                     "mnemonic":ins.mnemonic,"op_str":ins.op_str})
        try:
            for op in ins.operands:
                if op.type==op_imm:
                    value=int(op.imm)
                    if pe.image_base<=value<pe.image_base+pe.size_of_image:
                        dest=value-pe.image_base; tf=pe.function_for(dest)
                        if ins.mnemonic in ("call","jmp"):
                            calls.append({"site":rva,"kind":ins.mnemonic,"dest":dest,
                                          "target_function_begin":tf["begin"] if tf else None})
                    elif abs(value)>=0x100:
                        imms.append({"site":rva,"value":value,"value_hex":f"0x{value & ((1<<64)-1):X}"})
                elif op.type==op_mem and op.mem.base==reg_rip:
                    target=ins.address+ins.size+op.mem.disp
                    if pe.image_base<=target<pe.image_base+pe.size_of_image:
                        trva=target-pe.image_base
                        refs.append({"site":rva,"target":trva,"target_hex":f"0x{trva:X}",
                                     "ascii":printable_at(pe,trva),
                                     "instruction":f"{ins.mnemonic} {ins.op_str}"})
        except Exception:pass
    def uniq(rows,keys):
        out=[];seen=set()
        for r in rows:
            k=tuple(r[x] for x in keys)
            if k not in seen:seen.add(k);out.append(r)
        return out
    return {"begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
            "instructions":rows,"calls":uniq(calls,("site","kind","dest")),
            "rip_refs":uniq(refs,("site","target")),"immediates":imms[:384]}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.game_root.expanduser().resolve()/"GoW.exe"
    before=sha256(exe)
    if before!=EXPECTED_SHA256:raise RuntimeError(f"unexpected GoW.exe SHA-256: {before}")
    helper=load_helper(); pe=helper.PE(exe.read_bytes())
    Cs,arch,mode,op_imm,op_mem,reg_rip=load_capstone(); md=Cs(arch,mode); md.detail=True

    roots={};queue=[]
    for name,meta in TARGETS.items():
        fn=pe.function_for(meta["rva"])
        roots[name]={"entry_rva":meta["rva"],"function_begin":fn["begin"] if fn else None,
                     "function_end":fn["end"] if fn else None,"pdata_missing":fn is None}
        if fn:queue.append((fn["begin"],0,name))

    funcs={}; provenance={}
    while queue and len(funcs)<MAX_FUNCTIONS:
        begin,depth,root=queue.pop(0)
        provenance.setdefault(begin,[]).append({"root":root,"depth":depth})
        if begin in funcs:continue
        fn=pe.function_for(begin)
        if not fn:continue
        rep=disasm_fn(pe,md,fn,op_imm,op_mem,reg_rip); funcs[begin]=rep
        if depth<MAX_DEPTH:
            for edge in rep["calls"]:
                tf=edge.get("target_function_begin")
                if tf is not None and tf not in funcs:queue.append((tf,depth+1,root))
    for b,r in funcs.items():r["provenance"]=provenance.get(b,[])

    report={"schema":1,"analysis":"questmanager_authoritative_getter_cfg","exe_sha256":before,
            "roots":roots,"functions":{f"0x{k:X}":v for k,v in sorted(funcs.items())},
            "limits":{"max_depth":MAX_DEPTH,"max_functions":MAX_FUNCTIONS,"max_insns":MAX_INSNS},
            "safety":{"read_only_static_pe":True,"game_launched":False,"active_save_opened":False,
                      "game_written":False,"save_or_progression_written":False}}
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=["Completionist Map - authoritative QuestManager getter CFG",f"exe_sha256={before}",
           "game_launched=false active_save_opened=false save_or_progression_written=false","","ROOTS"]
    for name,r in roots.items():
        lines.append(f"{name} entry=0x{r['entry_rva']:X} fn="+
                     (f"0x{r['function_begin']:X}-0x{r['function_end']:X}" if r["function_begin"] is not None else "<no_pdata>"))
    for begin,rep in sorted(funcs.items()):
        prov=",".join(f"{p['root']}@{p['depth']}" for p in rep["provenance"])
        lines+=["",f"FUNCTION 0x{begin:X}-0x{rep['end']:X} size={rep['size']} via={prov}"]
        if rep["rip_refs"]:
            lines.append("  RIP_REFS")
            for x in rep["rip_refs"]:lines.append(f"    0x{x['site']:X} -> 0x{x['target']:X} ascii={x['ascii']!r} {x['instruction']}")
        if rep["calls"]:
            lines.append("  EDGES")
            for e in rep["calls"]:lines.append(f"    {e['kind']} 0x{e['site']:X} -> 0x{e['dest']:X} targetFn="+(f"0x{e['target_function_begin']:X}" if e['target_function_begin'] is not None else "none"))
        lines.append("  DISASM")
        for ins in rep["instructions"]:lines.append(f"    {ins['rva_hex']}: {ins['bytes']:<24} {ins['mnemonic']} {ins['op_str']}")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    if sha256(exe)!=before:raise RuntimeError("GoW.exe changed during read-only scan")
    print(f"QUESTMANAGER_GETTER_CFG_COMPLETE functions={len(funcs)}")
    print("source_hash_unchanged=true game_launched=false active_save_opened=false save_or_progression_written=false")
    return 0

if __name__=="__main__":raise SystemExit(main())
