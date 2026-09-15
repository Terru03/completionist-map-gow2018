"""Offline tests for Raven scheduler/allocator runtime capture protocol."""
from __future__ import annotations

import base64
import ctypes
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("capture-raven-scheduler-allocator-runtime.py")


def load_module():
    spec = importlib.util.spec_from_file_location("raven_scheduler_allocator_runtime", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_token_round_trip(self):
        for registry_id, flavor, slot in ((0, 0, 0), (0x1234, 1, 0x54321), (0xFFFF, 1, 0xFFFFF)):
            token = self.module.encode_token(registry_id, flavor, slot)
            self.assertEqual(self.module.decode_token(token), {
                "registry_id": registry_id, "flavor": flavor, "slot": slot})

    def test_circular_scan_skips_zero_and_wraps(self):
        report = self.module.circular_scan([0, 11, 0, 33], 3, 4)
        self.assertEqual([row["slot"] for row in report["tested"]], [3, 1, 2])
        self.assertEqual(report["selected_slot"], 2)
        self.assertEqual(report["next_cursor"], 3)

    def test_exact_binding_never_uses_name_or_id_alone(self):
        target = {"raw": b"FULL", "payload": b"PAYLOAD", "payload_unique": True,
                  "name": "raven", "sha256": "x"}
        blob = {"label": "x", "address": "0x1000", "data_base64": base64.b64encode(
            b"raven" + bytes.fromhex(self.module.TARGET_RECORD_ID)).decode("ascii")}
        result = self.module.exact_binding_from_blobs([blob], target)
        self.assertFalse(result["proved"])
        self.assertIsNone(result["method"])

    def test_exact_binding_accepts_unique_full_payload(self):
        target = {"raw": b"HEADERPAYLOAD", "payload": b"PAYLOAD", "payload_unique": True,
                  "name": "raven", "sha256": "x"}
        blob = {"label": "scheduler", "address": "0x2000",
                "data_base64": base64.b64encode(b"xxPAYLOADyy").decode("ascii")}
        result = self.module.exact_binding_from_blobs([blob], target)
        self.assertTrue(result["proved"])
        self.assertEqual(result["method"], "unique_full_raw_record_payload")

    def _run(self, history: bool, token: int = 0x100001):
        decoded = self.module.decode_token(token)
        return {
            "exact_record_binding": {"proved": True},
            "allocator": {"registry_id": decoded["registry_id"], "cursor": 3, "live_count": 4,
                          "occupancy_sha256": "same", "selected_slot": decoded["slot"]},
            "gameobject": {"decoded": {**decoded, "token": token}},
            "allocator_history": {"complete_since_fresh_registry": history,
                                  "stable_event_identities_complete": history,
                                  "causal_sha256": "causal" if history else None},
        }

    def test_same_token_without_causal_history_stays_blocked(self):
        result = self.module.compare_runs(self._run(False), self._run(False))
        self.assertEqual(result["gameobject_persistent_key_status"], "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY")
        self.assertIn("prior_dynamic_history", result["classification"])

    def test_pass_requires_exact_binding_and_same_complete_history(self):
        result = self.module.compare_runs(self._run(True), self._run(True))
        self.assertEqual(result["gameobject_persistent_key_status"], "PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY")
        self.assertTrue(result["causal_history_reproducible"])

    def test_instruction_contract_is_version_locked(self):
        self.assertEqual(self.module.BREAKPOINTS["canonical_loader_call"], (0x859C0D, "e83ed3ffff"))
        self.assertEqual(self.module.BREAKPOINTS["allocator_entry"], (0x4EF2B0, "4055"))
        self.assertIn("descriptor_no_hint", self.module.ANCHORS)

    def test_windows_context_layout_matches_amd64_abi(self):
        if hasattr(self.module, "CONTEXT64"):
            self.assertEqual(ctypes.sizeof(self.module.CONTEXT64), 1232)
            self.assertEqual(self.module.CONTEXT64.Rip.offset, 248)

    def test_static_preflight_checks_supported_local_files_when_present(self):
        exe = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe")
        wad = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar\exec\wad\pc_le\alf355_chiseldungeon.wad")
        if not exe.is_file() or not wad.is_file():
            self.skipTest("supported local game files absent")
        result = self.module.static_preflight(exe, wad)
        self.assertEqual(result["status"], "PREFLIGHT_PASSED_ATTACH_NOT_TESTED")
        self.assertFalse(result["process_attach_tested"])
        self.assertEqual(result["canonical_record_index"], 9633)

    def test_windows_api_prototypes_are_explicit(self):
        if hasattr(self.module, "kernel32"):
            for name in ("CreateToolhelp32Snapshot", "Module32FirstW", "Thread32First",
                         "Thread32Next", "OpenProcess", "OpenThread", "CloseHandle",
                         "DebugActiveProcess", "DebugActiveProcessStop",
                         "DebugSetProcessKillOnExit", "FlushInstructionCache",
                         "SuspendThread", "ResumeThread"):
                self.assertIsNotNone(getattr(self.module.kernel32, name).argtypes, name)

    def test_wrong_executable_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GoW.exe"
            path.write_bytes(b"not the supported executable")
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                self.module.verify_image(path)


if __name__ == "__main__":
    unittest.main()
