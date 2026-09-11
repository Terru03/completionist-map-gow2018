"""Offline acceptance checks for Raven compass lifecycle v3.3."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location(
        "uid_routing_v33", HERE / "build-raven-uid-compass-lifecycle-v3.3.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RavenUidCompassLifecycleV33Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load()
        cls.root = Path(
            os.environ.get(
                "COMPLETIONIST_RAVEN_ROOT",
                "G:/SteamLibrary/steamapps/common/GodOfWar",
            )
        )
        cls.files, cls.proof = cls.p.generate(cls.root)
        cls.shared_files, cls.shared_proof = cls.p.shared.generate(cls.root)
        cls.routing = cls.p.ROUTING_PATH.read_text(encoding="utf-8")
        cls.twin_hook = cls.p.TWIN_HOOK_PATH.read_text(encoding="utf-8")

    def test_scope_is_exact_shared_loader_four_files(self):
        self.assertEqual(set(self.files), set(self.shared_files) | {self.p.EVENTS})
        self.assertEqual(len(self.files), 5)
        self.assertNotIn("exec/wad/pc_le/r_ui.wad", self.files)
        self.assertNotIn("exec/dc/pc_le/compassgraph.dcb", self.files)

    def test_binary_candidate_is_byte_identical_to_shared_loader_map_base(self):
        for rel in (self.p.shared.MASTER, self.p.shared.COORDS, self.p.shared.UI):
            self.assertEqual(self.files[rel], self.shared_files[rel])

    def test_lua_is_append_only_on_shared_loader_candidate(self):
        before = self.shared_files[self.p.LUA]
        after = self.files[self.p.LUA]
        self.assertTrue(after.startswith(before))
        self.assertEqual(after[len(before):], self.p.routing_bytes())

    def test_two_native_marker_uids_remain_distinct_and_share_map_loader(self):
        ids = self.proof["identities"]
        self.assertNotEqual(ids["raven_uid"], ids["twin_uid"])
        self.assertEqual(ids["raven_uid"], "E15E6BC82AE2773E")
        self.assertEqual(ids["twin_uid"], "2F530E7F3F156D90")
        self.assertEqual(ids["shared_map_loader"], "goMapIconCompletionistRaven")
        self.assertEqual(ids["compass_class"], "CompletionistRaven")

    def test_selection_captures_exact_collision_table_object_references(self):
        required = (
            "function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)",
            "collision == self.completionistSharedLoaderTwinGO",
            "collision == self.completionistMapV100MapIconGO",
            "completionistMapV104RavenSelection",
            "SELECT_CANDIDATE",
            "SELECT_ARM",
            "SELECT_DISARM",
            "SELECT_CONSUME",
        )
        for token in required:
            self.assertIn(token, self.routing)

    def test_prompt_ownership_disambiguates_same_twin_id_from_different_stock_id(self):
        contract = self.proof["routing_contract"]
        self.assertEqual(
            contract["real_prompt_ownership"],
            "show=true, real exact candidate, completionistMapV100Selected=true, "
            "Nornir selections nil, currMarkerID=nil",
        )
        self.assertEqual(
            contract["twin_prompt_ownership"],
            "show=true, exact Twin object candidate, currMarkerID nonnil, and "
            "tostring(currMarkerID)==selected.IdString",
        )
        self.assertFalse(contract["curr_marker_id_alone_infers_twin"])
        self.assertIn("exactTwinCollisionSelection", self.routing)
        self.assertIn("currentMarkerDiffersFromSelection", self.routing)
        self.assertIn("tostring(self.currMarkerID) == selected.IdString", self.routing)
        self.assertIn("tostring(self.currMarkerID) ~= selected.IdString", self.routing)

    def test_native_marker_identity_is_looked_up_after_object_disambiguation(self):
        self.assertIn("game.Map.GetMarkerInfo(name)", self.routing)
        self.assertIn("Id = info.Id", self.routing)
        self.assertIn("IdString = tostring(info.Id)", self.routing)

    def test_selected_native_name_is_routed_to_proven_custom_compass_class(self):
        self.assertIn("game.Compass.ShowMarker(selected.Name, ravenClass)", self.routing)
        self.assertIn("game.Compass.HideMarker(selected.Name)", self.routing)
        self.assertIn("game.Compass.FindMarkersByIconClass({ravenClass})", self.routing)

    def test_single_active_replacement_paths_are_present(self):
        self.assertIn('hideCustomTargets("raven_uid_replace", selected.IdString)', self.routing)
        self.assertIn('hideStockTargets("raven_uid_replace")', self.routing)
        self.assertIn('STOCK_REPLACE_TWIN', self.routing)
        self.assertIn('STOCK_REPLACE_TWIN_REFUSED', self.routing)
        self.assertEqual(self.proof["expected_runtime_matrix"]["maximum_active_user_target"], 1)
        self.assertEqual(
            self.proof["routing_contract"]["replacement_hide_failure_policy"],
            "refuse replacement; never broaden hide scope",
        )
        self.assertIn("return allHidden, hidden", self.routing)

    def test_completion_is_observe_only_and_clears_only_original_route(self):
        contract = self.proof["routing_contract"]
        self.assertTrue(contract["lifecycle_observation"])
        self.assertEqual(contract["completion_oracle"], "native precisionchallenge ravenKilled after native callback")
        self.assertEqual(contract["completion_cleanup_scope"], "exact real Raven CompletionistRaven target only")
        self.assertEqual(contract["gameplay_cleanup_owner"], "persistent precisionchallenge Raven lifecycle")
        self.assertFalse(contract["gameplay_mapmenu_dependency"])
        self.assertFalse(contract["lifecycle_progression_mutation"])
        self.assertFalse(contract["synthetic_progression_writes"])
        self.assertIn("CompletionistMapV100_IsRavenCollected", self.routing)
        self.assertIn("game.Compass.HideMarker(ravenName)", self.routing)
        self.assertIn("twinTouched=false progressionWrites=false", self.routing)
        for token in (
            "SetMarkerState",
            "challengeComplete",
            "OPENED",
            "SetToken",
            "SetProgress",
            "CompletionistMapV100_PublishTargetState",
        ):
            self.assertNotIn(token, self.routing)

    def test_twin_lifetime_no_longer_requires_live_original_ui_object(self):
        contract = self.proof["routing_contract"]
        self.assertTrue(contract["twin_lifetime_independent_of_original_ui_object"])
        self.assertIn("local originalPresent = original ~= nil", self.twin_hook)
        self.assertIn('Map.CreateMarkerIcon(info.Id, region, "")', self.twin_hook)
        self.assertIn("originalPresent=false", self.twin_hook)
        self.assertNotIn("SKIP reason=original_raven_absent", self.twin_hook)

    def test_no_resource_identity_expansion(self):
        contract = self.proof["routing_contract"]
        self.assertFalse(contract["new_wad_resource_identity"])
        self.assertFalse(contract["compassgraph_changed"])
        self.assertFalse(self.proof["map_title_behavior_changed"])

    def test_gameplay_native_prefix_unchanged(self):
        source = (self.root/self.p.EVENTS).read_bytes()
        self.assertEqual(
            self.files[self.p.EVENTS],
            source + b"\n" + self.p.canonical_lua_bytes(self.p.EVENTS_PATH),
        )
        self.assertFalse(self.proof["routing_contract"]["polling"])
        self.assertTrue(self.proof["routing_contract"]["completion_latch_reversible"])

    def test_gameplay_lifecycle_hook_is_byte_identical_to_runtime_proven_v31(self):
        self.assertEqual(
            self.p.canonical_lua_bytes(self.p.EVENTS_PATH),
            self.p.canonical_lua_bytes(self.p.EVENTS_V31_PATH),
        )
        self.assertTrue(self.proof["routing_contract"]["gameplay_hook_byte_identical_to_v31"])
        self.assertEqual(
            self.p.canonical_lua_bytes(self.p.EVENTS_PATH),
            self.p.canonical_lua_bytes(self.p.EVENTS_V32_PATH),
        )
        self.assertTrue(self.proof["routing_contract"]["gameplay_hook_byte_identical_to_v32"])
        self.assertEqual(
            self.proof["files"][self.p.EVENTS]["sha256"],
            "61e6bc8efe1fcb9b2a6e796aa86ce9a5f74fc18e97229aae7cc52b652a565800",
        )

    def test_authored_lua_line_endings_are_canonical_across_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            crlf = Path(tmp) / "hook.lua"
            crlf.write_bytes(b"line1\r\nline2\r\n")
            self.assertEqual(self.p.canonical_lua_bytes(crlf), b"line1\nline2\n")
        self.assertNotIn(b"\r", self.p.routing_bytes())
        self.assertNotIn(b"\r", self.p.shared_hook_bytes())
        self.assertNotIn(b"\r", self.p.canonical_lua_bytes(self.p.EVENTS_PATH))

    def test_full_candidate_is_identical_from_lf_or_crlf_authored_lua(self):
        originals = {
            "ROUTING_PATH": self.p.ROUTING_PATH,
            "TWIN_HOOK_PATH": self.p.TWIN_HOOK_PATH,
            "EVENTS_PATH": self.p.EVENTS_PATH,
        }
        texts = {
            name: path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
            for name, path in originals.items()
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name, text in texts.items():
                    path = root / f"{name}.lua"
                    path.write_bytes(text.encode("utf-8"))
                    setattr(self.p, name, path)
                lf_files, lf_proof = self.p.generate(self.root)
                for name, text in texts.items():
                    getattr(self.p, name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
                crlf_files, crlf_proof = self.p.generate(self.root)
                self.assertEqual(lf_files, crlf_files)
                self.assertEqual(lf_proof, crlf_proof)
        finally:
            for name, path in originals.items():
                setattr(self.p, name, path)

    def test_gameplay_cleanup_is_exact_and_mapmenu_independent(self):
        events = self.p.EVENTS_PATH.read_text(encoding="utf-8")
        self.assertIn("game.Map.GetMarkerInfo(ravenName)", events)
        self.assertIn("game.Compass.FindMarkersByIconClass({ravenClass})", events)
        self.assertIn("game.Compass.HideMarker(ravenName)", events)
        self.assertIn("retryLimit = 20", events)
        self.assertIn("SCHEDULE_FAILED", events)
        self.assertTrue(self.proof["routing_contract"]["event_retry_schedule_failure_safe"])
        for token in (
            "CompletionistMapV104ObserveRavenCompletion",
            "CompletionistMapV104UidRavenTrackedName",
            "mapIconCollision",
            "MapOn.Update",
            "util.create_thread",
        ):
            self.assertNotIn(token, events)

    def test_selection_contract_is_ui_lifecycle_bounded(self):
        contract = self.proof["routing_contract"]
        self.assertEqual(
            contract["selection_state_machine"],
            ["none", "candidate-custom", "armed-custom"],
        )
        self.assertIsNone(contract["selection_frame_ttl"])
        self.assertTrue(contract["selection_armed_one_shot"])
        self.assertEqual(
            contract["selection_arm_signal"],
            "visible GetShowOnCompassPrompt with proven real bridge or exact Twin "
            "collision and matching nonnil currMarkerID",
        )
        self.assertEqual(
            contract["confirmed_stock_signal"],
            "currMarkerID nonnil and string-different from exact current custom candidate "
            "Id; action guard repeats exact comparison",
        )
        self.assertEqual(
            contract["incidental_noncustom_collision_policy"],
            "ignore callback alone; defer to prompt owner or prompt availability",
        )
        disarm = set(contract["selection_disarm"])
        self.assertIn("MapOn.ClearIcons", disarm)
        self.assertIn("real Raven completion", disarm)
        self.assertIn("prompt unavailable", disarm)
        self.assertNotIn("new noncustom collision", disarm)
        self.assertNotIn("30 frame expiry", disarm)
        self.assertNotIn("ttl_expired", self.routing)

    def test_deterministic_output(self):
        second, second_proof = self.p.generate(self.root)
        self.assertEqual(self.files, second)
        self.assertEqual(self.proof, second_proof)

    def test_both_complete_candidate_scripts_compile_lua51(self):
        from test_raven_uid_compass_routing_lua import LuaRuntime
        lua = LuaRuntime()
        compile_script = lua.eval('function(s) local f,e=loadstring(s); assert(f,e); return true end')
        for rel in (self.p.LUA, self.p.EVENTS):
            self.assertTrue(compile_script(self.files[rel].decode('utf-8')))

    def test_twin_teardown_and_no_production_destroy_coupling(self):
        self.assertNotIn('CompletionistMapV100_DestroyMapPin =', self.twin_hook)
        self.assertIn('{"SubmenuExit", "Exit", "ClearIcons"}', self.twin_hook)

    def test_lexical_oracle_and_no_unproven_thread(self):
        self.assertNotIn('_G.CompletionistMapV100_IsRavenCollected', self.routing)
        self.assertNotIn('util.create_thread', self.routing)
        self.assertIn('type(state) == "boolean"', self.routing)

if __name__ == "__main__":
    unittest.main()
