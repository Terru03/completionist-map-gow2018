#!/usr/bin/env python3
"""Build the UID-aware Raven compass-routing v2 probe offline.

The runtime-proven shared-loader Twin remains the binary/map base. This builder changes
no WAD/resource identity. V2 appends a Lua-only routing layer that distinguishes the two
shared Raven map objects by exact live object reference, routes the selected native
marker Name/Id through the already-proven CompletionistRaven compass class, and observes
the existing production Raven completion oracle only to clear UI/compass routing state.

The Twin Lua hook is also allowed to outlive the original Raven UI object. No progression
or marker-state write is introduced, and no game file is written by this builder.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SHARED_PATH = HERE / "build-raven-shared-loader.py"
ROUTING_PATH = HERE / "raven-uid-compass-routing.lua"
TWIN_HOOK_PATH = HERE / "raven-shared-loader-twin.lua"

spec = importlib.util.spec_from_file_location("uid_routing_shared_base", SHARED_PATH)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)

BRANCH = "codex/v104-raven-uid-compass-routing-v2"
BASE_HEAD = "4fa06adc412f5e2c1e8e84f0a4769d57319b63b7"
SHARED_LOADER_RUNTIME_SUCCESS_HEAD = "e29b841b2e8799ebe90780413c8330755415183f"
RESULT = "RAVEN_UID_COMPASS_ROUTING_V2_OFFLINE_PROOF_PASSED"
OUTPUT = REPO / "build/v0.10.4-raven-uid-compass-routing-v2/offline/candidate/game-root"
REPORT = REPO / "archive/field-logs/completionist-v104-raven-uid-compass-routing-v2-offline.json"
LUA = shared.LUA


def routing_bytes() -> bytes:
    return b"\n" + ROUTING_PATH.read_bytes()


def generate(root: Path):
    root = root.resolve()
    shared_files, shared_proof = shared.generate(root)
    outputs = dict(shared_files)
    shared_lua = shared_files[LUA]
    routed_lua = shared_lua + routing_bytes()
    shared.b.check(routed_lua.startswith(shared_lua), "Shared-loader Lua prefix changed")
    outputs[LUA] = routed_lua

    # V2 remains binary-identical to the successful shared-loader map experiment. Only
    # Lua behavior changes: independent Twin lifetime + UID routing/completion cleanup.
    for rel in (shared.MASTER, shared.COORDS, shared.UI):
        shared.b.check(outputs[rel] == shared_files[rel], f"Shared-loader binary changed: {rel}")

    text = ROUTING_PATH.read_text(encoding="utf-8")
    twin_text = TWIN_HOOK_PATH.read_text(encoding="utf-8")
    required = (
        "collision == self.completionistSharedLoaderTwinGO",
        "collision == self.completionistMapV100MapIconGO",
        "game.Map.GetMarkerInfo(name)",
        "game.Compass.FindMarkersByIconClass({ravenClass})",
        "game.Compass.ShowMarker(selected.Name, ravenClass)",
        "game.Compass.HideMarker(selected.Name)",
        "CompletionistMapV100_IsRavenCollected",
        "game.Compass.HideMarker(ravenName)",
        "twinTouched=false progressionWrites=false",
        "Completionist_V103_Veithurgard_Raven_01",
        "Completionist_V104_Veithurgard_Raven_Twin_01",
        "CompletionistMapV104UidAwareRavenCompassRouting",
        "CompletionistMapV104ObserveRavenCompletion",
    )
    missing = [token for token in required if token not in text]
    shared.b.check(not missing, f"UID-routing v2 source contract missing: {missing}")

    twin_required = (
        "local originalPresent = original ~= nil",
        "Map.CreateMarkerIcon(info.Id, region, \"\")",
        "originalPresent=false",
        "independentTwinLifetime=true",
    )
    twin_missing = [token for token in twin_required if token not in twin_text]
    shared.b.check(not twin_missing, f"Independent Twin source contract missing: {twin_missing}")
    shared.b.check(
        "SKIP reason=original_raven_absent" not in twin_text,
        "Twin is still gated on a live original Raven UI object",
    )

    forbidden = (
        "SetMarkerState",
        "challengeComplete",
        "OPENED",
        "SetToken",
        "SetProgress",
        "CompletionistMapV100_PublishTargetState",
    )
    present = [token for token in forbidden if token in text]
    shared.b.check(not present, f"Lifecycle/progression mutation token present in routing shim: {present}")

    proof = {
        "schema": 2,
        "result": RESULT,
        "branch_contract": BRANCH,
        "base_head": BASE_HEAD,
        "shared_loader_runtime_success_head": SHARED_LOADER_RUNTIME_SUCCESS_HEAD,
        "source_root": str(root),
        "source_sha256": shared_proof["source_sha256"],
        "files": {
            rel: {"sha256": shared.b.sha_bytes(raw), "bytes": len(raw)}
            for rel, raw in outputs.items()
        },
        "identities": {
            "raven_name": shared.b.RAVEN_MARKER_NAME,
            "raven_uid": f"{shared.b.RAVEN_MARKER_UID:016X}",
            "twin_name": shared.b.TWIN_MARKER_NAME,
            "twin_uid": f"{shared.b.TWIN_MARKER_UID:016X}",
            "shared_map_loader": shared.b.RAVEN_MAP_GO,
            "shared_map_resource_hash": f"{shared.b.RAVEN_MAP_HASH:016X}",
            "compass_class": "CompletionistRaven",
        },
        "shared_loader_base": {
            "result": shared_proof["result"],
            "candidate_sha256": {
                rel: shared_proof["files"][rel]["sha256"] for rel in shared_files
            },
            "binary_candidate_bytes_identical": True,
            "mapmenu_shared_loader_prefix_exact": True,
            "map_instance_architecture_runtime_proven": True,
        },
        "routing_contract": {
            "selection_identity_source": "exact live map object reference retained by shared-loader",
            "native_identity_source": "game.Map.GetMarkerInfo(Name).Id",
            "same_visual_resource_for_both_map_markers": True,
            "selected_name_routed_to_native_compass": True,
            "selected_uid_used_for_active_target_comparison": True,
            "single_active_custom_target_policy": True,
            "stock_target_replace_policy_preserved": True,
            "new_wad_resource_identity": False,
            "compassgraph_changed": False,
            "lifecycle_observation": True,
            "completion_oracle": "CompletionistMapV100_IsRavenCollected",
            "completion_cleanup_scope": "original Raven compass/local routing state only",
            "twin_lifetime_independent_of_original_ui_object": True,
            "lifecycle_progression_mutation": False,
            "synthetic_progression_writes": False,
        },
        "expected_runtime_matrix": {
            "original_click": "Show original Raven through CompletionistRaven",
            "twin_click": "Show Twin through CompletionistRaven",
            "original_to_twin": "Twin replaces original",
            "twin_to_original": "original replaces Twin",
            "second_click_same_marker": "remove active target",
            "twin_to_stock": "stock replaces Twin",
            "stock_to_twin": "Twin replaces stock",
            "complete_tracked_original": "original custom compass/in-world target clears automatically",
            "complete_original_while_twin_tracked": "Twin remains active and untouched",
            "reopen_map_after_original_completion": "Twin is still created without a live original Raven UI object",
            "maximum_active_user_target": 1,
        },
        "candidate_file_count": len(outputs),
        "game_files_written": False,
        "runtime_test_performed": False,
        "ready_for_runtime_test": True,
        "retired_candidates_used": False,
        "progression_or_marker_state_writes": False,
        "map_title_behavior_changed": False,
    }
    return outputs, proof


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--check", action="store_true", help="Verify disk candidate and proof; write nothing.")
    args = ap.parse_args()
    root = args.raven_root.resolve()
    shared.b.assert_output_scope(root, OUTPUT, REPORT)
    files, proof = generate(root)

    if args.check:
        actual = {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob("*") if p.is_file()}
        shared.b.check(actual == set(files), "Candidate file set differs")
        for rel, raw in files.items():
            shared.b.check((OUTPUT / rel).read_bytes() == raw, f"Candidate differs: {rel}")
        saved = json.loads(REPORT.read_text(encoding="utf-8"))
        shared.b.check(saved == json.loads(json.dumps(proof)), "Offline proof differs")
        print("RAVEN_UID_COMPASS_ROUTING_V2_REBUILD_VERIFIED")
        return

    existing = {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob("*") if p.is_file()}
    shared.b.check(existing <= set(files), "Unexpected stale candidate file")
    for rel, raw in files.items():
        shared.b.write_bytes_atomic(OUTPUT, OUTPUT / rel, raw, "uid-routing v2 candidate")
    shared.b.write_bytes_atomic(
        REPORT.parent,
        REPORT,
        (json.dumps(proof, indent=2) + "\n").encode("utf-8"),
        "uid-routing v2 proof",
    )

    print(RESULT)
    print(json.dumps(proof["files"], indent=2))
    print("  shared-loader binary candidate unchanged: true")
    print("  new WAD resource identity: false")
    print("  completion observation: true")
    print("  lifecycle/progression writes: false")
    print("  Twin depends on live original UI object: false")
    print("  map title behavior changed: false")
    print("  runtime test performed: false")


if __name__ == "__main__":
    main()
