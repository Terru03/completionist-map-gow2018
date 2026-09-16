"""Characterise GoW native serialisation functions at RVAs 0x5491A0 and 0x549420.

This is a static, read-only pass over the supported God of War executable plus the
reusable research SQLite index. It does not launch the game and does not read or
modify save files.

The pass deliberately avoids assigning semantic names to the two target functions
until evidence supports them. It records:
- exact containing function boundaries;
- complete target-function disassembly;
- direct callers and callees;
- RIP-relative/global references;
- constants and memory displacements;
- shortest call-graph paths to/from proven persistence anchors;
- relationships between the two targets themselves.

Known anchors:
- 0x7E9190: proven native custom-userdata save serializer;
- 0x7E9550: proven native restore orchestrator;
- 0x7E7B60: function containing proven restore record dispatch;
- 0x544C40: checkpoint pickle-return serializer context, kept separate unless linked.

The objective is to prove where 0x5491A0 / 0x549420 sit in the persistence pipeline,
not to infer a role from address proximity.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000

TARGETS = {
    "target_5491A0": 0x5491A0,
    "target_549420": 0x549420,
}
ANCHORS = {
    "save_userdata_serializer": 0x7E9190,
    "restore_orchestrator": 0x7E9550,
    "restore_record_dispatch_fn": 0x7E7B60,
    "checkpoint_pickle_return_context": 0x544C40,
}
INTERESTING_DISPS = {0x20, 0x28, 0x30, 0x48, 0xA4, 0xB8, 0xC0, 0xC8, 0xD0, 0xD8, 0xE0}
MAX_PATH_DEPTH = 10


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    p = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base", p)
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


def function_for(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions "
        "WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if row is None:
        return None
    return {"begin": int(row[0]), "end": int(row[1]), "size": int(row[2]), "section": row[3]}


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def load_edges(con: sqlite3.Connection):
    cols = table_columns(con, "edges")
    required = {"src_fn", "target_fn", "kind"}
    if not required.issubset(cols):
        raise RuntimeError(f"edges table missing required columns: {sorted(required - cols)}")
    have_site = "site" in cols
    select = "src_fn,target_fn,kind" + (",site" if have_site else "")
    rows = []
    out = defaultdict(set)
    rev = defaultdict(set)
    for row in con.execute(f"SELECT {select} FROM edges WHERE target_fn IS NOT NULL"):
        src = row[0]
        dst = row[1]
        kind = row[2]
        site = row[3] if have_site else None
        if src is None or dst is None:
            continue
        src = int(src)
        dst = int(dst)
        item = {"src_fn": src, "target_fn": dst, "kind": str(kind), "site": None if site is None else int(site)}
        rows.append(item)
        if kind == "call":
            out[src].add(dst)
            rev[dst].add(src)
    return rows, out, rev


def shortest_path(graph, start: int, goal: int, max_depth: int = MAX_PATH_DEPTH):
    if start == goal:
        return [start]
    q = deque([(start, [start])])
    seen = {start}
    while q:
        cur, path = q.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for nxt in sorted(graph.get(cur, ())):
            if nxt == goal:
                return path + [nxt]
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, path + [nxt]))
    return None


def disasm_function(md, pe, meta):
    off = pe.rva_to_file(meta["begin"])
    if off is None:
        return []
    blob = pe.data[off: off + (meta["end"] - meta["begin"])]
    return list(md.disasm(blob, IMAGE_BASE + meta["begin"]))


def ins_record(ins):
    return {
        "rva": int(ins.address - IMAGE_BASE),
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }


def analyse_disassembly(md, pe, meta, op_imm, op_mem, rip_reg):
    insns = disasm_function(md, pe, meta)
    instructions = []
    direct_calls = []
    direct_jumps = []
    rip_refs = []
    immediates = Counter()
    displacements = Counter()
    interesting_mem = []
    indirect_calls = []

    for ins in insns:
        if ins.mnemonic == ".byte":
            continue
        rec = ins_record(ins)
        instructions.append(rec)
        try:
            ops = list(ins.operands)
        except Exception:
            ops = []

        for op in ops:
            if op.type == op_imm:
                val = int(op.imm)
                if -(1 << 63) <= val < (1 << 64):
                    immediates[val] += 1
            elif op.type == op_mem:
                disp = int(op.mem.disp)
                displacements[disp] += 1
                base_name = md.reg_name(op.mem.base) if op.mem.base else None
                index_name = md.reg_name(op.mem.index) if op.mem.index else None
                mem = {
                    "site": rec["rva"],
                    "mnemonic": ins.mnemonic,
                    "op_str": ins.op_str,
                    "base": base_name,
                    "index": index_name,
                    "scale": int(op.mem.scale),
                    "disp": disp,
                    "size": int(op.size),
                }
                if disp in INTERESTING_DISPS:
                    interesting_mem.append(mem)
                if op.mem.base == rip_reg:
                    target_va = ins.address + ins.size + disp
                    target_rva = int(target_va - IMAGE_BASE)
                    rip_refs.append({**mem, "target_rva": target_rva})

        if ins.mnemonic in ("call", "jmp") and ops:
            op0 = ops[0]
            if op0.type == op_imm:
                va = int(op0.imm)
                if IMAGE_BASE <= va < IMAGE_BASE + 0x4000000:
                    item = {"site": rec["rva"], "target": int(va - IMAGE_BASE), "op": ins.mnemonic}
                    if ins.mnemonic == "call":
                        direct_calls.append(item)
                    else:
                        direct_jumps.append(item)
            elif ins.mnemonic == "call":
                indirect_calls.append(rec)

    return {
        "instructions": instructions,
        "direct_calls": direct_calls,
        "direct_jumps": direct_jumps,
        "indirect_calls": indirect_calls,
        "rip_relative_refs": rip_refs,
        "interesting_memory_accesses": interesting_mem,
        "immediates": [{"value": k, "count": v} for k, v in immediates.most_common(80)],
        "memory_displacements": [{"disp": k, "count": v} for k, v in displacements.most_common(80)],
    }


def index_rip_refs(con: sqlite3.Connection, fn_begin: int):
    cols = table_columns(con, "rip_refs")
    if "src_fn" not in cols:
        return []
    wanted = [x for x in ("site", "target_rva", "target_string") if x in cols]
    if not wanted:
        return []
    rows = []
    for row in con.execute(
        f"SELECT {','.join(wanted)} FROM rip_refs WHERE src_fn=? ORDER BY "
        + ("site" if "site" in wanted else wanted[0]),
        (fn_begin,),
    ):
        item = dict(zip(wanted, row))
        for key in ("site", "target_rva"):
            if item.get(key) is not None:
                item[key] = int(item[key])
        rows.append(item)
    return rows


def resolve_all(con, mapping):
    result = {}
    for name, rva in mapping.items():
        meta = function_for(con, rva)
        result[name] = {
            "requested_rva": rva,
            "function": meta,
            "is_function_entry": bool(meta and meta["begin"] == rva),
        }
    return result


def edges_for_fn(edge_rows, fn):
    callers = []
    callees = []
    for e in edge_rows:
        if e["kind"] != "call":
            continue
        if e["target_fn"] == fn:
            callers.append(e)
        if e["src_fn"] == fn:
            callees.append(e)
    callers.sort(key=lambda x: ((x["site"] if x["site"] is not None else -1), x["src_fn"]))
    callees.sort(key=lambda x: ((x["site"] if x["site"] is not None else -1), x["target_fn"]))
    return callers, callees


def fmt_path(path):
    return " -> ".join(f"0x{x:X}" for x in path) if path else "NONE"


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
    actual_sha = sha256(exe).lower()
    if actual_sha != EXPECTED_SHA256:
        raise SystemExit(f"unsupported GoW.exe SHA256: {actual_sha}")
    if not db.is_file():
        raise SystemExit(f"missing reusable research index: {db}")

    con = sqlite3.connect(db)
    try:
        edge_rows, graph, rev_graph = load_edges(con)
        targets = resolve_all(con, TARGETS)
        anchors = resolve_all(con, ANCHORS)

        capstone, Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
        pe = load_pe_module().PE(exe.read_bytes())
        md = Cs(arch, mode)
        md.detail = True
        md.skipdata = True

        target_reports = {}
        for name, info in targets.items():
            meta = info["function"]
            if meta is None:
                target_reports[name] = {**info, "error": "no containing function in index"}
                continue
            fn = meta["begin"]
            callers, callees = edges_for_fn(edge_rows, fn)
            static = analyse_disassembly(md, pe, meta, op_imm, op_mem, rip_reg)
            paths = {}
            for anchor_name, anchor_info in anchors.items():
                anchor_meta = anchor_info["function"]
                if not anchor_meta:
                    continue
                afn = anchor_meta["begin"]
                paths[anchor_name] = {
                    "target_to_anchor": shortest_path(graph, fn, afn),
                    "anchor_to_target": shortest_path(graph, afn, fn),
                    "target_reached_from_anchor_via_reverse_graph": shortest_path(rev_graph, fn, afn),
                }

            target_reports[name] = {
                **info,
                "direct_callers_index": callers,
                "direct_callees_index": callees,
                "index_rip_refs": index_rip_refs(con, fn),
                "static_disassembly": static,
                "paths_to_known_anchors": paths,
            }

        relations = {}
        names = list(TARGETS)
        if all(targets[n]["function"] for n in names):
            a = targets[names[0]]["function"]["begin"]
            b = targets[names[1]]["function"]["begin"]
            relations[f"{names[0]}_to_{names[1]}"] = shortest_path(graph, a, b)
            relations[f"{names[1]}_to_{names[0]}"] = shortest_path(graph, b, a)

        anchor_relations = {}
        anchor_names = list(ANCHORS)
        for src_name in anchor_names:
            sm = anchors[src_name]["function"]
            if not sm:
                continue
            for dst_name in anchor_names:
                if src_name == dst_name:
                    continue
                dm = anchors[dst_name]["function"]
                if not dm:
                    continue
                p = shortest_path(graph, sm["begin"], dm["begin"])
                if p:
                    anchor_relations[f"{src_name}_to_{dst_name}"] = p

        result = {
            "schema": 1,
            "analysis": "gow_serialization_format_5491a0_549420",
            "exe_sha256": actual_sha,
            "targets": target_reports,
            "anchors": anchors,
            "target_relations": relations,
            "anchor_relations": anchor_relations,
            "max_path_depth": MAX_PATH_DEPTH,
            "edge_count": len(edge_rows),
            "capstone_version": capstone.__version__,
            "proven_context": {
                "save_record_shape": "[8-byte CodeSideLuaClass key][class +0xB8 callback payload]",
                "save_record_size_byte": "payload_length + 8",
                "restore_record_tables": {
                    "descriptor_plus_0x20": "u16 record offset table",
                    "descriptor_plus_0x28": "u8 record size table",
                    "descriptor_plus_0x30": "record blob base",
                },
                "restore_callback_slot": "CodeSideLuaClass +0xC0",
                "restore_payload": "record+8, size-8",
            },
            "safety": {
                "game_launched": False,
                "save_opened": False,
                "save_written": False,
                "exe_modified": False,
            },
        }

        Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

        lines = [
            "Completionist Map - GoW serialization format trace for 0x5491A0 / 0x549420",
            f"exe_sha256={actual_sha}",
            f"capstone={capstone.__version__}",
            f"edge_count={len(edge_rows)}",
            "",
            "PROVEN CONTEXT (carried forward, not re-inferred here)",
            "save_record=[8-byte CodeSideLuaClass key][class +0xB8 callback payload]",
            "save_record_size_byte=payload_length+8",
            "restore_tables=descriptor+0x20:u16 offsets, +0x28:u8 sizes, +0x30:blob",
            "restore_callback=CodeSideLuaClass+0xC0(payload=record+8,len=size-8)",
            "",
            "TARGET FUNCTION RESOLUTION",
        ]
        for name, report in target_reports.items():
            req = report["requested_rva"]
            meta = report.get("function")
            if not meta:
                lines.append(f"{name} requested=0x{req:X} NOT_RESOLVED")
                continue
            fn = meta["begin"]
            lines.append(
                f"{name} requested=0x{req:X} fn=0x{fn:X}-0x{meta['end']:X} "
                f"size=0x{meta['size']:X} entry={report['is_function_entry']}"
            )
            lines.append(f"  direct_callers={len(report['direct_callers_index'])}")
            for e in report["direct_callers_index"]:
                site = "?" if e["site"] is None else f"0x{e['site']:X}"
                lines.append(f"    caller=0x{e['src_fn']:X} site={site}")
            lines.append(f"  direct_callees={len(report['direct_callees_index'])}")
            for e in report["direct_callees_index"]:
                site = "?" if e["site"] is None else f"0x{e['site']:X}"
                lines.append(f"    site={site} callee=0x{e['target_fn']:X}")

            lines.append("  paths_to_known_anchors:")
            for aname, p in report["paths_to_known_anchors"].items():
                lines.append(f"    {aname}: target_to_anchor={fmt_path(p['target_to_anchor'])}")
                lines.append(f"    {aname}: anchor_to_target={fmt_path(p['anchor_to_target'])}")

            st = report["static_disassembly"]
            lines.append("  interesting_memory_accesses:")
            for m in st["interesting_memory_accesses"]:
                lines.append(
                    f"    0x{m['site']:X} disp=0x{m['disp']:X} size={m['size']} "
                    f"{m['mnemonic']} {m['op_str']}"
                )
            lines.append("  RIP_relative_refs:")
            for r in st["rip_relative_refs"]:
                lines.append(
                    f"    0x{r['site']:X} -> rva=0x{r['target_rva']:X} "
                    f"{r['mnemonic']} {r['op_str']}"
                )
            for r in report["index_rip_refs"]:
                s = r.get("target_string")
                if s:
                    lines.append(f"    INDEX_STRING 0x{r.get('site', 0):X} {s!r}")

            lines.append("  complete_disassembly:")
            for ins in st["instructions"]:
                lines.append(
                    f"    0x{ins['rva']:08X}  {ins['bytes']:<24} "
                    f"{ins['mnemonic']:<8} {ins['op_str']}"
                )
            lines.append("")

        lines.append("TARGET-TO-TARGET CALL-GRAPH RELATION")
        for key, path in relations.items():
            lines.append(f"{key}={fmt_path(path)}")
        lines.append("")
        lines.append("ANCHOR-TO-ANCHOR PATHS FOUND WITHIN DEPTH LIMIT")
        if anchor_relations:
            for key, path in sorted(anchor_relations.items()):
                lines.append(f"{key}={fmt_path(path)}")
        else:
            lines.append("NONE")
        lines += [
            "",
            "INTERPRETATION RULES",
            "- A direct/short call-graph edge is evidence of structural relationship, not semantic identity.",
            "- 0x544C40 is intentionally kept separate from 0x5491A0/0x549420 unless a path proves a link.",
            "- No role is assigned to either target solely from address proximity.",
            "- The 8-byte CodeSideLuaClass key is not labelled a hash or pointer here.",
            "",
            "SAFETY",
            "game_launched=false",
            "save_opened=false",
            "save_written=false",
            "exe_modified=false",
        ]
        Path(args.output_text).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"SERIALIZATION_FORMAT_TRACE_OK targets={len(target_reports)} edges={len(edge_rows)}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
