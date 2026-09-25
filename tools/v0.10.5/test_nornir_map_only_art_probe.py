#!/usr/bin/env python3
"""Run the established fake-game transaction checks on the map-only artifact."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("map_only_test_builder", "build-nornir-map-only-art-probe.py")
installer = load("map_only_test_installer", "install-nornir-map-only-art-probe.py")
harness = load("map_only_transaction_harness", "test_nornir_one_family_art_probe.py")
# Reuse its fake-game setup, success/rollback test and injected copy failure.
harness.builder = SimpleNamespace(**vars(builder.base))
harness.builder.build = builder.build
harness.installer = installer.transaction


class MapOnlyProbeTests(harness.OneFamilyProbeTest):
    def test_failed_live_wad_is_blocked(self):
        # The old one-family artifact includes HUD resources and must not be
        # accepted through this narrower install entry point.
        _, old_report = builder.base.build()
        with patch.object(installer, "original_candidate", return_value=old_report):
            with self.assertRaisesRegex(ValueError, "no-HUD proof absent"):
                installer.candidate()

    def test_running_game_blocks_pack_rollback(self):
        with patch.object(installer.transaction.base, "game_stopped",
                          side_effect=ValueError("game running")), \
                patch.object(installer, "load") as load_mock:
            with self.assertRaisesRegex(ValueError, "game running"):
                installer.install(Path("prior.json"), Path("pack.json"))
            load_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
