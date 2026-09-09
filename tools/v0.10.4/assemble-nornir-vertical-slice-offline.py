#!/usr/bin/env python3
"""Assemble and strictly verify the complete OFFLINE Nornir vertical slice.

This combines the separately proven Nornir native-data, map/HUD, and perm-class
candidates. The only new mutation is retargeting the OFFLINE Nornir map marker
from the temporary Raven map GameObject to goMapIconCompletionistNornirChest.
Nothing is installed into God of War.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_VERTICAL_SLICE_OFFLINE_GATE_PASSED"

NORNIR_ID = 0x381B067F07254A25
NORNIR_MARKER = "Completionist_V104_Veithurgard_NornirChest_01"
NORNIR_MAP_VISUAL = "goMapIconCompletionistNornirChest"
NORNIR_MAP_HASH = 0xE14C66C3B90633E0
NORNIR_HUD_HASH = 0x7DDC11175EBD1E94
NORNIR_CLASS_UID = 0x8D5A770E0C4272CE
NORNIR_INWORLD_UID = 0x32BBE7E267644D93
NORNIR_ANCHOR = 0x45DE535858C63212

RAVEN_ID = 0xE15E6BC82AE2773E
RAVEN_MAP_VISUAL = "goMapIconCompletionistRaven"
RAVEN_ANCHOR = 0xBABC033C454755A0

EXPECTED_FILES = {
    "r_ui.wad",
    "wad_r_ui.dcb",
    "wad_r_perm.dcb",
    "mapmaster.dcb",
    "mapcoords.dcb",
    "compassgraph.dcb",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_native_builder():
    path = HERE / "build-nornir-native-data-offline.py"
    spec = importlib.util.spec_from_file_location("nornir_vertical_native", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    check(path.is_file(), f"missing proof report: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require_false_safety(report: dict, keys: tuple[str, ...]) -> None:
    safety = report.get("safety", report)
    for key in keys:
        check(safety.get(key) is False, f"component safety flag is not false: {key}")


def bind_components(native_dir: Path, native_report_path: Path,
                    map_hud_dir: Path, map_hud_report_path: Path,
                    perm_candidate: Path, perm_report_path: Path) -> tuple[dict, dict, dict]:
    native_report = load_json(native_report_path)
    check(native_report.get("result") == "OFFLINE_NORNIR_NATIVE_DATA_BUILT_AND_REPARSED",
          "native-data report is not the passing gate")
    check(native_report.get("source_game_files_unchanged") is True,
          "native-data source-game immutability proof missing")
    check(native_report.get("game_files_written") is False and
          native_report.get("saves_progression_marker_state_written") is False and
          native_report.get("runtime_install_performed") is False,
          "native-data safety contract failed")
    check(native_report.get("candidate", {}).get("id") == f"{NORNIR_ID:016X}",
          "native-data candidate marker ID changed")
    check(native_report.get("candidate", {}).get("name") == NORNIR_MARKER,
          "native-data candidate marker name changed")
    check(native_report.get("candidate", {}).get("selected_graph_neighbor") == f"{NORNIR_ANCHOR:016X}",
          "native-data selected graph neighbour changed")
    for name in ("mapmaster.dcb", "mapcoords.dcb", "compassgraph.dcb"):
        path = native_dir / name
        expected = native_report.get("generated_files", {}).get(name, {}).get("sha256")
        check(isinstance(expected, str) and sha256(path) == expected.lower(),
              f"native-data candidate SHA mismatch: {name}")

    map_report = load_json(map_hud_report_path)
    check(map_report.get("result") == "OFFLINE_NORNIR_MAP_HUD_BUILT" and
          map_report.get("ready_for_next_offline_gate") is True,
          "map/HUD report is not next-gate ready")
    proof = map_report.get("proof", {})
    for key in (
        "candidate_wad_reparsed",
        "candidate_wad_normalizes_exactly_to_raven_production",
        "candidate_gopool_normalizes_exactly_to_raven_production",
        "all_existing_gopool_rows_preserved",
        "raven_resources_preserved",
    ):
        check(proof.get(key) is True, f"map/HUD proof missing: {key}")
    require_false_safety(map_report, (
        "game_files_written", "runtime_install_performed", "save_state_written",
        "progression_state_written", "marker_state_written", "stock_resources_modified",
        "raven_production_files_changed",
    ))
    check(map_report.get("nornir", {}).get("map_go") == NORNIR_MAP_VISUAL and
          map_report.get("nornir", {}).get("map_go_hash") == f"{NORNIR_MAP_HASH:016X}" and
          map_report.get("nornir", {}).get("hud_go_hash") == f"{NORNIR_HUD_HASH:016X}",
          "map/HUD Nornir visual identities changed")
    wad_expected = map_report.get("candidate", {}).get("wad", {}).get("candidate_sha256")
    pool_expected = map_report.get("candidate", {}).get("gopool", {}).get("candidate_sha256")
    check(isinstance(wad_expected, str) and sha256(map_hud_dir / "r_ui.wad") == wad_expected.lower(),
          "map/HUD r_ui.wad SHA mismatch")
    check(isinstance(pool_expected, str) and sha256(map_hud_dir / "wad_r_ui.dcb") == pool_expected.lower(),
          "map/HUD wad_r_ui.dcb SHA mismatch")
    check(map_report.get("candidate", {}).get("gopool", {}).get("hud_capacity") == 2,
          "Nornir HUD GOPool capacity is not 2")

    perm_report = load_json(perm_report_path)
    check(perm_report.get("result") == "OFFLINE_NORNIR_PERM_BUILT_AND_REPARSED" and
          perm_report.get("ready_for_vertical_slice_assembly") is True and
          perm_report.get("runtime_ready") is False,
          "perm report is not vertical-slice ready")
    pproof = perm_report.get("proof", {})
    for key in (
        "all_existing_exports_preserved",
        "all_existing_relocation_semantics_preserved",
        "candidate_data_normalizes_exactly_to_raven_production",
        "frozen_raven_class_preserved",
        "frozen_raven_inworld_preserved",
        "stock_DockPoint_resources_preserved_by_exact_normalization",
        "unrelated_chunks_11_14_35_identical",
    ):
        check(pproof.get(key) is True, f"perm proof missing: {key}")
    require_false_safety(perm_report, (
        "game_files_written", "save_state_written", "progression_state_written",
        "marker_state_written", "runtime_install_performed",
    ))
    check(perm_report.get("nornir_class", {}).get("uid") == f"{NORNIR_CLASS_UID:016X}" and
          perm_report.get("nornir_class", {}).get("IconName") == f"{NORNIR_HUD_HASH:016X}" and
          perm_report.get("nornir_class", {}).get("InWorld_tMPIcon_Name") == f"{NORNIR_INWORLD_UID:016X}",
          "Nornir perm class bindings changed")
    check(perm_report.get("nornir_inworld", {}).get("uid") == f"{NORNIR_INWORLD_UID:016X}" and
          perm_report.get("nornir_inworld", {}).get("IconName") == f"{NORNIR_HUD_HASH:016X}",
          "Nornir in-world carrier binding changed")
    check(sha256(perm_candidate) == str(perm_report.get("candidate_sha256", "")).lower(),
          "perm candidate SHA mismatch")

    return native_report, map_report, perm_report


def retarget_nornir_map_visual(builder, source: Path, output: Path, proof_dir: Path) -> dict:
    master = builder.native.Dcb(source)
    rows = [(realm, region, marker) for realm, region, _r, marker in builder.iter_markers(master)
            if master.unpack("<Q", marker)[0] == NORNIR_ID]
    check(len(rows) == 1, f"expected one Nornir marker in native candidate, found {len(rows)}")
    _realm, _region, marker = rows[0]
    check(master.string(marker + 8) == RAVEN_MAP_VISUAL,
          "native-data candidate no longer carries the temporary Raven map visual")
    check(marker + 8 in master.relocations, "Nornir marker icon pointer is not relocated")

    before_snapshot = builder.marker_snapshot(master)
    raven_before = [r for r in before_snapshot if r["id"] == f"{RAVEN_ID:016X}"]
    check(len(raven_before) == 1 and raven_before[0]["icon"] == RAVEN_MAP_VISUAL,
          "frozen Raven marker visual changed before Nornir retarget")

    blob = bytearray(master.blob)
    relocs = set(master.relocations)
    old_delta = master.unpack("<q", marker + 8)[0]
    appended_at = len(blob)
    encoded = NORNIR_MAP_VISUAL.encode("ascii") + b"\0"
    blob.extend(encoded)
    struct.pack_into("<q", blob, marker + 8, appended_at - (marker + 8))
    output.parent.mkdir(parents=True, exist_ok=True)
    builder.rebuild_dcb(master, blob, relocs, output)

    candidate = builder.native.Dcb(output)
    after_snapshot = builder.marker_snapshot(candidate)
    nornir_after = [r for r in after_snapshot if r["id"] == f"{NORNIR_ID:016X}"]
    raven_after = [r for r in after_snapshot if r["id"] == f"{RAVEN_ID:016X}"]
    check(len(nornir_after) == 1 and nornir_after[0]["icon"] == NORNIR_MAP_VISUAL,
          "Nornir marker did not bind the dedicated map visual")
    check(raven_after == raven_before, "frozen Raven map marker changed during Nornir retarget")
    check(len(after_snapshot) == len(before_snapshot), "map marker count changed during visual retarget")

    before_by_id = {r["id"]: r for r in before_snapshot}
    after_by_id = {r["id"]: r for r in after_snapshot}
    check(set(before_by_id) == set(after_by_id), "map marker identity set changed during visual retarget")
    for uid, before in before_by_id.items():
        after = dict(after_by_id[uid])
        if uid == f"{NORNIR_ID:016X}":
            check(after["icon"] == NORNIR_MAP_VISUAL, "Nornir icon retarget missing")
            after["icon"] = before["icon"]
        check(after == before, f"map marker changed outside allowed Nornir icon field: {uid}")

    # Exact inverse proof against the native-data candidate bytes.
    normalized_blob = bytearray(candidate.blob)
    check(len(normalized_blob) == len(master.blob) + len(encoded), "unexpected mapmaster data growth")
    struct.pack_into("<q", normalized_blob, marker + 8, old_delta)
    del normalized_blob[-len(encoded):]
    proof_dir.mkdir(parents=True, exist_ok=True)
    inverse = proof_dir / "mapmaster.inverse-normalized.dcb"
    builder.rebuild_dcb(candidate, normalized_blob, set(candidate.relocations), inverse)
    check(inverse.read_bytes() == source.read_bytes(),
          "Nornir map-visual retarget does not normalize exactly to native-data candidate")
    inverse.unlink()

    return {
        "marker": NORNIR_MARKER,
        "id": f"{NORNIR_ID:016X}",
        "visual_before": RAVEN_MAP_VISUAL,
        "visual_after": NORNIR_MAP_VISUAL,
        "visual_hash_after": f"{NORNIR_MAP_HASH:016X}",
        "only_nornir_icon_field_changed_semantically": True,
        "frozen_raven_marker_preserved": True,
        "marker_count_preserved": True,
        "exact_inverse_normalization_to_native_candidate": True,
        "appended_string_bytes": len(encoded),
    }


def live_sources(game: Path) -> dict[str, Path]:
    dc = game / "exec/dc/pc_le"
    wad = game / "exec/wad/pc_le"
    return {
        "r_ui.wad": wad / "r_ui.wad",
        "wad_r_ui.dcb": dc / "wad_r_ui.dcb",
        "wad_r_perm.dcb": dc / "wad_r_perm.dcb",
        "mapmaster.dcb": dc / "mapmaster.dcb",
        "mapcoords.dcb": dc / "mapcoords.dcb",
        "compassgraph.dcb": dc / "compassgraph.dcb",
    }


def bind_live_sources(paths: dict[str, Path], native_report: dict,
                      map_report: dict, perm_report: dict) -> dict[str, str]:
    expected = {
        "r_ui.wad": map_report["source"]["r_ui_wad_sha256"],
        "wad_r_ui.dcb": map_report["source"]["wad_r_ui_dcb_sha256"],
        "wad_r_perm.dcb": perm_report["source_sha256"],
        "mapmaster.dcb": native_report["source_hashes_before"]["mapmaster.dcb"],
        "mapcoords.dcb": native_report["source_hashes_before"]["mapcoords.dcb"],
        "compassgraph.dcb": native_report["source_hashes_before"]["compassgraph.dcb"],
    }
    actual = {name: sha256(path) for name, path in paths.items()}
    for name in EXPECTED_FILES:
        check(actual[name] == str(expected[name]).lower(),
              f"live Raven production source changed before assembly: {name}")
    return actual


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--native-dir", type=Path, required=True)
    ap.add_argument("--native-report", type=Path, required=True)
    ap.add_argument("--map-hud-dir", type=Path, required=True)
    ap.add_argument("--map-hud-report", type=Path, required=True)
    ap.add_argument("--perm-candidate", type=Path, required=True)
    ap.add_argument("--perm-report", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    native_dir = args.native_dir.resolve()
    map_hud_dir = args.map_hud_dir.resolve()
    perm_candidate = args.perm_candidate.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    check(not output_dir.is_relative_to(game) and not report_path.is_relative_to(game),
          "vertical-slice output/report must stay outside the game directory")
    check(not output_dir.is_relative_to(repo / ".git") and not report_path.is_relative_to(repo / ".git"),
          "refusing to write inside Git metadata")

    builder = load_native_builder()
    native_report, map_report, perm_report = bind_components(
        native_dir, args.native_report.resolve(), map_hud_dir, args.map_hud_report.resolve(),
        perm_candidate, args.perm_report.resolve())
    live = live_sources(game)
    before_live = bind_live_sources(live, native_report, map_report, perm_report)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    dc_out = output_dir / "game-root/exec/dc/pc_le"
    wad_out = output_dir / "game-root/exec/wad/pc_le"
    dc_out.mkdir(parents=True, exist_ok=True)
    wad_out.mkdir(parents=True, exist_ok=True)

    shutil.copy2(map_hud_dir / "r_ui.wad", wad_out / "r_ui.wad")
    shutil.copy2(map_hud_dir / "wad_r_ui.dcb", dc_out / "wad_r_ui.dcb")
    shutil.copy2(perm_candidate, dc_out / "wad_r_perm.dcb")
    shutil.copy2(native_dir / "mapcoords.dcb", dc_out / "mapcoords.dcb")
    shutil.copy2(native_dir / "compassgraph.dcb", dc_out / "compassgraph.dcb")
    retarget = retarget_nornir_map_visual(
        builder, native_dir / "mapmaster.dcb", dc_out / "mapmaster.dcb", output_dir / "proof")

    # Final native routing reparse.
    final_master = builder.native.Dcb(dc_out / "mapmaster.dcb")
    final_coords = builder.native.Dcb(dc_out / "mapcoords.dcb")
    final_graph = builder.native.Dcb(dc_out / "compassgraph.dcb")
    markers = builder.marker_snapshot(final_master)
    coords = builder.coord_snapshot(final_coords)
    edges = builder.graph_edges(final_graph)
    nornir_markers = [r for r in markers if r["id"] == f"{NORNIR_ID:016X}"]
    nornir_coords = [r for r in coords if r["id"] == f"{NORNIR_ID:016X}"]
    check(len(nornir_markers) == 1 and nornir_markers[0]["icon"] == NORNIR_MAP_VISUAL,
          "final Nornir map marker failed reparse")
    check(len(nornir_coords) == 1, "final Nornir map coordinate count is not one")
    check((NORNIR_ID, NORNIR_ANCHOR) in edges, "final Nornir graph edge missing")
    check((RAVEN_ID, RAVEN_ANCHOR) in edges, "runtime-proven Raven graph edge missing")

    produced = {
        "r_ui.wad": wad_out / "r_ui.wad",
        "wad_r_ui.dcb": dc_out / "wad_r_ui.dcb",
        "wad_r_perm.dcb": dc_out / "wad_r_perm.dcb",
        "mapmaster.dcb": dc_out / "mapmaster.dcb",
        "mapcoords.dcb": dc_out / "mapcoords.dcb",
        "compassgraph.dcb": dc_out / "compassgraph.dcb",
    }
    check(set(produced) == EXPECTED_FILES and all(path.is_file() for path in produced.values()),
          "complete six-file vertical slice was not assembled")

    # Five files are exact proven component bytes; mapmaster differs only by the
    # strictly reversible Nornir icon retarget above.
    check(sha256(produced["r_ui.wad"]) == sha256(map_hud_dir / "r_ui.wad"), "assembled WAD changed")
    check(sha256(produced["wad_r_ui.dcb"]) == sha256(map_hud_dir / "wad_r_ui.dcb"), "assembled UI pool changed")
    check(sha256(produced["wad_r_perm.dcb"]) == sha256(perm_candidate), "assembled perm candidate changed")
    check(sha256(produced["mapcoords.dcb"]) == sha256(native_dir / "mapcoords.dcb"), "assembled mapcoords changed")
    check(sha256(produced["compassgraph.dcb"]) == sha256(native_dir / "compassgraph.dcb"), "assembled compassgraph changed")

    after_live = {name: sha256(path) for name, path in live.items()}
    check(after_live == before_live, "one or more live God of War files changed during offline assembly")

    file_report = {
        name: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for name, path in produced.items()
    }
    report = {
        "schema": 1,
        "result": RESULT,
        "candidate": {
            "marker": NORNIR_MARKER,
            "marker_id": f"{NORNIR_ID:016X}",
            "map_visual": NORNIR_MAP_VISUAL,
            "map_visual_hash": f"{NORNIR_MAP_HASH:016X}",
            "hud_visual_hash": f"{NORNIR_HUD_HASH:016X}",
            "compass_class_uid": f"{NORNIR_CLASS_UID:016X}",
            "inworld_carrier_uid": f"{NORNIR_INWORLD_UID:016X}",
            "graph_neighbor": f"{NORNIR_ANCHOR:016X}",
            "files": file_report,
        },
        "mapmaster_retarget": retarget,
        "component_proofs": {
            "native_data_result": native_report["result"],
            "map_hud_result": map_report["result"],
            "perm_result": perm_report["result"],
            "native_candidate_hashes_bound": True,
            "map_hud_candidate_hashes_bound": True,
            "perm_candidate_hash_bound": True,
        },
        "proof": {
            "complete_six_file_candidate": True,
            "dedicated_nornir_map_visual_bound": True,
            "dedicated_nornir_hud_capacity_two": True,
            "dedicated_nornir_compass_class_bound_to_hud_and_carrier": True,
            "dedicated_nornir_inworld_carrier_bound_to_hud": True,
            "nornir_native_coordinate_and_graph_edge_reparsed": True,
            "runtime_proven_raven_edge_preserved": True,
            "frozen_raven_class_and_carrier_preserved_by_perm_normalization": True,
            "frozen_raven_map_hud_resources_preserved_by_ui_normalization": True,
            "stock_DockPoint_resources_preserved_by_component_normalization": True,
            "mapmaster_retarget_exactly_reversible": True,
            "live_raven_production_files_unchanged": True,
        },
        "live_source_hashes_before": before_live,
        "live_source_hashes_after": after_live,
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
        "ready_for_mapmenu_lifecycle_offline_gate": True,
        "runtime_ready": False,
        "next_gate": "Add Nornir single-target mapmenu behavior plus real chest-completion lifecycle OFFLINE, then perform a final reversible runtime-candidate gate before installation.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  marker:             {NORNIR_MARKER}")
    print(f"  marker ID:          {NORNIR_ID:016X}")
    print(f"  map visual:         {NORNIR_MAP_VISUAL} / {NORNIR_MAP_HASH:016X}")
    print(f"  HUD visual:         {NORNIR_HUD_HASH:016X} / GOPool capacity 2")
    print(f"  compass class UID:  {NORNIR_CLASS_UID:016X}")
    print(f"  in-world UID:       {NORNIR_INWORLD_UID:016X}")
    print(f"  graph neighbour:    {NORNIR_ANCHOR:016X}")
    print("  six-file candidate: complete")
    print("  Nornir mapmaster retarget exact inverse proof: true")
    print("  Raven class/carrier/map/HUD/native edge preserved: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  candidate root: {output_dir / 'game-root'}")
    print(f"  report:         {report_path}")


if __name__ == "__main__":
    main()
