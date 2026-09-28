"""Validate exact artefact checkpoint owners and replay archived saved states."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'config/collectibles/v0.10.5/all-collectibles.json'
AUTHORITY = ROOT / 'catalogue/artefact-authority.json'
STOCK = ROOT.parent / 'completionist-map-gow2018/dist/gowlua-src/gameart/scripts/levels/gameplaymodules/progression/interact_loot_artifact.lua'
NESTED = 'artefact_f7fbfc3f44991b3da37871879e6de737'
PROTOTYPE = 'bdff29c1ed8dba4aa015b7b27261f0f0'
BRIDGE_ELEMENT = '7edefbc9ee9fdb4185eb36e85d21eaa9'
spec = importlib.util.spec_from_file_location('artefact_identity', HERE / 'build-raven-serialized-gameobject-identities.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(data, source):
    rows = data['rows']
    selected = {r['catalogue_id']: r for r in source['collectibles'] if r['family'] == 'artefact'}
    need(len(rows) == len(selected) == 45 and {r['catalogue_id'] for r in rows} == set(selected),
         'need 45 exact artefact identities')
    need(data['field'] == 'state' and data['collected_value'] == 3 and
         data['allowed_values'] == [1, 2, 3] and data['prototype_identity_element'] == PROTOTYPE,
         'artefact state contract differs')
    keys = set()
    for row in rows:
        source_row = selected[row['catalogue_id']]
        native = source_row['native']
        need(row['wad'] == source_row['source']['wad'] and
             row['source_wad_sha256'] == source_row['source']['wad_sha256'] and
             row['physical_guid'] == native['instance_guid'], 'artefact placement differs')
        paths = [p for p in native['carrier_transform_paths'] if p['state_carrier_guid'] == row['carrier_guid']]
        need(len(paths) == 1, 'artefact carrier missing or ambiguous')
        chain = paths[0]['transform_chain']
        placement = next(i for i, node in enumerate(chain) if node['record_id'] == native['placement_final_record_id'])
        kept = [i for i in range(len(chain) - 1, placement, -1)
                if chain[i]['name'].endswith(('_ents', '_ents_nooffset', '_ents_offset', '_cbt'))]
        kept += [placement, 0]
        if row['catalogue_id'] == NESTED:
            need(row['carrier_guid'] == 'ffa95828-42dd-e146-75e3-a39ff3385d8c' and
                 placement == 2 and len(chain) == 7, 'nested bridge carrier differs')
            kept = [6, 5, 3, 2, 0]
        need(kept == row['kept_chain_indices'], 'artefact scene ownership differs')
        elements = [identity.adjusted_record_id(chain[i]['record_id']).hex() for i in kept]
        if row['catalogue_id'] == NESTED:
            elements.insert(2, BRIDGE_ELEMENT)
            proof = data['nested_bridge_loaded_evidence']
            need(proof['catalogue_id'] == NESTED and proof['registry_id'] == 96 and
                 proof['identity_elements'] == row['identity_elements'] and
                 proof['object_hash'] == row['object_hash'], 'nested loaded identity proof differs')
        elements.append(PROTOTYPE)
        registry = identity.registry_hash_for_wad(row['wad'])
        obj = identity.identity_hash([bytes.fromhex(e) for e in elements])
        need(elements == row['identity_elements'] and row['registry_hash'] == f'{registry:016X}' and
             row['object_hash'] == f'{obj:016X}' and
             row['serialized_key'] == identity.payload(registry, obj).hex(), 'artefact native identity differs')
        need(row['state_path'] == native['instance_guid'] + '.' + row['carrier_guid'], 'artefact state path differs')
        need(row['serialized_key'] not in keys, 'duplicate artefact owner')
        keys.add(row['serialized_key'])
        need(row['fixture_state'] in (1, 2, 3), 'invalid artefact fixture state')
    return rows


def load():
    data = json.loads(AUTHORITY.read_text())
    raw = SOURCE.read_bytes()
    need(sha(raw) == data['source_catalogue_sha256'], 'artefact source catalogue changed')
    need(sha(STOCK.read_bytes()) == data['script_sha256'], 'artefact stock predicate changed')
    return validate(data, json.loads(raw))


def replay():
    import chest_open_capture
    data = json.loads(AUTHORITY.read_text())
    rows = load()
    capture = ROOT / data['capture']
    report = json.loads((capture / 'replay-report.json').read_text())
    records = {r['name'].lower() + '.wad': r for r in report['records']}
    result = []
    for row in rows:
        record = records[row['wad']]
        raw = (capture / record['payload_file']).read_bytes()
        need(record['payload_file'] == row['fixture_payload'] and sha(raw) == row['fixture_sha256'],
             'artefact archived payload changed')
        decoded = chest_open_capture.inspect_payload(raw, record['cached_channel_a_lua_length'], [row])
        need(not decoded['errors'], str(decoded['errors']))
        state = decoded['states'][row['catalogue_id']]
        need(state == row['fixture_state'], 'artefact replay state differs: ' + row['catalogue_id'])
        result.append({'catalogue_id': row['catalogue_id'], 'state': state})
    return result


if __name__ == '__main__':
    rows = replay()
    print('ARTEFACT_REPLAY_OK count=45 collected=' + str(sum(r['state'] == 3 for r in rows)))
