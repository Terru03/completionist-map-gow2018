#!/usr/bin/env python3
"""Offline tests for the Raven Twin Stage A2 type-accounting correction."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
A2_PATH = HERE / "build-raven-twin-stage-a2-offline.py"
FAILED_STAGE_A_REPORT = REPO / "archive/field-logs/completionist-v104-raven-twin-stage-a-offline.json"
A2_REPORT = REPO / "archive/field-logs/completionist-v104-raven-twin-stage-a2-offline.json"
A2_OUTPUT = REPO / "build/v0.10.4-raven-twin-stage-a2/offline/candidate/game-root"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


a2 = load("raven_twin_stage_a2", A2_PATH)


class RavenTwinStageA2AccountingTests(unittest.TestCase):
    def test_failed_stage_a_report_contains_the_historical_index_range_bug_signature(self):
        report = json.loads(FAILED_STAGE_A_REPORT.read_text(encoding="utf-8"))
        accounting = report["proofs"]["r_ui_wad"]["accounting"]
        self.assertEqual(accounting["before_total"], 16805)
        self.assertEqual(accounting["after_total"], 16813)
        self.assertEqual(accounting["accounted_delta"], 8)
        self.assertEqual(accounting["type_increments"], {
            "0x20001": 4,
            "0x2000C": 3,
            "0xD": 1,
        })
        self.assertNotEqual(accounting["type_increments"], {
            "0xA": 1,
            "0x10001": 1,
            "0x20001": 1,
            "0x2000C": 1,
            "0x10015": 2,
        })

    def test_expected_serialized_type_deltas_match_first_corrected_raven_class(self):
        self.assertEqual(a2.EXPECTED_PHYSICAL_DELTA, 8)
        self.assertEqual(a2.EXPECTED_TYPED_DELTA, 6)
        self.assertEqual(a2.EXPECTED_UNTYPED_GPU_DELTA, 2)
        self.assertEqual(a2.EXPECTED_TYPED_INCREMENTS, {
            0xA: 1,
            0x10001: 1,
            0x20001: 1,
            0x2000C: 1,
            0x10015: 2,
        })

    def test_a2_report_has_correct_type_accounting_when_built(self):
        if not A2_REPORT.is_file():
            self.skipTest(f"build A2 first: {A2_REPORT}")
        report = json.loads(A2_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["result"], a2.RESULT)
        accounting = report["proofs"]["r_ui_wad"]["accounting"]
        self.assertEqual(accounting["physical_payload_delta"], 8)
        self.assertEqual(accounting["typed_payload_delta"], 6)
        self.assertEqual(accounting["untyped_gpu_payload_delta"], 2)
        self.assertEqual(accounting["accounted_delta"], 6)
        self.assertEqual(accounting["after_total"], accounting["before_total"] + 6)
        self.assertEqual(accounting["type_increments"], {
            "0xA": 1,
            "0x10001": 1,
            "0x20001": 1,
            "0x2000C": 1,
            "0x10015": 2,
        })
        self.assertTrue(accounting["physical_delta_is_not_typed_delta"])
        self.assertEqual(accounting["accounting_basis"],
                         "serialized resource type signatures, never physical payload index ranges")

    def test_a2_keeps_stage_a_scope_and_only_changes_wad_candidate(self):
        if not A2_REPORT.is_file():
            self.skipTest(f"build A2 first: {A2_REPORT}")
        failed = json.loads(FAILED_STAGE_A_REPORT.read_text(encoding="utf-8"))
        fixed = json.loads(A2_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(fixed["stage"], failed["stage"])
        self.assertEqual(fixed["identities"], failed["identities"])
        self.assertEqual(fixed["field_policy"], failed["field_policy"])
        self.assertNotEqual(fixed["files"]["exec/wad/pc_le/r_ui.wad"]["sha256"],
                            failed["files"]["exec/wad/pc_le/r_ui.wad"]["sha256"])
        for path in (
            "exec/dc/pc_le/wad_r_ui.dcb",
            "exec/dc/pc_le/mapmaster.dcb",
            "exec/dc/pc_le/mapcoords.dcb",
        ):
            self.assertEqual(fixed["files"][path]["sha256"], failed["files"][path]["sha256"])
        actual = {p.relative_to(A2_OUTPUT).as_posix() for p in A2_OUTPUT.rglob("*") if p.is_file()}
        self.assertEqual(actual, {
            "exec/wad/pc_le/r_ui.wad",
            "exec/dc/pc_le/wad_r_ui.dcb",
            "exec/dc/pc_le/mapmaster.dcb",
            "exec/dc/pc_le/mapcoords.dcb",
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
