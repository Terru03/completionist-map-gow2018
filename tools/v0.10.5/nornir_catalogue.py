"""Build exact physical Nornir definitions. Does not infer progression state."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'config/collectibles/v0.10.5/all-collectibles.json'
FAMILIES = {
    'nornir_chest': ('CompletionistNornirChest', 22),
    'nornir_seal': ('CompletionistNornirSeal', 30),
    'nornir_bell': ('CompletionistNornirBell', 24),
    'nornir_mechanism': ('CompletionistNornirMechanism', 12),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def build(source):
    rows = [r for r in source['collectibles'] if r['family'] in FAMILIES]
    require(Counter(r['family'] for r in rows) == Counter({k: v[1] for k, v in FAMILIES.items()}), 'physical family counts')
    ids, uids, names, children = {}, set(), set(), Counter()
    live_paths = set()
    result = []
    for row in rows:
        cid, family = row['catalogue_id'], row['family']
        marker, native, progression, provenance = row['marker'], row['native'], row['progression'], row['source']
        require(cid not in ids, 'duplicate catalogue ID')
        require(re.fullmatch(r'[0-9A-F]{16}', marker['uid']) is not None and marker['uid'] not in uids, 'invalid/duplicate UID')
        require(marker['name'] and marker['name'] not in names, 'duplicate marker name')
        expected = FAMILIES[family][0]
        require(marker['compass_class'] == expected and marker['map_resource'] == 'goMapIcon' + expected, 'distinct family resource required')
        require(len(marker['position_world']) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in marker['position_world']), 'finite world position required')
        require(marker['coordinate_wad'].lower() == 'wad_' + Path(provenance['wad']).stem.lower(), 'coordinate WAD mismatch')
        require(re.fullmatch(r'[a-f0-9]{64}', provenance['wad_sha256']) is not None and provenance['transform_chain'], 'missing source evidence')
        require(progression['read_only'] is True, 'read-only state required')
        ids[cid] = row
        uids.add(marker['uid'])
        names.add(marker['name'])
        parent = native.get('parent_catalogue_id')
        if family == 'nornir_chest':
            require(parent is None and progression['field'] == 'state == OPENED', 'parent state contract')
            chain = provenance['transform_chain']
            placement = [i for i, node in enumerate(chain)
                         if node['record_id'] == native['placement_final_record_id']]
            require(len(placement) == 1, 'exact physical placement path required')
            require(placement[0] >= 2 and chain[0]['name'] == 'gochestscript_rn' and
                    chain[1]['name'] == 'gochest_locked_parent', 'exact runic script owner path required')
            loaded_path = [node['name'] for node in chain[placement[0]:]]
            loaded_script_path = [node['name'] for node in chain[1:]]
            require(loaded_path[0] == native['placement_object_name'], 'placement name differs')
            key = (provenance['wad'], tuple(loaded_path))
            require(key not in live_paths, 'duplicate live placement path')
            live_paths.add(key)
        else:
            require(parent and parent == progression['parent_catalogue_id'], 'parent link mismatch')
            require(native['parent_reference_source'] == 'exact_lua_table_attribute_on_parent_placement', 'exact child link required')
            require(progression['durable_individual_completion'] is (family == 'nornir_seal'), 'child completion contract')
            children[parent] += 1
            loaded_path = [node['name'] for node in provenance['transform_chain']]
            loaded_script_path = None
        result.append(dict(id=cid, family=family, parent=parent, uid=marker['uid'], name=marker['name'],
                           realm=row['realm_id'], realm_name=row['realm'], region=row['region'], region_id=row['region_id'],
                           resource=marker['map_resource'], **{'class': marker['compass_class']},
                           wad=provenance['wad'], coordinate_wad=marker['coordinate_wad'],
                           position=marker['position_world'], source_sha256=provenance['wad_sha256'],
                           native_guid=native['instance_guid'], state_adapter=progression['state_adapter'],
                           reference_name=native.get('reference_name'),
                           loaded_level=Path(provenance['wad']).stem,
                           loaded_path=loaded_path,
                           loaded_script_path=loaded_script_path,
                           instance_keys=progression.get('instance_keys', [])))
    for row in rows:
        if row['family'] == 'nornir_chest':
            require(children[row['catalogue_id']] == 3, 'parent must have three children')
        else:
            parent = ids.get(row['native']['parent_catalogue_id'])
            require(parent is not None and parent['family'] == 'nornir_chest', 'missing parent')
            require(parent['source']['wad'] == row['source']['wad'] and parent['realm_id'] == row['realm_id'], 'child WAD/realm mismatch')
            require(parent['native']['instance_guid'] == row['native']['parent_instance_guid'], 'child parent GUID mismatch')
    return sorted(result, key=lambda r: r['id'])


def render_lua(rows):
    def value(item):
        if item is None:
            return 'nil'
        if isinstance(item, str):
            # Current native names are ASCII; JSON escapes also valid in Lua 5.1 here.
            require(item.isascii() and not any(ord(c) < 32 for c in item), 'unsupported Lua string')
            return json.dumps(item)
        if isinstance(item, list):
            return '{' + ','.join(value(v) for v in item) + '}'
        if type(item) in (int, float) and math.isfinite(item):
            return repr(item)
        raise ValueError('unsupported Lua value')
    return '-- Generated exact Nornir definitions. No progression state.\nreturn {\n' + ''.join(
        '  {' + ','.join('[' + value(k) + ']=' + value(v) for k, v in row.items()) + '},\n' for row in rows
    ) + '}\n'


def manifest():
    return {'schema_version': 1, 'source': str(SOURCE.relative_to(ROOT)).replace('\\', '/'),
            'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'release_ready': False,
            'gates': ['live exact-path/getter/restore proof', 'unloaded checkpoint authority', 'live map/artwork/compass/navigation proof'],
            'collectibles': build(json.loads(SOURCE.read_text(encoding='utf-8')))}


if __name__ == '__main__':
    # Validation only. Generation is explicit through the offline build script.
    print(json.dumps({'status': 'PASS_STATIC', 'count': len(manifest()['collectibles']), 'release_ready': False}))
