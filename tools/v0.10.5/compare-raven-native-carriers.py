#!/usr/bin/env python3
"""Compare the exact frozen Raven native carriers and replay ALIVE -> DEAD structurally.

Read-only. The only DEAD-side datum permitted as a seed for the forward replay
is the newly observed 25-byte Raven record itself. All prefix, metadata, table,
row, header, and compression changes are reconstructed from ALIVE structure and
deterministic insertion rules, then checked byte-for-byte against DEAD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

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
LAYOUT = {"prefix": 4160, "stride": 1677512, "slot_count": 20, "header_size": 208}
TARGETS = {
    "alive": {"slot_index": 17, "relative_offset": 39272},
    "dead": {"slot_index": 18, "relative_offset": 39203},
}
TAG_WIDTHS = {0: 3, 2: 2}
RAVEN_NAME = b"ravenKilled\x00"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_layout(blob: bytes) -> dict:
    words = struct.unpack_from("<8I", blob, 0)
    header_size, stride, declared = words[4], words[5], words[6]
    if declared != len(blob):
        raise RuntimeError(f"declared size mismatch {declared} != {len(blob)}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    return {
        "prefix": prefix,
        "stride": stride,
        "slot_count": count,
        "header_size": header_size,
    }


def decode_token(raw: bytes) -> dict:
    tag = raw[0]
    return {
        "tag": tag,
        "width": len(raw),
        "value": int.from_bytes(raw[1:], "little"),
        "raw_hex": raw.hex(),
    }


def encode_token(token: dict) -> bytes:
    tag = token["tag"]
    width = token["width"]
    return bytes([tag]) + int(token["value"]).to_bytes(width - 1, "little")


def copy_token(token: dict, *, add: int = 0) -> dict:
    return {
        "tag": token["tag"],
        "width": token["width"],
        "value": token["value"] + add,
        "raw_hex": "",
    }


def parse_strings(prefix: bytes) -> list[dict]:
    out = []
    pos = 0
    while pos < len(prefix):
        end = prefix.find(b"\x00", pos)
        if end < 0:
            out.append({"offset": pos, "text": None, "raw_hex": prefix[pos:].hex()})
            break
        raw = prefix[pos:end]
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            text = None
        out.append({"offset": pos, "text": text, "raw_hex": raw.hex()})
        pos = end + 1
    return out


def parse_carrier(blob: bytes, label: str) -> dict:
    if save_layout(blob) != LAYOUT:
        raise RuntimeError(f"{label}: unexpected save layout {save_layout(blob)}")
    target = TARGETS[label]
    slot_start = LAYOUT["prefix"] + target["slot_index"] * LAYOUT["stride"]
    stream_offset = slot_start + target["relative_offset"]
    carrier_start = stream_offset - HEADER.size
    words = HEADER.unpack_from(blob, carrier_start)
    header = dict(zip(HEADER_FIELDS, words))
    comp_end = stream_offset + header["compressed_length"]
    compressed = blob[stream_offset:comp_end]
    decoded = zlib.decompress(compressed)
    expected_decoded = header["record_blob_offset"] + header["record_blob_length"]
    if len(decoded) != expected_decoded:
        raise RuntimeError(f"{label}: decoded length {len(decoded)} != header {expected_decoded}")

    pos = comp_end
    section0_raw = blob[pos:pos + 2 * header["section0_word_count"]]
    section0 = list(struct.unpack("<" + "H" * header["section0_word_count"], section0_raw))
    pos += len(section0_raw)

    token_count = 2 * header["metadata_pair_count"]
    tokens = []
    for _ in range(token_count):
        tag = blob[pos]
        width = TAG_WIDTHS.get(tag)
        if width is None:
            raise RuntimeError(f"{label}: unsupported metadata tag {tag} at 0x{pos:X}")
        raw = blob[pos:pos + width]
        tokens.append(decode_token(raw))
        pos += width
    metadata_pairs = [
        [tokens[i], tokens[i + 1]] for i in range(0, len(tokens), 2)
    ]

    size_raw = blob[pos:pos + header["record_count"]]
    sizes = list(size_raw)
    pos += len(size_raw)

    offset_raw = blob[pos:pos + 2 * header["record_count"]]
    offsets = list(struct.unpack("<" + "H" * header["record_count"], offset_raw))
    pos += len(offset_raw)

    rows = []
    for _ in range(header["row_count"]):
        raw = blob[pos:pos + 6]
        if len(raw) != 6:
            raise RuntimeError(f"{label}: truncated row table")
        values = struct.unpack("<3H", raw)
        rows.append({"values": list(values), "raw_hex": raw.hex()})
        pos += 6

    prefix = decoded[:header["record_blob_offset"]]
    record_blob = decoded[
        header["record_blob_offset"]:
        header["record_blob_offset"] + header["record_blob_length"]
    ]
    records = []
    for i, (off, size) in enumerate(zip(offsets, sizes)):
        raw = record_blob[off:off + size]
        if len(raw) != size:
            raise RuntimeError(f"{label}: record {i} truncated")
        class_key = struct.unpack_from("<Q", raw, 0)[0] if size >= 8 else None
        payload = raw[8:] if size >= 8 else b""
        records.append({
            "index": i,
            "offset": off,
            "size": size,
            "raw": raw,
            "raw_hex": raw.hex(),
            "class_key": class_key,
            "class_key_hex": f"0x{class_key:016X}" if class_key is not None else None,
            "payload_hex": payload.hex(),
            "payload_prefix_hex": payload[:-8].hex() if len(payload) >= 8 else payload.hex(),
            "trailing_u64": (
                int.from_bytes(payload[-8:], "little") if len(payload) >= 8 else None
            ),
            "trailing_u64_hex": (
                f"0x{int.from_bytes(payload[-8:], 'little'):016X}"
                if len(payload) >= 8 else None
            ),
        })

    carrier = blob[carrier_start:pos]
    return {
        "label": label,
        "slot_start": slot_start,
        "stream_offset": stream_offset,
        "carrier_start": carrier_start,
        "carrier_end": pos,
        "carrier_length": len(carrier),
        "carrier": carrier,
        "header": header,
        "compressed": compressed,
        "decoded": decoded,
        "prefix": prefix,
        "prefix_strings": parse_strings(prefix),
        "record_blob": record_blob,
        "section0": section0,
        "metadata_pairs": metadata_pairs,
        "sizes": sizes,
        "offsets": offsets,
        "rows": rows,
        "records": records,
    }


def public_carrier(c: dict) -> dict:
    return {
        "label": c["label"],
        "slot_start": c["slot_start"],
        "stream_offset": c["stream_offset"],
        "carrier_start": c["carrier_start"],
        "carrier_end": c["carrier_end"],
        "carrier_length": c["carrier_length"],
        "carrier_sha256": sha256_bytes(c["carrier"]),
        "compressed_sha256": sha256_bytes(c["compressed"]),
        "decoded_sha256": sha256_bytes(c["decoded"]),
        "header": c["header"],
        "prefix_hex": c["prefix"].hex(),
        "prefix_strings": c["prefix_strings"],
        "record_blob_hex": c["record_blob"].hex(),
        "section0": c["section0"],
        "metadata_pairs": c["metadata_pairs"],
        "sizes": c["sizes"],
        "offsets": c["offsets"],
        "rows": c["rows"],
        "records": [
            {k: v for k, v in r.items() if k != "raw"} for r in c["records"]
        ],
    }


def encode_pair(pair: list[dict]) -> bytes:
    return b"".join(encode_token(t) for t in pair)


def build_carrier(
    prefix: bytes,
    records: list[bytes],
    section0: list[int],
    metadata_pairs: list[list[dict]],
    rows: list[tuple[int, int, int]],
    scalar_c: int,
    level: int,
) -> bytes:
    offsets = []
    cursor = 0
    for rec in records:
        offsets.append(cursor)
        cursor += len(rec)
    record_blob = b"".join(records)
    decoded = prefix + record_blob
    comp = zlib.compress(decoded, level)
    header = HEADER.pack(
        len(section0),
        len(prefix),
        len(metadata_pairs),
        len(rows),
        len(records),
        len(record_blob),
        scalar_c,
        len(comp),
    )
    tail = bytearray()
    if section0:
        tail += struct.pack("<" + "H" * len(section0), *section0)
    for pair in metadata_pairs:
        tail += encode_pair(pair)
    tail += bytes(len(rec) for rec in records)
    if offsets:
        tail += struct.pack("<" + "H" * len(offsets), *offsets)
    for row in rows:
        tail += struct.pack("<3H", *row)
    return header + comp + bytes(tail)


def compression_matches(
    prefix: bytes,
    records: list[bytes],
    section0: list[int],
    metadata_pairs: list[list[dict]],
    rows: list[tuple[int, int, int]],
    scalar_c: int,
    target: bytes,
) -> list[int]:
    return [
        level
        for level in range(10)
        if build_carrier(prefix, records, section0, metadata_pairs, rows, scalar_c, level)
        == target
    ]


def common_prefix(a: bytes, b: bytes) -> int:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a: bytes, b: bytes) -> int:
    i = 0
    limit = min(len(a), len(b))
    while i < limit and a[len(a)-1-i] == b[len(b)-1-i]:
        i += 1
    return i


def analyse(alive_path: Path, dead_path: Path, out_dir: Path) -> dict:
    before = {"alive": sha256_file(alive_path), "dead": sha256_file(dead_path)}
    alive_blob = alive_path.read_bytes()
    dead_blob = dead_path.read_bytes()
    alive = parse_carrier(alive_blob, "alive")
    dead = parse_carrier(dead_blob, "dead")

    if len(alive["records"]) != 2 or len(dead["records"]) != 3:
        raise RuntimeError("unexpected Raven record counts")
    if alive["records"][0]["raw"] != dead["records"][0]["raw"]:
        raise RuntimeError("record 0 is not preserved ALIVE -> DEAD")
    if alive["records"][1]["raw"] != dead["records"][2]["raw"]:
        raise RuntimeError("record 1 is not preserved as DEAD record 2")
    inserted_record = dead["records"][1]["raw"]

    expected_alive_prefix = b"__subobjs\x00mapSummaryComplete\x00"
    expected_dead_prefix = b"__subobjs\x00ravenKilled\x00mapSummaryComplete\x00"
    if alive["prefix"] != expected_alive_prefix:
        raise RuntimeError("unexpected ALIVE decoded prefix")
    if dead["prefix"] != expected_dead_prefix:
        raise RuntimeError("unexpected DEAD decoded prefix")

    insert_at = len(b"__subobjs\x00")
    replay_prefix = alive["prefix"][:insert_at] + RAVEN_NAME + alive["prefix"][insert_at:]
    replay_records = [
        alive["records"][0]["raw"],
        inserted_record,
        alive["records"][1]["raw"],
    ]

    replay_section0 = alive["section0"] + [alive["header"]["record_blob_offset"]]

    base_a = alive["metadata_pairs"][2]
    new_pair_a = [copy_token(base_a[0], add=0x100), copy_token(base_a[1], add=0x100)]

    base_b = alive["metadata_pairs"][-1]
    new_pair_b = [copy_token(base_b[0], add=1), copy_token(base_b[1])]

    replay_metadata = (
        alive["metadata_pairs"][:3]
        + [new_pair_a]
        + [alive["metadata_pairs"][3]]
        + [new_pair_b]
        + [alive["metadata_pairs"][4]]
    )

    arows = [tuple(r["values"]) for r in alive["rows"]]
    replay_rows = [
        arows[0],
        (arows[1][0], arows[1][1] + 1, arows[1][2]),
        *[(r[0] + 1, r[1], r[2]) for r in arows[2:]],
        (arows[-1][0] + 2, 1, 0),
    ]

    exact_forward_levels = compression_matches(
        replay_prefix,
        replay_records,
        replay_section0,
        replay_metadata,
        replay_rows,
        alive["header"]["scalar_c"],
        dead["carrier"],
    )

    reverse_prefix = dead["prefix"].replace(RAVEN_NAME, b"", 1)
    reverse_records = [dead["records"][0]["raw"], dead["records"][2]["raw"]]
    reverse_section0 = dead["section0"][:-1]
    reverse_metadata = (
        dead["metadata_pairs"][:3]
        + [dead["metadata_pairs"][4]]
        + [dead["metadata_pairs"][6]]
    )
    drows = [tuple(r["values"]) for r in dead["rows"]]
    reverse_rows = [
        drows[0],
        (drows[1][0], drows[1][1] - 1, drows[1][2]),
        *[(r[0] - 1, r[1], r[2]) for r in drows[2:4]],
    ]
    exact_reverse_levels = compression_matches(
        reverse_prefix,
        reverse_records,
        reverse_section0,
        reverse_metadata,
        reverse_rows,
        dead["header"]["scalar_c"],
        alive["carrier"],
    )

    forward_components = {
        "prefix_matches": replay_prefix == dead["prefix"],
        "records_match": replay_records == [r["raw"] for r in dead["records"]],
        "section0_matches": replay_section0 == dead["section0"],
        "metadata_matches": [
            encode_pair(p).hex() for p in replay_metadata
        ] == [encode_pair(p).hex() for p in dead["metadata_pairs"]],
        "rows_match": replay_rows == [tuple(r["values"]) for r in dead["rows"]],
    }
    reverse_components = {
        "prefix_matches": reverse_prefix == alive["prefix"],
        "records_match": reverse_records == [r["raw"] for r in alive["records"]],
        "section0_matches": reverse_section0 == alive["section0"],
        "metadata_matches": [
            encode_pair(p).hex() for p in reverse_metadata
        ] == [encode_pair(p).hex() for p in alive["metadata_pairs"]],
        "rows_match": reverse_rows == [tuple(r["values"]) for r in alive["rows"]],
    }

    verdict = (
        "RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT"
        if exact_forward_levels and exact_reverse_levels
        and all(forward_components.values()) and all(reverse_components.values())
        else "RAVEN_NATIVE_CARRIER_REPLAY_NOT_EXACT"
    )

    inserted = dead["records"][1]
    summary = {
        "schema": 1,
        "analysis": "raven_native_carrier_structural_replay",
        "verdict": verdict,
        "source_hashes_before": before,
        "alive": public_carrier(alive),
        "dead": public_carrier(dead),
        "corrected_decoded_comparison": {
            "whole_common_prefix_length": common_prefix(alive["decoded"], dead["decoded"]),
            "whole_common_suffix_length": common_suffix(alive["decoded"], dead["decoded"]),
            "prefix_common_prefix_length": common_prefix(alive["prefix"], dead["prefix"]),
            "record_mapping": {
                "alive_0_to_dead_0_exact": alive["records"][0]["raw"] == dead["records"][0]["raw"],
                "alive_1_to_dead_2_exact": alive["records"][1]["raw"] == dead["records"][2]["raw"],
                "dead_inserted_record_index": 1,
            },
        },
        "inserted_raven_record": {
            **{k: v for k, v in inserted.items() if k != "raw"},
            "seed_source": "frozen_dead_observation",
            "note": (
                "The 25-byte record identity is observed, not yet generically derived "
                "from ravenKilled or a world-instance identifier."
            ),
        },
        "derived_forward_rules": {
            "string_insert_offset": insert_at,
            "string_insert_ascii": "ravenKilled\\0",
            "section0_append_value": alive["header"]["record_blob_offset"],
            "metadata_new_pair_a_rule": "alive pair[2] token payloads + 0x100",
            "metadata_new_pair_a_hex": encode_pair(new_pair_a).hex(),
            "metadata_new_pair_b_rule": "alive final pair first token value + 1; partner unchanged",
            "metadata_new_pair_b_hex": encode_pair(new_pair_b).hex(),
            "record_insert_index": 1,
            "row_rules": [
                "row0 unchanged",
                "row1 second u16 + 1",
                "rows2..end first u16 + 1",
                "append (old_last_first + 2, 1, 0)",
            ],
        },
        "forward_component_checks": forward_components,
        "reverse_component_checks": reverse_components,
        "forward_exact_zlib_levels": exact_forward_levels,
        "reverse_exact_zlib_levels": exact_reverse_levels,
        "forward_exact": bool(exact_forward_levels) and all(forward_components.values()),
        "reverse_exact": bool(exact_reverse_levels) and all(reverse_components.values()),
        "remaining_unknown": (
            "generic derivation/binding of the inserted record's trailing 64-bit "
            "identity to a specific Raven/world instance"
        ),
    }

    after = {"alive": sha256_file(alive_path), "dead": sha256_file(dead_path)}
    summary["source_hashes_after"] = after
    summary["source_hashes_unchanged"] = before == after
    if before != after:
        raise RuntimeError("frozen save hash changed during read-only analysis")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Raven native-carrier structural replay",
        "",
        f"**Verdict:** `{verdict}`",
        "",
        f"- ALIVE carrier: `{alive['carrier_start']:#x}`..`{alive['carrier_end']:#x}` ({alive['carrier_length']} bytes)",
        f"- DEAD carrier: `{dead['carrier_start']:#x}`..`{dead['carrier_end']:#x}` ({dead['carrier_length']} bytes)",
        f"- Correct whole-decoded common prefix: **{summary['corrected_decoded_comparison']['whole_common_prefix_length']} bytes**.",
        f"- Inserted record class: `{inserted['class_key_hex']}`.",
        f"- Inserted record trailing identity: `{inserted['trailing_u64_hex']}`.",
        f"- Forward exact zlib levels: `{exact_forward_levels}`.",
        f"- Reverse exact zlib levels: `{exact_reverse_levels}`.",
        "",
        "## What was proven",
        "",
        "- The DEAD carrier is reproduced structurally from ALIVE plus the single observed Raven record seed.",
        "- Prefix, section0, metadata, record-size/offset tables, and six-byte rows all follow deterministic insertion/renumbering rules for this transition.",
        "- The reverse removal also rebuilds the frozen ALIVE carrier exactly when the verdict is exact.",
        "",
        "## Remaining unknown",
        "",
        "- The trailing 64-bit identity of the inserted 25-byte record is observed but not yet generically derived/bound to a Raven world instance.",
        "- Therefore this closes the carrier grammar for the Raven transition, but not yet the general instance-key derivation needed to generalise every collectible.",
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    for label, c in (("alive", alive), ("dead", dead)):
        (out_dir / f"{label}-carrier.bin").write_bytes(c["carrier"])
        (out_dir / f"{label}-decoded.bin").write_bytes(c["decoded"])
        (out_dir / f"{label}-tail-structure.json").write_text(
            json.dumps({
                "section0": c["section0"],
                "metadata_pairs": c["metadata_pairs"],
                "sizes": c["sizes"],
                "offsets": c["offsets"],
                "rows": c["rows"],
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(verdict)
    print(f"FORWARD_EXACT_ZLIB_LEVELS={','.join(map(str, exact_forward_levels)) or 'NONE'}")
    print(f"REVERSE_EXACT_ZLIB_LEVELS={','.join(map(str, exact_reverse_levels)) or 'NONE'}")
    print("RAVEN_NATIVE_CARRIER_STRUCTURAL_REPLAY_COMPLETE")
    if verdict != "RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT":
        raise SystemExit(2)
    return summary


def selftest() -> None:
    pairs = [
        [
            {"tag": 2, "width": 2, "value": 0, "raw_hex": ""},
            {"tag": 0, "width": 3, "value": 0x0203, "raw_hex": ""},
        ]
    ]
    rec = bytes.fromhex("62409b14ab50e07501b0b227342530c24ee561807520d55c16")
    raw = build_carrier(
        b"__subobjs\x00",
        [rec],
        [0],
        pairs,
        [(0, 1, 0)],
        1,
        6,
    )
    words = HEADER.unpack_from(raw, 0)
    assert words[0] == 1
    assert words[1] == 10
    assert words[2] == 1
    assert words[3] == 1
    assert words[4] == 1
    assert words[5] == 25
    comp = raw[16:16 + words[7]]
    assert zlib.decompress(comp) == b"__subobjs\x00" + rec
    assert encode_pair(pairs[0]).hex() == "0200000302"
    print("RAVEN_NATIVE_CARRIER_REPLAY_SELFTEST_PASSED")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    an = sub.add_parser("analyse")
    an.add_argument("--alive", type=Path, required=True)
    an.add_argument("--dead", type=Path, required=True)
    an.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "selftest":
        selftest()
        return
    analyse(args.alive, args.dead, args.output_dir)


if __name__ == "__main__":
    main()
