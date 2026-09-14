"""Read-only context correlation for the runtime-proven Veithurgard Raven key.

This is a follow-up to probe-known-raven-runtime-keys.py. It validates the same two
frozen saves, locates the exact real Raven marker UID in each aligned save slot,
and compares bounded windows around matching occurrences. It also reports which
slots lost the runtime-proven region/stock identifiers between A and B.

No active save is opened. No arbitrary byte excerpts are emitted: only offsets,
counts, hashes, bounded diff-run metadata and explicit 0/1 transition candidates.
Nothing here is promoted to a state oracle automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

SAVE_SIZE = 33_554_400
PREFIX_SIZE = 4_160
SLOT_SIZE = 1_677_512
SLOT_COUNT = 20
WINDOW_RADIUS = 16_384
MAX_DIFF_RUNS = 128
MAX_BOOL_CANDIDATES = 128

EXPECTED_BACKUPS = {
    "GodOfWar-SaveBackup-2026-09-13_21-53-50": "617dc5867850dc14b6a4791bc116ace132a84a6a188d3165cec5276049d48438",
    "GodOfWar-SaveBackup-2026-09-13_22-01-52": "d1d7b43780ad878e300507d71059347734f96515d2ae3d0cf40e9571216bc63d",
}

REAL_MARKER_UID = -2207208259907848386
REGION_UID = -6808215654220372037
STOCK_BACKING_UID = 2924516555722838670
SYNTHETIC_TWIN_UID = 3410085282531601808
KNOWN_TEXT = (b"ravenKilled", "ravenKilled".encode("utf-16le"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def backup_name(path: Path) -> str:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name in EXPECTED_BACKUPS:
            return parent.name
    raise RuntimeError(f"Save is not inside an expected frozen backup: {resolved}")


def validate_save(path: Path) -> tuple[str, str, bytes]:
    path = path.expanduser().resolve()
    if path.name.lower() != "game.sav" or not path.is_file():
        raise RuntimeError(f"Expected existing game.sav, got: {path}")
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    if is_under(path, active):
        raise RuntimeError("Refusing to open active God of War save directory")
    name = backup_name(path)
    actual = sha256_file(path)
    if actual != EXPECTED_BACKUPS[name]:
        raise RuntimeError(f"Frozen backup hash mismatch for {name}: {actual}")
    if path.stat().st_size != SAVE_SIZE:
        raise RuntimeError(f"Unexpected save size for {name}: {path.stat().st_size}")
    blob = path.read_bytes()
    words = struct.unpack_from("<8I", blob, 0)
    if words[6] != SAVE_SIZE or words[5] != SLOT_SIZE:
        raise RuntimeError(f"Known save layout changed for {name}")
    return name, actual, blob


def i64le(value: int) -> bytes:
    return struct.pack("<q", value)


def u64le(value: int) -> bytes:
    return struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)


def slot_chunk(blob: bytes, slot: int) -> bytes:
    start = PREFIX_SIZE + slot * SLOT_SIZE
    return blob[start:start + SLOT_SIZE]


def all_offsets(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        at = data.find(needle, start)
        if at < 0:
            return out
        out.append(at)
        start = at + len(needle)


def slot_occurrences(blob: bytes, value: int) -> list[dict]:
    needle = i64le(value)
    rows: list[dict] = []
    for slot in range(SLOT_COUNT):
        chunk = slot_chunk(blob, slot)
        for off in all_offsets(chunk, needle):
            rows.append({"slot": slot, "slot_offset": off})
    return rows


def slots_with(blob: bytes, value: int) -> list[int]:
    needle = i64le(value)
    return [slot for slot in range(SLOT_COUNT) if needle in slot_chunk(blob, slot)]


def bounded_window(chunk: bytes, center: int) -> tuple[int, bytes]:
    lo = max(0, center - WINDOW_RADIUS)
    hi = min(len(chunk), center + 8 + WINDOW_RADIUS)
    return lo, chunk[lo:hi]


def diff_runs(a: bytes, b: bytes, base_relative: int) -> tuple[list[dict], int]:
    limit = min(len(a), len(b))
    runs: list[dict] = []
    changed = 0
    i = 0
    while i < limit:
        if a[i] == b[i]:
            i += 1
            continue
        start = i
        while i < limit and a[i] != b[i]:
            i += 1
        end = i
        changed += end - start
        if len(runs) < MAX_DIFF_RUNS:
            runs.append({
                "relative_start": base_relative + start,
                "length": end - start,
                "A_sha256": sha256_bytes(a[start:end]),
                "B_sha256": sha256_bytes(b[start:end]),
            })
    if len(a) != len(b):
        changed += abs(len(a) - len(b))
    return runs, changed


def boolean_candidates(a: bytes, b: bytes, base_relative: int) -> list[dict]:
    out: list[dict] = []
    for i, (av, bv) in enumerate(zip(a, b)):
        if av != bv and av in (0, 1) and bv in (0, 1):
            out.append({"relative_offset": base_relative + i, "A": av, "B": bv})
            if len(out) >= MAX_BOOL_CANDIDATES:
                break
    return out


def token_locations(window: bytes, base_relative: int) -> list[dict]:
    out: list[dict] = []
    for needle, encoding in ((KNOWN_TEXT[0], "ascii"), (KNOWN_TEXT[1], "utf16le")):
        for at in all_offsets(window, needle):
            out.append({"token": "ravenKilled", "encoding": encoding, "relative_offset": base_relative + at})
    return out


def context_rows(blob_a: bytes, blob_b: bytes) -> list[dict]:
    a_occ = slot_occurrences(blob_a, REAL_MARKER_UID)
    b_occ = slot_occurrences(blob_b, REAL_MARKER_UID)
    b_index = {(r["slot"], r["slot_offset"]): r for r in b_occ}
    rows: list[dict] = []
    for arow in a_occ:
        key = (arow["slot"], arow["slot_offset"])
        brow = b_index.get(key)
        if brow is None:
            rows.append({**arow, "exact_pair": False})
            continue
        achunk = slot_chunk(blob_a, arow["slot"])
        bchunk = slot_chunk(blob_b, brow["slot"])
        alo, awin = bounded_window(achunk, arow["slot_offset"])
        blo, bwin = bounded_window(bchunk, brow["slot_offset"])
        base_rel = alo - arow["slot_offset"]
        runs, changed = diff_runs(awin, bwin, base_rel)
        bools = boolean_candidates(awin, bwin, base_rel)
        rows.append({
            **arow,
            "exact_pair": True,
            "A_window_sha256": sha256_bytes(awin),
            "B_window_sha256": sha256_bytes(bwin),
            "window_changed": awin != bwin,
            "changed_bytes": changed,
            "diff_runs": runs,
            "boolean_transition_candidates": bools,
            "known_field_tokens_A": token_locations(awin, base_rel),
            "known_field_tokens_B": token_locations(bwin, base_rel),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-a", type=Path, required=True)
    ap.add_argument("--save-b", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    name_a, hash_a, blob_a = validate_save(args.save_a)
    name_b, hash_b, blob_b = validate_save(args.save_b)
    if name_a == name_b:
        raise RuntimeError("Expected two distinct frozen backups")

    rows = context_rows(blob_a, blob_b)
    changed_rows = [r for r in rows if r.get("window_changed")]
    exact_pairs = [r for r in rows if r.get("exact_pair")]

    region_a = slots_with(blob_a, REGION_UID)
    region_b = slots_with(blob_b, REGION_UID)
    stock_a = slots_with(blob_a, STOCK_BACKING_UID)
    stock_b = slots_with(blob_b, STOCK_BACKING_UID)
    control_a = slots_with(blob_a, SYNTHETIC_TWIN_UID)
    control_b = slots_with(blob_b, SYNTHETIC_TWIN_UID)

    report = {
        "schema": 1,
        "scan_kind": "read_only_known_raven_runtime_key_context_correlation",
        "A": {"backup": name_a, "sha256": hash_a},
        "B": {"backup": name_b, "sha256": hash_b},
        "runtime_key": {"real_marker_uid": REAL_MARKER_UID, "region_uid": REGION_UID, "stock_backing_uid": STOCK_BACKING_UID},
        "real_marker_occurrences_A": slot_occurrences(blob_a, REAL_MARKER_UID),
        "real_marker_occurrences_B": slot_occurrences(blob_b, REAL_MARKER_UID),
        "context_comparison": rows,
        "slot_presence": {
            "region_A": region_a,
            "region_B": region_b,
            "region_disappeared": sorted(set(region_a) - set(region_b)),
            "region_appeared": sorted(set(region_b) - set(region_a)),
            "stock_A": stock_a,
            "stock_B": stock_b,
            "stock_disappeared": sorted(set(stock_a) - set(stock_b)),
            "stock_appeared": sorted(set(stock_b) - set(stock_a)),
            "synthetic_twin_A": control_a,
            "synthetic_twin_B": control_b,
        },
        "interpretation": "Changed context near a runtime-proven identity is correlation evidence only, not collected-state proof.",
        "runtime_generation_allowed": False,
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "scan_only": True,
            "frozen_backup_hashes_verified": True,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "Completionist Map - known Raven runtime-key context correlation",
        f"A={name_a} sha256={hash_a}",
        f"B={name_b} sha256={hash_b}",
        f"real_marker_occurrences_A={len(report['real_marker_occurrences_A'])}",
        f"real_marker_occurrences_B={len(report['real_marker_occurrences_B'])}",
        f"exact_context_pairs={len(exact_pairs)}",
        f"changed_context_pairs={len(changed_rows)}",
        f"region_disappeared_slots={report['slot_presence']['region_disappeared']}",
        f"region_appeared_slots={report['slot_presence']['region_appeared']}",
        f"stock_disappeared_slots={report['slot_presence']['stock_disappeared']}",
        f"stock_appeared_slots={report['slot_presence']['stock_appeared']}",
        f"synthetic_twin_slots_A={control_a}",
        f"synthetic_twin_slots_B={control_b}",
    ]
    for row in changed_rows:
        lines.append(
            "CHANGED_CONTEXT "
            f"slot={row['slot']} slot_offset={row['slot_offset']} "
            f"changed_bytes={row['changed_bytes']} "
            f"diff_runs={len(row['diff_runs'])} bool_candidates={len(row['boolean_transition_candidates'])} "
            f"field_tokens_A={len(row['known_field_tokens_A'])} field_tokens_B={len(row['known_field_tokens_B'])}"
        )
    lines += [
        "runtime_generation_allowed=false",
        "status=EVIDENCE_ONLY",
        "active_save_opened=false game_written=false save_or_progression_written=false game_launched=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "KNOWN_RAVEN_CONTEXT_CORRELATION_COMPLETED "
        f"exact_pairs={len(exact_pairs)} changed_pairs={len(changed_rows)} "
        f"region_disappeared={report['slot_presence']['region_disappeared']} "
        f"stock_disappeared={report['slot_presence']['stock_disappeared']}"
    )
    print("active_save_opened=false game_written=false game_launched=false runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
