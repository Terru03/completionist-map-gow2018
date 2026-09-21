#!/usr/bin/env python3
"""Refresh generated Raven Lua files inside the existing five-file candidate."""
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


GENERATED = {
    build.MAP_LUA: {
        "marker": b"-- BEGIN COMPLETIONIST V0.10.5 ALL RAVENS",
        "template": HERE / "all-ravens-map-runtime.lua",
        "token": "-- @@RAVEN_CATALOGUE_ROWS@@",
        "state_rows": False,
        "label": "map",
    },
    build.EVENT_LUA: {
        "marker": b"-- BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS",
        "template": HERE / "all-ravens-gameplay-events.lua",
        "token": "-- @@RAVEN_STATE_ROWS@@",
        "state_rows": True,
        "label": "events",
    },
}


def rendered_candidate(relative: str, catalogue: dict) -> tuple[bytes, bytes]:
    spec = GENERATED[relative]
    path = build.OUTPUT / relative
    current = path.read_bytes()
    marker = spec["marker"]
    if current.count(marker) != 1:
        raise ValueError(f"existing {spec['label']} candidate hook marker differs")
    marker_at = current.index(marker)
    if marker_at == 0 or current[marker_at - 1 : marker_at] != b"\n":
        raise ValueError(f"existing {spec['label']} candidate hook boundary differs")
    base = current[: marker_at - 1]
    if sha(base) != build.SOURCE_HASHES[relative]:
        raise ValueError(
            f"existing {spec['label']} candidate base is not runtime-proven source"
        )
    hook = build.render_lua(
        catalogue,
        spec["template"],
        spec["token"],
        spec["state_rows"],
    )
    return current, base + b"\n" + hook


def prepare(check_only: bool, refresh_proof: bool = False) -> None:
    proof = json.loads(build.REPORT.read_text(encoding="utf-8"))
    expected_files = set(proof["files"])
    actual_files = {
        path.relative_to(build.OUTPUT).as_posix()
        for path in build.OUTPUT.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("existing candidate file set differs")

    generated_paths = set(GENERATED)
    for relative in expected_files - generated_paths:
        raw = (build.OUTPUT / relative).read_bytes()
        if sha(raw) != proof["files"][relative]["sha256"]:
            raise ValueError(f"existing accepted candidate differs: {relative}")

    catalogue = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))
    rendered = {}
    for relative in GENERATED:
        current, refreshed = rendered_candidate(relative, catalogue)
        expected = proof["files"][relative]
        expected_matches_current = (
            sha(current) == expected["sha256"] and len(current) == expected["bytes"]
        )
        if refresh_proof:
            if not expected_matches_current and current != refreshed:
                raise ValueError(
                    f"existing generated candidate matches neither pinned proof "
                    f"nor current rendered runtime: {relative}"
                )
            if current != refreshed:
                build.stage.write_bytes_atomic(
                    build.OUTPUT,
                    build.OUTPUT / relative,
                    refreshed,
                    f"native snapshot delivery {GENERATED[relative]['label']} candidate",
                )
            proof["files"][relative] = {
                "sha256": sha(refreshed),
                "bytes": len(refreshed),
            }
        rendered[relative] = refreshed

    if refresh_proof:
        build.stage.write_bytes_atomic(
            build.REPORT.parent,
            build.REPORT,
            build.canonical_json(proof).encode("utf-8"),
            "refreshed native snapshot delivery proof",
        )

    for relative, refreshed in rendered.items():
        expected = proof["files"][relative]
        if sha(refreshed) != expected["sha256"] or len(refreshed) != expected["bytes"]:
            raise ValueError(f"rendered delivery candidate differs from pinned proof: {relative}")
        path = build.OUTPUT / relative
        current = path.read_bytes()
        if check_only and current != refreshed:
            raise ValueError(f"generated candidate needs refresh: {relative}")
        if not check_only and not refresh_proof and current != refreshed:
            build.stage.write_bytes_atomic(
                build.OUTPUT,
                path,
                refreshed,
                f"native snapshot delivery {GENERATED[relative]['label']} candidate",
            )
        if path.read_bytes() != refreshed:
            raise ValueError(f"generated candidate verification failed: {relative}")

    print(
        "ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_PREPARED files=5 "
        f"map_sha256={sha(rendered[build.MAP_LUA])} "
        f"events_sha256={sha(rendered[build.EVENT_LUA])}"
    )
    print("ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_ROOT=" + str(build.OUTPUT.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--refresh-proof", action="store_true")
    args = parser.parse_args()
    prepare(args.check, args.refresh_proof)


if __name__ == "__main__":
    main()
