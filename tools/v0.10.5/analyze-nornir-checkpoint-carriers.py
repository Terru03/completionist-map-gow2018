#!/usr/bin/env python3
"""Decode the exact Nornir WAD checkpoint carriers in the two-save capture.

The process dumps and save copies are opened read-only. The report records
GameObject hash pairs and typed fields, with exact byte matches into save slots.
It does not infer a state for a missing checkpoint object.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
STAGES = (
    "A0_before_runes", "A1_after_first_rune", "A2_after_second_rune",
    "A3_after_chest_open", "B0_before_chest_open", "B1_after_chest_open",
)
TARGETS = {
    "A": ("Xpl200_Funeral", "nornir_chest_c190d59340706bb79925cb9f2d5867cf"),
    "B": ("Peak720_SummitAscentHUB", "nornir_chest_c0cf411940bad7d00042afa7a46f5514"),
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DUMPS = load_module(HERE / "analyze-nornir-two-save-dumps.py", "nornir_dump_reader")
CODEC = load_module(HERE / "decode-active-raven-subobject-state.py", "nornir_carrier_codec")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def read_target_payload(root: Path, stage: str, wad_name: str) -> bytes:
    metadata = json.loads((root / f"{stage}.json").read_text(encoding="utf-8-sig"))
    require(metadata["stage"] == stage, f"wrong stage metadata: {stage}")
    require(metadata["executable_sha256"] == DUMPS.EXPECTED_EXE_SHA,
            f"unsupported GoW executable: {stage}")
    dump = DUMPS.FullMemoryDump(root / f"{stage}.dmp")
    try:
        base = dump.module_base()
        require(base == int(metadata["module_base"], 16),
                f"module base differs from metadata: {stage}")
        pool_size, = struct.unpack("<I", dump.read_virtual(base + DUMPS.POOL_SIZE_RVA, 4))
        pool_base, = struct.unpack("<Q", dump.read_virtual(base + DUMPS.POOL_BASE_RVA, 8))
        count, = struct.unpack("<I", dump.read_virtual(base + DUMPS.RECORD_COUNT_RVA, 4))
        require(count <= DUMPS.MAX_RECORDS and pool_size <= DUMPS.MAX_POOL_SIZE,
                f"implausible staging table: {stage}")
        matches = []
        for index in range(count):
            raw = dump.read_virtual(base + DUMPS.RECORD_BASE_RVA + index * DUMPS.RECORD_STRIDE,
                                    DUMPS.RECORD_STRIDE)
            name = raw[0x84:0xA8].split(b"\0", 1)[0].decode("ascii", errors="replace")
            if name != wad_name:
                continue
            address, = struct.unpack_from("<Q", raw, 0x48)
            size, = struct.unpack_from("<I", raw, 0x58)
            require(4 <= size <= DUMPS.MAX_PAYLOAD and pool_base <= address and
                    address + size <= pool_base + pool_size,
                    f"target WAD payload outside staged pool: {stage}")
            matches.append(dump.read_virtual(address, size))
        require(len(matches) == 1, f"expected one {wad_name} record at {stage}; found {len(matches)}")
        return matches[0]
    finally:
        dump.close()


def decode_carrier(carrier: bytes) -> dict:
    require(len(carrier) >= 18, "short checkpoint carrier")
    got = CODEC.decompress_stream(carrier, 16)
    require(got is not None, "checkpoint carrier has no valid zlib stream")
    decoded, consumed = got
    canonical = CODEC.validate_and_decode_candidate(carrier, 0, decoded, consumed, None, {})
    canonical = [row for row in canonical if row["carrier_length"] == len(carrier)]
    require(len(canonical) == 1, f"ambiguous checkpoint carrier graph: {len(canonical)} parses")
    parsed = canonical[0]
    header = parsed["header"]
    strings = parsed["strings"]
    rows = parsed["rows"]
    pair_count = header["metadata_pair_count"]
    row_count = header["row_count"]
    record_count = header["record_count"]
    section0_end = 16 + consumed + 2 * header["section0_word_count"]
    paths = [
        (end, tokens)
        for end, tokens in CODEC.parse_token_paths(carrier, section0_end, pair_count * 2)
        if end + 3 * record_count + 6 * row_count == len(carrier)
    ]
    require(len(paths) == 1, f"ambiguous checkpoint token path: {len(paths)}")
    metadata_end, tokens = paths[0]
    sizes = carrier[metadata_end:metadata_end + record_count]
    offsets = struct.unpack_from(f"<{record_count}H", carrier,
                                 metadata_end + record_count) if record_count else ()
    blob = decoded[header["record_blob_offset"]:]
    records = []
    for size, offset in zip(sizes, offsets):
        require(size >= 8 and offset + size <= len(blob), "invalid custom record extent")
        records.append(blob[offset:offset + size])

    def token_value(token: dict):
        tag, number = token["tag"], token["payload"]
        if tag == 0:
            require(number in (0, 1), "invalid Boolean token")
            return bool(number)
        if tag == 1:
            require(token["width"] == 5, "invalid float token width")
            value, = struct.unpack("<f", bytes.fromhex(token["raw_hex"])[1:])
            require(math.isfinite(value), "nonfinite checkpoint float")
            return value
        if tag == 2:
            require(number < len(strings), "invalid string index")
            return strings[number]
        if tag == 3:
            require(1 <= number <= len(rows), "invalid table index")
            return {"table_row": number - 1}
        if tag == 5:
            require(number < len(records), "invalid GameObject record index")
            record = records[number]
            game_object = CODEC.parse_gameobject_payload(record[8:])
            require(game_object is not None, "invalid GameObject checkpoint key")
            return {
                "record_index": number,
                "class_key_hex": f"0x{int.from_bytes(record[:8], 'little'):016X}",
                "registry_hash_hex": f"0x{game_object['registry_hash']:016X}",
                "object_hash_hex": f"0x{game_object['object_hash']:016X}",
            }
        return {"tag": tag, "payload": number, "raw_hex": token["raw_hex"]}

    row_pairs = []
    for row in rows:
        pairs = []
        for index in range(row["first_pair"], row["first_pair"] + row["pair_count"]):
            pairs.append((token_value(tokens[2 * index]),
                          token_value(tokens[2 * index + 1])))
        row_pairs.append(pairs)
    roots = [value["table_row"] for pairs in row_pairs for key, value in pairs
             if key == "__subobjs" and isinstance(value, dict) and "table_row" in value]
    require(len(roots) == 1, f"expected one __subobjs table; found {len(roots)}")
    subobjects = []
    for key, value in row_pairs[roots[0]]:
        require(isinstance(key, dict) and "object_hash_hex" in key and
                isinstance(value, dict) and "table_row" in value,
                "unexpected __subobjs entry")
        fields = {}
        for field, state in row_pairs[value["table_row"]]:
            require(isinstance(field, str) and field not in fields,
                    "ambiguous checkpoint field")
            fields[field] = state
        subobjects.append({**key, "state_row": value["table_row"], "fields": fields})
    return {
        "header": header,
        "strings": strings,
        "subobjects": subobjects,
        "carrier_bytes": len(carrier),
        "carrier_sha256": hashlib.sha256(carrier).hexdigest(),
    }


def save_carrier_matches(path: Path, carrier: bytes) -> list[dict]:
    if not path.exists():
        return []
    save = path.read_bytes()
    require(len(save) == DUMPS.SAVE_PREFIX + DUMPS.SAVE_SLOT_COUNT * DUMPS.SAVE_SLOT_SIZE,
            f"unexpected save layout: {path}")
    matches = []
    for index in range(DUMPS.SAVE_SLOT_COUNT):
        start = DUMPS.SAVE_PREFIX + index * DUMPS.SAVE_SLOT_SIZE
        slot = save[start:start + DUMPS.SAVE_SLOT_SIZE]
        cursor = 0
        while True:
            offset = slot.find(carrier, cursor)
            if offset < 0:
                break
            matches.append({"slot": index, "slot_offset": offset})
            cursor = offset + 1
    return matches


def inspect_stage(root: Path, stage: str) -> dict:
    wad_name, catalogue_id = TARGETS[stage[0]]
    metadata = json.loads((root / f"{stage}.json").read_text(encoding="utf-8-sig"))
    payload = read_target_payload(root, stage, wad_name)
    require(len(payload) >= 4 and int.from_bytes(payload[:2], "little") == len(payload) - 2,
            f"invalid staged payload framing: {stage}")
    carrier = payload[4:]
    decoded = decode_carrier(carrier)
    return {
        "stage": stage,
        "wad": wad_name,
        "chest_catalogue_id": catalogue_id,
        "process_id": metadata["process_id"],
        "process_start_utc": metadata["process_start_utc"],
        "location_note": metadata["note"],
        "save_sha256": metadata["save"].get("sha256"),
        "staged_payload_bytes": len(payload),
        "staged_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "save_carrier_matches": save_carrier_matches(root / f"{stage}.game.sav", carrier),
        **decoded,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root", type=Path)
    args = parser.parse_args()
    root = args.capture_root.resolve()
    require(root.is_dir(), f"capture directory missing: {root}")
    stages = [inspect_stage(root, stage) for stage in STAGES
              if (root / f"{stage}.json").exists()]
    report = {
        "schema": 1,
        "result": "NORNIR_TWO_SAVE_CHECKPOINT_CARRIERS_DECODED",
        "capture_root": str(root),
        "stage_count": len(stages),
        "stages": stages,
        "game_or_save_writes": False,
    }
    output = root / "checkpoint-carriers.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NORNIR_CHECKPOINT_CARRIERS stages={len(stages)} report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
