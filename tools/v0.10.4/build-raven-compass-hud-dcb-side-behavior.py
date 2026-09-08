"""Build an OFFLINE CompletionistRaven class with SIDE behavior and Raven HUD art.

This is the likely follow-up if the stock SIDE A/B runtime control proves that
quest-style class behavior is what enables routed/native compass presentation.
It does not install anything. The custom class keeps its own Raven IconName,
while every remaining 0x20 CompassIconClass field is copied byte-for-byte from
stock SIDE.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct

import compass_hud_physical_groups as hud

check = hud.check
REPO = hud.REPO
BASE_FILE = "build-raven-compass-hud-dcb-offline.py"
RESULT = "OFFLINE_COMPLETIONIST_RAVEN_SIDE_BEHAVIOR_DCB_BUILT"
OUTPUT_DCB = REPO / "build/v0.10.4/raven-compass-hud-side-behavior/wad_r_perm.dcb"
OUTPUT_REPORT = REPO / "archive/field-logs/completionist-v104-raven-compass-hud-side-behavior-dcb.json"

HUD_RESOURCE_NAME = "goCompletionistRavenHUD"
HUD_RESOURCE_HASH = 0x45E5C7943749F81C
SIDE_RADIUS_HASH = 0xE6B82F258C8DFD49
SIDE_INWORLD_HASH = 0x0E24CF72E968ACF0


def load_module(filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_candidate(stock_raw: bytes) -> tuple[bytes, dict]:
    wrapper = load_module(BASE_FILE)
    icon_candidate, icon_report = wrapper.build_candidate(stock_raw)

    hud_art = wrapper.load_base()
    packed = hud_art.load_base()
    legacy = packed.load_legacy()
    chunks = legacy.parse_chunks(icon_candidate)
    data_chunk = legacy.one(chunks, 12)
    exports_chunk = legacy.one(chunks, 13)
    data = bytes(data_chunk["payload"])
    _header, exports, tail = legacy.parse_exports(exports_chunk["payload"])
    by_name = {row["name"]: row for row in exports}
    raven = by_name.get(legacy.NEW_CLASS)
    side = by_name.get("SIDE")
    dock = by_name.get("DockPoint")
    check(raven is not None and side is not None and dock is not None, "required CompassIconClass export missing")

    rr, sr, dr = int(raven["root"]), int(side["root"]), int(dock["root"])
    size = 0x20
    for label, root in (("Raven", rr), ("SIDE", sr), ("DockPoint", dr)):
        check(0 <= root <= len(data) - size, f"{label} record outside DCB data")

    raven_before = data[rr:rr + size]
    side_record = data[sr:sr + size]
    dock_record = data[dr:dr + size]
    icon_before = struct.unpack_from("<Q", raven_before, 0)[0]
    check(icon_before == HUD_RESOURCE_HASH, "dedicated Raven HUD IconName missing before SIDE behavior transform")
    check(struct.unpack_from("<Q", raven_before, 8)[0] == 0, "Raven source RadiusIconName is no longer Dock-shaped")
    check(struct.unpack_from("<Q", raven_before, 16)[0] == wrapper.DOCK_INWORLD_HASH,
          "Raven source InWorld binding is no longer Dock-shaped")
    check(struct.unpack_from("<Q", side_record, 8)[0] == SIDE_RADIUS_HASH, "stock SIDE radius hash changed")
    check(struct.unpack_from("<Q", side_record, 16)[0] == SIDE_INWORLD_HASH, "stock SIDE in-world hash changed")
    check(struct.unpack_from("<f", side_record, 24)[0] == 1.0, "stock SIDE scale changed")
    check(side_record[28] == 0, "stock SIDE IsMainQuest changed")

    patched_data = bytearray(data)
    # Keep the dedicated Raven IconName at +0x00. Copy all behavioral/presentation
    # fields after it from stock SIDE, including radius, in-world, scale, bool and tail.
    patched_data[rr + 8:rr + size] = side_record[8:size]
    candidate = legacy.build_file(chunks, {12: bytes(patched_data)})

    out_chunks = legacy.parse_chunks(candidate)
    out_data = bytes(legacy.one(out_chunks, 12)["payload"])
    _oh, out_exports, out_tail = legacy.parse_exports(legacy.one(out_chunks, 13)["payload"])
    check(out_tail == tail, "export string tail changed")
    out_by_name = {row["name"]: row for row in out_exports}
    out_raven = out_data[rr:rr + size]
    out_side = out_data[sr:sr + size]
    out_dock = out_data[dr:dr + size]

    check(struct.unpack_from("<Q", out_raven, 0)[0] == HUD_RESOURCE_HASH, "Raven HUD IconName changed")
    check(out_raven[8:size] == side_record[8:size], "Raven non-IconName fields do not exactly match SIDE")
    check(out_side == side_record, "real SIDE class changed")
    check(out_dock == dock_record, "real DockPoint class changed")
    check([int(e["uid"]) for e in out_exports] == [int(e["uid"]) for e in exports], "export UID order changed")
    for name in (legacy.NEW_CLASS, "SIDE", "DockPoint"):
        before = by_name[name]
        after = out_by_name[name]
        check(all(int(before[k]) == int(after[k]) for k in ("root", "type_id", "uid", "string_offset")),
              f"{name} export metadata changed")
    for kind in (11, 13, 14, 35, 15):
        check(legacy.one(chunks, kind)["payload"] == legacy.one(out_chunks, kind)["payload"],
              f"non-data chunk {kind} changed")

    changed = [i for i, (a, b) in enumerate(zip(data, out_data)) if a != b]
    check(changed, "SIDE behavior transform produced no changes")
    check(all(rr + 8 <= i < rr + size for i in changed),
          "SIDE behavior transform changed data outside CompletionistRaven non-IconName fields")

    report = {
        "result": RESULT,
        "source_sha256": legacy.EXPECTED,
        "icon_only_candidate_sha256": wrapper.load_base().sha256(icon_candidate),
        "candidate_sha256": wrapper.load_base().sha256(candidate),
        "class": legacy.NEW_CLASS,
        "class_uid": f"{int(raven['uid']):016X}",
        "hud_resource_name": HUD_RESOURCE_NAME,
        "IconName": f"{HUD_RESOURCE_HASH:016X}",
        "behavior_donor": "SIDE",
        "RadiusIconName": f"{SIDE_RADIUS_HASH:016X}",
        "InWorld_tMPIcon_Name": f"{SIDE_INWORLD_HASH:016X}",
        "IconScale": struct.unpack_from("<f", out_raven, 24)[0],
        "IsMainQuest": bool(out_raven[28]),
        "all_non_IconName_class_bytes_equal_stock_SIDE": True,
        "real_SIDE_record_byte_identical": True,
        "real_DockPoint_record_byte_identical": True,
        "export_uid_order_unchanged": True,
        "changed_data_offsets": [f"0x{x:X}" for x in changed],
        "changes_confined_to_CompletionistRaven_behavior_fields": True,
        "game_files_written": False,
        "installed": False,
        "ready_for_runtime_install": False,
        "gate": "Only consider runtime install after the stock SIDE A/B control proves routed/native behavior.",
        "prior_icon_only_report": icon_report,
    }
    return candidate, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output-dcb", type=Path, default=OUTPUT_DCB)
    ap.add_argument("--report", type=Path, default=OUTPUT_REPORT)
    args = ap.parse_args()

    wrapper = load_module(BASE_FILE)
    hud_art = wrapper.load_base()
    packed = hud_art.load_base()
    legacy = packed.load_legacy()
    source = args.game_root.resolve() / "exec/dc/pc_le/wad_r_perm.dcb"
    raw = source.read_bytes()
    check(wrapper.load_base().sha256(raw) == legacy.EXPECTED,
          "wad_r_perm.dcb is not the researched stock source; build from clean baseline only")

    output = hud.safe_output(args.output_dcb, REPO / "build/v0.10.4")
    report_path = hud.safe_output(args.report, REPO / "archive/field-logs")
    check(not output.is_relative_to(args.game_root.resolve()), "offline output overlaps game tree")
    candidate, report = build_candidate(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == raw, "source wad_r_perm.dcb changed during offline build")

    print(RESULT)
    print("  Raven IconName: custom dedicated HUD")
    print("  behavior donor: SIDE")
    print("  real SIDE/DockPoint changed: false")
    print("  game files written: false")
    print("  runtime install authorized: false (await A/B control)")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
