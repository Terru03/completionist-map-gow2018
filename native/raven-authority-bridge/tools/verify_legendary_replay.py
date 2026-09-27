"""Check chest states through Python graph parser against frozen raw bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools/v0.10.5'))
import staged_wad_bitstream as staged

CAPTURE = REPO / 'archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1'
CATALOGUE = REPO / 'catalogue/legendary-chest-authority.json'
EVIDENCE = REPO / 'docs/research/legendary-native-authority-replay.json'
STATES = {'010000803f': 1, '0100000040': 2,
          '0100004040': 3, '0100008040': 4}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inspect_graph(record: dict, candidate: dict, wanted: dict) -> dict:
    envelope = (CAPTURE / record['payload_file']).read_bytes()
    if int.from_bytes(envelope[:2], 'little') != len(envelope) - 2:
        raise ValueError('Archived frame length differs')
    bit = candidate['bit_offset']
    aligned = staged._aligned_bytes(envelope[2:], bit % 8)
    start, length = bit // 8, record['cached_channel_a_lua_length']
    if int.from_bytes(aligned[start-2:start], 'big') != length:
        raise ValueError('Archived Lua length differs')
    raw = aligned[start:start+length]
    module = staged._decoder()
    decoded, consumed = module.decompress_stream(raw, 16)
    parses = staged._decode_paths(module, raw, decoded, consumed, None, {})
    if len(parses) != 1:
        raise ValueError('Archived graph ambiguous')
    parsed = parses[0]
    header = struct.unpack_from('<8H', raw)
    token_end = 16 + consumed + 2 * header[0] + sum(t['width'] for t in parsed['token_parse'])
    sizes = raw[token_end:token_end+header[4]]
    offsets = struct.unpack_from(f'<{header[4]}H', raw, token_end+header[4])
    blob = decoded[header[1]:header[1]+header[5]]
    records = [blob[offset:offset+size] for offset, size in zip(offsets, sizes)]
    tokens = parsed['token_parse']
    pairs = list(zip(tokens[::2], tokens[1::2]))

    def row_pairs(index):
        row = parsed['rows'][index]
        return pairs[row['first_pair']:row['first_pair']+row['pair_count']]

    matches = []
    for subrow in parsed['subobj_table_rows']:
        for key, value in row_pairs(subrow):
            if key['tag'] != 5 or value['tag'] != 3:
                continue
            saved = records[key['payload']]
            if saved[8:].hex() != wanted['serialized_key']:
                continue
            if int.from_bytes(saved[:8], 'little') != 0x75E050AB149B4062:
                raise ValueError('Chest class differs')
            state_row = value['payload'] - 1
            state = [v for k, v in row_pairs(state_row)
                     if k['tag'] == 2 and parsed['strings'][k['payload']] == 'state']
            if len(state) != 1 or state[0]['raw_hex'] not in STATES:
                raise ValueError('Chest state missing, duplicate, or invalid')
            matches.append({'raw': state[0]['raw_hex'], 'state_row': state_row})
    if len(matches) != 1:
        raise ValueError(f"Need one exact saved chest: {wanted['catalogue_id']}")
    return {**matches[0], 'payload_file': record['payload_file'],
            'payload_sha256': digest(envelope), 'bit_offset': bit,
            'lua_length': length, 'serialized_key': wanted['serialized_key']}


def replay() -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding='utf-8'))
    report_bytes = (CAPTURE / 'replay-report.json').read_bytes()
    report = json.loads(report_bytes)
    records = {r['name'].lower() + '.wad': r for r in report['records']}
    rows = []
    for wanted in catalogue['rows']:
        record = records.get(wanted['wad'])
        result = {'catalogue_id': wanted['catalogue_id'], 'wad': wanted['wad']}
        if record is None:
            result.update(raw=None, reason='wad_absent_state_unknown')
        else:
            candidates = record['decode']['candidates']
            if len(candidates) != 1:
                raise ValueError('Need one frozen carrier location')
            result.update(inspect_graph(record, candidates[0], wanted))
        rows.append(result)
    return {'schema': 1, 'capture': CAPTURE.relative_to(REPO).as_posix(),
            'replay_report_sha256': digest(report_bytes), 'rows': rows,
            'opened': sum(r['raw'] == '0100008040' for r in rows),
            'remaining': sum(r['raw'] in STATES and r['raw'] != '0100008040' for r in rows),
            'unknown': sum(r['raw'] is None for r in rows),
            'live_delivery_ready': False, 'marker_generation_ready': False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-evidence', action='store_true')
    args = parser.parse_args()
    result = replay()
    if args.record_evidence:
        EVIDENCE.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        if result != json.loads(EVIDENCE.read_text(encoding='utf-8')):
            raise ValueError('Pinned replay evidence differs')
        expected = json.loads(CATALOGUE.read_text(encoding='utf-8'))['rows']
        if [(r['catalogue_id'], r['raw']) for r in result['rows']] != [
                (r['catalogue_id'], r['fixture_raw']) for r in expected]:
            raise ValueError('Catalogue replay expectations differ')
    print(f"LEGENDARY_PYTHON_REPLAY opened={result['opened']} "
          f"remaining={result['remaining']} unknown={result['unknown']}")


if __name__ == '__main__':
    main()
