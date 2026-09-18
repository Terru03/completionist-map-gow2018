#!/usr/bin/env python3
"""Trace the real contiguous CFG of the Raven/GameObject identity-vector method.

The GameObject save encoder calls vtable+0x38 at GoW.exe RVA 0x5495C9.  For the
three proven VikingFuneral Ravens that virtual method resolves to RVA 0x550700.
The PE unwind/PData row ends at 0x550750 even though reachable code branches
past that address, so this analysis intentionally follows machine-code control
flow directly instead of trusting the unwind-function end.

Read-only and version-locked.  No game launch, save I/O, debugger, process
memory access, or executable modification.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SEED_RVA = 0x550700
ENCODER_CALLSITE_RVA = 0x5495C9
MAX_SPAN = 0x5000
MAX_BLOCKS = 512
MAX_INSTRUCTIONS = 20000
CALLEE_CAP = 0x1800


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe():
    helper = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_identity_cfg_pe", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {helper}")
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
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def rva_blob(pe, rva: int, size: int) -> bytes:
    off = pe.rva_to_file(rva)
    return b"" if off is None else pe.data[off:off + size]


def ascii_at(pe, rva: int, cap: int = 200):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    raw = pe.data[off:off + cap]
    out = bytearray()
    for b in raw:
        if b == 0:
            break
        if not (0x20 <= b <= 0x7E):
            return None
        out.append(b)
    if len(out) < 4:
        return None
    return out.decode("ascii", "replace")


def one(md, pe, rva: int):
    blob = rva_blob(pe, rva, 16)
    if not blob:
        return None
    return next(iter(md.disasm(blob, IMAGE_BASE + rva, count=1)), None)


def direct_target(ins, op_imm):
    try:
        ops = list(ins.operands)
    except Exception:
        return None
    if not ops or ops[0].type != op_imm:
        return None
    va = int(ops[0].imm)
    return va - IMAGE_BASE if IMAGE_BASE <= va < IMAGE_BASE + 0x4000000 else None


def is_conditional(mn: str) -> bool:
    return mn.startswith("j") and mn not in ("jmp", "jmpq")


def record(md, pe, ins, op_imm, op_mem, rip_reg):
    rva = int(ins.address - IMAGE_BASE)
    row = {
        "rva": rva,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }
    mem = []
    rip_refs = []
    try:
        for idx, op in enumerate(ins.operands):
            if op.type != op_mem:
                continue
            base = md.reg_name(op.mem.base) if op.mem.base else None
            index = md.reg_name(op.mem.index) if op.mem.index else None
            m = {
                "operand": idx,
                "base": base,
                "index": index,
                "scale": int(op.mem.scale),
                "disp": int(op.mem.disp),
            }
            if op.mem.base == rip_reg:
                target = int(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
                m["rip_target_rva"] = target
                text = ascii_at(pe, target)
                if text is not None:
                    m["ascii"] = text
                rip_refs.append({
                    "site": rva,
                    "target_rva": target,
                    "ascii": text,
                    "instruction": f"{ins.mnemonic} {ins.op_str}",
                })
            mem.append(m)
    except Exception:
        pass
    if mem:
        row["memory"] = mem
    tgt = direct_target(ins, op_imm)
    if tgt is not None:
        row["direct_target"] = tgt
    try:
        rr, rw = ins.regs_access()
        row["regs_read"] = [md.reg_name(x) for x in rr]
        row["regs_write"] = [md.reg_name(x) for x in rw]
    except Exception:
        pass
    return row, rip_refs


def cfg(md, pe, op_imm, op_mem, rip_reg):
    pending = deque([SEED_RVA])
    queued = {SEED_RVA}
    decoded = {}
    blocks = []
    calls = []
    refs = []
    min_rva = SEED_RVA
    max_rva = SEED_RVA

    while pending and len(blocks) < MAX_BLOCKS and len(decoded) < MAX_INSTRUCTIONS:
        start = pending.popleft()
        cur = start
        rows = []
        succ = []
        reason = "limit"
        while len(decoded) < MAX_INSTRUCTIONS:
            if abs(cur - SEED_RVA) > MAX_SPAN:
                reason = "span_limit"
                break
            if cur in decoded and cur != start:
                succ.append(cur)
                reason = "joins_existing"
                break
            ins = one(md, pe, cur)
            if ins is None:
                reason = "decode_failure"
                break
            row, row_refs = record(md, pe, ins, op_imm, op_mem, rip_reg)
            decoded[cur] = row
            rows.append(row)
            refs.extend(row_refs)
            min_rva = min(min_rva, cur)
            max_rva = max(max_rva, cur + ins.size)
            target = direct_target(ins, op_imm)

            if ins.mnemonic == "call":
                calls.append({
                    "site": cur,
                    "target": target,
                    "op_str": ins.op_str,
                    "indirect": target is None,
                })
                cur += ins.size
                continue
            if ins.mnemonic in ("ret", "retf", "iret", "iretq"):
                reason = "return"
                break
            if ins.mnemonic in ("jmp", "jmpq"):
                if target is not None:
                    succ.append(target)
                    if target not in queued:
                        pending.append(target)
                        queued.add(target)
                    reason = "direct_jump"
                else:
                    reason = "indirect_jump"
                break
            if is_conditional(ins.mnemonic):
                fall = cur + ins.size
                succ.append(fall)
                if fall not in queued:
                    pending.append(fall)
                    queued.add(fall)
                if target is not None:
                    succ.append(target)
                    if target not in queued:
                        pending.append(target)
                        queued.add(target)
                reason = "conditional_jump"
                break
            cur += ins.size
        blocks.append({
            "start": start,
            "end": rows[-1]["rva"] + len(bytes.fromhex(rows[-1]["bytes"])) if rows else start,
            "reason": reason,
            "successors": sorted(set(succ)),
            "instructions": rows,
        })

    uniq_refs = []
    seen = set()
    for r in refs:
        k = (r["site"], r["target_rva"])
        if k not in seen:
            seen.add(k)
            uniq_refs.append(r)

    return {
        "seed": SEED_RVA,
        "block_count": len(blocks),
        "instruction_count": len(decoded),
        "rva_min": min_rva,
        "rva_max": max_rva,
        "span": max_rva - min_rva,
        "limits_hit": bool(pending or len(blocks) >= MAX_BLOCKS or len(decoded) >= MAX_INSTRUCTIONS),
        "blocks": sorted(blocks, key=lambda x: x["start"]),
        "instructions": [decoded[k] for k in sorted(decoded)],
        "calls": sorted(calls, key=lambda x: x["site"]),
        "rip_refs": uniq_refs,
    }


def callee_report(md, pe, target: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(target)
    if fn is None:
        return {"target": target, "function": None}
    size = fn["end"] - fn["begin"]
    cap = min(size, CALLEE_CAP)
    blob = rva_blob(pe, fn["begin"], cap)
    rows = []
    calls = []
    refs = []
    for ins in md.disasm(blob, IMAGE_BASE + fn["begin"]):
        row, row_refs = record(md, pe, ins, op_imm, op_mem, rip_reg)
        rows.append(row)
        refs.extend(row_refs)
        if ins.mnemonic == "call":
            calls.append({
                "site": int(ins.address - IMAGE_BASE),
                "target": direct_target(ins, op_imm),
                "op_str": ins.op_str,
            })
    return {
        "target": target,
        "function": {"begin": fn["begin"], "end": fn["end"], "size": size},
        "truncated": size > cap,
        "instructions": rows,
        "calls": calls,
        "rip_refs": refs,
    }


def output_and_object_accesses(instructions):
    # At method entry RCX is the GameObject and RDX is the identity-vector output.
    # 0x55071F copies RDX to RDI, so RDI-relative stores are especially important.
    out = []
    obj = []
    for row in instructions:
        for m in row.get("memory", []):
            base = m.get("base")
            if base in ("rdi", "rdx"):
                out.append({
                    "rva": row["rva"],
                    "base": base,
                    "disp": m.get("disp"),
                    "instruction": f"{row['mnemonic']} {row['op_str']}",
                })
            if base == "rcx":
                obj.append({
                    "rva": row["rva"],
                    "disp": m.get("disp"),
                    "instruction": f"{row['mnemonic']} {row['op_str']}",
                })
    return out, obj


def fmt(row):
    return f"0x{row['rva']:08X}  {row['bytes']:<24} {row['mnemonic']:<8} {row['op_str']}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.game_root.resolve() / "GoW.exe"
    before = sha256(exe)
    if before.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {before}")

    capstone, Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    pe = load_pe().PE(exe.read_bytes())
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    traced = cfg(md, pe, op_imm, op_mem, rip_reg)
    output_accesses, object_accesses = output_and_object_accesses(traced["instructions"])
    direct_targets = sorted({c["target"] for c in traced["calls"] if c["target"] is not None})
    callees = [callee_report(md, pe, t, op_imm, op_mem, rip_reg) for t in direct_targets]

    pdata = pe.function_for(SEED_RVA)
    result = {
        "schema": 1,
        "analysis": "raven_gameobject_identity_method_real_cfg",
        "exe_sha256": before,
        "seed_rva": SEED_RVA,
        "encoder_virtual_callsite_rva": ENCODER_CALLSITE_RVA,
        "pdata_row": None if pdata is None else {
            "begin": pdata["begin"],
            "end": pdata["end"],
            "size": pdata["end"] - pdata["begin"],
        },
        "real_cfg": traced,
        "output_buffer_accesses": output_accesses,
        "gameobject_rcx_accesses": object_accesses,
        "direct_callees": callees,
        "interpretation": [
            "The method entry ABI is RCX=GameObject, RDX=identity-vector output.",
            "RDI becomes an output alias at 0x55071F.",
            "The encoder hashes count*16 bytes emitted by this method after the vtable+0x38 call.",
            "The real CFG is authoritative here because the PDATA row is known to end before reachable branches.",
        ],
        "safety": {
            "game_launched": False,
            "process_opened": False,
            "debugger_attached": False,
            "process_memory_written": False,
            "save_opened": False,
            "save_or_progression_written": False,
            "exe_modified": False,
        },
    }

    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe changed during read-only analysis")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - Raven GameObject identity method real CFG",
        f"exe_sha256={before}",
        f"seed=0x{SEED_RVA:X}",
        f"encoder_virtual_callsite=0x{ENCODER_CALLSITE_RVA:X}",
        f"pdata={result['pdata_row']}",
        (
            f"real_cfg blocks={traced['block_count']} instructions={traced['instruction_count']} "
            f"range=0x{traced['rva_min']:X}-0x{traced['rva_max']:X} "
            f"span=0x{traced['span']:X} limits_hit={traced['limits_hit']}"
        ),
        "",
        "DIRECT CALLS",
    ]
    for c in traced["calls"]:
        target = "INDIRECT" if c["target"] is None else f"0x{c['target']:X}"
        lines.append(f"  0x{c['site']:X} -> {target} {c['op_str']}")
    lines += ["", "RIP REFERENCES"]
    for r in traced["rip_refs"]:
        extra = "" if r["ascii"] is None else f" ascii={r['ascii']!r}"
        lines.append(f"  0x{r['site']:X} -> 0x{r['target_rva']:X}{extra}")
    lines += ["", "OUTPUT-RELATIVE ACCESSES (RDX/RDI)"]
    for r in output_accesses:
        lines.append(f"  0x{r['rva']:X} {r['base']}+{r['disp']:+#x} {r['instruction']}")
    lines += ["", "GAMEOBJECT RCX-RELATIVE ACCESSES"]
    for r in object_accesses:
        lines.append(f"  0x{r['rva']:X} rcx+{r['disp']:+#x} {r['instruction']}")
    lines += ["", "REAL REACHABLE DISASSEMBLY"]
    for row in traced["instructions"]:
        lines.append("  " + fmt(row))

    lines += ["", "DIRECT CALLEE SUMMARIES"]
    for c in callees:
        lines.append(f"CALLEE target=0x{c['target']:X} function={c['function']} truncated={c.get('truncated')}")
        for r in c.get("rip_refs", []):
            if r.get("ascii"):
                lines.append(f"  STR 0x{r['site']:X} {r['ascii']!r}")
        for row in c.get("instructions", []):
            mem = row.get("memory", [])
            interesting = any(
                m.get("base") in ("rcx", "rdx", "r8", "r9", "rdi")
                or m.get("rip_target_rva") is not None
                for m in mem
            )
            if interesting or row["mnemonic"] == "call":
                lines.append("  " + fmt(row))

    lines += [
        "",
        "SAFETY",
        "game_launched=false",
        "process_opened=false",
        "debugger_attached=false",
        "process_memory_written=false",
        "save_or_progression_written=false",
        "exe_modified=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "RAVEN_IDENTITY_METHOD_REAL_CFG_PASS "
        f"blocks={traced['block_count']} instructions={traced['instruction_count']} "
        f"calls={len(traced['calls'])} range=0x{traced['rva_min']:X}-0x{traced['rva_max']:X}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
