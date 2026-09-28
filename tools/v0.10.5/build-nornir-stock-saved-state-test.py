#!/usr/bin/env python3
"""Build exact Nornir chest checkpoint reads on the Raven-safe stock icons."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import nornir_checkpoint_keys as keys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_stock_base", HERE / "build-nornir-stock-family-test.py")
assert spec is not None and spec.loader is not None
stock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock)

MAP = stock.base.MAP_LUA
TEMPLATE = HERE / "nornir-native-map-saved-state.lua"
READER = HERE / "nornir-saved-reader.lua"
OUT = REPO / "build/nornir-stock-saved-state-test/candidate/game-root"
REPORT = REPO / "build/nornir-stock-saved-state-test/report.json"
BRIDGE_SHA256 = "cc91a2ea4475c83085488c33bb0ece223f958054c1a4ac71d26d67a31a84f7b7"


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build(game: Path = stock.base.GAME) -> tuple[dict[str, bytes], dict]:
    outputs, report = stock.build(game)
    definitions = copy.deepcopy(stock.base.rows())
    for row in definitions:
        row["marker"]["compass_class"] = stock.COMPASS[row["family"]]
    source = (game / MAP).read_bytes()
    raven = stock.handoff.inject(source)
    lua, proof = stock.base.build_lua(raven, definitions, TEMPLATE)
    reader = READER.read_text(encoding="utf-8")
    need(lua.count(b"-- @@NORNIR_SAVED_READER@@") == 1 and
         lua.count(b"@@NORNIR_SAVE_CONTRACT@@") == 1,
         "saved reader template tokens differ")
    contract = keys.contract(keys.build())
    lua = lua.replace(b"-- @@NORNIR_SAVED_READER@@", reader.encode("utf-8"), 1)
    lua = lua.replace(b"@@NORNIR_SAVE_CONTRACT@@", contract.encode("ascii"), 1)
    lua = lua.replace(
        b"Each Nornir family has its own map resource, compass class, and chest key.",
        b"Nornir families use stock map art, matching compass classes, and exact chest keys.", 1)
    lua = lua.replace(b"renderer=dedicated compass=dedicated checkpoint=exact_or_unknown",
                      b"renderer=stock_family compass=stock_family checkpoint=exact_or_unknown", 1)
    need(lua.startswith(raven) and lua != outputs[MAP] and
         b"NORNIR_SNAPSHOT_V1" in lua and contract.encode() in lua and
         b"renderer=stock_family compass=stock_family" in lua,
         "stock saved-state layer or Raven prefix differs")
    need(sha((game / MAP).read_bytes()) == report["source_sha256"][MAP],
         "Raven source changed during build")
    outputs[MAP] = lua
    report["files"][MAP] = {"sha256": sha(lua), "bytes": len(lua)}
    report["proof"][MAP] = {**proof,
                            "exact_checkpoint_contract": contract,
                            "raven_lua_exact_prefix": True,
                            "missing_chest_state": "UNKNOWN",
                            "save_boundary_clears_prior_chest_state": True}
    report["kind"] = "NORNIR_STOCK_FAMILY_SAVED_STATE_TEST"
    report["completion_state_enabled"] = "loaded_events_and_exact_checkpoint_or_unknown"
    report["required_native_bridge_sha256"] = BRIDGE_SHA256
    return outputs, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=stock.base.GAME)
    args = parser.parse_args()
    outputs, report = build(args.game_root)
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_STOCK_SAVED_STATE_OFFLINE_BUILT rows=88 chests=22")
    print(REPORT)


if __name__ == "__main__":
    main()
