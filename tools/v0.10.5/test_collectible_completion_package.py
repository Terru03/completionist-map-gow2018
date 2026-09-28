"""Package transactions preserve exact bytes across failure and rollback."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompletionPackageTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'install-collectible-completion.py').is_file(),
                        'completion installer missing')
        self.mod = load('completion_installer_test', 'install-collectible-completion.py')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game, self.output = self.root / 'game', self.root / 'build'
        self.candidate_root = self.output / 'draft/game-root'
        self.before = {}
        files, preserved = {}, {}
        for name in self.mod.PRESERVED:
            self.write(self.game / name, ('preserve ' + name).encode())
            preserved[name] = self.mod.io.sha(self.game / name)
        for index, name in enumerate(self.mod.FILES):
            old = None if index >= 5 else ('working ' + name).encode()
            self.before[name] = old
            if old is not None:
                self.write(self.game / name, old)
            self.write(self.candidate(name), ('completion ' + name).encode())
            files[name] = {'before': self.mod.io.sha(self.game / name),
                           'after': self.mod.io.sha(self.candidate(name))}
        self.write(self.candidate(self.mod.builder.UPSTREAM), b'companion contract=' + b'a' * 64)
        files[self.mod.builder.UPSTREAM]['after'] = self.mod.io.sha(self.candidate(self.mod.builder.UPSTREAM))
        companion = self.mod.io.sha(self.candidate(self.mod.builder.UPSTREAM))
        self.write(self.candidate('dxgi.dll'), ('shim ' + companion).encode())
        files['dxgi.dll']['after'] = self.mod.io.sha(self.candidate('dxgi.dll'))
        manifest = {'schema': 1, 'owner': self.mod.KIND, 'target_relative': 'dxgi.dll',
                    'installed_sha256': files['dxgi.dll']['after'],
                    'upstream_relative': self.mod.builder.UPSTREAM,
                    'upstream_sha256': companion, 'supported_exe_sha256': preserved['GoW.exe'],
                    'marker_slots': 2048, 'entity_slots': 4096, 'ui_physics_slots': 2048}
        self.write(self.candidate(self.mod.builder.MANIFEST), json.dumps(manifest).encode())
        files[self.mod.builder.MANIFEST]['after'] = self.mod.io.sha(
            self.candidate(self.mod.builder.MANIFEST))
        self.report = {'schema': 1, 'kind': self.mod.KIND, 'mode': 'hide_collected',
                       'unknown_state_policy': 'visible', 'location_count': 410,
                       'contract': 'a' * 64, 'files': files, 'preserved': preserved,
                       'capacity_shim': manifest,
                       'inputs_sha256': 'c' * 64,
                       'proof': {'lua51_compiled': True, 'lua52_compiled': True, 'map_assets_unchanged': True,
                                 'raven_prefix_changed_only_for_authority_notification': True,
                                 'native_contract_in_actual_dll': True, 'native_ctest_passed': True,
                                 'companion_dxgi_forwarding_passed': True, 'shim_export_contract_passed': True,
                                 'two_build_hashes_equal': True}}
        self.save_report()
        self.supported = patch.object(self.mod, 'EXE_SHA', preserved['GoW.exe'])
        self.supported.start()
        self.addCleanup(self.supported.stop)

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def candidate(self, name):
        return self.candidate_root / name

    def save_report(self):
        if 'candidate_relative' not in self.report:
            identity = self.mod.builder.locations.sha(json.dumps({'inputs': self.report['inputs_sha256'],
                'files': {n: h['after'] for n, h in self.report['files'].items()}}, sort_keys=True).encode())
            self.report['candidate_relative'] = f'packages/{identity}/game-root'
            dest = self.output / self.report['candidate_relative']
            dest.parent.parent.mkdir(parents=True, exist_ok=True)
            self.candidate_root.parent.rename(dest.parent)
            self.candidate_root = dest
        self.mod.io.write_json(self.candidate_root.parent / 'report.json', self.report)
        self.mod.io.write_json(self.output / 'report.json', self.report)

    def installed(self):
        return self.mod.install(self.game, self.output, lambda: None)

    def assert_before(self):
        for name, data in self.before.items():
            path = self.game / name
            self.assertEqual(path.read_bytes() if path.exists() else None, data, name)

    def test_install_verify_and_rollback_use_only_own_journal(self):
        journal = self.installed()
        self.mod.verify(journal, self.game, self.output)
        shutil.rmtree(self.output / 'packages')
        (self.output / 'report.json').unlink()
        self.mod.rollback(journal, self.game, self.output, lambda: None)
        self.mod.rollback(journal, self.game, self.output, lambda: None)
        self.assert_before()
        self.assertEqual(json.loads(journal.read_text())['status'], 'rolled_back')

    def test_partial_copy_failure_restores_every_prior_byte(self):
        original = self.mod.io.atomic_copy
        copies = []
        def fail(source, destination, after, before):
            if 'packages' in source.parts:
                copies.append(destination)
                if len(copies) == 5:
                    raise OSError('test write failure')
            return original(source, destination, after, before)
        with patch.object(self.mod.io, 'atomic_copy', fail), self.assertRaisesRegex(OSError, 'test write'):
            self.installed()
        self.assertEqual(len(copies), 5)
        self.assert_before()

    def test_failure_after_replace_also_rolls_back(self):
        original = self.mod.io.atomic_copy
        def fail(source, destination, after, before):
            original(source, destination, after, before)
            if 'packages' in source.parts and destination.name == 'dxgi.dll':
                raise OSError('test after replace')
        with patch.object(self.mod.io, 'atomic_copy', fail), self.assertRaisesRegex(OSError, 'after replace'):
            self.installed()
        self.assert_before()

    def test_game_running_refuses_install_without_journal_or_writes(self):
        def running():
            raise ValueError('God of War is running')
        with self.assertRaisesRegex(ValueError, 'running'):
            self.mod.install(self.game, self.output, running)
        self.assertFalse((self.output / 'backups').exists())
        self.assert_before()

    def test_immutable_package_path_and_report_are_required(self):
        for relative in ('candidate/game-root', '../outside', 'packages/' + '0'*64 + '/game-root'):
            original = self.report['candidate_relative']
            self.report['candidate_relative'] = relative
            self.save_report()
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.installed()
            self.report['candidate_relative'] = original
        self.save_report()
        (self.candidate_root.parent / 'report.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'immutable package report'):
            self.installed()
        self.assertFalse((self.output / 'backups').exists())
        self.assert_before()

    def test_dll_contract_is_checked_in_actual_bytes(self):
        self.report['contract'] = 'd' * 64
        self.save_report()
        with self.assertRaisesRegex(ValueError, 'actual companion contract'):
            self.installed()
        self.assert_before()

    def test_source_candidate_and_preserved_drift_refuse_all_writes(self):
        for path in (self.game / self.mod.FILES[0], self.candidate(self.mod.FILES[-1]),
                     self.game / 'version.dll'):
            old = path.read_bytes()
            path.write_bytes(b'unrelated edit')
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                self.installed()
            self.assertFalse((self.output / 'backups').exists())
            self.assertEqual(path.read_bytes(), b'unrelated edit')
            path.write_bytes(old)
        self.assert_before()

    def test_unrelated_edit_blocks_all_rollback_writes(self):
        journal = self.installed()
        (self.game / self.mod.FILES[-1]).write_bytes(b'later user edit')
        snapshot = {n: (self.game / n).read_bytes() for n in self.mod.FILES}
        with self.assertRaisesRegex(ValueError, 'unrelated edit'):
            self.mod.rollback(journal, self.game, self.output, lambda: None)
        self.assertEqual(snapshot, {n: (self.game / n).read_bytes() for n in self.mod.FILES})

    def test_corrupt_backup_blocks_all_rollback_writes(self):
        journal = self.installed()
        (journal.parent / 'before' / self.mod.FILES[0]).write_bytes(b'corrupt backup')
        snapshot = {n: (self.game / n).read_bytes() for n in self.mod.FILES}
        with self.assertRaisesRegex(ValueError, 'backup'):
            self.mod.rollback(journal, self.game, self.output, lambda: None)
        self.assertEqual(snapshot, {n: (self.game / n).read_bytes() for n in self.mod.FILES})

    def test_bad_paths_hashes_and_missing_capacity_refuse_all_writes(self):
        defects = [('files', '../outside'), ('files', 'C:/outside'),
                   ('files', 'dxgi.dll:stream'), ('preserved', '../outside')]
        for section, name in defects:
            old = self.report[section]
            self.report[section] = dict(old, **{name: next(iter(old.values()))})
            self.save_report()
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.installed()
            self.report[section] = old
        for section, key, bad in [('capacity_shim', 'entity_slots', 732),
                                  ('capacity_shim', 'ui_physics_slots', 500),
                                  ('preserved', 'version.dll', None)]:
            old = self.report[section][key]
            self.report[section][key] = bad
            self.save_report()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.installed()
            self.report[section][key] = old
        self.assertFalse((self.output / 'backups').exists())
        self.assert_before()

    def test_malformed_journal_rejected_before_rollback(self):
        journal = self.installed()
        original = json.loads(journal.read_text())
        for key, value in [('schema', 2), ('status', 'bogus'), ('kind', 'wrong'),
                           ('game_root', str(self.root / 'another-game'))]:
            data = dict(original, **{key: value})
            self.mod.io.write_json(journal, data)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.mod.rollback(journal, self.game, self.output, lambda: None)
        self.mod.io.write_json(journal, original)
        moved = self.output / 'not-backups/operation.json'
        self.write(moved, journal.read_bytes())
        with self.assertRaises(ValueError):
            self.mod.rollback(moved, self.game, self.output, lambda: None)
        self.mod.verify(journal, self.game, self.output)

    def test_duplicate_json_fields_rejected(self):
        path = self.output / 'report.json'
        raw = path.read_text()
        path.write_text(raw.replace('"schema": 1', '"schema": 2, "schema": 1'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.installed()
        self.assert_before()

    def test_linked_candidate_refuses_writes(self):
        path = self.candidate(self.mod.FILES[-1])
        other = self.root / 'linked-source'
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.hardlink_to(other)
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            self.installed()
        self.assert_before()


class BuilderProofTest(unittest.TestCase):
    def setUp(self):
        self.mod = load('completion_builder_test', 'build-collectible-completion.py')

    def test_authority_hook_calls_existing_reader_and_inverse_preserves_prefix(self):
        import sys
        sys.path.insert(0, str(HERE.parents[2] / 'completionist-map-gow2018/dist/re-tools'))
        from lupa.lua51 import LuaRuntime
        prefix = b'''local calls = 0
local function refreshNativeAuthority(reason) calls=calls+1; return reason end
local function beginAuthorityBoundary() end
_G.CompletionistMapV105NotifyAuthorityBoundary = beginAuthorityBoundary
local requestedBoundaryEpoch = 7
local snapshot = {restoreEpoch=7}
_G.CompletionistMapV105LastNativeRestoreEpoch = requestedBoundaryEpoch
_G.CompletionistMapV105LastNativeRestoreEpoch = snapshot.restoreEpoch
_G.CompletionistMapV105LastNativeRestoreEpoch = requestedBoundaryEpoch
_G.CompletionistMapV105LastNativeRestoreEpoch = snapshot.restoreEpoch
_G.GetCalls = function() return calls end
'''
        lua = LuaRuntime()
        lua.execute(self.mod.wire_authority(prefix).decode())
        self.assertEqual(lua.globals().CompletionistMapV105RefreshLocationAuthority(), 'collectible_background')
        self.assertEqual(lua.globals().GetCalls(), 1)
        self.assertEqual(self.mod.unwire_authority(self.mod.wire_authority(prefix)), prefix)

    def test_working_map_hooks_all_four_authority_success_paths(self):
        original = (self.mod.BUILD / 'baseline' / self.mod.MAP).read_bytes()
        prefix = original.split(self.mod.START, 1)[0]
        wired = self.mod.wire_authority(prefix)
        self.assertEqual(wired.count(b'LocationAuthorityReady(requestedBoundaryEpoch)'), 2)
        self.assertEqual(wired.count(b'LocationAuthorityReady(snapshot.restoreEpoch)'), 2)
        self.assertEqual(self.mod.unwire_authority(wired), prefix)

    def test_working_map_hooks_toggle_and_resync_paths(self):
        original = (self.mod.BUILD / 'baseline' / self.mod.MAP).read_bytes()
        prefix = original.split(self.mod.START, 1)[0]
        wired = self.mod.wire_toggle(self.mod.wire_authority(prefix))
        self.assertIn(b'_G.CompletionistMapV105ResyncRavens = function', wired)
        self.assertIn(b'_G.CompletionistMapV105ResyncNornir = function', wired)
        self.assertIn(b'_G.CompletionistMapV105ShowAll', wired)
        self.assertIn(b'_G.CompletionistMapV105ShowCategories', wired)
        unwired = self.mod.unwire_authority(self.mod.unwire_toggle(wired))
        self.assertEqual(unwired, prefix)

    def test_recovery_validator_refuses_path_hash_schema_status_and_game_changes(self):
        data = json.loads((self.mod.BUILD / 'baseline.json').read_text())
        self.mod.validate_recovery(data, self.mod.GAME)
        for key, value in [('schema', True), ('status', 'rolled_back'), ('kind', 'wrong'),
                           ('game_root', 'C:/wrong'), ('files', {'../x': {'before': None, 'after': 'a'*64}})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.mod.validate_recovery(dict(data, **{key: value}), self.mod.GAME)

    def test_freeze_source_drift_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source.py'
            source.write_bytes(b'old source')
            with patch.object(self.mod, 'source_inventory', return_value={'source.py': source}):
                self.mod.freeze_sources(root, {})
                before = (root / 'inputs.json').read_bytes()
                source.write_bytes(b'new source')
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    self.mod.freeze_sources(root, {})
                self.assertEqual((root / 'inputs.json').read_bytes(), before)

    def test_marker_identity_diff_is_rejected(self):
        old = b'{Name="Pin",IdString="42",Family="coffin",Realm="Midgard",Native=false},'
        new = b'{Name="Pin", IdString="42", Family="coffin", Realm="Midgard", CatalogueId="a", Native=false},'
        self.mod.preserve_rows(old, new)
        with self.assertRaisesRegex(ValueError, 'marker identities'):
            self.mod.preserve_rows(old, new.replace(b'42', b'43'))


if __name__ == '__main__':
    unittest.main()
