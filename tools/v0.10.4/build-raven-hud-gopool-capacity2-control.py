#!/usr/bin/env python3
"""Build an offline WAD_R_UI GOPool capacity-2 A/B for goCompletionistRavenHUD.

The dedicated Raven in-world carrier resolves when it points at stock Dock art, but
renders nothing when it points at goCompletionistRavenHUD. The custom Raven HUD root
is currently registered with GOPool capacity 1 while stock Dock uses capacity 2.
Because the Raven HUD root is already instantiated on the compass, an in-world copy
may require a second simultaneous pool instance.

This builder changes only the 16-bit capacity field of the existing Raven HUD GOPool
row from 1 to 2. It never writes the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SOURCE = "40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36"
EXPECTED_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
HUD_HASH = 0x45E5C7943749F81C
DOCK_HASH = 0x82F0296748C7393D
MAP_RAVEN_HASH = 0x584F31DC8BD6E738
GOP_BASE = 0x90
ROW_SIZE = 16
EXPECTED_COUNT = 257
EXPECTED_HUD_INDEX = 256


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def align16(v: int) -> int:
    return (v + 15) & ~15


def parse_chunks(raw: bytes) -> list[dict]:
    out = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short DCB header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(flags == 0x10 and padded <= len(raw), f"invalid DCB chunk at {off:#x}")
        out.append({"kind": kind, "header": off, "start": start, "end": end, "padded": padded})
        off = padded
    check(off == len(raw), "DCB walk did not end at EOF")
    return out


def one(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    check(len(rows) == 1, f"expected one chunk {kind}, found {len(rows)}")
    return rows[0]


def rows(data: bytes) -> tuple[int, list[dict]]:
    count = struct.unpack_from("<I", data, 8)[0]
    check(GOP_BASE + count * ROW_SIZE <= len(data), "GOPool exceeds data chunk")
    out = []
    for i in range(count):
        off = GOP_BASE + i * ROW_SIZE
        uid, capacity = struct.unpack_from("<QH", data, off)
        out.append({"index": i, "offset": off, "uid": uid, "capacity": capacity,
                    "raw": bytes(data[off:off + ROW_SIZE])})
    return count, out


def by_uid(items: list[dict], uid: int) -> list[dict]:
    return [r for r in items if r["uid"] == uid]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    dcb = game / "exec/dc/pc_le/wad_r_ui.dcb"
    wad = game / "exec/wad/pc_le/r_ui.wad"
    check(dcb.is_file() and wad.is_file(), "required live r_ui files are missing")
    source = dcb.read_bytes()
    wad_raw = wad.read_bytes()
    check(sha256(source) == EXPECTED_SOURCE, f"unexpected registered wad_r_ui.dcb: {sha256(source)}")
    check(sha256(wad_raw) == EXPECTED_WAD, f"unexpected custom r_ui.wad: {sha256(wad_raw)}")

    chunks = parse_chunks(source)
    check([c["kind"] for c in chunks] == [11, 12, 13, 14, 15], "unexpected DCB chunk order")
    dc = one(chunks, 12)
    data = bytearray(source[dc["start"]:dc["end"]])
    count, pool = rows(data)
    check(count == EXPECTED_COUNT, f"expected {EXPECTED_COUNT} GOPool rows, found {count}")

    hud = by_uid(pool, HUD_HASH)
    dock = by_uid(pool, DOCK_HASH)
    map_raven = by_uid(pool, MAP_RAVEN_HASH)
    check(len(hud) == 1 and hud[0]["index"] == EXPECTED_HUD_INDEX and hud[0]["capacity"] == 1,
          "Raven HUD row is not the expected unique index-256 capacity-1 row")
    check(len(dock) == 1 and dock[0]["capacity"] == 2, "stock Dock control is not capacity 2")
    check(len(map_raven) == 1 and map_raven[0]["capacity"] == 1, "map Raven control changed")

    capacity_off = hud[0]["offset"] + 8
    before_data = bytes(data)
    struct.pack_into("<H", data, capacity_off, 2)

    header = bytearray(source[dc["header"]:dc["start"]])
    candidate = source[:dc["header"]] + bytes(header) + bytes(data) + source[dc["end"]:]
    check(len(candidate) == len(source), "capacity-only candidate size changed")

    diffs = [i for i, (a, b) in enumerate(zip(source, candidate)) if a != b]
    expected_file_off = dc["start"] + capacity_off
    check(diffs == [expected_file_off], f"candidate changed bytes outside capacity low byte: {diffs[:16]}")

    reparsed = parse_chunks(candidate)
    rdc = one(reparsed, 12)
    rdata = candidate[rdc["start"]:rdc["end"]]
    rcount, rpool = rows(rdata)
    rhud = by_uid(rpool, HUD_HASH)
    check(rcount == count, "GOPool count changed")
    check(len(rhud) == 1 and rhud[0]["index"] == EXPECTED_HUD_INDEX and rhud[0]["capacity"] == 2,
          "candidate Raven HUD row is not capacity 2")

    for before, after in zip(pool, rpool):
        if before["uid"] == HUD_HASH:
            check(before["raw"][:8] == after["raw"][:8] and before["raw"][10:] == after["raw"][10:],
                  "Raven HUD row changed outside capacity field")
        else:
            check(before["raw"] == after["raw"], f"unrelated GOPool row changed at index {before['index']}")

    for c0, c1 in zip(chunks, reparsed):
        if c0["kind"] == 12:
            continue
        check(source[c0["header"]:c0["padded"]] == candidate[c1["header"]:c1["padded"]],
              f"non-data chunk {c0['kind']} changed")

    out = args.output.resolve()
    report = args.report.resolve()
    check(not out.is_relative_to(game) and not report.is_relative_to(game), "outputs must stay outside game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(candidate)

    result = {
        "schema": 1,
        "result": "OFFLINE_RAVEN_HUD_GOPOOL_CAPACITY2_CONTROL_BUILT",
        "source_sha256": EXPECTED_SOURCE,
        "candidate_sha256": sha256(candidate),
        "r_ui_wad_sha256": EXPECTED_WAD,
        "hud_hash": f"{HUD_HASH:016X}",
        "hud_index": EXPECTED_HUD_INDEX,
        "capacity_before": 1,
        "capacity_after": 2,
        "stock_dock_capacity": dock[0]["capacity"],
        "gopool_count_unchanged": True,
        "only_changed_file_byte_offset": f"0x{expected_file_off:X}",
        "only_capacity_low_byte_changed": True,
        "all_other_gopool_rows_byte_identical": True,
        "non_data_chunks_byte_identical": True,
        "file_size_unchanged": True,
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "candidate": str(out),
    }
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    check(dcb.read_bytes() == source and wad.read_bytes() == wad_raw, "live game files changed during offline build")
    print("OFFLINE_RAVEN_HUD_GOPOOL_CAPACITY2_CONTROL_BUILT")
    print(f"  wad_r_ui.dcb: {EXPECTED_SOURCE} -> {result['candidate_sha256']}")
    print(f"  HUD row:      {HUD_HASH:016X} index {EXPECTED_HUD_INDEX} capacity 1 -> 2")
    print("  all other GOPool rows byte-identical: true")
    print("  non-data chunks byte-identical: true")
    print("  game files written: false")
    print(f"  candidate: {out}")
    print(f"  report:    {report}")


if __name__ == "__main__":
    main()
