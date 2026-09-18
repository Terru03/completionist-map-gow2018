#!/usr/bin/env python3
"""Generate stable save-side GameObject identities for all 53 Odin's Ravens.

The recipe is proven by the exact read-only VikingFuneral capture:

1. Walk the authored transform chain root -> leaf.
2. For each 16-byte transform record id, decrement byte index 12 by one.
3. Resolve the leaf transform's prototype record through native.prototype_id.
4. Append the 16-byte GameObject identity stored at prototype payload +0x6C.
5. Hash the concatenated 16-byte elements with GoW's serializer hash loop.
6. Serialize as flag 0x01 + registry_hash + object_hash, both little-endian.

The frozen DEAD transition proves that the inserted ravenKilled record is
0x98BE1707BA2D65A9 and belongs to
raven_642d0d164af0a5d4076e77933c549a5d. The two other frozen hashes were
already present in the ALIVE carrier and are not Raven instance identities.

This tool reads shipped game WADs and writes repository evidence/output only.
It never opens an active save and never writes game/progression state.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE = REPO / "catalogue" / "odins-ravens.json"
OUTPUT = REPO / "catalogue" / "odins-ravens-save-identities.json"

REGISTRY_HASH = 0x4EC230253427B2B0
KNOWN_RAVEN = "raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_OBJECT_HASH = 0x98BE1707BA2D65A9
KNOWN_VECTOR = [
    "6a40442bc7277743a15f2986a3279901",
    "82bdafe150a9ea49ac27331f1525d1d5",
    "160d2d64d4a5f04a93776e075d9a543c",
    "805b030bf339564cb157837c52906465",
]
KNOWN_PAYLOAD = "01b0b227342530c24ea9652dba0717be98"
MASK64 = 0xFFFFFFFFFFFFFFFF


def load_rc():
    path = HERE / "raven_catalogue.py"
    spec = importlib.util.spec_from_file_location("raven_catalogue_identity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raw_identity_hash(elements: list[bytes]) -> int:
    value = 0
    for element in elements:
        if len(element) != 16:
            raise ValueError(f"identity element is {len(element)} bytes, expected 16")
        for byte in element:
            value = ((value + byte) * 0x401) & MASK64
            value ^= value >> 6
    return value


def transform_identity(raw: bytes) -> bytes:
    """Convert a scene transform record id to its GameObject identity element."""
    if len(raw) != 16:
        raise ValueError("transform record id must be 16 bytes")
    out = bytearray(raw)
    if out[12] == 0:
        raise ValueError(f"cannot decrement byte[12] for transform id {raw.hex()}")
    out[12] -= 1
    return bytes(out)


def one_record(records: list[dict], record_id: bytes, *, offset: int | None = None, name: str | None = None) -> dict:
    hits = [r for r in records if r["id"] == record_id]
    if offset is not None:
        hits = [r for r in hits if r["offset"] == offset]
    if name is not None:
        hits = [r for r in hits if r["name"] == name]
    if len(hits) != 1:
        found = [f"0x{r['offset']:X}:{r['name']}" for r in hits]
        raise RuntimeError(
            f"record {record_id.hex()} expected exactly once after filters, found {len(hits)} {found}"
        )
    return hits[0]


def prototype_identity(records: list[dict], prototype_id: bytes) -> tuple[bytes, dict]:
    hits = [r for r in records if r["id"] == prototype_id and r["kind"] == 1]
    if len(hits) != 1:
        found = [f"0x{r['offset']:X}:{r['name']}" for r in hits]
        raise RuntimeError(
            f"prototype {prototype_id.hex()} expected one record, found {len(hits)} {found}"
        )
    record = hits[0]
    if len(record["data"]) < 0x7C:
        raise RuntimeError(
            f"prototype record {record['name']} too short for +0x6C identity: {len(record['data'])}"
        )
    identity = record["data"][0x6C:0x7C]
    if identity == bytes(16):
        raise RuntimeError(f"prototype record {record['name']} has zero +0x6C identity")
    return identity, {
        "record_id": record["id"].hex(),
        "record_name": record["name"],
        "record_offset": f"0x{record['offset']:X}",
        "payload_identity_offset": "0x6C",
        "identity_hex": identity.hex(),
    }


def payload_for(object_hash: int) -> bytes:
    return bytes([1]) + REGISTRY_HASH.to_bytes(8, "little") + object_hash.to_bytes(8, "little")


def derive_row(row: dict, records: list[dict]) -> dict:
    source = row["source"]
    native = row["native"]

    final = one_record(
        records,
        bytes.fromhex(native["final_record_id"]),
        offset=int(source["final_offset"], 16),
        name=native["object_name"],
    )
    if final["data"][0x0C:0x1C].hex() != native["prototype_id"]:
        raise RuntimeError(f"{row['catalogue_id']}: final prototype pointer disagrees with catalogue")

    chain = source["transform_chain"]
    if not chain or chain[0]["record_id"] != native["final_record_id"]:
        raise RuntimeError(f"{row['catalogue_id']}: transform chain does not start at final record")

    transform_elements = [
        transform_identity(bytes.fromhex(item["record_id"]))
        for item in reversed(chain)
    ]
    proto_element, proto_evidence = prototype_identity(
        records, bytes.fromhex(native["prototype_id"])
    )
    elements = transform_elements + [proto_element]
    object_hash = raw_identity_hash(elements)
    payload = payload_for(object_hash)

    return {
        "catalogue_id": row["catalogue_id"],
        "instance_guid": native["instance_guid"],
        "realm": row["realm"],
        "region": row["region"],
        "wad": source["wad"],
        "registry_hash_hex": f"0x{REGISTRY_HASH:016X}",
        "object_hash_hex": f"0x{object_hash:016X}",
        "serialized_payload_hex": payload.hex(),
        "identity_element_count": len(elements),
        "identity_elements_hex": [x.hex() for x in elements],
        "transform_identity_elements": [
            {
                "source_record_name": item["name"],
                "source_record_id": item["record_id"],
                "source_offset": item["offset"],
                "identity_hex": element.hex(),
            }
            for item, element in zip(reversed(chain), transform_elements)
        ],
        "prototype_identity": proto_evidence,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output", type=Path, default=OUTPUT)
    ap.add_argument("--evidence-json", type=Path)
    args = ap.parse_args()

    rc = load_rc()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    ravens = catalogue["ravens"]
    if len(ravens) != 53:
        raise RuntimeError(f"expected 53 catalogue Ravens, found {len(ravens)}")

    wad_root = args.game_root / "exec" / "wad" / "pc_le"
    cache: dict[str, list[dict]] = {}
    raw_cache: dict[str, bytes] = {}
    expected_sha_by_wad: dict[str, set[str]] = defaultdict(set)
    for row in ravens:
        expected_sha_by_wad[row["source"]["wad"]].add(row["source"]["wad_sha256"])

    for wad_name, shas in expected_sha_by_wad.items():
        if len(shas) != 1:
            raise RuntimeError(f"catalogue has conflicting SHA-256 values for {wad_name}: {sorted(shas)}")
        path = wad_root / wad_name
        raw = path.read_bytes()
        actual = rc.digest(raw)
        expected = next(iter(shas))
        if actual != expected:
            raise RuntimeError(f"WAD SHA mismatch for {wad_name}: expected {expected}, got {actual}")
        raw_cache[wad_name] = raw
        cache[wad_name] = rc.parse_wad(raw)

    identities = [derive_row(row, cache[row["source"]["wad"]]) for row in ravens]
    identities.sort(key=lambda x: x["catalogue_id"])

    by_id = {x["catalogue_id"]: x for x in identities}
    known = by_id[KNOWN_RAVEN]
    known_checks = {
        "identity_vector_exact": known["identity_elements_hex"] == KNOWN_VECTOR,
        "object_hash_exact": int(known["object_hash_hex"], 16) == KNOWN_OBJECT_HASH,
        "serialized_payload_exact": known["serialized_payload_hex"] == KNOWN_PAYLOAD,
    }
    if not all(known_checks.values()):
        raise RuntimeError(
            "proven VikingFuneral Raven identity did not reproduce frozen DEAD record: "
            + json.dumps({"checks": known_checks, "derived": known}, sort_keys=True)
        )

    hashes = [x["object_hash_hex"] for x in identities]
    payloads = [x["serialized_payload_hex"] for x in identities]
    if len(set(hashes)) != 53:
        dup = sorted({h for h in hashes if hashes.count(h) > 1})
        raise RuntimeError(f"save object hashes are not unique: {dup}")
    if len(set(payloads)) != 53:
        raise RuntimeError("serialized Raven payloads are not unique")

    result = {
        "schema_version": 1,
        "catalogue": "completionist-map-gow2018-odins-ravens-save-identities",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_authority": "native_pc_wad_identity_recipe_plus_frozen_ravenKilled_proof",
        "registry_hash_hex": f"0x{REGISTRY_HASH:016X}",
        "record_format": "01 + registry_hash_le_u64 + object_hash_le_u64",
        "derivation": {
            "transform_order": "root_to_leaf",
            "transform_record_id_rule": "copy 16-byte record id and decrement byte index 12 by one",
            "prototype_rule": "resolve native.prototype_id record and append payload[0x6C:0x7C]",
            "object_hash_rule": "for each byte: value=((value+byte)*0x401)&u64; value^=value>>6",
        },
        "frozen_binding_correction": {
            "alive_existing_object_hashes_not_ravens": [
                "0x165CD520758061E5",
                "0xADB72E5C5003A8A0",
            ],
            "inserted_ravenKilled_object_hash": f"0x{KNOWN_OBJECT_HASH:016X}",
            "inserted_raven_catalogue_id": KNOWN_RAVEN,
            "proof": "exact live identity vector matches transformed native WAD chain and frozen DEAD inserted record",
        },
        "proof_checks": known_checks,
        "identity_count": len(identities),
        "unique_object_hash_count": len(set(hashes)),
        "unique_serialized_payload_count": len(set(payloads)),
        "identities": identities,
        "safety": {
            "game_launched": False,
            "process_opened": False,
            "active_save_opened": False,
            "game_files_written": False,
            "save_or_progression_written": False,
            "repository_files_written": True,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.evidence_json:
        args.evidence_json.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "result": "RAVEN_SAVE_IDENTITY_CATALOGUE_COMPLETE",
            "identity_count": result["identity_count"],
            "unique_object_hash_count": result["unique_object_hash_count"],
            "proof_checks": known_checks,
            "known_raven": {
                "catalogue_id": KNOWN_RAVEN,
                "object_hash_hex": known["object_hash_hex"],
                "serialized_payload_hex": known["serialized_payload_hex"],
                "identity_elements_hex": known["identity_elements_hex"],
            },
            "wad_count": len(cache),
            "safety": result["safety"],
        }
        args.evidence_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("RAVEN_SAVE_IDENTITY_CATALOGUE_COMPLETE")
    print(f"identities={len(identities)} unique_hashes={len(set(hashes))} wads={len(cache)}")
    print(f"known_raven={KNOWN_RAVEN}")
    print(f"known_hash={known['object_hash_hex']}")
    print(f"known_payload={known['serialized_payload_hex']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
