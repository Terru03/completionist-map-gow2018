#!/usr/bin/env python3
"""Read-only structural inspection of stock compass in-world exports.

The byte scan proved that COMPASS_INWORLD_DOCK and COMPASS_INWORLD_SIDE are exported
objects inside wad_r_perm.dcb, not ordinary named r_ui.wad roots. This inspector parses
the live DCB properly and correlates each in-world export with the CompassIconClass that
references it. It also checks whether the in-world object embeds that class's HUD
IconName, which is the key gate for cloning a Raven in-world carrier safely.

No game file is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_LIVE_SHA256 = "7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961"
COMPASS_CLASS_TYPE = 0x11E
TARGET_NAMES = ("COMPASS_INWORLD_DOCK", "COMPASS_INWORLD_SIDE", "COMPASS_INWORLD_MAIN")
RAVEN_HUD_HASH = 0x45E5C7943749F81C


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_packed():
    path = HERE / "build-packed-raven-compass-class.py"
    spec = importlib.util.spec_from_file_location("completionist_inworld_packed", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def next_distinct_root(exports: list[dict], root: int, data_len: int) -> int:
    later = sorted({int(row["root"]) for row in exports if int(row["root"]) > root})
    return later[0] if later else data_len


def owning_export(exports_sorted: list[dict], target: int) -> dict | None:
    owner = None
    for row in exports_sorted:
        if int(row["root"]) > target:
            break
        owner = row
    return owner


def u64_hits(blob: bytes, value: int) -> list[int]:
    needle = struct.pack("<Q", value)
    hits = []
    start = 0
    while True:
        pos = blob.find(needle, start)
        if pos < 0:
            break
        hits.append(pos)
        start = pos + 1
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    check(source.is_file(), f"missing {source}")
    raw = source.read_bytes()
    live_sha = sha256(raw)
    check(live_sha == EXPECTED_LIVE_SHA256,
          f"wad_r_perm.dcb is not the proven dedicated-Raven HUD baseline: {live_sha}")

    packed = load_packed()
    chunks = packed.parse_chunks(raw)
    data = bytes(packed.one(chunks, 12)["payload"])
    _header, exports, _tail = packed.parse_exports(packed.one(chunks, 13)["payload"])
    relocs = packed.parse_relocations(packed.one(chunks, 15)["payload"], data)
    by_name = {row["name"]: row for row in exports}
    exports_sorted = sorted(exports, key=lambda row: (int(row["root"]), int(row["type_id"]), row["name"]))

    compass_classes = []
    for row in exports:
        if int(row["type_id"]) != COMPASS_CLASS_TYPE:
            continue
        root = int(row["root"])
        check(root + 0x20 <= len(data), f"CompassIconClass outside data: {row['name']}")
        record = data[root:root + 0x20]
        icon, radius, inworld = struct.unpack_from("<QQQ", record, 0)
        scale = struct.unpack_from("<f", record, 24)[0]
        compass_classes.append({
            "name": row["name"],
            "uid": f"{int(row['uid']):016X}",
            "root": f"0x{root:X}",
            "IconName": f"{icon:016X}",
            "RadiusIconName": f"{radius:016X}",
            "InWorld_tMPIcon_Name": f"{inworld:016X}",
            "IconScale": scale,
            "IsMainQuest": bool(record[28]),
            "icon_value": icon,
            "inworld_value": inworld,
        })

    inworld_exports = []
    discovered = sorted(row["name"] for row in exports if row["name"].startswith("COMPASS_INWORLD_"))
    for name in discovered:
        row = by_name[name]
        root = int(row["root"])
        end = next_distinct_root(exports, root, len(data))
        check(root < end <= len(data), f"invalid object span for {name}: {root:#x}..{end:#x}")
        record = data[root:end]
        refs = [c for c in compass_classes if int(c["inworld_value"]) == int(row["uid"])]
        rel = []
        for r in relocs:
            field = int(r["field"])
            if root <= field < end:
                owner = owning_export(exports_sorted, int(r["target"]))
                rel.append({
                    "field": f"0x{field:X}",
                    "field_relative": f"0x{field-root:X}",
                    "target": f"0x{int(r['target']):X}",
                    "target_owner": None if owner is None else owner["name"],
                    "target_owner_root": None if owner is None else f"0x{int(owner['root']):X}",
                })

        correlations = []
        for c in refs:
            icon_value = int(c["icon_value"])
            hits = u64_hits(record, icon_value)
            correlations.append({
                "class": c["name"],
                "class_IconName": f"{icon_value:016X}",
                "IconName_hits_in_inworld_record": [f"0x{x:X}" for x in hits],
                "exactly_one_icon_hit": len(hits) == 1,
            })

        inworld_exports.append({
            "name": name,
            "uid": f"{int(row['uid']):016X}",
            "type_id": f"0x{int(row['type_id']):X}",
            "root": f"0x{root:X}",
            "end": f"0x{end:X}",
            "span_bytes": len(record),
            "record_hex": record.hex(),
            "relocations": rel,
            "referencing_compass_classes": [c["name"] for c in refs],
            "class_icon_correlations": correlations,
            "custom_raven_hud_hash_hits": [f"0x{x:X}" for x in u64_hits(record, RAVEN_HUD_HASH)],
        })

    target_rows = {row["name"]: row for row in inworld_exports if row["name"] in TARGET_NAMES}
    dock = target_rows.get("COMPASS_INWORLD_DOCK")
    side = target_rows.get("COMPASS_INWORLD_SIDE")
    main = target_rows.get("COMPASS_INWORLD_MAIN")

    pair = None
    if dock is not None and side is not None:
        db = bytes.fromhex(dock["record_hex"])
        sb = bytes.fromhex(side["record_hex"])
        diffs = [i for i, (a, b) in enumerate(zip(db, sb)) if a != b]
        pair = {
            "same_type": dock["type_id"] == side["type_id"],
            "same_span": len(db) == len(sb),
            "dock_span": len(db),
            "side_span": len(sb),
            "byte_diff_offsets_common_span": [f"0x{x:X}" for x in diffs],
            "byte_diff_count_common_span": len(diffs),
        }

    def has_single_correlated_icon(row: dict | None) -> bool:
        if row is None or len(row["class_icon_correlations"]) != 1:
            return False
        return bool(row["class_icon_correlations"][0]["exactly_one_icon_hit"])

    clone_gate = {
        "dock_export_present": dock is not None,
        "side_export_present": side is not None,
        "main_export_present": main is not None,
        "dock_referenced_by_compass_class": bool(dock and dock["referencing_compass_classes"]),
        "side_referenced_by_compass_class": bool(side and side["referencing_compass_classes"]),
        "dock_record_contains_its_class_IconName_exactly_once": has_single_correlated_icon(dock),
        "side_record_contains_its_class_IconName_exactly_once": has_single_correlated_icon(side),
        "dock_side_same_type": bool(pair and pair["same_type"]),
        "dock_side_same_span": bool(pair and pair["same_span"]),
    }
    clone_gate["ready_to_design_offline_raven_inworld_clone"] = all([
        clone_gate["dock_export_present"],
        clone_gate["side_export_present"],
        clone_gate["dock_referenced_by_compass_class"],
        clone_gate["side_referenced_by_compass_class"],
        clone_gate["dock_record_contains_its_class_IconName_exactly_once"],
        clone_gate["side_record_contains_its_class_IconName_exactly_once"],
        clone_gate["dock_side_same_type"],
        clone_gate["dock_side_same_span"],
    ])

    report = {
        "schema": 1,
        "result": "READ_ONLY_RAVEN_INWORLD_EXPORT_TOPOLOGY",
        "source": str(source),
        "source_sha256": live_sha,
        "discovered_inworld_exports": discovered,
        "compass_classes": [{k: v for k, v in c.items() if k not in ("icon_value", "inworld_value")} for c in compass_classes],
        "inworld_exports": inworld_exports,
        "dock_side_comparison": pair,
        "clone_gate": clone_gate,
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
    }

    out = args.output.resolve()
    check(not out.is_relative_to(game), "report must stay outside game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == raw, "wad_r_perm.dcb changed during read-only inspection")

    print(report["result"])
    print(f"  source SHA256: {live_sha}")
    print(f"  COMPASS_INWORLD_* exports: {len(discovered)}")
    for label in TARGET_NAMES:
        row = target_rows.get(label)
        if row is None:
            print(f"  {label}: MISSING")
            continue
        corr = row["class_icon_correlations"]
        icon_summary = ", ".join(
            f"{c['class']} IconName={c['class_IconName']} hit={c['IconName_hits_in_inworld_record']}"
            for c in corr
        ) or "no class correlation"
        print(f"  {label}: uid={row['uid']} type={row['type_id']} root={row['root']} span={row['span_bytes']} relocs={len(row['relocations'])}")
        print(f"    {icon_summary}")
    if pair is not None:
        print(f"  Dock/SIDE same type: {str(pair['same_type']).lower()}")
        print(f"  Dock/SIDE same span: {str(pair['same_span']).lower()}")
        print(f"  Dock/SIDE byte diffs: {pair['byte_diff_count_common_span']}")
    print(f"  Raven clone design gate: {'READY' if clone_gate['ready_to_design_offline_raven_inworld_clone'] else 'NOT_READY'}")
    print("  game files written: false")
    print(f"  output: {out}")


if __name__ == "__main__":
    main()
