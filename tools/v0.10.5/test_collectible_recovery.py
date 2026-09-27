"""Capacity boundary and rollback of a user's modified installation."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).with_name("recover-collectible-locations.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

class RecoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.game, self.build = Path(temporary.name)/"game", Path(temporary.name)/"build"
        files = {}
        for name in recovery.FILES:
            source = self.game/name
            before = None
            if name != recovery.UPSTREAM:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(("user modified " + name).encode())
                before = recovery.io.sha(source)
            candidate = self.build/"candidate/game-root"/name
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(("fixed " + name).encode())
            files[name] = {"before": before, "after": recovery.io.sha(candidate)}
        self.files = files
        report = {"kind": recovery.KIND, "schema": 1, "location_count": 410,
                  "native_marker_capacity": 2048, "native_marker_entries": 922,
                  "capacity_shim": {"upstream_sha256": recovery.builder.UNTOUCHED["dxgi.dll"],
                                    "marker_slots": 2048, "entity_slots": 4096,
                                    "ui_physics_slots": 2048},
                  "preserved": {}, "files": files}
        recovery.io.write_json(self.build/"report.json", report)

    def test_rollback_restores_modified_files_and_removes_owned_companion(self):
        journal = recovery.install(self.game, self.build, lambda: None)
        recovery.verify(journal, self.game, self.build, lambda: None)
        shutil.rmtree(self.build/"candidate")
        recovery.rollback(journal, self.game, self.build, lambda: None)
        for name, hashes in self.files.items():
            self.assertEqual(recovery.io.sha(self.game/name), hashes["before"])

    def test_failure_after_companion_copy_restores_complete_user_state(self):
        original = recovery.io.atomic_copy
        def fail(source, dest, after, before):
            if "candidate" in source.parts and dest.name == "dxgi.dll":
                raise OSError("write failure")
            return original(source, dest, after, before)
        with patch.object(recovery.io, "atomic_copy", fail), self.assertRaises(OSError):
            recovery.install(self.game, self.build, lambda: None)
        for name, hashes in self.files.items():
            self.assertEqual(recovery.io.sha(self.game/name), hashes["before"])

    def test_unrelated_edit_prevents_every_rollback_write(self):
        journal = recovery.install(self.game, self.build, lambda: None)
        (self.game/"dxgi.dll").write_bytes(b"new user edit")
        with self.assertRaisesRegex(ValueError, "unrelated edit"):
            recovery.rollback(journal, self.game, self.build, lambda: None)
        self.assertEqual(recovery.io.sha(self.game/recovery.FILES[0]), self.files[recovery.FILES[0]]["after"])

    def test_unmodified_engine_capacity_rejects_full_location_layer(self):
        source = recovery.BUILD/"v4-source"
        with self.assertRaisesRegex(ValueError, "922 > 732"):
            recovery.builder.build(source)

    def test_marker_only_shim_is_rejected_before_install(self):
        report = json.loads((self.build/"report.json").read_text())
        del report["capacity_shim"]["entity_slots"]
        recovery.io.write_json(self.build/"report.json", report)
        with self.assertRaisesRegex(ValueError, "invalid recovery candidate"):
            recovery.install(self.game, self.build, lambda: None)
        for name, hashes in self.files.items():
            self.assertEqual(recovery.io.sha(self.game/name), hashes["before"])

    def test_shim_without_ui_physics_capacity_is_rejected_before_install(self):
        report = json.loads((self.build/"report.json").read_text())
        del report["capacity_shim"]["ui_physics_slots"]
        recovery.io.write_json(self.build/"report.json", report)
        with self.assertRaisesRegex(ValueError, "invalid recovery candidate"):
            recovery.install(self.game, self.build, lambda: None)
        for name, hashes in self.files.items():
            self.assertEqual(recovery.io.sha(self.game/name), hashes["before"])

if __name__ == "__main__": unittest.main()
