"""Read-only probe of one runtime-proven Raven identity set against frozen saves.

The generic catalogue identity oracle found no direct catalogue GUID join.  This
probe instead uses identifiers observed for the *same* Veithurgard Raven during a
verified kill -> checkpoint restore -> re-kill lifecycle capture:

- real map marker UID: -2207208259907848386
- native region marker UID: -6808215654220372037
- stock backing marker observed during the same map session: 2924516555722838670
- synthetic twin UID (negative control): 3410085282531601808
- gameplay region quest text: RegionSummary_VF_Raven_Parent
- gameplay object world position: (-64.850898742676, 12.987384796143, 787.30694580078)

It searches exact binary/text representations in both raw save containers and
validated zlib streams.  It never opens the active save tree and emits only labels,
hashes, counts and offsets, never arbitrary save byte excerpts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import zlib

SAVE_SIZE = 33_554_400
PREFIX_SIZE = 4_160
SLOT_SIZE = 1_677_512
SLOT_COUNT = 20
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
MAX_HITS_PER_REP = 64

EXPECTED_BACKUPS = {
    "GodOfWar-SaveBackup-2026-09-13_21-53-50": "617dc5867850dc14b6a4791bc116ace132a84a6a188d3165cec5276049d48438",
    "GodOfWar-SaveBackup-2026-09-13_22-01-52": "d1d7b43780ad878e300507d71059347734f96515d2ae3d0cf40e9571216bc63d",
}

RUNTIME_KEYS = {
    "real_marker_uid": -2207208259907848386,
    "region_uid": -6808215654220372037,
    "stock_backing_uid": 2924516555722838670,
    "synthetic_twin_uid_control": 3410085282531601808,
}
REGION_QUEST = "RegionSummary_VF_Raven_Parent"
WORLD_POSITION = (-64.850898742676, 12.987384796143, 787.30694580078)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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
    raise RuntimeError(f"Save is not inside a frozen expected backup: {resolved}")


def validate_save(path: Path) -> tuple[str, str, bytes]:
    path = path.expanduser().resolve()
    if path.name.lower() != "game.sav" or not path.is_file():
        raise RuntimeError(f"Expected an existing game.sav, got: {path}")
    active = (Path.home() / "Saved Games" / "God of War").resolve()
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
    if len(blob) != SAVE_SIZE:
        raise RuntimeError(f"Short read for {name}")
    words = struct.unpack_from("<8I", blob, 0)
    if words[6] != SAVE_SIZE or words[5] != SLOT_SIZE:
        raise RuntimeError(f"Known save layout changed for {name}")
    if (SAVE_SIZE - PREFIX_SIZE) // SLOT_SIZE != SLOT_COUNT:
        raise RuntimeError(f"Known slot count changed for {name}")
    return name, actual, blob


def add_rep(reps: dict[bytes, set[str]], raw: bytes, label: str) -> None:
    if raw:
        reps[raw].add(label)


def int_representations(reps: dict[bytes, set[str]], name: str, value: int) -> None:
    unsigned = value & 0xFFFFFFFFFFFFFFFF
    signed = value if -(1 << 63) <= value < (1 << 63) else unsigned - (1 << 64)
    add_rep(reps, struct.pack("<Q", unsigned), f"{name}:u64_le")
    add_rep(reps, struct.pack(">Q", unsigned), f"{name}:u64_be")
    add_rep(reps, struct.pack("<q", signed), f"{name}:i64_le")
    add_rep(reps, struct.pack(">q", signed), f"{name}:i64_be")
    decimal = str(value)
    add_rep(reps, decimal.encode("ascii"), f"{name}:decimal_ascii")
    add_rep(reps, decimal.encode("utf-16le"), f"{name}:decimal_utf16le")
    hex16 = f"{unsigned:016x}"
    add_rep(reps, hex16.encode("ascii"), f"{name}:hex_ascii")
    add_rep(reps, ("0x" + hex16).encode("ascii"), f"{name}:0xhex_ascii")


def build_representations() -> dict[bytes, set[str]]:
    reps: dict[bytes, set[str]] = defaultdict(set)
    for name, value in RUNTIME_KEYS.items():
        int_representations(reps, name, value)

    add_rep(reps, REGION_QUEST.encode("ascii"), "region_quest:ascii")
    add_rep(reps, REGION_QUEST.encode("utf-16le"), "region_quest:utf16le")

    x, y, z = WORLD_POSITION
    for axis, value in zip("xyz", WORLD_POSITION):
        add_rep(reps, struct.pack("<f", value), f"world_{axis}:f32_le")
        add_rep(reps, struct.pack("<d", value), f"world_{axis}:f64_le")
    add_rep(reps, struct.pack("<fff", x, y, z), "world_xyz:f32_triplet_le")
    add_rep(reps, struct.pack("<ddd", x, y, z), "world_xyz:f64_triplet_le")
    return reps


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


def raw_location(offset: int) -> dict:
    if offset < PREFIX_SIZE:
        return {"area": "global_prefix", "absolute_offset": offset}
    rel = offset - PREFIX_SIZE
    return {
        "area": "aligned_slot",
        "slot": rel // SLOT_SIZE,
        "slot_offset": rel % SLOT_SIZE,
        "absolute_offset": offset,
    }


def scan_blob(data: bytes, reps: dict[bytes, set[str]], domain: dict) -> list[dict]:
    hits: list[dict] = []
    for raw, labels in sorted(reps.items(), key=lambda item: (-len(item[0]), sorted(item[1]))):
        start = 0
        count = 0
        while count < MAX_HITS_PER_REP:
            at = data.find(raw, start)
            if at < 0:
                break
            count += 1
            hit = {
                **domain,
                "labels": sorted(labels),
                "representation_sha256": sha256_bytes(raw),
                "representation_length": len(raw),
                "match_offset": at,
            }
            hits.append(hit)
            start = at + max(1, len(raw))
    return hits


def scan_save(blob: bytes, reps: dict[bytes, set[str]]) -> tuple[list[dict], dict]:
    hits = scan_blob(blob, reps, {"domain": "raw"})
    for hit in hits:
        hit.update(raw_location(hit["match_offset"]))

    validated = 0
    streams_with_hits = 0
    for slot in range(SLOT_COUNT):
        slot_start = PREFIX_SIZE + slot * SLOT_SIZE
        chunk = blob[slot_start:slot_start + SLOT_SIZE]
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
            stream_hits = scan_blob(raw, reps, {
                "domain": "zlib",
                "slot": slot,
                "compressed_slot_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "stream_sha256": sha256_bytes(raw),
            })
            if stream_hits:
                streams_with_hits += 1
                hits.extend(stream_hits)
    return hits, {"validated_zlib_streams": validated, "zlib_streams_with_hits": streams_with_hits}


def labels_summary(hits: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    labels = sorted({label for hit in hits for label in hit["labels"]})
    for label in labels:
        matching = [hit for hit in hits if label in hit["labels"]]
        out[label] = {
            "hits": len(matching),
            "domains": dict(Counter(hit["domain"] for hit in matching)),
            "locations": [
                {k: hit[k] for k in (
                    "domain", "absolute_offset", "slot", "slot_offset",
                    "compressed_slot_offset", "match_offset", "stream_sha256"
                ) if k in hit}
                for hit in matching[:16]
            ],
        }
    return out


def semantic_key(label: str) -> str:
    return label.split(":", 1)[0]


def semantic_summary(label_summary: dict[str, dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for label, info in label_summary.items():
        key = semantic_key(label)
        row = grouped.setdefault(key, {"hits": 0, "representations": [], "domains": Counter()})
        row["hits"] += info["hits"]
        row["representations"].append({"label": label, "hits": info["hits"]})
        row["domains"].update(info["domains"])
    for row in grouped.values():
        row["domains"] = dict(row["domains"])
        row["representations"].sort(key=lambda x: (-x["hits"], x["label"]))
    return dict(sorted(grouped.items()))


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

    reps = build_representations()
    hits_a, stats_a = scan_save(blob_a, reps)
    hits_b, stats_b = scan_save(blob_b, reps)
    labels_a = labels_summary(hits_a)
    labels_b = labels_summary(hits_b)
    semantic_a = semantic_summary(labels_a)
    semantic_b = semantic_summary(labels_b)

    all_semantics = sorted(set(semantic_a) | set(semantic_b))
    comparison = []
    for key in all_semantics:
        a_count = semantic_a.get(key, {}).get("hits", 0)
        b_count = semantic_b.get(key, {}).get("hits", 0)
        comparison.append({
            "key": key,
            "A_hits": a_count,
            "B_hits": b_count,
            "delta": b_count - a_count,
            "present_in_both": a_count > 0 and b_count > 0,
        })

    exact_runtime_identity_hits = [
        row for row in comparison
        if row["key"] in RUNTIME_KEYS and (row["A_hits"] or row["B_hits"])
    ]
    control = next((row for row in comparison if row["key"] == "synthetic_twin_uid_control"), None)

    report = {
        "schema": 1,
        "scan_kind": "read_only_known_raven_runtime_key_save_probe",
        "runtime_evidence": {
            "real_marker_uid": RUNTIME_KEYS["real_marker_uid"],
            "region_uid": RUNTIME_KEYS["region_uid"],
            "stock_backing_uid": RUNTIME_KEYS["stock_backing_uid"],
            "synthetic_twin_uid_control": RUNTIME_KEYS["synthetic_twin_uid_control"],
            "region_quest": REGION_QUEST,
            "world_position": list(WORLD_POSITION),
            "provenance": "v33-runtime-20260913-193047 verified Raven lifecycle capture",
        },
        "A": {
            "backup": name_a, "sha256": hash_a, **stats_a,
            "total_hits": len(hits_a), "by_label": labels_a, "by_semantic_key": semantic_a,
        },
        "B": {
            "backup": name_b, "sha256": hash_b, **stats_b,
            "total_hits": len(hits_b), "by_label": labels_b, "by_semantic_key": semantic_b,
        },
        "comparison": comparison,
        "exact_runtime_identity_hits": exact_runtime_identity_hits,
        "negative_control": control,
        "interpretation": (
            "A hit for a real runtime identity is evidence of an encoded bridge candidate, "
            "not by itself proof that the value is the collected-state oracle. The synthetic "
            "twin UID is a negative control."
        ),
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "scan_only": True,
            "frozen_backup_hashes_verified": True,
        },
    }

    lines = [
        "Completionist Map - known Raven runtime-key save probe",
        f"A={name_a} sha256={hash_a}",
        f"B={name_b} sha256={hash_b}",
        f"A_hits={len(hits_a)} B_hits={len(hits_b)}",
        f"A_zlib={stats_a['validated_zlib_streams']} B_zlib={stats_b['validated_zlib_streams']}",
        "active_save_opened=false game_written=false game_launched=false",
        "",
        "Runtime identity comparison:",
    ]
    for row in comparison:
        if row["key"] in RUNTIME_KEYS or row["key"] in {"region_quest", "world_x", "world_y", "world_z", "world_xyz"}:
            lines.append(
                f"  {row['key']}: A={row['A_hits']} B={row['B_hits']} delta={row['delta']}"
            )
    lines.append("")
    if exact_runtime_identity_hits:
        lines.append("BRIDGE_CANDIDATE_PRESENT=true")
        for row in exact_runtime_identity_hits:
            lines.append(f"  candidate={row['key']} A={row['A_hits']} B={row['B_hits']}")
    else:
        lines.append("BRIDGE_CANDIDATE_PRESENT=false")
    control_hits = 0 if control is None else control["A_hits"] + control["B_hits"]
    lines.append(f"synthetic_twin_control_hits={control_hits}")
    lines.append("runtime_generation_allowed=false")
    lines.append("status=EVIDENCE_ONLY")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "KNOWN_RAVEN_RUNTIME_KEY_SAVE_PROBE_COMPLETED "
        f"A_hits={len(hits_a)} B_hits={len(hits_b)} "
        f"real_identity_candidates={len(exact_runtime_identity_hits)} control_hits={control_hits}"
    )
    print("active_save_opened=false game_written=false game_launched=false runtime_generation_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
