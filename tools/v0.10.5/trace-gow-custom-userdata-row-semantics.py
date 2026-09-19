#!/usr/bin/env python3
"""Targeted static trace of GoW custom-userdata row/metadata restore semantics.

The outer carrier framing is already solved. This pass disassembles only the
remaining restore-side structures needed to connect serialized Lua table state:
- the six-byte row loop in 0x7E9550;
- the descriptor consumers at 0x7E7660 and 0x7E7920;
- the decoded-record dispatch at 0x7E7B60.

It is version-locked to the supported GoW.exe and performs no game launch,
process access, save access, or writes outside the requested report files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TARGETS = {
    "restore_row_loop": 0x7E97C7,
    "descriptor_consumer": 0x7E7660,
    "descriptor_helper": 0x7E7920,
    "record_dispatch": 0x7E7B60,
}
ROW_WINDOW = (0x7E97B0, 0x7E9868)
DESCRIPTOR_OFFSETS = {0x20, 0x28, 0x30, 0x38, 0x3A, 0x40, 0x50}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_helper():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_row_semantics_pe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_capstone(repo: Path):
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


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
    if name.startswith("r") and name[-1:] in ("d","w","b") and name[1:-1].isdigit():
        return name[:-1]
    return name


def instruction_row(md, ins, OP_IMM, OP_MEM, OP_REG, RIP):
    row = {
        "rva": ins.address - IMAGE_BASE,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }
    mem = []
    imm = []
    regs = []
    for idx, op in enumerate(getattr(ins, "operands", [])):
        if op.type == OP_MEM:
            item = {
                "operand": idx,
                "base": norm_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
                "index": norm_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
                "scale": op.mem.scale,
                "disp": op.mem.disp,
                "size": op.size,
            }
            if op.mem.base == RIP:
                item["rip_target_rva"] = ins.address + ins.size + op.mem.disp - IMAGE_BASE
            mem.append(item)
        elif op.type == OP_IMM:
            value = op.imm
            if IMAGE_BASE <= value < IMAGE_BASE + 0x3000000:
                value -= IMAGE_BASE
            imm.append({"operand": idx, "value": value})
        elif op.type == OP_REG:
            regs.append({"operand": idx, "reg": norm_reg(md.reg_name(op.reg))})
    if mem:
        row["mem"] = mem
    if imm:
        row["immediates"] = imm
    if regs:
        row["register_operands"] = regs
    try:
        rd, wr = ins.regs_access()
        row["registers_read"] = [norm_reg(md.reg_name(x)) for x in rd]
        row["registers_written"] = [norm_reg(md.reg_name(x)) for x in wr]
    except Exception:
        pass
    return row


def disassemble_function(pe, md, target, OP_IMM, OP_MEM, OP_REG, RIP):
    fn = pe.function_for(target)
    if fn is None:
        raise RuntimeError(f"no runtime function contains RVA 0x{target:X}")
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        raise RuntimeError(f"function 0x{fn['begin']:X} is not file-backed")
    raw = pe.data[off:off + fn["end"] - fn["begin"]]
    rows = [
        instruction_row(md, ins, OP_IMM, OP_MEM, OP_REG, RIP)
        for ins in md.disasm(raw, IMAGE_BASE + fn["begin"])
    ]
    return {"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"], "instructions": rows}


def fmt(row):
    return f"0x{row['rva']:08X}  {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.exe.expanduser().resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")
    digest = sha256_file(exe)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA256 mismatch: {digest}")

    repo = Path(__file__).resolve().parents[2]
    helper = load_pe_helper()
    pe = helper.PE(exe.read_bytes())
    Cs, ARCH, MODE, OP_IMM, OP_MEM, OP_REG, RIP = load_capstone(repo)
    md = Cs(ARCH, MODE)
    md.detail = True

    functions = {}
    for label, target in TARGETS.items():
        functions[label] = disassemble_function(pe, md, target, OP_IMM, OP_MEM, OP_REG, RIP)

    root_rows = functions["restore_row_loop"]["instructions"]
    row_window = [r for r in root_rows if ROW_WINDOW[0] <= r["rva"] < ROW_WINDOW[1]]
    rsi_reads = []
    six_byte_reads = []
    for row in row_window:
        for mem in row.get("mem", []):
            if mem.get("base") == "rsi":
                rsi_reads.append({"instruction": row, "memory": mem})
                if 0 <= mem.get("disp", -999) <= 5:
                    six_byte_reads.append({"instruction": row, "memory": mem})

    descriptor_accesses = []
    for label in ("descriptor_consumer", "descriptor_helper", "record_dispatch"):
        for row in functions[label]["instructions"]:
            for mem in row.get("mem", []):
                if mem.get("disp") in DESCRIPTOR_OFFSETS:
                    descriptor_accesses.append({
                        "function": label,
                        "instruction": row,
                        "memory": mem,
                    })

    # Calls/jumps inside the focused functions are useful for following row-built
    # descriptor entries into the record dispatch.
    control_edges = []
    for label, fn in functions.items():
        for row in fn["instructions"]:
            if row["mnemonic"] not in ("call", "jmp"):
                continue
            vals = row.get("immediates", [])
            if vals:
                control_edges.append({
                    "function": label,
                    "site": row["rva"],
                    "kind": row["mnemonic"],
                    "target": vals[0]["value"],
                })

    report = {
        "schema": 1,
        "analysis": "gow_custom_userdata_row_semantics",
        "exe_sha256": digest,
        "targets": TARGETS,
        "row_window": {
            "start": ROW_WINDOW[0],
            "end": ROW_WINDOW[1],
            "instructions": row_window,
            "rsi_memory_accesses": rsi_reads,
            "six_byte_row_candidate_reads": six_byte_reads,
        },
        "functions": functions,
        "descriptor_offset_accesses": descriptor_accesses,
        "control_edges": control_edges,
        "safety": {
            "static_exe_read_only": True,
            "game_launched": False,
            "process_accessed": False,
            "save_opened": False,
            "save_written": False,
            "progression_written": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - custom-userdata row semantics trace",
        f"exe_sha256={digest}",
        "",
        "RESTORE ROW WINDOW",
    ]
    lines.extend(fmt(row) for row in row_window)
    lines.extend(["", "RSI MEMORY ACCESSES IN ROW WINDOW"])
    for item in rsi_reads:
        m = item["memory"]
        lines.append(f"{fmt(item['instruction'])}  ; [rsi{m['disp']:+#x}] size={m['size']}")
    lines.extend(["", "CANDIDATE READS OF SIX-BYTE ROW OFFSETS 0..5"])
    for item in six_byte_reads:
        m = item["memory"]
        lines.append(f"{fmt(item['instruction'])}  ; row+0x{m['disp']:X} size={m['size']}")

    for label in ("descriptor_consumer", "descriptor_helper", "record_dispatch"):
        fn = functions[label]
        lines.extend([
            "",
            f"FUNCTION {label} 0x{fn['begin']:X}..0x{fn['end']:X}",
        ])
        lines.extend(fmt(row) for row in fn["instructions"])

    lines.extend(["", "DESCRIPTOR OFFSET ACCESSES"])
    for item in descriptor_accesses:
        m = item["memory"]
        lines.append(f"{item['function']}: {fmt(item['instruction'])} ; disp={m['disp']:+#x} size={m['size']}")

    lines.extend([
        "",
        "SAFETY static_exe_read_only=true game_launched=false process_accessed=false "
        "save_opened=false save_written=false progression_written=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "GOW_CUSTOM_USERDATA_ROW_SEMANTICS_TRACE_COMPLETE "
        f"rowInstructions={len(row_window)} rsiAccesses={len(rsi_reads)} "
        f"rowCandidateReads={len(six_byte_reads)} descriptorAccesses={len(descriptor_accesses)}"
    )
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
