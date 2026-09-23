#!/usr/bin/env python3
"""Offline staged WAD graph reader. Preserves token and GameObject state fields."""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

staged = load_module("_ship_staged_wad", HERE / "staged_wad_bitstream.py")

def token_value(token: dict, strings: list[str], records: list[dict]) -> dict:
    result = {
        "tag": token["tag"],
        "payload": token["payload"],
        "width": token["width"],
        "raw_hex": token["raw_hex"],
    }
    if token["tag"] == 0:
        result["kind"] = "bool"
        result["decoded"] = bool(token["payload"])
    elif token["tag"] == 1:
        result["kind"] = "scalar_u32"
        result["decoded"] = token["payload"]
    elif token["tag"] == 2:
        result["kind"] = "string"
        result["decoded"] = strings[token["payload"]]
    elif token["tag"] == 3:
        result["kind"] = "table_ref"
        result["decoded"] = token["payload"] - 1
    elif token["tag"] == 4:
        result["kind"] = "opaque_tag4"
    elif token["tag"] == 5:
        result["kind"] = "record_ref"
        record_index = token["payload"]
        result["decoded"] = record_index
        if 0 <= record_index < len(records):
            record = records[record_index]
            result["record_class_key_hex"] = f"0x{record['class_key']:016X}"
            result["record_payload_hex"] = record["payload"].hex()
            parsed = staged._decoder().parse_gameobject_payload(record["payload"])
            if parsed is not None:
                result["gameobject"] = {
                    "flags": parsed["flags"],
                    "aux": parsed["aux"],
                    "has_upper": parsed["has_upper"],
                    "upper_u32": parsed["upper_u32"],
                    "registry_hash_hex": f"0x{parsed['registry_hash']:016X}",
                    "object_hash_hex": f"0x{parsed['object_hash']:016X}",
                }
    else:
        result["kind"] = "unknown"
    return result


def carrier_with_tokens(envelope: bytes, expected_lua_length: int) -> list[dict]:
    if len(envelope) < 2:
        return []
    outer_length = int.from_bytes(envelope[:2], "little")
    if outer_length != len(envelope) - 2:
        return []

    module = staged._decoder()
    payload = envelope[2:]
    candidates = []
    for alignment in range(8):
        aligned = staged._aligned_bytes(payload, alignment)
        needle = expected_lua_length.to_bytes(2, "big")
        positions = []
        cursor = 0
        while True:
            at = aligned.find(needle, cursor)
            if at < 0:
                break
            positions.append(at)
            if len(positions) > staged.MAX_LENGTH_POSITIONS:
                raise RuntimeError("lua_length_position_cap")
            cursor = at + 1

        for at in positions:
            start = at + 2
            if start + expected_lua_length > len(aligned):
                continue
            raw = aligned[start:start + expected_lua_length]
            if len(raw) < 18:
                continue
            got = module.decompress_stream(raw, 16)
            if got is None:
                continue
            decoded, consumed = got
            header = struct.unpack_from("<8H", raw)
            if header[7] != consumed or header[1] + header[5] != len(decoded):
                continue
            for parsed in staged._decode_paths(
                module, raw, decoded, consumed, None, {}
            ):
                if parsed["carrier_length"] != len(raw):
                    continue
                candidates.append(
                    {
                        "alignment": alignment,
                        "bit_offset": alignment + start * 8,
                        "raw": raw,
                        "decoded": decoded,
                        "parsed": parsed,
                    }
                )
    # The canonical capture is expected to have one exact graph parse.
    unique = {}
    for item in candidates:
        p = item["parsed"]
        key = (
            item["alignment"],
            item["bit_offset"],
            p["carrier_length"],
            tuple(
                (t["tag"], t["payload"], t["width"], t["raw_hex"])
                for t in p["token_parse"]
            ),
        )
        unique[key] = item
    return list(unique.values())


def graph_records(raw: bytes, decoded: bytes, parsed: dict):
    header = struct.unpack_from("<8H", raw)
    (
        section0_count,
        blob_offset,
        pair_count,
        row_count,
        record_count,
        blob_length,
        _scalar_c,
        consumed,
    ) = header

    module = staged._decoder()
    after_compressed = 16 + consumed
    section0_end = after_compressed + 2 * section0_count
    section0 = (
        list(struct.unpack_from(f"<{section0_count}H", raw, after_compressed))
        if section0_count
        else []
    )
    prefix = decoded[:blob_offset]
    strings = []
    for offset in section0:
        value = module.extract_string(prefix, offset)
        if value is None:
            raise RuntimeError("invalid string table in accepted graph")
        strings.append(value)

    tokens = parsed["token_parse"]
    if len(tokens) != pair_count * 2:
        raise RuntimeError("accepted token count changed")
    metadata_end = section0_end + sum(token["width"] for token in tokens)
    fixed_end = metadata_end + record_count + 2 * record_count + 6 * row_count
    if fixed_end > len(raw):
        raise RuntimeError("accepted graph metadata overflow")

    sizes = raw[metadata_end:metadata_end + record_count]
    offsets_start = metadata_end + record_count
    offsets_raw = raw[offsets_start:offsets_start + 2 * record_count]
    rows_raw = raw[
        offsets_start + 2 * record_count:
        offsets_start + 2 * record_count + 6 * row_count
    ]
    blob = decoded[blob_offset:blob_offset + blob_length]

    offsets = [
        struct.unpack_from("<H", offsets_raw, index * 2)[0]
        for index in range(record_count)
    ]
    records = []
    for index, (size, offset) in enumerate(zip(sizes, offsets)):
        if size < 8 or offset + size > len(blob):
            raise RuntimeError("accepted record bounds changed")
        record = blob[offset:offset + size]
        records.append(
            {
                "index": index,
                "class_key": struct.unpack_from("<Q", record, 0)[0],
                "payload": record[8:],
            }
        )

    rows = []
    for index in range(row_count):
        first, count, aux = struct.unpack_from("<HHH", rows_raw, index * 6)
        if first + count > pair_count:
            raise RuntimeError("accepted row pair bounds changed")
        rows.append({"first_pair": first, "pair_count": count, "aux": aux})

    pairs = [
        (tokens[index * 2], tokens[index * 2 + 1])
        for index in range(pair_count)
    ]
    return strings, records, rows, pairs


def extract_state_entries(raw: bytes, decoded: bytes, parsed: dict) -> list[dict]:
    strings, records, rows, pairs = graph_records(raw, decoded, parsed)

    def string_value(token: dict):
        if token["tag"] != 2:
            return None
        if token["payload"] >= len(strings):
            return None
        return strings[token["payload"]]

    def table_index(token: dict):
        return token["payload"] - 1 if token["tag"] == 3 else None

    def row_pairs(index: int):
        row = rows[index]
        return pairs[row["first_pair"]:row["first_pair"] + row["pair_count"]]

    subobj_tables = set()
    for row_index in range(len(rows)):
        for key, value in row_pairs(row_index):
            if string_value(key) == "__subobjs":
                target = table_index(value)
                if target is not None:
                    subobj_tables.add(target)

    output = []
    for sub_index in sorted(subobj_tables):
        for parent_key, state_ref in row_pairs(sub_index):
            state_index = table_index(state_ref)
            if state_index is None:
                continue

            fields = []
            state_token = None
            for field_key, field_value in row_pairs(state_index):
                name = string_value(field_key)
                if name is None:
                    continue
                value = token_value(field_value, strings, records)
                fields.append({"name": name, "value": value})
                if name == "state":
                    state_token = value

            if state_token is None:
                continue

            parent = token_value(parent_key, strings, records)
            signature = tuple(
                sorted((field["name"], field["value"]["tag"]) for field in fields)
            )
            output.append(
                {
                    "subobj_table_row": sub_index,
                    "state_row": state_index,
                    "parent": parent,
                    "state": state_token,
                    "fields": fields,
                    "field_signature": [
                        {"name": name, "value_tag": tag}
                        for name, tag in signature
                    ],
                    "field_names": sorted(field["name"] for field in fields),
                }
            )
    return output
