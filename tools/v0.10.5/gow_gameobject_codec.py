#!/usr/bin/env python3
"""Shared God of War GameObject save-reference codec.

The numeric packed GameObject token and the serialized hash-pair representation
are different identity domains. The 64-bit serialized values are lookup keys,
not arithmetic encodings of registry/slot IDs, so conversion is intentionally
driven by an explicit bijective lookup table.

This module implements the verified flag-0x01 hashed-reference path used by the
frozen Raven save vectors and exposes generic lookup primitives so additional
GameObject mappings can be added from future evidence without changing the
codec itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

FLAG_HASHED_REFERENCE = 0x01
HASHED_REFERENCE_SIZE = 17

PRESENT_MASK = 0x1
REGISTRY_SHIFT = 1
REGISTRY_MASK = 0xFFFF
AUX_SHIFT = 17
AUX_MASK = 0x1
SLOT_SHIFT = 18
SLOT_MASK = 0xFFFFF
FLAVOUR_SHIFT = 38
FLAVOUR_MASK = 0x3F


@dataclass(frozen=True, slots=True)
class GameObjectFields:
    present: bool
    registry: int
    aux: int
    slot: int
    flavour: int


@dataclass(frozen=True, slots=True)
class SerializedHashIdentity:
    registry_hash: int
    object_hash: int


@dataclass(frozen=True, slots=True)
class GameObjectMapping:
    registry_hash: int
    object_hash: int
    registry: int
    slot: int

    @property
    def hash_identity(self) -> SerializedHashIdentity:
        return SerializedHashIdentity(self.registry_hash, self.object_hash)

    @property
    def numeric_identity(self) -> tuple[int, int]:
        return self.registry, self.slot


class GameObjectLookup:
    """Bijective hash-pair <-> numeric GameObject identity lookup."""

    def __init__(self, mappings: Iterable[GameObjectMapping] = ()) -> None:
        self._forward: dict[SerializedHashIdentity, tuple[int, int]] = {}
        self._reverse: dict[tuple[int, int], SerializedHashIdentity] = {}
        for mapping in mappings:
            self.add(mapping)

    def add(self, mapping: GameObjectMapping) -> None:
        validate_u64(mapping.registry_hash, "registry_hash")
        validate_u64(mapping.object_hash, "object_hash")
        validate_registry(mapping.registry)
        validate_slot(mapping.slot)

        hash_key = mapping.hash_identity
        numeric_key = mapping.numeric_identity

        old_numeric = self._forward.get(hash_key)
        if old_numeric is not None and old_numeric != numeric_key:
            raise ValueError(
                f"ambiguous forward GameObject lookup for {hash_key}: "
                f"{old_numeric} vs {numeric_key}"
            )

        old_hash = self._reverse.get(numeric_key)
        if old_hash is not None and old_hash != hash_key:
            raise ValueError(
                f"ambiguous reverse GameObject lookup for {numeric_key}: "
                f"{old_hash} vs {hash_key}"
            )

        self._forward[hash_key] = numeric_key
        self._reverse[numeric_key] = hash_key

    def resolve_hashes(self, registry_hash: int, object_hash: int) -> tuple[int, int]:
        key = SerializedHashIdentity(registry_hash, object_hash)
        try:
            return self._forward[key]
        except KeyError as exc:
            raise KeyError(
                f"unresolved GameObject hash pair registry=0x{registry_hash:016X} "
                f"object=0x{object_hash:016X}"
            ) from exc

    def resolve_numeric(self, registry: int, slot: int) -> SerializedHashIdentity:
        key = (registry, slot)
        try:
            return self._reverse[key]
        except KeyError as exc:
            raise KeyError(
                f"no reverse GameObject lookup for registry={registry} slot={slot}"
            ) from exc

    def __len__(self) -> int:
        return len(self._forward)


def validate_u64(value: int, name: str) -> None:
    if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"{name} out of range for u64: {value}")


def validate_registry(registry: int) -> None:
    if not 0 <= registry <= REGISTRY_MASK:
        raise ValueError(f"registry out of range: {registry}")


def validate_slot(slot: int) -> None:
    if not 0 <= slot <= SLOT_MASK:
        raise ValueError(f"slot out of range: {slot}")


def pack_token(
    registry: int,
    slot: int,
    *,
    aux: int = 0,
    flavour: int = 0,
    present: bool = True,
) -> int:
    validate_registry(registry)
    validate_slot(slot)
    if aux not in (0, 1):
        raise ValueError(f"aux must be 0 or 1: {aux}")
    if not 0 <= flavour <= FLAVOUR_MASK:
        raise ValueError(f"flavour out of range: {flavour}")

    return (
        (1 if present else 0)
        | (registry << REGISTRY_SHIFT)
        | (aux << AUX_SHIFT)
        | (slot << SLOT_SHIFT)
        | (flavour << FLAVOUR_SHIFT)
    )


def unpack_token(token: int) -> GameObjectFields:
    validate_u64(token, "token")
    return GameObjectFields(
        present=bool(token & PRESENT_MASK),
        registry=(token >> REGISTRY_SHIFT) & REGISTRY_MASK,
        aux=(token >> AUX_SHIFT) & AUX_MASK,
        slot=(token >> SLOT_SHIFT) & SLOT_MASK,
        flavour=(token >> FLAVOUR_SHIFT) & FLAVOUR_MASK,
    )


def parse_flag1_payload(payload: bytes) -> SerializedHashIdentity:
    if len(payload) != HASHED_REFERENCE_SIZE:
        raise ValueError(
            f"expected {HASHED_REFERENCE_SIZE}-byte flag-1 payload, got {len(payload)} bytes"
        )
    if payload[0] != FLAG_HASHED_REFERENCE:
        raise ValueError(
            f"expected hashed GameObject flag 0x{FLAG_HASHED_REFERENCE:02X}, "
            f"got 0x{payload[0]:02X}"
        )
    return SerializedHashIdentity(
        registry_hash=int.from_bytes(payload[1:9], "little"),
        object_hash=int.from_bytes(payload[9:17], "little"),
    )


def emit_flag1_payload(registry_hash: int, object_hash: int) -> bytes:
    validate_u64(registry_hash, "registry_hash")
    validate_u64(object_hash, "object_hash")
    return (
        bytes((FLAG_HASHED_REFERENCE,))
        + registry_hash.to_bytes(8, "little")
        + object_hash.to_bytes(8, "little")
    )


class GameObjectCodec:
    """Codec for the verified hashed-reference save representation."""

    def __init__(self, lookup: GameObjectLookup) -> None:
        self.lookup = lookup

    def decode_flag1(self, payload: bytes) -> int:
        identity = parse_flag1_payload(payload)
        registry, slot = self.lookup.resolve_hashes(
            identity.registry_hash, identity.object_hash
        )
        # For the verified flag-0x01 path, aux/flavour are absent and therefore 0.
        return pack_token(registry, slot)

    def encode_flag1(self, token: int) -> bytes:
        fields = unpack_token(token)
        if not fields.present:
            raise ValueError(
                "cannot encode a non-present GameObject token as a flag-0x01 reference"
            )
        if fields.aux != 0 or fields.flavour != 0:
            raise ValueError(
                "flag-0x01 GameObject references require aux=0 and flavour=0; "
                f"got aux={fields.aux} flavour={fields.flavour}"
            )
        identity = self.lookup.resolve_numeric(fields.registry, fields.slot)
        return emit_flag1_payload(identity.registry_hash, identity.object_hash)


RAVEN_REGISTRY_HASH = 0x4EC230253427B2B0
RAVEN_MAPPINGS = (
    GameObjectMapping(
        registry_hash=RAVEN_REGISTRY_HASH,
        object_hash=0x165CD520758061E5,
        registry=238,
        slot=1796,
    ),
    GameObjectMapping(
        registry_hash=RAVEN_REGISTRY_HASH,
        object_hash=0xADB72E5C5003A8A0,
        registry=238,
        slot=1810,
    ),
    GameObjectMapping(
        registry_hash=RAVEN_REGISTRY_HASH,
        object_hash=0x98BE1707BA2D65A9,
        registry=238,
        slot=1772,
    ),
)

RAVEN_LOOKUP = GameObjectLookup(RAVEN_MAPPINGS)
RAVEN_CODEC = GameObjectCodec(RAVEN_LOOKUP)


def _self_test() -> None:
    expected = (
        ("01b0b227342530c24ee561807520d55c16", 0x000000001C1001DD),
        ("01b0b227342530c24ea0a803505c2eb7ad", 0x000000001C4801DD),
        ("01b0b227342530c24ea9652dba0717be98", 0x000000001BB001DD),
    )
    for payload_hex, expected_token in expected:
        payload = bytes.fromhex(payload_hex)
        token = RAVEN_CODEC.decode_flag1(payload)
        if token != expected_token:
            raise AssertionError(
                f"decode mismatch for {payload_hex}: "
                f"0x{token:016X} != 0x{expected_token:016X}"
            )
        rebuilt = RAVEN_CODEC.encode_flag1(token)
        if rebuilt != payload:
            raise AssertionError(
                f"round-trip mismatch: {rebuilt.hex()} != {payload_hex}"
            )
    print("PASS: shared GameObject codec exact-byte Raven self-test.")


if __name__ == "__main__":
    _self_test()
