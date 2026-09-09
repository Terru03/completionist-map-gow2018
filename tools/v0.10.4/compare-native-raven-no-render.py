"""Compare native Raven evidence read-only; reconstruct control only in ignored build/."""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILD = REPO / 'build/v0.10.4/native-raven-no-render'
ARCHIVE = REPO / 'archive/field-logs'
BRANCH = 'codex/v104-raven-hud-research'
HISTORICAL = {
    'mapmaster.dcb': '1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a',
    'mapcoords.dcb': '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb',
    'compassgraph.dcb': 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68',
}
LIVE = {
    'exec/dc/pc_le/mapmaster.dcb': 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f',
    'exec/dc/pc_le/mapcoords.dcb': '5d0b7591032d7b56581a0d77946c3fad4f0cbc1b9d245f3578407177c40bbe7d',
    'exec/dc/pc_le/compassgraph.dcb': 'c2fa6bab0c7c1dbe413a41f477a5e01ab396731fc6f6d611047a8bd346a56c5e',
    'exec/dc/pc_le/wad_r_perm.dcb': '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961',
    'exec/wad/pc_le/r_ui.wad': '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60',
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua': 'd101bb60807ad95919e42d92e3155ea9e7bda9c713bc1cad646b932d6f7c928d',
    'exec/boot-options.json': 'cd6018e5a911839135d7af2b8dca3caf4c064f200dd9f3e11057f93b065b5051',
    'GoW.exe': 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452',
}
PATCH_FILES = {
    'exec/patch/pc_le/completionist_v104_raven_map.texpack': '648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7',
    'exec/patch/pc_le/completionist_v104_raven_map.texpack.toc': '67cceea0d91298881f4426bf0ce5e8883da45a82905921313004df618d959053',
}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_info(path):
    if not path.is_file():
        return {'path': str(path), 'exists': False}
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'exists': True, 'bytes': path.stat().st_size, 'sha256': sha}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def ensure_closed():
    check(os.name == 'nt', 'Process gate requires Windows.')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { exit 9 }; exit 0"],
        capture_output=True, text=True, check=False)
    check(result.returncode == 0, 'Close God of War; process gate failed.')


def safe_output(path, tree, game):
    path, tree, game = path.resolve(), tree.resolve(), game.resolve()
    check(path != tree and path.is_relative_to(tree), f'Output must stay below {tree}')
    check(not path.is_relative_to(game), 'Output overlaps game tree.')
    check(not path.is_dir(), 'Output is directory.')
    check(not path.exists() or path.stat().st_nlink == 1, 'Output has hard links.')
    return path


def write_report(path, value, game):
    path = safe_output(path, ARCHIVE, game)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def runtime_evidence(text):
    """Keep manager evidence tied to request and API lifetime; never infer pixels."""
    lines = [line for line in text.splitlines() if '[CompletionistMap v0.10.3-native]' in line]
    attempts, active = [], None
    for line in lines:
        if 'NATIVE_RAVEN_API installed=true' in line:
            active = None
        if 'NATIVE_RAVEN_PREFLIGHT ' in line:
            active = {'preflight': line, 'show_before': False, 'lua_return_ok': False,
                      'request_claim_logged': False, 'manager_verified': False}
            attempts.append(active)
        if active is None:
            continue
        if 'NATIVE_RAVEN_SHOW stage=before' in line:
            active['show_before'] = True
        if 'NATIVE_RAVEN_SHOW stage=lua_return' in line:
            active['lua_return_ok'] = 'ok=true' in line
        if 'NATIVE_RAVEN_RESULT request_queued=true' in line:
            active['request_claim_logged'] = True
        if 'NATIVE_RAVEN_VERIFY active=true' in line and 'native_manager=true' in line:
            active['manager_verified'] = active['show_before'] and active['lua_return_ok']
    return {'lines': lines, 'attempts': attempts,
            'manager_verified_attempts': sum(a['manager_verified'] for a in attempts),
            'visual_readiness_proven': False,
            'note': 'pcall success and Lua active=true do not prove native worker success or rendering; absent verification is not a logged negative query.'}


def native_state(root, proof):
    native = proof.native
    dcbs = {name: native.Dcb(root / name) for name in HISTORICAL}
    master, coords, graph = [dcbs[n + '.dcb'] for n in ('mapmaster', 'mapcoords', 'compassgraph')]
    markers = []
    for realm, region, region_off, off in proof.iter_markers(master):
        raw = bytearray(master.blob[off:off + 0x48])
        raw[8:16] = b'\0' * 8
        raw[0x20:0x28] = b'\0' * 8
        markers.append({'id': f'{master.unpack("<Q", off)[0]:016X}',
            'realm': f'{realm:016X}', 'region': f'{region:016X}',
            'icon': master.string(off + 8), 'init_state': master.unpack('<B', off + 0x1C)[0],
            'lams_name': master.unpack('<I',off+0x10)[0], 'lams_description': master.unpack('<I',off+0x14)[0],
            'height_offset': master.unpack('<f',off+0x18)[0], 'fast_travel': f'{master.unpack("<Q",off+0x30)[0]:016X}',
            'priority': master.unpack('<I',off+0x38)[0], 'radius': master.unpack('<f',off+0x3C)[0],
            'offset_xy': master.unpack('<2f',off+0x40),
            'flags': [f'{master.unpack("<Q", f)[0]:016X}' for f in master.array(off + 0x20, 8)],
            'record_without_relative_pointers_hex': raw.hex(),
            'offset': off, 'region_marker_count': len(master.array(region_off + 0x38, 0x48))})
    positions = native.read_positions(coords, 'MAP_COORDS_PERM_DATA', 0x40A)
    helpers = native.read_positions(graph, 'COMPASS_HELPER_PERM_DATA', 0x40C, True)
    edges = [graph.unpack('<QQ', off) for off in graph.array(graph.root('COMPASS_GRAPH_EDGE_PERM_DATA', 0x40E), 0x10)]
    candidate = f'{proof.RAVEN_ID:016X}'
    return {'files': {name: d.inventory() for name, d in dcbs.items()},
        'counts': {'map_records': len(markers), 'coordinates': len(positions), 'helpers': len(helpers), 'edges': len(edges)},
        'candidate': {'markers': [m for m in markers if m['id'] == candidate],
            'coordinate': positions.get(proof.RAVEN_ID),
            'helper_with_candidate_id': helpers.get(proof.RAVEN_ID),
            'edges': [[f'{x:016X}' for x in pair] for pair in edges if proof.RAVEN_ID in pair]},
        'unresolved_endpoints': [f'{x:016X}' for x in sorted({x for pair in edges for x in pair} - (set(positions) | set(helpers)))],
        'all_markers': markers}, dcbs


def reconstruct(proof, game):
    stock_dir = REPO / 'build/v0.10.3-native-raven-dcb/stock-backup'
    stock = {}
    for name, sha in proof.EXPECTED.items():
        check(file_info(stock_dir / name).get('sha256') == sha, f'Historical stock backup mismatch: {name}')
        stock[name] = proof.native.Dcb(stock_dir / name)
    master, coords, graph = [stock[n + '.dcb'] for n in ('mapmaster', 'mapcoords', 'compassgraph')]
    transforms = {'mapmaster.dcb': proof.patch_mapmaster(master),
        'mapcoords.dcb': proof.patch_mapcoords(coords),
        'compassgraph.dcb': proof.patch_compassgraph(coords, graph)}
    folder = BUILD / 'historical'
    for name, (blob, relocs, _) in transforms.items():
        if name == 'mapmaster.dcb':
            matches = [i for i in range(0, len(blob) - 0x48 + 1, 8)
                       if struct.unpack_from('<Q', blob, i)[0] == proof.RAVEN_ID]
            check(len(matches) == 1, 'Historical Raven identity is not unique.')
            blob[matches[0] + 0x1C] = 0
        out = safe_output(folder / name, BUILD, game)
        proof.rebuild_dcb(stock[name], blob, relocs, out)
        check(file_info(out)['sha256'] == HISTORICAL[name], f'Historical reconstruction differs: {name}')
    return folder


def compare_native(game, proof):
    historical_dir = reconstruct(proof, game)
    old, old_dcb = native_state(historical_dir, proof)
    live, live_dcb = native_state(game / 'exec/dc/pc_le', proof)
    a, b = old_dcb['mapmaster.dcb'], live_dcb['mapmaster.dcb']
    differences = [i for i, (x, y) in enumerate(zip(a.blob, b.blob)) if x != y]
    old_marker = old['candidate']['markers'][0]
    icon_field = old_marker['offset'] + 8
    only_icon = (len(live['candidate']['markers']) == 1 and
        all(icon_field <= i < icon_field + 8 for i in differences) and
        b.blob[len(a.blob):] == b'goMapIconCompletionistRaven\0' and
        all(a.chunks[k][1] == b.chunks[k][1] for k in (11, 13, 14, 15)))
    changed_markers = []
    for before, after in zip(old.pop('all_markers'), live.pop('all_markers')):
        if before != after:
            changed_markers.append({'id': before['id'], 'fields': [k for k in before if before[k] != after[k]]})
    return {'historical': old, 'live': live,
        'mapmaster_changed_markers': changed_markers,
        'mapmaster_only_raven_icon_pointer_and_appended_string': only_icon,
        'mapmaster_changed_blob_offsets': [hex(i) for i in differences],
        'mapmaster_tail_bytes_added': len(b.blob) - len(a.blob),
        'note': 'WAD association lives in mapcoords, not mapmaster; zero unresolved graph endpoints does not check absent map identities.'}


def perm_context(stock_path, current_path):
    packed = load(HERE / 'build-packed-raven-compass-class.py')
    builder = load(HERE / 'build-raven-compass-hud-dcb-offline.py')
    stock_raw, raw = stock_path.read_bytes(), current_path.read_bytes()
    check(digest(stock_raw) == packed.EXPECTED, 'Stock packed DCB backup mismatch.')
    expected, _ = builder.build_candidate(stock_raw)
    chunks, old_chunks = packed.parse_chunks(raw), packed.parse_chunks(stock_raw)
    data, old_data = packed.one(chunks, 12)['payload'], packed.one(old_chunks, 12)['payload']
    exports = packed.parse_exports(packed.one(chunks, 13)['payload'])[1]
    old_exports = packed.parse_exports(packed.one(old_chunks, 13)['payload'])[1]
    uids = [e['uid'] for e in exports]
    sorted_ok = all(a < b for a, b in zip(uids, uids[1:]))
    lookup_errors, shifted_exports = [], 0
    for e in old_exports:
        index = bisect.bisect_left(uids, e['uid'])
        if index == len(exports) or exports[index]['uid'] != e['uid']:
            lookup_errors.append(e['name'])
            continue
        row = exports[index]
        expected_root = packed.shifted(e['root'])
        shifted_exports += expected_root != e['root']
        if row['name'] != e['name'] or row['type_id'] != e['type_id'] or row['root'] != expected_root:
            lookup_errors.append(e['name'])
    rels = packed.parse_relocations(packed.one(chunks, 15)['payload'], data)
    old_rels = packed.parse_relocations(packed.one(old_chunks, 15)['payload'], old_data)
    relocation_equal = len(rels) == len(old_rels) and all(
        b['field'] == packed.shifted(a['field']) and b['target'] == packed.shifted(a['target'])
        for a, b in zip(old_rels, rels))
    classes = []
    for e in exports:
        if e['type_id'] != 0x11E:
            continue
        root = e['root']
        icon, radius, world, scale = struct.unpack_from('<QQQf', data, root)
        old_e = next((a for a in old_exports if a['uid'] == e['uid']), None)
        classes.append({'name': e['name'], 'uid': f'{e["uid"]:016X}', 'index': e['index'],
            'root': hex(root), 'IconName': f'{icon:016X}', 'RadiusIconName': f'{radius:016X}',
            'InWorld_tMPIcon_Name': f'{world:016X}', 'IconScale': scale, 'IsMainQuest': bool(data[root + 28]),
            'stock_record_identical': None if old_e is None else data[root:root+32] == old_data[old_e['root']:old_e['root']+32]})
    return {'stock': file_info(stock_path), 'current': file_info(current_path),
        'matches_full_recomputed_candidate': raw == expected,
        'export_count_before': len(old_exports), 'export_count_after': len(exports),
        'uid_order_strict': sorted_ok, 'all_stock_binary_lookup_errors': lookup_errors,
        'shifted_stock_roots_checked': shifted_exports, 'relocation_entries_checked': len(rels),
        'relocation_sequence_targets_and_duplicate_multiplicity_preserved': relocation_equal,
        'chunks_11_14_35_unchanged': all(packed.one(chunks,k)['payload'] == packed.one(old_chunks,k)['payload'] for k in (11,14,35)),
        'classes': classes,
        'dock_inworld_export': [e for e in exports if e['uid']==0x0E24C47DE2F769CA],
        'dock_export_neighbors': exports[max(0, next(e['index'] for e in exports if e['name']=='DockPoint')-1):next(e['index'] for e in exports if e['name']=='DockPoint')+2],
        'runtime_lookup_model_source': 'build-packed-raven-compass-class-v2.py; native RVA 0x431B90',
        'limits': 'Static binary lookup model and full transform equivalence; no live cache or renderer inspection.'}


def wad_context(source_path, live_path):
    four = load(HERE / 'build-raven-compass-hud-four-payload.py')
    helper = four.BASE.load_helper()
    source_raw, raw = source_path.read_bytes(), live_path.read_bytes()
    expected, report = four.build_candidate(source_raw)
    records, source_records = helper.parse_wad(raw), helper.parse_wad(source_raw)
    account = four.accounting_snapshot(records)
    old_account = four.accounting_snapshot(source_records)
    payloads = helper.payload_records(records)
    population = Counter(struct.unpack_from('<I', r['data'])[0] for r in payloads if len(r['data']) >= 4)
    old_population = Counter(struct.unpack_from('<I', r['data'])[0] for r in helper.payload_records(source_records) if len(r['data']) >= 4)
    rows, base = [], 0
    for row in account['rows']:
        old_row = next(r for r in old_account['rows'] if r['key']==row['key'])
        rows.append({'type': hex(row['key']), 'base': row['base'], 'expected_base': base,
            'count': row['count'], 'payload_population': population[row['key']],
            'baseline_count': old_row['count'], 'baseline_payload_population': old_population[row['key']],
            'base_consistent': row['base'] == base,
            'count_delta_matches_payload_delta': row['count']-old_row['count']==population[row['key']]-old_population[row['key']],
            'absolute_population_check': (row['count']==population[row['key']]) if row['key'] in four.TYPE_INCREMENTS else None})
        base += row['count']
    def one(name, records=records):
        hits = [i for i,r in enumerate(records) if r['kind']==1 and r['data'] and r['name'].lower()==name.lower()]
        check(len(hits)==1, f'Expected unique WAD payload: {name}')
        return hits[0], records[hits[0]]
    names = [four.SOURCE_ROOT, four.SOURCE_PROTO, four.SOURCE_MODEL,
             four.SOURCE_MATERIAL, four.SOURCE_MESH, four.SHARED_COMPASS,
             four.RAVEN_MATERIAL, 'goMapIconCompletionistRaven', 'goProtoMapIconCompletionistRaven']
    resources = []
    for name in names:
        index, row = one(name)
        _, original = one(name, source_records)
        key = struct.unpack_from('<I', row['data'])[0]
        ordinal = sum(struct.unpack_from('<I', r['data'])[0] == key for r in records[:index] if r['kind']==1 and len(r['data'])>=4)
        type_row = next((r for r in account['rows'] if r['key']==key), None)
        resources.append({'name': name, 'id': row['id'].hex(), 'physical_index': index,
            'payload_sha256': digest(row['data']), 'record_equal_to_pre_hud': helper.record_bytes(row)==helper.record_bytes(original),
            'type': hex(key), 'type_ordinal': ordinal,
            'modeled_heap_index': None if type_row is None else type_row['base']+ordinal,
            'type_ordinal_in_range': None if type_row is None else ordinal < type_row['count']})
    ri, root = one(four.SOURCE_ROOT)
    pi, proto = one(four.SOURCE_PROTO)
    mi, model = one(four.SOURCE_MODEL)
    links = []
    for index, role in ((ri,'root'),(pi,'prototype'),(mi,'model')):
        group = four.hud.validate_hud_group(records,index,role)
        for row in records[group['start']:group['end']+1]:
            if row['kind']==1 and not row['data']:
                hits = [r for r in payloads if r['id']==row['id']]
                links.append({'from': role, 'name': row['name'], 'id': row['id'].hex(),
                    'definition_count': len(hits), 'definition_names': [r['name'] for r in hits]})
    root_hash_hits = [r['name'] for r in payloads if helper.name_hash(r['name'])==0x82F0296748C7393D]
    return {'pre_hud': file_info(source_path), 'current': file_info(live_path),
        'matches_full_recomputed_candidate': raw==expected, 'recomputed_validation': report['validation'],
        'heap_total_before': old_account['total'], 'heap_total_after': account['total'],
        'all_type_rows': rows, 'resources': resources, 'stock_dock_dependency_links': links,
        'stock_dock_root_name_hash_hits': root_hash_hits,
        'stock_root_to_prototype': bytes(root['data'][0x0C:0x1C])==proto['id'],
        'stock_root_to_shared_compass': bytes(root['data'][0x54:0x64])==one(four.SHARED_COMPASS)[1]['id'],
        'stock_prototype_self_id': bytes(proto['data'][0x3A8:0x3B8])==proto['id'],
        'limits': 'Resolved authored stock Dock chain and modeled Rig slots; runtime resource instantiation/GPU state unobserved. Model payload sits outside Rig table. First dword is not universal type population accounting; absolute checks limited to three traced HUD types, other rows compared by delta.'}


def manifest_inventory():
    paths = []
    for folder in (REPO / 'build').glob('v0.10.*'):
        if folder.is_dir():
            paths.extend(folder.glob('*.json'))
    paths.extend((REPO/'build/v0.10.4/raven-compass-hud-four-payload/runtime-install-backups').glob('*/*.json'))
    local = Path(os.environ.get('LOCALAPPDATA', '')) / 'CompletionistMap/state'
    paths.extend(local.glob('*/active.json'))
    output = []
    for path in sorted(set(paths)):
        entry = file_info(path)
        try:
            entry['content'] = read_json(path)
        except (ValueError, OSError) as error:
            entry['error'] = str(error)
        output.append(entry)
    return output


def classifications(comparison, sections):
    labels = {name: 'changed and plausibly causal' for name in
              ('mapcoords.dcb','compassgraph.dcb','mapmaster.dcb','wad_r_perm.dcb','r_ui.wad','mapmenu.lua','loader_log.txt')}
    labels['boot-options.json'] = 'unknown/unrecoverable'
    for name in HISTORICAL:
        actual = comparison.get('live',{}).get('files',{}).get(name,{}).get('sha256')
        if actual is None:
            labels[name] = 'unknown/unrecoverable'
        elif actual == HISTORICAL[name]:
            labels[name] = 'exact known-good equivalent'
    for file_name,section in (('wad_r_perm.dcb','packed_class'),('r_ui.wad','wad')):
        if sections.get(section,{}).get('unavailable'):
            labels[file_name] = 'unknown/unrecoverable'
    labels['mapmaster_non_icon_fields'] = ('exact known-good equivalent'
        if comparison.get('mapmaster_only_raven_icon_pointer_and_appended_string') is True or labels['mapmaster.dcb']=='exact known-good equivalent'
        else 'unknown/unrecoverable')
    perm = sections.get('packed_class', {})
    stock_classes = [c for c in perm.get('classes',[]) if c['name']!='CompletionistRaven']
    lookup_ok = (perm.get('matches_full_recomputed_candidate') is True and
                 perm.get('uid_order_strict') is True and perm.get('all_stock_binary_lookup_errors')==[] and
                 perm.get('relocation_sequence_targets_and_duplicate_multiplicity_preserved') is True and
                 perm.get('chunks_11_14_35_unchanged') is True and len(stock_classes)==9 and
                 all(c.get('stock_record_identical') is True for c in stock_classes))
    labels['DockPoint_record_and_static_lookup_contract'] = ('exact known-good equivalent' if lookup_ok else 'unknown/unrecoverable')
    return labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, default=Path('G:/SteamLibrary/steamapps/common/GodOfWar'))
    parser.add_argument('--output', type=Path, default=ARCHIVE/'completionist-v104-native-raven-no-render-comparison.json')
    args = parser.parse_args()
    game = args.game_root.resolve()
    safe_output(args.output, ARCHIVE, game)
    ensure_closed()
    proof = load(HERE.parent/'v0.10.3/build-native-raven-dcb-proof.py')
    inventory = {path: file_info(game/path) for path in [*LIVE, 'mods/loader_log.txt']}
    boot = read_json(game/'exec/boot-options.json')
    patches = []
    for entry in boot.get('patch-texpacks', []):
        # Resolve from exec/wad/pc_le; same path used by patch-loading tools.
        prefix = (game/'exec/wad/pc_le'/entry).resolve()
        check(prefix.is_relative_to(game/'exec/patch'), 'Unexpected patch prefix outside game patch tree.')
        for suffix in ('.texpack', '.texpack.toc'):
            patches.append(file_info(Path(str(prefix)+suffix)))
    comparison = compare_native(game, proof)
    backup_dir = REPO/'build/v0.10.4/raven-compass-hud-four-payload/runtime-install-backups/20260908-203244'
    sections = {}
    for key, fn in [('packed_class', lambda: perm_context(backup_dir/'wad_r_perm.dcb.before-raven-hud',game/'exec/dc/pc_le/wad_r_perm.dcb')),
                    ('wad', lambda: wad_context(backup_dir/'r_ui.wad.before-raven-hud',game/'exec/wad/pc_le/r_ui.wad'))]:
        try:
            sections[key] = fn()
        except (ValueError, OSError, KeyError) as error:
            sections[key] = {'unavailable': str(error)}
    archive_path = ARCHIVE/'completionist-v104-native-raven-route-reproof.txt'
    archive = archive_path.read_text(encoding='utf-8-sig') if archive_path.exists() else ''
    runtime = runtime_evidence(archive)
    log_runtime = runtime_evidence((game/'mods/loader_log.txt').read_text(encoding='utf-8-sig', errors='replace'))
    maptext = (game/'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua').read_bytes().replace(b'\r\n',b'\n')
    bridge = (HERE.parent/'v0.10.3/native-raven-production.lua').read_bytes().replace(b'\r\n',b'\n').rstrip(b'\n')
    known = (REPO/'build/v0.10.3-native-show/mapmenu-before-native-show.lua').read_bytes()
    show = (HERE.parent/'v0.10.3/native-compass-show-probe.lua').read_bytes()
    reconstructed_lua = known + b'\r\n' + show + b'\r\n'
    state = comparison['live']['candidate']
    missing = len(state['markers']) == 1 and state['coordinate'] is None and not state['edges']
    bad_runtime = any('wad=nil x=0 y=0 z=0' in a['preflight'] for a in runtime['attempts'])
    result = 'ROOT_CAUSE_NARROWED_NOT_PROVEN' if missing and bad_runtime else 'EVIDENCE_INSUFFICIENT'
    preserved = {k:v['sha256'] for k,v in inventory.items() if k not in ('mods/loader_log.txt','exec/dc/pc_le/mapcoords.dcb','exec/dc/pc_le/compassgraph.dcb') and v.get('exists')}
    report = {'schema': 1, 'result': result, 'captured_utc': datetime.now(timezone.utc).isoformat(),
        'branch': subprocess.check_output(['git','-C',str(REPO),'branch','--show-current'],text=True).strip(),
        'analysis_head': subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        'pulled_start_head': '5673e50043e8427abd318fdd56d7a40c4404a4eb',
        'inventory': inventory, 'task_dcb_path_correction': 'DCBs reside in exec/dc/pc_le; exec/wad/pc_le DCB names checked separately.',
        'task_spelling_paths': {n: file_info(game/'exec/wad/pc_le'/n) for n in [*HISTORICAL,'wad_r_perm.dcb']},
        'boot_build_info': boot.get('build-info'), 'active_patch_entries': boot.get('patch-texpacks'), 'patch_files': patches,
        'native_comparison': comparison, **sections,
        'runtime_archive': {**file_info(archive_path), **runtime}, 'current_loader_native_lines': log_runtime,
        'archive_native_lines_match_live_log': runtime['lines']==log_runtime['lines'] and bool(runtime['lines']),
        'lua': {'historical_reconstructed_sha256': digest(reconstructed_lua),
            'historical_manifest_sha256': '79ad424da5e0813ad20f11b3c27bb4cc22e6910a404353a6a5bec4edd39e0068',
            'historical_exact_reconstruction': digest(reconstructed_lua)=='79ad424da5e0813ad20f11b3c27bb4cc22e6910a404353a6a5bec4edd39e0068',
            'current_ends_with_exact_production_bridge_normalized_eol': maptext.rstrip(b'\n').endswith(bridge),
            'bridge_occurrences': maptext.count(b'BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'),
            'preflight_limit': 'Checks flag and Coordinates non-nil; does not check WAD, XYZ or compass node/graph membership.'},
        'manifests': manifest_inventory(),
        'classification': classifications(comparison, sections),
        'classification_limit': 'Whole-file HUD/Lua changes not proven unrelated by static invariance. Historical whole WAD/boot snapshot not bound to successful session; pre-HUD backup is later v104 baseline.',
        'ab_control': {'prepared_not_installed': True, 'specific_subsystem': 'native mapcoords/compassgraph identity join',
            'eligible': missing and bad_runtime and comparison['mapmaster_only_raven_icon_pointer_and_appended_string'] and all(inventory[k].get('sha256')==v for k,v in LIVE.items()),
            'sources': {n: str(BUILD/'historical'/n) for n in ('mapcoords.dcb','compassgraph.dcb')},
            'before': {n: proof.EXPECTED[n] for n in ('mapcoords.dcb','compassgraph.dcb')},
            'after': {n: HISTORICAL[n] for n in ('mapcoords.dcb','compassgraph.dcb')},
            'preserved': preserved, 'patch_files': patches},
        'safety': {'game_launched': False, 'game_files_written': False, 'saves_or_progression_accessed': False,
            'runtime_test_performed': False}}
    ensure_closed()
    report['safety']['inventory_unchanged_during_analysis'] = all(file_info(game/p)==info for p,info in inventory.items())
    check(report['safety']['inventory_unchanged_during_analysis'], 'Game input changed during analysis.')
    check(all(file_info(Path(p['path']))==p for p in patches), 'Patch input changed during analysis.')
    write_report(args.output, report, game)
    print(json.dumps({'result': result, 'missing_coordinate_and_edge': missing,
        'manager_verified_attempts': runtime['manager_verified_attempts'],
        'mapmaster_icon_only': comparison['mapmaster_only_raven_icon_pointer_and_appended_string'],
        'class_rebuild_equal': sections['packed_class'].get('matches_full_recomputed_candidate'),
        'wad_rebuild_equal': sections['wad'].get('matches_full_recomputed_candidate'),
        'ab_eligible': report['ab_control']['eligible'], 'report': str(args.output)},indent=2))


if __name__ == '__main__':
    main()
