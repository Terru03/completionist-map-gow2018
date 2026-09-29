"""Unit tests for Compass HUD artwork pipeline for all collectible families."""
from collections import Counter
import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

spec_art = importlib.util.spec_from_file_location("art", HERE / "collectible_family_art.py")
art = importlib.util.module_from_spec(spec_art)
spec_art.loader.exec_module(art)

spec_packed = importlib.util.spec_from_file_location("packed", HERE.parent / "v0.10.4/build-packed-raven-compass-class.py")
p = importlib.util.module_from_spec(spec_packed)
spec_packed.loader.exec_module(p)


class CollectibleHudArtTests(unittest.TestCase):
    def setUp(self):
        self.families = [
            "artefact", "cipher_chest", "coffin", "jotnar_shrine", "legendary_chest",
            "lore_marker", "lore_scroll", "nornir_bell", "nornir_chest", "nornir_mechanism",
            "nornir_seal", "realm_tear", "treasure_dig", "treasure_map", "wooden_chest"
        ]

    def test_hud_names_and_hashes_unique_and_no_collision(self):
        seen_classes = set()
        seen_huds = set()
        for fam in self.families:
            spec = art.spec_for(fam)
            compass_class = spec.get("compass_class")
            hud_resource = spec.get("hud_resource")
            self.assertIsNotNone(compass_class)
            self.assertIsNotNone(hud_resource)
            class_uid = p.name_hash(compass_class)
            hud_hash = p.name_hash(hud_resource)
            self.assertNotIn(class_uid, seen_classes, f"Class collision: {compass_class}")
            self.assertNotIn(hud_hash, seen_huds, f"HUD collision: {hud_resource}")
            seen_classes.add(class_uid)
            seen_huds.add(hud_hash)
        self.assertEqual(len(seen_classes), 15)
        self.assertEqual(len(seen_huds), 15)

    def test_build_perm_inserts_15_classes_and_inverses_exactly(self):
        perm_path = art.BUILD / "all-types/baseline" / art.PERM
        if not perm_path.exists():
            perm_path = art.locations.GAME / art.PERM
        raw = perm_path.read_bytes()
        specs = [art.spec_for(fam) for fam in self.families]
        candidate, proof = art.build_perm(raw, specs)
        self.assertTrue(proof["exact_inverse"])
        self.assertEqual(proof["added_classes"], 15)

        chunks = p.parse_chunks(candidate)
        out_data = bytes(p.one(chunks, 12)["payload"])
        _, out_exports, _ = p.parse_exports(p.one(chunks, 13)["payload"])
        by_name = {e["name"]: e for e in out_exports}

        for fam in self.families:
            spec = art.spec_for(fam)
            cname = spec["compass_class"]
            self.assertIn(cname, by_name)
            exp = by_name[cname]
            self.assertEqual(exp["type_id"], 0x11E)
            rec = out_data[exp["root"]:exp["root"] + 0x20]
            icon_hash = struct.unpack_from("<Q", rec, 0)[0]
            self.assertEqual(icon_hash, p.name_hash(spec["hud_resource"]))

        # Verify CompletionistRaven has custom HUD and matches side_inworld carrier
        self.assertIn("CompletionistRaven", by_name)
        raven_exp = by_name["CompletionistRaven"]
        raven_rec = out_data[raven_exp["root"]:raven_exp["root"] + 0x20]
        r_hud, _, r_inworld, _ = struct.unpack("<QQQI", raven_rec[:28])
        self.assertEqual(r_hud, p.name_hash("goCompletionistRavenHUD"))
        side_exp = by_name["SIDE"]
        side_rec = out_data[side_exp["root"]:side_exp["root"] + 0x20]
        _, _, s_inworld, _ = struct.unpack("<QQQI", side_rec[:28])
        self.assertEqual(r_inworld, s_inworld)

    def test_lua_has_exact_mapping_for_all_15_families(self):
        lua_text = (HERE / "collectible-location-map.lua").read_text(encoding="utf-8")
        for fam in self.families:
            spec = art.spec_for(fam)
            self.assertIn(f'["{fam}"] = "{spec["compass_class"]}"', lua_text)


if __name__ == "__main__":
    unittest.main()
