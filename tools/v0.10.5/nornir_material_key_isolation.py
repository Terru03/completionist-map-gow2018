"""Replace adjacent Nornir material keys with independent name hashes."""
from __future__ import annotations

import copy
import struct

import nornir_model_group_isolation as groups


FAMILIES = ("Chest", "Seal", "Bell", "Mechanism")
RAVEN_MATERIAL = "MAT_AE4AD85BB993F040"


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def material_rows(records: list[dict]) -> list[dict]:
    return [row for row in records if row["kind"] == 1 and row["data"] and
            row["name"].startswith("MAT_") and len(row["data"]) >= 0x28]


def qword(row: dict, offset: int) -> int:
    return struct.unpack_from("<Q", row["data"], offset)[0]


def isolate(stage, raven_wad: bytes, node_isolated_wad: bytes) -> tuple[bytes, dict]:
    logical = groups.logical_module(stage)
    raven = logical.parse_wad(raven_wad)
    source = logical.parse_wad(node_isolated_wad)
    need(logical.serialize_wad(source) == node_isolated_wad,
         "node-isolated WAD does not roundtrip")
    _, raven_material = groups.one_payload(raven, RAVEN_MATERIAL)
    _, source_raven = groups.one_payload(source, RAVEN_MATERIAL)
    need(logical.record_bytes(raven_material) == logical.record_bytes(source_raven),
         "Raven material changed in Nornir source")
    raven_key = qword(raven_material, 0x10)
    shader_key = qword(raven_material, 0x20)

    records = copy.deepcopy(source)
    all_materials = material_rows(records)
    old_keys = {qword(row, 0x10) for row in all_materials}
    old_shader_keys = {qword(row, 0x20) for row in all_materials}
    need(len(old_keys) == len(all_materials), "source material keys already duplicate")
    changes = []
    for index, family in enumerate(FAMILIES):
        name = "MAT_cm_nornir_" + family.lower()
        _, row = groups.one_payload(records, name)
        old_key = qword(row, 0x10)
        need(old_key == raven_key + index + 1 and qword(row, 0x20) == shader_key,
             f"unexpected existing material keys: {name}")
        new_key = stage.folded_name_hash(
            "CompletionistNornir" + family + "MaterialIdentity0")
        need(new_key not in old_keys and new_key not in old_shader_keys and
             all(new_key >> 8 != key >> 8 for key in old_keys),
             f"new material key aliases an existing material: {name}")
        struct.pack_into("<Q", row["data"], 0x10, new_key)
        changes.append((name, old_key, new_key))

    candidate = logical.serialize_wad(records)
    need(len(candidate) == len(node_isolated_wad) and candidate != node_isolated_wad,
         "material key edit changed WAD shape or made no change")
    parsed = logical.parse_wad(candidate)
    need(logical.serialize_wad(parsed) == candidate, "material key WAD roundtrip failed")
    keys = [qword(row, 0x10) for row in material_rows(parsed)]
    need(len(keys) == len(set(keys)) and len(keys) == len(all_materials) and
         len({key >> 8 for key in keys}) == len(keys),
         "material key or low-byte cohort collision remains")
    _, final_raven = groups.one_payload(parsed, RAVEN_MATERIAL)
    need(logical.record_bytes(final_raven) == logical.record_bytes(raven_material),
         "Raven material changed")
    for name, old_key, new_key in changes:
        _, row = groups.one_payload(parsed, name)
        need(qword(row, 0x10) == new_key and qword(row, 0x20) == shader_key,
             f"material key or donor shader differs: {name}")
        struct.pack_into("<Q", row["data"], 0x10, old_key)
    need(logical.serialize_wad(parsed) == node_isolated_wad,
         "material key replacement has no exact inverse")
    return candidate, {
        "four_independent_name_hashes": True,
        "no_low_byte_cohort_collision": True,
        "raven_material_byte_identical": True,
        "donor_shader_key_preserved": f"{shader_key:016X}",
        "same_wad_length": True,
        "exact_inverse_to_node_isolated_candidate": True,
        "material_keys": {name: {"before": f"{old:016X}", "after": f"{new:016X}"}
                          for name, old, new in changes},
    }
