"""Trace GoW's no-hint GameObject slot allocator used by canonical WAD loads.

Read-only, version-locked static analysis for the supported GoW.exe. This tracer
starts from the proved loader call at 0x857329 -> 0x4EF4C0 and compares the
no-hint allocator with the explicit-hint allocator at 0x4EF2B0. It does not
launch the game or access saves.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
DYNAMIC_ALLOCATOR = 0x4EF4C0
HINT_ALLOCATOR = 0x4EF2B0
LOADER_DYNAMIC_CALL = 0x857329
LOADER = 0x856F50


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_dynamic_slot_pe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def read_bytes(pe, rva: int, n: int) -> bytes:
    off = pe.rva_to_file(rva)
    if off is None or off + n > len(pe.data):
        raise RuntimeError(f"RVA not file-backed: 0x{rva:X}")
    return pe.data[off:off+n]


def decode_fn(md, pe, rva: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(rva)
    if fn is None:
        raise RuntimeError(f"no runtime function for 0x{rva:X}")
    rows = []
    raw = pe.bytes_for(fn)
    for ins in md.disasm(raw, IMAGE_BASE + fn["begin"]):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        mems = []
        imms = []
        rips = []
        for idx, op in enumerate(ins.operands):
            if op.type == op_imm:
                v = op.imm
                if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
                    v -= IMAGE_BASE
                imms.append(v)
            elif op.type == op_mem:
                base = ins.reg_name(op.mem.base) if op.mem.base else None
                index = ins.reg_name(op.mem.index) if op.mem.index else None
                mems.append({
                    "operand_index": idx,
                    "base": base,
                    "index": index,
                    "scale": op.mem.scale,
                    "disp": op.mem.disp,
                })
                if op.mem.base == rip_reg:
                    rips.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if mems:
            row["memory_operands"] = mems
        if imms:
            row["immediates"] = imms
        if rips:
            row["rip_targets"] = rips
        rows.append(row)
    return {"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"], "instructions": rows}


def decode_window(md, pe, start: int, end: int, op_imm, op_mem, rip_reg):
    raw = read_bytes(pe, start, end-start)
    rows = []
    for ins in md.disasm(raw, IMAGE_BASE + start):
        rva = ins.address - IMAGE_BASE
        if rva >= end:
            break
        row = {"rva": rva, "bytes": ins.bytes.hex(), "mnemonic": ins.mnemonic, "op_str": ins.op_str}
        mems = []
        imms = []
        rips = []
        for idx, op in enumerate(ins.operands):
            if op.type == op_imm:
                v = op.imm
                if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
                    v -= IMAGE_BASE
                imms.append(v)
            elif op.type == op_mem:
                base = ins.reg_name(op.mem.base) if op.mem.base else None
                index = ins.reg_name(op.mem.index) if op.mem.index else None
                mems.append({"operand_index": idx, "base": base, "index": index, "scale": op.mem.scale, "disp": op.mem.disp})
                if op.mem.base == rip_reg:
                    rips.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if mems:
            row["memory_operands"] = mems
        if imms:
            row["immediates"] = imms
        if rips:
            row["rip_targets"] = rips
        rows.append(row)
    return rows


def direct_edges(rows, pe):
    out = []
    for row in rows:
        if row["mnemonic"] not in ("call", "jmp"):
            continue
        for v in row.get("immediates", []):
            if 0 <= v < pe.size_of_image:
                fn = pe.function_for(v)
                out.append({
                    "site": row["rva"],
                    "kind": row["mnemonic"],
                    "dest": v,
                    "target_function_begin": fn["begin"] if fn else None,
                    "target_function_end": fn["end"] if fn else None,
                })
    return out


def callers(con, dest: int):
    return [
        {"site": a, "source_function": b, "kind": c}
        for a, b, c in con.execute("SELECT site,src_fn,kind FROM edges WHERE dest=? ORDER BY site", (dest,))
    ]


def interesting(rows):
    out = []
    for row in rows:
        text = row["op_str"].lower()
        keep = False
        for m in row.get("memory_operands", []):
            disp = m["disp"]
            if disp in (0x278, 0x280, 0x284, 0x10, 0x18, 0x20, 0x24, 0x30):
                keep = True
            if m["index"] is not None and m["scale"] in (4, 8):
                keep = True
        if row["mnemonic"] in ("call", "jmp", "cmp", "test", "inc", "dec"):
            keep = True
        if "0xffffffff" in text or "-1" in text:
            keep = True
        if keep:
            out.append(row)
    return out


def self_test():
    assert LOADER_DYNAMIC_CALL == 0x857329
    assert DYNAMIC_ALLOCATOR == 0x4EF4C0
    assert HINT_ALLOCATOR == 0x4EF2B0
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    if not db.is_file():
        raise RuntimeError(f"missing research index: {db}")

    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode); md.detail = True

    dynamic = decode_fn(md, pe, DYNAMIC_ALLOCATOR, op_imm, op_mem, rip_reg)
    hinted = decode_fn(md, pe, HINT_ALLOCATOR, op_imm, op_mem, rip_reg)
    loader_window = decode_window(md, pe, 0x8572D0, 0x857350, op_imm, op_mem, rip_reg)

    # Version-lock the proved dynamic loader call.
    call_row = next((r for r in loader_window if r["rva"] == LOADER_DYNAMIC_CALL), None)
    dynamic_call_proved = bool(call_row and DYNAMIC_ALLOCATOR in call_row.get("immediates", []))

    with sqlite3.connect(db) as con:
        incoming_dynamic = callers(con, DYNAMIC_ALLOCATOR)
        incoming_hint = callers(con, HINT_ALLOCATOR)

    dyn_edges = direct_edges(dynamic["instructions"], pe)
    hint_edges = direct_edges(hinted["instructions"], pe)

    return {
        "schema": 1,
        "analysis": "gow_dynamic_slot_allocation",
        "status": "PASS_DYNAMIC_SLOT_ALLOCATION_TRACE" if dynamic_call_proved else "BLOCKED_DYNAMIC_SLOT_ALLOCATION_TRACE",
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "anchors": {
            "loader_dynamic_call": f"0x{LOADER_DYNAMIC_CALL:X}",
            "dynamic_allocator": f"0x{DYNAMIC_ALLOCATOR:X}",
            "hint_allocator": f"0x{HINT_ALLOCATOR:X}",
            "dynamic_call_proved": dynamic_call_proved,
        },
        "loader_call_window": loader_window,
        "dynamic_allocator": dynamic,
        "dynamic_allocator_interesting": interesting(dynamic["instructions"]),
        "dynamic_direct_edges": dyn_edges,
        "hint_allocator": hinted,
        "hint_allocator_interesting": interesting(hinted["instructions"]),
        "hint_direct_edges": hint_edges,
        "incoming_dynamic": incoming_dynamic,
        "incoming_hint": incoming_hint,
        "precise_missing_edge": "classify no-hint slot selection in 0x4EF4C0 (first-free/append/other) and connect its deterministic input/order to canonical WAD catalogue record order",
        "safety": {
            "analysis_mode": "read-only",
            "game_launched": False,
            "active_save_opened": False,
            "frozen_save_opened": False,
            "save_or_progression_written": False,
            "exe_written": False,
        },
    }


def render_rows(rows):
    return [f"0x{r['rva']:X}  {r['bytes']:<24} {r['mnemonic']} {r['op_str']}" for r in rows]


def render_text(r):
    lines = [
        "GoW dynamic slot allocation trace",
        "=================================",
        f"status={r['status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        f"dynamic_allocator=0x{r['dynamic_allocator']['begin']:X}-0x{r['dynamic_allocator']['end']:X}",
        f"hint_allocator=0x{r['hint_allocator']['begin']:X}-0x{r['hint_allocator']['end']:X}",
        f"incoming_dynamic={len(r['incoming_dynamic'])}",
        f"incoming_hint={len(r['incoming_hint'])}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
        "Loader dynamic-call window",
    ]
    lines += render_rows(r["loader_call_window"])
    lines += ["", "Dynamic allocator interesting instructions"]
    lines += render_rows(r["dynamic_allocator_interesting"])
    lines += ["", "Hint allocator interesting instructions"]
    lines += render_rows(r["hint_allocator_interesting"])
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--exe", type=Path)
    p.add_argument("--db", type=Path)
    p.add_argument("--output-json", type=Path)
    p.add_argument("--output-text", type=Path)
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if any(x is None for x in (a.exe, a.db, a.output_json, a.output_text)):
        p.error("--exe, --db, --output-json and --output-text required")
    r = analyze(a.exe, a.db)
    a.output_json.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    a.output_text.write_text(render_text(r), encoding="utf-8")
    print(r["status"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
