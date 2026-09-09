#!/usr/bin/env python3
"""Build the Nornir Chest map/HUD WAD + GOPool candidate entirely offline.

The frozen runtime-proven Raven production resources are the only visual/runtime
resource donors. The builder clones them under collision-free Nornir identities,
injects the already-proven Nornir resident artwork, and appends the planned map
and HUD GOPool rows. Every original WAD record and every existing GOPool row is
proved recoverable byte-for-byte by normalization. No God of War file is
modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = "OFFLINE_NORNIR_MAP_HUD_BUILT"

EXPECTED_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
EXPECTED_UI_DCB = "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d"
EXPECTED_ART_REPORT = "OFFLINE_NORNIR_RESIDENT_ART_BUILT"
EXPECTED_TEXPACK = "f01a3b935e8b54ae5774004b7d77a01312f7304ef31f3237f4e41b1a523fef9d"
EXPECTED_RESIDENT = {
    "diffuse": (9228, "4912eca29c970d137f584f75627b2cfe30f3681652bec7762f96ff7e0e86e9e4"),
    "emissive": (4620, "ab37213e0c654b5ef7047d57b0b1f07f671ca1980a8528d39b8522995ba0244c"),
}

RAVEN = {
    "map_root": "gomapiconcompletionistraven",
    "map_proto": "goProtoMapIconCompletionistRaven",
    "map_model": "MDL_completionistraven",
    "material": "MAT_AE4AD85BB993F040",
    "diffuse": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
    "emissive": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
    "hud_root": "gocompletionistravenhud",
    "hud_proto": "goProtoCompletionistRavenHUD",
    "hud_model": "MDL_completionistravenhud",
}
NORNIR = {
    "map_go": "goMapIconCompletionistNornirChest",
    "map_root": "gomapiconcompletionistnornirchest",
    "map_proto": "goProtoMapIconCompletionistNornirChest",
    "map_model": "MDL_completionistnornirchest",
    "material": "MAT_completionistnornirchest",
    "diffuse": "TX_completionist_nornir_chest_map_diffuse_0A43AEB29D6F80DA",
    "emissive": "TX_completionist_nornir_chest_map_emissive_58012A499511A0BB",
    "hud_go": "goCompletionistNornirChestHUD",
    "hud_root": "gocompletionistnornirchesthud",
    "hud_proto": "goProtoCompletionistNornirChestHUD",
    "hud_model": "MDL_completionistnornirchesthud",
}
FILE_HASH = {"diffuse": 0x0A43AEB29D6F80DA, "emissive": 0x58012A499511A0BB}
MAP_GO_HASH = 0xE14C66C3B90633E0
HUD_GO_HASH = 0x7DDC11175EBD1E94
RAVEN_MAP_HASH = 0x584F31DC8BD6E738
RAVEN_HUD_HASH = 0x45E5C7943749F81C
GOP_BASE = 0x90
GOP_ROW = 16


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(filename: str, module_name: str):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def deterministic_id(name: str) -> bytes:
    seed = f"completionist-map-gow2018:v0.10.4:nornir:{name}".encode("ascii")
    return hashlib.sha256(seed).digest()[:16]


def texture_def_id(file_hash: int) -> bytes:
    return bytes.fromhex("5458455400455255") + struct.pack("<II", file_hash >> 32, file_hash & 0xFFFFFFFF)


def texture_gpu_id(user_hash: int) -> bytes:
    return bytes(8) + struct.pack("<II", user_hash >> 32, user_hash & 0xFFFFFFFF)


def set_name(row: dict, name: str) -> None:
    check(len(name.encode("ascii")) <= 55, f"resource name too long: {name}")
    row["name"] = name
    row["original_offset"] = None


def unique_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def unique_texture(records: list[dict], name: str, *, gpu: bool) -> tuple[int, dict]:
    if gpu:
        hits = [(i, row) for i, row in enumerate(records)
                if row["kind"] == 0x1D and row["flags"] == 0x80A1 and row["data"]
                and row["name"].lower() == name.lower()]
    else:
        hits = [(i, row) for i, row in enumerate(records)
                if row["kind"] == 1 and row["flags"] == 0x8021 and row["data"]
                and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one {'GPU' if gpu else 'definition'} {name!r}, found {len(hits)}")
    return hits[0]


def texture_removal_rows(records: list[dict], name: str, group_removal: set[int]) -> set[int]:
    """Find old two-row texture shape. New wrappers may tighten this hook."""
    del group_removal
    rows = {i for i, row in enumerate(records) if row["name"].lower() == name.lower()}
    check(len(rows) == 2, f"expected exactly two Nornir texture records for {name!r}")
    return rows


def group_bounds(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    payload = records[payload_index]
    start = payload["parent"]
    check(start is not None and records[start]["kind"] == 2, f"{payload['name']}: missing group start")
    return start, logical.matching_group_end(records, start)


def clone_scope(records: list[dict], start: int, end: int) -> list[dict]:
    out = copy.deepcopy(records[start:end + 1])
    for source, clone in zip(records[start:end + 1], out):
        clone["_source_payload_index"] = source["payload_index"] if source["data"] else None
        clone["original_offset"] = None
        clone["payload_index"] = None
    return out


def rename_boundaries(rows: list[dict], old: str, new: str) -> None:
    for row in rows:
        if row["kind"] in (2, 3) and row["name"].lower() == old.lower():
            set_name(row, new)


def target_in_clone(rows: list[dict], old_name: str) -> dict:
    hits = [row for row in rows if row["kind"] == 1 and row["data"]
            and row["name"].lower() == old_name.lower()]
    check(len(hits) == 1, f"clone target {old_name!r} is not unique")
    return hits[0]


def retarget_link(rows: list[dict], old_name: str, old_id: bytes, new_name: str, new_id: bytes) -> int:
    hits = [row for row in rows if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == old_name.lower() and row["id"] == old_id]
    check(len(hits) == 1, f"expected one dependency {old_name!r}, found {len(hits)}")
    set_name(hits[0], new_name)
    hits[0]["id"] = new_id
    return 1


def replace_id(blob: bytearray, old: bytes, new: bytes) -> int:
    check(len(old) == len(new) == 16, "resource ID width changed")
    count = bytes(blob).count(old)
    check(count >= 1, "source self ID is absent from cloned prototype payload")
    blob[:] = bytes(blob).replace(old, new)
    check(bytes(blob).count(old) == 0, "old self ID remained after replacement")
    return count


def clone_group(logical, records: list[dict], old_name: str, new_name: str, new_id: bytes) -> tuple[list[dict], dict, dict]:
    source_index, source = unique_payload(records, old_name)
    start, end = group_bounds(logical, records, source_index)
    rows = clone_scope(records, start, end)
    rename_boundaries(rows, old_name, new_name)
    target = target_in_clone(rows, old_name)
    set_name(target, new_name)
    target["id"] = new_id
    return rows, target, {"source_index": source_index, "start": start, "end": end, "source": source}


def clone_texture(source: dict, new_name: str, new_id: bytes, resident: bytes) -> dict:
    row = copy.deepcopy(source)
    row["_source_payload_index"] = source["payload_index"]
    row["original_offset"] = None
    row["payload_index"] = None
    set_name(row, new_name)
    row["id"] = new_id
    row["data"] = bytearray(resident)
    return row


def parse_art_report(path: Path) -> tuple[dict, dict[str, bytes], dict[str, int]]:
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    check(report.get("result") == EXPECTED_ART_REPORT, "Nornir resident-art report result changed")
    check(report.get("source_raven_wad_sha256") == EXPECTED_WAD, "resident-art source WAD changed")
    check(report.get("nornir_texpack_sha256") == EXPECTED_TEXPACK, "Nornir texpack SHA changed")
    check(report.get("ready_for_nornir_wad_clone") is True, "resident-art report is not ready for WAD clone")
    rows = {row["label"]: row for row in report.get("rows", [])}
    check(set(rows) == {"diffuse", "emissive"}, "resident-art report does not contain exactly diffuse/emissive")
    residents: dict[str, bytes] = {}
    users: dict[str, int] = {}
    for label in ("diffuse", "emissive"):
        row = rows[label]
        expected_bytes, expected_sha = EXPECTED_RESIDENT[label]
        check(row["resource_name"] == NORNIR[label], f"{label}: resource name changed")
        check(int(row["file_hash"], 16) == FILE_HASH[label], f"{label}: file hash changed")
        check(row["resident_bytes"] == expected_bytes and row["resident_sha256"] == expected_sha,
              f"{label}: resident contract changed")
        resident_path = Path(row["output"])
        check(resident_path.is_file(), f"{label}: resident payload missing: {resident_path}")
        raw = resident_path.read_bytes()
        check(len(raw) == expected_bytes and sha(raw) == expected_sha, f"{label}: resident payload bytes changed")
        user_value = row["texpack_stream"]["user_hash"]
        users[label] = int(user_value, 16) if isinstance(user_value, str) else int(user_value)
        residents[label] = raw
    check(users["diffuse"] != users["emissive"], "Nornir texture user hashes collide")
    return report, residents, users


def source_type_row(logical, records: list[dict], payload_index: int) -> dict:
    payloads = logical.payload_records(records)
    root = payloads[1]
    matches = [row for row in logical.read_type_table(root["data"])
               if row["base"] <= payload_index < row["base"] + row["count"]]
    check(len(matches) == 1, f"payload {payload_index} does not map to exactly one type row")
    return matches[0]


def apply_accounting(logical, records: list[dict], cloned_rows: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    check(len(payloads) >= 2, "WAD accounting payloads missing")
    heap, root = payloads[0], payloads[1]
    before_heap = bytes(heap["data"])
    before_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0], "WAD totals disagree")
    rows = logical.read_type_table(root["data"])
    increments: dict[int, int] = {}
    cloned_payloads = [row for row in cloned_rows if row["data"]]
    for clone in cloned_payloads:
        source_index = clone.get("_source_payload_index")
        check(isinstance(source_index, int), f"clone {clone['name']} lost source payload index")
        matches = [row for row in rows if row["base"] <= source_index < row["base"] + row["count"]]
        check(len(matches) == 1, f"clone source payload {source_index} has no unique type row")
        increments[matches[0]["index"]] = increments.get(matches[0]["index"], 0) + 1
    new_base = 0
    for row in rows:
        new_count = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, new_count)
        new_base += new_count
    check(new_base == old_total + len(cloned_payloads), "WAD accounting delta disagrees with cloned payload count")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)
    return {
        "before_total": old_total,
        "after_total": new_base,
        "payload_delta": len(cloned_payloads),
        "type_increments": {f"0x{rows[index]['key']:X}": amount for index, amount in sorted(increments.items())},
        "source_heap_data": before_heap,
        "source_root_data": before_root,
    }


def build_wad(source_raw: bytes, art_report: Path) -> tuple[bytes, dict]:
    check(sha(source_raw) == EXPECTED_WAD, "r_ui.wad is not frozen Raven production")
    logical = load_module("build-raven-ui-logical-clone.py", "nornir_map_hud_logical")
    records = logical.parse_wad(source_raw)
    check(logical.serialize_wad(records) == source_raw, "production WAD does not round-trip exactly")
    _, residents, user_hashes = parse_art_report(art_report)

    check(folded_name_hash(NORNIR["map_root"]) == folded_name_hash(NORNIR["map_go"]) == MAP_GO_HASH,
          "Nornir map root/GOPool hash relation changed")
    check(folded_name_hash(NORNIR["hud_root"]) == folded_name_hash(NORNIR["hud_go"]) == HUD_GO_HASH,
          "Nornir HUD root/GOPool hash relation changed")

    ids = {key: deterministic_id(NORNIR[key]) for key in
           ("map_root", "map_proto", "map_model", "material", "hud_root", "hud_proto", "hud_model")}
    check(len(set(ids.values())) == len(ids), "generated Nornir resource IDs collide with one another")
    existing_ids = {row["id"] for row in records}
    for key, rid in ids.items():
        check(rid not in existing_ids, f"generated Nornir {key} ID collides with production WAD")
    for label in ("diffuse", "emissive"):
        check(texture_def_id(FILE_HASH[label]) not in existing_ids, f"{label}: definition ID collision")
        check(texture_gpu_id(user_hashes[label]) not in existing_ids, f"{label}: GPU ID collision")

    existing_names = {row["name"].lower() for row in records}
    for name in NORNIR.values():
        if name.startswith(("go", "MDL_", "MAT_", "TX_")):
            check(name.lower() not in existing_names, f"Nornir WAD name already exists: {name}")

    source_texture = {}
    texture_clones = {}
    for label in ("diffuse", "emissive"):
        gpu_index, gpu = unique_texture(records, RAVEN[label], gpu=True)
        def_index, definition = unique_texture(records, RAVEN[label], gpu=False)
        check(len(gpu["data"]) == EXPECTED_RESIDENT[label][0], f"{label}: Raven resident size changed")
        check(len(definition["data"]) == 356, f"{label}: Raven texture definition size changed")
        new_gpu = clone_texture(gpu, NORNIR[label], texture_gpu_id(user_hashes[label]), residents[label])
        new_def = clone_texture(definition, NORNIR[label], texture_def_id(FILE_HASH[label]), bytes(definition["data"]))
        struct.pack_into("<Q", new_def["data"], 0x9C, user_hashes[label])
        texture_clones[label] = (new_gpu, new_def)
        source_texture[label] = {"gpu_index": gpu_index, "def_index": def_index, "gpu": gpu, "definition": definition}

    mat_rows, mat_target, mat_info = clone_group(logical, records, RAVEN["material"], NORNIR["material"], ids["material"])
    check(len(mat_target["data"]) >= 0x28, "Raven material payload is too short for identity fields")
    material_q10 = folded_name_hash("CompletionistNornirChestMaterialIdentity0")
    material_q20 = folded_name_hash("CompletionistNornirChestMaterialIdentity1")
    check(material_q10 != material_q20, "Nornir material identity hashes collide")
    used_material_qwords = set()
    for row in records:
        if row["data"] and row["name"].upper().startswith("MAT_") and len(row["data"]) >= 0x28:
            used_material_qwords.add(struct.unpack_from("<Q", row["data"], 0x10)[0])
            used_material_qwords.add(struct.unpack_from("<Q", row["data"], 0x20)[0])
    check(material_q10 not in used_material_qwords and material_q20 not in used_material_qwords,
          "Nornir material internal identity collides with an existing material")
    struct.pack_into("<Q", mat_target["data"], 0x10, material_q10)
    struct.pack_into("<Q", mat_target["data"], 0x20, material_q20)
    retarget_link(mat_rows, RAVEN["diffuse"], source_texture["diffuse"]["definition"]["id"],
                  NORNIR["diffuse"], texture_def_id(FILE_HASH["diffuse"]))
    retarget_link(mat_rows, RAVEN["emissive"], source_texture["emissive"]["definition"]["id"],
                  NORNIR["emissive"], texture_def_id(FILE_HASH["emissive"]))

    map_model_rows, _, map_model_info = clone_group(logical, records, RAVEN["map_model"], NORNIR["map_model"], ids["map_model"])
    retarget_link(map_model_rows, RAVEN["material"], mat_info["source"]["id"], NORNIR["material"], ids["material"])

    map_proto_rows, map_proto_target, map_proto_info = clone_group(logical, records, RAVEN["map_proto"], NORNIR["map_proto"], ids["map_proto"])
    map_proto_self_refs = replace_id(map_proto_target["data"], map_proto_info["source"]["id"], ids["map_proto"])
    retarget_link(map_proto_rows, RAVEN["map_model"], map_model_info["source"]["id"], NORNIR["map_model"], ids["map_model"])

    map_root_rows, map_root_target, map_root_info = clone_group(logical, records, RAVEN["map_root"], NORNIR["map_root"], ids["map_root"])
    check(len(map_root_target["data"]) == 164, "Raven map root payload size changed")
    check(bytes(map_root_target["data"][0x0C:0x1C]) == map_proto_info["source"]["id"], "Raven map root prototype slot changed")
    check(bytes(map_root_target["data"][0x1C:0x54]) == RAVEN["map_root"].encode("ascii").ljust(56, b"\0"),
          "Raven map root internal loader name changed")
    map_root_target["data"][0x0C:0x1C] = ids["map_proto"]
    map_root_target["data"][0x1C:0x54] = NORNIR["map_root"].encode("ascii").ljust(56, b"\0")

    hud_model_rows, _, hud_model_info = clone_group(logical, records, RAVEN["hud_model"], NORNIR["hud_model"], ids["hud_model"])
    retarget_link(hud_model_rows, RAVEN["material"], mat_info["source"]["id"], NORNIR["material"], ids["material"])

    hud_proto_rows, hud_proto_target, hud_proto_info = clone_group(logical, records, RAVEN["hud_proto"], NORNIR["hud_proto"], ids["hud_proto"])
    hud_proto_self_refs = replace_id(hud_proto_target["data"], hud_proto_info["source"]["id"], ids["hud_proto"])
    retarget_link(hud_proto_rows, RAVEN["hud_model"], hud_model_info["source"]["id"], NORNIR["hud_model"], ids["hud_model"])

    hud_root_rows, hud_root_target, hud_root_info = clone_group(logical, records, RAVEN["hud_root"], NORNIR["hud_root"], ids["hud_root"])
    check(len(hud_root_target["data"]) == 164, "Raven HUD root payload size changed")
    check(bytes(hud_root_target["data"][0x0C:0x1C]) == hud_proto_info["source"]["id"], "Raven HUD root prototype slot changed")
    check(bytes(hud_root_target["data"][0x1C:0x54]) == RAVEN["hud_root"].encode("ascii").ljust(56, b"\0"),
          "Raven HUD root internal loader name changed")
    hud_root_target["data"][0x0C:0x1C] = ids["hud_proto"]
    hud_root_target["data"][0x1C:0x54] = NORNIR["hud_root"].encode("ascii").ljust(56, b"\0")

    parent_links = [(i, row) for i, row in enumerate(records)
                    if row["kind"] == 1 and not row["data"]
                    and row["name"].lower() == RAVEN["map_root"].lower()
                    and row["id"] == map_root_info["source"]["id"]]
    check(len(parent_links) == 1, f"expected one Raven map parent link, found {len(parent_links)}")
    parent_index, parent_source = parent_links[0]
    parent_clone = copy.deepcopy(parent_source)
    parent_clone["original_offset"] = None
    parent_clone["payload_index"] = None
    set_name(parent_clone, NORNIR["map_root"])
    parent_clone["id"] = ids["map_root"]

    clone_sets = [
        [texture_clones["diffuse"][0]], [texture_clones["diffuse"][1]],
        [texture_clones["emissive"][0]], [texture_clones["emissive"][1]],
        mat_rows, map_model_rows, map_proto_rows, map_root_rows,
        hud_model_rows, hud_proto_rows, hud_root_rows,
    ]
    all_clones = [row for rows in clone_sets for row in rows]
    accounting = apply_accounting(logical, records, all_clones)

    jobs = [
        (source_texture["diffuse"]["gpu_index"], [texture_clones["diffuse"][0]]),
        (source_texture["diffuse"]["def_index"], [texture_clones["diffuse"][1]]),
        (source_texture["emissive"]["gpu_index"], [texture_clones["emissive"][0]]),
        (source_texture["emissive"]["def_index"], [texture_clones["emissive"][1]]),
        (mat_info["end"], mat_rows),
        (map_model_info["end"], map_model_rows),
        (map_proto_info["end"], map_proto_rows),
        (map_root_info["end"], map_root_rows),
        (hud_model_info["end"], hud_model_rows),
        (hud_proto_info["end"], hud_proto_rows),
        (hud_root_info["end"], hud_root_rows),
        (parent_index, [parent_clone]),
    ]
    for after, rows in sorted(jobs, key=lambda item: item[0], reverse=True):
        records[after + 1:after + 1] = rows

    candidate = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate)
    check(logical.serialize_wad(reparsed) == candidate, "Nornir WAD candidate does not reparse/round-trip exactly")
    check(len(logical.payload_records(reparsed)) == len(logical.payload_records(logical.parse_wad(source_raw))) + accounting["payload_delta"],
          "Nornir WAD candidate payload count delta changed")

    for label in ("diffuse", "emissive"):
        _, gpu = unique_texture(reparsed, NORNIR[label], gpu=True)
        _, definition = unique_texture(reparsed, NORNIR[label], gpu=False)
        check(bytes(gpu["data"]) == residents[label], f"{label}: resident bytes changed after WAD serialization")
        check(gpu["id"] == texture_gpu_id(user_hashes[label]), f"{label}: GPU ID changed")
        check(definition["id"] == texture_def_id(FILE_HASH[label]), f"{label}: definition ID changed")
        check(struct.unpack_from("<Q", definition["data"], 0x9C)[0] == user_hashes[label], f"{label}: user hash field changed")

    _, candidate_material = unique_payload(reparsed, NORNIR["material"])
    check(struct.unpack_from("<Q", candidate_material["data"], 0x10)[0] == material_q10, "Nornir material +0x10 changed")
    check(struct.unpack_from("<Q", candidate_material["data"], 0x20)[0] == material_q20, "Nornir material +0x20 changed")
    _, candidate_map_root = unique_payload(reparsed, NORNIR["map_root"])
    _, candidate_hud_root = unique_payload(reparsed, NORNIR["hud_root"])
    check(bytes(candidate_map_root["data"][0x0C:0x1C]) == ids["map_proto"], "Nornir map root lost map prototype")
    check(bytes(candidate_hud_root["data"][0x0C:0x1C]) == ids["hud_proto"], "Nornir HUD root lost HUD prototype")

    # Strong reversibility proof: remove every Nornir record, restore only the
    # WAD accounting payload bytes, and require the exact frozen Raven WAD.
    removal: set[int] = set()
    for name in (NORNIR["material"], NORNIR["map_model"], NORNIR["map_proto"], NORNIR["map_root"],
                 NORNIR["hud_model"], NORNIR["hud_proto"], NORNIR["hud_root"]):
        idx, _ = unique_payload(reparsed, name)
        start, end = group_bounds(logical, reparsed, idx)
        removal.update(range(start, end + 1))
    for label in ("diffuse", "emissive"):
        removal.update(texture_removal_rows(reparsed, NORNIR[label], removal))
    new_parent = [i for i, row in enumerate(reparsed) if row["kind"] == 1 and not row["data"]
                  and row["name"].lower() == NORNIR["map_root"].lower() and row["id"] == ids["map_root"]]
    check(len(new_parent) == 1, "Nornir map parent link did not reparse uniquely")
    removal.add(new_parent[0])
    stripped = [copy.deepcopy(row) for i, row in enumerate(reparsed) if i not in removal]
    stripped_payloads = logical.payload_records(stripped)
    stripped_payloads[0]["data"] = bytearray(accounting["source_heap_data"])
    stripped_payloads[1]["data"] = bytearray(accounting["source_root_data"])
    normalized = logical.serialize_wad(stripped)
    check(normalized == source_raw, "normalized Nornir WAD candidate does not equal frozen Raven WAD byte-for-byte")

    return candidate, {
        "source_sha256": sha(source_raw),
        "candidate_sha256": sha(candidate),
        "source_bytes": len(source_raw),
        "candidate_bytes": len(candidate),
        "accounting": {k: v for k, v in accounting.items() if not k.startswith("source_")},
        "resource_ids": {key: value.hex() for key, value in ids.items()},
        "texture_user_hashes": {key: f"{value:016X}" for key, value in user_hashes.items()},
        "material_identity_q10": f"{material_q10:016X}",
        "material_identity_q20": f"{material_q20:016X}",
        "map_prototype_self_id_replacements": map_proto_self_refs,
        "hud_prototype_self_id_replacements": hud_proto_self_refs,
        "map_parent_link_cloned": True,
        "resident_art_injected_exactly": True,
        "candidate_reparse_roundtrip_exact": True,
        "normalized_candidate_equals_frozen_raven_wad": True,
        "raven_records_mutated": False,
    }


def dcb_rows(data: bytes) -> tuple[int, list[dict], int]:
    count = struct.unpack_from("<I", data, 8)[0]
    end = GOP_BASE + count * GOP_ROW
    check(end <= len(data), "GOPool exceeds data chunk")
    rows = []
    for index in range(count):
        at = GOP_BASE + index * GOP_ROW
        uid, capacity = struct.unpack_from("<QH", data, at)
        rows.append({"index": index, "uid": uid, "capacity": capacity, "raw": bytes(data[at:at + GOP_ROW])})
    return count, rows, end


def build_dcb(source: bytes) -> tuple[bytes, dict]:
    check(sha(source) == EXPECTED_UI_DCB, "wad_r_ui.dcb is not frozen Raven production")
    verifier = load_module("verify-raven-production-state.py", "nornir_map_hud_verify")
    chunks = verifier.parse_chunks(source)
    check([row["kind"] for row in chunks] == [11, 12, 13, 14, 15], "WAD_R_UI DCB chunk order changed")
    dc = verifier.one(chunks, 12)
    data = bytearray(source[dc["start"]:dc["end"]])
    count, rows, pool_end = dcb_rows(data)
    check(count == 257, f"expected 257 frozen GOPool rows, found {count}")
    existing = {row["uid"] for row in rows}
    check(MAP_GO_HASH not in existing and HUD_GO_HASH not in existing, "Nornir GOPool row already exists")
    raven_map = [row for row in rows if row["uid"] == RAVEN_MAP_HASH]
    raven_hud = [row for row in rows if row["uid"] == RAVEN_HUD_HASH]
    check(len(raven_map) == 1 and raven_map[0]["index"] == 255 and raven_map[0]["capacity"] == 1,
          "Raven map GOPool row changed")
    check(len(raven_hud) == 1 and raven_hud[0]["index"] == 256 and raven_hud[0]["capacity"] == 2,
          "Raven HUD GOPool row changed")
    ptr10 = struct.unpack_from("<q", data, 0x10)[0]
    ptr20 = struct.unpack_from("<q", data, 0x20)[0]
    check(ptr10 == pool_end - GOP_ROW and ptr20 == pool_end,
          f"GOPool tail pointer relation changed: ptr10={ptr10:#x} ptr20={ptr20:#x} pool_end={pool_end:#x}")

    inserted = struct.pack("<QH6x", MAP_GO_HASH, 1) + struct.pack("<QH6x", HUD_GO_HASH, 2)
    candidate_data = bytearray(data[:pool_end] + inserted + data[pool_end:])
    struct.pack_into("<I", candidate_data, 8, count + 2)
    struct.pack_into("<q", candidate_data, 0x10, ptr10 + len(inserted))
    struct.pack_into("<q", candidate_data, 0x20, ptr20 + len(inserted))
    header = bytearray(source[dc["header"]:dc["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = source[:dc["header"]] + bytes(header) + bytes(candidate_data) + source[dc["end"]:]

    after_chunks = verifier.parse_chunks(candidate)
    check([row["kind"] for row in after_chunks] == [11, 12, 13, 14, 15], "candidate DCB chunk order changed")
    adc = verifier.one(after_chunks, 12)
    round_data = candidate[adc["start"]:adc["end"]]
    new_count, new_rows, new_end = dcb_rows(round_data)
    check(new_count == 259, f"candidate GOPool count is {new_count}, expected 259")
    check(round_data[GOP_BASE:pool_end] == data[GOP_BASE:pool_end], "an existing GOPool row changed")
    check(round_data[pool_end:pool_end + 32] == inserted, "Nornir GOPool rows are not exact")
    check(round_data[new_end:] == data[pool_end:], "MemoryPools/Lua tail changed instead of shifting")
    map_rows = [row for row in new_rows if row["uid"] == MAP_GO_HASH]
    hud_rows = [row for row in new_rows if row["uid"] == HUD_GO_HASH]
    check(len(map_rows) == 1 and map_rows[0]["index"] == 257 and map_rows[0]["capacity"] == 1,
          "Nornir map GOPool row is not index 257 capacity 1")
    check(len(hud_rows) == 1 and hud_rows[0]["index"] == 258 and hud_rows[0]["capacity"] == 2,
          "Nornir HUD GOPool row is not index 258 capacity 2")

    before_non_data = {c["kind"]: source[c["header"]:c["padded"]] for c in chunks if c["kind"] != 12}
    after_non_data = {c["kind"]: candidate[c["header"]:c["padded"]] for c in after_chunks if c["kind"] != 12}
    check(before_non_data == after_non_data, "a non-data WAD_R_UI DCB chunk changed")

    normalized_data = bytearray(round_data[:pool_end] + round_data[pool_end + 32:])
    struct.pack_into("<I", normalized_data, 8, count)
    struct.pack_into("<q", normalized_data, 0x10, ptr10)
    struct.pack_into("<q", normalized_data, 0x20, ptr20)
    normalized_header = bytearray(candidate[adc["header"]:adc["start"]])
    struct.pack_into("<I", normalized_header, 4, len(normalized_data))
    normalized = candidate[:adc["header"]] + bytes(normalized_header) + bytes(normalized_data) + candidate[adc["end"]:]
    check(normalized == source, "normalized GOPool candidate does not equal frozen Raven DCB byte-for-byte")

    return candidate, {
        "source_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "source_rows": count,
        "candidate_rows": new_count,
        "map_index": 257,
        "map_capacity": 1,
        "hud_index": 258,
        "hud_capacity": 2,
        "all_existing_rows_byte_identical": True,
        "raven_map_row_preserved": True,
        "raven_hud_row_preserved": True,
        "memorypools_lua_tail_preserved_after_shift": True,
        "non_data_chunks_byte_identical": True,
        "normalized_candidate_equals_frozen_raven_dcb": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--art-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    check(not output_dir.is_relative_to(game) and not report_path.is_relative_to(game), "offline output must stay outside game directory")
    check(repo == REPO.resolve(), f"unexpected repo root: {repo}")

    live_wad = game / "exec/wad/pc_le/r_ui.wad"
    live_dcb = game / "exec/dc/pc_le/wad_r_ui.dcb"
    check(file_sha(live_wad) == EXPECTED_WAD, "live r_ui.wad is not frozen Raven production")
    check(file_sha(live_dcb) == EXPECTED_UI_DCB, "live wad_r_ui.dcb is not frozen Raven production")
    before = {"r_ui_wad": live_wad.read_bytes(), "wad_r_ui": live_dcb.read_bytes()}

    wad_candidate, wad_report = build_wad(before["r_ui_wad"], args.art_report.resolve())
    dcb_candidate, dcb_report = build_dcb(before["wad_r_ui"])

    output_dir.mkdir(parents=True, exist_ok=True)
    wad_path = output_dir / "r_ui.wad"
    dcb_path = output_dir / "wad_r_ui.dcb"
    wad_path.write_bytes(wad_candidate)
    dcb_path.write_bytes(dcb_candidate)
    check(wad_path.read_bytes() == wad_candidate and dcb_path.read_bytes() == dcb_candidate, "offline candidate write verification failed")
    check(live_wad.read_bytes() == before["r_ui_wad"], "live Raven r_ui.wad changed during offline build")
    check(live_dcb.read_bytes() == before["wad_r_ui"], "live Raven wad_r_ui.dcb changed during offline build")

    report = {
        "schema": 1,
        "result": RESULT,
        "source": {
            "r_ui_wad_sha256": EXPECTED_WAD,
            "wad_r_ui_dcb_sha256": EXPECTED_UI_DCB,
            "resident_art_report": str(args.art_report.resolve()),
            "resident_art_texpack_sha256": EXPECTED_TEXPACK,
        },
        "candidate": {
            "r_ui_wad": str(wad_path),
            "wad_r_ui_dcb": str(dcb_path),
            "wad": wad_report,
            "gopool": dcb_report,
        },
        "nornir": {
            "map_go": NORNIR["map_go"],
            "map_go_hash": f"{MAP_GO_HASH:016X}",
            "hud_go": NORNIR["hud_go"],
            "hud_go_hash": f"{HUD_GO_HASH:016X}",
            "diffuse": NORNIR["diffuse"],
            "diffuse_sha256": EXPECTED_RESIDENT["diffuse"][1],
            "emissive": NORNIR["emissive"],
            "emissive_sha256": EXPECTED_RESIDENT["emissive"][1],
        },
        "proof": {
            "runtime_proven_raven_resource_grammar_used_as_donor": True,
            "resident_art_injected_exactly": True,
            "candidate_wad_reparsed": True,
            "candidate_wad_normalizes_exactly_to_raven_production": True,
            "candidate_gopool_normalizes_exactly_to_raven_production": True,
            "all_existing_gopool_rows_preserved": True,
            "raven_resources_preserved": True,
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "stock_resources_modified": False,
            "raven_production_files_changed": False,
        },
        "ready_for_next_offline_gate": True,
        "next_gate": "Add CompletionistNornirChest and its dedicated in-world carrier to a cloned wad_r_perm.dcb, retarget only the offline Nornir native mapmaster candidate to the Nornir map GameObject, then validate the complete four-file Nornir candidate before any runtime install."
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"r_ui.wad:     {wad_report['source_sha256']} -> {wad_report['candidate_sha256']}")
    print(f"wad_r_ui.dcb: {dcb_report['source_sha256']} -> {dcb_report['candidate_sha256']}")
    print(f"WAD payload delta: {wad_report['accounting']['payload_delta']}")
    print("GOPool:       257 -> 259 rows")
    print(f"map:          {NORNIR['map_go']} index 257 capacity 1")
    print(f"HUD:          {NORNIR['hud_go']} index 258 capacity 2")
    print("resident Nornir art injected exactly: true")
    print("normalized WAD equals Raven production: true")
    print("normalized GOPool DCB equals Raven production: true")
    print("Raven production files changed: false")
    print("game files written: false")
    print("runtime install performed: false")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
