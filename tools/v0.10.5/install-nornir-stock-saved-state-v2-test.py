#!/usr/bin/env python3
"""Install or roll back map-Lua-only synchronous Nornir checkpoint read."""
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
    "nornir_stock_saved_v1_installer", HERE / "install-nornir-stock-saved-state-test.py")
assert spec is not None and spec.loader is not None
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
base = prior.base

BUILD = ROOT / "build/nornir-stock-saved-state-v2-test"
REPORT = BUILD / "report.json"
BACKUPS = BUILD / "backups"
MAP = prior.MAP
GAME = prior.GAME
KIND = "NORNIR_STOCK_SAVED_STATE_MAP_OPEN_OVERLAY_TEST"


def candidate() -> dict:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    old = json.loads(prior.REPORT.read_text(encoding="utf-8"))
    base.need(report.get("kind") == "NORNIR_STOCK_SAVED_STATE_MAP_OPEN_TEST" and
              report.get("before_sha256") == old["files"][MAP]["sha256"] and
              report.get("checkpoint_contract") ==
              old["proof"][MAP]["exact_checkpoint_contract"] and
              report.get("raven_prefix_byte_identical") is True and
              report.get("stock_resources_byte_identical") is True and
              report.get("required_native_bridge_sha256") == prior.manifests()[1]["required_native_bridge_sha256"] and
              base.sha(BUILD / "candidate/game-root" / MAP) == report.get("after_sha256"),
              "map-open checkpoint candidate differs")
    return report


def read_operation(journal: Path, game: Path) -> dict:
    journal = base.safe(journal)
    data = json.loads(journal.read_text(encoding="utf-8"))
    base.need(data.get("kind") == KIND and data.get("schema") == 1 and
              data.get("game_root") == str(game.absolute()) and
              journal.parent.is_relative_to(base.safe(BACKUPS)),
              "unknown map-open operation")
    return data


def verify(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] == "installed", "map-open overlay not installed")
    report = candidate()
    old_operation = prior.read_operation(Path(data["prior_operation"]), game)
    base.need(old_operation["status"] == "installed", "prior overlay not installed")
    stock_operation = base.read_operation(Path(old_operation["base_operation"]), game)
    base.need(stock_operation["status"] == "installed", "stock base not installed")
    for relative, file in stock_operation["files"].items():
        expected = report["after_sha256"] if relative == MAP else file["after"]
        base.need(base.sha(base.target(game, relative)) == expected,
                  f"installed file differs: {relative}")
    base.need(base.sha(journal.parent / "before" / MAP) == report["before_sha256"],
              "map-open backup differs")
    base.need(base.sha(game / "dxgi.dll") == report["required_native_bridge_sha256"],
              "Nornir bridge differs")
    old_report = prior.manifests()[1]
    for relative, expected in old_report["untouched_sha256"].items():
        base.need(base.sha(game / relative) == expected,
                  f"Raven resource differs: {relative}")


def rollback(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "unknown map-open operation status")
    report = candidate()
    target = base.target(game, MAP)
    current = base.sha(target)
    if current != report["before_sha256"]:
        base.need(current == report["after_sha256"], "map changed after map-open install")
        base.atomic_copy(journal.parent / "before" / MAP, target,
                         report["before_sha256"], report["after_sha256"])
    data["status"] = "rolled_back"
    base.write_json(journal, data)
    prior.verify(Path(data["prior_operation"]), game, stopped)


def install(prior_operation: Path, game: Path = GAME,
            stopped=base.game_stopped) -> Path:
    stopped()
    prior.verify(prior_operation, game, stopped)
    report = candidate()
    directory = base.safe(BACKUPS / uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    backup = directory / "before" / MAP
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base.target(game, MAP), backup)
    base.need(base.sha(backup) == report["before_sha256"], "map backup differs")
    journal = directory / "operation.json"
    data = {"schema": 1, "kind": KIND, "status": "prepared",
            "game_root": str(game.absolute()),
            "prior_operation": str(prior_operation.absolute()),
            "before": report["before_sha256"], "after": report["after_sha256"]}
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
    parser.add_argument("--prior-operation", type=Path)
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        base.need(args.prior_operation is not None and args.operation is None,
                  "install requires --prior-operation")
        print(install(args.prior_operation))
    else:
        base.need(args.operation is not None and args.prior_operation is None,
                  "verify/rollback requires --operation")
        if args.action == "verify":
            verify(args.operation)
            print("NORNIR_STOCK_SAVED_STATE_MAP_OPEN_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print("NORNIR_STOCK_SAVED_STATE_MAP_OPEN_ROLLED_BACK")


if __name__ == "__main__":
    main()
