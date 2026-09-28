"""Check Nornir child-node isolation and reversible installation."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("nornir_node_builder_test", "build-nornir-native-node-isolated-test.py")
wrapper = load("nornir_node_installer_test", "install-nornir-native-node-isolated-test.py")
old_tests = load("nornir_native_installer_tests_base", "test_nornir_native_installer.py")


class NodeBuildTest(unittest.TestCase):
    def test_reproducible_full_candidate_and_exact_inverse(self):
        # Build against the Raven files backed up before the live install, so
        # this check remains runnable while the candidate is installed.
        report_path = builder.REPORT
        prior_report = json.loads(report_path.read_text(encoding="utf-8"))
        journals = sorted(report_path.parent.glob("backups/*/operation.json"))
        backups = [path.parent / "before" for path in journals
                   if json.loads(path.read_text(encoding="utf-8")).get("status")
                   in {"installed", "rolled_back"}]
        source = next((folder for folder in backups
                       if all((folder / rel).exists() and
                              hashlib.sha256((folder / rel).read_bytes()).hexdigest() == expected
                              for rel, expected in prior_report["source_sha256"].items())), None)
        self.assertIsNotNone(source)
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary)
            for relative in prior_report["source_sha256"]:
                destination = game / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, destination)
            graph = builder.base.base.GRAPH
            target = game / graph
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(builder.base.base.base.GAME / graph, target)
            first, report = builder.build(game)
            second, repeated = builder.build(game)
        self.assertEqual(first, second)
        self.assertEqual(report, repeated)
        wad = builder.base.base.WAD
        proof = report["proof"][wad]["prototype_child_isolation"]
        self.assertEqual(proof["new_internal_node_ids"], 16)
        self.assertTrue(proof["raven_prototypes_preserved"])
        self.assertTrue(proof["exact_inverse_to_model_group_candidate"])
        self.assertNotEqual(report["files"][wad]["sha256"],
                            report["source_model_group_wad_sha256"])


class NodeInstallerTest(old_tests.NornirNativeInstallerTest):
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
        path.write_text(json.dumps(report), encoding="utf-8")

    def test_missing_child_identity_proof_blocks_install(self):
        path = self.build / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["proof"][wrapper.base.WAD].pop("prototype_child_isolation")
        path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prototype child identity proof absent"):
            wrapper.base.install(self.build, self.game, lambda: None)
        for relative in wrapper.base.NEW_FILES:
            self.assertFalse((self.game / relative).exists())


if __name__ == "__main__":
    unittest.main()
