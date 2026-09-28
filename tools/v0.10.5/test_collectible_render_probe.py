"""Binary graph, scope and recovery checks for the two-family rendering test."""
from collections import Counter
import copy
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

import collectible_family_art as art
import collectible_art_textures as textures

builder = art.load('render_probe_builder_tests', art.HERE / 'build-collectible-render-probe.py')
installer = art.load('render_probe_installer_tests', art.HERE / 'install-collectible-family-art.py')


def payload(records, name):
    return art.clone.unique_payload(records, name)[1]


def dependencies(records, target):
    return [r for r in records[target['parent']:art.logical.matching_group_end(records, target['parent']) + 1]
            if r['kind'] == 1 and not r['data']]


class RenderProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = builder.OUTPUT
        cls.report = textures.read_json(cls.output / 'report.json')
        cls.package = cls.output / 'packages' / cls.report['package_id'] / 'game-root'
        cls.source = (cls.output / 'baseline' / art.WAD).read_bytes()
        cls.raw = (cls.package / art.WAD).read_bytes()
        cls.before = art.logical.parse_wad(cls.source)
        cls.after = art.logical.parse_wad(cls.raw)
        cls.families = []
        for family, row in cls.report['proof']['textures']['families'].items():
            data = {}
            for role in ('diffuse', 'emissive'):
                data[role] = {k: row[role][k] for k in ('name', 'file_hash', 'user_hash')}
                data[role]['resident'] = bytes(art.clone.unique_texture(cls.after, row[role]['name'], gpu=True)[1]['data'])
            cls.families.append((art.spec_for(family, include_hud=False), data))

    def test_each_model_and_material_resolve_private_render_resources(self):
        known_ids = {r['id'] for r in self.before}
        known_names = {r['name'].lower() for r in self.before}
        for spec, _ in self.families:
            for role, owner in (('model_group', 'map_model'), ('pixel_shader', 'material')):
                links = dependencies(self.after, payload(self.after, spec['names'][owner]))
                name = ('MG_cmf_' + spec['family'] + '_0' if role == 'model_group'
                        else 'cmf_' + spec['family'] + '_ps_10000207')
                resource = payload(self.after, name)
                self.assertEqual(sum(r['name'] == name and r['id'] == resource['id'] for r in links), 1)
                self.assertFalse(any(r['name'] == art.RENDER_DONORS[role] for r in links))
                self.assertNotIn(resource['id'], known_ids)
                self.assertNotIn(name.lower(), known_names)
                known_ids.add(resource['id'])
                known_names.add(name.lower())
                self.assertEqual(resource['data'], payload(self.before, art.RENDER_DONORS[role])['data'])
                self.assertIsNone(resource['parent'])

    def test_shader_program_and_unknown_model_fields_are_preserved(self):
        raven = payload(self.before, art.RAVEN['material'])
        for spec, _ in self.families:
            material = payload(self.after, spec['names']['material'])
            expected = bytearray(raven['data'])
            struct.pack_into('<Q', expected, 0x10, spec['q10'])
            self.assertEqual(material['data'], expected)
            self.assertEqual(payload(self.after, spec['names']['map_model'])['data'],
                             payload(self.before, art.RAVEN['map_model'])['data'])
        for name in (*art.RAVEN.values(), *art.RENDER_DONORS.values()):
            self.assertEqual([art.logical.record_bytes(r) for r in self.before if r['name'] == name],
                             [art.logical.record_bytes(r) for r in self.after if r['name'] == name], name)

    def test_type_table_delta_matches_actual_new_payload_types(self):
        def typed(records):
            return Counter(struct.unpack_from('<I', r['data'])[0] & 0xFFFFFF for r in records
                           if r['kind'] == 1 and len(r['data']) >= 4)
        def table(records):
            return {r['key']: r['count'] for r in art.logical.read_type_table(
                art.logical.payload_records(records)[1]['data'])}
        expected = Counter({0xA: 2, 0x1000A: 2, 0x1000C: 2, 0x2000C: 2,
                            0x10001: 2, 0x20001: 2, 0x10015: 4})
        self.assertEqual(typed(self.after) - typed(self.before), expected)
        self.assertEqual(Counter(table(self.after)) - Counter(table(self.before)), expected)
        self.assertEqual(self.report['proof'][art.WAD]['added_typed'], 16)
        self.assertEqual(self.report['proof'][art.WAD]['added_payloads'], 20)

    def test_repeat_build_has_exact_inverse_and_is_not_failed_full_package(self):
        raw, proof = art.build_wad(self.source, self.families, isolate_render_resources=True)
        self.assertEqual(raw, self.raw)
        self.assertTrue(proof['exact_inverse'])
        self.assertTrue(self.report['proof']['two_compositions_equal'])
        self.assertFalse(self.report['runtime_coexistence_verified'])
        self.assertNotEqual(art.sha(raw), '80ad1a4b6fb1b6d84555c8ee06420f2616297a3d16236c2625314e7205b55bed')

    def test_render_id_collision_and_wrong_donor_type_fail_closed(self):
        original = art.identity
        collision = payload(self.before, art.RENDER_DONORS['model_group'])['id']
        def identity(family, role, size=16):
            return collision if role == 'model_group' else original(family, role, size)
        with patch.object(art, 'identity', identity), self.assertRaisesRegex(ValueError, 'render resource collision'):
            art.build_wad(self.source, self.families, isolate_render_resources=True)
        wrong = copy.deepcopy(self.before)
        struct.pack_into('<I', payload(wrong, art.RENDER_DONORS['pixel_shader'])['data'], 0, 0x2000A)
        with self.assertRaisesRegex(ValueError, 'render donor grammar'):
            art.build_wad(art.logical.serialize_wad(wrong), self.families, isolate_render_resources=True)

    def test_only_two_families_change_and_pool_capacity_stays_constant(self):
        before = art.stage.marker_snapshot(art.locations.base.parsed(
            (self.output / 'baseline' / art.MASTER).read_bytes(), 'mapmaster.dcb'))
        after = art.stage.marker_snapshot(art.locations.base.parsed(
            (self.package / art.MASTER).read_bytes(), 'mapmaster.dcb'))
        selected = {r['marker']['uid']: r['family'] for r in art.all_definitions()
                    if r['family'] in builder.FAMILIES}
        expected = [{**r, 'icon': art.spec_for(selected[r['uid']])['resource']} if r['uid'] in selected else r
                    for r in before]
        self.assertEqual(after, expected)
        self.assertEqual(sum(a != b for a, b in zip(before, after)), 144)
        self.assertEqual(self.report['proof'][art.POOL]['added_physics_objects'], 0)
        self.assertEqual((self.package / art.POOL).stat().st_size,
                         (self.output / 'baseline' / art.POOL).stat().st_size)
        pack = (self.package / 'exec/patch/pc_le' / (textures.PACK + '.texpack')).read_bytes()
        self.assertEqual(len(textures.binding.parse_texpack_entries(pack)), 4)
        self.assertEqual(set(self.report['proof']['textures']['families']), set(builder.FAMILIES))

    def fake_game(self, root):
        game, output = root / 'game', root / 'output'
        shutil.copytree(self.output / 'baseline', game)
        shutil.copytree(self.package.parent, output / 'packages' / self.report['package_id'])
        (output / 'report.json').write_text(json.dumps(self.report))
        return game, output

    def assert_restored(self, game):
        for name, item in self.report['files'].items():
            self.assertEqual(installer.digest_file(game / name), item['before'], name)
        installer.preserve(self.report, game)

    def test_real_file_install_verify_and_rollback_preserve_completion_v6(self):
        with tempfile.TemporaryDirectory() as temp:
            game, output = self.fake_game(Path(temp))
            journal = installer.install(game, output, lambda: None)
            installer.verify(journal, game, output)
            self.assertEqual(set(self.report['preserved']), set(textures.PRESERVED) | {art.PERM})
            shutil.rmtree(output / 'packages')
            (output / 'report.json').unlink()
            installer.rollback(journal, game, output, lambda: None)
            installer.rollback(journal, game, output, lambda: None)
            self.assert_restored(game)

    def test_failed_wad_install_rolls_back_all_artwork(self):
        with tempfile.TemporaryDirectory() as temp:
            game, output = self.fake_game(Path(temp))
            original = installer.io.atomic_copy
            def fail(source, target, after, before):
                original(source, target, after, before)
                if 'packages' in source.parts and target.name == 'r_ui.wad':
                    raise OSError('simulated post-WAD failure')
            with patch.object(installer.io, 'atomic_copy', fail), self.assertRaisesRegex(OSError, 'post-WAD'):
                installer.install(game, output, lambda: None)
            self.assert_restored(game)


if __name__ == '__main__':
    unittest.main()
