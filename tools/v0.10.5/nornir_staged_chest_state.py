"""Read exact Nornir reward-chest states from a captured staged WAD pool.

This is an offline reader. A missing WAD or chest record remains unknown.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

import nornir_checkpoint_keys as keys
import staged_wad_bitstream as bits


STATE_TOKENS = {
    "010000803f": 1,
    "0100000040": 2,
    "0100004040": 3,
    "0100008040": 4,
}
CHEST_CLASS = 0x75E050AB149B4062


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def inspect_payload(payload: bytes, lua_length: int, rows: list[dict]) -> dict:
    """Decode one staged WAD envelope, rejecting ambiguous carrier graphs."""
    states = {row["catalogue_id"]: None for row in rows}
    errors = []
    try:
        need(0 < lua_length <= bits.MAX_CARRIER_BYTES,
             "no bounded cached Lua length")
        result = bits.extract_channel_a(
            payload, None, {}, expected_lua_length=lua_length)
        need(not result["ambiguity_reasons"] and len(result["candidates"]) == 1,
             "need one unambiguous carrier graph")
        candidate = result["candidates"][0]
        bit = candidate["bit_offset"]
        aligned = bits._aligned_bytes(payload[2:], bit % 8)
        raw = aligned[bit // 8:bit // 8 + lua_length]
        module = bits._decoder()
        decoded, consumed = module.decompress_stream(raw, 16)
        parses = bits._decode_paths(module, raw, decoded, consumed, None, {})
        need(len(parses) == 1, "graph parse ambiguous")
        parsed = parses[0]
        header = struct.unpack_from("<8H", raw)
        end = (16 + consumed + 2 * header[0] +
               sum(token["width"] for token in parsed["token_parse"]))
        sizes = raw[end:end + header[4]]
        offsets = struct.unpack_from(f"<{header[4]}H", raw, end + header[4])
        blob = decoded[header[1]:header[1] + header[5]]
        records = [blob[offset:offset + size]
                   for offset, size in zip(offsets, sizes)]
        tokens = parsed["token_parse"]
        pairs = list(zip(tokens[::2], tokens[1::2]))
        wanted = {row["serialized_key"]: row["catalogue_id"] for row in rows}
        need(len(wanted) == len(rows), "duplicate chest key")
        found = set()

        def row_pairs(index: int) -> list[tuple[dict, dict]]:
            row = parsed["rows"][index]
            return pairs[row["first_pair"]:row["first_pair"] + row["pair_count"]]

        for subrow in parsed["subobj_table_rows"]:
            for key, value in row_pairs(subrow):
                if key["tag"] != 5:
                    continue
                saved = records[key["payload"]]
                catalogue_id = wanted.get(saved[8:].hex())
                if catalogue_id is None:
                    continue
                need(catalogue_id not in found, "duplicate exact chest record")
                found.add(catalogue_id)
                need(int.from_bytes(saved[:8], "little") == CHEST_CLASS and
                     value["tag"] == 3,
                     "exact chest class or state table invalid")
                state = [item for field, item in row_pairs(value["payload"] - 1)
                         if field["tag"] == 2 and
                         parsed["strings"][field["payload"]] == "state"]
                need(len(state) == 1 and state[0]["raw_hex"] in STATE_TOKENS,
                     "chest state missing, duplicate, or unknown")
                states[catalogue_id] = STATE_TOKENS[state[0]["raw_hex"]]
    except (ValueError, RuntimeError, IndexError, KeyError, TypeError,
            struct.error) as exc:
        states = dict.fromkeys(states)
        errors.append(str(exc))
    return {"states": states, "errors": errors}


def replay(capture: Path, identities: list[dict] | None = None) -> dict:
    identities = keys.build() if identities is None else identities
    report = json.loads((capture / "replay-report.json").read_text(encoding="utf-8"))
    records = {}
    for record in report["records"]:
        name = record["name"].lower()
        wad = name if name.endswith(".wad") else name + ".wad"
        need(wad not in records, "duplicate staged WAD: " + wad)
        records[wad] = record
    states = []
    errors = []
    for row in identities:
        record = records.get(row["wad"])
        value = None
        reason = "wad_absent"
        if record is not None:
            relative = Path(record["payload_file"])
            need(not relative.is_absolute() and ".." not in relative.parts,
                 "unsafe payload path")
            payload = (capture / relative).read_bytes()
            got = inspect_payload(
                payload, record["cached_channel_a_lua_length"], [row])
            if got["errors"]:
                errors.append({"catalogue_id": row["catalogue_id"],
                               "errors": got["errors"]})
                reason = "decode_rejected"
            else:
                value = got["states"][row["catalogue_id"]]
                reason = "exact_state" if value is not None else "exact_key_absent"
        states.append({"catalogue_id": row["catalogue_id"], "wad": row["wad"],
                       "state": value, "classification":
                       "OPENED" if value == 4 else
                       "UNOPENED" if value in (1, 2, 3) else "UNKNOWN",
                       "reason": reason})
    return {
        "schema": 1,
        "result": "EXACT_STAGED_NORNIR_CHEST_STATES",
        "capture": str(capture),
        "identity_contract": keys.contract(identities),
        "opened_count": sum(r["classification"] == "OPENED" for r in states),
        "unopened_count": sum(r["classification"] == "UNOPENED" for r in states),
        "unknown_count": sum(r["classification"] == "UNKNOWN" for r in states),
        "states": states,
        "errors": errors,
        "game_or_save_writes": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = replay(args.capture.resolve())
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        destination = args.output.resolve()
        need(not destination.is_relative_to(args.capture.resolve()),
             "report cannot overwrite capture")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(raw, encoding="utf-8")
        print("NORNIR_STAGED_CHEST_STATE", destination)
    else:
        print(raw, end="")


if __name__ == "__main__":
    main()
