#!/usr/bin/env python3
"""Read only the two field-observed Nornir chest identities in a GoW save.

An exact ``state = 4.0`` checkpoint record is an observed opened result. A
missing record is unknown, since an unopened object need not be serialized.
This research probe is not a production runtime state adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
IDENTITIES = {
    "nornir_chest_c190d59340706bb79925cb9f2d5867cf": {
        "wad": "Xpl200_Funeral",
        "registry_hash": 0x4EC230253427B2B0,
        "object_hash": 0xC0FF99FB89416EC1,
    },
    "nornir_chest_c0cf411940bad7d00042afa7a46f5514": {
        "wad": "Peak720_SummitAscentHUB",
        "registry_hash": 0x63E06E045427145F,
        "object_hash": 0x895FDE6574116698,
    },
}
SAVE_PREFIX = 4160
SAVE_SLOT_SIZE = 1_677_512
SAVE_SLOT_COUNT = 20


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKPOINT = load_module(HERE / "analyze-nornir-checkpoint-carriers.py", "nornir_checkpoint")
CODEC = CHECKPOINT.CODEC


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def newest_slot(save: bytes) -> tuple[int, int, bytes]:
    require(len(save) == SAVE_PREFIX + SAVE_SLOT_COUNT * SAVE_SLOT_SIZE,
            f"unexpected game.sav size: {len(save)}")
    rows = []
    for index in range(SAVE_SLOT_COUNT):
        start = SAVE_PREFIX + index * SAVE_SLOT_SIZE
        slot = save[start:start + SAVE_SLOT_SIZE]
        stamp, = struct.unpack_from("<I", slot)
        rows.append((stamp, index, slot))
    highest = max(stamp for stamp, _, _ in rows)
    current = [row for row in rows if row[0] == highest]
    require(len(current) == 1, f"ambiguous newest save slot: {[row[1] for row in current]}")
    return current[0]


def find_observed_records(slot: bytes) -> tuple[list[dict], list[dict]]:
    needles = {
        identity["object_hash"].to_bytes(8, "little")
        for identity in IDENTITIES.values()
    }
    observed = []
    rejected = []
    for offset, consumed, decoded in CODEC.scan_streams(slot):
        if not any(needle in decoded for needle in needles):
            continue
        header_start = offset - 16
        if header_start < 0:
            rejected.append({"zlib_offset": offset, "reason": "carrier_header_missing"})
            continue
        candidates = CODEC.validate_and_decode_candidate(
            slot, header_start, decoded, consumed, None, {})
        if len(candidates) != 1:
            rejected.append({"zlib_offset": offset, "reason": "ambiguous_carrier",
                             "candidate_count": len(candidates)})
            continue
        length = candidates[0]["carrier_length"]
        carrier = slot[header_start:header_start + length]
        try:
            parsed = CHECKPOINT.decode_carrier(carrier)
        except ValueError as exc:
            rejected.append({"zlib_offset": offset, "reason": str(exc)})
            continue
        for entry in parsed["subobjects"]:
            registry = int(entry["registry_hash_hex"], 16)
            obj = int(entry["object_hash_hex"], 16)
            for catalogue_id, identity in IDENTITIES.items():
                if registry == identity["registry_hash"] and obj == identity["object_hash"]:
                    observed.append({
                        "catalogue_id": catalogue_id,
                        "wad": identity["wad"],
                        "carrier_offset": header_start,
                        "carrier_sha256": parsed["carrier_sha256"],
                        "registry_hash_hex": entry["registry_hash_hex"],
                        "object_hash_hex": entry["object_hash_hex"],
                        "fields": entry["fields"],
                    })
    return observed, rejected


def inspect(save_path: Path) -> dict:
    before = hashlib.sha256(save_path.read_bytes()).hexdigest()
    save = save_path.read_bytes()
    after = hashlib.sha256(save_path.read_bytes()).hexdigest()
    require(before == after == hashlib.sha256(save).hexdigest(),
            "save changed while being read; retry after saving finishes")
    stamp, index, slot = newest_slot(save)
    observed, rejected = find_observed_records(slot)
    by_id = {catalogue_id: [] for catalogue_id in IDENTITIES}
    for row in observed:
        by_id[row["catalogue_id"]].append(row)
    states = []
    for catalogue_id, identity in IDENTITIES.items():
        matches = by_id[catalogue_id]
        if not rejected and len(matches) == 1 and matches[0]["fields"].get("state") == 4.0:
            classification = "OBSERVED_OPENED"
        else:
            classification = "UNKNOWN"
        states.append({
            "catalogue_id": catalogue_id,
            "wad": identity["wad"],
            "classification": classification,
            "match_count": len(matches),
            "matches": matches,
        })
    return {
        "schema": 1,
        "classification": "FIELD_OBSERVED_TWO_CHEST_RESEARCH_ORACLE",
        "save_path": str(save_path),
        "save_sha256": before,
        "newest_slot": index,
        "newest_slot_stamp": stamp,
        "states": states,
        "rejected_matching_streams": rejected,
        "game_or_save_writes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = args.save.resolve()
    require(path.is_file(), f"save missing: {path}")
    result = inspect(path)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = args.output.resolve()
        require(target != path, "output must differ from the save")
        target.write_text(payload, encoding="utf-8")
        print(f"NORNIR_RESEARCH_SAVE_STATE report={target}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
