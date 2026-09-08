"""Build the offline CompletionistRaven DCB binding for the dedicated HUD root.

This reuses the runtime-proven UID-sorted CompletionistRaven registration
builder. Only CompletionistRaven.IconName is changed from stock DockPoint to
goCompletionistRavenHUD. InWorld_tMPIcon_Name remains stock Dock.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import compass_hud_physical_groups as hud

check = hud.check
REPO = hud.REPO
BASE_NAME = "build-packed-raven-compass-hud-art-v1.py"
RESULT = "OFFLINE_PACKED_COMPLETIONIST_RAVEN_DEDICATED_HUD_BINDING_BUILT"
HUD_RESOURCE_NAME = "goCompletionistRavenHUD"
HUD_RESOURCE_HASH = 0x45E5C7943749F81C
DOCK_HUD_HASH = 0x82F0296748C7393D
DOCK_INWORLD_HASH = 0x0E24C47DE2F769CA

OUTPUT_DCB = REPO / "build/v0.10.4/raven-compass-hud-four-payload/wad_r_perm.dcb"
OUTPUT_REPORT = REPO / "archive/field-logs/completionist-v104-raven-compass-hud-dcb-offline.json"


def load_base():
    path = Path(__file__).with_name(BASE_NAME)
    spec = importlib.util.spec_from_file_location("completionist_hud_art_v1_reused", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_candidate(stock_raw: bytes) -> tuple[bytes, dict]:
    base = load_base()
    base.RAVEN_UI_NAME = HUD_RESOURCE_NAME
    base.RAVEN_HUD_ICON_HASH = HUD_RESOURCE_HASH
    base.RESULT = RESULT
    candidate, report, legacy = base.build_hud_candidate(stock_raw)

    check(legacy.name_hash(HUD_RESOURCE_NAME) == HUD_RESOURCE_HASH, "dedicated HUD name hash changed")
    check(report["result"] == RESULT, "wrapped DCB builder result changed")
    visual = report["visual_isolation"]
    check(visual["hud_IconName_before"] == f"{DOCK_HUD_HASH:016X}", "DCB source IconName changed")
    check(visual["hud_IconName_after"] == f"{HUD_RESOURCE_HASH:016X}", "dedicated HUD IconName not applied")
    check(visual["InWorld_tMPIcon_Name"] == f"{DOCK_INWORLD_HASH:016X}", "InWorld binding changed")
    check(visual["changed_bytes_confined_to_raven_IconName"], "DCB transform escaped IconName field")
    check(visual["real_DockPoint_record_byte_identical"], "real DockPoint class changed")

    report["resource_contract"] = {
        "hud_resource_name": HUD_RESOURCE_NAME,
        "hud_resource_hash": f"{HUD_RESOURCE_HASH:016X}",
        "resource_kind": "dedicated_compass_HUD_GameObject_root",
        "resource_expected_in": "r_ui.wad offline four-payload candidate",
        "map_GameObject_reused_as_HUD_root": False,
        "stock_DockPoint_resource_modified": False,
        "working_map_Raven_resource_modified": False,
    }
    report["expected_runtime"] = {
        "map_marker": "existing Raven map artwork unchanged",
        "compass_hud": "dedicated goCompletionistRavenHUD chain",
        "floating_inworld": "DockPoint artwork intentionally unchanged for isolation",
    }
    report["ready_for_combined_offline_contract_gate"] = True
    report["ready_for_runtime_test"] = False
    report["next_gate"] = (
        "Validate this DCB byte-for-byte together with the four-payload r_ui.wad candidate. "
        "Do not install either candidate before the combined contract gate passes."
    )
    return candidate, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output-dcb", type=Path, default=OUTPUT_DCB)
    parser.add_argument("--report", type=Path, default=OUTPUT_REPORT)
    args = parser.parse_args()

    base = load_base()
    packed = base.load_base()
    legacy = packed.load_legacy()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    stock_raw = source.read_bytes()
    digest = base.sha256(stock_raw)
    check(digest == legacy.EXPECTED, f"wad_r_perm.dcb is not the researched stock file: {digest}")

    output = hud.safe_output(args.output_dcb, REPO / "build/v0.10.4")
    report_path = hud.safe_output(args.report, REPO / "archive/field-logs")
    check(not output.is_relative_to(game) and not report_path.is_relative_to(game),
          "offline DCB outputs overlap game tree")

    candidate, report = build_candidate(stock_raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output_dcb"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == stock_raw, "source wad_r_perm.dcb changed during offline build")

    print(RESULT)
    print(f"  HUD IconName:       {DOCK_HUD_HASH:016X} -> {HUD_RESOURCE_HASH:016X}")
    print(f"  HUD resource:       {HUD_RESOURCE_NAME}")
    print(f"  in-world:           {DOCK_INWORLD_HASH:016X} (unchanged)")
    print("  map Raven touched:  false")
    print("  game files written: false")
    print("  runtime test:       NOT SAFE YET")
    print(f"  candidate:          {output}")
    print(f"  report:             {report_path}")


if __name__ == "__main__":
    main()
