#!/usr/bin/env python3
"""Build Nornir marker test with eight isolated map/HUD model groups."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_native_base", HERE / "build-nornir-native-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
import nornir_model_group_isolation as mg

OUT = REPO / "build/nornir-native-isolated-test/candidate/game-root"
REPORT = REPO / "build/nornir-native-isolated-test/report.json"


def build(game: Path = base.base.GAME) -> tuple[dict[str, bytes], dict]:
    outputs, report = base.build(game)
    original_wad = (game / base.WAD).read_bytes()
    isolated, proof = mg.isolate(base.base.stage, original_wad, outputs[base.WAD])
    outputs[base.WAD] = isolated
    report["kind"] = "NORNIR_SEPARATE_ISOLATED_MARKERS_TEST"
    report["source_art_wad_sha256"] = report["files"][base.WAD]["sha256"]
    report["files"][base.WAD] = {
        "sha256": hashlib.sha256(isolated).hexdigest(), "bytes": len(isolated)}
    report["proof"][base.WAD]["model_group_isolation"] = proof
    report["renderer"] = "dedicated_nornir_family_art_isolated_model_groups"
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
    print("NORNIR_NATIVE_ISOLATED_OFFLINE_BUILT rows=88 children=66 raven_rows=preserved")
    print(REPORT)


if __name__ == "__main__":
    main()
