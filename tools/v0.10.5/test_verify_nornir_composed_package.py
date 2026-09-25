#!/usr/bin/env python3
"""Regression checks for the current Raven + Nornir offline verifier."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_composed_verifier", HERE / "verify-nornir-composed-package.py")
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ART = (v.REPO.parent / "completionist-map-gow2018-all-ravens-release-candidate"
       / "build/nornir-native-stock-read-02/candidate/game-root")


class ComposedVerifierTests(unittest.TestCase):
    def test_legacy_four_family_package_preserves_bytes_but_failed_live_art(self):
        report = v.verify(v.RAVEN_ROOT, v.RAVEN_ROOT, [ART])
        self.assertTrue(report["offline_structural_integrity"])
        self.assertEqual(report["raven_marker_count"], 53)
        self.assertEqual(report["nornir_marker_count"], 88)
        self.assertEqual(report["ui_pool"]["baseline_rows_preserved_byte_exact"], 301)
        self.assertEqual(len(report["perm"]["added_exports"]), 8)
        self.assertTrue(report["known_failed_live_art"])
        self.assertFalse(report["runtime_art_isolation_proven"])
        self.assertFalse(report["install_eligible"])

    def test_raven_wad_payload_tamper_is_rejected(self):
        original = (v.RAVEN_ROOT / v.WAD).read_bytes()
        row = next(r for r in v.logical.parse_wad(original)
                   if r["name"] == "MDL_completionistraven" and r["data"])
        changed = bytearray(original)
        changed[row["original_offset"] + 96] ^= 1
        with self.assertRaisesRegex(ValueError, "WAD record changed"):
            v.verify_wad(original, bytes(changed))

    def test_raven_pool_row_tamper_is_rejected(self):
        original = (v.RAVEN_ROOT / v.UI).read_bytes()
        chunk = v.stage.one_chunk(v.stage.parse_dcb_chunks(original), 12)
        _, rows, _ = v.stage.dcb_rows(original[chunk["start"]:chunk["end"]])
        index = next(r["index"] for r in rows if r["uid"] == v.legacy.RAVEN_MAP_HASH)
        changed = bytearray(original)
        changed[chunk["start"] + 0x90 + index * 16 + 8] ^= 1
        with self.assertRaisesRegex(ValueError, "pool prefix changed"):
            v.verify_pool(original, bytes(changed))

    def test_raven_compass_class_tamper_is_rejected(self):
        original = (v.RAVEN_ROOT / v.PERM).read_bytes()
        chunks = v.legacy.parse_chunks(original)
        data = v.legacy.one(chunks, 12)
        exports = v.legacy.parse_exports(
            original[v.legacy.one(chunks, 13)["start"]:
                     v.legacy.one(chunks, 13)["end"]])
        raven = next(row for row in exports if row["name"] == "CompletionistRaven")
        changed = bytearray(original)
        at = data["start"] + raven["root"]
        struct.pack_into("<Q", changed, at, 0)
        with self.assertRaisesRegex(ValueError, "Raven perm payload changed"):
            v.verify_perm(original, bytes(changed))


if __name__ == "__main__":
    unittest.main()
