"""Check fail-closed registry provenance tracer rules."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("trace-gow-registry-runtime-provenance.py")


def load_module():
    spec = importlib.util.spec_from_file_location("registry_runtime_provenance", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegistryRuntimeProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_registry_table_shape(self):
        self.assertEqual(self.module.TABLE_BYTES, 64 * 8)
        self.assertEqual(self.module.TABLE_BEGIN + self.module.TABLE_BYTES, 0x22A9AC0)

    def test_writer_anchors_stay_exact(self):
        self.assertEqual(self.module.ANCHORS["registry_table_insert"], 0x4F37A2)
        self.assertEqual(self.module.ANCHORS["registry_table_remove"], 0x4F35A5)
        self.assertEqual(set(self.module.ANCHORS), set(self.module.ANCHOR_EXPECTED))

    def test_status_names_stay_fail_closed(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY"', source)
        self.assertIn('"BLOCKED_EXACT_UNLOADED_STATE_ORACLE"', source)
        self.assertNotIn('"PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY"', source)


if __name__ == "__main__":
    unittest.main()
