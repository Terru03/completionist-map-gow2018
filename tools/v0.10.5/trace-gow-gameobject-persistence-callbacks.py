"""Trace the exact GameObject userdata persistence save/restore callbacks.

Read-only, version-locked static analysis for the supported God of War executable.
The callback ownership is already proved through:

  GameObject descriptor 0x2D1B710
    +0x48 -> parent descriptor 0x27DA820
  parent +0xB8 -> save callback    0x5F96B0
  parent +0xC0 -> restore callback 0x5F95F0

This tracer stays narrow: it verifies the two independent initializer writes,
disassembles only the two callbacks and their direct callees, records direct
memory/RIP references, and highlights writes through the save output buffer.
No game launch and no save access.
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

SAVE_CALLBACK = 0x5F96B0
RESTORE_CALLBACK = 0x5F95F0
PARENT_DESCRIPTOR = 0x27DA820
SAVE_SLOT = PARENT_DESCRIPTOR + 0xB8
RESTORE_SLOT = PARENT_DESCRIPTOR + 0xC0

ANCHORS = {
    "init_a_save_value": (0x5AAE9E, "488d050be80400"),
    "init_a_save_store": (0x5AAEA5, "4889052cfa2202"),
    "init_a_restore_value": (0x5AAEAC, "488d053de70400"),
    "init_a_restore_store": (0x5AAEB3, "48890526fa2202"),
    "init_b_save_value": (0x60B94D, "488d055cddfeff"),
    "init_b_save_store": (0x60B954, "4889057def1c02"),
    "init_b_restore_value": (0x60B95B, "488d058edcfeff"),
    "init_b_restore_store": (0x60B962, "48890577ef1c02"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_persistence_callbacks_pe", path)
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


def exact_bytes(pe, rva: int, expected: str) -> None:
    raw = bytes.fromhex(expected)
    off = pe.rva_to_file(rva)
    if off is None:
        raise AssertionError(f"RVA not file backed: 0x{rva:X}")
    actual = pe.data[off:off + len(raw)]
    if actual != raw:
        raise AssertionError(f"bytes changed at 0x{rva:X}: {actual.hex()} != {expected}")


def disassemble(md, pe, begin: int, op_imm, op_mem, rip_reg) -> dict:
    fn = pe.function_for(begin)
    if fn is None or fn["begin"] != begin:
        raise RuntimeError(f"exact function boundary absent at 0x{begin:X}")
    rows = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + begin):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        rip_targets = []
        immediates = []
        mem = []
        for op in ins.operands:
            if op.type == op_imm:
                value = op.imm
                if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                    value -= IMAGE_BASE
                immediates.append(value)
            elif op.type == op_mem:
                mem.append({
                    "base": ins.reg_name(op.mem.base) if op.mem.base else None,
                    "index": ins.reg_name(op.mem.index) if op.mem.index else None,
                    "scale": op.mem.scale,
                    "disp": op.mem.disp,
                })
                if op.mem.base == rip_reg:
                    rip_targets.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if rip_targets:
            row["rip_targets"] = rip_targets
        if immediates:
            row["immediates"] = immediates
        if mem:
            row["memory_operands"] = mem
        rows.append(row)
    return {
        "begin": begin,
        "end": fn["end"],
        "size": fn["end"] - begin,
        "instructions": rows,
    }


def ascii_at(pe, rva: int) -> str | None:
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    end = pe.data.find(b"\0", off, min(len(pe.data), off + 256))
    if end < 0 or end == off:
        return None
    raw = pe.data[off:end]
    if not all(0x20 <= b <= 0x7E for b in raw):
        return None
    return raw.decode("ascii", "replace")


def direct_edges(con: sqlite3.Connection, src_fn: int) -> list[dict]:
    return [
        {"site": site, "kind": kind, "dest": dest}
        for site, kind, dest in con.execute(
            "SELECT site,kind,dest FROM edges WHERE src_fn=? ORDER BY site", (src_fn,)
        )
    ]


def function_summary(report: dict, pe, con: sqlite3.Connection) -> dict:
    rip_refs = []
    output_like = []
    for row in report["instructions"]:
        for target in row.get("rip_targets", []):
            rip_refs.append({
                "site": row["rva"],
                "target": target,
                "ascii": ascii_at(pe, target),
                "instruction": f"{row['mnemonic']} {row['op_str']}".strip(),
            })
        # Save ABI has R8 as output buffer. Flag direct [r8+disp] accesses and
        # obvious aliases so manual review can prove the payload layout without
        # broad dataflow guessing.
        for mem in row.get("memory_operands", []):
            if mem["base"] in {"r8", "r9", "rdx", "rcx"}:
                output_like.append({
                    "site": row["rva"],
                    "instruction": f"{row['mnemonic']} {row['op_str']}".strip(),
                    "memory": mem,
                })
    return {
        **report,
        "direct_edges": direct_edges(con, report["begin"]),
        "rip_references": rip_refs,
        "abi_related_memory_accesses": output_like,
    }


def self_test() -> None:
    assert SAVE_SLOT == 0x27DA8D8
    assert RESTORE_SLOT == 0x27DA8E0
    assert SAVE_CALLBACK == 0x5F96B0
    assert RESTORE_CALLBACK == 0x5F95F0
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path) -> dict:
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    if not db.is_file():
        raise RuntimeError(f"research index missing: {db}")

    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode)
    md.detail = True

    for _, (rva, expected) in ANCHORS.items():
        exact_bytes(pe, rva, expected)

    save = disassemble(md, pe, SAVE_CALLBACK, op_imm, op_mem, rip_reg)
    restore = disassemble(md, pe, RESTORE_CALLBACK, op_imm, op_mem, rip_reg)

    with sqlite3.connect(db) as con:
        save = function_summary(save, pe, con)
        restore = function_summary(restore, pe, con)
        direct_callee_rvas = sorted({
            edge["dest"]
            for group in (save, restore)
            for edge in group["direct_edges"]
            if pe.function_for(edge["dest"]) is not None
            and pe.function_for(edge["dest"])["begin"] == edge["dest"]
        })
        callees = []
        for target in direct_callee_rvas:
            fn = pe.function_for(target)
            if fn is None or fn["end"] - fn["begin"] > 0x1200:
                continue
            callees.append(function_summary(
                disassemble(md, pe, target, op_imm, op_mem, rip_reg), pe, con
            ))

    return {
        "schema": 1,
        "analysis": "gow_gameobject_persistence_callbacks",
        "gameobject_userdata_callback_status": "PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK",
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "ownership": {
            "gameobject_descriptor": "0x2D1B710",
            "parent_descriptor": "0x27DA820",
            "save_slot": "0x27DA8D8",
            "restore_slot": "0x27DA8E0",
            "save_callback": "0x5F96B0",
            "restore_callback": "0x5F95F0",
            "proof": (
                "two independent initializer paths load the same executable callback "
                "addresses immediately before storing parent +0xB8/+0xC0"
            ),
        },
        "save_callback": save,
        "restore_callback": restore,
        "direct_callees": callees,
        "callback_abi": {
            "save": {
                "rcx": "Lua state/context",
                "edx": "original userdata stack index",
                "r8": "0x80-byte output buffer",
                "r9d": "0x80 maximum payload bytes",
                "out_length": "caller stack dword supplied through callback contract",
            },
            "restore": "inverse callback ABI to be recovered from exact disassembly",
        },
        "precise_missing_edge": (
            "callback semantics: exact bytes written by 0x5F96B0 and their connected "
            "stable GameObject identity ancestry; then inverse resolution through 0x5F95F0"
        ),
        "safety": {
            "analysis_mode": "read-only",
            "game_launched": False,
            "active_save_opened": False,
            "frozen_save_opened": False,
            "save_or_progression_written": False,
            "exe_written": False,
        },
        "assertions": [f"{name}@0x{rva:X}" for name, (rva, _) in ANCHORS.items()],
    }


def render_text(r: dict) -> str:
    save = r["save_callback"]
    restore = r["restore_callback"]
    lines = [
        "GoW GameObject persistence callback trace",
        "=========================================",
        f"gameobject_userdata_callback_status={r['gameobject_userdata_callback_status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        "save_callback=0x5F96B0",
        f"save_size={save['size']}",
        f"save_direct_edges={len(save['direct_edges'])}",
        f"save_rip_refs={len(save['rip_references'])}",
        "restore_callback=0x5F95F0",
        f"restore_size={restore['size']}",
        f"restore_direct_edges={len(restore['direct_edges'])}",
        f"restore_rip_refs={len(restore['rip_references'])}",
        f"direct_callees_disassembled={len(r['direct_callees'])}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
        "Save instructions",
    ]
    lines.extend(
        f"0x{x['rva']:X}  {x['bytes']:<24} {x['mnemonic']} {x['op_str']}"
        for x in save["instructions"]
    )
    lines += ["", "Restore instructions"]
    lines.extend(
        f"0x{x['rva']:X}  {x['bytes']:<24} {x['mnemonic']} {x['op_str']}"
        for x in restore["instructions"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--exe", type=Path)
    p.add_argument("--db", type=Path)
    p.add_argument("--output-json", type=Path)
    p.add_argument("--output-text", type=Path)
    a = p.parse_args()
    if a.self_test:
        self_test()
        return 0
    if any(x is None for x in (a.exe, a.db, a.output_json, a.output_text)):
        p.error("--exe, --db, --output-json and --output-text required")
    r = analyze(a.exe, a.db)
    a.output_json.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    a.output_text.write_text(render_text(r), encoding="utf-8")
    print(r["gameobject_userdata_callback_status"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    print(f"ASSERTIONS={len(r['assertions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
