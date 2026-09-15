"""Trace the inverse handler for native custom-userdata checkpoint records.

The save-side native userdata serializer is already proven to emit records as:

    [8-byte CodeSideLuaClass key][class +0xB8 callback payload]

and to store a per-record byte equal to payload_length + 8.  This pass starts
at the proven restore decoder (0x7E9550), follows its direct-call graph using
the reusable SQLite index, and targeted-disassembles only those reachable
functions.  It looks for the inverse shape instead of guessing callback slots:

* byte-sized record metadata loads;
* arithmetic/comparisons involving the fixed 8-byte class-key header;
* qword reads from record pointers;
* indirect reconstruction dispatch;
* CodeSideLuaClass fields +0x48/+0xA4/+0xB8 and neighboring slots;
* semantic strings and GameObject resolver/unbox/token-packer reachability.

Read-only: no game launch, save I/O, or executable modification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
RESTORE_ROOT = 0x7E9550
SERIALIZER = 0x7E9190
GAMEOBJECT_TARGETS = {0x4EF0B0, 0x5F9350, 0x60B9C0}
CLASS_FIELDS = {0x48, 0xA4, 0xB8, 0xC0, 0xC8, 0xD0, 0xD8, 0xE0}
TERMS = (
    "codesideluaclass", "gameobject", "pickle", "unpickle", "restore",
    "serialize", "deserialize", "userdata", "classref", "tableref",
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
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


def norm_reg(name: str | None) -> str | None:
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


def safe_ops(ins):
    try:
        return list(ins.operands)
    except Exception:
        return []


def safe_regs(ins, md):
    try:
        rr, rw = ins.regs_access()
        return ([norm_reg(md.reg_name(x)) for x in rr], [norm_reg(md.reg_name(x)) for x in rw])
    except Exception:
        return ([], [])


def function_for(con, rva):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    return None if row is None else {"begin":row[0],"end":row[1],"size":row[2],"section":row[3]}


def build_graph(con):
    out = defaultdict(set)
    for src, dst in con.execute("SELECT src_fn,target_fn FROM edges WHERE kind='call' AND target_fn IS NOT NULL"):
        if src is not None and dst is not None:
            out[src].add(dst)
    return out


def reachable(graph, start, max_depth=4, max_nodes=700):
    dist = {start: 0}
    q = deque([start])
    while q and len(dist) < max_nodes:
        cur = q.popleft()
        d = dist[cur]
        if d >= max_depth:
            continue
        for nxt in graph.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
                if len(dist) >= max_nodes:
                    break
    return dist


def disasm(md, pe, fn):
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        return []
    blob = pe.data[off:off + fn["end"] - fn["begin"]]
    return list(md.disasm(blob, IMAGE_BASE + fn["begin"]))


def rec(ins):
    return {"rva":ins.address-IMAGE_BASE,"bytes":ins.bytes.hex(),"mnemonic":ins.mnemonic,"op_str":ins.op_str}


def direct_target(ins, op_imm):
    if ins.mnemonic not in ("call", "jmp"):
        return None
    ops = safe_ops(ins)
    if not ops or ops[0].type != op_imm:
        return None
    v = ops[0].imm
    if IMAGE_BASE <= v < IMAGE_BASE + 0x2000000:
        return v - IMAGE_BASE
    return None


def indirect_target(ins, md, op_mem, op_reg):
    if ins.mnemonic != "call":
        return None
    ops = safe_ops(ins)
    if not ops:
        return None
    op = ops[0]
    if op.type == op_reg:
        return {"kind":"reg","reg":norm_reg(md.reg_name(op.reg))}
    if op.type == op_mem:
        return {"kind":"mem","base":norm_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
                "index":norm_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
                "scale":op.mem.scale,"disp":op.mem.disp}
    return None


def operand_features(ins, md, op_imm, op_mem):
    rr, rw = safe_regs(ins, md)
    imms=[]; mem=[]
    for oi, op in enumerate(safe_ops(ins)):
        if op.type == op_imm:
            imms.append(op.imm)
        elif op.type == op_mem:
            mem.append({"operand":oi,
                        "base":norm_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
                        "index":norm_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
                        "scale":op.mem.scale,"disp":op.mem.disp,"size":op.size})
    return rr, rw, imms, mem


def relevant_strings(con, fn):
    rows=[]
    for site, text in con.execute(
        "SELECT site,target_string FROM rip_refs WHERE src_fn=? AND target_string IS NOT NULL ORDER BY site", (fn,)
    ):
        low=text.lower()
        if any(t in low for t in TERMS):
            rows.append({"site":site,"text":text})
    return rows


def analyze_function(md, pe, con, fn, depth, op_imm, op_mem, op_reg):
    meta=function_for(con,fn)
    if not meta:
        return None
    insns=disasm(md,pe,meta)
    rows=[]; byte_loads=[]; imm8=[]; qword_zero=[]; indirects=[]; class_fields=[]; direct=[]
    for idx, ins in enumerate(insns):
        if ins.mnemonic == ".byte":
            continue
        rr,rw,imms,mem=operand_features(ins,md,op_imm,op_mem)
        row=rec(ins); row.update({"reads":rr,"writes":rw,"imms":imms,"mem":mem})
        rows.append(row)
        # Byte metadata read.
        if ins.mnemonic in ("movzx","mov"):
            for m in mem:
                if m["size"] == 1:
                    byte_loads.append({"index":idx,"instruction":row,"mem":m})
        # Fixed class-key header arithmetic / comparison.
        if 8 in imms and ins.mnemonic in ("add","sub","cmp","lea","and","or"):
            imm8.append({"index":idx,"instruction":row})
        # Candidate first qword of record.
        if ins.mnemonic in ("mov","movzx"):
            for m in mem:
                if m["size"] == 8 and m["disp"] == 0 and m.get("base") not in (None,"rsp","rbp","rip"):
                    qword_zero.append({"index":idx,"instruction":row,"mem":m})
        for m in mem:
            if m["disp"] in CLASS_FIELDS:
                class_fields.append({"index":idx,"instruction":row,"mem":m})
        dt=direct_target(ins,op_imm)
        if dt is not None:
            direct.append({"site":ins.address-IMAGE_BASE,"dest":dt,"mnemonic":ins.mnemonic})
        it=indirect_target(ins,md,op_mem,op_reg)
        if it:
            indirects.append({"index":idx,"site":ins.address-IMAGE_BASE,"target":it,"instruction":row})

    # Correlate a byte load with +8 arithmetic and subsequent qword-key / dispatch within a local window.
    chains=[]
    for b in byte_loads:
        bi=b["index"]
        near8=[x for x in imm8 if bi-8 <= x["index"] <= bi+24]
        if not near8:
            continue
        nearq=[x for x in qword_zero if bi-8 <= x["index"] <= bi+50]
        neari=[x for x in indirects if bi-8 <= x["index"] <= bi+70]
        lo=max(0,bi-12); hi=min(len(insns),bi+75)
        chains.append({"byte_load":b,"imm8":near8,"qword_reads":nearq,"indirect_calls":neari,
                       "window":[rec(x) for x in insns[lo:hi]]})

    strings=relevant_strings(con,fn)
    score=0
    score += len(chains)*500
    score += min(len(byte_loads),10)*15
    score += min(len(imm8),10)*35
    score += min(len(qword_zero),10)*20
    score += min(len(indirects),8)*45
    score += len(class_fields)*70
    score += len(strings)*120
    if fn == function_for(con,RESTORE_ROOT)["begin"]: score += 500
    if any(c["dest"] in GAMEOBJECT_TARGETS for c in direct): score += 500
    if any(x["mem"]["disp"] == 0xB8 for x in class_fields): score += 250
    return {"function":fn,"end":meta["end"],"size":meta["size"],"depth":depth,"score":score,
            "byte_loads":byte_loads,"imm8_ops":imm8,"qword_zero_reads":qword_zero,
            "class_fields":class_fields,"indirect_calls":indirects,"direct_calls":direct,
            "interesting_strings":strings,"custom_record_chains":chains}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",required=True); ap.add_argument("--db",required=True)
    ap.add_argument("--output-json",required=True); ap.add_argument("--output-text",required=True)
    args=ap.parse_args()
    exe=Path(args.exe); db=Path(args.db)
    if not exe.is_file() or sha256(exe).lower()!=EXPECTED_SHA256:
        raise SystemExit("missing or unsupported GoW.exe")
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")

    con=sqlite3.connect(db)
    root_meta=function_for(con,RESTORE_ROOT)
    if not root_meta:
        raise SystemExit("restore root not present in reusable index")
    graph=build_graph(con)
    dist=reachable(graph,root_meta["begin"],4,700)

    capstone,Cs,arch,mode,op_imm,op_mem,op_reg,rip_reg=load_capstone()
    pe=load_pe_module().PE(exe.read_bytes())
    md=Cs(arch,mode); md.detail=True; md.skipdata=True

    analyses=[]
    for fn,depth in sorted(dist.items(),key=lambda x:(x[1],x[0])):
        try:
            a=analyze_function(md,pe,con,fn,depth,op_imm,op_mem,op_reg)
            if a is not None:
                analyses.append(a)
        except Exception as e:
            analyses.append({"function":fn,"depth":depth,"score":-1,"error":repr(e)})
    analyses.sort(key=lambda x:(-x.get("score",-1),x.get("depth",99),x["function"]))

    result={"schema":1,"analysis":"gow_custom_userdata_record_inverse","exe_sha256":EXPECTED_SHA256,
            "restore_root":RESTORE_ROOT,"reachable_functions":len(dist),"max_depth":4,
            "ranked_functions":analyses[:250],"capstone_version":capstone.__version__,
            "game_launched":False,"save_opened":False,"exe_modified":False}
    con.close()
    Path(args.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

    lines=["Completionist Map - custom userdata record inverse trace",
           f"exe_sha256={EXPECTED_SHA256}",f"restore_root=0x{RESTORE_ROOT:X}",
           f"reachable_functions={len(dist)}",f"capstone={capstone.__version__}","",
           "PROVEN SAVE RECORD SHAPE",
           "class_key=qword[class_metadata+0]",
           "payload=class_metadata+0xB8 callback output",
           "record_size_byte=payload_length+8","",
           "RANKED RESTORE-SIDE CANDIDATES"]
    for n,a in enumerate(analyses[:80],1):
        lines.append(f"#{n} fn=0x{a['function']:X} depth={a.get('depth')} score={a.get('score')} chains={len(a.get('custom_record_chains',[]))} byte_loads={len(a.get('byte_loads',[]))} imm8={len(a.get('imm8_ops',[]))} qword0={len(a.get('qword_zero_reads',[]))} indirect={len(a.get('indirect_calls',[]))}")
        for s in a.get("interesting_strings",[]):
            lines.append(f"    STRING 0x{s['site']:X} {s['text']!r}")
        for f in a.get("class_fields",[]):
            lines.append(f"    CLASS_FIELD 0x{f['instruction']['rva']:X} disp=0x{f['mem']['disp']:X} {f['instruction']['mnemonic']} {f['instruction']['op_str']}")
        for c in a.get("custom_record_chains",[]):
            b=c["byte_load"]["instruction"]
            lines.append(f"    CUSTOM_CHAIN byte=0x{b['rva']:X} {b['mnemonic']} {b['op_str']}")
            for x in c["imm8"]:
                i=x["instruction"]; lines.append(f"      HEADER8 0x{i['rva']:X} {i['mnemonic']} {i['op_str']}")
            for x in c["qword_reads"][:8]:
                i=x["instruction"]; lines.append(f"      QWORD0 0x{i['rva']:X} {i['mnemonic']} {i['op_str']}")
            for x in c["indirect_calls"][:8]:
                lines.append(f"      INDIRECT 0x{x['site']:X} target={x['target']}")
            lines.append("      WINDOW")
            for i in c["window"]:
                lines.append(f"        0x{i['rva']:08X} {i['bytes']:<20} {i['mnemonic']:<8} {i['op_str']}")

    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    chain_count=sum(len(a.get("custom_record_chains",[])) for a in analyses)
    print("GOW_CUSTOM_USERDATA_RECORD_INVERSE_PASSED")
    print(f"reachable_functions={len(dist)}")
    print(f"custom_record_chains={chain_count}")
    for a in analyses[:8]:
        print(f"candidate=0x{a['function']:X} depth={a.get('depth')} score={a.get('score')} chains={len(a.get('custom_record_chains',[]))}")

if __name__ == "__main__":
    main()
