#!/usr/bin/env python3
"""Trace the two remaining helpers behind the Raven GameObject identity vector.

Static part:
  * real CFG from 0x1017F0 (called with one 16-byte object identity element)
  * real CFG from 0x101A90 (tail-called by 0x1029C0 for +0x240 identity data)
  * direct callees, memory accesses and RIP references

Optional live part:
  If the supported GoW process is already running and the three frozen
  VikingFuneral Raven tokens resolve, read only the exact identity-relevant
  object fields and metadata arrays. No debugger and no process writes.

The live step is optional and never makes the static trace fail.
"""
from __future__ import annotations

import argparse
from collections import deque
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SEEDS = {
    "single_element_builder": 0x1017F0,
    "external_identity_append": 0x101A90,
}
MAX_SPAN = 0x4000
MAX_BLOCKS = 512
MAX_INSTRUCTIONS = 20000

KNOWN = (
    ("raven_642d0d164af0a5d4076e77933c549a5d", 0x1C1001DD),
    ("raven_c945cb53465b58decfcbd4a221cb5326", 0x1C4801DD),
    ("raven_e32f7bab42fd7298890f6aa56a734562", 0x1BB001DD),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper {path}")
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
    return out.decode("ascii", "replace") if len(out) >= 4 else None


def one(md, pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    blob = pe.data[off:off + 16]
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


def cond(mn: str) -> bool:
    return mn.startswith("j") and mn not in ("jmp", "jmpq")


def row_for(md, pe, ins, op_imm, op_mem, rip_reg):
    rva = int(ins.address - IMAGE_BASE)
    row = {
        "rva": rva,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }
    mem = []
    try:
        for idx, op in enumerate(ins.operands):
            if op.type != op_mem:
                continue
            m = {
                "operand": idx,
                "base": md.reg_name(op.mem.base) if op.mem.base else None,
                "index": md.reg_name(op.mem.index) if op.mem.index else None,
                "scale": int(op.mem.scale),
                "disp": int(op.mem.disp),
            }
            if op.mem.base == rip_reg:
                target = int(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
                m["rip_target_rva"] = target
                m["ascii"] = ascii_at(pe, target)
            mem.append(m)
    except Exception:
        pass
    if mem:
        row["memory"] = mem
    t = direct_target(ins, op_imm)
    if t is not None:
        row["direct_target"] = t
    try:
        rr, rw = ins.regs_access()
        row["regs_read"] = [md.reg_name(x) for x in rr]
        row["regs_write"] = [md.reg_name(x) for x in rw]
    except Exception:
        pass
    return row


def trace_seed(md, pe, seed: int, op_imm, op_mem, rip_reg):
    pending = deque([seed])
    queued = {seed}
    decoded = {}
    blocks = []
    calls = []

    while pending and len(blocks) < MAX_BLOCKS and len(decoded) < MAX_INSTRUCTIONS:
        start = pending.popleft()
        cur = start
        rows = []
        succ = []
        reason = "limit"
        while len(decoded) < MAX_INSTRUCTIONS:
            if abs(cur - seed) > MAX_SPAN:
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
            row = row_for(md, pe, ins, op_imm, op_mem, rip_reg)
            decoded[cur] = row
            rows.append(row)
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
                        pending.append(target); queued.add(target)
                    reason = "direct_jump"
                else:
                    reason = "indirect_jump"
                break
            if cond(ins.mnemonic):
                fall = cur + ins.size
                succ.append(fall)
                if fall not in queued:
                    pending.append(fall); queued.add(fall)
                if target is not None:
                    succ.append(target)
                    if target not in queued:
                        pending.append(target); queued.add(target)
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

    keys = sorted(decoded)
    return {
        "seed": seed,
        "pdata": None if pe.function_for(seed) is None else {
            "begin": pe.function_for(seed)["begin"],
            "end": pe.function_for(seed)["end"],
        },
        "block_count": len(blocks),
        "instruction_count": len(decoded),
        "rva_min": keys[0] if keys else seed,
        "rva_max": (
            keys[-1] + len(bytes.fromhex(decoded[keys[-1]]["bytes"]))
            if keys else seed
        ),
        "limits_hit": bool(pending),
        "blocks": sorted(blocks, key=lambda x: x["start"]),
        "instructions": [decoded[k] for k in keys],
        "calls": sorted(calls, key=lambda x: x["site"]),
    }


def u64(raw: bytes, off: int = 0) -> int:
    return struct.unpack_from("<Q", raw, off)[0]


def optional_live_sample(catalogue_path: Path):
    if os.name != "nt":
        return {"attempted": False, "reason": "non_windows"}

    live = load_module("gow_ro_live_identity", "read-raven-gameobject-identity-memory.py")
    k32 = live.configure_kernel32()
    try:
        pid, exe_name = live.find_supported_process(k32)
    except Exception as exc:
        return {"attempted": False, "reason": f"game_not_running_or_unavailable: {exc}"}

    module_base, module_size, exe_path = live.get_main_module(k32, pid, exe_name)
    actual = live.sha256_file(exe_path)
    if actual.lower() != EXPECTED_SHA256:
        return {"attempted": False, "reason": f"unsupported_exe_sha256:{actual}"}

    access = live.PROCESS_VM_READ | live.PROCESS_QUERY_INFORMATION
    process = k32.OpenProcess(access, False, pid)
    if not process:
        return {"attempted": True, "complete": False, "reason": "OpenProcess read-only failed"}

    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    cat = {x["catalogue_id"]: x for x in catalogue.get("ravens", [])}
    records = []

    def read(addr: int, size: int):
        return live.safe_read(k32, process, addr, size)

    try:
        for catalogue_id, token in KNOWN:
            try:
                resolved = live.resolve_token_read_only(k32, process, module_base, token)
            except Exception as exc:
                records.append({
                    "catalogue_id": catalogue_id,
                    "token_hex": f"0x{token:08X}",
                    "resolved": False,
                    "error": repr(exc),
                })
                continue
            obj = int(resolved["object_ptr"])
            head = read(obj, 0x300)
            if head is None:
                records.append({
                    "catalogue_id": catalogue_id,
                    "token_hex": f"0x{token:08X}",
                    "resolved": False,
                    "error": "object head read failed",
                })
                continue

            meta = u64(head, 0x30)
            parent = u64(head, 0x28)
            ext = u64(head, 0x240)
            field40 = head[0x40:0x50]

            meta_report = None
            if meta:
                mh = read(meta, 0xC8)
                if mh is not None:
                    source = u64(mh, 0xB0) if len(mh) >= 0xB8 else 0
                    source2 = 0
                    if source:
                        sh = read(source, 0x20)
                        if sh is not None:
                            source2 = u64(sh, 0x10)
                    vec = None
                    if source2:
                        vh = read(source2, 4)
                        if vh is not None:
                            count = struct.unpack("<I", vh)[0]
                            if count <= 256:
                                vb = read(source2 + 4, count * 16)
                                if vb is not None:
                                    vec = {
                                        "count": count,
                                        "elements_hex": [
                                            vb[i:i+16].hex()
                                            for i in range(0, len(vb), 16)
                                        ],
                                    }
                    meta_report = {
                        "ptr": f"0x{meta:X}",
                        "type_byte_2": mh[2] if len(mh) > 2 else None,
                        "identity_source_b0": f"0x{source:X}" if source else None,
                        "identity_vector_ptr": f"0x{source2:X}" if source2 else None,
                        "identity_vector": vec,
                    }

            candidates = {}
            entry = cat.get(catalogue_id, {})
            native = entry.get("native", {})
            raw_values = {
                "final_record_id": native.get("final_record_id"),
                "override_record_id": native.get("override_record_id"),
                "parent_prototype_id": native.get("parent_prototype_id"),
                "prototype_id": native.get("prototype_id"),
            }
            for name, value in raw_values.items():
                if isinstance(value, str) and len(value) == 32:
                    try:
                        candidates[name] = bytes.fromhex(value).hex()
                    except ValueError:
                        pass
            candidates["field40_hex"] = field40.hex()

            matches = [
                name for name, hx in candidates.items()
                if name != "field40_hex" and hx.lower() == field40.hex().lower()
            ]

            records.append({
                "catalogue_id": catalogue_id,
                "token_hex": f"0x{token:08X}",
                "resolved": True,
                "object_ptr": f"0x{obj:X}",
                "field_40_16bytes_hex": field40.hex(),
                "catalogue_raw_16byte_matches": matches,
                "parent_ptr": f"0x{parent:X}" if parent else None,
                "external_identity_ptr_240": f"0x{ext:X}" if ext else None,
                "metadata": meta_report,
            })

        return {
            "attempted": True,
            "complete": True,
            "pid": pid,
            "module_base": f"0x{module_base:X}",
            "records": records,
            "safety": {
                "open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
                "debugger_attached": False,
                "process_memory_written": False,
                "save_or_progression_written": False,
            },
        }
    finally:
        live.close_handle(k32, process)


def fmt(r):
    return f"0x{r['rva']:08X}  {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.game_root.resolve() / "GoW.exe"
    before = sha256(exe)
    if before.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {before}")

    capstone, Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    pe = load_module("gow_helper_cfg_pe", "trace-gameobject-pickle-bridges.py").PE(exe.read_bytes())
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    traces = {
        name: trace_seed(md, pe, seed, op_imm, op_mem, rip_reg)
        for name, seed in SEEDS.items()
    }
    live = optional_live_sample(args.catalogue.resolve())

    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe changed during read-only static analysis")

    report = {
        "schema": 1,
        "analysis": "raven_identity_helper_paths",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "exe_sha256": before,
        "traces": traces,
        "optional_live_readonly_sample": live,
        "safety": {
            "static_exe_modified": False,
            "debugger_attached": False,
            "process_memory_written": False,
            "save_or_progression_written": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - Raven identity helper-path trace",
        f"exe_sha256={before}",
        "",
    ]
    for name, tr in traces.items():
        lines.append(
            f"{name} seed=0x{tr['seed']:X} pdata={tr['pdata']} "
            f"blocks={tr['block_count']} instructions={tr['instruction_count']} "
            f"range=0x{tr['rva_min']:X}-0x{tr['rva_max']:X} limits_hit={tr['limits_hit']}"
        )
        lines.append("  calls:")
        for c in tr["calls"]:
            target = "INDIRECT" if c["target"] is None else f"0x{c['target']:X}"
            lines.append(f"    0x{c['site']:X} -> {target} {c['op_str']}")
        lines.append("  reachable disassembly:")
        for r in tr["instructions"]:
            lines.append("    " + fmt(r))
        lines.append("")

    lines.append("OPTIONAL LIVE READ-ONLY SAMPLE")
    lines.append(json.dumps(live, indent=2))
    lines += [
        "",
        "SAFETY",
        "debugger_attached=false",
        "process_memory_written=false",
        "save_or_progression_written=false",
        "exe_modified=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_IDENTITY_HELPER_TRACE_PASS "
        + " ".join(
            f"{name}=0x{tr['rva_min']:X}-0x{tr['rva_max']:X}"
            for name, tr in traces.items()
        )
        + f" live_attempted={live.get('attempted')}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
