#!/usr/bin/env python3
"""Trace LuaClient-owned +0x70/+0x78 fields from the real LuaClient vtable.

Static, read-only, version-locked analysis for God of War (2018).

Why this exists:
The broad field-writer scan found thousands of unrelated structures that happen
to use offsets 0x70/0x78. This tracer anchors object identity at the known
LuaClient vftable (RVA 0xE04018), enumerates its virtual methods, then propagates
the exact LuaClient pointer through direct helper calls. Only accesses whose
base is proven to derive from that LuaClient pointer are reported.

No game launch, process access, save access, patching, or progression writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import struct
import sys
from collections import deque
from pathlib import Path

EXPECTED = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
LUACLIENT_VTABLE_RVA = 0xE04018
TARGET_FIELDS = {0x70, 0x78}
ARG_REGS = ("rcx", "rdx", "r8", "r9")
NONVOLATILE = {"rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14", "r15"}
VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
MAX_DEPTH = 4
MAX_STATES = 600
MAX_FUNCTION_SIZE = 0x5000

REG_CANON = {
    "al":"rax","ah":"rax","ax":"rax","eax":"rax","rax":"rax",
    "bl":"rbx","bh":"rbx","bx":"rbx","ebx":"rbx","rbx":"rbx",
    "cl":"rcx","ch":"rcx","cx":"rcx","ecx":"rcx","rcx":"rcx",
    "dl":"rdx","dh":"rdx","dx":"rdx","edx":"rdx","rdx":"rdx",
    "sil":"rsi","si":"rsi","esi":"rsi","rsi":"rsi",
    "dil":"rdi","di":"rdi","edi":"rdi","rdi":"rdi",
    "bpl":"rbp","bp":"rbp","ebp":"rbp","rbp":"rbp",
    "spl":"rsp","sp":"rsp","esp":"rsp","rsp":"rsp",
}
for _n in range(8, 16):
    REG_CANON[f"r{_n}b"] = f"r{_n}"
    REG_CANON[f"r{_n}w"] = f"r{_n}"
    REG_CANON[f"r{_n}d"] = f"r{_n}"
    REG_CANON[f"r{_n}"] = f"r{_n}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pe_helper():
    p = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_luaclient_lineage_pe", p)
    if not spec or not spec.loader:
        raise RuntimeError("PE helper load failed")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_capstone():
    root = Path(__file__).resolve().parents[2] / ".research-index" / "python-packages"
    if root.is_dir():
        sys.path.insert(0, str(root))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_READ, CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return (
        Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_READ, CS_AC_WRITE,
        X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP,
    )


def canon(name: str | None) -> str | None:
    if not name:
        return None
    return REG_CANON.get(name, name)


def fn_for(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions "
        "WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if row is None:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def incoming(con: sqlite3.Connection, fn: int, limit: int = 40):
    rows = con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges "
        "WHERE target_fn=? ORDER BY site LIMIT ?",
        (fn, limit),
    ).fetchall()
    return [
        {"site": r[0], "src_fn": r[1], "kind": r[2], "dest": r[3], "target_fn": r[4]}
        for r in rows if r[1] is not None and r[1] != fn
    ]


def ascii_at(pe, rva: int, maxlen: int = 160):
    off = pe.rva_to_file(rva)
    if off is None:
        return None
    out = []
    for b in pe.data[off:off + maxlen]:
        if b == 0:
            break
        if 32 <= b <= 126:
            out.append(chr(b))
        else:
            return None
    s = "".join(out)
    return s if len(s) >= 4 else None


def enumerate_vtable(pe, con, max_slots: int = 96):
    out = []
    invalid_run = 0
    seen_valid = False
    for slot in range(max_slots):
        rva = LUACLIENT_VTABLE_RVA + slot * 8
        off = pe.rva_to_file(rva)
        if off is None or off + 8 > len(pe.data):
            break
        va = struct.unpack_from("<Q", pe.data, off)[0]
        target = va - IMAGE_BASE if IMAGE_BASE <= va < IMAGE_BASE + pe.size_of_image else None
        meta = fn_for(con, target) if target is not None else None
        valid = target is not None and meta is not None
        if valid:
            seen_valid = True
            invalid_run = 0
            out.append({
                "slot": slot,
                "entry_rva": rva,
                "target_rva": target,
                "function": meta["begin"],
                "size": meta["size"],
                "valid": True,
            })
        else:
            invalid_run += 1
            out.append({
                "slot": slot,
                "entry_rva": rva,
                "raw_va": va,
                "target_rva": target,
                "valid": False,
            })
            if seen_valid and invalid_run >= 5:
                break
    while out and not out[-1]["valid"]:
        out.pop()
    return out


def op_reg(md, op):
    return canon(md.reg_name(op.reg)) if op.reg else None


def mem_base(md, op):
    return canon(md.reg_name(op.mem.base)) if op.mem.base else None


def mem_index(md, op):
    return canon(md.reg_name(op.mem.index)) if op.mem.index else None


def prov_text(p):
    if p is None:
        return None
    return f"luaclient{p:+#x}" if p else "luaclient"


def analyse_state(
    pe, con, md, consts, fnmeta, seedreg: str, depth: int, path: list[str]
):
    CS_AC_READ, CS_AC_WRITE, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP = consts
    off = pe.rva_to_file(fnmeta["begin"])
    if off is None:
        return None
    data = pe.data[off:off + fnmeta["size"]]

    # Provenance maps a register to byte offset from the exact LuaClient pointer.
    prov: dict[str, int] = {seedreg: 0}
    hits = []
    calls = []
    strings = []
    insns = []

    for ins in md.disasm(data, IMAGE_BASE + fnmeta["begin"]):
        rva = ins.address - IMAGE_BASE
        try:
            ops = list(ins.operands)
        except Exception:
            ops = []

        row = {"rva": rva, "hex": ins.bytes.hex(), "mnemonic": ins.mnemonic, "op_str": ins.op_str}
        insns.append(row)

        # Record strings and exact LuaClient field accesses before mutating provenance.
        for oi, op in enumerate(ops):
            if op.type != X86_OP_MEM:
                continue
            if op.mem.base == X86_REG_RIP:
                target = ins.address + ins.size + int(op.mem.disp) - IMAGE_BASE
                s = ascii_at(pe, target)
                if s:
                    strings.append({"site": rva, "target": target, "string": s})
                continue

            base = mem_base(md, op)
            index = mem_index(md, op)
            if base in prov and not index:
                effective = prov[base] + int(op.mem.disp)
                if effective in TARGET_FIELDS:
                    access = int(getattr(op, "access", 0))
                    # Capstone sometimes leaves access at zero. Infer the common write form.
                    inferred_write = oi == 0 and ins.mnemonic in {
                        "mov","movzx","movsx","movsxd","lea","add","sub","and","or","xor",
                        "inc","dec","cmpxchg","xchg"
                    }
                    kind = "write" if (access & CS_AC_WRITE) or inferred_write else "read"
                    if (access & CS_AC_READ) and ((access & CS_AC_WRITE) or inferred_write):
                        kind = "readwrite"
                    src = None
                    if oi == 0 and len(ops) >= 2:
                        src = ins.op_str.split(",", 1)[1].strip() if "," in ins.op_str else None
                    hits.append({
                        "site": rva,
                        "field": effective,
                        "kind": kind,
                        "instruction": f"{ins.mnemonic} {ins.op_str}",
                        "base_register": base,
                        "base_provenance": prov_text(prov[base]),
                        "source_text": src,
                    })

        # Propagate LuaClient pointer through direct calls before volatile clobber.
        if ins.mnemonic == "call" and ops and ops[0].type == X86_OP_IMM:
            va = int(ops[0].imm)
            if IMAGE_BASE <= va < IMAGE_BASE + pe.size_of_image:
                target = va - IMAGE_BASE
                target_meta = fn_for(con, target)
                if target_meta and target_meta["size"] <= MAX_FUNCTION_SIZE:
                    args = []
                    for ar in ARG_REGS:
                        if prov.get(ar) == 0:
                            args.append(ar)
                    if args:
                        calls.append({
                            "site": rva,
                            "target": target_meta["begin"],
                            "target_size": target_meta["size"],
                            "lua_client_args": args,
                        })

        # Register provenance update.
        if len(ops) >= 2 and ops[0].type == X86_OP_REG:
            dst = op_reg(md, ops[0])
            if dst:
                updated = False
                if ins.mnemonic == "mov" and ops[1].type == X86_OP_REG:
                    src = op_reg(md, ops[1])
                    if src in prov:
                        prov[dst] = prov[src]
                    else:
                        prov.pop(dst, None)
                    updated = True
                elif ins.mnemonic == "lea" and ops[1].type == X86_OP_MEM:
                    base = mem_base(md, ops[1])
                    idx = mem_index(md, ops[1])
                    if base in prov and not idx:
                        prov[dst] = prov[base] + int(ops[1].mem.disp)
                    else:
                        prov.pop(dst, None)
                    updated = True
                elif ins.mnemonic in ("add", "sub") and ops[1].type == X86_OP_IMM and dst in prov:
                    delta = int(ops[1].imm)
                    prov[dst] = prov[dst] + (delta if ins.mnemonic == "add" else -delta)
                    updated = True
                if not updated and ins.mnemonic not in ("cmp", "test"):
                    prov.pop(dst, None)
        elif ops and ops[0].type == X86_OP_REG:
            dst = op_reg(md, ops[0])
            if dst and ins.mnemonic not in ("cmp", "test", "push"):
                prov.pop(dst, None)

        if ins.mnemonic == "call":
            for reg in VOLATILE:
                prov.pop(reg, None)

    return {
        "function": fnmeta,
        "seed_register": seedreg,
        "depth": depth,
        "path": path,
        "hits": hits,
        "calls": calls,
        "strings": strings,
        "instructions": insns,
    }


def make_snippet(instructions, site: int, radius: int = 10):
    idx = next((i for i, x in enumerate(instructions) if x["rva"] == site), None)
    if idx is None:
        return []
    lo = max(0, idx - radius)
    hi = min(len(instructions), idx + radius + 1)
    return instructions[lo:hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    actual = sha256(args.exe)
    if actual != EXPECTED:
        raise RuntimeError(f"unsupported GoW.exe sha256={actual}")

    peh = load_pe_helper()
    pe = peh.PE(args.exe.read_bytes())
    (
        Cs, arch, mode, CS_AC_READ, CS_AC_WRITE,
        X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP,
    ) = load_capstone()
    md = Cs(arch, mode)
    md.detail = True
    consts = (
        CS_AC_READ, CS_AC_WRITE, X86_OP_IMM, X86_OP_MEM,
        X86_OP_REG, X86_REG_RIP,
    )

    con = sqlite3.connect(args.db)
    try:
        vtable = enumerate_vtable(pe, con)
        if not vtable:
            raise RuntimeError("LuaClient vtable produced no function entries")

        queue = deque()
        best_depth = {}
        for slot in vtable:
            key = (slot["function"], "rcx")
            path = [f"vslot[{slot['slot']}]=>0x{slot['function']:X}"]
            if key not in best_depth or 0 < best_depth[key]:
                best_depth[key] = 0
                queue.append((slot["function"], "rcx", 0, path))

        states = []
        all_hits = []
        while queue and len(states) < MAX_STATES:
            fn, seedreg, depth, path = queue.popleft()
            meta = fn_for(con, fn)
            if not meta or meta["size"] > MAX_FUNCTION_SIZE:
                continue
            state = analyse_state(pe, con, md, consts, meta, seedreg, depth, path)
            if not state:
                continue
            states.append(state)
            for hit in state["hits"]:
                rec = {
                    **hit,
                    "function": fn,
                    "seed_register": seedreg,
                    "depth": depth,
                    "path": path,
                    "incoming": incoming(con, fn, 20),
                    "strings": state["strings"][:30],
                    "snippet": make_snippet(state["instructions"], hit["site"]),
                }
                all_hits.append(rec)

            if depth >= MAX_DEPTH:
                continue
            for call in state["calls"]:
                for arg in call["lua_client_args"]:
                    key = (call["target"], arg)
                    nd = depth + 1
                    if key in best_depth and best_depth[key] <= nd:
                        continue
                    best_depth[key] = nd
                    npath = path + [f"0x{fn:X}@0x{call['site']:X}->{arg}:0x{call['target']:X}"]
                    queue.append((call["target"], arg, nd, npath))

        all_hits.sort(key=lambda h: (h["field"], h["kind"], h["depth"], h["function"], h["site"]))
        writes = [h for h in all_hits if h["kind"] in ("write", "readwrite")]
        reads = [h for h in all_hits if h["kind"] == "read"]

        out = {
            "schema": 1,
            "analysis": "luaclient_vtable_field_lineage",
            "exe_sha256": EXPECTED,
            "luaclient_vtable_rva": LUACLIENT_VTABLE_RVA,
            "target_fields": sorted(TARGET_FIELDS),
            "max_depth": MAX_DEPTH,
            "vtable": vtable,
            "states_analysed": len(states),
            "state_limit_hit": len(states) >= MAX_STATES,
            "hits": all_hits,
            "summary": {
                "hits": len(all_hits),
                "writes": len(writes),
                "reads": len(reads),
                "field_0x70": sum(1 for h in all_hits if h["field"] == 0x70),
                "field_0x78": sum(1 for h in all_hits if h["field"] == 0x78),
            },
            "safety": {
                "static_pe_only": True,
                "game_launched": False,
                "process_opened": False,
                "save_opened": False,
                "exe_modified": False,
                "save_modified": False,
                "progression_written": False,
            },
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        lines = [
            "Completionist Map - LuaClient vtable field lineage",
            f"exe_sha256={EXPECTED}",
            f"luaclient_vtable_rva=0x{LUACLIENT_VTABLE_RVA:X}",
            f"vtable_slots={len(vtable)} states={len(states)} hits={len(all_hits)} writes={len(writes)} reads={len(reads)}",
            "game_launched=false process_opened=false save_opened=false exe_modified=false save_modified=false progression_written=false",
            "",
            "VTABLE",
        ]
        for s in vtable:
            lines.append(
                f"  slot={s['slot']:02d} entry=0x{s['entry_rva']:X} "
                f"fn=0x{s['function']:X} size=0x{s['size']:X}"
            )

        lines.append("")
        lines.append("FIELD_HITS")
        if not all_hits:
            lines.append("  NONE")
        for h in all_hits:
            lines.append(
                f"  {h['kind'].upper()} field=0x{h['field']:X} fn=0x{h['function']:X} "
                f"site=0x{h['site']:X} depth={h['depth']} seed={h['seed_register']} "
                f"base={h['base_register']} op={h['instruction']}"
            )
            lines.append("    path=" + " | ".join(h["path"]))
            if h.get("source_text"):
                lines.append(f"    source={h['source_text']}")
            for s in h.get("strings", [])[:8]:
                lines.append(f"    string@0x{s['site']:X}={s['string']!r}")
            lines.append("    snippet:")
            for ins in h["snippet"]:
                mark = ">>" if ins["rva"] == h["site"] else "  "
                lines.append(
                    f"      {mark} 0x{ins['rva']:X}: {ins['hex']:<24} "
                    f"{ins['mnemonic']} {ins['op_str']}"
                )

        args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

        print(
            "LUACLIENT_VTABLE_FIELD_LINEAGE_COMPLETE "
            f"vtable_slots={len(vtable)} states={len(states)} "
            f"hits={len(all_hits)} writes={len(writes)} reads={len(reads)}"
        )
        for h in writes[:40]:
            print(
                f"WRITE field=0x{h['field']:X} fn=0x{h['function']:X} "
                f"site=0x{h['site']:X} depth={h['depth']} "
                f"seed={h['seed_register']} op={h['instruction']}"
            )
        if not writes:
            print("WRITE NONE")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
