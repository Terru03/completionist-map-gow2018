#!/usr/bin/env python3
"""Build the UID-aware Raven compass-lifecycle v3.2 candidate offline.

The runtime-proven shared-loader Twin remains the binary/map base. This builder changes
no WAD/resource identity. V3.2 captures exact custom identity in the map collision
callback and arms it only from the production custom-Raven prompt owner. Its gameplay
hook is byte-identical to runtime-proven v3.1.

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
ROUTING_PATH = HERE / "raven-uid-compass-routing-v3.2.lua"
TWIN_HOOK_PATH = HERE / "raven-shared-loader-twin.lua"

spec = importlib.util.spec_from_file_location("uid_routing_shared_base", SHARED_PATH)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)

BRANCH = "codex/v104-raven-uid-compass-lifecycle-v3.2"
BASE_HEAD = "4b028127e3a196742d0073d8c8fb339e2098f5f6"
SHARED_LOADER_RUNTIME_SUCCESS_HEAD = "e29b841b2e8799ebe90780413c8330755415183f"
RESULT = "RAVEN_UID_COMPASS_LIFECYCLE_V32_OFFLINE_PROOF_PASSED"
OUTPUT = REPO / "build/v0.10.4-raven-uid-compass-lifecycle-v3.2/offline/candidate/game-root"
REPORT = REPO / "archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3.2-offline.json"
LUA = shared.LUA
EVENTS = "mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"
EVENTS_SHA = "c22aa8a649e2380a60040d64c3843a392101fb6dcd733f9078d24141600ad69c"
EVENTS_PATH = HERE / "raven-uid-compass-lifecycle-v3.2-events.lua"
EVENTS_V31_PATH = HERE / "raven-uid-compass-lifecycle-v3.1-events.lua"


def canonical_lua_bytes(path: Path) -> bytes:
    """Return authored Lua as UTF-8 with canonical LF line endings on every host."""
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def shared_hook_bytes() -> bytes:
    return b"\n" + canonical_lua_bytes(TWIN_HOOK_PATH)


# build-raven-shared-loader.py historically reads its authored Twin hook with raw
# read_bytes(), so a Windows checkout with core.autocrlf can generate a different
# candidate from the exact same Git blob. Override only that hook reader in this
# v3.2 build path; the runtime-proven shared builder/source itself stays unchanged.
shared.hook_bytes = shared_hook_bytes


def routing_bytes() -> bytes:
    return b"\n" + canonical_lua_bytes(ROUTING_PATH)


def generate(root: Path):
    root = root.resolve()
    shared_files, shared_proof = shared.generate(root)
    outputs = dict(shared_files)
    shared_lua = shared_files[LUA]
    routed_lua = shared_lua + routing_bytes()
    shared.b.check(routed_lua.startswith(shared_lua), "Shared-loader Lua prefix changed")
    outputs[LUA] = routed_lua
    event_source = (root / EVENTS).read_bytes()
    shared.b.check(shared.b.sha_bytes(event_source) == EVENTS_SHA, "Frozen Raven gameplay source differs")
    event_hook = canonical_lua_bytes(EVENTS_PATH)
    shared.b.check(
        event_hook == canonical_lua_bytes(EVENTS_V31_PATH),
        "Gameplay hook differs from runtime-proven v3.1",
    )
    outputs[EVENTS] = event_source + b"\n" + event_hook
    shared.b.check((root / EVENTS).read_bytes() == event_source, "Gameplay source changed during build")

    # V3.2 remains binary-identical to the successful shared-loader map experiment.
    # Only mapmenu selection handoff changes; gameplay cleanup stays byte-identical.
    for rel in (shared.MASTER, shared.COORDS, shared.UI):
        shared.b.check(outputs[rel] == shared_files[rel], f"Shared-loader binary changed: {rel}")

    text = ROUTING_PATH.read_text(encoding="utf-8")
    twin_text = TWIN_HOOK_PATH.read_text(encoding="utf-8")
    required = (
        "function MapOn:MapCollisionChangeHandler(currState, collisionGameObjectTable, realmName)",
        "collision == self.completionistSharedLoaderTwinGO",
        "collision == self.completionistMapV100MapIconGO",
        "completionistMapV104RavenSelection",
        'selected.State = "candidate-custom"',
        'selected.State = "armed-custom"',
        "SELECT_CANDIDATE",
        "SELECT_ARM",
        "SELECT_DISARM",
        "SELECT_CONSUME",
        "STOCK_REPLACE_TWIN_REFUSED",
        "confirmed_native_prompt:marker=",
        "confirmed_native_action:marker=",
        "confirmed_other_custom_prompt",
        "prompt_unavailable",
        "map_teardown:",
        "armedSelectionExpiry=ui_lifecycle_only",
        "game.Map.GetMarkerInfo(name)",
        "game.Compass.FindMarkersByIconClass({ravenClass})",
        "game.Compass.ShowMarker(selected.Name, ravenClass)",
        "game.Compass.HideMarker(selected.Name)",
        "return allHidden, hidden",
        "CompletionistMapV100_IsRavenCollected",
        "game.Compass.HideMarker(ravenName)",
        "twinTouched=false progressionWrites=false",
        "Completionist_V103_Veithurgard_Raven_01",
        "Completionist_V104_Veithurgard_Raven_Twin_01",
        "CompletionistMapV104UidAwareRavenCompassRouting",
        "identitySource=MapOn.MapCollisionChangeHandler_collision_table",
    )
    missing = [token for token in required if token not in text]
    shared.b.check(not missing, f"UID-lifecycle v3.2 source contract missing: {missing}")
    for token in ("selectionTTL", "ttl_expired", "new_noncustom_collision"):
        shared.b.check(token not in text, f"Fragile v3.1 selection rule remains: {token}")

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

    shared.b.check("CompletionistMapV100_DestroyMapPin =" not in twin_text,
                   "Twin cleanup coupled to real Raven destroy")
    shared.b.check("util.create_thread" not in text, "Unproven polling API used")
    for token in forbidden:
        shared.b.check(token not in event_hook.decode("utf-8"), "Gameplay hook writes progression")
    event_text = event_hook.decode("utf-8")
    event_required = (
        "game.Map.GetMarkerInfo(ravenName)",
        "game.Compass.FindMarkersByIconClass({ravenClass})",
        "game.Compass.HideMarker(ravenName)",
        "retryLimit = 20",
        "SCHEDULE_FAILED",
        "observedKilled",
        "staleTicketCancelled=true",
        "mapmenuDependency=false progressionWrites=false",
    )
    event_missing = [token for token in event_required if token not in event_text]
    shared.b.check(not event_missing, f"Gameplay v3.2 contract missing: {event_missing}")
    for token in (
        "CompletionistMapV104ObserveRavenCompletion",
        "CompletionistMapV104UidRavenTrackedName",
        "mapIconCollision",
        "MapOn.Update",
        "util.create_thread",
    ):
        shared.b.check(token not in event_text, f"Gameplay hook has mapmenu dependency: {token}")
    proof = {
        "schema": 5,
        "result": RESULT,
        "branch_contract": BRANCH,
        "base_head": BASE_HEAD,
        "shared_loader_runtime_success_head": SHARED_LOADER_RUNTIME_SUCCESS_HEAD,
        "source_root": "pinned frozen Raven production baseline (read-only)",
        "source_sha256": {**shared_proof["source_sha256"], EVENTS: EVENTS_SHA},
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
            "selection_identity_source": "MapOn.MapCollisionChangeHandler exact collision table object reference",
            "selection_fallback": None,
            "selection_state_machine": ["none", "candidate-custom", "armed-custom"],
            "selection_frame_ttl": None,
            "selection_armed_one_shot": True,
            "selection_arm_signal": (
                "GetShowOnCompassPrompt visible with completionistMapV100Selected=true "
                "and currMarkerID=nil"
            ),
            "confirmed_stock_signal": (
                "visible GetShowOnCompassPrompt with currMarkerID set; action guard "
                "repeats currMarkerID check"
            ),
            "incidental_noncustom_collision_policy": (
                "ignore callback alone; defer to prompt owner or prompt availability"
            ),
            "selection_disarm": [
                "different custom collision replaces identity",
                "visible native stock prompt with currMarkerID",
                "visible non-Raven custom prompt",
                "prompt unavailable",
                "MapOn.SubmenuExit",
                "MapOn.Exit",
                "MapOn.ClearIcons",
                "armed action consumption",
                "action without prompt arm",
                "custom prompt owner lost before action",
                "real Raven completion",
            ],
            "native_identity_source": "game.Map.GetMarkerInfo(Name).Id",
            "same_visual_resource_for_both_map_markers": True,
            "selected_name_routed_to_native_compass": True,
            "selected_uid_used_for_active_target_comparison": True,
            "single_active_custom_target_policy": True,
            "replacement_hide_failure_policy": "refuse replacement; never broaden hide scope",
            "stock_target_replace_policy_preserved": True,
            "new_wad_resource_identity": False,
            "compassgraph_changed": False,
            "lifecycle_observation": True,
            "gameplay_hook": "precisionchallenge.OnHitByWeapon post-native ravenKilled",
            "gameplay_hook_byte_identical_to_v31": True,
            "gameplay_cleanup_owner": "persistent precisionchallenge Raven lifecycle",
            "gameplay_mapmenu_dependency": False,
            "gameplay_target_match": "CompletionistRaven enumeration plus exact real marker Id",
            "rearm_hooks": ["OnRestoreCheckpoint", "OnStart"],
            "completion_latch_reversible": True,
            "polling": False,
            "event_retry": "level.timer.StartLevelTimer: 0.1 seconds, at most 20, ticket cancelled by false restore/start",
            "event_retry_schedule_failure_safe": True,
            "twin_cleanup_hooks": ["MapOn.SubmenuExit", "MapOn.Exit", "MapOn.ClearIcons"],
            "production_destroy_recycles_twin": False,
            "completion_oracle": "native precisionchallenge ravenKilled after native callback",
            "completion_cleanup_scope": "exact real Raven CompletionistRaven target only",
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
        "runtime_result": "not tested; human runtime matrix required",
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
        print("RAVEN_UID_COMPASS_LIFECYCLE_V32_REBUILD_VERIFIED")
        return

    existing = {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob("*") if p.is_file()}
    shared.b.check(existing <= set(files), "Unexpected stale candidate file")
    for rel, raw in files.items():
        shared.b.write_bytes_atomic(OUTPUT, OUTPUT / rel, raw, "uid-lifecycle v3.2 candidate")
    shared.b.write_bytes_atomic(
        REPORT.parent,
        REPORT,
        (json.dumps(proof, indent=2) + "\n").encode("utf-8"),
        "uid-lifecycle v3.2 proof",
    )

    print(RESULT)
    print(json.dumps(proof["files"], indent=2))
    print("  shared-loader binary candidate unchanged: true")
    print("  new WAD resource identity: false")
    print("  collision-table candidate plus prompt-armed identity: true")
    print("  armed selection frame TTL: none")
    print("  gameplay-side exact real cleanup: true")
    print("  lifecycle/progression writes: false")
    print("  Twin depends on live original UI object: false")
    print("  map title behavior changed: false")
    print("  runtime test performed: false")


if __name__ == "__main__":
    main()
