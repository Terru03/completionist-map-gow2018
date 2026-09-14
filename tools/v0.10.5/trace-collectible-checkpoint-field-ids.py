"""Read-only structural trace for collectible checkpoint-field IDs in frozen GoW saves.

This is a narrowing probe, not a completion oracle. It derives 16-byte schema field
IDs from schema-style zlib streams containing known collectible checkpoint field
names, then traces those IDs through raw aligned slots and validated zlib streams.
No aggregate counters, actor absence, discovery, or arbitrary byte differences are
interpreted as individual collectible state.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

SAVE_SIZE = 33_554_400
PREFIX_SIZE = 4_160
SLOT_SIZE = 1_677_512
SLOT_COUNT = 20
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
FIELD_RECORD_SIZE = 25
FIELD_PREFIX_SIZE = 9
MAX_SCHEMA_OCCURRENCES = 12
MAX_HIT_LOCATIONS = 24
MAX_NAMES_PER_SCHEMA = 120

EXPECTED_BACKUPS = {
    "GodOfWar-SaveBackup-2026-09-13_21-53-50": "617dc5867850dc14b6a4791bc116ace132a84a6a188d3165cec5276049d48438",
    "GodOfWar-SaveBackup-2026-09-13_22-01-52": "d1d7b43780ad878e300507d71059347734f96515d2ae3d0cf40e9571216bc63d",
}

TARGET_FIELDS = (
    "ravenKilled",
    "state",
    "mapSummaryComplete",
    "bRuneReadStarted",
    "wellRead",
    "destroyed",
    "keysUsed",
    "challengeComplete",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_name(path: Path) -> str:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name in EXPECTED_BACKUPS:
            return parent.name
    raise RuntimeError(f"Save is not inside an expected frozen backup: {resolved}")


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_save(path: Path) -> tuple[str, str, bytes]:
    path = path.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    if path.name.lower() != "game.sav" or not path.is_file():
        raise RuntimeError(f"Expected an existing game.sav: {path}")
    if is_under(path, active):
        raise RuntimeError("Refusing to open the active God of War save directory")
    name = backup_name(path)
    actual = sha256_file(path)
    expected = EXPECTED_BACKUPS[name]
    if actual != expected:
        raise RuntimeError(f"Frozen backup hash mismatch for {name}: {actual}")
    if path.stat().st_size != SAVE_SIZE:
        raise RuntimeError(f"Unexpected save size for {name}: {path.stat().st_size}")
    blob = path.read_bytes()
    words = struct.unpack_from("<8I", blob, 0)
    if words[6] != SAVE_SIZE or words[5] != SLOT_SIZE:
        raise RuntimeError(f"Known save layout mismatch for {name}")
    if SAVE_SIZE % SLOT_SIZE != PREFIX_SIZE:
        raise RuntimeError("Known prefix/stride invariant changed")
    if (SAVE_SIZE - PREFIX_SIZE) // SLOT_SIZE != SLOT_COUNT:
        raise RuntimeError("Known slot-count invariant changed")
    return name, actual, blob


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) + flg) % 31 == 0


def decompress_stream(data: bytes, offset: int) -> tuple[bytes, int] | None:
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset:min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(raw) > MAX_DECOMPRESSED or not obj.eof or not raw:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return raw, consumed
    except zlib.error:
        return None


def scan_streams(blob: bytes) -> list[dict]:
    streams: list[dict] = []
    for slot in range(SLOT_COUNT):
        start = PREFIX_SIZE + slot * SLOT_SIZE
        chunk = blob[start:start + SLOT_SIZE]
        cursor = 0
        while True:
            at = chunk.find(b"\x78", cursor)
            if at < 0:
                break
            cursor = at + 1
            result = decompress_stream(chunk, at)
            if result is None:
                continue
            raw, consumed = result
            streams.append({
                "slot": slot,
                "relative_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "raw": raw,
            })
    return streams


def printable_name(part: bytes) -> bool:
    return bool(part) and len(part) <= 160 and all(0x20 <= b <= 0x7E for b in part)


def parse_schema_for_target(raw: bytes, target: str) -> dict | None:
    needle = target.encode("ascii")
    if needle not in raw:
        return None
    candidates: list[dict] = []
    max_fields = min(512, (len(raw) - 1) // FIELD_RECORD_SIZE)
    for n in range(1, max_fields + 1):
        split = len(raw) - n * FIELD_RECORD_SIZE
        if split <= 0:
            break
        names_blob = raw[:split]
        if not names_blob.endswith(b"\0") or needle not in names_blob:
            continue
        parts = names_blob[:-1].split(b"\0")
        if len(parts) != n or not all(printable_name(part) for part in parts):
            continue
        try:
            names = [part.decode("ascii") for part in parts]
        except UnicodeDecodeError:
            continue
        if target not in names:
            continue
        records = [
            raw[split + i * FIELD_RECORD_SIZE: split + (i + 1) * FIELD_RECORD_SIZE]
            for i in range(n)
        ]
        prefixes = [record[:FIELD_PREFIX_SIZE] for record in records]
        ids = [record[FIELD_PREFIX_SIZE:] for record in records]
        candidates.append({
            "split": split,
            "names": names,
            "records": records,
            "prefixes": prefixes,
            "ids": ids,
            "common_record_prefix": len(set(prefixes)) == 1,
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (not c["common_record_prefix"], -len(c["names"]), c["split"]))
    best = candidates[0]
    best["candidate_count"] = len(candidates)
    return best


def derive_field_ids(streams_by_label: dict[str, list[dict]]) -> tuple[dict[bytes, dict], dict]:
    ids: dict[bytes, dict] = {}
    target_schema_counts: dict[str, int] = defaultdict(int)
    for label, streams in streams_by_label.items():
        for stream in streams:
            raw = stream["raw"]
            for target in TARGET_FIELDS:
                if target.encode("ascii") not in raw:
                    continue
                parsed = parse_schema_for_target(raw, target)
                if parsed is None:
                    continue
                idx = parsed["names"].index(target)
                fid = parsed["ids"][idx]
                prefix = parsed["prefixes"][idx]
                target_schema_counts[target] += 1
                item = ids.setdefault(fid, {
                    "field_id_hex": fid.hex(),
                    "targets": set(),
                    "record_prefixes": set(),
                    "schema_occurrences": [],
                    "schema_name_sets": set(),
                })
                item["targets"].add(target)
                item["record_prefixes"].add(prefix.hex())
                names_tuple = tuple(parsed["names"][:MAX_NAMES_PER_SCHEMA])
                item["schema_name_sets"].add(names_tuple)
                if len(item["schema_occurrences"]) < MAX_SCHEMA_OCCURRENCES:
                    item["schema_occurrences"].append({
                        "save": label,
                        "slot": stream["slot"],
                        "relative_offset": stream["relative_offset"],
                        "stream_sha256": stream["sha256"],
                        "field_count": len(parsed["names"]),
                        "schema_candidate_count": parsed["candidate_count"],
                        "common_record_prefix": parsed["common_record_prefix"],
                    })
    return ids, dict(sorted(target_schema_counts.items()))


def compile_id_pattern(ids: dict[bytes, dict]) -> re.Pattern[bytes] | None:
    if not ids:
        return None
    alternatives = sorted(ids, key=lambda token: (-len(token), token))
    return re.compile(b"(?:" + b"|".join(re.escape(token) for token in alternatives) + b")")


def trace_ids(blob: bytes, streams: list[dict], ids: dict[bytes, dict], pattern: re.Pattern[bytes] | None) -> dict:
    raw_hits: dict[str, list[dict]] = defaultdict(list)
    stream_hits: dict[str, list[dict]] = defaultdict(list)
    if pattern is None:
        return {"raw_hits": raw_hits, "stream_hits": stream_hits}

    for slot in range(SLOT_COUNT):
        start = PREFIX_SIZE + slot * SLOT_SIZE
        chunk = blob[start:start + SLOT_SIZE]
        for match in pattern.finditer(chunk):
            key = match.group(0).hex()
            if len(raw_hits[key]) < MAX_HIT_LOCATIONS:
                raw_hits[key].append({"slot": slot, "slot_offset": match.start()})

    for stream in streams:
        raw = stream["raw"]
        literal_targets = [target for target in TARGET_FIELDS if target.encode("ascii") in raw]
        for match in pattern.finditer(raw):
            token = match.group(0)
            key = token.hex()
            meta = ids[token]
            defining_literal_present = any(target in literal_targets for target in meta["targets"])
            if len(stream_hits[key]) < MAX_HIT_LOCATIONS:
                stream_hits[key].append({
                    "slot": stream["slot"],
                    "relative_offset": stream["relative_offset"],
                    "match_offset": match.start(),
                    "stream_sha256": stream["sha256"],
                    "decompressed_bytes": stream["decompressed_bytes"],
                    "defining_target_literal_present": defining_literal_present,
                    "literal_targets": literal_targets,
                })
    return {"raw_hits": raw_hits, "stream_hits": stream_hits}


def stream_map(streams: list[dict]) -> dict[tuple[int, int], dict]:
    return {(s["slot"], s["relative_offset"]): s for s in streams}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-a", type=Path, required=True)
    ap.add_argument("--save-b", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    name_a, hash_a, blob_a = validate_save(args.save_a)
    name_b, hash_b, blob_b = validate_save(args.save_b)
    before = {name_a: hash_a, name_b: hash_b}

    streams_a = scan_streams(blob_a)
    streams_b = scan_streams(blob_b)
    streams_by_label = {"A": streams_a, "B": streams_b}

    ids, schema_counts = derive_field_ids(streams_by_label)
    pattern = compile_id_pattern(ids)
    traced_a = trace_ids(blob_a, streams_a, ids, pattern)
    traced_b = trace_ids(blob_b, streams_b, ids, pattern)

    map_a = stream_map(streams_a)
    map_b = stream_map(streams_b)

    field_reports: list[dict] = []
    structural_candidates: list[dict] = []
    for token in sorted(ids, key=lambda t: (sorted(ids[t]["targets"]), t.hex())):
        key = token.hex()
        meta = ids[token]
        a_stream_hits = traced_a["stream_hits"].get(key, [])
        b_stream_hits = traced_b["stream_hits"].get(key, [])
        a_out = [h for h in a_stream_hits if not h["defining_target_literal_present"]]
        b_out = [h for h in b_stream_hits if not h["defining_target_literal_present"]]

        pair_keys = sorted(
            {(h["slot"], h["relative_offset"]) for h in a_out}
            | {(h["slot"], h["relative_offset"]) for h in b_out}
        )
        changed_pairs: list[dict] = []
        for pair in pair_keys:
            sa = map_a.get(pair)
            sb = map_b.get(pair)
            if sa is None or sb is None or sa["sha256"] == sb["sha256"]:
                continue
            a_matches = [h for h in a_out if (h["slot"], h["relative_offset"]) == pair]
            b_matches = [h for h in b_out if (h["slot"], h["relative_offset"]) == pair]
            row = {
                "slot": pair[0],
                "relative_offset": pair[1],
                "A_stream_sha256": sa["sha256"],
                "B_stream_sha256": sb["sha256"],
                "A_match_offsets": [h["match_offset"] for h in a_matches],
                "B_match_offsets": [h["match_offset"] for h in b_matches],
                "changed_slot_known": pair[0] in (6, 16),
            }
            changed_pairs.append(row)
            structural_candidates.append({
                "field_id_hex": key,
                "targets": sorted(meta["targets"]),
                **row,
            })

        field_reports.append({
            "field_id_hex": key,
            "targets": sorted(meta["targets"]),
            "record_prefixes": sorted(meta["record_prefixes"]),
            "schema_occurrences": meta["schema_occurrences"],
            "schema_name_sets": [list(x) for x in sorted(meta["schema_name_sets"])[:8]],
            "A_raw_hit_count_capped": len(traced_a["raw_hits"].get(key, [])),
            "B_raw_hit_count_capped": len(traced_b["raw_hits"].get(key, [])),
            "A_stream_hit_count_capped": len(a_stream_hits),
            "B_stream_hit_count_capped": len(b_stream_hits),
            "A_outside_defining_literal_count_capped": len(a_out),
            "B_outside_defining_literal_count_capped": len(b_out),
            "changed_paired_streams": changed_pairs[:MAX_HIT_LOCATIONS],
        })

    after = {name_a: sha256_file(args.save_a), name_b: sha256_file(args.save_b)}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during structural field-ID trace")

    candidate_target_counts: dict[str, int] = defaultdict(int)
    for candidate in structural_candidates:
        for target in candidate["targets"]:
            candidate_target_counts[target] += 1

    report = {
        "schema": 1,
        "scan_kind": "collectible_checkpoint_schema_field_id_structural_trace",
        "status": "BLOCKED_STRUCTURAL_TRACE_ONLY",
        "targets": list(TARGET_FIELDS),
        "saves": [
            {"label": "A", "backup": name_a, "sha256": hash_a, "size": len(blob_a)},
            {"label": "B", "backup": name_b, "sha256": hash_b, "size": len(blob_b)},
        ],
        "zlib": {"A_validated_streams": len(streams_a), "B_validated_streams": len(streams_b)},
        "schema_occurrences_by_target": schema_counts,
        "unique_field_ids": len(ids),
        "field_ids": field_reports,
        "structural_candidate_count": len(structural_candidates),
        "structural_candidate_counts_by_target": dict(sorted(candidate_target_counts.items())),
        "structural_candidates": structural_candidates[:250],
        "oracle_contract": {
            "proven_oracle_rows": [],
            "runtime_generation_allowed": False,
            "unknown_rows_remain_hidden": True,
            "interpretation": (
                "Field-ID hits and A/B structural differences are leads only. "
                "They do not bind a persisted value to an exact catalogue row."
            ),
        },
        "safety": {
            "active_save_opened": False,
            "game_launched": False,
            "game_written": False,
            "save_or_progression_written": False,
            "aggregate_completion_inference_used": False,
            "actor_absence_inference_used": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "# Collectible checkpoint field-ID structural trace",
        "",
        "Status: **BLOCKED_STRUCTURAL_TRACE_ONLY**",
        "",
        "This probe derives schema field IDs for known checkpoint fields and traces those IDs through the two frozen saves.",
        "A hit is structural evidence only; it is not an individual completion oracle.",
        "",
        "## Summary",
        "",
        f"- Validated zlib streams: A={len(streams_a)}, B={len(streams_b)}",
        f"- Unique derived 16-byte field IDs: {len(ids)}",
        f"- Changed paired-stream structural candidates: {len(structural_candidates)}",
        "- Runtime generation allowed: **false**",
        "",
        "## Schema occurrences",
        "",
    ]
    for target in TARGET_FIELDS:
        lines.append(f"- `{target}`: {schema_counts.get(target, 0)} parsed schema occurrences")
    lines += ["", "## Candidate counts", ""]
    for target in TARGET_FIELDS:
        lines.append(f"- `{target}`: {candidate_target_counts.get(target, 0)} changed paired-stream candidates")
    lines += [
        "",
        "## Interpretation",
        "",
        "The previous exact-identity probe found zero literal per-row identity representations. This trace therefore looks one layer lower, at schema field IDs. Even a changed field-ID-bearing stream cannot be mapped to a collectible row without an exact instance-record binding and a semantically validated value.",
        "",
        "Unknown state remains hidden/fail-closed.",
    ]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_lines = [
        "COLLECTIBLE_SCHEMA_FIELD_TRACE_COMPLETED",
        "status=BLOCKED_STRUCTURAL_TRACE_ONLY",
        f"unique_field_ids={len(ids)}",
        f"structural_candidate_count={len(structural_candidates)}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "source_hashes_unchanged=true",
        "save_or_progression_written=false",
        "game_launched=false",
    ]
    args.summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
