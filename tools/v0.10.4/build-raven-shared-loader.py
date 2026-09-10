"""Build shared-loader Twin offline from frozen Raven. No real game writes."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('shared_base', HERE/'build-raven-twin-stage-a-offline.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
# Private module copy. Reuse only proven DCB append code; never call WAD builder.
b.TWIN_MAP_GO = b.RAVEN_MAP_GO
MASTER = 'exec/dc/pc_le/mapmaster.dcb'
COORDS = 'exec/dc/pc_le/mapcoords.dcb'
UI = 'exec/dc/pc_le/wad_r_ui.dcb'
LUA = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
FILES = {MASTER: b.FILES[MASTER], COORDS: b.FILES[COORDS], UI: b.FILES[UI],
         LUA: '67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b'}
BRANCH = 'codex/v104-raven-shared-loader-twin'
BASE_HEAD = '8abf20bafe4534c798daa62d2ef5a70c50ecb056'
RESULT = 'RAVEN_SHARED_LOADER_OFFLINE_PROOF_PASSED'
OUTPUT = REPO/'build/v0.10.4-raven-shared-loader/offline/candidate/game-root'
REPORT = REPO/'archive/field-logs/completionist-v104-raven-shared-loader-offline.json'


def parse(raw, name):
    return b.parse_native_candidate(b.load_native_module(), Path(name), raw)


def validate_append(source, candidate, kind):
    marker = kind == 'marker'
    snapshot = b.marker_snapshot if marker else b.coordinate_snapshot
    stride = 72 if marker else 40
    pointers = (8, 32) if marker else (8,)
    old, new = snapshot(source), snapshot(candidate)
    raven_uid, twin_uid = (f'{uid:016X}' for uid in (b.RAVEN_MARKER_UID, b.TWIN_MARKER_UID))
    b.check(not any(r['uid'] == twin_uid for r in old), 'Twin already exists')
    twins = [r for r in new if r['uid'] == twin_uid]
    b.check(len(new) == len(old)+1 and len(twins) == 1, 'Append count or Twin UID differs')
    twin = twins[0]
    donor = next(r for r in old if r['uid'] == raven_uid)
    if marker:
        region = next(reg for _, _, reg, at in b.iter_markers(source) if at == donor['offset'])
        field = region+0x38
        b.check((twin['realm'], twin['region'], twin['icon'], twin['flags']) ==
                (donor['realm'], donor['region'], donor['icon'], donor['flags']), 'Twin owner/loader/flags differ')
    else:
        field = source.root('MAP_COORDS_PERM_DATA', 0x40A)
        b.check(twin['wad'] == donor['wad'] and tuple(twin['position']) == b.TWIN_POSITION,
                'Twin coordinate differs')
    old_array = list(source.array(field, stride))
    new_array = list(candidate.array(field, stride))
    b.check(len(new_array) == len(old_array)+1 and new_array[-1] == twin['offset'], 'Array ownership differs')
    b.check(new_array[0] == (len(source.blob)+15) & ~15, 'Append start differs')
    b.check(candidate.blob[len(source.blob):new_array[0]] == bytes(new_array[0]-len(source.blob)), 'Append padding differs')
    prefix = bytearray(candidate.blob[:len(source.blob)])
    prefix[field:field+12] = source.blob[field:field+12]
    b.check(bytes(prefix) == source.blob, 'Original bytes changed outside array pointer/count')
    # Compare every active original row, not just dead copies at old offsets.
    survivors = [r for r in new if r['uid'] != twin_uid]
    expected_relocations = set(source.relocations)
    for before, after in zip(old, survivors):
        keys = ('uid', 'canonical', 'realm', 'region', 'icon', 'flags') if marker else ('uid', 'canonical', 'wad', 'position')
        b.check(all(before[k] == after[k] for k in keys), 'Active original record differs')
        for offset in pointers:
            sf, df = before['offset']+offset, after['offset']+offset
            sd, dd = source.unpack('<q', sf)[0], candidate.unpack('<q', df)[0]
            b.check((sf+sd if sd else None) == (df+dd if dd else None), 'Active original pointer target differs')
            expected_relocations.add(df)
    expected = bytearray(donor['canonical'])
    struct.pack_into('<Q', expected, 0, b.TWIN_MARKER_UID)
    if not marker:
        struct.pack_into('<3e', expected, 16, *b.TWIN_POSITION)
    b.check(bytes(expected) == twin['canonical'], 'Twin opaque/scalar bytes differ')
    for offset in pointers:
        expected_relocations.add(twin['offset']+offset)
        if marker and offset == 8:
            continue
        sf, df = donor['offset']+offset, twin['offset']+offset
        sd, dd = source.unpack('<q', sf)[0], candidate.unpack('<q', df)[0]
        b.check((sf+sd if sd else None) == (df+dd if dd else None), 'Twin inherited pointer target differs')
    b.check(candidate.relocations == expected_relocations, 'Relocation set differs')
    relocation_payload = struct.pack(f'<I{len(expected_relocations)}I', len(expected_relocations), *sorted(expected_relocations))
    b.check(candidate.chunks[15][1] == relocation_payload, 'Serialized relocation order/count differs')
    for chunk in b.parse_dcb_chunks(candidate.raw):
        b.check(candidate.raw[chunk['end']:chunk['padded']] == bytes(chunk['padded']-chunk['end']), 'DCB chunk padding differs')
    tail = new_array[-1]+stride
    expected_tail = (b.RAVEN_MAP_GO.encode()+b'\0') if marker else b''
    b.check(candidate.blob[tail:] == expected_tail, 'Unexpected appended payload')
    if marker:
        b.check(candidate.pointer(twin['offset']+8) == tail, 'Twin loader pointer differs')
    normalized = b.rebuild_dcb_bytes(candidate, prefix, set(source.relocations))
    b.check(normalized == source.raw, 'Inverse is not exact frozen DCB')
    return {'source_records': len(old), 'candidate_records': len(new),
            'array_field': hex(field), 'old_array_count': len(old_array), 'new_array_count': len(new_array),
            'old_array_target': hex(old_array[0]), 'new_array_target': hex(new_array[0]),
            'source_relocations': len(source.relocations), 'candidate_relocations': len(candidate.relocations),
            'new_relocation_fields': [hex(p) for p in sorted(candidate.relocations-source.relocations)],
            'original_prefix_unchanged_except_array_12_bytes': True,
            'active_original_records_and_pointer_targets_exact': True,
            'twin_opaque_bytes_exact': True, 'normalized_to_frozen_raven_exact': True}


def build_pool(source):
    b.check(b.sha_bytes(source) == FILES[UI], 'Frozen pool source differs')
    chunk = b.one_chunk(b.parse_dcb_chunks(source), 12)
    data = bytearray(source[chunk['start']:chunk['end']])
    count, rows, end = b.dcb_rows(data)
    raven = [r for r in rows if r['uid'] == b.RAVEN_MAP_HASH]
    b.check(count == 257 and len(raven) == 1 and raven[0]['capacity'] == 1, 'Frozen Raven pool differs')
    b.check(struct.unpack_from('<q', data, 16)[0] == end-16 and
            struct.unpack_from('<q', data, 32)[0] == end, 'Pool tail pointer shape differs')
    after = bytearray(data[:end] + raven[0]['raw'] + data[end:])
    struct.pack_into('<I', after, 8, count+1)
    for field in (16, 32):
        struct.pack_into('<q', after, field, struct.unpack_from('<q', data, field)[0]+16)
    header = bytearray(source[chunk['header']:chunk['start']])
    struct.pack_into('<I', header, 4, len(after))
    result = source[:chunk['header']]+header+after+source[chunk['end']:]
    return bytes(result), validate_pool(source, bytes(result))


def validate_pool(source, candidate):
    old_chunk = b.one_chunk(b.parse_dcb_chunks(source), 12)
    new_chunk = b.one_chunk(b.parse_dcb_chunks(candidate), 12)
    old = source[old_chunk['start']:old_chunk['end']]
    new = candidate[new_chunk['start']:new_chunk['end']]
    count, rows, end = b.dcb_rows(old)
    nc, nr, ne = b.dcb_rows(new)
    raven = next(r for r in rows if r['uid'] == b.RAVEN_MAP_HASH)
    b.check(nc == count+1 and ne == end+16, 'Pool count differs')
    b.check(new[144:end] == old[144:end] and nr[-1]['raw'] == raven['raw'], 'Pool row changed')
    b.check(new[ne:] == old[end:], 'Pool tail changed')
    inverse = bytearray(new[:end]+new[ne:])
    struct.pack_into('<I', inverse, 8, count)
    for at in (16, 32):
        b.check(struct.unpack_from('<q', new, at)[0] == struct.unpack_from('<q', old, at)[0]+16,
                'Pool pointer differs')
        inverse[at:at+8] = old[at:at+8]
    header = bytearray(candidate[new_chunk['header']:new_chunk['start']])
    struct.pack_into('<I', header, 4, len(inverse))
    normalized = candidate[:new_chunk['header']]+header+inverse+candidate[new_chunk['end']:]
    b.check(bytes(normalized) == source, 'Pool inverse differs from frozen bytes')
    return {'raven_capacity_before': sum(r['capacity'] for r in rows if r['uid'] == b.RAVEN_MAP_HASH),
            'raven_capacity_after': sum(r['capacity'] for r in nr if r['uid'] == b.RAVEN_MAP_HASH),
            'source_rows': count, 'candidate_rows': nc,
            'all_original_rows_byte_identical': True, 'new_row_is_exact_raven_row_copy': True,
            'normalized_to_frozen_raven_exact': True}


def hook_bytes():
    return b'\n' + (HERE/'raven-shared-loader-twin.lua').read_bytes()


def generate(root):
    for rel, expected in {**b.FILES, **FILES}.items():
        b.check(b.sha_file(root/rel) == expected, f'Frozen source differs: {rel}')
    before = {rel: b.sha_file(root/rel) for rel in {**b.FILES, **FILES}}
    master, _ = b.build_mapmaster(root/MASTER, Path(MASTER))
    coords, _ = b.build_mapcoords(root/COORDS, Path(COORDS))
    proofs = {rel: validate_append(b.load_native_module().Dcb(root/rel), parse(raw, rel), kind)
              for rel, raw, kind in ((MASTER, master, 'marker'), (COORDS, coords, 'coordinate'))}
    ui, proofs[UI] = build_pool((root/UI).read_bytes())
    source_lua = (root/LUA).read_bytes()
    lua = source_lua + hook_bytes()
    b.check(lua[:len(source_lua)] == source_lua, 'Frozen Lua prefix changed')
    proofs[LUA] = {'frozen_prefix_bytes': len(source_lua), 'frozen_prefix_sha256': b.sha_bytes(source_lua),
                    'appended_bytes': len(lua)-len(source_lua), 'normalized_to_frozen_raven_exact': True}
    outputs = {MASTER: master, COORDS: coords, UI: ui, LUA: lua}
    b.check(b.folded_name_hash(b.TWIN_MARKER_NAME) == b.TWIN_MARKER_UID, 'Twin UID/name mismatch')
    b.check(b.folded_name_hash(b.TWIN_MAP_GO) == b.RAVEN_MAP_HASH, 'Shared resource hash mismatch')
    b.check({rel: b.sha_file(root/rel) for rel in before} == before, 'Source changed during build')
    return outputs, {'schema': 1, 'result': RESULT, 'branch_contract': BRANCH, 'base_head': BASE_HEAD,
        'source_root': str(root), 'source_sha256': before,
        'files': {rel: {'sha256': b.sha_bytes(raw), 'bytes': len(raw)} for rel, raw in outputs.items()},
        'identities': {'raven_uid': f'{b.RAVEN_MARKER_UID:016X}', 'twin_uid': f'{b.TWIN_MARKER_UID:016X}',
                       'loader': b.RAVEN_MAP_GO, 'resource_hash': f'{b.RAVEN_MAP_HASH:016X}',
                       'twin_position': b.TWIN_POSITION, 'offset_metres': 32, 'init_state': 0},
        'proofs': proofs, 'all_four_files_inverse_exact': True,
        'extra_files_required_by_evidence': {UI: 'Pool checkout capacity 1 cannot supply two live objects. Append additive same-hash row.',
                                            LUA: 'InitState=0 excluded by normal map loop. Append visual-only Twin create/recycle; no state writes.'},
        'game_files_written': False, 'runtime_test_performed': False, 'ready_for_runtime_test': True,
        'retired_candidates_used': False, 'progression_or_marker_state_writes': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raven-root', type=Path, default=Path('G:/SteamLibrary/steamapps/common/GodOfWar'))
    ap.add_argument('--check', action='store_true', help='Verify disk candidate and proof; write nothing.')
    args = ap.parse_args()
    root = args.raven_root.resolve()
    b.assert_output_scope(root, OUTPUT, REPORT)
    files, proof = generate(root)
    if args.check:
        b.check({p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob('*') if p.is_file()} == set(FILES), 'Candidate file set differs')
        for rel, raw in files.items():
            b.check((OUTPUT/rel).read_bytes() == raw, f'Candidate differs: {rel}')
        saved = json.loads(REPORT.read_text())
        b.check(saved == json.loads(json.dumps(proof)), 'Offline proof differs')
        print('RAVEN_SHARED_LOADER_REBUILD_VERIFIED')
        return
    existing = {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob('*') if p.is_file()}
    b.check(existing <= set(FILES), 'Unexpected stale candidate file')
    for rel, raw in files.items():
        b.write_bytes_atomic(OUTPUT, OUTPUT/rel, raw, 'shared-loader candidate')
    b.write_bytes_atomic(REPORT.parent, REPORT, (json.dumps(proof, indent=2)+'\n').encode(), 'shared-loader proof')
    print(RESULT)
    print(json.dumps(proof['files'], indent=2))


if __name__ == '__main__':
    main()
