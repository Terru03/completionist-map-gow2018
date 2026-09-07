"""Build a Raven-only logical map-icon clone offline.

This is the smallest structural isolation gate after the v0.10.4 map-icon-chain
trace. It creates a new r_ui.wad final-instance identity named
``gomapiconcompletionistraven`` that deliberately reuses the proven stock Dock
prototype. It also adds ``goMapIconCompletionistRaven`` to WAD_R_UI.GOPool.

The candidate therefore has its own UI resource identity while still rendering
stock Dock artwork. That is intentional: a later material/resource clone can be
attached only to this Raven identity without touching real boat docks.

No game files are written. Candidate binaries go to --work-dir and the JSON
report goes to --output.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
RAVEN_GO_HASH = 0x584F31DC8BD6E738
RAVEN_WAD_NAME = "gomapiconcompletionistraven"
RAVEN_DCB_NAME = "goMapIconCompletionistRaven"
# Opaque WAD resource id. Resource ids are linked by exact 16-byte equality;
# this deterministic id is reserved for the Completionist Raven final instance.
RAVEN_FINAL_ID = bytes.fromhex("3d8f7153809e6db191c2d5e354f1e88c")
STOCK_FINAL_NAME = "gomapicondock"
STOCK_PARENT_NAME = "goProtoNW633B8059"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def set_header_name(header: bytearray, name: str) -> None:
    encoded = name.encode("ascii")
    check(len(encoded) <= 55, f"WAD header name too long: {name}")
    header[24:80] = encoded + bytes(56 - len(encoded))


def parse_wad(raw: bytes) -> list[dict]:
    records: list[dict] = []
    stack: list[int] = []
    off = 0
    payload_index = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short WAD header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(padded <= len(raw), f"short WAD payload at {off:#x}")
        header = bytearray(raw[off:start])
        name = bytes(header[24:80]).split(b"\0", 1)[0].decode("ascii")
        record = {
            "kind": kind,
            "flags": flags,
            "header": header,
            "data": bytearray(raw[start:end]),
            "padding": bytes(raw[end:padded]),
            "name": name,
            "id": bytes(header[8:24]),
            "parent": stack[-1] if stack else None,
            "original_offset": off,
            "payload_index": payload_index if size else None,
        }
        records.append(record)
        here = len(records) - 1
        if size:
            payload_index += 1
        if kind == 2:
            stack.append(here)
        elif kind == 3:
            check(bool(stack), f"unmatched WAD group end at {off:#x}")
            stack.pop()
        off = padded
    check(not stack and off == len(raw), "WAD group walk did not end cleanly")
    return records


def record_bytes(record: dict) -> bytes:
    header = bytearray(record["header"])
    data = bytes(record["data"])
    struct.pack_into("<HHI", header, 0, record["kind"], record["flags"], len(data))
    header[8:24] = record["id"]
    set_header_name(header, record["name"])
    padding_len = align16(96 + len(data)) - (96 + len(data))
    padding = record["padding"]
    if len(padding) != padding_len:
        padding = bytes(padding_len)
    return bytes(header) + data + padding


def serialize_wad(records: list[dict]) -> bytes:
    return b"".join(record_bytes(r) for r in records)


def matching_group_end(records: list[dict], group_start_index: int) -> int:
    check(records[group_start_index]["kind"] == 2, "not a group start")
    depth = 0
    for i in range(group_start_index, len(records)):
        if records[i]["kind"] == 2:
            depth += 1
        elif records[i]["kind"] == 3:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("group has no matching end")


def one_record(records: list[dict], *, name: str, has_data: bool | None = None) -> dict:
    rows = [r for r in records if r["name"].lower() == name.lower() and
            (has_data is None or (len(r["data"]) > 0) == has_data)]
    check(len(rows) == 1, f"expected one {name!r}, found {len(rows)}")
    return rows[0]


def payload_records(records: list[dict]) -> list[dict]:
    return [r for r in records if len(r["data"]) > 0]


def read_type_table(root_data: bytes) -> list[dict]:
    count = struct.unpack_from("<I", root_data, 0x20)[0]
    rows = []
    base = 0
    for i in range(count):
        off = 0x28 + i * 12
        key, start, amount = struct.unpack_from("<III", root_data, off)
        check(start == base, f"non-contiguous WAD type table at row {i}")
        rows.append({"index": i, "offset": off, "key": key, "base": start, "count": amount})
        base += amount
    check(base == struct.unpack_from("<I", root_data, 0x1C)[0], "WAD type total mismatch")
    return rows


def build_wad(raw: bytes) -> tuple[bytes, dict]:
    records = parse_wad(raw)
    check(serialize_wad(records) == raw, "stock r_ui.wad byte round-trip failed")
    stock_physical = len(records)
    stock_payloads = len(payload_records(records))
    check((stock_physical, stock_payloads) == (53777, 20407), "unexpected stock WAD counts")

    check(not any(r["id"] == RAVEN_FINAL_ID for r in records), "reserved Raven final id collides")
    check(not any(r["name"].lower() == RAVEN_WAD_NAME for r in records), "Raven WAD name already exists")

    stock_final = one_record(records, name=STOCK_FINAL_NAME, has_data=True)
    stock_final_payload_index = stock_final["payload_index"]
    check(stock_final_payload_index == 13914, f"unexpected Dock final payload index {stock_final_payload_index}")
    check(len(stock_final["data"]) == 164 and stock_final["flags"] == 0x3D, "unexpected Dock final layout")
    stock_final_bytes = record_bytes(stock_final)

    stock_group_start_idx = stock_final["parent"]
    check(stock_group_start_idx is not None, "Dock final has no containing group")
    stock_group_end_idx = matching_group_end(records, stock_group_start_idx)
    check(stock_group_end_idx - stock_group_start_idx == 2, "Dock final group is not the expected 3-record group")
    check(records[stock_group_start_idx + 1] is stock_final, "Dock final is not sole payload in its group")

    parent_def = one_record(records, name=STOCK_PARENT_NAME, has_data=True)
    parent_group_start = records[parent_def["parent"]] if parent_def["parent"] is not None else None
    check(parent_group_start is not None and parent_group_start["kind"] == 2, "map-icon parent group missing")
    stock_parent_link = [r for r in records
                         if r["parent"] == parent_def["parent"] and
                         r["name"].lower() == STOCK_FINAL_NAME and len(r["data"]) == 0]
    check(len(stock_parent_link) == 1, f"expected one parent Dock link, found {len(stock_parent_link)}")
    stock_parent_link = stock_parent_link[0]

    # Patch only the two stock accounting payloads. Everything else remains
    # byte-identical. The new final payload is inserted inside the same type block
    # as the stock Dock final.
    heap = payload_records(records)[0]
    root = payload_records(records)[1]
    stock_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(stock_total == 0x419C == struct.unpack_from("<I", root["data"], 0x1C)[0], "unexpected WAD heap total")
    type_rows = read_type_table(root["data"])
    target_rows = [row for row in type_rows
                   if row["base"] <= stock_final_payload_index < row["base"] + row["count"]]
    check(len(target_rows) == 1, "could not identify Dock final WAD type block")
    target = target_rows[0]
    check(target["key"] == 0xD, f"Dock final type key changed: {target['key']:#x}")

    new_base = 0
    new_type_rows = []
    for row in type_rows:
        amount = row["count"] + (1 if row["index"] == target["index"] else 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, amount)
        new_type_rows.append({"key": row["key"], "base": new_base, "count": amount})
        new_base += amount
    check(new_base == stock_total + 1, "new WAD type total is wrong")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    # Clone exactly the self-contained final-instance group. It intentionally
    # keeps the stock Dock prototype id in the 164-byte instance payload.
    clone_group = [copy.deepcopy(records[i]) for i in range(stock_group_start_idx, stock_group_end_idx + 1)]
    clone_group[0]["name"] = RAVEN_WAD_NAME
    clone_group[0]["original_offset"] = None
    clone_final = clone_group[1]
    clone_final["name"] = RAVEN_WAD_NAME
    clone_final["id"] = RAVEN_FINAL_ID
    clone_final["original_offset"] = None
    clone_final["payload_index"] = None
    clone_group[2]["original_offset"] = None
    clone_group[2]["payload_index"] = None

    insertion = stock_group_end_idx + 1
    records[insertion:insertion] = clone_group

    # Add a sibling link under goProtoNW633B8059 so the new final instance lives
    # in the same authored map-icon resource scope as the stock icons.
    parent_start_now = records.index(parent_group_start)
    parent_end_now = matching_group_end(records, parent_start_now)
    raven_link = copy.deepcopy(stock_parent_link)
    raven_link["name"] = RAVEN_WAD_NAME
    raven_link["id"] = RAVEN_FINAL_ID
    raven_link["original_offset"] = None
    raven_link["payload_index"] = None
    records.insert(parent_end_now, raven_link)

    candidate = serialize_wad(records)
    reparsed = parse_wad(candidate)
    check(len(reparsed) == stock_physical + 4, "candidate physical-record delta is wrong")
    check(len(payload_records(reparsed)) == stock_payloads + 1, "candidate payload delta is wrong")
    raven_defs = [r for r in reparsed if r["name"].lower() == RAVEN_WAD_NAME and len(r["data"]) > 0]
    raven_links = [r for r in reparsed if r["name"].lower() == RAVEN_WAD_NAME and len(r["data"]) == 0]
    check(len(raven_defs) == 1 and len(raven_links) >= 1, "Raven definition/link did not reparse")
    check(raven_defs[0]["id"] == RAVEN_FINAL_ID, "Raven definition id changed")
    check(bytes(raven_defs[0]["data"]) == bytes(stock_final["data"]), "Raven final payload is not byte-identical to Dock final")

    reparsed_payloads = payload_records(reparsed)
    candidate_heap, candidate_root = reparsed_payloads[0], reparsed_payloads[1]
    check(struct.unpack_from("<I", candidate_heap["data"], 4)[0] == stock_total + 1, "candidate heap total wrong")
    candidate_type_rows = read_type_table(candidate_root["data"])
    candidate_target = next(row for row in candidate_type_rows if row["key"] == 0xD)
    check(candidate_target["count"] == target["count"] + 1, "type 0xD count did not increment")

    # Source stock definition is still untouched. The only stock records changed
    # are the two accounting payloads, by construction.
    check(record_bytes(stock_final) == stock_final_bytes, "stock Dock final was mutated")

    return candidate, {
        "stock_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "stock_physical_records": stock_physical,
        "candidate_physical_records": len(reparsed),
        "stock_payloads": stock_payloads,
        "candidate_payloads": len(reparsed_payloads),
        "stock_final_payload_index": stock_final_payload_index,
        "raven_final_payload_index": raven_defs[0]["payload_index"],
        "raven_wad_name": RAVEN_WAD_NAME,
        "raven_final_id": RAVEN_FINAL_ID.hex(),
        "shared_stock_dock_prototype_id": bytes(stock_final["data"])[0x0C:0x1C].hex(),
        "type_key": f"0x{target['key']:X}",
        "type_count_before": target["count"],
        "type_count_after": candidate_target["count"],
        "heap_total_before": stock_total,
        "heap_total_after": stock_total + 1,
        "full_group_reparse_passed": True,
        "stock_dock_final_unchanged": True,
    }


def parse_dcb_chunks(raw: bytes) -> list[dict]:
    chunks = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short DCB header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        check(flags == 0x10 and end <= len(raw), f"invalid DCB chunk at {off:#x}")
        chunks.append({"kind": kind, "header": off, "start": start, "end": end, "size": size})
        off = align16(end)
    check(off == len(raw), "DCB chunk walk did not end at EOF")
    return chunks


def one_chunk(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    check(len(rows) == 1, f"expected one DCB chunk {kind}, found {len(rows)}")
    return rows[0]


def build_dcb(raw: bytes) -> tuple[bytes, dict]:
    check(name_hash(RAVEN_DCB_NAME) == RAVEN_GO_HASH, "Raven GOPool hash constant mismatch")
    chunks = parse_dcb_chunks(raw)
    data_chunk = one_chunk(chunks, 12)
    data = bytearray(raw[data_chunk["start"]:data_chunk["end"]])
    check(len(data) == 4272, "unexpected WAD_R_UI data size")
    check(struct.unpack_from("<I", data, 8)[0] == 255, "unexpected stock GOPool count")
    check(data[0xF80:0xF90] == bytes.fromhex("3e17709448f3417f2800000000000000"), "stock Dock GOPool row changed")

    rows = [data[o:o + 16] for o in range(0x90, 0x1080, 16)]
    check(len(rows) == 255 and all(len(r) == 16 for r in rows), "stock GOPool range changed")
    check(all(struct.unpack_from("<Q", r, 0)[0] != RAVEN_GO_HASH for r in rows), "Raven GOPool row already exists")
    raven_row = struct.pack("<QH6x", RAVEN_GO_HASH, 1)

    candidate_data = bytearray(data[:0x1080] + raven_row + data[0x1080:])
    struct.pack_into("<I", candidate_data, 8, 256)
    # Relative-pointer deltas for fields at +0x10 and +0x20 after inserting one
    # 16-byte GOPool row before MemoryPools/Lua.
    struct.pack_into("<q", candidate_data, 0x10, 0x1080)
    struct.pack_into("<q", candidate_data, 0x20, 0x1090)

    header = bytearray(raw[data_chunk["header"]:data_chunk["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = raw[:data_chunk["header"]] + bytes(header) + bytes(candidate_data) + raw[data_chunk["end"]:]
    reparsed = parse_dcb_chunks(candidate)
    candidate_data_chunk = one_chunk(reparsed, 12)
    round_data = candidate[candidate_data_chunk["start"]:candidate_data_chunk["end"]]
    check(len(round_data) == len(data) + 16, "candidate DCB data size wrong")
    check(struct.unpack_from("<I", round_data, 8)[0] == 256, "candidate GOPool count wrong")
    check(round_data[0x90:0x1080] == data[0x90:0x1080], "stock GOPool rows changed")
    check(round_data[0x1080:0x1090] == raven_row, "Raven GOPool row missing")
    check(round_data[0x1090:] == data[0x1080:], "stock MemoryPools/Lua bytes changed")

    # Every non-data DCB chunk is byte-identical; only its file offset moves by
    # 16 bytes because the data chunk grew by one aligned row.
    original_by_kind = {c["kind"]: raw[c["start"]:c["end"] for c in chunks if c["kind"] != 12}
    candidate_by_kind = {c["kind"]: candidate[c["start"]:c["end"] for c in reparsed if c["kind"] != 12}
    check(original_by_kind == candidate_by_kind, "a non-data DCB chunk changed")

    return candidate, {
        "stock_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "gopool_count_before": 255,
        "gopool_count_after": 256,
        "raven_name": RAVEN_DCB_NAME,
        "raven_hash": f"{RAVEN_GO_HASH:016X}",
        "raven_row_hex": raven_row.hex(),
        "stock_rows_byte_identical": True,
        "stock_memory_arrays_byte_identical": True,
        "non_data_chunks_byte_identical": True,
        "reparse_passed": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--work-dir", type=Path,
                    default=Path(os.environ.get("LOCALAPPDATA", ".")) / "CompletionistMap/work/v0.10.4/raven-ui-logical-clone")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    work = args.work_dir.resolve()
    output = args.output.resolve()
    check(not work.is_relative_to(game), "work directory must stay outside the game tree")
    check(not output.is_relative_to(game), "report must stay outside the game tree")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    for path in (wad_path, dcb_path):
        check(path.is_file(), f"missing source: {path}")

    wad_raw = wad_path.read_bytes()
    dcb_raw = dcb_path.read_bytes()
    check(digest(wad_raw) == EXPECTED_WAD, "r_ui.wad is not the researched stock file")
    check(digest(dcb_raw) == EXPECTED_DCB, "wad_r_ui.dcb is not the researched stock file")

    wad_candidate, wad_report = build_wad(wad_raw)
    dcb_candidate, dcb_report = build_dcb(dcb_raw)

    work.mkdir(parents=True, exist_ok=True)
    wad_out = work / "r_ui.wad"
    dcb_out = work / "wad_r_ui.dcb"
    wad_out.write_bytes(wad_candidate)
    dcb_out.write_bytes(dcb_candidate)

    check(wad_path.read_bytes() == wad_raw and dcb_path.read_bytes() == dcb_raw, "source game files changed during build")

    report = {
        "result": "OFFLINE_RAVEN_UI_LOGICAL_CLONE_BUILT",
        "game_files_written": False,
        "source_hashes_unchanged_after_build": True,
        "architecture": {
            "dedicated_ui_identity": RAVEN_DCB_NAME,
            "dedicated_ui_hash": f"{RAVEN_GO_HASH:016X}",
            "dedicated_wad_resource": RAVEN_WAD_NAME,
            "shares_stock_Dock_prototype": True,
            "real_Dock_resources_modified": False,
            "expected_artwork_at_this_gate": "stock Dock artwork",
            "purpose": "Prove a Raven-only logical GameObject identity before attaching Raven-only material/texture resources.",
        },
        "source": {
            "r_ui_wad": {"path": str(wad_path), "sha256": EXPECTED_WAD},
            "wad_r_ui_dcb": {"path": str(dcb_path), "sha256": EXPECTED_DCB},
        },
        "candidate": {
            "directory": str(work),
            "r_ui_wad": {"path": str(wad_out), "bytes": len(wad_candidate), "sha256": digest(wad_candidate)},
            "wad_r_ui_dcb": {"path": str(dcb_out), "bytes": len(dcb_candidate), "sha256": digest(dcb_candidate)},
        },
        "wad_validation": wad_report,
        "dcb_validation": dcb_report,
        "safety": {
            "save_state_written": False,
            "progression_state_written": False,
            "boot_options_written": False,
            "game_directory_written": False,
            "stock_Dock_material_or_texture_changed": False,
            "native_Kratos_marker_touched": False,
        },
        "next_gate": (
            "If this offline structure validates, clone only the Dock visual material dependency for the dedicated "
            "Completionist Raven identity and point that clone at unique Raven diffuse/emissive hashes. Build the "
            "matching texpack offline. Do not install this logical-only candidate as a release artifact."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Built offline WAD: {wad_out}")
    print(f"Built offline DCB: {dcb_out}")
    print(f"Saved validation: {output}")
    print(f"Raven UI hash: {RAVEN_GO_HASH:016X}")
    print("Logical Raven identity is isolated; artwork intentionally still shares stock Dock prototype at this gate.")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
