"""Build an OFFLINE HUD-only Raven CompassIconClass artwork candidate.

The UID-sorted packed CompletionistRaven class is now runtime-proven. This
follow-up changes only that class's HUD IconName field to the already-proven
`goMapIconCompletionistRaven` GameObject identity used by the working Raven map
art. The floating in-world marker deliberately remains DockPoint for this
isolation test.

No game files, saves, progression, marker state, map artwork resources, or stock
DockPoint data are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

BASE_BUILDER = "build-packed-raven-compass-class-v2.py"
RESULT = "OFFLINE_PACKED_COMPLETIONIST_RAVEN_HUD_ART_BUILT"
RAVEN_UI_NAME = "goMapIconCompletionistRaven"
RAVEN_HUD_ICON_HASH = 0x584F31DC8BD6E738
DOCK_HUD_ICON_HASH = 0x82F0296748C7393D
DOCK_INWORLD_HASH = 0x0E24C47DE2F769CA


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_base():
    path = Path(__file__).with_name(BASE_BUILDER)
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("completionist_packed_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_hud_candidate(stock_raw: bytes):
    base = load_base()
    registered, base_report, legacy = base.build_corrected(stock_raw)

    # The existing dedicated map GameObject already resolves at this exact hash.
    if legacy.name_hash(RAVEN_UI_NAME) != RAVEN_HUD_ICON_HASH:
        raise ValueError("goMapIconCompletionistRaven hash contract changed")
    if legacy.name_hash("goboatdock") != DOCK_HUD_ICON_HASH:
        raise ValueError("Dock HUD name hash contract changed")
    if legacy.name_hash("COMPASS_INWORLD_DOCK") != DOCK_INWORLD_HASH:
        raise ValueError("Dock in-world hash contract changed")

    chunks = legacy.parse_chunks(registered)
    data_chunk = legacy.one(chunks, 12)
    export_chunk = legacy.one(chunks, 13)
    reloc_chunk = legacy.one(chunks, 15)
    data_before = bytes(data_chunk["payload"])
    _h8, exports, _tail = legacy.parse_exports(export_chunk["payload"])
    by_name = {e["name"]: e for e in exports}

    raven = by_name.get(legacy.NEW_CLASS)
    dock = by_name.get(legacy.SOURCE_CLASS)
    if raven is None or dock is None:
        raise ValueError("CompletionistRaven or DockPoint export missing")
    if int(raven["root"]) != legacy.INSERT_AT or int(raven["type_id"]) != legacy.TYPE_ID:
        raise ValueError("CompletionistRaven root/type no longer matches proven candidate")
    if int(dock["root"]) != 0x4E2BB0 or int(dock["type_id"]) != legacy.TYPE_ID:
        raise ValueError("DockPoint root/type changed")

    rr = int(raven["root"])
    dr = int(dock["root"])
    size = int(legacy.RECORD_SIZE)
    raven_before = data_before[rr:rr + size]
    dock_record = data_before[dr:dr + size]
    if len(raven_before) != size or len(dock_record) != size:
        raise ValueError("short CompassIconClass record")
    if raven_before != dock_record:
        raise ValueError("proven registration candidate no longer starts as a DockPoint clone")

    icon_before, radius_before, inworld_before = struct.unpack_from("<QQQ", raven_before, 0)
    scale_before = struct.unpack_from("<f", raven_before, 0x18)[0]
    main_before = raven_before[0x1C]
    if icon_before != DOCK_HUD_ICON_HASH:
        raise ValueError(f"unexpected pre-HUD IconName {icon_before:016X}")
    if radius_before != 0 or inworld_before != DOCK_INWORLD_HASH:
        raise ValueError("pre-HUD Radius/InWorld fields differ from DockPoint")
    if scale_before != 1.0 or main_before != 0:
        raise ValueError("pre-HUD scale/main-quest fields differ from DockPoint")

    patched_data = bytearray(data_before)
    struct.pack_into("<Q", patched_data, rr + 0x00, RAVEN_HUD_ICON_HASH)

    candidate = legacy.build_file(chunks, {12: bytes(patched_data)})
    out_chunks = legacy.parse_chunks(candidate)
    out_data = bytes(legacy.one(out_chunks, 12)["payload"])
    _oh8, out_exports, out_tail = legacy.parse_exports(legacy.one(out_chunks, 13)["payload"])
    out_by_name = {e["name"]: e for e in out_exports}

    # Preserve the proven UID-sorted registration index and every non-data chunk.
    out_uids = [int(e["uid"]) for e in out_exports]
    if not base.strictly_increasing(out_uids):
        raise ValueError("HUD candidate lost strict UID export ordering")
    if out_tail != _tail:
        raise ValueError("export string tail changed")
    for kind in (11, 13, 14, 35, 15):
        if legacy.one(chunks, kind)["payload"] != legacy.one(out_chunks, kind)["payload"]:
            raise ValueError(f"chunk {kind} changed in HUD-only transform")

    raven_after_export = out_by_name.get(legacy.NEW_CLASS)
    if raven_after_export is None:
        raise ValueError("CompletionistRaven export disappeared")
    if any(int(raven_after_export[k]) != int(raven[k]) for k in ("root", "type_id", "string_offset", "uid")):
        raise ValueError("CompletionistRaven export semantics changed")

    raven_after = out_data[rr:rr + size]
    dock_after = out_data[dr:dr + size]
    icon_after, radius_after, inworld_after = struct.unpack_from("<QQQ", raven_after, 0)
    scale_after = struct.unpack_from("<f", raven_after, 0x18)[0]
    main_after = raven_after[0x1C]
    if icon_after != RAVEN_HUD_ICON_HASH:
        raise ValueError("Raven HUD IconName was not applied")
    if radius_after != radius_before or inworld_after != DOCK_INWORLD_HASH:
        raise ValueError("Radius/InWorld changed during HUD-only transform")
    if scale_after != scale_before or main_after != main_before:
        raise ValueError("scale/main-quest fields changed during HUD-only transform")
    if dock_after != dock_record:
        raise ValueError("real DockPoint record changed")

    changed = [i for i, (a, b) in enumerate(zip(data_before, out_data)) if a != b]
    if not changed:
        raise ValueError("HUD-only transform produced no data change")
    if any(not (rr <= i < rr + 8) for i in changed):
        raise ValueError("HUD-only transform changed bytes outside CompletionistRaven.IconName")

    # Relocation table and all relocation targets remain valid and unchanged.
    base_relocs = legacy.parse_relocations(reloc_chunk["payload"], data_before)
    out_relocs = legacy.parse_relocations(legacy.one(out_chunks, 15)["payload"], out_data)
    if base_relocs != out_relocs:
        raise ValueError("relocation semantics changed in HUD-only transform")

    report = {
        "result": RESULT,
        "game_files_written": False,
        "installed": False,
        "save_progression_marker_state_written": False,
        "source_sha256": legacy.EXPECTED,
        "base_registration_candidate_sha256": sha256(registered),
        "candidate_sha256": sha256(candidate),
        "candidate_bytes": len(candidate),
        "class": {
            "name": legacy.NEW_CLASS,
            "uid": f"{int(raven['uid']):016X}",
            "root": f"0x{rr:X}",
            "type_id": f"0x{int(raven['type_id']):X}",
            "export_index": next(i for i, e in enumerate(out_exports) if e["name"] == legacy.NEW_CLASS),
            "export_uid_order_strictly_increasing": True,
        },
        "visual_isolation": {
            "hud_IconName_before": f"{icon_before:016X}",
            "hud_IconName_after": f"{icon_after:016X}",
            "hud_resource_name": RAVEN_UI_NAME,
            "RadiusIconName": f"{radius_after:016X}",
            "InWorld_tMPIcon_Name": f"{inworld_after:016X}",
            "inworld_expected_resource": "COMPASS_INWORLD_DOCK",
            "IconScale": scale_after,
            "IsMainQuest": bool(main_after),
            "changed_data_byte_offsets": [f"0x{x:X}" for x in changed],
            "changed_bytes_confined_to_raven_IconName": True,
            "real_DockPoint_record_byte_identical": True,
        },
        "resource_contract": {
            "existing_proven_raven_ui_identity": RAVEN_UI_NAME,
            "existing_proven_raven_ui_hash": f"{RAVEN_HUD_ICON_HASH:016X}",
            "new_ui_resources_created": False,
            "map_raven_resource_modified": False,
            "real_dock_resource_modified": False,
        },
        "expected_runtime": {
            "map_marker": "existing Raven artwork unchanged",
            "compass_hud": "Raven artwork via goMapIconCompletionistRaven",
            "floating_inworld": "DockPoint artwork intentionally unchanged for isolation",
        },
        "safety": {
            "game_directory_written": False,
            "save_state_written": False,
            "progression_state_written": False,
            "map_marker_state_written": False,
            "map_raven_artwork_touched": False,
            "real_dock_visuals_touched": False,
        },
        "next_gate": (
            "Run a reversible HUD-only runtime proof. Require CompletionistRaven to remain manager-verified; "
            "visually confirm the compass glyph changes to Raven while the floating in-world marker remains DockPoint."
        ),
    }
    return candidate, report, legacy


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    base = load_base()
    legacy = base.load_legacy()
    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)
    stock_raw = source.read_bytes()
    digest = sha256(stock_raw)
    if digest != legacy.EXPECTED:
        raise ValueError(f"wad_r_perm.dcb is not the researched stock file: {digest}")

    output = args.output.resolve()
    report_path = args.report.resolve()
    if output.is_relative_to(game) or report_path.is_relative_to(game):
        raise ValueError("offline candidate/report must stay outside the game directory")

    candidate, report, _legacy = build_hud_candidate(stock_raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if source.read_bytes() != stock_raw:
        raise ValueError("source wad_r_perm.dcb changed during offline build")

    print(RESULT)
    print("  class:            CompletionistRaven")
    print("  HUD IconName:     82F0296748C7393D -> 584F31DC8BD6E738")
    print("  HUD resource:     goMapIconCompletionistRaven")
    print("  in-world visual:  COMPASS_INWORLD_DOCK (unchanged for isolation)")
    print(f"  candidate SHA256: {sha256(candidate)}")
    print(f"  output:           {output}")
    print(f"  report:           {report_path}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
