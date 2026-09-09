#!/usr/bin/env python3
"""Focused tests for frozen Raven MG accounting grammar."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
V3_PATH = HERE / "build-nornir-mg-isolation-offline-v3.py"


def load_v3():
    spec = importlib.util.spec_from_file_location("test_nornir_mg_v3", V3_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v3 builder: {V3_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v3 = load_v3()


def clone(kind: str) -> dict:
    expected = v3.EXPECTED_GRAMMAR[kind]
    data = bytearray(expected["source_payload_bytes"])
    struct.pack_into("<I", data, 0, v3.EXPECTED_FIRST_DWORD)
    return {
        "name": expected["clone_name"],
        "kind": 1,
        "flags": 0x98,
        "data": data,
        "_source_payload_index": expected["source_payload_index"],
    }


class FakeLogical:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def payload_records(self, records: list[dict]) -> list[dict]:
        return records

    def read_type_table(self, _root_data: bytearray) -> list[dict]:
        return self.rows


class MgAccountingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"index": 0, "offset": 0x28, "key": 0x1000C, "base": 0, "count": 990},
            {"index": 1, "offset": 0x34, "key": 0x2000C, "base": 990, "count": 15826},
        ]

    def test_map_mg_uses_ordinary_range_before_first_dword_key(self):
        target, detail = v3.classify_mg_clone(self.rows, clone("map"))
        self.assertEqual(target["key"], 0x2000C)
        self.assertEqual(detail["accounting_mode"], "ordinary_payload_index")
        self.assertEqual(detail["first_dword"], "0x1000C")
        self.assertTrue(detail["first_dword_matches_existing_type_key"])
        self.assertFalse(detail["intentionally_physically_present_but_unaccounted"])

    def test_hud_mg_uses_first_dword_key_when_outside_all_ranges(self):
        target, detail = v3.classify_mg_clone(self.rows, clone("hud"))
        self.assertEqual(target["key"], 0x1000C)
        self.assertEqual(detail["accounting_mode"], "first_dword_type_key")
        self.assertFalse(detail["payload_index_in_ordinary_type_range"])
        self.assertFalse(detail["intentionally_physically_present_but_unaccounted"])

    def test_unknown_out_of_range_payload_fails_closed(self):
        row = clone("hud")
        struct.pack_into("<I", row["data"], 0, 0xDEADBEEF)
        with self.assertRaisesRegex(ValueError, "MG first dword changed"):
            v3.classify_mg_clone(self.rows, row)

    def test_unexpected_clone_identity_fails_closed(self):
        row = clone("hud")
        row["name"] = "MG_some_other_clone"
        with self.assertRaisesRegex(ValueError, "unexpected MG clone"):
            v3.classify_mg_clone(self.rows, row)

    def test_duplicate_type_keys_fail_closed(self):
        rows = self.rows + [
            {"index": 2, "offset": 0x40, "key": 0x1000C, "base": 16816, "count": 1},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate keys"):
            v3.classify_mg_clone(rows, clone("map"))

    def test_apply_accounts_both_clones_and_no_unaccounted_payload(self):
        heap = {"data": bytearray(8)}
        root = {"data": bytearray(0x40)}
        struct.pack_into("<I", heap["data"], 4, v3.EXPECTED_FAILED_ACCOUNTED_TOTAL)
        struct.pack_into("<I", root["data"], 0x1C, v3.EXPECTED_FAILED_ACCOUNTED_TOTAL)
        report = v3.apply_mg_accounting(
            FakeLogical(self.rows), [heap, root], [[clone("map")], [clone("hud")]])
        self.assertEqual(report["before_total"], 16816)
        self.assertEqual(report["after_total"], 16818)
        self.assertEqual(report["payload_delta"], 2)
        self.assertEqual(report["accounted_delta"], 2)
        self.assertEqual(report["direct_index_accounted_payloads"], 1)
        self.assertEqual(report["fallback_type_key_accounted_payloads"], 1)
        self.assertEqual(report["unaccounted_payload_count"], 0)
        self.assertEqual(report["type_increments"], {"0x1000C": 1, "0x2000C": 1})
        self.assertTrue(report["mg_accounting_grammar_verified"])


if __name__ == "__main__":
    unittest.main()
