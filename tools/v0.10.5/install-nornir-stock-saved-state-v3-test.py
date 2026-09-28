#!/usr/bin/env python3
"""Install or roll back exact loaded Nornir seal reads."""
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
    "nornir_saved_v2_installer", HERE / "install-nornir-stock-saved-state-v2-test.py")
assert spec is not None and spec.loader is not None
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
base = prior.base

BUILD = ROOT / "build/nornir-stock-saved-state-v3-test"
REPORT = BUILD / "report.json"
BACKUPS = BUILD / "backups"
MAP = prior.MAP
RUNIC = "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua"
FILES = (MAP, RUNIC)
GAME = prior.GAME
KIND = "NORNIR_STOCK_SAVED_STATE_LOADED_SEALS_OVERLAY_TEST"


def candidate() -> dict:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    old = prior.candidate()
    v1 = prior.prior.manifests()[1]
    base.need(report.get("kind") == "NORNIR_STOCK_SAVED_STATE_LOADED_SEALS_TEST" and
              set(report.get("files", {})) == set(FILES) and
              report["files"][MAP]["before"] == old["after_sha256"] and
              report["files"][RUNIC]["before"] == v1["files"][RUNIC]["sha256"] and
              report.get("checkpoint_contract") == old["checkpoint_contract"] and
              report.get("required_native_bridge_sha256") ==
              old["required_native_bridge_sha256"] and
              report.get("raven_prefix_byte_identical") is True and
              report.get("stock_resources_byte_identical") is True and
              report.get("loaded_parent_paths") == 22,
              "loaded seal candidate differs")
    for name in FILES:
        base.need(base.sha(BUILD / "candidate/game-root" / name) ==
                  report["files"][name]["after"] and
                  report["files"][name]["before"] != report["files"][name]["after"],
                  f"loaded seal file differs: {name}")
    return report


def read_operation(journal: Path, game: Path) -> dict:
    journal = base.safe(journal)
    data = json.loads(journal.read_text(encoding="utf-8"))
    base.need(data.get("kind") == KIND and data.get("schema") == 1 and
              data.get("game_root") == str(game.absolute()) and
              journal.parent.is_relative_to(base.safe(BACKUPS)),
              "unknown loaded seal operation")
    return data


def verify(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] == "installed", "loaded seal overlay not installed")
    report = candidate()
    v2_operation = prior.read_operation(Path(data["prior_operation"]), game)
    base.need(v2_operation["status"] == "installed", "map-open overlay not installed")
    v1_operation = prior.prior.read_operation(Path(v2_operation["prior_operation"]), game)
    base.need(v1_operation["status"] == "installed", "checkpoint overlay not installed")
    stock_operation = base.read_operation(Path(v1_operation["base_operation"]), game)
    base.need(stock_operation["status"] == "installed", "stock marker base not installed")
    for relative, file in stock_operation["files"].items():
        expected = report["files"][relative]["after"] if relative in FILES else file["after"]
        base.need(base.sha(base.target(game, relative)) == expected,
                  f"installed file differs: {relative}")
    for relative in FILES:
        base.need(base.sha(journal.parent / "before" / relative) ==
                  report["files"][relative]["before"],
                  f"loaded seal backup differs: {relative}")
    base.need(base.sha(game / "dxgi.dll") == report["required_native_bridge_sha256"],
              "Nornir bridge differs")
    for relative, expected in prior.prior.manifests()[1]["untouched_sha256"].items():
        base.need(base.sha(game / relative) == expected,
                  f"Raven resource differs: {relative}")


def rollback(journal: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "unknown loaded seal operation status")
    report = candidate()
    for relative in FILES:
        target = base.target(game, relative)
        before = report["files"][relative]["before"]
        after = report["files"][relative]["after"]
        current = base.sha(target)
        if current != before:
            base.need(current == after, f"file changed after loaded seal install: {relative}")
            base.atomic_copy(journal.parent / "before" / relative,
                             target, before, after)
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
    for relative in FILES:
        backup = directory / "before" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base.target(game, relative), backup)
        base.need(base.sha(backup) == report["files"][relative]["before"],
                  f"loaded seal backup differs: {relative}")
    journal = directory / "operation.json"
    data = {"schema": 1, "kind": KIND, "status": "prepared",
            "game_root": str(game.absolute()),
            "prior_operation": str(prior_operation.absolute()),
            "files": report["files"]}
    base.write_json(journal, data)
    try:
        data["status"] = "installing"
        base.write_json(journal, data)
        for relative in FILES:
            hashes = report["files"][relative]
            base.atomic_copy(BUILD / "candidate/game-root" / relative,
                             base.target(game, relative), hashes["after"], hashes["before"])
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
                  "install needs --prior-operation")
        print(install(args.prior_operation))
    else:
        base.need(args.operation is not None and args.prior_operation is None,
                  "verify/rollback needs --operation")
        if args.action == "verify":
            verify(args.operation)
            print("NORNIR_STOCK_LOADED_SEALS_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print("NORNIR_STOCK_LOADED_SEALS_ROLLED_BACK")


if __name__ == "__main__":
    main()
