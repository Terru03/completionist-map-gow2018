"""Nornir source integrity and fail-closed checks."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest

import nornir_static_gate as gate
import nornir_marker_namespace as namespace


class NornirStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(gate.CATALOGUE.read_text(encoding="utf-8"))
        cls.audit = json.loads(gate.AUDIT.read_text(encoding="utf-8"))
        cls.ravens = json.loads(gate.RAVENS.read_text(encoding="utf-8"))
        cls.marker_manifest = json.loads(gate.MARKER_NAMESPACE.read_text(encoding="utf-8"))

    def changed(self, mutate):
        catalogue = copy.deepcopy(self.catalogue)
        audit = copy.deepcopy(self.audit)
        mutate(catalogue, audit)
        audit["catalogue_sha256"] = hashlib.sha256(
            gate.canonical_json(catalogue).encode()).hexdigest()
        return gate.assess(catalogue, audit)

    def test_all_physical_chests_hold_runtime_off(self):
        report = gate.assess(self.catalogue, self.audit)
        self.assertEqual((report["physical_count"], report["tracked_candidate_count"],
                          report["linked_child_count"], report["direct_native_binding_count"]),
                         (22, 21, 66, 0))
        self.assertFalse(report["runtime_generation_allowed"])
        with self.assertRaisesRegex(ValueError, "Nornir generation blocked"):
            gate.require_generation_ready(report)

    def test_parent_and_child_markers_have_separate_reserved_identities(self):
        report = gate.assess(self.catalogue, self.audit)
        manifest = self.marker_manifest
        self.assertEqual(manifest, namespace.build_manifest(self.catalogue, self.ravens))
        self.assertEqual((report["reserved_parent_marker_count"],
                          report["reserved_child_marker_count"]), (22, 66))
        self.assertFalse(manifest["native_registration_allowed"])
        raven_uids = {row["marker"]["uid"] for row in self.ravens["ravens"]}
        raven_uids.add("E15E6BC82AE2773E")  # frozen v0.10.4 Raven
        all_nornir_uids = [record["uid"] for group in manifest["groups"]
                           for record in [group["parent"], *group["children"]]]
        self.assertEqual(len(all_nornir_uids), len(set(all_nornir_uids)))
        self.assertFalse(set(all_nornir_uids) & raven_uids)
        self.assertNotIn(manifest["namespace"]["uid"], raven_uids | set(all_nornir_uids))
        self.assertTrue(all(len(group["children"]) == 3 for group in manifest["groups"]))

    def test_installed_id_audit_is_bound_to_exact_manifest(self):
        manifest_bytes = gate.MARKER_NAMESPACE.read_bytes()
        audit_path = gate.REPO / "docs/research/nornir-installed-marker-id-audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["result"], "NORNIR_INSTALLED_MARKER_IDS_CLEAR_READ_ONLY")
        self.assertEqual(audit["collision_count"], 0)
        self.assertEqual(audit["namespace_manifest_sha256"],
                         hashlib.sha256(manifest_bytes.replace(b"\r\n", b"\n")).hexdigest())

    def test_raven_marker_uid_cannot_be_assigned_to_nornir(self):
        def collide(cat, _audit):
            chest = next(row for row in cat["collectibles"]
                         if row["family"] == "nornir_chest")
            chest["marker"]["uid"] = self.ravens["ravens"][0]["marker"]["uid"]
        with self.assertRaisesRegex(ValueError, "reuses reserved Raven/other identity"):
            self.changed(collide)

    def test_raven_visual_cannot_be_assigned_to_nornir(self):
        def reuse_raven_visual(cat, _audit):
            chest = next(row for row in cat["collectibles"]
                         if row["family"] == "nornir_chest")
            chest["marker"]["map_resource"] = "goMapIconCompletionistRaven"
        with self.assertRaisesRegex(ValueError, "uses another family's visual/class"):
            self.changed(reuse_raven_visual)

    def test_manifest_cannot_reassign_child_to_another_chest(self):
        manifest = copy.deepcopy(self.marker_manifest)
        child = manifest["groups"][0]["children"].pop()
        manifest["groups"][1]["children"].append(child)
        with self.assertRaisesRegex(ValueError, "marker ownership manifest differs"):
            gate.assess(self.catalogue, self.audit, self.ravens, manifest)

    def test_weak_count_join_rejected(self):
        with self.assertRaisesRegex(ValueError, "weak Nornir join authority"):
            self.changed(lambda _cat, audit:
                         audit["nornir_accounting"].update(target_count_is_join_authority=True))

    def test_unproved_quest_claim_rejected(self):
        with self.assertRaisesRegex(ValueError, "unproved parent state or quest promoted"):
            self.changed(lambda cat, _audit:
                         next(row for row in cat["collectibles"] if row["family"] == "nornir_chest")
                         ["progression"].update(parent_quest="RegionSummary_RunicChest_Parent_Alfheim"))

    def test_child_link_must_be_exact(self):
        with self.assertRaisesRegex(ValueError, "child parent reference differs"):
            self.changed(lambda cat, _audit:
                         next(row for row in cat["collectibles"] if row["family"] == "nornir_bell")
                         ["native"].update(parent_reference_source="nearby_chest"))

    def test_missing_binding_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "evidence does not cover every parent"):
            self.changed(lambda _cat, audit:
                         audit["nornir_exact_binding_evidence"].pop())

    def test_helheim_exception_must_have_source_proof(self):
        with self.assertRaisesRegex(ValueError, "Helheim exception evidence differs"):
            self.changed(lambda _cat, audit:
                         audit["helheim_unjoined_nornir"].update(result="UNPROVED"))

    def test_catalogue_checkout_and_git_blob_have_same_content(self):
        blob = subprocess.check_output(
            ["git", "show", "HEAD:config/collectibles/v0.10.5/all-collectibles.json"],
            cwd=gate.REPO)
        self.assertEqual(
            hashlib.sha256(gate.CATALOGUE.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            hashlib.sha256(blob).hexdigest())


if __name__ == "__main__":
    unittest.main()
