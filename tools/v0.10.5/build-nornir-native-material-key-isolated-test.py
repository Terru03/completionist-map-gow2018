#!/usr/bin/env python3
"""Build custom Nornir art with independent material identity hashes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_node_base", HERE / "build-nornir-native-node-isolated-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
import nornir_material_key_isolation as materials

OUT = REPO / "build/nornir-native-material-key-isolated-test/candidate/game-root"
REPORT = REPO / "build/nornir-native-material-key-isolated-test/report.json"


def build(game: Path = base.base.base.base.GAME) -> tuple[dict[str, bytes], dict]:
    outputs, report = base.build(game)
    wad = base.base.base.WAD
    raven_wad = (game / wad).read_bytes()
    isolated, proof = materials.isolate(base.base.base.base.stage, raven_wad,
                                        outputs[wad])
    report["source_node_isolated_wad_sha256"] = report["files"][wad]["sha256"]
    outputs[wad] = isolated
    report["files"][wad] = {
        "sha256": hashlib.sha256(isolated).hexdigest(), "bytes": len(isolated)}
    report["proof"][wad]["material_key_isolation"] = proof
    report["kind"] = "NORNIR_SEPARATE_MATERIAL_KEY_ISOLATED_MARKERS_TEST"
    report["renderer"] = "dedicated_nornir_art_with_independent_material_keys"
    return outputs, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=base.base.base.base.GAME)
    args = parser.parse_args()
    outputs, report = build(args.game_root)
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_MATERIAL_KEY_ISOLATED_OFFLINE_BUILT rows=88 raven_material=unchanged")
    print(REPORT)


if __name__ == "__main__":
    main()
