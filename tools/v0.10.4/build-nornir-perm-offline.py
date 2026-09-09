#!/usr/bin/env python3
"""Build the OFFLINE Nornir CompassIconClass and dedicated in-world carrier.

Starts from the frozen runtime-proven Raven production wad_r_perm.dcb. Adds
CompletionistNornirChest (0x11E) and a dedicated type-0x129 in-world carrier by
cloning the proven Raven records. The game tree is read only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_SOURCE_SHA256 = "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5"
RESULT = "OFFLINE_NORNIR_PERM_BUILT_AND_REPARSED"

RAVEN_CLASS = "CompletionistRaven"
RAVEN_CLASS_UID = 0x5DC46967D3095F7E
RAVEN_HUD = 0x45E5C7943749F81C
RAVEN_INWORLD = "COMPASS_INWORLD_COMPLETIONIST_RAVEN"
RAVEN_INWORLD_UID = 0x21DC5A7D4AD17628

NORNIR_CLASS = "CompletionistNornirChest"
NORNIR_CLASS_UID = 0x8D5A770E0C4272CE
NORNIR_HUD = 0x7DDC11175EBD1E94
NORNIR_INWORLD = "COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST"
NORNIR_INWORLD_UID = 0x32BBE7E267644D93

COMPASS_CLASS_TYPE = 0x11E
INWORLD_TYPE = 0x129
CLASS_SIZE = 0x20
INWORLD_SIZE = 0x98


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_packed():
    path = HERE / "build-packed-raven-compass-class.py"
    spec = importlib.util.spec_from_file_location("nornir_perm_packed", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shifted(offset: int, at: int, size: int) -> int:
    return offset + size if offset >= at else offset


def strict_inc(values: list[int]) -> bool:
    return all(a < b for a, b in zip(values, values[1:]))


def next_root(exports: list[dict], root: int, data_len: int) -> int:
    later = sorted({int(e["root"]) for e in exports if int(e["root"]) > root})
    return later[0] if later else data_len


def relocs_in(relocs: list[dict], root: int, size: int) -> list[dict]:
    return [r for r in relocs if root <= int(r["field"]) < root + size]


def shift_relocs(data: bytearray, relocs: list[dict], at: int, size: int) -> list[dict]:
    out = []
    for r in relocs:
        field = shifted(int(r["field"]), at, size)
        target = shifted(int(r["target"]), at, size)
        struct.pack_into("<q", data, field, target - field)
        out.append({"field": field, "target": target, "delta": target - field})
    return out


def serialize_exports(header8: bytes, exports: list[dict], tail: bytes) -> bytes:
    h = bytearray(header8)
    struct.pack_into("<I", h, 0, len(exports))
    out = bytearray(h)
    for e in exports:
        out += struct.pack("<IIQQ", int(e["root"]), int(e["type_id"]),
                           int(e["string_offset"]), int(e["uid"]))
    out += tail
    return bytes(out)


def build_candidate(source_raw: bytes) -> tuple[bytes, dict]:
    packed = load_packed()
    check(sha256(source_raw) == EXPECTED_SOURCE_SHA256,
          "wad_r_perm.dcb is not frozen Raven production")
    check(packed.name_hash(NORNIR_CLASS) == NORNIR_CLASS_UID, "Nornir class UID mismatch")
    check(packed.name_hash(NORNIR_INWORLD) == NORNIR_INWORLD_UID, "Nornir carrier UID mismatch")

    chunks = packed.parse_chunks(source_raw)
    data = bytes(packed.one(chunks, 12)["payload"])
    header8, exports, tail = packed.parse_exports(packed.one(chunks, 13)["payload"])
    relocs = packed.parse_relocations(packed.one(chunks, 15)["payload"], data)
    by_name = {e["name"]: e for e in exports}

    check(strict_inc([int(e["uid"]) for e in exports]), "production export table is not UID-sorted")
    for name in (RAVEN_CLASS, RAVEN_INWORLD, "DockPoint", "COMPASS_INWORLD_DOCK", "COMPASS_GLOBALS"):
        check(name in by_name, f"required production export missing: {name}")
    check(NORNIR_CLASS not in by_name and NORNIR_INWORLD not in by_name,
          "Nornir perm exports already exist")
    check(all(int(e["uid"]) not in (NORNIR_CLASS_UID, NORNIR_INWORLD_UID) for e in exports),
          "Nornir UID collision")

    raven_class = by_name[RAVEN_CLASS]
    raven_iw = by_name[RAVEN_INWORLD]
    check(int(raven_class["uid"]) == RAVEN_CLASS_UID and int(raven_class["type_id"]) == COMPASS_CLASS_TYPE,
          "Raven class identity changed")
    check(int(raven_iw["uid"]) == RAVEN_INWORLD_UID and int(raven_iw["type_id"]) == INWORLD_TYPE,
          "Raven carrier identity changed")

    rc_root = int(raven_class["root"])
    rc = data[rc_root:rc_root + CLASS_SIZE]
    check(len(rc) == CLASS_SIZE, "short Raven class record")
    raven_icon, raven_radius, raven_inworld_uid = struct.unpack_from("<QQQ", rc, 0)
    check(raven_icon == RAVEN_HUD and raven_inworld_uid == RAVEN_INWORLD_UID,
          "Raven class bindings changed")
    check(not relocs_in(relocs, rc_root, CLASS_SIZE), "Raven class unexpectedly contains relocations")

    ri_root = int(raven_iw["root"])
    check(next_root(exports, ri_root, len(data)) - ri_root == INWORLD_SIZE,
          "Raven carrier span changed")
    ri = data[ri_root:ri_root + INWORLD_SIZE]
    check(struct.unpack_from("<Q", ri, 0)[0] == RAVEN_HUD, "Raven carrier visual changed")
    ri_relocs = relocs_in(relocs, ri_root, INWORLD_SIZE)
    check(len(ri_relocs) == 1, f"expected one Raven carrier relocation, found {len(ri_relocs)}")
    field_rel = int(ri_relocs[0]["field"]) - ri_root
    target_rel = int(ri_relocs[0]["target"]) - ri_root
    check(0 <= target_rel < INWORLD_SIZE, "Raven carrier relocation is not self-contained")

    iw = sorted([e for e in exports if int(e["type_id"]) == INWORLD_TYPE and
                 e["name"].startswith("COMPASS_INWORLD_")], key=lambda e: int(e["root"]))
    classes = sorted([e for e in exports if int(e["type_id"]) == COMPASS_CLASS_TYPE],
                     key=lambda e: int(e["root"]))
    check(len(iw) == 9, f"expected 9 production in-world exports, found {len(iw)}")
    check(len(classes) == 10, f"expected 10 production compass classes, found {len(classes)}")
    iw_roots = [int(e["root"]) for e in iw]
    class_roots = [int(e["root"]) for e in classes]
    check(all(b - a == INWORLD_SIZE for a, b in zip(iw_roots, iw_roots[1:])),
          "production in-world block is not packed 0x98 records")
    check(all(b - a == CLASS_SIZE for a, b in zip(class_roots, class_roots[1:])),
          "production class block is not packed 0x20 records")
    check(iw[-1]["name"] == RAVEN_INWORLD, "Raven carrier is not final in-world record")
    check(classes[-1]["name"] == RAVEN_CLASS, "Raven class is not final compass class")

    insert_iw = iw_roots[-1] + INWORLD_SIZE
    check(insert_iw == class_roots[0], "in-world block no longer ends at compass-class block")
    globals_row = by_name["COMPASS_GLOBALS"]
    check(class_roots[-1] + CLASS_SIZE == int(globals_row["root"]),
          "compass-class block no longer ends at COMPASS_GLOBALS")

    # Append dedicated Nornir carrier at the end of the packed type-0x129 block.
    nornir_iw = bytearray(ri)
    struct.pack_into("<Q", nornir_iw, 0, NORNIR_HUD)
    data1 = bytearray(data[:insert_iw] + bytes(nornir_iw) + data[insert_iw:])
    relocs1 = shift_relocs(data1, relocs, insert_iw, INWORLD_SIZE)
    clone_field = insert_iw + field_rel
    clone_target = insert_iw + target_rel
    struct.pack_into("<q", data1, clone_field, clone_target - clone_field)
    relocs1.append({"field": clone_field, "target": clone_target, "delta": clone_target - clone_field})

    # Append Nornir class at the end of the now-shifted packed type-0x11E block.
    raven_class_root1 = shifted(rc_root, insert_iw, INWORLD_SIZE)
    insert_class = shifted(int(globals_row["root"]), insert_iw, INWORLD_SIZE)
    check(raven_class_root1 + CLASS_SIZE == insert_class, "shifted Raven class block changed")
    nornir_class = bytearray(data1[raven_class_root1:raven_class_root1 + CLASS_SIZE])
    check(bytes(nornir_class) == rc, "Raven class bytes changed after carrier insertion")
    struct.pack_into("<Q", nornir_class, 0, NORNIR_HUD)
    struct.pack_into("<Q", nornir_class, 16, NORNIR_INWORLD_UID)
    data2 = bytearray(data1[:insert_class] + bytes(nornir_class) + data1[insert_class:])
    relocs2 = shift_relocs(data2, relocs1, insert_class, CLASS_SIZE)

    def final_offset(offset: int) -> int:
        return shifted(shifted(offset, insert_iw, INWORLD_SIZE), insert_class, CLASS_SIZE)

    # Two new export rows shift all existing export-name string offsets by 48 bytes.
    final_exports = [{**e, "root": final_offset(int(e["root"])),
                      "string_offset": int(e["string_offset"]) + 48} for e in exports]
    strings_at = 8 + (len(exports) + 2) * 24 + len(tail)
    final_exports.extend([
        {"root": insert_iw, "type_id": INWORLD_TYPE, "string_offset": strings_at,
         "uid": NORNIR_INWORLD_UID, "name": NORNIR_INWORLD},
        {"root": insert_class, "type_id": COMPASS_CLASS_TYPE,
         "string_offset": strings_at + len(NORNIR_INWORLD) + 1,
         "uid": NORNIR_CLASS_UID, "name": NORNIR_CLASS},
    ])
    final_exports.sort(key=lambda e: int(e["uid"]))
    check(strict_inc([int(e["uid"]) for e in final_exports]), "candidate export UIDs are not sorted")
    final_tail = tail + NORNIR_INWORLD.encode("ascii") + b"\0" + NORNIR_CLASS.encode("ascii") + b"\0"
    export_payload = serialize_exports(header8, final_exports, final_tail)

    fields = [int(r["field"]) for r in relocs2]
    reloc_payload = struct.pack("<I", len(fields))
    if fields:
        reloc_payload += struct.pack(f"<{len(fields)}I", *fields)
    candidate = packed.build_file(chunks, {12: bytes(data2), 13: export_payload, 15: reloc_payload})

    # Strict reparse.
    out_chunks = packed.parse_chunks(candidate)
    out_data = bytes(packed.one(out_chunks, 12)["payload"])
    _h, out_exports, out_tail = packed.parse_exports(packed.one(out_chunks, 13)["payload"])
    out_relocs = packed.parse_relocations(packed.one(out_chunks, 15)["payload"], out_data)
    out_by_name = {e["name"]: e for e in out_exports}
    check(len(out_exports) == len(exports) + 2, "candidate export count mismatch")
    check(len(out_relocs) == len(relocs) + 1, "candidate relocation count mismatch")
    check(out_tail == final_tail, "candidate export string tail mismatch")

    for old in exports:
        new = out_by_name.get(old["name"])
        check(new is not None, f"existing export disappeared: {old['name']}")
        check(int(new["uid"]) == int(old["uid"]) and int(new["type_id"]) == int(old["type_id"]),
              f"existing export identity changed: {old['name']}")
        check(int(new["root"]) == final_offset(int(old["root"])),
              f"existing export root shift wrong: {old['name']}")

    ni = out_by_name.get(NORNIR_INWORLD)
    nc = out_by_name.get(NORNIR_CLASS)
    check(ni is not None and int(ni["uid"]) == NORNIR_INWORLD_UID and
          int(ni["type_id"]) == INWORLD_TYPE and int(ni["root"]) == insert_iw,
          "Nornir in-world export failed reparse")
    check(nc is not None and int(nc["uid"]) == NORNIR_CLASS_UID and
          int(nc["type_id"]) == COMPASS_CLASS_TYPE and int(nc["root"]) == insert_class,
          "Nornir class export failed reparse")

    ni_bytes = out_data[insert_iw:insert_iw + INWORLD_SIZE]
    check(struct.unpack_from("<Q", ni_bytes, 0)[0] == NORNIR_HUD and ni_bytes[8:] == ri[8:],
          "Nornir carrier differs from Raven grammar outside IconName")
    nc_bytes = out_data[insert_class:insert_class + CLASS_SIZE]
    out_icon, out_radius, out_inworld = struct.unpack_from("<QQQ", nc_bytes, 0)
    check(out_icon == NORNIR_HUD and out_radius == raven_radius and out_inworld == NORNIR_INWORLD_UID,
          "Nornir class bindings changed")
    check(nc_bytes[24:] == rc[24:], "Nornir class tail differs from Raven class")

    # Existing relocation semantics transform exactly through both packed insertions.
    for index, old in enumerate(relocs):
        got = out_relocs[index]
        check(int(got["field"]) == final_offset(int(old["field"])) and
              int(got["target"]) == final_offset(int(old["target"])),
              f"existing relocation semantic changed at index {index}")
    check(int(out_relocs[-1]["field"]) == clone_field and int(out_relocs[-1]["target"]) == clone_target,
          "Nornir carrier relocation topology changed")

    # Exact inverse data proof.
    normalized = bytearray(out_data)
    del normalized[insert_class:insert_class + CLASS_SIZE]
    del normalized[insert_iw:insert_iw + INWORLD_SIZE]
    for old in relocs:
        struct.pack_into("<q", normalized, int(old["field"]), int(old["delta"]))
    check(bytes(normalized) == data, "candidate data does not normalize exactly to Raven production")
    for kind in (11, 14, 35):
        check(packed.one(chunks, kind)["payload"] == packed.one(out_chunks, kind)["payload"],
              f"unrelated chunk {kind} changed")

    out_rc = out_by_name[RAVEN_CLASS]
    out_ri = out_by_name[RAVEN_INWORLD]
    check(out_data[int(out_rc["root"]):int(out_rc["root"]) + CLASS_SIZE] == rc,
          "frozen Raven class bytes changed")
    check(out_data[int(out_ri["root"]):int(out_ri["root"]) + INWORLD_SIZE] == ri,
          "frozen Raven carrier bytes changed")

    report = {
        "schema": 1,
        "result": RESULT,
        "source_sha256": sha256(source_raw),
        "candidate_sha256": sha256(candidate),
        "candidate_bytes": len(candidate),
        "nornir_class": {
            "name": NORNIR_CLASS, "uid": f"{NORNIR_CLASS_UID:016X}",
            "type_id": f"0x{COMPASS_CLASS_TYPE:X}", "root": f"0x{insert_class:X}",
            "IconName": f"{out_icon:016X}", "RadiusIconName": f"{out_radius:016X}",
            "InWorld_tMPIcon_Name": f"{out_inworld:016X}", "cloned_from": RAVEN_CLASS,
            "tail_equal_to_raven": True,
        },
        "nornir_inworld": {
            "name": NORNIR_INWORLD, "uid": f"{NORNIR_INWORLD_UID:016X}",
            "type_id": f"0x{INWORLD_TYPE:X}", "root": f"0x{insert_iw:X}",
            "IconName": f"{NORNIR_HUD:016X}", "cloned_from": RAVEN_INWORLD,
            "equal_to_raven_except_IconName": True,
            "relocation_field_relative": f"0x{field_rel:X}",
            "relocation_target_relative": f"0x{target_rel:X}",
            "relocation_self_contained": True,
        },
        "proof": {
            "source_inworld_rows": len(iw), "candidate_inworld_rows": len(iw) + 1,
            "source_compass_class_rows": len(classes), "candidate_compass_class_rows": len(classes) + 1,
            "all_existing_exports_preserved": True,
            "all_existing_relocation_semantics_preserved": True,
            "candidate_data_normalizes_exactly_to_raven_production": True,
            "frozen_raven_class_preserved": True,
            "frozen_raven_inworld_preserved": True,
            "stock_DockPoint_resources_preserved_by_exact_normalization": True,
            "unrelated_chunks_11_14_35_identical": True,
        },
        "safety": {
            "game_files_written": False, "save_state_written": False,
            "progression_state_written": False, "marker_state_written": False,
            "runtime_install_performed": False,
        },
        "ready_for_vertical_slice_assembly": True,
        "runtime_ready": False,
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
    check(source.is_file(), f"missing source: {source}")
    source_raw = source.read_bytes()
    output = args.output.resolve()
    report_path = args.report.resolve()
    check(not output.is_relative_to(game) and not report_path.is_relative_to(game),
          "offline outputs must stay outside the game directory")

    candidate, report = build_candidate(source_raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == source_raw, "source wad_r_perm.dcb changed during offline build")

    print(RESULT)
    print(f"  source SHA256:    {report['source_sha256']}")
    print(f"  candidate SHA256: {report['candidate_sha256']}")
    print(f"  class:            {NORNIR_CLASS} / {NORNIR_CLASS_UID:016X} / 0x{COMPASS_CLASS_TYPE:X}")
    print(f"  HUD IconName:     {NORNIR_HUD:016X}")
    print(f"  in-world:         {NORNIR_INWORLD} / {NORNIR_INWORLD_UID:016X} / 0x{INWORLD_TYPE:X}")
    print("  Raven class/carrier preserved: true")
    print("  existing export/relocation semantics preserved: true")
    print("  candidate normalizes exactly to Raven production: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
