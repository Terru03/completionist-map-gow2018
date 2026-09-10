#!/usr/bin/env python3
"""Offline acceptance tests for map-only Raven Twin Stage A."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILDER_PATH = HERE / "build-raven-twin-stage-a-offline.py"
FRAMEWORK_PATH = HERE / "collectible_framework.py"
REPORT_PATH = REPO / "archive/field-logs/completionist-v104-raven-twin-stage-a-offline.json"
OUTPUT_ROOT = REPO / "build/v0.10.4-raven-twin-stage-a/offline/candidate/game-root"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("test_raven_twin_stage_a_builder", BUILDER_PATH)
framework = load("test_raven_twin_stage_a_framework", FRAMEWORK_PATH)


class RavenTwinStageATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raven_root = Path(os.environ.get(
            "COMPLETIONIST_RAVEN_ROOT", r"G:\SteamLibrary\steamapps\common\GodOfWar"))
        if not cls.raven_root.is_dir():
            raise unittest.SkipTest(f"frozen Raven source not found: {cls.raven_root}")
        if not REPORT_PATH.is_file():
            raise unittest.SkipTest(f"Stage A report not built: {REPORT_PATH}")
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_identity_hashes_are_exact_and_distinct(self):
        self.assertEqual(builder.folded_name_hash(builder.TWIN_MARKER_NAME), builder.TWIN_MARKER_UID)
        self.assertEqual(builder.folded_name_hash(builder.TWIN_MAP_GO), builder.TWIN_MAP_HASH)
        self.assertEqual(builder.folded_name_hash(builder.TWIN["map_root"]), builder.TWIN_MAP_HASH)
        self.assertNotEqual(builder.TWIN_MARKER_UID, builder.RAVEN_MARKER_UID)
        self.assertNotEqual(builder.TWIN_MAP_HASH, builder.RAVEN_MAP_HASH)

    def test_current_raven_source_matches_all_four_frozen_hashes(self):
        for relative, expected in builder.FILES.items():
            with self.subTest(relative=relative):
                self.assertEqual(builder.sha_file(self.raven_root / relative), expected)

    def test_candidate_contains_exactly_four_map_files(self):
        actual = {path.relative_to(OUTPUT_ROOT).as_posix()
                  for path in OUTPUT_ROOT.rglob("*") if path.is_file()}
        self.assertEqual(actual, set(builder.FILES))
        forbidden = ("wad_r_perm.dcb", "compassgraph.dcb", "mapmenu.lua", "mainhud.lua",
                     "interact_chest_runic.lua", "interact_chest_standard.lua")
        self.assertFalse(any(path.name in forbidden for path in OUTPUT_ROOT.rglob("*") if path.is_file()))

    def test_report_proves_scope_normalization_and_zero_unexplained_bytes(self):
        report = self.report
        self.assertEqual(report["result"], builder.RESULT)
        self.assertTrue(report["ready_for_runtime_test"])
        self.assertFalse(report["runtime_test_performed"])
        self.assertFalse(report["stage"]["compass_inworld_added"])
        self.assertFalse(report["stage"]["lifecycle_added"])
        self.assertFalse(report["stage"]["nornir_art_added"])
        proof = report["proofs"]
        self.assertTrue(proof["exact_normalization_to_frozen_raven_for_all_four_files"])
        self.assertTrue(proof["original_raven_records_byte_identical"])
        self.assertTrue(proof["stock_dock_boatdock_records_byte_identical"])
        self.assertTrue(proof["all_twin_differences_classified"])
        self.assertEqual(proof["unexplained_changed_payload_bytes"], 0)
        self.assertTrue(report["safety"]["linked_output_destinations_rejected"])
        self.assertTrue(report["safety"]["atomic_candidate_and_report_writes"])
        for key in ("r_ui_wad", "wad_r_ui_dcb", "mapmaster_dcb", "mapcoords_dcb"):
            self.assertTrue(proof[key]["normalized_to_frozen_raven_exact"])
            self.assertEqual(proof[key]["unexplained_changed_payload_bytes"], 0)

    def test_raven_art_and_opaque_payload_policy_are_exact(self):
        wad = self.report["proofs"]["r_ui_wad"]
        for texture in wad["texture_identities"].values():
            self.assertTrue(texture["resident_payload_equal_to_raven"])
        opaque = wad["opaque_donor_fields"]
        self.assertTrue(opaque["material_payload_byte_identical"])
        self.assertEqual(opaque["material_qword_0x10"], "1B0989158D4A2908")
        self.assertEqual(opaque["material_qword_0x20"], "D595197B0961F689")
        self.assertTrue(opaque["map_model_payload_byte_identical"])
        self.assertFalse(opaque["model_group_payloads_mutated"])
        self.assertFalse(opaque["unexplained_scalar_fields_changed"])

    def test_wad_and_gopool_rebuild_deterministically(self):
        source_wad = (self.raven_root / "exec/wad/pc_le/r_ui.wad").read_bytes()
        source_ui = (self.raven_root / "exec/dc/pc_le/wad_r_ui.dcb").read_bytes()
        wad, wad_proof = builder.build_wad(source_wad)
        ui, ui_proof = builder.build_ui_dcb(source_ui)
        self.assertEqual(wad, (OUTPUT_ROOT / "exec/wad/pc_le/r_ui.wad").read_bytes())
        self.assertEqual(ui, (OUTPUT_ROOT / "exec/dc/pc_le/wad_r_ui.dcb").read_bytes())
        self.assertTrue(wad_proof["normalized_to_frozen_raven_exact"])
        self.assertTrue(ui_proof["normalized_to_frozen_raven_exact"])

    def test_native_map_files_rebuild_deterministically(self):
        with tempfile.TemporaryDirectory(prefix="completionist-raven-twin-stage-a-") as temp:
            root = Path(temp)
            master, master_proof = builder.build_mapmaster(
                self.raven_root / "exec/dc/pc_le/mapmaster.dcb", root / "mapmaster.dcb")
            coords, coords_proof = builder.build_mapcoords(
                self.raven_root / "exec/dc/pc_le/mapcoords.dcb", root / "mapcoords.dcb")
        self.assertEqual(master, (OUTPUT_ROOT / "exec/dc/pc_le/mapmaster.dcb").read_bytes())
        self.assertEqual(coords, (OUTPUT_ROOT / "exec/dc/pc_le/mapcoords.dcb").read_bytes())
        self.assertTrue(master_proof["original_raven_marker_physical_bytes_at_original_offset_identical"])
        self.assertTrue(coords_proof["original_raven_coordinate_physical_bytes_at_original_offset_identical"])
        self.assertTrue(master_proof["original_raven_marker_canonical_bytes_identical"])
        self.assertTrue(coords_proof["original_raven_coordinate_canonical_bytes_identical"])

    def test_framework_treats_material_qwords_as_opaque_not_unique(self):
        registry = framework.load_registry()
        proof = framework.validate_registry(registry)
        self.assertNotIn("material_q10_unique", proof)
        self.assertTrue(proof["opaque_material_fields_preserved_from_donor"])
        self.assertIn("material payload +0x10", proof["opaque_donor_policy"])
        raven = framework.definition_for(registry, "odins_raven")
        probe = framework.definition_for(registry, "framework_probe")
        self.assertEqual(probe["resources"]["material"]["qword_0x10"],
                         raven["resources"]["material"]["qword_0x10"])
        self.assertEqual(probe["resources"]["material"]["qword_0x20"],
                         raven["resources"]["material"]["qword_0x20"])

    def test_stage_b_is_design_only_and_art_delta_is_narrow(self):
        stage_b = self.report["stage_b_design_only"]
        self.assertFalse(stage_b["implemented"])
        self.assertTrue(stage_b["topology_and_identity_bytes_must_equal_stage_a"])
        self.assertEqual(len(stage_b["allowed_future_delta_after_stage_a_runtime_success"]), 3)

    def test_offline_writer_rejects_hardlink_without_changing_target(self):
        (REPO / "build").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
                prefix="raven-twin-write-root-", dir=REPO / "build") as root_temp:
            with tempfile.TemporaryDirectory(prefix="raven-twin-victim-") as victim_temp:
                root = Path(root_temp).resolve()
                victim = Path(victim_temp) / "victim.bin"
                target = root / "exec/wad/pc_le/r_ui.wad"
                target.parent.mkdir(parents=True)
                original = b"outside-target-must-not-change"
                victim.write_bytes(original)
                try:
                    os.link(victim, target)
                except (OSError, NotImplementedError) as error:
                    self.skipTest(f"hard links unavailable: {error}")
                with self.assertRaisesRegex(ValueError, "multiple hard links"):
                    builder.write_bytes_atomic(root, target, b"replacement", "test output")
                self.assertEqual(victim.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
