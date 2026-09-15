"""Trace exact GameObject keys used by checkpoint ``__subobjs``.

Read-only. Version locked. Prove linked native flow at known RVAs.
No game launch. No save read. No registry scan.
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

REUSED_ARCHIVES = (
    "object-checkpoint-dispatch-20260914-205500",
    "gameobject-token-resolver-20260914-220203",
    "gameobject-token-resolver-v2-20260914-220529",
    "gameobject-token-allocator-trace-20260914-221542",
    "gameobject-token-allocator-trace-v2-20260914-221951",
    "object-token-inverse-20260914-214158",
    "gameobject-argument-decoder-20260914-214448",
    "gameobject-argument-decoder-20260914-214814",
    "gameobject-identity-field-stores-20260914-220954",
    "gameobject-pickle-codec-20260914-222442",
    "gameobject-pickle-bridge-trace-20260914-222927",
    "checkpoint-pickle-return-serializer-20260914-232017",
    "core-pickle-registration-trace-20260914-223441",
    "core-pickle-game-resource-scan-20260914-224243",
    "core-pickle-source-snippets-20260914-224927",
    "object-unpickle-resolver-20260914-213155",
    "object-unpickle-functions-20260914-213459",
    "savelib-object-key-usage-20260914-190854",
    "known-raven-runtime-key-save-probe-20260914-150602",
    "known-raven-runtime-key-context-20260914-151244",
)

# Exact bytes prove each linked path. Reject near code and lone strings.
SITES = {
    # Save: subobject -> GameObject -> token -> userdata -> table set.
    "save_gameobject_load_a": (0x5AC899, "498b4e28"),
    "save_valid_test_a": (0x5AC8B1, "f6817802000001"),
    "save_flags_load_a": (0x5AC8BD, "8b8178020000"),
    "save_slot_load_a": (0x5AC8C3, "8b9184020000"),
    "save_registry_load_a": (0x5AC8DB, "0fb78180020000"),
    "save_userdata_push_a": (0x5AC8F3, "e868b1f9ff"),
    "save_callback_a": (0x5AC924, "e8b773ffff"),
    "save_savedinfo_nonempty_probe_a": (0x5ACA85, "e896064400"),
    "save_table_set_a": (0x5ACACF, "e8dc794300"),
    "save_gameobject_load_b": (0x5ACBC7, "498b4e28"),
    "save_userdata_push_b": (0x5ACC21, "e83aaef9ff"),
    "save_callback_b": (0x5ACC51, "e88a70ffff"),
    "save_savedinfo_nonempty_probe_b": (0x5ACDB6, "e865034400"),
    "save_table_set_b": (0x5ACE00, "e8ab764300"),
    # Other save path uses shared packer.
    "save_shared_packer_load": (0x174B8C, "488b5228"),
    "save_shared_packer_call": (0x174B93, "e8286e4900"),
    # Restore: same object makes lookup key. Then code eats entry.
    "restore_gameobject_load": (0x5AD597, "488b5628"),
    "restore_packer_call": (0x5AD5A5, "e816e40500"),
    "restore_table_get": (0x5AD5BA, "e861ff4300"),
    "restore_callback": (0x5AD608, "e8d366ffff"),
    "restore_consume_load": (0x5AD6B8, "488b5628"),
    # Shared packer and userdata payload.
    "packer_valid": (0x60B9D7, "41f6807802000001"),
    "packer_flags": (0x60B9E1, "418b8078020000"),
    "packer_slot": (0x60B9E8, "418b9084020000"),
    "packer_registry": (0x60BA01, "410fb78080020000"),
    "packer_final_shift": (0x60BA10, "4803d2"),
    "packer_to_userdata": (0x60BA17, "e944c0f3ff"),
    "userdata_payload_store": (0x547B67, "48895808"),
    # Unbox and inverse resolver.
    "unbox_payload_load": (0x5F93D6, "488b4a08"),
    "unbox_flavor": (0x5F93F7, "4180e001"),
    "unbox_resolver_call": (0x5F9407, "e8a45cefff"),
    "resolver_registry_compare": (0x4EF0C8, "413909"),
    "resolver_slot_bound": (0x4EF0E9, "423b540810"),
    "resolver_bank_load": (0x4EF0F0, "4a8b0408"),
    "resolver_object_load": (0x4EF0F6, "488b04c8"),
    # Remove clears slot and ID fields.
    "remove_slot_clear": (0x4EF27D, "4c892cc8"),
    "remove_flags_clear": (0x4EF284, "4183a778020000f6"),
    "remove_identity_invalidate": (0x4EF296, "49c78780020000ffffffff"),
    # Flavor-one allocator takes slot hint and writes fields.
    "allocator_hint_load": (0x4EF2F6, "418b4804"),
    "allocator_slot_store": (0x4EF339, "4b893cc2"),
    "allocator_flags_store": (0x4EF377, "838f7802000009"),
    "allocator_registry_store": (0x4EF3A5, "898f80020000"),
    "allocator_slot_field_store": (0x4EF3B8, "898784020000"),
    # Loader gives level ID and slot hint to allocator.
    "loader_level_registry": (0x856FAD, "8b9f3c0c0000"),
    "loader_record_hint": (0x856FB7, "8b4630"),
    "loader_hint_registry_copy": (0x857243, "8b442444"),
    "loader_hint_slot_copy": (0x85724B, "8b4630"),
    "loader_hint_allocator_call": (0x8572AA, "e80180c9ff"),
    "loader_dynamic_call": (0x857329, "e89281c9ff"),
    "descriptor_slot_arg_store": (0x85670A, "8b442460"),
    "descriptor_slot_field_store": (0x85670E, "41894630"),
    # Binary: userdata -> callback blob -> typed node writer.
    "value_userdata_branch": (0x7E8F5F, "448bc5"),
    "value_userdata_callback": (0x7E8F70, "e81b020000"),
    "callback_parent_walk": (0x7E925F, "4c8b90b8000000"),
    "callback_indirect_call": (0x7E9298, "41ffd2"),
    "callback_blob_copy": (0x7E92E6, "e8af40c0ff"),
    "callback_node_tag": (0x7E92FE, "41881408"),
    "binary_node_writer": (0x7E9450, "440fb64904"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pack_token(registry_id: int, flavor: int, slot: int) -> int:
    return 1 | ((registry_id & 0xFFFF) << 1) | ((flavor & 1) << 17) | ((slot & 0xFFFFF) << 18)


def unpack_token(token: int) -> dict[str, int]:
    if token & 1 == 0 or token & 0xFFFFFFC000000000:
        raise ValueError("not supported GameObject token")
    return {
        "registry_id": (token >> 1) & 0xFFFF,
        "flavor": (token >> 17) & 1,
        "slot": (token >> 18) & 0xFFFFF,
    }


def persistent_claim_allowed(evidence: set[str]) -> bool:
    required = {"connected_producer", "connected_consumer", "reload_stable", "catalogue_join"}
    forbidden = {"disconnected_guid_string", "generic_resolver_only", "nearby_bits_only", "allocator_only"}
    return required <= evidence and not (evidence & forbidden)


def self_test() -> None:
    cases = ((0, 0, 0), (0xFFFF, 1, 0xFFFFF), (0x1234, 0, 0x56789))
    for registry_id, flavor, slot in cases:
        token = pack_token(registry_id, flavor, slot)
        assert unpack_token(token) == {
            "registry_id": registry_id,
            "flavor": flavor,
            "slot": slot,
        }
    for rejected in (
        {"disconnected_guid_string"},
        {"generic_resolver_only"},
        {"nearby_bits_only"},
        {"connected_producer", "connected_consumer", "allocator_only"},
    ):
        assert not persistent_claim_allowed(rejected)
    assert persistent_claim_allowed(
        {"connected_producer", "connected_consumer", "reload_stable", "catalogue_join"}
    )
    for bad in (0, 2, 0xFC000000001):
        try:
            unpack_token(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid token 0x{bad:X}")
    print("SELF_TEST_PASSED")


def load_pe_module():
    helper = Path(__file__).with_name("trace-gameobject-pickle-bridges.py")
    spec = importlib.util.spec_from_file_location("gow_subobjs_pe", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load PE helper: {helper}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capstone():
    repo = Path(__file__).resolve().parents[2]
    local = repo / ".research-index" / "python-packages"
    if local.is_dir():
        sys.path.insert(0, str(local))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    return Cs, CS_ARCH_X86, CS_MODE_64


def find_archives(repo: Path) -> list[dict[str, str]]:
    base = repo / "archive" / "field-logs" / "source-scans"
    names = {item.name: item for item in base.iterdir() if item.is_dir()}
    found = []
    for wanted in REUSED_ARCHIVES:
        matches = [name for name in names if name == wanted or name.endswith(wanted)]
        if len(matches) != 1:
            raise AssertionError(f"archive recovery mismatch for {wanted}: {matches}")
        found.append({"name": wanted, "path": str(names[matches[0]].relative_to(repo)).replace("\\", "/")})
    return found


def analyze(exe: Path, db: Path) -> dict:
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")
    if not db.is_file():
        raise RuntimeError(f"missing research index: {db}")

    repo = Path(__file__).resolve().parents[2]
    archives = find_archives(repo)
    pe_module = load_pe_module()
    pe = pe_module.PE(exe.read_bytes())
    Cs, arch, mode = load_capstone()
    md = Cs(arch, mode)

    assertions = []
    site_rows = {}
    for name, (rva, expected) in SITES.items():
        offset = pe.rva_to_file(rva)
        if offset is None:
            raise AssertionError(f"RVA not file backed: 0x{rva:X}")
        actual = pe.data[offset:offset + len(bytes.fromhex(expected))].hex()
        if actual != expected:
            raise AssertionError(f"exact bytes changed at 0x{rva:X}: {actual} != {expected}")
        ins = next(md.disasm(pe.data[offset:offset + 16], IMAGE_BASE + rva), None)
        if ins is None:
            raise AssertionError(f"cannot disassemble 0x{rva:X}")
        site_rows[name] = {
            "rva": f"0x{rva:X}", "bytes": expected,
            "instruction": f"{ins.mnemonic} {ins.op_str}".strip(),
        }
        assertions.append(f"{name}@0x{rva:X}")

    con = sqlite3.connect(db)
    try:
        indexed_calls = []
        for site, target in ((0x5AC8F3, 0x547A60), (0x5ACA85, 0x9ED120),
                             (0x5AD5A5, 0x60B9C0), (0x5F9407, 0x4EF0B0),
                             (0x7E8F70, 0x7E9190)):
            row = con.execute(
                "SELECT src_fn,kind,dest FROM edges WHERE site=? AND dest=?", (site, target)
            ).fetchone()
            if row is None:
                raise AssertionError(f"indexed call edge absent: 0x{site:X}->0x{target:X}")
            indexed_calls.append({"site": f"0x{site:X}", "source_function": f"0x{row[0]:X}",
                                  "kind": row[1], "target": f"0x{row[2]:X}"})
    finally:
        con.close()

    return {
        "analysis": "gow_subobjs_object_key",
        "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
        "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        "executable": {"path": str(exe), "sha256": digest.lower(), "sha256_verified": True},
        "safety": {
            "analysis_mode": "read-only", "game_launched": False,
            "active_save_opened": False, "active_save_modified": False,
            "save_or_progression_written": False, "exe_written": False,
            "frozen_save_opened": False,
        },
        "reused_archives": archives,
        "phase_1_save_connected_dataflow": {
            "path": [
                "subobject", "subobject+0x28 GameObject pointer",
                "GameObject fields +0x278/+0x280/+0x284", "packed qword token",
                "GameObject full userdata with token at userdata+0x8",
                "OnSaveCheckpoint savedInfo", "__subobjs[key]=savedInfo",
            ],
            "key_lua_type": "full userdata",
            "native_payload": "qword token at userdata+0x8",
            "token_equation": "1 | ((u16[GameObject+0x280])<<1) | (((u32[GameObject+0x278]>>3)&1)<<17) | ((u32[GameObject+0x284]&0xFFFFF)<<18)",
            "token_layout": {"bit_0": "valid marker 1", "bits_1_16": "registry_id",
                             "bit_17": "flavor/bank", "bits_18_37": "slot", "bits_38_63": "zero"},
            "shared_packer_0x60B9C0": "used on save at 0x174B93; normal builder 0x5AC760 uses exact inlined formula",
            "connected_native_ancestors": ["GameObject+0x278 bit 3", "GameObject+0x280 low 16", "GameObject+0x284 low 20"],
            "not_connected_ancestors": ["GameObjectGUID", "GameObjectIDA", "GameObjectIDB", "coordinates", "nearby hashes"],
        },
        "phase_2_restore_inverse": {
            "path": ["__subobjs userdata key", "userdata+0x8 qword", "0x5F9350 unbox",
                     "0x4EF0B0 resolver", "runtime registry bank[slot]", "GameObject"],
            "inverse": {"registry_id": "(token>>1)&0xFFFF", "flavor": "(token>>17)&1",
                        "slot": "(token>>18)&0xFFFFF"},
            "resolver_layout": "descriptor selected by registry_id; flavor chooses descriptor+0x08 or +0x20 bank; slot indexes pointer array",
            "lifetime_evidence": "0x4EF27D clears bank[slot]; 0x4EF284 clears valid/flavor bits; 0x4EF296 writes -1 across +0x280/+0x284",
        },
        "phase_3_stable_identity": {
            "result": "not proved",
            "allocator_input": "loader descriptor +0x30 supplies preferred slot; level/WAD object +0xC3C supplies registry_id",
            "dynamic_case": "descriptor +0x30 == -1 reaches 0x857329 and allocates a free flavor-one slot",
            "precise_missing_edge": "no connected producer/consumer maps (level/WAD +0xC3C registry_id, descriptor +0x30 slot) to canonical catalogue instance identity and proves same pair after unload/reload",
            "guid_zero_hit_answer": "raw GUID fields are proved absent from token ancestry; exact reason raw catalogue GUID bytes are absent from frozen saves remains unproved because the GameObject userdata callback payload is unresolved",
            "evidence_strength": "strong for runtime handle; insufficient for stable persistent identity",
            "candidates": [
                {
                    "name": "runtime GameObject token",
                    "producer_rva": "0x60B9C0 (shared) / 0x5AC8B1 and 0x5ACBDF (inlined)",
                    "consumer_rva": "0x5F9350 then 0x4EF0B0",
                    "fields": "GameObject+0x278 bit 3, +0x280 low 16, +0x284 low 20",
                    "width": "38 meaningful bits in qword",
                    "endian_layout": "native little-endian qword at userdata+0x8; checkpoint wire layout unresolved",
                    "transformations": "bit packing and inverse masks/shifts stated above",
                    "level_wad_component": "+0x280 derives from level/WAD +0xC3C registry_id on allocator path",
                    "catalogue_relationship": "none proved",
                    "survives_unload_reload": False,
                    "evidence_strength": "strong allocator lifecycle proof",
                },
                {
                    "name": "loader registry_id and preferred slot tuple",
                    "producer_rva": "0x856FAD and 0x856FB7; descriptor +0x30 itself set at 0x85670E from stack argument",
                    "consumer_rva": "0x857243/0x85724B -> 0x8572AA -> 0x4EF2B0",
                    "fields": "level/WAD object+0xC3C u32 and loader descriptor+0x30 u32",
                    "width": "u32 + u32, later truncated to 16 + 20 bits",
                    "endian_layout": "native little-endian fields; checkpoint wire layout unresolved",
                    "transformations": "preferred slot feeds allocator; -1 selects dynamic allocation",
                    "level_wad_component": "registry_id is loaded from level/WAD object+0xC3C",
                    "catalogue_relationship": "not proved",
                    "survives_unload_reload": "unproved",
                    "evidence_strength": "strong connected allocator input; weak persistence claim",
                },
            ],
        },
        "phase_4_binary_mapping": {
            "connected_path": ["__subobjs table", "0x7E7F10 table codec", "0x7E8EF0 value classifier",
                               "userdata branch 0x7E8F5F", "0x7E9190 callback dispatcher",
                               "callback blob node type 5", "0x7E9450 binary node writer"],
            "conflict": "connected GameObject-key flow requires userdata callback, but exact recovered CodeSideLuaClass registry has only GroundType and CollisionType with null save/restore callbacks",
            "result": "GameObject callback target, blob layout, and inverse are unresolved; structural frozen-save parser is not justified",
        },
        "phase_5_frozen_save_probe": {"performed": False, "decoder_created": False,
                                      "reason": "phase 4 structural proof gate failed"},
        "exact_sites": site_rows,
        "sqlite_call_edges": indexed_calls,
        "assertions": assertions,
        "rejected_evidence_classes": ["disconnected GUID-string references", "generic GameObject resolver calls",
                                      "nearby bit manipulation without token provenance",
                                      "allocator-only tokens labelled persistent IDs"],
    }


def render_text(report: dict) -> str:
    p1 = report["phase_1_save_connected_dataflow"]
    p3 = report["phase_3_stable_identity"]
    p4 = report["phase_4_binary_mapping"]
    lines = [
        "GoW __subobjs GameObject key trace",
        "===================================",
        f"exe_sha256={report['executable']['sha256']}",
        f"gameobject_persistent_key_status={report['gameobject_persistent_key_status']}",
        f"production_oracle_status={report['production_oracle_status']}",
        "",
        "Exact Lua key",
        f"type={p1['key_lua_type']}",
        f"payload={p1['native_payload']}",
        f"token={p1['token_equation']}",
        f"shared_packer={p1['shared_packer_0x60B9C0']}",
        "",
        "Inverse",
        "registry_id=(token>>1)&0xFFFF",
        "flavor=(token>>17)&1",
        "slot=(token>>18)&0xFFFFF",
        "resolver=runtime descriptor bank selected by registry_id/flavor, then bank[slot]",
        "",
        "Stable identity",
        f"result={p3['result']}",
        f"missing_edge={p3['precise_missing_edge']}",
        f"guid_zero_hits={p3['guid_zero_hit_answer']}",
        "",
        "Binary mapping",
        f"result={p4['result']}",
        f"conflict={p4['conflict']}",
        "",
        "Safety",
    ]
    lines.extend(f"{key}={str(value).lower()}" for key, value in report["safety"].items())
    lines.extend(("", f"exact_rva_assertions={len(report['assertions'])}",
                  f"reused_archives={len(report['reused_archives'])}"))
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
    required = (args.exe, args.db, args.output_json, args.output_text)
    if any(value is None for value in required):
        parser.error("--exe, --db, --output-json, and --output-text are required")
    report = analyze(args.exe, args.db)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text(render_text(report), encoding="utf-8")
    print(report["gameobject_persistent_key_status"])
    print(report["production_oracle_status"])
    print(f"EXACT_RVA_ASSERTIONS={len(report['assertions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
