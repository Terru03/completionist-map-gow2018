#!/usr/bin/env python3
"""Verify the frozen Raven GameObject save-codec mappings without launching GoW.

The runtime evidence was captured from GoW's native decoder path at RVA 0x5493A1.
This verifier treats the 64-bit registry/object hashes as lookup keys, constructs
forward and reverse lookup tables from the frozen evidence, and proves an exact
17-byte payload -> packed token -> identical payload round trip for all three
Raven vectors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

EVIDENCE_RELATIVE = Path(
    "archive/field-logs/runtime/"
    "raven-gameobject-token-resolver-20260916-173709/"
    "raven-gameobject-token-resolver.json"
)
EVIDENCE_COMMIT = "f0757771d6c077bcd5cc0e7cda94d99cfbce3aaf"
EXPECTED_SCHEMA = "completionist-map.raven-gameobject-token-resolution.v2"
EXPECTED_SOURCE = "passive in-thread hook at GoW.exe RVA 0x5493A1"
EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
EXPECTED_REGISTRY_HASH = 0x4EC230253427B2B0

EXPECTED = (
    {
        "payload_hex": "01b0b227342530c24ee561807520d55c16",
        "object_hash": 0x165CD520758061E5,
        "registry": 238,
        "slot": 1796,
        "token": 0x000000001C1001DD,
    },
    {
        "payload_hex": "01b0b227342530c24ea0a803505c2eb7ad",
        "object_hash": 0xADB72E5C5003A8A0,
        "registry": 238,
        "slot": 1810,
        "token": 0x000000001C4801DD,
    },
    {
        "payload_hex": "01b0b227342530c24ea9652dba0717be98",
        "object_hash": 0x98BE1707BA2D65A9,
        "registry": 238,
        "slot": 1772,
        "token": 0x000000001BB001DD,
    },
)


def pack_token(registry: int, slot: int, aux: int = 0, flavour: int = 0) -> int:
    if not 0 <= registry <= 0xFFFF:
        raise ValueError(f"registry out of range: {registry}")
    if not 0 <= slot <= 0xFFFFF:
        raise ValueError(f"slot out of range: {slot}")
    if aux not in (0, 1):
        raise ValueError(f"aux must be 0 or 1: {aux}")
    if not 0 <= flavour <= 0x3F:
        raise ValueError(f"flavour out of range: {flavour}")
    return (
        1
        | (registry << 1)
        | (aux << 17)
        | (slot << 18)
        | (flavour << 38)
    )


def unpack_token(token: int) -> dict[str, int | bool]:
    return {
        "present": bool(token & 1),
        "registry": (token >> 1) & 0xFFFF,
        "aux": (token >> 17) & 1,
        "slot": (token >> 18) & 0xFFFFF,
        "flavour": (token >> 38) & 0x3F,
    }


def parse_flag1_payload(payload: bytes) -> tuple[int, int]:
    if len(payload) != 17:
        raise ValueError(f"expected 17-byte flag-1 payload, got {len(payload)} bytes")
    if payload[0] != 0x01:
        raise ValueError(f"expected Raven flag 0x01, got 0x{payload[0]:02X}")
    registry_hash = int.from_bytes(payload[1:9], "little")
    object_hash = int.from_bytes(payload[9:17], "little")
    return registry_hash, object_hash


def emit_flag1_payload(registry_hash: int, object_hash: int) -> bytes:
    return (
        b"\x01"
        + registry_hash.to_bytes(8, "little")
        + object_hash.to_bytes(8, "little")
    )


def load_evidence(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != EXPECTED_SCHEMA:
        raise RuntimeError(f"unexpected evidence schema: {doc.get('schema')!r}")
    if doc.get("source") != EXPECTED_SOURCE:
        raise RuntimeError(f"unexpected evidence source: {doc.get('source')!r}")
    if doc.get("exe", {}).get("sha256", "").lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError("evidence was captured from an unexpected GoW.exe build")
    verification = doc.get("verification", {})
    if verification.get("all_three_resolved") is not True:
        raise RuntimeError("evidence does not mark all three mappings resolved")
    if verification.get("all_formula_checks_passed") is not True:
        raise RuntimeError("evidence does not mark all token formula checks passed")
    if verification.get("synthetic_decoder_call_used") is not False:
        raise RuntimeError("evidence is not the required native-thread capture")
    return doc


def build_lookups(records: list[dict]) -> tuple[dict[tuple[int, int], tuple[int, int]], dict[tuple[int, int], tuple[int, int]]]:
    forward: dict[tuple[int, int], tuple[int, int]] = {}
    reverse: dict[tuple[int, int], tuple[int, int]] = {}
    for record in records:
        registry_hash = int(record["registry_hash_hex"], 16)
        object_hash = int(record["object_hash_hex"], 16)
        registry = int(record["registry"])
        slot = int(record["slot"])
        hash_key = (registry_hash, object_hash)
        numeric_key = (registry, slot)
        if hash_key in forward and forward[hash_key] != numeric_key:
            raise RuntimeError(f"ambiguous forward lookup for {hash_key!r}")
        if numeric_key in reverse and reverse[numeric_key] != hash_key:
            raise RuntimeError(f"ambiguous reverse lookup for {numeric_key!r}")
        forward[hash_key] = numeric_key
        reverse[numeric_key] = hash_key
    return forward, reverse


def decode_payload(payload: bytes, forward: dict[tuple[int, int], tuple[int, int]]) -> int:
    registry_hash, object_hash = parse_flag1_payload(payload)
    try:
        registry, slot = forward[(registry_hash, object_hash)]
    except KeyError as exc:
        raise KeyError(
            f"unresolved GameObject hash pair registry=0x{registry_hash:016X} "
            f"object=0x{object_hash:016X}"
        ) from exc
    return pack_token(registry, slot)


def encode_token(token: int, reverse: dict[tuple[int, int], tuple[int, int]]) -> bytes:
    fields = unpack_token(token)
    if not fields["present"]:
        raise ValueError("cannot encode a non-present GameObject token as a Raven flag-1 record")
    if fields["aux"] != 0 or fields["flavour"] != 0:
        raise ValueError(
            "Raven flag-1 vectors require aux=0 and flavour=0; "
            f"got aux={fields['aux']} flavour={fields['flavour']}"
        )
    numeric_key = (int(fields["registry"]), int(fields["slot"]))
    try:
        registry_hash, object_hash = reverse[numeric_key]
    except KeyError as exc:
        raise KeyError(
            f"no reverse GameObject lookup for registry={numeric_key[0]} slot={numeric_key[1]}"
        ) from exc
    return emit_flag1_payload(registry_hash, object_hash)


def verify(evidence_path: Path) -> None:
    doc = load_evidence(evidence_path)
    records = doc.get("records")
    if not isinstance(records, list) or len(records) != 3:
        raise RuntimeError(f"expected exactly 3 captured records, got {len(records) if isinstance(records, list) else 'non-list'}")

    forward, reverse = build_lookups(records)
    if len(forward) != 3 or len(reverse) != 3:
        raise RuntimeError("expected three unique forward and reverse lookup entries")

    for index, (expected, record) in enumerate(zip(EXPECTED, records, strict=True), start=1):
        payload = bytes.fromhex(expected["payload_hex"])
        registry_hash, object_hash = parse_flag1_payload(payload)
        captured_token = int(record["token_hex"], 16)

        checks = {
            "payload": record["payload_hex"].lower() == expected["payload_hex"],
            "registry_hash": registry_hash == EXPECTED_REGISTRY_HASH == int(record["registry_hash_hex"], 16),
            "object_hash": object_hash == expected["object_hash"] == int(record["object_hash_hex"], 16),
            "registry": int(record["registry"]) == expected["registry"],
            "slot": int(record["slot"]) == expected["slot"],
            "aux": int(record["aux_flag"]) == 0,
            "flavour": int(record["flavour"]) == 0,
            "token": captured_token == expected["token"],
            "captured_formula": record["raven_formula_match"] is True,
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError(f"frozen evidence mismatch for target {index}: {', '.join(failed)}")

        packed = pack_token(expected["registry"], expected["slot"])
        decoded = decode_payload(payload, forward)
        encoded = encode_token(decoded, reverse)
        fields = unpack_token(decoded)

        if packed != expected["token"] or decoded != captured_token:
            raise RuntimeError(f"token reconstruction mismatch for target {index}")
        if encoded != payload:
            raise RuntimeError(f"exact-byte round trip mismatch for target {index}")
        if fields != {
            "present": True,
            "registry": expected["registry"],
            "aux": 0,
            "slot": expected["slot"],
            "flavour": 0,
        }:
            raise RuntimeError(f"token field extraction mismatch for target {index}: {fields!r}")

        print(
            f"PASS {index}/3 object=0x{expected['object_hash']:016X} "
            f"registry={expected['registry']} slot={expected['slot']} "
            f"token=0x{decoded:016X} bytes={encoded.hex()}"
        )

    print("PASS: Raven GameObject codec exact-byte round-trip verified for all frozen runtime mappings.")
    print(f"Evidence commit: {EVIDENCE_COMMIT}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=repo_root / EVIDENCE_RELATIVE,
        help="path to the frozen native-thread Raven mapping evidence JSON",
    )
    args = parser.parse_args()
    try:
        verify(args.evidence.resolve())
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
