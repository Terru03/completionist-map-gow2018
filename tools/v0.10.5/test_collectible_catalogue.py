"""Native non-Raven catalogue contract tests."""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

import jsonschema


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import collectible_catalogue as catalogue_tool


CATALOGUE_PATH = REPO / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"
SCHEMA_PATH = CATALOGUE_PATH.with_name("all-collectibles.schema.json")
AUDIT_PATH = REPO / "docs" / "research" / "all-collectibles-native-audit.json"


def transform_record(name, prototype_id, parent_id, x, *, record_id):
    data = bytearray(164)
    data[0x0C:0x1C] = prototype_id
    data[0x54:0x64] = parent_id
    struct.pack_into("<9f", data, 0x68, 1, 0, 0, 0, 1, 0, 0, 0, 1)
    struct.pack_into("<3f", data, 0x8C, x, 0, 0)
    return {
        "name": name,
        "kind": 1,
        "flags": 0x3D,
        "size": 164,
        "data": bytes(data),
        "id": record_id,
        "offset": x,
    }


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
            "artefact": 45,
            "legendary_chest": 64,
            "lore_marker": 43,
            "nornir_bell": 24,
            "nornir_chest": 22,
            "nornir_mechanism": 12,
            "nornir_seal": 30,
        })

    def test_shared_prefab_child_expands_all_exact_first_parent_branches(self):
        shared_parent_id = bytes.fromhex("11" * 16)
        child = transform_record(
            "goartifactscript", bytes.fromhex("22" * 16), shared_parent_id, 1,
            record_id=bytes.fromhex("01" * 16))
        first = transform_record(
            "goartifactshiphead03", shared_parent_id, bytes(16), 10,
            record_id=bytes.fromhex("02" * 16))
        second = transform_record(
            "goartifactshiphead07", shared_parent_id, bytes(16), 20,
            record_id=bytes.fromhex("03" * 16))

        paths = catalogue_tool.exact_world_transforms(child, [first, child, second])
        repeated = catalogue_tool.exact_world_transforms(child, [first, child, second])

        self.assertEqual([path[1][0] for path in paths], [11, 21])
        self.assertEqual(
            [[path[0], path[1], path[2]] for path in paths],
            [[path[0], path[1], path[2]] for path in repeated])
        self.assertEqual(
            [[node["name"] for node in path[3]] for path in paths],
            [["goartifactscript", "goartifactshiphead03"],
             ["goartifactscript", "goartifactshiphead07"]])

    def test_no_nearest_record_first_parent_heuristic_remains(self):
        source = Path(catalogue_tool.__file__).read_text(encoding="utf-8")
        self.assertNotIn("abs(pair[0] - current_index)", source)

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
        self.assertNotIn("nornir_chest", self.audit["tracked_physical_counts"])
        self.assertEqual(self.audit["tracked_physical_counts"]["artefact"], 11)
        self.assertEqual(self.audit["ship_head_accounting"]["physical_placements"], 9)
        self.assertEqual(self.audit["ship_head_accounting"]["state_carriers"], 9)
        self.assertEqual(self.audit["ship_head_accounting"]["tracked_target"], 10)
        self.assertEqual(
            self.audit["ship_head_accounting"]["target_discrepancy_result"],
            "BLOCKED_EXACT_REASON_UNKNOWN")

    def test_legendary_raw_membership_and_production_eligibility_are_separate(self):
        rows = [row for row in self.rows if row["family"] == "legendary_chest"]
        self.assertEqual(len(rows), 64)
        self.assertEqual(collections.Counter(row["native_classification"] for row in rows), {
            "tracked_legendary": 33,
            "trial_reward": 27,
            "non_map_counted_physical": 2,
            "unresolved_nontracked": 2,
        })
        self.assertEqual(collections.Counter(row["production_eligibility"] for row in rows), {
            "tracked_collectible": 33,
            "exclude_trial_reward": 27,
            "exclude_non_map_counted": 2,
            "unresolved": 2,
        })
        tracked = [row for row in rows
                   if row["production_eligibility"] == "tracked_collectible"]
        self.assertEqual(len(tracked), 33)
        self.assertTrue(all(row["native_classification"] == "tracked_legendary"
                            and row["production_eligibility"] == "tracked_collectible"
                            for row in tracked))

    def test_every_legendary_has_machine_readable_classification_evidence(self):
        rows = [row for row in self.rows if row["family"] == "legendary_chest"]
        evidence = self.audit["legendary_classification_evidence"]
        self.assertEqual(len(evidence), 64)
        self.assertEqual({row["catalogue_id"] for row in evidence},
                         {row["catalogue_id"] for row in rows})
        required = {
            "catalogue_id", "physical_instance_guid", "state_carrier_guid",
            "state_carrier_guids", "wad", "world_xyz",
            "parent_region_summary_target", "classification",
            "production_eligibility", "final_status", "native_evidence_sources",
            "source_file_hashes", "record_locators", "rationale",
        }
        for item in evidence:
            self.assertTrue(required <= set(item), item["catalogue_id"])
            self.assertTrue(item["native_evidence_sources"])
            self.assertIn(item["final_status"], {
                "PASS_EXACT", "BLOCKED_EXACT_REASON_UNKNOWN"})

    def test_legendary_exclusions_require_pass_exact_positive_native_evidence(self):
        for item in self.audit["legendary_classification_evidence"]:
            if not item["production_eligibility"].startswith("exclude_"):
                continue
            self.assertEqual(item["final_status"], "PASS_EXACT")
            self.assertTrue(any(source.get("positive_classification_edge") is True
                                for source in item["native_evidence_sources"]))
            catalogue_tool.validate_legendary_classification_evidence(item)

        invalid = copy.deepcopy(next(
            item for item in self.audit["legendary_classification_evidence"]
            if item["production_eligibility"].startswith("exclude_")))
        invalid["native_evidence_sources"] = [{
            "source_file": "quests.dcb",
            "evidence_role": "region_summary_absence",
            "positive_classification_edge": False,
        }]
        with self.assertRaises(ValueError):
            catalogue_tool.validate_legendary_classification_evidence(invalid)

    def test_unresolved_legendary_rows_stay_unresolved_and_not_excluded(self):
        evidence = self.audit["legendary_classification_evidence"]
        unresolved = [item for item in evidence
                      if item["classification"] == "unresolved_nontracked"]
        self.assertEqual(len(unresolved), 2)
        self.assertTrue(all(item["production_eligibility"] == "unresolved"
                            and item["final_status"] == "BLOCKED_EXACT_REASON_UNKNOWN"
                            for item in unresolved))

    def test_region_summary_absence_or_wad_name_alone_cannot_classify_legendary(self):
        sample = copy.deepcopy(next(
            row for row in self.rows
            if row["family"] == "legendary_chest"
            and row["native_classification"] == "unresolved_nontracked"))
        sample["source"]["wad"] = "msp100_base.wad"
        sample["progression"]["parent_quest"] = None
        sample["native"]["placement_object_name"] = "gochest_legendary_tier3_test_1"
        sample["native"]["attribute_values"] = ["Legendary"]
        sample["source"]["transform_chain"] = [{
            "name": "gomsp100_ents", "offset": "0x10", "record_id": "11" * 16,
        }]
        result = catalogue_tool.classify_legendary_row(sample)
        self.assertEqual(result["classification"], "unresolved_nontracked")
        self.assertEqual(result["production_eligibility"], "unresolved")

    def test_legendary_classification_has_no_nearest_distance_or_count_input(self):
        source = Path(catalogue_tool.__file__).read_text(encoding="utf-8")
        block = source[source.index("def classify_legendary_row"):
                       source.index("def build_legendary_classification_evidence")]
        for forbidden in ("nearest", "distance", "target_count", "math.dist"):
            self.assertNotIn(forbidden, block.lower())

    def test_ship_head_physical_identity_and_carrier_paths_are_exact(self):
        rows = [row for row in self.rows
                if row["family"] == "artefact" and row["subtype"] == "Ship Head"]
        self.assertEqual(len(rows), 9)
        self.assertEqual(len({row["native"]["instance_guid"] for row in rows}), 9)
        self.assertEqual(
            {number for row in rows for number in row["native"]["numbered_object_evidence"]},
            set(range(1, 10)))
        for row in rows:
            paths = row["native"]["carrier_transform_paths"]
            self.assertTrue(paths)
            self.assertTrue(all(path["physical_instance_guid"] == row["native"]["instance_guid"]
                                for path in paths))
            self.assertEqual(
                row["native"]["state_carrier_guids"],
                sorted({path["state_carrier_guid"] for path in paths}))

    def test_nornir_joins_fail_closed_without_exact_native_binding(self):
        parents = [row for row in self.rows if row["family"] == "nornir_chest"]
        joined = [row for row in parents if row["progression"].get("parent_quest")]
        self.assertEqual(joined, [])
        self.assertTrue(all(
            row["progression"].get("parent_quest_source") not in {
                "unique_region_family_inference",
                "region_or_count_inference",
                "nearest_record_logic",
                "wad_prefix_only_inference",
                "exact_native_level_zone_ownership",
            }
            for row in parents))
        unjoined = {row["native"]["instance_guid"]: row for row in parents
                    if not row["progression"].get("parent_quest")}
        self.assertEqual(len(unjoined), 22)
        self.assertTrue({
            "f8548c57-4dc6-7cba-277c-5cb31099648b",
            "6fc8ac79-4c63-bf63-a137-36b7cd3c7f25",
        } <= set(unjoined))
        self.assertEqual(
            self.audit["tyrs_vault_nornir_binding"]["result"],
            "BLOCKED_EXACT_REASON_UNKNOWN")
        self.assertEqual(
            self.audit["helheim_unjoined_nornir"],
            {
                "classification": "level_scripted_untracked_triple_chest_reward",
                "evidence": [
                    "Placement owns HelR100_TripleChest_Callback.",
                    "helr100_docks level script owns same callback and triple-chest encounter names.",
                    "quests.dcb has no Helheim RunicChest target.",
                ],
                "physical_instance_guid": "6fc8ac79-4c63-bf63-a137-36b7cd3c7f25",
                "result": "PASS_EXPLAINED",
                "wad": "helr100_docks.wad",
            })

    def test_every_nornir_parent_has_machine_readable_binding_evidence(self):
        parents = [row for row in self.rows if row["family"] == "nornir_chest"]
        evidence = self.audit["nornir_exact_binding_evidence"]
        self.assertEqual(len(evidence), len(parents))
        self.assertEqual(
            {row["catalogue_id"] for row in evidence},
            {row["catalogue_id"] for row in parents})
        required = {
            "catalogue_id", "physical_instance_guid", "state_carrier_guid",
            "state_carrier_guids",
            "wad", "world_xyz", "proposed_region_summary_parent",
            "native_realm_id", "native_region_id", "native_level_zone_identity",
            "exact_evidence_sources", "evidence_classification", "final_status",
            "physical_object", "source_level_zone", "map_region_ownership",
            "region_summary_target", "completion_state_oracle",
        }
        for row in evidence:
            self.assertTrue(required <= set(row), row["catalogue_id"])
            self.assertEqual(row["state_carrier_guids"], [row["state_carrier_guid"]])
            self.assertIsNone(row["native_level_zone_identity"]["native_zone_identity"])
            self.assertIn(row["final_status"], {
                "PASS_EXACT", "BLOCKED_EXACT_REASON_UNKNOWN"})

    def test_pass_exact_requires_native_reference_chain(self):
        for row in self.audit["nornir_exact_binding_evidence"]:
            if row["final_status"] != "PASS_EXACT":
                continue
            self.assertEqual(row["evidence_classification"],
                             "exact_native_reference_chain")
            self.assertTrue(row["exact_evidence_sources"])
            self.assertTrue(all(source["source_file"] for source in
                                row["exact_evidence_sources"]))
        invalid = {
            "final_status": "PASS_EXACT",
            "evidence_classification": "wad_filename_namespace_only",
            "proposed_region_summary_parent": "RegionSummary_RunicChest_Parent_Alfheim",
            "exact_evidence_sources": [],
        }
        with self.assertRaises(ValueError):
            catalogue_tool.validate_nornir_binding_evidence(invalid, {
                "RegionSummary_RunicChest_Parent_Alfheim": {}})

    def test_right_looking_wad_name_without_native_chain_does_not_join(self):
        quest, source = catalogue_tool.resolve_nornir_parent_binding(
            "alf210_lakedarklh.wad", None, {
                "RegionSummary_RunicChest_Parent_Alfheim": {}})
        self.assertIsNone(quest)
        self.assertIsNone(source)

    def test_count_deficit_does_not_create_nornir_join(self):
        quest, source = catalogue_tool.resolve_nornir_parent_binding(
            "synthetic_right_looking.wad", {
                "final_status": "BLOCKED_EXACT_REASON_UNKNOWN",
                "evidence_classification": "target_count_deficit",
                "proposed_region_summary_parent":
                    "RegionSummary_RunicChest_Parent_TyrsVault",
                "exact_evidence_sources": [],
            }, {"RegionSummary_RunicChest_Parent_TyrsVault": {}})
        self.assertIsNone(quest)
        self.assertIsNone(source)

    def test_exact_native_binding_edge_can_create_join(self):
        target = "RegionSummary_RunicChest_Parent_Alfheim"
        evidence = {
            "final_status": "PASS_EXACT",
            "evidence_classification": "exact_native_reference_chain",
            "proposed_region_summary_parent": target,
            "native_realm_id": "REALM00000000001",
            "native_region_id": "REGION0000000001",
            "exact_evidence_sources": [{
                "source_file": "native-fixture.dcb",
                "evidence_role": "binding_edge",
                "record_offset": "0x10",
            }],
        }
        quest, source = catalogue_tool.resolve_nornir_parent_binding(
            "synthetic.wad", evidence, {target: {
                "realm_id": "REALM00000000001",
                "region_id": "REGION0000000001",
            }})
        self.assertEqual(quest, target)
        self.assertEqual(source, "exact_native_reference_chain")

    def test_nornir_evidence_accounting_and_special_cases(self):
        evidence = self.audit["nornir_exact_binding_evidence"]
        self.assertEqual(self.audit["nornir_accounting"]["exact_joined"], 0)
        self.assertEqual(self.audit["nornir_accounting"]["pass_exact"], 0)
        self.assertEqual(self.audit["nornir_accounting"]["blocked_exact_reason_unknown"], 22)
        cal = next(row for row in evidence if row["wad"] == "cal500_runevault.wad")
        self.assertEqual(cal["final_status"], "BLOCKED_EXACT_REASON_UNKNOWN")
        self.assertEqual(cal["proposed_region_summary_parent"],
                         "RegionSummary_RunicChest_Parent_TyrsVault")
        hel = next(row for row in evidence if row["wad"] == "helr100_docks.wad")
        self.assertEqual(hel["final_status"], "BLOCKED_EXACT_REASON_UNKNOWN")
        self.assertEqual(hel["tracking_classification"],
                         "level_scripted_untracked_triple_chest_reward")
        self.assertIsNone(hel["proposed_region_summary_parent"])

    def test_naked_nornir_exact_allowlist_removed(self):
        source = Path(catalogue_tool.__file__).read_text(encoding="utf-8")
        self.assertNotIn("NORNIR_EXACT_LEVEL_QUESTS", source)
        self.assertNotIn("exact_native_level_zone_ownership", source)

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

    def test_atomic_output_success_and_failure_rollback(self):
        build_root = REPO / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="collectible-output-test-", dir=build_root) as root:
            target = Path(root) / "catalogue.json"
            catalogue_tool.write_atomic(target, "old")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            with mock.patch.object(Path, "replace", side_effect=OSError("injected boundary failure")):
                with self.assertRaises(OSError):
                    catalogue_tool.write_atomic(target, "new")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(root).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
