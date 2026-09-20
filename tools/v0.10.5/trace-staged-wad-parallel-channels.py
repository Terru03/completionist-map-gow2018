#!/usr/bin/env python3
"""Trace neighbouring staged-WAD globals and record channels around the proven 0xA8 table.

Static/read-only analysis of the pinned GoW executable and research index.
The goal is to locate the parallel checkpoint/SoftPickle stream that is not
present in the first staged payload pool at 0x22C6940/0x22C6938.

Outputs:
- all RIP-referenced globals in the narrow 0x22C6900..0x22C7200 staging band;
- exact references into the first 0xA8 staged-record template;
- full disassembly of the key checkpoint functions that create/consume this area;
- compact candidate ranking for neighbouring pointer/size globals.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, struct, sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
BAND_START=0x22C6900
BAND_END=0x22C7200
RECORD_BASE=0x22C7170
RECORD_STRIDE=0xA8
FOCUS=(0x6671E0,0x667230,0x6672F0,0x667380,0x668683,0x6687F0,0x669300,0x669B00,0x66ABD0,0x66B650,0x66C080,0x82B070,0x82B250,0x82CDAE,0x82CF00,0x82D660,0x82D760)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-checkpoint-restore-bridge.py")
    spec=importlib.util.spec_from_file_location("bridge_pe2",p)
    if spec is None or spec.loader is None:raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load_capstone(path):
    sys.path.insert(0,str(path))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    return md,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def fn_for(con,addr):
    r=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(addr,addr)).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def dis(md,pe,start,end,opimm,opmem,rip):
    out=[]
    for ins in md.disasm(pe.read(start,end-start),IMAGE_BASE+start):
        row={"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str,"rip_targets":[],"mem_disps":[],"immediates":[]}
        for op in ins.operands:
            if op.type==opimm:
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+0x80000000:v-=IMAGE_BASE
                row["immediates"].append(v)
            elif op.type==opmem:
                row["mem_disps"].append(int(op.mem.disp))
                if op.mem.base==rip:
                    row["rip_targets"].append(ins.address+ins.size+op.mem.disp-IMAGE_BASE)
        out.append(row)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--capstone-path",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    digest=sha256_file(a.exe).lower()
    if digest!=EXPECTED_SHA256:raise RuntimeError(f"unsupported GoW.exe SHA-256: {digest}")
    helper=load_pe();pe=helper.PE(a.exe.read_bytes())
    md,opimm,opmem,rip=load_capstone(a.capstone_path)
    con=sqlite3.connect(f"file:{a.db.as_posix()}?mode=ro",uri=True)
    try:
        refs=con.execute("SELECT target,site,src_fn,mnemonic FROM rip_refs WHERE target>=? AND target<? ORDER BY target,site",(BAND_START,BAND_END)).fetchall()
        by_target=defaultdict(list)
        for t,s,f,m in refs:by_target[t].append({"site":s,"src_fn":f,"mnemonic":m})
        targets=[]
        for t,rs in sorted(by_target.items()):
            fns=sorted(set(x["src_fn"] for x in rs))
            targets.append({"rva":t,"offset_from_record_base":t-RECORD_BASE if RECORD_BASE<=t<RECORD_BASE+RECORD_STRIDE else None,"ref_count":len(rs),"source_functions":fns,"refs":rs})
        focus={}
        seen=set()
        for addr in FOCUS:
            fn=fn_for(con,addr)
            if not fn or fn["begin"] in seen:continue
            seen.add(fn["begin"])
            rows=dis(md,pe,fn["begin"],fn["end"],opimm,opmem,rip)
            focus[f"0x{fn['begin']:X}"]={"function":fn,"instructions":rows,"band_hits":[r for r in rows if any(BAND_START<=x<BAND_END for x in r["rip_targets"])],
                "small_struct_disps":sorted(set(d for r in rows for d in r["mem_disps"] if -0x20<=d<=0xC0))}
        # Candidate neighbouring globals: referenced by checkpoint focus functions, excluding the already-proven first pool.
        focus_begins={v["function"]["begin"] for v in focus.values()}
        cands=[]
        for row in targets:
            hits=[r for r in row["refs"] if r["src_fn"] in focus_begins]
            if hits:
                cands.append({**row,"focus_ref_count":len(hits),"focus_refs":hits})
        cands.sort(key=lambda x:(-x["focus_ref_count"],x["rva"]))
        result={"schema":1,"analysis":"staged_wad_parallel_channels","exe_sha256":digest,
            "band":{"start":BAND_START,"end":BAND_END,"record_base":RECORD_BASE,"record_stride":RECORD_STRIDE},
            "targets":targets,"candidate_globals":cands,"focus":focus,
            "safety":{"static_only":True,"game_launched":False,"process_opened":False,"save_opened":False,"process_memory_written":False,"save_written":False,"progression_written":False}}
    finally:con.close()
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    L=["Completionist Map - staged WAD parallel channel trace",f"exe_sha256={digest}",f"band=0x{BAND_START:X}..0x{BAND_END:X}",f"rip_targets={len(targets)}","",
       "CANDIDATE GLOBALS"]
    for x in cands:
        off=x["offset_from_record_base"]
        L.append(f"  rva=0x{x['rva']:X} recordOff={('0x%X'%off) if off is not None else '-'} refs={x['ref_count']} focusRefs={x['focus_ref_count']} fns="+",".join(f"0x{v:X}" for v in x["source_functions"][:16]))
    L+=["","FOCUS FUNCTIONS"]
    for k,v in focus.items():
        fn=v["function"];L.append(f"\nFUNCTION {k}..0x{fn['end']:X} size={fn['size']} smallDisps="+",".join(hex(x) for x in v["small_struct_disps"]))
        for r in v["instructions"]:
            marks=[]
            for t in r["rip_targets"]:
                if BAND_START<=t<BAND_END:marks.append(f"BAND=0x{t:X}")
            mark=(" ; "+" ".join(marks)) if marks else ""
            L.append(f"  0x{r['rva']:08X} {r['bytes']:<20} {r['mnemonic']:<8} {r['op_str']}{mark}")
    L+=["","SAFETY static_only=true process_opened=false process_memory_written=false save_opened=false save_written=false progression_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"STAGED_WAD_PARALLEL_CHANNEL_TRACE_COMPLETE targets={len(targets)} candidates={len(cands)} focus={len(focus)}")

if __name__=="__main__":raise SystemExit(main())
