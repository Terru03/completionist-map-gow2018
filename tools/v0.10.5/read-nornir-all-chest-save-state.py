#!/usr/bin/env python3
"""Read exact Nornir reward-chest states from one explicitly selected save slot.

Missing records remain UNKNOWN. The newest ring slot is an offline ordering
heuristic; it does not identify which older slot the game has actively loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import nornir_checkpoint_keys as keys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_two_chest_reader", HERE / "read-observed-nornir-save-state.py")
assert spec is not None and spec.loader is not None
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)

CHEST_CLASS = "0x75E050AB149B4062"


def scan_slot(slot: bytes, identities: list[dict]) -> tuple[list[dict], list[dict]]:
    expected = {(int(row["registry_hash"], 16), int(row["object_hash"], 16)):
                row["catalogue_id"] for row in identities}
    needles = {row["catalogue_id"]: int(row["object_hash"], 16).to_bytes(8, "little")
               for row in identities}
    matches = {row["catalogue_id"]: [] for row in identities}
    rejected = []
    for offset, consumed, decoded in prior.CODEC.scan_streams(slot):
        implicated = {catalogue_id for catalogue_id, needle in needles.items()
                      if needle in decoded}
        if not implicated:
            continue
        start = offset - 16
        try:
            prior.require(start >= 0, "carrier header missing")
            candidates = prior.CODEC.validate_and_decode_candidate(
                slot, start, decoded, consumed, None, {})
            prior.require(len(candidates) == 1, "ambiguous carrier graph")
            carrier = slot[start:start + candidates[0]["carrier_length"]]
            parsed = prior.CHECKPOINT.decode_carrier(carrier)
            for entry in parsed["subobjects"]:
                pair = (int(entry["registry_hash_hex"], 16),
                        int(entry["object_hash_hex"], 16))
                catalogue_id = expected.get(pair)
                if catalogue_id is not None:
                    matches[catalogue_id].append({
                        "carrier_offset": start,
                        "carrier_sha256": parsed["carrier_sha256"],
                        "class_key_hex": entry["class_key_hex"],
                        "fields": entry["fields"],
                    })
        except (ValueError, KeyError, TypeError, struct.error) as exc:
            rejected.append({"offset": offset, "catalogue_ids": sorted(implicated),
                             "reason": str(exc)})
    states = []
    for row in identities:
        catalogue_id = row["catalogue_id"]
        found = matches[catalogue_id]
        bad = any(catalogue_id in item["catalogue_ids"] for item in rejected)
        value = (found[0]["fields"].get("state") if len(found) == 1 and not bad and
                 found[0]["class_key_hex"] == CHEST_CLASS else None)
        classification = ("OPENED" if value == 4.0 else
                          "UNOPENED" if value in (1.0, 2.0, 3.0) else "UNKNOWN")
        states.append({
            "catalogue_id": catalogue_id,
            "wad": row["wad"],
            "classification": classification,
            "state": value if classification != "UNKNOWN" else None,
            "match_count": len(found),
        })
    return states, rejected


def inspect(path: Path, *, slot_index: int | None = None,
            newest: bool = False) -> dict:
    prior.require((slot_index is not None) != newest,
                  "select exactly one save slot or --newest")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    save = path.read_bytes()
    prior.require(before == hashlib.sha256(save).hexdigest() ==
                  hashlib.sha256(path.read_bytes()).hexdigest(),
                  "save changed during read")
    prior.require(len(save) == prior.SAVE_PREFIX +
                  prior.SAVE_SLOT_COUNT * prior.SAVE_SLOT_SIZE,
                  "unsupported save container length")
    if newest:
        stamp, slot_index, slot = prior.newest_slot(save)
        selection = "highest_stamp_offline_not_active_load_proof"
    else:
        prior.require(slot_index is not None and 0 <= slot_index < prior.SAVE_SLOT_COUNT,
                      "save slot outside ring")
        start = prior.SAVE_PREFIX + slot_index * prior.SAVE_SLOT_SIZE
        slot = save[start:start + prior.SAVE_SLOT_SIZE]
        stamp, = struct.unpack_from("<I", slot)
        selection = "explicit_slot"
    identities = keys.build()
    states, rejected = scan_slot(slot, identities)
    return {
        "schema": 1,
        "result": "EXACT_NORNIR_REWARD_CHEST_SAVE_SLOT_STATES",
        "save": str(path),
        "save_sha256": before,
        "selection": selection,
        "slot_index": slot_index,
        "slot_stamp": stamp,
        "identity_contract": keys.contract(identities),
        "opened_count": sum(row["classification"] == "OPENED" for row in states),
        "unopened_count": sum(row["classification"] == "UNOPENED" for row in states),
        "unknown_count": sum(row["classification"] == "UNKNOWN" for row in states),
        "states": states,
        "rejected_matching_streams": rejected,
        "game_or_save_writes": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--slot", type=int)
    selection.add_argument("--newest", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inspect(args.save.resolve(), slot_index=args.slot, newest=args.newest)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        destination = args.output.resolve()
        prior.require(destination != args.save.resolve(), "report cannot overwrite save")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
        print("NORNIR_ALL_CHEST_SAVE_STATE", destination)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
