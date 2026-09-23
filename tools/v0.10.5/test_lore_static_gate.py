"""Lore static proof and fail-closed regression tests."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

import lore_static_gate as gate


class LoreStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = tuple(json.loads(path.read_text(encoding="utf-8")) for path in
                           (gate.CATALOGUE, gate.AUDIT, gate.BINDINGS))

    def changed(self, mutate):
        catalogue, audit, bindings = copy.deepcopy(self.inputs)
        mutate(catalogue, audit, bindings)
        digest = hashlib.sha256(gate.canonical_json(catalogue).encode()).hexdigest()
        audit["catalogue_sha256"] = digest
        bindings["catalogue_lf_sha256"] = digest
        return gate.assess(catalogue, audit, bindings)

    def test_census_and_gate(self):
        report = gate.assess(*self.inputs)
        self.assertEqual((report["physical_count"], report["direct_object_parent_count"],
                          report["level_script_context_count"], report["native_summary_target"],
                          report["external_guide_count_user_baseline"]), (43, 40, 3, 43, 39))
        self.assertEqual(report["native_with_journal_id_count"], 37)
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertTrue(all(not row["production_ready"] and not row["marker_generation_ready"]
                            for row in report["rows"]))

    def test_script_context_cannot_be_promoted_to_exact_parent(self):
        def mutate(catalogue, _audit, _bindings):
            row = next(row for row in catalogue["collectibles"] if row["family"] ==
                       "lore_marker" and row["subtype"] == "level_script_lore_marker")
            row["progression"]["parent_quest"] = "RegionSummary_CALT_LoreMarker_Parent"
            row["progression"]["parent_quest_source"] = "exact_native_object_attribute"
        with self.assertRaisesRegex(ValueError, "level Lore context falsely promoted"):
            self.changed(mutate)

    def test_native_parent_needs_exact_record_proof(self):
        def mutate(_catalogue, _audit, bindings):
            row = next(row for row in bindings["rows"] if row["subtype"] ==
                       "native_lore_marker")
            row["binding"] = "inferred"
        with self.assertRaisesRegex(ValueError, "native Lore direct binding differs"):
            self.changed(mutate)

    def test_duplicate_physical_identity_fails(self):
        def mutate(catalogue, _audit, _bindings):
            rows = [row for row in catalogue["collectibles"] if row["family"] == "lore_marker"]
            rows[1]["source"]["wad"] = rows[0]["source"]["wad"]
            rows[1]["native"]["instance_guid"] = rows[0]["native"]["instance_guid"]
        with self.assertRaisesRegex(ValueError, "duplicate Lore physical"):
            self.changed(mutate)

    def test_binding_audit_cannot_grant_generation(self):
        with self.assertRaisesRegex(ValueError, "Lore binding audit differs"):
            self.changed(lambda _catalogue, _audit, bindings:
                         bindings.update(runtime_generation_allowed=True))


if __name__ == "__main__":
    unittest.main()
