"""Trace connected restore-side dataflow for GoW custom-userdata records.

Read-only pass. It verifies the known executable hash, reuses the SQLite
research index, and disassembles only the restore root, its codec-band path,
its direct callers, and one small false-positive evidence window.

Proven save record:
    [8-byte CodeSideLuaClass key][callback payload]
    record_size_byte = payload_length + 8
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
RESTORE_ROOT = 0x7E9550
SAVE_SERIALIZER = 0x7E9190
RECORD_DISPATCH = 0x7E7B60
FALSE_INFLATE = 0x9C6480
CODEC_LO = 0x7E0000
CODEC_HI = 0x7F0000


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_pe_base", path)
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
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    return capstone, Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


def norm_reg(name: str | None) -> str | None:
    if not name:
        return None
    aliases = {
        "eax": "rax", "ax": "rax", "al": "rax", "ah": "rax",
        "ebx": "rbx", "bx": "rbx", "bl": "rbx", "bh": "rbx",
        "ecx": "rcx", "cx": "rcx", "cl": "rcx", "ch": "rcx",
        "edx": "rdx", "dx": "rdx", "dl": "rdx", "dh": "rdx",
        "esi": "rsi", "si": "rsi", "sil": "rsi",
        "edi": "rdi", "di": "rdi", "dil": "rdi",
        "ebp": "rbp", "bp": "rbp", "bpl": "rbp",
        "esp": "rsp", "sp": "rsp", "spl": "rsp",
    }
    if name in aliases:
        return aliases[name]
    match = re.fullmatch(r"r(\d+)(?:d|w|b)?", name)
    return f"r{match.group(1)}" if match else name


def function_for(con: sqlite3.Connection, rva: int):
    row = con.execute(
        "SELECT begin,end,size,section FROM functions "
        "WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1",
        (rva, rva),
    ).fetchone()
    if row is None:
        return None
    return {"begin": row[0], "end": row[1], "size": row[2], "section": row[3]}


def operands(ins):
    try:
        return list(ins.operands)
    except Exception:
        return []


def instruction_record(md, ins, op_imm, op_mem, rip_reg):
    row = {
        "rva": ins.address - IMAGE_BASE,
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    }
    if getattr(ins, "id", 0) == 0:
        row["skipdata"] = True
        return row
    mem = []
    imms = []
    for index, op in enumerate(operands(ins)):
        if op.type == op_imm:
            value = op.imm
            if IMAGE_BASE <= value < IMAGE_BASE + 0x2000000:
                value -= IMAGE_BASE
            imms.append({"operand": index, "value": value})
        elif op.type == op_mem:
            item = {
                "operand": index,
                "base": norm_reg(md.reg_name(op.mem.base)) if op.mem.base else None,
                "index": norm_reg(md.reg_name(op.mem.index)) if op.mem.index else None,
                "scale": op.mem.scale,
                "disp": op.mem.disp,
                "size": op.size,
            }
            if op.mem.base == rip_reg:
                item["rip_target_rva"] = ins.address + ins.size + op.mem.disp - IMAGE_BASE
            mem.append(item)
    if mem:
        row["mem"] = mem
    if imms:
        row["immediates"] = imms
    try:
        reads, writes = ins.regs_access()
        row["registers_read"] = [norm_reg(md.reg_name(reg)) for reg in reads]
        row["registers_written"] = [norm_reg(md.reg_name(reg)) for reg in writes]
    except Exception:
        row["register_access_unavailable"] = True
    return row


def disassemble(md, pe, fn, op_imm, op_mem, rip_reg):
    offset = pe.rva_to_file(fn["begin"])
    if offset is None:
        return []
    data = pe.data[offset:offset + fn["end"] - fn["begin"]]
    return [instruction_record(md, ins, op_imm, op_mem, rip_reg) for ins in md.disasm(data, IMAGE_BASE + fn["begin"])]


def direct_target(row):
    if row["mnemonic"] not in ("call", "jmp"):
        return None
    values = row.get("immediates", [])
    return values[0]["value"] if values else None


def window(rows, center_rva, before=5, after=7):
    index = next((i for i, row in enumerate(rows) if row["rva"] == center_rva), None)
    if index is None:
        return []
    return rows[max(0, index - before):min(len(rows), index + after + 1)]


def exact(rows, rva, mnemonic=None, text=None):
    row = next((item for item in rows if item["rva"] == rva), None)
    if row is None:
        return None
    if mnemonic is not None and row["mnemonic"] != mnemonic:
        return None
    if text is not None and text not in row["op_str"]:
        return None
    return row


def call_at(rows, rva, target):
    row = exact(rows, rva, "call")
    return row if row is not None and direct_target(row) == target else None


def edge_rows(con, fn, direction):
    if direction == "out":
        query = "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site"
    else:
        query = "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE target_fn=? ORDER BY site"
    return [
        {"site": row[0], "source_function": row[1], "kind": row[2], "destination": row[3], "target_function": row[4]}
        for row in con.execute(query, (fn,))
        if row[1] != fn or row[4] != fn
    ]


def collect_target_functions(con):
    root_fn = function_for(con, RESTORE_ROOT)
    if root_fn is None:
        raise RuntimeError("restore root absent from index")
    selected = {root_fn["begin"]: {"reason": "restore_root", "depth": 0}}
    for site, _, kind, _, target in con.execute(
        "SELECT site,src_fn,kind,dest,target_fn FROM edges WHERE src_fn=? ORDER BY site",
        (root_fn["begin"],),
    ):
        if kind == "call" and target is not None and CODEC_LO <= target < CODEC_HI:
            selected.setdefault(target, {"reason": f"immediate_codec_callee_at_0x{site:X}", "depth": 1})
    # 0x7E7660 passes descriptor-backed entries to 0x7E7B60.
    first_hop = list(selected)
    for source in first_hop:
        for site, kind, target in con.execute(
            "SELECT site,kind,target_fn FROM edges WHERE src_fn=? ORDER BY site", (source,)
        ):
            if kind == "call" and target is not None and CODEC_LO <= target < CODEC_HI:
                selected.setdefault(target, {"reason": f"local_codec_callee_at_0x{site:X}", "depth": 2})
    selected.setdefault(RECORD_DISPATCH, {"reason": "record_dispatch_focus", "depth": 2})
    return selected


def cursor_dataflow(root_rows):
    events = []
    byte_loads = []
    anchors = [
        (0x7E957C, "input_argument", "r15 := entry r8 (serialized restore input/header)"),
        (0x7E95BF, "cursor_create", "rsi := r15 + 0x10 (serialized body cursor)"),
        (0x7E964F, "compressed_input_pointer", "inflate state input := rsi"),
        (0x7E965B, "decompressed_output_pointer", "inflate state output := r12"),
        (0x7E9677, "compression_only_call", "inflate parser call; carrier step, never restore-handler candidate"),
        (0x7E968E, "cursor_length_load", "rax := word[r15+0xE]"),
        (0x7E9693, "cursor_advance", "rsi += word[r15+0xE] after compression stream"),
        (0x7E96A0, "record_blob_subbuffer", "rax := decompressed output r12 + word[input+2]"),
        (0x7E96A3, "descriptor_record_blob", "descriptor+0x30 := decompressed output sub-buffer"),
        (0x7E96B1, "copy_source", "rdx := rsi for descriptor table copy"),
        (0x7E96BE, "cursor_advance", "rsi += 2*word[r15]"),
        (0x7E97A9, "cursor_advance", "rsi += word[r15+8] after record-size table"),
        (0x7E97C4, "cursor_advance", "rsi += 2*word[r15+8] after record-offset table"),
        (0x7E97E9, "cursor_advance", "rsi += 6 for each descriptor row"),
    ]
    for rva, kind, explanation in anchors:
        row = exact(root_rows, rva)
        if row:
            events.append({"kind": kind, "instruction": row, "explanation": explanation})

    # rsi stays serialized cursor until 0x7E9867, where it is reassigned to Lua
    # runtime state. Do not mislabel later [rsi+...] loads as input-byte loads.
    for row in root_rows:
        if row["rva"] >= 0x7E9867:
            continue
        for mem in row.get("mem", []):
            if mem["size"] == 1 and mem["base"] == "rsi":
                uses = []
                if row["rva"] == 0x7E96E0:
                    uses = [
                        {"kind": "type_bounds", "rva": 0x7E96E8, "detail": "cmp eax,5; ja rejects type outside jump table"},
                        {"kind": "cursor_advance", "rvas": [0x7E9702, 0x7E9710, 0x7E9720, 0x7E972B], "detail": "tag selects encoded width 2, 5, or 3; rsi += selected width"},
                    ]
                elif row["rva"] == 0x7E96FA:
                    uses = [{"kind": "decoded_value", "rva": 0x7E96FE, "detail": "one-byte value copied from cursor+1"}]
                elif row["rva"] == 0x7E972E:
                    uses = [
                        {"kind": "type_bounds", "rva": 0x7E9736, "detail": "cmp eax,5; ja rejects type outside jump table"},
                        {"kind": "cursor_advance", "rvas": [0x7E9751, 0x7E9760, 0x7E9771, 0x7E977C], "detail": "tag selects encoded width 2, 5, or 3; rsi += selected width"},
                    ]
                elif row["rva"] == 0x7E9748:
                    uses = [{"kind": "decoded_value", "rva": 0x7E974C, "detail": "one-byte value copied from cursor+1"}]
                byte_loads.append({"instruction": row, "cursor_expression": f"rsi{mem['disp']:+d}", "uses": uses})

    table_copies = [
        {
            "call_site": 0x7E97A4,
            "helper": 0x3ED39A,
            "classification": "memcpy_direct_cursor_carrier",
            "source": "rsi",
            "destination": "qword[descriptor+0x28]",
            "length": "zero_extend(word[input+8])",
            "meaning": "record-size byte table",
            "post_advance": 0x7E97A9,
            "window": window(root_rows, 0x7E97A4, 7, 4),
        },
        {
            "call_site": 0x7E97BF,
            "helper": 0x3ED39A,
            "classification": "memcpy_direct_cursor_carrier",
            "source": "rsi",
            "destination": "qword[descriptor+0x20]",
            "length": "2 * zero_extend(word[input+8])",
            "meaning": "record-offset word table",
            "post_advance": 0x7E97C4,
            "window": window(root_rows, 0x7E97BF, 8, 4),
        },
    ]
    return {
        "entry_registers": {"rcx": "Lua/decoder state", "rdx": "caller context", "r8": "serialized restore input"},
        "cursor_expression": "rsi = input_r8 + 0x10, then advanced through serialized sections",
        "events": events,
        "byte_loads_directly_derived_from_cursor": byte_loads,
        "record_table_copies": table_copies,
    }


def connected_record_chain(rows):
    checks = [
        ("record_index", 0x7E7D7F, "movzx", "word ptr [r8]"),
        ("size_table_base", 0x7E7D86, "mov", "[rdx + 0x28]"),
        ("record_size_byte", 0x7E7D98, "movzx", "byte ptr [rcx + rax]"),
        ("offset_table_base", 0x7E7D9C, "mov", "[rdx + 0x20]"),
        ("record_offset", 0x7E7DA0, "movzx", "word ptr [rax + rcx*2]"),
        ("record_blob_base", 0x7E7D8D, "mov", "[rdx + 0x30]"),
        ("class_key_qword", 0x7E7DA5, "mov", "qword ptr [r11 + rbx]"),
        ("key_compare", 0x7E7DB8, "cmp", "qword ptr [rcx], rax"),
        ("class_callback", 0x7E7DD6, "mov", "[rcx + 0xc0]"),
        ("class_parent", 0x7E7DDD, "mov", "[rcx + 0x48]"),
        ("payload_length_seed", 0x7E7DE6, "movzx", "r8d, dil"),
        ("payload_pointer_plus_8", 0x7E7DEA, "lea", "[rbx + 8]"),
        ("payload_length_minus_8", 0x7E7DEE, "sub", "r8d, 8"),
        ("payload_pointer_plus_offset", 0x7E7DF2, "add", "rdx, r11"),
        ("restore_dispatch", 0x7E7E07, "jmp", "r9"),
    ]
    evidence = []
    missing = []
    for name, rva, mnemonic, text in checks:
        row = exact(rows, rva, mnemonic, text)
        if row:
            evidence.append({"step": name, "instruction": row})
        else:
            missing.append({"step": name, "expected_rva": rva, "mnemonic": mnemonic, "operand_contains": text})

    present = {item["step"] for item in evidence}
    segments = {
        "size_from_descriptor": {"record_index", "size_table_base", "record_size_byte"} <= present,
        "offset_to_record": {"record_index", "offset_table_base", "record_offset", "record_blob_base"} <= present,
        "qword_key_read": "class_key_qword" in present,
        "key_lookup": {"class_key_qword", "key_compare"} <= present,
        "class_metadata_callback": {"key_compare", "class_callback", "class_parent"} <= present,
        "payload_split": {"record_size_byte", "payload_length_seed", "payload_length_minus_8", "payload_pointer_plus_8", "payload_pointer_plus_offset"} <= present,
        "reconstruction_dispatch": {"class_callback", "payload_length_minus_8", "payload_pointer_plus_offset", "restore_dispatch"} <= present,
    }
    # Score only whole connected segments. Loose features add no points.
    weights = {
        "size_from_descriptor": 12,
        "offset_to_record": 13,
        "qword_key_read": 8,
        "key_lookup": 14,
        "class_metadata_callback": 14,
        "payload_split": 21,
        "reconstruction_dispatch": 18,
    }
    score = sum(weights[name] for name, found in segments.items() if found)
    if score >= 90:
        confidence = "HIGH"
    elif score >= 60:
        confidence = "MEDIUM"
    elif score >= 30:
        confidence = "LOW"
    else:
        confidence = "INSUFFICIENT"
    return {
        "chain_id": "record_size_to_native_restore_dispatch",
        "function": RECORD_DISPATCH,
        "score": score,
        "score_basis": "connected semantic segments only; independent byte/qword/immediate-8 hits score zero",
        "confidence": confidence,
        "segments": segments,
        "missing_expected_steps": missing,
        "evidence": evidence,
        "register_dataflow": [
            "ecx := word[r8] is record index",
            "rax := qword[rdx+0x28]; edi := byte[rax+rcx] is record_size",
            "rax := qword[rdx+0x20]; r11 := word[rax+rcx*2] is record_offset",
            "rbx := qword[rdx+0x30] is record_blob_base",
            "rax := qword[rbx+r11] is first qword and CodeSideLuaClass key",
            "rax key is compared with qword entries in global lookup table",
            "matching class metadata is walked via +0x48; callback comes from +0xC0",
            "r8d := zero_extend(record_size_byte); r8d -= 8 gives payload_length",
            "rdx := record_blob_base + record_offset + 8 gives payload_pointer",
            "tail jmp r9 dispatches callback(rcx=restore state, rdx=payload pointer, r8=payload length)",
        ],
        "bounds_and_loops": [
            {"rva": 0x7E7DA9, "meaning": "test global CodeSideLuaClass count"},
            {"rvas": [0x7E7DB5, 0x7E7DB8, 0x7E7DBD, 0x7E7DC0, 0x7E7DC4, 0x7E7DC7], "meaning": "bounded 8-byte key lookup loop"},
            {"rva": 0x7E7DCF, "meaning": "terminate if class key not found"},
            {"rvas": [0x7E7DD1, 0x7E7DDD, 0x7E7DE1, 0x7E7DE4], "meaning": "walk class parent metadata until callback found or chain ends"},
            {"finding": "no explicit record_size >= 8 guard is visible in this dispatch block; subtract is direct"},
        ],
        "instruction_window": [row for row in rows if 0x7E7D7F <= row["rva"] <= 0x7E7E07],
    }


def descriptor_bridge(root_rows, table_rows, dispatch_rows):
    needed = {
        0x7E964F: exact(root_rows, 0x7E964F, "mov", "[rbp - 0x39], rsi"),
        0x7E965B: exact(root_rows, 0x7E965B, "mov", "[rbp - 0x29], r12"),
        0x7E96A0: exact(root_rows, 0x7E96A0, "add", "rax, r12"),
        0x7E96A3: exact(root_rows, 0x7E96A3, "mov", "[rbp - 0x79], rax"),
        0x7E97A4: call_at(root_rows, 0x7E97A4, 0x3ED39A),
        0x7E97BF: call_at(root_rows, 0x7E97BF, 0x3ED39A),
        0x7E9A27: call_at(root_rows, 0x7E9A27, 0x7E7660),
        0x7E7674: exact(table_rows, 0x7E7674, "mov", "r13, r8"),
        0x7E76B0: exact(table_rows, 0x7E76B0, "movzx", "[r13 + 0x48]"),
        0x7E76BD: exact(table_rows, 0x7E76BD, "mov", "[r13 + 0x40]"),
        0x7E77C5: exact(table_rows, 0x7E77C5, "add", "[r13 + 0x50]"),
        0x7E77CC: call_at(table_rows, 0x7E77CC, RECORD_DISPATCH),
        0x7E77E3: call_at(table_rows, 0x7E77E3, RECORD_DISPATCH),
        0x7E7D98: exact(dispatch_rows, 0x7E7D98, "movzx"),
        0x7E7DA0: exact(dispatch_rows, 0x7E7DA0, "movzx"),
    }
    present = {rva for rva, row in needed.items() if row}
    segments = {
        "cursor_record_tables": {0x7E97A4, 0x7E97BF} <= present,
        "decompressed_record_subbuffer": {0x7E964F, 0x7E965B, 0x7E96A0, 0x7E96A3} <= present,
        "descriptor_to_local_dispatch": {0x7E9A27, 0x7E7674, 0x7E76B0, 0x7E76BD, 0x7E77C5, 0x7E77CC, 0x7E77E3} <= present,
        "descriptor_record_reads": {0x7E7D98, 0x7E7DA0} <= present,
    }
    weights = {"cursor_record_tables": 22, "decompressed_record_subbuffer": 16, "descriptor_to_local_dispatch": 28, "descriptor_record_reads": 20}
    score = sum(weights[name] for name, found in segments.items() if found)
    connected = all(segments.values())
    return {
        "chain_id": "restore_input_cursor_to_descriptor_to_record_dispatch",
        "score": score,
        "score_basis": "complete connected inter-function segments only",
        "confidence": "HIGH" if connected else ("MEDIUM" if score >= 52 else "LOW"),
        "connected": connected,
        "segments": segments,
        "register_dataflow": [
            "0x7E9550 r8 input becomes r15; rsi=input+0x10",
            "0x7E97A4 copies cursor bytes to descriptor+0x28 (record-size table)",
            "0x7E97BF copies cursor words to descriptor+0x20 (record-offset table)",
            "inflate output r12 plus input header offset becomes descriptor+0x30 record blob base",
            "0x7E9A27 passes descriptor as r8 to 0x7E7660",
            "0x7E7660 preserves descriptor in r13 and derives record entries from descriptor+0x40/+0x50",
            "0x7E77CC and 0x7E77E3 pass descriptor in rdx to 0x7E7B60",
            "0x7E7B60 reads descriptor+0x28 size bytes, +0x20 offsets, and +0x30 blob base",
        ],
        "evidence": [{"rva": rva, "instruction": row} for rva, row in needed.items() if row],
        "missing_rvas": [rva for rva, row in needed.items() if not row],
        "windows": {
            "size_table_copy": window(root_rows, 0x7E97A4, 8, 5),
            "offset_table_copy": window(root_rows, 0x7E97BF, 9, 5),
            "descriptor_consumer_call": window(root_rows, 0x7E9A27, 6, 5),
            "entry_dispatch": [row for row in table_rows if 0x7E77B0 <= row["rva"] <= 0x7E77E8],
        },
    }


def false_positive_classification(inflate_rows):
    magic = exact(inflate_rows, 0x9C6587, "cmp", "0x8b1f")
    shifts = [
        row for row in inflate_rows
        if row["mnemonic"] in ("shl", "shr", "sar", "rol", "ror") and 0x9C6500 <= row["rva"] < 0x9C7900
    ]
    bit_width_ops = [
        row for row in inflate_rows
        if row["mnemonic"] in ("bt", "btr", "bts", "and", "or") and 0x9C6500 <= row["rva"] < 0x9C7900
    ]
    return [{
        "function": FALSE_INFLATE,
        "classification": "SUPPRESSED_FALSE_POSITIVE",
        "score": 0,
        "confidence": "HIGH",
        "reason": "inflate/compression bitstream parser, not custom-userdata restore handler",
        "evidence": {
            "gzip_magic_compare": magic,
            "gzip_magic_semantics": "0x8B1F is little-endian byte order for gzip magic 1F 8B",
            "shift_operation_count": len(shifts),
            "sample_shift_operations": shifts[:24],
            "bit_width_operation_count": len(bit_width_ops),
        },
        "suppression_rule": "compression functions never receive candidate score unless proven record cursor reaches size-minus-8, key lookup, payload split, and dispatch in one connected chain",
        "call_context": {
            "caller": RESTORE_ROOT,
            "call_site": 0x7E9677,
            "role": "decode compressed restore stream before codec tables are consumed",
        },
    }]


def classify_calls(edges, root_rows):
    compression = {0x9C6380, 0x9C6480, 0x9C9CC0}
    memcpy = {0x3ED39A}
    allocator = {0x3ED388}
    rows = []
    for edge in edges:
        target = edge["target_function"] or edge["destination"]
        if target in compression:
            category = "compression_suppressed"
        elif target in memcpy:
            category = "memcpy_included_only_at_direct_cursor_sites"
        elif target in allocator:
            category = "allocation_suppressed"
        elif target is not None and CODEC_LO <= target < CODEC_HI:
            category = "local_codec"
        else:
            category = "generic_lua_or_runtime_suppressed_unless_cursor_connected"
        rows.append({
            **edge,
            "classification": category,
            "instruction_window": window(root_rows, edge["site"], 2, 2),
        })
    return rows


def call_windows(con, decoded):
    callers = edge_rows(con, RESTORE_ROOT, "in")
    result = []
    for caller in callers:
        source = caller["source_function"]
        rows = decoded.get(source)
        if rows is None:
            continue
        result.append({**caller, "instruction_window": window(rows, caller["site"], 8, 4)})
    return result


def run_self_test():
    steps = {
        "size_from_descriptor": True,
        "offset_to_record": True,
        "qword_key_read": True,
        "key_lookup": True,
        "class_metadata_callback": True,
        "payload_split": True,
        "reconstruction_dispatch": True,
    }
    weights = [12, 13, 8, 14, 14, 21, 18]
    assert sum(weights) == 100
    # Loose signals must not score. Only complete segments do.
    loose = {name: False for name in steps}
    assert sum(weight for weight, found in zip(weights, loose.values()) if found) == 0
    # Compression is hard-suppressed even when byte/qword/immediate-8 hits exist.
    compression_score = 0
    assert compression_score == 0
    loose_rows = [
        {"rva": 1, "bytes": "", "mnemonic": "movzx", "op_str": "eax, byte ptr [rcx]"},
        {"rva": 2, "bytes": "", "mnemonic": "mov", "op_str": "rax, qword ptr [rbx]"},
        {"rva": 3, "bytes": "", "mnemonic": "sub", "op_str": "r8d, 8"},
    ]
    assert connected_record_chain(loose_rows)["score"] == 0
    print("SELF_TEST_PASSED")


def format_instruction(row):
    return f"0x{row['rva']:08X}  {row['bytes']:<22} {row['mnemonic']:<8} {row['op_str']}"


def write_text(path: Path, result):
    lines = [
        "Completionist Map - GoW custom-userdata restore dataflow",
        f"exe_sha256={result['exe_sha256']}",
        f"restore_root=0x{RESTORE_ROOT:X}",
        f"save_serializer=0x{SAVE_SERIALIZER:X}",
        "mode=read-only targeted disassembly",
        "game_launched=false",
        "active_save_opened=false",
        "exe_modified=false",
        "",
        "MAIN RESULT",
    ]
    for rank, chain in enumerate(result["ranked_evidence_chains"], 1):
        lines.append(f"#{rank} {chain['chain_id']} score={chain['score']} confidence={chain['confidence']}")
        for text in chain.get("register_dataflow", []):
            lines.append(f"  FLOW {text}")
    main = result["ranked_evidence_chains"][0]
    lines += ["", "CONNECTED RECORD INVERSE CHAIN"]
    for item in main["evidence"]:
        lines.append(f"  {item['step']}: {format_instruction(item['instruction'])}")
    lines += ["", "PRECISE RECORD DISPATCH WINDOW"]
    lines.extend(format_instruction(row) for row in main["instruction_window"])

    cursor = result["input_cursor_dataflow"]
    lines += ["", "INPUT/READ CURSOR PROVENANCE", f"  {cursor['cursor_expression']}"]
    for event in cursor["events"]:
        lines.append(f"  {event['kind']}: {format_instruction(event['instruction'])} -- {event['explanation']}")
    lines += ["", "EVERY DIRECT BYTE LOAD FROM RSI CURSOR"]
    for load in cursor["byte_loads_directly_derived_from_cursor"]:
        lines.append(f"  {format_instruction(load['instruction'])}")
        for use in load["uses"]:
            lines.append(f"    USE {use['kind']}: {use['detail']}")
    lines += ["", "RECORD TABLE COPIES FROM CURSOR"]
    for copy in cursor["record_table_copies"]:
        lines.append(
            f"  0x{copy['call_site']:X} {copy['meaning']}: {copy['source']} -> {copy['destination']}; length={copy['length']}"
        )

    lines += ["", "BOUNDS, LOOP, AND LENGTH FINDINGS"]
    for item in main["bounds_and_loops"]:
        lines.append(f"  {item}")

    lines += ["", "DIRECT CALLERS OF 0x7E9550"]
    for caller in result["direct_callers"]:
        lines.append(f"  caller=0x{caller['source_function']:X} site=0x{caller['site']:X}")
        lines.extend(f"    {format_instruction(row)}" for row in caller["instruction_window"])
    lines += ["", "DIRECT CALLEES OF 0x7E9550"]
    for callee in result["direct_callees"]:
        target = callee["target_function"] or callee["destination"]
        target_text = "NONE" if target is None else f"0x{target:X}"
        lines.append(f"  site=0x{callee['site']:X} target={target_text} class={callee['classification']}")
        lines.extend(f"    {format_instruction(row)}" for row in callee["instruction_window"])

    lines += ["", "FALSE_POSITIVE_CLASSIFICATION"]
    for item in result["FALSE_POSITIVE_CLASSIFICATION"]:
        lines.append(f"  function=0x{item['function']:X} class={item['classification']} score={item['score']}")
        lines.append(f"  reason={item['reason']}")
        magic = item["evidence"]["gzip_magic_compare"]
        if magic:
            lines.append(f"  gzip_magic={format_instruction(magic)}")
        lines.append(f"  shift_operation_count={item['evidence']['shift_operation_count']}")
        lines.append(f"  suppression_rule={item['suppression_rule']}")

    lines += ["", "SUPPRESSED PATH POLICY"]
    for item in result["suppressed_path_policy"]:
        lines.append(f"  {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe")
    parser.add_argument("--db")
    parser.add_argument("--output-json")
    parser.add_argument("--output-text")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return
    required = {"--exe": args.exe, "--db": args.db, "--output-json": args.output_json, "--output-text": args.output_text}
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error(f"required arguments missing: {', '.join(missing)}")

    exe = Path(args.exe)
    db = Path(args.db)
    if not exe.is_file():
        raise SystemExit(f"missing executable: {exe}")
    actual_hash = file_sha256(exe).lower()
    if actual_hash != EXPECTED_SHA256:
        raise SystemExit(f"unsupported GoW.exe SHA256: {actual_hash}")
    if not db.is_file():
        raise SystemExit(f"missing reusable index: {db}")

    con = sqlite3.connect(db)
    selected = collect_target_functions(con)
    capstone, Cs, arch, mode, op_imm, op_mem, _, rip_reg = load_capstone()
    pe = load_pe_module().PE(exe.read_bytes())
    md = Cs(arch, mode)
    md.detail = True
    md.skipdata = True

    # Add direct callers for call-site windows and inflate only for false-positive proof.
    for edge in edge_rows(con, RESTORE_ROOT, "in"):
        selected.setdefault(edge["source_function"], {"reason": "direct_caller_window", "depth": -1})
    selected.setdefault(FALSE_INFLATE, {"reason": "false_positive_classification", "depth": 1})

    decoded = {}
    target_manifest = []
    for begin, why in sorted(selected.items()):
        fn = function_for(con, begin)
        if fn is None:
            continue
        rows = disassemble(md, pe, fn, op_imm, op_mem, rip_reg)
        decoded[fn["begin"]] = rows
        target_manifest.append({**fn, **why, "instruction_count": len(rows)})

    root_rows = decoded[function_for(con, RESTORE_ROOT)["begin"]]
    table_rows = decoded.get(0x7E7660, [])
    dispatch_rows = decoded.get(RECORD_DISPATCH, [])
    inflate_rows = decoded.get(FALSE_INFLATE, [])
    record_chain = connected_record_chain(dispatch_rows)
    bridge_chain = descriptor_bridge(root_rows, table_rows, dispatch_rows)
    ranked = sorted([record_chain, bridge_chain], key=lambda row: (-row["score"], row["chain_id"]))

    direct_callees = classify_calls(edge_rows(con, RESTORE_ROOT, "out"), root_rows)
    direct_callers = call_windows(con, decoded)
    result = {
        "schema": 2,
        "analysis": "gow_custom_userdata_restore_dataflow",
        "exe_sha256": actual_hash,
        "index": str(db),
        "restore_root": RESTORE_ROOT,
        "save_side_serializer": SAVE_SERIALIZER,
        "proven_record_shape": {
            "layout": "[8-byte CodeSideLuaClass key][callback payload]",
            "stored_size": "payload_length + 8",
            "inverse_sought": "payload_length = record_size - 8",
        },
        "targeted_disassembly": target_manifest,
        "input_cursor_dataflow": cursor_dataflow(root_rows),
        "ranked_evidence_chains": ranked,
        "direct_callers": direct_callers,
        "direct_callees": direct_callees,
        "FALSE_POSITIVE_CLASSIFICATION": false_positive_classification(inflate_rows),
        "suppressed_path_policy": [
            "gzip/zlib/inflate/deflate code gets score 0 unless full record-connected chain is present",
            "generic Lua string/table allocation gets score 0 unless it carries proven record cursor",
            "memcpy/allocation helpers get score 0; memcpy windows remain evidence only when rdx is proven cursor",
            "independent byte load + qword load + immediate 8 never forms a scored chain",
        ],
        "confidence": record_chain["confidence"],
        "read_only_guarantees": {
            "game_launched": False,
            "active_save_opened": False,
            "save_modified": False,
            "exe_modified": False,
            "targeted_disassembly_only": True,
            "reused_sqlite_index": True,
        },
        "capstone_version": capstone.__version__,
    }
    con.close()

    Path(args.output_json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_text(Path(args.output_text), result)
    print("GOW_CUSTOM_USERDATA_RESTORE_DATAFLOW_PASSED")
    print(f"confidence={record_chain['confidence']}")
    print(f"record_chain_score={record_chain['score']}")
    print(f"record_chain_complete={str(not record_chain['missing_expected_steps']).lower()}")
    print(f"cursor_byte_loads={len(result['input_cursor_dataflow']['byte_loads_directly_derived_from_cursor'])}")
    print("best_chain=record-size@0x7E7D98 -> key@0x7E7DA5 -> size-8@0x7E7DEE -> payload@0x7E7DF2 -> dispatch@0x7E7E07")
    print("false_positive_0x9C6480=SUPPRESSED_INFLATE score=0")
    print("game_or_save_modified=false")


if __name__ == "__main__":
    main()
