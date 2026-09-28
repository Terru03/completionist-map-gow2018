"""Isolate four Nornir icon families from Raven and each other in r_ui.wad."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import struct


FAMILIES = ("chest", "seal", "bell", "mechanism")
DONORS = {"map": "MG_mapicondock_0", "hud": "MG_boatdock_0"}
TYPE_KEYS = {"map": 0x2000C, "hud": 0x1000C}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def logical_module(stage):
    path = stage.HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_isolated_wad_logical", path)
    need(spec is not None and spec.loader is not None, "WAD parser unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one_payload(records: list[dict], name: str) -> tuple[int, dict]:
    rows = [(index, row) for index, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    need(len(rows) == 1, f"expected one payload: {name}")
    return rows[0]


def model_name(family: str, kind: str) -> str:
    return "MDL_cm_nornir_" + family + ("_hud" if kind == "hud" else "")


def mg_name(family: str, kind: str) -> str:
    return "MG_cm_nornir_" + family + "_" + kind


def mg_id(name: str) -> bytes:
    return hashlib.sha256(("completionist:v105:nornir-isolated-mg:" + name).encode()).digest()[:16]


def model_link(records: list[dict], logical, family: str, kind: str,
               expected_name: str, expected_id: bytes) -> dict:
    index, model = one_payload(records, model_name(family, kind))
    start = model["parent"]
    need(start is not None and records[start]["kind"] == 2,
         f"model group missing: {model['name']}")
    end = logical.matching_group_end(records, start)
    links = [row for row in records[start:end + 1]
             if row["kind"] == 1 and not row["data"] and
             row["name"].lower() == expected_name.lower() and row["id"] == expected_id]
    need(len(links) == 1, f"model dependency differs: {model['name']}")
    return links[0]


def isolate(stage, raven_wad: bytes, candidate_wad: bytes) -> tuple[bytes, dict]:
    logical = logical_module(stage)
    source = logical.parse_wad(candidate_wad)
    raven = logical.parse_wad(raven_wad)
    need(logical.serialize_wad(source) == candidate_wad, "candidate WAD roundtrip failed")
    need(logical.serialize_wad(raven) == raven_wad, "Raven WAD roundtrip failed")
    records = copy.deepcopy(source)
    names = {row["name"].lower() for row in records}
    ids = {row["id"] for row in records}
    donor_rows = {}
    for kind, donor_name in DONORS.items():
        index, donor = one_payload(records, donor_name)
        _, old = one_payload(raven, donor_name)
        need(donor["parent"] is None and old["parent"] is None and
             logical.record_bytes(donor) == logical.record_bytes(old),
             f"shared {kind} model group changed from Raven baseline")
        need(donor["kind"] == 1 and donor["flags"] == 0x98 and
             struct.unpack_from("<I", donor["data"])[0] == 0x1000C,
             f"shared {kind} model group grammar differs")
        need(donor["data"].count(donor["id"]) == 0 and
             donor_name.lower().encode() not in bytes(donor["data"]).lower(),
             f"shared {kind} model group embeds its old identity")
        donor_rows[kind] = (index, donor)

    payloads = logical.payload_records(records)
    heap, root = payloads[:2]
    before_heap, before_root = bytes(heap["data"]), bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    need(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0],
         "WAD accounting total differs")
    types = logical.read_type_table(root["data"])
    by_key = {row["key"]: row for row in types}
    need(len(by_key) == len(types) and all(key in by_key for key in TYPE_KEYS.values()),
         "WAD model group type rows differ")
    map_donor = donor_rows["map"][1]
    map_ranges = [row for row in types if row["base"] <= map_donor["payload_index"] <
                  row["base"] + row["count"]]
    need(len(map_ranges) == 1 and map_ranges[0]["key"] == TYPE_KEYS["map"],
         "map model group accounting differs")
    hud_donor = donor_rows["hud"][1]
    need(not any(row["base"] <= hud_donor["payload_index"] <
                 row["base"] + row["count"] for row in types),
         "HUD model group accounting differs")
    cohort = [row for row in payloads if row["parent"] is None and
              row["kind"] == 1 and row["flags"] == 0x98 and
              len(row["data"]) >= 4 and
              struct.unpack_from("<I", row["data"])[0] == TYPE_KEYS["hud"]]
    need(len(cohort) == by_key[TYPE_KEYS["hud"]]["count"] and
         hud_donor in cohort and map_donor in cohort,
         "model group type cohort differs")

    clones = []
    for kind, donor_name in DONORS.items():
        index, donor = donor_rows[kind]
        for family in FAMILIES:
            name = mg_name(family, kind)
            rid = mg_id(name)
            need(name.lower() not in names and rid not in ids,
                 f"new model group identity collides: {name}")
            names.add(name.lower())
            ids.add(rid)
            clone = copy.deepcopy(donor)
            clone["name"] = name
            clone["id"] = rid
            clone["original_offset"] = None
            clone["payload_index"] = None
            clone["_source_payload_index"] = donor["payload_index"]
            link = model_link(records, logical, family, kind, donor_name, donor["id"])
            link["name"] = name
            link["id"] = rid
            link["original_offset"] = None
            clones.append((index, clone, family, kind))

    total = 0
    for row in types:
        increase = len(FAMILIES) if row["key"] in TYPE_KEYS.values() else 0
        count = row["count"] + increase
        struct.pack_into("<III", root["data"], row["offset"], row["key"], total, count)
        total += count
    need(total == old_total + 8, "model group accounting delta differs")
    struct.pack_into("<I", root["data"], 0x1C, total)
    struct.pack_into("<I", heap["data"], 4, total)

    for index, clone, _, _ in sorted(clones, key=lambda item: item[0], reverse=True):
        records[index + 1:index + 1] = [clone]
    isolated = logical.serialize_wad(records)
    parsed = logical.parse_wad(isolated)
    need(logical.serialize_wad(parsed) == isolated, "isolated WAD roundtrip failed")
    for _, _, family, kind in clones:
        name = mg_name(family, kind)
        _, resource = one_payload(parsed, name)
        need(resource["id"] == mg_id(name) and resource["parent"] is None,
             f"isolated model group missing: {name}")
        model_link(parsed, logical, family, kind, name, resource["id"])
        need(sum(row["kind"] == 1 and not row["data"] and row["id"] == resource["id"]
                 for row in parsed) == 1,
             f"isolated model group has extra references: {name}")
    for kind, donor_name in DONORS.items():
        _, donor = donor_rows[kind]
        index, model = one_payload(parsed, "MDL_completionistraven" +
                                   ("hud" if kind == "hud" else ""))
        start = model["parent"]
        end = logical.matching_group_end(parsed, start)
        need(any(row["kind"] == 1 and not row["data"] and
                 row["name"] == donor_name and row["id"] == donor["id"]
                 for row in parsed[start:end + 1]),
             f"Raven {kind} model group changed")

    normalized = copy.deepcopy(parsed)
    remove = set()
    for _, _, family, kind in clones:
        name = mg_name(family, kind)
        link = model_link(normalized, logical, family, kind, name, mg_id(name))
        link["name"] = DONORS[kind]
        link["id"] = donor_rows[kind][1]["id"]
        link["original_offset"] = None
        index, _ = one_payload(normalized, name)
        remove.add(index)
    restored = [row for index, row in enumerate(normalized) if index not in remove]
    restored_payloads = logical.payload_records(restored)
    restored_payloads[0]["data"] = bytearray(before_heap)
    restored_payloads[1]["data"] = bytearray(before_root)
    need(logical.serialize_wad(restored) == candidate_wad,
         "model group isolation has no exact inverse")
    return isolated, {
        "families": len(FAMILIES), "new_model_groups": len(clones),
        "raven_model_groups_preserved": True,
        "nornir_family_model_groups_unique": True,
        "accounted_payload_delta": total - old_total,
        "exact_inverse_to_art_package": True,
    }
