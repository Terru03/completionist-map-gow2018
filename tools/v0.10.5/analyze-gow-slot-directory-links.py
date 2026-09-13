"""Read-only structural trace of slot-internal zlib directory/index links in frozen GoW saves.

This tool is intentionally forensic-only.  It reads exactly two recognized Desktop
backup copies, derives the 20 aligned fixed slots, finds the slots that changed,
indexes every valid zlib stream, and asks whether the early changed binary region
contains direct little-endian references to later Raven-related compressed streams.
It also reports periodic changed-run structure (notably fixed-stride table-like
patterns) without dumping arbitrary save contents.  The active save directory is
never opened or written.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

MAX_DECOMPRESSED = 8 * 1024 * 1024
INPUT_LIMIT = 2 * 1024 * 1024
EARLY_LIMIT = 256 * 1024
RAVEN_FIELD_ID = bytes.fromhex("b0b227342530c24ea0a803505c2eb7ad")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate_backup_dirs(desktop: Path) -> list[Path]:
    patterns = (
        "GodOfWar-SaveBackup-*",
        "GodOfWar-BeforeRestore-*",
        "GoW-TestSave-*",
        "GodOfWar-TestSave-*",
    )
    found: dict[str, Path] = {}
    for pattern in patterns:
        for p in desktop.glob(pattern):
            if p.is_dir():
                found[str(p.resolve()).lower()] = p.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())


def locate_game_save(backup: Path) -> Path | None:
    files = [p for p in backup.rglob("game.sav") if p.is_file()]
    return files[0] if len(files) == 1 else None


def layout(blob: bytes) -> dict:
    if len(blob) < 32:
        raise RuntimeError("Save too small")
    words = struct.unpack_from("<8I", blob, 0)
    stride = words[5]
    declared = words[6]
    header_size = words[4]
    if declared != len(blob):
        raise RuntimeError(f"Declared size mismatch header={declared} actual={len(blob)}")
    if stride <= 0 or stride >= len(blob):
        raise RuntimeError(f"Implausible stride {stride}")
    prefix = len(blob) % stride
    count = (len(blob) - prefix) // stride
    if count <= 0 or prefix < header_size:
        raise RuntimeError(f"Implausible layout prefix={prefix} count={count}")
    return {"prefix": prefix, "stride": stride, "slot_count": count, "header_size": header_size}


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) + flg) % 31 == 0


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


def printable_strings(raw: bytes, minimum: int = 4) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, raw):
        s = m.group(0).decode("ascii", "ignore")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def scan_streams(slot: bytes) -> list[dict]:
    streams: list[dict] = []
    cursor = 0
    while True:
        at = slot.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(slot, at):
            continue
        got = decompress_stream(slot, at)
        if got is None:
            continue
        raw, consumed = got
        strings = printable_strings(raw)[:30]
        streams.append({
            "offset": at,
            "compressed_bytes": consumed,
            "decompressed_bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "raven": (b"ravenKilled" in raw or RAVEN_FIELD_ID in raw),
            "strings": strings,
        })
    return streams


def changed_positions(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise RuntimeError("Slot size mismatch")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def runs_from_positions(pos: list[int]) -> list[tuple[int, int]]:
    if not pos:
        return []
    out: list[tuple[int, int]] = []
    start = prev = pos[0]
    for p in pos[1:]:
        if p == prev + 1:
            prev = p
        else:
            out.append((start, prev - start + 1))
            start = prev = p
    out.append((start, prev - start + 1))
    return out


def find_all(data: bytes, needle: bytes, cap: int = 128) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < cap:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def small_context(data: bytes, offset: int, radius: int = 24) -> dict:
    start = max(0, offset - radius)
    end = min(len(data), offset + 4 + radius)
    return {"start": start, "end": end, "hex": data[start:end].hex()}


def periodic_run_report(runs: list[tuple[int, int]]) -> dict:
    starts = [s for s, n in runs if s < EARLY_LIMIT and n <= 8]
    deltas = collections.Counter(b - a for a, b in zip(starts, starts[1:]) if 0 < b - a <= 512)
    residues96 = collections.Counter(s % 96 for s in starts)
    sequences = []
    by_residue: dict[int, list[int]] = collections.defaultdict(list)
    for s in starts:
        by_residue[s % 96].append(s)
    for residue, vals in by_residue.items():
        vals = sorted(vals)
        current = [vals[0]] if vals else []
        for v in vals[1:]:
            if v - current[-1] == 96:
                current.append(v)
            else:
                if len(current) >= 4:
                    sequences.append({"residue": residue, "first": current[0], "last": current[-1], "count": len(current)})
                current = [v]
        if len(current) >= 4:
            sequences.append({"residue": residue, "first": current[0], "last": current[-1], "count": len(current)})
    sequences.sort(key=lambda x: (-x["count"], x["first"]))
    return {
        "small_run_count": len(starts),
        "top_start_deltas": [{"delta": d, "count": c} for d, c in deltas.most_common(20)],
        "top_mod96_residues": [{"residue": r, "count": c} for r, c in residues96.most_common(20)],
        "stride96_sequences": sequences[:50],
    }


def stream_pointer_refs(slot: bytes, streams: list[dict], changed_set: set[int]) -> list[dict]:
    refs: list[dict] = []
    early = slot[:EARLY_LIMIT]
    interesting = [s for s in streams if s["raven"]]
    # Also include the first few non-Raven streams in the changed early region so we
    # can compare directory behaviour rather than assuming Raven-specific encoding.
    interesting += [s for s in streams if s["offset"] < EARLY_LIMIT and not s["raven"]][:20]
    seen = set()
    for s in interesting:
        key = (s["offset"], s["sha256"])
        if key in seen:
            continue
        seen.add(key)
        value = s["offset"]
        needles = {
            "offset_u32_le": struct.pack("<I", value),
            "offset_u32_be": struct.pack(">I", value),
        }
        hits = []
        for kind, needle in needles.items():
            for at in find_all(early, needle, 64):
                # Ignore the zlib bytes themselves if a coincidental integer appears there.
                overlaps_stream = s["offset"] <= at < s["offset"] + s["compressed_bytes"]
                hits.append({
                    "kind": kind,
                    "at": at,
                    "overlaps_target_stream": overlaps_stream,
                    "changed_here": any((at + k) in changed_set for k in range(4)),
                    "context": small_context(early, at),
                })
        if hits:
            refs.append({
                "stream_offset": s["offset"],
                "compressed_bytes": s["compressed_bytes"],
                "decompressed_bytes": s["decompressed_bytes"],
                "sha256": s["sha256"],
                "raven": s["raven"],
                "strings": s["strings"][:12],
                "refs": hits,
            })
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    candidates: list[tuple[Path, Path]] = []
    for backup in candidate_backup_dirs(desktop):
        save = locate_game_save(backup)
        if save is not None:
            candidates.append((backup, save))
    if len(candidates) != 2:
        raise RuntimeError(f"Expected exactly two recognized frozen game.sav backups, found {len(candidates)}")

    before = {str(save): sha256_file(save) for _, save in candidates}
    blobs = [save.read_bytes() for _, save in candidates]
    layouts = [layout(x) for x in blobs]
    if layouts[0] != layouts[1]:
        raise RuntimeError(f"Backups disagree on layout: {layouts}")
    lay = layouts[0]

    slots: list[list[bytes]] = [[], []]
    for source, blob in enumerate(blobs):
        for i in range(lay["slot_count"]):
            start = lay["prefix"] + i * lay["stride"]
            slots[source].append(blob[start : start + lay["stride"]])

    changed = []
    slot_reports = {}
    for i in range(lay["slot_count"]):
        pos = changed_positions(slots[0][i], slots[1][i])
        if not pos:
            continue
        changed.append(i)
        runs = runs_from_positions(pos)
        changed_set = set(pos)
        per_source = {}
        for source, name in ((0, "A"), (1, "B")):
            streams = scan_streams(slots[source][i])
            per_source[name] = {
                "stream_count": len(streams),
                "raven_streams": [s for s in streams if s["raven"]],
                "pointer_refs": stream_pointer_refs(slots[source][i], streams, changed_set),
            }
        slot_reports[str(i)] = {
            "changed_bytes": len(pos),
            "first_changed": pos[0],
            "last_changed": pos[-1],
            "changed_run_count": len(runs),
            "periodicity": periodic_run_report(runs),
            "A": per_source["A"],
            "B": per_source["B"],
        }

    after = {str(save): sha256_file(save) for _, save in candidates}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only slot directory trace")

    report = {
        "schema": 1,
        "scan_kind": "read_only_slot_zlib_directory_link_trace",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "layout": lay,
        "changed_slots": changed,
        "slots": slot_reports,
        "files": [
            {"backup": backup.name, "path": str(save), "sha256": before[str(save)]}
            for backup, save in candidates
        ],
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "source_hashes_unchanged": True,
        },
    }

    lines = [
        "Completionist Map - GoW slot zlib-directory link trace",
        f"layout prefix={lay['prefix']} stride={lay['stride']} slots={lay['slot_count']}",
        f"changed slots={changed}",
        "",
    ]
    for i in changed:
        r = slot_reports[str(i)]
        lines.append(
            f"slot {i}: changed={r['changed_bytes']} first={r['first_changed']} last={r['last_changed']} runs={r['changed_run_count']}"
        )
        periodic = r["periodicity"]
        lines.append(
            "  top deltas=" + ", ".join(f"{x['delta']}x{x['count']}" for x in periodic["top_start_deltas"][:8])
        )
        lines.append(
            "  mod96=" + ", ".join(f"r{x['residue']}x{x['count']}" for x in periodic["top_mod96_residues"][:8])
        )
        for seq in periodic["stride96_sequences"][:8]:
            lines.append(
                f"  stride96 residue={seq['residue']} first={seq['first']} last={seq['last']} count={seq['count']}"
            )
        for name in ("A", "B"):
            s = r[name]
            raven_refs = [x for x in s["pointer_refs"] if x["raven"]]
            all_ref_hits = sum(len(x["refs"]) for x in s["pointer_refs"])
            raven_ref_hits = sum(len(x["refs"]) for x in raven_refs)
            lines.append(
                f"  {name}: zlib={s['stream_count']} ravenStreams={len(s['raven_streams'])} pointerStreams={len(s['pointer_refs'])} pointerHits={all_ref_hits} ravenPointerHits={raven_ref_hits}"
            )
            for rr in raven_refs[:12]:
                lines.append(
                    f"    RAVEN stream={rr['stream_offset']} bytes={rr['decompressed_bytes']} refs=" +
                    ",".join(f"{h['kind']}@{h['at']} changed={h['changed_here']}" for h in rr["refs"][:12])
                )
        lines.append("")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "GOW_SLOT_DIRECTORY_LINK_TRACE_PASSED "
        f"changedSlots={','.join(map(str, changed)) or 'none'}"
    )
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
