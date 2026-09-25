#!/usr/bin/env python3
"""Check exact pack-only input and reversible game-file transaction."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("nornir_pack_test_builder", "build-nornir-pack-only-probe.py")
installer = load("nornir_pack_test_installer", "install-nornir-pack-only-probe.py")


class PackOnlyProbeTest(unittest.TestCase):
    def test_candidate_only_registers_chest_pack(self) -> None:
        outputs, report = builder.build()
        self.assertEqual(set(outputs), set(builder.FILES))
        self.assertEqual(report, installer.candidate())
        self.assertEqual(report["unchanged_wad_sha256"],
                         installer.v4.prior.prior.prior.manifests()[1]
                         ["untouched_sha256"]["exec/wad/pc_le/r_ui.wad"])
        self.assertEqual(set(report["files"]), set(builder.FILES))

    def prepare(self, game: Path) -> None:
        source = (builder.ROOT /
                  "build/nornir-native-material-key-isolated-test/source-game-root" /
                  builder.BOOT)
        destination = game / builder.BOOT
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        self.assertEqual(installer.base.sha(destination), builder.OLD_BOOT_SHA256)

    def test_install_and_rollback_restore_exact_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nornir-pack-only-") as folder:
            game = Path(folder).resolve()
            self.prepare(game)
            with patch.object(installer.v4, "verify", return_value=None), \
                    patch.object(installer, "verify", return_value=None), \
                    patch.dict(installer.RAVEN_PACKS, {}, clear=True):
                journal = installer.install(game / "prior.json", game, lambda: None)
                report = installer.candidate()
                for name in installer.FILES:
                    self.assertEqual(installer.base.sha(game / name),
                                     report["files"][name]["after"])
                installer.rollback(journal, game, lambda: None)
            self.assertEqual(installer.base.sha(game / builder.BOOT),
                             builder.OLD_BOOT_SHA256)
            for name in installer.FILES[1:]:
                self.assertFalse((game / name).exists())
            self.assertEqual(installer.read_operation(journal, game)["status"],
                             "rolled_back")

    def test_partial_install_restores_boot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nornir-pack-only-fail-") as folder:
            game = Path(folder).resolve()
            self.prepare(game)
            atomic = installer.base.atomic_copy
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second-file failure")
                return atomic(*args, **kwargs)

            with patch.object(installer.v4, "verify", return_value=None), \
                    patch.object(installer, "verify", return_value=None), \
                    patch.dict(installer.RAVEN_PACKS, {}, clear=True), \
                    patch.object(installer.base, "atomic_copy", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "injected second-file failure"):
                    installer.install(game / "prior.json", game, lambda: None)
            self.assertGreaterEqual(calls, 3)
            self.assertEqual(installer.base.sha(game / builder.BOOT),
                             builder.OLD_BOOT_SHA256)
            for name in installer.FILES[1:]:
                self.assertFalse((game / name).exists())


if __name__ == "__main__":
    unittest.main()
