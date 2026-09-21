#!/usr/bin/env python3
"""Refresh the generated map Lua inside the existing five-file Raven candidate."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD_PATH = HERE / "build-all-ravens-release-candidate.py"
SPEC = importlib.util.spec_from_file_location("all_ravens_delivery_build", BUILD_PATH)
build = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare(check_only: bool) -> None:
    proof = json.loads(build.REPORT.read_text(encoding="utf-8"))
    expected_files = set(proof["files"])
    actual_files = {
        path.relative_to(build.OUTPUT).as_posix()
        for path in build.OUTPUT.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("existing candidate file set differs")

    for relative in expected_files - {build.MAP_LUA}:
        raw = (build.OUTPUT / relative).read_bytes()
        if sha(raw) != proof["files"][relative]["sha256"]:
            raise ValueError(f"existing accepted candidate differs: {relative}")

    map_path = build.OUTPUT / build.MAP_LUA
    current = map_path.read_bytes()
    marker = b"-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS"
    if current.count(marker) != 1:
        raise ValueError("existing map candidate hook marker differs")
    marker_at = current.index(marker)
    if marker_at == 0 or current[marker_at - 1 : marker_at] != b"\n":
        raise ValueError("existing map candidate hook boundary differs")
    base = current[: marker_at - 1]
    if sha(base) != build.SOURCE_HASHES[build.MAP_LUA]:
        raise ValueError("existing map candidate base is not runtime-proven source")

    catalogue = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))
    hook = build.render_lua(
        catalogue,
        HERE / "all-ravens-map-runtime.lua",
        "-- @@RAVEN_CATALOGUE_ROWS@@",
    )
    refreshed = base + b"\n" + hook
    expected = proof["files"][build.MAP_LUA]
    if sha(refreshed) != expected["sha256"] or len(refreshed) != expected["bytes"]:
        raise ValueError("rendered delivery candidate differs from pinned proof")
    if check_only and current != refreshed:
        raise ValueError("generated map candidate needs refresh")
    if not check_only and current != refreshed:
        build.stage.write_bytes_atomic(
            build.OUTPUT,
            map_path,
            refreshed,
            "native snapshot delivery map candidate",
        )
    if map_path.read_bytes() != refreshed:
        raise ValueError("generated map candidate verification failed")
    print("ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_PREPARED files=5 map_sha256=" + sha(refreshed))
    print("ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_ROOT=" + str(build.OUTPUT.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    prepare(args.check)


if __name__ == "__main__":
    main()
