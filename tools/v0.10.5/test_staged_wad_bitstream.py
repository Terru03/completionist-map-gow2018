"""Offline frozen-carrier and fail-closed checks. No game needed."""
import copy
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

import staged_wad_bitstream as subject

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = REPO / "archive/field-logs/source-scans/raven-native-carrier-replay-v2-20260916-134106"
TARGET = "raven_642d0d164af0a5d4076e77933c549a5d"


def pack(carriers, alignment=0, endian="big"):
    bits = "1" * alignment
    for carrier in carriers:
        raw = len(carrier).to_bytes(2, endian) + carrier
        bits += "".join(f"{byte:08b}" for byte in raw)
    bits += "0" * (-len(bits) % 8)
    payload = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    return len(payload).to_bytes(2, "little") + payload


class ChannelATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalogue = json.loads((REPO / "catalogue/odins-ravens-save-identities.json").read_text())
        cls.registry = int(catalogue["registry_hash_hex"], 16)
        cls.objects = {int(row["object_hash_hex"], 16): row["catalogue_id"]
                       for row in catalogue["identities"]}
        cls.alive = (FROZEN / "alive-carrier.bin").read_bytes()
        cls.dead = (FROZEN / "dead-carrier.bin").read_bytes()

    def decode(self, envelope):
        return subject.extract_channel_a(envelope, self.registry, self.objects)

    def false_carrier(self):
        raw = bytearray(self.dead)
        module = subject._decoder()
        header = struct.unpack_from("<8H", raw)
        start = 16 + header[7] + 2 * header[0]
        paths = subject._token_paths(module, raw, start, 2 * header[2])
        self.assertEqual(len(paths), 1)
        pos = start
        patched = 0
        for token in paths[0][1]:
            if token["tag"] == 0 and token["payload"] == 1:
                raw[pos + 1] = 0
                patched += 1
            pos += token["width"]
        self.assertGreater(patched, 0)
        return bytes(raw)

    def test_frozen_dead_at_every_bit_alignment(self):
        for alignment in range(8):
            with self.subTest(alignment=alignment):
                result = self.decode(pack([self.dead], alignment))
                self.assertTrue(result["unambiguous"])
                self.assertFalse(result["production_ready"])
                self.assertEqual(result["candidate_count"], 1)
                self.assertIs(result["raven_states"][TARGET], True)
                candidate = result["candidates"][0]
                self.assertEqual(candidate["bit_offset"], 16 + alignment)
                self.assertEqual(candidate["envelope_bit_offset"], 32 + alignment)
                self.assertEqual(candidate["length"], len(self.dead))

    def test_frozen_alive_absence_stays_unknown_at_every_alignment(self):
        for alignment in range(8):
            result = self.decode(pack([self.alive], alignment))
            self.assertEqual(result["candidate_count"], 1)
            self.assertIsNone(result["raven_states"][TARGET])
            self.assertTrue(all(state is None for state in result["raven_states"].values()))

    def test_explicit_false_stays_false(self):
        result = self.decode(pack([self.false_carrier()], 5))
        self.assertIs(result["raven_states"][TARGET], False)

    def test_nested_little_endian_length_rejected(self):
        result = self.decode(pack([self.dead], 3, "little"))
        self.assertEqual(result["candidate_count"], 0)
        self.assertIsNone(result["raven_states"][TARGET])

    def test_outer_big_endian_length_rejected(self):
        packed = pack([self.dead])
        result = self.decode(packed[:2][::-1] + packed[2:])
        self.assertEqual(result["rejected"][0]["reason"], "outer_length_mismatch")

    def test_outer_truncation_and_extra_data_rejected(self):
        for data in (b"", b"\0", pack([self.dead])[:-1], pack([self.dead]) + b"\0"):
            result = self.decode(data)
            self.assertFalse(result["candidates"])
            self.assertTrue(result["rejected"])

    def test_nested_truncation_rejected(self):
        payload = pack([self.dead])[2:-1]
        result = self.decode(len(payload).to_bytes(2, "little") + payload)
        self.assertEqual(result["candidate_count"], 0)
        self.assertIn("nested_buffer_truncated", [r["reason"] for r in result["rejected"]])

    def test_wrong_nested_length_rejected(self):
        packed = bytearray(pack([self.dead]))
        packed[2:4] = (len(self.dead) - 1).to_bytes(2, "big")
        result = self.decode(bytes(packed))
        self.assertEqual(result["candidate_count"], 0)
        self.assertIn("no_exact_carrier_graph", [r["reason"] for r in result["rejected"]])

    def test_conflicting_carriers_clear_all_states(self):
        result = self.decode(pack([self.dead, self.false_carrier()], 7))
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["unambiguous"])
        self.assertIsNone(result["raven_states"][TARGET])
        self.assertIn("conflicting_raven_states", [r["reason"] for r in result["ambiguity_reasons"]])

    def test_equal_repeated_carriers_remain_candidates(self):
        result = self.decode(pack([self.dead, self.dead], 2))
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(result["unambiguous"])
        self.assertFalse(result["production_ready"])

    def test_no_raven_bytes_means_unknown(self):
        result = self.decode(b"\x04\0abcd")
        self.assertEqual(result["candidate_count"], 0)
        self.assertTrue(all(v is None for v in result["raven_states"].values()))

    def test_malformed_graph_rejected(self):
        raw = bytearray(self.dead)
        header = struct.unpack_from("<8H", raw)
        raw[16 + header[7] + 2 * header[0]] = 255
        result = self.decode(pack([bytes(raw)]))
        self.assertEqual(result["candidate_count"], 0)

    def test_multiple_parse_results_fail_closed(self):
        original = subject._decode_paths
        def ambiguous(*args):
            paths = original(*args)
            other = copy.deepcopy(paths[0])
            other["raven_entries"][0]["ravenKilled"] = False
            return paths + [other]
        with patch.object(subject, "_decode_paths", side_effect=ambiguous):
            result = self.decode(pack([self.dead]))
        self.assertFalse(result["unambiguous"])
        self.assertIsNone(result["raven_states"][TARGET])
        self.assertIn("multiple_graph_parses", [r["reason"] for r in result["ambiguity_reasons"]])

    def test_real_tag4_ambiguous_graphs_not_deduplicated(self):
        compressed = zlib.compress(b"x")
        header = struct.pack("<8H", 0, 1, 1, 0, 0, 0, 0, len(compressed))
        carrier = header + compressed + b"\x04" * 7
        result = self.decode(pack([carrier], 4))
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["unambiguous"])
        self.assertIn("multiple_graph_parses", [r["reason"] for r in result["ambiguity_reasons"]])

    def test_cached_lua_length_is_only_cross_check(self):
        result = subject.extract_channel_a(pack([self.dead]), self.registry, self.objects,
                                          expected_lua_length=len(self.dead))
        self.assertEqual(result["candidate_count"], 1)
        self.assertFalse(result["production_ready"])
        result = subject.extract_channel_a(pack([self.dead]), self.registry, self.objects,
                                          expected_lua_length=len(self.dead) + 1)
        self.assertEqual(result["candidate_count"], 0)
        self.assertIn("cached_lua_length_mismatch", [r["reason"] for r in result["rejected"]])

    def test_bounded_parser_keeps_alternatives(self):
        paths = subject._token_paths(subject._decoder(), b"\x04\0\0\0\0", 0, 1)
        self.assertEqual([p[0] for p in paths], [2, 3, 5])

    def test_ambiguous_parse_limit_fails_closed(self):
        with self.assertRaisesRegex(subject.DecodeLimit, "token_parse_path_cap"):
            subject._token_paths(subject._decoder(), b"\x04" * 100, 0, 10)

    def test_stream_scan_cap_fails_closed(self):
        payload = b"\x78" * (subject.MAX_STREAM_MARKERS + 1)
        result = self.decode(len(payload).to_bytes(2, "little") + payload)
        self.assertFalse(result["unambiguous"])
        self.assertIsNone(result["raven_states"][TARGET])
        self.assertEqual(result["ambiguity_reasons"][0]["reason"], "stream_marker_cap")


    def test_native_length_framing_bypasses_unrelated_marker_cap(self):
        garbage = b"\x78" * (subject.MAX_STREAM_MARKERS + 32)
        body = garbage + len(self.dead).to_bytes(2, "big") + self.dead
        envelope = len(body).to_bytes(2, "little") + body
        result = subject.extract_channel_a(
            envelope, self.registry, self.objects, expected_lua_length=len(self.dead)
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["unambiguous"])
        self.assertIs(result["raven_states"][TARGET], True)
        self.assertNotIn("stream_marker_cap", [r["reason"] for r in result["ambiguity_reasons"]])

    def test_unmatched_raven_state_identity_is_preserved(self):
        module = subject._decoder()
        parsed = module.decode_one_carrier(self.dead, self.registry, {})
        self.assertEqual(len(parsed["raven_state_entries_all"]), 1)
        self.assertEqual(len(parsed["unmatched_raven_state_entries"]), 1)
        entry = parsed["unmatched_raven_state_entries"][0]
        self.assertIsNone(entry["catalogue_id"])
        self.assertIs(entry["ravenKilled"], True)
        self.assertTrue(entry["record_payload_hex"].startswith("01"))

    def test_raw_identity_need_not_exist_in_envelope(self):
        packed = pack([self.dead], 3)
        target_hash = next(key for key, value in self.objects.items() if value == TARGET)
        self.assertNotIn(target_hash.to_bytes(8, "little"), packed)
        self.assertIs(self.decode(packed)["raven_states"][TARGET], True)


if __name__ == "__main__":
    unittest.main()
