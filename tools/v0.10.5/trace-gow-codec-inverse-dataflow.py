"""Trace the native Lua checkpoint codec inverse dataflow in one broad pass.

Version-locked, read-only static analysis of the supported GoW.exe.  This pass
covers the whole native codec band 0x7E7000-0x7EA600, not one tiny probe.  It
uses real Capstone instruction boundaries and recovers:

* full function listings for the classref/tableref/restore functions;
* every indirect call in the codec band;
* backward slices for the register used as the indirect call target;
* memory displacements involved in callback/class metadata access;
* RIP-relative string references and direct-call targets;
* likely callback-slot loads (e.g. mov reg,[class+offset] -> call reg).

No game launch, save I/O, or executable modification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
RANGE_LO = 0x7E7000
RANGE_HI = 0x7EA600
FOCUS = {
    "tableref_classref_dispatch": 0x7E7B60,
    "tableref_to_table": 0x7E7660,
    "tableref_to_classname": 0x7E7920,
    "classref_reader": 0x7E9026,
    "userdata_serializer": 0x7E9190,
    "userdata_serializer_helper": 0x7E9340,
    "restore_pre_helper": 0x7E9550,
    "byte_serializer": 0x7E7F10,
}
INTERESTING_STRINGS = (
    "classref", "tableref", "codesideluaclass", "GameObject", "pickle",
    "unpickle", "serialize", "userdata", "classname", "root",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
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
    from capstone.x86_const import (
        X86_OP_IMM, X86_OP_MEM, X86_OP_REG,
        X86_REG_RIP,
    )
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


def ascii_strings(pe):
    out = {}
    data = pe.data
    for s in pe.sections:
        start = s["raw"]
        end = min(len(data), start + s["rawsize"])
        i = start
        while i < end:
            if 0x20 <= data[i] <= 0x7E:
                j = i
                while j < end and 0x20 <= data[j] <= 0x7E:
                    j += 1
                if j - i >= 4 and j < end and data[j] == 0:
                    rva = pe.file_to_rva(i)
                    if rva is not None:
                        out[rva] = data[i:j].decode("ascii", "replace")
                i = max(i + 1, j + 1)
            else:
                i += 1
    return out


def runtime_functions(pe):
    return [f for f in pe.runtime_functions if f["begin"] < RANGE_HI and f["end"] > RANGE_LO]


def disasm_fn(md, pe, fn):
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        return []
    blob = pe.data[off: off + fn["end"] - fn["begin"]]
    return list(md.disasm(blob, IMAGE_BASE + fn["begin"]))


def reg_name(md, rid):
    return md.reg_name(rid) if rid else None


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


def ins_record(md, ins, strings, op_imm, op_mem, op_reg, rip_reg):
    rec = {
        "rva": ins.address - IMAGE_BASE,
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
        "bytes": ins.bytes.hex(),
    }
    refs = []
    mems = []
    for idx, op in enumerate(ins.operands):
        if op.type == op_imm:
            val = op.imm
            if IMAGE_BASE <= val < IMAGE_BASE + 0x2000000:
                rva = val - IMAGE_BASE
                refs.append({"kind":"imm","operand":idx,"target_rva":rva,"string":strings.get(rva)})
        elif op.type == op_mem:
            base = reg_name(md, op.mem.base)
            index = reg_name(md, op.mem.index)
            mem = {"operand":idx,"base":normalize_reg(base),"index":normalize_reg(index),"scale":op.mem.scale,"disp":op.mem.disp}
            if op.mem.base == rip_reg:
                target = ins.address + ins.size + op.mem.disp
                rva = target - IMAGE_BASE
                mem["rip_target_rva"] = rva
                mem["string"] = strings.get(rva)
                refs.append({"kind":"rip","operand":idx,"target_rva":rva,"string":strings.get(rva)})
            mems.append(mem)
    if refs:
        rec["refs"] = refs
    if mems:
        rec["mem"] = mems
    try:
        rr, rw = ins.regs_access()
        rec["regs_read"] = [normalize_reg(reg_name(md, x)) for x in rr]
        rec["regs_write"] = [normalize_reg(reg_name(md, x)) for x in rw]
    except Exception:
        pass
    return rec


def direct_dest(ins, op_imm):
    if ins.mnemonic not in ("call", "jmp") or not ins.operands:
        return None
    op = ins.operands[0]
    if op.type != op_imm:
        return None
    val = op.imm
    if IMAGE_BASE <= val < IMAGE_BASE + 0x2000000:
        return val - IMAGE_BASE
    return None


def indirect_target(ins, md, op_mem, op_reg):
    if ins.mnemonic != "call" or not ins.operands:
        return None
    op = ins.operands[0]
    if op.type == op_reg:
        return {"kind":"reg","reg":normalize_reg(reg_name(md, op.reg))}
    if op.type == op_mem:
        return {
            "kind":"mem",
            "base":normalize_reg(reg_name(md, op.mem.base)),
            "index":normalize_reg(reg_name(md, op.mem.index)),
            "scale":op.mem.scale,
            "disp":op.mem.disp,
        }
    return None


def backward_slice(records, call_index, target, limit=80):
    """Lightweight register provenance slice for an indirect call target."""
    wanted = set()
    if target["kind"] == "reg" and target.get("reg"):
        wanted.add(target["reg"])
    elif target["kind"] == "mem":
        for k in ("base","index"):
            if target.get(k): wanted.add(target[k])
    steps = []
    callback_loads = []
    for i in range(call_index - 1, max(-1, call_index - limit - 1), -1):
        r = records[i]
        writes = set(r.get("regs_write", []))
        reads = set(r.get("regs_read", []))
        if not (writes & wanted) and not (reads & wanted):
            continue
        steps.append(r)
        hit_writes = writes & wanted
        # Detect mov/lea targetReg,[base+disp] as likely callback/table load.
        if hit_writes and r["mnemonic"] in ("mov","lea") and r.get("mem"):
            for m in r["mem"]:
                if m.get("base") or "rip_target_rva" in m:
                    callback_loads.append({"instruction":r,"mem":m,"written_regs":sorted(hit_writes)})
        # Continue provenance through source regs of a write to wanted.
        if hit_writes:
            wanted -= hit_writes
            for x in reads:
                if x not in ("rsp","rip","eflags"):
                    wanted.add(x)
        if not wanted:
            break
    steps.reverse()
    callback_loads.reverse()
    return {"steps":steps,"callback_loads":callback_loads,"unresolved_regs":sorted(wanted)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    exe = Path(args.exe)
    if not exe.is_file():
        raise SystemExit(f"missing exe: {exe}")
    if sha256(exe).lower() != EXPECTED_SHA256:
        raise SystemExit("unsupported GoW.exe SHA256")

    capstone, Cs, arch, mode, op_imm, op_mem, op_reg, rip_reg = load_capstone()
    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    strings = ascii_strings(pe)
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    funcs = runtime_functions(pe)
    decoded = {}
    indirects = []
    function_rows = []
    offset_hist = defaultdict(int)
    interesting_string_hits = []

    for fn in funcs:
        insns = disasm_fn(md, pe, fn)
        records = [ins_record(md, ins, strings, op_imm, op_mem, op_reg, rip_reg) for ins in insns]
        decoded[fn["begin"]] = (fn, insns, records)
        for r in records:
            for m in r.get("mem", []):
                d = m.get("disp")
                if isinstance(d, int) and 0 <= d <= 0x300:
                    offset_hist[d] += 1
            for ref in r.get("refs", []):
                s = ref.get("string") or ""
                if any(t.lower() in s.lower() for t in INTERESTING_STRINGS):
                    interesting_string_hits.append({"function":fn["begin"],"instruction":r,"string":s})
        for idx, ins in enumerate(insns):
            t = indirect_target(ins, md, op_mem, op_reg)
            if t:
                sl = backward_slice(records, idx, t, 100)
                indirects.append({
                    "function":fn["begin"],
                    "site":ins.address-IMAGE_BASE,
                    "target":t,
                    "slice":sl,
                })
        function_rows.append({"begin":fn["begin"],"end":fn["end"],"size":fn["end"]-fn["begin"],"instruction_count":len(insns)})

    focus = {}
    for name, rva in FOCUS.items():
        fn = pe.function_for(rva)
        if not fn:
            focus[name] = {"query_rva":rva,"function":None}
            continue
        tup = decoded.get(fn["begin"])
        if tup is None:
            insns = disasm_fn(md, pe, fn)
            records = [ins_record(md, ins, strings, op_imm, op_mem, op_reg, rip_reg) for ins in insns]
        else:
            _, insns, records = tup
        calls = []
        for ins in insns:
            d = direct_dest(ins, op_imm)
            if d is not None:
                calls.append({"site":ins.address-IMAGE_BASE,"mnemonic":ins.mnemonic,"dest":d})
        focus[name] = {
            "query_rva":rva,
            "function":{"begin":fn["begin"],"end":fn["end"]},
            "instructions":records,
            "direct_calls":calls,
            "indirect_calls":[x for x in indirects if x["function"]==fn["begin"]],
        }

    result = {
        "schema":1,
        "analysis":"gow_codec_inverse_dataflow",
        "exe_sha256":EXPECTED_SHA256,
        "range":{"begin":RANGE_LO,"end":RANGE_HI},
        "capstone_version":capstone.__version__,
        "function_count":len(function_rows),
        "functions":function_rows,
        "focus":focus,
        "indirect_calls":indirects,
        "memory_displacement_histogram":[{"disp":k,"count":v} for k,v in sorted(offset_hist.items(), key=lambda x:(-x[1],x[0]))],
        "interesting_string_hits":interesting_string_hits,
        "game_launched":False,
        "save_opened":False,
        "exe_modified":False,
    }
    Path(args.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

    lines = [
        "Completionist Map - broad codec inverse dataflow trace",
        f"exe_sha256={EXPECTED_SHA256}",
        f"range=0x{RANGE_LO:X}-0x{RANGE_HI:X}",
        f"capstone={capstone.__version__}",
        f"functions={len(function_rows)}",
        f"indirect_calls={len(indirects)}",
        "",
        "INDIRECT CALLS AND BACKWARD SLICES",
    ]
    for i,row in enumerate(indirects,1):
        lines.append(f"#{i} fn=0x{row['function']:X} site=0x{row['site']:X} target={row['target']}")
        for c in row["slice"]["callback_loads"]:
            ins=c["instruction"]; m=c["mem"]
            lines.append(f"    CALLBACK_LOAD 0x{ins['rva']:X} {ins['mnemonic']} {ins['op_str']} mem={m} writes={c['written_regs']}")
        for s in row["slice"]["steps"]:
            lines.append(f"    SLICE 0x{s['rva']:X} {s['mnemonic']} {s['op_str']}")
        if row["slice"]["unresolved_regs"]:
            lines.append(f"    UNRESOLVED {row['slice']['unresolved_regs']}")

    lines += ["", "FOCUS FUNCTION LISTINGS"]
    for name in FOCUS:
        rec=focus[name]
        lines.append(f"",)
        lines.append(f"=== {name} query=0x{rec['query_rva']:X} function={rec['function']} ===")
        for ins in rec.get("instructions",[]):
            extra=[]
            for ref in ins.get("refs",[]):
                if ref.get("string"):
                    extra.append(f"REF={ref['string']!r}")
            lines.append(f"0x{ins['rva']:08X}  {ins['bytes']:<24} {ins['mnemonic']:<8} {ins['op_str']} {' '.join(extra)}".rstrip())

    lines += ["", "TOP MEMORY DISPLACEMENTS (0..0x300)"]
    for row in result["memory_displacement_histogram"][:100]:
        lines.append(f"disp=0x{row['disp']:X} count={row['count']}")
    lines += ["", "INTERESTING STRING REFERENCES"]
    for hit in interesting_string_hits:
        r=hit["instruction"]
        lines.append(f"fn=0x{hit['function']:X} site=0x{r['rva']:X} string={hit['string']!r}")

    Path(args.output_text).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("GOW_CODEC_INVERSE_DATAFLOW_PASSED")
    print(f"functions={len(function_rows)}")
    print(f"indirect_calls={len(indirects)}")
    for name in ("tableref_classref_dispatch","classref_reader","restore_pre_helper"):
        rec=focus[name]
        print(f"{name}_indirect_calls={len(rec.get('indirect_calls',[]))}")

if __name__ == "__main__":
    main()
