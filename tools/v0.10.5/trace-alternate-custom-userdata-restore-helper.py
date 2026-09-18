#!/usr/bin/env python3
"""Trace the alternate custom-userdata restore helper around 0x5AEC60.

Read-only static analysis of the supported GoW.exe plus the existing SQLite
research index. This helper is the only direct restore-root caller other than
LuaClient::Restore and is adjacent to __PickleTable/__SoftPickleTable access.

The pass disassembles:
- 0x5AEC20 / 0x5AEC40 wrappers
- the function containing 0x5AEC9E -> 0x7E9550
- direct callers of that helper
- one additional caller hop
and reports strings, RIP-relative globals, object field offsets and edges.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, sqlite3, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
SEEDS=[0x5AEC20,0x5AEC40,0x5AEC60,0x5AEC9E]
TERMS=("pickle","subobj","restore","save","checkpoint","wad","level","lua","state","soft")

def sha256(p:Path):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def load_pe():
 p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
 s=importlib.util.spec_from_file_location("gow_alt_restore",p)
 if not s or not s.loader:raise RuntimeError("PE helper load failed")
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def load_cs():
 root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
 if root.is_dir():sys.path.insert(0,str(root))
 from capstone import Cs,CS_ARCH_X86,CS_MODE_64
 from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
 return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def fn_for(con,rva):
 row=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
 return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def ascii_at(pe,rva,maxlen=180):
 off=pe.rva_to_file(rva)
 if off is None:return None
 out=[]
 for b in pe.data[off:off+maxlen]:
  if b==0:break
  if 32<=b<=126:out.append(chr(b))
  else:return None
 s="".join(out)
 return s if len(s)>=4 else None

def disasm(pe,md,fn,opi,opm,rip):
 off=pe.rva_to_file(fn["begin"])
 data=pe.data[off:off+fn["end"]-fn["begin"]]
 rows=[]; refs=[]; calls=[]; fields=[]
 for ins in md.disasm(data,IMAGE_BASE+fn["begin"]):
  rva=ins.address-IMAGE_BASE
  rows.append({"rva":rva,"rva_hex":f"0x{rva:X}","bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str})
  try:
   ops=list(ins.operands)
  except Exception:
   ops=[]
  for op in ops:
   if op.type==opi and ins.mnemonic in ("call","jmp"):
    v=int(op.imm); dest=v-IMAGE_BASE if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image else None
    if dest is not None:calls.append({"site":rva,"kind":ins.mnemonic,"dest":dest,"dest_hex":f"0x{dest:X}"})
   elif op.type==opm:
    base=md.reg_name(op.mem.base) if op.mem.base else None
    if op.mem.base==rip:
     target=ins.address+ins.size+op.mem.disp-IMAGE_BASE
     refs.append({"site":rva,"target":target,"target_hex":f"0x{target:X}","ascii":ascii_at(pe,target),"instruction":f"{ins.mnemonic} {ins.op_str}"})
    elif base and op.mem.disp and abs(op.mem.disp)<=0x500:
     fields.append({"site":rva,"base":base,"disp":op.mem.disp,"disp_hex":f"0x{op.mem.disp & 0xFFFFFFFF:X}","instruction":f"{ins.mnemonic} {ins.op_str}"})
 strings=sorted({x["ascii"] for x in refs if x.get("ascii")})
 score=sum(1 for s in strings for t in TERMS if t in s.lower())
 return {"begin":fn["begin"],"end":fn["end"],"size":fn["size"],"strings":strings,"score":score,
         "rip_refs":refs,"calls":calls,"fields":fields,"instructions":rows}

def incoming(con,fn):
 rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(fn,)).fetchall()
 return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]} for r in rows if r[1]!=fn]

def outgoing(con,fn):
 rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(fn,)).fetchall()
 return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]} for r in rows if r[4]!=fn]

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--exe",type=Path,required=True);ap.add_argument("--db",type=Path,required=True)
 ap.add_argument("--output-json",type=Path,required=True);ap.add_argument("--output-text",type=Path,required=True)
 a=ap.parse_args()
 if sha256(a.exe)!=EXPECTED:raise RuntimeError("unsupported GoW.exe")
 peh=load_pe();pe=peh.PE(a.exe.read_bytes())
 Cs,arch,mode,opi,opm,rip=load_cs();md=Cs(arch,mode);md.detail=True
 con=sqlite3.connect(a.db)
 try:
  seed_fns={}
  for rva in SEEDS:
   fn=fn_for(con,rva)
   if not fn:raise RuntimeError(f"missing function for 0x{rva:X}")
   seed_fns[fn["begin"]]=fn
  selected=set(seed_fns)
  first_callers=set()
  for fn in seed_fns:
   for e in incoming(con,fn):
    if e["src_fn"] is not None:
     first_callers.add(e["src_fn"]);selected.add(e["src_fn"])
  second_callers=set()
  for fn in first_callers:
   for e in incoming(con,fn):
    if e["src_fn"] is not None:
     second_callers.add(e["src_fn"]);selected.add(e["src_fn"])
  reps={}
  for fn in sorted(selected):
   meta=fn_for(con,fn)
   if not meta:continue
   rep=disasm(pe,md,meta,opi,opm,rip)
   rep["incoming"]=incoming(con,fn)
   rep["outgoing"]=outgoing(con,fn)
   rep["tier"]="seed" if fn in seed_fns else ("caller1" if fn in first_callers else "caller2")
   reps[f"0x{fn:X}"]=rep
  ranked=sorted(
   [{"fn":k,"tier":v["tier"],"score":v["score"],"strings":v["strings"],
     "calls_restore_root":any(c.get("dest")==0x7E9550 for c in v["calls"]),
     "field_offsets":sorted({x["disp_hex"] for x in v["fields"]})}
    for k,v in reps.items()],
   key=lambda x:(0 if x["tier"]=="seed" else 1 if x["tier"]=="caller1" else 2,-x["score"],x["fn"])
  )
  out={"schema":1,"analysis":"alternate_custom_userdata_restore_helper","exe_sha256":EXPECTED,
       "seed_rvas":[f"0x{x:X}" for x in SEEDS],"functions":reps,"ranked":ranked,
       "safety":{"static_pe_only":True,"game_launched":False,"save_opened":False,"exe_modified":False}}
  a.output_json.parent.mkdir(parents=True,exist_ok=True)
  a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
  lines=["Completionist Map - alternate custom userdata restore helper",f"exe_sha256={EXPECTED}",
         "game_launched=false save_opened=false exe_modified=false",""]
  for r in ranked:
   lines.append(f"{r['tier'].upper()} {r['fn']} score={r['score']} restoreRoot={r['calls_restore_root']} fields={r['field_offsets']} strings={r['strings']}")
  for k,v in reps.items():
   lines+=["",f"FUNCTION {k} tier={v['tier']} size={v['size']} score={v['score']}"]
   for rr in v["rip_refs"]:
    if rr.get("ascii"):lines.append(f"  REF 0x{rr['site']:X}->0x{rr['target']:X} {rr['ascii']!r}")
   for c in v["calls"]:
    lines.append(f"  EDGE {c['kind']} 0x{c['site']:X}->0x{c['dest']:X}")
   lines.append("  DISASM")
   for ins in v["instructions"]:lines.append(f"    {ins['rva_hex']}: {ins['bytes']:<24} {ins['mnemonic']} {ins['op_str']}")
  a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
  print(f"ALT_RESTORE_HELPER_TRACE_COMPLETE functions={len(reps)} seedFns={len(seed_fns)} caller1={len(first_callers)} caller2={len(second_callers)}")
  for r in ranked[:30]:print(f"RANK {r['tier']} {r['fn']} score={r['score']} restoreRoot={r['calls_restore_root']} strings={' | '.join(r['strings'][:8])}")
 finally:
  con.close()
 return 0
if __name__=="__main__":raise SystemExit(main())
