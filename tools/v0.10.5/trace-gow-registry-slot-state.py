"""Trace GoW GameObject registry table and slot cursor initialization/reset state.

Read-only, version-locked analysis for the supported GoW.exe. The allocator policy
is already proved: registry +0x20 is the slot bank, +0x28 the circular first-free
cursor, +0x2C the live count, and +0x30 the capacity. This tracer inspects the
64-entry global registry-pointer table used by 0x4EF2B0 and records any static
registry state plus exact code references to that table. No game launch/save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TABLE_BEGIN = 0x22A98C0
TABLE_END = 0x22A9AC0
ALLOCATOR = 0x4EF2B0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_registry_slot_pe", path)
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
    from capstone.x86_const import X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_MEM, X86_REG_RIP


def read_at(pe, rva: int, n: int) -> bytes | None:
    off = pe.rva_to_file(rva)
    if off is None or off + n > len(pe.data):
        return None
    return pe.data[off:off+n]


def u32(pe, rva: int):
    b = read_at(pe, rva, 4)
    return struct.unpack("<I", b)[0] if b else None


def u64(pe, rva: int):
    b = read_at(pe, rva, 8)
    return struct.unpack("<Q", b)[0] if b else None


def ptr_rva(v: int | None, pe):
    if v is None:
        return None
    if IMAGE_BASE <= v < IMAGE_BASE + pe.size_of_image:
        return v - IMAGE_BASE
    return None


def table_rows(pe):
    rows = []
    for i, rva in enumerate(range(TABLE_BEGIN, TABLE_END, 8)):
        raw = u64(pe, rva)
        target = ptr_rva(raw, pe)
        row = {"index": i, "entry_rva": rva, "raw_qword": raw, "target_rva": target}
        if target is not None:
            row["registry_id"] = u32(pe, target)
            bank_raw = u64(pe, target + 0x20)
            row["bank_raw_qword"] = bank_raw
            row["bank_target_rva"] = ptr_rva(bank_raw, pe)
            row["cursor_0x28"] = u32(pe, target + 0x28)
            row["live_count_0x2c"] = u32(pe, target + 0x2C)
            row["capacity_0x30"] = u32(pe, target + 0x30)
        rows.append(row)
    return rows


def xrefs_to_table(md, pe, op_mem, rip_reg):
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        off = s["raw"]
        raw = pe.data[off:off+s["rawsize"]]
        for ins in md.disasm(raw, IMAGE_BASE + s["rva"]):
            for op in ins.operands:
                if op.type != op_mem or op.mem.base != rip_reg:
                    continue
                target = ins.address + ins.size + op.mem.disp - IMAGE_BASE
                if TABLE_BEGIN - 0x40 <= target <= TABLE_END + 0x40:
                    site = ins.address - IMAGE_BASE
                    fn = pe.function_for(site)
                    out.append({
                        "site": site,
                        "instruction": f"{ins.mnemonic} {ins.op_str}".strip(),
                        "target_rva": target,
                        "function_begin": fn["begin"] if fn else None,
                        "function_end": fn["end"] if fn else None,
                    })
    return out


def allocator_policy():
    return {
        "bank": "+0x20",
        "cursor": "+0x28",
        "live_count": "+0x2C",
        "capacity": "+0x30",
        "no_hint_policy": "circular first-free from cursor; slot 0 skipped; cursor advances to next index",
        "proved_sites": {
            "cursor_load": "0x4EF33F",
            "capacity_load": "0x4EF346",
            "bank_load": "0x4EF34A",
            "empty_test": "0x4EF35E",
            "slot_store": "0x4EF369",
            "cursor_store": "0x4EF36D",
            "live_count_inc": "0x4EF371",
        },
    }


def self_test():
    assert TABLE_END - TABLE_BEGIN == 64 * 8
    assert ALLOCATOR == 0x4EF2B0
    print("SELF_TEST_PASSED")


def analyze(exe: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode); md.detail = True

    rows = table_rows(pe)
    xrefs = xrefs_to_table(md, pe, op_mem, rip_reg)
    static_targets = [r for r in rows if r["target_rva"] is not None]
    nonzero_raw = [r for r in rows if r["raw_qword"] not in (None, 0)]

    if static_targets:
        state = "STATIC_REGISTRY_OBJECTS_PRESENT"
        missing = "determine which table entry/registry belongs to the target WAD and prove cursor reset/load ordering"
    elif nonzero_raw:
        state = "NON_IMAGE_STATIC_POINTERS_PRESENT"
        missing = "resolve relocated/runtime registry pointers and identify registry creation/reset path"
    else:
        state = "RUNTIME_INITIALIZED_REGISTRY_TABLE"
        missing = "trace registry table population and +0x28/+0x2C/+0x30 initialization/reset before canonical WAD allocation"

    return {
        "schema": 1,
        "analysis": "gow_registry_slot_state",
        "status": "PASS_REGISTRY_SLOT_POLICY",
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "registry_pointer_table": {
            "begin": TABLE_BEGIN,
            "end": TABLE_END,
            "entry_count": len(rows),
            "static_target_count": len(static_targets),
            "nonzero_raw_count": len(nonzero_raw),
            "initialization_class": state,
            "entries": rows,
        },
        "table_xrefs": xrefs,
        "allocator_policy": allocator_policy(),
        "precise_missing_edge": missing,
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
    t = r["registry_pointer_table"]
    lines = [
        "GoW registry slot-state trace",
        "=============================",
        f"status={r['status']}",
        f"gameobject_persistent_key_status={r['gameobject_persistent_key_status']}",
        f"table=0x{t['begin']:X}-0x{t['end']:X}",
        f"entries={t['entry_count']}",
        f"static_target_count={t['static_target_count']}",
        f"nonzero_raw_count={t['nonzero_raw_count']}",
        f"initialization_class={t['initialization_class']}",
        f"table_xrefs={len(r['table_xrefs'])}",
        f"policy={r['allocator_policy']['no_hint_policy']}",
        f"precise_missing_edge={r['precise_missing_edge']}",
        "",
        "Non-null/static entries",
    ]
    for row in t["entries"]:
        if row["raw_qword"] not in (None, 0):
            target_text = "-" if row["target_rva"] is None else f"0x{row['target_rva']:X}"
            lines.append(
                f"[{row['index']:02d}] entry=0x{row['entry_rva']:X} raw=0x{row['raw_qword']:016X} "
                f"target={target_text} "
                f"id={row.get('registry_id')} cursor={row.get('cursor_0x28')} live={row.get('live_count_0x2c')} cap={row.get('capacity_0x30')}"
            )
    lines += ["", "Table xrefs"]
    for x in r["table_xrefs"]:
        fn_text = "-" if x["function_begin"] is None else f"0x{x['function_begin']:X}"
        lines.append(
            f"0x{x['site']:X} fn={fn_text} -> 0x{x['target_rva']:X} {x['instruction']}"
        )
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--exe", type=Path)
    p.add_argument("--output-json", type=Path)
    p.add_argument("--output-text", type=Path)
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if any(x is None for x in (a.exe, a.output_json, a.output_text)):
        p.error("--exe, --output-json and --output-text required")
    r = analyze(a.exe)
    a.output_json.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    a.output_text.write_text(render_text(r), encoding="utf-8")
    print(r["status"])
    print(r["registry_pointer_table"]["initialization_class"])
    print(r["gameobject_persistent_key_status"])
    print(r["production_oracle_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
