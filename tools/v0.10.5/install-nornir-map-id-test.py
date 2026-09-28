#!/usr/bin/env python3
"""Install, verify, or roll back the isolated Nornir map ID test."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
GAME = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar")
BUILD = ROOT / "build/nornir-id-test"
REPORT = BUILD / "report.json"
BACKUPS = BUILD / "backups"
EXPECTED_KIND = "NORNIR_ID_ISOLATED_MAP_PLACEMENT_TEST"
RESULT_LABEL = "NORNIR_ID_TEST"
WAD = "exec/wad/pc_le/r_ui.wad"
GRAPH = "exec/dc/pc_le/compassgraph.dcb"
STOCK_UNTOUCHED = {
    WAD: "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    GRAPH: "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/boot-options.json": "8bbac2bb2a522dfacf69c676e48665686f722289a44127518ae4e8ca299a0e92",
}
STOCK_COMPASS = {
    "nornir_chest": "SIDE",
    "nornir_seal": "Valkyrie",
    "nornir_bell": "FightLocation",
    "nornir_mechanism": "AreaEntrance",
}
RUNIC = "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua"
STANDARD = "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua"
ALLOWED = {
    "exec/dc/pc_le/mapmaster.dcb",
    "exec/dc/pc_le/mapcoords.dcb",
    "exec/dc/pc_le/wad_r_ui.dcb",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
    RUNIC,
    STANDARD,
}


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def safe(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            data = part.lstat()
        except FileNotFoundError:
            continue
        need(not stat.S_ISLNK(data.st_mode) and
             not (getattr(data, "st_file_attributes", 0) & 0x400),
             f"linked or reparse path: {part}")
        need(not stat.S_ISREG(data.st_mode) or data.st_nlink == 1,
             f"hardlinked file: {part}")
    return path


def target(root: Path, relative: str) -> Path:
    need(relative in ALLOWED, f"unapproved target: {relative}")
    base = safe(root)
    path = safe(base / relative)
    need(path.is_relative_to(base), f"target outside game root: {relative}")
    return path


def sha(path: Path) -> str | None:
    path = safe(path)
    if not path.exists():
        return None
    need(path.is_file(), f"not file: {path}")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_copy(source: Path, destination: Path, expected_source: str,
                expected_before: str | None) -> None:
    need(sha(source) == expected_source, f"source drift: {source}")
    need(sha(destination) == expected_before, f"target drift: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe(destination.parent)
    temporary = safe(destination.parent / (".nornir-" + uuid.uuid4().hex + ".tmp"))
    try:
        with source.open("rb") as src, temporary.open("xb") as out:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        need(sha(temporary) == expected_source, "temporary copy differs")
        need(sha(destination) == expected_before, "target changed during copy")
        os.replace(temporary, destination)
        need(sha(destination) == expected_source, "installed copy differs")
    finally:
        if temporary.exists():
            safe(temporary).unlink()


def write_json(path: Path, value: dict) -> None:
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = safe(path.parent / (".operation-" + uuid.uuid4().hex + ".tmp"))
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(value, out, indent=2, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            safe(temporary).unlink()


def game_stopped() -> None:
    need(os.name == "nt", "real install needs Windows process check")
    result = subprocess.run(["tasklist.exe", "/FO", "CSV", "/NH"],
                            text=True, capture_output=True, check=True)
    rows = list(csv.reader(io.StringIO(result.stdout)))
    need(not any(row and row[0].casefold() in {"gow.exe", "godofwar.exe"}
                 for row in rows), "God of War is running")


def inputs(build: Path, game: Path) -> dict:
    manifest = json.loads(safe(build / "report.json").read_text(encoding="utf-8"))
    need(manifest.get("kind") == EXPECTED_KIND and
         manifest.get("new_marker_count") == 88 and
         manifest.get("child_marker_count") == 66,
         "unexpected candidate report")
    need(set(manifest.get("files", {})) == ALLOWED, "candidate file list differs")
    need(set(manifest.get("source_sha256", {})) == ALLOWED - {RUNIC, STANDARD},
         "source file list differs")
    need(manifest["proof"]["exec/dc/pc_le/mapmaster.dcb"]["exact_inverse"] and
         manifest["proof"]["exec/dc/pc_le/mapcoords.dcb"]["exact_inverse"] and
         manifest["proof"]["mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"]["raven_lua_exact_prefix"],
         "Raven preservation proof absent")
    if EXPECTED_KIND == "NORNIR_STOCK_FAMILY_MARKERS_TEST":
        pool = manifest["proof"]["exec/dc/pc_le/wad_r_ui.dcb"]
        need(pool.get("new_rows") == 88 and
             pool.get("raven_rows_unchanged") == 45 and
             pool.get("exact_inverse") is True and
             manifest.get("renderer") == "distinct_stock_family_icons" and
             manifest.get("compass") == STOCK_COMPASS and
             len(set(manifest.get("stock_art", {}).values())) == 4 and
             manifest.get("untouched_sha256") == STOCK_UNTOUCHED,
             "stock family preservation proof absent")
    for relative, data in manifest["files"].items():
        need(sha(safe(build / "candidate/game-root" / relative)) == data["sha256"],
             f"candidate drift: {relative}")
    for relative, expected in manifest["source_sha256"].items():
        need(sha(target(game, relative)) == expected,
             f"installed Raven base differs: {relative}")
    need(sha(target(game, RUNIC)) is None, "runic Lua override already exists")
    need(sha(target(game, STANDARD)) is None, "standard Lua override already exists")
    need(sha(game / WAD) == manifest["untouched_raven_wad_sha256"],
         "Raven art WAD changed")
    need(sha(game / GRAPH) == manifest["untouched_compassgraph_sha256"],
         "Raven compass graph changed")
    for relative, expected in manifest.get("untouched_sha256", {}).items():
        need(relative in {WAD, GRAPH, "exec/dc/pc_le/wad_r_perm.dcb",
                          "exec/boot-options.json"} and
             sha(game / relative) == expected,
             f"untouched Raven resource differs: {relative}")
    return manifest


def install(build: Path = BUILD, game: Path = GAME,
            stopped=game_stopped) -> Path:
    stopped()
    manifest = inputs(build, game)
    backup = safe(build / "backups" / uuid.uuid4().hex)
    backup.mkdir(parents=True, exist_ok=False)
    operation = {
        "schema": 1,
        "kind": manifest["kind"],
        "status": "prepared",
        "game_root": str(game.absolute()),
        "files": {relative: {"before": manifest["source_sha256"].get(relative),
                             "after": manifest["files"][relative]["sha256"]}
                  for relative in sorted(ALLOWED)},
    }
    for relative in sorted(ALLOWED - {RUNIC, STANDARD}):
        source = target(game, relative)
        before = safe(backup / "before" / relative)
        before.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, before)
        need(sha(before) == operation["files"][relative]["before"],
             f"backup differs: {relative}")
    journal = backup / "operation.json"
    write_json(journal, operation)
    try:
        operation["status"] = "installing"
        write_json(journal, operation)
        for relative in sorted(ALLOWED):
            stopped()
            file = operation["files"][relative]
            atomic_copy(safe(build / "candidate/game-root" / relative),
                        target(game, relative), file["after"], file["before"])
        operation["status"] = "installed"
        write_json(journal, operation)
        verify(journal, game, stopped)
    except Exception:
        rollback(journal, game, stopped)
        raise
    return journal


def read_operation(journal: Path, game: Path) -> dict:
    journal = safe(journal)
    data = json.loads(journal.read_text(encoding="utf-8"))
    need(data.get("schema") == 1 and
        data.get("kind") == EXPECTED_KIND and
         data.get("game_root") == str(game.absolute()) and
         set(data.get("files", {})) == ALLOWED,
         "unknown operation journal")
    need(journal.parent.is_relative_to(safe(BACKUPS)) or
         journal.parent.is_relative_to(safe(BUILD / "backups")),
         "operation outside backup root")
    return data


def verify(journal: Path, game: Path = GAME, stopped=game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    need(data["status"] == "installed", "operation not installed")
    for relative, file in data["files"].items():
        need(sha(target(game, relative)) == file["after"],
             f"installed file differs: {relative}")
        if file["before"] is not None:
            need(sha(journal.parent / "before" / relative) == file["before"],
                 f"backup differs: {relative}")
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    need(sha(game / WAD) == report["untouched_raven_wad_sha256"] and
         sha(game / GRAPH) == report["untouched_compassgraph_sha256"],
         "untouched Raven resource differs")
    for relative, expected in report.get("untouched_sha256", {}).items():
        need(relative in {WAD, GRAPH, "exec/dc/pc_le/wad_r_perm.dcb",
                          "exec/boot-options.json"} and
             sha(game / relative) == expected,
             f"untouched Raven resource differs: {relative}")


def rollback(journal: Path, game: Path = GAME, stopped=game_stopped) -> None:
    stopped()
    data = read_operation(journal, game)
    need(data["status"] in {"prepared", "installing", "installed", "rolled_back"},
         "unknown operation state")
    for relative, file in reversed(list(data["files"].items())):
        stopped()
        path = target(game, relative)
        current = sha(path)
        if current == file["before"]:
            continue
        need(current == file["after"], f"target changed after install: {relative}")
        if file["before"] is None:
            path.unlink()
        else:
            atomic_copy(safe(journal.parent / "before" / relative), path,
                        file["before"], file["after"])
    data["status"] = "rolled_back"
    write_json(journal, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "rollback"))
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        need(args.operation is None, "install makes a new operation")
        print(install(BUILD))
    else:
        need(args.operation is not None, "--operation required")
        if args.action == "verify":
            verify(args.operation)
            print(RESULT_LABEL + "_INSTALLED_VERIFIED")
        else:
            rollback(args.operation)
            print(RESULT_LABEL + "_ROLLED_BACK")


if __name__ == "__main__":
    main()
