"""Fail-closed tests for master collectible inventory policy."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("master_inventory", HERE / "build-master-collectible-inventory.py")
assert SPEC and SPEC.loader
inv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inv)


class MasterCollectibleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(inv.DEFAULT_POLICY.read_text(encoding="utf-8"))

    def test_valkyrie_never_duplicates_native_marker(self):
        marker, source = inv.marker_policy(self.policy, "valkyrie", None)
        self.assertEqual(marker, "NATIVE_MARKER_NO_DUPLICATE")
        self.assertEqual(source, "family_policy")

    def test_gateway_and_shop_never_duplicate_native_markers(self):
        self.assertEqual(inv.marker_policy(self.policy, "mystic_gateway", None)[0], "NATIVE_MARKER_NO_DUPLICATE")
        self.assertEqual(inv.marker_policy(self.policy, "shop", None)[0], "NATIVE_MARKER_NO_DUPLICATE")

    def test_unknown_family_fails_closed(self):
        marker, source = inv.marker_policy(self.policy, "mystery_collectible", None)
        self.assertEqual(marker, "RESEARCH_REQUIRED")
        self.assertEqual(source, "default_fail_closed")

    def test_guide_count_never_authorizes_runtime_marker(self):
        row = {
            "catalogue_id": "raven_test",
            "family": "raven",
            "realm_id": "midgard",
            "region_id": "test",
            "native": {"instance_guid": "00000000-0000-0000-0000-000000000001"},
            "marker": {"position_world": [1, 2, 3]},
        }
        normalized = inv.normalize(row, Path("fixture.json"), self.policy)
        self.assertEqual(normalized["mod_marker_policy"], "CUSTOM_MARKER_CANDIDATE")
        self.assertFalse(normalized["mod_marker_allowed"])
        self.assertIn("never authorizes", normalized["marker_block_reason"])

    def test_ship_head_subtype_remains_candidate_but_not_authorized(self):
        row = {
            "catalogue_id": "artefact_test",
            "family": "artefact",
            "subtype": "Ship Head",
            "native": {"instance_guid": "00000000-0000-0000-0000-000000000002"},
        }
        normalized = inv.normalize(row, Path("fixture.json"), self.policy)
        self.assertEqual(normalized["mod_marker_policy"], "CUSTOM_MARKER_CANDIDATE")
        self.assertEqual(normalized["mod_marker_policy_source"], "subtype_override")
        self.assertFalse(normalized["mod_marker_allowed"])

    def test_conflicting_duplicate_physical_rows_are_rejected(self):
        a = {"catalogue_id": "x", "physical_id": "g", "family": "artefact", "source_row_sha256": "a"}
        b = {"catalogue_id": "x", "physical_id": "g", "family": "artefact", "source_row_sha256": "b"}
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            inv.dedupe([a, b])

    def test_different_catalogue_ids_same_physical_identity_are_rejected(self):
        a = {"catalogue_id": "a", "physical_id": "g", "family": "artefact"}
        b = {"catalogue_id": "b", "physical_id": "G", "family": "artefact"}
        with self.assertRaisesRegex(ValueError, "duplicate physical identity"):
            inv.dedupe([a, b])

    def test_external_expected_count_creates_no_physical_rows(self):
        audit = inv.discrepancy(self.policy, [])
        raven = next(x for x in audit if x["family"] == "odin_raven")
        self.assertEqual(raven["external_guide_expected"], 51)
        self.assertEqual(raven["physical_rows"], 0)
        self.assertEqual(raven["audit_status"], "NO_PHYSICAL_EVIDENCE")

    def test_physical_and_tracked_censuses_are_separate(self):
        rows = [{"family": "nornir_chest", "production_ready": False, "marker_generation_ready": False} for _ in range(22)]
        audit = inv.discrepancy(self.policy, rows, {"nornir_chest": {"tracked_candidates": 21, "explained_untracked": 1, "unresolved": 0}})
        nornir = next(x for x in audit if x["family"] == "nornir_chest")
        self.assertEqual((nornir["physical_rows"], nornir["tracked_candidates"], nornir["explained_untracked"]), (22, 21, 1))
        self.assertEqual(nornir["audit_status"], "GUIDE_MATCHES_TRACKED_CANDIDATES")

    def test_evidence_cannot_authorize_marker(self):
        for key in ("mod_marker_allowed", "runtime_generation_allowed"):
            with self.assertRaisesRegex(ValueError, "authorize runtime marker"):
                inv.reject_marker_authority({"rows": [{key: True}]})

    def test_real_pinned_family_overlays(self):
        manifest = os.environ.get("MASTER_SOURCE_MANIFEST")
        if not manifest:
            self.skipTest("wrapper supplies pinned family source manifest")
        rows, summary, sources = inv.load_pinned_sources(Path(manifest), self.policy)
        audit = {x["family"]: x for x in inv.discrepancy(self.policy, rows, summary)}
        self.assertEqual((audit["odin_raven"]["physical_rows"], audit["odin_raven"]["native_accounting_target"]), (53, 51))
        self.assertEqual((audit["nornir_chest"]["physical_rows"], audit["nornir_chest"]["tracked_candidates"], audit["nornir_chest"]["explained_untracked"]), (22, 21, 1))
        legendary = audit["legendary_chest"]
        self.assertEqual((legendary["physical_rows"], legendary["tracked_candidates"], legendary["explained_untracked"], legendary["unresolved"]), (64, 33, 29, 2))
        self.assertEqual(legendary["classification_counts"], {"tracked_legendary": 33, "trial_reward": 27, "non_map_counted_physical": 2, "unresolved_nontracked": 2})
        self.assertEqual(legendary["audit_status"], "GUIDE_TRACKED_CANDIDATE_DISAGREEMENT")
        self.assertEqual(legendary["gate_catalogue_hash_basis"], "windows_crlf_checkout_bytes")
        self.assertFalse(legendary["catalogue_content_changed_since_gate"])
        self.assertEqual(len(sources), 6)
        self.assertTrue(all(x["source_commit"] and x["source_sha256"] for x in sources))
        self.assertTrue(all(not row["mod_marker_allowed"] and not row["marker_generation_ready"] for row in rows))
        self.assertTrue(all(row["classification_evidence"] for row in rows if row["family"] in ("odin_raven", "nornir_chest", "legendary_chest")))

    def test_generated_report_retains_evidence_provenance(self):
        manifest = os.environ.get("MASTER_SOURCE_MANIFEST")
        if not manifest:
            self.skipTest("wrapper supplies pinned family source manifest")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["python", str(HERE / "build-master-collectible-inventory.py"),
                            "--source-manifest", manifest, "--output-dir", td], check=True, capture_output=True)
            report = json.loads((Path(td) / "master-collectible-inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["source_catalogues"]), 6)
            raven = next(row for row in report["rows"] if row["family"] == "odin_raven")
            self.assertEqual(raven["catalogue_provenance"]["source_branch"], "codex/all-ravens-release-candidate")
            self.assertTrue(raven["classification_evidence"][0]["source"]["source_sha256"])
            self.assertFalse(report["runtime_generation_allowed"])

    def test_conflicting_gate_identity_fails_closed(self):
        manifest = os.environ.get("MASTER_SOURCE_MANIFEST")
        if not manifest:
            self.skipTest("wrapper supplies pinned family source manifest")
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        for entry in data["sources"]:
            entry["file"] = str((Path(manifest).resolve().parent / entry["file"]).resolve())
        gate = next(x for x in data["sources"] if x["role"] == "family_gate")
        with tempfile.TemporaryDirectory() as td:
            changed = Path(td) / "gate.json"
            original = json.loads(Path(gate["file"]).read_text(encoding="utf-8"))
            original["rows"][0]["catalogue_id"] = "nonexistent_nornir_chest"
            changed.write_text(json.dumps(original), encoding="utf-8")
            gate["file"] = str(changed)
            gate["sha256"] = inv.sha(changed)
            pinned = Path(td) / "manifest.json"
            pinned.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identities conflict"):
                inv.load_pinned_sources(pinned, self.policy)

    def test_conflicting_gate_catalogue_hash_fails_closed(self):
        manifest = os.environ.get("MASTER_SOURCE_MANIFEST")
        if not manifest:
            self.skipTest("wrapper supplies pinned family source manifest")
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        for entry in data["sources"]:
            entry["file"] = str((Path(manifest).resolve().parent / entry["file"]).resolve())
        gate = next(x for x in data["sources"] if x["role"] == "family_gate")
        with tempfile.TemporaryDirectory() as td:
            changed = Path(td) / "gate.json"
            original = json.loads(Path(gate["file"]).read_text(encoding="utf-8"))
            original["source_sha256"]["config/collectibles/v0.10.5/all-collectibles.json"] = "0" * 64
            changed.write_text(json.dumps(original), encoding="utf-8")
            gate["file"] = str(changed)
            gate["sha256"] = inv.sha(changed)
            pinned = Path(td) / "manifest.json"
            pinned.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content conflict"):
                inv.load_pinned_sources(pinned, self.policy)

    def test_empty_catalogue_is_valid_incomplete_input(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.json"
            p.write_text("", encoding="utf-8")
            self.assertEqual(inv.load_catalogue(p), [])


if __name__ == "__main__":
    unittest.main()
