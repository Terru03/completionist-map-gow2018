#!/usr/bin/env python3
"""Standalone-record-safe wrapper for the Nornir MG isolation builder.

The first isolation attempt assumed MG_mapicondock_0 and MG_boatdock_0 were
ordinary WAD resource groups. Runtime-format inspection proved these two donor
MG payloads are standalone data-bearing records with no GroupStart parent.

This wrapper changes only that structural assumption. A standalone payload is
treated as a one-record resource span; grouped resources still use the original
group logic. The underlying builder keeps all accounting, retargeting, reparse,
reverse-reference and byte-exact normalization proofs intact.

No God of War file is modified.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "build-nornir-mg-isolation-offline.py"


def load_base():
    spec = importlib.util.spec_from_file_location("completionist_nornir_mg_isolation_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load base builder: {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()
_original_group_bounds = base.group_bounds
_original_build = base.build


def resource_span(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    """Return containing group bounds, or the payload itself when standalone."""
    row = records[payload_index]
    parent = row["parent"]
    if parent is None:
        base.check(row["kind"] == 1 and bool(row["data"]),
                   f"{row['name']}: parentless resource is not a standalone payload")
        return payload_index, payload_index
    return _original_group_bounds(logical, records, payload_index)


# All base helpers resolve group_bounds from the base module globals at runtime.
# Replacing this one hook therefore preserves grouped model-resource behavior
# while allowing the two stock MG donor payloads to be cloned as one-row spans.
base.group_bounds = resource_span


def build_standalone_safe(failed_raw: bytes, raven_raw: bytes):
    logical = base.load_logical()
    failed_records = logical.parse_wad(failed_raw)
    raven_records = logical.parse_wad(raven_raw)

    shape = {}
    for kind in ("map", "hud"):
        c_idx, c = base.unique_payload(failed_records, base.STOCK_MG[kind])
        r_idx, r = base.unique_payload(raven_records, base.STOCK_MG[kind])
        base.check(c["parent"] is None,
                   f"{kind}: failed-candidate {base.STOCK_MG[kind]} is no longer standalone")
        base.check(r["parent"] is None,
                   f"{kind}: Raven-baseline {base.STOCK_MG[kind]} is no longer standalone")
        base.check(c["id"] == r["id"], f"{kind}: standalone stock MG ID differs from Raven baseline")
        base.check(logical.record_bytes(c) == logical.record_bytes(r),
                   f"{kind}: standalone stock MG record differs from Raven baseline")
        shape[kind] = {
            "name": base.STOCK_MG[kind],
            "failed_candidate_record_index": c_idx,
            "raven_record_index": r_idx,
            "payload_index": c["payload_index"],
            "id": c["id"].hex(),
            "parent": None,
            "physical_rows": 1,
            "payload_rows": 1,
            "record_byte_identical_to_raven_baseline": True,
        }

    candidate, report = _original_build(failed_raw, raven_raw)
    report["standalone_stock_mg_donors"] = shape
    report["proofs"]["stock_mg_payloads_are_standalone_records"] = True
    report["proofs"]["standalone_stock_mg_records_match_raven_baseline_byte_exactly"] = True
    report["proofs"]["standalone_resource_span_logic_used"] = True
    return candidate, report


base.build = build_standalone_safe


if __name__ == "__main__":
    base.main()
