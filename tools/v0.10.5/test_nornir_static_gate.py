"""Nornir source integrity and fail-closed checks."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

import nornir_static_gate as gate


class NornirStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(gate.CATALOGUE.read_text(encoding="utf-8"))
        cls.audit = json.loads(gate.AUDIT.read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
