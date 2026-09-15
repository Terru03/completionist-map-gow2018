"""Trace the exact GameObject userdata -> persistence-class lookup path.

Read-only, version-locked static analysis for the supported God of War executable.
This tracer is deliberately narrow. It starts from the already-proven GameObject
userdata constructor and the exact userdata serializer at 0x7E9190, recovers the
18-byte lookup key at 0xDF6660, and inventories only direct references/functions
connected to that key, the GameObject registration string, and constructor.

It does not launch the game, open saves, or modify the executable.
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

KEY_RVA = 0xDF6660
KEY_LENGTH = 0x12
GAMEOBJECT_STRING_RVA = 0xE061D8

ANCHORS = {
    "gameobject_token_to_userdata": 0x60BA17,
    "userdata_constructor": 0x547A60,
    "userdata_token_store": 0x547B67,
    "gameobject_unbox": 0x5F9350,
    "gameobject_registration_owner": 0x822C40,
    "gameobject_registration_string_ref": 0x822F28,
    "userdata_serializer": 0x7E9190,
}

SITES = {
    "token_tailjump_userdata_constructor": (0x60BA17, "e944c0f3ff"),
    "userdata_token_store": (0x547B67, "48895808"),
    "serializer_key_lea": (0x7E91CA, "488d158fd46000"),
    "serializer_key_length": (0x7E91D1, "41b812000000"),
    "serializer_key_string_helper": (0x7E91DE, "e80dbb2000"),
    "serializer_userdata_lookup": (0x7E9206, "e855642000"),
    "serializer_result_tag2": (0x7E9215, "83f902"),
    "serializer_result_tag7": (0x7E921A, "83f907"),
    "serializer_tag7_payload": (0x7E9223, "488b58f0"),
    "serializer_tag7_payload_plus30": (0x7E9227, "4883c330"),
    "serializer_tag2_pointer": (0x7E922D, "488b58f0"),
    "serializer_callback_guard": (0x7E9255, "443890a4000000"),
    "serializer_callback_load_b8": (0x7E925F, "4c8b90b8000000"),
    "serializer_parent_load_48": (0x7E9266, "488b4048"),
    "serializer_callback_max_payload": (0x7E9282, "41b980000000"),
    "serializer_callback_output_buffer": (0x7E928D, "4c8d442440"),
    "serializer_callback_stack_index": (0x7E9292, "418bd6"),
    "serializer_callback_lua_state": (0x7E9295, "488bcd"),
    "serializer_callback_call": (0x7E9298, "41ffd2"),
    "serializer_callback_length": (0x7E92B2, "8b5c2430"),
    "serializer_callback_blob_copy": (0x7E92E6, "e8af40c0ff"),
    "serializer_callback_node_tag": (0x7E92FE, "41881408"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pe_module():
    path = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_userdata_persistence_pe", path)
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


def read_bytes(pe, rva: int, length: int) -> bytes:
    off = pe.rva_to_file(rva)
    if off is None or off + length > len(pe.data):
        raise RuntimeError(f"RVA not file backed: 0x{rva:X}")
    return pe.data[off:off + length]


def printable(raw: bytes) -> str:
    return "".join(chr(b) if 0x20 <= b <= 0x7E else f"\\x{b:02x}" for b in raw)


def disassemble(md, pe, begin: int, op_imm: int, op_mem: int, rip_reg: int) -> dict:
    fn = pe.function_for(begin)
    if fn is None:
        raise RuntimeError(f"function boundary absent for 0x{begin:X}")
    rows = []
    for ins in md.disasm(pe.bytes_for(fn), IMAGE_BASE + fn["begin"]):
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
        rows.append(row)
    return {
        "requested_rva": begin,
        "begin": fn["begin"],
        "end": fn["end"],
        "size": fn["end"] - fn["begin"],
        "instructions": rows,
    }


def exact_instruction(md, pe, rva: int, expected_hex: str) -> dict:
    raw = bytes.fromhex(expected_hex)
    actual = read_bytes(pe, rva, len(raw))
    if actual != raw:
        raise AssertionError(
            f"exact bytes changed at 0x{rva:X}: {actual.hex()} != {expected_hex}"
        )
    ins = next(md.disasm(read_bytes(pe, rva, 16), IMAGE_BASE + rva), None)
    if ins is None:
        raise AssertionError(f"cannot disassemble 0x{rva:X}")
    return {
        "rva": rva,
        "bytes": expected_hex,
        "instruction": f"{ins.mnemonic} {ins.op_str}".strip(),
    }


def function_refs(con: sqlite3.Connection, target: int) -> list[dict]:
    return [
        {"site": site, "source_function": src_fn, "mnemonic": mnemonic}
        for site, src_fn, mnemonic in con.execute(
            "SELECT site,src_fn,mnemonic FROM rip_refs WHERE target=? ORDER BY site",
            (target,),
        )
    ]


def callers(con: sqlite3.Connection, dest: int) -> list[dict]:
    return [
        {"site": site, "source_function": src_fn, "kind": kind, "dest": target}
        for site, src_fn, kind, target in con.execute(
            "SELECT site,src_fn,kind,dest FROM edges WHERE dest=? ORDER BY site", (dest,)
        )
    ]


def outgoing(con: sqlite3.Connection, src_fn: int) -> list[dict]:
    return [
        {"site": site, "source_function": owner, "kind": kind, "dest": dest}
        for site, owner, kind, dest in con.execute(
            "SELECT site,src_fn,kind,dest FROM edges WHERE src_fn=? ORDER BY site", (src_fn,)
        )
    ]


def data_ptrs(con: sqlite3.Connection, target: int) -> list[int]:
    return [
        row[0]
        for row in con.execute(
            "SELECT location_rva FROM data_ptrs WHERE value_rva=? ORDER BY location_rva",
            (target,),
        )
    ]


def compact_owner_disassembly(md, pe, owners: list[int], op_imm, op_mem, rip_reg) -> list[dict]:
    out = []
    seen = set()
    for owner in owners:
        if owner in seen:
            continue
        seen.add(owner)
        fn = pe.function_for(owner)
        if fn is None:
            continue
        report = disassemble(md, pe, fn["begin"], op_imm, op_mem, rip_reg)
        if report["size"] <= 0x1000:
            out.append(report)
            continue
        selected = []
        for row in report["instructions"]:
            if (
                KEY_RVA in row.get("rip_targets", [])
                or GAMEOBJECT_STRING_RVA in row.get("rip_targets", [])
                or any(f"+ 0x{x:x}" in row["op_str"] for x in (0x48, 0xA4, 0xB8, 0xC0))
            ):
                selected.append(row)
        out.append({
            "requested_rva": owner,
            "begin": report["begin"],
            "end": report["end"],
            "size": report["size"],
            "instructions": selected,
            "truncated_to_anchor_instructions": True,
        })
    return out


def lookup_bridge_claim(key_text: str, key_refs: list[dict], assertions: list[str]) -> bool:
    return (
        key_text == "__CodeSideLuaClass"
        and any(row["site"] == 0x7E91CA for row in key_refs)
        and "serializer_callback_load_b8@0x7E925F" in assertions
        and "serializer_parent_load_48@0x7E9266" in assertions
        and "serializer_callback_call@0x7E9298" in assertions
    )


def callback_claim_allowed(evidence: set[str]) -> bool:
    required = {
        "gameobject_userdata_connected",
        "exact_class_descriptor",
        "exact_parent_chain",
        "exact_b8_target",
    }
    forbidden = {
        "arbitrary_b8",
        "stack_b8",
        "static_enum_registry_only",
        "generic_gameobject_only",
        "runtime_token_as_persistent",
        "string_only_guid",
    }
    return required <= evidence and not evidence.intersection(forbidden)


def self_test() -> None:
    assert len("__CodeSideLuaClass") == KEY_LENGTH
    assert not callback_claim_allowed({"gameobject_userdata_connected", "arbitrary_b8"})
    assert not callback_claim_allowed(
        {"gameobject_userdata_connected", "exact_class_descriptor", "static_enum_registry_only"}
    )
    assert callback_claim_allowed(
        {
            "gameobject_userdata_connected",
            "exact_class_descriptor",
            "exact_parent_chain",
            "exact_b8_target",
        }
    )
    print("SELF_TEST_PASSED")


def analyze(exe: Path, db: Path) -> dict:
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

    assertions = []
    exact_sites = {}
    for name, (rva, expected) in SITES.items():
        exact_sites[name] = exact_instruction(md, pe, rva, expected)
        assertions.append(f"{name}@0x{rva:X}")

    key_raw = read_bytes(pe, KEY_RVA, KEY_LENGTH)
    key_ascii = printable(key_raw)
    key_nul = read_bytes(pe, KEY_RVA + KEY_LENGTH, 1) == b"\x00"

    with sqlite3.connect(db) as con:
        key_refs = function_refs(con, KEY_RVA)
        gameobject_refs = function_refs(con, GAMEOBJECT_STRING_RVA)
        key_data_ptrs = data_ptrs(con, KEY_RVA)
        gameobject_data_ptrs = data_ptrs(con, GAMEOBJECT_STRING_RVA)
        constructor_callers = callers(con, ANCHORS["userdata_constructor"])
        constructor_outgoing = outgoing(con, pe.function_for(ANCHORS["userdata_constructor"])["begin"])
        serializer_outgoing = outgoing(con, ANCHORS["userdata_serializer"])
        registration_outgoing = outgoing(con, ANCHORS["gameobject_registration_owner"])

    if not any(row["site"] == 0x7E91CA for row in key_refs):
        raise AssertionError("research index lost exact serializer key reference 0x7E91CA")
    if not any(row["site"] == 0x822F28 for row in gameobject_refs):
        raise AssertionError("research index lost GameObject string reference 0x822F28")

    targeted_functions = {
        "userdata_constructor": disassemble(
            md, pe, ANCHORS["userdata_constructor"], op_imm, op_mem, rip_reg
        ),
        "userdata_serializer": disassemble(
            md, pe, ANCHORS["userdata_serializer"], op_imm, op_mem, rip_reg
        ),
        "gameobject_registration": disassemble(
            md, pe, ANCHORS["gameobject_registration_owner"], op_imm, op_mem, rip_reg
        ),
        "gameobject_unbox": disassemble(
            md, pe, ANCHORS["gameobject_unbox"], op_imm, op_mem, rip_reg
        ),
        "key_string_helper": disassemble(md, pe, 0x9F4CF0, op_imm, op_mem, rip_reg),
        "userdata_lookup_helper": disassemble(md, pe, 0x9EF660, op_imm, op_mem, rip_reg),
        "serializer_entry_helper": disassemble(md, pe, 0x9E3F80, op_imm, op_mem, rip_reg),
    }

    owner_rvas = [row["source_function"] for row in key_refs + gameobject_refs]
    reference_owner_functions = compact_owner_disassembly(
        md, pe, owner_rvas, op_imm, op_mem, rip_reg
    )

    lookup_pass = lookup_bridge_claim(key_ascii, key_refs, assertions)
    callback_evidence = {"gameobject_userdata_connected"} if lookup_pass else set()
    callback_status = (
        "PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK"
        if callback_claim_allowed(callback_evidence)
        else "BLOCKED_EXACT_GAMEOBJECT_USERDATA_CALLBACK"
    )

    blocker = (
        "The serializer's exact userdata->class lookup is proved, but the concrete "
        "GameObject __CodeSideLuaClass descriptor value returned at runtime is not yet "
        "statically connected to its registration/initializer. Therefore its parent "
        "chain and executable +0xB8 callback target cannot yet be named. Use the "
        "reported exact key xref owners, GameObject registration owner, constructor "
        "callers, and narrow disassemblies as the next connected edge."
        if lookup_pass
        else
        "The expected userdata class lookup bridge did not satisfy all exact guards."
    )

    return {
        "schema": 1,
        "analysis": "gow_gameobject_userdata_persistence",
        "gameobject_userdata_callback_status": callback_status,
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {
            "path": str(exe),
            "sha256": digest.lower(),
            "sha256_verified": True,
        },
        "safety": {
            "analysis_mode": "read-only",
            "game_launched": False,
            "active_save_opened": False,
            "active_save_modified": False,
            "frozen_save_opened": False,
            "save_or_progression_written": False,
            "exe_written": False,
        },
        "exact_userdata_class_lookup": {
            "status": "PASS_EXACT_USERDATA_CLASS_LOOKUP" if lookup_pass else "BLOCKED",
            "key_rva": f"0x{KEY_RVA:X}",
            "key_length": KEY_LENGTH,
            "key_hex": key_raw.hex(),
            "key_ascii": key_ascii,
            "nul_terminated_after_key": key_nul,
            "connected_path": [
                "serializer receives Lua state RCX and original userdata stack index R8D",
                "0x7E91CA loads exact 18-byte key",
                "0x7E91DE interns/builds key TValue through 0x9F4CF0",
                "0x7E9206 performs userdata lookup through 0x9EF660",
                "lookup result tag 2 uses pointer directly",
                "lookup result tag 7 uses userdata payload +0x30",
                "resulting pointer becomes class metadata RAX",
                "0x7E9255 validates +0xA4",
                "0x7E925F reads +0xB8 callback",
                "0x7E9266 walks +0x48 parent",
                "0x7E9298 invokes first non-null inherited callback",
            ],
            "callback_calling_convention": {
                "rcx": "Lua state / serializer Lua context preserved from function entry",
                "edx": "original userdata stack index from serializer input R8D",
                "r8": "pointer to 0x80-byte stack output buffer at rsp+0x40",
                "r9d": "0x80 maximum payload bytes",
                "stack_out_length": "dword at rsp+0x30, consumed after callback",
                "return_al": "success boolean, asserted nonzero",
            },
            "key_rip_refs": key_refs,
            "key_data_pointer_locations": key_data_ptrs,
        },
        "gameobject_registration_bridge": {
            "gameobject_string_rva": f"0x{GAMEOBJECT_STRING_RVA:X}",
            "gameobject_rip_refs": gameobject_refs,
            "gameobject_data_pointer_locations": gameobject_data_ptrs,
            "constructor_callers": constructor_callers,
            "constructor_outgoing": constructor_outgoing,
            "registration_outgoing": registration_outgoing,
            "serializer_outgoing": serializer_outgoing,
            "precise_missing_edge": (
                "runtime value returned by userdata['__CodeSideLuaClass'] "
                "-> concrete GameObject class descriptor/initializer"
            ),
        },
        "targeted_functions": targeted_functions,
        "reference_owner_functions": reference_owner_functions,
        "exact_sites": exact_sites,
        "assertions": assertions,
        "blocker": blocker,
        "rejected_claims": [
            "arbitrary +0xB8 structure without GameObject userdata provenance",
            "stack-relative +0xB8 false positives",
            "GroundType/CollisionType static registry as GameObject class",
            "generic GameObject function proximity",
            "runtime token as stable persistent identity",
            "GUID/string occurrence without connected callback dataflow",
        ],
    }


def render_text(report: dict) -> str:
    lookup = report["exact_userdata_class_lookup"]
    bridge = report["gameobject_registration_bridge"]
    lines = [
        "GoW GameObject userdata persistence trace",
        "========================================",
        f"exe_sha256={report['executable']['sha256']}",
        f"gameobject_userdata_callback_status={report['gameobject_userdata_callback_status']}",
        f"gameobject_persistent_key_status={report['gameobject_persistent_key_status']}",
        f"production_oracle_status={report['production_oracle_status']}",
        "",
        "Exact userdata class lookup",
        f"status={lookup['status']}",
        f"key_rva={lookup['key_rva']}",
        f"key_length={lookup['key_length']}",
        f"key_hex={lookup['key_hex']}",
        f"key_ascii={lookup['key_ascii']}",
        f"nul_terminated_after_key={str(lookup['nul_terminated_after_key']).lower()}",
        f"key_rip_refs={len(lookup['key_rip_refs'])}",
        "",
        "Callback ABI at 0x7E9298",
        "rcx=Lua state/context",
        "edx=original userdata stack index",
        "r8=0x80-byte output buffer",
        "r9d=0x80 max payload",
        "out_length=dword[rsp+0x30]",
        "",
        "Registration bridge",
        f"gameobject_rip_refs={len(bridge['gameobject_rip_refs'])}",
        f"constructor_callers={len(bridge['constructor_callers'])}",
        f"missing_edge={bridge['precise_missing_edge']}",
        "",
        f"blocker={report['blocker']}",
        "",
        "Safety",
    ]
    lines.extend(f"{k}={str(v).lower()}" for k, v in report["safety"].items())
    lines.extend(("", f"exact_rva_assertions={len(report['assertions'])}"))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-text", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    if any(x is None for x in (args.exe, args.db, args.output_json, args.output_text)):
        parser.error("--exe, --db, --output-json, and --output-text are required")

    report = analyze(args.exe, args.db)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_text.write_text(render_text(report), encoding="utf-8")

    print(report["exact_userdata_class_lookup"]["status"])
    print(report["gameobject_userdata_callback_status"])
    print(report["gameobject_persistent_key_status"])
    print(report["production_oracle_status"])
    print(f"EXACT_RVA_ASSERTIONS={len(report['assertions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
