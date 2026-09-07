"""Inspect kind-35 DCB metadata after CompletionistRaven runtime rejection.

Read-only. The offline v0.10.4 class builder appended a type-0x11E export but
left kind-35 byte-identical. At runtime ShowMarker rejected CompletionistRaven as
an invalid type before queueing the native request. This tool checks whether the
extra kind-35 chunk correlates with export/type registration metadata and compares
it across the installed DCB set. It never writes game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_WAD_R_PERM = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"


def align16(value: int) -> int:
    return (value + 15) & ~15


def parse_chunks(raw: bytes) -> list[dict]:
    chunks = []
    off = 0
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"truncated IFF header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or end > len(raw):
            raise ValueError(f"invalid chunk at {off:#x}")
        chunks.append({"kind": kind, "header": off, "start": start, "end": end, "size": size})
        off = align16(end)
    if off != len(raw):
        raise ValueError("chunk walk did not end at EOF")
    return chunks


def one(chunks: list[dict], kind: int) -> dict | None:
    rows = [c for c in chunks if c["kind"] == kind]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError(f"multiple chunk kind {kind}")
    return rows[0]


def export_count(raw: bytes, chunks: list[dict]) -> int | None:
    c = one(chunks, 13)
    if c is None or c["size"] < 4:
        return None
    return struct.unpack_from("<I", raw, c["start"])[0]


def relocation_count(raw: bytes, chunks: list[dict]) -> int | None:
    c = one(chunks, 15)
    if c is None or c["size"] < 4:
        return None
    return struct.unpack_from("<I", raw, c["start"])[0]


def describe_kind35(payload: bytes, facts: dict[str, int | None]) -> dict:
    u32 = list(struct.unpack(f"<{len(payload) // 4}I", payload[: len(payload) // 4 * 4]))
    u64 = list(struct.unpack(f"<{len(payload) // 8}Q", payload[: len(payload) // 8 * 8]))
    matches = []
    for label, expected in facts.items():
        if expected is None:
            continue
        for i, value in enumerate(u32):
            if value == expected:
                matches.append({"width": 32, "index": i, "offset": i * 4, "label": label, "value": value})
        for i, value in enumerate(u64):
            if value == expected:
                matches.append({"width": 64, "index": i, "offset": i * 8, "label": label, "value": value})
    return {
        "bytes": len(payload),
        "hex": payload.hex().upper(),
        "u32": [f"0x{x:08X}" for x in u32],
        "u64": [f"0x{x:016X}" for x in u64],
        "matches_known_counts_or_sizes": matches,
    }


def inspect_file(path: Path) -> dict | None:
    raw = path.read_bytes()
    try:
        chunks = parse_chunks(raw)
    except Exception as exc:
        return None
    k35 = one(chunks, 35)
    if k35 is None:
        return None
    data = one(chunks, 12)
    exports = one(chunks, 13)
    relocs = one(chunks, 15)
    facts = {
        "file_bytes": len(raw),
        "data_chunk_bytes": data["size"] if data else None,
        "export_chunk_bytes": exports["size"] if exports else None,
        "export_count": export_count(raw, chunks),
        "relocation_chunk_bytes": relocs["size"] if relocs else None,
        "relocation_count": relocation_count(raw, chunks),
    }
    payload = raw[k35["start"]:k35["end"]]
    return {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "chunk_kinds": [c["kind"] for c in chunks],
        "facts": facts,
        "kind35": describe_kind35(payload, facts),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--repo-root", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    dc = game / "exec/dc/pc_le"
    perm = dc / "wad_r_perm.dcb"
    if not perm.is_file():
        raise FileNotFoundError(perm)
    if hashlib.sha256(perm.read_bytes()).hexdigest() != EXPECTED_WAD_R_PERM:
        raise ValueError("wad_r_perm.dcb is not the researched stock file; ensure the runtime proof was rolled back")

    rows = []
    for path in sorted(dc.glob("*.dcb")):
        row = inspect_file(path)
        if row is not None:
            rows.append(row)

    perm_row = next((r for r in rows if r["file"] == "wad_r_perm.dcb"), None)
    if perm_row is None:
        raise ValueError("wad_r_perm.dcb kind-35 chunk was not found")

    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["kind35"]["hex"], []).append(row["file"])

    report = {
        "result": "READ_ONLY_KIND35_REGISTRATION_INDEX_SCAN",
        "game_files_written": False,
        "runtime_failure_context": {
            "CompletionistRaven_export_was_present_offline": True,
            "ShowMarker_error": "trying to set invalid type 'CompletionistRaven' on compass marker '<unknown>'",
            "request_queued": False,
            "hypothesis": "A stock registration/index structure outside the ordinary export table may also need updating. kind-35 is being inspected because the failed offline builder intentionally left it unchanged.",
        },
        "wad_r_perm": perm_row,
        "files_with_kind35": len(rows),
        "kind35_payload_groups": [
            {"hex": key, "count": len(files), "files": files}
            for key, files in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "files": rows,
        "next_gate": "Use the cross-file pattern to determine whether kind-35 participates in type/tweak registration before attempting another custom CompassIconClass runtime build.",
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("output must stay outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {out}")
    print(f"DCBs with kind-35: {len(rows)}")
    print(f"wad_r_perm kind-35 bytes: {perm_row['kind35']['bytes']}")
    print(f"wad_r_perm kind-35 hex: {perm_row['kind35']['hex']}")
    print(f"Known-value matches: {len(perm_row['kind35']['matches_known_counts_or_sizes'])}")
    print(f"Distinct kind-35 payloads: {len(groups)}")
    print('No game files were modified.')


if __name__ == '__main__':
    main()
