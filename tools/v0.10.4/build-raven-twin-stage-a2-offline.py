#!/usr/bin/env python3
"""Build Raven Twin Stage A2 with serialized-type accounting fixed.

Stage A's runtime failure exposed a concrete regression: its accounting_update()
classified cloned payloads by *physical payload index ranges*. That is the same
historical mistake already fixed for the first runtime-successful custom Raven
map class. WAD type-table rows are keyed by serialized resource type signatures;
the two GPU texture payloads are physical payloads but are not members of the
five typed cohorts used by this map-resource chain.

This wrapper deliberately changes only that accounting function. All Raven Twin
identities, resource topology, mapmaster/mapcoords construction, artwork and
opaque donor fields remain exactly Stage A. It is OFFLINE ONLY; no game files,
saves, progression or marker state are written.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "build-raven-twin-stage-a-offline.py"
RESULT = "RAVEN_TWIN_STAGE_A2_TYPE_ACCOUNTING_OFFLINE_PROOF_PASSED"

EXPECTED_TYPED_INCREMENTS = {
    0x0000000A: 1,   # material
    0x00010001: 1,   # prototype
    0x00020001: 1,   # final/root instance
    0x0002000C: 1,   # model
    0x00010015: 2,   # diffuse + emissive texture definitions
}
EXPECTED_PHYSICAL_DELTA = 8
EXPECTED_TYPED_DELTA = 6
EXPECTED_UNTYPED_GPU_DELTA = 2


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_base():
    spec = importlib.util.spec_from_file_location("raven_twin_stage_a_base", BASE_PATH)
    check(spec is not None and spec.loader is not None, f"could not load {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serialized_type_key(row: dict) -> int | None:
    """Return the proved WAD type-table key for a cloned map payload.

    These predicates are the same serialized signatures used by the corrected
    first Raven-class builder. GPU texture records (kind 0x1D / flags 0x80A1)
    are resident physical payloads, but they are not counted in these WAD type
    rows and therefore return None.
    """
    data = bytes(row["data"])
    if not data:
        return None
    if row["kind"] == 0x1D and row["flags"] == 0x80A1:
        return None
    check(len(data) >= 4, f"typed payload too small: {row['name']}")
    word = struct.unpack_from("<I", data)[0]
    if row["kind"] == 1 and row["flags"] == 0x14 and word == 0x0000000A:
        return 0x0000000A
    if row["kind"] == 1 and row["flags"] == 0x3D and word == 0x00010001:
        return 0x00010001
    if row["kind"] == 1 and row["flags"] == 0x3D and word == 0x00020001:
        return 0x00020001
    if row["kind"] == 1 and row["flags"] == 0x8E and (word & 0x0FFFFFFF) == 0x0002000C:
        return 0x0002000C
    if row["kind"] == 1 and row["flags"] == 0x8021 and word == 0x00010015:
        return 0x00010015
    raise ValueError(
        f"unclassified data-bearing Raven Twin clone: name={row['name']} "
        f"kind=0x{row['kind']:X} flags=0x{row['flags']:X} word=0x{word:X}"
    )


def corrected_accounting_update(logical, records: list[dict], cloned_rows: list[dict]) -> dict:
    payloads = logical.payload_records(records)
    heap, root = payloads[0], payloads[1]
    source_heap = bytes(heap["data"])
    source_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0], "WAD totals differ")

    type_rows = logical.read_type_table(root["data"])
    by_key = {row["key"]: row for row in type_rows}
    check(len(by_key) == len(type_rows), "duplicate WAD type-table key")
    for key in EXPECTED_TYPED_INCREMENTS:
        check(key in by_key, f"required WAD type-table key missing: 0x{key:X}")

    physical = [row for row in cloned_rows if row["data"]]
    check(len(physical) == EXPECTED_PHYSICAL_DELTA,
          f"Raven Twin physical payload delta changed: {len(physical)}")

    increments: dict[int, int] = {}
    untyped_gpu = []
    classified = []
    for clone in physical:
        key = serialized_type_key(clone)
        if key is None:
            check(clone["kind"] == 0x1D and clone["flags"] == 0x80A1,
                  f"unexpected untyped payload: {clone['name']}")
            untyped_gpu.append(clone["name"])
            continue
        increments[key] = increments.get(key, 0) + 1
        classified.append({
            "name": clone["name"],
            "kind": f"0x{clone['kind']:X}",
            "flags": f"0x{clone['flags']:X}",
            "type_key": f"0x{key:X}",
        })

    check(increments == EXPECTED_TYPED_INCREMENTS,
          f"Raven Twin typed increments changed: {increments}")
    check(len(untyped_gpu) == EXPECTED_UNTYPED_GPU_DELTA,
          f"Raven Twin GPU/untyped payload count changed: {len(untyped_gpu)}")
    check(sum(increments.values()) == EXPECTED_TYPED_DELTA,
          "Raven Twin typed delta is not six")

    new_base = 0
    changed_rows = []
    for row in type_rows:
        old_base = row["base"]
        old_count = row["count"]
        new_count = old_count + increments.get(row["key"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, new_count)
        if new_base != old_base or new_count != old_count:
            changed_rows.append({
                "key": f"0x{row['key']:X}",
                "before_base": old_base,
                "after_base": new_base,
                "before_count": old_count,
                "after_count": new_count,
                "count_delta": new_count - old_count,
            })
        new_base += new_count

    check(new_base == old_total + EXPECTED_TYPED_DELTA,
          f"corrected WAD typed total mismatch: {old_total} -> {new_base}")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    return {
        "before_total": old_total,
        "after_total": new_base,
        "physical_payload_delta": len(physical),
        "typed_payload_delta": EXPECTED_TYPED_DELTA,
        "untyped_gpu_payload_delta": len(untyped_gpu),
        "physical_delta_is_not_typed_delta": True,
        "accounted_delta": EXPECTED_TYPED_DELTA,
        "type_increments": {f"0x{k:X}": v for k, v in EXPECTED_TYPED_INCREMENTS.items()},
        "untyped_gpu_payloads": untyped_gpu,
        "classified_typed_clones": classified,
        "changed_type_rows": changed_rows,
        "source_heap": source_heap,
        "source_root": source_root,
        "accounting_basis": "serialized resource type signatures, never physical payload index ranges",
    }


def main() -> None:
    base = load_base()
    # Preserve the entire Stage A construction and replace only the known-bad
    # accounting primitive. build_wad() resolves this global at call time.
    base.accounting_update = corrected_accounting_update
    base.RESULT = RESULT
    base.main()


if __name__ == "__main__":
    main()
