"""Install completion package with pinned files and own rollback journal."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('completion_package_builder', HERE / 'build-collectible-completion.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
io = builder.io
KIND, FILES = builder.KIND, builder.FILES
EXE_SHA = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
PRESERVED = ('GoW.exe', 'version.dll', io.RUNIC, 'exec/dc/pc_le/mapmaster.dcb',
             'exec/dc/pc_le/mapcoords.dcb', 'exec/dc/pc_le/wad_r_ui.dcb',
             *io.STOCK_UNTOUCHED)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            io.need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(io.safe(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def digest(value, absent=False):
    io.need((absent and value is None) or
            (isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)), 'invalid SHA256')


def validate(data):
    io.need(isinstance(data, dict) and type(data.get('schema')) is int and data['schema'] == 1
            and data.get('kind') == KIND, 'invalid package schema/kind')
    io.need(isinstance(data.get('files'), dict) and set(data['files']) == set(FILES), 'invalid file allowlist')
    io.need(isinstance(data.get('preserved'), dict) and set(data['preserved']) == set(PRESERVED), 'invalid preserved allowlist')
    for item in data['files'].values():
        io.need(isinstance(item, dict) and set(item) == {'before', 'after'}, 'invalid file hashes')
        digest(item['before'], absent=True)
        digest(item['after'])
    for value in data['preserved'].values():
        digest(value)
    io.need(data['preserved']['GoW.exe'] == EXE_SHA, 'unsupported game executable')


def preserve(data, game):
    for name, expected in data['preserved'].items():
        io.need(io.sha(game / name) == expected, 'preserved file drift: ' + name)


def candidate(data, output):
    relative = data.get('candidate_relative')
    io.need(isinstance(relative, str) and re.fullmatch(r'packages/[0-9a-f]{64}/game-root', relative),
            'invalid immutable package path')
    digest(data.get('inputs_sha256'))
    identity = builder.locations.sha(json.dumps({'inputs': data['inputs_sha256'],
        'files': {n: h['after'] for n, h in data['files'].items()}}, sort_keys=True).encode())
    io.need(relative == f'packages/{identity}/game-root', 'immutable package identity differs')
    root = io.safe(output / relative)
    io.need(root.is_relative_to(io.safe(output)), 'package escapes output')
    io.need(read_json(root.parent / 'report.json') == data, 'immutable package report differs')
    return root


def inputs(game, output):
    data = read_json(output / 'report.json')
    validate(data)
    io.need(data.get('mode') == 'hide_collected' and data.get('unknown_state_policy') == 'visible'
            and data.get('location_count') == 410, 'invalid completion mode/count')
    digest(data.get('contract'))
    io.need(all(data.get('proof', {}).get(k) is True for k in ('lua51_compiled',
            'lua52_compiled', 'map_assets_unchanged', 'raven_prefix_changed_only_for_authority_notification',
            'native_contract_in_actual_dll', 'native_ctest_passed', 'companion_dxgi_forwarding_passed',
            'shim_export_contract_passed', 'two_build_hashes_equal')), 'missing proof')
    package = candidate(data, output)
    manifest = data.get('capacity_shim', {})
    expected = {'schema': 1, 'owner': KIND, 'target_relative': 'dxgi.dll',
                'installed_sha256': data['files']['dxgi.dll']['after'],
                'upstream_relative': builder.UPSTREAM,
                'upstream_sha256': data['files'][builder.UPSTREAM]['after'],
                'supported_exe_sha256': EXE_SHA, 'marker_slots': 2048,
                'entity_slots': 4096, 'ui_physics_slots': 2048}
    io.need(all(manifest.get(k) == v for k, v in expected.items()), 'invalid capacity manifest')
    for name, hashes in data['files'].items():
        io.need(io.sha(package / name) == hashes['after'], 'candidate drift: ' + name)
        io.need(io.sha(game / name) == hashes['before'], 'working file drift: ' + name)
    io.need(read_json(package / builder.MANIFEST) == manifest, 'candidate manifest differs')
    io.need(data['contract'].encode() in builder.raw(package / builder.UPSTREAM),
            'actual companion contract differs')
    io.need(data['files'][builder.UPSTREAM]['after'].encode() in builder.raw(package / 'dxgi.dll'),
            'actual shim companion pin differs')
    preserve(data, game)
    return data


def read_operation(journal, game, output):
    journal, game, output = io.safe(journal), io.safe(game), io.safe(output)
    io.need(journal.name == 'operation.json' and journal.parent.parent == output / 'backups'
            and re.fullmatch('[0-9a-f]{32}', journal.parent.name), 'invalid journal path')
    data = read_json(journal)
    validate(data)
    io.need(data.get('game_root') == str(game) and data.get('operation') == journal.parent.name,
            'invalid journal game root/operation')
    io.need(data.get('status') in {'prepared', 'installing', 'installed', 'rolling_back',
                                 'rollback_failed', 'rolled_back'}, 'invalid journal status')
    return data


def preflight_rollback(data, journal, game):
    preserve(data, game)
    for name, item in data['files'].items():
        io.need(io.sha(game / name) in (item['before'], item['after']), 'unrelated edit: ' + name)
        io.need(io.sha(journal.parent / 'before' / name) == item['before'], 'backup drift: ' + name)


def verify(journal, game=builder.GAME, output=builder.BUILD):
    data = read_operation(journal, game, output)
    io.need(data['status'] == 'installed', 'operation not installed')
    preflight_rollback(data, journal, game)
    for name, item in data['files'].items():
        io.need(io.sha(game / name) == item['after'], 'installed drift: ' + name)


def rollback(journal, game=builder.GAME, output=builder.BUILD, stopped=io.game_stopped):
    stopped()
    data = read_operation(journal, game, output)
    preflight_rollback(data, journal, game)
    if data['status'] == 'rolled_back':
        io.need(all(io.sha(game / n) == h['before'] for n, h in data['files'].items()), 'rolled-back target drift')
        return
    data['status'] = 'rolling_back'
    io.write_json(journal, data)
    try:
        for name, item in reversed(list(data['files'].items())):
            stopped()
            path = io.safe(game / name)
            current = io.sha(path)
            if current == item['before']:
                continue
            io.need(current == item['after'], 'unrelated edit: ' + name)
            if item['before'] is None:
                stopped()
                io.need(io.sha(path) == item['after'], 'target drift before removal')
                path.unlink()
            else:
                io.atomic_copy(journal.parent / 'before' / name, path, item['before'], item['after'])
        preserve(data, game)
        io.need(all(io.sha(game / n) == h['before'] for n, h in data['files'].items()), 'rollback verification failed')
        data['status'] = 'rolled_back'
        data.pop('rollback_error', None)
        io.write_json(journal, data)
    except Exception as error:
        data['status'], data['rollback_error'] = 'rollback_failed', str(error)
        io.write_json(journal, data)
        raise


def install(game=builder.GAME, output=builder.BUILD, stopped=io.game_stopped):
    stopped()
    game, output = io.safe(game), io.safe(output)
    data = inputs(game, output)
    package = candidate(data, output)
    backup = io.safe(output / 'backups' / uuid.uuid4().hex)
    backup.mkdir(parents=True, exist_ok=False)
    operation = {'schema': 1, 'kind': KIND, 'status': 'prepared', 'operation': backup.name,
                 'game_root': str(game), 'files': data['files'], 'preserved': data['preserved']}
    journal = backup / 'operation.json'
    for name, item in operation['files'].items():
        if item['before'] is not None:
            io.atomic_copy(game / name, backup / 'before' / name, item['before'], None)
    preflight_rollback(operation, journal, game)
    inputs(game, output)
    stopped()
    io.write_json(journal, operation)
    try:
        operation['status'] = 'installing'
        io.write_json(journal, operation)
        for name, item in operation['files'].items():
            stopped()
            io.atomic_copy(package / name, game / name, item['after'], item['before'])
        operation['status'] = 'installed'
        io.write_json(journal, operation)
        verify(journal, game, output)
    except Exception as error:
        try:
            rollback(journal, game, output, stopped)
        except Exception as rollback_error:
            operation = read_operation(journal, game, output)
            operation['status'] = 'rollback_failed'
            operation['install_error'], operation['rollback_error'] = str(error), str(rollback_error)
            io.write_json(journal, operation)
            raise RuntimeError(f'Install failed; rollback needs action: {journal}: {rollback_error}') from error
        raise
    return journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'verify', 'rollback'))
    parser.add_argument('--game', type=Path, default=builder.GAME)
    parser.add_argument('--output', type=Path, default=builder.BUILD)
    parser.add_argument('--operation', type=Path)
    args = parser.parse_args()
    if args.action == 'install':
        io.need(args.operation is None, 'install makes own journal')
        print(install(args.game, args.output))
    else:
        io.need(args.operation is not None, '--operation required')
        globals()[args.action](args.operation, args.game, args.output)
        print(args.action.upper() + '_OK')

if __name__ == '__main__':
    main()
