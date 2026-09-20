#!/usr/bin/env python3
"""Locate producers of LuaClient transient normal/soft pickle blobs.

Proven immediately before this pass:
- LuaLevelClient +0x68 is the durable per-resource backing node.
- +0x70 / +0x78 are transient normal/soft pickle blobs.
- +0x80 is a third transient pointer cleared by the adjacent teardown path.
- 0x5A6C10 consumes +0x70/+0x78 through virtual restore slots +0x80/+0x88,
  frees them through the +0x68 allocator backing, and zeros the pointers.
- 0x5A6DD0 constructs the client with +0x68 and initially zeros +0x70/+0x78.
- 0x5A7720 is the proven live/backing transfer path.

This pass scans every runtime function in the version-locked executable for
actual writes to object offsets +0x70/+0x78/+0x80. Candidates are ranked using
corroborating accesses to +0x58/+0x68, known LuaClient vtable membership, and
call-graph proximity to the proven LuaClient / checkpoint / SoftPickle paths.

Static/read-only only. No process access and no save access.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

TRANSIENT = (0x70, 0x78, 0x80)
CORROBORATING = (0x58, 0x68)
TRACKED = CORROBORATING + TRANSIENT

ANCHORS = (
    0x5A6C10,  # consume normal/soft blobs
    0x5A6DD0,  # client ctor / durable backing attach
    0x5A7720,  # live/backing transfer
    0x463C60,  # pending-node prepare/cache
    0x464410,  # pending-node lookup/remove
    0x4654A0,  # LuaContext::CreateClient
    0x5AEC20, 0x5AEC40, 0x5AEC60,
    0x5AEF60, 0x5AEF90, 0x5AEFC0, 0x5AF01C, 0x5AF4E0,
    0x5B1030, 0x5AD4A0, 0x5AD8E0, 0x5AC760,
)

VTABLES = {
    "BaseLuaClient": 0xE03658,
    "LuaLevelClient": 0xE03F18,
    "LuaClient": 0xE04018,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_helper():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("lua_transient_producer_pe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capstone(repo: Path):
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_WRITE, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def u64(pe, rva: int):
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def decode_fn(pe, md, fn, OP_IMM, OP_MEM, RIP, AC_WRITE):
    off = pe.rva_to_file(fn["begin"])
    if off is None:
        return []
    raw = pe.data[off:off + fn["end"] - fn["begin"]]
    rows = []
    for ins in md.disasm(raw, IMAGE_BASE + fn["begin"]):
        mem = []
        imms = []
        for idx, op in enumerate(getattr(ins, "operands", [])):
            if op.type == OP_IMM:
                value = op.imm
                if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                    value -= IMAGE_BASE
                imms.append(value)
            elif op.type == OP_MEM:
                base = md.reg_name(op.mem.base) if op.mem.base else None
                item = {
                    "base": base,
                    "index": md.reg_name(op.mem.index) if op.mem.index else None,
                    "disp": op.mem.disp,
                    "size": op.size,
                    "operand_index": idx,
                    "write": bool(getattr(op, "access", 0) & AC_WRITE),
                }
                # Capstone occasionally leaves access unset. For common x86 write
                # forms, operand 0 is the destination, so retain a conservative
                # fallback rather than missing a producer.
                if not item["write"] and getattr(op, "access", 0) == 0 and idx == 0:
                    if ins.mnemonic in {
                        "mov", "movzx", "movsx", "movsxd", "lea", "xchg",
                        "add", "sub", "and", "or", "xor", "inc", "dec",
                        "shl", "shr", "sar", "rol", "ror",
                    }:
                        item["write"] = True
                if op.mem.base == RIP:
                    item["rip_target"] = ins.address + ins.size + op.mem.disp - IMAGE_BASE
                mem.append(item)
        rows.append({
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
            "mem": mem,
            "imms": imms,
        })
    return rows


def direct_calls(pe, rows):
    out = []
    for row in rows:
        if row["mnemonic"] not in ("call", "jmp") or not row["imms"]:
            continue
        target = row["imms"][0]
        if not isinstance(target, int):
            continue
        section = pe.section_for_rva(target)
        if not section or not section.get("exec"):
            continue
        tf = pe.function_for(target)
        out.append({
            "site": row["rva"],
            "target": target,
            "target_function": tf["begin"] if tf else None,
            "kind": row["mnemonic"],
        })
    return out


def tracked_hits(rows):
    hits = []
    for row in rows:
        for m in row["mem"]:
            base = m.get("base")
            if base in (None, "rsp", "rbp", "rip"):
                continue
            if m.get("disp") not in TRACKED:
                continue
            clear = (
                m.get("write")
                and row["mnemonic"] == "mov"
                and len(row["imms"]) > 0
                and row["imms"][-1] == 0
            )
            hits.append({
                "site": row["rva"],
                "offset": m["disp"],
                "base": base,
                "write": bool(m.get("write")),
                "clear": clear,
                "op": row["op_str"],
            })
    return hits


def context_windows(rows, sites, radius=7):
    by_site = {row["rva"]: i for i, row in enumerate(rows)}
    indices = set()
    for site in sites:
        idx = by_site.get(site)
        if idx is None:
            continue
        for j in range(max(0, idx - radius), min(len(rows), idx + radius + 1)):
            indices.add(j)
    return [rows[i] for i in sorted(indices)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe"))
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.exe.expanduser().resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")
    digest = sha256_file(exe)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"SHA mismatch: {digest}")

    repo = Path(__file__).resolve().parents[2]
    helper = load_helper()
    pe = helper.PE(exe.read_bytes())
    Cs, ARCH, MODE, AC_WRITE, OP_IMM, OP_MEM, RIP = load_capstone(repo)
    md = Cs(ARCH, MODE)
    md.detail = True

    vtable_targets = {}
    all_vtable_functions = set()
    for name, base in VTABLES.items():
        slots = []
        for index in range(40):
            slot = base + index * 8
            value = u64(pe, slot)
            target = None
            if value is not None and IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                candidate = value - IMAGE_BASE
                sec = pe.section_for_rva(candidate)
                if sec and sec.get("exec"):
                    target = candidate
                    fn = pe.function_for(candidate)
                    if fn:
                        all_vtable_functions.add(fn["begin"])
            slots.append({"index": index, "slot_rva": slot, "target_rva": target})
        vtable_targets[name] = slots

    anchor_functions = set()
    for anchor in ANCHORS:
        fn = pe.function_for(anchor)
        if fn:
            anchor_functions.add(fn["begin"])

    decoded = {}
    calls_by_function = {}
    callers = defaultdict(list)

    # One whole-executable pass builds both field evidence and the direct call graph.
    for fn in pe.runtime_functions:
        rows = decode_fn(pe, md, fn, OP_IMM, OP_MEM, RIP, AC_WRITE)
        if not rows:
            continue
        decoded[fn["begin"]] = rows
        calls = direct_calls(pe, rows)
        calls_by_function[fn["begin"]] = calls
        for call in calls:
            target_fn = call.get("target_function")
            if target_fn is not None:
                callers[target_fn].append({"caller": fn["begin"], "site": call["site"]})

    candidates = []
    for begin, rows in decoded.items():
        hits = tracked_hits(rows)
        transient_writes = [
            hit for hit in hits
            if hit["offset"] in TRANSIENT and hit["write"]
        ]
        if not transient_writes:
            continue

        nonclear_7078 = [
            hit for hit in transient_writes
            if hit["offset"] in (0x70, 0x78) and not hit["clear"]
        ]
        nonclear_80 = [
            hit for hit in transient_writes
            if hit["offset"] == 0x80 and not hit["clear"]
        ]
        accesses68 = any(hit["offset"] == 0x68 for hit in hits)
        accesses58 = any(hit["offset"] == 0x58 for hit in hits)

        calls = calls_by_function.get(begin, [])
        direct_anchor_calls = [
            call for call in calls
            if call.get("target_function") in anchor_functions or call.get("target") in ANCHORS
        ]
        called_by_anchor = [
            row for row in callers.get(begin, [])
            if row["caller"] in anchor_functions
        ]

        score = 0
        score += 20 * len(nonclear_7078)
        score += 12 * len(nonclear_80)
        score += 8 if accesses68 else 0
        score += 5 if accesses58 else 0
        score += 8 if begin in all_vtable_functions else 0
        score += 9 if direct_anchor_calls else 0
        score += 7 if called_by_anchor else 0

        # Pure zeroing in the known constructor/consumer/destructor paths is
        # evidence, but rank it below potential blob producers.
        if not nonclear_7078 and not nonclear_80:
            score -= 20

        fn = pe.function_for(begin)
        sites = [hit["site"] for hit in transient_writes]
        candidates.append({
            "begin": begin,
            "end": fn["end"] if fn else None,
            "score": score,
            "known_anchor": begin in anchor_functions,
            "lua_client_vtable_method": begin in all_vtable_functions,
            "hits": hits,
            "transient_writes": transient_writes,
            "direct_anchor_calls": direct_anchor_calls,
            "called_by_anchor": called_by_anchor,
            "callers": callers.get(begin, []),
            "calls": calls,
            "context": context_windows(rows, sites),
        })

    candidates.sort(key=lambda item: (
        -item["score"],
        item["begin"],
    ))

    report = {
        "schema": 1,
        "analysis": "lua_client_transient_blob_producers",
        "exe_sha256": digest,
        "tracked_offsets": list(TRACKED),
        "transient_offsets": list(TRANSIENT),
        "anchors": list(ANCHORS),
        "anchor_functions": sorted(anchor_functions),
        "vtables": vtable_targets,
        "candidate_count": len(candidates),
        "candidates": candidates,
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
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "Completionist Map - LuaClient transient blob producer scan",
        f"exe_sha256={digest}",
        f"candidate_count={len(candidates)}",
        "",
    ]
    for index, candidate in enumerate(candidates[:80], 1):
        lines.append(
            f"CANDIDATE {index:02d} score={candidate['score']} "
            f"0x{candidate['begin']:X}..0x{candidate['end']:X} "
            f"anchor={str(candidate['known_anchor']).lower()} "
            f"vtable={str(candidate['lua_client_vtable_method']).lower()}"
        )
        for hit in candidate["hits"]:
            mode = "WRITE" if hit["write"] else "READ"
            clear = " CLEAR" if hit["clear"] else ""
            lines.append(
                f"  {mode}{clear} 0x{hit['site']:X} +0x{hit['offset']:X} "
                f"base={hit['base']} {hit['op']}"
            )
        for call in candidate["direct_anchor_calls"]:
            lines.append(
                f"  ANCHOR_CALL 0x{call['site']:X} -> 0x{call['target']:X}"
            )
        for caller in candidate["called_by_anchor"]:
            lines.append(
                f"  CALLED_BY_ANCHOR 0x{caller['caller']:X}@0x{caller['site']:X}"
            )
        lines.append("  CONTEXT")
        for row in candidate["context"]:
            lines.append(
                f"    0x{row['rva']:08X} {row['bytes']:<24} "
                f"{row['mnemonic']:<8} {row['op_str']}"
            )
        lines.append("")

    lines.append(
        "SAFETY static_exe_read_only=true game_launched=false "
        "process_accessed=false save_opened=false save_written=false "
        "progression_written=false game_files_written=false"
    )
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    strong = sum(
        1 for candidate in candidates
        if any(
            hit["offset"] in (0x70, 0x78) and hit["write"] and not hit["clear"]
            for hit in candidate["transient_writes"]
        )
    )
    print(
        "LUA_CLIENT_TRANSIENT_BLOB_PRODUCER_SCAN_COMPLETE "
        f"candidates={len(candidates)} strong_7078={strong}"
    )
    print(
        "save_opened=false save_written=false progression_written=false "
        "game_launched=false"
    )


if __name__ == "__main__":
    main()
