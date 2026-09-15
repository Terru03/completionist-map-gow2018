"""Trace Lua userdata reconstruction branches in the native checkpoint codec.

Version-locked, read-only targeted disassembly of the already-proven codec band
0x7E7000-0x7EA600.  This pass does not guess callback offsets.  It finds:

* GC object type writes (especially type 5/table and type 7/userdata);
* TValue tag writes (especially 0x45/table and 0x47/userdata);
* low-nibble type tests (and reg,0xF / cmp ...,7);
* allocator calls and direct/indirect calls surrounding each type site;
* full local instruction windows for all userdata candidates.

No game launch, save I/O, or executable modification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
RANGE_LO = 0x7E7000
RANGE_HI = 0x7EA600
RESTORE_ROOT = 0x7E9550


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
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


def safe_ops(ins):
    try:
        return list(ins.operands)
    except Exception:
        return []


def disasm_fn(md, pe, fn):
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        return []
    blob = pe.data[off:off + fn["end"] - fn["begin"]]
    return list(md.disasm(blob, IMAGE_BASE + fn["begin"]))


def runtime_functions(pe):
    return [f for f in pe.runtime_functions if f["begin"] < RANGE_HI and f["end"] > RANGE_LO]


def rec(ins):
    return {
        "rva": ins.address - IMAGE_BASE,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }


def immediate_values(ins, op_imm):
    return [op.imm for op in safe_ops(ins) if op.type == op_imm]


def mem_immediate_write(ins, md, op_mem, op_imm):
    ops = safe_ops(ins)
    if ins.mnemonic != "mov" or len(ops) < 2:
        return None
    dst, src = ops[0], ops[1]
    if dst.type != op_mem or src.type != op_imm:
        return None
    base = md.reg_name(dst.mem.base) if dst.mem.base else None
    index = md.reg_name(dst.mem.index) if dst.mem.index else None
    return {
        "base": base,
        "index": index,
        "scale": dst.mem.scale,
        "disp": dst.mem.disp,
        "imm": src.imm,
        "size": dst.size,
    }


def direct_call(ins, op_imm):
    if ins.mnemonic not in ("call", "jmp"):
        return None
    ops = safe_ops(ins)
    if not ops or ops[0].type != op_imm:
        return None
    val = ops[0].imm
    if IMAGE_BASE <= val < IMAGE_BASE + 0x2000000:
        return val - IMAGE_BASE
    return None


def indirect_call(ins, md, op_mem, op_reg):
    if ins.mnemonic != "call":
        return None
    ops = safe_ops(ins)
    if not ops:
        return None
    op = ops[0]
    if op.type == op_reg:
        return {"kind": "reg", "reg": md.reg_name(op.reg)}
    if op.type == op_mem:
        return {
            "kind": "mem",
            "base": md.reg_name(op.mem.base) if op.mem.base else None,
            "index": md.reg_name(op.mem.index) if op.mem.index else None,
            "scale": op.mem.scale,
            "disp": op.mem.disp,
        }
    return None


def window(records, idx, before=28, after=36):
    lo = max(0, idx - before)
    hi = min(len(records), idx + after + 1)
    return records[lo:hi]


def classify_type_write(w):
    imm = w["imm"] & 0xFFFFFFFFFFFFFFFF
    disp = w["disp"]
    size = w["size"]
    labels = []
    # Lua 5.x GC object tt byte is commonly at +8 in this build.
    if disp == 8 and size == 1:
        if imm == 5: labels.append("gc_table_type_5")
        if imm == 7: labels.append("gc_userdata_type_7")
        if 0 <= imm <= 15: labels.append(f"gc_type_{imm}")
    # TValue tt_ is a 32-bit field at +8 in this build; collectable bit is 0x40.
    if disp == 8 and size == 4:
        if imm == 0x45: labels.append("tvalue_table_0x45")
        if imm == 0x47: labels.append("tvalue_userdata_0x47")
        if imm in range(0x40, 0x50): labels.append(f"tvalue_collectable_0x{imm:X}")
    return labels


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
    pe = load_pe_module().PE(exe.read_bytes())
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    functions = runtime_functions(pe)
    all_sites = []
    tag_tests = []
    skipdata = 0
    decoded = {}

    for fn in functions:
        insns = disasm_fn(md, pe, fn)
        records = [rec(i) for i in insns]
        decoded[fn["begin"]] = (fn, insns, records)
        for idx, ins in enumerate(insns):
            if ins.mnemonic == ".byte":
                skipdata += 1
                continue
            w = mem_immediate_write(ins, md, op_mem, op_imm)
            if w:
                labels = classify_type_write(w)
                if labels:
                    calls = []
                    indirects = []
                    for j in range(max(0, idx - 20), min(len(insns), idx + 40)):
                        d = direct_call(insns[j], op_imm)
                        if d is not None:
                            calls.append({"site": insns[j].address - IMAGE_BASE, "dest": d, "mnemonic": insns[j].mnemonic})
                        ind = indirect_call(insns[j], md, op_mem, op_reg)
                        if ind:
                            indirects.append({"site": insns[j].address - IMAGE_BASE, "target": ind})
                    all_sites.append({
                        "function": fn["begin"],
                        "site": ins.address - IMAGE_BASE,
                        "write": w,
                        "labels": labels,
                        "window": window(records, idx),
                        "nearby_direct_calls": calls,
                        "nearby_indirect_calls": indirects,
                    })

            # Find explicit low-nibble/type-7 tests even when not part of a write.
            ops = safe_ops(ins)
            imms = immediate_values(ins, op_imm)
            low = ins.op_str.lower()
            if (ins.mnemonic in ("and", "cmp", "test") and
                (7 in imms or 0xF in imms or 0x47 in imms or "0xf" in low or ", 7" in low)):
                tag_tests.append({
                    "function": fn["begin"],
                    "site": ins.address - IMAGE_BASE,
                    "instruction": rec(ins),
                    "window": window(records, idx, 16, 22),
                })

    userdata_sites = [s for s in all_sites if any("userdata" in x for x in s["labels"])]
    table_sites = [s for s in all_sites if any("table" in x for x in s["labels"])]

    result = {
        "schema": 1,
        "analysis": "gow_decoder_userdata_branch",
        "exe_sha256": EXPECTED_SHA256,
        "range": {"begin": RANGE_LO, "end": RANGE_HI},
        "capstone_version": capstone.__version__,
        "function_count": len(functions),
        "skipdata_records": skipdata,
        "type_write_sites": all_sites,
        "userdata_sites": userdata_sites,
        "table_sites": table_sites,
        "tag_tests": tag_tests,
        "restore_root": RESTORE_ROOT,
        "game_launched": False,
        "save_opened": False,
        "exe_modified": False,
    }
    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - decoder userdata/type branch trace",
        f"exe_sha256={EXPECTED_SHA256}",
        f"range=0x{RANGE_LO:X}-0x{RANGE_HI:X}",
        f"capstone={capstone.__version__}",
        f"functions={len(functions)}",
        f"skipdata_records={skipdata}",
        f"type_write_sites={len(all_sites)}",
        f"table_sites={len(table_sites)}",
        f"userdata_sites={len(userdata_sites)}",
        f"tag_tests={len(tag_tests)}",
        "",
        "TYPE WRITE SUMMARY",
    ]
    for s in all_sites:
        w = s["write"]
        lines.append(
            f"- fn=0x{s['function']:X} site=0x{s['site']:X} labels={s['labels']} "
            f"base={w['base']} disp=0x{w['disp']:X} size={w['size']} imm=0x{w['imm'] & 0xFFFFFFFFFFFFFFFF:X}"
        )

    lines += ["", "USERDATA CANDIDATE WINDOWS"]
    if not userdata_sites:
        lines.append("- NONE")
    for n, s in enumerate(userdata_sites, 1):
        lines.append(f"=== USERDATA #{n} fn=0x{s['function']:X} site=0x{s['site']:X} labels={s['labels']} ===")
        for r in s["window"]:
            lines.append(f"0x{r['rva']:08X}  {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")
        for c in s["nearby_direct_calls"]:
            lines.append(f"    DIRECT {c['mnemonic']} 0x{c['site']:X} -> 0x{c['dest']:X}")
        for c in s["nearby_indirect_calls"]:
            lines.append(f"    INDIRECT 0x{c['site']:X} target={c['target']}")

    lines += ["", "TABLE CANDIDATE WINDOWS"]
    for n, s in enumerate(table_sites[:12], 1):
        lines.append(f"=== TABLE #{n} fn=0x{s['function']:X} site=0x{s['site']:X} labels={s['labels']} ===")
        for r in s["window"]:
            lines.append(f"0x{r['rva']:08X}  {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")

    lines += ["", "TYPE/TAG TEST WINDOWS"]
    for n, s in enumerate(tag_tests, 1):
        i = s["instruction"]
        lines.append(f"=== TEST #{n} fn=0x{s['function']:X} site=0x{s['site']:X}: {i['mnemonic']} {i['op_str']} ===")
        for r in s["window"]:
            lines.append(f"0x{r['rva']:08X}  {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}")

    Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GOW_DECODER_USERDATA_BRANCH_PASSED")
    print(f"functions={len(functions)}")
    print(f"type_write_sites={len(all_sites)}")
    print(f"table_sites={len(table_sites)}")
    print(f"userdata_sites={len(userdata_sites)}")
    print(f"tag_tests={len(tag_tests)}")
    print(f"skipdata_records={skipdata}")


if __name__ == "__main__":
    main()
