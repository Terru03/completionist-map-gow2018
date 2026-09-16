#!/usr/bin/env python3
"""Correlate the frozen Raven before/after zlib streams with native GoW carriers."""
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
CARRIER_PATH = HERE / "gow-custom-userdata-carrier.py"
SCANNER_PATH = HERE / "gow-custom-userdata-carrier-scan.py"
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

EXPECTED = {
    "alive": {
        "relative_offset": 39272,
        "compressed_length": 73,
        "decompressed_length": 79,
        "required_strings": [],
        "reported_stream_index": 27,
    },
    "dead": {
        "relative_offset": 39203,
        "compressed_length": 96,
        "decompressed_length": 116,
        "required_strings": ["ravenKilled", "mapSummaryComplete"],
        "reported_stream_index": 27,
    },
}


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


def is_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 2 > len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and (((cmf << 8) | flg) % 31) == 0
    )


def enumerate_zlib_streams(data: bytes):
    """Enumerate complete standard-zlib streams beginning at raw byte offsets."""
    streams = []
    for offset in range(max(0, len(data) - 1)):
        if not is_zlib_header(data, offset):
            continue
        obj = zlib.decompressobj(15)
        try:
            decoded = obj.decompress(data[offset:])
            decoded += obj.flush()
        except zlib.error:
            continue
        if not obj.eof:
            continue
        consumed = len(data) - offset - len(obj.unused_data)
        if consumed <= 0:
            continue
        streams.append(
            {
                "offset": offset,
                "offset_hex": f"0x{offset:X}",
                "compressed_length": consumed,
                "decompressed_length": len(decoded),
                "compressed_sha256": sha256_bytes(data[offset:offset + consumed]),
                "decompressed_sha256": sha256_bytes(decoded),
                "_compressed": data[offset:offset + consumed],
                "_decompressed": decoded,
            }
        )
    streams.sort(key=lambda item: item["offset"])
    for index, stream in enumerate(streams):
        stream["index0"] = index
        stream["index1"] = index + 1
    return streams


def scanner_args():
    return SimpleNamespace(
        start_offset=0,
        end_offset=None,
        max_hits=256,
        max_tag_solutions=128,
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


def public_stream(stream: dict) -> dict:
    return {k: v for k, v in stream.items() if not k.startswith("_")}


def inspect_preceding_header(
    data: bytes,
    stream: dict,
    expected: dict,
    carrier_matches: list[dict],
):
    offset = stream["offset"]
    header_start = offset - HEADER.size
    result = {
        "header_start": header_start if header_start >= 0 else None,
        "header_start_hex": f"0x{header_start:X}" if header_start >= 0 else None,
        "has_preceding_16_bytes": header_start >= 0,
        "words": None,
        "fields": None,
        "compressed_length_matches_stream": False,
        "compressed_length_matches_expected": False,
        "expected_decompressed_length_from_header": None,
        "decompressed_length_matches_header": False,
        "scanner_carrier_at_header_start": False,
        "scanner_matches": [],
    }
    if header_start < 0:
        return result

    words = HEADER.unpack_from(data, header_start)
    fields = dict(zip(HEADER_FIELDS, words))
    expected_decompressed = fields["record_blob_offset"] + fields["record_blob_length"]
    exact_matches = [
        match
        for match in carrier_matches
        if match["offset"] == header_start
        and match["header"]["compressed_length"] == stream["compressed_length"]
    ]
    result.update(
        {
            "preceding_16_hex": data[header_start:offset].hex(),
            "words": list(words),
            "fields": fields,
            "compressed_length_matches_stream": (
                fields["compressed_length"] == stream["compressed_length"]
            ),
            "compressed_length_matches_expected": (
                fields["compressed_length"] == expected["compressed_length"]
            ),
            "expected_decompressed_length_from_header": expected_decompressed,
            "decompressed_length_matches_header": (
                expected_decompressed == stream["decompressed_length"]
            ),
            "scanner_carrier_at_header_start": bool(exact_matches),
            "scanner_matches": exact_matches,
        }
    )
    return result


def save_target_artifacts(
    out_dir: Path,
    label: str,
    candidate_number: int,
    data: bytes,
    stream: dict,
):
    stem = f"{label}-target-{candidate_number:02d}"
    offset = stream["offset"]
    compressed = stream["_compressed"]
    decoded = stream["_decompressed"]
    header_start = max(0, offset - 16)
    context_start = max(0, offset - 64)
    context_end = min(len(data), offset + len(compressed) + 64)

    (out_dir / f"{stem}-compressed.bin").write_bytes(compressed)
    (out_dir / f"{stem}-decompressed.bin").write_bytes(decoded)
    (out_dir / f"{stem}-preceding-16.bin").write_bytes(data[header_start:offset])
    (out_dir / f"{stem}-context.bin").write_bytes(data[context_start:context_end])

    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in decoded)
    (out_dir / f"{stem}-decompressed-ascii.txt").write_text(
        printable + "\n", encoding="utf-8"
    )


def analyse_save(label: str, path: Path, scanner, carrier):
    expected = EXPECTED[label]
    data = path.read_bytes()

    scan_args = scanner_args()
    carrier_matches, plausible_headers, decompression_hits = scanner.scan_bytes(
        data, scan_args, carrier
    )
    streams = enumerate_zlib_streams(data)

    size_matches = [
        stream
        for stream in streams
        if stream["compressed_length"] == expected["compressed_length"]
        and stream["decompressed_length"] == expected["decompressed_length"]
    ]

    target_candidates = []
    for stream in size_matches:
        decoded = stream["_decompressed"]
        string_presence = {
            text: (
                text.encode("ascii") in decoded
                or text.encode("utf-16le") in decoded
            )
            for text in expected["required_strings"]
        }
        target = public_stream(stream)
        target["required_string_presence"] = string_presence
        target["required_strings_all_present"] = all(string_presence.values())
        target["reported_stream_index"] = expected["reported_stream_index"]
        target["reported_stream_index_matches_index0"] = (
            stream["index0"] == expected["reported_stream_index"]
        )
        target["reported_stream_index_matches_index1"] = (
            stream["index1"] == expected["reported_stream_index"]
        )
        target["known_relative_offset"] = expected["relative_offset"]
        target["known_relative_offset_hex"] = f"0x{expected['relative_offset']:X}"
        target["offset_minus_known_relative"] = stream["offset"] - expected["relative_offset"]
        target["offset_minus_known_relative_hex"] = (
            f"{stream['offset'] - expected['relative_offset']:+#x}"
        )
        target["immediate_parent_test"] = inspect_preceding_header(
            data, stream, expected, carrier_matches
        )
        target_candidates.append(target)

    return {
        "label": label,
        "input_name": path.name,
        "input_length": len(data),
        "input_sha256": sha256_file(path),
        "expected": expected,
        "zlib_stream_count": len(streams),
        "zlib_streams": [public_stream(stream) for stream in streams],
        "target_size_match_count": len(size_matches),
        "target_candidates": target_candidates,
        "carrier_scan": {
            "plausible_headers_tested": plausible_headers,
            "exact_decompression_length_hits": decompression_hits,
            "match_count": len(carrier_matches),
            "matches": carrier_matches,
        },
        "_data": data,
        "_streams": streams,
    }


def verdict_for(alive: dict, dead: dict) -> tuple[str, str]:
    if alive["target_size_match_count"] == 0 or dead["target_size_match_count"] == 0:
        return (
            "TARGET_STREAM_NOT_FOUND",
            "At least one exact 73/79 or 96/116 target stream was not visible as a raw standard-zlib stream in the corresponding game.sav.",
        )
    if alive["target_size_match_count"] != 1 or dead["target_size_match_count"] != 1:
        return (
            "AMBIGUOUS_MULTIPLE_TARGETS",
            "At least one save contains multiple zlib streams with the expected compressed/decompressed sizes, so the target cannot be uniquely selected by size alone.",
        )

    a = alive["target_candidates"][0]
    d = dead["target_candidates"][0]
    if EXPECTED["dead"]["required_strings"] and not d["required_strings_all_present"]:
        return (
            "DEAD_STREAM_SEMANTICS_MISMATCH",
            "The unique 96/116 stream does not contain all expected Raven transition strings.",
        )

    a_native = a["immediate_parent_test"]["scanner_carrier_at_header_start"]
    d_native = d["immediate_parent_test"]["scanner_carrier_at_header_start"]
    if a_native and d_native:
        return (
            "NATIVE_CARRIER_CONFIRMED",
            "Both frozen Raven target zlib streams are the compressed bodies of structurally valid native carriers beginning exactly 16 bytes earlier.",
        )
    if not a_native and not d_native:
        return (
            "TARGET_ZLIB_FOUND_BUT_NOT_IMMEDIATE_NATIVE_CARRIER",
            "Both target streams are present, but neither has a structurally valid native carrier beginning exactly 16 bytes earlier. This points to another persistence layer or a different enclosing buffer.",
        )
    return (
        "MIXED_IMMEDIATE_CARRIER_RESULT",
        "Only one frozen target stream is immediately preceded by a structurally valid native carrier. The two sides need individual inspection before assigning the persistence layer.",
    )


def clean_for_json(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def markdown_report(summary: dict) -> str:
    lines = [
        "# Frozen Raven carrier correlation",
        "",
        f"**Verdict:** `{summary['verdict']}`",
        "",
        summary["verdict_explanation"],
        "",
        "## Target streams",
        "",
        "| Save | Expected relative offset | Exact size matches | Selected raw offset | zlib index (0/1 based) | Immediate native carrier | Slot-base delta |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for label in ("alive", "dead"):
        side = summary[label]
        candidates = side["target_candidates"]
        if len(candidates) == 1:
            target = candidates[0]
            parent = target["immediate_parent_test"]
            selected = target["offset"]
            indices = f"{target['index0']} / {target['index1']}"
            native = "yes" if parent["scanner_carrier_at_header_start"] else "no"
            delta = target["offset_minus_known_relative"]
        else:
            selected = "n/a"
            indices = "n/a"
            native = "n/a"
            delta = "n/a"
        lines.append(
            f"| {label.upper()} | {side['expected']['relative_offset']} | "
            f"{side['target_size_match_count']} | {selected} | {indices} | {native} | {delta} |"
        )

    lines += [
        "",
        "## Whole-file native carrier scan",
        "",
        "| Save | zlib streams | plausible headers tested | exact decompression hits | valid carriers |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in ("alive", "dead"):
        side = summary[label]
        scan = side["carrier_scan"]
        lines.append(
            f"| {label.upper()} | {side['zlib_stream_count']} | "
            f"{scan['plausible_headers_tested']} | {scan['exact_decompression_length_hits']} | "
            f"{scan['match_count']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- The decisive immediate-parent test uses the actual raw target offset, not the previously reported slot-relative number.",
        "- `yes` means a complete carrier accepted by `gow-custom-userdata-carrier-scan.py` starts exactly 16 bytes before that zlib stream and declares the same compressed length.",
        "- A non-zero slot-base delta is retained as evidence that the earlier offset was relative to an enclosing slot/buffer rather than the start of `game.sav`.",
        "- A negative immediate-parent result does not discard the Raven evidence. It narrows the stream to another persistence layer or a nested/enclosing buffer.",
        "",
        "Full machine-readable evidence is in `summary.json`; exact target compressed/decompressed bytes and local contexts are archived beside this report.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alive", required=True, type=Path)
    ap.add_argument("--dead", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()

    for path in (args.alive, args.dead):
        if not path.is_file():
            raise SystemExit(f"input does not exist: {path}")

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    carrier = load_module("gow_custom_userdata_carrier_raven", CARRIER_PATH)
    scanner = load_module("gow_custom_userdata_carrier_scan_raven", SCANNER_PATH)

    alive = analyse_save("alive", args.alive, scanner, carrier)
    dead = analyse_save("dead", args.dead, scanner, carrier)

    for side in (alive, dead):
        label = side["label"]
        streams_by_offset = {stream["offset"]: stream for stream in side["_streams"]}
        for index, candidate in enumerate(side["target_candidates"]):
            stream = streams_by_offset[candidate["offset"]]
            save_target_artifacts(out_dir, label, index, side["_data"], stream)

    verdict, explanation = verdict_for(alive, dead)
    summary = {
        "schema": "gow-raven-frozen-carrier-correlation-v1",
        "verdict": verdict,
        "verdict_explanation": explanation,
        "alive": clean_for_json(alive),
        "dead": clean_for_json(dead),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(markdown_report(summary), encoding="utf-8")

    print(f"VERDICT={verdict}")
    for label in ("alive", "dead"):
        side = summary[label]
        print(
            f"{label.upper()} zlib_streams={side['zlib_stream_count']} "
            f"target_matches={side['target_size_match_count']} "
            f"carrier_matches={side['carrier_scan']['match_count']}"
        )
        for target in side["target_candidates"]:
            parent = target["immediate_parent_test"]
            print(
                f"{label.upper()} target raw_offset={target['offset']} "
                f"index0={target['index0']} index1={target['index1']} "
                f"delta={target['offset_minus_known_relative']} "
                f"immediate_native_carrier={parent['scanner_carrier_at_header_start']}"
            )
    print("RAVEN_FROZEN_CARRIER_CORRELATION_ANALYSIS_COMPLETE")


if __name__ == "__main__":
    main()
