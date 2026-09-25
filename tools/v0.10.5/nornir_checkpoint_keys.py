"""Derive exact reward-chest checkpoint keys for all 22 physical Nornir chests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
CATALOGUE_SHA256 = "df4a44914426599a52ab28bf165142941f950f407b9919b6519ee65968b51ae7"
STANDARD_CHEST_ELEMENT = bytes.fromhex("947a7c50b25f004ea3365dd8dc232ee1")
BEACH_MAZE = "nornir_chest_c02f019049d50ea0146c478fd46f4a49"
OBSERVED = {
    "nornir_chest_c190d59340706bb79925cb9f2d5867cf":
        (0x4EC230253427B2B0, 0xC0FF99FB89416EC1),
    "nornir_chest_c0cf411940bad7d00042afa7a46f5514":
        (0x63E06E045427145F, 0x895FDE6574116698),
}

spec = importlib.util.spec_from_file_location(
    "nornir_checkpoint_identity", HERE / "build-raven-serialized-gameobject-identities.py")
assert spec is not None and spec.loader is not None
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def build() -> list[dict]:
    raw = CATALOGUE.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == CATALOGUE_SHA256,
         "Nornir source catalogue changed")
    source = json.loads(raw)
    chests = [row for row in source["collectibles"]
              if row["family"] == "nornir_chest"]
    need(len(chests) == 22, "physical Nornir chest count differs")
    result = []
    for row in chests:
        chain = row["source"]["transform_chain"]
        placement = [index for index, node in enumerate(chain)
                     if node["record_id"] == row["native"]["placement_final_record_id"]]
        need(len(placement) == 1, "ambiguous chest placement chain")
        pivot = placement[0]
        kept = [index for index in range(len(chain) - 1, pivot, -1)
                if chain[index]["name"].endswith(
                    ("_ents", "_ents_nooffset", "_ents_offset", "_cbt"))]
        kept += [pivot]
        kept += [index for index in range(pivot - 1, -1, -1)
                 if not chain[index]["name"].endswith("_parent")]
        if row["catalogue_id"] == BEACH_MAZE:
            need(chain[2]["record_id"] == "138c79b301f78d4fa7cfe7bf92b55f97" and
                 chain[3]["record_id"] == "bbb3945cfe281b488f4b0f61bee1ae18",
                 "BeachMaze nested identity differs")
            kept = [7, 6, 4, 2, 0]
        elements = [identity.adjusted_record_id(chain[index]["record_id"])
                    for index in kept] + [STANDARD_CHEST_ELEMENT]
        registry = identity.registry_hash_for_wad(row["source"]["wad"])
        obj = identity.identity_hash(elements)
        result.append({
            "catalogue_id": row["catalogue_id"],
            "wad": row["source"]["wad"],
            "registry_hash": f"{registry:016X}",
            "object_hash": f"{obj:016X}",
            "serialized_key": identity.payload(registry, obj).hex(),
            "identity_elements": [value.hex() for value in elements],
        })
    result.sort(key=lambda row: row["catalogue_id"])
    need(len({row["catalogue_id"] for row in result}) == 22 and
         len({row["serialized_key"] for row in result}) == 22,
         "Nornir checkpoint keys overlap")
    indexed = {row["catalogue_id"]: row for row in result}
    for catalogue_id, (registry, obj) in OBSERVED.items():
        row = indexed[catalogue_id]
        need(row["registry_hash"] == f"{registry:016X}" and
             row["object_hash"] == f"{obj:016X}",
             f"field-observed chest identity differs: {catalogue_id}")
    return result


def contract(rows: list[dict]) -> str:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()
