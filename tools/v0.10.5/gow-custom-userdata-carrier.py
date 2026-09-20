#!/usr/bin/env python3
"""Inspect GoW 2018 custom-userdata outer carriers.

This parser implements only framing that is supported by mirrored native
save/restore dataflow. Unknown header fields and metadata tag meanings retain
neutral names. Metadata tag widths are inferred from the proven 2/3/5-byte
encoding widths and the fixed tail length; no tag->width table is guessed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import struct
import sys
import zlib

HEADER_STRUCT = struct.Struct("<8H")
WIDTHS = (2, 3, 5)


class CarrierError(ValueError):
    pass


@dataclass(frozen=True)
class Header:
    section0_word_count: int
    record_blob_offset: int
    metadata_pair_count: int
    row_count: int
    record_count: int
    record_blob_length: int
    scalar_c: int
    compressed_length: int


@dataclass(frozen=True)
class MetadataToken:
    index: int
    tag: int
    width: int
    raw_hex: str


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_STRUCT.size:
        raise CarrierError(f"carrier shorter than 16-byte header: {len(data)}")
    return Header(*HEADER_STRUCT.unpack_from(data, 0))


def infer_metadata(data: bytes, pair_count: int, max_candidates: int = 128):
    """Infer used tag widths from exact metadata span length.

    Restore proves tag <= 5 and encoded widths in {2,3,5}. It consumes two
    tagged scalars per metadata entry. Real checkpoint carriers can exceed
    Python's recursion depth, so solve the tiny tag-width state space with an
    explicit stack and reconstruct token rows only for complete candidates.
    """
    token_count = 2 * pair_count
    results: list[dict] = []
    stack: list[tuple[int, int, dict[int, int]]] = [(0, 0, {})]
    seen: set[tuple[int, int, tuple[tuple[int, int], ...]]] = set()

    def build_tokens(mapping: dict[int, int]) -> list[dict]:
        pos = 0
        tokens: list[dict] = []
        for token_index in range(token_count):
            if pos >= len(data):
                return []
            tag = data[pos]
            width = mapping.get(tag)
            if width is None or width not in WIDTHS:
                return []
            end = pos + width
            if end > len(data):
                return []
            tokens.append(asdict(MetadataToken(
                token_index, tag, width, data[pos:end].hex()
            )))
            pos = end
        return tokens if pos == len(data) else []

    while stack and len(results) < max_candidates:
        pos, token_index, mapping = stack.pop()
        state = (pos, token_index, tuple(sorted(mapping.items())))
        if state in seen:
            continue
        seen.add(state)

        if token_index == token_count:
            if pos == len(data):
                tokens = build_tokens(mapping)
                if tokens or token_count == 0:
                    results.append({
                        "used_tag_widths": {
                            str(k): v for k, v in sorted(mapping.items())
                        },
                        "tokens": tokens,
                    })
            continue

        remaining_tokens = token_count - token_index
        remaining_bytes = len(data) - pos
        if remaining_bytes < 2 * remaining_tokens or remaining_bytes > 5 * remaining_tokens:
            continue
        if pos >= len(data):
            continue

        tag = data[pos]
        if tag > 5:
            continue
        choices = (mapping[tag],) if tag in mapping else WIDTHS
        # Reverse pushes so effective DFS order remains 2,3,5 bytes.
        for width in reversed(tuple(choices)):
            end = pos + width
            if end > len(data):
                continue
            if tag in mapping:
                new_mapping = mapping
            else:
                new_mapping = dict(mapping)
                new_mapping[tag] = width
            stack.append((end, token_index + 1, new_mapping))

    return results


def try_decompress(data: bytes):
    attempts = (("zlib", 15), ("gzip", 31), ("raw-deflate", -15))
    errors = {}
    for name, wbits in attempts:
        try:
            out = zlib.decompress(data, wbits)
            return {"format": name, "data": out}
        except zlib.error as exc:
            errors[name] = str(exc)
    return {"format": None, "data": None, "errors": errors}


def parse_records(blob: bytes, sizes: bytes, offsets: bytes):
    records = []
    count = len(sizes)
    if len(offsets) != count * 2:
        raise CarrierError("record-offset table length does not equal 2 * record_count")
    for i in range(count):
        size = sizes[i]
        offset = struct.unpack_from("<H", offsets, i * 2)[0]
        end = offset + size
        item = {
            "index": i,
            "offset": offset,
            "stored_size": size,
            "valid": False,
        }
        if size < 8:
            item["error"] = "stored size < 8"
        elif end > len(blob):
            item["error"] = f"record end {end} exceeds blob length {len(blob)}"
        else:
            rec = blob[offset:end]
            item.update({
                "valid": True,
                "class_key": f"0x{struct.unpack_from('<Q', rec, 0)[0]:016X}",
                "payload_length": size - 8,
                "payload_hex": rec[8:].hex(),
            })
        records.append(item)
    return records


def inspect_carrier(data: bytes, max_metadata_candidates: int = 128):
    header = parse_header(data)
    cursor = 16

    compressed_end = cursor + header.compressed_length
    if compressed_end > len(data):
        raise CarrierError("compressed section exceeds carrier length")
    compressed = data[cursor:compressed_end]
    cursor = compressed_end

    section0_len = 2 * header.section0_word_count
    section0_end = cursor + section0_len
    if section0_end > len(data):
        raise CarrierError("section0 word table exceeds carrier length")
    section0 = data[cursor:section0_end]
    cursor = section0_end

    fixed_tail_len = (
        header.record_count
        + 2 * header.record_count
        + 6 * header.row_count
    )
    if cursor + fixed_tail_len > len(data):
        raise CarrierError("fixed post-metadata tail exceeds carrier length")

    metadata_len = len(data) - cursor - fixed_tail_len
    min_metadata = 4 * header.metadata_pair_count
    max_metadata = 10 * header.metadata_pair_count
    if not (min_metadata <= metadata_len <= max_metadata):
        raise CarrierError(
            "metadata span length inconsistent with two 2/3/5-byte tagged "
            f"scalars per entry: got {metadata_len}, expected {min_metadata}..{max_metadata}"
        )

    metadata = data[cursor:cursor + metadata_len]
    cursor += metadata_len

    sizes = data[cursor:cursor + header.record_count]
    cursor += header.record_count
    offsets = data[cursor:cursor + 2 * header.record_count]
    cursor += 2 * header.record_count
    rows = data[cursor:cursor + 6 * header.row_count]
    cursor += 6 * header.row_count
    if cursor != len(data):
        raise CarrierError(f"internal cursor mismatch: {cursor} != {len(data)}")

    metadata_candidates = infer_metadata(
        metadata, header.metadata_pair_count, max_metadata_candidates
    )

    dec = try_decompress(compressed)
    decompressed = dec["data"]
    decompressed_summary = {
        "format": dec["format"],
        "length": len(decompressed) if decompressed is not None else None,
        "expected_length": header.record_blob_offset + header.record_blob_length,
        "length_matches_header": (
            decompressed is not None
            and len(decompressed) == header.record_blob_offset + header.record_blob_length
        ),
    }
    if decompressed is None:
        decompressed_summary["errors"] = dec["errors"]
        records = []
        prefix = blob = None
    else:
        blob_start = header.record_blob_offset
        blob_end = blob_start + header.record_blob_length
        if blob_end > len(decompressed):
            prefix = decompressed[:min(blob_start, len(decompressed))]
            blob = None
            records = []
            decompressed_summary["error"] = "record blob exceeds decompressed payload"
        else:
            prefix = decompressed[:blob_start]
            blob = decompressed[blob_start:blob_end]
            records = parse_records(blob, sizes, offsets)

    return {
        "carrier_length": len(data),
        "header": asdict(header),
        "sections": {
            "header": {"offset": 0, "length": 16},
            "compressed": {"offset": 16, "length": len(compressed)},
            "section0_words": {"offset": compressed_end, "length": len(section0)},
            "tagged_metadata": {"offset": section0_end, "length": len(metadata)},
            "record_sizes": {"offset": section0_end + len(metadata), "length": len(sizes)},
            "record_offsets": {
                "offset": section0_end + len(metadata) + len(sizes),
                "length": len(offsets),
            },
            "six_byte_rows": {
                "offset": section0_end + len(metadata) + len(sizes) + len(offsets),
                "length": len(rows),
            },
        },
        "metadata_candidate_count": len(metadata_candidates),
        "metadata_candidates_truncated": len(metadata_candidates) >= max_metadata_candidates,
        "metadata_candidates": metadata_candidates,
        "decompression": decompressed_summary,
        "decompressed_prefix_hex": prefix.hex() if prefix is not None else None,
        "record_blob_hex": blob.hex() if blob is not None else None,
        "record_sizes_hex": sizes.hex(),
        "record_offsets_hex": offsets.hex(),
        "six_byte_rows_hex": rows.hex(),
        "records": records,
    }


def make_selftest_carrier():
    prefix = b"PFX"
    r0 = struct.pack("<Q", 0x1122334455667788) + b"\xAA\xBB"
    r1 = struct.pack("<Q", 0x8877665544332211) + b"\xCC\xDD\xEE"
    blob = r0 + r1
    sizes = bytes((len(r0), len(r1)))
    offsets = struct.pack("<HH", 0, len(r0))
    decompressed = prefix + blob
    compressed = zlib.compress(decompressed)

    metadata = (
        bytes((0, 0xA1))
        + bytes((1, 0xB1, 0xB2))
        + bytes((2, 0xC1, 0xC2, 0xC3, 0xC4))
        + bytes((0, 0xD1))
    )
    section0 = struct.pack("<HH", 0x1234, 0x5678)
    rows = b"\x01\x02\x03\x04\x05\x06"
    header = HEADER_STRUCT.pack(
        2,
        len(prefix),
        2,
        1,
        2,
        len(blob),
        7,
        len(compressed),
    )
    return header + compressed + section0 + metadata + sizes + offsets + rows


def command_inspect(args):
    raw = Path(args.input).read_bytes()
    if args.offset:
        if args.offset >= len(raw):
            raise CarrierError("offset is beyond input file")
        raw = raw[args.offset:]
    if args.length is not None:
        raw = raw[:args.length]
    result = inspect_carrier(raw, args.max_metadata_candidates)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


def command_selftest(_args):
    carrier = make_selftest_carrier()
    result = inspect_carrier(carrier)
    assert result["header"]["record_count"] == 2
    assert result["decompression"]["format"] == "zlib"
    assert result["decompression"]["length_matches_header"] is True
    assert len(result["records"]) == 2
    assert all(r["valid"] for r in result["records"])
    assert any(
        c["used_tag_widths"].get("0") == 2
        and c["used_tag_widths"].get("1") == 3
        and c["used_tag_widths"].get("2") == 5
        for c in result["metadata_candidates"]
    )

    # Regression: 600 pairs means 1,200 tokens, beyond Python's default
    # recursion depth. Metadata inference must remain iterative.
    deep_pairs = 600
    deep_metadata = bytes((0, 0xA1)) * (2 * deep_pairs)
    deep = infer_metadata(deep_metadata, deep_pairs, 8)
    assert len(deep) == 1
    assert deep[0]["used_tag_widths"] == {"0": 2}
    assert len(deep[0]["tokens"]) == 2 * deep_pairs

    print("GOW_CUSTOM_USERDATA_CARRIER_SELFTEST_PASSED")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect one exact outer-carrier byte buffer")
    inspect_p.add_argument("input")
    inspect_p.add_argument("--offset", type=lambda x: int(x, 0), default=0)
    inspect_p.add_argument("--length", type=lambda x: int(x, 0))
    inspect_p.add_argument("--output")
    inspect_p.add_argument("--max-metadata-candidates", type=int, default=128)
    inspect_p.set_defaults(func=command_inspect)

    self_p = sub.add_parser("selftest")
    self_p.set_defaults(func=command_selftest)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except CarrierError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
