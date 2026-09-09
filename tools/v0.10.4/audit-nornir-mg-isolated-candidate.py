#!/usr/bin/env python3
"""Read-only post-build audit for the isolated Nornir model-group candidate.

The first Nornir runtime candidate reused the same stock model-group identities
as Raven/stock and failed at runtime. The MG-isolation gate now produces a WAD
where only the Nornir map/HUD models point at dedicated MG clones.

This audit independently reparses that WAD and proves the reverse-reference
boundary before any second runtime candidate is assembled. It writes only a
JSON report outside the God of War directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = "NORNIR_MG_ISOLATED_CANDIDATE_AUDIT_READ_ONLY"
EXPECTED = {
    "raven": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "failed": "340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c",
    "isolated": "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef",
}
STOCK_MG = {
    "map": ("MG_mapicondock_0", bytes.fromhex("44b11676af9c4e0ff860108fd46b0b32")),
    "hud": ("MG_boatdock_0", bytes.fromhex("c3f6b4c5a8270df607ea3e6e7f891292")),
}
NORNIR_MG = {
    "map": ("MG_completionistnornirchest_map", bytes.fromhex("5744bb47f2e8c80f74e30dbdf4a53b3a")),
    "hud": ("MG_completionistnornirchest_hud", bytes.fromhex("4e70c65d5c2fa007585254e7c2a3e333")),
}
NORNIR_MODEL = {
    "map": "MDL_completionistnornirchest",
    "hud": "MDL_completionistnornirchesthud",
}
RAVEN_MODEL = {
    "map": "MDL_completionistraven",
    "hud": "MDL_completionistravenhud",
}
NORNIR_MATERIAL = "MAT_completionistnornirchest"
NORNIR_TEXTURES = {
    "diffuse": "TX_completionist_nornir_chest_diff_0A43AEB29D6F80DA",
    "emissive": "TX_completionist_nornir_chest_emis_58012A499511A0BB",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_mg_isolated_audit_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def unique_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one data payload {name!r}, found {len(hits)}")
    return hits[0]


def group_bounds(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    parent = records[payload_index]["parent"]
    check(parent is not None and records[parent]["kind"] == 2,
          f"{records[payload_index]['name']}: expected containing resource group")
    return parent, logical.matching_group_end(records, parent)


def group_links(logical, records: list[dict], payload_index: int) -> list[tuple[int, dict]]:
    start, end = group_bounds(logical, records, payload_index)
    return [(i, records[i]) for i in range(start, end + 1)
            if records[i]["kind"] == 1 and not records[i]["data"]]


def resource_group_bytes(logical, records: list[dict], name: str) -> bytes:
    idx, _ = unique_payload(records, name)
    start, end = group_bounds(logical, records, idx)
    return b"".join(logical.record_bytes(records[i]) for i in range(start, end + 1))


def all_refs(records: list[dict], rid: bytes) -> list[tuple[int, dict]]:
    return [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and not row["data"] and row["id"] == rid]


def ref_indices_in_resource(logical, records: list[dict], resource_name: str, rid: bytes) -> set[int]:
    idx, _ = unique_payload(records, resource_name)
    return {i for i, row in group_links(logical, records, idx) if row["id"] == rid}


def named_rows(records: list[dict], name: str) -> list[dict]:
    return [{
        "index": i,
        "kind": row["kind"],
        "flags": row["flags"],
        "bytes": len(row["data"]),
        "id": row["id"].hex(),
        "payload_index": row["payload_index"],
        "parent": row["parent"],
    } for i, row in enumerate(records) if row["name"].lower() == name.lower()]


def model_dependency_proof(logical, records: list[dict], kind: str) -> dict:
    stock_name, stock_id = STOCK_MG[kind]
    dedicated_name, dedicated_id = NORNIR_MG[kind]

    n_idx, _ = unique_payload(records, NORNIR_MODEL[kind])
    n_links = group_links(logical, records, n_idx)
    n_dedicated = [(i, row) for i, row in n_links
                   if row["name"].lower() == dedicated_name.lower() and row["id"] == dedicated_id]
    n_stock = [(i, row) for i, row in n_links
               if row["name"].lower() == stock_name.lower() and row["id"] == stock_id]
    check(len(n_dedicated) == 1, f"{kind}: Nornir model does not have exactly one dedicated MG dependency")
    check(not n_stock, f"{kind}: Nornir model still references the stock MG")

    r_idx, _ = unique_payload(records, RAVEN_MODEL[kind])
    r_links = group_links(logical, records, r_idx)
    r_stock = [(i, row) for i, row in r_links
               if row["name"].lower() == stock_name.lower() and row["id"] == stock_id]
    r_dedicated = [(i, row) for i, row in r_links
                   if row["name"].lower() == dedicated_name.lower() or row["id"] == dedicated_id]
    check(len(r_stock) == 1, f"{kind}: Raven model lost its stock MG dependency")
    check(not r_dedicated, f"{kind}: Raven model references the dedicated Nornir MG")

    refs = all_refs(records, dedicated_id)
    check(len(refs) == 1, f"{kind}: dedicated MG reverse-reference count is {len(refs)}, expected 1")
    check(refs[0][0] == n_dedicated[0][0], f"{kind}: dedicated MG is referenced outside its intended Nornir model")

    return {
        "nornir_model": NORNIR_MODEL[kind],
        "raven_model": RAVEN_MODEL[kind],
        "stock_mg": {"name": stock_name, "id": stock_id.hex()},
        "dedicated_mg": {"name": dedicated_name, "id": dedicated_id.hex()},
        "nornir_dedicated_ref_index": n_dedicated[0][0],
        "nornir_stock_ref_count": len(n_stock),
        "raven_stock_ref_index": r_stock[0][0],
        "raven_dedicated_ref_count": len(r_dedicated),
        "dedicated_reverse_ref_count": len(refs),
    }


def material_texture_boundary(logical, records: list[dict]) -> dict:
    _, material = unique_payload(records, NORNIR_MATERIAL)
    material_refs = all_refs(records, material["id"])
    intended_material_indices = (
        ref_indices_in_resource(logical, records, NORNIR_MODEL["map"], material["id"]) |
        ref_indices_in_resource(logical, records, NORNIR_MODEL["hud"], material["id"])
    )
    check(len(material_refs) == 2, f"Nornir material reference count changed: {len(material_refs)}")
    check({i for i, _ in material_refs} == intended_material_indices and len(intended_material_indices) == 2,
          "Nornir material reference leaked outside the two intended Nornir models")

    texture_rows = {}
    material_idx, _ = unique_payload(records, NORNIR_MATERIAL)
    material_links = group_links(logical, records, material_idx)
    for label, name in NORNIR_TEXTURES.items():
        defs = [(i, row) for i, row in enumerate(records)
                if row["kind"] == 1 and row["flags"] == 0x8021 and row["data"]
                and row["name"].lower() == name.lower()]
        check(len(defs) == 1, f"expected one {label} Nornir texture definition")
        definition = defs[0][1]
        refs = all_refs(records, definition["id"])
        intended = [(i, row) for i, row in material_links if row["id"] == definition["id"]]
        check(len(refs) == 1 and len(intended) == 1 and refs[0][0] == intended[0][0],
              f"Nornir {label} texture reference leaked outside the Nornir material")
        texture_rows[label] = {
            "name": name,
            "definition_id": definition["id"].hex(),
            "reference_index": refs[0][0],
        }

    return {
        "material_id": material["id"].hex(),
        "material_reference_count": len(material_refs),
        "material_refs_only_from_nornir_models": True,
        "textures": texture_rows,
        "texture_refs_only_from_nornir_material": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raven-wad", type=Path, required=True)
    ap.add_argument("--failed-wad", type=Path, required=True)
    ap.add_argument("--isolated-wad", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raven_raw = args.raven_wad.read_bytes()
    failed_raw = args.failed_wad.read_bytes()
    isolated_raw = args.isolated_wad.read_bytes()
    check(sha(raven_raw) == EXPECTED["raven"], f"Raven WAD changed: {sha(raven_raw)}")
    check(sha(failed_raw) == EXPECTED["failed"], f"failed candidate WAD changed: {sha(failed_raw)}")
    check(sha(isolated_raw) == EXPECTED["isolated"], f"isolated candidate WAD changed: {sha(isolated_raw)}")

    logical = load_logical()
    raven = logical.parse_wad(raven_raw)
    failed = logical.parse_wad(failed_raw)
    isolated = logical.parse_wad(isolated_raw)
    check(logical.serialize_wad(raven) == raven_raw, "Raven WAD round-trip failed")
    check(logical.serialize_wad(failed) == failed_raw, "failed candidate WAD round-trip failed")
    check(logical.serialize_wad(isolated) == isolated_raw, "isolated candidate WAD round-trip failed")

    mg_payloads = {}
    for kind in ("map", "hud"):
        stock_name, stock_id = STOCK_MG[kind]
        dedicated_name, dedicated_id = NORNIR_MG[kind]
        s_idx, stock = unique_payload(isolated, stock_name)
        d_idx, dedicated = unique_payload(isolated, dedicated_name)
        check(stock["id"] == stock_id and dedicated["id"] == dedicated_id,
              f"{kind}: stock/dedicated MG ID mismatch")
        check(stock["parent"] is None and dedicated["parent"] is None,
              f"{kind}: MG donor/clone is no longer standalone")
        check(stock["kind"] == dedicated["kind"] == 1 and stock["flags"] == dedicated["flags"] == 0x98,
              f"{kind}: MG kind/flags changed")
        check(bytes(stock["data"]) == bytes(dedicated["data"]),
              f"{kind}: dedicated MG payload differs from its stock donor")

        _, failed_stock = unique_payload(failed, stock_name)
        _, raven_stock = unique_payload(raven, stock_name)
        check(stock["id"] == failed_stock["id"] == raven_stock["id"] and
              bytes(stock["data"]) == bytes(failed_stock["data"]) == bytes(raven_stock["data"]),
              f"{kind}: original stock MG changed across Raven/failed/isolated WADs")
        check(not named_rows(failed, dedicated_name), f"{kind}: dedicated MG unexpectedly exists in failed candidate")
        check(not named_rows(raven, dedicated_name), f"{kind}: dedicated MG unexpectedly exists in Raven baseline")
        rows = named_rows(isolated, dedicated_name)
        check(len(rows) == 2, f"{kind}: expected dedicated MG payload + one dependency link, found {len(rows)} rows")
        mg_payloads[kind] = {
            "stock_record_index": s_idx,
            "dedicated_record_index": d_idx,
            "stock_name": stock_name,
            "stock_id": stock_id.hex(),
            "dedicated_name": dedicated_name,
            "dedicated_id": dedicated_id.hex(),
            "payload_bytes": len(dedicated["data"]),
            "all_named_rows": rows,
            "payload_byte_identical_to_donor": True,
        }

    dependencies = {kind: model_dependency_proof(logical, isolated, kind) for kind in ("map", "hud")}

    # Raven model resource groups must remain byte-identical to the failed
    # candidate. The isolated build is allowed to change only the Nornir model
    # links, add two MG payloads, and adjust WAD accounting.
    raven_group_proofs = {}
    for kind in ("map", "hud"):
        before = resource_group_bytes(logical, failed, RAVEN_MODEL[kind])
        after = resource_group_bytes(logical, isolated, RAVEN_MODEL[kind])
        check(before == after, f"{kind}: Raven model resource group changed in isolated candidate")
        raven_group_proofs[kind] = True

    boundary = material_texture_boundary(logical, isolated)

    report = {
        "schema": 1,
        "result": RESULT,
        "sha256": {
            "frozen_raven": sha(raven_raw),
            "failed_candidate": sha(failed_raw),
            "isolated_candidate": sha(isolated_raw),
        },
        "model_groups": mg_payloads,
        "model_dependencies": dependencies,
        "raven_model_groups_byte_identical_to_failed_candidate": raven_group_proofs,
        "nornir_material_texture_boundary": boundary,
        "proofs": {
            "isolated_candidate_reparse_roundtrip_exact": True,
            "original_stock_mg_payloads_preserved": True,
            "dedicated_mg_payloads_match_stock_donors": True,
            "nornir_models_use_dedicated_mg_only": True,
            "raven_models_use_stock_mg_only": True,
            "dedicated_mg_reverse_refs_exactly_intended_nornir_models": True,
            "raven_model_groups_unchanged": True,
            "nornir_material_refs_do_not_leak": True,
            "nornir_texture_refs_do_not_leak": True,
            "shared_stock_model_group_isolation_gap_closed": True,
            "safe_to_assemble_runtime_candidate_2": True,
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
    print(f"  isolated WAD: {report['sha256']['isolated_candidate']}")
    for kind in ("map", "hud"):
        row = dependencies[kind]
        print(f"  {kind}: Nornir -> {row['dedicated_mg']['name']}:{row['dedicated_mg']['id']}")
        print(f"  {kind}: Raven  -> {row['stock_mg']['name']}:{row['stock_mg']['id']}")
        print(f"  {kind}: dedicated reverse refs={row['dedicated_reverse_ref_count']} stale Nornir stock refs={row['nornir_stock_ref_count']}")
    print(f"  Nornir material refs: {boundary['material_reference_count']} (only intended Nornir models)")
    print("  Nornir texture refs outside Nornir material: 0")
    print("  stock MG payloads changed: false")
    print("  Raven model groups changed: false")
    print("  shared stock model-group isolation gap closed: true")
    print("  safe to assemble runtime candidate #2: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
