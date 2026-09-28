"""Check native Nornir art install and rollback on a fake game tree."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nornir_native_installer", HERE / "install-nornir-native-test.py")
installer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(installer)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class NornirNativeInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.build = root / "build"
        self.game = root / "game"
        self.before = {}
        self.after = {}
        for relative in installer.ALLOWED:
            candidate = self.build / "candidate/game-root" / relative
            candidate.parent.mkdir(parents=True, exist_ok=True)
            raw = ("candidate " + relative).encode()
            candidate.write_bytes(raw)
            self.after[relative] = raw
            if relative not in installer.NEW_FILES:
                target = self.game / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                prior = ("Raven baseline " + relative).encode()
                target.write_bytes(prior)
                self.before[relative] = prior
        for relative in (installer.GRAPH,):
            path = self.game / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("untouched " + relative).encode())
        report = {
            "kind": "NORNIR_SEPARATE_NATIVE_MARKERS_TEST",
            "new_marker_count": 88,
            "child_marker_count": 66,
            "files": {relative: {"sha256": digest(raw)} for relative, raw in self.after.items()},
            "source_sha256": {relative: digest(raw) for relative, raw in self.before.items()},
            "proof": {
                "exec/dc/pc_le/mapmaster.dcb": {"exact_inverse": True},
                "exec/dc/pc_le/mapcoords.dcb": {"exact_inverse": True},
                "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": {"raven_lua_exact_prefix": True},
                installer.WAD: {"four_unique_material_keys": True},
                "exec/dc/pc_le/wad_r_ui.dcb": {"new_rows": 96},
            },
            "unchanged_compassgraph_sha256": installer.sha(self.game / installer.GRAPH),
        }
        self.build.mkdir(parents=True, exist_ok=True)
        (self.build / "report.json").write_text(json.dumps(report), encoding="utf-8")
        patcher = patch.multiple(installer, BUILD=self.build, BACKUPS=self.build / "backups",
                                 REPORT=self.build / "report.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_install_verify_and_rollback(self):
        journal = installer.install(self.build, self.game, lambda: None)
        installer.verify(journal, self.game, lambda: None)
        for relative, raw in self.after.items():
            self.assertEqual((self.game / relative).read_bytes(), raw)
        installer.rollback(journal, self.game, lambda: None)
        for relative, raw in self.before.items():
            self.assertEqual((self.game / relative).read_bytes(), raw)
        for relative in installer.NEW_FILES:
            self.assertFalse((self.game / relative).exists())
        installer.rollback(journal, self.game, lambda: None)

    def test_partial_install_rolls_back(self):
        calls = 0

        def stopped():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("game started during install")

        with self.assertRaisesRegex(RuntimeError, "game started"):
            installer.install(self.build, self.game, stopped)
        for relative, raw in self.before.items():
            self.assertEqual((self.game / relative).read_bytes(), raw)
        for relative in installer.NEW_FILES:
            self.assertFalse((self.game / relative).exists())

    def test_source_drift_blocks_all_writes(self):
        drift_relative = "exec/dc/pc_le/mapmaster.dcb"
        (self.game / drift_relative).write_bytes(b"unexpected change")
        with self.assertRaisesRegex(ValueError, "Raven base differs"):
            installer.install(self.build, self.game, lambda: None)
        for relative in installer.NEW_FILES:
            self.assertFalse((self.game / relative).exists())
        self.assertEqual((self.game / drift_relative).read_bytes(), b"unexpected change")


if __name__ == "__main__":
    unittest.main()
