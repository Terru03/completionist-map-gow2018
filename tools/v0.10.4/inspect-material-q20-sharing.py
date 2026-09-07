"""Inspect stock sharing semantics of the 0x20 qword in UI materials.

Read-only. The previous identity-field gate was intentionally conservative and
stopped because qword +0x20 is not globally unique. This probe determines
whether stock materials intentionally share +0x20 values, while +0x10 remains
unique, and whether that makes the safe Raven clone strategy "fresh +0x10,
retain Dock +0x20" rather than inventing a fresh +0x20 value.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
DOCK_INDEX = 13699


def check(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def align16(v: int) -> int:
    return (v + 15) & ~15


def parse_wad(raw: bytes):
    records = []
    payloads = []
    children = collections.defaultdict(list)
    stack = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short WAD header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(padded <= len(raw), f"short WAD payload at {off:#x}")
        hdr = raw[off:start]
        rec = {
            "physical_index": len(records),
            "payload_index": len(payloads) if size else None,
            "offset": off,
            "kind": kind,
            "flags": flags,
            "size": size,
            "id": hdr[8:24],
            "name": hdr[24:80].split(b"\0", 1)[0].decode("ascii", errors="replace"),
            "data": raw[start:end],
            "parent": stack[-1] if stack else None,
        }
        records.append(rec)
        if rec["parent"] is not None:
            children[rec["parent"]].append(rec["physical_index"])
        if size:
            payloads.append(rec)
        if kind == 2:
            stack.append(rec["physical_index"])
        elif kind == 3:
            check(stack, f"unmatched WAD group end at {off:#x}")
            stack.pop()
        off = padded
    check(not stack and off == len(raw), "WAD walk did not end cleanly")
    return records, payloads, children


def summary(r: dict) -> dict:
    return {
        "physical_index": r["physical_index"],
        "payload_index": r["payload_index"],
        "offset": f"0x{r['offset']:X}",
        "name": r["name"],
        "id": r["id"].hex(),
    }


def canonical_payload(blob: bytes) -> bytes:
    # Remove the two varying qwords so we can compare the rest of the authored
    # material payload independently of these fields.
    b = bytearray(blob)
    b[0x10:0x18] = bytes(8)
    b[0x20:0x28] = bytes(8)
    return bytes(b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    output = args.output.resolve()
    check(not output.is_relative_to(game), "output must stay outside game directory")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    raw = wad_path.read_bytes()
    check(sha256(raw) == EXPECTED_WAD, "unexpected r_ui.wad hash")
    records, payloads, children = parse_wad(raw)
    check((len(records), len(payloads)) == (53777, 20407), "unexpected WAD counts")

    materials = [r for r in payloads
                 if r["kind"] == 1 and r["flags"] == 0x14 and r["size"] == 384
                 and r["name"].startswith("MAT_")]
    check(len(materials) == 60, f"expected 60 matching materials, found {len(materials)}")
    by_index = {r["payload_index"]: r for r in materials}
    dock = by_index[DOCK_INDEX]

    q10_map = collections.defaultdict(list)
    q20_map = collections.defaultdict(list)
    for r in materials:
        q10 = struct.unpack_from("<Q", r["data"], 0x10)[0]
        q20 = struct.unpack_from("<Q", r["data"], 0x20)[0]
        q10_map[q10].append(r)
        q20_map[q20].append(r)

    duplicate_groups = []
    for value, rows in sorted(q20_map.items()):
        if len(rows) < 2:
            continue
        canonical_hashes = collections.defaultdict(list)
        for r in rows:
            canonical_hashes[sha256(canonical_payload(r["data"]))].append(r["payload_index"])
        group = {
            "qword_0x20": f"{value:016X}",
            "count": len(rows),
            "distinct_resource_ids": len({r["id"] for r in rows}),
            "distinct_names": len({r["name"] for r in rows}),
            "canonical_payload_variant_count": len(canonical_hashes),
            "canonical_payload_groups": dict(canonical_hashes),
            "materials": [],
        }
        for r in rows:
            parent_children = [records[i] for i in children.get(r["parent"], [])] if r["parent"] is not None else []
            links = [x for x in parent_children if x["kind"] == 1 and x["size"] == 0]
            group["materials"].append({
                **summary(r),
                "qword_0x10": f"{struct.unpack_from('<Q', r['data'], 0x10)[0]:016X}",
                "canonical_payload_sha256": sha256(canonical_payload(r["data"])),
                "group_links": [{"name": x["name"], "id": x["id"].hex()} for x in links],
            })
        duplicate_groups.append(group)

    dock_q10 = struct.unpack_from("<Q", dock["data"], 0x10)[0]
    dock_q20 = struct.unpack_from("<Q", dock["data"], 0x20)[0]
    all_q10_unique = all(len(v) == 1 for v in q10_map.values())
    stock_q20_sharing_proven = any(
        g["distinct_resource_ids"] > 1 and g["distinct_names"] > 1 for g in duplicate_groups
    )

    # A duplicate +0x20 value across distinct stock materials proves that +0x20
    # is not required to be a globally unique material identity. The conservative
    # clone can therefore preserve the known-good Dock +0x20 state while giving
    # the Raven material a fresh +0x10 identity.
    safe_strategy = all_q10_unique and stock_q20_sharing_proven and len(q20_map[dock_q20]) == 1

    report = {
        "result": "MATERIAL_Q20_SHARING_INSPECTED",
        "game_files_written": False,
        "source_wad_sha256": sha256(raw),
        "material_count": len(materials),
        "qword_0x10": {
            "unique_value_count": len(q10_map),
            "all_values_unique": all_q10_unique,
        },
        "qword_0x20": {
            "unique_value_count": len(q20_map),
            "duplicate_group_count": len(duplicate_groups),
            "stock_sharing_across_distinct_materials_proven": stock_q20_sharing_proven,
            "duplicate_groups": duplicate_groups,
        },
        "dock": {
            "material": summary(dock),
            "qword_0x10": f"{dock_q10:016X}",
            "qword_0x20": f"{dock_q20:016X}",
            "qword_0x20_stock_user_count": len(q20_map[dock_q20]),
        },
        "decision": {
            "safe_to_clone_with_fresh_q10_and_preserved_dock_q20": safe_strategy,
            "reason": (
                "Stock proves +0x20 may be shared by distinct materials, while +0x10 is globally unique. "
                "If true, keep the known-good Dock +0x20 in the Raven clone and generate only a fresh +0x10."
            ),
        },
        "next_gate": (
            "If decision is true, build the Raven-only material clone using a fresh +0x10 and preserved Dock +0x20, "
            "then clone fresh Raven texture definition/GPU identities and wire the Raven model/prototype to that material."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Materials inspected: {len(materials)}")
    print(f"q20 duplicate groups: {len(duplicate_groups)}")
    print(f"Safe fresh-q10/preserve-q20 strategy: {safe_strategy}")
    print(f"Saved: {output}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
