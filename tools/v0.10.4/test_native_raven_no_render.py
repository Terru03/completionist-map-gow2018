"""Behavior checks on disposable files. Never use installed game as write target."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load('compare-native-raven-no-render.py')


class RuntimeTests(unittest.TestCase):
    def test_queued_is_not_manager_or_visual_proof(self):
        source = (compare.ARCHIVE/'completionist-v104-native-raven-route-reproof.txt').read_text(encoding='utf-8-sig')
        result = compare.runtime_evidence(source)
        self.assertTrue(result['attempts'][0]['lua_return_ok'])
        self.assertEqual(result['manager_verified_attempts'], 0)
        self.assertFalse(result['visual_readiness_proven'])

    def test_old_manager_line_cannot_verify_new_request(self):
        prefix = '[CompletionistMap v0.10.3-native] '
        lines = ['NATIVE_RAVEN_VERIFY active=true native_manager=true',
                 'NATIVE_RAVEN_PREFLIGHT wad=nil x=0 y=0 z=0',
                 'NATIVE_RAVEN_SHOW stage=before', 'NATIVE_RAVEN_SHOW stage=lua_return ok=true',
                 'NATIVE_RAVEN_API installed=true',
                 'NATIVE_RAVEN_VERIFY active=true native_manager=true']
        self.assertEqual(compare.runtime_evidence('\n'.join(prefix+s for s in lines))['manager_verified_attempts'], 0)

    def test_empty_log_gives_no_runtime_claim(self):
        self.assertEqual(compare.runtime_evidence('')['attempts'], [])

    def test_missing_class_evidence_never_classified_exact(self):
        self.assertTrue(hasattr(compare,'classifications'), 'Evidence-based classification missing')
        labels = compare.classifications({'mapmaster_only_raven_icon_pointer_and_appended_string':False},
                                        {'packed_class':{'unavailable':'backup missing'}})
        self.assertEqual(labels['DockPoint_record_and_static_lookup_contract'], 'unknown/unrecoverable')
        self.assertNotEqual(labels['mapmaster_non_icon_fields'], 'exact known-good equivalent')

    def test_changed_native_fields_remove_equivalence_claim(self):
        labels=compare.classifications({'mapmaster_only_raven_icon_pointer_and_appended_string':False,
            'live':{'files':{'mapmaster.dcb':{'sha256':'f'*64},
                             'mapcoords.dcb':{'sha256':compare.HISTORICAL['mapcoords.dcb']}}}}, {})
        self.assertEqual(labels['mapmaster_non_icon_fields'],'unknown/unrecoverable')
        self.assertEqual(labels['mapmaster.dcb'],'changed and plausibly causal')
        self.assertEqual(labels['mapcoords.dcb'],'exact known-good equivalent')

    def test_output_cannot_escape_or_overlap_game(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                compare.safe_output(root/'outside.json', root/'reports', root/'game')
            with self.assertRaises(ValueError):
                compare.safe_output(root/'game/out.json', root, root/'game')


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'native-raven-data-ab.py').exists(), 'Two-file fail-closed A/B installer missing')
        self.ab = load('native-raven-data-ab.py')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game, self.sources, self.state = [self.root/n for n in ('game','sources','state')]
        self.game.mkdir(); self.sources.mkdir(); self.state.mkdir()
        self.rows = {}
        for n in ('mapcoords.dcb','compassgraph.dcb'):
            (self.game/n).write_bytes(b'before '+n.encode())
            (self.sources/n).write_bytes(b'after '+n.encode())
            self.rows[n] = {'target': str(self.game/n), 'source': str(self.sources/n),
                'before': compare.file_info(self.game/n)['sha256'], 'after': compare.file_info(self.sources/n)['sha256']}
        self.guard = lambda: None

    def install(self):
        return self.ab.install_pair(self.rows, self.state, self.game, self.guard)

    def assert_before(self):
        for row in self.rows.values():
            self.assertEqual(compare.file_info(Path(row['target']))['sha256'], row['before'])

    def test_round_trip_backups_and_manifest(self):
        manifest = self.install()
        for row in self.rows.values():
            self.assertEqual(compare.file_info(Path(row['target']))['sha256'], row['after'])
        self.ab.rollback_pair(manifest, self.rows, self.game, self.guard)
        self.assert_before()
        self.assertEqual(json.loads(manifest.read_text())['state'], 'rolled_back')
        self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)
        self.assert_before()

    def test_unresolved_manifest_blocks_new_install(self):
        manifest=self.install()
        for name in self.rows:
            (self.game/name).write_bytes((manifest.parent/(name+'.before')).read_bytes())
        with self.assertRaises(ValueError): self.install()
        self.assert_before()
        self.assertEqual(len(list(self.state.glob('*/manifest.json'))),1)

    def test_interrupted_mix_can_be_rolled_back(self):
        manifest=self.install()
        name='mapcoords.dcb'
        (self.game/name).write_bytes((manifest.parent/(name+'.before')).read_bytes())
        self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)
        self.assert_before()

    def test_wrong_game_manifest_refused(self):
        manifest=self.install()
        value=json.loads(manifest.read_text())
        value['game_root']=str(self.root/'another-game')
        manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)

    def test_changed_second_source_refuses_all_writes(self):
        (self.sources/'compassgraph.dcb').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.install()
        self.assert_before()

    def test_changed_second_live_file_refuses_first_write(self):
        (self.game/'compassgraph.dcb').write_bytes(b'new user state')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual((self.game/'mapcoords.dcb').read_bytes(), b'before mapcoords.dcb')

    def test_corrupt_second_backup_blocks_whole_rollback(self):
        manifest = self.install()
        (manifest.parent/'compassgraph.dcb.before').write_bytes(b'broken backup')
        with self.assertRaises(ValueError): self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)
        self.assertEqual((self.game/'mapcoords.dcb').read_bytes(), b'after mapcoords.dcb')

    def test_changed_target_blocks_whole_rollback(self):
        manifest = self.install()
        (self.game/'compassgraph.dcb').write_bytes(b'user edit')
        with self.assertRaises(ValueError): self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)
        self.assertEqual((self.game/'mapcoords.dcb').read_bytes(), b'after mapcoords.dcb')

    def test_partial_install_failure_restores_pair(self):
        replace = self.ab.replace_checked
        def fail_second(source, target, before, after):
            if Path(target).name == 'compassgraph.dcb' and before == self.rows['compassgraph.dcb']['before']:
                raise OSError('simulated second-file write failure')
            return replace(source,target,before,after)
        with patch.object(self.ab, 'replace_checked', side_effect=fail_second):
            with self.assertRaises(OSError): self.install()
        self.assert_before()
        manifests = list(self.state.glob('*/manifest.json'))
        self.assertEqual(len(manifests),1)
        self.assertEqual(json.loads(manifests[0].read_text())['state'],'rolled_back')

    def test_process_guard_refusal_has_no_writes(self):
        def running(): raise ValueError('GoW running')
        self.guard = running
        with self.assertRaises(ValueError): self.install()
        self.assert_before()

    def test_manifest_cannot_redirect_backup(self):
        manifest = self.install()
        value = json.loads(manifest.read_text())
        value['rows']['mapcoords.dcb']['backup'] = str(self.sources/'mapcoords.dcb')
        manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.ab.rollback_pair(manifest,self.rows,self.game,self.guard)

    def test_hardlinked_target_refused(self):
        os.link(self.game/'mapcoords.dcb', self.game/'alias.dcb')
        with self.assertRaises(ValueError): self.install()
        self.assert_before()


if __name__ == '__main__':
    unittest.main()
