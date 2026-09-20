#!/usr/bin/env python3
"""Trace LuaClient virtual slot 11 restore dispatch and transient-blob materialisation.

Proven before this pass:
- LuaClient/LuaLevelClient +0x68 is the durable per-resource backing node.
- +0x70/+0x78 are transient normal/soft pickle blobs consumed by BaseLuaClient
  slot 11 at 0x5A6C10.
- LuaLevelClient slot 11 = 0x5ADE30 and LuaClient slot 11 = 0x5B1F50.
- 0x5A6DD0 constructs a client with +0x68 attached and +0x70/+0x78 zero.
- 0x5A7720 -> 0x5A6270 is the opposite, teardown/backing-transfer direction.

Therefore the unresolved restore-side edge must occur after construction and
before/at virtual slot-11 dispatch. This pass finds every indirect slot-11 call
(call/jmp [vtable+0x58]), captures its enclosing function and nearby call graph,
and highlights any +0x68/+0x70/+0x78/+0x80 accesses in that typed neighbourhood.

Static/read-only only. No game launch, process access, save access, or writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

SLOT11_DISP = 0x58
CLIENT_OFFSETS = (0x58, 0x60, 0x68, 0x70, 0x78, 0x80)
TRANSIENT = (0x70, 0x78, 0x80)

TARGETS = {
    "base_slot11_restore": 0x5A6C10,
    "luavel_slot11_restore": 0x5ADE30,
    "lua_slot11_restore": 0x5B1F50,
    "client_ctor": 0x5A6DD0,
    "backing_transfer": 0x5A7720,
    "backing_pack": 0x5A6270,
    "pending_prepare": 0x463C60,
    "pending_take": 0x464410,
    "create_client": 0x4654A0,
}

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
    spec = importlib.util.spec_from_file_location("slot11_restore_pe", path)
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
                item = {
                    "base": md.reg_name(op.mem.base) if op.mem.base else None,
                    "index": md.reg_name(op.mem.index) if op.mem.index else None,
                    "disp": op.mem.disp,
                    "size": op.size,
                    "operand_index": idx,
                    "write": bool(getattr(op, "access", 0) & AC_WRITE),
                }
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
        sec = pe.section_for_rva(target)
        if not sec or not sec.get("exec"):
            continue
        tf = pe.function_for(target)
        out.append({
            "site": row["rva"],
            "kind": row["mnemonic"],
            "target": target,
            "target_function": tf["begin"] if tf else None,
        })
    return out


def client_hits(rows):
    out = []
    for row in rows:
        for m in row["mem"]:
            base = m.get("base")
            if base in (None, "rsp", "rbp", "rip"):
                continue
            if m.get("disp") not in CLIENT_OFFSETS:
                continue
            out.append({
                "site": row["rva"],
                "offset": m["disp"],
                "base": base,
                "write": bool(m.get("write")),
                "size": m.get("size"),
                "op": row["op_str"],
            })
    return out


def slot11_sites(rows):
    sites = []
    for row in rows:
        if row["mnemonic"] not in ("call", "jmp"):
            continue
        for m in row["mem"]:
            if m.get("disp") == SLOT11_DISP and m.get("base") not in (None, "rsp", "rbp", "rip"):
                sites.append({
                    "site": row["rva"],
                    "kind": row["mnemonic"],
                    "base": m.get("base"),
                    "op": row["op_str"],
                })
    return sites


def windows(rows, sites, before=24, after=16):
    lookup = {row["rva"]: i for i, row in enumerate(rows)}
    keep = set()
    for site in sites:
        idx = lookup.get(site)
        if idx is None:
            continue
        for j in range(max(0, idx-before), min(len(rows), idx+after+1)):
            keep.add(j)
    return [rows[i] for i in sorted(keep)]


def function_summary(pe, decoded, calls_by_fn, callers, begin):
    fn = pe.function_for(begin)
    if not fn:
        return None
    rows = decoded.get(fn["begin"], [])
    return {
        "begin": fn["begin"],
        "end": fn["end"],
        "slot11_sites": slot11_sites(rows),
        "client_hits": client_hits(rows),
        "calls": calls_by_fn.get(fn["begin"], []),
        "callers": callers.get(fn["begin"], []),
    }


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

    decoded = {}
    calls_by_fn = {}
    callers = defaultdict(list)
    slot_dispatchers = []

    for fn in pe.runtime_functions:
        rows = decode_fn(pe, md, fn, OP_IMM, OP_MEM, RIP, AC_WRITE)
        if not rows:
            continue
        decoded[fn["begin"]] = rows
        calls = direct_calls(pe, rows)
        calls_by_fn[fn["begin"]] = calls
        for call in calls:
            target_fn = call.get("target_function")
            if target_fn is not None:
                callers[target_fn].append({"caller": fn["begin"], "site": call["site"]})
        sites = slot11_sites(rows)
        if sites:
            slot_dispatchers.append({
                "begin": fn["begin"],
                "end": fn["end"],
                "sites": sites,
                "client_hits": client_hits(rows),
                "calls": calls,
                "callers": callers.get(fn["begin"], []),
                "context": windows(rows, [s["site"] for s in sites]),
            })

    # Refresh caller lists now that the whole graph exists.
    for item in slot_dispatchers:
        item["callers"] = callers.get(item["begin"], [])

    target_functions = {}
    for name, rva in TARGETS.items():
        fn = pe.function_for(rva)
        target_functions[name] = fn["begin"] if fn else None

    # Graph distance in both directions from typed LuaClient targets.
    seeds = {v for v in target_functions.values() if v is not None}
    reverse = defaultdict(set)
    forward = defaultdict(set)
    for source, calls in calls_by_fn.items():
        for call in calls:
            target = call.get("target_function")
            if target is not None:
                forward[source].add(target)
                reverse[target].add(source)

    def distances(graph, seeds, max_depth=3):
        dist = {s: 0 for s in seeds}
        q = deque(seeds)
        while q:
            cur = q.popleft()
            if dist[cur] >= max_depth:
                continue
            for nxt in graph.get(cur, ()):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    q.append(nxt)
        return dist

    outward = distances(forward, seeds, 3)
    inward = distances(reverse, seeds, 3)

    neighbourhood = set(outward) | set(inward)
    typed_neighbourhood = []
    for begin in sorted(neighbourhood):
        summary = function_summary(pe, decoded, calls_by_fn, callers, begin)
        if summary is None:
            continue
        hits = summary["client_hits"]
        interesting = (
            summary["slot11_sites"]
            or any(h["offset"] in (0x68, 0x70, 0x78, 0x80) for h in hits)
            or begin in seeds
        )
        if not interesting:
            continue
        summary["outward_distance"] = outward.get(begin)
        summary["inward_distance"] = inward.get(begin)
        rows = decoded.get(begin, [])
        focus_sites = [s["site"] for s in summary["slot11_sites"]]
        focus_sites += [h["site"] for h in hits if h["offset"] in (0x68, 0x70, 0x78, 0x80)]
        summary["context"] = windows(rows, focus_sites, before=14, after=14)
        typed_neighbourhood.append(summary)

    report = {
        "schema": 1,
        "analysis": "luaclient_slot11_restore_materialisation",
        "exe_sha256": digest,
        "slot11_displacement": SLOT11_DISP,
        "targets": TARGETS,
        "target_functions": target_functions,
        "vtables": VTABLES,
        "slot_dispatcher_count": len(slot_dispatchers),
        "slot_dispatchers": slot_dispatchers,
        "typed_neighbourhood": typed_neighbourhood,
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
        "Completionist Map - LuaClient slot11 restore/materialisation trace",
        f"exe_sha256={digest}",
        f"slot11_dispatcher_count={len(slot_dispatchers)}",
        "",
        "TARGET FUNCTIONS",
    ]
    for name, begin in target_functions.items():
        lines.append(f"  {name}={('-' if begin is None else f'0x{begin:X}')}")
    lines.append("")

    lines.append("INDIRECT SLOT11 DISPATCHERS")
    for item in slot_dispatchers:
        lines.append(f"FUNCTION 0x{item['begin']:X}..0x{item['end']:X}")
        for site in item["sites"]:
            lines.append(f"  SLOT11 0x{site['site']:X} {site['kind']} {site['op']}")
        for hit in item["client_hits"]:
            if hit["offset"] in (0x68, 0x70, 0x78, 0x80):
                mode = "WRITE" if hit["write"] else "READ"
                lines.append(
                    f"  {mode} 0x{hit['site']:X} +0x{hit['offset']:X} "
                    f"size={hit['size']} base={hit['base']} {hit['op']}"
                )
        for row in item["context"]:
            lines.append(
                f"    0x{row['rva']:08X} {row['bytes']:<24} "
                f"{row['mnemonic']:<8} {row['op_str']}"
            )
        lines.append("")

    lines.append("TYPED CALL-GRAPH NEIGHBOURHOOD <=3 HOPS")
    for item in typed_neighbourhood:
        lines.append(
            f"FUNCTION 0x{item['begin']:X}..0x{item['end']:X} "
            f"out={item['outward_distance']} in={item['inward_distance']}"
        )
        for site in item["slot11_sites"]:
            lines.append(f"  SLOT11 0x{site['site']:X} {site['op']}")
        for hit in item["client_hits"]:
            if hit["offset"] in (0x68, 0x70, 0x78, 0x80):
                mode = "WRITE" if hit["write"] else "READ"
                lines.append(
                    f"  {mode} 0x{hit['site']:X} +0x{hit['offset']:X} "
                    f"size={hit['size']} base={hit['base']} {hit['op']}"
                )
        for call in item["calls"]:
            if call.get("target_function") in neighbourhood:
                lines.append(
                    f"  CALL 0x{call['site']:X} -> 0x{call['target_function']:X}"
                )
        for row in item["context"]:
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

    typed_dispatchers = sum(
        1 for item in slot_dispatchers
        if any(h["offset"] in (0x68, 0x70, 0x78, 0x80) for h in item["client_hits"])
    )
    print(
        "LUACLIENT_SLOT11_RESTORE_MATERIALISATION_TRACE_COMPLETE "
        f"dispatchers={len(slot_dispatchers)} typed_dispatchers={typed_dispatchers} "
        f"neighbourhood={len(typed_neighbourhood)}"
    )
    print(
        "save_opened=false save_written=false progression_written=false "
        "game_launched=false"
    )


if __name__ == "__main__":
    main()
