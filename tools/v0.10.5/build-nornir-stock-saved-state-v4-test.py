#!/usr/bin/env python3
"""Build restored seal snapshots that survive late map save boundaries."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v3_builder", HERE / "build-nornir-stock-saved-state-v3-test.py")
assert spec is not None and spec.loader is not None
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)

MAP = v3.MAP
RUNIC = v3.RUNIC
TEMPLATE = HERE / "nornir-native-map-saved-state-v4.lua"
EVENTS = HERE / "nornir-restored-seal-events.lua"
GAME = v3.GAME
OUT = ROOT / "build/nornir-stock-saved-state-v4-test/candidate/game-root"
REPORT = ROOT / "build/nornir-stock-saved-state-v4-test/report.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build() -> tuple[dict[str, bytes], dict]:
    prior = json.loads(v3.REPORT.read_text(encoding="utf-8"))
    old_template = v3.TEMPLATE
    try:
        v3.TEMPLATE = TEMPLATE
        outputs, _ = v3.build()
    finally:
        v3.TEMPLATE = old_template
    old_map = (v3.OUT / MAP).read_bytes()
    old_runic = (v3.OUT / RUNIC).read_bytes()
    map_raw = outputs[MAP]
    runic_raw = outputs[RUNIC] + b"\n" + EVENTS.read_bytes()
    marker = b"-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST"
    v3.v1.need(old_map.count(marker) == map_raw.count(marker) == 1 and
               old_map.split(marker, 1)[0] == map_raw.split(marker, 1)[0] and
               sha(old_map) == prior["files"][MAP]["after"] and
               sha(old_runic) == prior["files"][RUNIC]["after"] and
               outputs[RUNIC] == old_runic and
               runic_raw.startswith(old_runic) and
               b"pendingSnapshots" in map_raw and
               b"event=snapshot" in runic_raw,
               "saved seal snapshot build differs")
    next_root = ROOT / "build/nornir-stock-saved-state-v5-test/candidate/game-root"
    known_maps = {sha(old_map), sha(map_raw)}
    known_runics = {sha(old_runic), sha(runic_raw)}
    for root in (OUT, next_root):
        if (root / MAP).exists():
            known_maps.add(sha((root / MAP).read_bytes()))
        if (root / RUNIC).exists():
            known_runics.add(sha((root / RUNIC).read_bytes()))
    if (GAME / MAP).exists() and b"CompletionistNornir" in (GAME / MAP).read_bytes():
        known_maps.add(sha((GAME / MAP).read_bytes()))
    if (GAME / RUNIC).exists() and b"CompletionistNornir" in (GAME / RUNIC).read_bytes():
        known_runics.add(sha((GAME / RUNIC).read_bytes()))
    v3.v1.need(sha((GAME / MAP).read_bytes()) in known_maps and
               sha((GAME / RUNIC).read_bytes()) in known_runics,
               "installed Nornir scripts differ")
    outputs[MAP], outputs[RUNIC] = map_raw, runic_raw
    report = {
        "schema": 1,
        "kind": "NORNIR_STOCK_SAVED_STATE_RESTORED_SEALS_TEST",
        "files": {
            MAP: {"before": sha(old_map), "after": sha(map_raw)},
            RUNIC: {"before": sha(old_runic), "after": sha(runic_raw)},
        },
        "prior_operation_kind": "NORNIR_STOCK_SAVED_STATE_LOADED_SEALS_OVERLAY_TEST",
        "required_native_bridge_sha256": prior["required_native_bridge_sha256"],
        "checkpoint_contract": prior["checkpoint_contract"],
        "raven_prefix_byte_identical": True,
        "stock_resources_byte_identical": True,
    }
    return outputs, report


def main() -> None:
    outputs, report = build()
    for relative in (MAP, RUNIC):
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(outputs[relative])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_STOCK_RESTORED_SEALS_OFFLINE_BUILT")
    print(REPORT)


if __name__ == "__main__":
    main()
