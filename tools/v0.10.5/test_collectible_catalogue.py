"""Native non-Raven catalogue contract tests."""
from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

import jsonschema


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import collectible_catalogue as catalogue_tool


CATALOGUE_PATH = REPO / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"
SCHEMA_PATH = CATALOGUE_PATH.with_name("all-collectibles.schema.json")
AUDIT_PATH = REPO / "docs" / "research" / "all-collectibles-native-audit.json"


class CollectibleCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        cls.rows = cls.catalogue["collectibles"]
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_schema(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(self.catalogue)

    def test_exact_static_family_counts(self):
        self.assertEqual(collections.Counter(row["family"] for row in self.rows), {
            "artefact": 43,
            "legendary_chest": 64,
            "lore_marker": 43,
            "nornir_bell": 24,
            "nornir_chest": 22,
            "nornir_mechanism": 12,
            "nornir_seal": 30,
        })

    def test_catalogue_and_marker_ids_unique(self):
        keys = [row["catalogue_id"] for row in self.rows]
        uids = [row["marker"]["uid"] for row in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(uids), len(set(uids)))

    def test_positions_are_finite_and_midgard_projection_present(self):
        for row in self.rows:
            self.assertTrue(all(math.isfinite(value) for value in row["marker"]["position_world"]))
            if row["realm"] == "Midgard":
                self.assertEqual(len(row["marker"]["position_map"]), 2)

    def test_every_fixed_nornir_parent_has_three_exact_children(self):
        children = collections.defaultdict(list)
        for row in self.rows:
            parent = row["progression"].get("parent_catalogue_id")
            if parent:
                children[parent].append(row)
        parents = [row for row in self.rows if row["family"] == "nornir_chest"]
        for parent in parents:
            linked = children[parent["catalogue_id"]]
            self.assertEqual(len(linked), 3, parent["catalogue_id"])
            self.assertTrue(all(row["native"]["parent_reference_source"]
                                == "exact_lua_table_attribute_on_parent_placement"
                                for row in linked))

    def test_nornir_subtypes_are_only_real_native_types(self):
        children = [row for row in self.rows if row["family"].startswith("nornir_")
                    and row["family"] != "nornir_chest"]
        self.assertEqual({row["native"]["key_type"] for row in children},
                         {"Breakable", "Bell", "MemoryChest"})
        self.assertEqual({row["subtype"] for row in children}, {"seal", "bell", "mechanism"})

    def test_parent_completion_never_uses_child_aggregate(self):
        parents = [row for row in self.rows if row["family"] == "nornir_chest"]
        self.assertTrue(all(row["progression"]["field"] == "state == OPENED" for row in parents))

    def test_native_tracked_discrepancies_are_explicit(self):
        self.assertEqual(self.audit["native_tracked_target_totals"], {
            "artefact_shiphead": 10,
            "legendary_chest": 33,
            "lore_marker": 43,
            "nornir_chest": 21,
        })
        self.assertEqual(self.audit["tracked_physical_counts"]["legendary_chest"], 33)
        self.assertEqual(self.audit["tracked_physical_counts"]["lore_marker"], 43)
        self.assertEqual(self.audit["tracked_physical_counts"]["nornir_chest"], 20)
        self.assertEqual(self.audit["tracked_physical_counts"]["artefact"], 9)

    def test_runtime_gate_is_fail_closed(self):
        self.assertFalse(self.audit["ready_for_runtime_test"])
        self.assertEqual(self.audit["family_gates"]["runtime_generation"], "BLOCKED_FAIL_CLOSED")
        self.assertEqual(self.catalogue["state_gate"], "unloaded_per_instance_queries_unresolved")
        self.assertTrue(all(row["progression"]["read_only"] for row in self.rows))

    def test_procedural_templates_are_not_physical_markers(self):
        self.assertEqual(self.audit["excluded"]["procedural_nornir_chest_template_placements"], 7)
        self.assertEqual(self.audit["excluded"]["procedural_legendary_chest_template_placements"], 56)
        self.assertFalse(any(row["source"]["wad"].lower().startswith("nid")
                             for row in self.rows if "chest" in row["family"]))

    def test_lambs_cress_is_excluded_from_artefacts(self):
        self.assertEqual(self.audit["excluded"]["non_artefact_shared_script_carriers"], 1)
        self.assertFalse(any("Lambs Cress" in row["native"].get("attribute_values", [])
                             for row in self.rows))

    def test_generated_catalogue_matches_native_fixture(self):
        if not catalogue_tool.GAME.is_dir():
            self.skipTest("native game fixture unavailable")
        generated, _audit = catalogue_tool.scan_native(catalogue_tool.GAME)
        self.assertEqual(hashlib.sha256(catalogue_tool.canonical_json(generated).encode()).hexdigest(),
                         hashlib.sha256(CATALOGUE_PATH.read_text(encoding="utf-8").encode()).hexdigest())

    def test_output_guard_rejects_escape_and_game_tree(self):
        with self.assertRaises(ValueError):
            catalogue_tool.safe_repo_output("../outside.json")
        with self.assertRaises(ValueError):
            catalogue_tool.safe_repo_output(str(catalogue_tool.GAME / "bad.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
