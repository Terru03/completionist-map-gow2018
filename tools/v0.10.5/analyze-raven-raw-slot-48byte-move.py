"""Offline/read-only test for a 48-byte structural record move between frozen Raven saves.

Prior analysis proved that DEAD slot 17 matches ALIVE slot 5 semantically for all
81 zlib streams. Streams 0..48 are displaced by -48 bytes, then later layout
returns to the original offset. This probe tests the narrow hypothesis that a
single 48-byte structural record moved/reordered between the two serialized slot
images.

It emits offsets, counts and SHA-256 hashes only; it never emits raw save bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PREFIX = 4160
STRIDE = 1677512
ALIVE_SLOT = 5
DEAD_SLOT = 17
BLOCK = 48


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_slot(blob: bytes, index: int) -> bytes:
    start = PREFIX + index * STRIDE
    out = blob[start:start + STRIDE]
    if len(out) != STRIDE:
        raise RuntimeError('slot extraction size mismatch')
    return out


def runs(indices: list[int]) -> list[dict]:
    if not indices:
        return []
    out = []
    s = p = indices[0]
    for x in indices[1:]:
        if x != p + 1:
            out.append({'start': s, 'end': p, 'length': p - s + 1})
            s = x
        p = x
    out.append({'start': s, 'end': p, 'length': p - s + 1})
    return out


def mismatch_count(a: bytes, b: bytes, start: int, end: int, delta: int = 0) -> int:
    bad = 0
    end = min(end, len(b))
    for bi in range(start, end):
        ai = bi + delta
        if ai < 0 or ai >= len(a) or a[ai] != b[bi]:
            bad += 1
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--alive', type=Path, required=True)
    ap.add_argument('--dead', type=Path, required=True)
    ap.add_argument('--output-json', type=Path, required=True)
    ap.add_argument('--summary', type=Path, required=True)
    args = ap.parse_args()

    alive = args.alive.expanduser().resolve()
    dead = args.dead.expanduser().resolve()
    active = (Path.home() / 'Saved Games' / 'God of War').resolve()
    for p in (alive, dead):
        if not p.is_file():
            raise RuntimeError(f'frozen save missing: {p}')
        try:
            p.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f'refusing active save: {p}')

    before = {'alive': sha256_file(alive), 'dead': sha256_file(dead)}
    a = get_slot(alive.read_bytes(), ALIVE_SLOT)
    b = get_slot(dead.read_bytes(), DEAD_SLOT)

    # Locate the exact onset of the +48 alignment by scoring candidates near the
    # previously proven transition into the shifted stream block.
    source_rank = []
    for p in range(17000, 23001):
        # Before p, same-offset should fit; after p+BLOCK, b should fit a+48.
        left_start = max(0, p - 2048)
        left_bad = mismatch_count(a, b, left_start, p, 0)
        right_end = min(55552, p + 32768)
        shifted_bad = mismatch_count(a, b, p, right_end, BLOCK)
        source_rank.append((left_bad + shifted_bad, p, left_bad, shifted_bad))
    source_rank.sort()
    source_score, source, source_left_bad, source_shift_bad = source_rank[0]

    # Locate where alignment returns to zero. Before q, +48 should fit; after
    # q+BLOCK, same-offset should fit.
    dest_rank = []
    for q in range(52000, 59001):
        left_start = max(source, q - 8192)
        shifted_bad = mismatch_count(a, b, left_start, q, BLOCK)
        right_end = min(210000, q + 32768)
        same_bad = mismatch_count(a, b, q + BLOCK, right_end, 0)
        dest_rank.append((shifted_bad + same_bad, q, shifted_bad, same_bad))
    dest_rank.sort()
    dest_score, dest, dest_shift_bad, dest_same_bad = dest_rank[0]

    alive_source_block = a[source:source + BLOCK]
    dead_dest_block = b[dest:dest + BLOCK]
    source_hash = sha256_bytes(alive_source_block)
    dest_hash = sha256_bytes(dead_dest_block)
    blocks_equal = alive_source_block == dead_dest_block

    # Model ALIVE -> DEAD as removing ALIVE[source:source+48] and inserting the
    # DEAD destination block at dest. This is deliberately an explanatory model,
    # not a mutation of either source file.
    model = a[:source] + a[source + BLOCK:]
    insert_at = max(0, min(dest, len(model)))
    model = model[:insert_at] + dead_dest_block + model[insert_at:]
    if len(model) != STRIDE:
        raise RuntimeError('modeled slot length mismatch')

    residual = [i for i in range(STRIDE) if model[i] != b[i]]
    residual_runs = runs(residual)
    raw_diff = [i for i in range(STRIDE) if a[i] != b[i]]

    # Also test the stronger pure-move model using the removed ALIVE block as the
    # inserted block. If hashes match, the two models are identical.
    pure = a[:source] + a[source + BLOCK:]
    pure = pure[:insert_at] + alive_source_block + pure[insert_at:]
    pure_residual = [i for i in range(STRIDE) if pure[i] != b[i]]

    after = {'alive': sha256_file(alive), 'dead': sha256_file(dead)}
    if before != after:
        raise RuntimeError('source save hash changed during read-only analysis')

    report = {
        'schema': 1,
        'analysis': 'raven_raw_slot_48byte_move',
        'source_hashes': before,
        'source_hashes_unchanged': True,
        'alive_slot': ALIVE_SLOT,
        'dead_slot': DEAD_SLOT,
        'block_size': BLOCK,
        'best_source_offset': source,
        'best_source_score': source_score,
        'best_source_left_mismatches': source_left_bad,
        'best_source_shifted_mismatches': source_shift_bad,
        'best_destination_offset': dest,
        'best_destination_score': dest_score,
        'best_destination_shifted_mismatches': dest_shift_bad,
        'best_destination_same_mismatches': dest_same_bad,
        'alive_source_block_sha256': source_hash,
        'dead_destination_block_sha256': dest_hash,
        'source_destination_blocks_equal': blocks_equal,
        'raw_changed_bytes': len(raw_diff),
        'modeled_residual_changed_bytes': len(residual),
        'modeled_residual_changed_runs': len(residual_runs),
        'modeled_match_ratio': 1.0 - (len(residual) / STRIDE),
        'pure_move_residual_changed_bytes': len(pure_residual),
        'pure_move_match_ratio': 1.0 - (len(pure_residual) / STRIDE),
        'residual_runs_top': sorted(residual_runs, key=lambda r: (-r['length'], r['start']))[:100],
        'interpretation': {
            'all_zlib_payloads_identical': True,
            'block_move_is_completion_truth': False,
            'requires_semantic_binding': True,
            'runtime_generation_allowed': False,
        },
        'safety': {
            'active_save_opened': False,
            'source_files_written': False,
            'raw_save_bytes_emitted': False,
            'process_memory_read': False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    lines = [
        'RAVEN_RAW_SLOT_48BYTE_MOVE_COMPLETED',
        f'best_source_offset={source}',
        f'best_destination_offset={dest}',
        f'source_destination_blocks_equal={str(blocks_equal).lower()}',
        f'alive_source_block_sha256={source_hash}',
        f'dead_destination_block_sha256={dest_hash}',
        f'raw_changed_bytes={len(raw_diff)}',
        f'modeled_residual_changed_bytes={len(residual)}',
        f'modeled_residual_changed_runs={len(residual_runs)}',
        f'modeled_match_ratio={report["modeled_match_ratio"]:.9f}',
        f'pure_move_residual_changed_bytes={len(pure_residual)}',
        f'pure_move_match_ratio={report["pure_move_match_ratio"]:.9f}',
        'runtime_generation_allowed=false',
        'active_save_opened=false',
        'raw_save_bytes_emitted=false',
    ]
    args.summary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
