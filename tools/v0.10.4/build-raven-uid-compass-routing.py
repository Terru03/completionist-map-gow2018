#!/usr/bin/env python3
"""Build the UID-aware Raven compass-routing probe offline.

The proven shared-loader Twin remains the binary/map base.  This builder changes no
resource identity and appends one Lua-only routing layer that distinguishes the two
shared Raven map objects by exact live object reference, then routes the selected native
marker Name/Id through the already-proven CompletionistRaven compass class.

No game file is written by this builder.
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

spec = importlib.util.spec_from_file_location("uid_routing_shared_base", SHARED_PATH)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)

BRANCH = "codex/v104-raven-uid-compass-routing"
BASE_HEAD = "e29b841b2e8799ebe90780413c8330755415183f"
RESULT = "RAVEN_UID_COMPASS_ROUTING_OFFLINE_PROOF_PASSED"
OUTPUT = REPO / "build/v0.10.4-raven-uid-compass-routing/offline/candidate/game-root"
REPORT = REPO / "archive/field-logs/completionist-v104-raven-uid-compass-routing-offline.json"
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

    # This experiment is Lua-only on top of the runtime-proven shared-loader binary map
    # setup.  The three binary candidate files must remain byte-for-byte identical.
    for rel in (shared.MASTER, shared.COORDS, shared.UI):
        shared.b.check(outputs[rel] == shared_files[rel], f"Shared-loader binary changed: {rel}")

    text = ROUTING_PATH.read_text(encoding="utf-8")
    required = (
        "collision == self.completionistSharedLoaderTwinGO",
        "collision == self.completionistMapV100MapIconGO",
        "game.Map.GetMarkerInfo(name)",
        "game.Compass.FindMarkersByIconClass({ravenClass})",
        "game.Compass.ShowMarker(selected.Name, ravenClass)",
        "game.Compass.HideMarker(selected.Name)",
        "Completionist_V103_Veithurgard_Raven_01",
        "Completionist_V104_Veithurgard_Raven_Twin_01",
        "CompletionistMapV104UidAwareRavenCompassRouting",
    )
    missing = [token for token in required if token not in text]
    shared.b.check(not missing, f"UID-routing source contract missing: {missing}")

    forbidden = (
        "SetMarkerState",
        "challengeComplete",
        "OPENED",
        "SetToken",
        "SetProgress",
    )
    present = [token for token in forbidden if token in text]
    shared.b.check(not present, f"Lifecycle/progression token present in routing shim: {present}")

    proof = {
        "schema": 1,
        "result": RESULT,
        "branch_contract": BRANCH,
        "base_head": BASE_HEAD,
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
        },
        "routing_contract": {
            "selection_identity_source": "exact live map object reference retained by shared-loader",
            "native_identity_source": "game.Map.GetMarkerInfo(Name).Id",
            "same_visual_resource_for_both_map_markers": True,
            "selected_name_routed_to_native_compass": True,
            "selected_uid_used_for_active-target comparison": True,
            "single_active_custom_target_policy": True,
            "stock_target_replace_policy_preserved": True,
            "new_wad_resource_identity": False,
            "compassgraph_changed": False,
            "lifecycle_changes": False,
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
            "maximum_active_user_target": 1,
        },
        "candidate_file_count": len(outputs),
        "game_files_written": False,
        "runtime_test_performed": False,
        "ready_for_runtime_test": True,
        "retired_candidates_used": False,
        "progression_or_marker_state_writes": False,
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
        print("RAVEN_UID_COMPASS_ROUTING_REBUILD_VERIFIED")
        return

    existing = {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob("*") if p.is_file()}
    shared.b.check(existing <= set(files), "Unexpected stale candidate file")
    for rel, raw in files.items():
        shared.b.write_bytes_atomic(OUTPUT, OUTPUT / rel, raw, "uid-routing candidate")
    shared.b.write_bytes_atomic(
        REPORT.parent,
        REPORT,
        (json.dumps(proof, indent=2) + "\n").encode("utf-8"),
        "uid-routing proof",
    )

    print(RESULT)
    print(json.dumps(proof["files"], indent=2))
    print("  shared-loader binary candidate unchanged: true")
    print("  new WAD resource identity: false")
    print("  lifecycle/progression writes: false")
    print("  runtime test performed: false")


if __name__ == "__main__":
    main()
