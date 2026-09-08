"""Validate the dedicated Raven compass HUD WAD and DCB candidates together.

No game files are written. Both candidate binaries are recomputed from the
current pinned live sources and must match the on-disk offline candidates
byte-for-byte before the pair is declared ready for a reversible install gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import compass_hud_physical_groups as hud

check = hud.check
REPO = hud.REPO
WAD = hud.load_module("build-raven-compass-hud-four-payload.py")
DCB = hud.load_module("build-raven-compass-hud-dcb-offline.py")

RESULT = "OFFLINE_RAVEN_COMPASS_HUD_COMBINED_CONTRACT_PASSED"
CONCLUSION = "RAVEN_COMPASS_HUD_RUNTIME_CANDIDATE_READY"
DEFAULT_WAD = REPO / "build/v0.10.4/raven-compass-hud-four-payload/r_ui.wad"
DEFAULT_DCB = REPO / "build/v0.10.4/raven-compass-hud-four-payload/wad_r_perm.dcb"
DEFAULT_REPORT = REPO / "archive/field-logs/completionist-v104-raven-compass-hud-combined-offline.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--wad-candidate", type=Path, default=DEFAULT_WAD)
    parser.add_argument("--dcb-candidate", type=Path, default=DEFAULT_DCB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    game = args.game_root.resolve()
    live_wad = game / "exec/wad/pc_le/r_ui.wad"
    live_dcb = game / "exec/dc/pc_le/wad_r_perm.dcb"
    wad_source = live_wad.read_bytes()
    dcb_source = live_dcb.read_bytes()

    wad_path = args.wad_candidate.resolve()
    dcb_path = args.dcb_candidate.resolve()
    report_path = hud.safe_output(args.report, REPO / "archive/field-logs")
    for path in (wad_path, dcb_path, report_path):
        check(not path.is_relative_to(game), f"offline candidate/report overlaps game tree: {path}")
    check(wad_path.is_file(), f"WAD candidate missing: {wad_path}")
    check(dcb_path.is_file(), f"DCB candidate missing: {dcb_path}")
    check(wad_path.stat().st_nlink == 1 and dcb_path.stat().st_nlink == 1,
          "candidate files must not be hard-linked")

    actual_wad = wad_path.read_bytes()
    actual_dcb = dcb_path.read_bytes()
    expected_wad, wad_report = WAD.build_candidate(wad_source)
    expected_dcb, dcb_report = DCB.build_candidate(dcb_source)
    check(actual_wad == expected_wad, "offline r_ui.wad candidate differs from recomputed candidate")
    check(actual_dcb == expected_dcb, "offline wad_r_perm.dcb candidate differs from recomputed candidate")

    helper = hud.BASE.load_helper()
    wad_records = helper.parse_wad(actual_wad)
    check(helper.serialize_wad(wad_records) == actual_wad, "candidate WAD round-trip differs")
    roots = [
        row for row in wad_records
        if row["kind"] == 1 and row["data"] and row["name"].lower() == WAD.NEW_ROOT.lower()
    ]
    check(len(roots) == 1, "dedicated HUD root missing or duplicated")
    root = roots[0]
    check(root["id"] == WAD.NEW_ROOT_ID, "dedicated HUD root resource ID changed")
    check(helper.name_hash("goCompletionistRavenHUD") == DCB.HUD_RESOURCE_HASH,
          "WAD/DCB HUD name hash contract changed")
    check(wad_report["architecture"]["hud_IconName_hash"] == f"{DCB.HUD_RESOURCE_HASH:016X}",
          "WAD report HUD hash differs from DCB builder")
    check(dcb_report["visual_isolation"]["hud_IconName_after"] == f"{DCB.HUD_RESOURCE_HASH:016X}",
          "DCB report does not bind dedicated HUD root")
    check(dcb_report["visual_isolation"]["InWorld_tMPIcon_Name"] == f"{DCB.DOCK_INWORLD_HASH:016X}",
          "DCB InWorld binding changed")
    check(wad_report["validation"]["local_scp_preserved_byte_exact"], "local SCP proof missing")
    check(wad_report["clone_accounting"]["physical_records_delta"] == 13, "WAD physical delta changed")
    check(wad_report["clone_accounting"]["payload_records_delta"] == 4, "WAD payload delta changed")
    check(wad_report["clone_accounting"]["wad_r_ui_accounting_delta"] == 3, "WAD accounting delta changed")

    check(live_wad.read_bytes() == wad_source, "live r_ui.wad changed during combined validation")
    check(live_dcb.read_bytes() == dcb_source, "live wad_r_perm.dcb changed during combined validation")

    report = {
        "result": RESULT,
        "conclusion": CONCLUSION,
        "contract": {
            "hud_resource_name": "goCompletionistRavenHUD",
            "hud_resource_hash": f"{DCB.HUD_RESOURCE_HASH:016X}",
            "wad_root_name": WAD.NEW_ROOT,
            "wad_root_id": WAD.NEW_ROOT_ID.hex(),
            "dcb_class": "CompletionistRaven",
            "dcb_IconName": f"{DCB.HUD_RESOURCE_HASH:016X}",
            "dcb_InWorld_tMPIcon_Name": f"{DCB.DOCK_INWORLD_HASH:016X}",
            "map_GameObject_used_as_HUD_root": False,
            "local_SCP_preserved": True,
            "raven_material_reused": WAD.RAVEN_MATERIAL,
            "stock_dock_mesh_reused": WAD.SOURCE_MESH,
            "shared_compass_reused": WAD.SHARED_COMPASS,
        },
        "wad_candidate": {
            "path": str(wad_path),
            "sha256": hud.BASE.sha256(actual_wad),
            "matches_recomputed_candidate": True,
            "physical_records_delta": 13,
            "payload_records_delta": 4,
            "wad_r_ui_accounting_delta": 3,
        },
        "dcb_candidate": {
            "path": str(dcb_path),
            "sha256": DCB.load_base().sha256(actual_dcb),
            "matches_recomputed_candidate": True,
            "only_CompletionistRaven_IconName_visual_field_changed": True,
            "real_DockPoint_record_byte_identical": True,
        },
        "live_sources": {
            "r_ui_wad_sha256": hud.BASE.sha256(wad_source),
            "wad_r_perm_dcb_sha256": DCB.load_base().sha256(dcb_source),
            "unchanged_during_validation": True,
        },
        "safety": {
            "game_files_written": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "runtime_test_performed": False,
            "installed": False,
        },
        "ready_for_reversible_runtime_install": True,
        "ready_for_runtime_test_after_reversible_install": True,
        "next_gate": (
            "Use a separate reversible installer that requires these exact candidate hashes, "
            "backs up both live files, installs both candidates as one pair, and can restore both. "
            "Do not reuse the failed map-GameObject HUD installer."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    check(live_wad.read_bytes() == wad_source, "live r_ui.wad changed after combined report write")
    check(live_dcb.read_bytes() == dcb_source, "live wad_r_perm.dcb changed after combined report write")

    print(RESULT)
    print(f"  conclusion:          {CONCLUSION}")
    print("  WAD clone:           +13 physical / +4 payload / +3 accounting")
    print("  SCP binding:         LOCAL_SCP_REQUIRED, preserved byte-exact")
    print(f"  DCB IconName:        {DCB.HUD_RESOURCE_HASH:016X}")
    print(f"  DCB InWorld:         {DCB.DOCK_INWORLD_HASH:016X} (unchanged)")
    print("  game files written:  false")
    print("  next:                reversible two-file install gate")
    print(f"  report:              {report_path}")


if __name__ == "__main__":
    main()
