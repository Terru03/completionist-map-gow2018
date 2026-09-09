#!/usr/bin/env python3
"""Registry-driven collectible resource build and validation.

This module writes only caller-selected offline outputs. It never opens game
process, changes live files, writes saves, or changes marker/progression state.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REGISTRY_PATH = REPO / "config/collectibles/v0.10.4/collectibles.json"
FROZEN_RAVEN_WAD_SHA256 = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
FROZEN_RAVEN_UI_DCB_SHA256 = "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d"
FROZEN_RAVEN_PERM_DCB_SHA256 = "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5"
FROZEN_RAVEN_PERM_DCB_SHA256 = "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5"
DONOR_MATERIAL_Q20 = 0xD595197B0961F689
STOCK_MODEL_GROUPS = {
    "map": ("MG_mapicondock_0", "44b11676af9c4e0ff860108fd46b0b32"),
    "hud": ("MG_boatdock_0", "c3f6b4c5a8270df607ea3e6e7f891292"),
}
STOCK_DONOR_NAMES = (
    "MAT_0C599DC8DC7E2170", "MDL_mapicondock", "MG_mapicondock_0",
    "gomapicondock", "MDL_boatdock", "MG_boatdock_0", "goboatdock",
)
RESOURCE_ROLES = (
    "map_root", "map_prototype", "map_model", "material", "diffuse",
    "emissive", "hud_root", "hud_prototype", "hud_model",
)
GROUP_ROLES = (
    "material", "map_model", "map_prototype", "map_root",
    "hud_model", "hud_prototype", "hud_root",
)
ADAPTERS = {
    "killable_collectible", "opened_chest", "pickup_collectible",
    "interact_read_collectible", "parent_puzzle_collectible",
    "child_puzzle_element", "synthetic_test",
}


class FrameworkError(ValueError):
    pass


def check(ok: bool, message: str) -> None:
    if not ok:
        raise FrameworkError(message)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def _hex64(value: Any, label: str) -> int:
    check(isinstance(value, str) and len(value) == 16, f"{label}: need 16 hex chars")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise FrameworkError(f"{label}: bad hex") from exc


def _hex128(value: Any, label: str) -> bytes:
    check(isinstance(value, str) and len(value) == 32, f"{label}: need 32 hex chars")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise FrameworkError(f"{label}: bad hex") from exc


def texture_definition_id(file_hash: int) -> bytes:
    return bytes.fromhex("5458455400455255") + struct.pack(
        "<II", file_hash >> 32, file_hash & 0xFFFFFFFF)


def texture_gpu_id(user_hash: int) -> bytes:
    return bytes(8) + struct.pack("<II", user_hash >> 32, user_hash & 0xFFFFFFFF)


def _deterministic_bytes(namespace: str, key: str, role: str, name: str) -> bytes:
    seed = f"{namespace}:{key}:{role}:{name}".encode("ascii")
    return hashlib.sha256(seed).digest()


def _resolved_definition(registry: dict, definition: dict) -> dict:
    row = copy.deepcopy(definition)
    if row.get("status") != "synthetic_test":
        return row
    namespace = registry["deterministic_namespace"]
    key = row["key"]
    resources = row["resources"]
    for role in GROUP_ROLES:
        resource = resources[role]
        if resource.get("id") is None:
            resource["id"] = _deterministic_bytes(
                namespace, key, f"resource:{role}", resource["name"])[:16].hex()
    material = resources["material"]
    if material.get("qword_0x10") is None:
        material["qword_0x10"] = _deterministic_bytes(
            namespace, key, "material:qword_0x10", material["name"])[:8].hex().upper()
    for label in ("diffuse", "emissive"):
        texture = resources[label]
        if texture.get("file_hash") is None:
            texture["file_hash"] = _deterministic_bytes(
                namespace, key, f"texture:{label}:file", texture["name"])[:8].hex().upper()
        if texture.get("user_hash") is None:
            texture["user_hash"] = _deterministic_bytes(
                namespace, key, f"texture:{label}:user", texture["name"])[8:16].hex().upper()
        file_hash = _hex64(texture["file_hash"], f"{key}.{label}.file_hash")
        user_hash = _hex64(texture["user_hash"], f"{key}.{label}.user_hash")
        texture["definition_id"] = texture_definition_id(file_hash).hex()
        texture["gpu_id"] = texture_gpu_id(user_hash).hex()
    for identity_role in ("map_icon", "compass"):
        identity = row["identities"][identity_role]
        if identity is not None and identity.get("folded_hash") is None:
            identity["folded_hash"] = f"{folded_name_hash(identity['game_object']):016X}"
    compass = row["identities"]["compass"]
    if compass.get("class_uid") is None:
        compass["class_uid"] = f"{folded_name_hash(compass['class_name']):016X}"
    in_world = row["identities"]["in_world"]
    if in_world.get("uid") is None:
        in_world["uid"] = f"{folded_name_hash(in_world['name']):016X}"
    by_role = {item["role"]: item for item in row["gopool"]}
    for role in ("map", "hud"):
        if by_role[role].get("folded_hash") is None:
            by_role[role]["folded_hash"] = f"{folded_name_hash(by_role[role]['name']):016X}"
    return row


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    check(path.is_file(), f"registry missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    check(raw.get("schema") == 1, "registry schema changed")
    check(isinstance(raw.get("deterministic_namespace"), str), "deterministic namespace missing")
    check(isinstance(raw.get("collectibles"), list), "collectibles must be list")
    raw["collectibles"] = [_resolved_definition(raw, row) for row in raw["collectibles"]]
    validate_registry(raw)
    return raw


def definitions_by_key(registry: dict) -> dict[str, dict]:
    return {row["key"]: row for row in registry["collectibles"]}


def definition_for(registry: dict, key: str) -> dict:
    rows = definitions_by_key(registry)
    check(key in rows, f"collectible not found: {key}")
    return copy.deepcopy(rows[key])


def _collect_unique(values: list[tuple[str, str]], label: str) -> None:
    seen: dict[str, str] = {}
    for owner, value in values:
        folded = value.lower()
        check(folded not in seen, f"duplicate {label}: {value} ({seen.get(folded)} and {owner})")
        seen[folded] = owner


def validate_registry(registry: dict) -> dict:
    rows = registry.get("collectibles", [])
    keys = [row.get("key") for row in rows]
    check(all(isinstance(key, str) and key for key in keys), "each collectible needs key")
    check(len(set(keys)) == len(keys), "duplicate collectible key")
    key_set = set(keys)
    resource_names: list[tuple[str, str]] = []
    resource_ids: list[tuple[str, str]] = []
    material_q10: list[tuple[str, str]] = []
    gopool_hashes: list[tuple[str, str]] = []

    for row in rows:
        key = row["key"]
        check(row.get("lifecycle", {}).get("adapter") in ADAPTERS,
              f"{key}: unknown lifecycle adapter")
        parent = row.get("parent_collectible_key")
        check(parent is None or parent in key_set, f"{key}: parent missing: {parent}")
        check(parent != key, f"{key}: cannot parent itself")
        unresolved = row.get("unresolved", [])
        if row.get("status") in {"placeholder", "synthetic_test"}:
            check(bool(unresolved), f"{key}: unresolved facts need reason")
        resources = row.get("resources", {})
        complete_resources = set(RESOURCE_ROLES).issubset(resources)
        if row.get("build", {}).get("enabled"):
            check(complete_resources, f"{key}: build resources incomplete")
        if not complete_resources:
            continue
        for role in RESOURCE_ROLES:
            name = resources[role].get("name")
            check(isinstance(name, str) and name, f"{key}.{role}: name missing")
            check(len(name.encode("ascii")) <= 55, f"{key}.{role}: WAD name too long")
            resource_names.append((f"{key}.{role}", name))
        for role in GROUP_ROLES:
            rid = resources[role].get("id")
            _hex128(rid, f"{key}.{role}.id")
            resource_ids.append((f"{key}.{role}", rid))
        for label in ("diffuse", "emissive"):
            texture = resources[label]
            file_hash = _hex64(texture.get("file_hash"), f"{key}.{label}.file_hash")
            user_hash = _hex64(texture.get("user_hash"), f"{key}.{label}.user_hash")
            def_id = _hex128(texture.get("definition_id"), f"{key}.{label}.definition_id")
            gpu_id = _hex128(texture.get("gpu_id"), f"{key}.{label}.gpu_id")
            check(def_id == texture_definition_id(file_hash), f"{key}.{label}: definition ID mismatch")
            check(gpu_id == texture_gpu_id(user_hash), f"{key}.{label}: GPU ID mismatch")
            resource_ids.extend([
                (f"{key}.{label}.definition", def_id.hex()),
                (f"{key}.{label}.gpu", gpu_id.hex()),
            ])
        material = resources["material"]
        _hex64(material.get("qword_0x10"), f"{key}.material.qword_0x10")
        check(_hex64(material.get("qword_0x20"), f"{key}.material.qword_0x20") == DONOR_MATERIAL_Q20,
              f"{key}: material +0x20 must preserve donor")
        material_q10.append((key, material["qword_0x10"]))

        policy = row.get("model_group_policy", {})
        for side in ("map", "hud"):
            expected_name, expected_id = STOCK_MODEL_GROUPS[side]
            item = policy.get(side, {})
            check(item.get("mode") == "share_stock", f"{key}.{side}: ModelGroup must share stock")
            check(item.get("name") == expected_name and item.get("id", "").lower() == expected_id,
                  f"{key}.{side}: stock ModelGroup identity changed")
            check(item.get("mutate_payload") is False, f"{key}.{side}: ModelGroup payload mutation forbidden")

        gopool = row.get("gopool", [])
        check([item.get("role") for item in gopool] == ["map", "hud"],
              f"{key}: GOPool needs map then hud")
        for item in gopool:
            expected_hash = folded_name_hash(item["name"])
            actual_hash = _hex64(item.get("folded_hash"), f"{key}.gopool.{item['role']}")
            check(actual_hash == expected_hash, f"{key}.{item['role']}: GOPool name hash mismatch")
            check(item.get("capacity") in (1, 2), f"{key}.{item['role']}: bad GOPool capacity")
            gopool_hashes.append((f"{key}.{item['role']}", item["folded_hash"]))
        check(folded_name_hash(resources["map_root"]["name"]) ==
              _hex64(gopool[0]["folded_hash"], f"{key}.map hash"),
              f"{key}: map root/GOPool hash mismatch")
        check(folded_name_hash(resources["hud_root"]["name"]) ==
              _hex64(gopool[1]["folded_hash"], f"{key}.hud hash"),
              f"{key}: HUD root/GOPool hash mismatch")
        compass = row["identities"]["compass"]
        in_world = row["identities"]["in_world"]
        check(compass is not None and in_world is not None, f"{key}: compass/in-world identity missing")
        check(_hex64(compass.get("class_uid"), f"{key}.compass.class_uid") ==
              folded_name_hash(compass["class_name"]), f"{key}: compass class UID mismatch")
        check(_hex64(in_world.get("uid"), f"{key}.in_world.uid") ==
              folded_name_hash(in_world["name"]), f"{key}: in-world UID mismatch")

    _collect_unique(resource_names, "resource name")
    _collect_unique(resource_ids, "resource ID")
    _collect_unique(material_q10, "material +0x10")
    _collect_unique(gopool_hashes, "GOPool hash")
    return {
        "collectible_count": len(rows),
        "build_enabled": [row["key"] for row in rows if row.get("build", {}).get("enabled")],
        "resource_names_unique": True,
        "resource_ids_unique": True,
        "material_q10_unique": True,
        "gopool_hashes_unique": True,
        "unknowns_explicit": True,
    }


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_v5():
    return _load_module(
        f"completionist_collectible_v5_{id(object())}",
        HERE / "build-nornir-map-hud-offline-v5.py")


def _resource_map(definition: dict) -> dict[str, str]:
    r = definition["resources"]
    return {
        "map_go": definition["identities"]["map_icon"]["game_object"],
        "map_root": r["map_root"]["name"],
        "map_proto": r["map_prototype"]["name"],
        "map_model": r["map_model"]["name"],
        "material": r["material"]["name"],
        "diffuse": r["diffuse"]["name"],
        "emissive": r["emissive"]["name"],
        "hud_go": definition["identities"]["compass"]["game_object"],
        "hud_root": r["hud_root"]["name"],
        "hud_proto": r["hud_prototype"]["name"],
        "hud_model": r["hud_model"]["name"],
    }


def _payloads_from_art_report(path: Path) -> dict[str, bytes]:
    check(path.is_file(), f"art report missing: {path}")
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    check(report.get("result") == "OFFLINE_NORNIR_RESIDENT_ART_BUILT", "art report result changed")
    rows = {row["label"]: row for row in report.get("rows", [])}
    check(set(rows) == {"diffuse", "emissive"}, "art report texture rows changed")
    output: dict[str, bytes] = {}
    expected = {
        "diffuse": (9228, "4912eca29c970d137f584f75627b2cfe30f3681652bec7762f96ff7e0e86e9e4"),
        "emissive": (4620, "ab37213e0c654b5ef7047d57b0b1f07f671ca1980a8528d39b8522995ba0244c"),
    }
    for label in ("diffuse", "emissive"):
        source = Path(rows[label]["output"])
        check(source.is_file(), f"resident payload missing: {source}")
        raw = source.read_bytes()
        size, digest = expected[label]
        check(len(raw) == size and sha_bytes(raw) == digest, f"{label}: resident payload changed")
        output[label] = raw
    return output


def _group_bounds(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    start = records[payload_index]["parent"]
    check(start is not None and records[start]["kind"] == 2, "payload lacks owner group")
    return start, logical.matching_group_end(records, start)


def _one_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(index, row) for index, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def _group_rows(logical, records: list[dict], payload_index: int) -> list[dict]:
    start, end = _group_bounds(logical, records, payload_index)
    return records[start:end + 1]


def _dependency(rows: list[dict], name: str, rid: bytes | None = None) -> dict:
    hits = [row for row in rows if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == name.lower() and (rid is None or row["id"] == rid)]
    check(len(hits) == 1, f"expected one dependency {name!r}, found {len(hits)}")
    return hits[0]


def _owner(logical, records: list[dict], index: int) -> str:
    start = records[index]["parent"]
    check(start is not None and records[start]["kind"] == 2, "dependency has no group owner")
    end = logical.matching_group_end(records, start)
    payloads = [records[i] for i in range(start + 1, end)
                if records[i]["kind"] == 1 and records[i]["data"]]
    check(bool(payloads), "dependency owner has no payload")
    return payloads[0]["name"]


def validate_reverse_ownership(definition: dict, evidence: dict) -> dict:
    resources = definition["resources"]
    expected = {
        "material": [resources["map_model"]["name"], resources["hud_model"]["name"]],
        "diffuse": [resources["material"]["name"]],
        "emissive": [resources["material"]["name"]],
        "map_model": [resources["map_prototype"]["name"]],
        "hud_model": [resources["hud_prototype"]["name"]],
        "map_prototype_payloads": [resources["map_prototype"]["name"],
                                   resources["map_root"]["name"]],
        "hud_prototype_payloads": [resources["hud_prototype"]["name"],
                                   resources["hud_root"]["name"]],
    }
    for role, owners in expected.items():
        check(evidence.get(role) == owners,
              f"{definition['key']}: {role} ownership leak: {evidence.get(role)}")
    check(evidence.get("map_root_parent_links") == 1,
          f"{definition['key']}: map root parent ownership leak")
    return {"valid": True, "expected": expected, "evidence": copy.deepcopy(evidence)}


def normalize_wad(logical, source_raw: bytes, candidate_records: list[dict], definition: dict) -> bytes:
    target = _resource_map(definition)
    resources = definition["resources"]
    stripped = copy.deepcopy(candidate_records)
    removal: set[int] = set()
    for key in ("material", "map_model", "map_proto", "map_root", "hud_model", "hud_proto", "hud_root"):
        index, _ = _one_payload(stripped, target[key])
        start, end = _group_bounds(logical, stripped, index)
        removal.update(range(start, end + 1))
    for label in ("diffuse", "emissive"):
        name = target[label]
        gpu = [i for i, row in enumerate(stripped) if row["name"].lower() == name.lower()
               and row["kind"] == 0x1D and row["flags"] == 0x80A1 and row["data"]]
        texdef = [i for i, row in enumerate(stripped) if row["name"].lower() == name.lower()
                  and row["kind"] == 1 and row["flags"] == 0x8021 and row["data"]]
        check(len(gpu) == len(texdef) == 1, f"{definition['key']}.{label}: texture shape changed")
        removal.update(gpu + texdef)
    root_id = _hex128(resources["map_root"]["id"], "map root id")
    refs = [i for i, row in enumerate(stripped) if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == target["map_root"].lower() and row["id"] == root_id]
    check(len(refs) == 1, "map root parent link changed")
    removal.add(refs[0])
    stripped = [row for index, row in enumerate(stripped) if index not in removal]
    source_payloads = logical.payload_records(logical.parse_wad(source_raw))
    stripped_payloads = logical.payload_records(stripped)
    stripped_payloads[0]["data"] = bytearray(source_payloads[0]["data"])
    stripped_payloads[1]["data"] = bytearray(source_payloads[1]["data"])
    return logical.serialize_wad(stripped)


def _art_payloads(base, source_records: list[dict], donor: dict, definition: dict,
                  art_report: Path | None) -> dict[str, bytes]:
    mode = definition["build"]["art_source"]
    if mode == "nornir_candidate3_resident_report":
        check(art_report is not None, "Nornir art report required")
        return _payloads_from_art_report(art_report)
    check(mode == "copy_donor_resident_bytes", f"unsupported art source: {mode}")
    donor_names = _resource_map(donor)
    return {
        label: bytes(base.unique_texture(source_records, donor_names[label], gpu=True)[1]["data"])
        for label in ("diffuse", "emissive")
    }


def build_collectible_wad(source_raw: bytes, registry: dict, key: str,
                          art_report: Path | None = None) -> tuple[bytes, dict]:
    check(sha_bytes(source_raw) == FROZEN_RAVEN_WAD_SHA256, "source WAD is not frozen Raven")
    definition = definition_for(registry, key)
    check(definition["build"]["enabled"] is True, f"{key}: build disabled")
    donor_key = definition["donors"].get("collectible_key")
    donor = definition_for(registry, donor_key)
    v5 = _load_v5()
    base = v5.base
    logical = base.load_module("build-raven-ui-logical-clone.py", f"collectible_logical_{key}")
    source_records = logical.parse_wad(source_raw)
    check(logical.serialize_wad(source_records) == source_raw, "source WAD round-trip changed")
    target = _resource_map(definition)
    donor_names = _resource_map(donor)
    resources = definition["resources"]
    payloads = _art_payloads(base, source_records, donor, definition, art_report)
    user_hashes = {label: _hex64(resources[label]["user_hash"], f"{key}.{label}.user")
                   for label in ("diffuse", "emissive")}
    file_hashes = {label: _hex64(resources[label]["file_hash"], f"{key}.{label}.file")
                   for label in ("diffuse", "emissive")}
    ids_by_name = {resources[role]["name"].lower(): _hex128(resources[role]["id"], f"{key}.{role}.id")
                   for role in GROUP_ROLES}

    base.RAVEN = {name: donor_names[name] for name in (
        "map_root", "map_proto", "map_model", "material", "diffuse",
        "emissive", "hud_root", "hud_proto", "hud_model")}
    base.NORNIR = dict(target)
    base.FILE_HASH = file_hashes
    base.MAP_GO_HASH = _hex64(definition["gopool"][0]["folded_hash"], f"{key}.map hash")
    base.HUD_GO_HASH = _hex64(definition["gopool"][1]["folded_hash"], f"{key}.hud hash")
    base.EXPECTED_RESIDENT = {
        label: (len(payloads[label]), sha_bytes(payloads[label])) for label in ("diffuse", "emissive")}
    base.deterministic_id = lambda name: ids_by_name[name.lower()]
    base.parse_art_report = lambda _path: ({"framework": key}, payloads, user_hashes)

    pre_rule, legacy_report = base.build_wad(source_raw, Path("registry-provided-art"))
    records = logical.parse_wad(pre_rule)
    material_index, material = _one_payload(records, target["material"])
    before_q10 = struct.unpack_from("<Q", material["data"], 0x10)[0]
    before_q20 = struct.unpack_from("<Q", material["data"], 0x20)[0]
    q10 = _hex64(resources["material"]["qword_0x10"], f"{key}.material.q10")
    q20 = _hex64(resources["material"]["qword_0x20"], f"{key}.material.q20")
    check(q20 == DONOR_MATERIAL_Q20, "material +0x20 donor rule changed")
    struct.pack_into("<Q", material["data"], 0x10, q10)
    struct.pack_into("<Q", material["data"], 0x20, q20)
    candidate = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate)
    check(logical.serialize_wad(reparsed) == candidate, "candidate WAD parse/serialize differs")
    normalized = normalize_wad(logical, source_raw, reparsed, definition)
    check(normalized == source_raw, "candidate does not normalize to frozen Raven")

    added_ids = set(ids_by_name.values())
    for label in ("diffuse", "emissive"):
        added_ids.add(_hex128(resources[label]["definition_id"], f"{key}.{label}.definition"))
        added_ids.add(_hex128(resources[label]["gpu_id"], f"{key}.{label}.gpu"))
    source_ids = {row["id"] for row in source_records}
    check(not (added_ids & source_ids), "new resource ID aliases frozen Raven")

    map_index, _ = _one_payload(reparsed, target["map_model"])
    hud_index, _ = _one_payload(reparsed, target["hud_model"])
    material_id = _hex128(resources["material"]["id"], f"{key}.material.id")
    map_rows = _group_rows(logical, reparsed, map_index)
    hud_rows = _group_rows(logical, reparsed, hud_index)
    _dependency(map_rows, target["material"], material_id)
    _dependency(hud_rows, target["material"], material_id)
    for side, rows in (("map", map_rows), ("hud", hud_rows)):
        name, rid = STOCK_MODEL_GROUPS[side]
        _dependency(rows, name, bytes.fromhex(rid))

    material_refs = [i for i, row in enumerate(reparsed) if row["kind"] == 1 and not row["data"]
                     and row["id"] == material_id]
    material_owners = [_owner(logical, reparsed, index) for index in material_refs]
    check(material_owners == [target["map_model"], target["hud_model"]],
          f"cross-collectible material owner leak: {material_owners}")
    texture_owners: dict[str, list[str]] = {}
    for label in ("diffuse", "emissive"):
        texture_id = _hex128(resources[label]["definition_id"], f"{key}.{label}.definition")
        refs = [i for i, row in enumerate(reparsed) if row["kind"] == 1 and not row["data"]
                and row["id"] == texture_id]
        owners = [_owner(logical, reparsed, index) for index in refs]
        check(owners == [target["material"]], f"cross-collectible texture owner leak: {owners}")
        texture_owners[label] = owners

    model_owners: dict[str, list[str]] = {}
    prototype_payload_owners: dict[str, list[str]] = {}
    for side in ("map", "hud"):
        model_role = f"{side}_model"
        proto_role = f"{side}_prototype"
        model_id = _hex128(resources[model_role]["id"], f"{key}.{model_role}.id")
        refs = [i for i, row in enumerate(reparsed) if row["kind"] == 1 and not row["data"]
                and row["id"] == model_id]
        owners = [_owner(logical, reparsed, index) for index in refs]
        check(owners == [resources[proto_role]["name"]],
              f"cross-collectible model owner leak: {side}: {owners}")
        model_owners[side] = owners
        root_role = f"{side}_root"
        _, root_payload = _one_payload(reparsed, resources[root_role]["name"])
        proto_id = _hex128(resources[proto_role]["id"], f"{key}.{proto_role}.id")
        check(bytes(root_payload["data"][0x0C:0x1C]) == proto_id,
              f"{key}.{side}: root/prototype ownership changed")
        proto_payload_owners = [row["name"] for row in reparsed
                                if row["kind"] == 1 and row["data"]
                                and bytes(row["data"]).count(proto_id) > 0]
        check(proto_payload_owners == [resources[proto_role]["name"], resources[root_role]["name"]],
              f"cross-collectible prototype/root owner leak: {side}: {proto_payload_owners}")
        prototype_payload_owners[side] = proto_payload_owners

    map_root_id = _hex128(resources["map_root"]["id"], f"{key}.map_root.id")
    map_root_refs = [row for row in reparsed if row["kind"] == 1 and not row["data"]
                     and row["id"] == map_root_id and
                     row["name"].lower() == target["map_root"].lower()]
    ownership_evidence = {
        "material": material_owners,
        "diffuse": texture_owners["diffuse"],
        "emissive": texture_owners["emissive"],
        "map_model": model_owners["map"],
        "hud_model": model_owners["hud"],
        "map_prototype_payloads": prototype_payload_owners["map"],
        "hud_prototype_payloads": prototype_payload_owners["hud"],
        "map_root_parent_links": len(map_root_refs),
    }
    ownership_proof = validate_reverse_ownership(definition, ownership_evidence)

    preserved_names = [donor_names[name] for name in (
        "material", "diffuse", "emissive", "map_model", "map_proto",
        "map_root", "hud_model", "hud_proto", "hud_root")]
    preserved_names += list(STOCK_DONOR_NAMES)
    preservation: dict[str, dict] = {}
    for name in preserved_names:
        before = [logical.record_bytes(row) for row in source_records if row["name"].lower() == name.lower()]
        after = [logical.record_bytes(row) for row in reparsed if row["name"].lower() == name.lower()]
        check(bool(before), f"frozen source record missing: {name}")
        pending = list(after)
        for raw in before:
            check(raw in pending, f"frozen source record mutated: {name}")
            pending.remove(raw)
        preservation[name] = {
            "source_record_count": len(before),
            "candidate_record_count": len(after),
            "every_source_record_byte_identical": True,
        }

    first_diff = [i for i, pair in enumerate(zip(pre_rule, candidate)) if pair[0] != pair[1]]
    return candidate, {
        "collectible_key": key,
        "source_sha256": sha_bytes(source_raw),
        "pre_material_rule_sha256": sha_bytes(pre_rule),
        "candidate_sha256": sha_bytes(candidate),
        "bytes": len(candidate),
        "resource_ids": {role: resources[role]["id"] for role in GROUP_ROLES},
        "material": {
            "qword_0x10_before_generic_rule": f"{before_q10:016X}",
            "qword_0x20_before_generic_rule": f"{before_q20:016X}",
            "qword_0x10": f"{q10:016X}",
            "qword_0x20": f"{q20:016X}",
            "owners": material_owners,
        },
        "texture_owners": texture_owners,
        "model_owners": model_owners,
        "prototype_payload_owners": prototype_payload_owners,
        "ownership": ownership_proof,
        "prototype_root_ownership_valid": True,
        "model_groups": {
            "map": definition["model_group_policy"]["map"],
            "hud": definition["model_group_policy"]["hud"],
            "opaque_payload_bytes_changed": False,
        },
        "accounting": legacy_report["accounting"],
        "legacy_compatible_report": legacy_report,
        "material_rule_diff_offsets": first_diff,
        "parse_serialize_roundtrip_exact": True,
        "normalized_to_frozen_raven_exact": True,
        "frozen_raven_records_preserved": True,
        "stock_dock_boatdock_preserved": True,
        "preserved_named_records": preservation,
        "reverse_reference_ownership_valid": True,
        "unexpected_payload_changes": False,
    }


def _dcb_rows(data: bytes) -> tuple[int, list[dict], int]:
    count = struct.unpack_from("<I", data, 8)[0]
    end = 0x90 + count * 16
    check(end <= len(data), "GOPool exceeds DCB data")
    rows = []
    for index in range(count):
        at = 0x90 + index * 16
        uid, capacity = struct.unpack_from("<QH", data, at)
        rows.append({"index": index, "uid": uid, "capacity": capacity,
                     "raw": bytes(data[at:at + 16])})
    return count, rows, end


def build_collectible_gopool(source: bytes, registry: dict, key: str) -> tuple[bytes, dict]:
    check(sha_bytes(source) == FROZEN_RAVEN_UI_DCB_SHA256, "source UI DCB is not frozen Raven")
    definition = definition_for(registry, key)
    check(definition["build"]["enabled"] is True, f"{key}: build disabled")
    verifier = _load_module(f"collectible_dcb_{key}", HERE / "verify-raven-production-state.py")
    chunks = verifier.parse_chunks(source)
    data_chunk = verifier.one(chunks, 12)
    data = bytearray(source[data_chunk["start"]:data_chunk["end"]])
    count, rows, pool_end = _dcb_rows(data)
    check(count == 257, "frozen Raven GOPool count changed")
    expected_indexes = [count + index for index in range(len(definition["gopool"]))]
    declared_indexes = [item["index"] for item in definition["gopool"]]
    check(declared_indexes == expected_indexes, f"{key}: GOPool indexes not append-only")
    existing = {row["uid"] for row in rows}
    append = []
    for item in definition["gopool"]:
        uid = _hex64(item["folded_hash"], f"{key}.{item['role']}.hash")
        check(uid not in existing, f"{key}: GOPool hash already exists")
        existing.add(uid)
        append.append(struct.pack("<QH6x", uid, item["capacity"]))
    inserted = b"".join(append)
    ptr10 = struct.unpack_from("<q", data, 0x10)[0]
    ptr20 = struct.unpack_from("<q", data, 0x20)[0]
    check(ptr10 == pool_end - 16 and ptr20 == pool_end, "GOPool tail pointer relation changed")
    candidate_data = bytearray(data[:pool_end] + inserted + data[pool_end:])
    struct.pack_into("<I", candidate_data, 8, count + len(append))
    struct.pack_into("<q", candidate_data, 0x10, ptr10 + len(inserted))
    struct.pack_into("<q", candidate_data, 0x20, ptr20 + len(inserted))
    header = bytearray(source[data_chunk["header"]:data_chunk["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = (source[:data_chunk["header"]] + bytes(header) + bytes(candidate_data) +
                 source[data_chunk["end"]:])
    after_chunks = verifier.parse_chunks(candidate)
    after_data_chunk = verifier.one(after_chunks, 12)
    after_data = candidate[after_data_chunk["start"]:after_data_chunk["end"]]
    new_count, new_rows, new_end = _dcb_rows(after_data)
    check(new_count == count + len(append), "GOPool append count changed")
    check(after_data[0x90:pool_end] == data[0x90:pool_end], "existing GOPool row changed")
    check(after_data[pool_end:pool_end + len(inserted)] == inserted, "new GOPool bytes changed")
    check(after_data[new_end:] == data[pool_end:], "GOPool tail changed")
    normalized_data = bytearray(after_data[:pool_end] + after_data[pool_end + len(inserted):])
    struct.pack_into("<I", normalized_data, 8, count)
    struct.pack_into("<q", normalized_data, 0x10, ptr10)
    struct.pack_into("<q", normalized_data, 0x20, ptr20)
    normalized_header = bytearray(candidate[after_data_chunk["header"]:after_data_chunk["start"]])
    struct.pack_into("<I", normalized_header, 4, len(normalized_data))
    normalized = (candidate[:after_data_chunk["header"]] + bytes(normalized_header) +
                  bytes(normalized_data) + candidate[after_data_chunk["end"]:])
    check(normalized == source, "GOPool candidate does not normalize to Raven")
    by_role = {item["role"]: item for item in definition["gopool"]}
    return candidate, {
        "collectible_key": key,
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "source_rows": count,
        "candidate_rows": new_count,
        "rows": [{"role": item["role"], "index": item["index"],
                  "hash": item["folded_hash"], "capacity": item["capacity"]}
                 for item in definition["gopool"]],
        "map_index": by_role["map"]["index"],
        "map_capacity": by_role["map"]["capacity"],
        "hud_index": by_role["hud"]["index"],
        "hud_capacity": by_role["hud"]["capacity"],
        "all_existing_rows_byte_identical": True,
        "raven_map_row_preserved": True,
        "raven_hud_row_preserved": True,
        "raven_rows_preserved": True,
        "memorypools_lua_tail_preserved_after_shift": True,
        "non_data_chunks_byte_identical": True,
        "normalized_candidate_equals_frozen_raven_dcb": True,
        "normalized_to_frozen_raven_exact": True,
    }


def build_collectible_compass_inworld(source: bytes, registry: dict,
                                      key: str) -> tuple[bytes, dict]:
    """Clone proven Raven compass class and in-world carrier from registry."""
    check(sha_bytes(source) == FROZEN_RAVEN_PERM_DCB_SHA256,
          "source perm DCB is not frozen Raven")
    definition = definition_for(registry, key)
    check(definition["build"]["enabled"] is True, f"{key}: build disabled")
    compass = definition["identities"]["compass"]
    in_world = definition["identities"]["in_world"]
    check(compass is not None and in_world is not None,
          f"{key}: compass/in-world identity unresolved")
    module = _load_module(
        f"collectible_perm_{key}", HERE / "build-nornir-perm-offline.py")
    module.NORNIR_CLASS = compass["class_name"]
    module.NORNIR_CLASS_UID = _hex64(compass["class_uid"], f"{key}.class uid")
    module.NORNIR_HUD = _hex64(compass["folded_hash"], f"{key}.HUD hash")
    module.NORNIR_INWORLD = in_world["name"]
    module.NORNIR_INWORLD_UID = _hex64(in_world["uid"], f"{key}.in-world uid")
    candidate, proof = module.build_candidate(source)
    check(proof["proof"]["candidate_data_normalizes_exactly_to_raven_production"] is True,
          f"{key}: compass/in-world data does not normalize")
    check(proof["proof"]["frozen_raven_class_preserved"] is True,
          f"{key}: Raven class changed")
    check(proof["proof"]["frozen_raven_inworld_preserved"] is True,
          f"{key}: Raven in-world carrier changed")
    return candidate, {
        "collectible_key": key,
        "source_sha256": sha_bytes(source),
        "candidate_sha256": sha_bytes(candidate),
        "compass_class": proof["nornir_class"],
        "in_world_carrier": proof["nornir_inworld"],
        "parse_rebuild_valid": True,
        "normalized_to_frozen_raven_exact": True,
        "frozen_raven_bytes_preserved": True,
        "runtime_proven": False,
    }


def assert_cross_collectible_isolation(registry: dict, keys: list[str]) -> dict:
    definitions = [definition_for(registry, key) for key in keys]
    names = []
    ids = []
    ownership = []
    for definition in definitions:
        key = definition["key"]
        resources = definition["resources"]
        for role in RESOURCE_ROLES:
            names.append((f"{key}.{role}", resources[role]["name"]))
        for role in GROUP_ROLES:
            ids.append((f"{key}.{role}", resources[role]["id"]))
        for role in ("material", "map_model", "map_prototype", "map_root",
                     "hud_model", "hud_prototype", "hud_root"):
            ownership.append({"collectible": key, "role": role,
                              "name": resources[role]["name"], "id": resources[role]["id"]})
    _collect_unique(names, "cross-collectible resource name")
    _collect_unique(ids, "cross-collectible resource ID")
    return {
        "collectibles": keys,
        "resource_names_unique": True,
        "resource_ids_unique": True,
        "material_model_prototype_root_ownership_disjoint": True,
        "ownership": ownership,
    }


def assert_offline_output(game_root: Path, output: Path, repo_root: Path = REPO) -> None:
    game = game_root.resolve()
    target = output.resolve()
    repo = repo_root.resolve()
    check(not target.is_relative_to(game), f"offline output inside game root: {target}")
    check(target.is_relative_to(repo / "build"), f"offline output outside repo build root: {target}")
