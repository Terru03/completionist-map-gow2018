"""Trace computed users of the GoW runtime GameObject registry table.

Version-locked, read-only static analysis for the supported GoW.exe.  Unlike the
older registry slot-state scan, this walks PE runtime-function boundaries and
propagates the table address through register copies and LEAs.  This finds
indexed table writes such as ``[table_base + registry_id*8]`` which have no
direct RIP-relative reference to the written entry.
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
TABLE_BEGIN = 0x22A98C0
TABLE_BYTES = 64 * 8
RAVEN_GUID = "95b9c644-4d47-9ac6-8207-b1829d02909b"

ANCHORS = {
    "registry_lookup_id": 0x4F366B,
    "registry_id_compare": 0x4F368A,
    "registry_zero_fields_begin": 0x4F3703,
    "registry_bank_store": 0x4F375C,
    "registry_capacity_store": 0x4F3773,
    "registry_table_insert": 0x4F37A2,
    "registry_cursor_soft_reset": 0x4F357C,
    "registry_table_remove": 0x4F35A5,
    "existing_record_id": 0x82D1A9,
    "wad_registry_id_store": 0x82D203,
    "new_record_id_store": 0x82D321,
    "record_runtime_ordinal_store": 0x82D219,
    "scheduler_outer_list": 0x85AC80,
    "scheduler_inner_list": 0x85ACD5,
    "scheduler_budgeted_call": 0x85AEE3,
    "loader_outer_index_lookup": 0x8583E2,
    "loader_inner_index_lookup": 0x85840F,
    "loader_rng_step": 0x85847E,
    "descriptor_no_hint": 0x859BA9,
    "descriptor_builder_call": 0x859BD6,
    "gameobject_loader_call": 0x859C0D,
}

ANCHOR_EXPECTED = {
    "registry_lookup_id": ("mov", "[rcx + 0xc3c]"),
    "registry_id_compare": ("cmp", "[rcx], esi"),
    "registry_zero_fields_begin": ("mov", "[rax + 4], ebx"),
    "registry_bank_store": ("mov", "[rdi + 0x20], rax"),
    "registry_capacity_store": ("mov", "[rdi + 0x30], 0x400"),
    "registry_table_insert": ("mov", "[r14 + rax*8], rdi"),
    "registry_cursor_soft_reset": ("mov", "[rbx + 0x28], edx"),
    "registry_table_remove": ("mov", "[r9 + rax*8], rdx"),
    "existing_record_id": ("mov", "[rbx + 0x24]"),
    "wad_registry_id_store": ("mov", "[r13 + 0xc3c], eax"),
    "new_record_id_store": ("mov", "[r15 + r9 + 0x24], edx"),
    "record_runtime_ordinal_store": ("mov", "[rbx + 0x28], r12d"),
    "scheduler_outer_list": ("mov", "r12, rdi"),
    "scheduler_inner_list": ("cmp", "rbx, r14"),
    "scheduler_budgeted_call": ("call", "0x140858320"),
    "loader_outer_index_lookup": ("mov", "qword ptr [rip"),
    "loader_inner_index_lookup": ("mov", "ecx, r15d"),
    "loader_rng_step": ("imul", "0x41c64e6d"),
    "descriptor_no_hint": ("mov", "[rsp + 0x30], 0xffffffff"),
    "descriptor_builder_call": ("call", "0x1408566b0"),
    "gameobject_loader_call": ("call", "0x140856f50"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_registry_runtime_pe", path)
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
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_READ, CS_AC_WRITE
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return (Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_READ, CS_AC_WRITE,
            X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP)


def normalize_reg(md, reg: int) -> str:
    """Map partial-register ids to the containing 64-bit register."""
    if not reg:
        return ""
    name = md.reg_name(reg)
    groups = {
        "rax": ("rax", "eax", "ax", "al", "ah"),
        "rbx": ("rbx", "ebx", "bx", "bl", "bh"),
        "rcx": ("rcx", "ecx", "cx", "cl", "ch"),
        "rdx": ("rdx", "edx", "dx", "dl", "dh"),
        "rsi": ("rsi", "esi", "si", "sil"),
        "rdi": ("rdi", "edi", "di", "dil"),
        "rbp": ("rbp", "ebp", "bp", "bpl"),
        "rsp": ("rsp", "esp", "sp", "spl"),
    }
    for i in range(8, 16):
        groups[f"r{i}"] = (f"r{i}", f"r{i}d", f"r{i}w", f"r{i}b")
    for root, names in groups.items():
        if name in names:
            return root
    return name


def row_for(ins, image_base: int) -> dict:
    return {
        "rva": ins.address - image_base,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }


def load_focus_rows(md, pe, rvas: list[int]) -> tuple[list[dict], dict[int, dict]]:
    focus_functions = []
    rows_by_rva = {}
    seen = set()
    for rva in rvas:
        fn = pe.function_for(rva)
        if fn is None:
            focus_functions.append({"query_rva": rva, "function": None, "instructions": []})
            continue
        if fn["begin"] in seen:
            continue
        seen.add(fn["begin"])
        chunks, insns = disassemble_flow_bundle(md, pe, fn)
        instruction_rows = [row_for(ins, IMAGE_BASE) for ins in insns]
        for row in instruction_rows:
            rows_by_rva[row["rva"]] = row
        focus_functions.append({
            "query_rva": rva,
            "function": {"begin": fn["begin"], "end": chunks[-1]["end"], "runtime_chunks": chunks},
            "instructions": instruction_rows,
        })
    return focus_functions, rows_by_rva


def load_raven_example(catalogue: Path, game_root: Path) -> dict:
    data = json.loads(catalogue.read_text(encoding="utf-8"))
    row = next(item for item in data["ravens"] if item["native"]["instance_guid"] == RAVEN_GUID)
    wad_rel = Path("exec") / "wad" / "pc_le" / row["source"]["wad"]
    wad_path = game_root / wad_rel
    module_path = Path(__file__).with_name("raven_catalogue.py")
    spec = importlib.util.spec_from_file_location("gow_registry_raven_catalogue", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load catalogue helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wad_digest = sha256(wad_path)
    expected_wad_digest = row["source"]["wad_sha256"].lower()
    if wad_digest.lower() != expected_wad_digest:
        raise RuntimeError(f"Raven WAD SHA mismatch: {wad_digest}")
    records = module.parse_wad(wad_path.read_bytes())
    final_offset = int(row["source"]["final_offset"], 0)
    final_id = row["native"]["final_record_id"]
    exact = [
        {"record_index": index, "offset": record["offset"], "kind": record["kind"],
         "flags": record["flags"], "size": record["size"], "name": record["name"],
         "record_id": record["id"].hex()}
        for index, record in enumerate(records)
        if record["offset"] == final_offset and record["id"].hex() == final_id
    ]
    if len(exact) != 1:
        raise RuntimeError(f"canonical Raven record match count is {len(exact)}, expected 1")
    same_id = [
        {"record_index": index, "offset": record["offset"], "kind": record["kind"],
         "flags": record["flags"], "size": record["size"], "name": record["name"]}
        for index, record in enumerate(records) if record["id"].hex() == final_id
    ]
    return {
        "instance_guid": RAVEN_GUID,
        "wad": row["source"]["wad"],
        "wad_sha256": row["source"]["wad_sha256"],
        "wad_sha256_verified": True,
        "catalogue_final_offset": final_offset,
        "catalogue_final_record_id": final_id,
        "wad_record_count": len(records),
        "physical_record": exact[0],
        "same_record_id_count": len(same_id),
        "same_record_id_records": same_id,
        "registry_id": None,
        "slot": None,
        "tuple_reconstructible": False,
        "reason": "physical WAD record index has no proved edge to runtime scheduler allocation ordinal",
    }


def is_write_operand(ins, operand_index: int, access: int, cs_write: int) -> bool:
    if access & cs_write:
        return True
    return operand_index == 0 and ins.mnemonic.lower() in {
        "mov", "movabs", "stosq", "stosd", "xchg", "cmpxchg", "add", "sub",
        "and", "or", "xor", "inc", "dec",
    }


def disassemble_flow_bundle(md, pe, fn, max_chunks: int = 8):
    """Join adjacent pdata chunks when control falls through across a boundary."""
    chunks = []
    insns = []
    current = fn
    seen = set()
    by_begin = {item["begin"]: item for item in pe.runtime_functions}
    while current and current["begin"] not in seen and len(chunks) < max_chunks:
        seen.add(current["begin"])
        chunks.append({"begin": current["begin"], "end": current["end"]})
        part = [ins for ins in md.disasm(pe.bytes_for(current), IMAGE_BASE + current["begin"]) if ins.id]
        insns.extend(part)
        if not part or part[-1].mnemonic.lower() in ("ret", "jmp"):
            break
        current = by_begin.get(current["end"])
    return chunks, insns


def trace_function(md, pe, fn, constants) -> dict | None:
    _cs_read, cs_write, op_imm, op_mem, op_reg, rip_reg = constants
    chunks, insns = disassemble_flow_bundle(md, pe, fn)
    # register -> table-relative constant offset.  None means table-derived but
    # offset depends on an index and therefore cannot be reduced statically.
    taint: dict[str, int | None] = {}
    seeds = []
    accesses = []
    calls = []

    for index, ins in enumerate(insns):
        ops = list(ins.operands)
        writes = set()
        try:
            _, written = ins.regs_access()
            writes = {normalize_reg(md, r) for r in written}
        except Exception:
            pass

        new_taint: tuple[str, int | None] | None = None
        if ops and ops[0].type == op_reg:
            dst = normalize_reg(md, ops[0].reg)
            if ins.mnemonic.lower() == "lea" and len(ops) > 1 and ops[1].type == op_mem:
                mem = ops[1].mem
                if mem.base == rip_reg:
                    target = ins.address + ins.size + int(mem.disp) - IMAGE_BASE
                    if target == TABLE_BEGIN:
                        new_taint = (dst, 0)
                        seeds.append(row_for(ins, IMAGE_BASE))
                else:
                    base = normalize_reg(md, mem.base)
                    idx = normalize_reg(md, mem.index)
                    if base in taint:
                        off = taint[base]
                        if mem.index:
                            off = None
                        elif off is not None:
                            off += int(mem.disp)
                        new_taint = (dst, off)
                    elif idx in taint:
                        new_taint = (dst, None)
            elif ins.mnemonic.lower() in ("mov", "movabs") and len(ops) > 1 and ops[1].type == op_reg:
                src = normalize_reg(md, ops[1].reg)
                if src in taint:
                    new_taint = (dst, taint[src])

        for oi, op in enumerate(ops):
            if ins.mnemonic.lower() == "nop" or op.type != op_mem or op.mem.base == rip_reg:
                continue
            base = normalize_reg(md, op.mem.base)
            idx = normalize_reg(md, op.mem.index)
            source = None
            rel = None
            if base in taint:
                source = base
                base_off = taint[base]
                rel = None if base_off is None or op.mem.index else base_off + int(op.mem.disp)
            elif idx in taint:
                source = idx
            if source is None:
                continue
            access = int(getattr(op, "access", 0) or 0)
            item = row_for(ins, IMAGE_BASE)
            item.update({
                "operand_index": oi,
                "table_register": source,
                "relative_offset": rel,
                "index_register": md.reg_name(op.mem.index) if op.mem.index else None,
                "scale": int(op.mem.scale),
                "disp": int(op.mem.disp),
                "access": access,
                "write": is_write_operand(ins, oi, access, cs_write),
                "context": [row_for(x, IMAGE_BASE) for x in insns[max(0, index-10):min(len(insns), index+11)]],
            })
            accesses.append(item)

        if ins.mnemonic.lower() in ("call", "jmp") and ops:
            arg_taints = {}
            for name in ("rcx", "rdx", "r8", "r9"):
                if name in taint:
                    arg_taints[name] = taint[name]
            if arg_taints:
                item = row_for(ins, IMAGE_BASE)
                item["argument_taints"] = arg_taints
                if ops[0].type == op_imm:
                    value = int(ops[0].imm)
                    item["target_rva"] = value - IMAGE_BASE if value >= IMAGE_BASE else value
                calls.append(item)

        for reg in writes:
            taint.pop(reg, None)
        if ins.mnemonic.lower() == "call":
            for reg in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
                taint.pop(reg, None)
        if new_taint is not None:
            taint[new_taint[0]] = new_taint[1]

    if not seeds:
        return None
    return {
        "function_begin": fn["begin"],
        "function_end": chunks[-1]["end"],
        "runtime_chunks": chunks,
        "seeds": seeds,
        "computed_accesses": accesses,
        "tainted_calls": calls,
        "instructions": [row_for(ins, IMAGE_BASE) for ins in insns] if any(a["write"] for a in accesses) else [],
    }


def self_test() -> None:
    assert TABLE_BYTES == 0x200
    assert TABLE_BEGIN + TABLE_BYTES == 0x22A9AC0
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path, catalogue: Path, game_root: Path, focus_rvas: list[int]) -> dict:
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA mismatch: {digest}")
    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    loaded = load_capstone()
    Cs, arch, mode = loaded[:3]
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True
    constants = loaded[3:]

    with sqlite3.connect(db) as con:
        indexed_function_rvas = {
            int(row[0]) for row in con.execute(
                "SELECT DISTINCT src_fn FROM rip_refs WHERE target=? ORDER BY src_fn",
                (TABLE_BEGIN,),
            )
        }
    functions = []
    for begin in sorted(indexed_function_rvas):
        fn = pe.function_for(begin)
        if fn is None:
            continue
        hit = trace_function(md, pe, fn, constants)
        if hit:
            functions.append(hit)
    writes = [
        {"function_begin": f["function_begin"], **a}
        for f in functions for a in f["computed_accesses"] if a["write"]
    ]
    required_focus = [0x4F3520, 0x4F3660, 0x82CF00, 0x85AC27, 0x858320]
    focus_functions, focus_rows = load_focus_rows(md, pe, required_focus + focus_rvas)
    anchor_rows = {name: focus_rows.get(rva) for name, rva in ANCHORS.items()}
    missing_anchors = []
    for name, row in anchor_rows.items():
        mnemonic, operand_text = ANCHOR_EXPECTED[name]
        if row is None or row["mnemonic"].lower() != mnemonic or operand_text not in row["op_str"].lower():
            missing_anchors.append(name)
    write_sites = {item["rva"] for item in writes}
    static_status = (
        "PASS_REGISTRY_RUNTIME_PROVENANCE_STATIC_TRACE"
        if not missing_anchors and write_sites == {0x4F35A5, 0x4F37A2}
        else "BLOCKED_REGISTRY_RUNTIME_PROVENANCE_STATIC_TRACE"
    )
    raven = load_raven_example(catalogue, game_root)
    return {
        "schema": 1,
        "analysis": "gow_registry_runtime_provenance",
        "status": static_status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"sha256": digest.lower(), "verified": True},
        "registry_table": {"begin": TABLE_BEGIN, "end": TABLE_BEGIN + TABLE_BYTES, "entries": 64},
        "indexed_seed_function_count": len(indexed_function_rvas),
        "function_count": len(functions),
        "computed_write_count": len(writes),
        "computed_writes": writes,
        "functions": functions,
        "focus_functions": focus_functions,
        "anchors": anchor_rows,
        "missing_anchors": missing_anchors,
        "proved": {
            "table_population": "0x4F3660 scans by registry ID; 0x4F37A2 inserts a new registry in first null table entry",
            "constructor": "0x4F36A2-0x4F37A6 zeroes 0x38-byte registry, sets ID, allocates and clears banks, sets capacity 0x400",
            "initial_fields": {"bank_0x20": "zero-filled 0x2000-byte allocation", "cursor_0x28": 0, "live_count_0x2c": 0, "capacity_0x30": 0x400},
            "soft_reset": "0x4F3579 clears +0x10 and 0x4F357C clears cursor +0x28 only; slot bank +0x20 and live count +0x2C are not cleared on this branch",
            "full_teardown": "0x4F35A5 clears table entry, then 0x4F35DD onward frees +0x20 bank and registry",
            "registry_id": "record +0x24 is copied to WAD +0xC3C; new record path computes record_index + 0x12 at 0x82D300-0x82D321",
            "record_0x28": "0x82D219 stores current runtime context ordinal; it is separate from registry cursor +0x28 and does not assign registry ID",
            "allocation_order": "0x85AC27 time-budget scheduler selects outer/inner runtime list indices and calls 0x858320; not a direct physical WAD record walk",
            "no_hint": "0x859BA9 passes 0xFFFFFFFF before 0x859BD6 builder and 0x859C0D loader",
        },
        "raven_example": raven,
        "precise_missing_edge": "bind canonical WAD physical record 9633 to its runtime scheduler allocation ordinal and prove identical prior live/free slot state across reload",
        "safety": {
            "analysis_mode": "read-only", "game_launched": False,
            "active_save_opened": False, "save_or_progression_written": False,
            "exe_written": False,
        },
    }


def render_text(result: dict) -> str:
    lines = [
        "GoW registry runtime provenance trace",
        "=====================================",
        f"status={result['status']}",
        f"gameobject_persistent_key_status={result['gameobject_persistent_key_status']}",
        f"table=0x{result['registry_table']['begin']:X}-0x{result['registry_table']['end']:X}",
        f"functions_with_table_base={result['function_count']}",
        f"computed_writes={result['computed_write_count']}",
        f"missing_anchors={len(result['missing_anchors'])}",
        "",
        "Computed writes",
    ]
    for item in result["computed_writes"]:
        rel = "indexed" if item["relative_offset"] is None else f"table+0x{item['relative_offset']:X}"
        lines.append(
            f"0x{item['rva']:X} fn=0x{item['function_begin']:X} {rel} "
            f"{item['mnemonic']} {item['op_str']}"
        )
    raven = result["raven_example"]
    lines += [
        "",
        "Canonical Raven example",
        f"guid={raven['instance_guid']}",
        f"wad={raven['wad']}",
        f"physical_record_index={raven['physical_record']['record_index']}",
        f"physical_record_offset=0x{raven['physical_record']['offset']:X}",
        f"tuple_reconstructible={str(raven['tuple_reconstructible']).lower()}",
        f"precise_missing_edge={result['precise_missing_edge']}",
    ]
    lines += ["", "All table-base functions"]
    for fn in result["functions"]:
        lines.append(
            f"fn=0x{fn['function_begin']:X}-0x{fn['function_end']:X} "
            f"seeds={len(fn['seeds'])} accesses={len(fn['computed_accesses'])} "
            f"tainted_calls={len(fn['tainted_calls'])}"
        )
        for access in fn["computed_accesses"]:
            kind = "WRITE" if access["write"] else "READ"
            rel = "indexed" if access["relative_offset"] is None else f"+0x{access['relative_offset']:X}"
            lines.append(f"    {kind} 0x{access['rva']:X} {rel} {access['mnemonic']} {access['op_str']}")
        for call in fn["tainted_calls"]:
            target = call.get("target_rva")
            target_text = "indirect" if target is None else f"0x{target:X}"
            lines.append(f"    CALL 0x{call['rva']:X} -> {target_text} args={call['argument_taints']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--exe", type=Path)
    p.add_argument("--db", type=Path)
    p.add_argument("--catalogue", type=Path)
    p.add_argument("--game-root", type=Path)
    p.add_argument("--output-json", type=Path)
    p.add_argument("--output-text", type=Path)
    p.add_argument("--focus-function", action="append", default=[], type=lambda value: int(value, 0))
    a = p.parse_args()
    if a.self_test:
        self_test()
        return 0
    if any(x is None for x in (a.exe, a.db, a.catalogue, a.game_root, a.output_json, a.output_text)):
        p.error("--exe, --db, --catalogue, --game-root, --output-json and --output-text required")
    result = analyze(a.exe, a.db, a.catalogue, a.game_root, a.focus_function)
    a.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    a.output_text.write_text(render_text(result), encoding="utf-8")
    print(result["status"])
    print(f"computed_writes={result['computed_write_count']}")
    print(result["gameobject_persistent_key_status"])
    print(result["production_oracle_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
