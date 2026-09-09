#!/usr/bin/env python3
"""Read-only native-peer differential audit for retired Nornir Candidate 2 MGs.

This stage deliberately does not construct Candidate 3.  It asks a narrower
question than the preceding payload-structure inventory: when stock model-group
payloads of the same physical size differ, which byte ranges vary, and are those
ranges explained by embedded references to known WAD resources?

The runtime failure remains the authority that retires Candidate 2.  Correlation
between native peer fields is reported as evidence only; it is never promoted to
an opaque "identity field" without an independently decoded semantic contract.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_MODEL_GROUP_NATIVE_PEER_DIFFERENTIAL_AUDIT_PASSED"
EXPECTED_CANDIDATE_SHA = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"

PAIRS = {
    "map": {
        "stock": "MG_mapicondock_0",
        "dedicated": "MG_completionistnornirchest_map",
        "expected_bytes": 1108,
    },
    "hud": {
        "stock": "MG_boatdock_0",
        "dedicated": "MG_completionistnornirchest_hud",
        "expected_bytes": 388,
    },
}
DEDICATED = {v["dedicated"].lower() for v in PAIRS.values()}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_native_peer_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def payload_record(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [
        (i, row)
        for i, row in enumerate(records)
        if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()
    ]
    check(len(hits) == 1, f"expected one payload record {name!r}, found {len(hits)}")
    return hits[0]


def mg_payloads(records: list[dict]) -> list[dict]:
    out = []
    for i, row in enumerate(records):
        if row["kind"] != 1 or not row["data"] or row["flags"] != 0x98:
            continue
        if not row["name"].lower().startswith("mg_"):
            continue
        out.append(
            {
                "record_index": i,
                "name": row["name"],
                "id": bytes(row["id"]),
                "id_hex": bytes(row["id"]).hex(),
                "payload_index": row["payload_index"],
                "payload_bytes": len(row["data"]),
                "data": bytes(row["data"]),
            }
        )
    return out


def build_id_index(records: list[dict]) -> dict[bytes, list[dict]]:
    index: dict[bytes, list[dict]] = defaultdict(list)
    for i, row in enumerate(records):
        rid = bytes(row["id"])
        if len(rid) != 16 or rid == b"\x00" * 16:
            continue
        index[rid].append(
            {
                "record_index": i,
                "name": row["name"],
                "kind": row["kind"],
                "flags": row["flags"],
                "has_data": bool(row["data"]),
            }
        )
    return dict(index)


def diff_offsets(a: bytes, b: bytes) -> tuple[int, ...]:
    check(len(a) == len(b), "equal-length payloads required")
    return tuple(i for i, (x, y) in enumerate(zip(a, b)) if x != y)


def runs(offsets: tuple[int, ...] | list[int]) -> list[tuple[int, int]]:
    if not offsets:
        return []
    result = []
    start = prev = offsets[0]
    for value in offsets[1:]:
        if value != prev + 1:
            result.append((start, prev))
            start = value
        prev = value
    result.append((start, prev))
    return result


def run_public(items: tuple[int, ...] | list[int], limit: int = 96) -> list[dict]:
    values = runs(items)
    return [
        {"start": start, "end": end, "length": end - start + 1}
        for start, end in values[:limit]
    ]


def known_id_hits(payload: bytes, id_index: dict[bytes, list[dict]]) -> list[dict]:
    hits = []
    for offset in range(0, max(0, len(payload) - 15)):
        rid = payload[offset : offset + 16]
        refs = id_index.get(rid)
        if not refs:
            continue
        hits.append(
            {
                "start": offset,
                "end": offset + 15,
                "id": rid.hex(),
                "targets": refs[:8],
                "target_count": len(refs),
            }
        )
    return hits


def overlapping_hits(hits: list[dict], start: int, end: int) -> list[dict]:
    return [row for row in hits if row["start"] <= end and row["end"] >= start]


def covered_offsets(hits: list[dict]) -> set[int]:
    result: set[int] = set()
    for row in hits:
        result.update(range(row["start"], row["end"] + 1))
    return result


def compact_targets(hits: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for hit in hits:
        key = (hit["start"], hit["id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "offset": hit["start"],
                "id": hit["id"],
                "targets": hit["targets"],
                "target_count": hit["target_count"],
            }
        )
    return out


def diff_detail(donor: dict, peer: dict, id_index: dict[bytes, list[dict]]) -> dict:
    offsets = diff_offsets(donor["data"], peer["data"])
    donor_hits = known_id_hits(donor["data"], id_index)
    peer_hits = known_id_hits(peer["data"], id_index)
    known_cover = covered_offsets(donor_hits) | covered_offsets(peer_hits)
    explained = [i for i in offsets if i in known_cover]
    unexplained = [i for i in offsets if i not in known_cover]

    details = []
    for start, end in runs(offsets):
        details.append(
            {
                "start": start,
                "end": end,
                "length": end - start + 1,
                "donor_hex": donor["data"][start : end + 1].hex(),
                "peer_hex": peer["data"][start : end + 1].hex(),
                "donor_known_id_overlaps": compact_targets(overlapping_hits(donor_hits, start, end)),
                "peer_known_id_overlaps": compact_targets(overlapping_hits(peer_hits, start, end)),
            }
        )

    return {
        "record_index": peer["record_index"],
        "name": peer["name"],
        "id": peer["id_hex"],
        "differing_byte_count": len(offsets),
        "differing_run_count": len(runs(offsets)),
        "diff_offsets": list(offsets),
        "diff_runs": details,
        "diff_bytes_inside_known_resource_id_windows": len(explained),
        "diff_bytes_outside_known_resource_id_windows": len(unexplained),
        "unexplained_diff_runs": run_public(unexplained),
    }


def signature_classes(donor: dict, peers: list[dict]) -> list[dict]:
    groups: dict[tuple[int, ...], list[dict]] = defaultdict(list)
    for peer in peers:
        groups[diff_offsets(donor["data"], peer["data"])].append(peer)
    result = []
    for sig, members in groups.items():
        result.append(
            {
                "member_count": len(members),
                "differing_byte_count": len(sig),
                "differing_run_count": len(runs(sig)),
                "members": [m["name"] for m in members],
                "diff_runs": run_public(sig),
            }
        )
    result.sort(key=lambda row: (-row["member_count"], row["differing_byte_count"], row["members"][0].lower()))
    return result


def shared_offsets(offset_sets: list[set[int]]) -> list[int]:
    if not offset_sets:
        return []
    result = set(offset_sets[0])
    for values in offset_sets[1:]:
        result.intersection_update(values)
    return sorted(result)


def variation_union(offset_sets: list[set[int]]) -> list[int]:
    result: set[int] = set()
    for values in offset_sets:
        result.update(values)
    return sorted(result)


def field_evidence_for_offsets(
    donor: dict,
    peers: list[dict],
    offsets: list[int],
    id_index: dict[bytes, list[dict]],
) -> dict:
    donor_hits = known_id_hits(donor["data"], id_index)
    peer_hits = {peer["name"]: known_id_hits(peer["data"], id_index) for peer in peers}
    evidence = []
    for start, end in runs(offsets):
        row = {
            "start": start,
            "end": end,
            "length": end - start + 1,
            "donor_hex": donor["data"][start : end + 1].hex(),
            "donor_known_id_overlaps": compact_targets(overlapping_hits(donor_hits, start, end)),
            "peers": [],
        }
        for peer in peers:
            row["peers"].append(
                {
                    "name": peer["name"],
                    "hex": peer["data"][start : end + 1].hex(),
                    "known_id_overlaps": compact_targets(overlapping_hits(peer_hits[peer["name"]], start, end)),
                }
            )
        evidence.append(row)
    return {
        "offset_count": len(offsets),
        "runs": evidence,
    }


def pair_report(label: str, records: list[dict], mgs: list[dict], id_index: dict[bytes, list[dict]]) -> dict:
    names = PAIRS[label]
    stock_i, stock_row = payload_record(records, names["stock"])
    dedicated_i, dedicated_row = payload_record(records, names["dedicated"])
    donor = next(row for row in mgs if row["record_index"] == stock_i)
    dedicated = next(row for row in mgs if row["record_index"] == dedicated_i)

    check(donor["payload_bytes"] == names["expected_bytes"], f"{label}: donor size changed")
    check(dedicated["data"] == donor["data"], f"{label}: retired Candidate 2 clone condition changed")

    native_same_size = [
        row for row in mgs
        if row["name"].lower() not in DEDICATED
        and row["payload_bytes"] == donor["payload_bytes"]
        and row["record_index"] != donor["record_index"]
    ]
    check(native_same_size, f"{label}: no native same-size peers")

    ranked = sorted(
        native_same_size,
        key=lambda peer: (len(diff_offsets(donor["data"], peer["data"])), peer["name"].lower(), peer["record_index"]),
    )
    min_diff = len(diff_offsets(donor["data"], ranked[0]["data"]))
    closest = [peer for peer in ranked if len(diff_offsets(donor["data"], peer["data"])) == min_diff]

    all_sets = [set(diff_offsets(donor["data"], peer["data"])) for peer in native_same_size]
    closest_sets = [set(diff_offsets(donor["data"], peer["data"])) for peer in closest]
    all_common = shared_offsets(all_sets)
    closest_common = shared_offsets(closest_sets)
    closest_union = variation_union(closest_sets)

    nearest_details = [diff_detail(donor, peer, id_index) for peer in ranked[:8]]

    return {
        "donor": {
            "record_index": donor["record_index"],
            "name": donor["name"],
            "id": donor["id_hex"],
            "payload_bytes": donor["payload_bytes"],
            "payload_sha256": sha256(donor["data"]),
        },
        "candidate2_dedicated_payload_exact_donor_clone": dedicated["data"] == donor["data"],
        "native_same_size_peer_count_excluding_donor": len(native_same_size),
        "minimum_native_diff_bytes": min_diff,
        "closest_cohort_count": len(closest),
        "closest_cohort_members": [peer["name"] for peer in closest],
        "closest_cohort_common_offsets": field_evidence_for_offsets(donor, closest, closest_common, id_index),
        "closest_cohort_union_offsets": {
            "offset_count": len(closest_union),
            "runs": run_public(closest_union),
        },
        "closest_cohort_has_identical_diff_signature": len({diff_offsets(donor["data"], peer["data"]) for peer in closest}) == 1,
        "all_same_size_peers_common_offsets": field_evidence_for_offsets(donor, ranked[:8], all_common, id_index),
        "nearest_native_peers": nearest_details,
        "native_diff_signature_classes": signature_classes(donor, native_same_size)[:16],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--structure-report", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raw = args.candidate_wad.read_bytes()
    candidate_sha = sha256(raw)
    check(candidate_sha == EXPECTED_CANDIDATE_SHA, f"Candidate 2 WAD SHA mismatch: {candidate_sha}")

    prior = json.loads(args.structure_report.read_text(encoding="utf-8"))
    check(prior.get("result") == "NORNIR_MODEL_GROUP_PAYLOAD_STRUCTURE_AUDIT_PASSED",
          "payload-structure prerequisite did not pass")
    check(prior.get("candidate_wad_sha256") == candidate_sha,
          "payload-structure report does not describe this Candidate 2 WAD")
    proofs = prior.get("proofs", {})
    check(proofs.get("candidate2_retired") is True, "Candidate 2 retirement proof missing")
    check(proofs.get("specific_internal_identity_field_proven") is False,
          "prerequisite unexpectedly claims a decoded hidden identity field")
    check(proofs.get("candidate3_constructed") is False, "Candidate 3 already constructed unexpectedly")
    check(proofs.get("runtime_install_allowed") is False, "runtime gate unexpectedly open")

    logical = load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "Candidate 2 WAD round-trip failed")
    mgs = mg_payloads(records)
    id_index = build_id_index(records)

    pairs = {
        "map": pair_report("map", records, mgs, id_index),
        "hud": pair_report("hud", records, mgs, id_index),
    }

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate_wad_sha256": candidate_sha,
        "pairs": pairs,
        "proofs": {
            "candidate_reparse_roundtrip_exact": True,
            "candidate2_retired": True,
            "candidate2_exact_clone_condition_preserved": all(
                row["candidate2_dedicated_payload_exact_donor_clone"] for row in pairs.values()
            ),
            "native_same_size_peer_differentials_measured": True,
            "known_resource_id_overlap_measured": True,
            "specific_internal_identity_field_proven": False,
            "candidate3_constructed": False,
            "runtime_install_allowed": False,
        },
        "interpretation": {
            "proven": "Native same-size MG payloads have measurable donor-specific differential regions. The report distinguishes bytes that overlap embedded IDs of known WAD resources from bytes that remain opaque.",
            "not_proven": "A differential region is not by itself a hidden identity/cache key. Candidate 3 must not be defined from correlation alone.",
            "next_step": "Use the closest-cohort differential runs and known-resource overlap evidence to decide whether a fully referenced native-style MG transform can be defined without guessing opaque bytes.",
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
        row = pairs[label]
        print(f"  {label}:")
        print(f"    same-size peers excl donor: {row['native_same_size_peer_count_excluding_donor']}")
        print(f"    minimum native diff bytes: {row['minimum_native_diff_bytes']}")
        print(f"    closest cohort count: {row['closest_cohort_count']}")
        print(f"    closest cohort: {', '.join(row['closest_cohort_members'])}")
        print(f"    closest cohort identical diff signature: {str(row['closest_cohort_has_identical_diff_signature']).lower()}")
        print(f"    closest common differential bytes: {row['closest_cohort_common_offsets']['offset_count']}")
        print(f"    all-peer common differential bytes: {row['all_same_size_peers_common_offsets']['offset_count']}")
        closest = row['nearest_native_peers'][0]
        print(f"    closest peer: {closest['name']}")
        print(f"      diff bytes/runs: {closest['differing_byte_count']}/{closest['differing_run_count']}")
        print(f"      diff bytes inside known resource-ID windows: {closest['diff_bytes_inside_known_resource_id_windows']}")
        print(f"      diff bytes outside known resource-ID windows: {closest['diff_bytes_outside_known_resource_id_windows']}")
        print("      first differential runs:")
        for d in closest['diff_runs'][:16]:
            donor_refs = sum(hit['target_count'] for hit in d['donor_known_id_overlaps'])
            peer_refs = sum(hit['target_count'] for hit in d['peer_known_id_overlaps'])
            print(f"        0x{d['start']:03X}-0x{d['end']:03X} len {d['length']} | known-ID overlap donor/peer {donor_refs}/{peer_refs}")
    print("  specific hidden identity field proven: false")
    print("  Candidate 3 constructed: false")
    print("  runtime install allowed: false")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
