#!/usr/bin/env python3
"""Build map-open checkpoint read over installed Raven-safe stock Nornir art."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v1", HERE / "build-nornir-stock-saved-state-test.py")
assert spec is not None and spec.loader is not None
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)

MAP = v1.MAP
TEMPLATE = HERE / "nornir-native-map-saved-state-v2.lua"
READER = HERE / "nornir-saved-reader-v2.lua"
SOURCE = REPO / "build/nornir-native-material-key-isolated-test/source-game-root"
OUT = REPO / "build/nornir-stock-saved-state-v2-test/candidate/game-root"
REPORT = REPO / "build/nornir-stock-saved-state-v2-test/report.json"
GAME = v1.stock.base.GAME


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build() -> tuple[bytes, dict]:
    prior = json.loads(v1.REPORT.read_text(encoding="utf-8"))
    old_template, old_reader = v1.TEMPLATE, v1.READER
    try:
        v1.TEMPLATE, v1.READER = TEMPLATE, READER
        outputs, report = v1.build(SOURCE)
    finally:
        v1.TEMPLATE, v1.READER = old_template, old_reader
    original = (v1.OUT / MAP).read_bytes()
    candidate = outputs[MAP]
    token = b"-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST"
    v1.need(original.count(token) == candidate.count(token) == 1 and
            original.split(token, 1)[0] == candidate.split(token, 1)[0],
            "Raven prefix changed")
    v1.need(all(prior["files"][name] == report["files"][name]
                for name in prior["files"] if name != MAP),
            "stock Nornir resource changed")
    v1.need(sha(original) == prior["files"][MAP]["sha256"] and
            candidate != original and
            b"checkpoint_initial=" in candidate and
            b"Saved:ReadOnce" in candidate,
            "map-open reader missing")
    v1.need(sha((GAME / MAP).read_bytes()) in {sha(original), sha(candidate)},
            "installed saved-state map differs from prior or v2 candidate")
    return candidate, {
        "schema": 1, "kind": "NORNIR_STOCK_SAVED_STATE_MAP_OPEN_TEST",
        "before_sha256": sha(original), "after_sha256": sha(candidate),
        "bytes": len(candidate),
        "required_native_bridge_sha256": v1.BRIDGE_SHA256,
        "checkpoint_contract": prior["proof"][MAP]["exact_checkpoint_contract"],
        "raven_prefix_byte_identical": True,
        "stock_resources_byte_identical": True,
        "changed_file": MAP,
    }


def main() -> None:
    candidate, report = build()
    target = OUT / MAP
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_STOCK_SAVED_STATE_MAP_OPEN_OFFLINE_BUILT")
    print(REPORT)


if __name__ == "__main__":
    main()
