"""Focused read-only disassembly probe for the v0.10.4 WAD loader gate.

The broad bookkeeping pass identified several candidate functions but its
ranking intentionally used weak displacement heuristics.  This follow-up keeps
only pinned GoW.exe static analysis and records complete instruction streams for
specific resource/WAD functions, exact direct-call sites, RIP-relative strings,
and stronger same-base offset patterns.

No game file, save, boot option, or process is modified.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE_TOOL = HERE / "inspect-wad-loader-bookkeeping.py"
spec = importlib.util.spec_from_file_location("wad_bookkeeping", BASE_TOOL)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load bookkeeping module")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

EXPECTED_EXE = base.EXPECTED_EXE
BASE = base.BASE

# Functions selected from the first broad pass.  Labels are hypotheses unless
# already proven by the previous registry work.
FOCUS = {
    0x617A50: "candidate WAD/resource metadata constructor; builds +0x78 hash array",
    0x610265: "candidate resource-name lookup using object +0x78 map",
    0x672890: "proven WAD_R_UI setup containing GOPool preallocation loop",
    0x67C800: "startup caller that reaches WAD_R_UI setup",
    0x750920: "proven general resource lookup path",
    0x423100: "proven resource resolver by folded name/hash",
    0x60DD80: "proven pool add/capacity clone",
    0x60EDA0: "proven pool checkout",
    0x4C8880: "direct caller candidate around generic pool/resource setup",
    0x615130: "direct caller candidate around resource/pool setup",
}
ROOT_OFFSETS = {0x1C, 0x20, 0x28}
NAME_MAP_OFFSET = 0x78
RIG_KEYS = {0x10001, 0x20001, 0x30001, 0x40001}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def printable_at(pe: base.PeImage, rva: int, limit: int = 160):
    try:
        raw = pe.read(rva, limit)
    except Exception:
        # Near a section end, progressively shorten the request.
        raw = None
        for n in (96, 64, 32, 16):
            try:
                raw = pe.read(rva, n)
                break
            except Exception:
                pass
        if raw is None:
            return None
    end = raw.find(b"\0")
    if end < 0:
        end = len(raw)
    chunk = raw[:end]
    if len(chunk) < 4:
        return None
    if not all(0x20 <= b < 0x7F or b in (9, 10, 13) for b in chunk):
        return None
    try:
        return chunk.decode("ascii")
    except UnicodeDecodeError:
        return None


def parse_functions(pe: base.PeImage):
    funcs = pe.runtime_functions()
    ranges = {start: end for start, end in funcs}
    return funcs, ranges


def direct_target(insn):
    import capstone
    from capstone.x86_const import X86_OP_IMM
    if insn.mnemonic not in ("call", "jmp") or not insn.operands:
        return None
    op = insn.operands[0]
    if op.type != X86_OP_IMM:
        return None
    value = op.imm
    return value - BASE if value >= BASE else None


def instruction_record(md, pe, insn):
    import capstone
    from capstone.x86_const import X86_OP_MEM, X86_REG_RIP
    rec = {
        "rva": f"0x{insn.address - BASE:X}",
        "bytes": bytes(insn.bytes).hex(),
        "mnemonic": insn.mnemonic,
        "op_str": insn.op_str,
    }
    target = direct_target(insn)
    if target is not None:
        rec["direct_target_rva"] = f"0x{target:X}"
    mem = []
    for index, op in enumerate(insn.operands):
        if op.type != X86_OP_MEM:
            continue
        item = {
            "operand": index,
            "base": md.reg_name(op.mem.base) if op.mem.base else None,
            "index": md.reg_name(op.mem.index) if op.mem.index else None,
            "scale": op.mem.scale,
            "disp": op.mem.disp,
        }
        if op.mem.base == X86_REG_RIP:
            target_rva = insn.address + insn.size + op.mem.disp - BASE
            item["rip_target_rva"] = f"0x{target_rva:X}"
            text = printable_at(pe, target_rva)
            if text is not None:
                item["ascii"] = text
        mem.append(item)
    if mem:
        rec["memory"] = mem
    return rec


def disassemble_function(pe, md, start: int, end: int):
    code = pe.read(start, end - start)
    return [instruction_record(md, pe, insn) for insn in md.disasm(code, BASE + start)]


def scan_all(pe, md, funcs):
    """Collect exact direct callers and stronger structural candidates."""
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM

    callers = collections.defaultdict(list)
    structural = []
    for start, end in funcs:
        try:
            code = pe.read(start, end - start)
        except ValueError:
            continue
        per_base = collections.defaultdict(set)
        writes_per_base = collections.defaultdict(set)
        imms = set()
        hash_mult = False
        stride12 = False
        direct_calls = set()
        for insn in md.disasm(code, BASE + start):
            target = direct_target(insn)
            if target is not None:
                direct_calls.add(target)
                callers[target].append({"caller_rva": f"0x{start:X}", "site_rva": f"0x{insn.address - BASE:X}"})
            if insn.mnemonic == "imul" and "0x401" in insn.op_str.lower():
                hash_mult = True
            if insn.mnemonic in ("add", "sub", "imul") and "0xc" in insn.op_str.lower():
                stride12 = True
            for op_idx, op in enumerate(insn.operands):
                if op.type == X86_OP_IMM:
                    value = op.imm
                    if value in ROOT_OFFSETS | RIG_KEYS | {0xC, 0x60, 0x78, 0x401, 6}:
                        imms.add(value)
                elif op.type == X86_OP_MEM and op.mem.base:
                    reg = md.reg_name(op.mem.base)
                    if op.mem.disp in ROOT_OFFSETS | {NAME_MAP_OFFSET}:
                        per_base[reg].add(op.mem.disp)
                        if op_idx == 0:
                            writes_per_base[reg].add(op.mem.disp)
        same_base_root = [reg for reg, ds in per_base.items() if ROOT_OFFSETS <= ds]
        name_map_write_bases = [reg for reg, ds in writes_per_base.items() if NAME_MAP_OFFSET in ds]
        score = 0
        reasons = []
        if same_base_root:
            score += 20
            reasons.append("same register base accesses +0x1C,+0x20,+0x28")
        if stride12:
            score += 5
            reasons.append("contains arithmetic stride 0xC")
        if hash_mult:
            score += 5
            reasons.append("contains folded-name hash multiplier 0x401")
        if name_map_write_bases:
            score += 8
            reasons.append("writes object offset +0x78")
        rig_hits = sorted(RIG_KEYS & imms)
        if rig_hits:
            score += 2 * len(rig_hits)
            reasons.append("references rig type key immediate(s)")
        if score:
            structural.append({
                "start_rva": f"0x{start:X}",
                "end_rva": f"0x{end:X}",
                "bytes": end - start,
                "score": score,
                "reasons": reasons,
                "same_base_root_registers": same_base_root,
                "name_map_write_registers": name_map_write_bases,
                "interesting_immediates": [f"0x{x:X}" for x in sorted(imms)],
                "direct_calls": [f"0x{x:X}" for x in sorted(direct_calls)],
            })
    structural.sort(key=lambda x: (-x["score"], int(x["start_rva"], 16)))
    return callers, structural[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--python-module-dir", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.python_module_dir:
        sys.path.insert(0, str(args.python_module_dir.resolve()))
    import capstone

    game = args.game_root.resolve()
    exe_path = game / "GoW.exe"
    raw = exe_path.read_bytes()
    check(sha(raw) == EXPECTED_EXE, "GoW.exe is not the pinned build")
    out = args.output.resolve()
    allowed = (HERE.parent.parent / "archive" / "field-logs").resolve()
    check(out.is_relative_to(allowed) and out.suffix.lower() == ".json", "output must be repo archive/field-logs JSON")
    check(not out.is_relative_to(game), "output must stay outside the game tree")

    pe = base.PeImage(raw)
    check(pe.image_base == BASE, "unexpected image base")
    funcs, ranges = parse_functions(pe)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    callers, structural = scan_all(pe, md, funcs)

    focus = []
    for rva, label in FOCUS.items():
        start = rva if rva in ranges else base.function_for_rva([x for x, _ in funcs], ranges, rva)
        check(start is not None, f"focus RVA is outside runtime function table: {rva:#x}")
        end = ranges[start]
        focus.append({
            "requested_rva": f"0x{rva:X}",
            "label": label,
            "function_start_rva": f"0x{start:X}",
            "function_end_rva": f"0x{end:X}",
            "bytes": end - start,
            "direct_callers": callers.get(start, []),
            "instructions": disassemble_function(pe, md, start, end),
        })

    result = {
        "result": "READ_ONLY_WAD_LOADER_FOCUS_DISASSEMBLY",
        "game_files_written": False,
        "save_files_written": False,
        "runtime_test_ready": False,
        "source_sha256": sha(raw),
        "capstone_version": capstone.__version__,
        "runtime_function_count": len(funcs),
        "focus_functions": focus,
        "same_base_structural_candidates": structural,
        "interpretation": {
            "focus_labels_are_hypotheses_unless_marked_proven": True,
            "same_base_scoring_is_a_search_aid_not_semantic_proof": True,
            "next_gate": "Manually trace the focused constructor/callers and pin exact instructions that consume WAD root type rows and build the resource name map.",
        },
    }
    check(sha(exe_path.read_bytes()) == EXPECTED_EXE, "GoW.exe changed during scan")
    result["source_hash_unchanged_after_scan"] = True
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "focus_functions": len(focus),
        "structural_candidates": len(structural),
        "runtime_test_ready": False,
        "output": str(out),
    }, indent=2))
    print("No game files, saves, boot options, or progression state were modified.")


if __name__ == "__main__":
    main()
