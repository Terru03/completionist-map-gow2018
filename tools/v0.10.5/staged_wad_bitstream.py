"""Bounded, offline Channel A candidate extraction. No process or save writes.

Input: exact LE u16 byte count plus that many MSB-first packed bytes.
Nested Lua buffers: MSB-first u16 byte count then bytes, at any bit offset.
Full enclosing WAD traversal remains unproved. Results stay CANDIDATE.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct

MAX_CHANNEL_BYTES = 0xFFFF
# Slot +5E14 to next count at +A614. Layout-derived policy, not native guard.
MAX_CARRIER_BYTES = 0x4800
MAX_STREAM_MARKERS = 512
MAX_TOKEN_COUNT = 4096
MAX_PARSE_STEPS = 16384
MAX_PARSE_PATHS = 64
MAX_CANDIDATES = 128


class DecodeLimit(ValueError):
    pass


def _decoder():
    path = Path(__file__).with_name("decode-active-raven-subobject-state.py")
    spec = importlib.util.spec_from_file_location("_staged_wad_canonical", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Header fields are u16. Larger decoded blobs cannot match header extent.
    module.MAX_DECOMPRESSED = 2 * 0xFFFF
    module.INPUT_LIMIT = MAX_CARRIER_BYTES
    return module


def _aligned_bytes(payload: bytes, alignment: int) -> bytes:
    if alignment == 0:
        return payload
    return bytes(((payload[i] << alignment) & 255) |
                 (payload[i + 1] >> (8 - alignment))
                 for i in range(len(payload) - 1))


def _token_paths(module, data: bytes, start: int, count: int):
    """Keep native widths. Bound work; never truncate parse alternatives."""
    if count > MAX_TOKEN_COUNT:
        raise DecodeLimit("token_count_cap")
    paths, stack, steps = [], [(start, 0, [])], 0
    while stack:
        steps += 1
        if steps > MAX_PARSE_STEPS:
            raise DecodeLimit("token_parse_work_cap")
        pos, index, tokens = stack.pop()
        if index == count:
            paths.append((pos, tokens))
            if len(paths) > MAX_PARSE_PATHS:
                raise DecodeLimit("token_parse_path_cap")
            continue
        if pos >= len(data):
            continue
        tag = data[pos]
        widths = ((module.KNOWN_WIDTHS[tag],) if tag in module.KNOWN_WIDTHS
                  else module.UNKNOWN_TAG4_WIDTHS if tag == 4 else ())
        for width in reversed(widths):
            end = pos + width
            if end <= len(data):
                raw = data[pos:end]
                token = {"tag": tag, "payload": int.from_bytes(raw[1:], "little"),
                         "width": width, "raw_hex": raw.hex()}
                stack.append((end, index + 1, tokens + [token]))
    return paths


def _decode_paths(module, raw, decoded, consumed, registry_hash, object_map):
    header = struct.unpack_from("<8H", raw)
    section0_count, _, pair_count, row_count, record_count, _, _, _ = header
    if max(row_count, record_count) > MAX_TOKEN_COUNT:
        raise DecodeLimit("graph_count_cap")
    token_start = 16 + consumed + 2 * section0_count
    paths = _token_paths(module, raw, token_start, pair_count * 2)
    original = module.parse_token_paths
    results = []
    try:
        for path in paths:
            # One path per call avoids canonical graph de-dup hiding ambiguity.
            module.parse_token_paths = lambda *args, path=path: [path]
            parsed = module.validate_and_decode_candidate(
                raw, 0, decoded, consumed, registry_hash, object_map)
            for item in parsed:
                if item["carrier_length"] != len(raw):
                    continue
                item["token_parse"] = path[1]
                # Canonical decoder picks first state key. Reject duplicate keys.
                duplicate_state_key = False
                for row in item["rows"]:
                    fields = []
                    for pair in range(row["first_pair"], row["first_pair"] + row["pair_count"]):
                        key = path[1][2 * pair]
                        if key["tag"] == 2:
                            fields.append(item["strings"][key["payload"]])
                    if fields.count("ravenKilled") > 1 or fields.count("__subobjs") > 1:
                        duplicate_state_key = True
                item["duplicate_state_key"] = duplicate_state_key
                results.append(item)
    finally:
        module.parse_token_paths = original
    return results


def extract_channel_a(envelope: bytes, registry_hash: int,
                      object_map: dict[int, str],
                      expected_lua_length: int | None = None) -> dict:
    """Return candidates, rejects, and tri-state Raven map. Never production truth.

    bit_offset counts from packed payload start; envelope_bit_offset adds 16.
    Any ambiguity or cap hit clears aggregate states to None. Missing stays None.
    expected_lua_length cross-checks record +60; it does not prove field position.
    """
    report = {
        "schema": 1, "classification": "CANDIDATE", "production_ready": False,
        "enclosing_field_traversal_validated": False,
        "candidates": [], "rejected": [], "ambiguity_reasons": [],
        "candidate_count": 0, "stream_marker_count": 0, "unambiguous": False,
        "expected_lua_length": expected_lua_length,
        "cached_lua_length_is_offset_proof": False,
        "raven_states": {rid: None for rid in sorted(set(object_map.values()))},
        "limits": {"channel_bytes": MAX_CHANNEL_BYTES,
                   "nested_carrier_bytes": MAX_CARRIER_BYTES,
                   "nested_carrier_limit_basis": "layout-derived policy; not explicit native guard",
                   "stream_markers": MAX_STREAM_MARKERS,
                   "token_count": MAX_TOKEN_COUNT, "parse_steps": MAX_PARSE_STEPS,
                   "parse_paths": MAX_PARSE_PATHS, "candidates": MAX_CANDIDATES},
    }
    if len(envelope) < 2:
        report["rejected"].append({"reason": "outer_length_missing"})
        return report
    length = int.from_bytes(envelope[:2], "little")
    report["outer_declared_bytes"] = length
    report["outer_actual_bytes"] = len(envelope) - 2
    if length != len(envelope) - 2:
        report["rejected"].append({"reason": "outer_length_mismatch"})
        return report
    module, payload, marker_count = _decoder(), envelope[2:], 0
    try:
        for alignment in range(8):
            aligned = _aligned_bytes(payload, alignment)
            marker_count += aligned.count(b"\x78")
            if marker_count > MAX_STREAM_MARKERS:
                raise DecodeLimit("stream_marker_cap")
            for at, consumed, decoded in module.scan_streams(aligned):
                start = at - 16
                if start < 2:
                    continue
                bit_offset = alignment + start * 8
                rejection = {"bit_offset": bit_offset}
                header = struct.unpack_from("<8H", aligned, start)
                if header[7] != consumed or header[1] + header[5] != len(decoded):
                    continue
                nested_length = int.from_bytes(aligned[start - 2:start], "big")
                if expected_lua_length is not None and nested_length != expected_lua_length:
                    report["rejected"].append(dict(rejection, reason="cached_lua_length_mismatch"))
                    continue
                if nested_length < 18 or nested_length > MAX_CARRIER_BYTES:
                    report["rejected"].append(dict(rejection, reason="nested_length_out_of_bounds"))
                    continue
                if start + nested_length > len(aligned):
                    report["rejected"].append(dict(rejection, reason="nested_buffer_truncated"))
                    continue
                raw = aligned[start:start + nested_length]
                parses = _decode_paths(module, raw, decoded, consumed, registry_hash, object_map)
                if not parses:
                    report["rejected"].append(dict(rejection, reason="no_exact_carrier_graph"))
                    continue
                if len(parses) != 1:
                    report["ambiguity_reasons"].append({"reason": "multiple_graph_parses",
                                                        "bit_offset": bit_offset, "parse_count": len(parses)})
                for parsed in parses:
                    if parsed["duplicate_state_key"]:
                        report["ambiguity_reasons"].append(dict(rejection, reason="duplicate_state_key"))
                    parsed.pop("token_parse")
                    report["candidates"].append({
                        "classification": "CANDIDATE", "bit_offset": bit_offset,
                        "envelope_bit_offset": bit_offset + 16,
                        "length_bit_offset": bit_offset - 16,
                        "alignment": alignment, "length": nested_length,
                        "raven_entries": parsed["raven_entries"], "carrier": parsed,
                    })
                    if len(report["candidates"]) > MAX_CANDIDATES:
                        raise DecodeLimit("candidate_count_cap")
    except DecodeLimit as exc:
        report["ambiguity_reasons"].append({"reason": str(exc)})
    states = {}
    for candidate in report["candidates"]:
        for entry in candidate["raven_entries"]:
            rid, state = entry["catalogue_id"], entry["ravenKilled"]
            if rid in states and states[rid] is not state:
                report["ambiguity_reasons"].append({"reason": "conflicting_raven_states",
                                                    "catalogue_id": rid})
            states[rid] = state
    report["candidate_count"] = len(report["candidates"])
    report["stream_marker_count"] = marker_count
    report["unambiguous"] = not report["ambiguity_reasons"]
    if report["unambiguous"]:
        report["raven_states"].update(states)
    return report
