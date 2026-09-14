from __future__ import annotations

import unittest

from object_checkpoint_dispatch import pack_object_token, unpack_object_token


class ObjectTokenTests(unittest.TestCase):
    def test_invalid_object_ref_returns_none(self):
        self.assertIsNone(pack_object_token(0, 0x1234, 0x56789))

    def test_pack_matches_native_bit_layout(self):
        token = pack_object_token(0b1001, 0xBEEF, 0xABCDE)
        self.assertIsNotNone(token)
        self.assertEqual(token & 1, 1)
        self.assertEqual(
            unpack_object_token(token),
            {
                "word_280": 0xBEEF,
                "flags_278_bit3": 1,
                "dword_284_low20": 0xABCDE,
            },
        )

    def test_masks_source_field_widths(self):
        token = pack_object_token(1, 0x1BEEF, 0xFABCDE)
        self.assertEqual(
            unpack_object_token(token),
            {
                "word_280": 0xBEEF,
                "flags_278_bit3": 0,
                "dword_284_low20": 0xABCDE,
            },
        )

    def test_unpack_rejects_non_object_tag(self):
        self.assertIsNone(unpack_object_token(0x1234))


if __name__ == "__main__":
    unittest.main(verbosity=2)
