#!/usr/bin/env python3
"""Freeze exact Raven release bytes as the Legendary one-marker source."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE_COMMIT = "e522268e45bdd0d8f966bdb7ddf336eb344cad7d"
BASE = REPO / "archive/legendary-live-test/raven-release-base"
GAME_ROOT = BASE / "game-root"
CANDIDATE = REPO / "build/v0.10.5-all-ravens-release-candidate/offline/candidate/game-root"
BUILDER_PATH = HERE / "build-all-ravens-release-candidate.py"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(relative: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{REFERENCE_COMMIT}:{relative}"], cwd=REPO)


def write_exact(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"archived Raven release byte drift: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main() -> None:
    spec = importlib.util.spec_from_file_location("legendary_raven_reference_build", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Raven builder absent")
    builder = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = builder
    spec.loader.exec_module(builder)
    proof = json.loads(git_blob("archive/all-ravens/all-ravens-release-candidate-offline.json"))
    catalogue = json.loads(builder.CATALOGUE.read_text(encoding="utf-8"))
    builder.validate_catalogue(catalogue)
    template = git_blob("tools/v0.10.5/all-ravens-map-runtime.lua")
    with tempfile.TemporaryDirectory(dir=REPO / "build") as scratch:
        template_path = Path(scratch) / "raven-map-runtime.lua"
        template_path.write_bytes(template)
        hook = builder.render_lua(catalogue, template_path, "-- @@RAVEN_CATALOGUE_ROWS@@")

    map_path = CANDIDATE / builder.MAP_LUA
    current = map_path.read_bytes()
    marker = b"-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS"
    if current.count(marker) != 1:
        raise ValueError("current candidate has no unique Raven hook boundary")
    boundary = current.index(marker)
    if current[boundary - 1:boundary] != b"\n":
        raise ValueError("Raven hook boundary changed")
    stock = current[:boundary - 1]
    if sha(stock) != builder.SOURCE_HASHES[builder.MAP_LUA]:
        raise ValueError("stock mapmenu source differs from Raven release pin")
    release_map = stock + b"\n" + hook

    files = {}
    for relative, expected in proof["files"].items():
        raw = release_map if relative == builder.MAP_LUA else (CANDIDATE / relative).read_bytes()
        if sha(raw) != expected["sha256"] or len(raw) != expected["bytes"]:
            raise ValueError(f"Raven reference proof differs: {relative}")
        write_exact(GAME_ROOT / relative, raw)
        files[relative] = {"sha256": sha(raw), "bytes": len(raw)}
    write_exact(BASE / "release-proof.json", git_blob(
        "archive/all-ravens/all-ravens-release-candidate-offline.json"))
    manifest = {
        "schema": 1,
        "purpose": "exact Raven release input for one Legendary diagnostic marker",
        "reference_commit": REFERENCE_COMMIT,
        "release_proof_sha256": sha((BASE / "release-proof.json").read_bytes()),
        "files": files,
        "game_files_written": False,
    }
    write_exact(BASE / "manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    print("RAVEN_REFERENCE_BASE_ARCHIVED_AND_VERIFIED")


if __name__ == "__main__":
    main()
