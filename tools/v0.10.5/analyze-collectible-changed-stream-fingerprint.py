"""Read-only semantic fingerprinting of changed zlib stream runs in frozen saves.

The save-oracle and schema-adjacency probes established that exact collectible
instance identities and literal checkpoint field IDs are not present in a form
we can safely use as an unloaded-state oracle.  This probe narrows the remaining
structural lead without exporting arbitrary save bytes: it sequence-aligns zlib
streams in the aligned save slots that differ between two frozen backups and
emits only hashes, offsets, sizes, known checkpoint field labels, and a tightly
filtered set of engine-style identifier tokens.

A token or changed stream is evidence for classification only.  It is never
interpreted as collectible completion truth.  Runtime generation stays closed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
TARGET_FIELDS = (
    "ravenKilled",
    "state",
    "mapSummaryComplete",
    "bRuneReadStarted",
    "wellRead",
    "destroyed",
    "keysUsed",
    "challengeComplete",
)
SAFE_TOKEN_KEYWORDS = (
    "RAVEN",
    "ODIN",
    "NORNIR",
    "LORE",
    "ARTEFACT",
    "ARTIFACT",
    "LEGENDARY",
    "CHEST",
    "RUNE",
    "PRECISION",
    "CHALLENGE",
    "DESTROY",
    "SUMMARY",
    "QUEST",
    "MAP",
    "ATREUS",
    "BOAT",
    "LEAD_THE_WAY",
    "CONTEXT",
    "BEHAVIOR",
)
KNOWN_CONTEXT_TOKENS = {
    "LEAD_THE_WAY_BEHAVIOR_CONTEXT_CONFIG",
    "BOAT_CONTEXT_CONFIG_NORMAL",
}
ASCII_ENGINE_TOKEN = re.compile(rb"[A-Z][A-Z0-9_]{5,119}")
UTF16_ENGINE_TOKEN = re.compile(rb"(?:[A-Z0-9_]\x00){6,120}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("Save too small for header")
    words = struct.unpack_from("<8I", blob, 0)
    header_size = words[4]
    stride = words[5]
    declared_size = words[6]
    if declared_size != len(blob):
        raise RuntimeError(
            f"Declared size mismatch header={declared_size} actual={len(blob)}"
        )
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"Implausible slot stride {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0 or prefix < header_size:
        raise RuntimeError(
            f"Implausible aligned layout prefix={prefix} slots={count}"
        )
    return {
        "prefix": prefix,
        "stride": stride,
        "slot_count": count,
        "header_size": header_size,
    }


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (
        (cmf & 0x0F) == 8
        and (cmf >> 4) <= 7
        and ((cmf << 8) + flg) % 31 == 0
    )


def decompress_stream(data: bytes, offset: int) -> tuple[bytes, int] | None:
    if not valid_zlib_header(data, offset):
        return None
    source = data[offset : min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(raw) > MAX_DECOMPRESSED or not obj.eof or not raw:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return raw, consumed
    except zlib.error:
        return None


def safe_tokens(raw: bytes) -> list[str]:
    """Return only engine-style identifiers matching a conservative allowlist."""
    found: set[str] = set()
    for match in ASCII_ENGINE_TOKEN.finditer(raw):
        token = match.group(0).decode("ascii", errors="ignore")
        if any(keyword in token for keyword in SAFE_TOKEN_KEYWORDS):
            found.add(token)
    for match in UTF16_ENGINE_TOKEN.finditer(raw):
        block = match.group(0)
        token = block[::2].decode("ascii", errors="ignore")
        if any(keyword in token for keyword in SAFE_TOKEN_KEYWORDS):
            found.add(token)
    return sorted(found)[:80]


def scan_slot(slot: bytes, slot_index: int) -> list[dict]:
    streams: list[dict] = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(slot, at):
            continue
        result = decompress_stream(slot, at)
        if result is None:
            continue
        raw, consumed = result
        fields = [
            name for name in TARGET_FIELDS if (name.encode("ascii") + b"\0") in raw
        ]
        streams.append(
            {
                "slot": slot_index,
                "index": len(streams),
                "relative_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "target_fields": fields,
                "safe_tokens": safe_tokens(raw),
            }
        )
    return streams


def compact_stream(stream: dict) -> dict:
    return {
        "index": stream["index"],
        "relative_offset": stream["relative_offset"],
        "compressed_bytes": stream["compressed_bytes"],
        "decompressed_bytes": stream["decompressed_bytes"],
        "sha256": stream["sha256"],
        "target_fields": stream["target_fields"],
        "safe_tokens": stream["safe_tokens"],
    }


def classify_tokens(tokens_a: set[str], tokens_b: set[str]) -> list[str]:
    hints: list[str] = []
    combined = tokens_a | tokens_b
    if combined & KNOWN_CONTEXT_TOKENS:
        hints.append("story_behavior_context_lead")
    if any("RAVEN" in t or "ODIN" in t for t in combined):
        hints.append("raven_related_identifier_lead")
    if any(
        keyword in token
        for token in combined
        for keyword in ("NORNIR", "LORE", "ARTEFACT", "ARTIFACT", "LEGENDARY", "CHEST")
    ):
        hints.append("other_collectible_identifier_lead")
    if not hints:
        hints.append("unclassified")
    return hints


def changed_runs(a_streams: list[dict], b_streams: list[dict], slot_index: int) -> list[dict]:
    matcher = SequenceMatcher(
        a=[s["sha256"] for s in a_streams],
        b=[s["sha256"] for s in b_streams],
        autojunk=False,
    )
    runs: list[dict] = []
    ordinal = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ordinal += 1
        aa = a_streams[i1:i2]
        bb = b_streams[j1:j2]
        tokens_a = {t for s in aa for t in s["safe_tokens"]}
        tokens_b = {t for s in bb for t in s["safe_tokens"]}
        runs.append(
            {
                "slot": slot_index,
                "run": ordinal,
                "opcode": tag,
                "a_index_range": [i1, i2],
                "b_index_range": [j1, j2],
                "a_stream_count": len(aa),
                "b_stream_count": len(bb),
                "a_streams": [compact_stream(s) for s in aa],
                "b_streams": [compact_stream(s) for s in bb],
                "tokens_only_a": sorted(tokens_a - tokens_b),
                "tokens_only_b": sorted(tokens_b - tokens_a),
                "tokens_shared": sorted(tokens_a & tokens_b),
                "classification_hints": classify_tokens(tokens_a, tokens_b),
                "contains_previous_adjacency_anchor": (
                    slot_index == 6
                    and ((i1 <= 49 < i2) or (j1 <= 49 < j2))
                ),
            }
        )
    return runs


def field_distance_summary(
    all_streams: dict[str, list[list[dict]]],
    changed_indices: dict[str, dict[int, set[int]]],
    changed_slots: list[int],
) -> dict:
    out: dict[str, dict] = {}
    for field in TARGET_FIELDS:
        entry = {
            "A_min_distance": None,
            "B_min_distance": None,
            "A_descriptor_count_in_changed_slots": 0,
            "B_descriptor_count_in_changed_slots": 0,
            "A_within_4": 0,
            "B_within_4": 0,
        }
        for label in ("A", "B"):
            distances: list[int] = []
            count = 0
            within = 0
            for slot in changed_slots:
                changed = changed_indices[label].get(slot, set())
                if not changed:
                    continue
                for stream in all_streams[label][slot]:
                    if field not in stream["target_fields"]:
                        continue
                    count += 1
                    distance = min(abs(stream["index"] - idx) for idx in changed)
                    distances.append(distance)
                    if distance <= 4:
                        within += 1
            entry[f"{label}_min_distance"] = min(distances) if distances else None
            entry[f"{label}_descriptor_count_in_changed_slots"] = count
            entry[f"{label}_within_4"] = within
        out[field] = entry
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-a", type=Path, required=True)
    ap.add_argument("--save-b", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    save_a = args.save_a.expanduser().resolve()
    save_b = args.save_b.expanduser().resolve()
    if save_a == save_b:
        raise RuntimeError("Frozen save A and B resolve to the same file")
    active_root = (Path.home() / "Saved Games" / "God of War").resolve()
    for path in (save_a, save_b):
        if not path.is_file():
            raise RuntimeError(f"Frozen save missing: {path}")
        try:
            path.relative_to(active_root)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing to inspect active save tree: {path}")

    before = {"A": sha256_file(save_a), "B": sha256_file(save_b)}
    blobs = {"A": save_a.read_bytes(), "B": save_b.read_bytes()}
    layouts = {label: layout(blob) for label, blob in blobs.items()}
    if layouts["A"] != layouts["B"]:
        raise RuntimeError(f"Frozen saves disagree on aligned layout: {layouts}")
    lay = layouts["A"]

    all_streams: dict[str, list[list[dict]]] = {"A": [], "B": []}
    slot_hashes: dict[str, list[str]] = {"A": [], "B": []}
    for label in ("A", "B"):
        blob = blobs[label]
        for slot_index in range(lay["slot_count"]):
            start = lay["prefix"] + slot_index * lay["stride"]
            slot = blob[start : start + lay["stride"]]
            slot_hashes[label].append(sha256_bytes(slot))
            all_streams[label].append(scan_slot(slot, slot_index))

    changed_slots = [
        i
        for i in range(lay["slot_count"])
        if slot_hashes["A"][i] != slot_hashes["B"][i]
    ]

    runs: list[dict] = []
    changed_indices: dict[str, dict[int, set[int]]] = {
        "A": defaultdict(set),
        "B": defaultdict(set),
    }
    for slot in changed_slots:
        slot_runs = changed_runs(all_streams["A"][slot], all_streams["B"][slot], slot)
        runs.extend(slot_runs)
        for run in slot_runs:
            i1, i2 = run["a_index_range"]
            j1, j2 = run["b_index_range"]
            changed_indices["A"][slot].update(range(i1, i2))
            changed_indices["B"][slot].update(range(j1, j2))

    field_distances = field_distance_summary(all_streams, changed_indices, changed_slots)
    context_token_hits = sorted(
        {
            token
            for run in runs
            for side in ("tokens_only_a", "tokens_only_b", "tokens_shared")
            for token in run[side]
            if token in KNOWN_CONTEXT_TOKENS
        }
    )
    raven_token_runs = sum(
        1
        for run in runs
        if "raven_related_identifier_lead" in run["classification_hints"]
    )
    anchor_runs = sum(1 for run in runs if run["contains_previous_adjacency_anchor"])

    after = {"A": sha256_file(save_a), "B": sha256_file(save_b)}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only fingerprint scan")

    status = "CHANGED_STREAMS_FINGERPRINTED" if runs else "NO_CHANGED_ZLIB_RUNS"
    report = {
        "schema": 1,
        "scan_kind": "collectible_changed_stream_fingerprint",
        "status": status,
        "runtime_generation_allowed": False,
        "interpretation_contract": {
            "semantic_token_is_completion_truth": False,
            "changed_stream_is_completion_truth": False,
            "requires_exact_instance_binding": True,
            "requires_semantically_validated_opposite_states": True,
            "unknown_rows_remain_hidden": True,
        },
        "layout": lay,
        "save_hashes": before,
        "source_hashes_unchanged": True,
        "validated_zlib_streams": {
            "A": sum(len(x) for x in all_streams["A"]),
            "B": sum(len(x) for x in all_streams["B"]),
        },
        "changed_slots": changed_slots,
        "changed_run_count": len(runs),
        "previous_adjacency_anchor_run_count": anchor_runs,
        "known_context_token_hits": context_token_hits,
        "raven_identifier_changed_run_count": raven_token_runs,
        "field_distance_to_changed_streams": field_distances,
        "changed_runs": runs,
        "safety": {
            "active_save_opened": False,
            "arbitrary_save_bytes_emitted": False,
            "only_allowlisted_engine_tokens_emitted": True,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Collectible changed-stream semantic fingerprint",
        "",
        f"Status: **{status}**",
        "",
        "This probe sequence-aligns zlib streams only inside changed aligned save slots. It emits hashes, sizes, ordinals, known checkpoint-field labels, and allowlisted engine-style identifiers. It does not emit arbitrary save bytes and does not infer completion state.",
        "",
        "## Summary",
        "",
        f"- Validated zlib streams: A={report['validated_zlib_streams']['A']}, B={report['validated_zlib_streams']['B']}",
        f"- Changed aligned slots: {', '.join(map(str, changed_slots)) if changed_slots else 'none'}",
        f"- Sequence-aligned changed runs: {len(runs)}",
        f"- Runs containing previous slot-6/index-49 adjacency anchor: {anchor_runs}",
        f"- Known story/context identifiers found: {', '.join(context_token_hits) if context_token_hits else 'none'}",
        f"- Changed runs with Raven/Odin identifiers: {raven_token_runs}",
        "- Runtime generation allowed: **false**",
        "",
        "## Changed runs",
        "",
    ]
    for run in runs:
        lines.append(
            f"### Slot {run['slot']} run {run['run']} — {run['opcode']} A{run['a_index_range']} B{run['b_index_range']}"
        )
        lines.append("")
        lines.append(
            f"- Previous adjacency anchor: {str(run['contains_previous_adjacency_anchor']).lower()}"
        )
        lines.append(
            f"- Classification hints: {', '.join(run['classification_hints'])}"
        )
        lines.append(
            f"- Tokens only A: {', '.join(run['tokens_only_a']) if run['tokens_only_a'] else 'none'}"
        )
        lines.append(
            f"- Tokens only B: {', '.join(run['tokens_only_b']) if run['tokens_only_b'] else 'none'}"
        )
        lines.append(
            f"- Shared safe tokens: {', '.join(run['tokens_shared']) if run['tokens_shared'] else 'none'}"
        )
        for label in ("a_streams", "b_streams"):
            side = "A" if label.startswith("a_") else "B"
            for stream in run[label]:
                fields = ",".join(stream["target_fields"]) or "none"
                lines.append(
                    f"- {side} stream {stream['index']}: off={stream['relative_offset']} compressed={stream['compressed_bytes']} decompressed={stream['decompressed_bytes']} sha256={stream['sha256']} fields={fields}"
                )
        lines.append("")

    lines.extend(["## Target-field proximity to changed streams", ""])
    for field in TARGET_FIELDS:
        entry = field_distances[field]
        lines.append(
            f"- `{field}`: A min={entry['A_min_distance']} within4={entry['A_within_4']}/{entry['A_descriptor_count_in_changed_slots']}; B min={entry['B_min_distance']} within4={entry['B_within_4']}/{entry['B_descriptor_count_in_changed_slots']}"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A changed-run token can help determine what a structural save difference belongs to, but it cannot bind a persisted value to an individual collectible. Exact instance binding plus known opposite semantic states for that same object are still required before any state could be used by production runtime code.",
            "",
            "Unknown collectible state remains hidden/fail-closed.",
            "",
        ]
    )
    args.output_md.write_text("\n".join(lines), encoding="utf-8")

    summary_lines = [
        "COLLECTIBLE_CHANGED_STREAM_FINGERPRINT_COMPLETED",
        f"status={status}",
        f"zlib_A={report['validated_zlib_streams']['A']}",
        f"zlib_B={report['validated_zlib_streams']['B']}",
        f"changed_slots={','.join(map(str, changed_slots))}",
        f"changed_runs={len(runs)}",
        f"adjacency_anchor_runs={anchor_runs}",
        f"known_context_tokens={','.join(context_token_hits)}",
        f"raven_identifier_changed_runs={raven_token_runs}",
        "runtime_generation_allowed=false",
        "active_save_opened=false",
        "arbitrary_save_bytes_emitted=false",
        "only_allowlisted_engine_tokens_emitted=true",
        "source_hashes_unchanged=true",
        "save_or_progression_written=false",
        "game_written=false",
    ]
    args.summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
