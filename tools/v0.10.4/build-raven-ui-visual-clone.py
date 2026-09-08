"""Build a complete Raven-only map UI visual chain offline.

Historical experiment only. Grown WAD failed runtime proof. Header rename does
not fix the retained Dock payload name or prove WAD bookkeeping. Do not install
its output. See map-class-registry findings.

Clones only the stock Dock dependencies that must become Raven-specific:
two texture definition/GPU pairs, the Dock artwork material, model, prototype
group and final instance. Geometry, animation, generic shaders and unrelated
material slots remain shared with stock. A dedicated WAD_R_UI GOPool row is
added through the already-validated logical-clone DCB builder.

No God of War files are written. The candidate WAD/DCB and a JSON validation
report are written outside the game directory. The matching Raven texpack is
built by the PowerShell wrapper after this structural build passes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"

RAVEN_DCB_NAME = "goMapIconCompletionistRaven"
RAVEN_WAD_NAME = "gomapiconcompletionistraven"
RAVEN_FINAL_ID = bytes.fromhex("3d8f7153809e6db191c2d5e354f1e88c")

RAVEN_PROTO_NAME = "goProtoMapIconCompletionistRaven"
RAVEN_PROTO_ID = bytes.fromhex("f29a83d61d2fe0b9bb96123ffe77225d")
RAVEN_MODEL_NAME = "MDL_completionistraven"
RAVEN_MODEL_ID = bytes.fromhex("e281a8d67849d97b3d5e7d88f140f59b")
RAVEN_MATERIAL_NAME = "MAT_AE4AD85BB993F040"
RAVEN_MATERIAL_ID = bytes.fromhex("dac6009fd0f18caad2ed322463c3d0c8")

RAVEN_MATERIAL_Q10 = 0x1B0989158D4A2908
STOCK_DOCK_MATERIAL_Q20 = 0xD595197B0961F689

RAVEN_DIFFUSE_HASH = 0x19A41F00834C19F3
RAVEN_EMISSIVE_HASH = 0x63F1E18FF93B9037
RAVEN_DIFFUSE_USER = 0x7ABBBA793C03C741
RAVEN_EMISSIVE_USER = 0x15AD16D2A17DEB42
RAVEN_DIFFUSE_NAME = f"TX_completionist_raven_map_diffuse_{RAVEN_DIFFUSE_HASH:016X}"
RAVEN_EMISSIVE_NAME = f"TX_completionist_raven_map_emissive_{RAVEN_EMISSIVE_HASH:016X}"

STOCK_DIFFUSE_NAME = "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC"
STOCK_EMISSIVE_NAME = "TX_mapmarker_docklocation_emissive_FCC664130951154C"
STOCK_MATERIAL_NAME = "MAT_0C599DC8DC7E2170"
STOCK_MODEL_NAME = "MDL_mapicondock"
STOCK_PROTO_NAME = "goProtoMapIconDock"
STOCK_FINAL_NAME = "gomapicondock"
STOCK_PARENT_NAME = "goProtoNW633B8059"

SOURCE_PAYLOADS = {
    "emissive_gpu": 2961,
    "emissive_def": 2962,
    "diffuse_gpu": 2963,
    "diffuse_def": 2964,
    "material": 13699,
    "model": 13908,
    "prototype": 13910,
    "script_map": 13911,
    "script_sphere": 13912,
    "script_flourish": 13913,
    "final": 13914,
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def load_logical():
    path = Path(__file__).with_name("build-raven-ui-logical-clone.py")
    spec = importlib.util.spec_from_file_location("completionist_logical_clone", path)
    check(spec is not None and spec.loader is not None, "could not load logical-clone helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def texture_def_id(file_hash: int) -> bytes:
    return bytes.fromhex("5458455400455255") + struct.pack("<II", file_hash >> 32, file_hash & 0xFFFFFFFF)


def texture_gpu_id(user_hash: int) -> bytes:
    return bytes(8) + struct.pack("<II", user_hash >> 32, user_hash & 0xFFFFFFFF)


def set_name(record: dict, name: str) -> None:
    record["name"] = name
    record["original_offset"] = None


def replace_all(blob: bytearray, old: bytes, new: bytes) -> int:
    check(len(old) == len(new) and old, "replace_all requires equal non-empty byte strings")
    count = 0
    start = 0
    while True:
        at = bytes(blob).find(old, start)
        if at < 0:
            return count
        blob[at:at + len(old)] = new
        count += 1
        start = at + len(new)


def identity_index(records: list[dict], target: dict) -> int:
    for i, record in enumerate(records):
        if record is target:
            return i
    raise ValueError("record object is no longer present in WAD list")


def payload_by_index(records: list[dict], index: int) -> dict:
    rows = [r for r in records if r["payload_index"] == index]
    check(len(rows) == 1, f"expected one payload index {index}, found {len(rows)}")
    return rows[0]


def group_span(logical, records: list[dict], payload: dict) -> list[dict]:
    parent = payload["parent"]
    check(parent is not None, f"{payload['name']} has no containing group")
    end = logical.matching_group_end(records, parent)
    return records[parent:end + 1]


def clone_group(group: list[dict]) -> list[dict]:
    cloned = copy.deepcopy(group)
    for r in cloned:
        r["original_offset"] = None
        r["payload_index"] = None
    return cloned


def clone_texture_pair(gpu: dict, definition: dict, *, new_name: str,
                       file_hash: int, user_hash: int) -> tuple[list[dict], dict]:
    check(gpu["kind"] == 0x1D and gpu["flags"] == 0x80A1, f"unexpected GPU texture record: {gpu['name']}")
    check(definition["kind"] == 1 and definition["flags"] == 0x8021 and len(definition["data"]) == 356,
          f"unexpected texture definition: {definition['name']}")
    check(gpu["name"] == definition["name"], "texture GPU/definition names differ")

    old_user = struct.unpack_from("<Q", definition["data"], 0x9C)[0]
    expected_old_gpu_id = texture_gpu_id(old_user)
    check(gpu["id"] == expected_old_gpu_id, "stock texture GPU id/user hash relation changed")
    old_user_le = struct.pack("<Q", old_user)
    def_occ = bytes(definition["data"]).count(old_user_le)
    gpu_occ = bytes(gpu["data"]).count(old_user_le)
    check(def_occ == 1 and bytes(definition["data"])[0x9C:0xA4] == old_user_le,
          f"unexpected stock user-hash layout for {definition['name']}")

    new_gpu = copy.deepcopy(gpu)
    new_def = copy.deepcopy(definition)
    for r in (new_gpu, new_def):
        set_name(r, new_name)
        r["payload_index"] = None

    new_def["id"] = texture_def_id(file_hash)
    new_gpu["id"] = texture_gpu_id(user_hash)
    struct.pack_into("<Q", new_def["data"], 0x9C, user_hash)
    gpu_replacements = replace_all(new_gpu["data"], old_user_le, struct.pack("<Q", user_hash))

    return [new_gpu, new_def], {
        "stock_name": definition["name"],
        "new_name": new_name,
        "file_hash": f"{file_hash:016X}",
        "user_hash": f"{user_hash:016X}",
        "definition_id": new_def["id"].hex(),
        "gpu_id": new_gpu["id"].hex(),
        "stock_user_hash": f"{old_user:016X}",
        "definition_user_hash_occurrences": def_occ,
        "gpu_user_hash_occurrences_replaced": gpu_replacements,
        "definition_bytes": len(new_def["data"]),
        "gpu_bytes": len(new_gpu["data"]),
    }


def rename_matching_group_boundaries(group: list[dict], old_name: str, new_name: str) -> None:
    for r in group:
        if r["kind"] in (2, 3) and r["name"].lower() == old_name.lower():
            set_name(r, new_name)


def build_wad(raw: bytes, logical) -> tuple[bytes, dict]:
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "stock r_ui.wad byte round-trip failed")
    stock_physical = len(records)
    stock_payload_count = len(logical.payload_records(records))
    check((stock_physical, stock_payload_count) == (53777, 20407), "unexpected stock WAD counts")

    reserved_ids = [
        RAVEN_FINAL_ID, RAVEN_PROTO_ID, RAVEN_MODEL_ID, RAVEN_MATERIAL_ID,
        texture_def_id(RAVEN_DIFFUSE_HASH), texture_def_id(RAVEN_EMISSIVE_HASH),
        texture_gpu_id(RAVEN_DIFFUSE_USER), texture_gpu_id(RAVEN_EMISSIVE_USER),
    ]
    for rid in reserved_ids:
        check(not any(r["id"] == rid for r in records), f"reserved resource id collision: {rid.hex()}")
    reserved_names = {
        RAVEN_WAD_NAME.lower(), RAVEN_PROTO_NAME.lower(), RAVEN_MODEL_NAME.lower(),
        RAVEN_MATERIAL_NAME.lower(), RAVEN_DIFFUSE_NAME.lower(), RAVEN_EMISSIVE_NAME.lower(),
    }
    check(not any(r["name"].lower() in reserved_names for r in records), "reserved Raven resource name collision")

    sources = {label: payload_by_index(records, idx) for label, idx in SOURCE_PAYLOADS.items()}
    check(sources["emissive_def"]["name"] == STOCK_EMISSIVE_NAME, "stock emissive source changed")
    check(sources["diffuse_def"]["name"] == STOCK_DIFFUSE_NAME, "stock diffuse source changed")
    check(sources["material"]["name"] == STOCK_MATERIAL_NAME, "stock material source changed")
    check(sources["model"]["name"] == STOCK_MODEL_NAME, "stock model source changed")
    check(sources["prototype"]["name"] == STOCK_PROTO_NAME, "stock prototype source changed")
    check(sources["final"]["name"] == STOCK_FINAL_NAME, "stock final source changed")

    stock_resource_bytes = {
        k: logical.record_bytes(v)
        for k, v in sources.items()
        if k in {"emissive_gpu", "emissive_def", "diffuse_gpu", "diffuse_def",
                 "material", "model", "prototype", "final"}
    }

    emissive_clone, emissive_report = clone_texture_pair(
        sources["emissive_gpu"], sources["emissive_def"],
        new_name=RAVEN_EMISSIVE_NAME, file_hash=RAVEN_EMISSIVE_HASH, user_hash=RAVEN_EMISSIVE_USER)
    diffuse_clone, diffuse_report = clone_texture_pair(
        sources["diffuse_gpu"], sources["diffuse_def"],
        new_name=RAVEN_DIFFUSE_NAME, file_hash=RAVEN_DIFFUSE_HASH, user_hash=RAVEN_DIFFUSE_USER)

    material_group = clone_group(group_span(logical, records, sources["material"]))
    rename_matching_group_boundaries(material_group, STOCK_MATERIAL_NAME, RAVEN_MATERIAL_NAME)
    mat_defs = [r for r in material_group if len(r["data"]) and r["name"] == STOCK_MATERIAL_NAME]
    check(len(mat_defs) == 1, "Raven material clone definition missing")
    raven_material = mat_defs[0]
    set_name(raven_material, RAVEN_MATERIAL_NAME)
    raven_material["id"] = RAVEN_MATERIAL_ID
    check(struct.unpack_from("<Q", raven_material["data"], 0x20)[0] == STOCK_DOCK_MATERIAL_Q20,
          "Dock material +0x20 changed before clone")
    struct.pack_into("<Q", raven_material["data"], 0x10, RAVEN_MATERIAL_Q10)
    struct.pack_into("<Q", raven_material["data"], 0x20, STOCK_DOCK_MATERIAL_Q20)

    material_texture_swaps = 0
    for r in material_group:
        if not r["data"] and r["kind"] == 1 and r["name"] == STOCK_DIFFUSE_NAME:
            set_name(r, RAVEN_DIFFUSE_NAME)
            r["id"] = texture_def_id(RAVEN_DIFFUSE_HASH)
            material_texture_swaps += 1
        elif not r["data"] and r["kind"] == 1 and r["name"] == STOCK_EMISSIVE_NAME:
            set_name(r, RAVEN_EMISSIVE_NAME)
            r["id"] = texture_def_id(RAVEN_EMISSIVE_HASH)
            material_texture_swaps += 1
    check(material_texture_swaps == 2, "Raven material did not retarget exactly diffuse and emissive")

    model_group = clone_group(group_span(logical, records, sources["model"]))
    rename_matching_group_boundaries(model_group, STOCK_MODEL_NAME, RAVEN_MODEL_NAME)
    model_defs = [r for r in model_group if len(r["data"]) and r["name"] == STOCK_MODEL_NAME]
    check(len(model_defs) == 1, "Raven model clone definition missing")
    raven_model = model_defs[0]
    set_name(raven_model, RAVEN_MODEL_NAME)
    raven_model["id"] = RAVEN_MODEL_ID
    model_material_swaps = 0
    for r in model_group:
        if not r["data"] and r["kind"] == 1 and r["name"] == STOCK_MATERIAL_NAME:
            set_name(r, RAVEN_MATERIAL_NAME)
            r["id"] = RAVEN_MATERIAL_ID
            model_material_swaps += 1
    check(model_material_swaps == 1, "Raven model did not retarget exactly one Dock artwork material")

    proto_group = clone_group(group_span(logical, records, sources["prototype"]))
    rename_matching_group_boundaries(proto_group, STOCK_PROTO_NAME, RAVEN_PROTO_NAME)
    proto_defs = [r for r in proto_group if len(r["data"]) and r["name"] == STOCK_PROTO_NAME]
    check(len(proto_defs) == 1, "Raven prototype clone definition missing")
    raven_proto = proto_defs[0]
    old_proto_id = bytes(sources["prototype"]["id"])
    set_name(raven_proto, RAVEN_PROTO_NAME)
    raven_proto["id"] = RAVEN_PROTO_ID
    proto_id_replacements = replace_all(raven_proto["data"], old_proto_id, RAVEN_PROTO_ID)
    check(proto_id_replacements >= 1, "prototype payload did not contain its root resource id")

    node_count = struct.unpack_from("<H", raven_proto["data"], 0xC)[0]
    id_table = struct.unpack_from("<I", raven_proto["data"], 0x18)[0]
    name_table = id_table - node_count * 56
    check(node_count == 4, f"unexpected Dock prototype node count: {node_count}")
    stock_node_names = []
    for i in range(node_count):
        start = name_table + 56 * i
        stock_node_names.append(bytes(raven_proto["data"][start:start + 56]).split(b"\0", 1)[0].decode("ascii"))
    check(stock_node_names[0] == "MapIconDock", "Dock prototype root node changed")

    proto_model_swaps = 0
    script_refs = 0
    script_names = {"SCP_MapIconDock", "SCP_CollidableSphere9", "SCP_flourishD1"}
    for r in proto_group:
        if not r["data"] and r["kind"] == 1 and r["name"] == STOCK_MODEL_NAME:
            set_name(r, RAVEN_MODEL_NAME)
            r["id"] = RAVEN_MODEL_ID
            proto_model_swaps += 1
        elif r["data"] and r["kind"] == 1 and r["name"] in script_names:
            # The stock map-icon scripts are generic payloads and already exist
            # as definitions in the stock WAD. Reference those definitions rather
            # than duplicating script payloads across the WAD type-table boundary.
            r["data"] = bytearray()
            r["flags"] = 0
            r["padding"] = bytes()
            r["payload_index"] = None
            script_refs += 1
    check(proto_model_swaps == 1, "Raven prototype did not retarget exactly one model link")
    check(script_refs == 3, "Raven prototype did not convert exactly three stock scripts to references")

    final_group = clone_group(group_span(logical, records, sources["final"]))
    rename_matching_group_boundaries(final_group, STOCK_FINAL_NAME, RAVEN_WAD_NAME)
    final_defs = [r for r in final_group if len(r["data"]) and r["name"] == STOCK_FINAL_NAME]
    check(len(final_defs) == 1, "Raven final clone definition missing")
    raven_final = final_defs[0]
    set_name(raven_final, RAVEN_WAD_NAME)
    raven_final["id"] = RAVEN_FINAL_ID
    check(bytes(raven_final["data"])[0x0C:0x1C] == old_proto_id, "Dock final prototype field changed")
    raven_final["data"][0x0C:0x1C] = RAVEN_PROTO_ID

    parent_def = logical.one_record(records, name=STOCK_PARENT_NAME, has_data=True)
    parent_start = parent_def["parent"]
    check(parent_start is not None, "map-icons parent group missing")
    parent_end_index = logical.matching_group_end(records, parent_start)
    parent_end_obj = records[parent_end_index]
    parent_links = [
        r for r in records[parent_start:parent_end_index + 1]
        if not r["data"] and r["kind"] == 1 and r["name"] == STOCK_FINAL_NAME
    ]
    check(len(parent_links) == 1, "stock Dock parent link missing")
    raven_parent_link = copy.deepcopy(parent_links[0])
    set_name(raven_parent_link, RAVEN_WAD_NAME)
    raven_parent_link["id"] = RAVEN_FINAL_ID
    raven_parent_link["payload_index"] = None

    # Type-table accounting: each cloned payload is inserted beside a source
    # payload already belonging to the correct WAD type block.
    heap = logical.payload_records(records)[0]
    root = logical.payload_records(records)[1]
    stock_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(stock_total == 0x419C == struct.unpack_from("<I", root["data"], 0x1C)[0],
          "unexpected WAD payload total")
    type_rows = logical.read_type_table(root["data"])
    source_clone_payload_indices = [
        SOURCE_PAYLOADS["emissive_gpu"], SOURCE_PAYLOADS["emissive_def"],
        SOURCE_PAYLOADS["diffuse_gpu"], SOURCE_PAYLOADS["diffuse_def"],
        SOURCE_PAYLOADS["material"], SOURCE_PAYLOADS["model"],
        SOURCE_PAYLOADS["prototype"], SOURCE_PAYLOADS["final"],
    ]
    increments: dict[int, int] = {}
    for source_index in source_clone_payload_indices:
        matches = [row for row in type_rows if row["base"] <= source_index < row["base"] + row["count"]]
        check(len(matches) == 1, f"could not map payload {source_index} to a type row")
        increments[matches[0]["index"]] = increments.get(matches[0]["index"], 0) + 1

    new_base = 0
    expected_type_counts = {}
    for row in type_rows:
        amount = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, amount)
        expected_type_counts[row["key"]] = amount
        new_base += amount
    clone_payload_delta = len(source_clone_payload_indices)
    check(new_base == stock_total + clone_payload_delta, "new WAD total mismatch")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    # Insert clones after their source scopes from highest physical position to
    # lowest so references to original record objects remain stable.
    insertion_jobs = []

    def add_job(after_obj: dict, new_records: list[dict]) -> None:
        insertion_jobs.append((identity_index(records, after_obj), after_obj, new_records))

    add_job(sources["emissive_gpu"], [emissive_clone[0]])
    add_job(sources["emissive_def"], [emissive_clone[1]])
    add_job(sources["diffuse_gpu"], [diffuse_clone[0]])
    add_job(sources["diffuse_def"], [diffuse_clone[1]])
    for src_key, cloned in [
        ("material", material_group), ("model", model_group), ("final", final_group),
    ]:
        src_group = group_span(logical, records, sources[src_key])
        add_job(src_group[-1], cloned)

    # The stock Dock prototype group itself straddles a WAD type-table boundary
    # because two inline scripts belong to the following type block. The Raven
    # clone references those existing generic scripts instead, so it has only one
    # payload and can be inserted before the stock prototype group while staying
    # inside the prototype payload's original type block.
    stock_proto_group = group_span(logical, records, sources["prototype"])
    proto_group_start_obj = stock_proto_group[0]

    for _, after_obj, new_records in sorted(insertion_jobs, key=lambda x: x[0], reverse=True):
        at = identity_index(records, after_obj) + 1
        records[at:at] = new_records

    proto_insert_at = identity_index(records, proto_group_start_obj)
    records[proto_insert_at:proto_insert_at] = proto_group

    # Parent group end moved, but the original end record object is still present.
    parent_end_now = identity_index(records, parent_end_obj)
    records.insert(parent_end_now, raven_parent_link)

    candidate = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate)
    payloads = logical.payload_records(reparsed)
    check(len(reparsed) > stock_physical, "candidate physical record count did not grow")
    check(len(payloads) == stock_payload_count + clone_payload_delta,
          "candidate payload delta is wrong")

    # Reparse and validate the complete dependency chain.
    raven_final_defs = [r for r in reparsed if r["name"].lower() == RAVEN_WAD_NAME.lower() and r["data"]]
    raven_proto_defs = [r for r in reparsed if r["name"].lower() == RAVEN_PROTO_NAME.lower() and r["data"]]
    raven_model_defs = [r for r in reparsed if r["name"].lower() == RAVEN_MODEL_NAME.lower() and r["data"]]
    raven_mat_defs = [r for r in reparsed if r["name"].lower() == RAVEN_MATERIAL_NAME.lower() and r["data"]]
    check(len(raven_final_defs) == len(raven_proto_defs) == len(raven_model_defs) == len(raven_mat_defs) == 1,
          "Raven visual-chain definitions did not reparse uniquely")

    def child_group(payload: dict) -> list[dict]:
        parent = payload["parent"]
        check(parent is not None, f"{payload['name']} has no reparsed group")
        end = logical.matching_group_end(reparsed, parent)
        return reparsed[parent:end + 1]

    final_group_r = child_group(raven_final_defs[0])
    proto_group_r = child_group(raven_proto_defs[0])
    model_group_r = child_group(raven_model_defs[0])
    mat_group_r = child_group(raven_mat_defs[0])

    check(bytes(raven_final_defs[0]["data"])[0x0C:0x1C] == RAVEN_PROTO_ID,
          "Raven final no longer points to Raven prototype")
    check(any((not r["data"] and r["kind"] == 1 and r["name"] == RAVEN_MODEL_NAME
               and r["id"] == RAVEN_MODEL_ID) for r in proto_group_r),
          "Raven prototype group lost Raven model reference")
    stock_script_ref_names = {"SCP_MapIconDock", "SCP_CollidableSphere9", "SCP_flourishD1"}
    reparsed_script_refs = [
        r for r in proto_group_r
        if not r["data"] and r["kind"] == 1 and r["name"] in stock_script_ref_names
    ]
    check(len(reparsed_script_refs) == 3, "Raven prototype script references did not reparse")
    check(any((not r["data"] and r["kind"] == 1 and r["name"] == RAVEN_MATERIAL_NAME
               and r["id"] == RAVEN_MATERIAL_ID) for r in model_group_r),
          "Raven model group lost Raven material reference")
    check(any((not r["data"] and r["kind"] == 1 and r["name"] == RAVEN_DIFFUSE_NAME
               and r["id"] == texture_def_id(RAVEN_DIFFUSE_HASH)) for r in mat_group_r),
          "Raven material group lost Raven diffuse reference")
    check(any((not r["data"] and r["kind"] == 1 and r["name"] == RAVEN_EMISSIVE_NAME
               and r["id"] == texture_def_id(RAVEN_EMISSIVE_HASH)) for r in mat_group_r),
          "Raven material group lost Raven emissive reference")
    check(struct.unpack_from("<Q", raven_mat_defs[0]["data"], 0x10)[0] == RAVEN_MATERIAL_Q10,
          "Raven material +0x10 changed")
    check(struct.unpack_from("<Q", raven_mat_defs[0]["data"], 0x20)[0] == STOCK_DOCK_MATERIAL_Q20,
          "Raven material did not preserve Dock +0x20")

    new_diff_defs = [r for r in reparsed if r["name"] == RAVEN_DIFFUSE_NAME and r["flags"] == 0x8021 and r["data"]]
    new_emis_defs = [r for r in reparsed if r["name"] == RAVEN_EMISSIVE_NAME and r["flags"] == 0x8021 and r["data"]]
    check(len(new_diff_defs) == len(new_emis_defs) == 1, "Raven texture definitions did not reparse uniquely")

    candidate_heap, candidate_root = payloads[0], payloads[1]
    check(struct.unpack_from("<I", candidate_heap["data"], 4)[0] == stock_total + clone_payload_delta,
          "candidate heap total wrong")
    candidate_rows = logical.read_type_table(candidate_root["data"])
    for row in candidate_rows:
        check(row["count"] == expected_type_counts[row["key"]],
              f"type-table count mismatch for key {row['key']:#x}")

    # Ensure selected stock source records stayed byte-identical. The WAD root and
    # heap accounting payloads are intentionally the only stock payloads edited.
    for key, before in stock_resource_bytes.items():
        source = sources[key]
        check(logical.record_bytes(source) == before, f"stock source mutated: {key}")

    return candidate, {
        "stock_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "stock_physical_records": stock_physical,
        "candidate_physical_records": len(reparsed),
        "stock_payloads": stock_payload_count,
        "candidate_payloads": len(payloads),
        "payload_delta": clone_payload_delta,
        "type_row_increments": [
            {
                "type_key": f"0x{type_rows[i]['key']:X}",
                "added_payloads": amount,
                "count_before": type_rows[i]["count"],
                "count_after": type_rows[i]["count"] + amount,
            }
            for i, amount in sorted(increments.items())
        ],
        "textures": {"diffuse": diffuse_report, "emissive": emissive_report},
        "material": {
            "name": RAVEN_MATERIAL_NAME,
            "id": RAVEN_MATERIAL_ID.hex(),
            "qword_0x10": f"{RAVEN_MATERIAL_Q10:016X}",
            "qword_0x20_preserved_from_Dock": f"{STOCK_DOCK_MATERIAL_Q20:016X}",
            "diffuse_emissive_links_retargeted": material_texture_swaps,
        },
        "model": {
            "name": RAVEN_MODEL_NAME,
            "id": RAVEN_MODEL_ID.hex(),
            "Raven_material_links": model_material_swaps,
            "stock_geometry_shared": True,
        },
        "prototype": {
            "name": RAVEN_PROTO_NAME,
            "id": RAVEN_PROTO_ID.hex(),
            "root_id_replacements": proto_id_replacements,
            "Raven_model_links": proto_model_swaps,
            "stock_animation_shared": True,
            "stock_script_definitions_referenced": script_refs,
            "node_names_preserved": stock_node_names,
        },
        "final": {
            "name": RAVEN_WAD_NAME,
            "id": RAVEN_FINAL_ID.hex(),
            "prototype_id": RAVEN_PROTO_ID.hex(),
        },
        "stock_selected_resources_byte_identical": True,
        "full_reparse_passed": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--work-dir", type=Path,
                    default=Path(os.environ.get("LOCALAPPDATA", ".")) / "CompletionistMap/work/v0.10.4/raven-ui-visual-clone")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    work = args.work_dir.resolve()
    output = args.output.resolve()
    check(not work.is_relative_to(game), "work directory must stay outside game tree")
    check(not output.is_relative_to(game), "report must stay outside game tree")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    wad_raw = wad_path.read_bytes()
    dcb_raw = dcb_path.read_bytes()
    check(digest(wad_raw) == EXPECTED_WAD, "r_ui.wad is not the researched stock file")
    check(digest(dcb_raw) == EXPECTED_DCB, "wad_r_ui.dcb is not the researched stock file")

    logical = load_logical()
    wad_candidate, wad_report = build_wad(wad_raw, logical)
    dcb_candidate, dcb_report = logical.build_dcb(dcb_raw)

    work.mkdir(parents=True, exist_ok=True)
    wad_out = work / "r_ui.wad"
    dcb_out = work / "wad_r_ui.dcb"
    wad_out.write_bytes(wad_candidate)
    dcb_out.write_bytes(dcb_candidate)

    check(wad_path.read_bytes() == wad_raw and dcb_path.read_bytes() == dcb_raw,
          "source game files changed during build")

    report = {
        "result": "OFFLINE_RAVEN_UI_VISUAL_CLONE_BUILT",
        "game_files_written": False,
        "source_hashes_unchanged_after_build": True,
        "architecture": {
            "map_ui_identity": RAVEN_DCB_NAME,
            "final_instance": RAVEN_WAD_NAME,
            "dedicated_prototype": RAVEN_PROTO_NAME,
            "dedicated_model": RAVEN_MODEL_NAME,
            "dedicated_material": RAVEN_MATERIAL_NAME,
            "dedicated_diffuse": RAVEN_DIFFUSE_NAME,
            "dedicated_emissive": RAVEN_EMISSIVE_NAME,
            "shares_stock_Dock_geometry": True,
            "shares_stock_Dock_animation": True,
            "shares_stock_Dock_generic_shader_links": True,
            "real_Dock_visual_resources_modified": False,
            "native_compass_navigation_type": "DockPoint remains internal and unchanged",
        },
        "candidate": {
            "directory": str(work),
            "r_ui_wad": {"path": str(wad_out), "bytes": len(wad_candidate), "sha256": digest(wad_candidate)},
            "wad_r_ui_dcb": {"path": str(dcb_out), "bytes": len(dcb_candidate), "sha256": digest(dcb_candidate)},
        },
        "texpack_contract": {
            "diffuse_filename": RAVEN_DIFFUSE_NAME + ".dds",
            "diffuse_file_hash": f"{RAVEN_DIFFUSE_HASH:016X}",
            "emissive_filename": RAVEN_EMISSIVE_NAME + ".dds",
            "emissive_file_hash": f"{RAVEN_EMISSIVE_HASH:016X}",
            "status": "PowerShell wrapper must build and validate matching offline texpack",
        },
        "wad_validation": wad_report,
        "dcb_validation": dcb_report,
        "safety": {
            "save_state_written": False,
            "progression_state_written": False,
            "boot_options_written": False,
            "game_directory_written": False,
            "stock_Dock_material_or_texture_changed": False,
            "native_Kratos_marker_touched": False,
        },
        "next_gate": (
            "Build the matching Raven texpack offline. If WAD/DCB and texpack all validate, "
            "prepare a reversible runtime install proof that loads the dedicated "
            "goMapIconCompletionistRaven resource without globally changing DockPoint artwork."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Built offline WAD: {wad_out}")
    print(f"Built offline DCB: {dcb_out}")
    print(f"Saved validation: {output}")
    print("Raven-only visual chain built. Stock Dock visual resources remain unchanged.")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
