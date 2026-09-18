#!/usr/bin/env python3
"""Trace the native callers that invoke both LuaClient pickle/unpickle vtable slots.

Read-only static GoW.exe analysis. The six seeds were identified by the existing
LuaClient persistence semantics pass as functions containing virtual calls through
both slot 14 (+0x70, pickle) and slot 16 (+0x80, unpickle). This pass disassembles
those seeds and their direct callers, reports RIP-relative globals/strings and
ranks likely WAD/save-state manager wrappers.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
SEEDS=[0x464EF0,0x6432C0,0x64351E,0x643B76,0x644050,0x9AB68B]
TERMS=("save","load","wad","level","checkpoint","pickle","persist","state","serialize","lua","client","stream")

def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def helper():
 p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
 s=importlib.util.spec_from_file_location("gow_luaclient_shared",p)
 if not s or not s.loader:raise RuntimeError("helper load failed")
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def capstone():
 root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
 if root.is_dir():sys.path.insert(0,str(root))
 from capstone import Cs,CS_ARCH_X86,CS_MODE_64
 from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
 return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def read_ascii(pe,rva,maxlen=180):
 off=pe.rva_to_file(rva)
 if off is None:return None
 raw=pe.data[off:off+maxlen]; out=bytearray()
 for b in raw:
  if b==0:break
  if 32<=b<=126:out.append(b)
  else:return None
 return out.decode("ascii","replace") if len(out)>=4 else None

def trace(pe,md,rva,opi,opm,rip):
 fn=pe.function_for(rva)
 if not fn:return {"entry":rva,"missing":True}
 rows=[];refs=[];calls=[]
 for ins in md.disasm(pe.bytes_for(fn),pe.image_base+fn["begin"]):
  ir=ins.address-pe.image_base
  rows.append({"rva":ir,"hex":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str})
  try:
   for op in ins.operands:
    if op.type==opm and op.mem.base==rip:
     target=ins.address+ins.size+op.mem.disp-pe.image_base
     refs.append({"site":ir,"target":target,"target_hex":f"0x{target:X}","ascii":read_ascii(pe,target),
                  "op":f"{ins.mnemonic} {ins.op_str}"})
    if ins.mnemonic=="call":
     if op.type==opi:
      va=int(op.imm); dest=va-pe.image_base if pe.image_base<=va<pe.image_base+pe.size_of_image else None
      if dest is not None:calls.append({"site":ir,"kind":"direct","dest":dest,"dest_hex":f"0x{dest:X}"})
     elif op.type==opm:
      calls.append({"site":ir,"kind":"indirect","op_str":ins.op_str})
  except Exception:pass
 strings=sorted({x["ascii"] for x in refs if x["ascii"]})
 score=sum(1 for s in strings for t in TERMS if t in s.lower())
 return {"entry":rva,"begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],
         "strings":strings,"score":score,"rip_refs":refs,"calls":calls,"instructions":rows}

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--exe",type=Path,required=True)
 ap.add_argument("--output-json",type=Path,required=True);ap.add_argument("--output-text",type=Path,required=True)
 a=ap.parse_args(); exe=a.exe.resolve()
 if sha(exe)!=EXPECTED:raise RuntimeError("unsupported GoW.exe")
 h=helper();pe=h.PE(exe.read_bytes()); Cs,arch,mode,opi,opm,rip=capstone();md=Cs(arch,mode);md.detail=True
 seeds={};caller_ids=set()
 for seed in SEEDS:
  rep=trace(pe,md,seed,opi,opm,rip)
  direct=h.direct_callers(pe,rep.get("begin",seed))
  rep["direct_callers"]=direct
  for c in direct:
   if c.get("function_begin") is not None:caller_ids.add(c["function_begin"])
  seeds[f"0x{seed:X}"]=rep
 callers={f"0x{x:X}":trace(pe,md,x,opi,opm,rip) for x in sorted(caller_ids)}
 ranked=sorted(
  [{"rva":k,"score":v.get("score",0),"strings":v.get("strings",[]),
    "calls_shared_seed":sorted({f"0x{c['dest']:X}" for c in v.get("calls",[]) if c.get("dest") in SEEDS})}
   for k,v in callers.items()],
  key=lambda x:(-x["score"],x["rva"]))
 out={"schema":1,"analysis":"luaclient_pickle_unpickle_shared_callers","exe_sha256":EXPECTED,
      "seeds":seeds,"caller_functions":callers,"ranked_callers":ranked,
      "safety":{"static_pe_only":True,"game_launched":False,"save_opened":False,"exe_modified":False}}
 a.output_json.parent.mkdir(parents=True,exist_ok=True)
 a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 lines=["Completionist Map - LuaClient pickle/unpickle shared caller trace",f"exe_sha256={EXPECTED}",
        "game_launched=false save_opened=false exe_modified=false",""]
 for k,v in seeds.items():
  lines.append(f"SEED {k} fn=0x{v.get('begin',0):X}-0x{v.get('end',0):X} score={v.get('score',0)} strings={v.get('strings',[])}")
  for c in v.get("calls",[]):
   if c["kind"]=="indirect" or c.get("dest") in (0x5B2130,0x5B2280):
    lines.append(f"  CALL 0x{c['site']:X} {c['kind']} {c.get('dest_hex',c.get('op_str'))}")
  for r in v.get("rip_refs",[]):
   if r.get("ascii"):lines.append(f"  REF 0x{r['site']:X}->0x{r['target']:X} {r['ascii']!r}")
 lines+=["","RANKED DIRECT CALLERS"]
 for r in ranked:
  lines.append(f"{r['rva']} score={r['score']} shared={r['calls_shared_seed']} strings={r['strings']}")
 lines+=["","CALLER DISASSEMBLY"]
 for k,v in callers.items():
  lines.append(f"FUNCTION {k} score={v.get('score',0)} strings={v.get('strings',[])}")
  for ins in v.get("instructions",[]):lines.append(f"  0x{ins['rva']:X}: {ins['hex']:<24} {ins['mnemonic']} {ins['op_str']}")
 a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
 print(f"LUACLIENT_SHARED_CALLER_TRACE_COMPLETE seeds={len(seeds)} callers={len(callers)}")
 for r in ranked[:20]:print(f"RANK {r['rva']} score={r['score']} strings={' | '.join(r['strings'][:8])}")
 return 0
if __name__=="__main__":raise SystemExit(main())
