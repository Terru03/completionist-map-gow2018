"""Offline structural probe for the exact Raven pre/post manual-save stream.

Reads only frozen saves outside the active save tree. It never emits raw save or
stream bytes. Output is limited to hashes, lengths, common-prefix/suffix metrics,
known allowlisted identifiers, and exact target GUID representation hits.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid

BASE = Path(__file__).with_name("analyze-collectible-changed-stream-fingerprint.py")
PRE_SLOT = 17
POST_SLOT = 18
STREAM_INDEX = 27
TARGET_GUID = uuid.UUID("95b9c644-4d47-9ac6-8207-b1829d02909b")

ALLOWLIST = [
    "ravenKilled",
    "mapSummaryComplete",
    "RegionSummary_ALF_Raven_Parent",
    "precisionchallenge_checkpoint_ravenKilled",
    "goprecisionchallenge_raven_perch",
    "goprecisionchallenge_raven_perch_overrideInst",
    "95b9c644-4d47-9ac6-8207-b1829d02909b",
    "95b9c6444d479ac68207b1829d02909b",
    "savedInfo",
    "__subobjs",
    "__PickleTable",
    "__SoftPickleTable",
    "OnRestoreCheckpoint",
]


def load_base():
    spec = importlib.util.spec_from_file_location("changed_stream_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_slot(blob: bytes, lay: dict, idx: int) -> bytes:
    start = lay["prefix"] + idx * lay["stride"]
    out = blob[start:start + lay["stride"]]
    if len(out) != lay["stride"]:
        raise RuntimeError("slot extraction size mismatch")
    return out


def stream_raw(slot: bytes, stream_index: int) -> tuple[bytes, dict]:
    streams = base.scan_slot(slot, 0)
    if stream_index >= len(streams):
        raise RuntimeError(f"stream {stream_index} missing; found {len(streams)}")
    meta = streams[stream_index]
    result = base.decompress_stream(slot, meta["relative_offset"])
    if result is None:
        raise RuntimeError("failed to decompress selected stream")
    raw, consumed = result
    if consumed != meta["compressed_bytes"]:
        raise RuntimeError("compressed-length disagreement")
    return raw, meta


def lcp(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def lcs(a: bytes, b: bytes, prefix: int) -> int:
    n = min(len(a), len(b)) - prefix
    i = 0
    while i < n and a[len(a)-1-i] == b[len(b)-1-i]:
        i += 1
    return i


def text_hits(raw: bytes) -> list[dict]:
    out = []
    for text in ALLOWLIST:
        needle = text.encode("ascii")
        start = 0
        positions = []
        while True:
            at = raw.find(needle, start)
            if at < 0:
                break
            positions.append(at)
            start = at + 1
        if positions:
            out.append({"label": text, "ascii_offsets": positions})
        u16 = text.encode("utf-16le")
        start = 0
        u16pos = []
        while True:
            at = raw.find(u16, start)
            if at < 0:
                break
            u16pos.append(at)
            start = at + 2
        if u16pos:
            found = next((x for x in out if x["label"] == text), None)
            if found is None:
                found = {"label": text}
                out.append(found)
            found["utf16le_offsets"] = u16pos
    return out


def binary_guid_hits(raw: bytes) -> list[dict]:
    reps = {
        "uuid_bytes": TARGET_GUID.bytes,
        "uuid_bytes_le": TARGET_GUID.bytes_le,
    }
    out = []
    for name, needle in reps.items():
        pos = []
        start = 0
        while True:
            at = raw.find(needle, start)
            if at < 0:
                break
            pos.append(at)
            start = at + 1
        if pos:
            out.append({"representation": name, "offsets": pos})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    pre_path = args.pre.expanduser().resolve()
    post_path = args.post.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    for p in (pre_path, post_path):
        if not p.is_file():
            raise RuntimeError(f"missing frozen save: {p}")
        try:
            p.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing active save: {p}")

    before = {"pre": base.sha256_file(pre_path), "post": base.sha256_file(post_path)}
    pre_blob = pre_path.read_bytes()
    post_blob = post_path.read_bytes()
    pre_lay = base.layout(pre_blob)
    post_lay = base.layout(post_blob)
    if pre_lay != post_lay:
        raise RuntimeError("layout mismatch")

    pre_raw, pre_meta = stream_raw(get_slot(pre_blob, pre_lay, PRE_SLOT), STREAM_INDEX)
    post_raw, post_meta = stream_raw(get_slot(post_blob, post_lay, POST_SLOT), STREAM_INDEX)

    prefix = lcp(pre_raw, post_raw)
    suffix = lcs(pre_raw, post_raw, prefix)
    pre_mid = pre_raw[prefix:len(pre_raw)-suffix if suffix else len(pre_raw)]
    post_mid = post_raw[prefix:len(post_raw)-suffix if suffix else len(post_raw)]
    delta = len(post_raw) - len(pre_raw)
    single_insertion = (
        delta >= 0
        and len(pre_mid) == 0
        and len(post_mid) == delta
        and pre_raw == post_raw[:prefix] + post_raw[prefix + delta:]
    )

    raven = b"ravenKilled"
    insertion_contains_raven = raven in post_mid if single_insertion else False

    after = {"pre": base.sha256_file(pre_path), "post": base.sha256_file(post_path)}
    if before != after:
        raise RuntimeError("source save changed during read-only analysis")

    report = {
        "schema": 1,
        "analysis": "raven_forced_manual_stream_structure",
        "pre_slot": PRE_SLOT,
        "post_slot": POST_SLOT,
        "stream_index": STREAM_INDEX,
        "pre_stream": base.compact_stream(pre_meta),
        "post_stream": base.compact_stream(post_meta),
        "length_delta": delta,
        "common_prefix_bytes": prefix,
        "common_suffix_bytes": suffix,
        "pre_middle_bytes": len(pre_mid),
        "post_middle_bytes": len(post_mid),
        "pre_middle_sha256": sha(pre_mid),
        "post_middle_sha256": sha(post_mid),
        "single_contiguous_insertion": single_insertion,
        "insertion_contains_ravenKilled": insertion_contains_raven,
        "pre_allowlisted_hits": text_hits(pre_raw),
        "post_allowlisted_hits": text_hits(post_raw),
        "pre_target_guid_binary_hits": binary_guid_hits(pre_raw),
        "post_target_guid_binary_hits": binary_guid_hits(post_raw),
        "source_hashes": before,
        "source_hashes_unchanged": True,
        "interpretation": {
            "exact_causal_transition_already_proved": True,
            "stable_stream_owner_proved": False,
            "runtime_generation_allowed": False,
        },
        "safety": {
            "active_save_opened": False,
            "raw_save_bytes_emitted": False,
            "raw_stream_bytes_emitted": False,
            "source_files_written": False,
            "process_memory_read": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "RAVEN_FORCED_MANUAL_STREAM_STRUCTURE_COMPLETED",
        f"pre_stream_sha256={pre_meta['sha256']}",
        f"post_stream_sha256={post_meta['sha256']}",
        f"pre_decompressed_bytes={len(pre_raw)}",
        f"post_decompressed_bytes={len(post_raw)}",
        f"length_delta={delta}",
        f"common_prefix_bytes={prefix}",
        f"common_suffix_bytes={suffix}",
        f"pre_middle_bytes={len(pre_mid)}",
        f"post_middle_bytes={len(post_mid)}",
        f"single_contiguous_insertion={str(single_insertion).lower()}",
        f"insertion_contains_ravenKilled={str(insertion_contains_raven).lower()}",
        f"pre_allowlisted_hits={len(report['pre_allowlisted_hits'])}",
        f"post_allowlisted_hits={len(report['post_allowlisted_hits'])}",
        f"pre_target_guid_binary_hits={len(report['pre_target_guid_binary_hits'])}",
        f"post_target_guid_binary_hits={len(report['post_target_guid_binary_hits'])}",
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
