"""Fail-closed Artefact family gate tests."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

import artefact_static_gate as gate


class ArtefactStaticGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = tuple(json.loads(path.read_text(encoding="utf-8")) for path in
                           (gate.CATALOGUE, gate.AUDIT, gate.SHIP_GATE, gate.PARENT_AUDIT))

    def changed(self, mutate):
        cat, audit, ship, parent = copy.deepcopy(self.inputs)
        mutate(cat, audit, ship, parent)
        audit["catalogue_sha256"] = hashlib.sha256(gate.canonical_json(cat).encode()).hexdigest()
        parent["catalogue_lf_sha256"] = audit["catalogue_sha256"]
        return gate.assess(cat, audit, ship, parent)

    def test_physical_census_and_subtypes_stay_distinct(self):
        report = gate.assess(*self.inputs)
        self.assertEqual(report["physical_count"], 45)
        self.assertEqual(report["subtype_counts"], gate.SUBTYPE_COUNTS)
        self.assertEqual((report["direct_shiphead_parent_count"],
                          report["other_artefact_unbound_count"],
                          report["shiphead_native_target"]), (9, 36, 10))
        self.assertEqual(report["frozen_serialized_identity_count"], 8)
        self.assertFalse(report["runtime_generation_allowed"])
        self.assertTrue(all(not row["production_ready"] and not row["marker_generation_ready"]
                            for row in report["rows"]))

    def test_region_inference_cannot_attach_shiphead_parent_to_toy(self):
        def mutate(cat, _audit, _ship, _parent):
            row = next(row for row in cat["collectibles"] if row["catalogue_id"] ==
                       "artefact_989065ff4bde64f5ec957da2759037cb")
            row["progression"]["parent_quest"] = "RegionSummary_CALS_Shiphead_Parent"
            row["progression"]["parent_quest_source"] = "unique_region_family_inference"
        with self.assertRaisesRegex(ValueError, "non-Ship-Head row has unproved parent"):
            self.changed(mutate)

    def test_duplicate_physical_identity_fails(self):
        def mutate(cat, _audit, _ship, _parent):
            rows = [row for row in cat["collectibles"] if row["family"] == "artefact"]
            rows[1]["source"]["wad"] = rows[0]["source"]["wad"]
            rows[1]["native"]["instance_guid"] = rows[0]["native"]["instance_guid"]
        with self.assertRaisesRegex(ValueError, "duplicate Artefact physical/catalogue identity"):
            self.changed(mutate)

    def test_ship_gate_cannot_grant_runtime_generation(self):
        with self.assertRaisesRegex(ValueError, "Ship Head evidence gate differs or grants delivery"):
            self.changed(lambda _cat, _audit, ship, _parent: ship.update(runtime_generation_allowed=True))

    def test_shiphead_parent_needs_exact_attribute_proof(self):
        def mutate(_cat, _audit, ship, _parent):
            ship["rows"][0]["native_parent_attribute_proven"] = False
        with self.assertRaisesRegex(ValueError, "Ship Head direct parent evidence differs"):
            self.changed(mutate)

    def test_parent_audit_cannot_claim_direct_override_text(self):
        def mutate(_cat, _audit, _ship, parent):
            parent["rows"][0]["parent_present_in_exact_override"] = True
        with self.assertRaisesRegex(ValueError, "cross-subtype parent evidence differs"):
            self.changed(mutate)


if __name__ == "__main__":
    unittest.main()
