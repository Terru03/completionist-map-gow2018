#!/usr/bin/env python3
"""Build a Nornir-only model-group isolation WAD candidate entirely offline.

The first Nornir runtime candidate rendered Nornir art on stock boat/dock map
markers, hid the proven Raven map art, and later crashed while the map was open.
Read-only audits then established:

* WAD_R_UI DCB relocation corruption is not present;
* Nornir material/texture references do not leak into stock/Raven groups;
* both Nornir models still depend on the exact stock MG_mapicondock_0 and
  MG_boatdock_0 identities also used by Raven/stock resources.

This builder starts from that exact failed-but-offline-verifiable Nornir WAD,
clones only those two shared MG groups under dedicated Nornir identities,
retargets only the Nornir map/HUD model dependencies, reparses the result, and
proves exact reversibility back to the failed candidate. The failed candidate
itself was already proven reversible to the frozen Raven WAD by the prior gate.

No God of War file is modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
RESULT = "OFFLINE_NORNIR_MG_ISOLATION_BUILT"
EXPECTED_FAILED_WAD = "340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c"
EXPECTED_RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"

STOCK_MG = {
    "map": "MG_mapicondock_0",
    "hud": "MG_boatdock_0",
}
NORNIR_MG = {
    "map": "MG_completionistnornirchest_map",
    "hud": "MG_completionistnornirchest_hud",
}
NORNIR_MODEL = {
    "map": "MDL_completionistnornirchest",
    "hud": "MDL_completionistnornirchesthud",
}
RAVEN_MODEL = {
    "map": "MDL_completionistraven",
    "hud": "MDL_completionistravenhud",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("nornir_mg_isolation_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deterministic_id(name: str) -> bytes:
    seed = f"completionist-map-gow2018:v0.10.4:nornir-mg:{name}".encode("ascii")
    return hashlib.sha256(seed).digest()[:16]


def set_name(row: dict, name: str) -> None:
    check(len(name.encode("ascii")) <= 55, f"WAD header name too long: {name}")
    row["name"] = name
    row["original_offset"] = None


def unique_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def group_bounds(logical, records: list[dict], payload_index: int) -> tuple[int, int]:
    parent = records[payload_index]["parent"]
    check(parent is not None and records[parent]["kind"] == 2,
          f"{records[payload_index]['name']}: missing containing group")
    return parent, logical.matching_group_end(records, parent)


def group_rows(logical, records: list[dict], payload_index: int) -> list[dict]:
    start, end = group_bounds(logical, records, payload_index)
    return records[start:end + 1]


def group_links(logical, records: list[dict], payload_index: int) -> list[dict]:
    start, end = group_bounds(logical, records, payload_index)
    return [records[i] for i in range(start, end + 1)
            if records[i]["kind"] == 1 and not records[i]["data"]]


def clone_single_payload_group(logical, records: list[dict], source_name: str,
                               new_name: str, new_id: bytes) -> tuple[list[dict], dict]:
    source_index, source = unique_payload(records, source_name)
    start, end = group_bounds(logical, records, source_index)
    source_group = records[start:end + 1]
    data_rows = [(i, row) for i, row in enumerate(source_group)
                 if row["kind"] == 1 and row["data"]]
    check(len(data_rows) == 1 and data_rows[0][1]["name"].lower() == source_name.lower(),
          f"{source_name}: expected a single-payload resource group, found {[(x[1]['name'], len(x[1]['data'])) for x in data_rows]}")

    source_blob = bytes(source["data"])
    check(source_blob.count(source["id"]) == 0,
          f"{source_name}: source payload embeds its own record ID; clone requires a dedicated self-ID transform")
    check(source_name.lower().encode("ascii") not in source_blob.lower(),
          f"{source_name}: source payload embeds its own ASCII name; clone requires a dedicated name transform")

    rows = copy.deepcopy(source_group)
    for old, row in zip(source_group, rows):
        row["_source_payload_index"] = old["payload_index"] if old["data"] else None
        row["original_offset"] = None
        row["payload_index"] = None
        if row["kind"] in (2, 3) and row["name"].lower() == source_name.lower():
            set_name(row, new_name)

    targets = [row for row in rows if row["kind"] == 1 and row["data"]
               and row["name"].lower() == source_name.lower()]
    check(len(targets) == 1, f"{source_name}: cloned target is not unique")
    target = targets[0]
    set_name(target, new_name)
    target["id"] = new_id

    return rows, {
        "source_index": source_index,
        "source_payload_index": source["payload_index"],
        "source_id": source["id"],
        "source_name": source_name,
        "source_group_start": start,
        "source_group_end": end,
        "source_group_physical_rows": len(source_group),
        "source_group_payload_rows": 1,
        "new_name": new_name,
        "new_id": new_id,
    }


def retarget_model_link(logical, records: list[dict], model_name: str,
                        old_name: str, old_id: bytes, new_name: str, new_id: bytes) -> dict:
    model_index, model = unique_payload(records, model_name)
    start, end = group_bounds(logical, records, model_index)
    hits = [(i, records[i]) for i in range(start, end + 1)
            if records[i]["kind"] == 1 and not records[i]["data"]
            and records[i]["name"].lower() == old_name.lower()
            and records[i]["id"] == old_id]
    check(len(hits) == 1,
          f"{model_name}: expected one dependency {old_name}:{old_id.hex()}, found {len(hits)}")
    index, row = hits[0]
    set_name(row, new_name)
    row["id"] = new_id
    return {
        "model_name": model_name,
        "model_id": model["id"].hex(),
        "link_record_index_before_reparse": index,
        "old_name": old_name,
        "old_id": old_id.hex(),
        "new_name": new_name,
        "new_id": new_id.hex(),
    }


def type_row_for_payload(logical, records: list[dict], payload_index: int) -> dict:
    payloads = logical.payload_records(records)
    check(len(payloads) >= 2, "WAD accounting payloads missing")
    root = payloads[1]
    rows = logical.read_type_table(root["data"])
    hits = [row for row in rows if row["base"] <= payload_index < row["base"] + row["count"]]
    check(len(hits) == 1,
          f"payload {payload_index} does not map to exactly one ordinary WAD type row")
    return hits[0]


def apply_direct_accounting(logical, records: list[dict], clone_groups: list[list[dict]]) -> dict:
    payloads = logical.payload_records(records)
    heap, root = payloads[0], payloads[1]
    before_heap = bytes(heap["data"])
    before_root = bytes(root["data"])
    old_total = struct.unpack_from("<I", heap["data"], 4)[0]
    check(old_total == struct.unpack_from("<I", root["data"], 0x1C)[0], "WAD accounting totals disagree")
    rows = logical.read_type_table(root["data"])

    increments: dict[int, int] = {}
    details = []
    cloned_payloads = [row for group in clone_groups for row in group if row["data"]]
    for clone in cloned_payloads:
        source_index = clone.get("_source_payload_index")
        check(isinstance(source_index, int), f"clone {clone['name']} lost source payload index")
        type_row = type_row_for_payload(logical, records, source_index)
        increments[type_row["index"]] = increments.get(type_row["index"], 0) + 1
        details.append({
            "clone_name": clone["name"],
            "source_payload_index": source_index,
            "type_key": f"0x{type_row['key']:X}",
            "type_row_index": type_row["index"],
        })

    new_base = 0
    for row in rows:
        amount = row["count"] + increments.get(row["index"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], new_base, amount)
        new_base += amount
    check(new_base == old_total + len(cloned_payloads), "MG clone accounting total changed unexpectedly")
    struct.pack_into("<I", root["data"], 0x1C, new_base)
    struct.pack_into("<I", heap["data"], 4, new_base)

    return {
        "before_total": old_total,
        "after_total": new_base,
        "payload_delta": len(cloned_payloads),
        "classified_payloads": details,
        "source_heap_data": before_heap,
        "source_root_data": before_root,
    }


def exact_group_bytes(logical, rows: list[dict]) -> bytes:
    return b"".join(logical.record_bytes(copy.deepcopy(row)) for row in rows)


def count_links(records: list[dict], name: str, rid: bytes) -> int:
    return sum(1 for row in records if row["kind"] == 1 and not row["data"]
               and row["name"].lower() == name.lower() and row["id"] == rid)


def build(failed_raw: bytes, raven_raw: bytes) -> tuple[bytes, dict]:
    check(sha(failed_raw) == EXPECTED_FAILED_WAD,
          f"input failed candidate WAD changed: {sha(failed_raw)}")
    check(sha(raven_raw) == EXPECTED_RAVEN_WAD,
          f"Raven baseline WAD changed: {sha(raven_raw)}")

    logical = load_logical()
    records = logical.parse_wad(failed_raw)
    raven_records = logical.parse_wad(raven_raw)
    check(logical.serialize_wad(records) == failed_raw, "failed candidate WAD does not round-trip exactly")
    check(logical.serialize_wad(raven_records) == raven_raw, "Raven baseline WAD does not round-trip exactly")

    existing_names = {row["name"].lower() for row in records}
    existing_ids = {row["id"] for row in records}
    new_ids = {kind: deterministic_id(name) for kind, name in NORNIR_MG.items()}
    check(len(set(new_ids.values())) == 2, "dedicated Nornir MG IDs collide with one another")
    for kind in ("map", "hud"):
        check(NORNIR_MG[kind].lower() not in existing_names,
              f"dedicated Nornir {kind} MG name already exists")
        check(new_ids[kind] not in existing_ids,
              f"dedicated Nornir {kind} MG ID collides with existing WAD resource")

    # Stock/Raven MG resource groups must be identical between the restored
    # Raven baseline and the failed candidate before we use them as donors.
    donor_proofs = {}
    for kind in ("map", "hud"):
        c_idx, c_payload = unique_payload(records, STOCK_MG[kind])
        r_idx, r_payload = unique_payload(raven_records, STOCK_MG[kind])
        c_rows = group_rows(logical, records, c_idx)
        r_rows = group_rows(logical, raven_records, r_idx)
        check(c_payload["id"] == r_payload["id"], f"{kind}: stock MG ID changed in failed candidate")
        check(exact_group_bytes(logical, c_rows) == exact_group_bytes(logical, r_rows),
              f"{kind}: stock MG group changed in failed candidate")
        donor_proofs[kind] = {
            "stock_name": STOCK_MG[kind],
            "stock_id": c_payload["id"].hex(),
            "group_byte_identical_to_raven_baseline": True,
            "group_physical_rows": len(c_rows),
            "group_payload_rows": sum(1 for row in c_rows if row["data"]),
        }

    clone_groups = {}
    clone_info = {}
    for kind in ("map", "hud"):
        rows, info = clone_single_payload_group(
            logical, records, STOCK_MG[kind], NORNIR_MG[kind], new_ids[kind])
        clone_groups[kind] = rows
        clone_info[kind] = info

    accounting = apply_direct_accounting(logical, records, [clone_groups["map"], clone_groups["hud"]])

    # Retarget only the Nornir models. Raven and stock users of the original MG
    # resource remain untouched.
    retargets = {}
    for kind in ("map", "hud"):
        retargets[kind] = retarget_model_link(
            logical, records, NORNIR_MODEL[kind], STOCK_MG[kind],
            clone_info[kind]["source_id"], NORNIR_MG[kind], new_ids[kind])

    # Insert each dedicated MG immediately after its stock donor group. Reverse
    # order avoids invalidating the earlier insertion index.
    jobs = [(clone_info[kind]["source_group_end"], clone_groups[kind]) for kind in ("map", "hud")]
    for after, rows in sorted(jobs, key=lambda item: item[0], reverse=True):
        records[after + 1:after + 1] = rows

    candidate = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate)
    check(logical.serialize_wad(reparsed) == candidate, "isolated MG candidate does not reparse/round-trip exactly")

    source_group_snapshots = {}
    for kind in ("map", "hud"):
        idx, payload = unique_payload(reparsed, NORNIR_MG[kind])
        check(payload["id"] == new_ids[kind], f"{kind}: dedicated MG ID changed after reparse")
        rows = group_rows(logical, reparsed, idx)
        check(sum(1 for row in rows if row["data"]) == 1, f"{kind}: dedicated MG group payload shape changed")
        source_group_snapshots[kind] = {
            "new_name": NORNIR_MG[kind],
            "new_id": new_ids[kind].hex(),
            "group_physical_rows": len(rows),
            "group_payload_rows": 1,
        }

        # Nornir model must use only the dedicated MG.
        n_idx, _ = unique_payload(reparsed, NORNIR_MODEL[kind])
        n_links = group_links(logical, reparsed, n_idx)
        dedicated = [row for row in n_links if row["name"].lower() == NORNIR_MG[kind].lower()
                     and row["id"] == new_ids[kind]]
        stale = [row for row in n_links if row["name"].lower() == STOCK_MG[kind].lower()
                 and row["id"] == clone_info[kind]["source_id"]]
        check(len(dedicated) == 1 and not stale,
              f"{kind}: Nornir model was not exclusively retargeted to dedicated MG")

        # Raven model must still use the original stock MG.
        r_idx, _ = unique_payload(reparsed, RAVEN_MODEL[kind])
        r_links = group_links(logical, reparsed, r_idx)
        raven_old = [row for row in r_links if row["name"].lower() == STOCK_MG[kind].lower()
                     and row["id"] == clone_info[kind]["source_id"]]
        raven_new = [row for row in r_links if row["name"].lower() == NORNIR_MG[kind].lower()
                     or row["id"] == new_ids[kind]]
        check(len(raven_old) == 1 and not raven_new,
              f"{kind}: Raven model dependency changed during Nornir MG isolation")

    # Dedicated IDs/names must only be consumed by the intended Nornir models.
    dedicated_reverse_refs = {}
    for kind in ("map", "hud"):
        refs = [(i, row) for i, row in enumerate(reparsed)
                if row["kind"] == 1 and not row["data"] and row["id"] == new_ids[kind]]
        check(len(refs) == 1, f"{kind}: dedicated MG has unexpected reverse-reference count {len(refs)}")
        dedicated_reverse_refs[kind] = {
            "count": 1,
            "record_index": refs[0][0],
            "name": refs[0][1]["name"],
            "id": refs[0][1]["id"].hex(),
        }

    # Strong reversibility proof: restore only the two Nornir model links,
    # remove the two dedicated MG groups, restore the two accounting payloads,
    # and require the exact failed candidate byte-for-byte.
    normalized_records = copy.deepcopy(reparsed)
    removal: set[int] = set()
    for kind in ("map", "hud"):
        n_idx, _ = unique_payload(normalized_records, NORNIR_MODEL[kind])
        start, end = group_bounds(logical, normalized_records, n_idx)
        hits = [normalized_records[i] for i in range(start, end + 1)
                if normalized_records[i]["kind"] == 1 and not normalized_records[i]["data"]
                and normalized_records[i]["name"].lower() == NORNIR_MG[kind].lower()
                and normalized_records[i]["id"] == new_ids[kind]]
        check(len(hits) == 1, f"{kind}: normalization cannot find dedicated Nornir model link")
        set_name(hits[0], STOCK_MG[kind])
        hits[0]["id"] = clone_info[kind]["source_id"]

        mg_idx, _ = unique_payload(normalized_records, NORNIR_MG[kind])
        mg_start, mg_end = group_bounds(logical, normalized_records, mg_idx)
        removal.update(range(mg_start, mg_end + 1))

    stripped = [copy.deepcopy(row) for i, row in enumerate(normalized_records) if i not in removal]
    payloads = logical.payload_records(stripped)
    payloads[0]["data"] = bytearray(accounting["source_heap_data"])
    payloads[1]["data"] = bytearray(accounting["source_root_data"])
    normalized = logical.serialize_wad(stripped)
    check(normalized == failed_raw,
          "isolated MG candidate does not normalize to the exact failed candidate byte-for-byte")

    return candidate, {
        "schema": 1,
        "result": RESULT,
        "source_failed_candidate_sha256": sha(failed_raw),
        "frozen_raven_wad_sha256": sha(raven_raw),
        "candidate_sha256": sha(candidate),
        "source_bytes": len(failed_raw),
        "candidate_bytes": len(candidate),
        "dedicated_model_groups": source_group_snapshots,
        "donor_proofs": donor_proofs,
        "retargets": retargets,
        "dedicated_reverse_references": dedicated_reverse_refs,
        "accounting": {k: v for k, v in accounting.items() if not k.startswith("source_")},
        "proofs": {
            "stock_mg_groups_unchanged_from_raven_baseline": True,
            "nornir_map_model_uses_dedicated_mg_only": True,
            "nornir_hud_model_uses_dedicated_mg_only": True,
            "raven_map_model_still_uses_stock_mg": True,
            "raven_hud_model_still_uses_stock_mg": True,
            "dedicated_mg_reverse_refs_exactly_one_each": True,
            "candidate_reparse_roundtrip_exact": True,
            "isolated_candidate_normalizes_to_failed_candidate_byte_exactly": True,
            "failed_candidate_previously_normalized_to_frozen_raven_wad": True,
            "shared_stock_model_group_isolation_gap_closed": True,
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--failed-candidate-wad", type=Path, required=True)
    ap.add_argument("--raven-wad", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    for path in (args.failed_candidate_wad, args.raven_wad):
        check(path.is_file(), f"missing input: {path}")
    check(not args.output.exists(), f"output already exists: {args.output}")
    check(not args.report.exists(), f"report already exists: {args.report}")

    out, report = build(args.failed_candidate_wad.read_bytes(), args.raven_wad.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(args.output.read_bytes() == out, "offline candidate write verification failed")

    print(RESULT)
    print(f"  failed source: {report['source_failed_candidate_sha256']}")
    print(f"  isolated WAD:  {report['candidate_sha256']}")
    for kind in ("map", "hud"):
        row = report["dedicated_model_groups"][kind]
        print(f"  {kind} MG: {row['new_name']} id={row['new_id']} rows={row['group_physical_rows']} payloads={row['group_payload_rows']}")
    print(f"  accounting payload delta: {report['accounting']['payload_delta']}")
    print("  Nornir map/HUD models use dedicated MGs only: true")
    print("  Raven models still use stock MGs: true")
    print("  isolated candidate normalizes to failed candidate byte-exactly: true")
    print("  failed candidate previously normalized to frozen Raven WAD: true")
    print("  shared stock model-group isolation gap closed: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
