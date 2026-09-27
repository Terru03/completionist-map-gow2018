"""Check coverage and reject unsafe completion bindings."""
from copy import deepcopy
import importlib.util
import json
import hashlib
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
GENERATOR = HERE / "build-collectible-completion-bindings.py"


class CompletionBindingsTest(unittest.TestCase):
    def module(self):
        self.assertTrue(GENERATOR.is_file(), "completion binding generator missing")
        spec = importlib.util.spec_from_file_location("completion_binding_test", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_selected_ids_have_one_unknown_binding_each(self):
        mod = self.module()
        rows, _, excluded = mod.builder.definitions()
        data = mod.build(include_proved=False)
        bindings = data["bindings"]
        self.assertEqual({r["catalogue_id"] for r in rows},
                         {b["catalogue_id"] for b in bindings})
        self.assertEqual(len(bindings), 410)
        self.assertEqual(len(excluded), 27)
        for binding in bindings:
            self.assertEqual(binding["status"], "unproved")
            self.assertEqual(binding["instance_keys"], [])
            self.assertIsNone(binding["predicate"])
            self.assertTrue(binding["source_wad"])
            self.assertTrue(binding["evidence"]["source_paths"])
        self.assertEqual(data["unproved_state"], "unknown")

    def test_duplicate_or_missing_binding_rejected(self):
        mod = self.module()
        data = mod.build()
        for rows in (data["bindings"] + [data["bindings"][0]], data["bindings"][:-1]):
            with self.subTest(count=len(rows)), self.assertRaises(ValueError):
                mod.validate(rows, mod.builder.definitions()[0])

    def test_archived_chests_keep_exact_nested_identities(self):
        data = self.module().build()
        proved = [r for r in data["bindings"] if r["status"] == "proved" and r['family'] == 'legendary_chest']
        self.assertEqual(len(proved), 33)
        self.assertTrue(all(r["predicate"] == {"field": "state", "type": "number", "equals": 4}
                            for r in proved))
        nested = next(r for r in proved if r["catalogue_id"] ==
                      "legendary_chest_ace99ef5472abcbac29bd2b396a3fdf3")
        self.assertIn(".1a10ffb6-4e57-7e17-2604-f4b11ae71140.", nested["instance_keys"][0])
        self.assertEqual(len(data["contract"]), 64)

    def test_all_artefacts_bind_acquired_without_changing_chest_predicate(self):
        mod = self.module()
        data = mod.build()
        artefacts = [r for r in data['bindings'] if r['family'] == 'artefact']
        replay = {r['catalogue_id']: r['state'] for r in mod.artefact_saved_state.replay()}
        self.assertEqual(len(artefacts), 45)
        for row in artefacts:
            self.assertEqual(row['status'], 'proved')
            self.assertEqual(row['predicate'], {'field': 'state', 'type': 'number', 'equals': 3})
            self.assertEqual(len(row['instance_keys']), 1)
            self.assertEqual(row['evidence']['fixture_state'], replay[row['catalogue_id']])
        self.assertEqual(sum(state == 3 for state in replay.values()), 38)
        self.assertEqual(sum(r['status'] == 'proved' for r in data['bindings']), 78)

    def test_proved_binding_needs_keys_predicate_and_evidence(self):
        mod = self.module()
        for field, value in (("instance_keys", []), ("predicate", None), ("evidence", {})):
            data = mod.build()["bindings"]
            data[0].update(status="proved", instance_keys=["exact-owner"],
                           predicate={"field": "state", "equals": 4}, evidence={"proof": "fixture"})
            data[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                mod.validate(data, mod.builder.definitions()[0])

    def test_duplicate_and_conflicting_owner_keys_rejected(self):
        mod = self.module()
        for within_row in (True, False):
            data = mod.build()["bindings"]
            data[0].update(status="proved", instance_keys=["exact-owner"],
                           predicate={"field": "state", "equals": 4}, evidence={"proof": "fixture"})
            if within_row:
                data[0]["instance_keys"].append("exact-owner")
            else:
                data[1].update(status="proved", source_wad=data[0]["source_wad"],
                               instance_keys=["exact-owner"], predicate={"field": "state", "equals": 1},
                               evidence={"proof": "fixture"})
            with self.subTest(within_row=within_row), self.assertRaises(ValueError):
                mod.validate(data, mod.builder.definitions()[0])

    def test_unproved_cannot_carry_active_predicate_or_keys(self):
        mod = self.module()
        first_unproved = next(i for i, row in enumerate(mod.build()["bindings"])
                              if row["status"] == "unproved")
        for field, value in (("instance_keys", ["record-id-only"]),
                             ("predicate", {"field": "state", "equals": 4}),
                             ("status", "collected")):
            data = mod.build()["bindings"]
            data[first_unproved][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                mod.validate(data, mod.builder.definitions()[0])

    def test_native_generator_rejects_contract_tamper_and_duplicate_identity(self):
        spec = importlib.util.spec_from_file_location("native_collectible_generator",
            HERE.parents[1] / "native/raven-authority-bridge/tools/generate_collectible_data.py")
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        original = self.module().build()
        self.assertIn("kCollectibleCount = 410", native.render(original))
        for defect in ("contract", "identity", "status", "fixture_state"):
            data = deepcopy(original)
            if defect == "contract":
                data["contract"] = "f" * 64
            elif defect == "status":
                data["bindings"][0]["status"] = "invalid"
            elif defect == "fixture_state":
                next(row for row in data["bindings"] if row["family"] == "artefact")["evidence"]["fixture_state"] = 4
            else:
                active = [r for r in data["bindings"] if r["status"] == "proved"]
                active[1]["native_identity"] = deepcopy(active[0]["native_identity"])
                active[1]["source_wad"] = active[0]["source_wad"]
                contract_rows = [{k:r.get(k) for k in ("catalogue_id","source_wad",
                    "instance_keys","predicate","native_identity")} for r in data["bindings"]]
                data["contract"] = hashlib.sha256(json.dumps(contract_rows,sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                native.render(data)

    def test_candidate_keys_remain_evidence_only(self):
        mod = self.module()
        data = mod.build()
        by_id = {b["catalogue_id"]: b for b in data["bindings"]}
        lore = by_id["lore_marker_peak180enttochimneylhwadcc54f8d5e69b0945a3674ddc65276412"]
        self.assertTrue(lore["evidence"]["candidate_instance_keys"])
        self.assertEqual(lore["instance_keys"], [])
        shrine = next(b for b in data["bindings"] if
                      b["evidence"].get("placement_name") == "gotriptych_thamur")
        self.assertEqual({p["wad"] for p in shrine["evidence"]["source_paths"]},
                         {"stn105_chiselsite.wad", "stn905_chiselsite.wad"})


if __name__ == "__main__":
    unittest.main()
