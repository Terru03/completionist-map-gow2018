#!/usr/bin/env python3
"""Build live loaded-seal read over the installed stock Nornir markers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import importlib.util

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_saved_v2_builder", HERE / "build-nornir-stock-saved-state-v2-test.py")
assert spec is not None and spec.loader is not None
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
v1 = v2.v1

MAP = v2.MAP
RUNIC = v1.stock.base.RUNIC_LUA
TEMPLATE = HERE / "nornir-native-map-saved-state-v3.lua"
READER = v2.READER
RUNIC_READER = HERE / "nornir-loaded-seal-reader.lua"
SOURCE = v2.SOURCE
GAME = v2.GAME
OUT = ROOT / "build/nornir-stock-saved-state-v3-test/candidate/game-root"
REPORT = ROOT / "build/nornir-stock-saved-state-v3-test/report.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def paths() -> str:
    result = []
    seen = set()
    for row in v1.stock.base.rows():
        if row["family"] != "nornir_chest":
            continue
        source = row["source"]
        native = row["native"]
        chain = source["transform_chain"]
        placement = [i for i, node in enumerate(chain)
                     if node["record_id"] == native["placement_final_record_id"]]
        v1.need(len(placement) == 1 and placement[0] >= 2 and
                chain[0]["name"] == "gochestscript_rn" and
                chain[1]["name"] == "gochest_locked_parent",
                "runic live path differs")
        level = Path(source["wad"]).stem
        path = [node["name"] for node in chain[placement[0]:]]
        script = [node["name"] for node in chain[1:]]
        v1.need(path[0] == native["placement_object_name"] and
                (level, tuple(path)) not in seen,
                "runic placement differs or repeats")
        seen.add((level, tuple(path)))
        cid = row["catalogue_id"]
        encoded = lambda values: "{" + ",".join(json.dumps(value) for value in values) + "}"
        result.append("    [%s]={Level=%s,Path=%s,ScriptPath=%s}," % (
            json.dumps(cid), json.dumps(level), encoded(path), encoded(script)))
    v1.need(len(result) == 22, "Nornir live path count differs")
    return "\n".join(result)


def build() -> tuple[dict[str, bytes], dict]:
    prior = json.loads(v2.REPORT.read_text(encoding="utf-8"))
    old_template, old_reader = v1.TEMPLATE, v1.READER
    try:
        v1.TEMPLATE, v1.READER = TEMPLATE, READER
        outputs, old_report = v1.build(SOURCE)
    finally:
        v1.TEMPLATE, v1.READER = old_template, old_reader
    token = b"-- @@NORNIR_LOADED_PATHS@@"
    v1.need(outputs[MAP].count(token) == 1, "loaded path token differs")
    map_raw = outputs[MAP].replace(token, paths().encode("ascii"), 1)
    old_map = (v2.OUT / MAP).read_bytes()
    marker = b"-- BEGIN COMPLETIONIST V0.10.5 NORNIR SAVED STATE TEST"
    v1.need(old_map.count(marker) == map_raw.count(marker) == 1 and
            old_map.split(marker, 1)[0] == map_raw.split(marker, 1)[0],
            "Raven map prefix changed")
    v1.need(sha(old_map) == prior["after_sha256"] and
            b"CompletionistNornirObserveSeals" in map_raw and
            b"NORNIR_SNAPSHOT_V1" in map_raw,
            "loaded seal read or checkpoint changed")
    old_runic = outputs[RUNIC]
    runic_raw = old_runic + b"\n" + RUNIC_READER.read_bytes()
    known_maps = {sha(old_map), sha(map_raw)}
    known_runics = {sha(old_runic), sha(runic_raw)}
    for version in ("v3", "v4", "v5"):
        candidate_root = ROOT / f"build/nornir-stock-saved-state-{version}-test/candidate/game-root"
        if (candidate_root / MAP).exists():
            known_maps.add(sha((candidate_root / MAP).read_bytes()))
        if (candidate_root / RUNIC).exists():
            known_runics.add(sha((candidate_root / RUNIC).read_bytes()))
    if (GAME / MAP).exists() and b"CompletionistNornir" in (GAME / MAP).read_bytes():
        known_maps.add(sha((GAME / MAP).read_bytes()))
    if (GAME / RUNIC).exists() and b"CompletionistNornir" in (GAME / RUNIC).read_bytes():
        known_runics.add(sha((GAME / RUNIC).read_bytes()))
    v1.need(runic_raw.startswith(old_runic) and
            b"CompletionistNornirObserveSeals" in runic_raw and
            sha((GAME / MAP).read_bytes()) in known_maps and
            sha((GAME / RUNIC).read_bytes()) in known_runics,
            "installed map or runic script differs")
    for name, file in old_report["files"].items():
        if name != MAP:
            v1.need(file == json.loads(v1.REPORT.read_text(encoding="utf-8"))["files"][name],
                    "stock marker file changed")
    report = {
        "schema": 1,
        "kind": "NORNIR_STOCK_SAVED_STATE_LOADED_SEALS_TEST",
        "files": {
            MAP: {"before": sha(old_map), "after": sha(map_raw)},
            RUNIC: {"before": sha(old_runic), "after": sha(runic_raw)},
        },
        "prior_operation_kind": "NORNIR_STOCK_SAVED_STATE_MAP_OPEN_OVERLAY_TEST",
        "required_native_bridge_sha256": prior["required_native_bridge_sha256"],
        "checkpoint_contract": prior["checkpoint_contract"],
        "raven_prefix_byte_identical": True,
        "stock_resources_byte_identical": True,
        "loaded_parent_paths": 22,
    }
    outputs[MAP], outputs[RUNIC] = map_raw, runic_raw
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
    print("NORNIR_STOCK_LOADED_SEALS_OFFLINE_BUILT parents=22")
    print(REPORT)


if __name__ == "__main__":
    main()
