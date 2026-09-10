"""Read native repeated markers, pinned code, and Stage A/A2. No game writes."""
import argparse
import collections
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load('shared_audit_base', HERE / 'build-raven-twin-stage-a-offline.py')
LUA = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
LUA_SHA = '67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b'
MARKER_FIELDS = [(0, 8, 'uID'), (8, 8, 'Icon relative pointer'),
                 (16, 4, 'LamsName'), (20, 4, 'LamsDescription'),
                 (24, 4, 'HeightOffset'), (28, 1, 'InitState'),
                 (29, 3, 'opaque gap'), (32, 8, 'Flags relative pointer'),
                 (40, 4, 'Flags count'), (44, 4, 'opaque gap'),
                 (48, 8, 'FastTravel'), (56, 4, 'Priority'),
                 (60, 4, 'Radius'), (64, 4, 'OffsetX'), (68, 4, 'OffsetY')]
COORD_FIELDS = [(0, 8, 'uID'), (8, 8, 'WadName relative pointer'),
                (16, 6, 'Position half3'), (22, 6, 'ForwardDir half3'),
                (28, 4, 'AdvanceRadiusMultiplier'), (32, 4, 'OverrideFuzzRadius'),
                (36, 4, 'InWorldMarkerDistance')]


def describe(dcb, row, fields, stride):
    at = row['offset']
    result = {k: v for k, v in row.items() if k != 'canonical'}
    result.update(data_offset=hex(at), file_offset=hex(dcb.file_base + at),
                  raw_hex=dcb.blob[at:at + stride].hex(),
                  fields={f'+0x{off:02X} {name}': dcb.blob[at+off:at+off+size].hex()
                          for off, size, name in fields},
                  pointer_targets={hex(p-at): hex(dcb.pointer(p))
                                   for p in sorted(dcb.relocations) if at <= p < at+stride})
    return result


def delta(a, z):
    return [f'0x{i:02X}' for i, (x, y) in enumerate(zip(a, z)) if x != y]


def audit(game):
    native = b.load_native_module()
    source_paths = {rel: game / rel for rel in b.FILES}
    source_paths[LUA] = game / LUA
    source_paths['GoW.exe'] = game / 'GoW.exe'
    hashes = {rel: b.sha_file(p) for rel, p in source_paths.items()}
    for rel, expected in {**b.FILES, LUA: LUA_SHA}.items():
        b.check(hashes[rel] == expected, f'Frozen source differs: {rel}')
    master = native.Dcb(source_paths['exec/dc/pc_le/mapmaster.dcb'])
    coords = native.Dcb(source_paths['exec/dc/pc_le/mapcoords.dcb'])
    markers = b.marker_snapshot(master)
    coordinates = b.coordinate_snapshot(coords)
    by_uid = {r['uid']: r for r in coordinates}
    b.check(len(by_uid) == len(coordinates), 'Coordinate UID collision')
    groups = collections.defaultdict(list)
    for row in markers:
        groups[row['icon']].append(row)
    logical = b.load_module('shared_audit_wad', HERE / 'build-raven-ui-logical-clone.py')
    wad = logical.parse_wad(source_paths['exec/wad/pc_le/r_ui.wad'].read_bytes())
    ui = source_paths['exec/dc/pc_le/wad_r_ui.dcb'].read_bytes()
    chunk = b.one_chunk(b.parse_dcb_chunks(ui), 12)
    _, pool, _ = b.dcb_rows(ui[chunk['start']:chunk['end']])
    repeated = []
    for icon, rows in groups.items():
        if len(rows) < 2:
            continue
        pairs = [(x, y) for i, x in enumerate(rows) for y in rows[i+1:]
                 if x['uid'] != y['uid'] and x['region'] == y['region']
                 and x['uid'] in by_uid and y['uid'] in by_uid]
        def pair_score(pair):
            x, y = pair
            a, z = by_uid[x['uid']], by_uid[y['uid']]
            return (len(delta(x['canonical'][8:], y['canonical'][8:])),
                    a['wad'] != z['wad'], len(delta(a['canonical'][22:], z['canonical'][22:])))
        best = min(pairs, key=pair_score) if pairs else None
        finals = [r for r in wad if r['kind'] == 1 and r['data'] and
                  r['flags'] == 0x3D and len(r['data']) == 164 and
                  r['name'].lower() == icon.lower()]
        item = {'loader': icon, 'folded_hash': f'{b.folded_name_hash(icon):016X}',
                'records': len(rows), 'distinct_uids': len({r['uid'] for r in rows}),
                'distinct_string_addresses': len({master.pointer(r['offset']+8) for r in rows}),
                'resource_definitions': [{'name': r['name'], 'id': r['id'].hex(),
                                          'payload_sha256': b.sha_bytes(bytes(r['data'])),
                                          'embedded_name': bytes(r['data'][28:84]).split(b'\0')[0].decode('ascii')}
                                         for r in finals],
                'pool_rows': [{'index': r['index'], 'capacity': r['capacity']}
                              for r in pool if r['uid'] == b.folded_name_hash(icon)],
                'field_variation': {f'+0x{off:02X} {name}': len({r['canonical'][off:off+size]
                                                               for r in rows})
                                    for off, size, name in MARKER_FIELDS
                                    if off not in (8, 32)},
                'flag_value_sets': sorted({tuple(r['flags']) for r in rows})}
        if best:
            x, y = best
            a, z = by_uid[x['uid']], by_uid[y['uid']]
            item['same_region_pair'] = {
                'markers': [describe(master, r, MARKER_FIELDS, 72) for r in best],
                'coordinates': [describe(coords, r, COORD_FIELDS, 40) for r in (a, z)],
                'marker_raw_different_offsets': delta(master.blob[x['offset']:x['offset']+72],
                                                      master.blob[y['offset']:y['offset']+72]),
                'marker_canonical_different_offsets': delta(x['canonical'], y['canonical']),
                'coordinate_canonical_different_offsets': delta(a['canonical'], z['canonical']),
                'flags_equal': x['flags'] == y['flags']}
        repeated.append(item)
    raven = next(r for r in markers if r['uid'] == f'{b.RAVEN_MARKER_UID:016X}')
    region_at = next(region for _, _, region, at in b.iter_markers(master) if at == raven['offset'])
    region_wads = [f'{master.unpack("<Q", at)[0]:016X}' for at in master.array(region_at+0x48, 8)]
    unprefixed = b.RAVEN_WAD.removeprefix('WAD_')
    region = {'data_offset': hex(region_at), 'raw_hex': master.blob[region_at:region_at+104].hex(),
              'marker_array_field': hex(region_at+0x38),
              'marker_array_target': hex(master.pointer(region_at+0x38)),
              'marker_count': len(master.array(region_at+0x38, 72)),
              'wad_array_qwords': region_wads,
              'coordinate_wad_string': b.RAVEN_WAD,
              'unprefixed_wad_name': unprefixed,
              'unprefixed_wad_folded_hash': f'{b.folded_name_hash(unprefixed):016X}',
              'unprefixed_wad_hash_present': f'{b.folded_name_hash(unprefixed):016X}' in region_wads}
    stages = {}
    for label in ('a', 'a2'):
        root = REPO / f'build/v0.10.4-raven-twin-stage-{label}/offline/candidate/game-root'
        stage_master = native.Dcb(root / 'exec/dc/pc_le/mapmaster.dcb')
        stage_coords = native.Dcb(root / 'exec/dc/pc_le/mapcoords.dcb')
        twin = next(r for r in b.marker_snapshot(stage_master) if r['uid'] == f'{b.TWIN_MARKER_UID:016X}')
        coord = next(r for r in b.coordinate_snapshot(stage_coords) if r['uid'] == twin['uid'])
        stages[label] = {'file_hashes': {rel: b.sha_file(root/rel) for rel in b.FILES},
                         'twin': describe(stage_master, twin, MARKER_FIELDS, 72),
                         'coordinate': describe(stage_coords, coord, COORD_FIELDS, 40),
                         'canonical_delta_from_raven': delta(raven['canonical'], twin['canonical'])}
    # Read Stage A2 history without changing checkout or old runtime reports.
    history_paths = ['tools/v0.10.4/build-raven-twin-stage-a2-offline.py',
                     'tools/v0.10.4/raven-twin-stage-a2-runtime.ps1',
                     'archive/field-logs/runtime-captures/raven-twin-stage-a2-20260910-125511/loader_log.txt',
                     'archive/field-logs/runtime-captures/raven-twin-stage-a2-20260910-125511/installed-file-hashes.json',
                     'archive/field-logs/runtime-captures/raven-twin-stage-a2-20260910-125511/transaction/active.json']
    history = {}
    for path in history_paths:
        raw = subprocess.check_output(['git', '-C', str(REPO), 'show', f'af65a172ad4df6d2f6fbe1e2a01e095777de679b:{path}'])
        entry = {'git_revision': 'af65a172ad4df6d2f6fbe1e2a01e095777de679b', 'sha256': b.sha_bytes(raw)}
        if path.endswith('loader_log.txt'):
            lines = raw.decode('utf-8-sig').splitlines()
            entry['original_raven_art_results'] = [line for line in lines if ' ART_RESULT ' in line]
            entry['twin_named_lines'] = [line for line in lines if b.TWIN_MARKER_NAME in line]
        history[path] = entry
    registry = load('shared_registry', HERE / 'inspect-map-class-registry.py')
    exe = source_paths['GoW.exe'].read_bytes()
    b.check(b.sha_bytes(exe) == registry.EXPECTED_EXE, 'Pinned executable differs')
    native_code = registry.executable_evidence(exe)
    pe = registry.Pe(exe)
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    native_code['additional_windows'] = []
    for start, size, label in ((0x761022, 0x97, 'marker UID linear scan'),
                               (0x7617FC, 0x31, 'coordinate UID linear scan; stride 0x28'),
                               (0x60EDED, 0x73, 'pool free/allocated/capacity guards')):
        raw = pe.read(start, size)
        native_code['additional_windows'].append({'rva': hex(start), 'bytes': size,
            'sha256': b.sha_bytes(raw), 'label': label,
            'instructions': [f'{i.address-registry.BASE:#x} {i.mnemonic} {i.op_str}'
                             for i in decoder.disasm(raw, registry.BASE+start)]})
    metadata = []
    for index in range(0x459A, 0x45EE):
        field = pe.read(0x1082030 + index * 32, 32)
        name, _, off, size, flags, _, parent = struct.unpack_from('<QQHHBBH', field)
        if parent in (0x409, 0x40A, 0x40F, 0x410, 0x413, 0x414, 0x415):
            metadata.append({'attribute': hex(index), 'type': hex(parent), 'offset': hex(off),
                             'size': size, 'kind': flags >> 2,
                             'name': pe.read(name-registry.BASE, 180).split(b'\0')[0].decode('ascii')})
    lua_text = source_paths[LUA].read_text(encoding='utf-8')
    lua_evidence = [{'line': i, 'text': line.strip()} for i, line in enumerate(lua_text.splitlines(), 1)
                    if any(token in line for token in ('local markerStates', 'tweaks.eTokenState.kDiscovered',
                           'mapUtil.MapMarkerInfoHasStates(markerInfo, markerStates)',
                           'Map.CreateMarkerIcon(', 'local candidate = "Completionist_V103',
                           'function MapOn:UpdateIcons', 'markerInfo.shown and',
                           'CompletionistMapV100_CreateMapPin = function'))]
    b.check(b.TWIN_MARKER_NAME not in lua_text, 'Unexpected Twin hook in frozen mapmenu')
    b.check({rel: b.sha_file(p) for rel, p in source_paths.items()} == hashes, 'Sources changed during audit')
    return {'result': 'RAVEN_SHARED_LOADER_FORENSIC_AUDIT', 'source_sha256': hashes,
            'runtime_facts_from_user': {'distinct_custom_ravens': 1, 'latest_stage_a_a2_crash': False,
                'dock_contamination': False, 'original_raven_works': True,
                'compass_add_replace_remove_work': True, 'distinct_twin_visible': False},
            'counts': {'markers': len(markers), 'unique_marker_uids': len({r['uid'] for r in markers}),
                       'coordinates': len(coordinates), 'unmatched_marker_uids': sorted({r['uid'] for r in markers}-set(by_uid))},
            'field_names_from_pinned_executable': metadata, 'native_repeated_loaders': repeated,
            'frozen_raven': {'marker': describe(master, raven, MARKER_FIELDS, 72),
                             'coordinate': describe(coords, by_uid[raven['uid']], COORD_FIELDS, 40),
                             'region': region},
            'stage_a_a2': stages, 'history': history,
            'native_code': native_code, 'frozen_mapmenu_gates': lua_evidence,
            'conclusions': [
                'Native distinct UIDs share loader text/hash and one WAD final definition. No per-instance resource is required.',
                'Native equal loader text occupies separate string addresses; pointer value is not resource identity. Native code hashes text.',
                'Some same-region marker pairs differ canonically only in UID; flags and all opaque bytes may be equal.',
                'Stage A/A2 Twin reaches region array and coordinate join offline; InitState remains 0 and frozen Lua only explicitly creates original Raven.',
                'Automatic map path gates CreateMarkerIcon by state and filter. Missing Twin creation is strongest supported blocker; no live Twin State capture exists.',
                'Shared Raven has one pool slot. Checkout returns null when no free instance and allocated count reaches capacity.',
                'Native duplicate GOPool rows add capacity for same resolved resource. Append same Raven hash/capacity 1 to preserve original row.',
                'Useful no-progression-write probe needs explicit Twin visual creation and one more pooled Raven instance; two DCB rows alone cannot establish two visible icons.'
            ],
            'ranked_uncertainty': [
                '1. Twin omitted by state gate / absent visual hook: source evidence strong, live Twin state not captured.',
                '2. Stage A2 dedicated resource may have further loader issues: untested because no Twin creation evidence; shared-loader probe removes this variable.',
                '3. Shared resource capacity exhaustion: proven future blocker for two live Raven objects with current capacity 1, not explanation for separate A2 pools.',
                '4. Position projection, lifecycle, or icon overlap: inspect live distinct objects and positions; 32 world metres does not prove screen separation.',
                '5. DCB ingest or UID lookup mismatch: offline array/join valid; live Twin lookup still required.'
            ], 'game_files_written': False, 'source_hashes_unchanged_after_audit': True}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game-root', type=Path, default=Path('G:/SteamLibrary/steamapps/common/GodOfWar'))
    ap.add_argument('--python-module-dir', type=Path, default=REPO/'dist/re-tools')
    args = ap.parse_args()
    sys.path.insert(0, str(args.python_module_dir.resolve()))
    report = audit(args.game_root.resolve())
    root = REPO/'archive/field-logs'
    b.write_bytes_atomic(root, root/'completionist-v104-raven-shared-loader-audit.json',
                         (json.dumps(report, indent=2)+'\n').encode(), 'forensic report')
    print(report['result'])
    print(json.dumps(report['counts']))
