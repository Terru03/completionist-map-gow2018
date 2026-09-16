"""Reconstruct real CFGs for GoW RVAs 0x5491A0 and 0x549420 and inspect paired callers.

The reusable SQLite function index is useful for call-graph discovery, but the
previous pass proved its function/chunk boundaries are incomplete for these two
addresses. This pass therefore decodes executable bytes directly and follows
reachable control flow from each target without trusting indexed function ends.

Read-only: no game launch, no save I/O, no executable modification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TARGETS = {"decode_like_5491A0": 0x5491A0, "encode_like_549420": 0x549420}
KNOWN_CALLERS = {
    0x5491A0: [0x2197A0, 0x21A6E0, 0x5F95F0, 0x668AC0, 0x8255A0],
    0x549420: [0x2194E8, 0x21A220, 0x5F96B0, 0x8254C0],
}
ANCHORS = {
    "save_userdata_serializer": 0x7E9190,
    "restore_orchestrator": 0x7E9550,
    "restore_record_dispatch": 0x7E7B60,
}
MAX_BLOCKS = 256
MAX_INSTRUCTIONS = 12000
MAX_SPAN = 0x5000
CALLER_SCAN = 0x1200


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    p = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base_cfg", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def rva_to_blob(pe, rva: int, size: int) -> bytes:
    off = pe.rva_to_file(rva)
    if off is None:
        return b""
    return pe.data[off:off + size]


def read_ascii(pe, rva: int, max_len: int = 160):
    off = pe.rva_to_file(rva)
    if off is None or off >= len(pe.data):
        return None
    raw = pe.data[off:off + max_len]
    if not raw:
        return None
    out = bytearray()
    for b in raw:
        if b == 0:
            break
        if 32 <= b <= 126 or b in (9, 10, 13):
            out.append(b)
        else:
            return None
    if len(out) < 4:
        return None
    try:
        return out.decode("ascii")
    except Exception:
        return None


def ins_rec(ins):
    return {
        "rva": int(ins.address - IMAGE_BASE),
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }


def branch_target(ins, op_imm):
    try:
        ops = list(ins.operands)
    except Exception:
        return None
    if not ops or ops[0].type != op_imm:
        return None
    va = int(ops[0].imm)
    if IMAGE_BASE <= va < IMAGE_BASE + 0x4000000:
        return va - IMAGE_BASE
    return None


def rip_refs_for_ins(md, pe, ins, op_mem, rip_reg):
    refs = []
    try:
        ops = list(ins.operands)
    except Exception:
        return refs
    for op in ops:
        if op.type != op_mem or op.mem.base != rip_reg:
            continue
        rva = int(ins.address - IMAGE_BASE)
        target = int(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        refs.append({
            "site": rva,
            "target_rva": target,
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
            "ascii": read_ascii(pe, target),
        })
    return refs


def decode_one(md, pe, rva: int):
    blob = rva_to_blob(pe, rva, 16)
    if not blob:
        return None
    for ins in md.disasm(blob, IMAGE_BASE + rva, count=1):
        return ins
    return None


def is_conditional_jump(mn: str) -> bool:
    return mn.startswith("j") and mn not in ("jmp", "jmpq")


def cfg_from_seed(md, pe, seed: int, op_imm, op_mem, rip_reg):
    pending = deque([seed])
    decoded = {}
    blocks = []
    calls = []
    rip_refs = []
    min_rva = seed
    max_rva = seed
    total = 0

    while pending and len(blocks) < MAX_BLOCKS and total < MAX_INSTRUCTIONS:
        start = pending.popleft()
        if any(b["start"] == start for b in blocks):
            continue
        if abs(start - seed) > MAX_SPAN:
            continue
        cur = start
        block_ins = []
        successors = []
        reason = "limit"

        while total < MAX_INSTRUCTIONS:
            if abs(cur - seed) > MAX_SPAN:
                reason = "span_limit"
                break
            if cur in decoded and cur != start:
                successors.append(cur)
                reason = "joins_existing"
                break

            ins = decode_one(md, pe, cur)
            if ins is None:
                reason = "decode_failure"
                break

            rec = ins_rec(ins)
            decoded[cur] = rec
            block_ins.append(rec)
            total += 1
            min_rva = min(min_rva, cur)
            max_rva = max(max_rva, cur + ins.size)

            rip_refs.extend(rip_refs_for_ins(md, pe, ins, op_mem, rip_reg))
            tgt = branch_target(ins, op_imm)

            if ins.mnemonic == "call":
                calls.append({
                    "site": cur,
                    "target": tgt,
                    "instruction": rec,
                    "direct": tgt is not None,
                })
                cur += ins.size
                continue

            if ins.mnemonic in ("ret", "retf", "iret", "iretq"):
                reason = "return"
                break

            if ins.mnemonic in ("jmp", "jmpq"):
                if tgt is not None:
                    successors.append(tgt)
                    pending.append(tgt)
                    reason = "direct_jump"
                else:
                    reason = "indirect_jump"
                break

            if is_conditional_jump(ins.mnemonic):
                fall = cur + ins.size
                successors.append(fall)
                pending.append(fall)
                if tgt is not None:
                    successors.append(tgt)
                    pending.append(tgt)
                reason = "conditional_jump"
                break

            cur += ins.size

        blocks.append({
            "start": start,
            "end": block_ins[-1]["rva"] + len(bytes.fromhex(block_ins[-1]["bytes"])) if block_ins else start,
            "reason": reason,
            "successors": sorted(set(successors)),
            "instructions": block_ins,
        })

    unique_rips = []
    seen = set()
    for ref in rip_refs:
        key = (ref["site"], ref["target_rva"])
        if key not in seen:
            seen.add(key)
            unique_rips.append(ref)

    return {
        "seed": seed,
        "block_count": len(blocks),
        "instruction_count": len(decoded),
        "rva_min": min_rva,
        "rva_max": max_rva,
        "span": max_rva - min_rva,
        "blocks": sorted(blocks, key=lambda b: b["start"]),
        "instructions": [decoded[k] for k in sorted(decoded)],
        "direct_and_indirect_calls": sorted(calls, key=lambda x: x["site"]),
        "rip_refs": unique_rips,
        "limits_hit": bool(pending or len(blocks) >= MAX_BLOCKS or total >= MAX_INSTRUCTIONS),
    }


def table_columns(con, table: str):
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def indexed_callers(con, target: int):
    cols = table_columns(con, "edges")
    have_site = "site" in cols
    fields = "src_fn,target_fn,kind" + (",site" if have_site else "")
    out = []
    for row in con.execute(
        f"SELECT {fields} FROM edges WHERE target_fn=? AND kind='call' ORDER BY src_fn",
        (target,),
    ):
        out.append({
            "src_fn": int(row[0]),
            "target_fn": int(row[1]),
            "kind": str(row[2]),
            "site": int(row[3]) if have_site and row[3] is not None else None,
        })
    return out


def caller_context(md, pe, caller: int, target: int, sites: list[int], op_imm, op_mem, rip_reg):
    blob = rva_to_blob(pe, caller, CALLER_SCAN)
    insns = list(md.disasm(blob, IMAGE_BASE + caller))
    records = [ins_rec(i) for i in insns]
    idx_by_rva = {r["rva"]: n for n, r in enumerate(records)}
    windows = []
    for site in sites:
        idx = idx_by_rva.get(site)
        if idx is None:
            windows.append({"site": site, "found": False})
            continue
        lo = max(0, idx - 16)
        hi = min(len(records), idx + 17)
        windows.append({"site": site, "found": True, "window": records[lo:hi]})

    calls = []
    refs = []
    for ins in insns:
        tgt = branch_target(ins, op_imm)
        if ins.mnemonic == "call":
            calls.append({"site": int(ins.address - IMAGE_BASE), "target": tgt, "op_str": ins.op_str})
        refs.extend(rip_refs_for_ins(md, pe, ins, op_mem, rip_reg))

    return {
        "caller": caller,
        "target": target,
        "scan_bytes": CALLER_SCAN,
        "call_sites": sites,
        "windows": windows,
        "direct_calls": calls,
        "rip_refs": refs,
    }


def pair_summary(target_reports):
    a = target_reports["decode_like_5491A0"]
    b = target_reports["encode_like_549420"]
    shared_calls = sorted(
        set(x["target"] for x in a["direct_and_indirect_calls"] if x["target"] is not None)
        & set(x["target"] for x in b["direct_and_indirect_calls"] if x["target"] is not None)
    )
    nearby_pairs = []
    for x in sorted(KNOWN_CALLERS[0x5491A0]):
        for y in sorted(KNOWN_CALLERS[0x549420]):
            delta = x - y
            if abs(delta) <= 0x500:
                nearby_pairs.append({"decode_caller": x, "encode_caller": y, "delta": delta})
    return {
        "shared_direct_callees_between_targets": shared_calls,
        "nearby_caller_pairs_within_0x500": nearby_pairs,
        "note": "Near-address caller pairing is structural evidence only; no semantic codec name is assigned automatically.",
    }


def fmt_ins(r):
    return f"0x{r['rva']:08X}  {r['bytes']:<24} {r['mnemonic']:<8} {r['op_str']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    exe = Path(args.exe)
    db = Path(args.db)
    if not exe.is_file():
        raise SystemExit(f"missing GoW.exe: {exe}")
    actual = sha256(exe).lower()
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"unsupported GoW.exe SHA256: {actual}")
    if not db.is_file():
        raise SystemExit(f"missing research index: {db}")

    capstone, Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    pe = load_pe_module().PE(exe.read_bytes())
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    con = sqlite3.connect(db)
    try:
        target_reports = {}
        caller_reports = []
        indexed = {}
        for name, target in TARGETS.items():
            target_reports[name] = cfg_from_seed(md, pe, target, op_imm, op_mem, rip_reg)
            rows = indexed_callers(con, target)
            indexed[f"0x{target:X}"] = rows
            grouped = defaultdict(list)
            for row in rows:
                if row["site"] is not None:
                    grouped[row["src_fn"]].append(row["site"])
            for caller in sorted(set(KNOWN_CALLERS[target]) | set(grouped)):
                caller_reports.append(
                    caller_context(md, pe, caller, target, sorted(grouped.get(caller, [])), op_imm, op_mem, rip_reg)
                )

        result = {
            "schema": 1,
            "analysis": "gow_5491a0_549420_cfg_and_callers",
            "exe_sha256": actual,
            "capstone_version": capstone.__version__,
            "targets": target_reports,
            "indexed_callers": indexed,
            "caller_reports": caller_reports,
            "pair_summary": pair_summary(target_reports),
            "known_persistence_anchors": ANCHORS,
            "interpretation": [
                "CFG bytes are decoded directly from the executable and do not trust SQLite function ends.",
                "A nearby caller pair does not prove encode/decode semantics by itself.",
                "No persistence relationship is asserted unless an actual call/data-flow link is present.",
            ],
            "safety": {
                "game_launched": False,
                "save_opened": False,
                "save_written": False,
                "exe_modified": False,
            },
        }
        Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

        lines = [
            "Completionist Map - 0x5491A0 / 0x549420 real-CFG and paired-caller trace",
            f"exe_sha256={actual}",
            f"capstone={capstone.__version__}",
            "",
        ]
        for name, rep in target_reports.items():
            lines += [
                f"TARGET {name} seed=0x{rep['seed']:X}",
                f"  blocks={rep['block_count']} instructions={rep['instruction_count']} span=0x{rep['span']:X} limits_hit={rep['limits_hit']}",
                f"  decoded_range=0x{rep['rva_min']:X}-0x{rep['rva_max']:X}",
                "  calls:",
            ]
            for c in rep["direct_and_indirect_calls"]:
                t = "INDIRECT" if c["target"] is None else f"0x{c['target']:X}"
                lines.append(f"    0x{c['site']:X} -> {t}  {c['instruction']['mnemonic']} {c['instruction']['op_str']}")
            lines.append("  RIP refs / strings:")
            for r in rep["rip_refs"]:
                s = "" if r["ascii"] is None else f" ascii={r['ascii']!r}"
                lines.append(f"    0x{r['site']:X} -> 0x{r['target_rva']:X}{s}  {r['mnemonic']} {r['op_str']}")
            lines.append("  reachable disassembly:")
            for ins in rep["instructions"]:
                lines.append("    " + fmt_ins(ins))
            lines.append("")

        lines.append("PAIRED CALLER SUMMARY")
        for p in result["pair_summary"]["nearby_caller_pairs_within_0x500"]:
            lines.append(
                f"  decode-caller=0x{p['decode_caller']:X} encode-caller=0x{p['encode_caller']:X} delta={p['delta']:+#x}"
            )
        lines.append("")

        lines.append("CALLER WINDOWS")
        for cr in caller_reports:
            lines.append(f"CALLER 0x{cr['caller']:X} -> target 0x{cr['target']:X}")
            if cr["rip_refs"]:
                lines.append("  strings/refs:")
                for r in cr["rip_refs"]:
                    if r["ascii"] is not None:
                        lines.append(f"    0x{r['site']:X} -> 0x{r['target_rva']:X} ascii={r['ascii']!r}")
            for w in cr["windows"]:
                lines.append(f"  callsite=0x{w['site']:X} found={w['found']}")
                for ins in w.get("window", []):
                    lines.append("    " + fmt_ins(ins))
            lines.append("")

        lines += [
            "INTERPRETATION",
            "- Real CFG decoding supersedes the prior SQLite end boundary for these two seeds.",
            "- Nearby caller pairing is a lead, not a semantic conclusion.",
            "- This pass is intended to decide whether these routines are generic codec/parser helpers or persistence-specific.",
            "",
            "SAFETY",
            "game_launched=false",
            "save_opened=false",
            "save_written=false",
            "exe_modified=false",
        ]
        Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(
            f"CFG_CALLER_TRACE_OK targetA_blocks={target_reports['decode_like_5491A0']['block_count']} "
            f"targetB_blocks={target_reports['encode_like_549420']['block_count']} callers={len(caller_reports)}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
