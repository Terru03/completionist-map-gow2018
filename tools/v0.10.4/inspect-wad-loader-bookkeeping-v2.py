"""Corrected entry point for the v0.10.4 WAD loader bookkeeping probe.

The first probe intentionally ranked native functions conservatively, but its
static table cross-check counted arbitrary first dwords from non-Rig payloads.
The stock WAD type table accounts Rig (header type/flags 0x3D) payloads. This
entry point replaces only that accounting layer while reusing the native probe.
"""
from __future__ import annotations

import collections
import importlib.util
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
BASE_TOOL = HERE / "inspect-wad-loader-bookkeeping.py"
spec = importlib.util.spec_from_file_location("wad_bookkeeping_base", BASE_TOOL)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load base bookkeeping probe")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def rig_type_word_counts(records: list[dict]) -> collections.Counter:
    return collections.Counter(
        base.payload_type_word(r)
        for r in records
        if r["data"] and r["flags"] == 0x3D and len(r["data"]) >= 4
    )


def accounting_evidence(logical, records: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    base.check(len(payloads) >= 2, "WAD lacks accounting payloads")
    heap, root = payloads[0], payloads[1]
    table = logical.read_type_table(root["data"])
    counts = rig_type_word_counts(records)
    flags = base.type_word_flags(records)
    root_total = struct.unpack_from("<I", root["data"], 0x1C)[0]
    heap_total = struct.unpack_from("<I", heap["data"], 4)[0]
    rig_payload_count = sum(1 for r in records if r["data"] and r["flags"] == 0x3D)
    rows = []
    for row in table:
        key = row["key"]
        rows.append({
            "key": f"0x{key:X}",
            "base": row["base"],
            "count": row["count"],
            "rig_payload_type_word_count": counts[key],
            "count_matches_rig_type_word": counts[key] == row["count"],
            "header_flags_for_matching_payloads": {f"0x{k:X}": v for k, v in sorted(flags[key].items())},
        })
    rig_rows = [x for x in rows if int(x["key"], 16) in base.RIG_KEYS]
    return {
        "heap_record": base.public_record(heap),
        "root_record": base.public_record(root),
        "heap_total": heap_total,
        "root_total": root_total,
        "payload_count": len(payloads),
        "rig_payload_count": rig_payload_count,
        "table_row_count": len(table),
        "table_count_sum": sum(r["count"] for r in table),
        "table_rows": rows,
        "all_table_counts_match_rig_type_words": all(x["count_matches_rig_type_word"] for x in rows),
        "rig_type_rows": rig_rows,
        "all_rig_counts_match": all(x["count_matches_rig_type_word"] for x in rig_rows),
        "totals_self_consistent": heap_total == root_total == rig_payload_count == sum(r["count"] for r in table),
    }


def clone_source_evidence(logical, records: list[dict]) -> dict:
    table = {r["key"]: r for r in logical.read_type_table(logical.payload_records(records)[1]["data"])}
    sources = []
    type_deltas = collections.Counter()
    for name in base.CLONE_SOURCE_NAMES:
        matches = [r for r in records if r["data"] and r["name"] == name]
        for r in matches:
            word = base.payload_type_word(r)
            participates = r["flags"] == 0x3D and word in table
            if participates:
                type_deltas[word] += 1
            item = base.public_record(r)
            item["rig_type_table_member"] = participates
            if participates:
                item["type_table_row"] = {
                    "key": f"0x{word:X}",
                    "base": table[word]["base"],
                    "count": table[word]["count"],
                }
            sources.append(item)
    finals = [r for r in records if r["data"] and r["flags"] == 0x3D and len(r["data"]) == 164]
    mismatches = []
    for r in finals:
        internal = base.payload_internal_name(r)
        if internal != r["name"]:
            mismatches.append({"header_name": r["name"], "payload_name": internal, "payload_index": r["payload_index"]})
    return {
        "sources": sources,
        "required_rig_type_count_delta_if_each_source_payload_is_cloned_once": {
            f"0x{k:X}": v for k, v in sorted(type_deltas.items())
        },
        "stock_final_header_payload_name_mismatches": mismatches,
    }


# Replace the base module's accounting functions. base.main() resolves these
# globals at runtime, so candidate audits and top-level output use the corrected
# Rig-only semantics without duplicating the native scanner.
base.accounting_evidence = accounting_evidence
base.clone_source_evidence = clone_source_evidence
base.rig_type_word_counts = rig_type_word_counts

if __name__ == "__main__":
    base.main()
