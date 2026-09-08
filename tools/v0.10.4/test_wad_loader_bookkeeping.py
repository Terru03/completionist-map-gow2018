from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
TARGET = HERE / "inspect-wad-loader-bookkeeping.py"
spec = importlib.util.spec_from_file_location("wad_bookkeeping", TARGET)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load bookkeeping probe")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def record(name="gomapiconx", flags=0x3D, data=b"", kind=1, index=1):
    return {
        "name": name,
        "flags": flags,
        "data": bytearray(data),
        "kind": kind,
        "payload_index": index,
        "original_offset": 0x100,
        "id": bytes(16),
    }


class WadLoaderBookkeepingTests(unittest.TestCase):
    def test_payload_type_word(self):
        r = record(data=struct.pack("<I", 0x20001) + bytes(160))
        self.assertEqual(mod.payload_type_word(r), 0x20001)

    def test_short_payload_has_no_type_word(self):
        self.assertIsNone(mod.payload_type_word(record(data=b"\x01\x02\x03")))

    def test_final_payload_name(self):
        data = bytearray(164)
        struct.pack_into("<I", data, 0, 0x20001)
        data[0x1C:0x1C + len(b"gomapiconraven\0")] = b"gomapiconraven\0"
        self.assertEqual(mod.payload_internal_name(record(name="gomapiconraven", data=data)), "gomapiconraven")

    def test_final_payload_name_requires_terminator(self):
        data = bytearray(164)
        data[0x1C:0x54] = b"A" * (0x54 - 0x1C)
        with self.assertRaises(ValueError):
            mod.payload_internal_name(record(data=data))

    def test_type_word_counts(self):
        rows = [
            record(data=struct.pack("<I", 0x10001) + bytes(4), index=1),
            record(data=struct.pack("<I", 0x10001) + bytes(4), index=2),
            record(data=struct.pack("<I", 0x20001) + bytes(4), index=3),
        ]
        counts = mod.type_word_counts(rows)
        self.assertEqual(counts[0x10001], 2)
        self.assertEqual(counts[0x20001], 1)

    def test_type_table_candidate_scoring(self):
        score, reasons = mod.score_type_table_candidate({0x1C, 0x20, 0x28}, {0xC, 0x20001}, {0x423100})
        self.assertGreaterEqual(score, 20)
        self.assertTrue(any("root offsets" in x for x in reasons))
        self.assertTrue(any("resource resolver" in x for x in reasons))

    def test_name_map_candidate_scoring(self):
        score, reasons = mod.score_name_map_candidate({0x78}, {0x401, 6}, {0x423100}, {0x78})
        self.assertGreaterEqual(score, 20)
        self.assertTrue(any("writes through +0x78" in x for x in reasons))

    def test_uninteresting_function_scores_zero(self):
        self.assertEqual(mod.score_type_table_candidate(set(), set(), set())[0], 0)
        self.assertEqual(mod.score_name_map_candidate(set(), set(), set(), set())[0], 0)


if __name__ == "__main__":
    unittest.main()
