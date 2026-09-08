"""Decide Raven compass HUD SCP binding from the pinned current r_ui.wad.

Read-only. The stock compass peers are the authority for HUD prototype grammar.
A shared-script path is rejected unless stock HUD evidence proves it; map-icon
sharing is reported only as non-equivalent supporting evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

import compass_hud_physical_groups as hud

BASE = hud.BASE
check = hud.check
REPO = hud.REPO
PHYSICAL = hud.load_module("inspect-compass-hud-physical-groups.py")
REDUCED = REPO / "archive/field-logs/completionist-v104-compass-hud-local-subtrees.json"
OUTPUT = REPO / "archive/field-logs/completionist-v104-raven-compass-hud-scp-binding.json"

SCP_SENTINEL_ID = bytes.fromhex("baaddbbad0baaddbbaaddbbad7baaddb")
MAP_PROTO = "goProtoMapIconCompletionistRaven"
LOCAL_DECISION = "LOCAL_SCP_REQUIRED"
UNRESOLVED_DECISION = "SCP_BINDING_UNRESOLVED"
RESULT = "READ_ONLY_RAVEN_COMPASS_HUD_SCP_BINDING"


def direct_group_rows(records: list[dict], target: int) -> tuple[list[dict], list[dict]]:
    roles = hud.group_roles(records, target)
    rows = [records[item["index"]] for item in roles]
    direct = [
        {"role": item["role"], "relative_index": item["relative_index"], "row": records[item["index"]]}
        for item in roles if item["depth"] == 1
    ]
    return roles, direct


def one_payload_index(records: list[dict], name: str) -> int | None:
    hits = [i for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) <= 1, f"expected at most one payload {name!r}, found {len(hits)}")
    return hits[0] if hits else None


def broad_prototype_binding_counts(records: list[dict]) -> dict:
    local = linked = both = neither = 0
    local_samples, link_samples = [], []
    seen_groups: set[int] = set()
    for index, row in enumerate(records):
        if row["kind"] != 1 or not row["data"] or hud.first_dword(row) != 0x10001:
            continue
        start = row["parent"]
        if start is None or start in seen_groups:
            continue
        seen_groups.add(start)
        try:
            roles = hud.group_roles(records, index)
        except ValueError:
            continue
        has_local = False
        has_link = False
        local_names: list[str] = []
        link_names: list[str] = []
        for item in roles:
            if item["depth"] != 1 or item["index"] == index:
                continue
            member = records[item["index"]]
            if member["kind"] != 1 or member["id"] != SCP_SENTINEL_ID:
                continue
            if member["data"] and hud.first_dword(member) == 0x10005:
                has_local = True
                local_names.append(member["name"])
            elif not member["data"]:
                has_link = True
                link_names.append(member["name"])
        if has_local and has_link:
            both += 1
        elif has_local:
            local += 1
        elif has_link:
            linked += 1
        else:
            neither += 1
        if has_local and len(local_samples) < 12:
            local_samples.append({"prototype": row["name"], "scripts": local_names})
        if has_link and len(link_samples) < 12:
            link_samples.append({"prototype": row["name"], "scripts": link_names})
    return {
        "prototype_groups_scanned": len(seen_groups),
        "local_sentinel_payload_only": local,
        "sentinel_zero_data_link_only": linked,
        "both_local_and_link": both,
        "neither": neither,
        "local_samples": local_samples,
        "link_samples": link_samples,
    }


def inspect_records(raw: bytes, records: list[dict], physical_report: dict) -> dict:
    helper = BASE.load_helper()
    check(BASE.sha256(raw) == BASE.EXPECTED_WAD, "source WAD hash differs from pinned Raven state")
    check(helper.serialize_wad(records) == raw, "source WAD round-trip differs")
    check(physical_report.get("result") == "READ_ONLY_COMPASS_HUD_PHYSICAL_GROUPS",
          "wrong physical grammar report")

    peer_rows = {}
    peer_bodies = []
    stock_has_sentinel_link = False
    for cls in hud.PEERS:
        branch = physical_report["classes"][cls]["prototype"]
        target = int(branch["target_record_index"])
        grammar = hud.validate_hud_group(records, target, "prototype")
        script_index = grammar["start"] + 3
        script = records[script_index]
        check(script["kind"] == 1 and script["data"], f"{cls}: SCP is not a local payload")
        check(script["id"] == SCP_SENTINEL_ID, f"{cls}: SCP sentinel ID changed")
        check((script["flags"], len(script["data"]), hud.first_dword(script)) == (0x18, 96, 0x10005),
              f"{cls}: SCP payload shape changed")
        peer_bodies.append(bytes(script["data"]))
        direct_links = []
        for i in range(grammar["start"] + 1, grammar["end"]):
            row = records[i]
            if row["kind"] == 1 and not row["data"] and row["id"] == SCP_SENTINEL_ID:
                direct_links.append({"record_index": i, "name": row["name"]})
        stock_has_sentinel_link = stock_has_sentinel_link or bool(direct_links)
        peer_rows[cls] = {
            "prototype": records[target]["name"],
            "prototype_record_index": target,
            "script_record_index": script_index,
            "script_name": script["name"],
            "script_id": script["id"].hex(),
            "script_flags": f"0x{script['flags']:X}",
            "script_bytes": len(script["data"]),
            "script_first_dword": f"0x{hud.first_dword(script):X}",
            "script_payload_sha256": BASE.sha256(bytes(script["data"])),
            "local_direct_member": True,
            "zero_data_sentinel_links_in_prototype_group": direct_links,
        }

    peer_scripts_byte_identical = len(set(peer_bodies)) == 1
    check(peer_scripts_byte_identical, "stock compass peer SCP bodies no longer match")

    payload_defs = [
        (i, row) for i, row in enumerate(records)
        if row["kind"] == 1 and row["data"] and row["id"] == SCP_SENTINEL_ID
    ]
    distinct_bodies = {bytes(row["data"]) for _, row in payload_defs}
    dock_body = peer_bodies[0]
    same_body = [(i, row) for i, row in payload_defs if bytes(row["data"]) == dock_body]
    zero_links = [
        (i, row) for i, row in enumerate(records)
        if row["kind"] == 1 and not row["data"] and row["id"] == SCP_SENTINEL_ID
    ]

    map_index = one_payload_index(records, MAP_PROTO)
    map_evidence = {"present": map_index is not None}
    if map_index is not None:
        map_row = records[map_index]
        roles, direct = direct_group_rows(records, map_index)
        direct_scripts = []
        for item in direct:
            row = item["row"]
            if row["kind"] == 1 and row["id"] == SCP_SENTINEL_ID:
                direct_scripts.append({
                    "relative_index": item["relative_index"],
                    "role": item["role"],
                    "name": row["name"],
                    "has_payload": bool(row["data"]),
                    "flags": f"0x{row['flags']:X}",
                    "bytes": len(row["data"]),
                    "first_dword": f"0x{hud.first_dword(row):X}" if row["data"] else None,
                })
        node_count = struct.unpack_from("<H", map_row["data"], 0xC)[0] if len(map_row["data"]) >= 0xE else None
        map_evidence.update({
            "record_index": map_index,
            "flags": f"0x{map_row['flags']:X}",
            "bytes": len(map_row["data"]),
            "first_dword": f"0x{hud.first_dword(map_row):X}",
            "node_count_at_0x0C": node_count,
            "direct_sentinel_members": direct_scripts,
            "uses_zero_data_sentinel_links": any(not item["has_payload"] for item in direct_scripts),
            "same_two_node_topology_as_stock_compass": node_count == 2,
            "note": (
                "The working map Raven may share generic SCP definitions, but it is not stock compass-HUD "
                "precedent and its node/member topology is evaluated separately."
            ),
        })

    broad = broad_prototype_binding_counts(records)
    reasons = {
        "all_stock_compass_peers_author_direct_local_scp_payload": all(
            row["local_direct_member"] for row in peer_rows.values()
        ),
        "stock_compass_peers_keep_local_scp_even_when_body_is_identical": peer_scripts_byte_identical,
        "scp_sentinel_id_is_not_unique_definition_identity": len(payload_defs) > 1 and len(distinct_bodies) > 1,
        "stock_compass_zero_data_scp_link_precedent_absent": not stock_has_sentinel_link,
        "map_zero_data_link_precedent_is_not_stock_compass_binding_proof": True,
    }
    local_required = all(reasons.values())
    decision = LOCAL_DECISION if local_required else UNRESOLVED_DECISION

    return {
        "result": RESULT,
        "source_wad_sha256": BASE.sha256(raw),
        "source_round_trip_byte_exact": True,
        "decision": decision,
        "decision_reasons": reasons,
        "stock_compass_peers": peer_rows,
        "scp_sentinel_population": {
            "id": SCP_SENTINEL_ID.hex(),
            "payload_definitions": len(payload_defs),
            "distinct_payload_bodies": len(distinct_bodies),
            "definitions_matching_stock_compass_body": len(same_body),
            "zero_data_links": len(zero_links),
            "zero_data_link_samples": [
                {"record_index": i, "name": row["name"], "parent_record_index": row["parent"]}
                for i, row in zero_links[:12]
            ],
        },
        "broad_0x10001_prototype_sample": broad,
        "working_map_raven_prototype": map_evidence,
        "selected_topology": {
            "root_payloads": 1,
            "prototype_payloads": 2,
            "model_payloads": 1,
            "physical_records": 13,
            "payload_records": 4,
            "wad_r_ui_accounting_delta": 3,
            "local_scp_payload_preserved": decision == LOCAL_DECISION,
        },
        "ready_for_offline_four_payload_builder": decision == LOCAL_DECISION,
        "ready_for_runtime_test": False,
        "game_files_read": True,
        "game_files_written": False,
        "dcb_files_read": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "conclusion": decision,
    }


def inspect_binding(game: Path) -> tuple[Path, bytes, list[dict], dict]:
    game = game.resolve()
    source = game / "exec/wad/pc_le/r_ui.wad"
    raw = source.read_bytes()
    reduced_raw = REDUCED.read_bytes()
    records, physical_report = PHYSICAL.inspect(raw, json.loads(reduced_raw))
    report = inspect_records(raw, records, physical_report)
    report["physical_grammar_report"] = "archive/field-logs/completionist-v104-compass-hud-physical-groups.json"
    report["reduced_report"] = "archive/field-logs/completionist-v104-compass-hud-local-subtrees.json"
    check(source.read_bytes() == raw, "source WAD changed during SCP binding inspection")
    return source, raw, records, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    source, raw, _records, report = inspect_binding(args.game_root)
    output = hud.safe_output(args.output, REPO / "archive/field-logs")
    check(not output.is_relative_to(args.game_root.resolve()), "report overlaps game tree")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == raw, "source WAD changed after SCP report write")

    print(RESULT)
    print(f"  decision:             {report['decision']}")
    print("  stock HUD SCP form:   direct local payload")
    print("  live game writes:     false")
    print("  runtime test:         NOT SAFE YET")
    print(f"  report:               {output}")


if __name__ == "__main__":
    main()
