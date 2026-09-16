#!/usr/bin/env python3
"""Resolve the frozen Odin's Raven transition by exact slot-local coordinates.

This is the deterministic second pass after correlate-raven-frozen-carrier.py.
It deliberately does not select streams by compressed/decompressed size alone.
The historical coordinates are interpreted with the same convention used by
analyze-collectible-changed-stream-fingerprint.py: zero-based slot index,
relative offset measured from the beginning of the complete slot stride, and
zero-based zlib index within that slot.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import zlib

HERE = Path(__file__).resolve().parent
SCANNER_PATH = HERE / "gow-custom-userdata-carrier-scan.py"
PARSER_PATH = HERE / "gow-custom-userdata-carrier.py"
HEADER = struct.Struct("<8H")
HEADER_FIELDS = (
    "section0_word_count",
    "record_blob_offset",
    "metadata_pair_count",
    "row_count",
    "record_count",
    "record_blob_length",
    "scalar_c",
    "compressed_length",
)

EXPECTED_LAYOUT = {
    "prefix": 4160,
    "stride": 1677512,
    "slot_count": 20,
    "header_size": 208,
}

# Historical coordinates recovered from the frozen Raven transition.  These
# slot numbers are zero-based, matching range(slot_count) in the original
# fingerprint scanner.  relative_offset is from the start of the whole slot.
TARGETS = {
    "alive": {
        "slot_index": 17,
        "slot_stream_index": 27,
        "relative_offset": 39272,
        "compressed_length": 73,
        "decompressed_length": 79,
        "required_strings": [],
    },
    "dead": {
        "slot_index": 18,
        "slot_stream_index": 27,
        "relative_offset": 39203,
        "compressed_length": 96,
        "decompressed_length": 116,
        "required_strings": ["ravenKilled", "mapSummaryComplete"],
    },
}

MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("save too small for aligned header")
    words = struct.unpack_from("<8I", blob, 0)
    header_size = words[4]
    stride = words[5]
    declared_size = words[6]
    if declared_size != len(blob):
        raise RuntimeError(
            f"declared size mismatch header={declared_size} actual={len(blob)}"
        )
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"implausible slot stride {stride}")
    prefix = len(blob) % stride
    slot_count = (len(blob) - prefix) // stride
    if slot_count <= 0 or prefix < header_size:
        raise RuntimeError(
            f"implausible aligned layout prefix={prefix} slots={slot_count}"
        )
    return {
        "prefix": prefix,
        "stride": stride,
        "slot_count": slot_count,
        "header_size": header_size,
    }


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and (((cmf << 8) | flg) % 31) == 0
    )


def decompress_stream(data: bytes, offset: int):
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset:min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj(15)
        decoded = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(decoded) > MAX_DECOMPRESSED or not obj.eof or not decoded:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return decoded, consumed
    except zlib.error:
        return None


def enumerate_slot_streams(slot: bytes) -> list[dict]:
    """Reproduce the historical slot-local stream enumeration exactly."""
    streams: list[dict] = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        result = decompress_stream(slot, at)
        if result is None:
            continue
        decoded, consumed = result
        streams.append({
            "index": len(streams),
            "relative_offset": at,
            "compressed_length": consumed,
            "decompressed_length": len(decoded),
            "compressed_sha256": sha256_bytes(slot[at:at + consumed]),
            "decompressed_sha256": sha256_bytes(decoded),
            "_compressed": slot[at:at + consumed],
            "_decompressed": decoded,
        })
    return streams


def enumerate_whole_file_streams(blob: bytes) -> list[dict]:
    streams: list[dict] = []
    cursor = 0
    while True:
        at = blob.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        result = decompress_stream(blob, at)
        if result is None:
            continue
        decoded, consumed = result
        streams.append({
            "index0": len(streams),
            "offset": at,
            "compressed_length": consumed,
            "decompressed_length": len(decoded),
            "decompressed_sha256": sha256_bytes(decoded),
        })
    return streams


def scanner_args(start: int, end: int):
    return SimpleNamespace(
        start_offset=start,
        end_offset=end,
        max_hits=64,
        max_tag_solutions=256,
        include_raw_deflate=False,
        require_valid_records=True,
        max_compressed_length=0xFFFF,
        max_record_count=1024,
        max_record_blob_length=0xFFFF,
        max_decompressed_length=0x20000,
        max_section0_words=8192,
        max_metadata_pairs=8192,
        max_rows=8192,
    )


def inspect_immediate_header(blob: bytes, raw_offset: int, stream: dict, scanner, parser) -> dict:
    start = raw_offset - HEADER.size
    if start < 0:
        return {"present": False}
    words = HEADER.unpack_from(blob, start)
    fields = dict(zip(HEADER_FIELDS, words))
    expected_decoded = fields["record_blob_offset"] + fields["record_blob_length"]
    length_signature = (
        fields["compressed_length"] == stream["compressed_length"]
        and expected_decoded == stream["decompressed_length"]
    )

    # The fixed tail for these headers is tiny, but allow 64 KiB after the
    # compressed body so a scanner rejection cannot be blamed on a short scan.
    scan_end = min(len(blob), raw_offset + stream["compressed_length"] + 0x10000)
    matches, plausible, decompression_hits = scanner.scan_bytes(
        blob, scanner_args(start, scan_end), parser
    )
    exact = [
        m for m in matches
        if m["offset"] == start
        and m["header"]["compressed_length"] == stream["compressed_length"]
    ]
    return {
        "present": True,
        "header_start": start,
        "header_start_hex": f"0x{start:X}",
        "preceding_16_hex": blob[start:raw_offset].hex(),
        "words": list(words),
        "fields": fields,
        "expected_decompressed_length_from_header": expected_decoded,
        "compressed_length_matches": fields["compressed_length"] == stream["compressed_length"],
        "decompressed_length_matches": expected_decoded == stream["decompressed_length"],
        "length_signature_matches": length_signature,
        "scanner_plausible_headers_tested": plausible,
        "scanner_exact_decompression_hits": decompression_hits,
        "scanner_full_carrier_at_header_start": bool(exact),
        "scanner_matches_at_header_start": exact,
    }


def printable_ascii(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def hexdump(data: bytes, base: int = 0) -> str:
    lines = []
    for pos in range(0, len(data), 16):
        chunk = data[pos:pos + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + pos:08X}  {hx:<47}  {asc}")
    return "\n".join(lines) + ("\n" if lines else "")


def byte_diff_summary(a: bytes, b: bytes) -> dict:
    prefix = 0
    limit = min(len(a), len(b))
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and a[len(a)-1-suffix] == b[len(b)-1-suffix]:
        suffix += 1
    a_end = len(a) - suffix if suffix else len(a)
    b_end = len(b) - suffix if suffix else len(b)
    return {
        "common_prefix_length": prefix,
        "common_suffix_length": suffix,
        "alive_changed_range": [prefix, a_end],
        "dead_changed_range": [prefix, b_end],
        "alive_changed_hex": a[prefix:a_end].hex(),
        "dead_changed_hex": b[prefix:b_end].hex(),
        "alive_changed_ascii": printable_ascii(a[prefix:a_end]),
        "dead_changed_ascii": printable_ascii(b[prefix:b_end]),
    }


def public_stream(stream: dict) -> dict:
    return {k: v for k, v in stream.items() if not k.startswith("_")}


def resolve_side(label: str, path: Path, scanner, parser, out_dir: Path) -> dict:
    expected = TARGETS[label]
    blob = path.read_bytes()
    layout = save_layout(blob)
    if layout != EXPECTED_LAYOUT:
        raise RuntimeError(f"{label}: unexpected save layout {layout}; expected {EXPECTED_LAYOUT}")

    slot_start = layout["prefix"] + expected["slot_index"] * layout["stride"]
    slot_end = slot_start + layout["stride"]
    slot = blob[slot_start:slot_end]
    raw_offset = slot_start + expected["relative_offset"]
    if raw_offset != layout["prefix"] + expected["slot_index"] * layout["stride"] + expected["relative_offset"]:
        raise AssertionError("raw-offset formula changed unexpectedly")

    streams = enumerate_slot_streams(slot)
    by_offset = [s for s in streams if s["relative_offset"] == expected["relative_offset"]]
    if len(by_offset) != 1:
        raise RuntimeError(
            f"{label}: expected exactly one zlib stream at slot-relative offset "
            f"{expected['relative_offset']}, found {len(by_offset)}"
        )
    stream = by_offset[0]
    failures = []
    for key in ("compressed_length", "decompressed_length"):
        if stream[key] != expected[key]:
            failures.append(f"{key}: got {stream[key]}, expected {expected[key]}")
    if stream["index"] != expected["slot_stream_index"]:
        failures.append(
            f"slot stream index: got {stream['index']}, expected {expected['slot_stream_index']}"
        )
    decoded = stream["_decompressed"]
    string_presence = {
        text: (text.encode("ascii") in decoded or text.encode("utf-16le") in decoded)
        for text in expected["required_strings"]
    }
    if not all(string_presence.values()):
        failures.append(f"required Raven strings missing: {string_presence}")
    if failures:
        raise RuntimeError(f"{label}: exact historical target validation failed: {'; '.join(failures)}")

    whole = enumerate_whole_file_streams(blob)
    whole_exact = [s for s in whole if s["offset"] == raw_offset]
    if len(whole_exact) != 1:
        raise RuntimeError(f"{label}: exact target not uniquely present in whole-file enumeration")
    whole_index = whole_exact[0]["index0"]

    same_size = [
        s for s in whole
        if s["compressed_length"] == expected["compressed_length"]
        and s["decompressed_length"] == expected["decompressed_length"]
    ]
    same_payload = [
        s for s in same_size if s["decompressed_sha256"] == stream["decompressed_sha256"]
    ]

    header = inspect_immediate_header(blob, raw_offset, stream, scanner, parser)
    compressed = stream["_compressed"]
    context_start = max(0, raw_offset - 256)
    context_end = min(len(blob), raw_offset + len(compressed) + 256)
    after_start = raw_offset + len(compressed)
    after = blob[after_start:min(len(blob), after_start + 256)]

    (out_dir / f"{label}-exact-compressed.bin").write_bytes(compressed)
    (out_dir / f"{label}-exact-decompressed.bin").write_bytes(decoded)
    (out_dir / f"{label}-exact-decompressed-ascii.txt").write_text(
        printable_ascii(decoded) + "\n", encoding="utf-8"
    )
    (out_dir / f"{label}-exact-decompressed-hexdump.txt").write_text(
        hexdump(decoded), encoding="utf-8"
    )
    (out_dir / f"{label}-exact-framing-context.bin").write_bytes(blob[context_start:context_end])
    (out_dir / f"{label}-exact-framing-context-hexdump.txt").write_text(
        hexdump(blob[context_start:context_end], context_start), encoding="utf-8"
    )

    return {
        "label": label,
        "input_name": path.name,
        "input_length": len(blob),
        "input_sha256": sha256_file(path),
        "layout": layout,
        "historical_coordinate": expected,
        "slot_start": slot_start,
        "slot_start_hex": f"0x{slot_start:X}",
        "raw_offset": raw_offset,
        "raw_offset_hex": f"0x{raw_offset:X}",
        "slot_stream_count": len(streams),
        "resolved_stream": public_stream(stream),
        "whole_file_stream_index0": whole_index,
        "whole_file_stream_count": len(whole),
        "same_size_candidate_count": len(same_size),
        "same_size_candidate_offsets": [s["offset"] for s in same_size],
        "same_payload_candidate_count": len(same_payload),
        "same_payload_candidate_offsets": [s["offset"] for s in same_payload],
        "required_string_presence": string_presence,
        "immediate_header": header,
        "post_compressed_256_hex": after.hex(),
        "post_compressed_256_ascii": printable_ascii(after),
        "_decoded": decoded,
    }


def verdict_for(alive: dict, dead: dict) -> tuple[str, str]:
    ah = alive["immediate_header"]
    dh = dead["immediate_header"]
    full = (ah.get("scanner_full_carrier_at_header_start", False), dh.get("scanner_full_carrier_at_header_start", False))
    sig = (ah.get("length_signature_matches", False), dh.get("length_signature_matches", False))
    if all(full):
        return (
            "EXACT_RAVEN_STREAMS_RESOLVED_NATIVE_CARRIER",
            "Both exact historical Raven streams are accepted as complete native custom-userdata carriers beginning 16 bytes earlier.",
        )
    if all(sig) and not any(full):
        return (
            "EXACT_RAVEN_STREAMS_RESOLVED_HEADER_VALID_TAIL_UNRESOLVED",
            "Both exact Raven streams have a length-consistent <8H> native header exactly 16 bytes earlier, but the current full-carrier scanner rejects the post-compression tail grammar. The remaining reverse-engineering target is the tail/framing, not stream identity.",
        )
    if not any(sig) and not any(full):
        return (
            "EXACT_RAVEN_STREAMS_RESOLVED_NOT_IMMEDIATE_NATIVE_HEADER",
            "The exact historical Raven streams are resolved, but neither is preceded by a length-consistent native header.",
        )
    return (
        "EXACT_RAVEN_STREAMS_RESOLVED_MIXED_HEADER_RESULT",
        "The two exact Raven states disagree on immediate native-header/full-carrier validation and must be inspected independently.",
    )


def markdown_report(summary: dict) -> str:
    lines = [
        "# Exact frozen Raven stream resolution",
        "",
        f"**Verdict:** `{summary['verdict']}`",
        "",
        summary["verdict_explanation"],
        "",
        "## Coordinate contract",
        "",
        "- Slot index is zero-based.",
        "- `relative_offset` is measured from the start of the complete slot stride, including its 208-byte header.",
        "- Slot-local zlib stream index is zero-based and reproduced with the historical scanner algorithm.",
        "- Exact stream identity is selected by `(slot_index, relative_offset)`, never by size alone.",
        "",
        "## Exact targets",
        "",
        "| State | Slot | Slot zlib index | Relative offset | Raw file offset | Compressed → decoded | Whole-file index | Header length signature | Full carrier scanner |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for label in ("alive", "dead"):
        side = summary[label]
        target = side["historical_coordinate"]
        resolved = side["resolved_stream"]
        header = side["immediate_header"]
        lines.append(
            f"| {label.upper()} | {target['slot_index']} | {resolved['index']} | "
            f"{resolved['relative_offset']} | {side['raw_offset']} | "
            f"{resolved['compressed_length']} → {resolved['decompressed_length']} | "
            f"{side['whole_file_stream_index0']} | "
            f"{'yes' if header.get('length_signature_matches') else 'no'} | "
            f"{'yes' if header.get('scanner_full_carrier_at_header_start') else 'no'} |"
        )
    lines += [
        "",
        "## Why this closes the earlier ambiguity",
        "",
        "The earlier broad pass found many same-size streams. This pass starts from the original slot-local coordinates and independently verifies offset, zero-based stream index, compressed size, decoded size, and DEAD Raven semantics. Same-size and same-payload duplicates are retained only as context.",
        "",
        "## Immediate-header result",
        "",
        "A matching compressed length plus `record_blob_offset + record_blob_length == decoded_length` is reported separately from full carrier acceptance. This distinction is intentional: it tells us whether the unresolved part is stream identity, the 16-byte header, or the post-compression tail grammar.",
        "",
        "Machine-readable details and the exact compressed/decompressed bytes plus ±256-byte framing contexts are archived beside this report.",
        "",
    ]
    return "\n".join(lines)


def command_analyse(args) -> int:
    for path in (args.alive, args.dead):
        if not path.is_file():
            raise RuntimeError(f"frozen save missing: {path}")
        active_root = (Path.home() / "Saved Games" / "God of War").resolve()
        try:
            path.resolve().relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"refusing to inspect active save tree: {path}")

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    scanner = load_module("gow_custom_userdata_carrier_scan_resolver", SCANNER_PATH)
    parser = load_module("gow_custom_userdata_carrier_resolver", PARSER_PATH)

    alive = resolve_side("alive", args.alive, scanner, parser, out_dir)
    dead = resolve_side("dead", args.dead, scanner, parser, out_dir)
    verdict, explanation = verdict_for(alive, dead)
    comparison = byte_diff_summary(alive.pop("_decoded"), dead.pop("_decoded"))

    summary = {
        "schema": 1,
        "analysis": "exact_frozen_raven_stream_resolution",
        "verdict": verdict,
        "verdict_explanation": explanation,
        "coordinate_semantics": {
            "slot_index_base": 0,
            "slot_stream_index_base": 0,
            "relative_offset_base": "complete_slot_start",
            "slot_header_included_in_relative_coordinates": True,
            "raw_offset_formula": "prefix + slot_index * stride + relative_offset",
        },
        "alive": alive,
        "dead": dead,
        "decoded_comparison": comparison,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(markdown_report(summary), encoding="utf-8")
    print(json.dumps({
        "verdict": verdict,
        "alive_raw_offset": alive["raw_offset"],
        "dead_raw_offset": dead["raw_offset"],
        "alive_slot_stream_index": alive["resolved_stream"]["index"],
        "dead_slot_stream_index": dead["resolved_stream"]["index"],
        "alive_header_signature": alive["immediate_header"]["length_signature_matches"],
        "dead_header_signature": dead["immediate_header"]["length_signature_matches"],
        "alive_full_carrier": alive["immediate_header"]["scanner_full_carrier_at_header_start"],
        "dead_full_carrier": dead["immediate_header"]["scanner_full_carrier_at_header_start"],
    }, indent=2))
    print("RAVEN_FROZEN_STREAM_RESOLUTION_ANALYSIS_COMPLETE")
    return 0


def command_selftest(_args) -> int:
    raw1 = b"alpha-raven-test"
    raw2 = b"beta-raven-test-with-more-data"
    comp1 = zlib.compress(raw1)
    comp2 = zlib.compress(raw2)
    slot = bytearray(b"\x00" * 512)
    slot[40:40 + len(comp1)] = comp1
    slot[220:220 + len(comp2)] = comp2
    streams = enumerate_slot_streams(bytes(slot))
    assert len(streams) == 2
    assert streams[0]["index"] == 0 and streams[0]["relative_offset"] == 40
    assert streams[1]["index"] == 1 and streams[1]["relative_offset"] == 220
    assert streams[0]["_decompressed"] == raw1
    assert streams[1]["_decompressed"] == raw2
    assert 4160 + 17 * 1677512 + 39272 == 28561136
    assert 4160 + 18 * 1677512 + 39203 == 30238579
    print("RAVEN_FROZEN_STREAM_RESOLVER_SELFTEST_PASSED")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    st = sub.add_parser("selftest")
    st.set_defaults(func=command_selftest)
    analyse = sub.add_parser("analyse")
    analyse.add_argument("--alive", required=True, type=Path)
    analyse.add_argument("--dead", required=True, type=Path)
    analyse.add_argument("--output-dir", required=True, type=Path)
    analyse.set_defaults(func=command_analyse)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
