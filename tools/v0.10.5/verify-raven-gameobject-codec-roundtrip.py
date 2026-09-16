#!/usr/bin/env python3
"""Verify frozen Raven mappings against the shared GameObject save codec."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import gow_gameobject_codec as gameobject

EVIDENCE_RELATIVE = Path(
    "archive/field-logs/runtime/"
    "raven-gameobject-token-resolver-20260916-173709/"
    "raven-gameobject-token-resolver.json"
)
EVIDENCE_COMMIT = "f0757771d6c077bcd5cc0e7cda94d99cfbce3aaf"
EXPECTED_SCHEMA = "completionist-map.raven-gameobject-token-resolution.v2"
EXPECTED_SOURCE = "passive in-thread hook at GoW.exe RVA 0x5493A1"
EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

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


def verify(evidence_path: Path) -> None:
    doc = load_evidence(evidence_path)
    records = doc.get("records")
    if not isinstance(records, list) or len(records) != len(EXPECTED):
        count = len(records) if isinstance(records, list) else "non-list"
        raise RuntimeError(f"expected exactly {len(EXPECTED)} captured records, got {count}")

    # The shared production lookup is the source of truth. Evidence must agree with
    # it before the exact-byte round-trip checks are allowed to pass.
    if len(gameobject.RAVEN_LOOKUP) != len(EXPECTED):
        raise RuntimeError("shared Raven lookup does not contain exactly three mappings")

    for index, (expected, record) in enumerate(
        zip(EXPECTED, records, strict=True), start=1
    ):
        payload = bytes.fromhex(expected["payload_hex"])
        identity = gameobject.parse_flag1_payload(payload)
        captured_token = int(record["token_hex"], 16)

        checks = {
            "payload": record["payload_hex"].lower() == expected["payload_hex"],
            "registry_hash": (
                identity.registry_hash
                == gameobject.RAVEN_REGISTRY_HASH
                == int(record["registry_hash_hex"], 16)
            ),
            "object_hash": (
                identity.object_hash
                == expected["object_hash"]
                == int(record["object_hash_hex"], 16)
            ),
            "registry": int(record["registry"]) == expected["registry"],
            "slot": int(record["slot"]) == expected["slot"],
            "aux": int(record["aux_flag"]) == 0,
            "flavour": int(record["flavour"]) == 0,
            "token": captured_token == expected["token"],
            "captured_formula": record["raven_formula_match"] is True,
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError(
                f"frozen evidence mismatch for target {index}: {', '.join(failed)}"
            )

        decoded = gameobject.RAVEN_CODEC.decode_flag1(payload)
        encoded = gameobject.RAVEN_CODEC.encode_flag1(decoded)
        fields = gameobject.unpack_token(decoded)

        expected_fields = gameobject.GameObjectFields(
            present=True,
            registry=expected["registry"],
            aux=0,
            slot=expected["slot"],
            flavour=0,
        )
        if decoded != captured_token:
            raise RuntimeError(f"shared codec token mismatch for target {index}")
        if encoded != payload:
            raise RuntimeError(f"shared codec exact-byte round trip mismatch for target {index}")
        if fields != expected_fields:
            raise RuntimeError(
                f"shared codec token field extraction mismatch for target {index}: {fields!r}"
            )

        print(
            f"PASS {index}/3 object=0x{expected['object_hash']:016X} "
            f"registry={expected['registry']} slot={expected['slot']} "
            f"token=0x{decoded:016X} bytes={encoded.hex()}"
        )

    # Fail loudly for unknown hashes/numeric identities; hashes are lookup keys,
    # never guessed or treated as reversible arithmetic encodings.
    try:
        gameobject.RAVEN_CODEC.decode_flag1(
            gameobject.emit_flag1_payload(gameobject.RAVEN_REGISTRY_HASH, 0)
        )
    except KeyError:
        pass
    else:
        raise RuntimeError("shared codec unexpectedly accepted an unresolved object hash")

    try:
        gameobject.RAVEN_CODEC.encode_flag1(
            gameobject.pack_token(238, 0xFFFFF)
        )
    except KeyError:
        pass
    else:
        raise RuntimeError("shared codec unexpectedly reverse-resolved an unknown slot")

    print("PASS: shared GameObject codec exact-byte Raven round-trip verified.")
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
