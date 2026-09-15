"""Trace load-time reconstruction of the persisted GameObject registry/slot tuple.

Read-only, version-locked analysis for the supported God of War executable.
This starts from the now-proved callback round-trip (the persisted payload is the
same packed runtime token) and follows only the loader anchors that recreate the
token fields:

  descriptor +0x30 preferred slot -> allocator
  level/WAD +0xC3C registry id    -> allocator

No save files are opened and the game is not launched.
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
    "save_callback": (0x5F96B0, "4883ec38"),
    "save_payload_qword": (0x5F96E4, "488b4008"),
    "save_encoder_call": (0x5F96FD, "e81efdf4ff"),
    "restore_decoder_call": (0x5F9633, "e868fbf4ff"),
    "restore_registry_shift": (0x5F966F, "48d1e9"),
    "restore_slot_shift": (0x5F9667, "48c1ea12"),
    "restore_resolver_call": (0x5F967B, "e8305aefff"),
    "descriptor_slot_arg_load": (0x85670A, "8b442460"),
    "descriptor_slot_store": (0x85670E, "41894630"),
    "loader_registry_load": (0x856FAD, "8b9f3c0c0000"),
    "loader_slot_load": (0x856FB7, "8b4630"),
    "loader_registry_copy": (0x857243, "8b442444"),
    "loader_slot_copy": (0x85724B, "8b4630"),
    "loader_allocator_call": (0x8572AA, "e80180c9ff"),
    "loader_dynamic_call": (0x857329, "e89281c9ff"),
}

TARGET_DISPLACEMENT = 0xC3C


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_loader_tuple_pe", path)
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
    from capstone.x86_const import X86_OP_MEM
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_MEM


def exact_bytes(pe, rva: int, expected: str):
    raw = bytes.fromhex(expected)
    off = pe.rva_to_file(rva)
    if off is None:
        raise AssertionError(f"RVA not file-backed: 0x{rva:X}")
    actual = pe.data[off:off + len(raw)]
    if actual != raw:
        raise AssertionError(f"bytes changed at 0x{rva:X}: {actual.hex()} != {expected}")


def disassemble(md, pe, rva: int):
    fn = pe.function_for(rva)
    if fn is None:
        raise RuntimeError(f"function boundary absent for 0x{rva:X}")
    out = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        mem = []
        for idx, op in enumerate(ins.operands):
            if op.type == 3:  # X86_OP_MEM
                mem.append({
                    "operand_index": idx,
                    "base": md.reg_name(op.mem.base) if op.mem.base else None,
                    "index": md.reg_name(op.mem.index) if op.mem.index else None,
                    "scale": op.mem.scale,
                    "disp": op.mem.disp,
                })
        if mem:
            row["memory_operands"] = mem
        out.append(row)
    return {"begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"], "instructions": out}


def edge_callers(con: sqlite3.Connection, target: int):
    return [
        {"site": a, "source_function": b, "kind": c, "dest": d}
        for a, b, c, d in con.execute(
            "SELECT site,src_fn,kind,dest FROM edges WHERE dest=? ORDER BY site", (target,)
        )
    ]


def edge_outgoing(con: sqlite3.Connection, owner: int):
    return [
        {"site": a, "source_function": b, "kind": c, "dest": d}
        for a, b, c, d in con.execute(
            "SELECT site,src_fn,kind,dest FROM edges WHERE src_fn=? ORDER BY site", (owner,)
        )
    ]


def window_for_site(md, pe, site: int, radius: int = 28):
    rep = disassemble(md, pe, site)
    rows = rep["instructions"]
    idx = next((i for i, row in enumerate(rows) if row["rva"] == site), None)
    if idx is None:
        return {"site": site, "begin": rep["begin"], "end": rep["end"], "instructions": []}
    lo = max(0, idx - radius)
    hi = min(len(rows), idx + radius + 1)
    return {"site": site, "begin": rep["begin"], "end": rep["end"], "instructions": rows[lo:hi]}


def scan_displacement(md, pe, displacement: int):
    hits = []
    seen = set()
    for fn in pe.runtime_functions:
        off = pe.rva_to_file(fn["begin"])
        if off is None:
            continue
        for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
            for idx, op in enumerate(ins.operands):
                if op.type != 3 or op.mem.disp != displacement:
                    continue
                key = (ins.address, idx)
                if key in seen:
                    continue
                seen.add(key)
                first_is_target = idx == 0
                write_like = first_is_target and ins.mnemonic in {
                    "mov", "movzx", "movsx", "movsxd", "and", "or", "xor", "add", "sub", "inc", "dec"
                }
                hits.append({
                    "site": ins.address - IMAGE_BASE,
                    "function": fn["begin"],
                    "mnemonic": ins.mnemonic,
                    "op_str": ins.op_str,
                    "operand_index": idx,
                    "base": md.reg_name(op.mem.base) if op.mem.base else None,
                    "index": md.reg_name(op.mem.index) if op.mem.index else None,
                    "scale": op.mem.scale,
                    "disp": op.mem.disp,
                    "write_like": write_like,
                })
    return hits


def self_test():
    token = 1 | (0x1234 << 1) | (1 << 17) | (0x54321 << 18)
    assert ((token >> 1) & 0xFFFF) == 0x1234
    assert ((token >> 17) & 1) == 1
    assert ((token >> 18) & 0xFFFFF) == 0x54321
    assert TARGET_DISPLACEMENT == 0xC3C
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    if not db.is_file():
        raise RuntimeError(f"research index missing: {db}")

    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, _ = load_capstone()
    md = Cs(arch, mode)
    md.detail = True

    for _, (rva, expected) in ANCHORS.items():
        exact_bytes(pe, rva, expected)

    builder = disassemble(md, pe, 0x85670A)
    loader = disassemble(md, pe, 0x856FAD)
    save = disassemble(md, pe, 0x5F96B0)
    restore = disassemble(md, pe, 0x5F95F0)
    encoder = disassemble(md, pe, 0x549420)
    decoder = disassemble(md, pe, 0x5491A0)

    with sqlite3.connect(db) as con:
        builder_callers = edge_callers(con, builder["begin"])
        loader_callers = edge_callers(con, loader["begin"])
        builder_outgoing = edge_outgoing(con, builder["begin"])
        loader_outgoing = edge_outgoing(con, loader["begin"])

    builder_caller_windows = [window_for_site(md, pe, row["site"]) for row in builder_callers[:64]]
    loader_caller_windows = [window_for_site(md, pe, row["site"]) for row in loader_callers[:64]]

    c3c_hits = scan_displacement(md, pe, TARGET_DISPLACEMENT)
    c3c_writes = [row for row in c3c_hits if row["write_like"]]
    c3c_writer_windows = [window_for_site(md, pe, row["site"], 20) for row in c3c_writes[:64]]

    callback_roundtrip = (
        any(r["rva"] == 0x5F96E4 and r["op_str"] == "rax, qword ptr [rax + 8]" for r in save["instructions"])
        and any(r["rva"] == 0x5F967B and "0x1404ef0b0" in r["op_str"].lower() for r in restore["instructions"])
    )

    return {
        "schema": 1,
        "analysis": "gow_loader_persistent_tuple",
        "gameobject_userdata_callback_status": "PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK",
        "callback_token_roundtrip_status": "PASS_EXACT_RUNTIME_TOKEN_ROUNDTRIP" if callback_roundtrip else "BLOCKED_EXACT_RUNTIME_TOKEN_ROUNDTRIP",
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "proved_payload_semantics": {
            "save": "userdata+0x8 qword is passed to 0x549420 encoder",
            "restore": "0x5491A0 decodes qword; registry_id/flavor/slot are extracted and passed to 0x4EF0B0",
            "stable_replacement_layer": False,
            "implication": "cross-load stability must come from deterministic reconstruction of registry_id/slot before restore resolution",
        },
        "descriptor_builder": builder,
        "loader": loader,
        "encoder": encoder,
        "decoder": decoder,
        "builder_callers": builder_callers,
        "loader_callers": loader_callers,
        "builder_outgoing": builder_outgoing,
        "loader_outgoing": loader_outgoing,
        "builder_caller_windows": builder_caller_windows,
        "loader_caller_windows": loader_caller_windows,
        "level_registry_plus_c3c_accesses": c3c_hits,
        "level_registry_plus_c3c_writes": c3c_writes,
        "level_registry_plus_c3c_writer_windows": c3c_writer_windows,
        "precise_missing_edge": "map descriptor-construction slot argument feeding +0x30 and level/WAD +0xC3C registry_id to a canonical WAD/catalogue record identity, proving the same tuple after reload",
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


def render_text(r):
    lines = [
        "GoW loader persistent tuple trace",
        "=================================",
        f"callback_token_roundtrip_status={r['callback_token_roundtrip_status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        f"builder_function=0x{r['descriptor_builder']['begin']:X}-0x{r['descriptor_builder']['end']:X}",
        f"loader_function=0x{r['loader']['begin']:X}-0x{r['loader']['end']:X}",
        f"builder_callers={len(r['builder_callers'])}",
        f"loader_callers={len(r['loader_callers'])}",
        f"c3c_accesses={len(r['level_registry_plus_c3c_accesses'])}",
        f"c3c_writes={len(r['level_registry_plus_c3c_writes'])}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
        "+0xC3C writers",
    ]
    for row in r["level_registry_plus_c3c_writes"]:
        lines.append(f"0x{row['site']:X} fn=0x{row['function']:X} {row['mnemonic']} {row['op_str']}")
    lines += ["", "Descriptor builder callers"]
    for row in r["builder_callers"]:
        lines.append(f"0x{row['site']:X} fn=0x{row['source_function']:X} {row['kind']}")
    lines += ["", "Loader callers"]
    for row in r["loader_callers"]:
        lines.append(f"0x{row['site']:X} fn=0x{row['source_function']:X} {row['kind']}")
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
    print(r["callback_token_roundtrip_status"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    print(f"C3C_WRITES={len(r['level_registry_plus_c3c_writes'])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
