"""Trace GameObject's exact parent CodeSideLuaClass persistence slots.

Read-only, version-locked static analysis. The child GameObject descriptor
0x2D1B710 and its normal static parent assignment are already proved:

    0x821D71 lea rax, [0x27DA820]
    0x821D83 mov [0x2D1B710 + 0x48], rax

This tool follows only that parent descriptor and its persistence slots. It does
not launch the game, open saves, or modify GoW.exe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
CHILD = 0x2D1B710
PARENT = 0x27DA820
FIELDS = {
    "parent_0x48": 0x48,
    "guard_0xA4": 0xA4,
    "save_0xB8": 0xB8,
    "restore_0xC0": 0xC0,
}
ANCHORS = {
    "child_parent_value": (0x821D71, "488d05a88afb01"),
    "child_parent_store": (0x821D83, "488905ce994f02"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_parent_pe", path)
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


def exact_bytes(pe, rva: int, expected: str):
    raw = bytes.fromhex(expected)
    off = pe.rva_to_file(rva)
    if off is None:
        raise AssertionError(f"RVA not file backed: 0x{rva:X}")
    actual = pe.data[off:off + len(raw)]
    if actual != raw:
        raise AssertionError(f"bytes changed at 0x{rva:X}: {actual.hex()} != {expected}")


def disassemble(md, pe, fn_rva: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(fn_rva)
    if fn is None:
        raise RuntimeError(f"function boundary absent for 0x{fn_rva:X}")
    rows = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        rip_targets, immediates = [], []
        for op in ins.operands:
            if op.type == op_imm:
                v = op.imm
                if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
                    v -= IMAGE_BASE
                immediates.append(v)
            elif op.type == op_mem and op.mem.base == rip_reg:
                rip_targets.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if rip_targets:
            row["rip_targets"] = rip_targets
        if immediates:
            row["immediates"] = immediates
        rows.append(row)
    return {"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"], "instructions": rows}


def refs(con, target: int):
    return {
        "rip_refs": [
            {"site": a, "source_function": b, "mnemonic": c}
            for a, b, c in con.execute(
                "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site", (target,)
            )
        ],
        "imm_refs": [
            {"site": a, "source_function": b, "mnemonic": c}
            for a, b, c in con.execute(
                "SELECT site,src_fn,mnemonic FROM imm_refs WHERE value_rva=? ORDER BY site", (target,)
            )
        ],
        "data_ptrs": [
            r[0] for r in con.execute(
                "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (target,)
            )
        ],
    }


def read_qword(pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def normalize_pointer(pe, qword):
    if qword is None:
        return None
    value = qword - IMAGE_BASE if qword >= IMAGE_BASE else qword
    sec = pe.section_for_rva(value)
    if sec and sec.get("exec"):
        return value
    return None


def compact_windows(md, pe, owners, targets, op_imm, op_mem, rip_reg):
    out = []
    for owner in sorted(set(owners)):
        if pe.function_for(owner) is None:
            continue
        report = disassemble(md, pe, owner, op_imm, op_mem, rip_reg)
        rows = report["instructions"]
        selected = set()
        for i, row in enumerate(rows):
            if any(t in targets for t in row.get("rip_targets", [])):
                selected.update(range(max(0, i - 16), min(len(rows), i + 9)))
        out.append({
            "begin": report["begin"], "end": report["end"], "size": report["size"],
            "instructions": [rows[i] for i in sorted(selected)],
        })
    return out


def write_evidence(pe, windows, target):
    hits = []
    for win in windows:
        rows = win["instructions"]
        for i, row in enumerate(rows):
            if target not in row.get("rip_targets", []):
                continue
            prev = rows[max(0, i - 16):i]
            candidates = []
            for p in prev:
                for v in p.get("rip_targets", []):
                    sec = pe.section_for_rva(v)
                    candidates.append({
                        "site": p["rva"], "kind": "rip", "value": v,
                        "executable": bool(sec and sec.get("exec")),
                    })
                for v in p.get("immediates", []):
                    sec = pe.section_for_rva(v) if isinstance(v, int) and v >= 0 else None
                    if sec:
                        candidates.append({
                            "site": p["rva"], "kind": "immediate", "value": v,
                            "executable": bool(sec.get("exec")),
                        })
            hits.append({
                "site": row["rva"],
                "instruction": f"{row['mnemonic']} {row['op_str']}",
                "preceding_candidates": candidates,
                "preceding_instructions": prev,
            })
    return hits


def self_test():
    assert CHILD + 0x48 == 0x2D1B758
    assert PARENT + 0x48 == 0x27DA868
    assert PARENT + 0xB8 == 0x27DA8D8
    assert PARENT + 0xC0 == 0x27DA8E0
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

    for _, (rva, expected) in ANCHORS.items():
        exact_bytes(pe, rva, expected)

    targets = {"parent_descriptor": PARENT}
    targets.update({name: PARENT + off for name, off in FIELDS.items()})
    with sqlite3.connect(db) as con:
        target_refs = {name: refs(con, target) for name, target in targets.items()}

    owners = []
    for group in target_refs.values():
        owners.extend(r["source_function"] for r in group["rip_refs"])
        owners.extend(r["source_function"] for r in group["imm_refs"])
    windows = compact_windows(md, pe, owners, set(targets.values()), op_imm, op_mem, rip_reg)

    slots = {}
    for name, off in FIELDS.items():
        rva = PARENT + off
        raw = read_qword(pe, rva)
        slots[name] = {
            "rva": rva,
            "file_qword": raw,
            "file_executable_rva": normalize_pointer(pe, raw),
            "write_evidence": write_evidence(pe, windows, rva),
        }

    direct_save = slots["save_0xB8"]["file_executable_rva"]
    status = "PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK" if direct_save is not None else "BLOCKED_EXACT_GAMEOBJECT_USERDATA_CALLBACK"
    missing = None if direct_save is not None else (
        "parent descriptor 0x27DA820 is proved; exact runtime value written to parent +0xB8, "
        "or inherited parent chain if +0xB8 is null, remains to be resolved from reported writer windows"
    )

    return {
        "schema": 1,
        "analysis": "gow_gameobject_parent_persistence",
        "gameobject_parent_descriptor_status": "PASS_EXACT_GAMEOBJECT_PARENT_DESCRIPTOR",
        "gameobject_userdata_callback_status": status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "child_descriptor": CHILD,
        "parent_descriptor": PARENT,
        "parent_assignment": {
            "value_site": "0x821D71", "store_site": "0x821D83",
            "target": "GameObject descriptor +0x48",
        },
        "target_refs": target_refs,
        "slots": slots,
        "resolved_save_callback_rva": direct_save,
        "owner_windows": windows,
        "precise_missing_edge": missing,
        "safety": {
            "analysis_mode": "read-only", "game_launched": False,
            "active_save_opened": False, "frozen_save_opened": False,
            "save_or_progression_written": False, "exe_written": False,
        },
        "assertions": [f"{k}@0x{v[0]:X}" for k, v in ANCHORS.items()],
    }


def render_text(r):
    lines = [
        "GoW GameObject parent persistence trace",
        "=======================================",
        f"gameobject_parent_descriptor_status={r['gameobject_parent_descriptor_status']}",
        f"gameobject_userdata_callback_status={r['gameobject_userdata_callback_status']}",
        f"child_descriptor=0x{r['child_descriptor']:X}",
        f"parent_descriptor=0x{r['parent_descriptor']:X}",
        f"resolved_save_callback_rva={('0x%X' % r['resolved_save_callback_rva']) if r['resolved_save_callback_rva'] is not None else 'none'}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "", "Slots",
    ]
    for name, row in r["slots"].items():
        lines.append(
            f"{name}@0x{row['rva']:X}: file_qword={row['file_qword']} "
            f"file_exec={row['file_executable_rva']} writes={len(row['write_evidence'])}"
        )
    lines += ["", "Reference counts"]
    for name, group in r["target_refs"].items():
        lines.append(f"{name}: rip={len(group['rip_refs'])} imm={len(group['imm_refs'])} ptr={len(group['data_ptrs'])}")
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
    print(r["gameobject_parent_descriptor_status"])
    print(r["gameobject_userdata_callback_status"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
