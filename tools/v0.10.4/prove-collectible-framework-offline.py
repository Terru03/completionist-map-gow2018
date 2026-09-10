#!/usr/bin/env python3
"""Build generic collectible proofs outside game and write machine report."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = "COLLECTIBLE_FRAMEWORK_OFFLINE_PROVED"
RAVEN_HASHES = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_ui.dcb": "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/dc/pc_le/mapmaster.dcb": "b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f",
    "exec/dc/pc_le/mapcoords.dcb": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
    "exec/dc/pc_le/compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": "67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path,
                        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO / "build/v0.10.4-collectible-framework/offline")
    parser.add_argument("--report", type=Path,
                        default=REPO / "archive/field-logs/completionist-v104-collectible-framework-offline.json")
    args = parser.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    report_path = args.report.resolve()
    if repo != REPO.resolve():
        raise ValueError(f"unexpected repo root: {repo}")
    if not game.is_dir():
        raise ValueError(f"game root missing: {game}")
    if output.is_relative_to(game) or report_path.is_relative_to(game):
        raise ValueError("framework proof output must stay outside game")
    build_root = (repo / "build").resolve()
    if not output.is_relative_to(build_root):
        raise ValueError(f"framework output must stay below {build_root}")

    cf = load("completionist_framework_proof", HERE / "collectible_framework.py")
    registry = cf.load_registry()
    registry_proof = cf.validate_registry(registry)
    before = {relative: cf.sha_file(game / relative) for relative in RAVEN_HASHES}
    if before != RAVEN_HASHES:
        raise ValueError(f"frozen Raven mismatch: {before}")

    wad_source = (game / "exec/wad/pc_le/r_ui.wad").read_bytes()
    dcb_source = (game / "exec/dc/pc_le/wad_r_ui.dcb").read_bytes()
    perm_source = (game / "exec/dc/pc_le/wad_r_perm.dcb").read_bytes()
    probe_wad_a, probe_wad_proof = cf.build_collectible_wad(
        wad_source, registry, "framework_probe")
    probe_wad_b, _ = cf.build_collectible_wad(
        wad_source, cf.load_registry(), "framework_probe")
    probe_dcb_a, probe_dcb_proof = cf.build_collectible_gopool(
        dcb_source, registry, "framework_probe")
    probe_dcb_b, _ = cf.build_collectible_gopool(
        dcb_source, cf.load_registry(), "framework_probe")
    probe_perm_a, probe_perm_proof = cf.build_collectible_compass_inworld(
        perm_source, registry, "framework_probe")
    probe_perm_b, _ = cf.build_collectible_compass_inworld(
        perm_source, cf.load_registry(), "framework_probe")
    if (probe_wad_a != probe_wad_b or probe_dcb_a != probe_dcb_b or
            probe_perm_a != probe_perm_b):
        raise ValueError("synthetic rebuild is not deterministic")

    output.mkdir(parents=True, exist_ok=True)
    outputs = {
        "framework_probe/r_ui.wad": probe_wad_a,
        "framework_probe/wad_r_ui.dcb": probe_dcb_a,
        "framework_probe/wad_r_perm.dcb": probe_perm_a,
    }
    manifest = {}
    for relative, raw in outputs.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        if target.read_bytes() != raw:
            raise ValueError(f"offline output mismatch: {target}")
        manifest[relative] = {"bytes": len(raw), "sha256": cf.sha_bytes(raw)}

    failure_path = repo / "archive/field-logs/completionist-v104-nornir-runtime-candidate3-failure.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8-sig"))
    if (failure.get("result") != "RUNTIME_NORNIR_CANDIDATE3_MAP_OPEN_CRASH_ROLLED_BACK"
            or failure.get("diagnosis", {}).get("root_cause_proven") is not False):
        raise ValueError("Candidate 3 failure archive is missing or overclaims diagnosis")

    service = repo / "tools/v0.10.4/completionist-collectible-service.lua"
    adapters = repo / "tools/v0.10.4/completionist-collectible-lifecycle-adapters.lua"
    lua_text = service.read_text(encoding="utf-8") + adapters.read_text(encoding="utf-8")
    forbidden = ("Map.ChangeMarkerState", "QuestManager.Set", "SaveGame",
                 "SoftSavePlayerState", "SetProgression")
    hits = [token for token in forbidden if token in lua_text]
    if hits:
        raise ValueError(f"framework Lua has forbidden state writes: {hits}")

    after = {relative: cf.sha_file(game / relative) for relative in RAVEN_HASHES}
    if after != before:
        raise ValueError("frozen Raven changed during framework proof")
    isolation = cf.assert_cross_collectible_isolation(
        registry, ["odins_raven", "nornir_chest", "framework_probe"])
    report = {
        "schema": 1,
        "result": RESULT,
        "registry": {
            "path": str(cf.REGISTRY_PATH),
            "sha256": cf.sha_file(cf.REGISTRY_PATH),
            "validation": registry_proof,
        },
        "raven_golden": {
            "hashes_before": before,
            "hashes_after": after,
            "byte_preserved": before == after,
            "production_frozen": True,
        },
        "retired_nornir_candidates": {
            "candidate3_failure_archive": str(failure_path),
            "candidate3_map_open_crash_archived": True,
            "candidate3_root_cause_claimed": False,
            "construction_use_allowed": False,
        },
        "synthetic_expansion": {
            "collectible_key": "framework_probe",
            "wad": probe_wad_proof,
            "gopool": probe_dcb_proof,
            "compass_inworld": probe_perm_proof,
            "built_from_registry_only": True,
            "generic_builder_logic_changed_for_probe": False,
            "deterministic_rebuild": True,
            "game_ready": False,
        },
        "cross_collectible_isolation": isolation,
        "lua_abstraction": {
            "service": {"path": str(service), "sha256": cf.sha_file(service)},
            "adapters": {"path": str(adapters), "sha256": cf.sha_file(adapters)},
            "installed": False,
            "forbidden_state_write_tokens": hits,
        },
        "offline_outputs": {"root": str(output), "files": manifest},
        "safety": {
            "god_of_war_launched": False,
            "installed_game_files_written": False,
            "save_files_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "candidate3_runtime_installer_created": False,
            "candidate3_runtime_tested": False,
            "opaque_model_group_payload_bytes_mutated": False,
            "candidate2_used": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(RESULT)
    print(f"  registry types: {registry_proof['collectible_count']}")
    print("  retired Nornir construction used: false")
    print(f"  synthetic WAD: {probe_wad_proof['candidate_sha256']}")
    print("  Raven changed: false")
    print("  game writes: false")
    print("  runtime install allowed: false")
    print(f"  report: {report_path}")


if __name__ == "__main__":
    main()
