"""Build the minimal Raven compass HUD resource clone offline.

This is an offline-only gate. It clones DockPoint's HUD root, prototype and
model resource groups, reuses the existing Raven material, stock Dock mesh and
shared compass prototype, and updates only the proven WAD_R_UI accounting rows.
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

EXPECTED_WAD = "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3"
HELPER = "build-raven-ui-logical-clone.py"
HELPER_SHA256_LF = "d5f7c5b77166b3e9ba46dec17174fc1f30ca5e3bab492527636cdf63c8b41b03"
RESULT = "OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BUILT"

SOURCE_ROOT = "goboatdock"
SOURCE_PROTO = "goProtoBoatDock"
SOURCE_MODEL = "MDL_boatdock"
SOURCE_MATERIAL = "MAT_0C599DC8DC7E2170"
SOURCE_MESH = "MG_boatdock_0"
SHARED_COMPASS = "goProtocompassicons"
RAVEN_MATERIAL = "MAT_AE4AD85BB993F040"

NEW_ROOT = "gocompletionistravenhud"
NEW_PROTO = "goProtoCompletionistRavenHUD"
NEW_MODEL = "MDL_completionistravenhud"

SOURCE_ROOT_ID = bytes.fromhex("e38da34945defe418b8be0bb6b985f12")
SOURCE_PROTO_ID = bytes.fromhex("e38da34945defe418b8be0bb6a985f12")
SOURCE_MODEL_ID = bytes.fromhex("808e5817524559f5c65636ffc0fbc1a9")
SOURCE_MATERIAL_ID = bytes.fromhex("61ed20dc7a5567ba23016085750aacf2")
SOURCE_MESH_ID = bytes.fromhex("c3f6b4c5a8270df607ea3e6e7f891292")
SHARED_COMPASS_ID = bytes.fromhex("502b9225361cf6449d8d85048f0b1a75")
RAVEN_MATERIAL_ID = bytes.fromhex("dac6009fd0f18caad2ed322463c3d0c8")

NEW_ROOT_ID = bytes.fromhex("f0029a68d9705e95a981aab8bff0c5b8")
NEW_PROTO_ID = bytes.fromhex("b2a833d6144789e8099acf85e832d652")
NEW_MODEL_ID = bytes.fromhex("4a7911dc2db72cecaf6c187a66bfd11f")

ROOT_PROTO_OFFSET = 0x0C
ROOT_SHARED_OFFSET = 0x54
TYPE_INCREMENTS = {0x10001: 1, 0x20001: 1}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_helper():
    path = Path(__file__).with_name(HELPER)
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    check(sha256(raw) == HELPER_SHA256_LF, f"pinned helper changed: {HELPER}")
    spec = importlib.util.spec_from_file_location("completionist_hud_three_payload_wad", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def one_payload(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"].lower() == name.lower() and len(r["data"]) > 0]
    check(len(rows) == 1, f"expected one payload {name!r}, found {len(rows)}")
    return rows[0]


def group_span(helper, records: list[dict], payload: dict) -> tuple[int, int]:
    start = payload["parent"]
    check(start is not None and records[start]["kind"] == 2,
          f"{payload['name']}: payload is not inside a resource group")
    end = helper.matching_group_end(records, start)
    check(start < records.index(payload) < end, f"{payload['name']}: malformed group span")
    return start, end


def count_bytes(data: bytes | bytearray, needle: bytes) -> int:
    return bytes(data).count(needle)


def replace_exact(data: bytearray, old: bytes, new: bytes, expected: int, label: str) -> None:
    check(len(old) == len(new), f"{label}: replacement width changed")
    count = count_bytes(data, old)
    check(count == expected, f"{label}: expected {expected} source id occurrence(s), found {count}")
    data[:] = bytes(data).replace(old, new)
    check(count_bytes(data, old) == 0, f"{label}: source id survived replacement")
    check(count_bytes(data, new) >= expected, f"{label}: target id missing after replacement")


def clone_group(helper, records: list[dict], payload: dict, new_name: str, new_id: bytes) -> list[dict]:
    start, end = group_span(helper, records, payload)
    clone = [copy.deepcopy(records[i]) for i in range(start, end + 1)]
    source_name = payload["name"].lower()
    source_id = bytes(payload["id"])
    renamed = 0
    reidentified = 0
    for record in clone:
        record["original_offset"] = None
        record["payload_index"] = None
        record["parent"] = None
        if record["name"].lower() == source_name:
            record["name"] = new_name
            renamed += 1
        if bytes(record["id"]) == source_id:
            record["id"] = new_id
            reidentified += 1
    check(renamed >= 2, f"{payload['name']}: group did not contain wrapper + payload names")
    check(reidentified >= 1, f"{payload['name']}: group did not carry its resource id")
    return clone


def payload_in_clone(clone: list[dict], name: str) -> dict:
    rows = [r for r in clone if r["name"].lower() == name.lower() and len(r["data"]) > 0]
    check(len(rows) == 1, f"clone expected one payload {name!r}, found {len(rows)}")
    return rows[0]


def retarget_zero_data_links(clone: list[dict], old_id: bytes, new_id: bytes,
                             old_name: str, new_name: str, expected: int, label: str) -> None:
    hits = [r for r in clone if len(r["data"]) == 0 and bytes(r["id"]) == old_id]
    check(len(hits) == expected, f"{label}: expected {expected} zero-data link(s), found {len(hits)}")
    for record in hits:
        record["id"] = new_id
        if record["name"].lower() == old_name.lower():
            record["name"] = new_name


def update_accounting(helper, records: list[dict]) -> dict:
    payloads = helper.payload_records(records)
    check(len(payloads) >= 2, "WAD has fewer than two payloads")
    heap, root = payloads[0], payloads[1]
    check(heap["name"].upper() == "WAD_R_UI" and root["name"].upper() == "WAD_R_UI",
          "first two WAD payloads are not WAD_R_UI accounting records")
    old_heap_total = struct.unpack_from("<I", heap["data"], 4)[0]
    old_root_total = struct.unpack_from("<I", root["data"], 0x1C)[0]
    check(old_heap_total == old_root_total == 16802, "unexpected current WAD_R_UI total")
    rows = helper.read_type_table(root["data"])
    by_key = {int(row["key"]): row for row in rows}
    check(0x10001 in by_key and 0x20001 in by_key, "required Rig rows missing")
    check(int(by_key[0x10001]["count"]) == 1725, "0x10001 source count changed")
    check(int(by_key[0x20001]["count"]) == 2073, "0x20001 source count changed")

    new_base = 0
    after_rows = []
    for row in rows:
        key = int(row["key"])
        amount = int(row["count"]) + TYPE_INCREMENTS.get(key, 0)
        struct.pack_into("<III", root["data"], int(row["offset"]), key, new_base, amount)
        after_rows.append({"key": f"0x{key:X}", "base": new_base, "count": amount,
                           "delta": TYPE_INCREMENTS.get(key, 0)})
        new_base += amount
    check(new_base == old_root_total + 2, "updated WAD_R_UI total is not source + 2")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)
    return {
        "before": old_root_total,
        "after": new_base,
        "type_rows_before": [{"key": f"0x{int(r['key']):X}", "base": int(r["base"]),
                              "count": int(r["count"])} for r in rows],
        "type_rows_after": after_rows,
    }


def normalise_accounting_for_compare(helper, original: list[dict], candidate: list[dict]) -> None:
    orig_payloads = helper.payload_records(original)
    cand_payloads = helper.payload_records(candidate)
    check(len(orig_payloads) >= 2 and len(cand_payloads) >= 2, "short accounting payload list")
    orig_heap, orig_root = orig_payloads[0], orig_payloads[1]
    cand_heap, cand_root = cand_payloads[0], cand_payloads[1]
    check(orig_heap["name"].upper() == cand_heap["name"].upper() == "WAD_R_UI", "heap identity changed")
    check(orig_root["name"].upper() == cand_root["name"].upper() == "WAD_R_UI", "root identity changed")

    cand_heap["data"][4:8] = orig_heap["data"][4:8]
    orig_rows = helper.read_type_table(orig_root["data"])
    cand_rows = helper.read_type_table(cand_root["data"])
    check(len(orig_rows) == len(cand_rows), "type-row count changed")
    cand_root["data"][0x1C:0x20] = orig_root["data"][0x1C:0x20]
    for before, after in zip(orig_rows, cand_rows):
        check(int(before["key"]) == int(after["key"]), "type-row key order changed")
        boff = int(before["offset"])
        aoff = int(after["offset"])
        cand_root["data"][aoff + 4:aoff + 12] = orig_root["data"][boff + 4:boff + 12]


def remove_new_group_spans(helper, records: list[dict]) -> tuple[list[dict], dict[str, int]]:
    spans = []
    sizes = {}
    for name in (NEW_MODEL, NEW_PROTO, NEW_ROOT):
        payload = one_payload(records, name)
        start, end = group_span(helper, records, payload)
        spans.append((start, end, name))
        sizes[name] = end - start + 1
    used = set()
    for start, end, name in spans:
        current = set(range(start, end + 1))
        check(not used.intersection(current), f"new group spans overlap at {name}")
        used.update(current)
    stripped = [copy.deepcopy(r) for i, r in enumerate(records) if i not in used]
    return stripped, sizes


def build(raw: bytes) -> tuple[bytes, dict]:
    check(sha256(raw) == EXPECTED_WAD, "r_ui.wad is not the current proven Raven state")
    helper = load_helper()
    records = helper.parse_wad(raw)
    check(helper.serialize_wad(records) == raw, "source r_ui.wad does not round-trip byte-exactly")
    original = copy.deepcopy(records)
    source_payload_count = len(helper.payload_records(records))
    source_physical_count = len(records)
    check(source_payload_count == 20415 and source_physical_count == 53811,
          "current WAD physical/payload counts changed")

    source_root = one_payload(records, SOURCE_ROOT)
    source_proto = one_payload(records, SOURCE_PROTO)
    source_model = one_payload(records, SOURCE_MODEL)
    source_material = one_payload(records, SOURCE_MATERIAL)
    source_mesh = one_payload(records, SOURCE_MESH)
    shared_compass = one_payload(records, SHARED_COMPASS)
    raven_material = one_payload(records, RAVEN_MATERIAL)

    expected_sources = [
        (source_root, SOURCE_ROOT_ID, 0x3D, 164),
        (source_proto, SOURCE_PROTO_ID, 0x3D, 1184),
        (source_model, SOURCE_MODEL_ID, 0x8E, 80),
        (source_material, SOURCE_MATERIAL_ID, 0x14, 384),
        (source_mesh, SOURCE_MESH_ID, 0x98, 388),
        (shared_compass, SHARED_COMPASS_ID, 0x3D, 784),
        (raven_material, RAVEN_MATERIAL_ID, 0x14, 384),
    ]
    for record, expected_id, flags, size in expected_sources:
        check(bytes(record["id"]) == expected_id, f"{record['name']}: resource id changed")
        check(int(record["flags"]) == flags and len(record["data"]) == size,
              f"{record['name']}: payload shape changed")

    check(bytes(source_root["data"])[ROOT_PROTO_OFFSET:ROOT_PROTO_OFFSET + 16] == SOURCE_PROTO_ID,
          "Dock root prototype reference changed")
    check(bytes(source_root["data"])[ROOT_SHARED_OFFSET:ROOT_SHARED_OFFSET + 16] == SHARED_COMPASS_ID,
          "Dock root shared compass reference changed")
    check(count_bytes(source_proto["data"], SOURCE_MODEL_ID) == 1,
          "Dock prototype model reference count changed")
    check(count_bytes(source_model["data"], SOURCE_MATERIAL_ID) == 1,
          "Dock model material reference count changed")
    check(count_bytes(source_model["data"], SOURCE_MESH_ID) == 1,
          "Dock model mesh reference count changed")

    for name in (NEW_ROOT, NEW_PROTO, NEW_MODEL):
        check(not any(r["name"].lower() == name.lower() for r in records),
              f"candidate resource name already exists: {name}")
    for new_id in (NEW_ROOT_ID, NEW_PROTO_ID, NEW_MODEL_ID):
        check(not any(bytes(r["id"]) == new_id for r in records),
              f"candidate resource id collision: {new_id.hex()}")

    model_clone = clone_group(helper, records, source_model, NEW_MODEL, NEW_MODEL_ID)
    model_payload = payload_in_clone(model_clone, NEW_MODEL)
    replace_exact(model_payload["data"], SOURCE_MATERIAL_ID, RAVEN_MATERIAL_ID, 1,
                  "Raven HUD model material")
    retarget_zero_data_links(model_clone, SOURCE_MATERIAL_ID, RAVEN_MATERIAL_ID,
                             SOURCE_MATERIAL, RAVEN_MATERIAL, 1, "Raven HUD model material link")
    check(count_bytes(model_payload["data"], SOURCE_MESH_ID) == 1,
          "Raven HUD model no longer shares Dock mesh")

    proto_clone = clone_group(helper, records, source_proto, NEW_PROTO, NEW_PROTO_ID)
    proto_payload = payload_in_clone(proto_clone, NEW_PROTO)
    replace_exact(proto_payload["data"], SOURCE_MODEL_ID, NEW_MODEL_ID, 1,
                  "Raven HUD prototype model")
    retarget_zero_data_links(proto_clone, SOURCE_MODEL_ID, NEW_MODEL_ID,
                             SOURCE_MODEL, NEW_MODEL, 1, "Raven HUD prototype model link")

    root_clone = clone_group(helper, records, source_root, NEW_ROOT, NEW_ROOT_ID)
    root_payload = payload_in_clone(root_clone, NEW_ROOT)
    check(bytes(root_payload["data"])[ROOT_PROTO_OFFSET:ROOT_PROTO_OFFSET + 16] == SOURCE_PROTO_ID,
          "cloned root prototype field changed before retarget")
    root_payload["data"][ROOT_PROTO_OFFSET:ROOT_PROTO_OFFSET + 16] = NEW_PROTO_ID
    check(bytes(root_payload["data"])[ROOT_SHARED_OFFSET:ROOT_SHARED_OFFSET + 16] == SHARED_COMPASS_ID,
          "cloned root shared compass field changed")
    # Some resource groups carry an explicit zero-data dependency record, while
    # others encode this dependency only inside the payload. Retarget it if present.
    root_proto_links = [r for r in root_clone if len(r["data"]) == 0 and bytes(r["id"]) == SOURCE_PROTO_ID]
    check(len(root_proto_links) in (0, 1), f"Raven HUD root has unexpected prototype link count {len(root_proto_links)}")
    for record in root_proto_links:
        record["id"] = NEW_PROTO_ID
        if record["name"].lower() == SOURCE_PROTO.lower():
            record["name"] = NEW_PROTO

    accounting = update_accounting(helper, records)

    source_spans = []
    for payload, clone in ((source_model, model_clone), (source_proto, proto_clone), (source_root, root_clone)):
        start, end = group_span(helper, records, payload)
        source_spans.append((start, end, clone))
    # Descending insertion preserves all source indices gathered above.
    for _start, end, clone in sorted(source_spans, key=lambda item: item[1], reverse=True):
        records[end + 1:end + 1] = clone

    candidate = helper.serialize_wad(records)
    reparsed = helper.parse_wad(candidate)
    check(helper.serialize_wad(reparsed) == candidate, "candidate WAD does not round-trip byte-exactly")
    check(len(helper.payload_records(reparsed)) == source_payload_count + 3,
          "candidate payload delta is not exactly +3")

    new_root = one_payload(reparsed, NEW_ROOT)
    new_proto = one_payload(reparsed, NEW_PROTO)
    new_model = one_payload(reparsed, NEW_MODEL)
    check(bytes(new_root["id"]) == NEW_ROOT_ID, "Raven HUD root id changed after reparse")
    check(bytes(new_proto["id"]) == NEW_PROTO_ID, "Raven HUD prototype id changed after reparse")
    check(bytes(new_model["id"]) == NEW_MODEL_ID, "Raven HUD model id changed after reparse")
    check(bytes(new_root["data"])[ROOT_PROTO_OFFSET:ROOT_PROTO_OFFSET + 16] == NEW_PROTO_ID,
          "Raven HUD root does not point to Raven HUD prototype")
    check(bytes(new_root["data"])[ROOT_SHARED_OFFSET:ROOT_SHARED_OFFSET + 16] == SHARED_COMPASS_ID,
          "Raven HUD root no longer shares goProtocompassicons")
    check(count_bytes(new_proto["data"], NEW_MODEL_ID) == 1,
          "Raven HUD prototype does not point to Raven HUD model exactly once")
    check(count_bytes(new_model["data"], RAVEN_MATERIAL_ID) == 1,
          "Raven HUD model does not point to Raven material exactly once")
    check(count_bytes(new_model["data"], SOURCE_MESH_ID) == 1,
          "Raven HUD model does not retain Dock mesh exactly once")

    payloads = helper.payload_records(reparsed)
    heap, root = payloads[0], payloads[1]
    check(struct.unpack_from("<I", heap["data"], 4)[0] == 16804, "candidate heap total wrong")
    check(struct.unpack_from("<I", root["data"], 0x1C)[0] == 16804, "candidate root total wrong")
    rows = helper.read_type_table(root["data"])
    by_key = {int(row["key"]): row for row in rows}
    check(int(by_key[0x10001]["count"]) == 1726, "candidate 0x10001 count wrong")
    check(int(by_key[0x20001]["count"]) == 2074, "candidate 0x20001 count wrong")
    count_10001 = sum(1 for r in payloads if len(r["data"]) >= 4 and
                      struct.unpack_from("<I", r["data"], 0)[0] == 0x10001)
    count_20001 = sum(1 for r in payloads if len(r["data"]) >= 4 and
                      struct.unpack_from("<I", r["data"], 0)[0] == 0x20001)
    check(count_10001 == int(by_key[0x10001]["count"]), "candidate 0x10001 population/count mismatch")
    check(count_20001 == int(by_key[0x20001]["count"]), "candidate 0x20001 population/count mismatch")
    model_key = struct.unpack_from("<I", new_model["data"], 0)[0]
    check(model_key == 0x1002000C and model_key not in by_key,
          "Raven HUD model unexpectedly participates in root type table")

    stripped, group_sizes = remove_new_group_spans(helper, reparsed)
    check(len(stripped) == len(original), "removing three clone groups did not restore original record count")
    normalise_accounting_for_compare(helper, original, stripped)
    for index, (before, after) in enumerate(zip(original, stripped)):
        check(helper.record_bytes(before) == helper.record_bytes(after),
              f"original record changed outside allowed accounting bytes: index={index} name={before['name']}")

    return candidate, {
        "result": RESULT,
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
        "clone_group_record_counts": group_sizes,
        "raven_hud": {
            "IconName_source_string": "goCompletionistRavenHUD",
            "root": {"name": NEW_ROOT, "id": NEW_ROOT_ID.hex(), "prototype": NEW_PROTO,
                     "shared_compass": SHARED_COMPASS},
            "prototype": {"name": NEW_PROTO, "id": NEW_PROTO_ID.hex(), "model": NEW_MODEL},
            "model": {"name": NEW_MODEL, "id": NEW_MODEL_ID.hex(),
                      "material": RAVEN_MATERIAL, "mesh": SOURCE_MESH},
        },
        "proof": {
            "candidate_round_trip_byte_exact": True,
            "three_new_payloads_only": True,
            "root_type_accounting_delta_exactly_two": True,
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
    print(f"  candidate:             {output_wad}")
    print(f"  candidate sha256:      {report['candidate_wad_sha256']}")
    print(f"  physical payload delta:+{report['physical_payload_delta']}")
    print(f"  WAD_R_UI accounting:   +{report['accounting_delta']}")
    print(f"  report:                {report_path}")
    print("  game files written:    false")


if __name__ == "__main__":
    main()
