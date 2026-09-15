"""Trace the final loader-record -> persistent GameObject tuple identity edge.

Read-only, version-locked static analysis for the supported God of War executable.
This is deliberately narrow: it inspects the shared builder/loader caller at 0x7B10A0,
the descriptor builder at 0x8566B0, and the four known level/WAD +0xC3C writers,
with special focus on the 0x82CF00 path where registry_id is loaded from [rbx+0x24].
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

ANCHORS = {
    "shared_owner": 0x7B10A0,
    "shared_builder_call": 0x7B1353,
    "shared_loader_call": 0x7B137F,
    "descriptor_builder": 0x8566B0,
    "descriptor_slot_arg_load": 0x85670A,
    "descriptor_slot_store": 0x85670E,
    "loader": 0x856F50,
    "registry_writer_owner": 0x82CF00,
    "registry_write_a": 0x82D203,
    "registry_write_b": 0x82D3B7,
    "registry_writer_alt": 0x4B7400,
    "registry_write_alt": 0x4B7AFE,
    "registry_writer_const": 0x45D040,
    "registry_write_const": 0x45D190,
}

WINDOWS = {
    "shared_builder_loader": (0x7B12C0, 0x7B13A8),
    "descriptor_slot": (0x8566B0, 0x856735),
    "registry_writer_a": (0x82D180, 0x82D250),
    "registry_writer_b": (0x82D330, 0x82D400),
    "registry_writer_alt": (0x4B7AA0, 0x4B7B30),
    "registry_writer_const": (0x45D140, 0x45D1C0),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_loader_record_pe", path)
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


def ascii_at(pe, rva: int, limit: int = 96):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    raw = pe.data[off:off+limit]
    end = raw.find(b"\0")
    if end < 4:
        return None
    raw = raw[:end]
    if not raw or any(b < 0x20 or b > 0x7E for b in raw):
        return None
    return raw.decode("ascii", "replace")


def disasm_window(md, pe, start: int, end: int, op_imm, op_mem, rip_reg):
    raw = read_bytes(pe, start, end-start)
    rows = []
    for ins in md.disasm(raw, IMAGE_BASE + start):
        rva = ins.address - IMAGE_BASE
        if rva >= end:
            break
        row = {"rva": rva, "bytes": ins.bytes.hex(), "mnemonic": ins.mnemonic, "op_str": ins.op_str}
        rip_targets = []
        immediates = []
        for op in ins.operands:
            if op.type == op_imm:
                v = op.imm
                if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
                    v -= IMAGE_BASE
                immediates.append(v)
            elif op.type == op_mem and op.mem.base == rip_reg:
                t = ins.address + ins.size + op.mem.disp - IMAGE_BASE
                rip_targets.append(t)
        if immediates:
            row["immediates"] = immediates
        if rip_targets:
            row["rip_targets"] = rip_targets
            strings = []
            for t in rip_targets:
                s = ascii_at(pe, t)
                if s:
                    strings.append({"rva": t, "ascii": s})
            if strings:
                row["ascii_targets"] = strings
        rows.append(row)
    return rows


def callers(con, dest: int):
    return [
        {"site": a, "source_function": b, "kind": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,kind FROM edges WHERE dest=? ORDER BY site", (dest,)
        )
    ]


def self_test():
    assert ANCHORS["shared_builder_call"] < ANCHORS["shared_loader_call"]
    assert ANCHORS["registry_write_a"] == 0x82D203
    assert ANCHORS["descriptor_slot_store"] == 0x85670E
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

    windows = {
        name: disasm_window(md, pe, a, b, op_imm, op_mem, rip_reg)
        for name, (a, b) in WINDOWS.items()
    }

    # Version-lock the most important semantics directly from disassembly text.
    def has(name, rva, text):
        return any(row["rva"] == rva and text in row["op_str"] for row in windows[name])

    assertions = {
        "shared_builder_call": has("shared_builder_loader", 0x7B1353, "0x1408566b0"),
        "shared_loader_call": has("shared_builder_loader", 0x7B137F, "0x140856f50"),
        "descriptor_slot_source": has("descriptor_slot", 0x85670A, "dword ptr [rsp + 0x60]"),
        "descriptor_slot_store": has("descriptor_slot", 0x85670E, "[r14 + 0x30]"),
        "registry_source_a": has("registry_writer_a", 0x82D1FB, "dword ptr [rbx + 0x24]"),
        "registry_store_a": has("registry_writer_a", 0x82D203, "[r13 + 0xc3c]"),
        "registry_store_b": has("registry_writer_b", 0x82D3B7, "[r13 + 0xc3c]"),
    }

    with sqlite3.connect(db) as con:
        incoming = {name: callers(con, rva) for name, rva in ANCHORS.items() if name.endswith("owner") or name in ("descriptor_builder", "loader", "registry_writer_alt", "registry_writer_const")}

    # Extract compact provenance facts already visible in this narrow path.
    facts = []
    if assertions["registry_source_a"] and assertions["registry_store_a"]:
        facts.append("0x82D1FB loads eax from dword [rbx+0x24], then 0x82D203 stores eax to level/WAD +0xC3C")
    if assertions["shared_builder_call"] and assertions["shared_loader_call"]:
        facts.append("0x7B10A0 calls descriptor builder and loader back-to-back using one local construction context")
    if assertions["descriptor_slot_source"] and assertions["descriptor_slot_store"]:
        facts.append("descriptor +0x30 comes directly from builder stack argument at [rsp+0x60]")

    status = "PASS_NARROW_LOADER_RECORD_EDGE" if all(assertions.values()) else "BLOCKED_NARROW_LOADER_RECORD_EDGE"
    return {
        "schema": 1,
        "analysis": "gow_loader_record_identity",
        "status": status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "assertions": assertions,
        "facts": facts,
        "precise_missing_edge": "identify the canonical loader record behind RBX at 0x82D1FB and map its +0x24 registry_id plus the 0x7B1353 builder slot argument to a catalogue/WAD instance identity",
        "windows": windows,
        "incoming_callers": incoming,
        "safety": {
            "analysis_mode": "read-only",
            "game_launched": False,
            "active_save_opened": False,
            "frozen_save_opened": False,
            "save_or_progression_written": False,
            "exe_written": False,
        },
    }


def render_text(r):
    lines = [
        "GoW loader record identity trace",
        "================================",
        f"status={r['status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        f"production_oracle_status={r['production_oracle_status']}",
        "",
        "Facts",
    ]
    lines += [f"- {x}" for x in r["facts"]]
    lines += ["", f"precise_missing_edge={r['precise_missing_edge']}", "", "Assertions"]
    lines += [f"{k}={str(v).lower()}" for k, v in r["assertions"].items()]
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
