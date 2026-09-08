"""Read pinned WAD groups. Report full grammar and three-payload gate conflict."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import compass_hud_physical_groups as hud

BASE = hud.BASE
check = hud.check
REDUCED = hud.REPO / "archive/field-logs/completionist-v104-compass-hud-local-subtrees.json"
OUTPUT = hud.REPO / "archive/field-logs/completionist-v104-compass-hud-physical-groups.json"


def describe_group(records: list[dict], target: int, role: str, definitions: dict) -> dict:
    helper = BASE.load_helper()
    result = hud.validate_hud_group(records, target, role)
    rows = []
    for item in hud.group_roles(records, target):
        row = records[item["index"]]
        parent = row["parent"]
        link = item["role"] in ("dependency_link", "nested_dependency_link")
        targets = definitions.get(row["id"], []) if link else []
        rows.append({
            "record_index": item["index"], "relative_index": item["relative_index"],
            "depth": item["depth"], "role": item["role"],
            "kind": row["kind"], "flags": f"0x{row['flags']:X}",
            "name": row["name"], "id": row["id"].hex(), "data_size": len(row["data"]),
            "first_dword": f"0x{hud.first_dword(row):X}" if row["data"] else None,
            "payload_index": row["payload_index"], "parent_record_index": parent,
            "parent_relative_index": parent - result["start"] if parent is not None else None,
            "containing_group_start": result["start"],
            "is_target_payload": item["index"] == target,
            "zero_data_dependency_link": link,
            "resolved_targets": [{"record_index": i, "name": records[i]["name"],
                                  "flags": f"0x{records[i]['flags']:X}",
                                  "data_size": len(records[i]["data"])} for i in targets],
            "payload_sha256": BASE.sha256(bytes(row["data"])) if row["data"] else None,
            "record_sha256": BASE.sha256(helper.record_bytes(row)),
        })
    result.update({"resource_role": role, "target_record_index": target, "records": rows})
    return result


def signature(rows: list[dict], payload: dict, target_id: bytes) -> dict:
    return {"inline_offsets": [i for i in range(len(payload["data"]))
                               if payload["data"][i:i + 16] == target_id],
            "local_link_relative_indices": [i for i, row in enumerate(rows)
                                             if row["kind"] == 1 and not row["data"]
                                             and row["flags"] == 0 and row["id"] == target_id]}


def inspect(raw: bytes, reduced: dict) -> tuple[list[dict], dict]:
    check(BASE.sha256(raw) == BASE.EXPECTED_WAD, "source WAD hash differs from pinned Raven state")
    helper = BASE.load_helper()
    records = helper.parse_wad(raw)
    check(helper.serialize_wad(records) == raw, "source WAD round-trip differs")
    payloads = helper.payload_records(records)
    check(len(records) == 53811 and len(payloads) == 20415, "source counts changed")
    check(reduced.get("result") == "REPORT_ONLY_COMPASS_HUD_LOCAL_SUBTREES", "wrong reduced class report")
    definitions = defaultdict(list)
    for i, row in enumerate(records):
        if row["kind"] == 1 and row["data"]:
            definitions[row["id"]].append(i)

    classes, clone_rows = {}, []
    for cls in hud.PEERS:
        check(cls in reduced["classes"], f"missing peer {cls}")
        branch = reduced["classes"][cls]
        check(len(branch["models"]) == 1, f"{cls} model count changed")
        resources = {"root": branch["root"], "prototype": branch["prototype"],
                     "model": branch["models"][0]["model"]}
        groups = {}
        for role, expected in resources.items():
            target = expected["record_index"]
            row = records[target]
            check(row["name"] == expected["name"] and row["id"].hex() == expected["id"],
                  f"{cls}/{role}: reduced report differs from pinned source")
            groups[role] = describe_group(records, target, role, definitions)
            if cls == "DockPoint":
                group = groups[role]
                clone_rows.extend(records[group["start"]:group["end"] + 1])

        root, proto, model = [records[resources[x]["record_index"]] for x in ("root", "prototype", "model")]
        check(root["data"][0xC:0x1C] == proto["id"], f"{cls}: root prototype slot changed")
        check(root["data"][0x54:0x64] == BASE.SHARED_COMPASS_ID, f"{cls}: shared compass slot changed")
        check(bytes(root["data"][0x1C:0x54]) == root["name"].encode("ascii").ljust(56, b"\0"),
              f"{cls}: root payload loader name differs from header")
        proto_rows = records[groups["prototype"]["start"]:groups["prototype"]["end"] + 1]
        model_rows = records[groups["model"]["start"]:groups["model"]["end"] + 1]
        material = branch["models"][0]["materials"][0]["material"]
        mesh = branch["models"][0]["meshes"][0]
        deps = {"prototype_to_model": signature(proto_rows, proto, model["id"]),
                "model_to_material": signature(model_rows, model, bytes.fromhex(material["id"])),
                "model_to_mesh": signature(model_rows, model, bytes.fromhex(mesh["id"]))}
        check(deps == {"prototype_to_model": {"inline_offsets": [], "local_link_relative_indices": [2]},
                       "model_to_material": {"inline_offsets": [], "local_link_relative_indices": [2]},
                       "model_to_mesh": {"inline_offsets": [], "local_link_relative_indices": [3]}},
              f"{cls}: dependency grammar differs")
        groups["dependency_encodings"] = deps
        groups["inline_fields"] = {"root_prototype_offset": "0xC", "root_shared_compass_offset": "0x54",
                                   "root_loader_name_offset": "0x1C", "root_loader_name_bytes": 56,
                                   "root_loader_name": root["name"],
                                   "prototype_self_id_offset": "0x3A8"}
        classes[cls] = groups

    for role in ("root", "prototype", "model"):
        layouts = {tuple((row["role"], row["depth"], row["kind"], row["flags"],
                          row["data_size"], row["first_dword"]) for row in branch[role]["records"])
                   for branch in classes.values()}
        check(len(layouts) == 1, f"peer {role} layouts differ")
        for relative in (0, -1):
            boundary_hashes = {branch[role]["records"][relative]["record_sha256"] for branch in classes.values()}
            check(len(boundary_hashes) == 1, f"peer {role} group boundary bytes differ")

    collisions = []
    for name, rid in [(BASE.NEW_ROOT, BASE.NEW_ROOT_ID), (BASE.NEW_PROTO, BASE.NEW_PROTO_ID),
                      (BASE.NEW_MODEL, BASE.NEW_MODEL_ID)]:
        name_hits = [i for i, r in enumerate(records) if r["name"].lower() == name.lower()]
        id_hits = [i for i, r in enumerate(records) if r["id"] == rid]
        check(not name_hits and not id_hits, f"new identity collision: {name}")
        collisions.append({"name": name, "id": rid.hex(), "name_collisions": name_hits, "id_collisions": id_hits})

    type_rows = helper.read_type_table(payloads[1]["data"])
    counts = {row["key"]: row["count"] for row in type_rows}
    for key, amount in ((0x10001, 1725), (0x20001, 2073), (0x10005, 2600)):
        population = sum(hud.first_dword(row) == key for row in payloads)
        check(counts[key] == population == amount, f"type {key:#x} population differs")
    required = hud.clone_accounting(clone_rows, counts)
    script_index = classes["DockPoint"]["prototype"]["records"][3]["record_index"]
    script = records[script_index]
    script_defs = [records[i] for i in definitions[script["id"]]]
    script_links = [{"record_index": i, "name": r["name"], "parent": r["parent"]}
                    for i, r in enumerate(records) if r["kind"] == 1 and not r["data"] and r["id"] == script["id"]]
    check(len({branch["prototype"]["records"][3]["payload_sha256"] for branch in classes.values()}) == 1,
          "peer auxiliary script bytes differ")
    report = {
        "result": "READ_ONLY_COMPASS_HUD_PHYSICAL_GROUPS",
        "source_wad_sha256": BASE.sha256(raw), "source_round_trip_byte_exact": True,
        "source_physical_records": len(records), "source_payload_records": len(payloads),
        "peer_classes": list(hud.PEERS), "peer_comparison_passed": True,
        "classes": classes, "reserved_identities": collisions,
        "required_clone": required,
        "accounting_if_complete_groups_cloned": {
            "heap_and_root_total": {"before": 16802, "after": 16802 + required["accounting_delta"]},
            "rows": [{"key": f"0x{key:X}", "before": counts[key], "after": counts[key] + 1}
                     for key in (0x10001, 0x20001, 0x10005)],
            "payload_records_after": len(payloads) + required["payload_records"],
            "physical_records_after": len(records) + required["physical_records"],
            "counts_are_inferred_for_complete_clone_not_a_built_candidate": True,
        },
        "script_reuse_evidence": {
            "source_record_index": script_index, "name": script["name"], "id": script["id"].hex(),
            "same_id_payload_definitions": len(script_defs),
            "distinct_payload_contents_for_id": len({bytes(r["data"]) for r in script_defs}),
            "same_id_and_same_payload_contents": sum(r["data"] == script["data"] for r in script_defs),
            "zero_data_links_with_same_id": script_links,
            "peer_scripts_byte_identical": True,
            "id_only_resolution_unique": len(script_defs) == 1,
            "hud_script_conversion_proven": False,
            "note": "Only three inserted Raven map links use this script ID. Map precedent does not prove HUD local script sharing.",
        },
        "conclusion": "THREE_PAYLOAD_DESIGN_CONFLICTS_WITH_COMPLETE_SOURCE_GROUPS",
        "game_files_read": True, "game_files_written": False, "dcb_files_read": False,
        "save_state_written": False, "progression_state_written": False, "marker_state_written": False,
        "ready_for_runtime_test": False,
    }
    check(helper.serialize_wad(records) == raw, "inspection changed parsed source records")
    return records, report


def read_inspection(game: Path) -> tuple[Path, bytes, list[dict], dict]:
    source = game.resolve() / "exec/wad/pc_le/r_ui.wad"
    raw, reduced_raw = source.read_bytes(), REDUCED.read_bytes()
    records, report = inspect(raw, json.loads(reduced_raw))
    report["reduced_report"] = str(REDUCED.relative_to(hud.REPO)).replace("\\", "/")
    report["reduced_report_sha256_lf"] = BASE.sha256(reduced_raw.replace(b"\r\n", b"\n"))
    check(source.read_bytes() == raw, "source WAD changed during inspection")
    return source, raw, records, report


def write_report(path: Path, report: dict, game: Path) -> None:
    path = hud.safe_output(path, hud.REPO / "archive/field-logs")
    check(path.suffix.lower() == ".json", "report must be JSON")
    check(not path.is_relative_to(game.resolve()), "report overlaps game tree")
    check(path != REDUCED.resolve(), "report overlaps reduced input")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source, raw, _, report = read_inspection(args.game_root)
    write_report(args.output, report, args.game_root)
    check(source.read_bytes() == raw, "source WAD changed after report write")
    print(report["result"])
    print("Peer groups: 5 classes match. Full clone: +13 records, +4 payloads, +3 accounting.")
    print("Three-payload gate: BLOCKED. Game writes: false. Runtime test: NOT SAFE YET.")
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
