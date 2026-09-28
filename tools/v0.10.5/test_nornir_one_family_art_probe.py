#!/usr/bin/env python3
"""Check chest-only WAD isolation and reversible probe install."""
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


builder = load("one_family_builder_test", "build-nornir-one-family-art-probe.py")
installer = load("one_family_installer_test", "install-nornir-one-family-art-probe.py")


class OneFamilyProbeTest(unittest.TestCase):
    def test_failed_live_wad_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nornir-retired-art-") as folder:
            with patch.object(installer.v4, "verify", return_value=None):
                with self.assertRaisesRegex(ValueError, "failed live"):
                    installer.install(Path(folder) / "prior.json", Path(folder), lambda: None)

    def prepare_game(self, game: Path) -> dict[str, str | None]:
        report = installer.candidate()
        before = installer.expected_before(report)
        for name, digest in before.items():
            if digest is None:
                continue
            source = builder.STOCK / name if name in (builder.POOL, builder.MASTER) else builder.SOURCE / name
            destination = game / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            self.assertEqual(installer.base.sha(destination), digest)
        for name, source in (
            (installer.v4.MAP, builder.MAP_V4 / builder.MAP),
            (installer.v4.RUNIC, installer.v4.BUILD / "candidate/game-root" /
             installer.v4.RUNIC),
            ("dxgi.dll", installer.GAME / "dxgi.dll"),
            *[(name, builder.SOURCE / name) for name in installer.UNTouched],
        ):
            destination = game / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for name in self.stock_files():
            if name in (builder.MASTER, builder.POOL, *installer.v4.FILES):
                continue
            destination = game / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(builder.STOCK / name, destination)
        (game / "prior.json").write_text("{}\n", encoding="utf-8")
        return before

    def stock_files(self) -> dict:
        report = json.loads((builder.REPO / "build/nornir-stock-saved-state-test/report.json")
                            .read_text(encoding="utf-8"))
        return {name: {"after": value["sha256"]}
                for name, value in report["files"].items()}

    def test_offline_art_has_one_family_and_exact_inverse(self) -> None:
        outputs, report = builder.build()
        self.assertEqual(set(outputs), installer.FILES)
        self.assertTrue(report["proof"][builder.WAD]["exact_inverse_to_raven"])
        self.assertEqual(report["proof"][builder.MASTER]["chest_resource_changes"], 22)
        self.assertEqual(report["proof"][builder.POOL]["stock_child_rows"], 66)
        for name, raw in outputs.items():
            self.assertEqual(installer.base.sha(installer.BUILD / "candidate/game-root" / name),
                             report["files"][name]["sha256"])

    def test_fake_game_install_and_rollback(self) -> None:
        build = builder.REPO / "build"
        with tempfile.TemporaryDirectory(prefix="nornir-one-art-", dir=build) as folder:
            game = Path(folder).resolve()
            self.assertTrue(game.is_relative_to(build.resolve()))
            before = self.prepare_game(game)
            with patch.object(installer, "FAILED_LIVE_WAD_SHA256", ""), \
                    patch.object(installer.v4, "verify", return_value=None), \
                    patch.object(installer.v4, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v3.json")}), \
                    patch.object(installer.v4.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v2.json")}), \
                    patch.object(installer.v4.prior.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v1.json")}), \
                    patch.object(installer.v4.prior.prior.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "base_operation": str(game / "stock.json")}), \
                    patch.object(installer.base, "read_operation",
                                      return_value={"status": "installed",
                                                    "files": self.stock_files()}):
                journal = installer.install(game / "prior.json", game, lambda: None)
                installer.verify(journal, game, lambda: None)
                installer.rollback(journal, game, lambda: None)
            for name, digest in before.items():
                self.assertEqual(installer.base.sha(game / name), digest)
            self.assertEqual(installer.operation(journal, game)["status"], "rolled_back")

    def test_partial_install_rolls_back(self) -> None:
        build = builder.REPO / "build"
        with tempfile.TemporaryDirectory(prefix="nornir-one-art-fail-", dir=build) as folder:
            game = Path(folder).resolve()
            self.assertTrue(game.is_relative_to(build.resolve()))
            before = self.prepare_game(game)
            atomic = installer.base.atomic_copy
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second-file failure")
                return atomic(*args, **kwargs)

            with patch.object(installer, "FAILED_LIVE_WAD_SHA256", ""), \
                    patch.object(installer.v4, "verify", return_value=None), \
                    patch.object(installer.v4, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v3.json")}), \
                    patch.object(installer.v4.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v2.json")}), \
                    patch.object(installer.v4.prior.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "prior_operation": str(game / "v1.json")}), \
                    patch.object(installer.v4.prior.prior.prior, "read_operation",
                                      return_value={"status": "installed",
                                                    "base_operation": str(game / "stock.json")}), \
                    patch.object(installer.base, "read_operation",
                                      return_value={"status": "installed",
                                                    "files": self.stock_files()}), \
                    patch.object(installer.base, "atomic_copy", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "injected second-file failure"):
                    installer.install(game / "prior.json", game, lambda: None)
            self.assertGreaterEqual(calls, 3)
            for name, digest in before.items():
                self.assertEqual(installer.base.sha(game / name), digest)


if __name__ == "__main__":
    unittest.main()
