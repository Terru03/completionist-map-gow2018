"""Recover exact static CodeSideLuaClass persistence registry entries.

Read-only, version-locked analysis. This follows only exact globals proven at
0x7E7D91..0x7E7DD6 plus their direct static writers and CRT entries. It does
not scan saves or launch game.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
REGISTRY_COUNT = 0x22AE7DC
REGISTRY_TABLE = 0x22AE820
RESTORE_LOOKUPS = (0x7E7B60, 0x7E7E40)
SAVE_SERIALIZER = 0x7E9190
GAMEOBJECT_TARGETS = {
    "OnPickleInternal": 0x5B2130,
    "OnUnpickleInternal": 0x5B2324,
    "gameobject_resolver": 0x4EF0B0,
    "gameobject_unbox": 0x5F9350,
}
ENTRIES = (
    {
        "name": "GroundType", "name_rva": 0xE0E7D8,
        "initializer": 0x3B8B0, "metadata": 0x2C2AEF0,
        "crt_pointer": 0xD4AD68, "aux_f0": 0x107CFE0,
        "aux_f8": 0x107D0F0,
    },
    {
        "name": "CollisionType", "name_rva": 0xE0E7E8,
        "initializer": 0x3BAE0, "metadata": 0x2C2A510,
        "crt_pointer": 0xD4AD70, "aux_f0": 0x107D2B0,
        "aux_f8": 0x107D210,
    },
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def class_key(name: str) -> int:
    value = 0
    for byte in name.encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_registry_pe", path)
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
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    return Cs, CS_ARCH_X86, CS_MODE_64, X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def read_c_string(pe, rva: int) -> str:
    off = pe.rva_to_file(rva)
    if off is None:
        raise RuntimeError(f"string RVA not file-backed: 0x{rva:X}")
    end = pe.data.find(b"\0", off)
    if end < 0:
        raise RuntimeError(f"unterminated string at 0x{rva:X}")
    return pe.data[off:end].decode("ascii")


def read_qword(pe, rva: int) -> int | None:
    off = pe.rva_to_file(rva)
    if off is None or off + 8 > len(pe.data):
        return None
    return struct.unpack_from("<Q", pe.data, off)[0]


def disassemble(md, pe, begin: int, op_imm: int, op_mem: int, rip_reg: int):
    fn = pe.function_for(begin)
    if fn is None or fn["begin"] != begin:
        raise RuntimeError(f"function boundary absent: 0x{begin:X}")
    out = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + begin):
        row = {
            "rva": ins.address - IMAGE_BASE,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        }
        rip_targets = []
        immediates = []
        for op in ins.operands:
            if op.type == op_imm:
                value = op.imm
                if IMAGE_BASE <= value < IMAGE_BASE + pe.size_of_image:
                    value -= IMAGE_BASE
                immediates.append(value)
            elif op.type == op_mem and op.mem.base == rip_reg:
                rip_targets.append(ins.address + ins.size + op.mem.disp - IMAGE_BASE)
        if rip_targets:
            row["rip_targets"] = rip_targets
        if immediates:
            row["immediates"] = immediates
        out.append(row)
    return out


def exact(rows, rva: int, mnemonic: str | None = None, fragment: str | None = None):
    row = next((item for item in rows if item["rva"] == rva), None)
    if row is None:
        return None
    if mnemonic and row["mnemonic"] != mnemonic:
        return None
    if fragment and fragment not in row["op_str"]:
        return None
    return row


def self_test() -> None:
    assert class_key("GroundType") == 0x994A9F8D559DEF45
    assert class_key("CollisionType") == 0x92272F4435C83E6C
    assert class_key("") == 0
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path):
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")
    if not db.is_file():
        raise RuntimeError(f"missing research index: {db}")

    pe_mod = load_pe_module()
    pe = pe_mod.PE(exe.read_bytes())
    Cs, arch, mode, op_imm, op_mem, rip_reg = load_capstone()
    md = Cs(arch, mode)
    md.detail = True
    con = sqlite3.connect(db)

    count_refs = [
        {"site": a, "function": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site",
            (REGISTRY_COUNT,),
        )
    ]
    table_refs = [
        {"site": a, "function": b, "mnemonic": c}
        for a, b, c in con.execute(
            "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site",
            (REGISTRY_TABLE,),
        )
    ]
    aliases = {
        "count_data_pointers": con.execute(
            "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (REGISTRY_COUNT,)
        ).fetchall(),
        "table_data_pointers": con.execute(
            "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva", (REGISTRY_TABLE,)
        ).fetchall(),
        "count_immediates": con.execute(
            "SELECT site FROM imm_refs WHERE value_rva=? ORDER BY site", (REGISTRY_COUNT,)
        ).fetchall(),
        "table_immediates": con.execute(
            "SELECT site FROM imm_refs WHERE value_rva=? ORDER BY site", (REGISTRY_TABLE,)
        ).fetchall(),
    }

    expected_count_sites = [0x3B924, 0x3B960, 0x3BB54, 0x3BB90, 0x7E7D91, 0x7E7E51]
    if [row["site"] for row in count_refs] != expected_count_sites:
        raise AssertionError("exact registry-count reference set changed")
    if [row["site"] for row in table_refs] != [0x7E7DAE, 0x7E7E78]:
        raise AssertionError("exact registry-table RIP reference set changed")
    if any(aliases.values()):
        raise AssertionError("unexpected static alias to registry globals")

    init_rows = {
        entry["initializer"]: disassemble(md, pe, entry["initializer"], op_imm, op_mem, rip_reg)
        for entry in ENTRIES
    }
    lookup_rows = {
        begin: disassemble(md, pe, begin, op_imm, op_mem, rip_reg)
        for begin in RESTORE_LOOKUPS
    }
    save_rows = disassemble(md, pe, SAVE_SERIALIZER, op_imm, op_mem, rip_reg)
    recovered = []
    for index, spec in enumerate(ENTRIES):
        rows = init_rows[spec["initializer"]]
        name = read_c_string(pe, spec["name_rva"])
        if name != spec["name"]:
            raise AssertionError(f"name mismatch for 0x{spec['initializer']:X}")
        if read_qword(pe, spec["crt_pointer"]) != IMAGE_BASE + spec["initializer"]:
            raise AssertionError(f"CRT pointer mismatch for {name}")

        # Verify semantic anchors by absolute sites; compiler layouts differ by
        # 0x230 only, so exact known sites keep claims fail-closed.
        anchors = (
            (0x3B8F3, 0x3B904, 0x3B924, 0x3B956, 0x3B960, 0x3B92B, 0x3B932, 0x3B939, 0x3B940)
            if index == 0 else
            (0x3BB23, 0x3BB34, 0x3BB54, 0x3BB86, 0x3BB90, 0x3BB5B, 0x3BB62, 0x3BB69, 0x3BB70)
        )
        evidence = [exact(rows, site) for site in anchors]
        if any(row is None for row in evidence):
            raise AssertionError(f"initializer anchors missing for {name}")
        if REGISTRY_COUNT not in evidence[2].get("rip_targets", []):
            raise AssertionError(f"count load not proved for {name}")
        if hex(REGISTRY_TABLE)[2:] not in evidence[3]["op_str"].lower():
            raise AssertionError(f"indexed table append not proved for {name}")
        if REGISTRY_COUNT not in evidence[4].get("rip_targets", []):
            raise AssertionError(f"count update not proved for {name}")
        if spec["aux_f0"] not in evidence[5].get("rip_targets", []):
            raise AssertionError(f"+0xF0 source not proved for {name}")
        if spec["metadata"] + 0xF0 not in evidence[6].get("rip_targets", []):
            raise AssertionError(f"+0xF0 store not proved for {name}")
        if spec["aux_f8"] not in evidence[7].get("rip_targets", []):
            raise AssertionError(f"+0xF8 source not proved for {name}")
        if spec["metadata"] + 0xF8 not in evidence[8].get("rip_targets", []):
            raise AssertionError(f"+0xF8 store not proved for {name}")

        metadata_section = pe.section_for_rva(spec["metadata"])
        if metadata_section is None or pe.rva_to_file(spec["metadata"]) is not None:
            raise AssertionError(f"expected zero-fill metadata for {name}")
        callback_slots = {
            "+0xA8": None, "+0xB0": None, "+0xB8_save": None,
            "+0xC0_restore": None, "+0xC8": None, "+0xD0": None,
        }
        recovered.append({
            "registry_index": index,
            "class_metadata_rva": spec["metadata"],
            "class_key": class_key(name),
            "name": name,
            "name_storage": {"source_rva": spec["name_rva"], "inline_offset": 0x64},
            "parent_plus_0x48": None,
            "callback_slots": callback_slots,
            "neighbouring_noncallback_fields": {
                "+0xF0": spec["aux_f0"], "+0xF8": spec["aux_f8"],
                "classification": "non-executable enum descriptor/value tables",
            },
            "initializer_rva": spec["initializer"],
            "registration_provenance": {
                "crt_pointer_rva": spec["crt_pointer"],
                "registry_append_site": evidence[3]["rva"],
                "count_load_site": evidence[2]["rva"],
                "count_increment_store_site": evidence[4]["rva"],
            },
            "initializer_evidence": evidence,
            "zero_fill_basis": "metadata lies in .data virtual tail with no raw-file backing; no initializer store targets +0x48/+0xB8/+0xC0",
            "gameobject_connectivity": {
                "has_persistence_callback": False,
                "paths_to_gameobject_targets": [],
            },
        })

    lookup_evidence = {}
    for begin, rows in lookup_rows.items():
        selected = [row for row in rows if any(
            target in row.get("rip_targets", []) for target in (REGISTRY_COUNT, REGISTRY_TABLE)
        ) or any(fragment in row["op_str"] for fragment in ("[rcx + 0xb8]", "[rcx + 0xc0]", "[rcx + 0x48]"))]
        lookup_evidence[f"0x{begin:X}"] = selected
    save_evidence = [
        exact(save_rows, 0x7E925F, "mov", "[rax + 0xb8]"),
        exact(save_rows, 0x7E9266, "mov", "[rax + 0x48]"),
        exact(save_rows, 0x7E9298, "call", "r10"),
    ]
    if any(row is None for row in save_evidence):
        raise AssertionError("save-side +0xB8 callback chain changed")
    lookup_evidence[f"0x{SAVE_SERIALIZER:X}"] = save_evidence

    result = {
        "schema": 1,
        "analysis": "gow_codeside_class_registry",
        "exe_sha256": digest,
        "registry": {
            "count_global_rva": REGISTRY_COUNT,
            "pointer_table_rva": REGISTRY_TABLE,
            "static_count_after_crt_initializers": len(recovered),
            "entry_size": 8,
            "crt_order_proved": True,
            "entries": recovered,
        },
        "reference_audit": {
            "count_refs": count_refs,
            "table_rip_refs": table_refs,
            "static_aliases": aliases,
            "scope": "exact registry globals, direct writers, two lookup consumers, and CRT pointers only",
            "broad_heuristic_scan": False,
        },
        "lookup_evidence": lookup_evidence,
        "callback_mapping": [
            {
                "class_key": row["class_key"],
                "class_name": row["name"],
                "save_plus_0xB8": None,
                "restore_plus_0xC0": None,
                "parent_plus_0x48": None,
            }
            for row in recovered
        ],
        "gameobject_persistence_class": None,
        "gameobject_payload_layout": None,
        "frozen_save_decoder_created": False,
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "blocker": (
            "The exact static registry contains only GroundType and CollisionType. Both have null parent, "
            "null +0xB8 save callback, and null +0xC0 restore callback. No connected registry pointer/callback "
            "evidence reaches OnUnpickleInternal 0x5B2324, OnPickleInternal 0x5B2130, the GameObject resolver, "
            "or unbox machinery. Therefore GameObject payload bytes, stable instance identity, and the semantic "
            "completion field remain unproved; frozen-save decoding and catalogue joins are not justified."
        ),
        "missing_evidence": [
            "connected registration provenance for a GameObject/persistent-object CodeSideLuaClass entry",
            "its exact +0xB8 encoder and +0xC0 decoder callbacks",
            "inverse-pair proof of stable instance identity fields and byte layout",
            "semantic completion field with opposite positively labelled values for same field",
        ],
        "safety": {
            "game_launched": False,
            "active_save_opened": False,
            "active_save_modified": False,
            "save_or_progression_written": False,
            "exe_written": False,
        },
    }
    con.close()
    return result


def render_text(result) -> str:
    reg = result["registry"]
    lines = [
        "Completionist Map - GoW CodeSideLuaClass persistence registry",
        f"exe_sha256={result['exe_sha256']}",
        f"registry_count_global=0x{reg['count_global_rva']:X}",
        f"registry_pointer_table=0x{reg['pointer_table_rva']:X}",
        f"registry_count={reg['static_count_after_crt_initializers']}",
        "mode=read-only exact-global trace",
        "broad_heuristic_scan=false",
        "",
        "DETERMINISTIC REGISTRY TABLE",
    ]
    for row in reg["entries"]:
        lines.append(
            f"[{row['registry_index']}] key=0x{row['class_key']:016X} metadata=0x{row['class_metadata_rva']:X} "
            f"name={row['name']} parent=null save_B8=null restore_C0=null init=0x{row['initializer_rva']:X}"
        )
        lines.append(
            f"    neighbour_F0=0x{row['neighbouring_noncallback_fields']['+0xF0']:X} "
            f"neighbour_F8=0x{row['neighbouring_noncallback_fields']['+0xF8']:X} "
            "class=non-executable-enum-data"
        )
    lines += [
        "",
        "EXACT CALLBACK MAPPING",
        "  (none: both static classes have null +0xB8/+0xC0 and null parent)",
        "",
        "GAMEOBJECT PERSISTENCE PAYLOAD",
        "  not decoded; no connected GameObject registry class/callback evidence",
        "",
        "FROZEN SAVE DECODER",
        "  not created; Phase 1/2 evidence threshold not met",
        "",
        "PRODUCTION ORACLE STATUS",
        f"  {result['production_oracle_status']}",
        f"  blocker={result['blocker']}",
        "",
        "MISSING EVIDENCE",
    ]
    lines.extend(f"  - {item}" for item in result["missing_evidence"])
    lines += ["", "SAFETY"]
    lines.extend(f"  {key}={str(value).lower()}" for key, value in result["safety"].items())
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--exe")
    parser.add_argument("--db")
    parser.add_argument("--output-json")
    parser.add_argument("--output-text")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.exe, args.db, args.output_json, args.output_text)):
        parser.error("--exe, --db, --output-json, and --output-text are required")
    result = analyze(Path(args.exe), Path(args.db))
    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    out_text.write_text(render_text(result), encoding="utf-8")
    print(result["production_oracle_status"])
    print(f"registry_count={result['registry']['static_count_after_crt_initializers']}")
    for row in result["registry"]["entries"]:
        print(f"registry[{row['registry_index']}]={row['name']} key=0x{row['class_key']:016X}")


if __name__ == "__main__":
    main()
