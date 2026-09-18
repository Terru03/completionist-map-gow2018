#!/usr/bin/env python3
"""Find native writers of the transient LuaClient pickle-buffer fields +0x70/+0x78.

Read-only static analysis of the supported GoW.exe using the existing runtime
function index.  The live capture proved these fields are empty after restore,
so the writer that populates them before 0x5AF4E0 is the best lead to the
unloaded-WAD persistence cache.

Ranking signals:
- writes both +0x70 and +0x78 in the same function;
- accesses LuaClient's proven Lua-state field +0x58;
- calls/branches to known persistence functions;
- belongs to the 0x5Axxxx/0x5Bxxxx LuaClient persistence neighborhood;
- direct caller/callee connectivity to known pickle/restore roots.

No game launch, process access, save access, or file modification.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sqlite3, sys
from pathlib import Path

EXPECTED="caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE=0x140000000
TARGET_DISPS={0x70,0x78}
KNOWN={
    0x5AF01C:"checkpoint_save_driver",
    0x5AF4E0:"softpickle_prev_restore_merge",
    0x5AEC60:"pickle_table_restore_helper",
    0x5B2130:"luaclient_pickle_virtual",
    0x5B2280:"luaclient_unpickle_virtual",
    0x7E7F10:"carrier_builder",
    0x7E9550:"carrier_restore",
}
NEAR_LO=0x5A0000
NEAR_HI=0x5C0000

def sha256(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def load_pe():
    p=Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    s=importlib.util.spec_from_file_location("gow_field_writer",p)
    if not s or not s.loader:raise RuntimeError("PE helper load failed")
    m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m

def load_cs():
    root=Path(__file__).resolve().parents[2]/".research-index"/"python-packages"
    if root.is_dir():sys.path.insert(0,str(root))
    import capstone
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
    from capstone.x86_const import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
    return capstone,Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP

def fn_for(con,rva):
    row=con.execute("SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",(rva,rva)).fetchone()
    return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}

def function_rows(con):
    return [{"begin":r[0],"end":r[1],"size":r[2],"section":r[3]}
            for r in con.execute("SELECT begin,end,size,section FROM functions WHERE section='.text' ORDER BY begin")]

def direct_callers(con,fn):
    rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site",(fn,)).fetchall()
    return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]}
            for r in rows if r[1] is not None and r[1]!=fn]

def outgoing(con,fn):
    rows=con.execute("SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",(fn,)).fetchall()
    return [{"site":r[0],"src_fn":r[1],"kind":r[2],"dest":r[3],"target_fn":r[4]}
            for r in rows if r[4] is not None and r[4]!=fn]

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

def inspect_fn(pe,md,fn,CS_AC_WRITE,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP):
    off=pe.rva_to_file(fn["begin"])
    if off is None:return None
    data=pe.data[off:off+fn["size"]]
    insns=[];writes=[];allfields=[];calls=[];refs=[]
    for ins in md.disasm(data,IMAGE_BASE+fn["begin"]):
        rva=ins.address-IMAGE_BASE
        row={"rva":rva,"rva_hex":f"0x{rva:X}","bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str}
        insns.append(row)
        try:ops=list(ins.operands)
        except Exception:ops=[]
        for op in ops:
            if op.type==X86_OP_MEM:
                base=md.reg_name(op.mem.base) if op.mem.base else None
                disp=int(op.mem.disp)
                access=int(getattr(op,"access",0))
                item={"site":rva,"base":base,"disp":disp,"access":access,"instruction":f"{ins.mnemonic} {ins.op_str}"}
                if op.mem.base==X86_REG_RIP:
                    target=ins.address+ins.size+disp-IMAGE_BASE
                    refs.append({"site":rva,"target":target,"ascii":ascii_at(pe,target),"instruction":item["instruction"]})
                elif abs(disp)<=0x300:
                    allfields.append(item)
                    if disp in TARGET_DISPS and (access & CS_AC_WRITE):
                        writes.append(item)
            elif op.type==X86_OP_IMM and ins.mnemonic in ("call","jmp"):
                v=int(op.imm)
                if IMAGE_BASE<=v<IMAGE_BASE+pe.size_of_image:
                    calls.append({"site":rva,"kind":ins.mnemonic,"dest":v-IMAGE_BASE})
    if not writes:return None
    strings=sorted({r["ascii"] for r in refs if r.get("ascii")})
    fieldset=sorted({f["disp"] for f in allfields})
    callset=sorted({c["dest"] for c in calls})
    score=0;reasons=[]
    wd={w["disp"] for w in writes}
    if wd==TARGET_DISPS:
        score+=20;reasons.append("writes_both_0x70_0x78")
    else:
        score+=8;reasons.append("writes_one_target_field")
    if 0x58 in fieldset:
        score+=12;reasons.append("accesses_lua_state_0x58")
    known_calls=sorted(set(callset)&set(KNOWN))
    if known_calls:
        score+=15+5*len(known_calls);reasons.append("calls_known_persistence")
    if NEAR_LO<=fn["begin"]<NEAR_HI:
        score+=12;reasons.append("lua_persistence_neighborhood")
    if any(("pickle" in s.lower() or "checkpoint" in s.lower() or "save" in s.lower() or "restore" in s.lower() or "wad" in s.lower()) for s in strings):
        score+=10;reasons.append("persistence_string")
    return {"begin":fn["begin"],"end":fn["end"],"size":fn["size"],"score":score,"reasons":reasons,
            "writes":writes,"field_disps":fieldset,"calls":calls,"known_calls":[{"rva":x,"name":KNOWN[x]} for x in known_calls],
            "strings":strings,"refs":refs,"instructions":insns}

def context(insns,site,before=8,after=10):
    idx=next((i for i,x in enumerate(insns) if x["rva"]==site),None)
    if idx is None:return []
    return insns[max(0,idx-before):min(len(insns),idx+after+1)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-text",type=Path,required=True)
    a=ap.parse_args()
    if sha256(a.exe)!=EXPECTED:raise RuntimeError("unsupported GoW.exe")
    peh=load_pe();pe=peh.PE(a.exe.read_bytes())
    cap,Cs,arch,mode,CS_AC_WRITE,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP=load_cs()
    md=Cs(arch,mode);md.detail=True
    con=sqlite3.connect(a.db)
    try:
        matches=[]
        total=0
        for fn in function_rows(con):
            total+=1
            rep=inspect_fn(pe,md,fn,CS_AC_WRITE,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP)
            if rep is None:continue
            rep["incoming"]=direct_callers(con,fn["begin"])
            rep["outgoing"]=outgoing(con,fn["begin"])
            rep["caller_known_links"]=[
                {"caller":e["src_fn"],"site":e["site"],"caller_known_name":KNOWN.get(e["src_fn"])}
                for e in rep["incoming"] if e["src_fn"] in KNOWN
            ]
            if rep["caller_known_links"]:
                rep["score"]+=15
                rep["reasons"].append("called_by_known_persistence")
            for w in rep["writes"]:
                w["context"]=context(rep["instructions"],w["site"])
            matches.append(rep)
        matches.sort(key=lambda x:(-x["score"],x["begin"]))
        out={"schema":1,"analysis":"luaclient_pickle_buffer_field_writers","exe_sha256":EXPECTED,
             "target_fields_hex":["0x70","0x78"],"functions_scanned":total,"match_count":len(matches),
             "known_functions":{f"0x{k:X}":v for k,v in KNOWN.items()},"matches":matches,
             "safety":{"static_pe_only":True,"game_launched":False,"process_opened":False,
                       "save_opened":False,"exe_modified":False}}
        a.output_json.parent.mkdir(parents=True,exist_ok=True)
        a.output_json.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        lines=["Completionist Map - LuaClient +0x70/+0x78 field writers",f"exe_sha256={EXPECTED}",
               f"functions_scanned={total}",f"match_count={len(matches)}",
               "game_launched=false process_opened=false save_opened=false exe_modified=false",""]
        for i,m in enumerate(matches[:120],1):
            lines.append(f"#{i} fn=0x{m['begin']:X}-0x{m['end']:X} score={m['score']} reasons={','.join(m['reasons'])} fields={[hex(x) for x in m['field_disps']]} strings={m['strings']}")
            for w in m["writes"]:
                lines.append(f"  WRITE site=0x{w['site']:X} base={w['base']} disp=0x{w['disp']:X} {w['instruction']}")
                for ins in w["context"]:
                    lines.append(f"    0x{ins['rva']:X}: {ins['bytes']:<24} {ins['mnemonic']} {ins['op_str']}")
            for k in m["known_calls"]:
                lines.append(f"  KNOWN_CALL 0x{k['rva']:X} {k['name']}")
            for e in m["incoming"][:24]:
                lines.append(f"  CALLER fn=0x{e['src_fn']:X} site=0x{e['site']:X}")
        a.output_text.write_text("\n".join(lines)+"\n",encoding="utf-8")
        print(f"LUACLIENT_PICKLE_FIELD_WRITER_SCAN_COMPLETE functions={total} matches={len(matches)}")
        for i,m in enumerate(matches[:30],1):
            print(f"RANK {i} fn=0x{m['begin']:X} score={m['score']} reasons={','.join(m['reasons'])} writes={','.join(hex(w['disp']) for w in m['writes'])} strings={' | '.join(m['strings'][:6])}")
    finally:
        con.close()
    return 0
if __name__=="__main__":raise SystemExit(main())
