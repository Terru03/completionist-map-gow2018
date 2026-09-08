"""Correlate stock WAD type-table rows with physical payload signatures.

Read-only static evidence.  This does not assume that every table row describes
one physical WAD payload.  It tests several observed tag encodings and reports
where a complete physical cohort exactly accounts for a table row.  Rows that
cannot be explained this way remain unresolved and may represent nested/runtime
objects.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
LOGICAL = HERE / "build-raven-ui-logical-clone.py"
spec = importlib.util.spec_from_file_location("completionist_logical", LOGICAL)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load WAD parser")
logical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logical)

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
SOURCE_NAMES = {
    "TX_mapmarker_docklocation_emissive_FCC664130951154C",
    "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
    "MAT_0C599DC8DC7E2170",
    "MDL_mapicondock",
    "goProtoMapIconDock",
    "gomapicondock",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def first_dword(record):
    return struct.unpack_from("<I", record["data"])[0] if len(record["data"]) >= 4 else None


def transforms(word: int):
    return {
        "raw32": word,
        "low28": word & 0x0FFFFFFF,
        "low24": word & 0x00FFFFFF,
        "low20": word & 0x000FFFFF,
        "low16": word & 0x0000FFFF,
    }


def public_record(record):
    word = first_dword(record)
    out = {
        "name": record["name"],
        "payload_index": record["payload_index"],
        "file_offset": f"0x{record['original_offset']:X}",
        "kind": f"0x{record['kind']:X}",
        "flags": f"0x{record['flags']:X}",
        "bytes": len(record["data"]),
        "resource_id": record["id"].hex(),
    }
    if word is not None:
        out["first_dword"] = f"0x{word:X}"
        out["first_dword_transforms"] = {k: f"0x{v:X}" for k, v in transforms(word).items()}
    return out


def contiguous_ranges(values):
    values = sorted(values)
    if not values:
        return []
    out = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        out.append([start, prev])
        start = prev = value
    out.append([start, prev])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--r-ui-wad", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    wad = args.r_ui_wad.resolve()
    raw = wad.read_bytes()
    check(sha(raw) == EXPECTED_WAD, "r_ui.wad is not the pinned stock build")
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "stock WAD byte round-trip failed")
    payloads = logical.payload_records(records)
    check(len(payloads) >= 2, "missing WAD accounting payloads")
    table = logical.read_type_table(payloads[1]["data"])
    table_by_key = {row["key"]: row for row in table}

    # Cohorts preserve header kind/flags because those are part of the physical
    # serializer format and prevent unrelated first-dword collisions from being
    # merged together.
    cohorts = collections.defaultdict(list)
    for rec in payloads:
        word = first_dword(rec)
        if word is None:
            continue
        for transform, value in transforms(word).items():
            cohorts[(transform, value, rec["kind"], rec["flags"])].append(rec)

    rows = []
    explained_keys = set()
    for row in table:
        candidates = []
        for (transform, value, kind, flags), members in cohorts.items():
            if value != row["key"]:
                continue
            indices = [r["payload_index"] for r in members if r["payload_index"] is not None]
            entry = {
                "transform": transform,
                "kind": f"0x{kind:X}",
                "flags": f"0x{flags:X}",
                "physical_payload_count": len(members),
                "count_matches_table": len(members) == row["count"],
                "payload_index_min": min(indices) if indices else None,
                "payload_index_max": max(indices) if indices else None,
                "payload_index_ranges": contiguous_ranges(indices),
                "table_base_equals_physical_min": bool(indices) and min(indices) == row["base"],
                "sample_names": [r["name"] for r in members[:8]],
            }
            candidates.append(entry)
        exact = [x for x in candidates if x["count_matches_table"]]
        if exact:
            explained_keys.add(row["key"])
        rows.append({
            "index": row["index"],
            "key": f"0x{row['key']:X}",
            "base": row["base"],
            "count": row["count"],
            "exact_count_physical_cohorts": exact,
            "all_matching_physical_cohorts": candidates,
            "physical_cohort_explains_full_row": bool(exact),
        })

    source = []
    for rec in records:
        if not rec["data"] or rec["name"] not in SOURCE_NAMES:
            continue
        item = public_record(rec)
        word = first_dword(rec)
        matches = []
        if word is not None:
            for transform, value in transforms(word).items():
                row = table_by_key.get(value)
                if row is not None:
                    cohort = cohorts[(transform, value, rec["kind"], rec["flags"])]
                    matches.append({
                        "transform": transform,
                        "table_key": f"0x{value:X}",
                        "table_base": row["base"],
                        "table_count": row["count"],
                        "same_header_cohort_count": len(cohort),
                        "same_header_cohort_exactly_matches_table_count": len(cohort) == row["count"],
                    })
        item["table_signature_matches"] = matches
        source.append(item)

    result = {
        "result": "READ_ONLY_WAD_TYPE_SIGNATURE_CORRELATION",
        "game_files_written": False,
        "runtime_test_ready": False,
        "source_sha256": sha(raw),
        "physical_payload_count": len(payloads),
        "type_table_row_count": len(table),
        "type_table_total": sum(r["count"] for r in table),
        "rows_explained_by_exact_physical_cohort": len(explained_keys),
        "rows_not_explained_by_exact_physical_cohort": len(table) - len(explained_keys),
        "type_rows": rows,
        "raven_clone_source_signatures": source,
        "interpretation": {
            "physical_payload_index_is_not_assumed_to_be_runtime_type_base": True,
            "exact_cohort_count_match_is_static_correlation_not_loader_semantic_proof": True,
            "unexplained_rows_may_describe_nested_or_nonphysical_serialized_objects": True,
            "next_gate": "Combine these cohort correlations with focused native loader disassembly before changing any WAD type count/base.",
        },
    }
    check(sha(wad.read_bytes()) == EXPECTED_WAD, "r_ui.wad changed during scan")
    result["source_hash_unchanged_after_scan"] = True
    out = args.output.resolve()
    allowed = (HERE.parent.parent / "archive" / "field-logs").resolve()
    check(out.is_relative_to(allowed) and out.suffix.lower() == ".json", "output must be repo archive/field-logs JSON")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "table_rows": len(table),
        "rows_explained_by_exact_physical_cohort": len(explained_keys),
        "unexplained_rows": len(table) - len(explained_keys),
        "runtime_test_ready": False,
        "output": str(out),
    }, indent=2))
    print("No God of War files, saves, boot options, or progression state were modified.")


if __name__ == "__main__":
    main()
