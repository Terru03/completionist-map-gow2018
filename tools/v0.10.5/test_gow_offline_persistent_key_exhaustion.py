"""Offline tests for exact Raven exhaustion tracer."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("trace-gow-offline-persistent-key-exhaustion.py")


def load_module():
    spec = importlib.util.spec_from_file_location("offline_persistent_key_exhaustion", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineExhaustionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.exe = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe")
        cls.wad = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\exec\wad\pc_le\alf355_chiseldungeon.wad")

    def test_anchor_set_covers_each_claimed_route(self):
        names = self.module.ANCHORS
        self.assertTrue(any(name.startswith("constructor_") for name in names))
        self.assertTrue(any(name.startswith("worker_") for name in names))
        self.assertTrue(any(name.startswith("metadata_") for name in names))
        self.assertTrue(any(name.startswith("slot_release_") for name in names))

    def test_supported_binary_and_wad_when_present(self):
        if not self.exe.is_file() or not self.wad.is_file():
            self.skipTest("supported local game files absent")
        self.assertGreaterEqual(self.module.verify_anchors(self.exe)["anchors_verified"], 30)
        report = self.module.verify_wad(self.wad)
        self.assertEqual(report["canonical"]["index"], 9633)
        self.assertFalse(report["exact_record_to_scheduler_item_proved"])
        self.assertEqual([row["index"] for row in report["prototype_payload_hits"]], [8545, 8548, 9633])

    def test_wrong_binary_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GoW.exe"
            path.write_bytes(b"wrong")
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                self.module.verify_anchors(path)

    def test_index_edges_when_present(self):
        index = Path(".research-index/gow-caebcb027980.sqlite")
        if not index.is_file():
            self.skipTest("research index absent")
        self.assertEqual(self.module.verify_edges(index)["edges_verified"], len(self.module.EXPECTED_EDGES))


if __name__ == "__main__":
    unittest.main()
