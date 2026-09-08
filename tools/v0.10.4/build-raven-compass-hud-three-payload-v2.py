"""Build the minimal Raven compass HUD resource clone offline, v2.

This version preserves the exact dependency encoding used by each source Dock
resource group. A dependency may be represented inline in the payload, by a
zero-data group link, or by both. The clone must reproduce that same signature.

It never writes into the God of War directory and does not modify DCB/save/state.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

BASE = "build-raven-compass-hud-three-payload.py"
RESULT = "OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BUILT"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_base():
    path = Path(__file__).with_name(BASE)
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    spec = importlib.util.spec_from_file_location("completionist_hud_three_payload_v1", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def group_records(base, helper, records: list[dict], payload: dict) -> list[dict]:
    start, end = base.group_span(helper, records, payload)
    return records[start:end + 1]


def dependency_signature(group: list[dict], payload: dict, target_id: bytes) -> dict:
    return {
        "inline": count_bytes(payload["data"], target_id),
        "zero_data_links": sum(
            1 for record in group
            if len(record["data"]) == 0 and bytes(record["id"]) == target_id
        ),
    }


def count_bytes(data: bytes | bytearray, needle: bytes) -> int:
    return bytes(data).count(needle)


def validate_signature(signature: dict, label: str) -> None:
    inline = int(signature["inline"])
    links = int(signature["zero_data_links"])
    check(inline in (0, 1), f"{label}: unexpected inline dependency count {inline}")
    check(links in (0, 1), f"{label}: unexpected zero-data dependency count {links}")
    check(inline + links >= 1, f"{label}: dependency is not represented in payload or group link")


def retarget_dependency(
    group: list[dict],
    payload: dict,
    old_id: bytes,
    new_id: bytes,
    old_name: str,
    new_name: str,
    expected_signature: dict,
    label: str,
) -> None:
    validate_signature(expected_signature, label)
    current = dependency_signature(group, payload, old_id)
    check(current == expected_signature,
          f"{label}: source encoding changed before retarget: expected {expected_signature}, got {current}")
    target_before = dependency_signature(group, payload, new_id)
    check(target_before == {"inline": 0, "zero_data_links": 0},
          f"{label}: target id already present before retarget: {target_before}")

    if expected_signature["inline"]:
        payload["data"][:] = bytes(payload["data"]).replace(old_id, new_id)

    for record in group:
        if len(record["data"]) == 0 and bytes(record["id"]) == old_id:
            record["id"] = new_id
            if record["name"].lower() == old_name.lower():
                record["name"] = new_name

    old_after = dependency_signature(group, payload, old_id)
    new_after = dependency_signature(group, payload, new_id)
    check(old_after == {"inline": 0, "zero_data_links": 0},
          f"{label}: old dependency survived retarget: {old_after}")
    check(new_after == expected_signature,
          f"{label}: clone dependency signature changed: expected {expected_signature}, got {new_after}")


def build(raw: bytes) -> tuple[bytes, dict]:
    base = load_base()
    check(sha256(raw) == base.EXPECTED_WAD, "r_ui.wad is not the current proven Raven state")
    helper = base.load_helper()
    records = helper.parse_wad(raw)
    check(helper.serialize_wad(records) == raw, "source r_ui.wad does not round-trip byte-exactly")
    original = copy.deepcopy(records)
    source_payload_count = len(helper.payload_records(records))
    source_physical_count = len(records)
    check(source_payload_count == 20415 and source_physical_count == 53811,
          "current WAD physical/payload counts changed")

    source_root = base.one_payload(records, base.SOURCE_ROOT)
    source_proto = base.one_payload(records, base.SOURCE_PROTO)
    source_model = base.one_payload(records, base.SOURCE_MODEL)
    source_material = base.one_payload(records, base.SOURCE_MATERIAL)
    source_mesh = base.one_payload(records, base.SOURCE_MESH)
    shared_compass = base.one_payload(records, base.SHARED_COMPASS)
    raven_material = base.one_payload(records, base.RAVEN_MATERIAL)

    expected_sources = [
        (source_root, base.SOURCE_ROOT_ID, 0x3D, 164),
        (source_proto, base.SOURCE_PROTO_ID, 0x3D, 1184),
        (source_model, base.SOURCE_MODEL_ID, 0x8E, 80),
        (source_material, base.SOURCE_MATERIAL_ID, 0x14, 384),
        (source_mesh, base.SOURCE_MESH_ID, 0x98, 388),
        (shared_compass, base.SHARED_COMPASS_ID, 0x3D, 784),
        (raven_material, base.RAVEN_MATERIAL_ID, 0x14, 384),
    ]
    for record, expected_id, flags, size in expected_sources:
        check(bytes(record["id"]) == expected_id, f"{record['name']}: resource id changed")
        check(int(record["flags"]) == flags and len(record["data"]) == size,
              f"{record['name']}: payload shape changed")

    check(bytes(source_root["data"])[base.ROOT_PROTO_OFFSET:base.ROOT_PROTO_OFFSET + 16] == base.SOURCE_PROTO_ID,
          "Dock root prototype reference changed")
    check(bytes(source_root["data"])[base.ROOT_SHARED_OFFSET:base.ROOT_SHARED_OFFSET + 16] == base.SHARED_COMPASS_ID,
          "Dock root shared compass reference changed")

    source_proto_group = group_records(base, helper, records, source_proto)
    source_model_group = group_records(base, helper, records, source_model)
    proto_model_sig = dependency_signature(source_proto_group, source_proto, base.SOURCE_MODEL_ID)
    model_material_sig = dependency_signature(source_model_group, source_model, base.SOURCE_MATERIAL_ID)
    model_mesh_sig = dependency_signature(source_model_group, source_model, base.SOURCE_MESH_ID)
    validate_signature(proto_model_sig, "Dock prototype -> model")
    validate_signature(model_material_sig, "Dock model -> material")
    validate_signature(model_mesh_sig, "Dock model -> mesh")

    for name in (base.NEW_ROOT, base.NEW_PROTO, base.NEW_MODEL):
        check(not any(r["name"].lower() == name.lower() for r in records),
              f"candidate resource name already exists: {name}")
    for new_id in (base.NEW_ROOT_ID, base.NEW_PROTO_ID, base.NEW_MODEL_ID):
        check(not any(bytes(r["id"]) == new_id for r in records),
              f"candidate resource id collision: {new_id.hex()}")

    model_clone = base.clone_group(helper, records, source_model, base.NEW_MODEL, base.NEW_MODEL_ID)
    model_payload = base.payload_in_clone(model_clone, base.NEW_MODEL)
    retarget_dependency(
        model_clone, model_payload,
        base.SOURCE_MATERIAL_ID, base.RAVEN_MATERIAL_ID,
        base.SOURCE_MATERIAL, base.RAVEN_MATERIAL,
        model_material_sig, "Raven HUD model -> Raven material",
    )
    check(dependency_signature(model_clone, model_payload, base.SOURCE_MESH_ID) == model_mesh_sig,
          "Raven HUD model no longer preserves the Dock mesh dependency encoding")

    proto_clone = base.clone_group(helper, records, source_proto, base.NEW_PROTO, base.NEW_PROTO_ID)
    proto_payload = base.payload_in_clone(proto_clone, base.NEW_PROTO)
    retarget_dependency(
        proto_clone, proto_payload,
        base.SOURCE_MODEL_ID, base.NEW_MODEL_ID,
        base.SOURCE_MODEL, base.NEW_MODEL,
        proto_model_sig, "Raven HUD prototype -> Raven HUD model",
    )

    root_clone = base.clone_group(helper, records, source_root, base.NEW_ROOT, base.NEW_ROOT_ID)
    root_payload = base.payload_in_clone(root_clone, base.NEW_ROOT)
    check(bytes(root_payload["data"])[base.ROOT_PROTO_OFFSET:base.ROOT_PROTO_OFFSET + 16] == base.SOURCE_PROTO_ID,
          "cloned root prototype field changed before retarget")
    root_payload["data"][base.ROOT_PROTO_OFFSET:base.ROOT_PROTO_OFFSET + 16] = base.NEW_PROTO_ID
    check(bytes(root_payload["data"])[base.ROOT_SHARED_OFFSET:base.ROOT_SHARED_OFFSET + 16] == base.SHARED_COMPASS_ID,
          "cloned root shared compass field changed")
    root_proto_links = [
        r for r in root_clone
        if len(r["data"]) == 0 and bytes(r["id"]) == base.SOURCE_PROTO_ID
    ]
    check(len(root_proto_links) in (0, 1),
          f"Raven HUD root has unexpected prototype link count {len(root_proto_links)}")
    for record in root_proto_links:
        record["id"] = base.NEW_PROTO_ID
        if record["name"].lower() == base.SOURCE_PROTO.lower():
            record["name"] = base.NEW_PROTO

    accounting = base.update_accounting(helper, records)

    source_spans = []
    for payload, clone in ((source_model, model_clone), (source_proto, proto_clone), (source_root, root_clone)):
        start, end = base.group_span(helper, records, payload)
        source_spans.append((start, end, clone))
    for _start, end, clone in sorted(source_spans, key=lambda item: item[1], reverse=True):
        records[end + 1:end + 1] = clone

    candidate = helper.serialize_wad(records)
    reparsed = helper.parse_wad(candidate)
    check(helper.serialize_wad(reparsed) == candidate, "candidate WAD does not round-trip byte-exactly")
    check(len(helper.payload_records(reparsed)) == source_payload_count + 3,
          "candidate payload delta is not exactly +3")

    new_root = base.one_payload(reparsed, base.NEW_ROOT)
    new_proto = base.one_payload(reparsed, base.NEW_PROTO)
    new_model = base.one_payload(reparsed, base.NEW_MODEL)
    check(bytes(new_root["id"]) == base.NEW_ROOT_ID, "Raven HUD root id changed after reparse")
    check(bytes(new_proto["id"]) == base.NEW_PROTO_ID, "Raven HUD prototype id changed after reparse")
    check(bytes(new_model["id"]) == base.NEW_MODEL_ID, "Raven HUD model id changed after reparse")
    check(bytes(new_root["data"])[base.ROOT_PROTO_OFFSET:base.ROOT_PROTO_OFFSET + 16] == base.NEW_PROTO_ID,
          "Raven HUD root does not point to Raven HUD prototype")
    check(bytes(new_root["data"])[base.ROOT_SHARED_OFFSET:base.ROOT_SHARED_OFFSET + 16] == base.SHARED_COMPASS_ID,
          "Raven HUD root no longer shares goProtocompassicons")

    new_proto_group = group_records(base, helper, reparsed, new_proto)
    new_model_group = group_records(base, helper, reparsed, new_model)
    check(dependency_signature(new_proto_group, new_proto, base.NEW_MODEL_ID) == proto_model_sig,
          "Raven HUD prototype does not preserve the source prototype->model encoding")
    check(dependency_signature(new_proto_group, new_proto, base.SOURCE_MODEL_ID) ==
          {"inline": 0, "zero_data_links": 0},
          "Raven HUD prototype still references stock MDL_boatdock")
    check(dependency_signature(new_model_group, new_model, base.RAVEN_MATERIAL_ID) == model_material_sig,
          "Raven HUD model does not preserve the source model->material encoding")
    check(dependency_signature(new_model_group, new_model, base.SOURCE_MATERIAL_ID) ==
          {"inline": 0, "zero_data_links": 0},
          "Raven HUD model still references the Dock material")
    check(dependency_signature(new_model_group, new_model, base.SOURCE_MESH_ID) == model_mesh_sig,
          "Raven HUD model does not preserve the Dock mesh dependency encoding")

    payloads = helper.payload_records(reparsed)
    heap, root = payloads[0], payloads[1]
    check(struct.unpack_from("<I", heap["data"], 4)[0] == 16804, "candidate heap total wrong")
    check(struct.unpack_from("<I", root["data"], 0x1C)[0] == 16804, "candidate root total wrong")
    rows = helper.read_type_table(root["data"])
    by_key = {int(row["key"]): row for row in rows}
    check(int(by_key[0x10001]["count"]) == 1726, "candidate 0x10001 count wrong")
    check(int(by_key[0x20001]["count"]) == 2074, "candidate 0x20001 count wrong")
    count_10001 = sum(
        1 for r in payloads
        if len(r["data"]) >= 4 and struct.unpack_from("<I", r["data"], 0)[0] == 0x10001
    )
    count_20001 = sum(
        1 for r in payloads
        if len(r["data"]) >= 4 and struct.unpack_from("<I", r["data"], 0)[0] == 0x20001
    )
    check(count_10001 == int(by_key[0x10001]["count"]), "candidate 0x10001 population/count mismatch")
    check(count_20001 == int(by_key[0x20001]["count"]), "candidate 0x20001 population/count mismatch")
    model_key = struct.unpack_from("<I", new_model["data"], 0)[0]
    check(model_key == 0x1002000C and model_key not in by_key,
          "Raven HUD model unexpectedly participates in root type table")

    stripped, group_sizes = base.remove_new_group_spans(helper, reparsed)
    check(len(stripped) == len(original), "removing three clone groups did not restore original record count")
    base.normalise_accounting_for_compare(helper, original, stripped)
    for index, (before, after) in enumerate(zip(original, stripped)):
        check(helper.record_bytes(before) == helper.record_bytes(after),
              f"original record changed outside allowed accounting bytes: index={index} name={before['name']}")

    return candidate, {
        "result": RESULT,
        "builder_revision": 2,
        "source_wad_sha256": sha256(raw),
        "candidate_wad_sha256": sha256(candidate),
        "source_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "source_physical_records": source_physical_count,
        "candidate_physical_records": len(reparsed),
        "source_payloads": source_payload_count,
        "candidate_payloads": len(payloads),
        "physical_payload_delta": 3,
        "accounting_delta": 2,
        "accounting": accounting,
        "source_dependency_signatures": {
            "prototype_to_model": proto_model_sig,
            "model_to_material": model_material_sig,
            "model_to_mesh": model_mesh_sig,
        },
        "clone_group_record_counts": group_sizes,
        "raven_hud": {
            "IconName_source_string": "goCompletionistRavenHUD",
            "root": {
                "name": base.NEW_ROOT,
                "id": base.NEW_ROOT_ID.hex(),
                "prototype": base.NEW_PROTO,
                "shared_compass": base.SHARED_COMPASS,
            },
            "prototype": {
                "name": base.NEW_PROTO,
                "id": base.NEW_PROTO_ID.hex(),
                "model": base.NEW_MODEL,
            },
            "model": {
                "name": base.NEW_MODEL,
                "id": base.NEW_MODEL_ID.hex(),
                "material": base.RAVEN_MATERIAL,
                "mesh": base.SOURCE_MESH,
            },
        },
        "proof": {
            "candidate_round_trip_byte_exact": True,
            "three_new_payloads_only": True,
            "root_type_accounting_delta_exactly_two": True,
            "dependency_encoding_preserved_exactly": True,
            "prototype_points_to_new_model": True,
            "model_points_to_existing_raven_material": True,
            "model_reuses_stock_dock_mesh": True,
            "root_reuses_shared_compass_prototype": True,
            "all_original_records_byte_identical_after_accounting_normalisation": True,
            "stock_dock_resources_untouched": True,
            "existing_raven_map_resources_untouched": True,
            "ready_for_offline_dcb_iconname_gate": True,
        },
        "game_files_read": True,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "conclusion": "THREE_PAYLOAD_RAVEN_HUD_CLONE_BUILT_OFFLINE",
        "next_gate": (
            "Keep this candidate outside the game tree. Build an offline-only wad_r_perm.dcb candidate "
            "that changes only the Raven compass class IconName from DockPoint to goCompletionistRavenHUD, "
            "then verify the DCB diff and combined WAD/DCB contract before any runtime install."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output-wad", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/wad/pc_le/r_ui.wad"
    check(source.is_file(), f"missing {source}")
    output_wad = args.output_wad.resolve()
    report_path = args.report.resolve()
    check(output_wad != source.resolve(), "output WAD overlaps live r_ui.wad")
    check(not output_wad.is_relative_to(game), "output WAD must stay outside game directory")
    check(not report_path.is_relative_to(game), "report must stay outside game directory")
    check(output_wad != report_path, "output WAD and report paths overlap")

    before = source.read_bytes()
    candidate, report = build(before)
    check(source.read_bytes() == before, "live r_ui.wad changed during offline build")
    output_wad.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_wad.write_bytes(candidate)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == before, "live r_ui.wad changed after output write")

    print(report["result"])
    print(f"  builder revision:       {report['builder_revision']}")
    print(f"  candidate:              {output_wad}")
    print(f"  candidate sha256:       {report['candidate_wad_sha256']}")
    print(f"  prototype -> model:     {report['source_dependency_signatures']['prototype_to_model']}")
    print(f"  model -> material:      {report['source_dependency_signatures']['model_to_material']}")
    print(f"  model -> mesh:          {report['source_dependency_signatures']['model_to_mesh']}")
    print(f"  physical payload delta: +{report['physical_payload_delta']}")
    print(f"  WAD_R_UI accounting:    +{report['accounting_delta']}")
    print(f"  report:                 {report_path}")
    print("  game files written:     false")


if __name__ == "__main__":
    main()
