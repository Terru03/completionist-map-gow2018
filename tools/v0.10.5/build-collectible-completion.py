"""Freeze working inputs and build a verified offline completion package."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collectible_completion_adapters as adapters


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


locations = load('completion_locations', 'build-collectible-locations.py')
bindings_module = load('completion_bindings', 'build-collectible-completion-bindings.py')
io = load('completion_io', 'install-nornir-map-id-test.py')
ROOT, GAME = locations.ROOT, locations.GAME
BUILD = ROOT / 'build/collectible-completion'
MAP = locations.base.MAP_LUA
UPSTREAM = 'mods/completionist-map/native/collectible-base-dxgi.dll'
MANIFEST = 'mods/completionist-map/native/raven-native-bridge-manifest.json'
SCRIPT_FILES = {key: 'mods/lua/' + adapters.PREFIX + entry[0] for key, entry in adapters.SCRIPTS.items()}
FILES = (MAP, UPSTREAM, 'dxgi.dll', MANIFEST, *SCRIPT_FILES.values())
KIND = 'COLLECTIBLE_HIDE_COLLECTED'
START = b'-- BEGIN COMPLETIONIST V0.10.5 COLLECTIBLE LOCATIONS'
EXE_SHA = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
MAP_SHA = '33721591615d37ca599006101af696c069ee47597d460a63abecb352e41ff4e1'
RECOVERY_JOURNAL = ROOT / 'build/collectible-recovery/backups/36c89608e5554c628fa5a9b5ae7695e2/operation.json'
JOURNAL_SHA = 'ece989ba68c8eaa2697557ea0048220ccf739b3ee88b2b11099dd356088c9cd5'
RECOVERY_FILES = (MAP, UPSTREAM, 'dxgi.dll', MANIFEST, locations.base.MASTER,
                  locations.base.COORDS, locations.base.POOL, *io.STOCK_UNTOUCHED)
RECOVERY_PRESERVED = ('GoW.exe', 'version.dll', io.RUNIC, io.STANDARD)
BRIDGE = ROOT / 'build/collectible-completion-bridge'
CAPACITY = ROOT / 'build/collectible-completion-capacity'
REFRESH_ANCHOR = b'_G.CompletionistMapV105NotifyAuthorityBoundary = beginAuthorityBoundary'
REFRESH_HOOK = (b'_G.CompletionistMapV105RefreshLocationAuthority = function() '
                b'return refreshNativeAuthority("collectible_background") end\n  ')
NOTIFY = rb'\n[ \t]*if type\(_G.CompletionistMapV105LocationAuthorityReady\) == "function" then _G.CompletionistMapV105LocationAuthorityReady\((?:requestedBoundaryEpoch|snapshot\.restoreEpoch)\) end'


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            io.need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(io.safe(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def digest(value, absent=False):
    io.need((absent and value is None) or
            (isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)), 'invalid SHA256')


def relative_name(name):
    io.need(isinstance(name, str) and name and '\\' not in name and ':' not in name
            and not name.startswith('/') and all(p not in {'', '.', '..'} and p.rstrip(' .') == p
            for p in name.split('/')), 'invalid relative path')
    return name


def raw(path):
    path = io.safe(path)
    io.need(path.is_file(), 'missing input: ' + str(path))
    return path.read_bytes()


def write_bytes(path, content):
    path = io.safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.safe(path.parent)
    with path.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    io.need(io.sha(path) == locations.sha(content), 'written bytes differ')


def validate_recovery(data, game):
    io.need(isinstance(data, dict) and set(data) == {'schema', 'kind', 'status', 'game_root', 'files', 'preserved'}
            and type(data.get('schema')) is int and data['schema'] == 1
            and data.get('kind') == 'COLLECTIBLE_LOCATIONS_CAPACITY_RECOVERY'
            and data.get('status') == 'installed' and data.get('game_root') == str(io.safe(game)),
            'invalid recovery journal schema/kind/status/game')
    io.need(isinstance(data['files'], dict) and set(data['files']) == set(RECOVERY_FILES)
            and isinstance(data['preserved'], dict) and set(data['preserved']) == set(RECOVERY_PRESERVED),
            'invalid recovery file allowlist')
    for name, hashes in data['files'].items():
        relative_name(name)
        io.need(isinstance(hashes, dict) and set(hashes) == {'before', 'after'}, 'invalid recovery hashes')
        digest(hashes['before'], absent=True)
        digest(hashes['after'])
    for name, value in data['preserved'].items():
        relative_name(name)
        digest(value)
    io.need(data['preserved']['GoW.exe'] == EXE_SHA and data['files'][MAP]['after'] == MAP_SHA,
            'unsupported executable or working map')
    return {name: h['after'] for name, h in data['files'].items()} | data['preserved']


def recovery(game, journal=RECOVERY_JOURNAL):
    io.need(io.safe(journal) == io.safe(RECOVERY_JOURNAL) and io.sha(journal) == JOURNAL_SHA,
            'unsupported or drifted recovery journal')
    data = read_json(journal)
    expected = validate_recovery(data, game)
    for name, value in expected.items():
        io.need(io.sha(game / name) == value, 'working installation changed: ' + name)
    return data, expected


def source_inventory():
    paths = [locations.CATALOGUE, locations.ADDITIONAL, locations.CATEGORIES, bindings_module.CHESTS,
             bindings_module.ARTEFACTS,
             bindings_module.OUTPUT]
    for folder in (ROOT / 'tools/v0.10.4', HERE, ROOT / 'native/raven-authority-bridge',
                   ROOT / 'native/collectible-marker-capacity'):
        paths.extend(p for p in folder.rglob('*') if p.is_file() and
                     p.suffix in {'.py', '.lua', '.cpp', '.h', '.asm', '.json', '.txt', '.def'})
    for folder in (BRIDGE, CAPACITY):
        paths.extend([folder / 'Release/dxgi.dll', folder / 'CMakeCache.txt'])
        paths.extend(p for p in (folder / 'generated').glob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): p for p in sorted(set(paths))}


def check_sources(manifest):
    io.need(isinstance(manifest, dict) and manifest.get('schema') == 1
            and manifest.get('kind') == 'COLLECTIBLE_COMPLETION_INPUTS', 'invalid input freeze')
    inventory = source_inventory()
    io.need(isinstance(manifest.get('sources'), dict) and set(manifest['sources']) == set(inventory),
            'source inventory drift')
    for name, expected in manifest['sources'].items():
        relative_name(name)
        digest(expected)
        io.need(io.sha(inventory[name]) == expected, 'source drift: ' + name)


def freeze_sources(output, scripts, upgrade=None):
    path = io.safe(output / 'inputs.json')
    if path.exists():
        saved = read_json(path)
        check_sources(saved)
        io.need(saved.get('scripts') == scripts, 'script source drift')
        io.need(saved.get('upgrade') == upgrade, 'upgrade source drift')
        return saved
    sources = {name: io.sha(p) for name, p in source_inventory().items()}
    for value in sources.values():
        digest(value)
    manifest = {'schema': 1, 'kind': 'COLLECTIBLE_COMPLETION_INPUTS',
                'sources': sources, 'scripts': scripts, 'recovery_journal_sha256': JOURNAL_SHA}
    if upgrade is not None:
        manifest['upgrade'] = upgrade
    check_sources(manifest)
    io.write_json(path, manifest)
    return manifest


def upgrade_source(game, journal):
    journal = io.safe(journal)
    previous = journal.parent.parent.parent
    installer = load('completion_upgrade_installer', 'install-collectible-completion.py')
    installer.verify(journal, game, previous)
    operation = installer.read_operation(journal, game, previous)
    report = read_json(previous / 'report.json')
    installer.validate(report)
    package = installer.candidate(report, previous)
    io.need(report['files'] == operation['files'] and report['preserved'] == operation['preserved'],
            'installed operation differs from source package')
    for name, hashes in operation['files'].items():
        io.need(io.sha(package / name) == hashes['after'], 'source package drift: ' + name)
    prior_inputs = read_json(previous / 'inputs.json')
    io.need(io.sha(previous / 'inputs.json') == report['inputs_sha256'], 'source input manifest drift')
    io.need(io.sha(RECOVERY_JOURNAL) == JOURNAL_SHA, 'recovery journal drift')
    baseline = read_json(RECOVERY_JOURNAL)
    expected_base = validate_recovery(baseline, game)
    io.need(read_json(previous / 'baseline.json') == baseline, 'source baseline journal drift')
    for name, value in expected_base.items():
        io.need(io.sha(previous / 'baseline' / name) == value, 'source baseline drift: ' + name)
    io.need(set(prior_inputs.get('scripts', {})) == set(SCRIPT_FILES.values()), 'source scripts missing')
    scripts = {}
    for name, item in prior_inputs['scripts'].items():
        digest(item.get('sha256'))
        source = io.safe(previous / 'scripts' / name)
        io.need(io.sha(source) == item['sha256'], 'source script drift: ' + name)
        io.need(b'BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION' not in raw(source), 'source script has probe')
        scripts[name] = {'source': str(source), 'sha256': item['sha256'],
                         'before': operation['files'][name]['after']}
    expected = {n: h['after'] for n, h in operation['files'].items()} | operation['preserved']
    upgrade = {'operation': str(journal), 'operation_sha256': io.sha(journal),
               'source_output': str(previous), 'inputs_sha256': report['inputs_sha256']}
    return baseline, expected_base, expected, scripts, upgrade


def freeze_upgrade(game, output, journal):
    game, output = io.safe(game), io.safe(output)
    io.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    baseline, base_hashes, _, scripts, upgrade = upgrade_source(game, journal)
    previous = Path(upgrade['source_output'])
    io.need(not output.is_relative_to(previous) and not previous.is_relative_to(output),
            'upgrade output overlaps source build')
    copies = {name: (previous / 'baseline' / name, output / 'baseline' / name, value)
              for name, value in base_hashes.items()}
    for name, item in scripts.items():
        copies['script:' + name] = (Path(item['source']), output / 'scripts' / name, item['sha256'])
    for _, target, value in copies.values():
        current = io.sha(target)
        io.need(current is None or current == value, 'frozen input changed: ' + str(target))
    existing = io.safe(output / 'baseline.json')
    if existing.exists():
        io.need(read_json(existing) == baseline, 'different baseline already exists')
    manifest_path = io.safe(output / 'inputs.json')
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        check_sources(manifest)
        io.need(manifest.get('scripts') == scripts and manifest.get('upgrade') == upgrade,
                'upgrade source drift')
    for source, target, value in copies.values():
        if io.sha(target) is None:
            io.atomic_copy(source, target, value, None)
    if not existing.exists():
        io.write_json(existing, baseline)
    io.need(upgrade_source(game, journal)[4] == upgrade, 'upgrade changed while freezing')
    return freeze_sources(output, scripts, upgrade)


def freeze(game=GAME, output=BUILD, journal=RECOVERY_JOURNAL):
    game, output = io.safe(game), io.safe(output)
    io.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    data, expected = recovery(game, journal)
    existing = output / 'baseline.json'
    if io.safe(existing).exists():
        io.need(read_json(existing) == data, 'different baseline already exists')
    scripts, contents = {}, {}
    for adapter, name in SCRIPT_FILES.items():
        current = io.sha(game / name)
        source = game / name if current is not None else adapters.STOCK / adapters.PREFIX / adapters.SCRIPTS[adapter][0]
        content = raw(source)
        io.need(b'BEGIN COMPLETIONIST COLLECTIBLE OBSERVATION' not in content, 'probe already installed')
        scripts[name] = {'source': str(io.safe(source)), 'sha256': locations.sha(content), 'before': current}
        contents[name] = content
    # Reject every conflicting file before any freeze write.
    for name, value in expected.items():
        path = io.safe(output / 'baseline' / name)
        if path.exists():
            io.need(io.sha(path) == value, 'frozen baseline changed: ' + name)
    for name, content in contents.items():
        path = io.safe(output / 'scripts' / name)
        if path.exists():
            io.need(io.sha(path) == locations.sha(content), 'frozen script changed: ' + name)
    if io.safe(output / 'inputs.json').exists():
        saved = read_json(output / 'inputs.json')
        check_sources(saved)
        io.need(saved.get('scripts') == scripts, 'script source drift')
    for name, value in expected.items():
        path = output / 'baseline' / name
        if io.sha(path) is None:
            io.atomic_copy(game / name, path, value, None)
    for name, content in contents.items():
        path = output / 'scripts' / name
        if io.sha(path) is None:
            write_bytes(path, content)
    if not existing.exists():
        io.write_json(existing, data)
    recovery(game, journal)
    manifest = freeze_sources(output, scripts)
    return manifest


def validate_frozen(game, output):
    manifest = read_json(output / 'inputs.json')
    upgrade = manifest.get('upgrade')
    if upgrade is None:
        data, expected = recovery(game)
        base_hashes = expected
        expected_scripts = None
    else:
        io.need(isinstance(upgrade, dict) and set(upgrade) ==
                {'operation', 'operation_sha256', 'source_output', 'inputs_sha256'}, 'invalid upgrade metadata')
        data, base_hashes, expected, expected_scripts, current_upgrade = upgrade_source(game, Path(upgrade['operation']))
        io.need(upgrade == current_upgrade, 'upgrade source drift')
    io.need(read_json(output / 'baseline.json') == data, 'frozen baseline journal changed')
    for name, value in base_hashes.items():
        io.need(io.sha(output / 'baseline' / name) == value, 'frozen baseline changed: ' + name)
    check_sources(manifest)
    io.need(manifest.get('recovery_journal_sha256') == JOURNAL_SHA
            and set(manifest.get('scripts', {})) == set(SCRIPT_FILES.values()), 'invalid frozen scripts')
    for name, item in manifest['scripts'].items():
        io.need(isinstance(item, dict) and set(item) == {'source', 'sha256', 'before'}, 'invalid frozen script metadata')
        digest(item['sha256'])
        digest(item['before'], absent=True)
        adapter = next(k for k, v in SCRIPT_FILES.items() if v == name)
        if expected_scripts is None:
            source = game / name if item['before'] is not None else adapters.STOCK / adapters.PREFIX / adapters.SCRIPTS[adapter][0]
        else:
            io.need(item == expected_scripts[name], 'upgrade script metadata drift')
            source = Path(item['source'])
        io.need(item['source'] == str(io.safe(source)) and io.sha(source) == item['sha256']
                and io.sha(game / name) == item['before']
                and io.sha(output / 'scripts' / name) == item['sha256'], 'script source drift: ' + name)
    return expected, manifest


def unwire_authority(prefix):
    return re.sub(NOTIFY, b'', prefix).replace(REFRESH_HOOK, b'', 1)


def wire_authority(prefix):
    io.need(REFRESH_HOOK not in prefix and prefix.count(REFRESH_ANCHOR) == 1, 'Raven refresh anchor changed')
    pattern = rb'(?m)^([ \t]*)_G.CompletionistMapV105LastNativeRestoreEpoch = (requestedBoundaryEpoch|snapshot\.restoreEpoch)\r?$'
    def replace(match):
        return match[0] + (b'\n' + match[1] + b'if type(_G.CompletionistMapV105LocationAuthorityReady) == "function" then '
                           b'_G.CompletionistMapV105LocationAuthorityReady(' + match[2] + b') end')
    result, count = re.subn(pattern, replace, prefix)
    io.need(count == 4, 'Raven current-save authority anchors changed')
    result = result.replace(REFRESH_ANCHOR, REFRESH_HOOK + REFRESH_ANCHOR, 1)
    io.need(unwire_authority(result) == prefix, 'authority handoff changed unrelated Lua')
    return result


def preserve_rows(old, new):
    def records(data):
        result = []
        for line in data.splitlines():
            if b'{Name=' not in line or b'IdString=' not in line:
                continue
            fields = dict(re.findall(rb'(Name|IdString|Family|Realm|Native)\s*=\s*("[^"]*"|true|false)', line))
            io.need(set(fields) == {b'Name', b'IdString', b'Family', b'Realm', b'Native'}, 'malformed marker identity')
            result.append(fields)
        return result
    before, after = records(old), records(new)
    io.need(before and before == after, 'marker identities changed')
    return len(before)


def native_checks(contract):
    companion, shim = raw(BRIDGE / 'Release/dxgi.dll'), raw(CAPACITY / 'Release/dxgi.dll')
    io.need(contract.encode() in companion, 'actual companion binary contract differs')
    io.need(locations.sha(companion).encode() in shim, 'capacity shim does not pin actual companion')
    for folder in (BRIDGE, CAPACITY):
        cache = raw(folder / 'CMakeCache.txt').decode()
        ctest = re.search(r'^CMAKE_CTEST_COMMAND:INTERNAL=(.+)$', cache, re.M)
        io.need(ctest is not None, 'native CTest path missing')
        command = [ctest[1].strip(), '--test-dir', str(folder), '-C', 'Release', '--output-on-failure']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        io.need('100% tests passed' in result.stdout, 'native test proof missing')
        print(result.stdout.strip())
    result = subprocess.run([str(BRIDGE / 'Release/raven_bridge_export_contract_tests.exe'),
                             str(CAPACITY / 'Release/dxgi.dll')], capture_output=True, text=True, check=True)
    print(result.stdout.strip())
    return companion, shim


def compose(output, expected, inputs, native):
    rows, config, _ = locations.definitions()
    bindings = bindings_module.build()
    io.need(read_json(bindings_module.OUTPUT) == bindings, 'regenerate completion bindings')
    original = raw(output / 'baseline' / MAP)
    io.need(original.count(START) == 1, 'working location layer missing or repeated')
    prefix, old_layer = original.split(START, 1)
    layer = locations.render_runtime(rows, config)
    row_count = preserve_rows(START + old_layer, layer)
    io.need(row_count == len(rows), 'location row count differs')
    outputs = {MAP: wire_authority(prefix) + layer, UPSTREAM: native[0], 'dxgi.dll': native[1]}
    for adapter, name in SCRIPT_FILES.items():
        outputs[name] = raw(output / 'scripts' / name) + adapters.render_probe(adapter).encode()
    sys.path.insert(0, str(ROOT.parent / 'completionist-map-gow2018/dist/re-tools'))
    from lupa.lua51 import LuaRuntime
    from lupa.lua52 import LuaRuntime as Lua52Runtime
    compile_lua = LuaRuntime().eval('function(code) local fn,err=loadstring(code); assert(fn,err); return true end')
    compile_lua52 = Lua52Runtime().eval('function(code) local fn,err=load(code); assert(fn,err); return true end')
    for name, content in outputs.items():
        if name.endswith('.lua'):
            compile_lua(content.decode('utf-8-sig'))
            compile_lua52(content.decode('utf-8-sig'))
    manifest = {'schema': 1, 'owner': KIND, 'target_relative': 'dxgi.dll',
                'installed_sha256': locations.sha(outputs['dxgi.dll']), 'upstream_relative': UPSTREAM,
                'upstream_sha256': locations.sha(outputs[UPSTREAM]), 'supported_exe_sha256': expected['GoW.exe'],
                'marker_slots': 2048, 'entity_slots': 4096, 'ui_physics_slots': 2048,
                'rollback': 'install-collectible-completion.py rollback --operation <operation.json>'}
    outputs[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    io.need(set(outputs) == set(FILES), 'completion file set differs')
    report = {'schema': 1, 'kind': KIND, 'mode': 'hide_collected', 'unknown_state_policy': 'visible',
              'contract': bindings['contract'], 'location_count': len(rows),
              'saved_identity_count': sum(b['status'] == 'proved' for b in bindings['bindings']),
              'script_inputs': inputs['scripts'], 'source_inputs': inputs['sources'],
              'recovery_journal_sha256': JOURNAL_SHA, 'inputs_sha256': io.sha(output / 'inputs.json'),
              'capacity_shim': manifest,
              'preserved': {name: value for name, value in expected.items() if name not in FILES},
              'files': {name: {'before': expected[name] if name in expected else inputs['scripts'][name]['before'],
                               'after': locations.sha(content)} for name, content in outputs.items()},
              'proof': {'lua51_compiled': True, 'lua52_compiled': True, 'map_assets_unchanged': True,
                        'raven_prefix_changed_only_for_authority_notification': True,
                        'prefix_sha256': locations.sha(prefix), 'prefix_inverse_sha256': locations.sha(unwire_authority(wire_authority(prefix))),
                        'marker_identities_preserved': row_count,
                        'immutable_files': {n: h for n, h in expected.items() if n not in FILES},
                        'native_contract_in_actual_dll': True, 'native_ctest_passed': True,
                        'companion_dxgi_forwarding_passed': True, 'shim_export_contract_passed': True},
              'live_validation': 'pending'}
    if 'upgrade' in inputs:
        report['upgrade_from'] = inputs['upgrade']
    return outputs, report


def build(game=GAME, output=BUILD):
    game, output = io.safe(game), io.safe(output)
    io.need(not output.is_relative_to(game) and not game.is_relative_to(output), 'output overlaps game')
    expected, inputs = validate_frozen(game, output)
    bindings = bindings_module.build()
    native = native_checks(bindings['contract'])
    first, report = compose(output, expected, inputs, native)
    second, second_report = compose(output, expected, inputs, native)
    io.need(first == second and report == second_report, 'build is not deterministic')
    validate_frozen(game, output)
    report['proof']['two_build_hashes_equal'] = True
    artifact_hashes = {n: locations.sha(b) for n, b in first.items()}
    report['determinism'] = {'first': artifact_hashes, 'second': artifact_hashes}
    package_id = locations.sha(json.dumps({'inputs': report['inputs_sha256'], 'files': artifact_hashes}, sort_keys=True).encode())
    report['candidate_relative'] = f'packages/{package_id}/game-root'
    package = io.safe(output / 'packages' / package_id)
    if package.exists():
        for name, value in artifact_hashes.items():
            io.need(io.sha(package / 'game-root' / name) == value, 'existing immutable package drift')
        io.need(read_json(package / 'report.json') == report, 'existing immutable report drift')
    else:
        staging = io.safe(output / 'packages' / ('.staging-' + uuid.uuid4().hex))
        for name, content in first.items():
            write_bytes(staging / 'game-root' / name, content)
        io.write_json(staging / 'report.json', report)
        validate_frozen(game, output)
        io.safe(package)
        os.rename(staging, package)
    io.write_json(output / 'report.json', report)
    print(f'COMPLETION_BUILT files={len(first)} locations={report["location_count"]} saved_identities={report["saved_identity_count"]} lua51=compiled')
    print(package / 'report.json')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--output', type=Path, default=BUILD)
    parser.add_argument('--freeze', action='store_true', help='Freeze once; existing different inputs are refused')
    parser.add_argument('--journal', type=Path, default=RECOVERY_JOURNAL)
    parser.add_argument('--from-operation', type=Path, help='Freeze upgrade from installed completion operation')
    args = parser.parse_args()
    if args.freeze:
        if args.from_operation:
            io.need(args.journal == RECOVERY_JOURNAL, '--journal cannot be combined with --from-operation')
            freeze_upgrade(args.game, args.output, args.from_operation)
        else:
            freeze(args.game, args.output, args.journal)
        print('COMPLETION_INPUTS_FROZEN')
    else:
        io.need(args.journal == RECOVERY_JOURNAL and args.from_operation is None,
                '--journal and --from-operation are only supported with --freeze')
        build(args.game, args.output)
