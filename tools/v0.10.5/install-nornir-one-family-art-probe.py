#!/usr/bin/env python3
"""Install or roll back the chest-only map-art probe over checkpoint v4."""
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
    "nornir_checkpoint_v4_installer", HERE / "install-nornir-stock-saved-state-v4-test.py")
assert spec is not None and spec.loader is not None
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
base = v4.base

BUILD = ROOT / "build/nornir-one-family-art-probe"
REPORT = BUILD / "report.json"
BACKUPS = BUILD / "backups"
GAME = v4.GAME
KIND = "NORNIR_CHEST_ONLY_MAP_ART_PROBE_OPERATION"
WAD = "exec/wad/pc_le/r_ui.wad"
FAILED_LIVE_WAD_SHA256 = "aebebaee06c91e1f5663cf25624a44b3401d74645f837d4cc0b33e4e4ba52ef5"
BOOT = "exec/boot-options.json"
POOL = "exec/dc/pc_le/wad_r_ui.dcb"
MASTER = "exec/dc/pc_le/mapmaster.dcb"
PACK = "completionist_v105_nornir_chest"
FILES = {WAD, BOOT, POOL, MASTER,
         "exec/patch/pc_le/" + PACK + ".texpack",
         "exec/patch/pc_le/" + PACK + ".texpack.toc"}
UNTouched = {
    "exec/dc/pc_le/compassgraph.dcb":
        "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "exec/dc/pc_le/wad_r_perm.dcb":
        "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
}


def target(game: Path, relative: str) -> Path:
    base.need(relative in FILES, "probe path outside allowlist: " + relative)
    root = base.safe(game)
    path = base.safe(root / relative)
    base.need(path.is_relative_to(root), "probe path outside game root")
    return path


def candidate() -> dict:
    report = json.loads(base.safe(REPORT).read_text(encoding="utf-8"))
    base.need(report.get("kind") == "NORNIR_CHEST_ONLY_MAP_ART_PROBE" and
              report.get("status") == "OFFLINE_BUILT_NOT_INSTALLED" and
              set(report.get("files", {})) == FILES and
              report.get("proof", {}).get(WAD, {}).get("exact_inverse_to_raven") is True and
              report.get("proof", {}).get(POOL, {}).get("exact_inverse") is True and
              report.get("proof", {}).get(MASTER, {}).get("chest_resource_changes") == 22,
              "one-family probe report differs")
    current = v4.candidate()
    base.need(report["untouched_map_lua_sha256"] == current["files"][v4.MAP]["after"] and
              report["untouched_compass_class_sha256"] == UNTouched[
                  "exec/dc/pc_le/wad_r_perm.dcb"],
              "probe changed checkpoint or compass class contract")
    for relative, file in report["files"].items():
        base.need(base.sha(base.safe(BUILD / "candidate/game-root" / relative)) ==
                  file["sha256"], "probe candidate drift: " + relative)
    return report


def expected_before(report: dict) -> dict[str, str | None]:
    old = json.loads(v4.prior.prior.prior.REPORT.read_text(encoding="utf-8"))
    base.need(report["source_stock_master_sha256"] == old["files"][MASTER]["sha256"] and
              report["source_stock_pool_sha256"] == old["files"][POOL]["sha256"],
              "stock marker source differs")
    return {WAD: report["raven_wad_sha256"],
            BOOT: v4.prior.prior.prior.manifests()[1]["untouched_sha256"][BOOT],
            MASTER: report["source_stock_master_sha256"],
            POOL: report["source_stock_pool_sha256"],
            "exec/patch/pc_le/" + PACK + ".texpack": None,
            "exec/patch/pc_le/" + PACK + ".texpack.toc": None}


def operation(path: Path, game: Path) -> dict:
    path = base.safe(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    base.need(path.parent.is_relative_to(base.safe(BACKUPS)) and
              data.get("schema") == 1 and data.get("kind") == KIND and
              data.get("game_root") == str(game.absolute()) and
              set(data.get("files", {})) == FILES,
              "unknown one-family probe operation")
    return data


def verify(path: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = operation(path, game)
    base.need(data["status"] == "installed", "one-family probe not installed")
    report = candidate()
    before = expected_before(report)
    v4_op = v4.read_operation(Path(data["prior_operation"]), game)
    base.need(v4_op["status"] == "installed", "checkpoint v4 base not installed")
    v3_op = v4.prior.read_operation(Path(v4_op["prior_operation"]), game)
    v2_op = v4.prior.prior.read_operation(Path(v3_op["prior_operation"]), game)
    v1_op = v4.prior.prior.prior.read_operation(Path(v2_op["prior_operation"]), game)
    stock = base.read_operation(Path(v1_op["base_operation"]), game)
    base.need(all(op["status"] == "installed" for op in
                  (v3_op, v2_op, v1_op, stock)),
              "stock marker or checkpoint base not installed")
    for relative, file in stock["files"].items():
        expected = (report["files"][relative]["sha256"] if relative in FILES else
                    v4.candidate()["files"][relative]["after"]
                    if relative in v4.FILES else file["after"])
        base.need(base.sha(game / relative) == expected,
                  "stock Nornir or checkpoint file changed: " + relative)
    for relative, file in data["files"].items():
        base.need(file["before"] == before[relative] and
                  file["after"] == report["files"][relative]["sha256"] and
                  base.sha(target(game, relative)) == file["after"],
                  "probe installed file differs: " + relative)
        if file["before"] is not None:
            base.need(base.sha(path.parent / "before" / relative) == file["before"],
                      "probe backup differs: " + relative)
    for relative, expected in UNTouched.items():
        base.need(base.sha(game / relative) == expected,
                  "Raven art or compass file differs: " + relative)
    base.need(base.sha(game / v4.MAP) == report["untouched_map_lua_sha256"],
              "checkpoint map changed")
    base.need(base.sha(game / v4.RUNIC) == v4.candidate()["files"][v4.RUNIC]["after"],
              "checkpoint runic script changed")
    base.need(base.sha(game / "dxgi.dll") ==
              v4.candidate()["required_native_bridge_sha256"],
              "native bridge changed")


def rollback(path: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = operation(path, game)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "probe operation status unknown")
    for relative, file in reversed(list(data["files"].items())):
        stopped()
        destination = target(game, relative)
        current = base.sha(destination)
        if current == file["before"]:
            continue
        base.need(current == file["after"], "probe target changed: " + relative)
        if file["before"] is None:
            destination.unlink()
        else:
            base.atomic_copy(base.safe(path.parent / "before" / relative),
                             destination, file["before"], file["after"])
    data["status"] = "rolled_back"
    base.write_json(path, data)
    v4.verify(Path(data["prior_operation"]), game, stopped)


def install(prior_operation: Path, game: Path = GAME,
            stopped=base.game_stopped) -> Path:
    stopped()
    v4.verify(prior_operation, game, stopped)
    report = candidate()
    base.need(report["files"][WAD]["sha256"] != FAILED_LIVE_WAD_SHA256,
              "chest-only art WAD failed live: Raven drew chest art")
    before = expected_before(report)
    for relative, expected in before.items():
        base.need(base.sha(target(game, relative)) == expected,
                  "probe source differs: " + relative)
    directory = base.safe(BACKUPS / uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    files = {relative: {"before": before[relative],
                        "after": report["files"][relative]["sha256"]}
             for relative in sorted(FILES)}
    for relative, file in files.items():
        if file["before"] is None:
            continue
        destination = base.safe(directory / "before" / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target(game, relative), destination)
        base.need(base.sha(destination) == file["before"],
                  "probe backup differs: " + relative)
    journal = directory / "operation.json"
    data = {"schema": 1, "kind": KIND, "status": "prepared",
            "game_root": str(game.absolute()),
            "prior_operation": str(prior_operation.absolute()), "files": files}
    base.write_json(journal, data)
    try:
        data["status"] = "installing"
        base.write_json(journal, data)
        for relative, file in files.items():
            stopped()
            base.atomic_copy(base.safe(BUILD / "candidate/game-root" / relative),
                             target(game, relative), file["after"], file["before"])
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
            print("NORNIR_CHEST_ONLY_MAP_ART_PROBE_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print("NORNIR_CHEST_ONLY_MAP_ART_PROBE_ROLLED_BACK")


if __name__ == "__main__":
    main()
