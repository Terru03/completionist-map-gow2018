#!/usr/bin/env python3
"""Read-only structural/differential audit of the retired Nornir Candidate 2 MG payloads.

Candidate 2 proved that changing only the top-level model-group record name/ID
while copying the stock boat-dock payload byte-for-byte is not runtime-safe.
This audit does not mutate a WAD. It compares the failed dedicated payloads with
all native model-group payloads in the same WAD to find evidence that can guide
a physically independent Candidate 3 without guessing an opaque identity field.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_MODEL_GROUP_PAYLOAD_STRUCTURE_AUDIT_PASSED"
EXPECTED_CANDIDATE_SHA = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"
EXPECTED_PAYLOAD_SHA = {
    "map": "faec010b37a5f1b24908a747316e344c4bf84977b67b98c6969e77b9cda8d364",
    "hud": "af1de3f90a7ed3bf09181b4ef91c9fd04a2ead68ba86aa1ef9acb3fb22be32b1",
}
PAIRS = {
    "map": {
        "stock": "MG_mapicondock_0",
        "dedicated": "MG_completionistnornirchest_map",
    },
    "hud": {
        "stock": "MG_boatdock_0",
        "dedicated": "MG_completionistnornirchest_hud",
    },
}
DEDICATED_NAMES = {v["dedicated"].lower() for v in PAIRS.values()}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes | bytearray) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_mg_payload_structure_logical", path)
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
                "id": row["id"].hex(),
                "id_bytes": row["id"],
                "flags": row["flags"],
                "payload_index": row["payload_index"],
                "parent": row["parent"],
                "top_level": row["parent"] is None,
                "payload_bytes": len(row["data"]),
                "payload_sha256": sha256(row["data"]),
                "data": bytes(row["data"]),
            }
        )
    return out


def positions(raw: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    result = []
    start = 0
    while True:
        pos = raw.find(needle, start)
        if pos < 0:
            return result
        result.append(pos)
        start = pos + 1


def diff_offsets(a: bytes, b: bytes) -> list[int]:
    check(len(a) == len(b), "diff_offsets requires equal lengths")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def runs(offsets: list[int], limit: int | None = None) -> list[dict]:
    if not offsets:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = offsets[0]
    for value in offsets[1:]:
        if value != prev + 1:
            groups.append((start, prev))
            start = value
        prev = value
    groups.append((start, prev))
    if limit is not None:
        groups = groups[:limit]
    return [
        {"start": start, "end": end, "length": end - start + 1}
        for start, end in groups
    ]


def printable_ascii(raw: bytes) -> list[dict]:
    return [
        {"offset": m.start(), "text": m.group().decode("ascii", errors="replace")}
        for m in re.finditer(rb"[ -~]{4,}", raw)
    ]


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


def embedded_known_ids(payload: bytes, id_index: dict[bytes, list[dict]], limit: int = 128) -> dict:
    hits = []
    for offset in range(0, max(0, len(payload) - 15)):
        chunk = payload[offset : offset + 16]
        refs = id_index.get(chunk)
        if not refs:
            continue
        hits.append(
            {
                "offset": offset,
                "id": chunk.hex(),
                "targets": refs[:12],
                "target_count": len(refs),
            }
        )
        if len(hits) >= limit:
            break
    return {
        "match_count_returned": len(hits),
        "truncated": len(hits) >= limit,
        "matches": hits,
    }


def nearest_same_size(
    donor: dict,
    native_same_size: list[dict],
    limit: int = 8,
) -> list[dict]:
    compared = []
    for peer in native_same_size:
        if peer["record_index"] == donor["record_index"]:
            continue
        offsets = diff_offsets(donor["data"], peer["data"])
        compared.append(
            {
                "record_index": peer["record_index"],
                "name": peer["name"],
                "id": peer["id"],
                "payload_sha256": peer["payload_sha256"],
                "differing_byte_count": len(offsets),
                "differing_run_count": len(runs(offsets)),
                "first_diff_runs": runs(offsets, 24),
            }
        )
    compared.sort(key=lambda row: (row["differing_byte_count"], row["name"].lower(), row["record_index"]))
    return compared[:limit]


def equivalence_classes(mgs: list[dict]) -> list[dict]:
    by_sha: dict[str, list[dict]] = defaultdict(list)
    for row in mgs:
        by_sha[row["payload_sha256"]].append(row)
    result = []
    for digest, members in by_sha.items():
        if len(members) < 2:
            continue
        result.append(
            {
                "payload_sha256": digest,
                "payload_bytes": members[0]["payload_bytes"],
                "member_count": len(members),
                "members": [
                    {
                        "record_index": row["record_index"],
                        "name": row["name"],
                        "id": row["id"],
                        "top_level": row["top_level"],
                        "dedicated_nornir": row["name"].lower() in DEDICATED_NAMES,
                    }
                    for row in members
                ],
            }
        )
    result.sort(key=lambda row: (-row["member_count"], row["payload_bytes"], row["payload_sha256"]))
    return result


def peer_variation(donor: dict, peers: list[dict]) -> dict:
    offsets: set[int] = set()
    for peer in peers:
        if peer["record_index"] == donor["record_index"]:
            continue
        offsets.update(diff_offsets(donor["data"], peer["data"]))
    ordered = sorted(offsets)
    return {
        "native_same_size_peer_count_excluding_donor": max(0, len(peers) - 1),
        "offsets_that_vary_against_at_least_one_native_peer_count": len(ordered),
        "variation_runs": runs(ordered, 96),
        "variation_runs_truncated": len(runs(ordered)) > 96,
        "first_variable_offsets": ordered[:128],
    }


def obvious_identity_occurrences(payload: bytes, name: str, rid: bytes) -> dict:
    return {
        "record_id_raw": positions(payload, rid),
        "record_id_reversed": positions(payload, rid[::-1]),
        "record_id_hex_ascii": positions(payload, rid.hex().encode("ascii")),
        "name_ascii": positions(payload, name.encode("ascii")),
        "name_utf16le": positions(payload, name.encode("utf-16le")),
    }


def public_mg(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in {"data", "id_bytes"}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--hidden-audit", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raw = args.candidate_wad.read_bytes()
    wad_sha = sha256(raw)
    check(wad_sha == EXPECTED_CANDIDATE_SHA, f"Candidate 2 WAD SHA mismatch: {wad_sha}")

    hidden = json.loads(args.hidden_audit.read_text(encoding="utf-8"))
    check(hidden.get("result") == "NORNIR_HIDDEN_IDENTITY_COLLISION_CONFIRMED",
          "hidden-identity prerequisite did not pass")
    check(hidden.get("candidate_wad_sha256") == wad_sha,
          "hidden-identity report does not describe this candidate")
    proofs = hidden.get("proofs", {})
    check(proofs.get("candidate2_runtime_install_allowed") is False,
          "Candidate 2 runtime block is missing from hidden-identity proof")
    check(proofs.get("specific_internal_identity_field_proven") is False,
          "hidden-identity prerequisite unexpectedly claims a decoded identity field")

    logical = load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "Candidate 2 WAD round-trip failed")

    mgs = mg_payloads(records)
    check(mgs, "no model-group payloads found")
    id_index = build_id_index(records)
    classes = equivalence_classes(mgs)

    pair_reports = {}
    for label, names in PAIRS.items():
        stock_i, stock_row = payload_record(records, names["stock"])
        dedicated_i, dedicated_row = payload_record(records, names["dedicated"])
        stock = next(row for row in mgs if row["record_index"] == stock_i)
        dedicated = next(row for row in mgs if row["record_index"] == dedicated_i)

        check(stock["payload_sha256"] == EXPECTED_PAYLOAD_SHA[label],
              f"{label}: stock donor payload SHA changed")
        check(dedicated["payload_sha256"] == EXPECTED_PAYLOAD_SHA[label],
              f"{label}: dedicated payload SHA changed")
        check(stock["data"] == dedicated["data"],
              f"{label}: Candidate 2 no longer has the exact clone condition")

        native = [
            row for row in mgs
            if row["name"].lower() not in DEDICATED_NAMES
        ]
        same_size = [
            row for row in native
            if row["payload_bytes"] == stock["payload_bytes"]
        ]
        exact_native_peers = [
            row for row in same_size
            if row["record_index"] != stock["record_index"]
            and row["payload_sha256"] == stock["payload_sha256"]
        ]

        pair_reports[label] = {
            "stock": {
                **public_mg(stock),
                "obvious_self_identity_occurrences": obvious_identity_occurrences(
                    stock["data"], stock["name"], stock["id_bytes"]
                ),
                "embedded_known_resource_ids": embedded_known_ids(stock["data"], id_index),
                "printable_ascii": printable_ascii(stock["data"]),
            },
            "dedicated": {
                **public_mg(dedicated),
                "obvious_self_identity_occurrences": obvious_identity_occurrences(
                    dedicated["data"], dedicated["name"], dedicated["id_bytes"]
                ),
                "stock_header_identity_occurrences": obvious_identity_occurrences(
                    dedicated["data"], stock["name"], stock["id_bytes"]
                ),
                "embedded_known_resource_ids": embedded_known_ids(dedicated["data"], id_index),
                "printable_ascii": printable_ascii(dedicated["data"]),
            },
            "dedicated_payload_exact_stock_clone": True,
            "native_same_size_payload_count_including_donor": len(same_size),
            "native_exact_payload_peer_count_excluding_donor": len(exact_native_peers),
            "native_exact_payload_peers": [public_mg(row) for row in exact_native_peers[:32]],
            "nearest_native_same_size_peers": nearest_same_size(stock, same_size),
            "native_peer_variation": peer_variation(stock, same_size),
        }

    stock_only_mgs = [row for row in mgs if row["name"].lower() not in DEDICATED_NAMES]
    stock_only_classes = equivalence_classes(stock_only_mgs)

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate_wad_sha256": wad_sha,
        "model_group_inventory": {
            "payload_count": len(mgs),
            "top_level_payload_count": sum(row["top_level"] for row in mgs),
            "native_payload_count": len(stock_only_mgs),
            "candidate2_dedicated_payload_count": len(mgs) - len(stock_only_mgs),
            "all_exact_payload_equivalence_class_count": len(classes),
            "native_only_exact_payload_equivalence_class_count": len(stock_only_classes),
        },
        "pairs": pair_reports,
        "all_exact_payload_equivalence_classes": classes,
        "native_only_exact_payload_equivalence_classes": stock_only_classes,
        "proofs": {
            "candidate_reparse_roundtrip_exact": True,
            "candidate2_retired": True,
            "candidate2_map_payload_still_exact_stock_clone": pair_reports["map"]["dedicated_payload_exact_stock_clone"],
            "candidate2_hud_payload_still_exact_stock_clone": pair_reports["hud"]["dedicated_payload_exact_stock_clone"],
            "native_duplicate_payload_classes_measured": True,
            "same_size_native_peer_differentials_measured": True,
            "known_resource_id_windows_scanned": True,
            "specific_internal_identity_field_proven": False,
            "candidate3_constructed": False,
            "runtime_install_allowed": False,
        },
        "interpretation": {
            "purpose": "Measure native MG payload equivalence and same-size peer variation before editing any opaque MG bytes.",
            "important_limit": "Byte equality is proven for the failed Candidate 2 clones, but this report does not infer a cache key or hidden identity field from correlation alone.",
            "next_step": "Use the native exact-duplicate and nearest-peer evidence to identify a field-aware, offline-only Candidate 3 transform. Require reversible byte normalization and donor-preservation proofs before any transactional runtime gate.",
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
    print(f"candidate WAD: {wad_sha}")
    print(f"MG payloads measured: {len(mgs)}")
    print(f"native exact-payload equivalence classes: {len(stock_only_classes)}")
    for label in ("map", "hud"):
        pair = pair_reports[label]
        stock = pair["stock"]
        print(f"{label}:")
        print(f"  payload bytes: {stock['payload_bytes']}")
        print(f"  Candidate 2 dedicated payload exact stock clone: true")
        print(f"  native same-size payloads incl donor: {pair['native_same_size_payload_count_including_donor']}")
        print(f"  native exact payload peers excl donor: {pair['native_exact_payload_peer_count_excluding_donor']}")
        print(
            "  stock header ID embedded in stock payload: "
            + str(bool(stock["obvious_self_identity_occurrences"]["record_id_raw"])).lower()
        )
        nearest = pair["nearest_native_same_size_peers"]
        if nearest:
            print("  nearest native same-size peers:")
            for peer in nearest[:5]:
                print(
                    f"    {peer['name']} | diff bytes {peer['differing_byte_count']} "
                    f"| diff runs {peer['differing_run_count']}"
                )
        else:
            print("  nearest native same-size peers: none")
    print("specific hidden identity field proven: false")
    print("Candidate 3 constructed: false")
    print("runtime install allowed: false")
    print("game files written: false")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
