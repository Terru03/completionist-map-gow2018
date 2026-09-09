#!/usr/bin/env python3
"""Build a read-only/offline dedicated Completionist Raven in-world carrier.

This starts from the currently proven v0.10.4 Raven HUD/native-routing wad_r_perm.dcb.
It clones stock COMPASS_INWORLD_DOCK as a new independent type-0x129 export,
changes only the clone's HUD icon binding to goCompletionistRavenHUD, and points
CompletionistRaven.InWorld_tMPIcon_Name at the new export.

The builder never writes the game directory. It fails closed unless the stock
COMPASS_INWORLD_* block, donor correlation, relocation topology, export ordering,
and proven CompletionistRaven class state all match the researched runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_SOURCE_SHA256 = "7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961"
RAVEN_CLASS = "CompletionistRaven"
DOCK_CLASS = "DockPoint"
SIDE_CLASS = "SIDE"
DONOR = "COMPASS_INWORLD_DOCK"
SIDE_INWORLD = "COMPASS_INWORLD_SIDE"
NEW_NAME = "COMPASS_INWORLD_COMPLETIONIST_RAVEN"
INWORLD_TYPE = 0x129
COMPASS_CLASS_TYPE = 0x11E
RECORD_SIZE = 0x98
RAVEN_HUD_HASH = 0x45E5C7943749F81C
DOCK_HUD_HASH = 0x82F0296748C7393D
RESULT = "OFFLINE_RAVEN_INWORLD_CARRIER_BUILT"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_packed():
    path = HERE / "build-packed-raven-compass-class.py"
    spec = importlib.util.spec_from_file_location("completionist_inworld_builder_packed", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_inc(values: list[int]) -> bool:
    return all(a < b for a, b in zip(values, values[1:]))


def next_root(exports: list[dict], root: int, data_len: int) -> int:
    later = sorted({int(e["root"]) for e in exports if int(e["root"]) > root})
    return later[0] if later else data_len


def shifted(offset: int, insert_at: int) -> int:
    return offset + RECORD_SIZE if offset >= insert_at else offset


def class_record(data: bytes, row: dict) -> bytes:
    root = int(row["root"])
    check(root + 0x20 <= len(data), f"class record outside data: {row['name']}")
    return data[root:root + 0x20]


def serialize_exports(packed, header8: bytes, exports: list[dict], tail: bytes) -> bytes:
    h = bytearray(header8)
    struct.pack_into("<I", h, 0, len(exports))
    out = bytearray(h)
    for e in exports:
        out += struct.pack(
            "<IIQQ",
            int(e["root"]),
            int(e["type_id"]),
            int(e["string_offset"]),
            int(e["uid"]),
        )
    out += tail
    return bytes(out)


def build_candidate(source_raw: bytes) -> tuple[bytes, dict]:
    packed = load_packed()
    chunks = packed.parse_chunks(source_raw)
    data_chunk = packed.one(chunks, 12)
    export_chunk = packed.one(chunks, 13)
    reloc_chunk = packed.one(chunks, 15)
    data = bytes(data_chunk["payload"])
    header8, exports, tail = packed.parse_exports(export_chunk["payload"])
    relocs = packed.parse_relocations(reloc_chunk["payload"], data)
    by_name = {e["name"]: e for e in exports}

    check(strict_inc([int(e["uid"]) for e in exports]), "live export table is not strictly UID-sorted")
    for required in (RAVEN_CLASS, DOCK_CLASS, SIDE_CLASS, DONOR, SIDE_INWORLD):
        check(required in by_name, f"required export missing: {required}")
    check(NEW_NAME not in by_name, f"{NEW_NAME} already exists")

    raven = by_name[RAVEN_CLASS]
    dock_class = by_name[DOCK_CLASS]
    side_class = by_name[SIDE_CLASS]
    donor = by_name[DONOR]
    side_iw = by_name[SIDE_INWORLD]

    check(int(raven["type_id"]) == COMPASS_CLASS_TYPE, "CompletionistRaven type changed")
    check(int(dock_class["type_id"]) == COMPASS_CLASS_TYPE, "DockPoint type changed")
    check(int(side_class["type_id"]) == COMPASS_CLASS_TYPE, "SIDE type changed")
    check(int(donor["type_id"]) == INWORLD_TYPE, "Dock in-world type changed")
    check(int(side_iw["type_id"]) == INWORLD_TYPE, "SIDE in-world type changed")

    raven_rec = class_record(data, raven)
    dock_class_rec = class_record(data, dock_class)
    side_class_rec = class_record(data, side_class)
    raven_icon, raven_radius, raven_inworld = struct.unpack_from("<QQQ", raven_rec, 0)
    dock_icon, _dock_radius, dock_inworld = struct.unpack_from("<QQQ", dock_class_rec, 0)
    side_icon, _side_radius, side_inworld = struct.unpack_from("<QQQ", side_class_rec, 0)
    check(raven_icon == RAVEN_HUD_HASH, f"CompletionistRaven HUD hash changed: {raven_icon:016X}")
    check(dock_icon == DOCK_HUD_HASH, f"DockPoint HUD hash changed: {dock_icon:016X}")
    check(raven_inworld == int(donor["uid"]), "CompletionistRaven no longer uses Dock donor before clone")
    check(dock_inworld == int(donor["uid"]), "DockPoint no longer references COMPASS_INWORLD_DOCK")
    check(side_inworld == int(side_iw["uid"]), "SIDE no longer references COMPASS_INWORLD_SIDE")

    iw = sorted(
        (e for e in exports if e["name"].startswith("COMPASS_INWORLD_")),
        key=lambda e: int(e["root"]),
    )
    check(len(iw) == 8, f"expected 8 COMPASS_INWORLD_* exports, found {len(iw)}")
    check(all(int(e["type_id"]) == INWORLD_TYPE for e in iw), "in-world exports no longer share type 0x129")
    roots = [int(e["root"]) for e in iw]
    check(all(b - a == RECORD_SIZE for a, b in zip(roots, roots[1:])),
          f"COMPASS_INWORLD block is not contiguous 0x{RECORD_SIZE:X}-byte records: {[hex(x) for x in roots]}")
    for e in iw:
        end = next_root(exports, int(e["root"]), len(data))
        check(end - int(e["root"]) == RECORD_SIZE, f"{e['name']} span changed: {end-int(e['root'])}")

    insert_at = roots[-1] + RECORD_SIZE
    compass_roots = sorted(int(e["root"]) for e in exports if int(e["type_id"]) == COMPASS_CLASS_TYPE)
    check(compass_roots and compass_roots[0] == insert_at,
          f"in-world block no longer ends exactly at CompassIconClass block: insert={insert_at:#x} firstClass={compass_roots[0] if compass_roots else None}")

    donor_root = int(donor["root"])
    side_root = int(side_iw["root"])
    donor_record = data[donor_root:donor_root + RECORD_SIZE]
    side_record = data[side_root:side_root + RECORD_SIZE]
    check(len(donor_record) == RECORD_SIZE and len(side_record) == RECORD_SIZE, "short in-world record")
    check(struct.unpack_from("<Q", donor_record, 0)[0] == DOCK_HUD_HASH,
          "Dock in-world record no longer embeds DockPoint IconName at +0x00")
    check(struct.unpack_from("<Q", side_record, 0)[0] == side_icon,
          "SIDE in-world record no longer embeds SIDE IconName at +0x00")
    diffs = [i for i, (a, b) in enumerate(zip(donor_record, side_record)) if a != b]
    check(diffs == list(range(8)),
          f"Dock/SIDE records no longer differ only in IconName qword: {[hex(x) for x in diffs]}")

    donor_relocs = [r for r in relocs if donor_root <= int(r["field"]) < donor_root + RECORD_SIZE]
    side_relocs = [r for r in relocs if side_root <= int(r["field"]) < side_root + RECORD_SIZE]
    check(len(donor_relocs) == 1 and len(side_relocs) == 1,
          f"expected one relocation in Dock/SIDE records, got {len(donor_relocs)}/{len(side_relocs)}")
    dr = donor_relocs[0]
    sr = side_relocs[0]
    donor_field_rel = int(dr["field"]) - donor_root
    side_field_rel = int(sr["field"]) - side_root
    donor_target_rel = int(dr["target"]) - donor_root
    side_target_rel = int(sr["target"]) - side_root
    check(donor_field_rel == side_field_rel,
          f"Dock/SIDE relocation field differs: {donor_field_rel:#x}/{side_field_rel:#x}")
    check(donor_target_rel == side_target_rel,
          f"Dock/SIDE relocation target-relative topology differs: {donor_target_rel:#x}/{side_target_rel:#x}")
    check(0 <= donor_target_rel < RECORD_SIZE,
          f"Dock relocation is not self-contained within donor record: target_rel={donor_target_rel:#x}")

    new_uid = int(packed.name_hash(NEW_NAME))
    check(all(int(e["uid"]) != new_uid for e in exports), f"new in-world UID collides: {new_uid:016X}")

    clone = bytearray(donor_record)
    struct.pack_into("<Q", clone, 0, RAVEN_HUD_HASH)
    patched_data = bytearray(data[:insert_at] + bytes(clone) + data[insert_at:])

    patched_fields: list[int] = []
    semantic_existing = []
    for r in relocs:
        old_field = int(r["field"])
        old_target = int(r["target"])
        new_field = shifted(old_field, insert_at)
        new_target = shifted(old_target, insert_at)
        new_delta = new_target - new_field
        struct.pack_into("<q", patched_data, new_field, new_delta)
        patched_fields.append(new_field)
        semantic_existing.append((old_field, old_target, new_field, new_target))

    clone_field = insert_at + donor_field_rel
    clone_target = insert_at + donor_target_rel
    struct.pack_into("<q", patched_data, clone_field, clone_target - clone_field)
    check(clone_field not in patched_fields, "clone relocation field collides with existing relocation")
    patched_fields.append(clone_field)

    new_raven_root = shifted(int(raven["root"]), insert_at)
    struct.pack_into("<Q", patched_data, new_raven_root + 16, new_uid)

    shift_strings = 24
    new_exports = []
    for e in exports:
        new_exports.append({
            **e,
            "root": shifted(int(e["root"]), insert_at),
            "string_offset": int(e["string_offset"]) + shift_strings,
        })
    new_name_offset = 8 + (len(exports) + 1) * 24 + len(tail)
    new_exports.append({
        "root": insert_at,
        "type_id": INWORLD_TYPE,
        "string_offset": new_name_offset,
        "uid": new_uid,
        "name": NEW_NAME,
    })
    new_exports.sort(key=lambda e: int(e["uid"]))
    check(strict_inc([int(e["uid"]) for e in new_exports]), "candidate export UIDs are not strictly increasing")
    new_tail = tail + NEW_NAME.encode("ascii") + b"\0"
    exports_payload = serialize_exports(packed, header8, new_exports, new_tail)

    reloc_payload = struct.pack("<I", len(patched_fields))
    if patched_fields:
        reloc_payload += struct.pack(f"<{len(patched_fields)}I", *patched_fields)

    candidate = packed.build_file(chunks, {
        12: bytes(patched_data),
        13: exports_payload,
        15: reloc_payload,
    })

    out_chunks = packed.parse_chunks(candidate)
    out_data = bytes(packed.one(out_chunks, 12)["payload"])
    _oh, out_exports, out_tail = packed.parse_exports(packed.one(out_chunks, 13)["payload"])
    out_relocs = packed.parse_relocations(packed.one(out_chunks, 15)["payload"], out_data)
    out_by_name = {e["name"]: e for e in out_exports}
    check(strict_inc([int(e["uid"]) for e in out_exports]), "serialized candidate export order is not UID-sorted")
    check(len(out_exports) == len(exports) + 1, "candidate export count mismatch")
    check(len(out_relocs) == len(relocs) + 1, "candidate relocation count mismatch")
    check(out_tail == new_tail, "candidate export string tail mismatch")
    check(NEW_NAME in out_by_name, "new in-world export missing after serialization")
    check(int(out_by_name[NEW_NAME]["root"]) == insert_at, "new in-world export root changed")
    check(int(out_by_name[NEW_NAME]["type_id"]) == INWORLD_TYPE, "new in-world export type changed")

    out_clone = out_data[insert_at:insert_at + RECORD_SIZE]
    check(struct.unpack_from("<Q", out_clone, 0)[0] == RAVEN_HUD_HASH, "clone HUD binding changed")
    check(out_clone[8:] == donor_record[8:], "clone differs from Dock donor outside IconName")

    out_raven = out_by_name[RAVEN_CLASS]
    out_raven_rec = class_record(out_data, out_raven)
    out_raven_icon, out_raven_radius, out_raven_inworld = struct.unpack_from("<QQQ", out_raven_rec, 0)
    check(out_raven_icon == RAVEN_HUD_HASH, "CompletionistRaven HUD IconName changed")
    check(out_raven_radius == raven_radius, "CompletionistRaven RadiusIconName changed")
    check(out_raven_inworld == new_uid, "CompletionistRaven did not bind new in-world carrier")
    check(out_raven_rec[24:] == raven_rec[24:], "CompletionistRaven non-binding tail changed")

    src_by_name = {e["name"]: e for e in exports}
    for name, before in src_by_name.items():
        after = out_by_name.get(name)
        check(after is not None, f"existing export disappeared: {name}")
        check(int(after["uid"]) == int(before["uid"]), f"{name} UID changed")
        check(int(after["type_id"]) == int(before["type_id"]), f"{name} type changed")
        check(int(after["root"]) == shifted(int(before["root"]), insert_at), f"{name} root shift wrong")

    out_pairs = [(int(r["field"]), int(r["target"])) for r in out_relocs]
    for old_field, old_target, expected_field, expected_target in semantic_existing:
        check((expected_field, expected_target) in out_pairs,
              f"existing relocation semantic lost: {old_field:#x}->{old_target:#x}")
    check((clone_field, clone_target) in out_pairs, "clone relocation semantic missing")

    normalized = bytearray(out_data)
    out_raven_root = int(out_raven["root"])
    struct.pack_into("<Q", normalized, out_raven_root + 16, raven_inworld)
    for old_field, _old_target, new_field, _new_target in semantic_existing:
        struct.pack_into("<q", normalized, new_field, struct.unpack_from("<q", data, old_field)[0])
    del normalized[insert_at:insert_at + RECORD_SIZE]
    check(bytes(normalized) == data,
          "candidate data does not normalize exactly to source after removing clone/binding transform")

    for kind in (11, 14, 35):
        check(packed.one(chunks, kind)["payload"] == packed.one(out_chunks, kind)["payload"],
              f"unrelated chunk {kind} changed")

    report = {
        "schema": 1,
        "result": RESULT,
        "source_sha256": sha256(source_raw),
        "candidate_sha256": sha256(candidate),
        "candidate_bytes": len(candidate),
        "new_export": {
            "name": NEW_NAME,
            "uid": f"{new_uid:016X}",
            "type_id": f"0x{INWORLD_TYPE:X}",
            "root": f"0x{insert_at:X}",
            "record_bytes": RECORD_SIZE,
            "donor": DONOR,
            "donor_record_equal_except_IconName": True,
            "IconName": f"{RAVEN_HUD_HASH:016X}",
            "relocation_field_relative": f"0x{donor_field_rel:X}",
            "relocation_target_relative": f"0x{donor_target_rel:X}",
            "relocation_self_contained": True,
        },
        "completionist_raven": {
            "IconName": f"{out_raven_icon:016X}",
            "RadiusIconName": f"{out_raven_radius:016X}",
            "InWorld_tMPIcon_Name_before": f"{raven_inworld:016X}",
            "InWorld_tMPIcon_Name_after": f"{out_raven_inworld:016X}",
            "other_class_fields_unchanged": True,
        },
        "topology_gates": {
            "eight_stock_inworld_exports": True,
            "stock_inworld_block_contiguous": True,
            "stock_inworld_record_size_0x98": True,
            "inworld_block_ends_at_compass_class_block": True,
            "dock_side_records_differ_only_at_IconName": True,
            "dock_side_relocation_topology_equal": True,
            "dock_relocation_self_contained": True,
            "export_uid_order_strict": True,
            "existing_relocation_semantics_preserved": True,
            "normalized_candidate_data_equals_source": True,
            "unrelated_chunks_11_14_35_identical": True,
        },
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "ready_for_reversible_runtime_install": True,
    }
    return candidate, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    check(source.is_file(), f"missing {source}")
    raw = source.read_bytes()
    digest = sha256(raw)
    check(digest == EXPECTED_SOURCE_SHA256,
          f"wad_r_perm.dcb is not the proven Raven HUD/native-routing baseline: {digest}")

    output = args.output.resolve()
    report_path = args.report.resolve()
    check(not output.is_relative_to(game) and not report_path.is_relative_to(game),
          "offline outputs must stay outside the game tree")

    candidate, report = build_candidate(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    check(source.read_bytes() == raw, "source wad_r_perm.dcb changed during offline build")

    ne = report["new_export"]
    cr = report["completionist_raven"]
    print(RESULT)
    print(f"  source SHA256:     {report['source_sha256']}")
    print(f"  candidate SHA256:  {report['candidate_sha256']}")
    print(f"  new export:        {ne['name']}")
    print(f"  new UID:           {ne['uid']}")
    print(f"  new root/type:     {ne['root']} / {ne['type_id']}")
    print(f"  clone donor:       {ne['donor']}")
    print("  clone differs from Dock only at IconName: true")
    print(f"  Raven InWorld:     {cr['InWorld_tMPIcon_Name_before']} -> {cr['InWorld_tMPIcon_Name_after']}")
    print("  existing export/relocation semantics preserved: true")
    print("  normalized candidate data equals source: true")
    print("  game files written: false")
    print("  ready for reversible runtime install: true")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
