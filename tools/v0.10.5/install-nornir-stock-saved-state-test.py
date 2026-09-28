#!/usr/bin/env python3
"""Install or roll back a map-Lua-only Nornir chest checkpoint reader."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_stock_installer", HERE / "install-nornir-stock-family-test.py")
assert spec is not None and spec.loader is not None
stock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock)
base = stock.base

BUILD = ROOT / "build/nornir-stock-saved-state-test"
REPORT = BUILD / "report.json"
BACKUPS = BUILD / "backups"
MAP = "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
GAME = base.GAME
KIND = "NORNIR_STOCK_SAVED_STATE_LUA_OVERLAY_TEST"


def manifests() -> tuple[dict, dict]:
    before = json.loads(stock.base.REPORT.read_text(encoding="utf-8"))
    after = json.loads(REPORT.read_text(encoding="utf-8"))
    base.need(before.get("kind") == stock.base.EXPECTED_KIND and
              after.get("kind") == "NORNIR_STOCK_FAMILY_SAVED_STATE_TEST",
              "unexpected Nornir build kind")
    base.need(set(before["files"]) == set(after["files"]) == base.ALLOWED,
              "candidate file list differs")
    base.need(all(before["files"][name] == after["files"][name]
                  for name in base.ALLOWED - {MAP}) and
              before["files"][MAP] != after["files"][MAP] and
              before["untouched_sha256"] == after["untouched_sha256"],
              "saved-state candidate changed stock or Raven resources")
    proof = after["proof"][MAP]
    base.need(proof.get("raven_lua_exact_prefix") is True and
              proof.get("missing_chest_state") == "UNKNOWN" and
              len(proof.get("exact_checkpoint_contract", "")) == 64 and
              proof.get("save_boundary_clears_prior_chest_state") is True,
              "saved-state safety proof absent")
    base.need(after.get("required_native_bridge_sha256") ==
              "cc91a2ea4475c83085488c33bb0ece223f958054c1a4ac71d26d67a31a84f7b7",
              "native bridge dependency differs")
    base.need(base.sha(BUILD / "candidate/game-root" / MAP) ==
              after["files"][MAP]["sha256"], "saved-state Lua candidate drift")
    return before, after


def read_operation(journal: Path, game: Path) -> dict:
    journal = base.safe(journal)
    data = json.loads(journal.read_text(encoding="utf-8"))
    base.need(data.get("kind") == KIND and data.get("schema") == 1 and
              data.get("game_root") == str(game.absolute()) and
              journal.parent.is_relative_to(base.safe(BACKUPS)),
              "unknown saved-state operation")
    return data


def verify(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] == "installed", "saved-state overlay not installed")
    before, after = manifests()
    original = base.read_operation(Path(data["base_operation"]), game)
    base.need(original["status"] == "installed", "stock base operation not installed")
    for relative, file in original["files"].items():
        expected = after["files"][relative]["sha256"] if relative == MAP else file["after"]
        base.need(base.sha(base.target(game, relative)) == expected,
                  f"installed file differs: {relative}")
    base.need(base.sha(journal.parent / "before" / MAP) ==
              before["files"][MAP]["sha256"], "map backup differs")
    base.need(base.sha(game / "dxgi.dll") ==
              after["required_native_bridge_sha256"], "Nornir bridge differs")
    for relative, expected in after["untouched_sha256"].items():
        base.need(base.sha(game / relative) == expected,
                  f"Raven resource differs: {relative}")


def rollback(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "unknown saved-state operation status")
    before, after = manifests()
    target = base.target(game, MAP)
    current = base.sha(target)
    old_hash = before["files"][MAP]["sha256"]
    new_hash = after["files"][MAP]["sha256"]
    if current != old_hash:
        base.need(current == new_hash, "map changed after saved-state install")
        base.atomic_copy(journal.parent / "before" / MAP, target, old_hash, new_hash)
    data["status"] = "rolled_back"
    base.write_json(journal, data)
    base.verify(Path(data["base_operation"]), game, stopped)


def install(base_operation: Path, game: Path = GAME,
            stopped=base.game_stopped) -> Path:
    stopped()
    base.verify(base_operation, game, stopped)
    before, after = manifests()
    base.need(base.sha(game / "dxgi.dll") ==
              after["required_native_bridge_sha256"], "Nornir bridge differs")
    directory = base.safe(BACKUPS / uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    backup = directory / "before" / MAP
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base.target(game, MAP), backup)
    base.need(base.sha(backup) == before["files"][MAP]["sha256"],
              "map backup differs")
    journal = directory / "operation.json"
    data = {"schema": 1, "kind": KIND, "status": "prepared",
            "game_root": str(game.absolute()),
            "base_operation": str(base_operation.absolute()),
            "before": before["files"][MAP]["sha256"],
            "after": after["files"][MAP]["sha256"],
            "checkpoint_contract": after["proof"][MAP]["exact_checkpoint_contract"]}
    base.write_json(journal, data)
    try:
        data["status"] = "installing"
        base.write_json(journal, data)
        base.atomic_copy(BUILD / "candidate/game-root" / MAP,
                         base.target(game, MAP), data["after"], data["before"])
        data["status"] = "installed"
        base.write_json(journal, data)
        verify(journal, game, stopped)
    except Exception:
        rollback(journal, game, stopped)
        raise
    return journal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "rollback"))
    parser.add_argument("--base-operation", type=Path)
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        base.need(args.base_operation is not None and args.operation is None,
                  "install requires --base-operation")
        print(install(args.base_operation))
    else:
        base.need(args.operation is not None and args.base_operation is None,
                  "verify/rollback requires --operation")
        if args.action == "verify":
            verify(args.operation)
            print("NORNIR_STOCK_SAVED_STATE_OVERLAY_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print("NORNIR_STOCK_SAVED_STATE_OVERLAY_ROLLED_BACK")


if __name__ == "__main__":
    main()
