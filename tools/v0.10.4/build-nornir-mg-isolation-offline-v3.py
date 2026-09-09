#!/usr/bin/env python3
"""Frozen-Raven-accounting-safe Nornir MG isolation builder.

The frozen Raven WAD proves two MG accounting paths. MG_mapicondock_0 still
sits in ordinary type row 0x2000C. MG_boatdock_0 sits past all ordinary rows,
but its 0x1000C first dword belongs to the exact 990-record 0x1000C cohort.
Both are accounted. Neither is a physical-but-unaccounted model payload.

This wrapper keeps v2 standalone-record handling. It replaces only the MG
accounting classifier. It accepts one exact direct clone and one exact type-key
fallback clone. All other shapes fail closed. No God of War file is modified.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
V2_PATH = HERE / "build-nornir-mg-isolation-offline-v2.py"


def load_v2():
    spec = importlib.util.spec_from_file_location("completionist_nornir_mg_isolation_v2", V2_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v2 builder: {V2_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2 = load_v2()
base = v2.base
_v2_build = base.build

EXPECTED_FAILED_ACCOUNTED_TOTAL = 16816
EXPECTED_FIRST_DWORD = 0x1000C
EXPECTED_TYPE_POPULATION = 990
EXPECTED_GRAMMAR = {
    "map": {
        "clone_name": base.NORNIR_MG["map"],
        "source_name": base.STOCK_MG["map"],
        "source_payload_index": 13917,
        "source_payload_bytes": 1108,
        "mode": "ordinary_payload_index",
        "type_key": 0x2000C,
    },
    "hud": {
        "clone_name": base.NORNIR_MG["hud"],
        "source_name": base.STOCK_MG["hud"],
        "source_payload_index": 18495,
        "source_payload_bytes": 388,
        "mode": "first_dword_type_key",
        "type_key": 0x1000C,
    },
}
EXPECTED_DONORS = {
    "raven": {
        "map": {"record_index": 32419, "payload_index": 13912, "type_base": 12928, "type_count": 991},
        "hud": {"record_index": 49144, "payload_index": 18487, "type_base": 11938, "type_count": 990},
    },
    "failed_candidate": {
        "map": {"record_index": 32432, "payload_index": 13917, "type_base": 12935, "type_count": 994},
        "hud": {"record_index": 49178, "payload_index": 18495, "type_base": 11945, "type_count": 990},
    },
}
EXPECTED_IDS = {
    "map": "44b11676af9c4e0ff860108fd46b0b32",
    "hud": "c3f6b4c5a8270df607ea3e6e7f891292",
}


def first_dword(row: dict) -> int | None:
    return struct.unpack_from("<I", row["data"], 0)[0] if len(row["data"]) >= 4 else None


def classify_mg_clone(rows: list[dict], clone: dict) -> tuple[dict, dict]:
    """Classify one clone with exact frozen MG grammar."""
    names = {value["clone_name"].lower(): kind for kind, value in EXPECTED_GRAMMAR.items()}
    kind = names.get(clone["name"].lower())
    base.check(kind is not None, f"unexpected MG clone for accounting: {clone['name']}")
    expected = EXPECTED_GRAMMAR[kind]

    source_index = clone.get("_source_payload_index")
    base.check(source_index == expected["source_payload_index"],
               f"{kind}: MG donor payload index changed: {source_index}")
    base.check(clone["kind"] == 1 and clone["flags"] == 0x98,
               f"{kind}: MG record kind/flags changed")
    base.check(len(clone["data"]) == expected["source_payload_bytes"],
               f"{kind}: MG payload byte length changed")
    word = first_dword(clone)
    base.check(word == EXPECTED_FIRST_DWORD,
               f"{kind}: MG first dword changed: {word!r}")

    by_key = {row["key"]: row for row in rows}
    base.check(len(by_key) == len(rows), "WAD type table contains duplicate keys")
    base.check(word in by_key, f"{kind}: MG first dword has no WAD type row")
    direct = [row for row in rows
              if row["base"] <= source_index < row["base"] + row["count"]]
    base.check(len(direct) <= 1,
               f"{kind}: MG donor payload maps to multiple ordinary type rows")

    if expected["mode"] == "ordinary_payload_index":
        base.check(len(direct) == 1,
                   f"{kind}: MG donor left its ordinary type row")
        target = direct[0]
    else:
        base.check(not direct,
                   f"{kind}: MG donor unexpectedly entered an ordinary type row")
        target = by_key[word]

    base.check(target["key"] == expected["type_key"],
               f"{kind}: MG accounting type changed: {target['key']:#x}")
    return target, {
        "kind": kind,
        "clone_name": clone["name"],
        "source_name": expected["source_name"],
        "source_payload_index": source_index,
        "record_kind": clone["kind"],
        "record_flags": f"0x{clone['flags']:X}",
        "payload_byte_length": len(clone["data"]),
        "first_dword": f"0x{word:X}",
        "payload_index_in_ordinary_type_range": bool(direct),
        "ordinary_type_key": f"0x{direct[0]['key']:X}" if direct else None,
        "first_dword_matches_existing_type_key": True,
        "accounting_mode": expected["mode"],
        "accounting_type_key": f"0x{target['key']:X}",
        "intentionally_physically_present_but_unaccounted": False,
    }


def apply_mg_accounting(logical, records: list[dict], clone_groups: list[list[dict]]) -> dict:
    payloads = logical.payload_records(records)
    base.check(len(payloads) >= 2, "WAD accounting payloads missing")
    heap, root = payloads[0], payloads[1]
    before_heap = bytes(heap["data"])
    before_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    base.check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0],
               "WAD accounting totals disagree")
    base.check(old_total == EXPECTED_FAILED_ACCOUNTED_TOTAL,
               f"failed Nornir accounted total changed: {old_total}")

    rows = logical.read_type_table(root["data"])
    clones = [row for group in clone_groups for row in group if row["data"]]
    base.check(len(clones) == 2, f"expected two MG clone payloads, found {len(clones)}")

    increments: dict[int, int] = {}
    details: list[dict] = []
    for clone in clones:
        target, detail = classify_mg_clone(rows, clone)
        increments[target["index"]] = increments.get(target["index"], 0) + 1
        details.append(detail)

    modes = {row["kind"]: row["accounting_mode"] for row in details}
    base.check(modes == {"map": "ordinary_payload_index", "hud": "first_dword_type_key"},
               f"MG accounting grammar changed: {modes!r}")
    base.check(sum(increments.values()) == len(clones),
               "not every MG clone was accounted")

    new_base = 0
    for row in rows:
        amount = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, amount)
        new_base += amount
    base.check(new_base == old_total + 2, "MG clone accounting total changed unexpectedly")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    return {
        "before_total": old_total,
        "after_total": new_base,
        "payload_delta": len(clones),
        "accounted_delta": sum(increments.values()),
        "direct_index_accounted_payloads": sum(row["accounting_mode"] == "ordinary_payload_index" for row in details),
        "fallback_type_key_accounted_payloads": sum(row["accounting_mode"] == "first_dword_type_key" for row in details),
        "unaccounted_payload_count": 0,
        "classified_payloads": details,
        "type_increments": {
            f"0x{rows[index]['key']:X}": amount
            for index, amount in sorted(increments.items())
        },
        "mg_accounting_grammar_verified": True,
        "source_heap_data": before_heap,
        "source_root_data": before_root,
    }


def donor_accounting_facts(logical, records: list[dict], context: str) -> dict:
    """Prove donor facts in frozen Raven or exact failed candidate."""
    base.check(context in EXPECTED_DONORS, f"unknown donor context: {context}")
    payloads = logical.payload_records(records)
    rows = logical.read_type_table(payloads[1]["data"])
    by_key = {row["key"]: row for row in rows}
    base.check(len(by_key) == len(rows), "WAD type table contains duplicate keys")

    cohort = [row for row in payloads if first_dword(row) == EXPECTED_FIRST_DWORD]
    type_row = by_key.get(EXPECTED_FIRST_DWORD)
    base.check(type_row is not None, "MG first-dword type row missing")
    base.check(type_row["count"] == EXPECTED_TYPE_POPULATION == len(cohort),
               "MG 0x1000C type row no longer equals its physical cohort")
    base.check(all(row["kind"] == 1 and row["flags"] == 0x98 and row["parent"] is None
                   for row in cohort),
               "MG 0x1000C cohort shape changed")

    facts = {}
    for kind, grammar in EXPECTED_GRAMMAR.items():
        record_index, donor = base.unique_payload(records, grammar["source_name"])
        expected = EXPECTED_DONORS[context][kind]
        base.check(record_index == expected["record_index"],
                   f"{context} {kind}: donor record index changed")
        base.check(donor["payload_index"] == expected["payload_index"],
                   f"{context} {kind}: donor payload index changed")
        base.check(donor["id"].hex() == EXPECTED_IDS[kind],
                   f"{context} {kind}: donor ID changed")
        base.check(donor["kind"] == 1 and donor["flags"] == 0x98,
                   f"{context} {kind}: donor kind/flags changed")
        base.check(len(donor["data"]) == grammar["source_payload_bytes"],
                   f"{context} {kind}: donor payload byte length changed")
        base.check(first_dword(donor) == EXPECTED_FIRST_DWORD,
                   f"{context} {kind}: donor first dword changed")

        direct = [row for row in rows
                  if row["base"] <= donor["payload_index"] < row["base"] + row["count"]]
        base.check(len(direct) == (1 if kind == "map" else 0),
                   f"{context} {kind}: ordinary range membership changed")
        accounted = direct[0] if direct else type_row
        base.check(accounted["key"] == grammar["type_key"],
                   f"{context} {kind}: accounted type key changed")
        base.check(accounted["base"] == expected["type_base"] and accounted["count"] == expected["type_count"],
                   f"{context} {kind}: accounted type row bounds changed")

        ordinal = cohort.index(donor)
        facts[kind] = {
            "name": donor["name"],
            "record_index": record_index,
            "payload_index": donor["payload_index"],
            "record_id": donor["id"].hex(),
            "kind": donor["kind"],
            "flags": f"0x{donor['flags']:X}",
            "payload_byte_length": len(donor["data"]),
            "first_dword": f"0x{first_dword(donor):X}",
            "payload_index_in_ordinary_type_range": bool(direct),
            "ordinary_type_row": ({
                "index": direct[0]["index"],
                "key": f"0x{direct[0]['key']:X}",
                "base": direct[0]["base"],
                "count": direct[0]["count"],
            } if direct else None),
            "first_dword_matches_existing_type_key": True,
            "first_dword_type_row": {
                "index": type_row["index"],
                "key": f"0x{type_row['key']:X}",
                "base": type_row["base"],
                "count": type_row["count"],
            },
            "first_dword_physical_population": len(cohort),
            "first_dword_population_equals_type_count": True,
            "type_ordinal_zero_based": ordinal,
            "modeled_type_index": type_row["base"] + ordinal,
            "accounting_mode": grammar["mode"],
            "accounting_type_key": f"0x{accounted['key']:X}",
            "intentionally_physically_present_but_unaccounted": False,
        }
    return facts


def comparable_raven_facts(logical, records: list[dict]) -> dict:
    """Show why MG fallback differs from Raven HUD model handling."""
    payloads = logical.payload_records(records)
    rows = logical.read_type_table(payloads[1]["data"])
    by_key = {row["key"]: row for row in rows}
    expected = [
        (32429, "MDL_completionistraven", "ordinary_payload_index"),
        (32438, "goProtoMapIconCompletionistRaven", "ordinary_payload_index"),
        (32459, "gomapiconcompletionistraven", "ordinary_payload_index"),
        (49151, "MDL_completionistravenhud", "physically_present_unaccounted"),
        (49161, "goProtoCompletionistRavenHUD", "first_dword_type_key"),
        (49163, "SCP_BoatDock", "first_dword_type_key"),
        (49169, "gocompletionistravenhud", "first_dword_type_key"),
    ]
    facts = []
    for record_index, name, mode in expected:
        row = records[record_index]
        base.check(row["name"].lower() == name.lower() and row["data"],
                   f"Raven comparison record changed at {record_index}")
        word = first_dword(row)
        direct = [item for item in rows
                  if item["base"] <= row["payload_index"] < item["base"] + item["count"]]
        actual = ("ordinary_payload_index" if direct else
                  "first_dword_type_key" if word in by_key else
                  "physically_present_unaccounted")
        base.check(actual == mode, f"Raven comparison grammar changed for {name}: {actual}")
        facts.append({
            "name": name,
            "record_index": record_index,
            "payload_index": row["payload_index"],
            "first_dword": f"0x{word:X}",
            "accounting_mode": actual,
            "accounting_type_key": (f"0x{direct[0]['key']:X}" if direct else
                                    f"0x{word:X}" if word in by_key else None),
        })
    return {
        "resources": facts,
        "map_resources_use_ordinary_payload_index_accounting": True,
        "hud_prototype_scp_root_use_first_dword_type_key_accounting": True,
        "hud_model_is_physically_present_but_unaccounted": True,
        "mg_hud_matches_accounted_type_key_grammar_not_unaccounted_model_grammar": True,
    }


base.apply_direct_accounting = apply_mg_accounting


def build_accounting_safe(failed_raw: bytes, raven_raw: bytes):
    logical = base.load_logical()
    failed_records = logical.parse_wad(failed_raw)
    raven_records = logical.parse_wad(raven_raw)
    donor_facts = {
        "frozen_raven": donor_accounting_facts(logical, raven_records, "raven"),
        "failed_candidate": donor_accounting_facts(logical, failed_records, "failed_candidate"),
    }
    comparisons = comparable_raven_facts(logical, raven_records)

    candidate, report = _v2_build(failed_raw, raven_raw)
    report["mg_donor_accounting_facts"] = donor_facts
    report["comparable_raven_accounting"] = comparisons
    report["proofs"]["mg_donor_accounting_grammar_proven_from_frozen_raven_wad"] = True
    report["proofs"]["both_mg_clone_payloads_strictly_accounted"] = True
    report["proofs"]["no_mg_clone_payload_intentionally_unaccounted"] = True
    return candidate, report


base.build = build_accounting_safe


if __name__ == "__main__":
    base.main()
