#!/usr/bin/env python3
"""Resolve Lua Map API registration stubs and signatures around 0x2AEF40.

Static, read-only, version-locked. Dumps the registration function around known
map APIs, resolves nearby code pointers, and disassembles the candidate native
binding stubs for:
  GetMarkersInfoTable
  GetMarkersInfoTableInRealmWithFlags
  GetMarkerInfo
  FindQuestForMarker
  FindRegionFromMarker
  GetRegionsInfoTable
  GetRealmsInfoTable

No game launch, process access, save access, or writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
REG_FN=0x2AEF40
APIS={
 "GetMarkerInfo":0xE2DF18,
 "GetRegionsInfoTable":0xE2DF28,
 "GetRealmsInfoTable":0xE2DF40,
 "GetMarkersInfoTableInRealmWithFlags":0xE2DF58,
 "GetMarkersInfoTable":0xE2DF80,
 "FindQuestForMarker":0xE2D5F8,
 "FindRegionFromMarker":0xE2E178,
}
def sha256(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def load_pe():
 p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
 s=importlib.util.spec_from_file_location("gow_mapapi_sig_pe",p)
 if not s or not s.loader:raise RuntimeError("PE helper load failed")
 m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def load_cs():
 root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
 if root.is_dir():sys.path.insert(0,str(root))
 from capstone import Cs,CS_ARCH_X86,CS_MODE_64
 from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP
 return Cs,CS_ARCH_X86,CS_MODE_64,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP
def fn_for(con,rva):
 row=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
 return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}
def ascii_at(pe,rva,maxlen=128):
 off=pe.rva_to_file(rva)
 if off is None:return None
 out=[]
 for b in pe.data[off:off+maxlen]:
  if b==0:break
  if 32<=b<=126:out.append(chr(b))
  else:return None
 s="".join(out)
 return s if len(s)>=4 else None
def disasm(pe,md,meta):
 off=pe.rva_to_file(meta["begin"])
 if off is None:return []
 return list(md.disasm(pe.data[off:off+meta["size"]],IMAGE_BASE+meta["begin"]))
def slim(ins):
 return {"rva":ins.address-IMAGE_BASE,"hex":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--exe",type=Path,required=True);ap.add_argument("--db",type=Path,required=True)
 ap.add_argument("--output-json",type=Path,required=True);ap.add_argument("--output-text",type=Path,required=True)
 a=ap.parse_args()
 if sha256(a.exe)!=EXPECTED:raise RuntimeError("unsupported GoW.exe")
 peh=load_pe();pe=peh.PE(a.exe.read_bytes())
 Cs,arch,mode,X86_OP_IMM,X86_OP_MEM,X86_OP_REG,X86_REG_RIP=load_cs()
 md=Cs(arch,mode);md.detail=True
 con=sqlite3.connect(a.db)
 try:
  regmeta=fn_for(con,REG_FN)
  rins=disasm(pe,md,regmeta)
  sites={}
  for name,srva in APIS.items():
   hit=[]
   for i,ins in enumerate(rins):
    try:ops=list(ins.operands)
    except Exception:ops=[]
    for op in ops:
     if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      t=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
      if t==srva:hit.append(i)
   sites[name]=hit

  # For each registration site, dump +/-18 instructions and collect code-address
  # RIP-relative LEAs in that window. The actual binding pointer is normally loaded
  # immediately around the API-name string before the common registrar call.
  reps={}
  candidate_fns=set()
  for name,idxs in sites.items():
   wins=[]
   for ix in idxs:
    rows=[];cands=[]
    for ins in rins[max(0,ix-18):min(len(rins),ix+19)]:
     row=slim(ins)
     try:ops=list(ins.operands)
     except Exception:ops=[]
     for op in ops:
      if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
       t=ins.address+ins.size+int(op.mem.disp)-IMAGE_BASE
       s=ascii_at(pe,t)
       fm=fn_for(con,t)
       row.setdefault("rip_refs",[]).append({"target":t,"string":s,"function":fm})
       if fm and fm["begin"]==t and fm["begin"]!=REG_FN:
        candidate_fns.add(t);cands.append(t)
     rows.append(row)
    wins.append({"site":rins[ix].address-IMAGE_BASE,"instructions":rows,"candidate_functions":sorted(set(cands))})
   reps[name]=wins

  bindings={}
  for fn in sorted(candidate_fns):
   meta=fn_for(con,fn)
   if not meta or meta["size"]>0x3000:continue
   ins=disasm(pe,md,meta)
   strings=[];calls=[]
   for x in ins:
    try:ops=list(x.operands)
    except Exception:ops=[]
    for op in ops:
     if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      t=x.address+x.size+int(op.mem.disp)-IMAGE_BASE;s=ascii_at(pe,t)
      if s:strings.append({"site":x.address-IMAGE_BASE,"target":t,"string":s})
     elif op.type==X86_OP_IMM and x.mnemonic in ("call","jmp"):
      v=int(op.imm)
      if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:calls.append({"site":x.address-IMAGE_BASE,"dest":v-IMAGE_BASE,"kind":x.mnemonic})
   bindings[f"0x{fn:X}"]={"function":meta,"strings":strings,"calls":calls,"instructions":[slim(x) for x in ins]}

  out={"schema":1,"analysis":"map_api_binding_signatures","exe_sha256":EXPECTED,
       "registration_function":regmeta,"apis":reps,"candidate_bindings":bindings,
       "safety":{"static_pe_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"exe_modified":False}}
  a.output_json.parent.mkdir(parents=True,exist_ok=True)
  a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
  lines=["Completionist Map - Map API binding signatures",f"exe_sha256={EXPECTED}","game_launched=false process_opened=false save_opened=false exe_modified=false",""]
  for name,wins in reps.items():
   lines.append(f"API {name} string_rva=0x{APIS[name]:X} sites={len(wins)}")
   for w in wins:
    lines.append(f"  REG_SITE 0x{w['site']:X} candidates="+",".join(f"0x{x:X}" for x in w["candidate_functions"]))
    for i in w["instructions"]:
     extra=""
     if i.get("rip_refs"):
      extra=" ; "+" | ".join(f"rip=0x{r['target']:X} str={r.get('string')!r} fn={(('0x%X'%r['function']['begin']) if r.get('function') else None)}" for r in i["rip_refs"])
     lines.append(f"    0x{i['rva']:X}: {i['hex']:<24} {i['mnemonic']} {i['op_str']}{extra}")
   lines.append("")
  lines.append("CANDIDATE_BINDINGS")
  for key,b in bindings.items():
   lines.append(f"  FUNCTION {key} size=0x{b['function']['size']:X}")
   for s in b["strings"]:lines.append(f"    STRING 0x{s['site']:X} {s['string']!r}")
   for i in b["instructions"]:lines.append(f"    0x{i['rva']:X}: {i['hex']:<24} {i['mnemonic']} {i['op_str']}")
   lines.append("")
  a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
  print("MAP_API_BINDING_SIGNATURES_COMPLETE api_sites="+str(sum(len(v) for v in reps.values()))+" candidate_bindings="+str(len(bindings)))
  for n,w in reps.items():
   for x in w: print(f"API {n} site=0x{x['site']:X} candidates="+",".join(f"0x{y:X}" for y in x["candidate_functions"]))
 finally:con.close()
if __name__=="__main__":raise SystemExit(main())
