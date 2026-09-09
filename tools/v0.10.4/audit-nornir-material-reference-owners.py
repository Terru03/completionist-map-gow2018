#!/usr/bin/env python3
"""Read-only classification of every reference to the failed Nornir material.

The shared-model-group audit reported at least one Nornir material reference in
an owner path that was not classified as Nornir. This audit resolves that flag
into exact parent/group ownership so we can distinguish an expected registration
link from an actual stock/Raven dependency leak before building another candidate.
No game files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
RESULT = "NORNIR_MATERIAL_REFERENCE_OWNERS_AUDIT_READ_ONLY"
NORNIR_MATERIAL = "MAT_completionistnornirchest"
NORNIR_MODELS = {"MDL_completionistnornirchest", "MDL_completionistnornirchesthud"}
RAVEN_TOKENS = ("raven", "completionistraven")
STOCK_DOCK_TOKENS = ("dock", "boatdock", "mapicondock")


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_material_owner_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def group_path(records: list[dict], index: int) -> list[dict]:
    out = []
    parent = records[index]["parent"]
    while parent is not None:
        row = records[parent]
        if row["kind"] == 2:
            out.append({"index": parent, "name": row["name"]})
        parent = row["parent"]
    out.reverse()
    return out


def nearest_group_payload(records: list[dict], index: int) -> dict | None:
    parent = records[index]["parent"]
    while parent is not None:
        if records[parent]["kind"] == 2:
            # direct data-bearing children of this group identify the resource owner
            end = parent + 1
            depth = 1
            while end < len(records) and depth:
                if records[end]["kind"] == 2:
                    depth += 1
                elif records[end]["kind"] == 3:
                    depth -= 1
                if depth == 1 and records[end]["kind"] == 1 and records[end]["data"]:
                    row = records[end]
                    return {"index": end, "name": row["name"], "id": row["id"].hex(), "bytes": len(row["data"])}
                end += 1
        parent = records[parent]["parent"]
    return None


def classify(path_names: list[str], owner_payload: dict | None) -> str:
    names = [x.lower() for x in path_names]
    owner = "" if owner_payload is None else owner_payload["name"].lower()
    joined = " / ".join(names + [owner])
    if owner_payload and owner_payload["name"] in NORNIR_MODELS:
        return "expected_nornir_model_dependency"
    if "completionistnornir" in joined or "nornir" in joined:
        return "other_nornir_scope"
    if any(token in joined for token in RAVEN_TOKENS):
        return "raven_scope_leak"
    if any(token in joined for token in STOCK_DOCK_TOKENS):
        return "stock_dock_scope_leak"
    return "other_scope"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-wad", type=Path, required=True)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raven_raw = args.raven_wad.read_bytes()
    candidate_raw = args.candidate_wad.read_bytes()
    check(sha(raven_raw) == EXPECTED_RAVEN_WAD, "Raven baseline WAD changed")

    logical = load_logical()
    raven_records = logical.parse_wad(raven_raw)
    records = logical.parse_wad(candidate_raw)
    check(logical.serialize_wad(raven_records) == raven_raw, "Raven WAD round-trip failed")
    check(logical.serialize_wad(records) == candidate_raw, "candidate WAD round-trip failed")

    defs = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == NORNIR_MATERIAL.lower()]
    check(len(defs) == 1, f"expected one Nornir material payload, found {len(defs)}")
    mat_index, mat = defs[0]

    refs = []
    for i, row in enumerate(records):
        if row["kind"] != 1 or row["data"] or row["id"] != mat["id"]:
            continue
        path = group_path(records, i)
        owner = nearest_group_payload(records, i)
        classification = classify([x["name"] for x in path], owner)
        refs.append({
            "index": i,
            "name": row["name"],
            "id": row["id"].hex(),
            "group_path": path,
            "owner_payload": owner,
            "classification": classification,
        })

    counts = {}
    for ref in refs:
        counts[ref["classification"]] = counts.get(ref["classification"], 0) + 1

    dangerous = [x for x in refs if x["classification"] in {"raven_scope_leak", "stock_dock_scope_leak"}]
    unexplained = [x for x in refs if x["classification"] == "other_scope"]

    report = {
        "schema": 1,
        "result": RESULT,
        "raven_wad_sha256": sha(raven_raw),
        "candidate_wad_sha256": sha(candidate_raw),
        "nornir_material": {"index": mat_index, "name": mat["name"], "id": mat["id"].hex()},
        "references": refs,
        "counts_by_classification": counts,
        "dangerous_stock_or_raven_leak_count": len(dangerous),
        "unexplained_other_scope_count": len(unexplained),
        "safe_to_interpret_previous_outside_scope_flag": len(dangerous) == 0 and len(unexplained) == 0,
        "safety": {"game_files_written": False, "runtime_install_performed": False,
                   "save_state_written": False, "progression_state_written": False,
                   "marker_state_written": False},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  Nornir material id: {mat['id'].hex()}")
    print(f"  total references: {len(refs)}")
    for ref in refs:
        path = " / ".join(x["name"] for x in ref["group_path"]) or "<root>"
        owner = "<none>" if ref["owner_payload"] is None else ref["owner_payload"]["name"]
        print(f"  ref#{ref['index']}: class={ref['classification']} owner={owner} path={path}")
    print(f"  dangerous stock/Raven leaks: {len(dangerous)}")
    print(f"  unexplained other-scope refs: {len(unexplained)}")
    print(f"  previous outside-scope flag is benign/understood: {str(report['safe_to_interpret_previous_outside_scope_flag']).lower()}")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
