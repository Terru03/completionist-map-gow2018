"""Trace the exact GameObject CodeSideLuaClass descriptor and callback slots.

Read-only, version-locked, narrow static analysis. Starts from the proved
GameObject registration bridge and descriptor RVA 0x2D1B710. It does not scan
saves or launch the game.
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
DESCRIPTOR = 0x2D1B710
REGISTER_HELPER = 0x545960
KEY_RVA = 0xDF6660
FIELDS = {
    "parent_0x48": 0x48,
    "guard_0xA4": 0xA4,
    "save_0xB8": 0xB8,
    "restore_0xC0": 0xC0,
}
ANCHORS = {
    "registration_descriptor_embed": (0x8232F2, "488d1517844f02"),
    "registration_descriptor_arg": (0x823363, "488d0da6834f02"),
    "registration_helper_call": (0x82336A, "e8f125d2ff"),
    "helper_key_ref": (0x545C85, "488d15d4098b00"),
    "helper_value_store": (0x545CB6, "488930"),
    "helper_value_tag": (0x545CB9, "c7400802000000"),
    "helper_set_call": (0x545CC5, "e8e6e74900"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_descriptor_pe", path)
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


def disassemble(md, pe, begin: int, op_imm, op_mem, rip_reg):
    fn = pe.function_for(begin)
    if fn is None:
        raise RuntimeError(f"function boundary absent for 0x{begin:X}")
    rows = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        rip_targets = []
        immediates = []
        for op in ins.operands:
            if op.type == op_imm:
                value = op.imm
                if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                    value -= IMAGE_BASE
                immediates.append(value)
            elif op.type == op_mem and op.mem.base == rip_reg:
                rip_targets.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if rip_targets:
            row["rip_targets"] = rip_targets
        if immediates:
            row["immediates"] = immediates
        rows.append(row)
    return {"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"], "instructions": rows}


def read_qword(pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def refs_for_target(con, target: int):
    rip = [
        {"site": a, "source_function": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site", (target,)
        )
    ]
    imm = [
        {"site": a, "source_function": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM imm_refs WHERE value_rva=? ORDER BY site", (target,)
        )
    ]
    ptrs = [r[0] for r in con.execute(
        "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (target,)
    )]
    return {"rip_refs": rip, "imm_refs": imm, "data_ptrs": ptrs}


def executable_rva(pe, value: int | None) -> bool:
    if value is None:
        return False
    sec = pe.section_for_rva(value)
    return bool(sec and sec.get("exec"))


def compact_owner(md, pe, fn_rva: int, op_imm, op_mem, rip_reg, interesting: set[int]):
    report = disassemble(md, pe, fn_rva, op_imm, op_mem, rip_reg)
    rows = report["instructions"]
    selected_idx = set()
    for i, row in enumerate(rows):
        if any(t in interesting for t in row.get("rip_targets", [])):
            selected_idx.update(range(max(0, i - 8), min(len(rows), i + 9)))
    # Always include helper entry and the key-set window.
    if report["begin"] == REGISTER_HELPER:
        selected_idx.update(range(0, min(len(rows), 32)))
        for i, row in enumerate(rows):
            if row["rva"] in (0x545C85, 0x545CB6, 0x545CB9, 0x545CC5):
                selected_idx.update(range(max(0, i - 10), min(len(rows), i + 12)))
    return {
        "begin": report["begin"], "end": report["end"], "size": report["size"],
        "instructions": [rows[i] for i in sorted(selected_idx)],
    }


def recover_direct_slot_value(pe, owner_reports, target: int):
    hits = []
    for report in owner_reports:
        rows = report["instructions"]
        for i, row in enumerate(rows):
            if target not in row.get("rip_targets", []):
                continue
            item = {"site": row["rva"], "instruction": f"{row['mnemonic']} {row['op_str']}"}
            # Capture nearby executable immediates/RIP targets as candidate values only.
            nearby = []
            for prev in rows[max(0, i - 6):i + 1]:
                for value in prev.get("immediates", []):
                    if executable_rva(pe, value):
                        nearby.append({"source_site": prev["rva"], "kind": "immediate", "value": value})
                for value in prev.get("rip_targets", []):
                    if executable_rva(pe, value):
                        nearby.append({"source_site": prev["rva"], "kind": "rip", "value": value})
            item["nearby_executable_values"] = nearby
            hits.append(item)
    return hits


def self_test():
    assert DESCRIPTOR + FIELDS["save_0xB8"] == 0x2D1B7C8
    assert DESCRIPTOR + FIELDS["restore_0xC0"] == 0x2D1B7D0
    assert DESCRIPTOR + FIELDS["parent_0x48"] == 0x2D1B758
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode)
    md.detail = True

    for _, (rva, expected) in ANCHORS.items():
        exact_bytes(pe, rva, expected)

    with sqlite3.connect(db) as con:
        targets = {"descriptor": DESCRIPTOR}
        targets.update({name: DESCRIPTOR + off for name, off in FIELDS.items()})
        refs = {name: refs_for_target(con, target) for name, target in targets.items()}

    interesting = set(targets.values())
    owner_ids = {REGISTER_HELPER, 0x822C40}
    for group in refs.values():
        owner_ids.update(x["source_function"] for x in group["rip_refs"])
        owner_ids.update(x["source_function"] for x in group["imm_refs"])

    owner_reports = []
    for owner in sorted(owner_ids):
        if pe.function_for(owner) is None:
            continue
        owner_reports.append(compact_owner(md, pe, owner, op_imm, op_mem, rip_reg, interesting))

    helper = disassemble(md, pe, REGISTER_HELPER, op_imm, op_mem, rip_reg)
    entry_rows = helper["instructions"][:40]
    rcx_to_rsi = any(r["mnemonic"] == "mov" and r["op_str"] == "rsi, rcx" for r in entry_rows)
    key_ref = next((r for r in helper["instructions"] if r["rva"] == 0x545C85 and KEY_RVA in r.get("rip_targets", [])), None)
    descriptor_pass = rcx_to_rsi and key_ref is not None

    static_slots = {}
    for name, off in FIELDS.items():
        raw = read_qword(pe, DESCRIPTOR + off)
        static_slots[name] = {
            "rva": DESCRIPTOR + off,
            "file_backed_qword": raw,
            "file_backed_qword_is_executable": executable_rva(pe, raw - IMAGE_BASE if raw and raw >= IMAGE_BASE else raw),
            "write_evidence": recover_direct_slot_value(pe, owner_reports, DESCRIPTOR + off),
        }

    save_static = static_slots["save_0xB8"]
    save_value = save_static["file_backed_qword"]
    if save_value and save_value >= IMAGE_BASE:
        save_value -= IMAGE_BASE
    save_callback = save_value if executable_rva(pe, save_value) else None

    callback_status = "PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK" if descriptor_pass and save_callback else "BLOCKED_EXACT_GAMEOBJECT_USERDATA_CALLBACK"
    missing = None
    if not descriptor_pass:
        missing = "registration helper input RCX was not proved to flow as RSI into __codesideluaclass assignment"
    elif not save_callback:
        missing = "exact runtime writer/value for GameObject descriptor +0xB8 (and +0x48 parent if inherited) remains unresolved"

    return {
        "schema": 1,
        "analysis": "gow_gameobject_class_descriptor",
        "gameobject_class_descriptor_status": "PASS_EXACT_GAMEOBJECT_CLASS_DESCRIPTOR" if descriptor_pass else "BLOCKED_EXACT_GAMEOBJECT_CLASS_DESCRIPTOR",
        "gameobject_userdata_callback_status": callback_status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "descriptor": {
            "rva": DESCRIPTOR,
            "registration_helper": REGISTER_HELPER,
            "helper_rcx_to_rsi": rcx_to_rsi,
            "key_assignment_anchor": key_ref,
            "registration_anchors": {k: f"0x{v[0]:X}" for k, v in ANCHORS.items()},
        },
        "target_refs": refs,
        "static_slots": static_slots,
        "resolved_save_callback_rva": save_callback,
        "precise_missing_edge": missing,
        "owner_windows": owner_reports,
        "safety": {
            "analysis_mode": "read-only", "game_launched": False,
            "active_save_opened": False, "frozen_save_opened": False,
            "save_or_progression_written": False, "exe_written": False,
        },
        "assertions": [f"{name}@0x{rva:X}" for name, (rva, _) in ANCHORS.items()],
    }


def render_text(r):
    lines = [
        "GoW exact GameObject class descriptor trace",
        "===========================================",
        f"gameobject_class_descriptor_status={r['gameobject_class_descriptor_status']}",
        f"gameobject_userdata_callback_status={r['gameobject_userdata_callback_status']}",
        f"descriptor_rva=0x{r['descriptor']['rva']:X}",
        f"registration_helper=0x{r['descriptor']['registration_helper']:X}",
        f"helper_rcx_to_rsi={str(r['descriptor']['helper_rcx_to_rsi']).lower()}",
        f"resolved_save_callback_rva={('0x%X' % r['resolved_save_callback_rva']) if r['resolved_save_callback_rva'] is not None else 'none'}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
        "Reference counts",
    ]
    for name, group in r["target_refs"].items():
        lines.append(f"{name}: rip={len(group['rip_refs'])} imm={len(group['imm_refs'])} ptr={len(group['data_ptrs'])}")
    lines += ["", "Slots"]
    for name, row in r["static_slots"].items():
        lines.append(f"{name}@0x{row['rva']:X}: file_qword={row['file_backed_qword']} writes={len(row['write_evidence'])}")
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
    print(r["gameobject_class_descriptor_status"])
    print(r["gameobject_userdata_callback_status"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
