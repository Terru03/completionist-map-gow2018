"""Read bounded checkpoint bytes. Keep chest evidence; never write game state."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import struct
import sys
import time
import unittest

import staged_wad_bitstream as bits

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE_SHA = 'fcf82fcfe96b415aba558f6cbd60c8f1119192209fdd2c4a7e5a00cf58433b5c'
MAX_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOTS = 128
MAX_OBSERVATIONS = 610
MAX_DECODE_RECORDS = 256
MAX_DECODE_BYTES = 32 * 1024 * 1024
STATE_TOKENS = {'010000803f': 1, '0100000040': 2, '0100004040': 3, '0100008040': 4}


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def helpers():
    path = HERE / 'capture-staged-wad-bitstream-raven-state-readonly.py'
    spec = importlib.util.spec_from_file_location('_chest_snapshot', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_catalogue():
    raw = (REPO / 'catalogue/legendary-chest-authority.json').read_bytes()
    if digest(raw) != CATALOGUE_SHA:
        raise ValueError('Pinned chest catalogue hash differs')
    rows = json.loads(raw)['rows']
    if len(rows) != 33 or len({r['catalogue_id'] for r in rows}) != 33 or len({r['serialized_key'] for r in rows}) != 33:
        raise ValueError('Need 33 unique chest keys')
    for row in rows:
        key = b'\x01' + struct.pack('<QQ', int(row['registry_hash'], 16), int(row['object_hash'], 16))
        if key.hex() != row['serialized_key']:
            raise ValueError('Chest registry/object key differs')
    return rows


def inspect_payload(payload, lua_length, rows):
    states = {row['catalogue_id']: None for row in rows}
    errors = []
    try:
        if not 0 < lua_length <= bits.MAX_CARRIER_BYTES:
            raise ValueError('No bounded cached Lua length')
        result = bits.extract_channel_a(payload, None, {}, expected_lua_length=lua_length)
        if result['ambiguity_reasons'] or len(result['candidates']) != 1:
            raise ValueError('Need one unambiguous carrier graph')
        candidate = result['candidates'][0]
        bit = candidate['bit_offset']
        aligned = bits._aligned_bytes(payload[2:], bit % 8)
        start = bit // 8
        raw = aligned[start:start + lua_length]
        module = bits._decoder()
        decoded, consumed = module.decompress_stream(raw, 16)
        parses = bits._decode_paths(module, raw, decoded, consumed, None, {})
        if len(parses) != 1:
            raise ValueError('Graph parse ambiguous')
        parsed = parses[0]
        header = struct.unpack_from('<8H', raw)
        end = 16 + consumed + 2 * header[0] + sum(token['width'] for token in parsed['token_parse'])
        sizes = raw[end:end + header[4]]
        offsets = struct.unpack_from(f'<{header[4]}H', raw, end + header[4])
        blob = decoded[header[1]:header[1] + header[5]]
        records = [blob[offset:offset + size] for offset, size in zip(offsets, sizes)]
        tokens = parsed['token_parse']
        pairs = list(zip(tokens[::2], tokens[1::2]))
        wanted = {row['serialized_key']: row['catalogue_id'] for row in rows}
        if len(wanted) != len(rows):
            raise ValueError('Duplicate catalogue key')
        found = set()

        def row_pairs(index):
            row = parsed['rows'][index]
            return pairs[row['first_pair']:row['first_pair'] + row['pair_count']]

        for subrow in parsed['subobj_table_rows']:
            for key, value in row_pairs(subrow):
                if key['tag'] != 5:
                    continue
                saved = records[key['payload']]
                rid = wanted.get(saved[8:].hex())
                if rid is None:
                    continue
                if rid in found:
                    raise ValueError('Duplicate exact chest record')
                found.add(rid)
                if int.from_bytes(saved[:8], 'little') != 0x75E050AB149B4062 or value['tag'] != 3:
                    raise ValueError('Exact chest class or state table invalid')
                state = [v for k, v in row_pairs(value['payload'] - 1)
                         if k['tag'] == 2 and parsed['strings'][k['payload']] == 'state']
                if len(state) != 1 or state[0]['raw_hex'] not in STATE_TOKENS:
                    raise ValueError('Chest state missing, duplicate, or unknown')
                states[rid] = STATE_TOKENS[state[0]['raw_hex']]
    except (ValueError, RuntimeError, IndexError, KeyError, TypeError, struct.error) as exc:
        states = dict.fromkeys(states)
        errors.append(str(exc))
    return {'states': states, 'errors': errors}


def inspect_snapshot(layout, table, pool, rows):
    states = {row['catalogue_id']: None for row in rows}
    errors = []
    try:
        helper = helpers()
        obs = helper.load_observer()
        records = helper.channel_a_records(layout, table, pool, obs)
        relevant = [(record, payload) for record, payload in records
                    if helper.normal_wad_name(record['name']) in {r['wad'] for r in rows}]
        if len(relevant) > MAX_DECODE_RECORDS or sum(len(p) for _, p in relevant) > MAX_DECODE_BYTES:
            raise ValueError('Snapshot decode work cap')
        seen = set()
        for record, payload in relevant:
            if not payload:
                continue
            wad = helper.normal_wad_name(record['name'])
            if wad in seen:
                raise ValueError('Duplicate staged chest WAD')
            seen.add(wad)
            got = inspect_payload(payload, record['cached_channel_a_lua_length'], [r for r in rows if r['wad'] == wad])
            errors.extend(f"record {record['index']}: {e}" for e in got['errors'])
            states.update(got['states'])
    except (ValueError, RuntimeError, struct.error) as exc:
        errors.append(str(exc))
    if errors:
        states = dict.fromkeys(states)
    return {'states': states, 'errors': errors}


def verify_observations(observations, selected_id):
    result = {'transition_observed': False, 'checkpoint_observed': False, 'reload_observed': False,
              'classification': 'inconclusive', 'changed_observed_chests': [], 'reasons': [],
              'persistence_provenance': 'manual phase labels; no automated save identity or disk-save check'}
    if not observations or any(o.get('errors') for o in observations):
        result['reasons'].append('Missing observations or parse/capture errors')
        return result
    identity = observations[0]['identity']
    if any(o['identity'] != identity for o in observations):
        result['reasons'].append('Process/session identity changed')
        return result
    phases = [o['phase'] for o in observations]
    order = {'before': 0, 'open': 1, 'checkpoint': 2, 'reload': 3}
    if phases[0] != 'before' or phases.count('before') != 1 or any(p not in order for p in phases) or [order[p] for p in phases] != sorted(order[p] for p in phases):
        result['reasons'].append('Phase order invalid')
        return result
    before = observations[0]['states'].get(selected_id)
    previous = {}
    for index, observation in enumerate(observations):
        for rid, state in observation['states'].items():
            if state is not None and rid in previous and previous[rid] != state:
                result['changed_observed_chests'].append({'catalogue_id': rid, 'from': previous[rid], 'to': state,
                                                          'phase': observation['phase'], 'observation': index})
            if state is not None:
                previous[rid] = state
        state = observation['states'].get(selected_id)
        if result['transition_observed'] and state in (1, 2, 3):
            result.update(transition_observed=False, checkpoint_observed=False, reload_observed=False)
            result['reasons'].append('Selected opened state reverted; session/checkpoint conflict')
            return result
        if before in (1, 2, 3) and state == 4 and observation['phase'] in ('open', 'checkpoint'):
            result['transition_observed'] = True
        if result['transition_observed'] and state == 4 and observation.get('manual_provenance') == 'user_confirmed_same_save':
            if observation['phase'] == 'checkpoint':
                result['checkpoint_observed'] = True
            if observation['phase'] == 'reload' and result['checkpoint_observed']:
                result['reload_observed'] = True
    if result['transition_observed']:
        result['classification'] = 'exact_staged_state_transition_observed'
    else:
        result['reasons'].append('Need selected exact state 1/2/3 before and 4 after; missing or unchanged checkpoint stays unknown')
    return result


def checked_path(path):
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Output path contains symlink/reparse point')


def new_output(repo, name, protected_roots=()):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name) or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])', name):
        raise ValueError('Output name must be one plain build folder name')
    root = repo.absolute()
    out = root / 'build' / name
    checked_path(out)
    save_roots = (Path.home() / 'Saved Games', Path.home() / 'Documents/My Games')
    if any(out.resolve().is_relative_to(Path(folder).resolve()) for folder in (*save_roots, *protected_roots)):
        raise ValueError('Output cannot lie under game/save folder')
    if out.exists():
        raise ValueError('Output folder must be new')
    (root / 'build').mkdir(exist_ok=True)
    out.mkdir()
    return out


class Recorder:
    def __init__(self, out, identity, max_bytes=MAX_BYTES):
        self.out, self.identity, self.max_bytes = out, dict(identity), max_bytes
        self.snapshots, self.observations = [], []
        self.bytes = 0
        self.keys = {}

    def add(self, sample, phase):
        if sample['identity'] != self.identity:
            raise ValueError('Process/session identity changed')
        if len(self.observations) >= MAX_OBSERVATIONS:
            raise ValueError('Observation cap')
        table, pool, layout = sample['table'], sample['pool'], list(sample['layout'])
        key = (tuple(layout), digest(table), digest(pool))
        if key not in self.keys:
            if len(self.snapshots) >= MAX_SNAPSHOTS or self.bytes + len(table) + len(pool) > self.max_bytes:
                raise ValueError('Raw capture disk/snapshot cap')
            index = len(self.snapshots)
            entry = {'layout': layout, 'table_file': f'{index:04d}-table.bin', 'pool_file': f'{index:04d}-pool.bin',
                     'table_sha256': key[1], 'pool_sha256': key[2], 'table_bytes': len(table), 'pool_bytes': len(pool)}
            checked_path(self.out)
            for kind, raw in (('table', table), ('pool', pool)):
                with (self.out / entry[f'{kind}_file']).open('xb') as stream:
                    stream.write(raw)
            self.bytes += len(table) + len(pool)
            self.keys[key] = index
            self.snapshots.append(entry)
        self.observations.append({'phase': phase, 'captured_utc': utc(), 'monotonic_ns': time.monotonic_ns(),
                                  'snapshot_index': self.keys[key], 'identity': dict(self.identity),
                                  'manual_provenance': 'user_confirmed_same_save'})


def read_snapshot(out, entry):
    values = []
    for kind in ('table', 'pool'):
        name = entry[f'{kind}_file']
        if not re.fullmatch(r'\d{4}-(?:table|pool)\.bin', name):
            raise ValueError('Invalid raw snapshot filename')
        path = out / name
        checked_path(path)
        expected = entry[f'{kind}_bytes']
        if not 0 <= expected <= 2 * 1024 * 1024 or path.stat().st_size != expected:
            raise ValueError('Raw snapshot size differs')
        raw = path.read_bytes()
        if digest(raw) != entry[f'{kind}_sha256']:
            raise ValueError('Raw snapshot hash differs')
        values.append(raw)
    return entry['layout'], *values


def open_read_only(kernel, pid):
    handle = kernel.OpenProcess(0x0010 | 0x0400, False, pid)
    if not handle:
        raise RuntimeError('OpenProcess read-only failed')
    return handle


class LiveReader:
    def __init__(self):
        if sys.platform != 'win32' or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError('64-bit Windows required')
        self.helper = helpers()
        self.obs = self.helper.load_observer()
        self.kernel = self.obs.k32_api()
        self.pid, name = self.obs.find_process(self.kernel)
        self.base, exe = self.obs.main_module(self.kernel, self.pid, name)
        exe_sha = self.obs.sha256_file(Path(exe))
        if exe_sha != self.obs.EXE_SHA:
            raise RuntimeError('Unsupported game executable hash')
        self.handle = open_read_only(self.kernel, self.pid)
        try:
            self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            self.kernel.GetProcessTimes.restype = wintypes.BOOL
            self.identity = {'pid': self.pid, 'creation_filetime': self.creation_time(), 'exe_sha256': exe_sha,
                             'module_base': self.base, 'exe_path': exe}
        except BaseException:
            self.close()
            raise

    def creation_time(self):
        values = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(self.handle, *(ctypes.byref(v) for v in values)):
            raise RuntimeError('Cannot read process creation identity')
        if values[1].dwLowDateTime or values[1].dwHighDateTime:
            raise RuntimeError('Game process exited')
        return values[0].dwLowDateTime | (values[0].dwHighDateTime << 32)

    def snapshot(self):
        if self.creation_time() != self.identity['creation_filetime']:
            raise RuntimeError('Process identity changed')
        layout, table, pool = self.helper.snapshot(lambda address, size: self.obs.read(self.kernel, self.handle, address, size), self.base, self.obs)
        self.creation_time()
        return {'identity': self.identity, 'layout': layout, 'table': table, 'pool': pool}

    def close(self):
        self.obs.close(self.kernel, self.handle)


def write_json(out, name, value):
    checked_path(out)
    with (out / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def source_hashes():
    paths = [Path(__file__), HERE / 'capture-legendary-opening-readonly.py', HERE / 'staged_wad_bitstream.py',
             HERE / 'decode-active-raven-subobject-state.py', HERE / 'capture-staged-wad-bitstream-raven-state-readonly.py',
             HERE / 'capture-staged-wad-raven-state-readonly.py', REPO / 'catalogue/legendary-chest-authority.json']
    return {str(p.relative_to(REPO)): digest(p.read_bytes()) for p in paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read chest checkpoint bytes. No game/save writes.')
    parser.add_argument('--chest')
    parser.add_argument('--output-name')
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--interval', type=float, default=0.25)
    parser.add_argument('--reload', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_chest_open_capture.py')
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    live, recorder, out = None, None, None
    errors = []
    try:
        rows = load_catalogue()
        if args.list:
            for row in rows:
                print(f"{row['catalogue_id']}  {row['wad']}  {row['world_position']}")
            return 0
        if args.chest not in {r['catalogue_id'] for r in rows} or not args.output_name:
            raise ValueError('Use --list; then set --chest and new --output-name')
        if not 1 <= args.seconds <= 60 or not 0.1 <= args.interval <= 5:
            raise ValueError('Seconds must be 1..60; interval 0.1..5')
        live = LiveReader()
        game_root = [Path(live.identity['exe_path']).parent] if 'exe_path' in live.identity else []
        out = new_output(REPO, args.output_name, protected_roots=game_root)
        recorder = Recorder(out, live.identity)
        write_json(out, 'session.json', {'schema': 1, 'started_utc': utc(), 'selected_chest': next(r for r in rows if r['catalogue_id'] == args.chest),
                                       'identity': live.identity, 'source_sha256': source_hashes(), 'args': vars(args),
                                       'safety': {'process_access': 'PROCESS_VM_READ|PROCESS_QUERY_INFORMATION', 'access_mask': '0x410',
                                                  'game_launched': False, 'game_memory_written': False, 'save_opened': False}})
        input('Stand by unopened chosen chest. Keep same save throughout. Press Enter for BEFORE: ')
        recorder.add(live.snapshot(), 'before')
        input('Press Enter, switch to game, open chosen chest now. Sampling starts: ')
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            try:
                recorder.add(live.snapshot(), 'open')
            except RuntimeError as exc:
                errors.append({'phase': 'open', 'captured_utc': utc(), 'error': str(exc)})
            time.sleep(args.interval)
        input('Wait for natural checkpoint on SAME save. Press Enter once done: ')
        recorder.add(live.snapshot(), 'checkpoint')
        if args.reload:
            input('Reload SAME save in game; keep game process running. Press Enter once loaded: ')
            recorder.add(live.snapshot(), 'reload')
    except (ValueError, RuntimeError, OSError, EOFError, KeyboardInterrupt) as exc:
        errors.append({'phase': 'capture', 'captured_utc': utc(), 'error': str(exc) or 'interrupted'})
    finally:
        if live:
            live.close()
    if recorder:
        write_json(out, 'capture.json', {'schema': 1, 'snapshots': recorder.snapshots, 'observations': recorder.observations, 'errors': errors})
        print('Raw capture done. Decode runs now; game state untouched.')
        decoded = [inspect_snapshot(*read_snapshot(out, entry), rows) for entry in recorder.snapshots]
        observations = [{**item, **decoded[item['snapshot_index']]} for item in recorder.observations]
        report = verify_observations(observations, args.chest)
        if errors:
            report.update(transition_observed=False, checkpoint_observed=False, reload_observed=False, classification='inconclusive')
            report['reasons'].append('Capture errors; see capture.json')
        report.update(schema=1, selected_id=args.chest, observations=observations, production_ready=False,
                      limits={'raw_bytes': MAX_BYTES, 'snapshots': MAX_SNAPSHOTS, 'observations': MAX_OBSERVATIONS},
                      limitations=['Equal double reads are not atomic.', 'Staged checkpoint table may lag live chest state.',
                                   'No arbitrary memory scan. Missing object means unknown.',
                                   'Same save/checkpoint/reload labels come from user; no save identity read.',
                                   'Nested carrier extraction remains candidate framing; enclosing field traversal unproved.'])
        write_json(out, 'report.json', report)
        print(f"{report['classification']} — evidence: {out}")
    for error in errors:
        print(f"Capture stopped: {error['error']}", file=sys.stderr)
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
