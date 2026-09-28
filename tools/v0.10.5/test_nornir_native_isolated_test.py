"""Check isolated Nornir build and installer transaction."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("nornir_isolated_builder_test", "build-nornir-native-isolated-test.py")
wrapper = load("nornir_isolated_installer_test", "install-nornir-native-isolated-test.py")
old_tests = load("nornir_native_installer_tests_base", "test_nornir_native_installer.py")


class IsolatedBuildTest(unittest.TestCase):
    def test_eight_model_groups_and_reproducible_output(self):
        first, report = builder.build()
        second, repeated = builder.build()
        self.assertEqual(first, second)
        self.assertEqual(report, repeated)
        proof = report["proof"][builder.base.WAD]["model_group_isolation"]
        self.assertEqual(proof["new_model_groups"], 8)
        self.assertTrue(proof["raven_model_groups_preserved"])
        self.assertTrue(proof["exact_inverse_to_art_package"])
        self.assertNotEqual(report["files"][builder.base.WAD]["sha256"],
                            report["source_art_wad_sha256"])


class IsolatedInstallerTest(old_tests.NornirNativeInstallerTest):
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
        path.write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
