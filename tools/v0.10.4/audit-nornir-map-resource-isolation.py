#!/usr/bin/env python3
"""Read-only runtime-failure audit for Nornir/Raven map resource isolation.

This does not patch or install anything. It compares the frozen Raven production
r_ui.wad with the failed Nornir lifecycle candidate and reports whether cloned
model/material/prototype/root payloads still carry Raven/stock identities or
byte-identical donor payloads that may alias at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
EXPECTED_RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
RESULT = "NORNIR_MAP_RESOURCE_ISOLATION_AUDIT_READ_ONLY"

RAVEN = {
    "map_root": "gomapiconcompletionistraven",
    "map_proto": "goProtoMapIconCompletionistRaven",
    "map_model": "MDL_completionistraven",
    "material": "MAT_AE4AD85BB993F040",
    "hud_root": "gocompletionistravenhud",
    "hud_proto": "goProtoCompletionistRavenHUD",
    "hud_model": "MDL_completionistravenhud",
}
NORNIR = {
    "map_root": "gomapiconcompletionistnornirchest",
    "map_proto": "goProtoMapIconCompletionistNornirChest",
    "map_model": "MDL_completionistnornirchest",
    "material": "MAT_completionistnornirchest",
    "hud_root": "gocompletionistnornirchesthud",
    "hud_proto": "goProtoCompletionistNornirChestHUD",
    "hud_model": "MDL_completionistnornirchesthud",
}
STOCK_NAMES = ("gomapicondock", "goProtoNW633B8059", "MG_boatdock_0")


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_runtime_isolation_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def one_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def group_rows(logical, records: list[dict], payload_index: int) -> list[tuple[int, dict]]:
    parent = records[payload_index]["parent"]
    check(parent is not None and records[parent]["kind"] == 2,
          f"{records[payload_index]['name']}: payload has no group parent")
    end = logical.matching_group_end(records, parent)
    return [(i, records[i]) for i in range(parent, end + 1)]


def links(logical, records: list[dict], payload_index: int) -> list[dict]:
    out = []
    for i, row in group_rows(logical, records, payload_index):
        if row["kind"] == 1 and not row["data"]:
            out.append({"index": i, "name": row["name"], "id": row["id"].hex()})
    return out


def ascii_tokens(blob: bytes) -> list[str]:
    values = []
    for raw in re.findall(rb"[ -~]{4,}", blob):
        text = raw.decode("ascii", errors="ignore")
        low = text.lower()
        if any(word in low for word in ("raven", "nornir", "dock", "boat", "mdl_", "mat_", "goproto", "mapicon")):
            values.append(text)
    # stable unique order
    seen = set()
    return [x for x in values if not (x in seen or seen.add(x))]


def occurrences(blob: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    out = []
    start = 0
    while True:
        at = blob.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def compare_pair(logical, raven_records: list[dict], candidate_records: list[dict], key: str) -> dict:
    r_idx, r = one_payload(raven_records, RAVEN[key])
    n_idx, n = one_payload(candidate_records, NORNIR[key])
    rb = bytes(r["data"])
    nb = bytes(n["data"])
    common = min(len(rb), len(nb))
    diff_count = sum(1 for i in range(common) if rb[i] != nb[i]) + abs(len(rb) - len(nb))
    return {
        "raven": {"index": r_idx, "name": r["name"], "id": r["id"].hex(), "bytes": len(rb),
                  "links": links(logical, raven_records, r_idx), "ascii_tokens": ascii_tokens(rb)},
        "nornir": {"index": n_idx, "name": n["name"], "id": n["id"].hex(), "bytes": len(nb),
                   "links": links(logical, candidate_records, n_idx), "ascii_tokens": ascii_tokens(nb)},
        "payload_byte_identical": rb == nb,
        "payload_byte_difference_count": diff_count,
        "raven_record_id_occurrences_in_nornir_payload": occurrences(nb, r["id"]),
        "nornir_record_id_occurrences_in_nornir_payload": occurrences(nb, n["id"]),
        "raven_name_occurrences_in_nornir_payload": occurrences(nb.lower(), RAVEN[key].encode("ascii").lower()),
        "nornir_name_occurrences_in_nornir_payload": occurrences(nb.lower(), NORNIR[key].encode("ascii").lower()),
    }


def named_records(records: list[dict], name: str) -> list[dict]:
    return [{"index": i, "kind": row["kind"], "flags": row["flags"], "bytes": len(row["data"]),
             "name": row["name"], "id": row["id"].hex(), "parent": row["parent"]}
            for i, row in enumerate(records) if row["name"].lower() == name.lower()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-wad", type=Path, required=True)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raven_raw = args.raven_wad.read_bytes()
    candidate_raw = args.candidate_wad.read_bytes()
    check(sha(raven_raw) == EXPECTED_RAVEN_WAD,
          "baseline r_ui.wad is not the frozen runtime-proven Raven production WAD")

    logical = load_logical()
    raven_records = logical.parse_wad(raven_raw)
    candidate_records = logical.parse_wad(candidate_raw)
    check(logical.serialize_wad(raven_records) == raven_raw, "Raven WAD round-trip failed")
    check(logical.serialize_wad(candidate_records) == candidate_raw, "candidate WAD round-trip failed")

    pairs = {key: compare_pair(logical, raven_records, candidate_records, key)
             for key in ("material", "map_model", "map_proto", "map_root", "hud_model", "hud_proto", "hud_root")}

    stock = {name: named_records(candidate_records, name) for name in STOCK_NAMES}
    nornir_names = {name: named_records(candidate_records, name) for name in NORNIR.values()}
    raven_names = {name: named_records(candidate_records, name) for name in RAVEN.values()}

    flags = {
        "nornir_map_model_payload_byte_identical_to_raven": pairs["map_model"]["payload_byte_identical"],
        "nornir_hud_model_payload_byte_identical_to_raven": pairs["hud_model"]["payload_byte_identical"],
        "nornir_material_payload_byte_identical_to_raven": pairs["material"]["payload_byte_identical"],
        "nornir_map_model_contains_raven_ascii_identity": bool(pairs["map_model"]["raven_name_occurrences_in_nornir_payload"] or pairs["map_model"]["nornir"]["ascii_tokens"]),
        "nornir_map_proto_contains_raven_record_id": bool(pairs["map_proto"]["raven_record_id_occurrences_in_nornir_payload"]),
        "nornir_map_root_contains_raven_record_id": bool(pairs["map_root"]["raven_record_id_occurrences_in_nornir_payload"]),
    }

    report = {
        "schema": 1,
        "result": RESULT,
        "raven_wad_sha256": sha(raven_raw),
        "candidate_wad_sha256": sha(candidate_raw),
        "pairs": pairs,
        "stock_named_records": stock,
        "raven_named_records_in_candidate": raven_names,
        "nornir_named_records_in_candidate": nornir_names,
        "suspicion_flags": flags,
        "interpretation": {
            "runtime_failure_already_observed": True,
            "root_cause_proven_by_this_audit": False,
            "purpose": "identify donor identity/dependency aliasing before any second runtime candidate"
        },
        "safety": {"game_files_written": False, "runtime_install_performed": False,
                   "save_state_written": False, "progression_state_written": False,
                   "marker_state_written": False}
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  Raven WAD:     {report['raven_wad_sha256']}")
    print(f"  candidate WAD: {report['candidate_wad_sha256']}")
    for key in ("material", "map_model", "map_proto", "map_root", "hud_model", "hud_proto", "hud_root"):
        row = pairs[key]
        print(f"  {key}: identical={str(row['payload_byte_identical']).lower()} diffBytes={row['payload_byte_difference_count']} ")
        print(f"    Raven links:  " + ", ".join(f"{x['name']}:{x['id']}" for x in row['raven']['links']))
        print(f"    Nornir links: " + ", ".join(f"{x['name']}:{x['id']}" for x in row['nornir']['links']))
        if row['nornir']['ascii_tokens']:
            print("    Nornir payload tokens: " + " | ".join(row['nornir']['ascii_tokens']))
        if row['raven_record_id_occurrences_in_nornir_payload']:
            print("    Raven record ID remains in Nornir payload at: " + ",".join(hex(x) for x in row['raven_record_id_occurrences_in_nornir_payload']))
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
