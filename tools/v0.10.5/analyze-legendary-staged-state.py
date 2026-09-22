#!/usr/bin/env python3
"""Extract generic state-bearing subobjects from a staged WAD capture.

This is an offline research decoder for Legendary Chest work. It reuses the
already-proven bounded staged-WAD framing and token parser, but it does not
change Raven decoding and does not interpret any row as a Legendary Chest yet.

For every tracked Legendary WAD present in the capture, preserve:
- the exact __subobjs parent key;
- parsed GameObject registry/object hashes when the key is a save reference;
- the complete child-state field-name/tag signature;
- the raw token for the field named "state";
- all sibling field tokens needed to classify recurring schemas.

No game process, active save, progression, or game files are touched.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STAGED_PATH = HERE / "staged_wad_bitstream.py"
DEFAULT_CAPTURE = (
    REPO
    / "archive"
    / "field-logs"
    / "runtime-captures"
    / "staged-wad-bitstream-raven-20260921-060345-c2c9bcc1"
)
DEFAULT_CATALOGUE = (
    REPO / "config" / "collectibles" / "v0.10.5" / "all-collectibles.json"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


staged = load_module("_legendary_staged_wad", STAGED_PATH)


def norm(value: str) -> str:
    return "".join(ch for ch in value.lower().removesuffix(".wad") if ch.isalnum())


def tracked_rows(catalogue: dict) -> list[dict]:
    rows = [
        row
        for row in catalogue.get("collectibles", [])
        if row.get("family") == "legendary_chest"
        and row.get("production_eligibility") == "tracked_collectible"
    ]
    if len(rows) != 33:
        raise RuntimeError(f"expected 33 tracked Legendary Chests, found {len(rows)}")
    return rows


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    capture_dir = args.capture_dir.resolve()
    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    rows = tracked_rows(catalogue)
    report_path = capture_dir / "report.json"
    source = json.loads(report_path.read_text(encoding="utf-8"))
    source_records = source.get("records", [])
    if len(source_records) != 425:
        raise RuntimeError(
            f"expected frozen 425-record staged capture, got {len(source_records)}"
        )

    by_norm = {norm(record.get("name", "")): record for record in source_records}
    by_wad = defaultdict(list)
    for row in rows:
        by_wad[norm(row["source"]["wad"])].append(row)

    wad_reports = []
    signature_counts = Counter()
    signature_wads = defaultdict(set)
    matched_catalogue_ids = set()

    for wad_norm, catalogue_rows in sorted(by_wad.items()):
        source_record = by_norm.get(wad_norm)
        if source_record is None:
            wad_reports.append(
                {
                    "wad": catalogue_rows[0]["source"]["wad"],
                    "catalogue_ids": sorted(
                        row["catalogue_id"] for row in catalogue_rows
                    ),
                    "capture_present": False,
                    "state_entries": [],
                }
            )
            continue

        payload_file = source_record.get("payload_file")
        if not payload_file:
            raise RuntimeError(
                f"{source_record['name']}: frozen capture lacks payload_file"
            )
        envelope = (capture_dir / payload_file).read_bytes()
        candidates = carrier_with_tokens(
            envelope, int(source_record["cached_channel_a_lua_length"])
        )
        if len(candidates) != 1:
            raise RuntimeError(
                f"{source_record['name']}: expected one exact carrier graph, "
                f"got {len(candidates)}"
            )
        candidate = candidates[0]
        entries = extract_state_entries(
            candidate["raw"], candidate["decoded"], candidate["parsed"]
        )

        for entry in entries:
            signature = tuple(
                (item["name"], item["value_tag"])
                for item in entry["field_signature"]
            )
            key = json.dumps(signature, separators=(",", ":"))
            signature_counts[key] += 1
            signature_wads[key].add(source_record["name"])

        catalogue_ids = sorted(row["catalogue_id"] for row in catalogue_rows)
        matched_catalogue_ids.update(catalogue_ids)
        wad_reports.append(
            {
                "wad": catalogue_rows[0]["source"]["wad"],
                "staged_name": source_record["name"],
                "staged_index": source_record["index"],
                "catalogue_ids": catalogue_ids,
                "capture_present": True,
                "cached_channel_a_lua_length": source_record[
                    "cached_channel_a_lua_length"
                ],
                "candidate_alignment": candidate["alignment"],
                "candidate_bit_offset": candidate["bit_offset"],
                "state_entry_count": len(entries),
                "state_entries": entries,
            }
        )

    signatures = []
    for key, count in signature_counts.most_common():
        signatures.append(
            {
                "signature": [
                    {"name": name, "value_tag": tag}
                    for name, tag in json.loads(key)
                ],
                "occurrences": count,
                "wad_count": len(signature_wads[key]),
                "wads": sorted(signature_wads[key]),
            }
        )

    absent = [
        item
        for item in wad_reports
        if not item["capture_present"]
    ]
    present = [
        item
        for item in wad_reports
        if item["capture_present"]
    ]
    result = {
        "schema": 1,
        "analysis": "legendary_chest_staged_state_schema_inventory",
        "source_capture": str(capture_dir.relative_to(REPO)),
        "tracked_catalogue_count": len(rows),
        "tracked_wad_count": len(by_wad),
        "capture_present_catalogue_count": sum(
            len(item["catalogue_ids"]) for item in present
        ),
        "capture_present_wad_count": len(present),
        "capture_absent_catalogue_count": sum(
            len(item["catalogue_ids"]) for item in absent
        ),
        "capture_absent_wads": [
            {
                "wad": item["wad"],
                "catalogue_ids": item["catalogue_ids"],
            }
            for item in absent
        ],
        "total_state_entries": sum(
            item.get("state_entry_count", 0) for item in present
        ),
        "schema_signature_count": len(signatures),
        "schema_signatures": signatures,
        "wads": wad_reports,
        "interpretation": {
            "legendary_binding_proven": False,
            "state_semantics_proven": False,
            "purpose": (
                "Inventory exact serialized parent GameObject keys and recurring "
                "state-row schemas before binding any row to a Legendary Chest."
            ),
            "fail_closed": True,
        },
        "safety": {
            "offline_only": True,
            "game_process_accessed": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_files_written": False,
            "raven_decoder_modified": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "Completionist Map - Legendary Chest staged state schema inventory",
        f"tracked_catalogue_count={result['tracked_catalogue_count']}",
        f"tracked_wad_count={result['tracked_wad_count']}",
        f"capture_present_catalogue_count={result['capture_present_catalogue_count']}",
        f"capture_present_wad_count={result['capture_present_wad_count']}",
        f"capture_absent_catalogue_count={result['capture_absent_catalogue_count']}",
        f"total_state_entries={result['total_state_entries']}",
        f"schema_signature_count={result['schema_signature_count']}",
        "legendary_binding_proven=false",
        "state_semantics_proven=false",
        "",
        "TOP SCHEMA SIGNATURES",
    ]
    for item in signatures[:20]:
        names = ",".join(
            f"{field['name']}:tag{field['value_tag']}"
            for field in item["signature"]
        )
        lines.append(
            f"occurrences={item['occurrences']} wad_count={item['wad_count']} "
            f"fields={names}"
        )
    if absent:
        lines += ["", "CAPTURE ABSENT"]
        for item in absent:
            lines.append(
                f"{item['wad']} catalogue_ids={','.join(item['catalogue_ids'])}"
            )
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "LEGENDARY_STAGED_STATE_SCHEMA_INVENTORY_COMPLETE "
        f"present_catalogue={result['capture_present_catalogue_count']} "
        f"present_wads={result['capture_present_wad_count']} "
        f"state_entries={result['total_state_entries']} "
        f"signatures={result['schema_signature_count']}"
    )
    print(
        "legendary_binding_proven=false state_semantics_proven=false "
        "game_process_accessed=false save_or_progression_written=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
