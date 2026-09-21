#!/usr/bin/env python3
"""Decode authoritative Odin's Raven SubObject state from an active GoW 2018 save.

This is a read-only decoder for the custom-userdata carrier semantics proven from
native restore code plus the frozen alive/dead Raven carrier pair.

Proven carrier graph used here:
- tag 0: boolean, encoded as tag byte + u8
- tag 1: 32-bit scalar, encoded as tag byte + u32 (semantic subtype not needed)
- tag 2: string reference, encoded as tag byte + u16 section0 index
- tag 3: table reference, encoded as tag byte + u16 1-based table/row id
- tag 5: custom userdata record reference, encoded as tag byte + u16 record index
- six-byte row = u16 first_pair, u16 pair_count, u16 auxiliary
- descriptor +0x50 is an array of 16-byte key/value pairs, each half one tagged value.

For Raven persistence the decoded graph is:
    root["__subobjs"][<Raven GameObject>] = { ravenKilled = true }

No save/progression/game files are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENTITIES = REPO / "catalogue" / "odins-ravens-save-identities.json"
AUTHORITY_TOOL = HERE / "probe-active-save-raven-ring-authority.py"
FROZEN = REPO / "archive" / "field-logs" / "source-scans" / "raven-native-carrier-replay-v2-20260916-134106"
HEADER_BYTES = 208
MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
KNOWN_WIDTHS = {0: 2, 1: 5, 2: 3, 3: 3, 5: 3}
UNKNOWN_TAG4_WIDTHS = (2, 3, 5)
RAVEN_FIELD = "ravenKilled"
SUBOBJS_FIELD = "__subobjs"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and (((cmf << 8) | flg) % 31) == 0


def decompress_stream(data: bytes, offset: int):
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset:min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj(15)
        decoded = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(decoded) > MAX_DECOMPRESSED or not obj.eof or not decoded:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return decoded, consumed
    except zlib.error:
        return None


def scan_streams(slot: bytes):
    out = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        got = decompress_stream(slot, at)
        if got is not None:
            decoded, consumed = got
            out.append((at, consumed, decoded))
    return out


def parse_token_paths(data: bytes, start: int, token_count: int, max_results: int = 64):
    """Return exact token parses using native-proven widths.

    Iterative rather than recursive because historical checkpoint carriers can
    contain thousands of serialized key/value tokens. Tag 4 was not present in
    the frozen Raven oracle, so all three structural widths are considered only
    when tag 4 is encountered; downstream graph/record validation disambiguates.
    """
    results = []
    # Stack item: (byte_position, token_index, parsed_tokens)
    stack = [(start, 0, [])]
    while stack and len(results) < max_results:
        pos, index, tokens = stack.pop()
        if index == token_count:
            results.append((pos, tokens))
            continue
        if pos >= len(data):
            continue
        tag = data[pos]
        if tag > 5:
            continue
        if tag in KNOWN_WIDTHS:
            widths = (KNOWN_WIDTHS[tag],)
        elif tag == 4:
            widths = UNKNOWN_TAG4_WIDTHS
        else:
            continue
        # Reverse push so the smallest width is explored first, matching the
        # previous recursive traversal order.
        for width in reversed(widths):
            end = pos + width
            if end > len(data):
                continue
            raw = data[pos:end]
            payload = int.from_bytes(raw[1:], "little")
            stack.append((end, index + 1, tokens + [{
                "tag": tag,
                "payload": payload,
                "width": width,
                "raw_hex": raw.hex(),
            }]))
    return results

def parse_gameobject_payload(payload: bytes):
    """Parse the native 0x5491A0 GameObject save-reference forms."""
    if not payload:
        return None
    flags = payload[0]
    present = bool(flags & 0x01)
    has_upper = bool(flags & 0x04)
    expected_length = 1 + (16 if present else 0) + (4 if present and has_upper else 0)
    if len(payload) != expected_length or not present:
        return None
    return {
        "flags": flags,
        "aux": (flags >> 1) & 1,
        "has_upper": has_upper,
        "upper_u32": int.from_bytes(payload[17:21], "little") if has_upper else 0,
        "registry_hash": int.from_bytes(payload[1:9], "little"),
        "object_hash": int.from_bytes(payload[9:17], "little"),
    }


def extract_string(prefix: bytes, offset: int):
    if offset < 0 or offset >= len(prefix):
        return None
    end = prefix.find(b"\0", offset)
    if end < 0:
        return None
    try:
        return prefix[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return None


def validate_and_decode_candidate(slot: bytes, header_start: int, decoded: bytes, consumed: int,
                                  registry_hash: int | None, object_map: dict):
    if header_start < 0 or header_start + 16 > len(slot):
        return []
    try:
        section0_count, blob_offset, pair_count, row_count, record_count, blob_length, scalar_c, comp_len = struct.unpack_from(
            "<8H", slot, header_start
        )
    except struct.error:
        return []
    if comp_len != consumed or blob_offset + blob_length != len(decoded):
        return []
    compressed_start = header_start + 16
    after_compressed = compressed_start + consumed
    section0_end = after_compressed + 2 * section0_count
    if section0_end > len(slot):
        return []
    section0 = list(struct.unpack_from(f"<{section0_count}H", slot, after_compressed)) if section0_count else []
    prefix = decoded[:blob_offset]
    blob = decoded[blob_offset:blob_offset + blob_length]

    strings = []
    for off in section0:
        s = extract_string(prefix, off)
        if s is None:
            return []
        strings.append(s)

    results = []
    token_count = pair_count * 2
    for metadata_end, tokens in parse_token_paths(slot, section0_end, token_count):
        fixed_end = metadata_end + record_count + 2 * record_count + 6 * row_count
        if fixed_end > len(slot):
            continue
        sizes = slot[metadata_end:metadata_end + record_count]
        offsets_start = metadata_end + record_count
        offsets_raw = slot[offsets_start:offsets_start + 2 * record_count]
        rows_raw = slot[offsets_start + 2 * record_count:fixed_end]

        offsets = [struct.unpack_from("<H", offsets_raw, i * 2)[0] for i in range(record_count)]
        records = []
        records_ok = True
        for idx, (size, off) in enumerate(zip(sizes, offsets)):
            if size < 8 or off + size > len(blob):
                records_ok = False
                break
            rec = blob[off:off + size]
            records.append({
                "index": idx,
                "class_key": struct.unpack_from("<Q", rec, 0)[0],
                "payload": rec[8:],
                "raw": rec,
            })
        if not records_ok:
            continue

        rows = []
        rows_ok = True
        for i in range(row_count):
            first, count, aux = struct.unpack_from("<HHH", rows_raw, i * 6)
            if first + count > pair_count:
                rows_ok = False
                break
            rows.append({"first_pair": first, "pair_count": count, "aux": aux})
        if not rows_ok:
            continue

        pairs = []
        graph_ok = True
        for i in range(pair_count):
            key = tokens[2 * i]
            value = tokens[2 * i + 1]
            for tok in (key, value):
                tag, payload = tok["tag"], tok["payload"]
                if tag == 0 and payload not in (0, 1):
                    graph_ok = False
                elif tag == 2 and payload >= len(strings):
                    graph_ok = False
                elif tag == 3 and not (1 <= payload <= row_count):
                    graph_ok = False
                elif tag == 5 and payload >= len(records):
                    graph_ok = False
            pairs.append((key, value))
        if not graph_ok:
            continue

        def string_value(tok):
            return strings[tok["payload"]] if tok["tag"] == 2 else None

        def table_index(tok):
            return tok["payload"] - 1 if tok["tag"] == 3 else None

        def row_pairs(index: int):
            row = rows[index]
            return pairs[row["first_pair"]:row["first_pair"] + row["pair_count"]]

        def catalogue_for(parsed):
            if registry_hash is None:
                return object_map.get((parsed["registry_hash"], parsed["object_hash"]))
            if parsed["registry_hash"] != registry_hash:
                return None
            return object_map.get(parsed["object_hash"])

        killed = set()
        explicit_false = set()
        raven_entries = []
        raven_state_entries_all = []
        raven_state_parent_keys = []
        subobj_tables = set()

        for row_index in range(row_count):
            for key, value in row_pairs(row_index):
                if string_value(key) == SUBOBJS_FIELD:
                    target = table_index(value)
                    if target is not None:
                        subobj_tables.add(target)

        for sub_index in sorted(subobj_tables):
            for key, value in row_pairs(sub_index):
                state_index = table_index(value)
                state = None
                if state_index is not None:
                    for skey, sval in row_pairs(state_index):
                        if string_value(skey) == RAVEN_FIELD and sval["tag"] == 0:
                            state = bool(sval["payload"])
                            break

                # Preserve the exact parent key for every explicit ravenKilled
                # row before applying any GameObject/registry assumptions.
                if state is not None:
                    parent = {
                        "subobj_table_row": sub_index,
                        "state_row": state_index,
                        "ravenKilled": state,
                        "key_tag": key["tag"],
                        "key_payload": key["payload"],
                        "key_width": key["width"],
                        "key_raw_hex": key["raw_hex"],
                    }
                    if key["tag"] == 5 and key["payload"] < len(records):
                        raw_record = records[key["payload"]]
                        parent.update({
                            "record_index": key["payload"],
                            "record_class_key_hex": f"0x{raw_record['class_key']:016X}",
                            "record_payload_hex": raw_record["payload"].hex(),
                        })
                        any_go = parse_gameobject_payload(raw_record["payload"])
                        if any_go is not None:
                            parent["parsed_gameobject"] = {
                                "flags": any_go["flags"],
                                "aux": any_go["aux"],
                                "has_upper": any_go["has_upper"],
                                "upper_u32": any_go["upper_u32"],
                                "registry_hash_hex": f"0x{any_go['registry_hash']:016X}",
                                "object_hash_hex": f"0x{any_go['object_hash']:016X}",
                                "catalogue_id": catalogue_for(any_go),
                            }
                    raven_state_parent_keys.append(parent)

                if key["tag"] != 5:
                    continue
                record = records[key["payload"]]
                parsed = parse_gameobject_payload(record["payload"])
                if parsed is None:
                    continue
                catalogue_id = catalogue_for(parsed)
                if state is not None:
                    raven_state_entries_all.append({
                        "catalogue_id": catalogue_id,
                        "record_index": key["payload"],
                        "record_payload_hex": record["payload"].hex(),
                        "flags": parsed["flags"],
                        "aux": parsed["aux"],
                        "has_upper": parsed["has_upper"],
                        "upper_u32": parsed["upper_u32"],
                        "registry_hash_hex": f"0x{parsed['registry_hash']:016X}",
                        "object_hash_hex": f"0x{parsed['object_hash']:016X}",
                        "state_row": state_index,
                        "ravenKilled": state,
                    })
                if catalogue_id is None:
                    continue
                if state is True:
                    killed.add(catalogue_id)
                elif state is False:
                    explicit_false.add(catalogue_id)
                raven_entries.append({
                    "catalogue_id": catalogue_id,
                    "record_index": key["payload"],
                    "object_hash_hex": f"0x{parsed['object_hash']:016X}",
                    "state_row": state_index,
                    "ravenKilled": state,
                })

        results.append({
            "carrier_offset": header_start,
            "carrier_length": fixed_end - header_start,
            "carrier_end": fixed_end,
            "header": {
                "section0_word_count": section0_count,
                "record_blob_offset": blob_offset,
                "metadata_pair_count": pair_count,
                "row_count": row_count,
                "record_count": record_count,
                "record_blob_length": blob_length,
                "scalar_c": scalar_c,
                "compressed_length": comp_len,
            },
            "strings": strings,
            "tag_widths_observed": {
                str(tag): sorted({t["width"] for t in tokens if t["tag"] == tag})
                for tag in sorted({t["tag"] for t in tokens})
            },
            "rows": rows,
            "subobj_table_rows": sorted(subobj_tables),
            "raven_entries": raven_entries,
            "raven_state_entries_all": raven_state_entries_all,
            "raven_state_parent_keys": raven_state_parent_keys,
            "unmatched_raven_state_entries": [x for x in raven_state_entries_all if x["catalogue_id"] is None],
            "killed_ravens": sorted(killed),
            "explicit_false_ravens": sorted(explicit_false),
        })
    # Deduplicate alternative tag-4 parses that produce the same exact boundary/graph.
    unique = {}
    for item in results:
        key = (
            item["carrier_end"],
            tuple(item["killed_ravens"]),
            tuple(item["explicit_false_ravens"]),
            tuple((x["catalogue_id"], x["state_row"], x["ravenKilled"]) for x in item["raven_entries"]),
            tuple((x["object_hash_hex"], x["state_row"], x["ravenKilled"]) for x in item["raven_state_entries_all"]),
            tuple((x["key_tag"], x["key_payload"], x["state_row"], x["ravenKilled"]) for x in item["raven_state_parent_keys"]),
        )
        unique[key] = item
    return list(unique.values())


def decode_carriers(slot: bytes, registry_hash: int | None, object_map: dict):
    carriers = []
    seen = set()
    stream_count = 0
    header_candidates = 0
    for at, consumed, decoded in scan_streams(slot):
        stream_count += 1
        if at < 16:
            continue
        header_start = at - 16
        try:
            header = struct.unpack_from("<8H", slot, header_start)
        except struct.error:
            continue
        if header[7] != consumed or header[1] + header[5] != len(decoded):
            continue
        header_candidates += 1
        parsed = validate_and_decode_candidate(slot, header_start, decoded, consumed, registry_hash, object_map)
        for item in parsed:
            key = (item["carrier_offset"], item["carrier_end"])
            if key in seen:
                continue
            seen.add(key)
            carriers.append(item)
    killed = sorted({rid for c in carriers for rid in c["killed_ravens"]})
    explicit_false = sorted({rid for c in carriers for rid in c["explicit_false_ravens"]})
    entries = [entry for c in carriers for entry in c["raven_entries"]]
    return {
        "stream_count": stream_count,
        "carrier_header_candidates": header_candidates,
        "decoded_carrier_count": len(carriers),
        "carriers_with_subobjs": sum(bool(c["subobj_table_rows"]) for c in carriers),
        "raven_entry_count": len(entries),
        "killed_raven_count": len(killed),
        "killed_raven_catalogue_ids": killed,
        "explicit_false_raven_catalogue_ids": explicit_false,
        "raven_entries": entries,
        "carriers": carriers,
    }


def decode_one_carrier(raw: bytes, registry_hash: int | None, object_map: dict):
    if len(raw) < 18:
        raise RuntimeError("frozen carrier too short")
    header = struct.unpack_from("<8H", raw, 0)
    consumed = header[7]
    decoded = zlib.decompress(raw[16:16 + consumed])
    rows = validate_and_decode_candidate(raw, 0, decoded, consumed, registry_hash, object_map)
    if len(rows) != 1:
        raise RuntimeError(f"expected one unambiguous frozen carrier parse, got {len(rows)}")
    return rows[0]


def selftest(registry_hash: int, object_map: dict[int, str]):
    alive_path = FROZEN / "alive-carrier.bin"
    dead_path = FROZEN / "dead-carrier.bin"
    if not alive_path.is_file() or not dead_path.is_file():
        raise RuntimeError("frozen Raven carrier regression fixtures are missing")
    alive = decode_one_carrier(alive_path.read_bytes(), registry_hash, object_map)
    dead = decode_one_carrier(dead_path.read_bytes(), registry_hash, object_map)
    target = "raven_642d0d164af0a5d4076e77933c549a5d"
    if target in alive["killed_ravens"]:
        raise RuntimeError("selftest failure: alive carrier decoded target as killed")
    if dead["killed_ravens"] != [target]:
        raise RuntimeError(f"selftest failure: dead carrier killed set {dead['killed_ravens']}")
    raven_rows = [x for x in dead["raven_entries"] if x["catalogue_id"] == target]
    if len(raven_rows) != 1 or raven_rows[0]["ravenKilled"] is not True:
        raise RuntimeError("selftest failure: dead Raven did not resolve ravenKilled=true")
    return {
        "passed": True,
        "alive_killed": alive["killed_ravens"],
        "dead_killed": dead["killed_ravens"],
        "dead_target_state": raven_rows[0]["ravenKilled"],
        "dead_subobj_rows": dead["subobj_table_rows"],
    }


def resolve_save(args):
    if args.save is not None:
        save = args.save.expanduser().resolve()
    else:
        root = args.save_root.expanduser().resolve()
        saves = sorted(p.resolve() for p in root.rglob("game.sav") if p.is_file())
        if len(saves) != 1:
            raise RuntimeError(f"expected exactly one active game.sav under {root}, found {len(saves)}")
        save = saves[0]
    if not save.is_file():
        raise RuntimeError(f"save not found: {save}")
    return save


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", type=Path)
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--identities", type=Path, default=IDENTITIES)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    identities = json.loads(args.identities.read_text(encoding="utf-8"))
    if identities.get("identity_count") != 53:
        raise RuntimeError("Raven save identity catalogue is incomplete")
    registry_hash = int(identities["registry_hash_hex"], 16)
    object_map = {
        int(row["object_hash_hex"], 16): row["catalogue_id"]
        for row in identities["identities"]
    }
    if len(object_map) != 53:
        raise RuntimeError("Raven object-hash map is not one-to-one")

    regression = selftest(registry_hash, object_map)

    authority = load_module("active_raven_authority_base", AUTHORITY_TOOL)
    save = resolve_save(args)
    before = sha256_file(save)
    blob = save.read_bytes()
    lay = authority.layout(blob)
    prefix = lay["global_prefix"]
    stride = lay["slot_stride"]

    slot_headers = []
    occupied = []
    stream_counts = {}
    slot_bytes = {}
    for idx in range(lay["slot_count"]):
        start = prefix + idx * stride
        slot = blob[start:start + stride]
        slot_bytes[idx] = slot
        slot_headers.append(slot[:HEADER_BYTES])
        count = len(scan_streams(slot))
        stream_counts[idx] = count
        if count:
            occupied.append(idx)

    header_analysis = authority.header_fields(slot_headers, occupied)
    authoritative = header_analysis["consensus_latest_slot"]
    if authoritative is None:
        raise RuntimeError("unable to determine authoritative/latest save-ring slot")

    # Decode every occupied ring entry. The newest aligned slot is not necessarily
    # self-contained for all SoftSave objects; the ring may act as a journal.
    all_slot_decodes = {}
    for idx in occupied:
        all_slot_decodes[idx] = decode_carriers(slot_bytes[idx], registry_hash, object_map)

    decoded = all_slot_decodes[authoritative]

    # Pick the strongest timestamp field that covers the most occupied slots.
    slot_timestamps = {}
    if header_analysis.get("timestamp_fields"):
        best_time = header_analysis["timestamp_fields"][0]
        slot_timestamps = {
            int(k): v for k, v in best_time.get("decoded_slots", {}).items()
        }

    # Build a semantic Raven journal. Absence never clears prior state; only an
    # explicit decoded Raven entry can update the latest-known state.
    journal = []
    latest_by_raven = {}
    for idx in occupied:
        stamp = slot_timestamps.get(idx)
        for entry in all_slot_decodes[idx]["raven_entries"]:
            row = dict(entry)
            row["slot_index"] = idx
            row["timestamp_utc"] = stamp
            journal.append(row)

    def journal_order(row):
        # ISO-8601 timestamps sort lexically; unknown timestamps remain oldest.
        return (row.get("timestamp_utc") or "", row["slot_index"])

    for row in sorted(journal, key=journal_order):
        latest_by_raven[row["catalogue_id"]] = row

    journal_killed = sorted(
        rid for rid, row in latest_by_raven.items()
        if row.get("ravenKilled") is True
    )
    journal_explicit_alive = sorted(
        rid for rid, row in latest_by_raven.items()
        if row.get("ravenKilled") is False
    )

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav SHA-256 changed during read-only decode")

    report = {
        "schema": 1,
        "analysis": "active_raven_subobject_graph_decode",
        "save_path": str(save),
        "save_sha256": before,
        "layout": lay,
        "occupied_slots": occupied,
        "stream_counts_by_slot": {str(k): v for k, v in stream_counts.items()},
        "slot_header_analysis": header_analysis,
        "authoritative_slot": authoritative,
        "regression_selftest": regression,
        "all_slot_decodes": {str(k): v for k, v in all_slot_decodes.items()},
        "raven_journal": {
            "timestamp_field": header_analysis["timestamp_fields"][0] if header_analysis.get("timestamp_fields") else None,
            "entry_count": len(journal),
            "entries": sorted(journal, key=journal_order),
            "latest_by_raven": latest_by_raven,
            "latest_killed_raven_count": len(journal_killed),
            "latest_killed_raven_catalogue_ids": journal_killed,
            "latest_explicit_alive_raven_catalogue_ids": journal_explicit_alive,
        },
        "native_semantics": {
            "tag_0": "boolean",
            "tag_1": "u32_scalar",
            "tag_2": "string_reference",
            "tag_3": "table_reference_1_based",
            "tag_5": "custom_userdata_record_reference",
            "row_word_0": "first_pair_index",
            "row_word_1": "pair_count",
            "row_word_2": "auxiliary_semantics_not_required_for_raven_decode",
            "raven_graph": "root.__subobjs[GameObject] -> state table -> ravenKilled=true",
        },
        "authoritative_decode": decoded,
        "identity_catalogue_sha256": sha256_file(args.identities),
        "safety": {
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - authoritative Raven SubObject graph decode",
        f"save_sha256={before}",
        f"authoritative_slot={authoritative}",
        f"consensus_reason={header_analysis['consensus_reason']}",
        "selftest=frozen_alive_dead_passed",
        "",
        "PROVEN GRAPH",
        'root["__subobjs"][<GameObject>] -> state table -> ravenKilled=true',
        "",
        "AUTHORITATIVE DECODE",
        f"streams={decoded['stream_count']}",
        f"carrier_header_candidates={decoded['carrier_header_candidates']}",
        f"decoded_carriers={decoded['decoded_carrier_count']}",
        f"carriers_with_subobjs={decoded['carriers_with_subobjs']}",
        f"raven_entries={decoded['raven_entry_count']}",
        f"killed_ravens={decoded['killed_raven_count']}",
        "",
        "RING JOURNAL DECODE",
        f"journal_entries={len(journal)}",
        f"latest_known_ravens={len(latest_by_raven)}",
        f"latest_killed_ravens={len(journal_killed)}",
    ]
    for rid in journal_killed:
        lines.append("  JOURNAL_KILLED " + rid)
    for rid in journal_explicit_alive:
        lines.append("  JOURNAL_ALIVE_EXPLICIT " + rid)
    lines.extend(["", "AUTHORITATIVE-SLOT RAVENS"])
    for rid in decoded["killed_raven_catalogue_ids"]:
        lines.append("  KILLED " + rid)
    for rid in decoded["explicit_false_raven_catalogue_ids"]:
        lines.append("  ALIVE_EXPLICIT " + rid)
    lines.extend([
        "",
        "RAVEN ENTRIES",
    ])
    for row in decoded["raven_entries"]:
        lines.append(
            f"  {row['catalogue_id']} object={row['object_hash_hex']} "
            f"stateRow={row['state_row']} ravenKilled={row['ravenKilled']}"
        )
    lines.extend([
        "",
        "SAFETY active_save_opened_read_only=true source_hash_unchanged=true "
        "save_written=false progression_written=false game_process_opened=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "ACTIVE_RAVEN_SUBOBJECT_DECODE_COMPLETE "
        f"slot={authoritative} carriers={decoded['decoded_carrier_count']} "
        f"subobjCarriers={decoded['carriers_with_subobjs']} "
        f"ravenEntries={decoded['raven_entry_count']} killed={decoded['killed_raven_count']} "
        f"journalEntries={len(journal)} journalKnown={len(latest_by_raven)} "
        f"journalKilled={len(journal_killed)}"
    )
    print("frozen_alive_dead_selftest=true source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
