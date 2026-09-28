"""Check independent material identity and guarded reversible installation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("nornir_material_builder_test",
               "build-nornir-native-material-key-isolated-test.py")
wrapper = load("nornir_material_installer_test",
               "install-nornir-native-material-key-isolated-test.py")
old_tests = load("nornir_material_installer_base_tests",
                 "test_nornir_native_installer.py")


class MaterialBuildTest(unittest.TestCase):
    def test_rebuild_preserves_raven_and_eliminates_adjacent_keys(self):
        source = builder.REPORT.parent / "source-game-root"
        self.assertTrue(source.is_dir())
        outputs, report = builder.build(source)
        wad = builder.base.base.base.WAD
        proof = report["proof"][wad]["material_key_isolation"]
        self.assertEqual(hashlib.sha256(outputs[wad]).hexdigest(),
                         report["files"][wad]["sha256"])
        self.assertTrue(proof["raven_material_byte_identical"])
        self.assertTrue(proof["no_low_byte_cohort_collision"])
        self.assertTrue(proof["exact_inverse_to_node_isolated_candidate"])
        self.assertEqual(len(proof["material_keys"]), 4)
        self.assertEqual(outputs[wad], (builder.OUT / wad).read_bytes())


class MaterialInstallerTest(old_tests.NornirNativeInstallerTest):
    def setUp(self):
        previous = old_tests.installer
        old_tests.installer = wrapper.base
        self.addCleanup(lambda: setattr(old_tests, "installer", previous))
        super().setUp()
        path = self.build / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["kind"] = wrapper.base.EXPECTED_KIND
        report["proof"][wrapper.base.WAD]["model_group_isolation"] = {
            "new_model_groups": 8,
            "raven_model_groups_preserved": True,
            "nornir_family_model_groups_unique": True,
            "exact_inverse_to_art_package": True,
        }
        report["proof"][wrapper.base.WAD]["prototype_child_isolation"] = {
            "new_internal_node_ids": 16,
            "map_child_ids_per_family": 3,
            "hud_child_ids_per_family": 1,
            "raven_prototypes_preserved": True,
            "exact_inverse_to_model_group_candidate": True,
        }
        report["proof"][wrapper.base.WAD]["material_key_isolation"] = {
            "four_independent_name_hashes": True,
            "no_low_byte_cohort_collision": True,
            "raven_material_byte_identical": True,
            "same_wad_length": True,
            "exact_inverse_to_node_isolated_candidate": True,
            "material_keys": {name: {} for name in builder.materials.FAMILIES},
        }
        path.write_text(json.dumps(report), encoding="utf-8")

    def test_missing_material_proof_blocks_install(self):
        path = self.build / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["proof"][wrapper.base.WAD].pop("material_key_isolation")
        path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "material key isolation proof absent"):
            wrapper.base.install(self.build, self.game, lambda: None)
        for relative in wrapper.base.NEW_FILES:
            self.assertFalse((self.game / relative).exists())


if __name__ == "__main__":
    unittest.main()
