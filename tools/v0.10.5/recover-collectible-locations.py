#!/usr/bin/env python3
"""Build/install the complete location layer with bounded native marker capacity."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

HERE = Path(__file__).resolve().parent
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

builder = load("recovery_locations", "build-collectible-locations.py")
io = load("recovery_io", "install-nornir-map-id-test.py")
ROOT, GAME = builder.ROOT, builder.GAME
BUILD = ROOT / "build/collectible-recovery"
UPSTREAM = "mods/completionist-map/native/collectible-base-dxgi.dll"
BRIDGE_MANIFEST = "mods/completionist-map/native/raven-native-bridge-manifest.json"
RESTORE = ("exec/wad/pc_le/r_ui.wad", "exec/dc/pc_le/wad_r_perm.dcb",
           "exec/dc/pc_le/compassgraph.dcb", "exec/boot-options.json")
FILES = (*builder.FILES, *RESTORE, UPSTREAM, "dxgi.dll", BRIDGE_MANIFEST)
PRESERVE = ("GoW.exe", "version.dll", builder.base.RUNIC_LUA, builder.base.STANDARD_LUA)
KIND = "COLLECTIBLE_LOCATIONS_CAPACITY_RECOVERY"
EXE_SHA = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"

def target(game, relative):
    io.need(relative in FILES, f"unapproved recovery target: {relative}")
    root = io.safe(game)
    result = io.safe(root / relative)
    io.need(result.is_relative_to(root), "recovery target escapes game root")
    return result

def pinned_source(name, digest, game):
    known = [game / name,
             ROOT / "build/collectible-locations/backups/18ec8719464d459da62eec716ea17564/before" / name,
             ROOT / "build/nornir-map-only-art-probe/backups/83d3624cdb2c446b9f20dd085d89d470/before" / name]
    if name == "dxgi.dll":
        known += list((game / "mods/completionist-map/native/backups").glob("dxgi-*.dll"))
    for path in known:
        if io.sha(path) == digest:
            return path
    for path in (ROOT / "build").rglob(Path(name).name):
        if io.sha(path) == digest:
            return path
    raise ValueError(f"verified source backup unavailable: {name}")

def build(game=GAME, output=BUILD):
    io.need(io.sha(game / "GoW.exe") == EXE_SHA, "unsupported game executable")
    baseline = output / "v4-source"
    for name, digest in {**builder.SOURCE, **builder.UNTOUCHED}.items():
        source = pinned_source(name, digest, game)
        dest = baseline / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source != dest:
            shutil.copyfile(source, dest)
    outputs, report = builder.build(baseline, native_marker_capacity=2048)
    shim = ROOT / "build/collectible-marker-capacity/Release/dxgi.dll"
    io.need(shim.is_file(), "build the collectible-marker-capacity native target first")
    outputs.update({name: (baseline / name).read_bytes() for name in RESTORE})
    outputs[UPSTREAM] = (baseline / "dxgi.dll").read_bytes()
    outputs["dxgi.dll"] = shim.read_bytes()
    manifest = {"schema": 1, "owner": KIND, "target_relative": "dxgi.dll",
                "installed_sha256": builder.sha(outputs["dxgi.dll"]),
                "upstream_relative": UPSTREAM, "upstream_sha256": builder.UNTOUCHED["dxgi.dll"],
                "supported_exe_sha256": EXE_SHA, "marker_slots": 2048,
                "entity_slots": 4096,
                "ui_physics_slots": 2048,
                "rollback": "Use recover-collectible-locations.py rollback with its operation journal."}
    outputs[BRIDGE_MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode()
    io.need(set(outputs) == set(FILES), "recovery file list differs")
    report.update({"schema": 1, "kind": KIND, "status": "BUILT",
                   "preserved": {name: io.sha(game / name) for name in PRESERVE},
                   "files": {name: {"before": io.sha(target(game, name)), "after": builder.sha(raw)}
                             for name, raw in outputs.items()},
                   "capacity_shim": manifest,
                   "recovered_resources": list(RESTORE)})
    for name, raw in outputs.items():
        dest = output / "candidate/game-root" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    io.write_json(output / "report.json", report)
    # Reuse the focused location/Lua tests against the exact composed map files.
    for name in builder.FILES:
        dest = builder.BUILD / "candidate/game-root" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(outputs[name])
    io.write_json(builder.BUILD / "report.json", report)
    print(f"RECOVERY_BUILT locations={report['location_count']} marker_entries={report['native_marker_entries']} capacity=2048")

def read_report(output):
    report = json.loads(io.safe(output / "report.json").read_text())
    io.need(report.get("kind") == KIND and report.get("schema") == 1 and
            set(report.get("files", {})) == set(FILES) and
            report.get("location_count") == sum(builder.COUNTS.values()) and
            report.get("native_marker_entries", 2049) <= 2048 and
            report.get("native_marker_capacity") == 2048 and
            report.get("capacity_shim", {}).get("marker_slots") == 2048 and
            report.get("capacity_shim", {}).get("entity_slots") == 4096 and
            report.get("capacity_shim", {}).get("ui_physics_slots") == 2048 and
            report.get("capacity_shim", {}).get("upstream_sha256") == builder.UNTOUCHED["dxgi.dll"],
            "invalid recovery candidate")
    for name, hashes in report["files"].items():
        io.need(io.sha(output / "candidate/game-root" / name) == hashes["after"], f"candidate drift: {name}")
    return report

def read_operation(journal, game=GAME, output=BUILD):
    journal = io.safe(journal)
    data = json.loads(journal.read_text())
    io.need(journal.parent.parent == io.safe(output / "backups") and data.get("kind") == KIND and
            data.get("game_root") == str(io.safe(game)) and set(data.get("files", {})) == set(FILES),
            "unknown recovery operation")
    for name, hashes in data["files"].items():
        io.need(io.sha(journal.parent / "before" / name) == hashes["before"], f"backup drift: {name}")
    return data

def verify(journal, game=GAME, output=BUILD, stopped=io.game_stopped):
    stopped()
    data = read_operation(journal, game, output)
    io.need(data["status"] == "installed", "recovery not installed")
    for name, hashes in data["files"].items():
        io.need(io.sha(target(game, name)) == hashes["after"], f"installed drift: {name}")
    for name, digest in data["preserved"].items():
        io.need(io.sha(game / name) == digest, f"preserved file drift: {name}")

def rollback(journal, game=GAME, output=BUILD, stopped=io.game_stopped):
    stopped()
    data = read_operation(journal, game, output)
    for name, hashes in data["files"].items():
        io.need(io.sha(target(game, name)) in {hashes["before"], hashes["after"]}, f"unrelated edit: {name}")
    for name, hashes in reversed(list(data["files"].items())):
        dest = target(game, name)
        if io.sha(dest) == hashes["before"]:
            continue
        if hashes["before"] is None:
            io.need(io.sha(dest) == hashes["after"], f"removal drift: {name}")
            dest.unlink()
        else:
            io.atomic_copy(journal.parent / "before" / name, dest, hashes["before"], hashes["after"])
    data["status"] = "rolled_back"
    io.write_json(journal, data)

def install(game=GAME, output=BUILD, stopped=io.game_stopped):
    stopped()
    report = read_report(output)
    for name, hashes in report["files"].items():
        io.need(io.sha(target(game, name)) == hashes["before"], f"source drift: {name}")
    for name, digest in report["preserved"].items():
        io.need(io.sha(game / name) == digest, f"preserved file drift: {name}")
    folder = io.safe(output / "backups" / uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    for name, hashes in report["files"].items():
        if hashes["before"] is not None:
            dest = folder / "before" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target(game, name), dest)
            io.need(io.sha(dest) == hashes["before"], f"backup differs: {name}")
    journal = folder / "operation.json"
    data = {"kind": KIND, "schema": 1, "game_root": str(io.safe(game)),
            "status": "prepared", "files": report["files"], "preserved": report["preserved"]}
    io.write_json(journal, data)
    try:
        stopped()
        data["status"] = "installing"
        io.write_json(journal, data)
        for name in FILES:
            hashes = data["files"][name]
            io.atomic_copy(output / "candidate/game-root" / name, target(game, name),
                           hashes["after"], hashes["before"])
        data["status"] = "installed"
        io.write_json(journal, data)
        verify(journal, game, output, stopped)
    except Exception:
        rollback(journal, game, output, stopped)
        raise
    return journal

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "install", "verify", "rollback"))
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.action == "install":
        print(install())
    else:
        io.need(args.operation is not None, "operation journal required")
        globals()[args.action](args.operation)
        print("RECOVERY_" + args.action.upper() + "_OK")
if __name__ == "__main__":
    main()
