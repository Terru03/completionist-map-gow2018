#!/usr/bin/env python3
"""Inspect and build GoW 2018 custom-userdata decoded record descriptors.

This tool works on the *decoded descriptor components* used by the native
save/restore codec. It does not claim to parse the outer 16-byte header,
compressed carrier, or trailing descriptor-row sections consumed by 0x7E9550.

Proven decoded record shape:
    sizes[i]   = u8 total record size
    offsets[i] = little-endian u16 offset into blob
    blob[offset:offset+size] =
        little-endian u64 CodeSideLuaClass key/reference + callback payload

The native save serializer at 0x7E9190 produces this shape. The restore
dispatcher near 0x7E7D7F consumes the inverse shape.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

MAX_RECORDS = 512
MAX_BLOB = 0x3000
MAX_CALLBACK_PAYLOAD = 0x80
KEY_SIZE = 8


class DescriptorError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    index: int
    offset: int
    stored_size: int
    class_key: int
    payload: bytes

    @property
    def payload_size(self) -> int:
        return len(self.payload)

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "offset": self.offset,
            "stored_size": self.stored_size,
            "payload_size": self.payload_size,
            "class_key": f"0x{self.class_key:016X}",
            "payload_sha256": hashlib.sha256(self.payload).hexdigest(),
            "payload_hex": self.payload.hex(),
        }


def _decode_offsets(raw: bytes, count: int) -> list[int]:
    expected = count * 2
    if len(raw) != expected:
        raise DescriptorError(
            f"offset table has {len(raw)} bytes; expected exactly {expected} "
            f"for {count} records"
        )
    if not raw:
        return []
    return list(struct.unpack(f"<{count}H", raw))


def parse_components(
    sizes: bytes,
    offsets_raw: bytes,
    blob: bytes,
    *,
    serializer_compatible: bool = False,
    require_contiguous: bool = False,
) -> list[Record]:
    count = len(sizes)
    offsets = _decode_offsets(offsets_raw, count)

    if serializer_compatible:
        if count > MAX_RECORDS:
            raise DescriptorError(
                f"{count} records exceeds native save-side limit {MAX_RECORDS}"
            )
        if len(blob) > MAX_BLOB:
            raise DescriptorError(
                f"blob length 0x{len(blob):X} exceeds native save-side limit "
                f"0x{MAX_BLOB:X}"
            )

    records: list[Record] = []
    occupied: list[tuple[int, int, int]] = []
    expected_offset = 0

    for index, (stored_size, offset) in enumerate(zip(sizes, offsets)):
        if stored_size < KEY_SIZE:
            raise DescriptorError(
                f"record {index}: stored size {stored_size} is smaller than "
                f"the {KEY_SIZE}-byte class-key header"
            )

        end = offset + stored_size
        if end > len(blob):
            raise DescriptorError(
                f"record {index}: range 0x{offset:X}..0x{end:X} exceeds blob "
                f"length 0x{len(blob):X}"
            )

        if require_contiguous and offset != expected_offset:
            raise DescriptorError(
                f"record {index}: offset 0x{offset:X}; expected contiguous "
                f"offset 0x{expected_offset:X}"
            )

        key = struct.unpack_from("<Q", blob, offset)[0]
        payload = blob[offset + KEY_SIZE:end]

        if serializer_compatible and len(payload) > MAX_CALLBACK_PAYLOAD:
            raise DescriptorError(
                f"record {index}: payload {len(payload)} exceeds native "
                f"save callback buffer 0x{MAX_CALLBACK_PAYLOAD:X}"
            )

        for other_start, other_end, other_index in occupied:
            if offset < other_end and end > other_start:
                raise DescriptorError(
                    f"record {index} overlaps record {other_index}: "
                    f"0x{offset:X}..0x{end:X} vs "
                    f"0x{other_start:X}..0x{other_end:X}"
                )
        occupied.append((offset, end, index))

        records.append(
            Record(
                index=index,
                offset=offset,
                stored_size=stored_size,
                class_key=key,
                payload=payload,
            )
        )
        expected_offset = end

    if require_contiguous and expected_offset != len(blob):
        raise DescriptorError(
            f"contiguous records end at 0x{expected_offset:X}, but blob length "
            f"is 0x{len(blob):X}"
        )

    return records


def _parse_class_key(value: object, index: int) -> int:
    if isinstance(value, int):
        key = value
    elif isinstance(value, str):
        try:
            key = int(value, 0)
        except ValueError as exc:
            raise DescriptorError(
                f"record {index}: invalid class_key {value!r}"
            ) from exc
    else:
        raise DescriptorError(
            f"record {index}: class_key must be an integer or 0x-prefixed string"
        )
    if not 0 <= key <= 0xFFFFFFFFFFFFFFFF:
        raise DescriptorError(
            f"record {index}: class_key 0x{key:X} does not fit in u64"
        )
    return key


def _parse_payload(item: dict, index: int) -> bytes:
    raw = item.get("payload_hex", "")
    if not isinstance(raw, str):
        raise DescriptorError(f"record {index}: payload_hex must be a string")
    compact = "".join(raw.split())
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise DescriptorError(
            f"record {index}: payload_hex is not valid hexadecimal"
        ) from exc


def build_components(items: Iterable[dict]) -> tuple[bytes, bytes, bytes, list[Record]]:
    sizes = bytearray()
    offsets = bytearray()
    blob = bytearray()
    records: list[Record] = []

    items = list(items)
    if len(items) > MAX_RECORDS:
        raise DescriptorError(
            f"{len(items)} records exceeds native save-side limit {MAX_RECORDS}"
        )

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise DescriptorError(f"record {index}: expected a JSON object")
        if "class_key" not in item:
            raise DescriptorError(f"record {index}: missing class_key")

        key = _parse_class_key(item["class_key"], index)
        payload = _parse_payload(item, index)
        if len(payload) > MAX_CALLBACK_PAYLOAD:
            raise DescriptorError(
                f"record {index}: payload {len(payload)} exceeds native save "
                f"callback buffer 0x{MAX_CALLBACK_PAYLOAD:X}"
            )

        stored_size = KEY_SIZE + len(payload)
        if stored_size > 0xFF:
            raise DescriptorError(
                f"record {index}: total size {stored_size} does not fit in u8"
            )

        offset = len(blob)
        if offset > 0xFFFF:
            raise DescriptorError(
                f"record {index}: offset 0x{offset:X} does not fit in u16"
            )
        if offset + stored_size > MAX_BLOB:
            raise DescriptorError(
                f"record {index}: blob would exceed native save-side limit "
                f"0x{MAX_BLOB:X}"
            )

        sizes.append(stored_size)
        offsets += struct.pack("<H", offset)
        blob += struct.pack("<Q", key)
        blob += payload
        records.append(Record(index, offset, stored_size, key, payload))

    return bytes(sizes), bytes(offsets), bytes(blob), records


def manifest(records: list[Record], blob: bytes) -> dict:
    return {
        "schema": 1,
        "format": "gow2018_custom_userdata_decoded_descriptor",
        "record_count": len(records),
        "blob_length": len(blob),
        "limits": {
            "max_records": MAX_RECORDS,
            "max_blob": MAX_BLOB,
            "max_callback_payload": MAX_CALLBACK_PAYLOAD,
            "class_key_size": KEY_SIZE,
        },
        "records": [r.to_json() for r in records],
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    sizes = args.sizes.read_bytes()
    offsets = args.offsets.read_bytes()
    blob = args.blob.read_bytes()
    if args.blob_length is not None:
        if not 0 <= args.blob_length <= len(blob):
            raise DescriptorError(
                f"--blob-length {args.blob_length} outside 0..{len(blob)}"
            )
        blob = blob[: args.blob_length]

    records = parse_components(
        sizes,
        offsets,
        blob,
        serializer_compatible=args.serializer_compatible,
        require_contiguous=args.require_contiguous,
    )
    out = manifest(records, blob)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(
            f"records={len(records)} blob=0x{len(blob):X} "
            f"serializer_compatible={args.serializer_compatible}"
        )
        for r in records:
            print(
                f"[{r.index:03d}] off=0x{r.offset:04X} size=0x{r.stored_size:02X} "
                f"payload=0x{r.payload_size:02X} key=0x{r.class_key:016X} "
                f"sha256={hashlib.sha256(r.payload).hexdigest()[:16]}"
            )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    source = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(source, dict):
        items = source.get("records")
    else:
        items = source
    if not isinstance(items, list):
        raise DescriptorError('input JSON must be a list or {"records": [...]}')

    sizes, offsets, blob, records = build_components(items)
    parsed = parse_components(
        sizes,
        offsets,
        blob,
        serializer_compatible=True,
        require_contiguous=True,
    )
    if parsed != records:
        raise AssertionError("internal build/parse round-trip mismatch")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "sizes.bin").write_bytes(sizes)
    (args.out_dir / "offsets.bin").write_bytes(offsets)
    (args.out_dir / "blob.bin").write_bytes(blob)
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest(records, blob), indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"built records={len(records)} blob=0x{len(blob):X} "
        f"out={args.out_dir}"
    )
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    source = [
        {"class_key": "0x1122334455667788", "payload_hex": ""},
        {"class_key": "0x0123456789ABCDEF", "payload_hex": "00 01 FE FF"},
        {
            "class_key": 0xA5A5A5A5A5A5A5A5,
            "payload_hex": bytes(range(MAX_CALLBACK_PAYLOAD)).hex(),
        },
    ]
    sizes, offsets, blob, built = build_components(source)
    parsed = parse_components(
        sizes,
        offsets,
        blob,
        serializer_compatible=True,
        require_contiguous=True,
    )
    assert parsed == built
    assert sizes == bytes([8, 12, 136])
    assert struct.unpack("<3H", offsets) == (0, 8, 20)
    assert len(blob) == 156

    try:
        parse_components(b"\x07", b"\x00\x00", b"\x00" * 7)
    except DescriptorError:
        pass
    else:
        raise AssertionError("size<8 rejection failed")

    try:
        build_components(
            [{"class_key": 1, "payload_hex": "00" * (MAX_CALLBACK_PAYLOAD + 1)}]
        )
    except DescriptorError:
        pass
    else:
        raise AssertionError("payload limit rejection failed")

    print("GOW_CUSTOM_USERDATA_DESCRIPTOR_SELFTEST_PASSED")
    print("records=3 blob=0x9C sizes=08,0C,88 offsets=0000,0008,0014")
    return 0


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Inspect/build the decoded GoW 2018 custom-userdata record descriptor; "
            "this does not parse the outer compressed save carrier."
        )
    )
    sub = p.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect decoded descriptor components")
    inspect_p.add_argument("--sizes", type=Path, required=True, help="u8 size table")
    inspect_p.add_argument(
        "--offsets", type=Path, required=True, help="little-endian u16 offset table"
    )
    inspect_p.add_argument("--blob", type=Path, required=True, help="record blob")
    inspect_p.add_argument(
        "--blob-length",
        type=lambda x: int(x, 0),
        help="optional logical blob length (decimal or 0x...)",
    )
    inspect_p.add_argument(
        "--serializer-compatible",
        action="store_true",
        help="also enforce the proven 0x7E9190 save-side limits",
    )
    inspect_p.add_argument(
        "--require-contiguous",
        action="store_true",
        help="require offsets to be the contiguous layout emitted by the builder",
    )
    inspect_p.add_argument("--json", action="store_true", help="emit JSON manifest")
    inspect_p.set_defaults(func=cmd_inspect)

    build_p = sub.add_parser("build", help="build native-compatible decoded components")
    build_p.add_argument("--input", type=Path, required=True, help="records JSON")
    build_p.add_argument("--out-dir", type=Path, required=True)
    build_p.set_defaults(func=cmd_build)

    test_p = sub.add_parser("selftest", help="run deterministic build/parse tests")
    test_p.set_defaults(func=cmd_selftest)
    return p


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (DescriptorError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
