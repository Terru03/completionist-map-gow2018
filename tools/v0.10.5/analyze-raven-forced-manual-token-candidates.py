"""Offline/read-only token-candidate probe for the causal Raven save stream.

The forced-manual experiment proved that PRE slot 17 -> POST slot 18 changes
exactly one validated zlib stream (index 27) and introduces ravenKilled. Earlier
native RE proved that GameObject save keys are opaque integer tokens with this
layout:

    token = 1
          | ((registry_id & 0xffff) << 1)
          | ((flavor & 1) << 17)
          | ((slot & 0xfffff) << 18)

This probe does NOT claim that arbitrary integers in the stream are GameObject
keys. It enumerates only structurally plausible little-endian u64/u32 values in
the one causal stream, decodes them with the proven token formula, compares PRE
and POST candidate sets, and reports offsets/distances to known field labels.
No raw save or decompressed stream bytes are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")
PRE_SLOT = 17
POST_SLOT = 18
STREAM_INDEX = 27
MAX_TOKEN_BITS = 38
KNOWN_LABELS = (b"__subobjs", b"mapSummaryComplete", b"ravenKilled")


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_slot(blob: bytes, lay: dict, index: int) -> bytes:
    start = lay["prefix"] + index * lay["stride"]
    out = blob[start : start + lay["stride"]]
    if len(out) != lay["stride"]:
        raise RuntimeError(f"slot {index} extraction size mismatch")
    return out


def get_raw_stream(slot_bytes: bytes, index: int) -> tuple[bytes, dict]:
    streams = base.scan_slot(slot_bytes, -1)
    if index >= len(streams):
        raise RuntimeError(f"stream {index} missing; found {len(streams)} streams")
    meta = streams[index]
    result = base.decompress_stream(slot_bytes, meta["relative_offset"])
    if result is None:
        raise RuntimeError(f"stream {index} no longer decompresses")
    raw, consumed = result
    if consumed != meta["compressed_bytes"]:
        raise RuntimeError("stream compressed length mismatch")
    if base.sha256_bytes(raw) != meta["sha256"]:
        raise RuntimeError("stream hash mismatch")
    return raw, meta


def label_offsets(raw: bytes) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for label in KNOWN_LABELS:
        positions = []
        cursor = 0
        while True:
            at = raw.find(label, cursor)
            if at < 0:
                break
            positions.append(at)
            cursor = at + 1
        out[label.decode("ascii")] = positions
    return out


def decode_token(value: int) -> dict:
    return {
        "token": value,
        "token_hex": f"0x{value:x}",
        "registry_id": (value >> 1) & 0xFFFF,
        "flavor": (value >> 17) & 1,
        "slot": (value >> 18) & 0xFFFFF,
    }


def nearest_label(offset: int, labels: dict[str, list[int]]) -> dict | None:
    hits = []
    for name, positions in labels.items():
        for at in positions:
            hits.append((abs(offset - at), offset - at, name, at))
    if not hits:
        return None
    distance, signed, name, at = min(hits)
    return {
        "label": name,
        "label_offset": at,
        "signed_distance": signed,
        "absolute_distance": distance,
    }


def plausible(value: int) -> bool:
    if value <= 1:
        return False
    if (value & 1) != 1:
        return False
    if value >> MAX_TOKEN_BITS:
        return False
    d = decode_token(value)
    # Slot zero is reserved/skipped by the proven allocator. Keeping this as a
    # strict structural filter dramatically reduces accidental tiny integers.
    return d["slot"] != 0


def candidates(raw: bytes) -> list[dict]:
    labels = label_offsets(raw)
    out = []
    seen = set()
    for width, fmt in ((8, "<Q"), (4, "<I")):
        for off in range(0, len(raw) - width + 1):
            value = struct.unpack_from(fmt, raw, off)[0]
            if not plausible(value):
                continue
            key = (off, width, value)
            if key in seen:
                continue
            seen.add(key)
            d = decode_token(value)
            # Evidence tier is descriptive only; none of these prove ownership.
            if d["registry_id"] in {0, 1, 18, 24, 238, 241} and d["slot"] <= 4096:
                tier = "area_or_known_registry_and_small_slot"
            elif d["slot"] <= 4096:
                tier = "small_slot"
            else:
                tier = "structurally_valid"
            out.append({
                "offset": off,
                "width": width,
                **d,
                "evidence_tier": tier,
                "nearest_known_label": nearest_label(off, labels),
            })
    out.sort(key=lambda x: (x["offset"], -x["width"], x["token"]))
    return out


def value_index(items: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for item in items:
        out.setdefault(item["token"], []).append(item)
    return out


def compact_value_group(value: int, occurrences: list[dict]) -> dict:
    d = decode_token(value)
    return {
        **d,
        "occurrences": [
            {
                "offset": x["offset"],
                "width": x["width"],
                "evidence_tier": x["evidence_tier"],
                "nearest_known_label": x["nearest_known_label"],
            }
            for x in occurrences
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    pre = args.pre.expanduser().resolve()
    post = args.post.expanduser().resolve()
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for path in (pre, post):
        if not path.is_file():
            raise RuntimeError(f"frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing active save tree: {path}")

    before = {"pre": sha256_file(pre), "post": sha256_file(post)}
    blobs = {"pre": pre.read_bytes(), "post": post.read_bytes()}
    lays = {k: base.layout(v) for k, v in blobs.items()}
    if lays["pre"] != lays["post"]:
        raise RuntimeError(f"save layouts differ: {lays}")
    lay = lays["pre"]

    pre_raw, pre_meta = get_raw_stream(get_slot(blobs["pre"], lay, PRE_SLOT), STREAM_INDEX)
    post_raw, post_meta = get_raw_stream(get_slot(blobs["post"], lay, POST_SLOT), STREAM_INDEX)

    expected_pre = "a20550b246cb5e25acc12402c64093110969eff4ba1fdd2b66e6850d359d2172"
    expected_post = "620bb85be8fd0ebf9c778eb06aba0e532ca57c74bec2d2252694512728e7f308"
    if base.sha256_bytes(pre_raw) != expected_pre or base.sha256_bytes(post_raw) != expected_post:
        raise RuntimeError("causal stream hashes do not match the proven forced-manual pair")

    pre_labels = label_offsets(pre_raw)
    post_labels = label_offsets(post_raw)
    pre_candidates = candidates(pre_raw)
    post_candidates = candidates(post_raw)
    pi = value_index(pre_candidates)
    qi = value_index(post_candidates)
    shared_values = sorted(set(pi) & set(qi))
    pre_only_values = sorted(set(pi) - set(qi))
    post_only_values = sorted(set(qi) - set(pi))

    # Prefer concise output focused on values that could actually discriminate
    # PRE from POST. Shared candidates are retained as a count and a bounded list.
    pre_only = [compact_value_group(v, pi[v]) for v in pre_only_values]
    post_only = [compact_value_group(v, qi[v]) for v in post_only_values]
    shared = [compact_value_group(v, pi[v] + qi[v]) for v in shared_values[:100]]

    after = {"pre": sha256_file(pre), "post": sha256_file(post)}
    if before != after:
        raise RuntimeError("source save hash changed during read-only analysis")

    report = {
        "schema": 1,
        "analysis": "raven_forced_manual_gameobject_token_candidates",
        "source_hashes": before,
        "source_hashes_unchanged": True,
        "pre_slot": PRE_SLOT,
        "post_slot": POST_SLOT,
        "stream_index": STREAM_INDEX,
        "pre_stream_sha256": pre_meta["sha256"],
        "post_stream_sha256": post_meta["sha256"],
        "pre_decompressed_bytes": len(pre_raw),
        "post_decompressed_bytes": len(post_raw),
        "pre_label_offsets": pre_labels,
        "post_label_offsets": post_labels,
        "token_formula": {
            "max_used_bit": 37,
            "registry_id": "(token >> 1) & 0xffff",
            "flavor": "(token >> 17) & 1",
            "slot": "(token >> 18) & 0xfffff",
        },
        "pre_candidate_occurrence_count": len(pre_candidates),
        "post_candidate_occurrence_count": len(post_candidates),
        "shared_candidate_value_count": len(shared_values),
        "pre_only_candidate_value_count": len(pre_only_values),
        "post_only_candidate_value_count": len(post_only_values),
        "pre_only_candidates": pre_only,
        "post_only_candidates": post_only,
        "shared_candidates_bounded": shared,
        "interpretation": {
            "exact_causal_transition_already_proved": True,
            "candidate_values_are_not_proven_gameobject_keys": True,
            "stable_stream_owner_proved": False,
            "runtime_generation_allowed": False,
        },
        "safety": {
            "active_save_opened": False,
            "source_files_written": False,
            "raw_save_bytes_emitted": False,
            "raw_stream_bytes_emitted": False,
            "process_memory_read": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "RAVEN_FORCED_MANUAL_TOKEN_CANDIDATES_COMPLETED",
        f"pre_stream_sha256={pre_meta['sha256']}",
        f"post_stream_sha256={post_meta['sha256']}",
        f"pre_candidate_occurrences={len(pre_candidates)}",
        f"post_candidate_occurrences={len(post_candidates)}",
        f"shared_candidate_values={len(shared_values)}",
        f"pre_only_candidate_values={len(pre_only_values)}",
        f"post_only_candidate_values={len(post_only_values)}",
        f"post_ravenKilled_offset={post_labels.get('ravenKilled', [])}",
        "stable_stream_owner_proved=false",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "raw_stream_bytes_emitted=false",
    ]
    args.summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
