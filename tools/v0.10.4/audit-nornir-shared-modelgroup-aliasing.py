#!/usr/bin/env python3
"""Read-only audit for shared stock MG resource aliasing in the failed Nornir candidate.

The first Nornir runtime candidate showed the Nornir artwork on every boat/dock
map marker, hid the proven Raven map artwork, and crashed while the map was open.
The previous audits ruled out DCB relocation corruption and showed that the
Nornir map/HUD model payloads are byte-identical to the Raven donors while both
still depend on the stock MG_mapicondock_0 / MG_boatdock_0 resources.

This audit answers a narrower question before any second runtime candidate:
which stock model-group identities are still shared by stock, Raven and Nornir,
and do any Nornir material/texture identities leak into non-Nornir groups?
It writes only a JSON report outside the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
RESULT = "NORNIR_SHARED_MODEL_GROUP_ALIASING_AUDIT_READ_ONLY"

RAVEN = {
    "map_model": "MDL_completionistraven",
    "hud_model": "MDL_completionistravenhud",
    "material": "MAT_AE4AD85BB993F040",
    "map_root": "gomapiconcompletionistraven",
}
NORNIR = {
    "map_model": "MDL_completionistnornirchest",
    "hud_model": "MDL_completionistnornirchesthud",
    "material": "MAT_completionistnornirchest",
    "map_root": "gomapiconcompletionistnornirchest",
    "diffuse": "TX_completionist_nornir_chest_diff_0A43AEB29D6F80DA",
    "emissive": "TX_completionist_nornir_chest_emis_58012A499511A0BB",
}
STOCK_MG = {
    "map": "MG_mapicondock_0",
    "hud": "MG_boatdock_0",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_shared_mg_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def group_end(logical, records: list[dict], start: int) -> int:
    return logical.matching_group_end(records, start)


def group_path(records: list[dict], index: int) -> list[str]:
    out: list[str] = []
    parent = records[index]["parent"]
    while parent is not None:
        row = records[parent]
        if row["kind"] == 2:
            out.append(row["name"])
        parent = row["parent"]
    out.reverse()
    return out


def rows_named(records: list[dict], name: str) -> list[dict]:
    out = []
    for i, row in enumerate(records):
        if row["name"].lower() != name.lower():
            continue
        out.append({
            "index": i,
            "kind": row["kind"],
            "flags": row["flags"],
            "bytes": len(row["data"]),
            "id": row["id"].hex(),
            "payload_index": row["payload_index"],
            "parent": row["parent"],
            "group_path": group_path(records, i),
        })
    return out


def unique_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def group_links(logical, records: list[dict], payload_index: int) -> list[dict]:
    parent = records[payload_index]["parent"]
    check(parent is not None and records[parent]["kind"] == 2,
          f"{records[payload_index]['name']}: no containing group")
    end = group_end(logical, records, parent)
    out = []
    for i in range(parent, end + 1):
        row = records[i]
        if row["kind"] == 1 and not row["data"]:
            out.append({
                "index": i,
                "name": row["name"],
                "id": row["id"].hex(),
                "group_path": group_path(records, i),
            })
    return out


def dependency(logical, records: list[dict], model_name: str, dependency_name: str) -> dict:
    idx, row = unique_payload(records, model_name)
    links = [x for x in group_links(logical, records, idx)
             if x["name"].lower() == dependency_name.lower()]
    check(len(links) == 1,
          f"{model_name}: expected one dependency {dependency_name!r}, found {len(links)}")
    return {
        "model_index": idx,
        "model_id": row["id"].hex(),
        "dependency": links[0],
    }


def all_links_to(records: list[dict], *, name: str | None = None, rid: bytes | None = None) -> list[dict]:
    out = []
    for i, row in enumerate(records):
        if row["kind"] != 1 or row["data"]:
            continue
        if name is not None and row["name"].lower() != name.lower():
            continue
        if rid is not None and row["id"] != rid:
            continue
        out.append({
            "index": i,
            "name": row["name"],
            "id": row["id"].hex(),
            "group_path": group_path(records, i),
        })
    return out


def payload_ids(records: list[dict], name: str) -> list[str]:
    return [row["id"] for row in rows_named(records, name) if row["bytes"] > 0]


def classify_owner(path: list[str]) -> str:
    low = " / ".join(path).lower()
    if "nornir" in low or "completionistnornir" in low:
        return "nornir"
    if "raven" in low or "completionistraven" in low:
        return "raven"
    return "stock_or_other"


def summarize_refs(rows: list[dict]) -> dict:
    counts = {"nornir": 0, "raven": 0, "stock_or_other": 0}
    for row in rows:
        counts[classify_owner(row["group_path"])] += 1
    return {"counts_by_owner": counts, "rows": rows}


def root_parent_links(records: list[dict], root_name: str, root_id: bytes) -> list[dict]:
    return all_links_to(records, name=root_name, rid=root_id)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-wad", type=Path, required=True)
    ap.add_argument("--candidate-wad", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raven_raw = args.raven_wad.read_bytes()
    candidate_raw = args.candidate_wad.read_bytes()
    check(sha(raven_raw) == EXPECTED_RAVEN_WAD,
          "baseline r_ui.wad is not frozen runtime-proven Raven production")

    logical = load_logical()
    raven_records = logical.parse_wad(raven_raw)
    candidate_records = logical.parse_wad(candidate_raw)
    check(logical.serialize_wad(raven_records) == raven_raw, "Raven WAD round-trip failed")
    check(logical.serialize_wad(candidate_records) == candidate_raw, "candidate WAD round-trip failed")

    map_mg_rows = rows_named(candidate_records, STOCK_MG["map"])
    hud_mg_rows = rows_named(candidate_records, STOCK_MG["hud"])
    check(map_mg_rows, "candidate has no MG_mapicondock_0 records")
    check(hud_mg_rows, "candidate has no MG_boatdock_0 records")

    raven_map_dep = dependency(logical, candidate_records, RAVEN["map_model"], STOCK_MG["map"])
    nornir_map_dep = dependency(logical, candidate_records, NORNIR["map_model"], STOCK_MG["map"])
    raven_hud_dep = dependency(logical, candidate_records, RAVEN["hud_model"], STOCK_MG["hud"])
    nornir_hud_dep = dependency(logical, candidate_records, NORNIR["hud_model"], STOCK_MG["hud"])

    shared_map_mg_id = raven_map_dep["dependency"]["id"] == nornir_map_dep["dependency"]["id"]
    shared_hud_mg_id = raven_hud_dep["dependency"]["id"] == nornir_hud_dep["dependency"]["id"]

    nornir_material_index, nornir_material = unique_payload(candidate_records, NORNIR["material"])
    nornir_material_refs = all_links_to(candidate_records, rid=nornir_material["id"])

    nornir_texture_refs = {}
    for label in ("diffuse", "emissive"):
        defs = [(i, row) for i, row in enumerate(candidate_records)
                if row["kind"] == 1 and row["flags"] == 0x8021 and row["data"]
                and row["name"].lower() == NORNIR[label].lower()]
        check(len(defs) == 1, f"expected one Nornir {label} texture definition")
        _, definition = defs[0]
        nornir_texture_refs[label] = all_links_to(candidate_records, rid=definition["id"])

    _, raven_root = unique_payload(candidate_records, RAVEN["map_root"])
    _, nornir_root = unique_payload(candidate_records, NORNIR["map_root"])
    raven_root_parents = root_parent_links(candidate_records, RAVEN["map_root"], raven_root["id"])
    nornir_root_parents = root_parent_links(candidate_records, NORNIR["map_root"], nornir_root["id"])

    stock_mg_link_refs = {
        "map": summarize_refs(all_links_to(candidate_records, name=STOCK_MG["map"],
                                            rid=bytes.fromhex(raven_map_dep["dependency"]["id"]))),
        "hud": summarize_refs(all_links_to(candidate_records, name=STOCK_MG["hud"],
                                            rid=bytes.fromhex(raven_hud_dep["dependency"]["id"]))),
    }

    material_summary = summarize_refs(nornir_material_refs)
    texture_summary = {k: summarize_refs(v) for k, v in nornir_texture_refs.items()}

    flags = {
        "nornir_map_model_reuses_exact_raven_stock_mg_id": shared_map_mg_id,
        "nornir_hud_model_reuses_exact_raven_stock_mg_id": shared_hud_mg_id,
        "nornir_material_referenced_outside_nornir_groups": material_summary["counts_by_owner"]["stock_or_other"] > 0 or material_summary["counts_by_owner"]["raven"] > 0,
        "nornir_diffuse_referenced_outside_nornir_groups": texture_summary["diffuse"]["counts_by_owner"]["stock_or_other"] > 0 or texture_summary["diffuse"]["counts_by_owner"]["raven"] > 0,
        "nornir_emissive_referenced_outside_nornir_groups": texture_summary["emissive"]["counts_by_owner"]["stock_or_other"] > 0 or texture_summary["emissive"]["counts_by_owner"]["raven"] > 0,
        "failed_runtime_symptom_consistent_with_shared_mg_cache_aliasing": shared_map_mg_id,
        "root_cause_proven": False,
    }

    report = {
        "schema": 1,
        "result": RESULT,
        "raven_wad_sha256": sha(raven_raw),
        "candidate_wad_sha256": sha(candidate_raw),
        "runtime_failure_observed": {
            "nornir_art_on_all_boat_markers": True,
            "raven_map_art_missing": True,
            "map_crash": True,
        },
        "stock_model_groups": {
            "map": {"name": STOCK_MG["map"], "records": map_mg_rows, "all_references": stock_mg_link_refs["map"]},
            "hud": {"name": STOCK_MG["hud"], "records": hud_mg_rows, "all_references": stock_mg_link_refs["hud"]},
        },
        "model_dependencies": {
            "raven_map": raven_map_dep,
            "nornir_map": nornir_map_dep,
            "raven_hud": raven_hud_dep,
            "nornir_hud": nornir_hud_dep,
        },
        "nornir_material": {
            "index": nornir_material_index,
            "id": nornir_material["id"].hex(),
            "references": material_summary,
        },
        "nornir_texture_references": texture_summary,
        "map_root_parent_links": {
            "raven": raven_root_parents,
            "nornir": nornir_root_parents,
        },
        "flags": flags,
        "interpretation": {
            "relocation_corruption_previously_ruled_out": True,
            "shared_stock_model_group_identity_is_a_real_isolation_gap": shared_map_mg_id or shared_hud_mg_id,
            "recommended_next_step_if_no_nornir_refs_leak_outside_nornir_groups": "Build an OFFLINE Nornir-only model-group isolation candidate that clones MG_mapicondock_0 and MG_boatdock_0 under dedicated Nornir identities, retargets only the Nornir model links, and proves byte-exact normalization back to the frozen Raven WAD. Do not runtime-install until that candidate passes structural audits.",
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  Raven WAD:     {report['raven_wad_sha256']}")
    print(f"  candidate WAD: {report['candidate_wad_sha256']}")
    print(f"  map MG shared Raven/Nornir ID: {str(shared_map_mg_id).lower()}")
    print(f"    Raven -> {STOCK_MG['map']}:{raven_map_dep['dependency']['id']}")
    print(f"    Nornir -> {STOCK_MG['map']}:{nornir_map_dep['dependency']['id']}")
    print(f"  HUD MG shared Raven/Nornir ID: {str(shared_hud_mg_id).lower()}")
    print(f"    Raven -> {STOCK_MG['hud']}:{raven_hud_dep['dependency']['id']}")
    print(f"    Nornir -> {STOCK_MG['hud']}:{nornir_hud_dep['dependency']['id']}")
    print(f"  Nornir material refs outside Nornir groups: {str(flags['nornir_material_referenced_outside_nornir_groups']).lower()}")
    print(f"  Nornir diffuse refs outside Nornir groups: {str(flags['nornir_diffuse_referenced_outside_nornir_groups']).lower()}")
    print(f"  Nornir emissive refs outside Nornir groups: {str(flags['nornir_emissive_referenced_outside_nornir_groups']).lower()}")
    print(f"  shared-MG isolation gap present: {str(report['interpretation']['shared_stock_model_group_identity_is_a_real_isolation_gap']).lower()}")
    print("  root cause proven: false")
    print("  game files written: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
