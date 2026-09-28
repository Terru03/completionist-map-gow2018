"""Check compiled family art and its exact map bindings."""
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

import collectible_family_art as art
import collectible_art_textures as textures
installer = art.load('all_family_art_installer_tests', art.HERE / 'install-collectible-family-art.py')


class AllFamilyArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = art.BUILD / 'all-types'
        cls.report = json.loads((cls.output / 'report.json').read_text())
        cls.package = cls.output / 'packages' / cls.report['package_id'] / 'game-root'

    def test_each_type_uses_its_own_source_and_texture_bytes(self):
        rows = self.report['proof']['textures']['families']
        self.assertEqual(set(rows), {r['family'] for r in art.all_definitions()})
        self.assertEqual(len(rows), 15)
        for role in ('diffuse', 'emissive'):
            self.assertEqual(len({r[role]['resident_sha256'] for r in rows.values()}), 15)
            self.assertEqual(len({r[role]['file_hash'] for r in rows.values()}), 15)
            self.assertEqual(len({r[role]['user_hash'] for r in rows.values()}), 15)
        for family, row in rows.items():
            self.assertEqual(row['source_sha256'], art.sha((textures.ASSETS / textures.FAMILY_PNG[family]).read_bytes()))
        self.assertEqual(textures.FAMILY_PNG['treasure_dig'], 'buried_treasure.png')

    def test_distinct_chains_reach_correct_texture_and_keep_raven(self):
        old = art.logical.parse_wad((self.output / 'baseline' / art.WAD).read_bytes())
        new = art.logical.parse_wad((self.package / art.WAD).read_bytes())
        material_keys, texture_keys = set(), set()
        for name in art.RAVEN.values():
            before = [art.logical.record_bytes(r) for r in old if r['name'] == name]
            after = [art.logical.record_bytes(r) for r in new if r['name'] == name]
            self.assertTrue(before, name)
            self.assertEqual(before, after, name)
        for family, row in self.report['proof']['textures']['families'].items():
            spec = art.spec_for(family)
            targets = {role: art.clone.unique_payload(new, spec['names'][role])[1] for role in art.MAP_ROLES}
            for role, dependency in (('map_proto', 'map_model'), ('map_model', 'material')):
                target = targets[role]
                group = new[target['parent']:art.logical.matching_group_end(new, target['parent']) + 1]
                self.assertEqual(sum(r['name'] == spec['names'][dependency] and
                                     r['id'] == spec['ids'][dependency] for r in group), 1)
            self.assertIn(spec['ids']['map_proto'], targets['map_root']['data'])
            self.assertEqual(sum(r['kind'] == 1 and not r['data'] and r['name'] == spec['names']['map_root']
                                 and r['id'] == spec['ids']['map_root'] for r in new), 1)
            for role, target in targets.items():
                group = new[target['parent']:art.logical.matching_group_end(new, target['parent']) + 1]
                for other in art.MAP_ROLES:
                    self.assertFalse(any(r['name'] == art.RAVEN[other] for r in group))
            _, material = art.clone.unique_payload(new, spec['names']['material'])
            group = new[material['parent']:art.logical.matching_group_end(new, material['parent']) + 1]
            for offset in (0x10, 0x20):
                key = struct.unpack_from('<Q', material['data'], offset)[0]
                self.assertNotIn(key, material_keys)
                material_keys.add(key)
            for role in ('diffuse', 'emissive'):
                name = row[role]['name']
                _, definition = art.clone.unique_texture(new, name, gpu=False)
                _, gpu = art.clone.unique_texture(new, name, gpu=True)
                self.assertTrue(any(r['name'] == name and r['id'] == definition['id'] for r in group))
                self.assertEqual(art.sha(gpu['data']), row[role]['resident_sha256'])
                self.assertEqual(definition['data'][12:68].split(b'\0')[0].decode(), name)
                self.assertEqual(gpu['id'], art.clone.texture_gpu_id(row[role]['user_hash']))
                for key in (definition['id'], gpu['id']):
                    self.assertNotIn(key, texture_keys)
                    texture_keys.add(key)

    def test_pack_toc_gnf_and_wad_share_only_the_right_keys(self):
        pack = (self.package / 'exec/patch/pc_le' / (textures.PACK + '.texpack')).read_bytes()
        toc = (self.package / 'exec/patch/pc_le' / (textures.PACK + '.texpack.toc')).read_bytes()
        entries = textures.binding.parse_texpack_entries(pack)
        self.assertEqual(entries, textures.binding.parse_texpack_entries(toc))
        desired = {row[role]['file_hash']: row[role]['user_hash']
                   for row in self.report['proof']['textures']['families'].values()
                   for role in ('diffuse', 'emissive')}
        self.assertEqual({r['file_hash']: r['user_hash'] for r in entries}, desired)
        self.assertEqual(textures.bind_user_hashes(pack, toc, desired), (pack, toc))
        bad = bytearray(pack)
        block = struct.unpack_from('<I', pack, entries[0]['block_info_off'])[0] << 4
        bad[block + 0x48] ^= 1
        with self.assertRaisesRegex(ValueError, 'GNF user hash'):
            textures.bind_user_hashes(bytes(bad), toc, desired)
        bad_toc = bytearray(toc)
        bad_toc[entries[0]['entry_offset'] + 8] ^= 1
        with self.assertRaisesRegex(ValueError, 'pack/TOC'):
            textures.bind_user_hashes(pack, bytes(bad_toc), desired)

    def test_all_498_bindings_change_only_icon_resource(self):
        before = art.stage.marker_snapshot(art.locations.base.parsed(
            (self.output / 'baseline' / art.MASTER).read_bytes(), 'mapmaster.dcb'))
        after = art.stage.marker_snapshot(art.locations.base.parsed(
            (self.package / art.MASTER).read_bytes(), 'mapmaster.dcb'))
        defs = {r['marker']['uid']: r for r in art.all_definitions()}
        self.assertEqual(len(defs), 498)
        expected = [{**r, 'icon': art.spec_for(defs[r['uid']]['family'])['resource']}
                    if r['uid'] in defs else r for r in before]
        self.assertEqual(after, expected)
        self.assertEqual(self.report['proof'][art.POOL]['added_physics_objects'], 0)
        self.assertEqual(self.report['proof'][art.POOL]['reassigned'], 498 + 15)
        self.assertEqual(self.report['proof'][art.POOL]['hud_slots'], 15)
        self.assertTrue(self.report['proof'][art.PERM]['exact_inverse'])
        self.assertEqual(self.report['proof'][art.PERM]['added_classes'], 15)

    def test_completion_files_pinned_and_not_written(self):
        self.assertEqual(set(self.report['preserved']), textures.PRESERVED)
        self.assertEqual(len(self.report['preserved']), len(textures.PRESERVED))
        for name, value in self.report['preserved'].items():
            self.assertEqual(art.sha((self.output / 'baseline' / name).read_bytes()), value)
            self.assertFalse((self.package / name).exists())
        self.assertTrue(self.report['proof']['two_compositions_equal'])
        self.assertFalse(self.report['runtime_coexistence_verified'])

    def fake_game(self, root):
        game, output = root / 'game', root / 'output'
        shutil.copytree(self.output / 'baseline', game)
        shutil.copytree(self.package.parent, output / 'packages' / self.report['package_id'])
        (output / 'report.json').write_text(json.dumps(self.report))
        return game, output

    def assert_restored(self, game):
        for name, hashes in self.report['files'].items():
            self.assertEqual(installer.digest_file(game / name), hashes['before'], name)
        installer.preserve(self.report, game)

    def test_full_package_restores_current_completion_without_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            game, output = self.fake_game(Path(temp))
            journal = installer.install(game, output, lambda: None)
            installer.verify(journal, game, output)
            shutil.rmtree(output / 'packages')
            (output / 'report.json').unlink()
            installer.rollback(journal, game, output, lambda: None)
            installer.rollback(journal, game, output, lambda: None)
            self.assert_restored(game)

    def test_failure_after_replacing_wad_restores_all_files(self):
        with tempfile.TemporaryDirectory() as temp:
            game, output = self.fake_game(Path(temp))
            original = installer.io.atomic_copy
            def fail_after_write(source, destination, after, before):
                original(source, destination, after, before)
                if 'packages' in source.parts and destination.name == 'r_ui.wad':
                    raise OSError('after WAD replace')
            with patch.object(installer.io, 'atomic_copy', fail_after_write), self.assertRaisesRegex(OSError, 'after WAD'):
                installer.install(game, output, lambda: None)
            self.assert_restored(game)

    def test_invalid_pair_and_immutable_report_refused_before_backup(self):
        data = json.loads(json.dumps(self.report))
        toc = 'exec/patch/pc_le/' + textures.PACK + '.texpack.toc'
        data['files'][toc.replace('.texpack.toc', '_probe.texpack')] = data['files'].pop(toc)
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            installer.validate(data)
        with tempfile.TemporaryDirectory() as temp:
            game, output = self.fake_game(Path(temp))
            (output / 'packages' / self.report['package_id'] / 'report.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'immutable art report'):
                installer.install(game, output, lambda: None)
            self.assertFalse((output / 'backups').exists())
            self.assert_restored(game)

    def test_compiled_diffuse_has_transparent_margin_and_visible_glyph(self):
        from PIL import Image
        import numpy as np
        work, compiled = textures.compile_textures(self.output, self.report['source_inputs'])
        for family, row in compiled['families'].items():
            name = Path(row['source']).stem + '.dds'
            with Image.open(work / 'dds/diffuse' / name) as image:
                self.assertEqual(image.size, (148, 148))
                self.assertEqual(image.mode, 'RGBA')
                alpha = image.getchannel('A')
                self.assertEqual(alpha.getextrema(), (0, 255), family)
                for corner in ((0, 0), (147, 0), (0, 147), (147, 147)):
                    self.assertEqual(image.getpixel(corner)[3], 0, f'{family} corner {corner}')
                arr = np.array(image)
                rgb_max = np.max(arr[:, :, :3], axis=2)
                alpha_arr = arr[:, :, 3]
                dark_fg = np.sum((alpha_arr > 200) & (rgb_max < 120))
                self.assertGreater(dark_fg, 50, f'{family} dark contour preserved')


if __name__ == '__main__':
    unittest.main()
