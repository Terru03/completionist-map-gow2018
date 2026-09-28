#!/usr/bin/env python3
"""Install or roll back a chest texture-pack-only diagnostic over checkpoint v4."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import uuid


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v4 = load("nornir_pack_v4_installer", "install-nornir-stock-saved-state-v4-test.py")
builder = load("nornir_pack_builder", "build-nornir-pack-only-probe.py")
base = v4.base
GAME = v4.GAME
BUILD = ROOT / "build/nornir-pack-only-probe"
BACKUPS = BUILD / "backups"
BOOT = builder.BOOT
FILES = builder.FILES
KIND = "NORNIR_CHEST_PACK_ONLY_PROBE_OPERATION"
RAVEN_PACKS = {
    "exec/patch/pc_le/completionist_v104_raven_map.texpack":
        "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7",
    "exec/patch/pc_le/completionist_v104_raven_map.texpack.toc":
        "67cceea0d91298881f4426bf0ce5e8883da45a82905921313004df618d959053",
}


def target(game: Path, relative: str) -> Path:
    base.need(relative in FILES, "path outside pack probe allowlist: " + relative)
    root = base.safe(game)
    path = base.safe(root / relative)
    base.need(path.is_relative_to(root), "pack probe path outside game root")
    return path


def candidate() -> dict:
    report = json.loads(base.safe(builder.REPORT).read_text(encoding="utf-8"))
    outputs, expected = builder.build()
    base.need(report == expected and set(report["files"]) == set(FILES) and
              report["files"][BOOT]["before"] ==
              v4.prior.prior.prior.manifests()[1]["untouched_sha256"][BOOT],
              "pack-only report differs")
    for name, raw in outputs.items():
        base.need(base.sha(BUILD / "candidate/game-root" / name) ==
                  report["files"][name]["after"] == builder.sha(raw),
                  "pack-only candidate differs: " + name)
    return report


def read_operation(path: Path, game: Path) -> dict:
    path = base.safe(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    base.need(path.parent.is_relative_to(base.safe(BACKUPS)) and
              data.get("schema") == 1 and data.get("kind") == KIND and
              data.get("game_root") == str(game.absolute()) and
              set(data.get("files", {})) == set(FILES),
              "unknown pack-only operation")
    return data


def verify(path: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(path, game)
    base.need(data["status"] == "installed", "pack-only probe not installed")
    report = candidate()
    v4_op = v4.read_operation(Path(data["prior_operation"]), game)
    v3_op = v4.prior.read_operation(Path(v4_op["prior_operation"]), game)
    v2_op = v4.prior.prior.read_operation(Path(v3_op["prior_operation"]), game)
    v1_op = v4.prior.prior.prior.read_operation(Path(v2_op["prior_operation"]), game)
    stock = base.read_operation(Path(v1_op["base_operation"]), game)
    base.need(all(op["status"] == "installed" for op in
                  (v4_op, v3_op, v2_op, v1_op, stock)),
              "stock marker or checkpoint base not installed")
    current_v4 = v4.candidate()
    for name, file in stock["files"].items():
        expected = (current_v4["files"][name]["after"] if name in v4.FILES
                    else file["after"])
        base.need(base.sha(game / name) == expected,
                  "Nornir marker or checkpoint file changed: " + name)
    untouched = v4.prior.prior.prior.manifests()[1]["untouched_sha256"]
    for name, expected in untouched.items():
        if name != BOOT:
            base.need(base.sha(game / name) == expected,
                      "Raven resource changed: " + name)
    for name, expected in RAVEN_PACKS.items():
        base.need(base.sha(game / name) == expected,
                  "Raven texture pack changed: " + name)
    base.need(base.sha(game / "dxgi.dll") ==
              current_v4["required_native_bridge_sha256"],
              "native bridge changed")
    for name, file in data["files"].items():
        base.need(file == report["files"][name] and
                  base.sha(target(game, name)) == file["after"],
                  "pack-only installed file differs: " + name)
        if file["before"] is not None:
            base.need(base.sha(path.parent / "before" / name) == file["before"],
                      "pack-only backup differs: " + name)


def rollback(path: Path, game: Path = GAME, stopped=base.game_stopped) -> None:
    stopped()
    data = read_operation(path, game)
    base.need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
              "unknown pack-only operation status")
    for name, file in reversed(list(data["files"].items())):
        stopped()
        destination = target(game, name)
        current = base.sha(destination)
        if current == file["before"]:
            continue
        base.need(current == file["after"], "pack-only target changed: " + name)
        if file["before"] is None:
            destination.unlink()
        else:
            base.atomic_copy(path.parent / "before" / name,
                             destination, file["before"], file["after"])
    data["status"] = "rolled_back"
    base.write_json(path, data)
    v4.verify(Path(data["prior_operation"]), game, stopped)


def install(prior_operation: Path, game: Path = GAME,
            stopped=base.game_stopped) -> Path:
    stopped()
    v4.verify(prior_operation, game, stopped)
    report = candidate()
    for name in FILES:
        base.need(base.sha(target(game, name)) == report["files"][name]["before"],
                  "pack-only source differs: " + name)
    for name, expected in RAVEN_PACKS.items():
        base.need(base.sha(game / name) == expected,
                  "Raven texture pack differs: " + name)
    directory = base.safe(BACKUPS / uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    backup = directory / "before" / BOOT
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target(game, BOOT), backup)
    base.need(base.sha(backup) == report["files"][BOOT]["before"],
              "pack-only boot backup differs")
    journal = directory / "operation.json"
    data = {"schema": 1, "kind": KIND, "status": "prepared",
            "game_root": str(game.absolute()),
            "prior_operation": str(prior_operation.absolute()),
            "files": report["files"]}
    base.write_json(journal, data)
    try:
        data["status"] = "installing"
        base.write_json(journal, data)
        for name in FILES:
            stopped()
            file = report["files"][name]
            base.atomic_copy(BUILD / "candidate/game-root" / name,
                             target(game, name), file["after"], file["before"])
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
            print("NORNIR_CHEST_PACK_ONLY_PROBE_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print("NORNIR_CHEST_PACK_ONLY_PROBE_ROLLED_BACK")


if __name__ == "__main__":
    main()
