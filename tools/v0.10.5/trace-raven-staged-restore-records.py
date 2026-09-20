#!/usr/bin/env python3
"""Prove the LuaClient +0x80 restore bridge and narrow staged WAD checkpoint storage.

Static/read-only analysis for the pinned God of War 2018 executable. This does
not open saves, launch/attach to the game, or write game/process state.

Goals:
1. Resolve vtable entries whose +0x80 slot is one of the known Lua restore
   implementations and prove those implementations call restore root 0x7E9550.
2. Record the exact +0x80 dispatch sites in 0x464EF0 and their argument setup.
3. Enumerate native references/readers/writers for the candidate checkpoint/WAD
   staging globals identified by the interrupted Astra pass.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import struct
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

DISPATCH_FUNCTION = 0x464EF0
DISPATCH_SITES = {
    0x465143: bytes.fromhex("ff9080000000"),
    0x4651E2: bytes.fromhex("ff9080000000"),
}
RESTORE_ROOT = 0x7E9550
RESTORE_IMPLS = {
    "base": 0x5A6C10,
    "level": 0x5AEC60,
    "lua": 0x5B2280,
}
RESTORE_ROOT_CALL_SITES = {
    0x5AECAD: RESTORE_ROOT,
    0x5B22C3: RESTORE_ROOT,
}

# Names are deliberately conservative until reader/writer ownership is proved.
STAGING_GLOBALS = {
    "candidate_checkpoint_block": 0x22C67D0,
    "candidate_wad_record_array": 0x22C7170,
    "candidate_wad_record_key_array": 0x22C7194,
    "candidate_wad_record_count": 0x22C696C,
    "candidate_wad_payload_base": 0x22C6940,
    "candidate_wad_payload_size": 0x22C6938,
}
FOCUS_FUNCTIONS = (
    0x464EF0,
    0x6687F0,
    0x669300,
    0x669B00,
    0x66ABD0,
    0x66C080,
    0x5AEC60,
    0x5B2280,
)

VTABLE_OFFSETS = (0x60, 0x70, 0x78, 0x80, 0x88)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_helper():
    p = Path(__file__).with_name("trace-checkpoint-restore-bridge.py")
    spec = importlib.util.spec_from_file_location("restore_bridge_pe", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper: {p}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fn_for(con, addr: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions "
        "WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (addr, addr),
    ).fetchone()
    if not row:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def read_target_rva(pe, rva: int):
    try:
        value = struct.unpack("<Q", pe.read(rva, 8))[0]
    except Exception:
        return None
    if IMAGE_BASE <= value < IMAGE_BASE + 0x80000000:
        return value - IMAGE_BASE
    return value


def query_refs(con, target: int):
    rip = [
        {"site": a, "src_fn": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site",
            (target,),
        )
    ]
    imm = [
        {"site": a, "src_fn": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM imm_refs WHERE value_rva=? ORDER BY site",
            (target,),
        )
    ]
    ptr = [
        x[0]
        for x in con.execute(
            "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva",
            (target,),
        )
    ]
    return {"rip": rip, "imm": imm, "data_ptrs": ptr}


def load_capstone(capstone_path: Path):
    sys.path.insert(0, str(capstone_path))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    return md, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def disassemble_range(md, pe, start: int, end: int, op_imm, op_mem, rip_reg):
    rows = []
    for ins in md.disasm(pe.read(start, end - start), IMAGE_BASE + start):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
            "rip_targets": [],
            "immediates": [],
        }
        for op in ins.operands:
            if op.type == op_imm:
                v = int(op.imm)
                if IMAGE_BASE <= v < IMAGE_BASE + 0x80000000:
                    v -= IMAGE_BASE
                row["immediates"].append(v)
            elif op.type == op_mem and op.mem.base == rip_reg:
                row["rip_targets"].append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        rows.append(row)
    return rows


def instruction_window(rows, site: int, radius: int = 8):
    for i, row in enumerate(rows):
        if row["rva"] == site:
            return rows[max(0, i - radius): min(len(rows), i + radius + 1)]
    return []


def function_rows(md, pe, con, addr: int, op_imm, op_mem, rip_reg):
    fn = fn_for(con, addr)
    if not fn:
        return None, []
    return fn, disassemble_range(md, pe, fn["begin"], fn["end"], op_imm, op_mem, rip_reg)


def executable_target(con, value):
    if not isinstance(value, int):
        return False
    return fn_for(con, value) is not None


def resolve_vtables(con, pe):
    out = []
    seen = set()
    for impl_name, impl in RESTORE_IMPLS.items():
        ptrs = [
            x[0]
            for x in con.execute(
                "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva",
                (impl,),
            )
        ]
        for loc in ptrs:
            base = loc - 0x80
            if base in seen:
                continue
            exact = read_target_rva(pe, base + 0x80)
            if exact != impl:
                continue
            slots = {}
            executable_count = 0
            for off in VTABLE_OFFSETS:
                value = read_target_rva(pe, base + off)
                is_exec = executable_target(con, value)
                executable_count += int(is_exec)
                slots[f"0x{off:X}"] = {"value_rva": value, "executable": is_exec}
            refs = query_refs(con, base)
            out.append({
                "vtable_rva": base,
                "restore_impl_name": impl_name,
                "restore_impl_rva": impl,
                "slot_0x80_ptr_location": loc,
                "executable_slots": executable_count,
                "slots": slots,
                "vtable_refs": refs,
            })
            seen.add(base)
    out.sort(key=lambda x: (-x["executable_slots"], x["vtable_rva"]))
    return out


def prove_restore_calls(md, pe, op_imm, op_mem, rip_reg):
    proofs = []
    for site, expected in RESTORE_ROOT_CALL_SITES.items():
        rows = disassemble_range(md, pe, site, site + 5, op_imm, op_mem, rip_reg)
        actual = None
        if rows and rows[0]["mnemonic"] == "call" and rows[0]["immediates"]:
            actual = rows[0]["immediates"][0]
        proofs.append({
            "site": site,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
            "instruction": rows[0] if rows else None,
        })
    return proofs


def analyze_globals(con, md, pe, op_imm, op_mem, rip_reg):
    report = {}
    owners = defaultdict(set)
    for name, target in STAGING_GLOBALS.items():
        refs = query_refs(con, target)
        detailed = []
        for ref in refs["rip"]:
            fn, rows = function_rows(md, pe, con, ref["src_fn"], op_imm, op_mem, rip_reg)
            win = instruction_window(rows, ref["site"], 7) if fn else []
            detailed.append({
                **ref,
                "function": fn,
                "window": win,
            })
            owners[ref["src_fn"]].add(name)
        report[name] = {
            "rva": target,
            "refs": refs,
            "rip_ref_details": detailed,
        }
    owner_summary = []
    for fn, names in owners.items():
        owner_summary.append({
            "function": fn_for(con, fn),
            "globals": sorted(names),
            "global_count": len(names),
        })
    owner_summary.sort(key=lambda x: (-x["global_count"], x["function"]["begin"] if x["function"] else 0))
    return report, owner_summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--capstone-path", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    digest = sha256_file(args.exe).lower()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {digest}")

    helper = load_pe_helper()
    pe = helper.PE(args.exe.read_bytes())
    md, op_imm, op_mem, rip_reg = load_capstone(args.capstone_path)

    con = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    try:
        # Exact dispatch-site byte assertions.
        dispatch_assertions = []
        for site, expected in DISPATCH_SITES.items():
            actual = pe.read(site, len(expected))
            dispatch_assertions.append({
                "site": site,
                "expected_hex": expected.hex(),
                "actual_hex": actual.hex(),
                "passed": actual == expected,
            })
            if actual != expected:
                raise RuntimeError(f"dispatch bytes changed at 0x{site:X}")

        dispatch_fn, dispatch_rows = function_rows(
            md, pe, con, DISPATCH_FUNCTION, op_imm, op_mem, rip_reg
        )
        dispatch_windows = {
            f"0x{site:X}": instruction_window(dispatch_rows, site, 12)
            for site in DISPATCH_SITES
        }

        vtables = resolve_vtables(con, pe)
        restore_call_proofs = prove_restore_calls(md, pe, op_imm, op_mem, rip_reg)
        globals_report, global_owners = analyze_globals(
            con, md, pe, op_imm, op_mem, rip_reg
        )

        focus = {}
        for addr in FOCUS_FUNCTIONS:
            fn, rows = function_rows(md, pe, con, addr, op_imm, op_mem, rip_reg)
            if fn:
                focus[f"0x{fn['begin']:X}"] = {
                    "function": fn,
                    "candidate_global_hits": [
                        row for row in rows
                        if any(t in STAGING_GLOBALS.values() for t in row["rip_targets"])
                    ],
                }

        bridge_pass = bool(vtables) and all(x["passed"] for x in restore_call_proofs)
        result = {
            "schema": 1,
            "analysis": "raven_staged_restore_records",
            "exe_sha256": digest,
            "dispatch_assertions": dispatch_assertions,
            "dispatch_function": dispatch_fn,
            "dispatch_windows": dispatch_windows,
            "restore_vtables": vtables,
            "restore_root_call_proofs": restore_call_proofs,
            "restore_bridge_status": "PASS" if bridge_pass else "BLOCKED",
            "staging_globals": globals_report,
            "staging_global_owners": global_owners,
            "focus": focus,
            "safety": {
                "static_only": True,
                "game_launched": False,
                "process_opened": False,
                "save_opened": False,
                "save_written": False,
                "progression_written": False,
                "game_files_written": False,
            },
        }
    finally:
        con.close()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - Raven staged restore record trace",
        f"exe_sha256={digest}",
        "mode=static read-only",
        f"restore_bridge_status={result['restore_bridge_status']}",
        "",
        "LUA RESTORE VTABLES",
    ]
    if not vtables:
        lines.append("  none resolved")
    for v in vtables:
        lines.append(
            f"  vtable=0x{v['vtable_rva']:X} +0x80=0x{v['restore_impl_rva']:X} "
            f"impl={v['restore_impl_name']} executable_slots={v['executable_slots']}"
        )
        for off, s in v["slots"].items():
            val = s["value_rva"]
            lines.append(
                f"    {off} -> {('0x%X' % val) if isinstance(val,int) else 'none'} "
                f"exec={str(s['executable']).lower()}"
            )
        for kind in ("rip", "imm"):
            for ref in v["vtable_refs"][kind][:12]:
                lines.append(
                    f"    VTABLE_REF {kind} site=0x{ref['site']:X} fn=0x{ref['src_fn']:X} {ref['mnemonic']}"
                )
    lines += ["", "RESTORE ROOT CALL PROOFS"]
    for p in restore_call_proofs:
        lines.append(
            f"  site=0x{p['site']:X} actual={('0x%X' % p['actual']) if p['actual'] is not None else 'none'} "
            f"expected=0x{p['expected']:X} pass={str(p['passed']).lower()}"
        )
    lines += ["", "DISPATCH +0x80 WINDOWS"]
    for site, rows in dispatch_windows.items():
        lines.append(f"  SITE {site}")
        for row in rows:
            mark = " <== +0x80" if row["rva"] in DISPATCH_SITES else ""
            lines.append(
                f"    0x{row['rva']:08X} {row['bytes']:<18} {row['mnemonic']:<8} {row['op_str']}{mark}"
            )

    lines += ["", "STAGED RECORD GLOBAL OWNERS"]
    for owner in global_owners[:80]:
        fn = owner["function"]
        if not fn:
            continue
        lines.append(
            f"  fn=0x{fn['begin']:X}..0x{fn['end']:X} globals={owner['global_count']} "
            + ",".join(owner["globals"])
        )
    lines += ["", "GLOBAL REFERENCES"]
    for name, item in globals_report.items():
        lines.append(f"  {name}=0x{item['rva']:X} rip_refs={len(item['refs']['rip'])}")
        for d in item["rip_ref_details"][:40]:
            lines.append(
                f"    REF site=0x{d['site']:X} fn=0x{d['src_fn']:X} {d['mnemonic']}"
            )
            for row in d["window"]:
                lines.append(
                    f"      0x{row['rva']:08X} {row['bytes']:<18} {row['mnemonic']:<8} {row['op_str']}"
                )

    lines += [
        "",
        "SAFETY static_only=true game_launched=false process_opened=false save_opened=false "
        "save_written=false progression_written=false game_files_written=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"RAVEN_STAGED_RESTORE_RECORDS_COMPLETE bridge={result['restore_bridge_status']} "
        f"vtables={len(vtables)} owners={len(global_owners)}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
