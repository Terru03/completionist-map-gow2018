"""Read-only structural probe for schema-descriptor / neighboring-payload pairing.

This probe intentionally does NOT decode collectible completion.  It asks a
narrower question: when a zlib stream that contains a known checkpoint schema is
stable between two frozen saves, do nearby zlib streams in the same aligned save
slot change while the descriptor itself stays identical?

Only hashes, offsets, sizes, target field names, and stream ordinals are emitted.
No arbitrary save-byte excerpts are written to the report.  A neighboring change
is a structural lead only; it is never interpreted as state truth.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import zlib

MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
WINDOW = 4
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
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("Save too small for header")
    words = struct.unpack_from("<8I", blob, 0)
    header_size = words[4]
    stride = words[5]
    declared_size = words[6]
    if declared_size != len(blob):
        raise RuntimeError(
            f"Declared size mismatch header={declared_size} actual={len(blob)}"
        )
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"Implausible slot stride {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0 or prefix < header_size:
        raise RuntimeError(
            f"Implausible aligned layout prefix={prefix} slots={count}"
        )
    return {
        "prefix": prefix,
        "stride": stride,
        "slot_count": count,
        "header_size": header_size,
    }


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and ((cmf << 8) + flg) % 31 == 0
    )


def decompress_stream(data: bytes, offset: int) -> tuple[bytes, int] | None:
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset : min(len(data), offset + INPUT_LIMIT)]
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


def scan_slot(slot: bytes, slot_index: int) -> list[dict]:
    streams: list[dict] = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(slot, at):
            continue
        result = decompress_stream(slot, at)
        if result is None:
            continue
        raw, consumed = result
        target_fields = [
            name for name in TARGET_FIELDS if (name.encode("ascii") + b"\0") in raw
        ]
        streams.append(
            {
                "slot": slot_index,
                "index": len(streams),
                "relative_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "target_fields": target_fields,
            }
        )
    return streams


def descriptor_key(stream: dict) -> tuple:
    return (stream["sha256"], tuple(stream["target_fields"]))


def compact_stream(stream: dict | None) -> dict | None:
    if stream is None:
        return None
    return {
        "index": stream["index"],
        "relative_offset": stream["relative_offset"],
        "compressed_bytes": stream["compressed_bytes"],
        "decompressed_bytes": stream["decompressed_bytes"],
        "sha256": stream["sha256"],
    }


def changed_neighbor_pairs(a_streams: list[dict], b_streams: list[dict], a_idx: int, b_idx: int) -> list[dict]:
    changed: list[dict] = []
    for delta in range(-WINDOW, WINDOW + 1):
        if delta == 0:
            continue
        ai = a_idx + delta
        bi = b_idx + delta
        a = a_streams[ai] if 0 <= ai < len(a_streams) else None
        b = b_streams[bi] if 0 <= bi < len(b_streams) else None
        if a is None and b is None:
            continue
        same = a is not None and b is not None and a["sha256"] == b["sha256"]
        if same:
            continue
        changed.append(
            {
                "delta": delta,
                "a": compact_stream(a),
                "b": compact_stream(b),
                "both_present": a is not None and b is not None,
                "same_decompressed_size": (
                    a is not None
                    and b is not None
                    and a["decompressed_bytes"] == b["decompressed_bytes"]
                ),
                "same_compressed_size": (
                    a is not None
                    and b is not None
                    and a["compressed_bytes"] == b["compressed_bytes"]
                ),
            }
        )
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-a", type=Path, required=True)
    ap.add_argument("--save-b", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    save_a = args.save_a.expanduser().resolve()
    save_b = args.save_b.expanduser().resolve()
    if save_a == save_b:
        raise RuntimeError("Frozen save A and B resolve to the same file")
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for path in (save_a, save_b):
        if not path.is_file():
            raise RuntimeError(f"Frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing to inspect active save tree: {path}")

    before = {"A": sha256_file(save_a), "B": sha256_file(save_b)}
    blobs = {"A": save_a.read_bytes(), "B": save_b.read_bytes()}
    layouts = {k: layout(v) for k, v in blobs.items()}
    if layouts["A"] != layouts["B"]:
        raise RuntimeError(f"Frozen saves disagree on aligned layout: {layouts}")
    lay = layouts["A"]

    all_streams: dict[str, list[list[dict]]] = {"A": [], "B": []}
    slot_hashes: dict[str, list[str]] = {"A": [], "B": []}
    for label in ("A", "B"):
        blob = blobs[label]
        for slot_index in range(lay["slot_count"]):
            start = lay["prefix"] + slot_index * lay["stride"]
            slot = blob[start : start + lay["stride"]]
            slot_hashes[label].append(sha256_bytes(slot))
            all_streams[label].append(scan_slot(slot, slot_index))

    changed_slots = [
        i
        for i in range(lay["slot_count"])
        if slot_hashes["A"][i] != slot_hashes["B"][i]
    ]

    candidates: list[dict] = []
    descriptor_pairs = 0
    descriptor_counts = {name: 0 for name in TARGET_FIELDS}

    for slot_index in range(lay["slot_count"]):
        a_streams = all_streams["A"][slot_index]
        b_streams = all_streams["B"][slot_index]
        a_by_key: dict[tuple, list[dict]] = defaultdict(list)
        b_by_key: dict[tuple, list[dict]] = defaultdict(list)
        for stream in a_streams:
            if stream["target_fields"]:
                a_by_key[descriptor_key(stream)].append(stream)
        for stream in b_streams:
            if stream["target_fields"]:
                b_by_key[descriptor_key(stream)].append(stream)

        for key in sorted(set(a_by_key) & set(b_by_key), key=lambda k: (k[1], k[0])):
            aa = sorted(a_by_key[key], key=lambda s: s["index"])
            bb = sorted(b_by_key[key], key=lambda s: s["index"])
            pair_count = min(len(aa), len(bb))
            for rank in range(pair_count):
                a_desc = aa[rank]
                b_desc = bb[rank]
                descriptor_pairs += 1
                for name in a_desc["target_fields"]:
                    descriptor_counts[name] += 1
                changed = changed_neighbor_pairs(
                    a_streams, b_streams, a_desc["index"], b_desc["index"]
                )
                if not changed:
                    continue
                candidates.append(
                    {
                        "slot": slot_index,
                        "slot_changed": slot_index in changed_slots,
                        "target_fields": a_desc["target_fields"],
                        "descriptor_sha256": a_desc["sha256"],
                        "descriptor_rank_for_same_key": rank,
                        "descriptor_a": compact_stream(a_desc),
                        "descriptor_b": compact_stream(b_desc),
                        "descriptor_same_relative_offset": (
                            a_desc["relative_offset"] == b_desc["relative_offset"]
                        ),
                        "changed_neighbors": changed,
                        "changed_neighbor_count": len(changed),
                    }
                )

    candidates.sort(
        key=lambda c: (
            not c["slot_changed"],
            not c["descriptor_same_relative_offset"],
            c["changed_neighbor_count"],
            c["slot"],
            c["descriptor_a"]["index"],
        )
    )

    after = {"A": sha256_file(save_a), "B": sha256_file(save_b)}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only adjacency trace")

    status = "STRUCTURAL_ADJACENCY_LEADS" if candidates else "NO_ADJACENCY_LEADS"
    report = {
        "schema": 1,
        "scan_kind": "collectible_schema_adjacency_trace",
        "status": status,
        "runtime_generation_allowed": False,
        "interpretation_contract": {
            "neighbor_change_is_completion_truth": False,
            "requires_exact_instance_binding": True,
            "requires_semantically_validated_opposite_states": True,
            "unknown_rows_remain_hidden": True,
        },
        "layout": lay,
        "save_hashes": before,
        "source_hashes_unchanged": True,
        "validated_zlib_streams": {
            "A": sum(len(x) for x in all_streams["A"]),
            "B": sum(len(x) for x in all_streams["B"]),
        },
        "changed_slots": changed_slots,
        "window": WINDOW,
        "stable_target_descriptor_pairs": descriptor_pairs,
        "descriptor_pair_counts_by_field": descriptor_counts,
        "candidate_count": len(candidates),
        "changed_slot_candidate_count": sum(1 for c in candidates if c["slot_changed"]),
        "candidates": candidates,
        "safety": {
            "active_save_opened": False,
            "arbitrary_save_bytes_emitted": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Collectible schema-adjacency structural trace",
        "",
        f"Status: **{status}**",
        "",
        "This is a read-only structural probe. A stable schema descriptor next to a changed zlib stream is only an addressing lead; it is not completion state.",
        "",
        "## Summary",
        "",
        f"- Validated zlib streams: A={report['validated_zlib_streams']['A']}, B={report['validated_zlib_streams']['B']}",
        f"- Changed aligned slots: {', '.join(map(str, changed_slots)) if changed_slots else 'none'}",
        f"- Stable target-schema descriptor pairs: {descriptor_pairs}",
        f"- Descriptor pairs with changed neighbors within ±{WINDOW}: {len(candidates)}",
        f"- Candidates located in changed aligned slots: {report['changed_slot_candidate_count']}",
        "- Runtime generation allowed: **false**",
        "",
        "## Stable descriptor pairs by field",
        "",
    ]
    for field in TARGET_FIELDS:
        lines.append(f"- `{field}`: {descriptor_counts[field]}")
    lines.extend(["", "## Candidate overview", ""])
    for i, c in enumerate(candidates[:80], 1):
        fields = ", ".join(f"`{x}`" for x in c["target_fields"])
        lines.append(
            f"{i}. slot {c['slot']} fields {fields}; descriptor indexes A={c['descriptor_a']['index']} B={c['descriptor_b']['index']}; same descriptor offset={str(c['descriptor_same_relative_offset']).lower()}; changed neighbor deltas={[x['delta'] for x in c['changed_neighbors']]}"
        )
    if len(candidates) > 80:
        lines.append(f"- {len(candidates) - 80} additional candidates are retained in the JSON report.")
    if not candidates:
        lines.append("No stable target-schema descriptor had a changed stream within the configured local window.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The previous probes ruled out literal per-instance identities and literal 16-byte checkpoint field IDs in candidate state payloads. This probe tests the narrower possibility that a stable schema descriptor addresses a nearby payload positionally. Any result remains structural only until an exact object binding and known opposite semantic states prove the value encoding.",
            "",
            "Unknown collectible state remains hidden/fail-closed.",
            "",
        ]
    )
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    summary_lines = [
        "COLLECTIBLE_SCHEMA_ADJACENCY_TRACE_COMPLETED",
        f"status={status}",
        f"zlib_A={report['validated_zlib_streams']['A']}",
        f"zlib_B={report['validated_zlib_streams']['B']}",
        f"changed_slots={','.join(map(str, changed_slots))}",
        f"stable_target_descriptor_pairs={descriptor_pairs}",
        f"adjacency_candidates={len(candidates)}",
        f"changed_slot_candidates={report['changed_slot_candidate_count']}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "arbitrary_save_bytes_emitted=false",
        "source_hashes_unchanged=true",
        "save_or_progression_written=false",
        "game_written=false",
    ]
    args.summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
