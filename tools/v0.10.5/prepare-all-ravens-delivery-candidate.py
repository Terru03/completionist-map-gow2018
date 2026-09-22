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


def _restore_bytes(originals: dict[Path, bytes | None]) -> None:
    errors: list[str] = []
    for path, raw in originals.items():
        temp = path.with_name(path.name + ".completionist-rollback.tmp")
        try:
            if raw is None:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(raw)
            temp.replace(path)
        except Exception as exc:  # pragma: no cover - catastrophic filesystem path
            errors.append(f"{path}: {exc}")
        finally:
            temp.unlink(missing_ok=True)
    if errors:
        raise RuntimeError("candidate rollback failed: " + "; ".join(errors))


def _apply_writes_atomically(
    writes: list[tuple[Path, Path, bytes, str]],
) -> None:
    originals: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None
        for _, path, _, _ in writes
    }
    try:
        for root, path, raw, label in writes:
            build.stage.write_bytes_atomic(root, path, raw, label)
    except Exception as exc:
        try:
            _restore_bytes(originals)
        except Exception as rollback_exc:
            raise RuntimeError(
                f"candidate write failed: {exc}; rollback also failed: {rollback_exc}"
            ) from exc
        raise


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
    frozen_binary_entries = {
        relative: dict(proof["files"][relative])
        for relative in expected_files - generated_paths
    }
    for relative, expected in frozen_binary_entries.items():
        raw = (build.OUTPUT / relative).read_bytes()
        if sha(raw) != expected["sha256"] or len(raw) != expected["bytes"]:
            raise ValueError(f"existing accepted candidate differs: {relative}")

    catalogue = json.loads(build.CATALOGUE.read_text(encoding="utf-8"))
    rendered: dict[str, bytes] = {}
    current_generated: dict[str, bytes] = {}
    for relative in GENERATED:
        current, refreshed = rendered_candidate(relative, catalogue)
        expected = proof["files"][relative]
        expected_matches_current = (
            sha(current) == expected["sha256"] and len(current) == expected["bytes"]
        )
        if refresh_proof and not expected_matches_current and current != refreshed:
            raise ValueError(
                f"existing generated candidate matches neither pinned proof "
                f"nor current rendered runtime: {relative}"
            )
        rendered[relative] = refreshed
        current_generated[relative] = current

    writes: list[tuple[Path, Path, bytes, str]] = []
    if refresh_proof:
        refreshed_proof = json.loads(json.dumps(proof))
        for relative, refreshed in rendered.items():
            refreshed_proof["files"][relative] = {
                "sha256": sha(refreshed),
                "bytes": len(refreshed),
            }
        refreshed_proof["router"] = build.router_contract()
        refreshed_proof["state"] = build.state_contract()

        for relative, expected in frozen_binary_entries.items():
            if refreshed_proof["files"][relative] != expected:
                raise ValueError(
                    f"refresh attempted to alter frozen binary proof entry: {relative}"
                )

        for relative, refreshed in rendered.items():
            if current_generated[relative] != refreshed:
                writes.append(
                    (
                        build.OUTPUT,
                        build.OUTPUT / relative,
                        refreshed,
                        f"native snapshot delivery {GENERATED[relative]['label']} candidate",
                    )
                )
        proof_raw = build.canonical_json(refreshed_proof).encode("utf-8")
        if build.REPORT.read_bytes() != proof_raw:
            writes.append(
                (
                    build.REPORT.parent,
                    build.REPORT,
                    proof_raw,
                    "refreshed native snapshot delivery proof",
                )
            )

        if writes:
            _apply_writes_atomically(writes)
        proof = refreshed_proof

    elif not check_only:
        for relative, refreshed in rendered.items():
            if current_generated[relative] != refreshed:
                writes.append(
                    (
                        build.OUTPUT,
                        build.OUTPUT / relative,
                        refreshed,
                        f"native snapshot delivery {GENERATED[relative]['label']} candidate",
                    )
                )
        if writes:
            _apply_writes_atomically(writes)

    for relative, expected in frozen_binary_entries.items():
        raw = (build.OUTPUT / relative).read_bytes()
        if sha(raw) != expected["sha256"] or len(raw) != expected["bytes"]:
            raise ValueError(f"frozen binary candidate changed during refresh: {relative}")

    for relative, refreshed in rendered.items():
        expected = proof["files"][relative]
        if sha(refreshed) != expected["sha256"] or len(refreshed) != expected["bytes"]:
            raise ValueError(
                f"rendered delivery candidate differs from pinned proof: {relative}"
            )
        path = build.OUTPUT / relative
        current = path.read_bytes()
        if check_only and current != refreshed:
            raise ValueError(f"generated candidate needs refresh: {relative}")
        if current != refreshed:
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
