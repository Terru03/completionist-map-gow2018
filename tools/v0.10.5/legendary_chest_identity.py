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


def scene_identity_elements(row: dict) -> tuple[list[bytes], list[dict]]:
    """Return the physical-placement scene portion of a chest identity.

    The audited Legendary transform chain starts inside the reusable state
    subobject:

      [0] gochestscript
      [1] gochest_legendary_parent
      [2] physical authored chest placement
      [3..] scene owners out to the WAD root

    A GameObject identity for the physical chest is therefore formed from the
    authored placement and its scene owners, not from the two nested reusable
    descendants.  Each retained record uses the same proven native identity
    transform as Ravens: decrement byte 12 and reverse root -> object.
    """
    chain = row["source"]["transform_chain"]
    if len(chain) < 3:
        raise ValueError(f"{row['catalogue_id']}: Legendary chain is too short")
    skipped: list[dict] = []
    for original_index in (0, 1):
        item = chain[original_index]
        skipped.append(
            {
                "source_record_name": item["name"],
                "source_record_id": item["record_id"],
                "adjusted_identity_hex": adjusted_record_id(
                    item["record_id"]
                ).hex(),
                "reason": (
                    "nested_reusable_state_subobject"
                    if original_index == 0
                    else "nested_reusable_legendary_parent"
                ),
            }
        )
    kept = [
        adjusted_record_id(item["record_id"])
        for item in reversed(chain[2:])
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
    }
