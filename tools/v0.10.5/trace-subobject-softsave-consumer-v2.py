#!/usr/bin/env python3
"""Precise native trace of GoW SubObject SoftSave consumers.

This supersedes the section-linear dirty-bit scan. It disassembles only PE
runtime-function ranges, preserving instruction alignment.

Anchors:
- game.SubObject.SoftSave Lua binding: RVA 0x948280
- native LuaSubObjectClient resolver: RVA 0x5443E0
- dirty flag set by SoftSave: byte [client + 0x58] |= 0x10
- callback literals: OnSaveCheckpoint / OnRestoreCheckpoint

The report correlates functions that:
1. access non-stack memory at displacement +0x58;
2. use immediate bit 0x10 in the same instruction/function;
3. directly call/jump to 0x5443E0;
4. RIP-reference the checkpoint callback strings;
5. call functions in any of those anchor sets.

Read-only, version-locked, no game/save/process access.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SOFTSAVE_BINDING = 0x948280
CLIENT_RESOLVER = 0x5443E0
DIRTY_DISP = 0x58
DIRTY_BIT = 0x10
CALLBACK_NAMES = ("OnSaveCheckpoint", "OnRestoreCheckpoint")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_helper():
    p = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("softsave_consumer_pe", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_capstone(repo: Path):
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def find_ascii_rva(pe, text: str) -> list[int]:
    needle = text.encode("ascii") + b"\0"
    out = []
    pos = 0
    while True:
        off = pe.data.find(needle, pos)
        if off < 0:
            break
        rva = pe.file_to_rva(off)
        if rva is not None:
            out.append(rva)
        pos = off + 1
    return out


def decode_function(pe, md, fn, OP_IMM, OP_MEM, RIP):
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        return []
    raw = pe.data[off:off + fn["end"] - fn["begin"]]
    rows = []
    for ins in md.disasm(raw, IMAGE_BASE + fn["begin"]):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
            "mem": [],
            "immediates": [],
        }
        for op in getattr(ins, "operands", []):
            if op.type == OP_IMM:
                val = op.imm
                if IMAGE_BASE <= val < IMAGE_BASE + pe.size_of_image:
                    val -= IMAGE_BASE
                row["immediates"].append(val)
            elif op.type == OP_MEM:
                item = {
                    "base": md.reg_name(op.mem.base) if op.mem.base else None,
                    "index": md.reg_name(op.mem.index) if op.mem.index else None,
                    "segment": md.reg_name(op.mem.segment) if op.mem.segment else None,
                    "scale": op.mem.scale,
                    "disp": op.mem.disp,
                    "size": op.size,
                }
                if op.mem.base == RIP:
                    item["rip_target_rva"] = ins.address + ins.size + op.mem.disp - IMAGE_BASE
                row["mem"].append(item)
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.exe.expanduser().resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")
    digest = sha256_file(exe)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA256 mismatch: {digest}")

    repo = Path(__file__).resolve().parents[2]
    helper = load_helper()
    pe = helper.PE(exe.read_bytes())
    Cs, ARCH, MODE, OP_IMM, OP_MEM, RIP = load_capstone(repo)
    md = Cs(ARCH, MODE)
    md.detail = True

    callback_rvas = {name: find_ascii_rva(pe, name) for name in CALLBACK_NAMES}
    callback_rva_set = {rva for vals in callback_rvas.values() for rva in vals}

    functions = {}
    direct_edges = []
    dirty_functions = set()
    resolver_callers = set()
    callback_ref_functions = set()

    for fn in pe.runtime_functions:
        rows = decode_function(pe, md, fn, OP_IMM, OP_MEM, RIP)
        if not rows:
            continue
        begin = fn["begin"]
        rec = {
            "begin": begin,
            "end": fn["end"],
            "dirty_hits": [],
            "resolver_sites": [],
            "callback_refs": [],
            "calls": [],
        }
        for row in rows:
            # Exclude stack/TLS false positives from +0x58.
            for mem in row["mem"]:
                base = mem.get("base")
                seg = mem.get("segment")
                if (
                    mem.get("disp") == DIRTY_DISP
                    and base not in ("rsp", "rbp", "rip")
                    and seg not in ("gs", "fs")
                ):
                    has_bit = DIRTY_BIT in row["immediates"] or "0x10" in row["op_str"].lower()
                    score = 1
                    if row["mnemonic"] in ("test", "and", "or", "cmp"):
                        score += 3
                    if has_bit:
                        score += 10
                    rec["dirty_hits"].append({
                        "rva": row["rva"],
                        "bytes": row["bytes"],
                        "mnemonic": row["mnemonic"],
                        "op_str": row["op_str"],
                        "base": base,
                        "size": mem.get("size"),
                        "has_bit_0x10": has_bit,
                        "score": score,
                    })
                    dirty_functions.add(begin)

            # Direct branch/call edges.
            if row["mnemonic"] in ("call", "jmp") and row["immediates"]:
                target = row["immediates"][0]
                if isinstance(target, int):
                    sec = pe.section_for_rva(target)
                    if sec and sec.get("exec"):
                        edge = {
                            "from": begin,
                            "site": row["rva"],
                            "kind": row["mnemonic"],
                            "to": target,
                        }
                        direct_edges.append(edge)
                        rec["calls"].append(edge)
                        if target == CLIENT_RESOLVER:
                            rec["resolver_sites"].append(row["rva"])
                            resolver_callers.add(begin)

            # RIP refs to callback strings.
            for mem in row["mem"]:
                rv = mem.get("rip_target_rva")
                if rv in callback_rva_set:
                    names = [name for name, vals in callback_rvas.items() if rv in vals]
                    rec["callback_refs"].append({
                        "site": row["rva"],
                        "target_rva": rv,
                        "names": names,
                        "mnemonic": row["mnemonic"],
                        "op_str": row["op_str"],
                    })
                    callback_ref_functions.add(begin)

        if rec["dirty_hits"] or rec["resolver_sites"] or rec["callback_refs"]:
            functions[begin] = rec

    # Build exact caller maps from runtime-function-aligned edges.
    callers = defaultdict(set)
    for edge in direct_edges:
        target_fn = pe.function_for(edge["to"])
        if target_fn is not None:
            callers[target_fn["begin"]].add(edge["from"])

    anchor_sets = {
        "dirty": set(dirty_functions),
        "resolver_callers": set(resolver_callers),
        "callback_refs": set(callback_ref_functions),
    }

    # Include one-hop callers of any anchor function.
    one_hop = set()
    for aset in anchor_sets.values():
        for fn_begin in aset:
            one_hop.update(callers.get(fn_begin, set()))

    candidate_begins = set().union(*anchor_sets.values(), one_hop)
    candidate_rows = []
    for begin in sorted(candidate_begins):
        fn = pe.function_for(begin)
        if fn is None:
            continue
        rows = decode_function(pe, md, fn, OP_IMM, OP_MEM, RIP)
        dirty = []
        cbrefs = []
        resolver_sites = []
        calls = []
        for row in rows:
            for mem in row["mem"]:
                base = mem.get("base")
                seg = mem.get("segment")
                if mem.get("disp") == DIRTY_DISP and base not in ("rsp", "rbp", "rip") and seg not in ("gs", "fs"):
                    has_bit = DIRTY_BIT in row["immediates"] or "0x10" in row["op_str"].lower()
                    dirty.append({
                        "rva": row["rva"], "bytes": row["bytes"], "mnemonic": row["mnemonic"],
                        "op_str": row["op_str"], "base": base, "size": mem.get("size"),
                        "has_bit_0x10": has_bit,
                    })
                rv = mem.get("rip_target_rva")
                if rv in callback_rva_set:
                    cbrefs.append({
                        "site": row["rva"],
                        "target_rva": rv,
                        "names": [name for name, vals in callback_rvas.items() if rv in vals],
                        "mnemonic": row["mnemonic"],
                        "op_str": row["op_str"],
                    })
            if row["mnemonic"] in ("call", "jmp") and row["immediates"]:
                target = row["immediates"][0]
                if isinstance(target, int):
                    sec = pe.section_for_rva(target)
                    if sec and sec.get("exec"):
                        calls.append({"site": row["rva"], "kind": row["mnemonic"], "to": target})
                        if target == CLIENT_RESOLVER:
                            resolver_sites.append(row["rva"])

        labels = []
        if begin in dirty_functions:
            labels.append("dirty_access")
        if begin in resolver_callers:
            labels.append("calls_client_resolver")
        if begin in callback_ref_functions:
            labels.append("references_checkpoint_callback")
        for name, aset in anchor_sets.items():
            if any(begin in callers.get(x, set()) for x in aset):
                labels.append("caller_of_" + name)

        score = 0
        score += 10 * sum(1 for x in dirty if x["has_bit_0x10"])
        score += 3 * len(dirty)
        score += 15 * len(cbrefs)
        score += 8 * len(resolver_sites)
        score += 2 * sum(1 for x in labels if x.startswith("caller_of_"))

        candidate_rows.append({
            "begin": begin,
            "end": fn["end"],
            "score": score,
            "labels": sorted(set(labels)),
            "dirty_hits": dirty,
            "callback_refs": cbrefs,
            "resolver_sites": resolver_sites,
            "calls": calls,
            "instructions": rows,
        })

    candidate_rows.sort(key=lambda x: (-x["score"], x["begin"]))

    report = {
        "schema": 2,
        "analysis": "subobject_softsave_consumer_precise",
        "exe_sha256": digest,
        "softsave_binding_rva": SOFTSAVE_BINDING,
        "client_resolver_rva": CLIENT_RESOLVER,
        "dirty_field_offset": DIRTY_DISP,
        "dirty_bit": DIRTY_BIT,
        "callback_rvas": callback_rvas,
        "runtime_function_count": len(pe.runtime_functions),
        "dirty_function_count": len(dirty_functions),
        "resolver_caller_count": len(resolver_callers),
        "callback_ref_function_count": len(callback_ref_functions),
        "dirty_functions": sorted(dirty_functions),
        "resolver_callers": sorted(resolver_callers),
        "callback_ref_functions": sorted(callback_ref_functions),
        "candidates": candidate_rows,
        "safety": {
            "static_exe_read_only": True,
            "game_launched": False,
            "process_accessed": False,
            "save_opened": False,
            "save_written": False,
            "progression_written": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - precise SubObject SoftSave consumer trace",
        f"exe_sha256={digest}",
        f"runtime_functions={len(pe.runtime_functions)}",
        f"dirty_functions={len(dirty_functions)} resolver_callers={len(resolver_callers)} callback_ref_functions={len(callback_ref_functions)}",
        "callback_rvas=" + ", ".join(
            f"{name}:" + "/".join(f"0x{x:X}" for x in vals) for name, vals in callback_rvas.items()
        ),
        "",
        "TOP CANDIDATES",
    ]
    for c in candidate_rows[:40]:
        lines.append(
            f"FUNCTION 0x{c['begin']:X}..0x{c['end']:X} score={c['score']} "
            f"labels={','.join(c['labels']) or '-'}"
        )
        for h in c["dirty_hits"]:
            lines.append(
                f"  DIRTY 0x{h['rva']:X} {h['bytes']:<20} {h['mnemonic']} {h['op_str']} "
                f"bit10={str(h['has_bit_0x10']).lower()} base={h['base']}"
            )
        for x in c["resolver_sites"]:
            lines.append(f"  RESOLVER_CALL site=0x{x:X} -> 0x{CLIENT_RESOLVER:X}")
        for x in c["callback_refs"]:
            lines.append(
                f"  CALLBACK_REF site=0x{x['site']:X} names={','.join(x['names'])} "
                f"{x['mnemonic']} {x['op_str']}"
            )
        for e in c["calls"][:40]:
            lines.append(f"  EDGE 0x{e['site']:X} {e['kind']} -> 0x{e['to']:X}")
        lines.append("")

    lines.extend([
        "ANCHOR SETS",
        "dirty=" + ",".join(f"0x{x:X}" for x in sorted(dirty_functions)),
        "resolver_callers=" + ",".join(f"0x{x:X}" for x in sorted(resolver_callers)),
        "callback_ref_functions=" + ",".join(f"0x{x:X}" for x in sorted(callback_ref_functions)),
        "",
        "SAFETY static_exe_read_only=true game_launched=false process_accessed=false "
        "save_opened=false save_written=false progression_written=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "SUBOBJECT_SOFTSAVE_CONSUMER_PRECISE_COMPLETE "
        f"dirtyFunctions={len(dirty_functions)} resolverCallers={len(resolver_callers)} "
        f"callbackRefs={len(callback_ref_functions)} candidates={len(candidate_rows)}"
    )
    print("save_opened=false save_written=false progression_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
