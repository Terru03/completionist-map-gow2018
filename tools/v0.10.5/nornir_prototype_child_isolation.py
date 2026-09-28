"""Give Nornir prototype child nodes their own internal WAD identities."""
from __future__ import annotations

import copy
import hashlib
import struct

import nornir_model_group_isolation as groups


FAMILIES = ("Chest", "Seal", "Bell", "Mechanism")
RAVEN_PROTOS = {
    "map": "goProtoMapIconCompletionistRaven",
    "hud": "goProtoCompletionistRavenHUD",
}


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def proto_name(family: str, kind: str) -> str:
    return ("goProtoMapIconCompletionistNornir" + family if kind == "map"
            else "goProtoCompletionistNornir" + family + "HUD")


def child_id(kind: str, family: str, node: int) -> bytes:
    key = f"completionist:v105:nornir-prototype-child:{kind}:{family}:{node}"
    return hashlib.sha256(key.encode("ascii")).digest()[:16]


def table(row: dict, expected_nodes: int) -> tuple[int, list[bytes]]:
    data = row["data"]
    count = struct.unpack_from("<H", data, 0xC)[0]
    offset = struct.unpack_from("<I", data, 0x18)[0]
    need(count == expected_nodes and offset + count * 16 <= len(data),
         f"prototype node table differs: {row['name']}")
    ids = [bytes(data[offset + node * 16:offset + (node + 1) * 16])
           for node in range(count)]
    need(ids[0] == row["id"] and len(set(ids)) == count,
         f"prototype root or child IDs differ: {row['name']}")
    return offset, ids


def isolate(stage, raven_wad: bytes, candidate_wad: bytes) -> tuple[bytes, dict]:
    logical = groups.logical_module(stage)
    raven = logical.parse_wad(raven_wad)
    source = logical.parse_wad(candidate_wad)
    need(logical.serialize_wad(source) == candidate_wad, "input WAD roundtrip failed")
    records = copy.deepcopy(source)
    changes = []
    for kind, count in (("map", 4), ("hud", 2)):
        _, raven_proto = groups.one_payload(raven, RAVEN_PROTOS[kind])
        _, unchanged = groups.one_payload(source, RAVEN_PROTOS[kind])
        need(logical.record_bytes(raven_proto) == logical.record_bytes(unchanged),
             f"Raven {kind} prototype changed")
        offset, raven_ids = table(unchanged, count)
        need(all(candidate_wad.count(value) == len(FAMILIES) + 2
                 for value in raven_ids[1:]),
             f"shared {kind} child IDs have unexpected references")
        for family in FAMILIES:
            name = proto_name(family, kind)
            _, proto = groups.one_payload(records, name)
            own_offset, old_ids = table(proto, count)
            need(own_offset == offset and old_ids[1:] == raven_ids[1:],
                 f"{name} is not the expected Raven child-node clone")
            expected = bytearray(unchanged["data"])
            expected[offset:offset + 16] = proto["id"]
            need(proto["data"] == expected,
                 f"{name} differs outside its root ID")
            for node in range(1, count):
                new = child_id(kind, family, node)
                need(candidate_wad.find(new) == -1,
                     f"new child identity collides: {name}/{node}")
                at = offset + node * 16
                proto["data"][at:at + 16] = new
                changes.append((name, at, old_ids[node], new))

    need(len(changes) == 16 and len({new for _, _, _, new in changes}) == 16,
         "Nornir child identity count or uniqueness differs")
    result = logical.serialize_wad(records)
    parsed = logical.parse_wad(result)
    need(logical.serialize_wad(parsed) == result, "output WAD roundtrip failed")
    for name, at, old, new in changes:
        _, proto = groups.one_payload(parsed, name)
        need(bytes(proto["data"][at:at + 16]) == new and result.count(new) == 1,
             f"new child identity not unique: {name}")
        proto["data"][at:at + 16] = old
    need(logical.serialize_wad(parsed) == candidate_wad,
         "child identity isolation has no exact inverse")
    for kind in RAVEN_PROTOS:
        _, before = groups.one_payload(source, RAVEN_PROTOS[kind])
        _, after = groups.one_payload(records, RAVEN_PROTOS[kind])
        need(logical.record_bytes(before) == logical.record_bytes(after),
             f"Raven {kind} prototype altered")
    return result, {
        "new_internal_node_ids": len(changes),
        "map_child_ids_per_family": 3,
        "hud_child_ids_per_family": 1,
        "raven_prototypes_preserved": True,
        "exact_inverse_to_model_group_candidate": True,
    }
