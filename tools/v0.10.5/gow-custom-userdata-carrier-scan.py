#!/usr/bin/env python3
"""Locate structurally valid GoW 2018 custom-userdata carriers in larger files.

The scanner uses the proven 16-byte header and body grammar from
`gow-custom-userdata-carrier.py`. It rejects candidates unless the compressed
section decodes to exactly `record_blob_offset + record_blob_length`, then
solves the variable tagged-metadata boundary and validates the fixed tables.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
PARSER_PATH = HERE / "gow-custom-userdata-carrier.py"
HEADER_STRUCT = struct.Struct("<8H")
WIDTHS = (2, 3, 5)


def load_parser():
    spec = importlib.util.spec_from_file_location("gow_custom_userdata_carrier", PARSER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load carrier parser: {PARSER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def scan_decompress(data: bytes, include_raw_deflate: bool):
    attempts: list[tuple[str, int]] = []
    if len(data) >= 2:
        cmf, flg = data[0], data[1]
        if (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) | flg) % 31 == 0:
            attempts.append(("zlib", 15))
        if data[:2] == b"\x1f\x8b":
            attempts.append(("gzip", 31))
    if include_raw_deflate:
        attempts.append(("raw-deflate", -15))
    for name, wbits in attempts:
        try:
            return name, zlib.decompress(data, wbits)
        except zlib.error:
            pass
    return None, None


def metadata_ends(data: bytes, start: int, token_count: int, fixed_tail: int,
                  max_end: int, max_solutions: int):
    """Yield metadata end offsets consistent with one width per observed tag."""
    results: list[tuple[int, dict[int, int]]] = []

    def visit(pos: int, token_index: int, mapping: dict[int, int]):
        if len(results) >= max_solutions:
            return
        if token_index == token_count:
            if pos + fixed_tail <= len(data):
                results.append((pos, dict(mapping)))
            return
        remaining_tokens = token_count - token_index
        if pos + 2 * remaining_tokens + fixed_tail > len(data):
            return
        if pos + 2 * remaining_tokens > max_end:
            return
        if pos >= len(data) or pos >= max_end:
            return
        tag = data[pos]
        if tag > 5:
            return
        choices = (mapping[tag],) if tag in mapping else WIDTHS
        for width in choices:
            end = pos + width
            if end > max_end:
                continue
            new_mapping = mapping
            if tag not in mapping:
                new_mapping = dict(mapping)
                new_mapping[tag] = width
            visit(end, token_index + 1, new_mapping)

    visit(start, 0, {})
    return results


def plausible_header(values, remaining: int, args) -> bool:
    section0, blob_offset, pair_count, row_count, record_count, blob_length, _scalar_c, compressed = values
    if compressed <= 0 or compressed > args.max_compressed_length:
        return False
    if record_count > args.max_record_count:
        return False
    if blob_length > args.max_record_blob_length:
        return False
    if blob_offset + blob_length <= 0 or blob_offset + blob_length > args.max_decompressed_length:
        return False
    if section0 > args.max_section0_words or pair_count > args.max_metadata_pairs or row_count > args.max_rows:
        return False
    fixed_tail = 3 * record_count + 6 * row_count
    minimum = 16 + compressed + 2 * section0 + 4 * pair_count + fixed_tail
    return minimum <= remaining


def scan_bytes(raw: bytes, args, parser):
    start_limit = min(max(args.start_offset, 0), len(raw))
    end_limit = len(raw) if args.end_offset is None else min(args.end_offset, len(raw))
    results = []
    seen = set()
    scanned_headers = 0
    decompression_hits = 0

    for start in range(start_limit, max(start_limit, end_limit - 15)):
        remaining = end_limit - start
        if remaining < 16:
            break
        values = HEADER_STRUCT.unpack_from(raw, start)
        if not plausible_header(values, remaining, args):
            continue
        scanned_headers += 1
        section0, blob_offset, pair_count, row_count, record_count, blob_length, scalar_c, compressed_len = values
        compressed_start = start + 16
        compressed_end = compressed_start + compressed_len
        if compressed_end > end_limit:
            continue
        comp_format, decompressed = scan_decompress(
            raw[compressed_start:compressed_end], args.include_raw_deflate
        )
        if decompressed is None or len(decompressed) != blob_offset + blob_length:
            continue
        decompression_hits += 1

        metadata_start = compressed_end + 2 * section0
        fixed_tail = 3 * record_count + 6 * row_count
        if metadata_start + fixed_tail > end_limit:
            continue
        max_metadata_end = min(
            metadata_start + 10 * pair_count,
            end_limit - fixed_tail,
        )
        token_count = 2 * pair_count
        solutions = metadata_ends(
            raw,
            metadata_start,
            token_count,
            fixed_tail,
            max_metadata_end,
            args.max_tag_solutions,
        )
        for metadata_end, tag_widths in solutions:
            carrier_end = metadata_end + fixed_tail
            key = (start, carrier_end)
            if key in seen:
                continue
            seen.add(key)
            candidate = raw[start:carrier_end]
            try:
                report = parser.inspect_carrier(candidate, args.max_tag_solutions)
            except parser.CarrierError:
                continue
            if report["metadata_candidate_count"] == 0:
                continue
            if not report["decompression"]["length_matches_header"]:
                continue
            records = report["records"]
            valid_records = sum(1 for item in records if item.get("valid"))
            invalid_records = len(records) - valid_records
            if args.require_valid_records and invalid_records:
                continue
            results.append({
                "offset": start,
                "offset_hex": f"0x{start:X}",
                "length": carrier_end - start,
                "end_offset": carrier_end,
                "end_offset_hex": f"0x{carrier_end:X}",
                "compression": comp_format,
                "header": {
                    "section0_word_count": section0,
                    "record_blob_offset": blob_offset,
                    "metadata_pair_count": pair_count,
                    "row_count": row_count,
                    "record_count": record_count,
                    "record_blob_length": blob_length,
                    "scalar_c": scalar_c,
                    "compressed_length": compressed_len,
                },
                "inferred_tag_widths": {str(k): v for k, v in sorted(tag_widths.items())},
                "metadata_candidate_count": report["metadata_candidate_count"],
                "valid_records": valid_records,
                "invalid_records": invalid_records,
                "class_keys": [r.get("class_key") for r in records if r.get("valid")],
            })
            if len(results) >= args.max_hits:
                return results, scanned_headers, decompression_hits
    return results, scanned_headers, decompression_hits


def command_scan(args):
    parser = load_parser()
    raw = Path(args.input).read_bytes()
    matches, plausible, decompression_hits = scan_bytes(raw, args, parser)
    result = {
        "input": str(Path(args.input)),
        "input_length": len(raw),
        "scan_start": args.start_offset,
        "scan_end": len(raw) if args.end_offset is None else min(args.end_offset, len(raw)),
        "plausible_headers_tested": plausible,
        "exact_decompression_length_hits": decompression_hits,
        "match_count": len(matches),
        "matches": matches,
    }
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


def selftest_args(path: Path):
    return argparse.Namespace(
        input=str(path),
        output=None,
        start_offset=0,
        end_offset=None,
        max_hits=16,
        max_tag_solutions=128,
        include_raw_deflate=False,
        require_valid_records=True,
        max_compressed_length=0xFFFF,
        max_record_count=512,
        max_record_blob_length=0x3000,
        max_decompressed_length=0x10000,
        max_section0_words=4096,
        max_metadata_pairs=4096,
        max_rows=4096,
    )


def command_selftest(_args):
    parser = load_parser()
    carrier = parser.make_selftest_carrier()
    prefix = b"NOT-A-CARRIER\x00\x01\x02"
    suffix = b"\xFE\xED\xFA\xCE"
    raw = prefix + carrier + suffix
    path = HERE / ".gow-carrier-scan-selftest.bin"
    try:
        path.write_bytes(raw)
        args = selftest_args(path)
        matches, _, _ = scan_bytes(raw, args, parser)
        exact = [m for m in matches if m["offset"] == len(prefix) and m["length"] == len(carrier)]
        assert len(exact) == 1
        assert exact[0]["valid_records"] == 2
        assert exact[0]["compression"] == "zlib"
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    print("GOW_CUSTOM_USERDATA_CARRIER_SCAN_SELFTEST_PASSED")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a larger file for exact carrier candidates")
    scan.add_argument("input")
    scan.add_argument("--output")
    scan.add_argument("--start-offset", type=lambda x: int(x, 0), default=0)
    scan.add_argument("--end-offset", type=lambda x: int(x, 0))
    scan.add_argument("--max-hits", type=int, default=64)
    scan.add_argument("--max-tag-solutions", type=int, default=128)
    scan.add_argument("--include-raw-deflate", action="store_true")
    scan.add_argument("--allow-invalid-records", dest="require_valid_records", action="store_false")
    scan.set_defaults(require_valid_records=True)
    scan.add_argument("--max-compressed-length", type=lambda x: int(x, 0), default=0xFFFF)
    scan.add_argument("--max-record-count", type=int, default=512)
    scan.add_argument("--max-record-blob-length", type=lambda x: int(x, 0), default=0x3000)
    scan.add_argument("--max-decompressed-length", type=lambda x: int(x, 0), default=0x10000)
    scan.add_argument("--max-section0-words", type=int, default=4096)
    scan.add_argument("--max-metadata-pairs", type=int, default=4096)
    scan.add_argument("--max-rows", type=int, default=4096)
    scan.set_defaults(func=command_scan)

    selftest = sub.add_parser("selftest")
    selftest.set_defaults(func=command_selftest)
    return ap


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
