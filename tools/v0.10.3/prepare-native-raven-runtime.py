"""Prepare Raven-only native DCB runtime copies outside the game directory.

This uses the validated v0.10.3 DCB builder, but changes the new Raven token's
InitState to kUndiscovered (0) before runtime use. Stock DCBs are read-only.
Nothing is installed and Compass.ShowMarker is never called here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_dcb_proof", HERE / "build-native-raven-dcb-proof.py"
)
proof = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(proof)
native = proof.native


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_raven_marker(master: native.Dcb) -> int:
    matches = [
        marker
        for _realm, _region, _region_record, marker in proof.iter_markers(master)
        if master.unpack("<Q", marker)[0] == proof.RAVEN_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one Raven marker, found {len(matches)}")
    return matches[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--game-root",
        type=Path,
        default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"),
    )
    ap.add_argument("--repo-root", type=Path, default=HERE.parents[1])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    game_root = args.game_root.resolve()
    repo_root = args.repo_root.resolve()
    stock_dir = game_root / "exec/dc/pc_le"
    runtime_root = repo_root / "build/v0.10.3-native-runtime/game-root"
    runtime_dir = runtime_root / "exec/dc/pc_le"
    report_path = (
        args.output.resolve()
        if args.output
        else repo_root / "build/v0.10.3-native-runtime/prepared.json"
    )

    if runtime_root.is_relative_to(game_root) or report_path.is_relative_to(game_root):
        raise ValueError("Runtime preparation must stay outside the game directory")

    stock_paths = {name: stock_dir / name for name in proof.EXPECTED}
    stock_hashes = {}
    for name, path in stock_paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256(path)
        if digest != proof.EXPECTED[name]:
            raise ValueError(f"{name} hash differs from researched build")
        stock_hashes[name] = digest

    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_dir.mkdir(parents=True)

    master = native.Dcb(stock_paths["mapmaster.dcb"])
    coords = native.Dcb(stock_paths["mapcoords.dcb"])
    graph = native.Dcb(stock_paths["compassgraph.dcb"])

    master_blob, master_relocs, marker_meta = proof.patch_mapmaster(master)
    coords_blob, coords_relocs, coord_meta = proof.patch_mapcoords(coords)
    graph_blob, graph_relocs, graph_meta = proof.patch_compassgraph(coords, graph)

    outputs = {
        "mapmaster.dcb": runtime_dir / "mapmaster.dcb",
        "mapcoords.dcb": runtime_dir / "mapcoords.dcb",
        "compassgraph.dcb": runtime_dir / "compassgraph.dcb",
    }
    proof.rebuild_dcb(master, master_blob, master_relocs, outputs["mapmaster.dcb"])
    proof.rebuild_dcb(coords, coords_blob, coords_relocs, outputs["mapcoords.dcb"])
    proof.rebuild_dcb(graph, graph_blob, graph_relocs, outputs["compassgraph.dcb"])

    # The offline proof deliberately used discovered=1. Runtime lookup testing does
    # not need discovery, so neutralise only our new token before installation.
    runtime_master = native.Dcb(outputs["mapmaster.dcb"])
    raven_marker = find_raven_marker(runtime_master)
    raw = bytearray(outputs["mapmaster.dcb"].read_bytes())
    raw[runtime_master.file_base + raven_marker + 0x1C] = 0
    outputs["mapmaster.dcb"].write_bytes(raw)

    patched_master = native.Dcb(outputs["mapmaster.dcb"])
    patched_coords = native.Dcb(outputs["mapcoords.dcb"])
    patched_graph = native.Dcb(outputs["compassgraph.dcb"])
    verification = proof.verify_candidate(
        patched_master, patched_coords, patched_graph, graph_meta["helper_id"]
    )
    if verification["marker"]["init_state"] != 0:
        raise ValueError("Runtime Raven marker is not neutral/undiscovered")

    stock_after = {name: sha256(path) for name, path in stock_paths.items()}
    if stock_after != stock_hashes:
        raise RuntimeError("A stock game DCB changed during runtime preparation")

    patched_counts = native.inspect(runtime_root)["counts"]
    stock_counts = native.inspect(game_root)["counts"]
    if patched_counts["map_records"] != stock_counts["map_records"] + 1:
        raise ValueError("Runtime map marker count mismatch")
    if patched_counts["coordinates"] != stock_counts["coordinates"] + 1:
        raise ValueError("Runtime coordinate count mismatch")
    if patched_counts["edges"] != stock_counts["edges"] + 1:
        raise ValueError("Runtime graph edge count mismatch")
    if patched_counts["unresolved_graph_endpoints"] != 0:
        raise ValueError("Runtime graph contains unresolved endpoints")

    report = {
        "result": "RUNTIME_DCB_COPIES_PREPARED_NOT_INSTALLED",
        "game_files_written": False,
        "compass_show_called": False,
        "save_files_written": False,
        "candidate": {
            "name": proof.RAVEN_NAME,
            "id": f"{proof.RAVEN_ID:016X}",
            "world_position": proof.RAVEN,
        },
        "runtime_init_state": 0,
        "stock_hashes": stock_hashes,
        "stock_counts": stock_counts,
        "patched_counts": patched_counts,
        "mapmaster_patch": marker_meta,
        "mapcoords_patch": coord_meta,
        "compassgraph_patch": graph_meta,
        "reparse_verification": verification,
        "generated_files": {
            name: {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in outputs.items()
        },
        "installation_status": "NOT_INSTALLED",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"NATIVE_MARKER_CREATE runtime_prepare=true id={proof.RAVEN_ID:016X}")
    print("NATIVE_MARKER_INFO init_state=0 stock_mutation=false")
    print(f"NATIVE_MARKER_INFO report={report_path}")
    print("NATIVE_COMPASS_RESULT show_attempted=false installed=false")


if __name__ == "__main__":
    main()
