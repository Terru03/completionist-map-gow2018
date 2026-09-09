#!/usr/bin/env python3
"""Test strict Nornir same-name texture removal proof."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
V5_PATH = HERE / "build-nornir-map-hud-offline-v5.py"


def load_v5():
    spec = importlib.util.spec_from_file_location("test_nornir_map_hud_v5", V5_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v5 builder: {V5_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v5 = load_v5()


def row(*, kind: int, flags: int, data: bytes, parent=None) -> dict:
    return {
        "kind": kind,
        "flags": flags,
        "data": bytearray(data),
        "name": v5.base.NORNIR["diffuse"],
        "id": bytes(16),
        "parent": parent,
        "original_offset": None,
        "payload_index": None,
    }


class StrictTextureRemovalTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            row(kind=0x1D, flags=0x80A1, data=b"gpu"),
            row(kind=1, flags=0x8021, data=b"definition"),
            row(kind=2, flags=0, data=b""),
            row(kind=1, flags=0, data=b"", parent=2),
            row(kind=3, flags=0, data=b"", parent=2),
        ]
        self.records[2]["name"] = "MAT_completionistnornirchest"
        self.records[4]["name"] = "MAT_completionistnornirchest"

    def test_removes_standalone_rows_and_classifies_in_group_link(self):
        removed = v5.strict_texture_removal_rows(
            self.records, v5.base.NORNIR["diffuse"], {2, 3, 4})
        self.assertEqual(removed, {0, 1})
        proof = v5._classifications["diffuse"]
        self.assertEqual(proof["additional_record_count"], 1)
        self.assertEqual(proof["additional_records"][0]["classification"],
                         "zero_data_dependency_link")
        self.assertTrue(proof["additional_records"][0]["in_scheduled_nornir_group"])

    def test_rejects_extra_gpu_row(self):
        self.records.append(row(kind=0x1D, flags=0x80A1, data=b"gpu2"))
        with self.assertRaisesRegex(ValueError, "expected one GPU"):
            v5.strict_texture_removal_rows(
                self.records, v5.base.NORNIR["diffuse"], {2, 3, 4})

    def test_rejects_extra_definition_row(self):
        self.records.append(row(kind=1, flags=0x8021, data=b"definition2"))
        with self.assertRaisesRegex(ValueError, "expected one definition"):
            v5.strict_texture_removal_rows(
                self.records, v5.base.NORNIR["diffuse"], {2, 3, 4})

    def test_rejects_same_name_ref_outside_scheduled_groups(self):
        with self.assertRaisesRegex(ValueError,
                                    "unexpected same-name record outside scheduled Nornir groups"):
            v5.strict_texture_removal_rows(
                self.records, v5.base.NORNIR["diffuse"], {2, 4})


if __name__ == "__main__":
    unittest.main()
