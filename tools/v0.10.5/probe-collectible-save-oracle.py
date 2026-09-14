"""Read-only exact-identity probe for non-Raven collectible state in frozen GoW saves.

This deliberately does not interpret aggregate completion, actor absence, map discovery,
or arbitrary byte differences as collectible truth.  It searches the two known frozen
backup saves for row-specific native identities, both in the raw container and inside
validated zlib streams.  Only hashes/offsets and known-token labels are emitted; no
arbitrary save byte excerpts are written to the report.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import uuid
import zlib

SAVE_SIZE = 33_554_400
PREFIX_SIZE = 4_160
SLOT_SIZE = 1_677_512
SLOT_COUNT = 20
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
MAX_HITS_PER_TOKEN = 8
CONTEXT_RADIUS = 128

EXPECTED_BACKUPS = {
    "GodOfWar-SaveBackup-2026-09-13_21-53-50": "617dc5867850dc14b6a4791bc116ace132a84a6a188d3165cec5276049d48438",
    "GodOfWar-SaveBackup-2026-09-13_22-01-52": "d1d7b43780ad878e300507d71059347734f96515d2ae3d0cf40e9571216bc63d",
}

KNOWN_NEAR_TOKENS = {
    "artefact": ("state", "ACQUIRED"),
    "lore_marker": ("mapSummaryComplete", "bRuneReadStarted", "wellRead"),
    "legendary_chest": ("state", "OPENED"),
    "nornir_chest": ("state", "OPENED"),
    "nornir_seal": ("destroyed", "rune"),
    "nornir_bell": ("ring", "cooldown"),
    "nornir_mechanism": ("state", "rune"),
}


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
    raise RuntimeError(f"Save is not inside one of the two frozen backup directories: {resolved}")


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_save(path: Path) -> tuple[str, str, bytes]:
    path = path.expanduser().resolve()
    if path.name.lower() != "game.sav" or not path.is_file():
        raise RuntimeError(f"Expected an existing game.sav, got: {path}")
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    if is_under(path, active):
        raise RuntimeError("Refusing to open the active God of War save directory")
    name = backup_name(path)
    expected = EXPECTED_BACKUPS[name]
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"Frozen backup hash mismatch for {name}: {actual}")
    if path.stat().st_size != SAVE_SIZE:
        raise RuntimeError(f"Unexpected save size for {name}: {path.stat().st_size}")
    blob = path.read_bytes()
    if len(blob) != SAVE_SIZE:
        raise RuntimeError(f"Short read for {name}")
    words = struct.unpack_from("<8I", blob, 0)
    if words[6] != SAVE_SIZE:
        raise RuntimeError(f"Declared save size mismatch for {name}: {words[6]}")
    if words[5] != SLOT_SIZE or SAVE_SIZE % SLOT_SIZE != PREFIX_SIZE:
        raise RuntimeError(f"Known aligned slot layout changed for {name}")
    if (SAVE_SIZE - PREFIX_SIZE) // SLOT_SIZE != SLOT_COUNT:
        raise RuntimeError(f"Known slot count changed for {name}")
    return name, actual, blob


def add_text(reps: dict[bytes, set[str]], label: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        return
    raw = value.encode("utf-8")
    if len(raw) >= 8:
        reps[raw].add(label + ":utf8")
    wide = value.encode("utf-16le")
    if len(wide) >= 8:
        reps[wide].add(label + ":utf16le")


def add_uuid(reps: dict[bytes, set[str]], label: str, value: object) -> None:
    if not isinstance(value, str):
        return
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return
    add_text(reps, label, str(parsed))
    reps[parsed.bytes].add(label + ":uuid_be")
    reps[parsed.bytes_le].add(label + ":uuid_le")


def add_hex_record(reps: dict[bytes, set[str]], label: str, value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return
    add_text(reps, label, value.lower())
    reps[bytes.fromhex(value)].add(label + ":raw16")


def row_representations(row: dict) -> dict[bytes, set[str]]:
    reps: dict[bytes, set[str]] = defaultdict(set)
    native = row.get("native", {})
    progression = row.get("progression", {})

    add_uuid(reps, "instance_guid", native.get("instance_guid"))
    add_uuid(reps, "state_instance_guid", native.get("state_instance_guid"))
    add_uuid(reps, "placement_record_uuid_hint", native.get("placement_record_uuid_hint"))
    add_text(reps, "instance_key", progression.get("instance_key"))

    for field in ("final_record_id", "override_record_id", "placement_final_record_id", "placement_override_record_id"):
        add_hex_record(reps, field, native.get(field))

    instance_guid = native.get("instance_guid")
    for value in native.get("attribute_values", []):
        if isinstance(value, str) and isinstance(instance_guid, str) and instance_guid in value and "." in value:
            add_text(reps, "native_attribute_composite", value)

    return reps


def build_unique_identity_index(rows: list[dict]) -> tuple[dict[bytes, dict], dict[str, int]]:
    uses: dict[bytes, list[tuple[str, str, set[str]]]] = defaultdict(list)
    for row in rows:
        cid = row["catalogue_id"]
        family = row["family"]
        for token, labels in row_representations(row).items():
            uses[token].append((cid, family, labels))

    index: dict[bytes, dict] = {}
    excluded_shared = 0
    for token, token_uses in uses.items():
        owners = {item[0] for item in token_uses}
        if len(owners) != 1:
            excluded_shared += 1
            continue
        cid = next(iter(owners))
        family = next(item[1] for item in token_uses if item[0] == cid)
        labels: set[str] = set()
        for owner, _, item_labels in token_uses:
            if owner == cid:
                labels.update(item_labels)
        index[token] = {
            "catalogue_id": cid,
            "family": family,
            "labels": sorted(labels),
            "token_sha256": sha256_bytes(token),
            "token_length": len(token),
        }
    return index, {"unique_tokens": len(index), "shared_tokens_excluded": excluded_shared}


def compile_index(index: dict[bytes, dict]) -> re.Pattern[bytes]:
    if not index:
        raise RuntimeError("No row-specific identity representations were generated")
    alternatives = sorted(index, key=lambda item: (-len(item), item))
    return re.compile(b"(?:" + b"|".join(re.escape(item) for item in alternatives) + b")")


def location_for_absolute(offset: int) -> dict:
    if offset < PREFIX_SIZE:
        return {"area": "global_prefix", "absolute_offset": offset}
    rel = offset - PREFIX_SIZE
    slot = rel // SLOT_SIZE
    return {
        "area": "aligned_slot",
        "slot": slot,
        "slot_offset": rel % SLOT_SIZE,
        "absolute_offset": offset,
    }


def nearby_known_tokens(window: bytes, family: str) -> list[str]:
    found: list[str] = []
    for text in KNOWN_NEAR_TOKENS.get(family, ()):
        if text.encode("ascii") in window or text.encode("utf-16le") in window:
            found.append(text)
    return found


def scan_identity_matches(data: bytes, pattern: re.Pattern[bytes], index: dict[bytes, dict], *, domain: dict) -> list[dict]:
    hits: list[dict] = []
    counts: Counter[bytes] = Counter()
    for match in pattern.finditer(data):
        token = match.group(0)
        counts[token] += 1
        if counts[token] > MAX_HITS_PER_TOKEN:
            continue
        meta = index[token]
        start = match.start()
        lo = max(0, start - CONTEXT_RADIUS)
        hi = min(len(data), match.end() + CONTEXT_RADIUS)
        window = data[lo:hi]
        hit = {
            **domain,
            "catalogue_id": meta["catalogue_id"],
            "family": meta["family"],
            "labels": meta["labels"],
            "token_sha256": meta["token_sha256"],
            "token_length": meta["token_length"],
            "match_offset": start,
            "window_sha256": sha256_bytes(window),
            "near_known_field_tokens": nearby_known_tokens(window, meta["family"]),
        }
        hits.append(hit)
    return hits


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


def scan_zlib(blob: bytes, pattern: re.Pattern[bytes], index: dict[bytes, dict]) -> tuple[list[dict], dict]:
    all_hits: list[dict] = []
    validated = 0
    with_identity = 0
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
            validated += 1
            hits = scan_identity_matches(
                raw,
                pattern,
                index,
                domain={
                    "domain": "zlib",
                    "slot": slot,
                    "compressed_slot_offset": at,
                    "compressed_bytes": consumed,
                    "decompressed_bytes": len(raw),
                    "stream_sha256": sha256_bytes(raw),
                },
            )
            if hits:
                with_identity += 1
                all_hits.extend(hits)
    return all_hits, {"validated_streams": validated, "streams_with_exact_identity": with_identity}


def same_location_key(hit: dict) -> tuple:
    if hit["domain"] == "raw":
        return ("raw", hit["token_sha256"], hit["absolute_offset"])
    return (
        "zlib",
        hit["token_sha256"],
        hit["slot"],
        hit["compressed_slot_offset"],
        hit["match_offset"],
    )


def compare_contexts(a_hits: list[dict], b_hits: list[dict]) -> list[dict]:
    a_map = {same_location_key(hit): hit for hit in a_hits}
    b_map = {same_location_key(hit): hit for hit in b_hits}
    candidates: list[dict] = []
    for key in sorted(set(a_map) & set(b_map), key=str):
        a = a_map[key]
        b = b_map[key]
        if a["window_sha256"] == b["window_sha256"]:
            continue
        candidates.append({
            "catalogue_id": a["catalogue_id"],
            "family": a["family"],
            "domain": a["domain"],
            "labels": a["labels"],
            "token_sha256": a["token_sha256"],
            "same_identity_location": True,
            "A_window_sha256": a["window_sha256"],
            "B_window_sha256": b["window_sha256"],
            "A_near_known_field_tokens": a["near_known_field_tokens"],
            "B_near_known_field_tokens": b["near_known_field_tokens"],
            "location": {k: a[k] for k in ("absolute_offset", "slot", "compressed_slot_offset", "match_offset") if k in a},
            "interpretation": "candidate_only_not_state_proof",
        })
    return candidates


def summarize_rows(rows: list[dict], hits_a: list[dict], hits_b: list[dict]) -> list[dict]:
    by_save = []
    for hits in (hits_a, hits_b):
        counts: Counter[str] = Counter(hit["catalogue_id"] for hit in hits)
        domains: dict[str, set[str]] = defaultdict(set)
        labels: dict[str, set[str]] = defaultdict(set)
        for hit in hits:
            cid = hit["catalogue_id"]
            domains[cid].add(hit["domain"])
            labels[cid].update(hit["labels"])
        by_save.append((counts, domains, labels))

    out: list[dict] = []
    for row in rows:
        cid = row["catalogue_id"]
        ca, da, la = by_save[0]
        cb, db, lb = by_save[1]
        if ca[cid] == 0 and cb[cid] == 0:
            continue
        out.append({
            "catalogue_id": cid,
            "family": row["family"],
            "display_name": row["display_name"],
            "instance_key": row.get("progression", {}).get("instance_key"),
            "A_hits": ca[cid],
            "B_hits": cb[cid],
            "A_domains": sorted(da[cid]),
            "B_domains": sorted(db[cid]),
            "identity_labels_seen": sorted(la[cid] | lb[cid]),
            "state_oracle": "unproven",
        })
    return out


def raw_scan(blob: bytes, pattern: re.Pattern[bytes], index: dict[bytes, dict]) -> list[dict]:
    hits = scan_identity_matches(blob, pattern, index, domain={"domain": "raw"})
    for hit in hits:
        hit.update(location_for_absolute(hit["match_offset"]))
    return hits


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Collectible save-oracle probe",
        "",
        f"Status: **{report['status']}**",
        "",
        "This is a read-only forensic scan of the two frozen backup saves. Exact native identity hits are evidence of serialization identity only; they are **not** interpreted as completion state. Aggregate counters, actor absence, and discovery are not used.",
        "",
        "No arbitrary save-byte excerpts are emitted. The report stores only offsets, hashes, catalogue identities, and labels of known field tokens.",
        "",
        "## Inputs",
        "",
    ]
    for save in report["saves"]:
        lines.append(f"- `{save['backup']}` — `{save['sha256']}`")
    lines += [
        "",
        "## Scan summary",
        "",
        f"- Catalogue rows: {report['catalogue_rows']}",
        f"- Row-specific identity representations: {report['identity_index']['unique_tokens']}",
        f"- Shared/non-row-specific representations excluded: {report['identity_index']['shared_tokens_excluded']}",
        f"- Rows with any exact native identity hit: {len(report['rows_with_identity_hits'])}",
        f"- Same-location identity contexts that differ A↔B: {len(report['context_change_candidates'])}",
        "- Proven unloaded per-instance completion oracle: **0**",
        "",
        "## Family identity-hit counts",
        "",
    ]
    for family, count in sorted(report["family_rows_with_hits"].items()):
        lines.append(f"- `{family}`: {count} rows")
    lines += [
        "",
        "## Interpretation",
        "",
        "A differing hashed neighborhood around the same exact identity is only a lead for the next parser step. Without a semantically bound persisted field/value and known opposite completion states for the same object, it is not enough to mark a collectible complete or incomplete.",
        "",
        "Runtime generation therefore remains fail-closed.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-a", type=Path, required=True)
    parser.add_argument("--save-b", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    name_a, hash_a, blob_a = validate_save(args.save_a)
    name_b, hash_b, blob_b = validate_save(args.save_b)
    if name_a == name_b:
        raise RuntimeError("The two inputs resolve to the same frozen backup")

    catalogue_bytes = args.catalogue.read_bytes()
    catalogue = json.loads(catalogue_bytes.decode("utf-8"))
    rows = catalogue.get("collectibles")
    if not isinstance(rows, list) or len(rows) != 238:
        raise RuntimeError(f"Expected the reviewed 238-row catalogue, got {len(rows) if isinstance(rows, list) else 'invalid'}")
    if catalogue.get("state_gate") != "unloaded_per_instance_queries_unresolved":
        raise RuntimeError("Catalogue state gate changed unexpectedly")

    index, identity_stats = build_unique_identity_index(rows)
    pattern = compile_index(index)

    raw_a = raw_scan(blob_a, pattern, index)
    raw_b = raw_scan(blob_b, pattern, index)
    zlib_a, zstats_a = scan_zlib(blob_a, pattern, index)
    zlib_b, zstats_b = scan_zlib(blob_b, pattern, index)
    hits_a = raw_a + zlib_a
    hits_b = raw_b + zlib_b

    row_summary = summarize_rows(rows, hits_a, hits_b)
    candidates = compare_contexts(hits_a, hits_b)
    family_counts = Counter(row["family"] for row in row_summary)

    # Re-hash after all reads.  The scanner has no write path to either input.
    after_a = sha256_file(args.save_a.resolve())
    after_b = sha256_file(args.save_b.resolve())
    if after_a != hash_a or after_b != hash_b:
        raise RuntimeError("Frozen backup hash changed during read-only oracle scan")

    report = {
        "schema": 1,
        "scan_kind": "collectible_exact_identity_save_oracle_probe",
        "status": "BLOCKED_NO_PROVEN_ORACLE",
        "reason": "exact_identity_hits_do_not_yet_bind_to_semantically_proven_per_instance_completion_values",
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "source_hashes_unchanged": True,
            "arbitrary_save_bytes_emitted": False,
            "aggregate_completion_inference_used": False,
            "actor_absence_inference_used": False,
        },
        "catalogue_sha256": sha256_bytes(catalogue_bytes),
        "catalogue_rows": len(rows),
        "identity_index": identity_stats,
        "saves": [
            {"label": "A", "backup": name_a, "sha256": hash_a, "size": len(blob_a)},
            {"label": "B", "backup": name_b, "sha256": hash_b, "size": len(blob_b)},
        ],
        "scan_stats": {
            "A_raw_hits": len(raw_a),
            "B_raw_hits": len(raw_b),
            "A_zlib_hits": len(zlib_a),
            "B_zlib_hits": len(zlib_b),
            "A_zlib": zstats_a,
            "B_zlib": zstats_b,
        },
        "family_rows_with_hits": dict(sorted(family_counts.items())),
        "rows_with_identity_hits": row_summary,
        "context_change_candidates": candidates,
        "oracle_contract": {
            "proven_rows": [],
            "unknown_rows_remain_hidden": True,
            "runtime_generation_allowed": False,
            "proof_requirement": "exact per-instance identity plus semantically validated persisted value across known opposite states",
        },
    }

    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.output_md, report)
    summary = [
        "status=BLOCKED_NO_PROVEN_ORACLE",
        f"catalogue_rows={len(rows)}",
        f"unique_identity_tokens={identity_stats['unique_tokens']}",
        f"rows_with_identity_hits={len(row_summary)}",
        f"context_change_candidates={len(candidates)}",
        "proven_oracle_rows=0",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "source_hashes_unchanged=true",
        "save_or_progression_written=false",
        "game_launched=false",
    ]
    args.summary.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("COLLECTIBLE_SAVE_ORACLE_SCAN_COMPLETED")
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
