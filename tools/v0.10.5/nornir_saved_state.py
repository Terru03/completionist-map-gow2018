"""Exact Nornir reward-chest checkpoint keys. Missing state stays unknown."""
import importlib.util
import hashlib
import json
from pathlib import Path

import nornir_catalogue as catalogue

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('raven_identity', HERE / 'build-raven-serialized-gameobject-identities.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
STANDARD_CHEST_ELEMENT = bytes.fromhex('947a7c50b25f004ea3365dd8dc232ee1')
CAPTURE = catalogue.ROOT / 'archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1'


def contract(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(source):
    catalogue.build(source)
    result = []
    for row in source['collectibles']:
        if row['family'] != 'nornir_chest':
            continue
        chain = row['source']['transform_chain']
        placement = next(i for i, node in enumerate(chain)
                         if node['record_id'] == row['native']['placement_final_record_id'])
        kept = [i for i in range(len(chain)-1, placement, -1)
                if chain[i]['name'].endswith(('_ents', '_ents_nooffset', '_ents_offset', '_cbt'))]
        kept += [placement]
        kept += [i for i in range(placement-1, -1, -1) if not chain[i]['name'].endswith('_parent')]
        if row['catalogue_id'] == 'nornir_chest_c02f019049d50ea0146c478fd46f4a49':
            # Exact archived key keeps this nested parent, omits tier wrapper.
            catalogue.require(chain[2]['record_id'] == '138c79b301f78d4fa7cfe7bf92b55f97' and
                              chain[3]['record_id'] == 'bbb3945cfe281b488f4b0f61bee1ae18',
                              'BeachMaze nested identity changed')
            kept = [7, 6, 4, 2, 0]
        elements = [identity.adjusted_record_id(chain[i]['record_id']) for i in kept]
        registry = identity.registry_hash_for_wad(row['source']['wad'])
        obj = identity.identity_hash(elements + [STANDARD_CHEST_ELEMENT])
        result.append({'catalogue_id': row['catalogue_id'], 'wad': row['source']['wad'],
                       'registry_hash': f'{registry:016X}', 'object_hash': f'{obj:016X}',
                       'serialized_key': identity.payload(registry, obj).hex(),
                       'identity_elements': [e.hex() for e in elements + [STANDARD_CHEST_ELEMENT]]})
    catalogue.require(len(result) == len({r['serialized_key'] for r in result}) == 22,
                      'need 22 unique Nornir reward identities')
    return sorted(result, key=lambda row: row['catalogue_id'])


def replay(rows):
    import chest_open_capture
    report = json.loads((CAPTURE / 'replay-report.json').read_text())
    records = {r['name'].lower() + '.wad': r for r in report['records']}
    output = []
    for row in rows:
        record = records.get(row['wad'])
        state = None
        reason = 'wad_absent'
        if record:
            got = chest_open_capture.inspect_payload((CAPTURE / record['payload_file']).read_bytes(),
                                                    record['cached_channel_a_lua_length'], [row])
            catalogue.require(not got['errors'], str(got['errors']))
            state = got['states'][row['catalogue_id']]
            reason = 'exact_state' if state is not None else 'exact_key_absent'
        output.append({**row, 'fixture_state': state, 'reason': reason})
    return output


if __name__ == '__main__':
    print(json.dumps(replay(build(json.loads(catalogue.SOURCE.read_text()))), indent=2))
