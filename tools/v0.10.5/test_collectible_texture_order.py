"""Check texture pixels selected by GoW's sequential WAD loader."""
import json
import unittest

import collectible_family_art as art


def resident_bindings(records):
    # Loader 0x41ee60 sets current buffer; texture ctor 0x4e1460 reads it.
    current = None
    result = {}
    for record in records:
        if record['kind'] == 29:
            current = bytes(record['data'])
        elif (record['kind'] == 1 and len(record['data']) >= 0x164
              and record['data'][:4] == b'\x15\x00\x01\x00'
              and record['data'][0x44] & 8):
            result[record['name']] = current
    return result


class TextureOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = (art.BUILD / 'resident-pairs-probe'
                  if (art.BUILD / 'resident-pairs-probe/report.json').exists()
                  else art.BUILD / 'render-probe')
        report = json.loads((output / 'report.json').read_text())
        package = output / 'packages' / report['package_id'] / 'game-root'
        cls.source = (output / 'baseline' / art.WAD).read_bytes()
        old = art.logical.parse_wad((package / art.WAD).read_bytes())
        cls.families = []
        for family, row in report['proof']['textures']['families'].items():
            textures = {}
            for role in ('diffuse', 'emissive'):
                textures[role] = {key: row[role][key] for key in ('name', 'file_hash', 'user_hash')}
                textures[role]['resident'] = bytes(art.clone.unique_texture(
                    old, row[role]['name'], gpu=True)[1]['data'])
            cls.families.append((art.spec_for(family), textures))

    def test_each_family_loads_its_own_pixels_in_either_order(self):
        for families in (self.families, self.families[::-1]):
            for isolated in (False, True):
                with self.subTest(order=[s['family'] for s, _ in families], isolated=isolated):
                    raw, _ = art.build_wad(self.source, families, isolate_render_resources=isolated)
                    bound = resident_bindings(art.logical.parse_wad(raw))
                    for _, textures in families:
                        for texture in textures.values():
                            self.assertEqual(art.sha(bound[texture['name']]),
                                             art.sha(texture['resident']), texture['name'])

    def test_new_pixels_do_not_replace_raven_or_stock_pixels(self):
        before = resident_bindings(art.logical.parse_wad(self.source))
        raw, proof = art.build_wad(self.source, self.families, isolate_render_resources=True)
        after = resident_bindings(art.logical.parse_wad(raw))
        self.assertTrue(before)
        for name, pixels in before.items():
            self.assertEqual(art.sha(after[name]), art.sha(pixels), name)
        self.assertTrue(proof['exact_inverse'])

    def test_all_fifteen_families_bind_own_pixels_and_preserve_raven(self):
        all_output = art.BUILD / 'all-types'
        report_path = all_output / 'report.json'
        if not report_path.exists():
            self.skipTest('all-types package not built')
        report = json.loads(report_path.read_text())
        pkg_wad = (all_output / 'packages' / report['package_id'] / 'game-root' / art.WAD).read_bytes()
        bound = resident_bindings(art.logical.parse_wad(pkg_wad))
        base_bound = resident_bindings(art.logical.parse_wad((all_output / 'baseline' / art.WAD).read_bytes()))
        # Preserved baseline textures stay identical
        for name, pixels in base_bound.items():
            self.assertEqual(art.sha(bound[name]), art.sha(pixels), f'Baseline texture altered: {name}')
        # All 15 families have distinct diffuse and emissive buffers
        custom_families = report['proof']['textures']['families']
        self.assertEqual(len(custom_families), 15)
        diff_shas = {family: art.sha(bound[row['diffuse']['name']]) for family, row in custom_families.items()}
        emis_shas = {family: art.sha(bound[row['emissive']['name']]) for family, row in custom_families.items()}
        self.assertEqual(len(set(diff_shas.values())), 15, 'Diffuse textures collided')
        self.assertEqual(len(set(emis_shas.values())), 15, 'Emissive textures collided')
        # None of the new textures share pixels with Raven
        raven_diff = art.sha(base_bound[art.RAVEN['diffuse']])
        raven_emis = art.sha(base_bound[art.RAVEN['emissive']])
        self.assertNotIn(raven_diff, diff_shas.values())
        self.assertNotIn(raven_emis, emis_shas.values())


if __name__ == '__main__':
    unittest.main()
