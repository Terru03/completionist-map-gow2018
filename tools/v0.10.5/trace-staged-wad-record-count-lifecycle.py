#!/usr/bin/env python3
"""Trace all native writes to the staged WAD record count.

Static/read-only. The remaining Raven authority question is whether individual
staged WAD records can be removed after unload. This probe classifies every
RIP-relative reference to the proven record_count global (0x22C696C), validates
operand direction with Capstone, and emits complete functions for every writer.

It also records references to record_base/key/payload globals in each writer so
full reset, checkpoint load/rebuild, append, and possible compaction paths can
be distinguished.

No game/process/save access and no writes.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, sys
from pathlib import Path

EXPECTED_SHA256="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
GLOBALS={
    "record_count":0x22C696C,
    "record_base":0x22C7170,
    "record_key":0x22C7194,
    "payload_size":0x22C6938,
    "payload_base":0x22C6940,
}
COUNT=GLOBALS["record_count"]

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-checkpoint-restore-bridge.py")
    spec=importlib.util.spec_from_file_location("record_count_pe",p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {p}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_capstone(path):
    sys.path.insert(0,str(path))
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
    return md,X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

def fn_for(con,addr):
    r=con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? "
        "ORDER BY begin DESC LIMIT 1",(addr,addr)
    ).fetchone()
    return None if not r else {"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}

def rows(cur):
    cols=[x[0] for x in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def dis(md,pe,start,end,opimm,opmem,rip):
    out=[]
    for ins in md.disasm(pe.read(start,end-start),IMAGE_BASE+start):
        row={"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,
             "op_str":ins.op_str,"rip_mem":[],"immediates":[]}
        for oi,op in enumerate(ins.operands):
            if op.type==opimm:
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+0x80000000: v-=IMAGE_BASE
                row["immediates"].append(v)
            elif op.type==opmem and op.mem.base==rip:
                target=ins.address+ins.size+op.mem.disp-IMAGE_BASE
                row["rip_mem"].append({
                    "operand_index":oi,"target":target,
                    "access":int(getattr(op,"access",0)),
                })
        out.append(row)
    return out

def is_write(access):
    return bool(int(access)&2)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--capstone-path",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()

    digest=sha256_file(a.exe).lower()
    if digest!=EXPECTED_SHA256: raise RuntimeError(f"unsupported GoW.exe SHA-256: {digest}")
    helper=load_pe(); pe=helper.PE(a.exe.read_bytes())
    md,opimm,opmem,rip=load_capstone(a.capstone_path)
    con=sqlite3.connect(f"file:{a.db.as_posix()}?mode=ro",uri=True)
    try:
        indexed=rows(con.execute(
            "SELECT site,src_fn,mnemonic,target FROM rip_refs WHERE target=? ORDER BY site",(COUNT,)
        ))
        fns=sorted(set(r["src_fn"] for r in indexed))
        refs=[]
        functions=[]
        for begin in fns:
            fn=fn_for(con,begin)
            if not fn: continue
            ins=dis(md,pe,fn["begin"],fn["end"],opimm,opmem,rip)
            count_refs=[]
            global_hits=[]
            for x in ins:
                for m in x["rip_mem"]:
                    if m["target"]==COUNT:
                        entry={**x,"access":m["access"],"write":is_write(m["access"])}
                        count_refs.append(entry); refs.append(entry)
                    for name,target in GLOBALS.items():
                        if m["target"]==target:
                            global_hits.append({"name":name,"instruction":x,"access":m["access"],
                                                "write":is_write(m["access"])})
            if any(r["write"] for r in count_refs):
                callers=rows(con.execute(
                    "SELECT site,src_fn,kind,dest,target_fn FROM edges "
                    "WHERE target_fn=? ORDER BY site",(fn["begin"],)
                ))
                callees=rows(con.execute(
                    "SELECT site,kind,dest,target_fn FROM edges "
                    "WHERE src_fn=? ORDER BY site",(fn["begin"],)
                ))
                functions.append({"function":fn,"count_refs":count_refs,
                                  "global_hits":global_hits,"callers":callers,
                                  "callees":callees,"instructions":ins})
        writes=[r for r in refs if r["write"]]
        reads=[r for r in refs if not r["write"]]
        result={
            "schema":1,"analysis":"staged_wad_record_count_lifecycle",
            "exe_sha256":digest,"record_count_rva":COUNT,
            "indexed_ref_count":len(indexed),"validated_ref_count":len(refs),
            "write_count":len(writes),"read_count":len(reads),
            "writes":writes,"writer_functions":functions,
            "safety":{"static_only":True,"game_launched":False,"process_opened":False,
                      "save_opened":False,"process_memory_written":False,
                      "save_written":False,"progression_written":False,
                      "game_files_written":False},
        }
    finally:
        con.close()

    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    L=[
        "Completionist Map - staged WAD record-count lifecycle trace",
        f"exe_sha256={digest}",
        f"record_count=0x{COUNT:X}",
        f"indexed_refs={len(indexed)} validated_refs={len(refs)} writes={len(writes)} reads={len(reads)}",
        "",
        "RECORD_COUNT WRITES",
    ]
    for w in writes:
        L.append(f"  site=0x{w['rva']:X} fn=0x{fn_for(con,w['rva'])['begin']:X} "
                 f"{w['mnemonic']} {w['op_str']} access={w['access']}")
    L+=["","WRITER FUNCTIONS"]
    for item in functions:
        fn=item["function"]
        L.append(f"\nFUNCTION 0x{fn['begin']:X}..0x{fn['end']:X} size={fn['size']}")
        L.append("  COUNT_REFS")
        for x in item["count_refs"]:
            L.append(f"    0x{x['rva']:08X} {x['mnemonic']:<8} {x['op_str']} write={str(x['write']).lower()}")
        L.append("  GLOBAL_HITS")
        for x in item["global_hits"]:
            ins=x["instruction"]
            L.append(f"    {x['name']} 0x{ins['rva']:08X} {ins['mnemonic']:<8} {ins['op_str']} "
                     f"write={str(x['write']).lower()}")
        L.append("  CALLERS")
        for x in item["callers"][:100]:
            L.append(f"    site=0x{x['site']:X} src=0x{x['src_fn']:X} kind={x['kind']} "
                     f"dest={x['dest']} target={x['target_fn']}")
        L.append("  CALLEES")
        for x in item["callees"][:140]:
            L.append(f"    site=0x{x['site']:X} kind={x['kind']} dest={x['dest']} target={x['target_fn']}")
        L.append("  DISASSEMBLY")
        for ins in item["instructions"]:
            marks=[]
            for m in ins["rip_mem"]:
                for name,target in GLOBALS.items():
                    if m["target"]==target:
                        marks.append(f"{name}:{'W' if is_write(m['access']) else 'R'}")
            mark=(" ; "+" ".join(marks)) if marks else ""
            L.append(f"    0x{ins['rva']:08X} {ins['bytes']:<20} {ins['mnemonic']:<8} {ins['op_str']}{mark}")
    L+=["","SAFETY static_only=true game_launched=false process_opened=false save_opened=false "
        "process_memory_written=false save_written=false progression_written=false game_files_written=false"]
    a.output_text.write_text("\n".join(L)+"\n",encoding="utf-8")
    print(f"STAGED_WAD_RECORD_COUNT_LIFECYCLE_COMPLETE refs={len(refs)} writes={len(writes)} writers={len(functions)}")
    return 0

if __name__=="__main__": raise SystemExit(main())
