"""Shared-loader acceptance and adversarial preservation checks. Offline only."""
import importlib.util
import os
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load():
    spec = importlib.util.spec_from_file_location('shared_probe', HERE/'build-raven-shared-loader.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SharedLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load()
        cls.root = Path(os.environ.get('COMPLETIONIST_RAVEN_ROOT', 'G:/SteamLibrary/steamapps/common/GodOfWar'))
        cls.files, cls.proof = cls.p.generate(cls.root)

    def test_exact_file_scope_no_wad_art_or_compass(self):
        self.assertEqual(set(self.files), set(self.p.FILES))
        self.assertEqual(len(self.files), 4)
        self.assertNotIn('exec/wad/pc_le/r_ui.wad', self.files)
        self.assertNotIn('exec/dc/pc_le/compassgraph.dcb', self.files)

    def test_independent_uids_shared_resource_and_coordinate(self):
        p = self.p
        m = p.parse(self.files[p.MASTER], p.MASTER)
        c = p.parse(self.files[p.COORDS], p.COORDS)
        rows = p.b.marker_snapshot(m)
        raven, twin = [next(r for r in rows if r['uid'] == f'{uid:016X}')
                       for uid in (p.b.RAVEN_MARKER_UID, p.b.TWIN_MARKER_UID)]
        self.assertEqual(raven['icon'], twin['icon'])
        self.assertEqual(twin['icon'], p.b.RAVEN_MAP_GO)
        self.assertNotEqual(raven['uid'], twin['uid'])
        self.assertEqual(raven['canonical'][8:], twin['canonical'][8:])
        co = next(r for r in p.b.coordinate_snapshot(c) if r['uid'] == twin['uid'])
        self.assertEqual(tuple(co['position']), p.b.TWIN_POSITION)
        self.assertEqual(m.blob[twin['offset']+28], 0)

    def test_original_pool_rows_exact_and_additive_capacity_two(self):
        p = self.p
        before = (self.root/p.UI).read_bytes()
        after = self.files[p.UI]
        proof = p.validate_pool(before, after)
        self.assertEqual(proof['raven_capacity_before'], 1)
        self.assertEqual(proof['raven_capacity_after'], 2)
        self.assertTrue(proof['all_original_rows_byte_identical'])

    def test_frozen_lua_is_exact_prefix(self):
        source = (self.root/self.p.LUA).read_bytes()
        self.assertTrue(self.files[self.p.LUA].startswith(source))
        self.assertEqual(self.files[self.p.LUA][len(source):], self.p.hook_bytes())

    def test_deterministic_output(self):
        second, _ = self.p.generate(self.root)
        self.assertEqual(self.files, second)

    def test_tampered_opaque_marker_byte_rejected(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.MASTER)
        result = p.parse(self.files[p.MASTER], p.MASTER)
        row = next(r for r in p.b.marker_snapshot(result) if r['uid'] == f'{p.b.TWIN_MARKER_UID:016X}')
        raw = bytearray(self.files[p.MASTER])
        raw[result.file_base+row['offset']+29] ^= 1
        with self.assertRaises(ValueError):
            p.validate_append(source, p.parse(bytes(raw), p.MASTER), 'marker')

    def test_stale_original_bytes_cannot_hide_tampered_active_native(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.MASTER)
        result = p.parse(self.files[p.MASTER], p.MASTER)
        row = next(r for r in p.b.marker_snapshot(result) if r['offset'] >= len(source.blob))
        raw = bytearray(self.files[p.MASTER])
        raw[result.file_base+row['offset']+16] ^= 1
        with self.assertRaises(ValueError):
            p.validate_append(source, p.parse(bytes(raw), p.MASTER), 'marker')

    def test_extra_relocation_rejected(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.MASTER)
        result = p.parse(self.files[p.MASTER], p.MASTER)
        result.relocations.add(next(i for i in range(0, len(result.blob), 8) if i not in result.relocations))
        with self.assertRaises(ValueError):
            p.validate_append(source, result, 'marker')

    def test_chunk_padding_tamper_rejected(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.MASTER)
        raw = bytearray(self.files[p.MASTER])
        chunk = next(c for c in p.b.parse_dcb_chunks(raw) if c['end'] < c['padded'])
        raw[chunk['end']] ^= 1
        with self.assertRaises(ValueError):
            p.validate_append(source, p.parse(bytes(raw), p.MASTER), 'marker')

    def test_original_array_padding_tamper_rejected(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.MASTER)
        raw = bytearray(self.files[p.MASTER])
        field = int(self.proof['proofs'][p.MASTER]['array_field'], 16)
        raw[source.file_base+field+12] ^= 1
        with self.assertRaises(ValueError):
            p.validate_append(source, p.parse(bytes(raw), p.MASTER), 'marker')

    def test_wrong_coordinate_uid_rejected(self):
        p = self.p
        source = p.b.load_native_module().Dcb(self.root/p.COORDS)
        result = p.parse(self.files[p.COORDS], p.COORDS)
        row = next(r for r in p.b.coordinate_snapshot(result) if r['uid'] == f'{p.b.TWIN_MARKER_UID:016X}')
        raw = bytearray(self.files[p.COORDS])
        raw[result.file_base+row['offset']] ^= 1
        with self.assertRaises(ValueError):
            p.validate_append(source, p.parse(bytes(raw), p.COORDS), 'coordinate')

    def test_source_pin_refuses_modified_input(self):
        raw = bytearray((self.root/self.p.UI).read_bytes())
        raw[-1] ^= 1
        with self.assertRaises(ValueError):
            self.p.build_pool(bytes(raw))

    def test_opaque_pool_row_tamper_rejected(self):
        p = self.p
        before = (self.root/p.UI).read_bytes()
        after = bytearray(self.files[p.UI])
        chunk = p.b.one_chunk(p.b.parse_dcb_chunks(after), 12)
        after[chunk['start']+p.b.GOP_BASE+10] ^= 1
        with self.assertRaises(ValueError):
            p.validate_pool(before, bytes(after))


if __name__ == '__main__':
    unittest.main()
