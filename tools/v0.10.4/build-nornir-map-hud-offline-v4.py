#!/usr/bin/env python3
"""Type-accounting-safe Nornir map/HUD offline builder wrapper.

The frozen Raven production WAD contains two different accounting grammars:

* the map-side Raven resources still sit inside the ordinary payload-index
  ranges described by the WAD_R_UI type table;
* the runtime-proven Raven compass HUD clone was appended later. Its prototype,
  local SCP and root are accounted by their payload type keys (0x10001,
  0x10005, 0x20001), while its model payload (0x1002000C) is deliberately not
  represented by the WAD_R_UI accounting table.

The original Nornir builder assumed every donor payload index had to fall inside
one type-table range. That is false for the proven Raven HUD donor and caused the
safe offline failure at source payload index 18489.

This wrapper preserves all v3 fixes (collision-safe GPU identities and <=55-byte
WAD texture aliases), but replaces only the accounting classifier. It accepts
exactly the already-proven Raven HUD grammar: three type-key-accounted HUD
payloads plus one unaccounted HUD model. Any other out-of-range payload fails
closed. No God of War file is modified.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
V3_PATH = HERE / "build-nornir-map-hud-offline-v3.py"


def load_v3():
    spec = importlib.util.spec_from_file_location("completionist_nornir_map_hud_v3", V3_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v3 builder: {V3_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v3 = load_v3()
base = v3.base

EXPECTED_FALLBACK_KEYS = {0x10001: 1, 0x10005: 1, 0x20001: 1}
EXPECTED_UNACCOUNTED_FIRST_DWORD = 0x1002000C
EXPECTED_SOURCE_ACCOUNTED_TOTAL = 16805


def apply_accounting_raven_grammar(logical, records: list[dict], cloned_rows: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    base.check(len(payloads) >= 2, "WAD accounting payloads missing")
    heap, root = payloads[0], payloads[1]
    before_heap = bytes(heap["data"])
    before_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    base.check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0],
               "WAD totals disagree")
    base.check(old_total == EXPECTED_SOURCE_ACCOUNTED_TOTAL,
               f"frozen Raven accounted total changed: {old_total}")

    rows = logical.read_type_table(root["data"])
    by_key = {row["key"]: row for row in rows}
    base.check(len(by_key) == len(rows), "WAD type table contains duplicate keys")

    increments: dict[int, int] = {}
    cloned_payloads = [row for row in cloned_rows if row["data"]]
    direct_count = 0
    fallback_counts: dict[int, int] = {}
    unaccounted: list[dict] = []

    for clone in cloned_payloads:
        source_index = clone.get("_source_payload_index")
        base.check(isinstance(source_index, int),
                   f"clone {clone['name']} lost source payload index")

        index_matches = [
            row for row in rows
            if row["base"] <= source_index < row["base"] + row["count"]
        ]
        base.check(len(index_matches) <= 1,
                   f"clone source payload {source_index} maps to multiple type rows")

        target = None
        if len(index_matches) == 1:
            target = index_matches[0]
            direct_count += 1
        else:
            first_dword = (struct.unpack_from("<I", clone["data"], 0)[0]
                           if len(clone["data"]) >= 4 else None)
            if first_dword in by_key:
                target = by_key[first_dword]
                fallback_counts[first_dword] = fallback_counts.get(first_dword, 0) + 1
            else:
                unaccounted.append({
                    "name": clone["name"],
                    "source_payload_index": source_index,
                    "first_dword": first_dword,
                })
                continue

        increments[target["index"]] = increments.get(target["index"], 0) + 1

    # This is the exact runtime-proven Raven HUD accounting grammar. The
    # prototype, its local SCP, and root participate in the type table by key.
    # The HUD model payload is physical WAD data but intentionally unaccounted.
    base.check(fallback_counts == EXPECTED_FALLBACK_KEYS,
               f"Raven HUD fallback accounting changed: {fallback_counts!r}")
    base.check(len(unaccounted) == 1,
               f"expected exactly one unaccounted Raven HUD model clone, found {len(unaccounted)}")
    only = unaccounted[0]
    base.check(only["name"].lower() == base.NORNIR["hud_model"].lower(),
               f"unexpected unaccounted payload: {only!r}")
    base.check(only["first_dword"] == EXPECTED_UNACCOUNTED_FIRST_DWORD,
               f"Nornir HUD model payload type changed: {only!r}")

    accounted_delta = sum(increments.values())
    base.check(accounted_delta == len(cloned_payloads) - 1,
               "accounted payload delta does not equal all cloned payloads minus the proven HUD model")

    new_base = 0
    for row in rows:
        new_count = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, new_count)
        new_base += new_count
    base.check(new_base == old_total + accounted_delta,
               "WAD accounting total disagrees with classified Nornir payloads")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    return {
        "before_total": old_total,
        "after_total": new_base,
        "payload_delta": len(cloned_payloads),
        "accounted_delta": accounted_delta,
        "direct_index_accounted_payloads": direct_count,
        "fallback_type_key_accounted_payloads": sum(fallback_counts.values()),
        "fallback_type_key_counts": {f"0x{key:X}": value for key, value in sorted(fallback_counts.items())},
        "unaccounted_payload_count": len(unaccounted),
        "unaccounted_payload_names": [row["name"] for row in unaccounted],
        "hud_accounting_grammar_verified": True,
        "type_increments": {
            f"0x{rows[index]['key']:X}": amount
            for index, amount in sorted(increments.items())
        },
        "source_heap_data": before_heap,
        "source_root_data": before_root,
    }


base.apply_accounting = apply_accounting_raven_grammar


if __name__ == "__main__":
    base.main()
