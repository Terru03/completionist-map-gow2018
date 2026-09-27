"""Artwork coexistence contracts and real-file transaction recovery."""
import copy
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest import mock
import collectible_family_art as art

installer = art.load("family_art_install_test", art.HERE / "install-collectible-family-art.py")


class FamilyArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((art.BUILD / "probe/report.json").read_text())
        cls.package = art.BUILD / "probe/packages" / cls.report["package_id"] / "game-root"

    def test_new_material_and_texture_identities_do_not_alias_raven(self):
        records = art.logical.parse_wad((self.package / art.WAD).read_bytes())
        spec = art.spec_for("nornir_chest")
        _, raven = art.clone.unique_payload(records, art.RAVEN["material"])
        _, chest = art.clone.unique_payload(records, spec["names"]["material"])
        for offset in (0x10, 0x20):
            self.assertNotEqual(raven["data"][offset:offset + 8], chest["data"][offset:offset + 8])
        links = records[chest["parent"]:art.logical.matching_group_end(records, chest["parent"]) + 1]
        custom = [r for r in links if r["name"].startswith("TX_cm_nornir_chest_")]
        self.assertEqual(len(custom), 2)
        for link in custom:
            _, definition = art.clone.unique_texture(records, link["name"], gpu=False)
            _, gpu = art.clone.unique_texture(records, link["name"], gpu=True)
            self.assertEqual(link["id"], definition["id"])
            self.assertEqual(definition["data"][12:68].split(b"\0")[0].decode(), link["name"])
            self.assertEqual(gpu["id"], art.clone.texture_gpu_id(struct.unpack_from("<Q", definition["data"], 0x9C)[0]))

    def test_all_family_material_keys_are_disjoint(self):
        specs = [art.spec_for(r["family"]) for r in art.all_definitions()]
        specs = {s["family"]: s for s in specs}.values()
        keys = [s[k] for s in specs for k in ("q10", "q20")]
        self.assertEqual(len(keys), 30)
        self.assertEqual(len(keys), len(set(keys)))

    def test_only_chest_binding_changes_and_pool_does_not_grow(self):
        source = art.BUILD / "baseline"
        old = art.stage.marker_snapshot(art.locations.base.parsed((source / art.MASTER).read_bytes(), "mapmaster.dcb"))
        new = art.stage.marker_snapshot(art.locations.base.parsed((self.package / art.MASTER).read_bytes(), "mapmaster.dcb"))
        changes = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(changes), 22)
        self.assertTrue(all(b["icon"] == art.spec_for("nornir_chest")["resource"] for a, b in changes))
        self.assertEqual((source / art.POOL).stat().st_size, (self.package / art.POOL).stat().st_size)
        for name in installer.PRESERVED:
            self.assertEqual(self.report["preserved"][name], art.sha((source / name).read_bytes()))

    def fake_game(self, directory):
        game = directory / "game"
        output = directory / "output"
        shutil.copytree(art.BUILD / "baseline", game)
        shutil.copytree(self.package, output / "packages" / self.report["package_id"] / "game-root")
        (output / "report.json").write_text(json.dumps(self.report))
        return game, output

    def check_baseline(self, game):
        for name, item in self.report["files"].items():
            self.assertEqual(installer.digest_file(game / name), item["before"])
        installer.preserve(self.report, game)

    def test_install_verify_and_exact_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, output = self.fake_game(Path(tmp))
            journal = installer.install(game, output, lambda: None)
            installer.verify(journal, game, output)
            installer.rollback(journal, game, output, lambda: None)
            self.check_baseline(game)

    def test_failed_copy_recovers_every_applied_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, output = self.fake_game(Path(tmp))
            original = installer.io.atomic_copy
            calls = 0
            def fail_third(*args):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("simulated disk failure")
                return original(*args)
            with mock.patch.object(installer.io, "atomic_copy", fail_third):
                with self.assertRaisesRegex(OSError, "simulated"):
                    installer.install(game, output, lambda: None)
            self.check_baseline(game)

    def test_rollback_checks_all_files_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, output = self.fake_game(Path(tmp))
            journal = installer.install(game, output, lambda: None)
            (game / art.MASTER).write_bytes(b"later user change")
            before = {n: installer.digest_file(game / n) for n in self.report["files"]}
            with self.assertRaisesRegex(ValueError, "unrelated edit"):
                installer.rollback(journal, game, output, lambda: None)
            self.assertEqual(before, {n: installer.digest_file(game / n) for n in self.report["files"]})

    def test_candidate_drift_and_running_game_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, output = self.fake_game(Path(tmp))
            def running():
                raise ValueError("God of War is running")
            with self.assertRaisesRegex(ValueError, "running"):
                installer.install(game, output, running)
            candidate = output / "packages" / self.report["package_id"] / "game-root" / art.WAD
            candidate.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "candidate drift"):
                installer.install(game, output, lambda: None)
            self.check_baseline(game)

    def test_historical_pack_drift_is_rejected(self):
        probe = art.load('family_art_probe_test', art.HERE / 'build-collectible-art-probe.py')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'changed.texpack'
            path.write_bytes(b'changed pack')
            with self.assertRaisesRegex(ValueError, 'historical texture pack differs'):
                probe.checked_pack(path, '.texpack')


if __name__ == "__main__":
    unittest.main()
