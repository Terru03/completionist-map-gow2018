"""Build the stock-shaped Raven compass HUD GameObject chain offline.

The current r_ui.wad remains untouched. This builder follows the proven stock
compass physical grammar and therefore preserves DockPoint's local SCP payload
inside the cloned prototype group. It creates exactly three new resource
identities but four payload records: model, prototype, local SCP, and root.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import struct

import compass_hud_physical_groups as hud

BASE = hud.BASE
check = hud.check
REPO = hud.REPO
PHYSICAL = hud.load_module("inspect-compass-hud-physical-groups.py")
BINDING = hud.load_module("inspect-raven-compass-hud-scp-binding.py")
REDUCED = REPO / "archive/field-logs/completionist-v104-compass-hud-local-subtrees.json"

RESULT = "OFFLINE_RAVEN_COMPASS_HUD_FOUR_PAYLOAD_BUILT"
CONCLUSION = "FOUR_PAYLOAD_RAVEN_HUD_CLONE_BUILT_OFFLINE"
OUTPUT_WAD = REPO / "build/v0.10.4/raven-compass-hud-four-payload/r_ui.wad"
OUTPUT_REPORT = REPO / "archive/field-logs/completionist-v104-raven-compass-hud-four-payload.json"

SOURCE_ROOT = BASE.SOURCE_ROOT
SOURCE_PROTO = BASE.SOURCE_PROTO
SOURCE_MODEL = BASE.SOURCE_MODEL
SOURCE_MATERIAL = BASE.SOURCE_MATERIAL
SOURCE_MESH = BASE.SOURCE_MESH
SHARED_COMPASS = BASE.SHARED_COMPASS
RAVEN_MATERIAL = BASE.RAVEN_MATERIAL

NEW_ROOT = BASE.NEW_ROOT
NEW_PROTO = BASE.NEW_PROTO
NEW_MODEL = BASE.NEW_MODEL

SOURCE_ROOT_ID = BASE.SOURCE_ROOT_ID
SOURCE_PROTO_ID = BASE.SOURCE_PROTO_ID
SOURCE_MODEL_ID = BASE.SOURCE_MODEL_ID
SOURCE_MATERIAL_ID = BASE.SOURCE_MATERIAL_ID
SOURCE_MESH_ID = BASE.SOURCE_MESH_ID
SHARED_COMPASS_ID = BASE.SHARED_COMPASS_ID
RAVEN_MATERIAL_ID = BASE.RAVEN_MATERIAL_ID
NEW_ROOT_ID = BASE.NEW_ROOT_ID
NEW_PROTO_ID = BASE.NEW_PROTO_ID
NEW_MODEL_ID = BASE.NEW_MODEL_ID

TYPE_INCREMENTS = {0x10001: 1, 0x10005: 1, 0x20001: 1}
EXPECTED_SOURCE_TYPE_COUNTS = {0x10001: 1725, 0x10005: 2600, 0x20001: 2073}
EXPECTED_SOURCE_TOTAL = 16802
EXPECTED_SOURCE_PHYSICAL = 53811
EXPECTED_SOURCE_PAYLOADS = 20415
EXPECTED_CANDIDATE_PHYSICAL = 53824
EXPECTED_CANDIDATE_PAYLOADS = 20419
EXPECTED_CANDIDATE_TOTAL = 16805


def one_payload_index(records: list[dict], name: str) -> int:
    hits = [i for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def accounting_snapshot(records: list[dict]) -> dict:
    helper = BASE.load_helper()
    payloads = helper.payload_records(records)
    check(len(payloads) >= 2, "WAD_R_UI accounting payloads missing")
    heap, root = payloads[0], payloads[1]
    rows = helper.read_type_table(root["data"])
    counts = {row["key"]: row["count"] for row in rows}
    heap_total = struct.unpack_from("<I", heap["data"], 4)[0]
    root_total = struct.unpack_from("<I", root["data"], 0x1C)[0]
    check(heap_total == root_total == sum(row["count"] for row in rows),
          "WAD_R_UI totals disagree")
    return {
        "heap": heap,
        "root": root,
        "rows": rows,
        "counts": counts,
        "total": root_total,
    }


def apply_accounting(records: list[dict]) -> dict:
    snap = accounting_snapshot(records)
    check(snap["total"] == EXPECTED_SOURCE_TOTAL, "source WAD_R_UI total changed")
    for key, expected in EXPECTED_SOURCE_TYPE_COUNTS.items():
        check(snap["counts"].get(key) == expected, f"source WAD_R_UI row {key:#x} changed")

    new_base = 0
    for row in snap["rows"]:
        new_count = row["count"] + TYPE_INCREMENTS.get(row["key"], 0)
        struct.pack_into("<III", snap["root"]["data"], row["offset"], row["key"], new_base, new_count)
        new_base += new_count
    check(new_base == EXPECTED_CANDIDATE_TOTAL, "candidate WAD_R_UI total arithmetic changed")
    struct.pack_into("<I", snap["root"]["data"], 0x1C, new_base)
    struct.pack_into("<I", snap["heap"]["data"], 4, new_base)

    return {
        "before_total": EXPECTED_SOURCE_TOTAL,
        "after_total": new_base,
        "type_increments": {f"0x{key:X}": value for key, value in TYPE_INCREMENTS.items()},
        "source_counts": {f"0x{key:X}": snap["counts"][key] for key in TYPE_INCREMENTS},
        "candidate_counts": {
            f"0x{key:X}": snap["counts"][key] + TYPE_INCREMENTS[key] for key in TYPE_INCREMENTS
        },
    }


def clone_groups(records: list[dict], physical_report: dict) -> tuple[list[dict], list[dict], list[dict], dict]:
    dock = physical_report["classes"]["DockPoint"]
    model_target = int(dock["model"]["target_record_index"])
    proto_target = int(dock["prototype"]["target_record_index"])
    root_target = int(dock["root"]["target_record_index"])

    hud.validate_hud_group(records, model_target, "model")
    hud.validate_hud_group(records, proto_target, "prototype")
    hud.validate_hud_group(records, root_target, "root")

    model_clone = hud.clone_resource(
        records, model_target, NEW_MODEL, NEW_MODEL_ID,
        links={2: (SOURCE_MATERIAL_ID, RAVEN_MATERIAL, RAVEN_MATERIAL_ID)},
    )
    proto_clone = hud.clone_resource(
        records, proto_target, NEW_PROTO, NEW_PROTO_ID,
        links={2: (SOURCE_MODEL_ID, NEW_MODEL, NEW_MODEL_ID)},
        inline={0x3A8: (SOURCE_PROTO_ID, NEW_PROTO_ID)},
    )
    root_clone = hud.clone_resource(
        records, root_target, NEW_ROOT, NEW_ROOT_ID,
        inline={0x0C: (SOURCE_PROTO_ID, NEW_PROTO_ID)},
    )

    helper = BASE.load_helper()
    source_proto_grammar = hud.validate_hud_group(records, proto_target, "prototype")
    source_scp = records[source_proto_grammar["start"] + 3]
    check(helper.record_bytes(proto_clone[3]) == helper.record_bytes(source_scp),
          "local SCP changed while cloning prototype")

    clone_rows = model_clone + proto_clone + root_clone
    source_counts = accounting_snapshot(records)["counts"]
    clone_math = hud.clone_accounting(clone_rows, source_counts)
    check(clone_math["physical_records"] == 13, "full clone physical count changed")
    check(clone_math["payload_records"] == 4, "full clone payload count changed")
    check(clone_math["accounting_delta"] == 3, "full clone accounting delta changed")
    check(clone_math["type_deltas"].get("0x10001") == 1, "prototype accounting delta changed")
    check(clone_math["type_deltas"].get("0x10005") == 1, "SCP accounting delta changed")
    check(clone_math["type_deltas"].get("0x20001") == 1, "root accounting delta changed")

    spans = {}
    for role, target in (("model", model_target), ("prototype", proto_target), ("root", root_target)):
        result = hud.validate_hud_group(records, target, role)
        spans[role] = {"start": result["start"], "end": result["end"]}

    return model_clone, proto_clone, root_clone, {
        "source_targets": {"model": model_target, "prototype": proto_target, "root": root_target},
        "source_spans": spans,
        "clone_math": clone_math,
        "source_scp_record_sha256": BASE.sha256(helper.record_bytes(source_scp)),
        "source_scp_payload_sha256": BASE.sha256(bytes(source_scp["data"])),
        "source_scp_name": source_scp["name"],
        "source_scp_id": source_scp["id"].hex(),
    }


def insert_after_source_groups(
    records: list[dict],
    model_clone: list[dict],
    proto_clone: list[dict],
    root_clone: list[dict],
    clone_info: dict,
) -> None:
    items = [
        (clone_info["source_spans"]["model"]["end"], model_clone),
        (clone_info["source_spans"]["prototype"]["end"], proto_clone),
        (clone_info["source_spans"]["root"]["end"], root_clone),
    ]
    for end, clone in sorted(items, key=lambda item: item[0], reverse=True):
        records[end + 1:end + 1] = copy.deepcopy(clone)


def validate_candidate(candidate: bytes, source_raw: bytes, source_records: list[dict], clone_info: dict) -> dict:
    helper = BASE.load_helper()
    records = helper.parse_wad(candidate)
    check(helper.serialize_wad(records) == candidate, "candidate WAD reparse round-trip differs")
    check(len(records) == EXPECTED_CANDIDATE_PHYSICAL, "candidate physical count changed")
    payloads = helper.payload_records(records)
    check(len(payloads) == EXPECTED_CANDIDATE_PAYLOADS, "candidate payload count changed")

    new_model = one_payload_index(records, NEW_MODEL)
    new_proto = one_payload_index(records, NEW_PROTO)
    new_root = one_payload_index(records, NEW_ROOT)
    model_grammar = hud.validate_hud_group(records, new_model, "model")
    proto_grammar = hud.validate_hud_group(records, new_proto, "prototype")
    root_grammar = hud.validate_hud_group(records, new_root, "root")

    model_rows = records[model_grammar["start"]:model_grammar["end"] + 1]
    proto_rows = records[proto_grammar["start"]:proto_grammar["end"] + 1]
    root_payload = records[new_root]
    proto_payload = records[new_proto]

    check(model_rows[2]["kind"] == 1 and not model_rows[2]["data"]
          and model_rows[2]["id"] == RAVEN_MATERIAL_ID and model_rows[2]["name"] == RAVEN_MATERIAL,
          "new model does not bind existing Raven material")
    check(model_rows[3]["kind"] == 1 and not model_rows[3]["data"]
          and model_rows[3]["id"] == SOURCE_MESH_ID and model_rows[3]["name"] == SOURCE_MESH,
          "new model did not preserve stock Dock mesh")
    check(proto_rows[2]["kind"] == 1 and not proto_rows[2]["data"]
          and proto_rows[2]["id"] == NEW_MODEL_ID and proto_rows[2]["name"] == NEW_MODEL,
          "new prototype does not bind new HUD model")
    check(bytes(proto_payload["data"][0x3A8:0x3B8]) == NEW_PROTO_ID,
          "new prototype self-ID slot changed")
    check(bytes(root_payload["data"][0x0C:0x1C]) == NEW_PROTO_ID,
          "new root prototype slot changed")
    check(bytes(root_payload["data"][0x54:0x64]) == SHARED_COMPASS_ID,
          "new root shared compass slot changed")
    check(bytes(root_payload["data"][0x1C:0x54]) == NEW_ROOT.encode("ascii").ljust(56, b"\0"),
          "new root loader name changed")

    source_proto_index = one_payload_index(source_records, SOURCE_PROTO)
    source_proto_grammar = hud.validate_hud_group(source_records, source_proto_index, "prototype")
    source_scp = source_records[source_proto_grammar["start"] + 3]
    candidate_scp = proto_rows[3]
    check(helper.record_bytes(candidate_scp) == helper.record_bytes(source_scp),
          "cloned local SCP is not serialized byte-identically to DockPoint SCP")
    check((candidate_scp["flags"], len(candidate_scp["data"]), hud.first_dword(candidate_scp))
          == (0x18, 96, 0x10005), "cloned local SCP shape changed")

    account = accounting_snapshot(records)
    check(account["total"] == EXPECTED_CANDIDATE_TOTAL, "candidate WAD_R_UI total changed")
    for key, before in EXPECTED_SOURCE_TYPE_COUNTS.items():
        expected = before + 1
        check(account["counts"].get(key) == expected, f"candidate type row {key:#x} count changed")
        population = sum(hud.first_dword(row) == key for row in payloads)
        check(population == expected, f"candidate type population {key:#x} disagrees with accounting")

    source_same_scp = sum(
        row["kind"] == 1 and row["data"] and row["id"] == source_scp["id"]
        and bytes(row["data"]) == bytes(source_scp["data"])
        for row in source_records
    )
    candidate_same_scp = sum(
        row["kind"] == 1 and row["data"] and row["id"] == source_scp["id"]
        and bytes(row["data"]) == bytes(source_scp["data"])
        for row in records
    )
    check(candidate_same_scp == source_same_scp + 1,
          "candidate did not add exactly one local stock-shaped SCP payload")

    stripped = copy.deepcopy(records)
    spans = []
    for name in (NEW_MODEL, NEW_PROTO, NEW_ROOT):
        index = one_payload_index(stripped, name)
        start = stripped[index]["parent"]
        check(start is not None and stripped[start]["kind"] == 2, f"{name}: missing group")
        end = helper.matching_group_end(stripped, start)
        spans.append((start, end))
    for start, end in sorted(spans, reverse=True):
        del stripped[start:end + 1]
    check(len(stripped) == EXPECTED_SOURCE_PHYSICAL, "stripped candidate physical count changed")
    check(len(helper.payload_records(stripped)) == EXPECTED_SOURCE_PAYLOADS,
          "stripped candidate payload count changed")

    source_payloads = helper.payload_records(source_records)
    stripped_payloads = helper.payload_records(stripped)
    changed_heap = [i for i, (a, b) in enumerate(zip(source_payloads[0]["data"], stripped_payloads[0]["data"])) if a != b]
    changed_root = [i for i, (a, b) in enumerate(zip(source_payloads[1]["data"], stripped_payloads[1]["data"])) if a != b]
    check(set(changed_heap).issubset(set(range(4, 8))), "candidate changed unexpected heap accounting bytes")
    allowed_root = set(range(0x1C, 0x20))
    for row in helper.read_type_table(source_payloads[1]["data"]):
        allowed_root.update(range(row["offset"] + 4, row["offset"] + 12))
    check(set(changed_root).issubset(allowed_root), "candidate changed unexpected root accounting bytes")

    stripped_payloads[0]["data"] = bytearray(source_payloads[0]["data"])
    stripped_payloads[1]["data"] = bytearray(source_payloads[1]["data"])
    check(len(stripped) == len(source_records), "normalized source record count changed")
    changed_original_records = [
        i for i, (before, after) in enumerate(zip(source_records, stripped))
        if helper.record_bytes(before) != helper.record_bytes(after)
    ]
    check(not changed_original_records,
          f"original WAD records changed outside allowed accounting: {changed_original_records[:8]}")

    return {
        "candidate_round_trip_byte_exact": True,
        "candidate_physical_records": len(records),
        "candidate_payload_records": len(payloads),
        "new_groups": {
            "model": {"physical_records": model_grammar["physical_count"], "payloads": model_grammar["payload_count"]},
            "prototype": {"physical_records": proto_grammar["physical_count"], "payloads": proto_grammar["payload_count"]},
            "root": {"physical_records": root_grammar["physical_count"], "payloads": root_grammar["payload_count"]},
        },
        "local_scp_preserved_byte_exact": True,
        "local_scp_same_body_population_before": source_same_scp,
        "local_scp_same_body_population_after": candidate_same_scp,
        "root_prototype_slot": NEW_PROTO_ID.hex(),
        "root_shared_compass_slot": SHARED_COMPASS_ID.hex(),
        "prototype_model_link": NEW_MODEL_ID.hex(),
        "model_material_link": RAVEN_MATERIAL_ID.hex(),
        "model_mesh_link": SOURCE_MESH_ID.hex(),
        "accounting_total": account["total"],
        "accounting_counts": {f"0x{key:X}": account["counts"][key] for key in TYPE_INCREMENTS},
        "original_records_byte_identical_after_removing_new_groups_and_normalizing_accounting": True,
        "source_sha256": BASE.sha256(source_raw),
        "candidate_sha256": BASE.sha256(candidate),
    }


def build_candidate(raw: bytes) -> tuple[bytes, dict]:
    check(BASE.sha256(raw) == BASE.EXPECTED_WAD, "source WAD hash differs from pinned Raven state")
    helper = BASE.load_helper()
    source_records = helper.parse_wad(raw)
    check(helper.serialize_wad(source_records) == raw, "source WAD round-trip differs")
    check(len(source_records) == EXPECTED_SOURCE_PHYSICAL, "source physical record count changed")
    check(len(helper.payload_records(source_records)) == EXPECTED_SOURCE_PAYLOADS, "source payload count changed")

    reduced = json.loads(REDUCED.read_text(encoding="utf-8"))
    inspected_records, physical_report = PHYSICAL.inspect(raw, reduced)
    check(helper.serialize_wad(inspected_records) == raw, "physical inspection changed source records")
    binding_report = BINDING.inspect_records(raw, inspected_records, physical_report)
    check(binding_report["decision"] == BINDING.LOCAL_DECISION,
          f"SCP binding gate is not LOCAL_SCP_REQUIRED: {binding_report['decision']}")
    check(binding_report["ready_for_offline_four_payload_builder"], "SCP binding gate did not authorize full clone")

    records = helper.parse_wad(raw)
    model_clone, proto_clone, root_clone, clone_info = clone_groups(records, physical_report)
    accounting = apply_accounting(records)
    insert_after_source_groups(records, model_clone, proto_clone, root_clone, clone_info)
    candidate = helper.serialize_wad(records)
    validation = validate_candidate(candidate, raw, source_records, clone_info)

    report = {
        "result": RESULT,
        "conclusion": CONCLUSION,
        "source_wad_sha256": BASE.sha256(raw),
        "candidate_wad_sha256": BASE.sha256(candidate),
        "scp_binding_decision": binding_report["decision"],
        "architecture": {
            "hud_IconName_source_string": "goCompletionistRavenHUD",
            "hud_IconName_hash": "45E5C7943749F81C",
            "root": {"name": NEW_ROOT, "id": NEW_ROOT_ID.hex(), "new": True},
            "prototype": {"name": NEW_PROTO, "id": NEW_PROTO_ID.hex(), "new": True},
            "model": {"name": NEW_MODEL, "id": NEW_MODEL_ID.hex(), "new": True},
            "local_scp": {
                "name": clone_info["source_scp_name"],
                "id": clone_info["source_scp_id"],
                "new_identity": False,
                "new_local_payload_instance": True,
                "serialized_byte_identical_to_DockPoint_source": True,
            },
            "material": {"name": RAVEN_MATERIAL, "id": RAVEN_MATERIAL_ID.hex(), "reused": True},
            "mesh": {"name": SOURCE_MESH, "id": SOURCE_MESH_ID.hex(), "reused": True},
            "shared_compass": {"name": SHARED_COMPASS, "id": SHARED_COMPASS_ID.hex(), "reused": True},
        },
        "clone_accounting": {
            "physical_records_delta": 13,
            "payload_records_delta": 4,
            "wad_r_ui_accounting_delta": 3,
            **accounting,
        },
        "validation": validation,
        "game_files_read": True,
        "game_files_written": False,
        "dcb_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "ready_for_offline_dcb_iconname_gate": True,
        "ready_for_runtime_test": False,
        "next_gate": (
            "Build the offline wad_r_perm.dcb candidate whose only visual change is "
            "CompletionistRaven.IconName -> goCompletionistRavenHUD, then validate both files together."
        ),
    }
    return candidate, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output-wad", type=Path, default=OUTPUT_WAD)
    parser.add_argument("--report", type=Path, default=OUTPUT_REPORT)
    args = parser.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/wad/pc_le/r_ui.wad"
    raw = source.read_bytes()
    output = hud.safe_output(args.output_wad, REPO / "build/v0.10.4")
    report_path = hud.safe_output(args.report, REPO / "archive/field-logs")
    check(not output.is_relative_to(game) and not report_path.is_relative_to(game),
          "offline outputs overlap game tree")

    candidate, report = build_candidate(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output_wad"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == raw, "source r_ui.wad changed during offline build")

    print(RESULT)
    print("  SCP decision:       LOCAL_SCP_REQUIRED")
    print("  physical delta:     +13")
    print("  payload delta:      +4")
    print("  WAD_R_UI delta:     +3")
    print("  local SCP:          preserved byte-exact")
    print("  game files written: false")
    print("  runtime test:       NOT SAFE YET")
    print(f"  candidate:          {output}")
    print(f"  report:             {report_path}")


if __name__ == "__main__":
    main()
