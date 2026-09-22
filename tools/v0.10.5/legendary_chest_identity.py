"""Exact static identity helpers for tracked Legendary Chests.

This module deliberately stops before claiming persisted state.  It turns the
already-audited WAD transform chain into the exact scene portion of a native
GameObject identity.  The final prototype identity element is learned from a
read-only live registry sweep, then the normal native 0x401 identity hash gives
the serialized object hash used by the checkpoint carrier.
"""
from __future__ import annotations

from pathlib import Path

MASK64 = 0xFFFFFFFFFFFFFFFF
FAMILY = "legendary_chest"
PRODUCTION_ELIGIBILITY = "tracked_collectible"
EXPECTED_TRACKED = 33
EXPECTED_RAW = 64
EXPECTED_TRIAL_EXCLUDED = 27
EXPECTED_UNRESOLVED = 4
CHEST_OWN_IDENTITY_ELEMENT = bytes.fromhex("947a7c50b25f004ea3365dd8dc232ee1")\nOPENED_STATE_NUMERIC = 4\nOPENED_STATE_FLOAT32 = 4.0\nOPENED_STATE_RAW_HEX = "0100008040"


def adjusted_record_id(hex_id: str) -> bytes:
    raw = bytearray.fromhex(hex_id)
    if len(raw) != 16:
        raise ValueError(f"not a 16-byte record id: {hex_id}")
    raw[12] = (raw[12] - 1) & 0xFF
    return bytes(raw)


def identity_hash(elements: list[bytes]) -> int:
    value = 0
    for element in elements:
        if len(element) != 16:
            raise ValueError("identity element length changed")
        for byte in element:
            value = ((value + byte) * 0x401) & MASK64
            value ^= value >> 6
    return value & MASK64


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & MASK64
        value ^= value >> 6
    return value & MASK64


def registry_hash_for_wad(wad: str) -> int:
    return name_hash(Path(wad).stem.lower())


def serialized_payload(registry_hash: int, object_hash: int) -> bytes:
    return (
        bytes([1])
        + int(registry_hash).to_bytes(8, "little")
        + int(object_hash).to_bytes(8, "little")
    )


def tracked_rows(catalogue: dict) -> list[dict]:
    return [
        row
        for row in catalogue.get("collectibles", [])
        if row.get("family") == FAMILY
        and row.get("production_eligibility") == PRODUCTION_ELIGIBILITY
    ]


def _is_scene_owner_name(name: str) -> bool:
    lower = name.lower()
    return (
        lower.endswith("_ents")
        or lower.endswith("_ents_nooffset")
        or lower.endswith("_ents_offset")
        or lower.endswith("_cbt")
    )


def scene_identity_elements(row: dict) -> tuple[list[bytes], list[dict]]:
    """Return the runtime/staged-proven Legendary authored identity vector.

    The full transform chain contains both native GameObject identity-bearing
    nodes and editor/organizational wrappers.

    Proven rules:
    - locate the physical chest placement using native.placement_final_record_id;
    - retain outer scene owners whose names end in *_ents*, *_ents_offset,
      *_ents_nooffset, or *_cbt;
    - omit intermediate outer organizational groups such as gopickups/goloot;
    - retain the physical placement;
    - retain nested chest objects between script and placement, except reusable
      *_parent containers;
    - retain gochestscript;
    - transform every retained record ID with the native byte-12 decrement and
      order root -> object.

    A staged-oracle subset search over all 32 represented tracked chests found
    exactly one matching subset per row, and every unique solution follows this
    structural rule. The remaining 33rd row (xpl100_httk) has the same layout
    with an organizational gocontainers wrapper and is therefore deterministic.
    """
    chain = row["source"]["transform_chain"]
    if len(chain) < 3:
        raise ValueError(f"{row['catalogue_id']}: Legendary chain is too short")

    placement_id = str(row["native"]["placement_final_record_id"]).lower()
    placement_indices = [
        index
        for index, item in enumerate(chain)
        if str(item["record_id"]).lower() == placement_id
    ]
    if len(placement_indices) != 1:
        raise ValueError(
            f"{row['catalogue_id']}: expected one placement_final_record_id "
            f"match, got {len(placement_indices)}"
        )
    placement_index = placement_indices[0]

    retained_indices: list[int] = []
    skipped: list[dict] = []

    # Root -> placement: only true scene owners participate; editor grouping
    # objects are omitted.
    for index in range(len(chain) - 1, placement_index, -1):
        item = chain[index]
        if _is_scene_owner_name(item["name"]):
            retained_indices.append(index)
        else:
            skipped.append({
                "source_record_name": item["name"],
                "source_record_id": item["record_id"],
                "adjusted_identity_hex": adjusted_record_id(
                    item["record_id"]
                ).hex(),
                "reason": "organizational_scene_wrapper",
            })

    retained_indices.append(placement_index)

    # Placement -> nested script: retain concrete nested chest objects but omit
    # reusable parent/prototype containers.
    for index in range(placement_index - 1, -1, -1):
        item = chain[index]
        if item["name"].lower().endswith("_parent"):
            skipped.append({
                "source_record_name": item["name"],
                "source_record_id": item["record_id"],
                "adjusted_identity_hex": adjusted_record_id(
                    item["record_id"]
                ).hex(),
                "reason": "reusable_parent_container",
            })
            continue
        retained_indices.append(index)

    if 0 not in retained_indices:
        raise ValueError(f"{row['catalogue_id']}: gochestscript was not retained")
    if not any(index > placement_index for index in retained_indices):
        raise ValueError(f"{row['catalogue_id']}: no outer scene owner retained")

    kept = [
        adjusted_record_id(chain[index]["record_id"])
        for index in retained_indices
    ]
    return kept, skipped
def diagnostic_identity_variants(row: dict) -> dict[str, list[bytes]]:
    """Candidate scene grammars retained only for runtime diagnosis."""
    chain = row["source"]["transform_chain"]
    adjusted = [adjusted_record_id(item["record_id"]) for item in chain]
    return {
        "physical_placement": list(reversed(adjusted[2:])),
        "include_legendary_parent": list(reversed(adjusted[1:])),
        "include_script_and_parent": list(reversed(adjusted)),
    }


def static_contract(catalogue: dict) -> dict:
    raw = [
        row for row in catalogue.get("collectibles", [])
        if row.get("family") == FAMILY
    ]
    tracked = tracked_rows(catalogue)
    trials = [
        row for row in raw
        if row.get("production_eligibility") == "exclude_trial_reward"
    ]
    unresolved = [
        row for row in raw
        if row.get("production_eligibility") == "unresolved"
    ]
    scenes = []
    skipped_count = 0
    for row in tracked:
        scene, skipped = scene_identity_elements(row)
        scenes.append(tuple(scene))
        skipped_count += len(skipped)
        if row["progression"].get("state_adapter") != (
            "interact_chest_standard_checkpoint_state"
        ):
            raise ValueError(
                f"{row['catalogue_id']}: unexpected state adapter"
            )
        if row["progression"].get("field") != "state == OPENED":
            raise ValueError(
                f"{row['catalogue_id']}: unexpected completion field"
            )
        if row["progression"].get("read_only") is not True:
            raise ValueError(
                f"{row['catalogue_id']}: progression contract is not read-only"
            )
        if not row["progression"].get("parent_quest"):
            raise ValueError(
                f"{row['catalogue_id']}: tracked chest lacks parent quest"
            )

    if len(raw) != EXPECTED_RAW:
        raise ValueError(f"expected {EXPECTED_RAW} raw Legendary rows, got {len(raw)}")
    if len(tracked) != EXPECTED_TRACKED:
        raise ValueError(
            f"expected {EXPECTED_TRACKED} tracked Legendary rows, got {len(tracked)}"
        )
    if len(trials) != EXPECTED_TRIAL_EXCLUDED:
        raise ValueError(
            "Legendary trial exclusion count changed: "
            f"{len(trials)} != {EXPECTED_TRIAL_EXCLUDED}"
        )
    if len(unresolved) != EXPECTED_UNRESOLVED:
        raise ValueError(
            "Legendary unresolved count changed: "
            f"{len(unresolved)} != {EXPECTED_UNRESOLVED}"
        )
    if len(set(scenes)) != len(scenes):
        raise ValueError("tracked Legendary scene identities are not unique")

    return {
        "raw": len(raw),
        "tracked": len(tracked),
        "trial_excluded": len(trials),
        "unresolved": len(unresolved),
        "unique_scene_identities": len(set(scenes)),
        "self_prototype_parents_skipped": skipped_count,
        "runtime_proven_own_identity_element_hex": CHEST_OWN_IDENTITY_ELEMENT.hex(),\n        "state_semantics_proven": True,\n        "opened_state_numeric": OPENED_STATE_NUMERIC,\n        "opened_state_float32": OPENED_STATE_FLOAT32,\n        "opened_state_raw_hex": OPENED_STATE_RAW_HEX,
    }
