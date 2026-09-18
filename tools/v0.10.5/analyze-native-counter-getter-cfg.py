#!/usr/bin/env python3
"""Read-only static CFG/disassembly for native Raven-relevant counter getters.

Targets the exact descriptor-backed functions already proved in the supported
GoW.exe:
  GetCounter              0x841E50   signature i_s|i_i
  GetCounterChild         0x841CE0   signature i_si|i_ii
  GetCounterChildrenCount 0x841D50   signature i_s|i_i
  GetRefBool              0x845700   signature b_s

The scan follows direct CALL/JMP targets to bounded depth, records RIP-relative
global/data references, immediate constants, and nearby ASCII where resolvable.
This is static PE analysis only: no game launch, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
TARGETS={
    "GetCounter":{"rva":0x841E50,"signature":"i_s|i_i"},
    "GetCounterChild":{"rva":0x841CE0,"signature":"i_si|i_ii"},
    "GetCounterChildrenCount":{"rva":0x841D50,"signature":"i_s|i_i"},
    "GetRefBool":{"rva":0x845700,"signature":"b_s"},
}
MAX_DEPTH=3
MAX_FUNCTIONS=96
MAX_INSNS=1024

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def load_helper():
    path=Path(__file__).with_name("analyze-gameobject-token-resolver.py")
    spec=importlib.util.spec_from_file_location("gow_pe_counter_getters",path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {path}")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def load_capstone():
    repo=Path(__file__).resolve().parents[2]
    local=repo/".research-index"/"python-packages"
    if local.is_dir(): sys.path.insert(0,str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def printable_at(pe,rva:int):
    try: return pe.ascii_at_rva(rva)
    except Exception: return None

def disasm_fn(pe,md,fn,op_imm,op_mem,reg_rip):
    blob=pe.bytes_for(fn)
    rows=[]; calls=[]; rip_refs=[]; immediates=[]
    for n,ins in enumerate(md.disasm(blob,pe.image_base+fn["begin"])):
        if n>=MAX_INSNS: break
        rva=ins.address-pe.image_base
        row={"rva":rva,"rva_hex":f"0x{rva:X}","bytes":ins.bytes.hex(),
             "mnemonic":ins.mnemonic,"op_str":ins.op_str}
        rows.append(row)
        try:
            for op in ins.operands:
                if op.type==op_imm:
                    value=int(op.imm)
                    if pe.image_base<=value<pe.image_base+pe.size_of_image:
                        dest=value-pe.image_base
                        tf=pe.function_for(dest)
                        if ins.mnemonic in ("call","jmp"):
                            calls.append({"site":rva,"kind":ins.mnemonic,"dest":dest,
                                          "target_function_begin":tf["begin"] if tf else None})
                    elif abs(value)>=0x100:
                        immediates.append({"site":rva,"value":value,"value_hex":f"0x{value & ((1<<64)-1):X}"})
                elif op.type==op_mem and op.mem.base==reg_rip:
                    target=ins.address+ins.size+op.mem.disp
                    if pe.image_base<=target<pe.image_base+pe.size_of_image:
                        trva=target-pe.image_base
                        rip_refs.append({"site":rva,"target":trva,"target_hex":f"0x{trva:X}",
                                         "ascii":printable_at(pe,trva),
                                         "instruction":f"{ins.mnemonic} {ins.op_str}"})
        except Exception:
            pass
    uniq_calls=[]; seen=set()
    for c in calls:
        key=(c["site"],c["kind"],c["dest"])
        if key not in seen: seen.add(key); uniq_calls.append(c)
    uniq_refs=[]; seen=set()
    for r in rip_refs:
        key=(r["site"],r["target"])
        if key not in seen: seen.add(key); uniq_refs.append(r)
    return {
        "begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
        "instructions":rows,"calls":uniq_calls,"rip_refs":uniq_refs,
        "immediates":immediates[:256],
    }

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root",type=Path,default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    args=ap.parse_args()
    exe=args.game_root.expanduser().resolve()/"GoW.exe"
    before=sha256(exe)
    if before!=EXPECTED_SHA256: raise RuntimeError(f"unexpected GoW.exe SHA-256: {before}")
    helper=load_helper(); pe=helper.PE(exe.read_bytes())
    Cs,arch,mode,op_imm,op_mem,reg_rip=load_capstone()
    md=Cs(arch,mode); md.detail=True

    queue=[]; roots={}
    for name,meta in TARGETS.items():
        fn=pe.function_for(meta["rva"])
        if fn is None: raise RuntimeError(f"{name}: no pdata function for 0x{meta['rva']:X}")
        roots[name]={"entry_rva":meta["rva"],"signature":meta["signature"],
                     "function_begin":fn["begin"],"function_end":fn["end"]}
        queue.append((fn["begin"],0,name))

    funcs={}; provenance={}
    while queue and len(funcs)<MAX_FUNCTIONS:
        begin,depth,root=queue.pop(0)
        if begin in funcs:
            provenance.setdefault(begin,[]).append({"root":root,"depth":depth})
            continue
        fn=pe.function_for(begin)
        if fn is None: continue
        rep=disasm_fn(pe,md,fn,op_imm,op_mem,reg_rip)
        funcs[begin]=rep
        provenance.setdefault(begin,[]).append({"root":root,"depth":depth})
        if depth>=MAX_DEPTH: continue
        for edge in rep["calls"]:
            tf=edge.get("target_function_begin")
            if tf is not None and tf not in funcs:
                queue.append((tf,depth+1,root))

    for begin,rep in funcs.items():
        rep["provenance"]=provenance.get(begin,[])

    report={
        "schema":1,
        "analysis":"native_counter_getter_cfg",
        "exe_sha256":before,
        "roots":roots,
        "functions":{f"0x{k:X}":v for k,v in sorted(funcs.items())},
        "limits":{"max_depth":MAX_DEPTH,"max_functions":MAX_FUNCTIONS,"max_instructions_per_function":MAX_INSNS},
        "safety":{"read_only_static_pe":True,"game_launched":False,"active_save_opened":False,
                  "game_written":False,"save_or_progression_written":False,"source_hash_unchanged":True},
    }

    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    lines=[
        "Completionist Map - native counter/ref getter CFG",
        f"exe_sha256={before}",
        "game_launched=false active_save_opened=false game_written=false save_or_progression_written=false",
        "",
        "ROOTS",
    ]
    for name,r in roots.items():
        lines.append(f"{name} signature={r['signature']} entry=0x{r['entry_rva']:X} fn=0x{r['function_begin']:X}-0x{r['function_end']:X}")
    for begin,rep in sorted(funcs.items()):
        prov=",".join(f"{p['root']}@{p['depth']}" for p in rep.get("provenance",[]))
        lines+=["",f"FUNCTION 0x{begin:X}-0x{rep['end']:X} size={rep['size']} via={prov}"]
        if rep["rip_refs"]:
            lines.append("  RIP_REFS")
            for r in rep["rip_refs"]:
                lines.append(f"    0x{r['site']:X} -> 0x{r['target']:X} ascii={r['ascii']!r} {r['instruction']}")
        if rep["calls"]:
            lines.append("  EDGES")
            for e in rep["calls"]:
                lines.append(f"    {e['kind']} 0x{e['site']:X} -> 0x{e['dest']:X} targetFn={('0x%X'%e['target_function_begin']) if e['target_function_begin'] is not None else 'none'}")
        lines.append("  DISASM")
        for ins in rep["instructions"]:
            lines.append(f"    {ins['rva_hex']}: {ins['bytes']:<24} {ins['mnemonic']} {ins['op_str']}")
    args.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    after=sha256(exe)
    if after!=before: raise RuntimeError("GoW.exe changed during read-only scan")
    print(f"NATIVE_COUNTER_GETTER_CFG_COMPLETE functions={len(funcs)}")
    print("source_hash_unchanged=true game_launched=false active_save_opened=false save_or_progression_written=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
