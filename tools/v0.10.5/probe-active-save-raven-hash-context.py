#!/usr/bin/env python3
"""Read-only context probe for Raven object hashes in the authoritative GoW save slot.

Chooses the newest of the 20 aligned game.sav ring slots, locates all 53 proven
Raven object hashes in raw slot bytes and validated zlib streams, labels only
states that current RegionSummary aggregates prove exactly, and compares byte
contexts around unambiguous killed vs alive hashes.

The active save is opened read-only and SHA-256 verified unchanged afterwards.
No save, progression, game, or process writes are performed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENTITIES = REPO / "catalogue" / "odins-ravens-save-identities.json"
CATALOGUE = REPO / "catalogue" / "odins-ravens.json"
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
CONTEXT = 96


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def layout(blob: bytes) -> tuple[int, int, int]:
    if len(blob) < 32:
        raise RuntimeError("game.sav too short")
    words = struct.unpack_from("<8I", blob, 0)
    stride = int(words[5])
    declared = int(words[6])
    if declared != len(blob):
        raise RuntimeError(f"declared save size mismatch: {declared} != {len(blob)}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count != 20:
        raise RuntimeError(f"expected 20 save-ring slots, found {count}")
    return prefix, stride, count


def valid_zlib(data: bytes, off: int) -> bool:
    if off + 1 >= len(data):
        return False
    cmf, flg = data[off], data[off + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and (((cmf << 8) | flg) % 31) == 0


def decompress_at(data: bytes, off: int):
    if not valid_zlib(data, off):
        return None
    src = data[off:min(len(data), off + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(src, MAX_DECOMPRESSED + 1)
        if not obj.eof or not raw or len(raw) > MAX_DECOMPRESSED:
            return None
        consumed = len(src) - len(obj.unused_data)
        return (raw, consumed) if consumed > 2 else None
    except zlib.error:
        return None


def find_all(data: bytes, needle: bytes, limit: int = 128) -> list[int]:
    out = []
    start = 0
    while len(out) < limit:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def extract_context(data: bytes, at: int, n: int) -> dict:
    lo = max(0, at - CONTEXT)
    hi = min(len(data), at + n + CONTEXT)
    raw = data[lo:hi]
    return {
        "context_start": lo,
        "hash_offset_in_context": at - lo,
        "context_hex": raw.hex(),
        "context_ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in raw),
    }


def latest_quest_report() -> Path | None:
    roots = sorted(
        (REPO / "archive" / "field-logs" / "runtime-captures").glob(
            "raven-authoritative-quest-records-*/console-log.txt"
        ),
        key=lambda p: p.parent.name,
        reverse=True,
    )
    return roots[0] if roots else None


def quest_states(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("RegionSummary_") or " found=True " not in line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        parent = parts[0]
        fields = {}
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            fields[key] = value
        try:
            progress = int(fields["progress"])
            goal = int(fields["goal"])
        except (KeyError, ValueError):
            continue
        out[parent] = {"progress": progress, "goal": goal}
    return out


def classify_rows(catalogue: dict, qstate: dict[str, dict]) -> dict[str, dict]:
    parent_rows = defaultdict(list)
    for row in catalogue["ravens"]:
        parent_rows[row["progression"]["parent_quest"]].append(row)

    result = {}
    for parent, rows in parent_rows.items():
        q = qstate.get(parent)
        surplus = any(
            "parent_contains_one_bonus_untracked_raven" in (r.get("special_handling") or [])
            for r in rows
        )
        label = "unknown"
        reason = "aggregate_unavailable"
        if q is not None:
            progress, goal = q["progress"], q["goal"]
            if progress == 0:
                label = "alive"
                reason = "aggregate_zero_progress"
            elif (not surplus) and goal == len(rows) and progress >= goal:
                label = "killed"
                reason = "aggregate_complete_exact_count"
            else:
                label = "ambiguous"
                reason = "partial_or_surplus_parent"
        for row in rows:
            result[row["catalogue_id"]] = {
                "state_label": label,
                "state_reason": reason,
                "parent": parent,
                "progress": None if q is None else q["progress"],
                "goal": None if q is None else q["goal"],
                "catalogue_count": len(rows),
                "surplus_parent": surplus,
            }
    return result


def signature_candidates(rows: list[dict], source_kind: str) -> list[dict]:
    labeled = {"killed": [], "alive": []}
    for row in rows:
        label = row["classification"]["state_label"]
        if label not in labeled:
            continue
        occurrences = row["raw_occurrences"] if source_kind == "raw" else row["stream_occurrences"]
        if len(occurrences) != 1:
            continue
        occ = occurrences[0]
        raw = bytes.fromhex(occ["context_hex"])
        center = int(occ["hash_offset_in_context"])
        labeled[label].append((raw, center))

    killed = labeled["killed"]
    alive = labeled["alive"]
    if len(killed) < 2 or len(alive) < 1:
        return []

    out = []
    for rel in range(-64, 65):
        if 0 <= rel < 8:
            continue
        kv, av = [], []
        valid = True
        for raw, center in killed:
            idx = center + rel
            if idx < 0 or idx >= len(raw):
                valid = False
                break
            kv.append(raw[idx])
        if not valid:
            continue
        for raw, center in alive:
            idx = center + rel
            if idx < 0 or idx >= len(raw):
                valid = False
                break
            av.append(raw[idx])
        if valid and len(set(kv)) == 1 and len(set(av)) == 1 and kv[0] != av[0]:
            out.append({
                "relative_offset": rel,
                "killed_byte": kv[0],
                "alive_byte": av[0],
                "killed_samples": len(killed),
                "alive_samples": len(alive),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    save_root = args.save_root.expanduser().resolve()
    saves = sorted(p.resolve() for p in save_root.rglob("game.sav") if p.is_file())
    if len(saves) != 1:
        raise RuntimeError(f"expected exactly one active game.sav under {save_root}, found {len(saves)}")
    save = saves[0]

    before = sha256_file(save)
    blob = save.read_bytes()
    prefix, stride, count = layout(blob)

    slots = []
    for i in range(count):
        start = prefix + i * stride
        slot = blob[start:start + stride]
        stamp = struct.unpack_from("<I", slot, 0)[0]
        slots.append((stamp, i, slot))
    stamp, slot_index, slot = max(slots, key=lambda x: x[0])

    identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    if identities.get("identity_count") != 53 or len(catalogue.get("ravens", [])) != 53:
        raise RuntimeError("53-Raven identity/catalogue contract not satisfied")

    qreport = latest_quest_report()
    classes = classify_rows(catalogue, quest_states(qreport))
    cat_by_id = {r["catalogue_id"]: r for r in catalogue["ravens"]}

    streams = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        got = decompress_at(slot, at)
        if got is None:
            continue
        raw, used = got
        streams.append({
            "offset": at,
            "compressed_bytes": used,
            "raw": raw,
            "has_ravenKilled": b"ravenKilled" in raw,
        })

    rows = []
    for ident in identities["identities"]:
        cid = ident["catalogue_id"]
        needle = int(ident["object_hash_hex"], 16).to_bytes(8, "little")
        raw_occurrences = [
            {"slot_offset": at, **extract_context(slot, at, len(needle))}
            for at in find_all(slot, needle)
        ]
        stream_occurrences = []
        for stream in streams:
            for at in find_all(stream["raw"], needle):
                stream_occurrences.append({
                    "stream_offset": stream["offset"],
                    "stream_compressed_bytes": stream["compressed_bytes"],
                    "stream_has_ravenKilled": stream["has_ravenKilled"],
                    "decoded_offset": at,
                    **extract_context(stream["raw"], at, len(needle)),
                })

        c = cat_by_id[cid]
        rows.append({
            "catalogue_id": cid,
            "object_hash_hex": ident["object_hash_hex"],
            "realm": c["realm"],
            "region": c["region"],
            "wad": c["source"]["wad"],
            "object_name": c["native"]["object_name"],
            "classification": classes[cid],
            "raw_occurrences": raw_occurrences,
            "stream_occurrences": stream_occurrences,
        })

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav changed during read-only context probe")

    report = {
        "schema": 1,
        "analysis": "authoritative_slot_raven_object_hash_context",
        "save_sha256": before,
        "layout": {"prefix": prefix, "stride": stride, "slots": count},
        "authoritative_slot": slot_index,
        "authoritative_timestamp_unix": stamp,
        "latest_quest_report": None if qreport is None else str(qreport.relative_to(REPO)),
        "validated_zlib_streams": len(streams),
        "rows_with_raw_hash": sum(bool(r["raw_occurrences"]) for r in rows),
        "rows_with_stream_hash": sum(bool(r["stream_occurrences"]) for r in rows),
        "state_label_counts": dict(Counter(r["classification"]["state_label"] for r in rows)),
        "raw_signature_candidates": signature_candidates(rows, "raw"),
        "stream_signature_candidates": signature_candidates(rows, "stream"),
        "rows": rows,
        "safety": {
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "ACTIVE_RAVEN_HASH_CONTEXT_COMPLETE "
        f"slot={slot_index} timestamp={stamp} rawRows={report['rows_with_raw_hash']} "
        f"streamRows={report['rows_with_stream_hash']} streams={len(streams)}"
    )
    print("state_labels=" + ",".join(f"{k}:{v}" for k, v in sorted(report["state_label_counts"].items())))
    print(f"raw_signature_candidates={len(report['raw_signature_candidates'])}")
    print(f"stream_signature_candidates={len(report['stream_signature_candidates'])}")
    for row in rows:
        if row["raw_occurrences"] or row["stream_occurrences"]:
            c = row["classification"]
            print(
                f"HASH {row['catalogue_id']} region={row['region']} "
                f"state={c['state_label']} progress={c['progress']}/{c['goal']} "
                f"raw={len(row['raw_occurrences'])} stream={len(row['stream_occurrences'])}"
            )
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
