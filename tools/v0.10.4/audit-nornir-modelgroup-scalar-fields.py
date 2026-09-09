#!/usr/bin/env python3
"""Read-only scalar/word-shape audit for retired Nornir Candidate 2 MG payloads.

The preceding differential audit proved that the closest native map/HUD MG peers
vary only in opaque bytes: none of the changing bytes overlap known 16-byte WAD
resource IDs.  This stage does not guess a Candidate 3 mutation.  It inspects
those differential bytes as aligned scalar words and asks whether the closest
native peers share coherent values at the same offsets.

This can distinguish a stable native field pattern from arbitrary byte noise,
but it still does not assign semantics to an opaque field or authorize runtime
installation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_MODEL_GROUP_SCALAR_FIELD_AUDIT_PASSED"
EXPECTED_CANDIDATE_SHA = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_peer_module():
    path = HERE / "audit-nornir-modelgroup-peer-differentials.py"
    spec = importlib.util.spec_from_file_location("nornir_peer_differential", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def aligned_words(offsets: tuple[int, ...] | list[int], payload_len: int) -> list[int]:
    words = sorted({value & ~0x3 for value in offsets})
    return [offset for offset in words if offset + 4 <= payload_len]


def decode_word(raw: bytes, offset: int) -> dict:
    chunk = raw[offset : offset + 4]
    check(len(chunk) == 4, f"short word at {offset:#x}")
    u32 = struct.unpack_from("<I", chunk)[0]
    i32 = struct.unpack_from("<i", chunk)[0]
    f32 = struct.unpack_from("<f", chunk)[0]
    if math.isfinite(f32):
        f32_text = f"{f32:.9g}"
        plausible_float = abs(f32) <= 1.0e9
    else:
        f32_text = str(f32)
        plausible_float = False
    u16_lo, u16_hi = struct.unpack_from("<HH", chunk)
    return {
        "hex": chunk.hex(),
        "u32": u32,
        "i32": i32,
        "u16_lo": u16_lo,
        "u16_hi": u16_hi,
        "f32": f32_text,
        "finite_plausible_f32": plausible_float,
    }


def byte_mask(donor: bytes, peer: bytes, offset: int) -> str:
    return "".join("1" if donor[offset + i] != peer[offset + i] else "0" for i in range(4))


def top_word_values(peers: list[dict], offset: int, limit: int = 6) -> list[dict]:
    counts = Counter(peer["data"][offset : offset + 4] for peer in peers)
    rows = []
    for value, count in counts.most_common(limit):
        decoded = decode_word(value, 0)
        rows.append({"count": count, **decoded})
    return rows


def pair_report(peer_mod, label: str, records: list[dict], mgs: list[dict]) -> dict:
    names = peer_mod.PAIRS[label]
    stock_i, _ = peer_mod.payload_record(records, names["stock"])
    dedicated_i, _ = peer_mod.payload_record(records, names["dedicated"])
    donor = next(row for row in mgs if row["record_index"] == stock_i)
    dedicated = next(row for row in mgs if row["record_index"] == dedicated_i)

    check(dedicated["data"] == donor["data"], f"{label}: Candidate 2 clone condition changed")

    native_same_size = [
        row for row in mgs
        if row["name"].lower() not in peer_mod.DEDICATED
        and row["payload_bytes"] == donor["payload_bytes"]
        and row["record_index"] != donor["record_index"]
    ]
    check(native_same_size, f"{label}: no same-size native peers")

    ranked = sorted(
        native_same_size,
        key=lambda row: (
            len(peer_mod.diff_offsets(donor["data"], row["data"])),
            row["name"].lower(),
            row["record_index"],
        ),
    )
    min_diff = len(peer_mod.diff_offsets(donor["data"], ranked[0]["data"]))
    closest = [
        row for row in ranked
        if len(peer_mod.diff_offsets(donor["data"], row["data"])) == min_diff
    ]
    signatures = {peer_mod.diff_offsets(donor["data"], row["data"]) for row in closest}
    check(len(signatures) == 1, f"{label}: closest cohort no longer has one diff signature")
    signature = next(iter(signatures))

    words = aligned_words(signature, donor["payload_bytes"])
    fields = []
    coherent_words = 0
    coherent_different_words = 0
    plausible_coherent_words = 0

    all_native_including_donor = [donor, *native_same_size]

    for offset in words:
        donor_decoded = decode_word(donor["data"], offset)
        peer_chunks = [row["data"][offset : offset + 4] for row in closest]
        closest_share = len(set(peer_chunks)) == 1
        shared_differs = closest_share and peer_chunks[0] != donor["data"][offset : offset + 4]
        if closest_share:
            coherent_words += 1
        if shared_differs:
            coherent_different_words += 1

        peer_rows = []
        for row in closest:
            decoded = decode_word(row["data"], offset)
            peer_rows.append(
                {
                    "name": row["name"],
                    "diff_mask_vs_donor": byte_mask(donor["data"], row["data"], offset),
                    **decoded,
                }
            )

        shared_decoded = decode_word(peer_chunks[0], 0) if closest_share else None
        if shared_differs and shared_decoded and (
            donor_decoded["finite_plausible_f32"] or shared_decoded["finite_plausible_f32"]
        ):
            plausible_coherent_words += 1

        field = {
            "offset": offset,
            "offset_hex": f"0x{offset:03X}",
            "signature_diff_bytes_in_word": [
                value for value in signature if offset <= value < offset + 4
            ],
            "donor": donor_decoded,
            "closest_peers": peer_rows,
            "closest_cohort_shares_exact_word_value": closest_share,
            "shared_closest_word_differs_from_donor": shared_differs,
            "shared_closest_value": shared_decoded,
            "native_word_value_cardinality_including_donor": len(
                {row["data"][offset : offset + 4] for row in all_native_including_donor}
            ),
            "native_top_word_values": top_word_values(all_native_including_donor, offset),
        }
        fields.append(field)

    return {
        "donor": {
            "record_index": donor["record_index"],
            "name": donor["name"],
            "payload_bytes": donor["payload_bytes"],
            "payload_sha256": sha256(donor["data"]),
        },
        "closest_cohort": [row["name"] for row in closest],
        "minimum_native_diff_bytes": min_diff,
        "closest_diff_signature_byte_count": len(signature),
        "aligned_word_count_covering_signature": len(words),
        "closest_cohort_exact_word_agreement_count": coherent_words,
        "closest_cohort_shared_word_different_from_donor_count": coherent_different_words,
        "coherent_words_with_plausible_float_interpretation_count": plausible_coherent_words,
        "fields": fields,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--peer-report", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raw = args.candidate_wad.read_bytes()
    candidate_sha = sha256(raw)
    check(candidate_sha == EXPECTED_CANDIDATE_SHA, f"Candidate 2 WAD SHA mismatch: {candidate_sha}")

    prior = json.loads(args.peer_report.read_text(encoding="utf-8"))
    check(prior.get("result") == "NORNIR_MODEL_GROUP_NATIVE_PEER_DIFFERENTIAL_AUDIT_PASSED",
          "native-peer differential prerequisite did not pass")
    check(prior.get("candidate_wad_sha256") == candidate_sha,
          "native-peer differential report describes another WAD")
    proofs = prior.get("proofs", {})
    check(proofs.get("candidate2_retired") is True, "Candidate 2 retirement proof missing")
    check(proofs.get("specific_internal_identity_field_proven") is False,
          "prerequisite unexpectedly claims a decoded identity field")
    check(proofs.get("candidate3_constructed") is False, "Candidate 3 unexpectedly exists")
    check(proofs.get("runtime_install_allowed") is False, "runtime gate unexpectedly open")

    peer_mod = load_peer_module()
    logical = peer_mod.load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "Candidate 2 WAD round-trip failed")
    mgs = peer_mod.mg_payloads(records)

    pair_reports = {
        label: pair_report(peer_mod, label, records, mgs)
        for label in ("map", "hud")
    }

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate_wad_sha256": candidate_sha,
        "pairs": pair_reports,
        "proofs": {
            "candidate2_retired": True,
            "closest_native_diff_bytes_are_opaque_to_known_resource_id_scan": True,
            "aligned_scalar_words_measured": True,
            "closest_peer_word_coherence_measured": True,
            "specific_internal_identity_field_proven": False,
            "candidate3_constructed": False,
            "runtime_install_allowed": False,
        },
        "interpretation": {
            "proven": "The opaque native-peer differential bytes have been measured as aligned scalar words, including exact closest-cohort value agreement and native value cardinality.",
            "not_proven": "Integer/float renderings are interpretations of opaque bytes only. They do not establish field semantics, a cache key, or a safe mutation by themselves.",
            "next_step": "Use coherent native word patterns, if present, to identify a structurally defensible field family or donor transform. If the values remain heterogeneous/opaque, widen the reverse-engineering target rather than constructing Candidate 3.",
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  candidate WAD: {candidate_sha}")
    for label in ("map", "hud"):
        p = pair_reports[label]
        print(f"  {label}:")
        print(f"    closest cohort: {', '.join(p['closest_cohort'])}")
        print(f"    diff bytes: {p['closest_diff_signature_byte_count']}")
        print(f"    aligned words covering diffs: {p['aligned_word_count_covering_signature']}")
        print(f"    closest cohort exact-word agreements: {p['closest_cohort_exact_word_agreement_count']}")
        print(f"    shared closest words differing from donor: {p['closest_cohort_shared_word_different_from_donor_count']}")
        print("    scalar words:")
        for field in p["fields"]:
            donor = field["donor"]
            if field["closest_cohort_shares_exact_word_value"]:
                peer = field["shared_closest_value"]
                peer_text = f"shared={peer['hex']} u32={peer['u32']} f32={peer['f32']}"
            else:
                values = ", ".join(
                    f"{row['name']}={row['hex']}"
                    for row in field["closest_peers"]
                )
                peer_text = f"variants: {values}"
            print(
                f"      {field['offset_hex']} mask-bytes={len(field['signature_diff_bytes_in_word'])}/4 "
                f"donor={donor['hex']} u32={donor['u32']} f32={donor['f32']} | "
                f"{peer_text} | native-values={field['native_word_value_cardinality_including_donor']}"
            )
    print("  specific hidden identity field proven: false")
    print("  Candidate 3 constructed: false")
    print("  runtime install allowed: false")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
