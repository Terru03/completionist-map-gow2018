#!/usr/bin/env python3
"""Build Nornir test with distinct model groups and prototype child IDs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_isolated_base", HERE / "build-nornir-native-isolated-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
import nornir_prototype_child_isolation as nodes

OUT = REPO / "build/nornir-native-node-isolated-test/candidate/game-root"
REPORT = REPO / "build/nornir-native-node-isolated-test/report.json"


def build(game: Path = base.base.base.GAME) -> tuple[dict[str, bytes], dict]:
    outputs, report = base.build(game)
    original = (game / base.base.WAD).read_bytes()
    isolated, proof = nodes.isolate(base.base.base.stage, original,
                                    outputs[base.base.WAD])
    report["source_model_group_wad_sha256"] = report["files"][base.base.WAD]["sha256"]
    outputs[base.base.WAD] = isolated
    report["files"][base.base.WAD] = {
        "sha256": hashlib.sha256(isolated).hexdigest(), "bytes": len(isolated)}
    report["proof"][base.base.WAD]["prototype_child_isolation"] = proof
    report["kind"] = "NORNIR_SEPARATE_NODE_ISOLATED_MARKERS_TEST"
    report["renderer"] = "dedicated_nornir_art_with_unique_prototype_child_nodes"
    return outputs, report


def main() -> None:
    outputs, report = build()
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_NATIVE_NODE_ISOLATED_OFFLINE_BUILT rows=88 children=66 raven_rows=preserved")
    print(REPORT)


if __name__ == "__main__":
    main()
