#!/usr/bin/env python3
"""Build the map-only Raven Twin candidate from frozen Raven production.

The source is the current runtime-proven Raven installation. The builder reads
four pinned files and writes only an offline candidate and proof report. It
does not launch the game, install files, add compass/in-world support, or add
lifecycle code.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = "RAVEN_TWIN_STAGE_A_OFFLINE_PROOF_PASSED"

FILES = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_ui.dcb": "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d",
    "exec/dc/pc_le/mapmaster.dcb": "b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f",
    "exec/dc/pc_le/mapcoords.dcb": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
}

RAVEN_MARKER_NAME = "Completionist_V103_Veithurgard_Raven_01"
RAVEN_MARKER_UID = 0xE15E6BC82AE2773E
RAVEN_MAP_GO = "goMapIconCompletionistRaven"
RAVEN_MAP_HASH = 0x584F31DC8BD6E738
RAVEN_POSITION = (-64.875, 12.984375, 787.5)
MIDGARD_REALM = 0x7CE593BC21393690
VEITHURGARD_REGION = 0xA1845BEF17F0E7BB
RAVEN_WAD = "WAD_Xpl200_Funeral"

TWIN_MARKER_NAME = "Completionist_V104_Veithurgard_Raven_Twin_01"
TWIN_MARKER_UID = 0x2F530E7F3F156D90
TWIN_MAP_GO = "goMapIconCompletionistRavenTwin"
TWIN_MAP_HASH = 0x3152371298304268
TWIN_POSITION = (-32.875, 12.984375, 787.5)

RAVEN = {
    "map_root": "gomapiconcompletionistraven",
    "map_proto": "goProtoMapIconCompletionistRaven",
    "map_model": "MDL_completionistraven",
    "material": "MAT_AE4AD85BB993F040",
    "diffuse": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
    "emissive": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
}
TWIN_FILE_HASH = {
    "diffuse": 0x1C25CED771C6B311,
    "emissive": 0x2F07426F7737EEB1,
}
TWIN_USER_HASH = {
    "diffuse": 0xD4DC4EA332F8F1BF,
    "emissive": 0xBECA3591D82B3DBE,
}
TWIN = {
    "map_go": TWIN_MAP_GO,
    "map_root": "gomapiconcompletionistraventwin",
    "map_proto": "goProtoMapIconCompletionistRavenTwin",
    "map_model": "MDL_completionistraventwin",
    "material": "MAT_completionistraventwin",
    "diffuse": f"TX_completionist_raven_twin_diff_{TWIN_FILE_HASH['diffuse']:016X}",
    "emissive": f"TX_completionist_raven_twin_emis_{TWIN_FILE_HASH['emissive']:016X}",
}
RESOURCE_NAMESPACE = "completionist-map-gow2018:v0.10.4:raven-twin-stage-a"
RESOURCE_ROLES = ("map_root", "map_proto", "map_model", "material")

STOCK_DONOR_NAMES = (
    "MAT_0C599DC8DC7E2170",
    "MDL_mapicondock",
    "MG_mapicondock_0",
    "gomapicondock",
    "MDL_boatdock",
    "MG_boatdock_0",
    "goboatdock",
)

GOP_BASE = 0x90
GOP_ROW = 0x10


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse_point(path: Path) -> bool:
    info = os.lstat(path)
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def assert_safe_write_path(root: Path, path: Path, label: str) -> None:
    """Reject out-of-root paths, linked parents, and linked destinations."""
    root = root.resolve()
    path = path.absolute()
    check(path != root and path.is_relative_to(root), f"{label} escapes approved root: {path}")

    current = root
    check(current.is_dir(), f"{label} root missing: {root}")
    check(not _is_reparse_point(current), f"{label} root is a link/reparse point: {root}")
    for part in path.parent.relative_to(root).parts:
        current = current / part
        if not current.exists():
            current.mkdir()
        check(current.is_dir(), f"{label} parent is not a directory: {current}")
        check(not _is_reparse_point(current),
              f"{label} parent is a link/reparse point: {current}")
    check(path.parent.resolve() == path.parent,
          f"{label} parent resolves outside its lexical path: {path.parent}")

    if path.exists() or path.is_symlink():
        check(not _is_reparse_point(path), f"{label} destination is a link/reparse point: {path}")
        check(path.is_file(), f"{label} destination is not a file: {path}")
        check(path.stat().st_nlink == 1, f"{label} destination has multiple hard links: {path}")


def write_bytes_atomic(root: Path, path: Path, raw: bytes, label: str) -> None:
    """Write within root without ever opening an existing destination for mutation."""
    root.mkdir(parents=True, exist_ok=True)
    assert_safe_write_path(root, path, label)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{path.name}.", suffix=".tmp",
                dir=path.parent, delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        check(temp_path.parent.resolve() == path.parent.resolve(),
              f"{label} temporary file escaped destination parent")
        assert_safe_write_path(root, path, label)
        os.replace(temp_path, path)
        temp_path = None
        check(path.read_bytes() == raw, f"{label} write verification failed: {path}")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def deterministic_resource_id(name: str) -> bytes:
    return hashlib.sha256(f"{RESOURCE_NAMESPACE}:{name}".encode("ascii")).digest()[:16]


def texture_definition_id(file_hash: int) -> bytes:
    return bytes.fromhex("5458455400455255") + struct.pack(
        "<II", file_hash >> 32, file_hash & 0xFFFFFFFF)


def texture_gpu_id(user_hash: int) -> bytes:
    return bytes(8) + struct.pack(
        "<II", user_hash >> 32, user_hash & 0xFFFFFFFF)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_name(row: dict, name: str) -> None:
    check(len(name.encode("ascii")) <= 55, f"WAD name too long: {name}")
    row["name"] = name
    row["original_offset"] = None


def one_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(index, row) for index, row in enumerate(records)
            if row["kind"] == 1 and row["data"]
            and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def one_texture(records: list[dict], name: str, gpu: bool) -> tuple[int, dict]:
    kind, flags = (0x1D, 0x80A1) if gpu else (1, 0x8021)
    hits = [(index, row) for index, row in enumerate(records)
            if row["kind"] == kind and row["flags"] == flags and row["data"]
            and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one texture record {name!r}, found {len(hits)}")
    return hits[0]


def group_bounds(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    start = records[payload_index]["parent"]
    check(start is not None and records[start]["kind"] == 2, "payload has no group")
    return start, logical.matching_group_end(records, start)


def clone_scope(records: list[dict], start: int, end: int) -> list[dict]:
    rows = copy.deepcopy(records[start:end + 1])
    for source, clone in zip(records[start:end + 1], rows):
        clone["_source_payload_index"] = source["payload_index"] if source["data"] else None
        clone["original_offset"] = None
        clone["payload_index"] = None
    return rows


def target_in_clone(rows: list[dict], name: str) -> dict:
    hits = [row for row in rows if row["kind"] == 1 and row["data"]
            and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"clone target is not unique: {name}")
    return hits[0]


def clone_group(logical, records: list[dict], old_name: str, new_name: str,
                new_id: bytes) -> tuple[list[dict], dict, dict]:
    source_index, source = one_payload(records, old_name)
    start, end = group_bounds(logical, records, source_index)
    rows = clone_scope(records, start, end)
    for row in rows:
        if row["kind"] in (2, 3) and row["name"].lower() == old_name.lower():
            set_name(row, new_name)
    target = target_in_clone(rows, old_name)
    set_name(target, new_name)
    target["id"] = new_id
    return rows, target, {
        "source_index": source_index,
        "start": start,
        "end": end,
        "source": source,
        "source_rows": records[start:end + 1],
    }


def retarget_link(rows: list[dict], old_name: str, old_id: bytes,
                  new_name: str, new_id: bytes) -> dict:
    hits = [(index, row) for index, row in enumerate(rows)
            if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == old_name.lower() and row["id"] == old_id]
    check(len(hits) == 1, f"expected one dependency {old_name!r}, found {len(hits)}")
    index, row = hits[0]
    set_name(row, new_name)
    row["id"] = new_id
    return {"row_index": index, "old_name": old_name, "new_name": new_name}


def replace_exact(blob: bytearray, old: bytes, new: bytes) -> list[int]:
    check(len(old) == len(new), "replacement width changed")
    offsets = []
    cursor = 0
    raw = bytes(blob)
    while True:
        found = raw.find(old, cursor)
        if found < 0:
            break
        offsets.append(found)
        cursor = found + len(old)
    check(offsets, "expected local self-reference is absent")
    blob[:] = raw.replace(old, new)
    return offsets


def clone_texture(source: dict, new_name: str, new_id: bytes) -> dict:
    row = copy.deepcopy(source)
    row["_source_payload_index"] = source["payload_index"]
    row["original_offset"] = None
    row["payload_index"] = None
    set_name(row, new_name)
    row["id"] = new_id
    return row


def merge_offsets(offsets: list[int]) -> list[list[int]]:
    if not offsets:
        return []
    spans = []
    start = previous = offsets[0]
    for offset in offsets[1:]:
        if offset != previous + 1:
            spans.append([start, previous])
            start = offset
        previous = offset
    spans.append([start, previous])
    return spans


def classify_record_diff(logical, donor: dict, twin: dict,
                         allowed: list[tuple[int, int, str, str]]) -> dict:
    before = logical.record_bytes(donor)
    after = logical.record_bytes(twin)
    check(len(before) == len(after), "record size changed")
    changed = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    classified = []
    covered: set[int] = set()
    for start, end, category, reason in allowed:
        actual = [offset for offset in changed if start <= offset < end]
        if not actual:
            continue
        classified.append({
            "byte_spans_in_serialized_record_inclusive": merge_offsets(actual),
            "field_window_half_open": [start, end],
            "category": category,
            "reason": reason,
        })
        covered.update(actual)
    unexplained = sorted(set(changed) - covered)
    check(not unexplained,
          f"unexplained changed payload/header bytes for {donor['name']}: {merge_offsets(unexplained)}")
    return {
        "donor_name": donor["name"],
        "twin_name": twin["name"],
        "kind": f"0x{donor['kind']:X}",
        "flags": f"0x{donor['flags']:X}",
        "payload_bytes": len(donor["data"]),
        "changed_byte_count": len(changed),
        "changes": classified,
        "unexplained_changed_bytes": [],
    }


def group_diff_ledger(logical, source_rows: list[dict], twin_rows: list[dict],
                      payload_windows: dict[int, list[tuple[int, int, str, str]]]) -> list[dict]:
    check(len(source_rows) == len(twin_rows), "clone group row count changed")
    ledger = []
    for index, (source, twin) in enumerate(zip(source_rows, twin_rows)):
        allowed: list[tuple[int, int, str, str]] = []
        if source["name"] != twin["name"]:
            category = "known_local_reference" if not source["data"] and source["kind"] == 1 else "known_identity"
            allowed.append((24, 80, category, "WAD record name or dependency name"))
        if source["id"] != twin["id"]:
            category = "known_local_reference" if not source["data"] else "known_identity"
            allowed.append((8, 24, category, "WAD record ID or dependency target ID"))
        allowed.extend(payload_windows.get(index, []))
        item = classify_record_diff(logical, source, twin, allowed)
        item["group_row_index"] = index
        ledger.append(item)
    return ledger


def accounting_update(logical, records: list[dict], cloned_rows: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    heap, root = payloads[0], payloads[1]
    source_heap = bytes(heap["data"])
    source_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0], "WAD totals differ")
    type_rows = logical.read_type_table(root["data"])
    increments: dict[int, int] = {}
    for clone in [row for row in cloned_rows if row["data"]]:
        source_index = clone.get("_source_payload_index")
        matches = [row for row in type_rows
                   if row["base"] <= source_index < row["base"] + row["count"]]
        check(len(matches) == 1,
              f"map clone payload {source_index} lacks one accounting row")
        index = matches[0]["index"]
        increments[index] = increments.get(index, 0) + 1
    new_base = 0
    for row in type_rows:
        new_count = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, new_count)
        new_base += new_count
    delta = sum(increments.values())
    check(new_base == old_total + delta, "WAD accounting delta mismatch")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)
    return {
        "before_total": old_total,
        "after_total": new_base,
        "payload_delta": len([row for row in cloned_rows if row["data"]]),
        "accounted_delta": delta,
        "type_increments": {
            f"0x{type_rows[index]['key']:X}": amount
            for index, amount in sorted(increments.items())
        },
        "source_heap": source_heap,
        "source_root": source_root,
    }


def preserved_named_records(logical, source: list[dict], candidate: list[dict],
                            names: list[str]) -> dict:
    proof = {}
    for name in names:
        before = [logical.record_bytes(row) for row in source
                  if row["name"].lower() == name.lower()]
        after = [logical.record_bytes(row) for row in candidate
                 if row["name"].lower() == name.lower()]
        check(before, f"source record missing: {name}")
        pending = list(after)
        for raw in before:
            check(raw in pending, f"source record changed: {name}")
            pending.remove(raw)
        proof[name] = {
            "source_record_count": len(before),
            "candidate_record_count": len(after),
            "every_source_record_byte_identical": True,
        }
    return proof


def build_wad(source_raw: bytes) -> tuple[bytes, dict]:
    check(sha_bytes(source_raw) == FILES["exec/wad/pc_le/r_ui.wad"],
          "r_ui.wad is not frozen Raven production")
    logical = load_module("raven_twin_logical", HERE / "build-raven-ui-logical-clone.py")
    records = logical.parse_wad(source_raw)
    source_records = copy.deepcopy(records)
    check(logical.serialize_wad(records) == source_raw, "frozen Raven WAD round-trip changed")

    check(folded_name_hash(TWIN_MAP_GO) == TWIN_MAP_HASH, "Twin map hash changed")
    check(folded_name_hash(TWIN["map_root"]) == TWIN_MAP_HASH,
          "Twin root/loader folded hash mismatch")
    ids = {role: deterministic_resource_id(TWIN[role]) for role in RESOURCE_ROLES}
    existing_ids = {row["id"] for row in records}
    check(len(set(ids.values())) == len(ids) and not (set(ids.values()) & existing_ids),
          "Twin WAD resource ID collision")
    existing_names = {row["name"].lower() for row in records}
    for name in TWIN.values():
        check(name.lower() not in existing_names, f"Twin WAD name collision: {name}")

    source_texture: dict[str, dict] = {}
    texture_clones: dict[str, tuple[dict, dict]] = {}
    texture_ledger = []
    for label in ("diffuse", "emissive"):
        gpu_index, gpu = one_texture(records, RAVEN[label], True)
        definition_index, definition = one_texture(records, RAVEN[label], False)
        new_gpu = clone_texture(gpu, TWIN[label], texture_gpu_id(TWIN_USER_HASH[label]))
        new_definition = clone_texture(
            definition, TWIN[label], texture_definition_id(TWIN_FILE_HASH[label]))
        check(len(new_definition["data"]) > 0xA4, "Raven texture definition shape changed")
        struct.pack_into("<Q", new_definition["data"], 0x9C, TWIN_USER_HASH[label])
        check(bytes(new_gpu["data"]) == bytes(gpu["data"]),
              f"{label}: Raven resident pixel payload changed")
        texture_clones[label] = (new_gpu, new_definition)
        source_texture[label] = {
            "gpu_index": gpu_index,
            "definition_index": definition_index,
            "gpu": gpu,
            "definition": definition,
        }
        texture_ledger.extend([
            classify_record_diff(logical, gpu, new_gpu, [
                (8, 24, "known_identity", "new GPU WAD record ID"),
                (24, 80, "known_identity", "new texture record name"),
            ]),
            classify_record_diff(logical, definition, new_definition, [
                (8, 24, "known_identity", "new texture-definition WAD record ID"),
                (24, 80, "known_identity", "new texture record name"),
                (96 + 0x9C, 96 + 0xA4, "known_local_reference",
                 "texture definition points at Twin GPU user hash"),
            ]),
        ])

    material_rows, material_target, material_info = clone_group(
        logical, records, RAVEN["material"], TWIN["material"], ids["material"])
    retarget_link(
        material_rows, RAVEN["diffuse"], source_texture["diffuse"]["definition"]["id"],
        TWIN["diffuse"], texture_definition_id(TWIN_FILE_HASH["diffuse"]))
    retarget_link(
        material_rows, RAVEN["emissive"], source_texture["emissive"]["definition"]["id"],
        TWIN["emissive"], texture_definition_id(TWIN_FILE_HASH["emissive"]))
    check(bytes(material_target["data"]) == bytes(material_info["source"]["data"]),
          "opaque Raven material payload changed")
    raven_q10 = struct.unpack_from("<Q", material_info["source"]["data"], 0x10)[0]
    raven_q20 = struct.unpack_from("<Q", material_info["source"]["data"], 0x20)[0]

    model_rows, model_target, model_info = clone_group(
        logical, records, RAVEN["map_model"], TWIN["map_model"], ids["map_model"])
    retarget_link(model_rows, RAVEN["material"], material_info["source"]["id"],
                  TWIN["material"], ids["material"])
    check(bytes(model_target["data"]) == bytes(model_info["source"]["data"]),
          "opaque Raven model payload changed")

    proto_rows, proto_target, proto_info = clone_group(
        logical, records, RAVEN["map_proto"], TWIN["map_proto"], ids["map_proto"])
    self_offsets = replace_exact(
        proto_target["data"], proto_info["source"]["id"], ids["map_proto"])
    retarget_link(proto_rows, RAVEN["map_model"], model_info["source"]["id"],
                  TWIN["map_model"], ids["map_model"])

    root_rows, root_target, root_info = clone_group(
        logical, records, RAVEN["map_root"], TWIN["map_root"], ids["map_root"])
    check(len(root_target["data"]) == 164, "Raven map root payload shape changed")
    check(bytes(root_target["data"][0x0C:0x1C]) == proto_info["source"]["id"],
          "Raven root prototype field changed")
    check(bytes(root_target["data"][0x1C:0x54]) ==
          RAVEN["map_root"].encode("ascii").ljust(56, b"\0"),
          "Raven root loader field changed")
    root_target["data"][0x0C:0x1C] = ids["map_proto"]
    root_target["data"][0x1C:0x54] = TWIN["map_root"].encode("ascii").ljust(56, b"\0")

    parent_hits = [(index, row) for index, row in enumerate(records)
                   if row["kind"] == 1 and not row["data"]
                   and row["name"].lower() == RAVEN["map_root"].lower()
                   and row["id"] == root_info["source"]["id"]]
    check(len(parent_hits) == 1, "Raven map root parent link changed")
    parent_index, parent_source = parent_hits[0]
    parent_clone = copy.deepcopy(parent_source)
    parent_clone["original_offset"] = None
    parent_clone["payload_index"] = None
    set_name(parent_clone, TWIN["map_root"])
    parent_clone["id"] = ids["map_root"]

    proto_target_index = proto_rows.index(proto_target)
    root_target_index = root_rows.index(root_target)
    clone_ledger = {
        "textures": texture_ledger,
        "material_group": group_diff_ledger(
            logical, material_info["source_rows"], material_rows, {}),
        "model_group": group_diff_ledger(
            logical, model_info["source_rows"], model_rows, {}),
        "prototype_group": group_diff_ledger(
            logical, proto_info["source_rows"], proto_rows, {
                proto_target_index: [
                    (96 + offset, 96 + offset + 16, "known_local_reference",
                     "prototype payload self-reference uses Twin prototype ID")
                    for offset in self_offsets
                ]
            }),
        "root_group": group_diff_ledger(
            logical, root_info["source_rows"], root_rows, {
                root_target_index: [
                    (96 + 0x0C, 96 + 0x1C, "known_local_reference",
                     "root points at Twin prototype ID"),
                    (96 + 0x1C, 96 + 0x54, "known_identity",
                     "root embeds Twin loader name"),
                ]
            }),
        "parent_link": [classify_record_diff(logical, parent_source, parent_clone, [
            (8, 24, "known_local_reference", "parent link points at Twin root ID"),
            (24, 80, "known_local_reference", "parent link names Twin root"),
        ])],
    }

    clone_sets = [
        [texture_clones["diffuse"][0]],
        [texture_clones["diffuse"][1]],
        [texture_clones["emissive"][0]],
        [texture_clones["emissive"][1]],
        material_rows,
        model_rows,
        proto_rows,
        root_rows,
    ]
    all_clones = [row for rows in clone_sets for row in rows]
    accounting = accounting_update(logical, records, all_clones)
    heap_after = bytes(logical.payload_records(records)[0]["data"])
    root_after = bytes(logical.payload_records(records)[1]["data"])

    jobs = [
        (source_texture["diffuse"]["gpu_index"], [texture_clones["diffuse"][0]]),
        (source_texture["diffuse"]["definition_index"], [texture_clones["diffuse"][1]]),
        (source_texture["emissive"]["gpu_index"], [texture_clones["emissive"][0]]),
        (source_texture["emissive"]["definition_index"], [texture_clones["emissive"][1]]),
        (material_info["end"], material_rows),
        (model_info["end"], model_rows),
        (proto_info["end"], proto_rows),
        (root_info["end"], root_rows),
        (parent_index, [parent_clone]),
    ]
    for after, rows in sorted(jobs, key=lambda item: item[0], reverse=True):
        records[after + 1:after + 1] = rows

    candidate = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate)
    check(logical.serialize_wad(reparsed) == candidate, "Twin WAD round-trip changed")

    for label in ("diffuse", "emissive"):
        _, raven_gpu = one_texture(source_records, RAVEN[label], True)
        _, twin_gpu = one_texture(reparsed, TWIN[label], True)
        check(bytes(twin_gpu["data"]) == bytes(raven_gpu["data"]),
              f"{label}: Twin pixel payload differs from Raven")
    _, candidate_material = one_payload(reparsed, TWIN["material"])
    check(bytes(candidate_material["data"]) == bytes(material_info["source"]["data"]),
          "Twin material opaque payload differs from Raven")

    removal: set[int] = set()
    for name in (TWIN["material"], TWIN["map_model"], TWIN["map_proto"], TWIN["map_root"]):
        index, _ = one_payload(reparsed, name)
        start, end = group_bounds(logical, reparsed, index)
        removal.update(range(start, end + 1))
    for label in ("diffuse", "emissive"):
        hits = [index for index, row in enumerate(reparsed)
                if row["name"].lower() == TWIN[label].lower()
                and row["data"] and row["kind"] in (1, 0x1D)]
        check(len(hits) == 2, f"{label}: Twin standalone texture shape changed")
        removal.update(hits)
    parent_hits_after = [index for index, row in enumerate(reparsed)
                         if row["kind"] == 1 and not row["data"]
                         and row["name"].lower() == TWIN["map_root"].lower()
                         and row["id"] == ids["map_root"]]
    check(len(parent_hits_after) == 1, "Twin parent link does not normalize uniquely")
    removal.add(parent_hits_after[0])
    stripped = [copy.deepcopy(row) for index, row in enumerate(reparsed) if index not in removal]
    stripped_payloads = logical.payload_records(stripped)
    stripped_payloads[0]["data"] = bytearray(accounting["source_heap"])
    stripped_payloads[1]["data"] = bytearray(accounting["source_root"])
    normalized = logical.serialize_wad(stripped)
    check(normalized == source_raw, "Twin WAD inverse normalization is not frozen Raven")

    preserve_names = list(RAVEN.values()) + list(STOCK_DONOR_NAMES)
    preservation = preserved_named_records(logical, source_records, reparsed, preserve_names)
    bookkeeping_ledger = []
    for label, before, after in (
        ("heap total", accounting["source_heap"], heap_after),
        ("root/type table", accounting["source_root"], root_after),
    ):
        offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
        bookkeeping_ledger.append({
            "payload": label,
            "changed_byte_spans_inclusive": merge_offsets(offsets),
            "category": "explicitly_justified",
            "reason": "WAD payload-count/type-range bookkeeping for eight appended map payloads",
            "unexplained_changed_bytes": [],
        })

    all_ledger_rows = [row for group in clone_ledger.values() for row in group]
    check(all(not row["unexplained_changed_bytes"] for row in all_ledger_rows),
          "WAD clone ledger has unexplained bytes")
    return candidate, {
        "source_sha256": sha_bytes(source_raw),
        "candidate_sha256": sha_bytes(candidate),
        "source_bytes": len(source_raw),
        "candidate_bytes": len(candidate),
        "resource_ids": {role: ids[role].hex() for role in RESOURCE_ROLES},
        "texture_identities": {
            label: {
                "name": TWIN[label],
                "file_hash": f"{TWIN_FILE_HASH[label]:016X}",
                "definition_id": texture_definition_id(TWIN_FILE_HASH[label]).hex(),
                "user_hash": f"{TWIN_USER_HASH[label]:016X}",
                "gpu_id": texture_gpu_id(TWIN_USER_HASH[label]).hex(),
                "resident_payload_sha256": sha_bytes(source_texture[label]["gpu"]["data"]),
                "resident_payload_equal_to_raven": True,
            }
            for label in ("diffuse", "emissive")
        },
        "opaque_donor_fields": {
            "material_payload_byte_identical": True,
            "material_qword_0x10": f"{raven_q10:016X}",
            "material_qword_0x20": f"{raven_q20:016X}",
            "map_model_payload_byte_identical": True,
            "model_group_payloads_mutated": False,
            "unexplained_scalar_fields_changed": False,
        },
        "accounting": {key: value for key, value in accounting.items()
                       if not key.startswith("source_")},
        "bookkeeping_ledger": bookkeeping_ledger,
        "raven_to_twin_record_ledger": clone_ledger,
        "all_twin_record_differences_classified": True,
        "unexplained_changed_payload_bytes": 0,
        "preserved_named_records": preservation,
        "original_raven_records_byte_identical": True,
        "stock_dock_boatdock_records_byte_identical": True,
        "parse_serialize_roundtrip_exact": True,
        "normalized_to_frozen_raven_exact": True,
    }


def parse_dcb_chunks(raw: bytes) -> list[dict]:
    chunks = []
    offset = 0
    while offset < len(raw):
        check(offset + 96 <= len(raw), "truncated DCB header")
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        check(flags == 0x10, "unexpected DCB flags")
        start = offset + 96
        end = start + size
        padded = (end + 15) & ~15
        check(padded <= len(raw), "truncated DCB payload")
        chunks.append({"kind": kind, "header": offset, "start": start,
                       "end": end, "padded": padded, "size": size})
        offset = padded
    check(offset == len(raw), "DCB chunk walk did not end exactly")
    return chunks


def one_chunk(chunks: list[dict], kind: int) -> dict:
    hits = [chunk for chunk in chunks if chunk["kind"] == kind]
    check(len(hits) == 1, f"expected one DCB chunk {kind}")
    return hits[0]


def dcb_rows(data: bytes) -> tuple[int, list[dict], int]:
    count = struct.unpack_from("<I", data, 8)[0]
    end = GOP_BASE + count * GOP_ROW
    check(end <= len(data), "GOPool exceeds data chunk")
    rows = []
    for index in range(count):
        at = GOP_BASE + index * GOP_ROW
        uid, capacity = struct.unpack_from("<QH", data, at)
        rows.append({"index": index, "uid": uid, "capacity": capacity,
                     "raw": bytes(data[at:at + GOP_ROW])})
    return count, rows, end


def build_ui_dcb(source: bytes) -> tuple[bytes, dict]:
    check(sha_bytes(source) == FILES["exec/dc/pc_le/wad_r_ui.dcb"],
          "wad_r_ui.dcb is not frozen Raven production")
    chunks = parse_dcb_chunks(source)
    check([row["kind"] for row in chunks] == [11, 12, 13, 14, 15],
          "wad_r_ui chunk order changed")
    data_chunk = one_chunk(chunks, 12)
    data = bytearray(source[data_chunk["start"]:data_chunk["end"]])
    count, rows, pool_end = dcb_rows(data)
    check(count == 257, f"expected 257 frozen GOPool rows, found {count}")
    check(not any(row["uid"] == TWIN_MAP_HASH for row in rows), "Twin GOPool row exists")
    raven = [row for row in rows if row["uid"] == RAVEN_MAP_HASH]
    check(len(raven) == 1 and raven[0]["index"] == 255 and raven[0]["capacity"] == 1,
          "frozen Raven map GOPool row changed")
    ptr10 = struct.unpack_from("<q", data, 0x10)[0]
    ptr20 = struct.unpack_from("<q", data, 0x20)[0]
    check(ptr10 == pool_end - GOP_ROW and ptr20 == pool_end,
          "frozen GOPool tail pointer relation changed")

    inserted = struct.pack("<QH6x", TWIN_MAP_HASH, 1)
    candidate_data = bytearray(data[:pool_end] + inserted + data[pool_end:])
    struct.pack_into("<I", candidate_data, 8, count + 1)
    struct.pack_into("<q", candidate_data, 0x10, ptr10 + GOP_ROW)
    struct.pack_into("<q", candidate_data, 0x20, ptr20 + GOP_ROW)
    header = bytearray(source[data_chunk["header"]:data_chunk["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = (source[:data_chunk["header"]] + bytes(header) + bytes(candidate_data) +
                 source[data_chunk["end"]:])

    after_chunks = parse_dcb_chunks(candidate)
    after_data_chunk = one_chunk(after_chunks, 12)
    after_data = candidate[after_data_chunk["start"]:after_data_chunk["end"]]
    new_count, new_rows, new_end = dcb_rows(after_data)
    twin = [row for row in new_rows if row["uid"] == TWIN_MAP_HASH]
    check(new_count == 258 and len(twin) == 1 and twin[0]["index"] == 257
          and twin[0]["capacity"] == 1, "Twin GOPool row shape changed")
    check(after_data[GOP_BASE:pool_end] == data[GOP_BASE:pool_end],
          "existing GOPool row changed")
    check(after_data[new_end:] == data[pool_end:], "GOPool tail changed instead of shifting")

    normalized_data = bytearray(after_data[:pool_end] + after_data[pool_end + GOP_ROW:])
    struct.pack_into("<I", normalized_data, 8, count)
    struct.pack_into("<q", normalized_data, 0x10, ptr10)
    struct.pack_into("<q", normalized_data, 0x20, ptr20)
    normalized_header = bytearray(candidate[after_data_chunk["header"]:after_data_chunk["start"]])
    struct.pack_into("<I", normalized_header, 4, len(normalized_data))
    normalized = (candidate[:after_data_chunk["header"]] + bytes(normalized_header) +
                  bytes(normalized_data) + candidate[after_data_chunk["end"]:])
    check(normalized == source, "Twin GOPool inverse normalization is not frozen Raven")
    return candidate, {
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "source_rows": count,
        "candidate_rows": new_count,
        "twin_row": {"index": twin[0]["index"], "hash": f"{TWIN_MAP_HASH:016X}",
                     "capacity": twin[0]["capacity"]},
        "known_identity_changes": ["new folded loader hash GOPool row"],
        "explicitly_justified_changes": [
            "GOPool count", "GOPool tail pointers", "data chunk size"],
        "all_existing_rows_byte_identical": True,
        "raven_row_byte_identical": True,
        "non_data_chunks_byte_identical": True,
        "normalized_to_frozen_raven_exact": True,
        "unexplained_changed_payload_bytes": 0,
    }


def load_native_module():
    return load_module("raven_twin_native", HERE.parent / "v0.10.3" / "inspect-native-markers.py")


def align_blob(blob: bytearray, boundary: int = 16) -> int:
    blob.extend(b"\0" * ((-len(blob)) % boundary))
    return len(blob)


def replace_array_pointer(blob: bytearray, field: int, start: int, count: int) -> None:
    struct.pack_into("<qI", blob, field, start - field, count)


def rebase_pointer(source, source_field: int, blob: bytearray,
                   destination_field: int, relocations: set[int]) -> None:
    check(source_field in source.relocations, f"source relocation missing: {source_field:#x}")
    delta = source.unpack("<q", source_field)[0]
    target = source_field + delta if delta else None
    new_delta = 0 if target is None else target - destination_field
    struct.pack_into("<q", blob, destination_field, new_delta)
    relocations.add(destination_field)


def rebuild_dcb_bytes(source, new_blob: bytes, relocations: set[int]) -> bytes:
    relocation_payload = struct.pack(
        f"<I{len(relocations)}I", len(relocations), *sorted(relocations))
    replacements = {12: bytes(new_blob), 15: relocation_payload}
    rebuilt = bytearray()
    for chunk in parse_dcb_chunks(source.raw):
        header = bytearray(source.raw[chunk["header"]:chunk["start"]])
        payload = source.raw[chunk["start"]:chunk["end"]]
        if chunk["kind"] in replacements:
            payload = replacements[chunk["kind"]]
        struct.pack_into("<I", header, 4, len(payload))
        rebuilt.extend(header)
        rebuilt.extend(payload)
        rebuilt.extend(b"\0" * ((-len(rebuilt)) % 16))
    return bytes(rebuilt)


def iter_markers(master):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        realm_uid = master.unpack("<Q", realm)[0]
        for region in master.array(realm + 0x30, 0x68):
            region_uid = master.unpack("<Q", region)[0]
            for marker in master.array(region + 0x38, 0x48):
                yield realm_uid, region_uid, region, marker


def marker_snapshot(master) -> list[dict]:
    rows = []
    for realm, region, _region_offset, marker in iter_markers(master):
        uid = master.unpack("<Q", marker)[0]
        canonical = bytearray(master.blob[marker:marker + 0x48])
        canonical[0x08:0x10] = bytes(8)
        canonical[0x20:0x28] = bytes(8)
        rows.append({
            "realm": f"{realm:016X}",
            "region": f"{region:016X}",
            "uid": f"{uid:016X}",
            "icon": master.string(marker + 8),
            "flags": [f"{master.unpack('<Q', field)[0]:016X}"
                      for field in master.array(marker + 0x20, 8)],
            "canonical": bytes(canonical),
            "offset": marker,
        })
    return rows


def coordinate_snapshot(coords) -> list[dict]:
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    rows = []
    for offset in coords.array(field, 0x28):
        uid = coords.unpack("<Q", offset)[0]
        canonical = bytearray(coords.blob[offset:offset + 0x28])
        canonical[0x08:0x10] = bytes(8)
        rows.append({
            "uid": f"{uid:016X}",
            "wad": coords.string(offset + 8),
            "position": list(coords.unpack("<3e", offset + 0x10)),
            "canonical": bytes(canonical),
            "offset": offset,
        })
    return rows


def parse_native_candidate(native, path: Path, raw: bytes):
    with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f"completionist-{path.stem}-", suffix=path.suffix,
            delete=False) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        temp_path = Path(stream.name)
    try:
        parsed = native.Dcb(temp_path)
        check(parsed.raw == raw, f"DCB parse changed bytes: {path.name}")
        return parsed
    finally:
        temp_path.unlink(missing_ok=True)


def build_mapmaster(source_path: Path, output_path: Path) -> tuple[bytes, dict]:
    native = load_native_module()
    source = native.Dcb(source_path)
    check(sha_bytes(source.raw) == FILES["exec/dc/pc_le/mapmaster.dcb"],
          "mapmaster.dcb is not frozen Raven production")
    before_rows = marker_snapshot(source)
    raven_rows = [row for row in before_rows if row["uid"] == f"{RAVEN_MARKER_UID:016X}"]
    check(len(raven_rows) == 1, "frozen Raven marker is not unique")
    raven = raven_rows[0]
    check(raven["realm"] == f"{MIDGARD_REALM:016X}"
          and raven["region"] == f"{VEITHURGARD_REGION:016X}"
          and raven["icon"] == RAVEN_MAP_GO, "frozen Raven marker contract changed")
    region_offset = next(region for realm, region_uid, region, marker in iter_markers(source)
                         if realm == MIDGARD_REALM and region_uid == VEITHURGARD_REGION
                         and marker == raven["offset"])
    array_field = region_offset + 0x38
    old_offsets = list(source.array(array_field, 0x48))

    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    new_start = align_blob(blob)
    for old_offset in old_offsets:
        blob.extend(source.blob[old_offset:old_offset + 0x48])
    twin_offset = len(blob)
    blob.extend(source.blob[raven["offset"]:raven["offset"] + 0x48])
    twin_icon_offset = len(blob)
    blob.extend(TWIN_MAP_GO.encode("ascii") + b"\0")

    for index, old_offset in enumerate(old_offsets):
        destination = new_start + index * 0x48
        rebase_pointer(source, old_offset + 0x08, blob, destination + 0x08, relocations)
        rebase_pointer(source, old_offset + 0x20, blob, destination + 0x20, relocations)
    struct.pack_into("<Q", blob, twin_offset, TWIN_MARKER_UID)
    struct.pack_into("<q", blob, twin_offset + 0x08, twin_icon_offset - (twin_offset + 0x08))
    relocations.add(twin_offset + 0x08)
    rebase_pointer(source, raven["offset"] + 0x20, blob, twin_offset + 0x20, relocations)
    replace_array_pointer(blob, array_field, new_start, len(old_offsets) + 1)
    check(array_field in relocations, "marker array relocation missing")

    candidate = rebuild_dcb_bytes(source, blob, relocations)
    parsed = parse_native_candidate(native, output_path, candidate)
    after_rows = marker_snapshot(parsed)
    twin_rows = [row for row in after_rows if row["uid"] == f"{TWIN_MARKER_UID:016X}"]
    check(len(twin_rows) == 1, "Twin marker is not unique")
    twin = twin_rows[0]
    check(twin["realm"] == raven["realm"] and twin["region"] == raven["region"],
          "Twin marker realm/region changed")
    check(twin["icon"] == TWIN_MAP_GO and twin["flags"] == raven["flags"],
          "Twin marker does not preserve Raven shape")
    filtered = [row for row in after_rows if row["uid"] != f"{TWIN_MARKER_UID:016X}"]
    check([(row["realm"], row["region"], row["uid"], row["icon"], row["flags"], row["canonical"])
           for row in filtered] ==
          [(row["realm"], row["region"], row["uid"], row["icon"], row["flags"], row["canonical"])
           for row in before_rows], "pre-existing marker records changed semantically")
    for row in before_rows:
        offset = row["offset"]
        check(parsed.blob[offset:offset + 0x48] == source.blob[offset:offset + 0x48],
              f"original marker bytes changed at original offset {offset:#x}")
    raven_after = [row for row in after_rows if row["uid"] == f"{RAVEN_MARKER_UID:016X}"][0]
    check(raven_after["canonical"] == raven["canonical"], "active Raven marker payload changed")

    normalized_blob = bytearray(parsed.blob[:len(source.blob)])
    normalized_blob[array_field:array_field + 16] = source.blob[array_field:array_field + 16]
    normalized = rebuild_dcb_bytes(source, normalized_blob, set(source.relocations))
    check(normalized == source.raw, "mapmaster inverse normalization is not frozen Raven")

    donor = source.blob[raven["offset"]:raven["offset"] + 0x48]
    twin_raw = parsed.blob[twin["offset"]:twin["offset"] + 0x48]
    changed = [index for index, pair in enumerate(zip(donor, twin_raw)) if pair[0] != pair[1]]
    allowed = set(range(0x00, 0x08)) | set(range(0x08, 0x10)) | set(range(0x20, 0x28))
    check(not (set(changed) - allowed), "mapmaster Twin row has unexplained bytes")
    return candidate, {
        "source_sha256": sha_bytes(source.raw),
        "candidate_sha256": sha_bytes(candidate),
        "source_marker_count": len(before_rows),
        "candidate_marker_count": len(after_rows),
        "twin": {
            "name": TWIN_MARKER_NAME,
            "uid": f"{TWIN_MARKER_UID:016X}",
            "icon": TWIN_MAP_GO,
            "realm": twin["realm"],
            "region": twin["region"],
            "flags_equal_to_raven": True,
        },
        "raven_to_twin_record_ledger": [
            {"field": "+0x00..+0x07", "category": "known_identity",
             "reason": "new marker UID derived from new marker name"},
            {"field": "+0x08..+0x0F", "category": "known_local_reference",
             "reason": "relative pointer to new Twin map GameObject loader name"},
            {"field": "+0x20..+0x27", "category": "known_local_reference",
             "reason": "rebased relative pointer to unchanged Raven flag array"},
            {"field": "appended NUL-terminated string", "category": "known_identity",
             "reason": "new Twin map GameObject loader name"},
        ],
        "explicitly_justified_container_changes": [
            "region marker-array pointer/count", "rebased pointers in copied array",
            "data chunk size", "relocation table/count"],
        "original_marker_records_semantically_identical": True,
        "original_marker_records_physical_bytes_at_original_offsets_identical": True,
        "original_raven_marker_physical_bytes_at_original_offset_identical": True,
        "original_raven_marker_canonical_bytes_identical": True,
        "normalized_to_frozen_raven_exact": True,
        "unexplained_changed_payload_bytes": 0,
    }


def build_mapcoords(source_path: Path, output_path: Path) -> tuple[bytes, dict]:
    native = load_native_module()
    source = native.Dcb(source_path)
    check(sha_bytes(source.raw) == FILES["exec/dc/pc_le/mapcoords.dcb"],
          "mapcoords.dcb is not frozen Raven production")
    before_rows = coordinate_snapshot(source)
    raven_rows = [row for row in before_rows if row["uid"] == f"{RAVEN_MARKER_UID:016X}"]
    check(len(raven_rows) == 1, "frozen Raven coordinate is not unique")
    raven = raven_rows[0]
    check(raven["wad"] == RAVEN_WAD and tuple(raven["position"]) == RAVEN_POSITION,
          "frozen Raven coordinate contract changed")
    array_field = source.root("MAP_COORDS_PERM_DATA", 0x40A)
    old_offsets = list(source.array(array_field, 0x28))

    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    new_start = align_blob(blob)
    for old_offset in old_offsets:
        blob.extend(source.blob[old_offset:old_offset + 0x28])
    twin_offset = len(blob)
    blob.extend(source.blob[raven["offset"]:raven["offset"] + 0x28])
    for index, old_offset in enumerate(old_offsets):
        rebase_pointer(source, old_offset + 0x08, blob,
                       new_start + index * 0x28 + 0x08, relocations)
    struct.pack_into("<Q", blob, twin_offset, TWIN_MARKER_UID)
    rebase_pointer(source, raven["offset"] + 0x08, blob, twin_offset + 0x08, relocations)
    struct.pack_into("<3e", blob, twin_offset + 0x10, *TWIN_POSITION)
    replace_array_pointer(blob, array_field, new_start, len(old_offsets) + 1)
    check(array_field in relocations, "mapcoords array relocation missing")

    candidate = rebuild_dcb_bytes(source, blob, relocations)
    parsed = parse_native_candidate(native, output_path, candidate)
    after_rows = coordinate_snapshot(parsed)
    twin_rows = [row for row in after_rows if row["uid"] == f"{TWIN_MARKER_UID:016X}"]
    check(len(twin_rows) == 1, "Twin coordinate is not unique")
    twin = twin_rows[0]
    authored_position = struct.unpack("<3e", struct.pack("<3e", *TWIN_POSITION))
    check(twin["wad"] == raven["wad"] and tuple(twin["position"]) == authored_position,
          "Twin coordinate does not match authored position")
    filtered = [row for row in after_rows if row["uid"] != f"{TWIN_MARKER_UID:016X}"]
    check([(row["uid"], row["wad"], row["position"], row["canonical"])
           for row in filtered] ==
          [(row["uid"], row["wad"], row["position"], row["canonical"])
           for row in before_rows], "pre-existing coordinate records changed semantically")
    for row in before_rows:
        offset = row["offset"]
        check(parsed.blob[offset:offset + 0x28] == source.blob[offset:offset + 0x28],
              f"original coordinate bytes changed at original offset {offset:#x}")
    raven_after = [row for row in after_rows if row["uid"] == f"{RAVEN_MARKER_UID:016X}"][0]
    check(raven_after["canonical"] == raven["canonical"], "active Raven coordinate payload changed")

    normalized_blob = bytearray(parsed.blob[:len(source.blob)])
    normalized_blob[array_field:array_field + 16] = source.blob[array_field:array_field + 16]
    normalized = rebuild_dcb_bytes(source, normalized_blob, set(source.relocations))
    check(normalized == source.raw, "mapcoords inverse normalization is not frozen Raven")

    donor = source.blob[raven["offset"]:raven["offset"] + 0x28]
    twin_raw = parsed.blob[twin["offset"]:twin["offset"] + 0x28]
    changed = [index for index, pair in enumerate(zip(donor, twin_raw)) if pair[0] != pair[1]]
    allowed = set(range(0x00, 0x08)) | set(range(0x08, 0x10)) | set(range(0x10, 0x16))
    check(not (set(changed) - allowed), "mapcoords Twin row has unexplained bytes")
    return candidate, {
        "source_sha256": sha_bytes(source.raw),
        "candidate_sha256": sha_bytes(candidate),
        "source_coordinate_count": len(before_rows),
        "candidate_coordinate_count": len(after_rows),
        "twin": {
            "uid": f"{TWIN_MARKER_UID:016X}",
            "wad": twin["wad"],
            "position": twin["position"],
            "position_offset_from_raven_metres": round(math.dist(twin["position"], raven["position"]), 6),
        },
        "raven_to_twin_record_ledger": [
            {"field": "+0x00..+0x07", "category": "known_identity",
             "reason": "new marker UID"},
            {"field": "+0x08..+0x0F", "category": "known_local_reference",
             "reason": "rebased pointer to unchanged Raven WAD name"},
            {"field": "+0x10..+0x15", "category": "marker_position",
             "reason": "deliberate 32-metre east offset so both map icons can be observed"},
        ],
        "explicitly_justified_container_changes": [
            "coordinate-array pointer/count", "rebased pointers in copied array",
            "data chunk size", "relocation table/count"],
        "original_coordinate_records_semantically_identical": True,
        "original_coordinate_records_physical_bytes_at_original_offsets_identical": True,
        "original_raven_coordinate_physical_bytes_at_original_offset_identical": True,
        "original_raven_coordinate_canonical_bytes_identical": True,
        "normalized_to_frozen_raven_exact": True,
        "unexplained_changed_payload_bytes": 0,
    }


def assert_output_scope(source_root: Path, output_root: Path, report_path: Path) -> None:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    report_path = report_path.resolve()
    build_root = (REPO / "build").resolve()
    archive_root = (REPO / "archive" / "field-logs").resolve()
    check(output_root.is_relative_to(build_root), "offline candidate must stay in repo build tree")
    check(report_path.is_relative_to(archive_root), "proof report must stay in archive/field-logs")
    check(not output_root.is_relative_to(source_root) and not source_root.is_relative_to(output_root),
          "offline output and Raven source must not overlap")
    check(not report_path.is_relative_to(source_root), "proof report must stay outside Raven source")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raven-root", type=Path,
                        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    parser.add_argument("--output-root", type=Path,
                        default=REPO / "build/v0.10.4-raven-twin-stage-a/offline/candidate/game-root")
    parser.add_argument("--report", type=Path,
                        default=REPO / "archive/field-logs/completionist-v104-raven-twin-stage-a-offline.json")
    args = parser.parse_args()

    source_root = args.raven_root.resolve()
    output_root = args.output_root.resolve()
    report_path = args.report.resolve()
    check(source_root.is_dir(), f"Raven source root missing: {source_root}")
    assert_output_scope(source_root, output_root, report_path)
    source_paths = {relative: source_root / relative for relative in FILES}
    for relative, expected in FILES.items():
        check(sha_file(source_paths[relative]) == expected,
              f"frozen Raven source mismatch: {relative}")
    source_hashes_before = {relative: sha_file(path) for relative, path in source_paths.items()}

    expected_outputs = {output_root / relative for relative in FILES}
    if output_root.exists():
        unexpected = {path for path in output_root.rglob("*") if path.is_file()} - expected_outputs
        check(not unexpected, f"unexpected stale output file: {sorted(str(p) for p in unexpected)}")

    wad_candidate, wad_report = build_wad(source_paths["exec/wad/pc_le/r_ui.wad"].read_bytes())
    ui_candidate, ui_report = build_ui_dcb(source_paths["exec/dc/pc_le/wad_r_ui.dcb"].read_bytes())
    master_output = output_root / "exec/dc/pc_le/mapmaster.dcb"
    coords_output = output_root / "exec/dc/pc_le/mapcoords.dcb"
    master_candidate, master_report = build_mapmaster(
        source_paths["exec/dc/pc_le/mapmaster.dcb"], master_output)
    coords_candidate, coords_report = build_mapcoords(
        source_paths["exec/dc/pc_le/mapcoords.dcb"], coords_output)

    outputs = {
        "exec/wad/pc_le/r_ui.wad": wad_candidate,
        "exec/dc/pc_le/wad_r_ui.dcb": ui_candidate,
        "exec/dc/pc_le/mapmaster.dcb": master_candidate,
        "exec/dc/pc_le/mapcoords.dcb": coords_candidate,
    }
    for relative, raw in outputs.items():
        path = output_root / relative
        write_bytes_atomic(output_root, path, raw, f"offline output {relative}")
    disk_files = {path.relative_to(output_root).as_posix()
                  for path in output_root.rglob("*") if path.is_file()}
    check(disk_files == set(FILES), f"Stage A output must contain exactly four files: {disk_files}")

    source_hashes_after = {relative: sha_file(path) for relative, path in source_paths.items()}
    check(source_hashes_after == source_hashes_before, "frozen Raven source changed during build")
    check(folded_name_hash(TWIN_MARKER_NAME) == TWIN_MARKER_UID, "Twin marker UID/name mismatch")
    check(folded_name_hash(TWIN_MAP_GO) == TWIN_MAP_HASH, "Twin map loader hash/name mismatch")

    report = {
        "schema": 1,
        "result": RESULT,
        "branch_contract": "codex/v104-raven-production",
        "expected_head_at_request": "036628c9870d1040b6a4219f7f9fc3cf0a8befef",
        "source": {
            "kind": "current frozen runtime-proven Raven implementation",
            "root": str(source_root),
            "hashes_before": source_hashes_before,
            "hashes_after": source_hashes_after,
            "source_files_byte_identical_after_build": True,
            "candidate_1_used": False,
            "candidate_2_used": False,
            "candidate_3_used": False,
            "old_nornir_lifecycle_artifacts_used": False,
        },
        "stage": {
            "name": "A",
            "scope": "map-only Raven Twin with Raven artwork",
            "runtime_question": "Can God of War open the map with original Raven + Raven Twin using two distinct identities but the same proven Raven artwork?",
            "compass_inworld_added": False,
            "lifecycle_added": False,
            "nornir_art_added": False,
            "mapmenu_modified": False,
            "mainhud_modified": False,
            "chest_lua_modified": False,
        },
        "identities": {
            "marker_name": TWIN_MARKER_NAME,
            "marker_uid": f"{TWIN_MARKER_UID:016X}",
            "map_game_object_loader_name": TWIN_MAP_GO,
            "map_game_object_folded_hash": f"{TWIN_MAP_HASH:016X}",
        },
        "field_policy": {
            "proven_identities": [
                "WAD resource names", "WAD record IDs used by dependency links",
                "texture definition/file hash IDs", "texture GPU/user hash IDs",
                "map GameObject loader name and folded hash", "marker name and marker UID",
            ],
            "known_local_references": [
                "WAD dependency names and IDs", "prototype payload self-ID",
                "root prototype ID", "texture-definition GPU user hash",
                "DCB relative pointers and array pointers",
            ],
            "opaque_donor_fields": [
                "material payload +0x10", "material payload +0x20",
                "all other material payload bytes", "map model payload",
                "ModelGroup payloads", "unexplained scalar fields",
            ],
            "opaque_donor_fields_preserved_byte_for_byte": True,
        },
        "files": {
            relative: {"bytes": len(raw), "sha256": sha_bytes(raw)}
            for relative, raw in outputs.items()
        },
        "proofs": {
            "r_ui_wad": wad_report,
            "wad_r_ui_dcb": ui_report,
            "mapmaster_dcb": master_report,
            "mapcoords_dcb": coords_report,
            "exact_normalization_to_frozen_raven_for_all_four_files": True,
            "original_raven_records_byte_identical": True,
            "stock_dock_boatdock_records_byte_identical": True,
            "all_twin_differences_classified": True,
            "unexplained_changed_payload_bytes": 0,
        },
        "stage_b_design_only": {
            "implemented": False,
            "allowed_future_delta_after_stage_a_runtime_success": [
                "Twin diffuse resident pixel payload",
                "Twin emissive resident pixel payload",
                "matching external texpack stream bytes under unchanged Twin texture identities",
            ],
            "topology_and_identity_bytes_must_equal_stage_a": True,
            "gate": "Do not build Stage B until Stage A runtime success is archived.",
        },
        "safety": {
            "god_of_war_launched": False,
            "installed_game_files_written": False,
            "save_files_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "runtime_installer_executed": False,
            "linked_output_destinations_rejected": True,
            "atomic_candidate_and_report_writes": True,
        },
        "ready_for_transactional_installer_creation": True,
        "ready_for_runtime_test": True,
        "runtime_test_performed": False,
    }
    write_bytes_atomic(
        (REPO / "archive" / "field-logs").resolve(), report_path,
        (json.dumps(report, indent=2) + "\n").encode("utf-8"), "offline proof report")
    print(RESULT)
    print("  source: current frozen runtime-proven Raven")
    print("  files: 4 map-only files")
    print("  Raven art payloads copied exactly: true")
    print("  opaque Raven fields preserved: true")
    print("  all Twin byte differences classified: true")
    print("  exact four-file inverse normalization: true")
    print("  game files written: false")
    print("  runtime test performed: false")
    print(f"  report: {report_path}")


if __name__ == "__main__":
    main()
