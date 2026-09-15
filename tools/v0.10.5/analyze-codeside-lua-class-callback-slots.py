"""Map native CodeSideLuaClass callback slots using the reusable GoW research index.

This is a broad, reusable follow-up to the checkpoint codec analysis.  It uses
SQLite to select native functions that combine indirect dispatch with class-like
field accesses, then Capstone-disassembles only those candidate functions from
the exact supported GoW.exe.  It recovers callback-register provenance and
ranks class walkers / callback slots, especially around the proven layout:

  +0x48 parent pointer
  +0xA4 asserted byte
  +0xB8 persistence encoder callback

The goal is to discover neighboring inverse/unpickle callback slots and connect
them to restore / GameObject machinery.  Read-only with respect to the game and
saves; outputs reports only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
RESTORE_ROOTS = (0x7E9550, 0x5B2324, 0x5B2280)
GAMEOBJECT_ROOTS = (0x4EF0B0, 0x5F9350, 0x60B9C0)
KNOWN_CLASS_FIELDS = {0x48, 0xA4, 0xB8}
CALLBACK_WINDOW = range(0x80, 0x101, 8)
INTERESTING_TERMS = (
    "codesideluaclass", "gameobject", "pickle", "unpickle", "restore",
    "checkpoint", "serialize", "deserialize", "classref", "userdata",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    p = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_MEM, X86_OP_REG
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_MEM, X86_OP_REG


def normalize_reg(name: str | None):
    if not name:
        return None
    aliases = {
        "eax":"rax","ax":"rax","al":"rax","ah":"rax",
        "ebx":"rbx","bx":"rbx","bl":"rbx","bh":"rbx",
        "ecx":"rcx","cx":"rcx","cl":"rcx","ch":"rcx",
        "edx":"rdx","dx":"rdx","dl":"rdx","dh":"rdx",
        "esi":"rsi","si":"rsi","sil":"rsi",
        "edi":"rdi","di":"rdi","dil":"rdi",
        "ebp":"rbp","bp":"rbp","bpl":"rbp",
        "esp":"rsp","sp":"rsp","spl":"rsp",
    }
    if name in aliases:
        return aliases[name]
    m = re.fullmatch(r"r(\d+)(?:d|w|b)?", name)
    return f"r{m.group(1)}" if m else name


def safe_operands(ins):
    try:
        return list(ins.operands)
    except Exception:
        return []


def safe_regs(ins, md):
    try:
        rr, rw = ins.regs_access()
        return ([normalize_reg(md.reg_name(x)) for x in rr],
                [normalize_reg(md.reg_name(x)) for x in rw])
    except Exception:
        return ([], [])


def function_for(con, rva):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    return None if not row else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}


def call_graph(con):
    out, rev = defaultdict(set), defaultdict(set)
    for src,dst in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        out[src].add(dst); rev[dst].add(src)
    return out, rev


def bfs(g, starts, depth=7):
    dist = {}
    q = deque()
    for s in starts:
        if s is not None and s not in dist:
            dist[s] = 0; q.append(s)
    while q:
        cur = q.popleft()
        if dist[cur] >= depth:
            continue
        for nxt in g.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1; q.append(nxt)
    return dist


def candidate_functions(con):
    callback_disps = tuple(CALLBACK_WINDOW)
    placeholders = ",".join("?" for _ in callback_disps)
    # Start with every function having an indirect call plus a plausible class callback field.
    sql = (
        "SELECT DISTINCT i.src_fn FROM indirect_calls i JOIN mem_refs m ON m.src_fn=i.src_fn "
        f"WHERE m.disp IN ({placeholders})"
    )
    cands = {r[0] for r in con.execute(sql, callback_disps) if r[0] is not None}
    # Add functions containing the proven parent/asserted fields and an indirect dispatch.
    for (fn,) in con.execute(
        "SELECT DISTINCT i.src_fn FROM indirect_calls i JOIN mem_refs m ON m.src_fn=i.src_fn "
        "WHERE m.disp IN (72,164,184)"
    ):
        if fn is not None: cands.add(fn)
    # Add functions referencing key semantic strings even if field indexing missed an instruction.
    term_hits = []
    for term in INTERESTING_TERMS:
        for row in con.execute(
            "SELECT DISTINCT src_fn FROM rip_refs WHERE target_string IS NOT NULL AND lower(target_string) LIKE ?",
            (f"%{term}%",),
        ):
            if row[0] is not None:
                term_hits.append(row[0])
    indirect_fns = {r[0] for r in con.execute("SELECT DISTINCT src_fn FROM indirect_calls WHERE src_fn IS NOT NULL")}
    cands.update(fn for fn in term_hits if fn in indirect_fns)
    return sorted(cands)


def disasm_function(md, pe, begin, end):
    off = pe.rva_to_file(begin)
    if off is None:
        return []
    blob = pe.data[off:off+(end-begin)]
    return list(md.disasm(blob, IMAGE_BASE + begin))


def mem_operands(ins, md, op_mem):
    out=[]
    for oi,op in enumerate(safe_operands(ins)):
        if op.type != op_mem:
            continue
        out.append({
            "operand":oi,
            "base":normalize_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
            "index":normalize_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
            "scale":op.mem.scale,
            "disp":op.mem.disp,
        })
    return out


def indirect_call_target(ins, md, op_mem, op_reg):
    if ins.mnemonic != "call":
        return None
    ops=safe_operands(ins)
    if not ops: return None
    op=ops[0]
    if op.type == op_reg:
        return {"kind":"reg","reg":normalize_reg(md.reg_name(op.reg))}
    if op.type == op_mem:
        return {"kind":"mem","base":normalize_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
                "index":normalize_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
                "scale":op.mem.scale,"disp":op.mem.disp}
    return None


def record(ins, md, op_mem):
    rr,rw=safe_regs(ins,md)
    return {
        "rva":ins.address-IMAGE_BASE,"mnemonic":ins.mnemonic,"op_str":ins.op_str,
        "bytes":ins.bytes.hex(),"reads":rr,"writes":rw,"mem":mem_operands(ins,md,op_mem)
    }


def backslice(records, idx, target, limit=90):
    wanted=set()
    if target["kind"]=="reg" and target.get("reg"):
        wanted.add(target["reg"])
    elif target["kind"]=="mem":
        if target.get("base"): wanted.add(target["base"])
        if target.get("index"): wanted.add(target["index"])
    steps=[]; loads=[]
    for j in range(idx-1,max(-1,idx-limit-1),-1):
        r=records[j]
        w=set(r["writes"]); rd=set(r["reads"])
        if not ((w|rd)&wanted):
            continue
        steps.append(r)
        hw=w&wanted
        if hw and r["mnemonic"] in ("mov","lea"):
            for m in r["mem"]:
                loads.append({"instruction":r,"mem":m,"written_regs":sorted(hw)})
        if hw:
            wanted-=hw
            wanted.update(x for x in rd if x not in ("rsp","rip","rflags","eflags"))
        if not wanted: break
    steps.reverse(); loads.reverse()
    return {"steps":steps,"loads":loads,"unresolved":sorted(wanted)}


def analyze_candidate(md,pe,con,fn,op_mem,op_reg,restore_dist,go_reverse):
    meta=function_for(con,fn)
    if not meta: return None
    insns=disasm_function(md,pe,meta["begin"],meta["end"])
    recs=[record(x,md,op_mem) for x in insns]
    callbacks=[]; class_fields=Counter(); parent_walk=False; asserted=False
    for r in recs:
        for m in r["mem"]:
            d=m["disp"]
            if 0 <= d <= 0x180: class_fields[d]+=1
            if d==0x48: parent_walk=True
            if d==0xA4: asserted=True
    for i,ins in enumerate(insns):
        t=indirect_call_target(ins,md,op_mem,op_reg)
        if not t: continue
        sl=backslice(recs,i,t)
        slot_candidates=[]
        if t["kind"]=="mem" and isinstance(t.get("disp"),int):
            slot_candidates.append({"disp":t["disp"],"source":"call_operand","base":t.get("base")})
        for ld in sl["loads"]:
            d=ld["mem"].get("disp")
            if isinstance(d,int) and 0x40 <= d <= 0x140:
                slot_candidates.append({"disp":d,"source":"backslice_load","base":ld["mem"].get("base"),"site":ld["instruction"]["rva"]})
        callbacks.append({"site":ins.address-IMAGE_BASE,"target":t,"slice":sl,"slot_candidates":slot_candidates})
    strings=[dict(site=r[0],text=r[1]) for r in con.execute(
        "SELECT site,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site",(fn,)
    )]
    interesting=[x for x in strings if any(t in x["text"].lower() for t in INTERESTING_TERMS)]
    score=0
    if parent_walk: score+=180
    if asserted: score+=180
    if 0xB8 in class_fields: score+=260
    score+=80*len(interesting)
    if fn in restore_dist: score+=max(0,180-20*restore_dist[fn])
    if fn in go_reverse: score+=max(0,180-20*go_reverse[fn])
    for cb in callbacks:
        for s in cb["slot_candidates"]:
            d=s["disp"]
            if d in CALLBACK_WINDOW: score+=120
            if d==0xB8: score+=180
            if d in (0xB0,0xC0,0xC8,0xD0): score+=100
    return {"function":fn,"end":meta["end"],"size":meta["size"],"score":score,
            "parent_48":parent_walk,"asserted_A4":asserted,"field_counts":dict(class_fields),
            "interesting_strings":interesting,"restore_depth":restore_dist.get(fn),
            "to_gameobject_depth":go_reverse.get(fn),"callbacks":callbacks}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",required=True); ap.add_argument("--db",required=True)
    ap.add_argument("--output-json",required=True); ap.add_argument("--output-text",required=True)
    args=ap.parse_args()
    exe=Path(args.exe); db=Path(args.db)
    if not exe.is_file() or sha256(exe).lower()!=EXPECTED_SHA256:
        raise SystemExit("missing or unsupported GoW.exe")
    if not db.is_file(): raise SystemExit(f"missing reusable index: {db}")
    con=sqlite3.connect(db)
    out,rev=call_graph(con)
    restore_starts=[]; go_starts=[]
    for r in RESTORE_ROOTS:
        f=function_for(con,r); restore_starts.append(f["begin"] if f else r)
    for r in GAMEOBJECT_ROOTS:
        f=function_for(con,r); go_starts.append(f["begin"] if f else r)
    restore_dist=bfs(out,restore_starts,8)
    go_reverse=bfs(rev,go_starts,8)
    cands=candidate_functions(con)

    capstone,Cs,arch,mode,op_mem,op_reg=load_capstone()
    pe=load_pe_module().PE(exe.read_bytes())
    md=Cs(arch,mode); md.detail=True; md.skipdata=True
    analyses=[]
    for fn in cands:
        try:
            rec=analyze_candidate(md,pe,con,fn,op_mem,op_reg,restore_dist,go_reverse)
            if rec: analyses.append(rec)
        except Exception as e:
            analyses.append({"function":fn,"error":repr(e),"score":-1})
    analyses.sort(key=lambda x:(-x.get("score",-1),x["function"]))

    slot_hist=Counter(); strong=[]
    for a in analyses:
        for cb in a.get("callbacks",[]):
            for s in cb["slot_candidates"]:
                d=s.get("disp")
                if isinstance(d,int) and 0 <= d <= 0x200: slot_hist[d]+=1
        if a.get("parent_48") and (a.get("asserted_A4") or a.get("field_counts",{}).get(0xB8)):
            strong.append(a)

    result={"schema":1,"analysis":"codeside_lua_class_callback_slots","exe_sha256":EXPECTED_SHA256,
            "capstone_version":capstone.__version__,"candidate_count":len(cands),
            "ranked_candidates":analyses[:300],"strong_class_walkers":strong[:100],
            "callback_slot_histogram":[{"disp":d,"count":n} for d,n in slot_hist.most_common()],
            "game_launched":False,"save_opened":False,"exe_modified":False}
    con.close()
    Path(args.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

    lines=["Completionist Map - CodeSideLuaClass callback-slot map",
           f"exe_sha256={EXPECTED_SHA256}",f"capstone={capstone.__version__}",
           f"candidate_functions={len(cands)}",f"strong_class_walkers={len(strong)}","",
           "CALLBACK SLOT HISTOGRAM"]
    for d,n in slot_hist.most_common(80): lines.append(f"- disp={d:+#x} count={n}")
    lines += ["","TOP CANDIDATES"]
    for i,a in enumerate(analyses[:80],1):
        lines.append(f"#{i} fn=0x{a['function']:X} score={a.get('score')} parent48={a.get('parent_48')} A4={a.get('asserted_A4')} restore_depth={a.get('restore_depth')} go_depth={a.get('to_gameobject_depth')}")
        for s in a.get("interesting_strings",[])[:8]: lines.append(f"    STRING 0x{s['site']:X} {s['text']!r}")
        for cb in a.get("callbacks",[])[:12]:
            lines.append(f"    INDIRECT 0x{cb['site']:X} target={cb['target']} slots={cb['slot_candidates']}")
            for ld in cb['slice']['loads'][:8]:
                ins=ld['instruction']; lines.append(f"      LOAD 0x{ins['rva']:X} {ins['mnemonic']} {ins['op_str']} mem={ld['mem']}")
    lines += ["","STRONG CLASS WALKERS"]
    for a in strong[:60]:
        lines.append(f"- fn=0x{a['function']:X} score={a['score']} fields={sorted((int(k),v) for k,v in a['field_counts'].items() if int(k) in set(CALLBACK_WINDOW)|KNOWN_CLASS_FIELDS)}")
        for cb in a.get('callbacks',[])[:10]: lines.append(f"    INDIRECT 0x{cb['site']:X} slots={cb['slot_candidates']}")
    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("CODESIDE_LUA_CLASS_CALLBACK_SLOT_MAP_PASSED")
    print(f"candidate_functions={len(cands)}")
    print(f"strong_class_walkers={len(strong)}")
    for d,n in slot_hist.most_common(12): print(f"slot_{d:+#x}={n}")

if __name__=="__main__": main()
