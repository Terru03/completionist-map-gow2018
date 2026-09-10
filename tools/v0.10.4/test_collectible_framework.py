#!/usr/bin/env python3
"""Unit and offline integration tests for collectible framework."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FRAMEWORK_PATH = HERE / "collectible_framework.py"
RAVEN_HASHES = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_ui.dcb": "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/dc/pc_le/mapmaster.dcb": "b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f",
    "exec/dc/pc_le/mapcoords.dcb": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
    "exec/dc/pc_le/compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": "67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cf = load("test_collectible_framework_module", FRAMEWORK_PATH)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = cf.load_registry()

    def test_required_collectibles_and_adapter_mapping_exist(self):
        rows = cf.definitions_by_key(self.registry)
        required = {
            "odins_raven", "nornir_chest", "nornir_bell", "nornir_seal",
            "nornir_mechanism", "lore_marker", "artefact", "legendary_chest",
        }
        self.assertTrue(required.issubset(rows))
        self.assertEqual(rows["odins_raven"]["lifecycle"]["adapter"], "killable_collectible")
        self.assertEqual(rows["legendary_chest"]["lifecycle"]["adapter"], "opened_chest")
        self.assertEqual(rows["artefact"]["lifecycle"]["adapter"], "pickup_collectible")
        self.assertEqual(rows["lore_marker"]["lifecycle"]["adapter"], "interact_read_collectible")
        for key in ("nornir_bell", "nornir_seal", "nornir_mechanism"):
            self.assertEqual(rows[key]["parent_collectible_key"], "nornir_chest")
            self.assertEqual(rows[key]["lifecycle"]["adapter"], "child_puzzle_element")

    def test_unknown_runtime_facts_stay_explicit(self):
        rows = cf.definitions_by_key(self.registry)
        for key in ("nornir_bell", "nornir_seal", "nornir_mechanism",
                    "lore_marker", "artefact", "legendary_chest"):
            self.assertFalse(rows[key]["build"]["enabled"])
            self.assertTrue(rows[key]["unresolved"])
            self.assertIsNone(rows[key]["native_discovery"]["marker_uid"])

    def test_raven_is_frozen_not_framework_build_input(self):
        raven = cf.definition_for(self.registry, "odins_raven")
        self.assertEqual(raven["status"], "production_frozen")
        self.assertFalse(raven["build"]["enabled"])

    def test_failed_nornir_candidates_are_not_build_inputs(self):
        nornir = cf.definition_for(self.registry, "nornir_chest")
        self.assertEqual(nornir["status"], "historical_failed")
        self.assertFalse(nornir["build"]["enabled"])

    def test_synthetic_resolution_is_deterministic(self):
        again = cf.load_registry()
        left = cf.definition_for(self.registry, "framework_probe")
        right = cf.definition_for(again, "framework_probe")
        self.assertEqual(left, right)
        self.assertEqual(left["resources"]["material"]["qword_0x10"], "1B0989158D4A2908")
        self.assertEqual(left["resources"]["material"]["qword_0x20"], "D595197B0961F689")

    def test_duplicate_resource_name_fails(self):
        bad = copy.deepcopy(self.registry)
        rows = cf.definitions_by_key(bad)
        rows["framework_probe"]["resources"]["material"]["name"] = \
            rows["nornir_chest"]["resources"]["material"]["name"]
        with self.assertRaisesRegex(cf.FrameworkError, "duplicate resource name"):
            cf.validate_registry(bad)

    def test_duplicate_resource_id_fails(self):
        bad = copy.deepcopy(self.registry)
        rows = cf.definitions_by_key(bad)
        rows["framework_probe"]["resources"]["material"]["id"] = \
            rows["nornir_chest"]["resources"]["material"]["id"]
        with self.assertRaisesRegex(cf.FrameworkError, "duplicate resource ID"):
            cf.validate_registry(bad)

    def test_opaque_material_donor_qword_violations_fail(self):
        for field in ("qword_0x10", "qword_0x20"):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.registry)
                cf.definitions_by_key(bad)["framework_probe"]["resources"]["material"][field] = \
                    "0000000000000000"
                with self.assertRaisesRegex(cf.FrameworkError, "opaque material"):
                    cf.validate_registry(bad)

    def test_material_qword_uniqueness_is_not_an_identity_rule(self):
        proof = cf.validate_registry(copy.deepcopy(self.registry))
        self.assertNotIn("material_q10_unique", proof)
        self.assertTrue(proof["opaque_material_fields_preserved_from_donor"])
        self.assertIn("material payload +0x10", proof["opaque_donor_policy"])

    def test_model_group_policy_violation_fails(self):
        bad = copy.deepcopy(self.registry)
        cf.definitions_by_key(bad)["framework_probe"]["model_group_policy"]["map"]["mutate_payload"] = True
        with self.assertRaisesRegex(cf.FrameworkError, "payload mutation forbidden"):
            cf.validate_registry(bad)

    def test_cross_collectible_identity_sets_do_not_alias(self):
        proof = cf.assert_cross_collectible_isolation(
            self.registry, ["odins_raven", "nornir_chest", "framework_probe"])
        self.assertTrue(proof["resource_names_unique"])
        self.assertTrue(proof["resource_ids_unique"])
        self.assertTrue(proof["material_model_prototype_root_ownership_disjoint"])

    def test_reverse_owner_leaks_fail_by_layer(self):
        definition = cf.definition_for(self.registry, "framework_probe")
        resources = definition["resources"]
        valid = {
            "material": [resources["map_model"]["name"], resources["hud_model"]["name"]],
            "diffuse": [resources["material"]["name"]],
            "emissive": [resources["material"]["name"]],
            "map_model": [resources["map_prototype"]["name"]],
            "hud_model": [resources["hud_prototype"]["name"]],
            "map_prototype_payloads": [resources["map_prototype"]["name"], resources["map_root"]["name"]],
            "hud_prototype_payloads": [resources["hud_prototype"]["name"], resources["hud_root"]["name"]],
            "map_root_parent_links": 1,
        }
        for field in ("material", "diffuse", "map_model", "map_prototype_payloads"):
            with self.subTest(field=field):
                bad = copy.deepcopy(valid)
                bad[field].append("foreign_collectible_owner")
                with self.assertRaisesRegex(cf.FrameworkError, "ownership leak"):
                    cf.validate_reverse_ownership(definition, bad)
        bad_root = copy.deepcopy(valid)
        bad_root["map_root_parent_links"] = 2
        with self.assertRaisesRegex(cf.FrameworkError, "map root parent ownership leak"):
            cf.validate_reverse_ownership(definition, bad_root)

    def test_lua_service_has_generic_api_and_no_game_state_writes(self):
        service = (HERE / "completionist-collectible-service.lua").read_text(encoding="utf-8")
        adapters = (HERE / "completionist-collectible-lifecycle-adapters.lua").read_text(encoding="utf-8")
        required = (
            "RegisterCollectible", "PublishState", "ShowMapMarker", "HideMapMarker",
            "AddCompassTarget", "ReplaceCompassTarget", "RemoveCompassTarget",
            "CreateInWorldMarker", "RemoveInWorldMarker", "SetActiveTarget", "Complete",
            "parentCollectibleKey", "suppressed", "activeTarget",
        )
        for token in required:
            self.assertIn(token, service)
        for token in ("KillableCollectible", "OpenedChest", "PickupCollectible",
                      "InteractReadCollectible", "ParentPuzzleCollectible",
                      "ChildPuzzleElement"):
            self.assertIn(token, adapters)
        forbidden = ("Map.ChangeMarkerState", "QuestManager.Set", "SaveGame",
                     "SoftSavePlayerState", "SetProgression")
        for token in forbidden:
            self.assertNotIn(token, service + adapters)


class OfflineBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = Path(os.environ.get(
            "COMPLETIONIST_GAME_ROOT", r"G:\SteamLibrary\steamapps\common\GodOfWar"))
        if not cls.game.is_dir():
            raise unittest.SkipTest(f"offline Raven fixture not found: {cls.game}")
        cls.registry = cf.load_registry()
        cls.wad = (cls.game / "exec/wad/pc_le/r_ui.wad").read_bytes()
        cls.ui = (cls.game / "exec/dc/pc_le/wad_r_ui.dcb").read_bytes()
        cls.perm = (cls.game / "exec/dc/pc_le/wad_r_perm.dcb").read_bytes()
        cls.art = REPO / "build/v0.10.4-nornir-resident-art/offline/nornir-resident-art.json"

    def test_raven_all_golden_file_bytes_stay_exact(self):
        for relative, expected in RAVEN_HASHES.items():
            with self.subTest(relative=relative):
                self.assertEqual(cf.sha_file(self.game / relative), expected)

    def test_raven_resource_ids_and_owner_graph_stay_exact(self):
        logical = load("test_collectible_raven_logical", HERE / "build-raven-ui-logical-clone.py")
        records = logical.parse_wad(self.wad)
        raven = cf.definition_for(self.registry, "odins_raven")
        for role in cf.GROUP_ROLES:
            index, row = cf._one_payload(records, raven["resources"][role]["name"])
            self.assertEqual(row["id"].hex(), raven["resources"][role]["id"])
            self.assertIsNotNone(index)
        map_index, _ = cf._one_payload(records, raven["resources"]["map_model"]["name"])
        hud_index, _ = cf._one_payload(records, raven["resources"]["hud_model"]["name"])
        map_rows = cf._group_rows(logical, records, map_index)
        hud_rows = cf._group_rows(logical, records, hud_index)
        cf._dependency(map_rows, "MG_mapicondock_0", bytes.fromhex(cf.STOCK_MODEL_GROUPS["map"][1]))
        cf._dependency(hud_rows, "MG_boatdock_0", bytes.fromhex(cf.STOCK_MODEL_GROUPS["hud"][1]))

    def test_raven_gopool_rows_stay_exact(self):
        verifier = load("test_collectible_raven_verifier", HERE / "verify-raven-production-state.py")
        proof = verifier.verify_ui_pool(self.game / "exec/dc/pc_le/wad_r_ui.dcb")
        self.assertEqual(proof["map_raven"]["index"], 255)
        self.assertEqual(proof["map_raven"]["capacity"], 1)
        self.assertEqual(proof["raven_hud"]["index"], 256)
        self.assertEqual(proof["raven_hud"]["capacity"], 2)

    def test_retired_nornir_build_paths_fail_closed(self):
        calls = (
            lambda: cf.build_collectible_wad(self.wad, self.registry, "nornir_chest", self.art),
            lambda: cf.build_collectible_gopool(self.ui, self.registry, "nornir_chest"),
            lambda: cf.build_collectible_compass_inworld(self.perm, self.registry, "nornir_chest"),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaisesRegex(cf.FrameworkError, "build disabled"):
                    call()

    def test_synthetic_collectible_uses_same_builder_and_is_deterministic(self):
        first, first_proof = cf.build_collectible_wad(
            self.wad, self.registry, "framework_probe")
        second, second_proof = cf.build_collectible_wad(
            self.wad, cf.load_registry(), "framework_probe")
        self.assertEqual(first, second)
        self.assertEqual(first_proof["candidate_sha256"], second_proof["candidate_sha256"])
        self.assertTrue(first_proof["normalized_to_frozen_raven_exact"])
        self.assertTrue(first_proof["reverse_reference_ownership_valid"])

    def test_synthetic_gopool_is_deterministic(self):
        first, _ = cf.build_collectible_gopool(self.ui, self.registry, "framework_probe")
        second, _ = cf.build_collectible_gopool(self.ui, cf.load_registry(), "framework_probe")
        self.assertEqual(first, second)

    def test_synthetic_compass_inworld_is_deterministic(self):
        first, proof = cf.build_collectible_compass_inworld(
            self.perm, self.registry, "framework_probe")
        second, _ = cf.build_collectible_compass_inworld(
            self.perm, cf.load_registry(), "framework_probe")
        self.assertEqual(first, second)
        self.assertTrue(proof["normalized_to_frozen_raven_exact"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
