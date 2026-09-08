"""Fail-closed v3 preflight. Full source groups conflict with exact +3/+2 gate.

Test edits in memory. Exit 3 means structural block. No WAD/DCB candidate write.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import compass_hud_physical_groups as hud

BASE = hud.BASE
check = hud.check
INSPECTOR = hud.load_module("inspect-compass-hud-physical-groups.py")
BLOCKED_EXIT_CODE = 3


def preview_clones(records: list[dict], inspection: dict) -> dict:
    helper = BASE.load_helper()
    dock = inspection["classes"]["DockPoint"]
    plans = {
        "model": (BASE.NEW_MODEL, BASE.NEW_MODEL_ID,
                  {2: (BASE.SOURCE_MATERIAL_ID, BASE.RAVEN_MATERIAL, BASE.RAVEN_MATERIAL_ID)}, {}),
        "prototype": (BASE.NEW_PROTO, BASE.NEW_PROTO_ID,
                      {2: (BASE.SOURCE_MODEL_ID, BASE.NEW_MODEL, BASE.NEW_MODEL_ID)},
                      {0x3A8: (BASE.SOURCE_PROTO_ID, BASE.NEW_PROTO_ID)}),
        "root": (BASE.NEW_ROOT, BASE.NEW_ROOT_ID, {},
                 {0xC: (BASE.SOURCE_PROTO_ID, BASE.NEW_PROTO_ID)}),
    }
    previews = {}
    for role, (new_name, new_id, links, inline) in plans.items():
        group = dock[role]
        start, end, target = group["start"], group["end"], group["target_record_index"]
        source_bytes = helper.serialize_wad(records[start:end + 1])
        clone = hud.clone_resource(records, target, new_name, new_id, links=links, inline=inline)
        clone_bytes = helper.serialize_wad(clone)
        parsed = helper.parse_wad(clone_bytes)
        check(helper.serialize_wad(parsed) == clone_bytes, f"{role}: clone group round-trip failed")
        shape = hud.validate_hud_group(parsed, target - start, role)
        check(shape["roles"] == group["roles"], f"{role}: cloned roles changed")
        check(parsed[target - start]["name"] == new_name and parsed[target - start]["id"] == new_id,
              f"{role}: clone identity differs")
        if role == "root":
            check(parsed[1]["data"][0xC:0x1C] == BASE.NEW_PROTO_ID, "new root prototype differs")
            check(parsed[1]["data"][0x54:0x64] == BASE.SHARED_COMPASS_ID, "shared compass differs")
            check(bytes(parsed[1]["data"][0x1C:0x54]) == new_name.encode("ascii").ljust(56, b"\0"),
                  "new root loader name differs")
        for relative, (_, name, rid) in links.items():
            check(parsed[relative]["name"] == name and parsed[relative]["id"] == rid,
                  f"{role}: clone link differs")
        restored = copy.deepcopy(parsed)
        original = records[target]
        restored[target - start]["name"], restored[target - start]["id"] = original["name"], original["id"]
        if role == "root":
            restored[target - start]["data"][0x1C:0x54] = original["data"][0x1C:0x54]
        for relative in links:
            restored[relative]["name"] = records[start + relative]["name"]
            restored[relative]["id"] = records[start + relative]["id"]
        for offset, (old_id, _) in inline.items():
            restored[target - start]["data"][offset:offset + 16] = old_id
        check(helper.serialize_wad(restored) == source_bytes, f"{role}: unplanned clone bytes changed")
        check(helper.serialize_wad(records[start:end + 1]) == source_bytes, "clone mutated source")
        previews[role] = {
            "physical_records": len(parsed), "payload_records": shape["payload_count"],
            "source_group_sha256": BASE.sha256(source_bytes),
            "in_memory_clone_group_sha256": BASE.sha256(clone_bytes),
            "round_trip_byte_exact": True, "undo_intentional_edits_restores_source_bytes": True,
            "changed_definition_relative_index": target - start,
            "changed_link_relative_indices": list(links),
            "changed_inline_id_offsets": [f"0x{x:X}" for x in inline],
            "changed_inline_name_offsets": ["0x1C"] if role == "root" else [],
        }
    return {"groups": previews, "full_wad_candidate_built": False,
            "script_payload_preserved": True, "stock_dock_mesh_link_preserved": True,
            "shared_compass_inline_ref_preserved": True,
            "note": "Group transforms tested in memory only. Full WAD acceptance gate remains blocked."}


def blocked_report(inspection: dict, candidate: Path) -> dict:
    candidate = hud.safe_output(candidate, hud.REPO / "build/v0.10.4")
    check(not candidate.exists(), f"candidate path already exists; refuse stale output: {candidate}")
    check(not inspection["required_clone"]["matches_three_payload_gate"],
          "source topology changed; this fail-closed preflight needs review")
    return {"result": "OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BLOCKED", "builder_revision": 3,
            "reason": "Complete prototype group includes nonempty SCP payload; +3 payload/+2 accounting gate conflicts.",
            "required_clone": inspection["required_clone"], "requested_payload_delta": 3,
            "requested_accounting_delta": 2, "candidate_written": False,
            "candidate_wad_sha256": None, "candidate_dcb_sha256": None,
            "candidate_path_reserved_only": str(candidate.relative_to(hud.REPO)).replace("\\", "/"),
            "ready_for_offline_dcb_iconname_gate": False, "ready_for_runtime_test": False,
            "game_files_written": False, "save_state_written": False,
            "progression_state_written": False, "marker_state_written": False,
            "conclusion": "STOP_REQUIRED_BY_AUTHORITATIVE_SPEC_TOPOLOGY_CLAUSE",
            "next_research": "Prove local SCP binding before changing topology or requested payload/accounting deltas."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output-wad", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    candidate = hud.safe_output(args.output_wad, hud.REPO / "build/v0.10.4")
    check(not candidate.is_relative_to(args.game_root.resolve()), "candidate overlaps game tree")
    check(not candidate.exists(), f"candidate path already exists; refuse stale output: {candidate}")
    check(args.report.resolve() != INSPECTOR.OUTPUT.resolve(), "gate report overlaps physical inspector report")
    source, raw, records, inspection = INSPECTOR.read_inspection(args.game_root)
    report = blocked_report(inspection, candidate)
    report["source_wad_sha256"] = inspection["source_wad_sha256"]
    report["source_round_trip_byte_exact"] = inspection["source_round_trip_byte_exact"]
    report["peer_comparison_passed"] = inspection["peer_comparison_passed"]
    report["clone_transform_preview"] = preview_clones(records, inspection)
    check(BASE.load_helper().serialize_wad(records) == raw, "preview changed parsed source WAD")
    check(source.read_bytes() == raw, "live source changed during preflight")
    report["source_unchanged_after_preview"] = True
    INSPECTOR.write_report(INSPECTOR.OUTPUT, inspection, args.game_root)
    INSPECTOR.write_report(args.report, report, args.game_root)
    check(source.read_bytes() == raw, "live source changed after report write")
    check(not candidate.exists(), "unexpected candidate exists after blocked gate")
    print(report["result"])
    print("Full groups need +13 physical records, +4 payloads, +3 accounting.")
    print("SCP_BoatDock adds fourth payload (0x10005). No WAD/DCB candidate written.")
    print(f"Proof report: {args.report.resolve()}")
    print(f"Runtime test: NOT SAFE YET. Exit {BLOCKED_EXIT_CODE}: structural gate blocked.")
    return BLOCKED_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
