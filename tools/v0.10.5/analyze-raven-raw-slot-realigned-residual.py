"""Offline/read-only residual comparison for the Raven alive/dead ring slots.

The prior structural-shift analysis proved that zlib streams 0..48 in DEAD slot
17 are exactly 48 bytes earlier than their byte-identical ALIVE slot-5 copies,
while streams 49..80 have delta 0. This tool finds where a -48 byte alignment
best begins/ends in the raw slot, then measures residual differences after
accounting for that structural displacement. It emits only aggregate counts and
changed ranges; no raw save payload bytes are exported.
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
SHIFT = 48
TRANSITION_HINT = 202972


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def slot(blob: bytes, index: int) -> bytes:
    start = PREFIX + index * STRIDE
    return blob[start:start + STRIDE]


def runs(indices: list[int]) -> list[dict]:
    if not indices:
        return []
    out = []
    start = prev = indices[0]
    for cur in indices[1:]:
        if cur != prev + 1:
            out.append({'start': start, 'end': prev, 'length': prev - start + 1})
            start = cur
        prev = cur
    out.append({'start': start, 'end': prev, 'length': prev - start + 1})
    return out


def score_alignment(a: bytes, b: bytes, start: int, end: int, shift: int) -> tuple[int, int]:
    matches = total = 0
    bs = max(0, start)
    be = min(len(b), end)
    for bi in range(bs, be):
        ai = bi + shift
        if ai < 0 or ai >= len(a):
            continue
        total += 1
        if b[bi] == a[ai]:
            matches += 1
    return matches, total


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
    a = slot(alive.read_bytes(), ALIVE_SLOT)
    b = slot(dead.read_bytes(), DEAD_SLOT)
    if len(a) != STRIDE or len(b) != STRIDE:
        raise RuntimeError('slot extraction size mismatch')

    # Find a contiguous region around the known moved-stream block where +48
    # alignment clearly outperforms same-offset alignment. Work in 256-byte
    # windows to avoid overfitting isolated bytes.
    window = 256
    shifted_better = []
    for s in range(0, min(TRANSITION_HINT + 65536, STRIDE - SHIFT), window):
        e = min(s + window, STRIDE - SHIFT)
        sm, st = score_alignment(a, b, s, e, 0)
        xm, xt = score_alignment(a, b, s, e, SHIFT)
        if st and xt and (xm / xt) - (sm / st) >= 0.20:
            shifted_better.append(s)

    # Coalesce windows and select the longest range overlapping the known
    # streams-0..48 neighborhood (roughly 22k..55k).
    groups = []
    if shifted_better:
        gs = gp = shifted_better[0]
        for cur in shifted_better[1:]:
            if cur == gp + window:
                gp = cur
            else:
                groups.append((gs, gp + window))
                gs = gp = cur
            gp = cur
        groups.append((gs, gp + window))
    overlapping = [g for g in groups if g[0] < 60000 and g[1] > 17000]
    chosen = max(overlapping, key=lambda g: g[1]-g[0]) if overlapping else (17744, 54624)

    # Extend boundaries bytewise while shifted alignment remains substantially
    # better in local 512-byte neighborhoods.
    shift_start, shift_end = chosen
    shift_start = max(0, shift_start)
    shift_end = min(TRANSITION_HINT, shift_end)

    # The stream evidence gives an exact semantic-safe envelope for moved data:
    # first moved compressed stream begins at dead offset 22271 and the last
    # moved stream ends before dead gap start 54577. Use a conservative envelope
    # that includes nearby structure rather than attempting to infer payload.
    envelope_start = max(0, min(shift_start, 22000))
    envelope_end = max(shift_end, 54577)

    residual = []
    explained_matches = 0
    compared = 0
    for bi in range(STRIDE):
        if envelope_start <= bi < envelope_end and bi + SHIFT < STRIDE:
            ai = bi + SHIFT
        else:
            ai = bi
        compared += 1
        if a[ai] == b[bi]:
            explained_matches += 1
        else:
            residual.append(bi)

    raw_diff = [i for i in range(STRIDE) if a[i] != b[i]]
    residual_runs = runs(residual)
    raw_runs = runs(raw_diff)

    # Also report fixed alignment quality in the important regions.
    regions = {}
    for name, s, e in [
        ('header', 0, 4096),
        ('pre_shift', 4096, envelope_start),
        ('shift_envelope', envelope_start, envelope_end),
        ('gap_to_transition', envelope_end, TRANSITION_HINT),
        ('post_transition', TRANSITION_HINT, STRIDE),
    ]:
        sm, st = score_alignment(a, b, s, e, 0)
        xm, xt = score_alignment(a, b, s, e, SHIFT)
        regions[name] = {
            'start': s, 'end': e,
            'same_offset_match_ratio': (sm / st) if st else None,
            'plus48_match_ratio': (xm / xt) if xt else None,
        }

    after = {'alive': sha256_file(alive), 'dead': sha256_file(dead)}
    if before != after:
        raise RuntimeError('source save hash changed during read-only analysis')

    report = {
        'schema': 1,
        'analysis': 'raven_raw_slot_realigned_residual',
        'source_hashes': before,
        'source_hashes_unchanged': True,
        'alive_slot': ALIVE_SLOT,
        'dead_slot': DEAD_SLOT,
        'structural_shift': SHIFT,
        'detected_shift_window_groups': [{'start': x, 'end': y} for x,y in groups],
        'chosen_shift_window': {'start': shift_start, 'end': shift_end},
        'conservative_shift_envelope': {'start': envelope_start, 'end': envelope_end},
        'raw_changed_bytes': len(raw_diff),
        'raw_changed_runs': len(raw_runs),
        'realigned_residual_changed_bytes': len(residual),
        'realigned_residual_changed_runs': len(residual_runs),
        'realigned_match_ratio': explained_matches / compared,
        'residual_runs_top': sorted(residual_runs, key=lambda r: (-r['length'], r['start']))[:100],
        'regions': regions,
        'interpretation': {
            'all_zlib_payloads_identical': True,
            'structural_shift_accounted_for': True,
            'residual_is_completion_truth': False,
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
        'RAVEN_RAW_SLOT_REALIGNED_RESIDUAL_COMPLETED',
        f'raw_changed_bytes={len(raw_diff)}',
        f'raw_changed_runs={len(raw_runs)}',
        f'shift_envelope={envelope_start}-{envelope_end}',
        f'realigned_residual_changed_bytes={len(residual)}',
        f'realigned_residual_changed_runs={len(residual_runs)}',
        f'realigned_match_ratio={explained_matches / compared:.9f}',
        'runtime_generation_allowed=false',
        'active_save_opened=false',
        'raw_save_bytes_emitted=false',
    ]
    for name, r in regions.items():
        lines.append(f"region_{name}=same:{r['same_offset_match_ratio']:.9f},plus48:{r['plus48_match_ratio']:.9f}")
    args.summary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
