"""Build a registration-only WAD_R_UI GOPool candidate for goCompletionistRavenHUD.

This is the narrow follow-up to the live A/B proof:

* CompletionistRaven + stock Dock artwork renders and uses native routing.
* The same custom r_ui.wad is stable in that control.
* goCompletionistRavenHUD is physically present in that WAD.
* Its folded-name hash is absent from the live WAD_R_UI.GOPool.

The builder therefore changes only wad_r_ui.dcb, adding one GOPool row for
0x45E5C7943749F81C with capacity 1. Existing rows, the MemoryPools/Lua tail,
and all non-data DCB chunks must remain byte-identical apart from the required
16-byte shift. No game file is written by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
EXPECTED_DCB = "b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b"
EXPECTED_DCB_BYTES = 4864
EXPECTED_DATA_BYTES = 0x10C0
EXPECTED_GOP_COUNT = 256
GOP_BASE = 0x90
ROW_BYTES = 16
EXPECTED_GOP_END = 0x1090

HUD_NAME = "goCompletionistRavenHUD"
HUD_HASH = 0x45E5C7943749F81C
MAP_RAVEN_HASH = 0x584F31DC8BD6E738
DOCK_HASH = 0x82F0296748C7393D

# These are the two relative-pointer deltas produced by the already-proven
# 255 -> 256 map-Raven GOPool insertion. Adding one row moves both targets by
# exactly 16 bytes.
EXPECTED_PTR_10 = 0x1080
EXPECTED_PTR_20 = 0x1090
CANDIDATE_PTR_10 = 0x1090
CANDIDATE_PTR_20 = 0x10A0


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def parse_chunks(raw: bytes) -> list[dict]:
    chunks: list[dict] = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short DCB header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(flags == 0x10, f"unexpected DCB flags at {off:#x}: {flags:#x}")
        check(padded <= len(raw), f"short DCB chunk at {off:#x}")
        chunks.append({
            "kind": kind,
            "flags": flags,
            "header": off,
            "start": start,
            "end": end,
            "padded_end": padded,
            "size": size,
        })
        off = padded
    check(off == len(raw), "DCB chunk walk did not end at EOF")
    return chunks


def one_chunk(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    check(len(rows) == 1, f"expected one DCB chunk {kind}, found {len(rows)}")
    return rows[0]


def pool_rows(data: bytes) -> tuple[int, list[dict], int]:
    count = struct.unpack_from("<I", data, 8)[0]
    end = GOP_BASE + count * ROW_BYTES
    check(end <= len(data), "GOPool exceeds WAD_R_UI data chunk")
    rows = []
    for index in range(count):
        off = GOP_BASE + index * ROW_BYTES
        uid, capacity = struct.unpack_from("<QH", data, off)
        rows.append({
            "index": index,
            "uid": uid,
            "uid_hex": f"{uid:016X}",
            "capacity": capacity,
            "raw": bytes(data[off:off + ROW_BYTES]),
        })
    return count, rows, end


def rows_for(rows: list[dict], uid: int) -> list[dict]:
    return [row for row in rows if row["uid"] == uid]


def chunk_bytes_by_kind(raw: bytes, chunks: list[dict], *, exclude: int) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    for chunk in chunks:
        if chunk["kind"] == exclude:
            continue
        check(chunk["kind"] not in out, f"duplicate non-data chunk kind {chunk['kind']}")
        out[chunk["kind"]] = raw[chunk["header"]:chunk["padded_end"]]
    return out


def build_candidate(source: bytes) -> tuple[bytes, dict]:
    check(len(source) == EXPECTED_DCB_BYTES, f"unexpected source DCB size: {len(source)}")
    check(sha256(source) == EXPECTED_DCB, "wad_r_ui.dcb is not the pinned live control")

    chunks = parse_chunks(source)
    check([c["kind"] for c in chunks] == [11, 12, 13, 14, 15],
          f"unexpected DCB chunk order: {[c['kind'] for c in chunks]}")
    data_chunk = one_chunk(chunks, 12)
    data = bytearray(source[data_chunk["start"]:data_chunk["end"]])
    check(len(data) == EXPECTED_DATA_BYTES, f"unexpected WAD_R_UI data size: {len(data):#x}")

    count, rows, pool_end = pool_rows(data)
    check(count == EXPECTED_GOP_COUNT, f"unexpected GOPool count: {count}")
    check(pool_end == EXPECTED_GOP_END, f"unexpected GOPool end: {pool_end:#x}")
    check(folded_name_hash(HUD_NAME) == HUD_HASH, "HUD folded-name hash constant mismatch")

    hud_rows = rows_for(rows, HUD_HASH)
    map_rows = rows_for(rows, MAP_RAVEN_HASH)
    dock_rows = rows_for(rows, DOCK_HASH)
    check(len(hud_rows) == 0, "HUD GOPool row is already present; refusing duplicate registration")
    check(len(map_rows) == 1 and map_rows[0]["capacity"] == 1,
          "working map Raven GOPool control is not exactly one capacity-1 row")
    check(len(dock_rows) == 1 and dock_rows[0]["capacity"] == 2,
          "stock Dock GOPool control is not exactly one capacity-2 row")
    check(map_rows[0]["index"] == 255, f"map Raven GOPool row moved from index 255: {map_rows[0]['index']}")

    ptr10 = struct.unpack_from("<q", data, 0x10)[0]
    ptr20 = struct.unpack_from("<q", data, 0x20)[0]
    check(ptr10 == EXPECTED_PTR_10, f"unexpected +0x10 relative pointer delta: {ptr10:#x}")
    check(ptr20 == EXPECTED_PTR_20, f"unexpected +0x20 relative pointer delta: {ptr20:#x}")

    hud_row = struct.pack("<QH6x", HUD_HASH, 1)
    candidate_data = bytearray(data[:pool_end] + hud_row + data[pool_end:])
    struct.pack_into("<I", candidate_data, 8, count + 1)
    struct.pack_into("<q", candidate_data, 0x10, CANDIDATE_PTR_10)
    struct.pack_into("<q", candidate_data, 0x20, CANDIDATE_PTR_20)

    header = bytearray(source[data_chunk["header"]:data_chunk["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = (
        source[:data_chunk["header"]]
        + bytes(header)
        + bytes(candidate_data)
        + source[data_chunk["end"]:]
    )

    reparsed = parse_chunks(candidate)
    check([c["kind"] for c in reparsed] == [11, 12, 13, 14, 15], "candidate DCB chunk order changed")
    candidate_chunk = one_chunk(reparsed, 12)
    round_data = candidate[candidate_chunk["start"]:candidate_chunk["end"]]
    check(len(round_data) == EXPECTED_DATA_BYTES + ROW_BYTES, "candidate data chunk did not grow by 16 bytes")

    new_count, new_rows, new_pool_end = pool_rows(round_data)
    check(new_count == 257, f"candidate GOPool count is not 257: {new_count}")
    check(new_pool_end == 0x10A0, f"candidate GOPool end is wrong: {new_pool_end:#x}")
    check(round_data[GOP_BASE:pool_end] == data[GOP_BASE:pool_end], "one or more existing GOPool rows changed")
    check(round_data[pool_end:pool_end + ROW_BYTES] == hud_row, "HUD GOPool row not inserted at index 256")
    check(round_data[new_pool_end:] == data[pool_end:], "MemoryPools/Lua tail changed instead of shifting by 16 bytes")
    check(struct.unpack_from("<q", round_data, 0x10)[0] == CANDIDATE_PTR_10, "candidate +0x10 pointer is wrong")
    check(struct.unpack_from("<q", round_data, 0x20)[0] == CANDIDATE_PTR_20, "candidate +0x20 pointer is wrong")

    new_hud = rows_for(new_rows, HUD_HASH)
    new_map = rows_for(new_rows, MAP_RAVEN_HASH)
    new_dock = rows_for(new_rows, DOCK_HASH)
    check(len(new_hud) == 1 and new_hud[0]["index"] == 256 and new_hud[0]["capacity"] == 1,
          "candidate HUD row is not unique index-256 capacity-1")
    check(len(new_map) == 1 and new_map[0]["raw"] == map_rows[0]["raw"], "map Raven GOPool row changed")
    check(len(new_dock) == 1 and new_dock[0]["raw"] == dock_rows[0]["raw"], "stock Dock GOPool row changed")

    before_non_data = chunk_bytes_by_kind(source, chunks, exclude=12)
    after_non_data = chunk_bytes_by_kind(candidate, reparsed, exclude=12)
    check(before_non_data == after_non_data, "a non-data DCB chunk changed")

    return candidate, {
        "source_gopool_count": count,
        "candidate_gopool_count": new_count,
        "source_gopool_end": f"0x{pool_end:X}",
        "candidate_gopool_end": f"0x{new_pool_end:X}",
        "hud_hash": f"{HUD_HASH:016X}",
        "hud_row_hex": hud_row.hex(),
        "hud_index": new_hud[0]["index"],
        "hud_capacity": new_hud[0]["capacity"],
        "map_raven_row_preserved": True,
        "stock_dock_row_preserved": True,
        "all_existing_gopool_rows_byte_identical": True,
        "memorypools_lua_tail_byte_identical_after_shift": True,
        "non_data_chunks_byte_identical": True,
        "pointer_delta_10_before": f"0x{ptr10:X}",
        "pointer_delta_10_after": f"0x{CANDIDATE_PTR_10:X}",
        "pointer_delta_20_before": f"0x{ptr20:X}",
        "pointer_delta_20_after": f"0x{CANDIDATE_PTR_20:X}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    work = args.work_dir.resolve()
    out = args.output.resolve()
    check(not work.is_relative_to(game), "work directory must stay outside the game tree")
    check(not out.is_relative_to(game), "report must stay outside the game tree")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    check(wad_path.is_file(), f"missing {wad_path}")
    check(dcb_path.is_file(), f"missing {dcb_path}")

    wad_raw = wad_path.read_bytes()
    source = dcb_path.read_bytes()
    check(sha256(wad_raw) == EXPECTED_WAD, "r_ui.wad is not the successful custom-WAD stock-art control")
    check(sha256(source) == EXPECTED_DCB, "wad_r_ui.dcb is not the audited unregistered control")

    candidate, validation = build_candidate(source)
    work.mkdir(parents=True, exist_ok=True)
    candidate_path = work / "wad_r_ui.dcb"
    candidate_path.write_bytes(candidate)

    check(wad_path.read_bytes() == wad_raw, "r_ui.wad changed during offline build")
    check(dcb_path.read_bytes() == source, "live wad_r_ui.dcb changed during offline build")

    report = {
        "schema": 1,
        "result": "OFFLINE_RAVEN_COMPASS_HUD_GOPOOL_REGISTRATION_BUILT",
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": {
            "r_ui.wad": {"path": str(wad_path), "sha256": EXPECTED_WAD, "bytes": len(wad_raw)},
            "wad_r_ui.dcb": {"path": str(dcb_path), "sha256": EXPECTED_DCB, "bytes": len(source)},
        },
        "candidate": {
            "path": str(candidate_path),
            "sha256": sha256(candidate),
            "bytes": len(candidate),
        },
        "validation": validation,
        "scope": {
            "only_candidate_file_changed": "wad_r_ui.dcb",
            "r_ui_wad_changed": False,
            "wad_r_perm_changed": False,
            "mapmaster_changed": False,
            "mapcoords_changed": False,
            "compassgraph_changed": False,
            "saves_or_progression_changed": False,
        },
        "next_gate": "Install only this DCB reversibly, rerun the live-resolution audit, and do not launch the game until the HUD row is proved registered.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("OFFLINE_RAVEN_COMPASS_HUD_GOPOOL_REGISTRATION_BUILT")
    print(f"  source DCB SHA256:    {EXPECTED_DCB}")
    print(f"  candidate DCB SHA256: {sha256(candidate)}")
    print(f"  GOPool rows:          {EXPECTED_GOP_COUNT} -> 257")
    print(f"  HUD row:              {HUD_HASH:016X}, capacity 1, index 256")
    print(f"  candidate:            {candidate_path}")
    print(f"  report:               {out}")
    print("  game files written:   false")


if __name__ == "__main__":
    main()
