#!/usr/bin/env python3
"""Read-only forensic audit for Candidate 2 model-group physical identity.

Candidate 2 gave the Nornir map/HUD models dedicated top-level MG names and IDs,
but the dedicated MG payloads were byte-for-byte copies of the stock boat-dock
MG payloads. Runtime then rendered Nornir art on stock boat docks, displaced the
Raven map marker and crashed on map open.

This audit deliberately does not attempt another repair. It proves what is and
is not physically distinct inside the isolated WAD and blocks Candidate 2 from
runtime reuse. It writes only a JSON report outside the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_HIDDEN_IDENTITY_COLLISION_CONFIRMED"
EXPECTED_ISOLATED_SHA = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"

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


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_hidden_identity_logical", path)
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


def positions(raw: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    start = 0
    while True:
        pos = raw.find(needle, start)
        if pos < 0:
            break
        out.append(pos)
        start = pos + 1
    return out


def printable_ascii(raw: bytes) -> list[dict]:
    found = []
    for m in re.finditer(rb"[ -~]{4,}", raw):
        found.append({"offset": m.start(), "text": m.group().decode("ascii", errors="replace")})
    return found


def identity_needles(name: str, rid: bytes) -> dict[str, bytes]:
    return {
        "record_id_raw": rid,
        "record_id_reversed": rid[::-1],
        "record_id_hex_ascii": rid.hex().encode("ascii"),
        "name_ascii": name.encode("ascii"),
        "name_utf16le": name.encode("utf-16le"),
    }


def occurrence_report(payload: bytes, name: str, rid: bytes) -> dict:
    return {
        label: positions(payload, needle)
        for label, needle in identity_needles(name, rid).items()
    }


def common_chunk_summary(a: bytes, b: bytes) -> dict:
    check(len(a) == len(b), "payload lengths differ")
    differing = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return {
        "length": len(a),
        "differing_byte_count": len(differing),
        "first_differing_offsets": differing[:64],
        "fully_identical": not differing,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--archived-audit", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raw = args.candidate_wad.read_bytes()
    wad_sha = sha256(raw)
    check(wad_sha == EXPECTED_ISOLATED_SHA,
          f"isolated candidate WAD SHA mismatch: {wad_sha}")

    archived = json.loads(args.archived_audit.read_text(encoding="utf-8"))
    archived_sha = archived.get("sha256", {}).get("isolated_candidate")
    check(archived_sha == wad_sha,
          "archived isolation audit does not describe this candidate WAD")

    logical = load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "candidate WAD round-trip failed")

    pair_reports: dict[str, dict] = {}
    all_identical = True
    all_top_level_distinct = True

    for label, names in PAIRS.items():
        stock_i, stock = payload_record(records, names["stock"])
        dedicated_i, dedicated = payload_record(records, names["dedicated"])
        stock_data = stock["data"]
        dedicated_data = dedicated["data"]

        compare = common_chunk_summary(stock_data, dedicated_data)
        all_identical = all_identical and compare["fully_identical"]
        top_level_distinct = (
            stock["name"].lower() != dedicated["name"].lower()
            and stock["id"] != dedicated["id"]
            and stock_i != dedicated_i
        )
        all_top_level_distinct = all_top_level_distinct and top_level_distinct

        pair_reports[label] = {
            "stock": {
                "record_index": stock_i,
                "name": stock["name"],
                "id": stock["id"].hex(),
                "flags": stock["flags"],
                "payload_index": stock["payload_index"],
                "payload_bytes": len(stock_data),
                "payload_sha256": sha256(stock_data),
                "self_identity_occurrences_inside_payload": occurrence_report(
                    stock_data, stock["name"], stock["id"]
                ),
                "printable_ascii": printable_ascii(stock_data),
            },
            "dedicated": {
                "record_index": dedicated_i,
                "name": dedicated["name"],
                "id": dedicated["id"].hex(),
                "flags": dedicated["flags"],
                "payload_index": dedicated["payload_index"],
                "payload_bytes": len(dedicated_data),
                "payload_sha256": sha256(dedicated_data),
                "self_identity_occurrences_inside_payload": occurrence_report(
                    dedicated_data, dedicated["name"], dedicated["id"]
                ),
                "stock_identity_occurrences_inside_payload": occurrence_report(
                    dedicated_data, stock["name"], stock["id"]
                ),
                "printable_ascii": printable_ascii(dedicated_data),
            },
            "top_level_record_identity_distinct": top_level_distinct,
            "payload_comparison": compare,
            "dedicated_payload_is_unmodified_stock_clone": compare["fully_identical"],
        }

    archived_claim = archived.get("proofs", {}).get("dedicated_mg_payloads_match_stock_donors")
    check(archived_claim is True, "archived audit no longer records byte-identical donor payloads")
    check(all_top_level_distinct, "expected dedicated top-level MG names/IDs to be distinct")
    check(all_identical, "Candidate 2 no longer has the exact payload-clone condition being audited")

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate_wad_sha256": wad_sha,
        "runtime_failure": {
            "raven_map_marker_disappeared": True,
            "stock_boat_docks_rendered_nornir_chest_art": True,
            "map_open_crash": True,
            "candidate2_retired": True,
        },
        "model_group_pairs": pair_reports,
        "proofs": {
            "candidate_reparse_roundtrip_exact": True,
            "top_level_mg_names_and_ids_are_distinct": all_top_level_distinct,
            "dedicated_map_mg_payload_is_byte_identical_to_stock_donor": pair_reports["map"]["payload_comparison"]["fully_identical"],
            "dedicated_hud_mg_payload_is_byte_identical_to_stock_donor": pair_reports["hud"]["payload_comparison"]["fully_identical"],
            "candidate2_top_level_isolation_was_insufficient_at_runtime": True,
            "specific_internal_identity_field_proven": False,
            "candidate2_runtime_install_allowed": False,
        },
        "interpretation": {
            "proven": "Candidate 2 changed the MG record names and IDs but did not create physically independent model-group payloads. Both dedicated Nornir MG payloads are exact stock donor clones, and runtime demonstrated that this construction aliases stock boat-dock behaviour/art.",
            "not_proven": "This audit does not name a specific hidden MG field as the cache/resource key unless that field can be independently decoded. The runtime result is the authority that invalidates Candidate 2.",
            "next_step": "Construct a genuinely independent Nornir model-group payload using the runtime-proven Raven construction as the structural reference, then require offline donor-preservation and reverse-reference proofs before any new runtime candidate.",
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
    print(f"  candidate WAD: {wad_sha}")
    for label in ("map", "hud"):
        p = pair_reports[label]
        print(f"  {label} top-level MG identity distinct: {str(p['top_level_record_identity_distinct']).lower()}")
        print(f"  {label} dedicated payload byte-identical to stock donor: {str(p['dedicated_payload_is_unmodified_stock_clone']).lower()}")
        print(f"    stock payload SHA:     {p['stock']['payload_sha256']}")
        print(f"    dedicated payload SHA: {p['dedicated']['payload_sha256']}")
    print("  Candidate 2 runtime install allowed: false")
    print("  specific hidden identity field proven: false")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
