"""Exercise exact chest identities against archived opened and closed carriers."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import nornir_checkpoint_keys as keys
import nornir_staged_chest_state as staged


FIXTURES = Path(__file__).with_name("fixtures") / "nornir-staged"
OPENED = ("opened-alfheim.bin", 3414,
          "nornir_chest_522448bf4d91b0f19de6adbd1c77d709",
          "e0a65ad932ac2a86c29d865700582eb23c814622c03546e15e83a6b230473768")
UNOPENED = ("unopened-veithurgard.bin", 9841,
            "nornir_chest_c190d59340706bb79925cb9f2d5867cf",
            "fcc1bcbd87c17d164a475d69d2a657799e9be9c4bdc51b0c49e44a7342f4b420")


class CheckpointStateTest(unittest.TestCase):
    def test_all_physical_chests_have_distinct_exact_keys(self):
        rows = keys.build()
        self.assertEqual(len(rows), 22)
        self.assertEqual(len({row["serialized_key"] for row in rows}), 22)
        for catalogue_id, (registry, obj) in keys.OBSERVED.items():
            row = next(row for row in rows if row["catalogue_id"] == catalogue_id)
            self.assertEqual((row["registry_hash"], row["object_hash"]),
                             (f"{registry:016X}", f"{obj:016X}"))

    @unittest.skipUnless(all((FIXTURES / name).is_file()
                             for name in (OPENED[0], UNOPENED[0])),
                         "local captured game checkpoints unavailable")
    def test_real_opened_and_unopened_carriers(self):
        rows = {row["catalogue_id"]: row for row in keys.build()}
        for fixture, lua_length, catalogue_id, expected_sha in (OPENED, UNOPENED):
            with self.subTest(fixture=fixture):
                raw = (FIXTURES / fixture).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha)
                got = staged.inspect_payload(raw, lua_length, [rows[catalogue_id]])
                self.assertEqual(got["errors"], [])
                self.assertEqual(got["states"][catalogue_id],
                                 4 if fixture == OPENED[0] else 2)
                wrong_length = staged.inspect_payload(
                    raw, lua_length + 1, [rows[catalogue_id]])
                self.assertTrue(wrong_length["errors"])
                self.assertIsNone(wrong_length["states"][catalogue_id])


if __name__ == "__main__":
    unittest.main()
