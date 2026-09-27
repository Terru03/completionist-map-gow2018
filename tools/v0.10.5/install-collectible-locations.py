#!/usr/bin/env python3
"""Install, verify or roll back the four-file collectible location overlay."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("location_builder_install", "build-collectible-locations.py")
base = load("location_install_io", "install-nornir-map-id-test.py")
BUILD, GAME = builder.BUILD, builder.GAME
FILES = set(builder.FILES)
KIND = "COLLECTIBLE_LOCATIONS_OPERATION"


def manifest(build: Path) -> dict:
    data = json.loads(base.safe(build / "report.json").read_text(encoding="utf-8"))
    base.need(data.get("kind") == builder.KIND and data.get("schema") == 1 and
              data.get("mode") == "all_known_locations" and
              data.get("family_counts") == builder.COUNTS and
              data.get("location_count") == sum(builder.COUNTS.values()) and
              data.get("reused_native_markers") == builder.REUSED_NATIVE_MARKERS and
              data.get("new_marker_count") == sum(builder.COUNTS.values()) - builder.REUSED_NATIVE_MARKERS and
              set(data.get("files", {})) == FILES and
              data.get("source_sha256") == builder.SOURCE and
              data.get("untouched_sha256") == builder.UNTOUCHED,
              "location candidate contract differs")
    for name, hashes in data["files"].items():
        base.need(hashes["before"] == builder.SOURCE[name] and
                  hashes["after"] != hashes["before"] and
                  base.sha(build / "candidate/game-root" / name) == hashes["after"] and
                  data["proof"][name].get("exact_inverse") is True,
                  f"candidate changed or lacks inverse proof: {name}")
    return data


def check_untouched(game: Path, expected: dict) -> None:
    for name, digest in expected.items():
        base.need(base.sha(game / name) == digest, f"preserved resource differs: {name}")


def read_operation(journal: Path, game: Path, build: Path) -> dict:
    journal = base.safe(journal)
    data = json.loads(journal.read_text(encoding="utf-8"))
    base.need(journal.parent.parent == base.safe(build / "backups") and
              data.get("schema") == 1 and data.get("kind") == KIND and
              data.get("game_root") == str(base.safe(game)) and
              set(data.get("files", {})) == FILES and
              data.get("untouched_sha256") == builder.UNTOUCHED,
              "unknown location operation")
    for name, hashes in data["files"].items():
        base.need(hashes["before"] == builder.SOURCE[name] and
                  base.sha(journal.parent / "before" / name) == hashes["before"],
                  f"location backup differs: {name}")
    return data


def verify(journal: Path, game: Path = GAME, build: Path = BUILD,
           stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game, build)
    base.need(data["status"] == "installed", "locations are not installed")
    for name, hashes in data["files"].items():
        base.need(base.sha(base.target(game, name)) == hashes["after"], f"installed file differs: {name}")
    check_untouched(game, data["untouched_sha256"])


def rollback(journal: Path, game: Path = GAME, build: Path = BUILD,
             stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(journal, game, build)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "unknown location operation status")
    # Preflight every file before restoring any: never overwrite unrelated changes.
    for name, hashes in data["files"].items():
        base.need(base.sha(base.target(game, name)) in {hashes["before"], hashes["after"]},
                  f"file changed after location install: {name}")
    for name, hashes in data["files"].items():
        target = base.target(game, name)
        if base.sha(target) != hashes["before"]:
            base.atomic_copy(journal.parent / "before" / name, target, hashes["before"], hashes["after"])
    data["status"] = "rolled_back"
    base.write_json(journal, data)


def install(game: Path = GAME, build: Path = BUILD, stopped=base.game_stopped) -> Path:
    stopped()
    data = manifest(build)
    check_untouched(game, data["untouched_sha256"])
    for name, hashes in data["files"].items():
        base.need(base.sha(base.target(game, name)) == hashes["before"], f"installed base differs: {name}")
    folder = base.safe(build / "backups" / uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    for name, hashes in data["files"].items():
        target = folder / "before" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base.target(game, name), target)
        base.need(base.sha(target) == hashes["before"], f"backup differs: {name}")
    journal = folder / "operation.json"
    operation = {"schema": 1, "kind": KIND, "status": "prepared",
                 "game_root": str(base.safe(game)), "files": data["files"],
                 "untouched_sha256": data["untouched_sha256"]}
    base.write_json(journal, operation)
    try:
        stopped()
        operation["status"] = "installing"
        base.write_json(journal, operation)
        for name, hashes in data["files"].items():
            base.atomic_copy(build / "candidate/game-root" / name, base.target(game, name),
                             hashes["after"], hashes["before"])
        operation["status"] = "installed"
        base.write_json(journal, operation)
        verify(journal, game, build, stopped)
    except Exception:
        rollback(journal, game, build, stopped)
        raise
    return journal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "rollback"))
    parser.add_argument("--operation", type=Path)
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--build", type=Path, default=BUILD)
    args = parser.parse_args()
    if args.action == "install":
        base.need(args.operation is None, "install does not accept --operation")
        print(install(args.game, args.build))
    else:
        base.need(args.operation is not None, "verify/rollback requires --operation")
        globals()[args.action](args.operation, args.game, args.build)
        print("COLLECTIBLE_LOCATIONS_" + args.action.upper() + "_OK")


if __name__ == "__main__":
    main()
