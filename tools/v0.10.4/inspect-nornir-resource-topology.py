#!/usr/bin/env python3
"""Read-only Nornir resource-topology gate from the frozen Raven production state.

This does not build or install a Nornir WAD/DCB. It proves the exact donor
resource groups, case-folded hashes, DCB export space and GOPool slots that the
next offline builder is allowed to use. No game file, save, progression value,
or marker state is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = "NORNIR_RESOURCE_TOPOLOGY_VERIFIED"
EXPECTED_BRANCH = "codex/v104-raven-production"

EXPECTED = {
    "r_ui_wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "wad_r_ui": "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d",
    "wad_r_perm": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
}
EXPECTED_NATIVE = {
    "result": "NORNIR_NATIVE_DATA_OFFLINE_GATE_PASSED",
    "marker_id": "381B067F07254A25",
    "mapmaster": "dc51308e22807b3404ea951ae52f7daf28e8dbb442b09e59bfa98b4d243fc8fa",
    "mapcoords": "b870adccf66baf0d71dd1c0774d12e5ca503415da1e9270f82d0b77c0f11cd7f",
    "compassgraph": "8477f6332436959ce06b0c7e84a4871a7ff947421f9e858589e360e2e7c0d45e",
}

RAVEN = {
    "map_root": "gomapiconcompletionistraven",
    "map_proto": "goProtoMapIconCompletionistRaven",
    "map_model": "MDL_completionistraven",
    "material": "MAT_AE4AD85BB993F040",
    "diffuse": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
    "emissive": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
    "hud_root": "gocompletionistravenhud",
    "hud_proto": "goProtoCompletionistRavenHUD",
    "hud_model": "MDL_completionistravenhud",
    "map_go": "goMapIconCompletionistRaven",
    "hud_go": "goCompletionistRavenHUD",
    "class": "CompletionistRaven",
    "inworld": "COMPASS_INWORLD_COMPLETIONIST_RAVEN",
}

PLANNED = {
    "map_go": "goMapIconCompletionistNornirChest",
    "map_root": "gomapiconcompletionistnornirchest",
    "map_proto": "goProtoMapIconCompletionistNornirChest",
    "map_model": "MDL_completionistnornirchest",
    "material": "MAT_completionistnornirchest",
    "diffuse_base": "TX_completionist_nornir_chest_map_diffuse",
    "emissive_base": "TX_completionist_nornir_chest_map_emissive",
    "hud_go": "goCompletionistNornirChestHUD",
    "hud_root": "gocompletionistnornirchesthud",
    "hud_proto": "goProtoCompletionistNornirChestHUD",
    "hud_model": "MDL_completionistnornirchesthud",
    "class": "CompletionistNornirChest",
    "inworld": "COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST",
}

EXPECTED_HASHES = {
    "map_go": 0xE14C66C3B90633E0,
    "hud_go": 0x7DDC11175EBD1E94,
    "class": 0x8D5A770E0C4272CE,
    "inworld": 0x32BBE7E267644D93,
    "diffuse_file": 0x0A43AEB29D6F80DA,
    "emissive_file": 0x58012A499511A0BB,
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(filename: str, module_name: str):
    path = HERE / filename
    check(path.is_file(), f"missing helper: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    check(spec is not None and spec.loader is not None, f"could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def unique_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(i, row) for i, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def group_snapshot(logical, records: list[dict], name: str) -> dict:
    index, payload = unique_payload(records, name)
    start = payload["parent"]
    check(start is not None and records[start]["kind"] == 2, f"{name}: missing group start")
    end = logical.matching_group_end(records, start)
    rows = records[start:end + 1]
    payload_rows = [r for r in rows if r["kind"] == 1 and r["data"]]
    return {
        "name": name,
        "payload_record_index": index,
        "group_start": start,
        "group_end": end,
        "physical_records": len(rows),
        "payload_records": len(payload_rows),
        "payload_type_keys": [f"0x{struct.unpack_from('<I', r['data'], 0)[0]:X}" if len(r["data"]) >= 4 else None
                              for r in payload_rows],
        "resource_id": payload["id"].hex(),
        "payload_sha256": hashlib.sha256(bytes(payload["data"])).hexdigest(),
    }


def texture_snapshot(records: list[dict], name: str) -> dict:
    gpu = [r for r in records if r["name"].lower() == name.lower()
           and r["kind"] == 0x1D and r["data"]]
    definition = [r for r in records if r["name"].lower() == name.lower()
                  and r["kind"] == 1 and r["flags"] == 0x8021 and r["data"]]
    check(len(gpu) == len(definition) == 1, f"{name}: expected one GPU and one definition")
    check(len(definition[0]["data"]) == 356, f"{name}: texture definition size changed")
    return {
        "name": name,
        "gpu_bytes": len(gpu[0]["data"]),
        "gpu_id": gpu[0]["id"].hex(),
        "gpu_sha256": hashlib.sha256(bytes(gpu[0]["data"])).hexdigest(),
        "definition_bytes": len(definition[0]["data"]),
        "definition_id": definition[0]["id"].hex(),
        "definition_sha256": hashlib.sha256(bytes(definition[0]["data"])).hexdigest(),
    }


def parse_gopool(verifier, path: Path) -> list[dict]:
    raw = path.read_bytes()
    chunks = verifier.parse_chunks(raw)
    dc = verifier.one(chunks, 12)
    data = raw[dc["start"]:dc["end"]]
    count = struct.unpack_from("<I", data, 8)[0]
    check(count == 257, f"expected frozen 257-row GOPool, found {count}")
    rows = []
    for index in range(count):
        off = verifier.GOP_BASE + index * verifier.GOP_ROW
        uid, capacity = struct.unpack_from("<QH", data, off)
        rows.append({"index": index, "uid": uid, "capacity": capacity})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--repo-root", type=Path, default=REPO)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    output = (args.output.resolve() if args.output else
              repo / "build/v0.10.4-nornir-resource-topology/nornir-resource-topology.json")
    check(not output.is_relative_to(game), "report must stay outside game directory")

    logical = load_module("build-raven-ui-logical-clone.py", "nornir_topology_logical")
    verifier = load_module("verify-raven-production-state.py", "nornir_topology_verify")

    live = {
        "r_ui_wad": game / "exec/wad/pc_le/r_ui.wad",
        "wad_r_ui": game / "exec/dc/pc_le/wad_r_ui.dcb",
        "wad_r_perm": game / "exec/dc/pc_le/wad_r_perm.dcb",
    }
    before = {key: sha256(path) for key, path in live.items()}
    for key, expected in EXPECTED.items():
        check(before[key] == expected, f"{key} is not frozen Raven production state: {before[key]}")

    # Reuse the strict production parsers as an independent structural gate.
    perm_verified = verifier.verify_perm(live["wad_r_perm"])
    pool_verified = verifier.verify_ui_pool(live["wad_r_ui"])

    native_archive = repo / "archive/field-logs/completionist-v104-nornir-native-data-offline-success.json"
    native = json.loads(native_archive.read_text(encoding="utf-8-sig"))
    check(native.get("result") == EXPECTED_NATIVE["result"], "Nornir native-data success archive missing/wrong")
    check(native["marker"]["id"] == EXPECTED_NATIVE["marker_id"], "Nornir marker ID changed")
    check(native["hashes"]["candidate_mapmaster_sha256"] == EXPECTED_NATIVE["mapmaster"], "Nornir mapmaster candidate changed")
    check(native["hashes"]["candidate_mapcoords_sha256"] == EXPECTED_NATIVE["mapcoords"], "Nornir mapcoords candidate changed")
    check(native["hashes"]["candidate_compassgraph_sha256"] == EXPECTED_NATIVE["compassgraph"], "Nornir graph candidate changed")

    wad_raw = live["r_ui_wad"].read_bytes()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "production r_ui.wad no longer round-trips exactly")

    donor_groups = {
        "map_model": group_snapshot(logical, records, RAVEN["map_model"]),
        "map_proto": group_snapshot(logical, records, RAVEN["map_proto"]),
        "map_root": group_snapshot(logical, records, RAVEN["map_root"]),
        "hud_model": group_snapshot(logical, records, RAVEN["hud_model"]),
        "hud_proto": group_snapshot(logical, records, RAVEN["hud_proto"]),
        "hud_root": group_snapshot(logical, records, RAVEN["hud_root"]),
        "material": group_snapshot(logical, records, RAVEN["material"]),
    }
    textures = {
        "diffuse": texture_snapshot(records, RAVEN["diffuse"]),
        "emissive": texture_snapshot(records, RAVEN["emissive"]),
    }
    check(textures["diffuse"]["gpu_bytes"] == 9228, "Raven diffuse resident size changed")
    check(textures["emissive"]["gpu_bytes"] == 4620, "Raven emissive resident size changed")

    # Derive the exact case-folded hashes using the game's observed name loop.
    hashes = {
        "map_go": name_hash(PLANNED["map_go"]),
        "hud_go": name_hash(PLANNED["hud_go"]),
        "class": name_hash(PLANNED["class"]),
        "inworld": name_hash(PLANNED["inworld"]),
        "diffuse_file": name_hash(PLANNED["diffuse_base"]),
        "emissive_file": name_hash(PLANNED["emissive_base"]),
    }
    check(hashes == EXPECTED_HASHES, f"Nornir naming hash contract changed: {hashes!r}")
    planned_diffuse = f"{PLANNED['diffuse_base']}_{hashes['diffuse_file']:016X}"
    planned_emissive = f"{PLANNED['emissive_base']}_{hashes['emissive_file']:016X}"

    # New WAD names must not already exist in the proven production WAD.
    planned_wad_names = [
        PLANNED["map_root"], PLANNED["map_proto"], PLANNED["map_model"], PLANNED["material"],
        planned_diffuse, planned_emissive,
        PLANNED["hud_root"], PLANNED["hud_proto"], PLANNED["hud_model"],
    ]
    existing_names = {r["name"].lower() for r in records}
    collisions = [name for name in planned_wad_names if name.lower() in existing_names]
    check(not collisions, f"planned Nornir WAD names already exist: {collisions}")

    perm_raw = live["wad_r_perm"].read_bytes()
    perm_chunks = verifier.parse_chunks(perm_raw)
    export_chunk = verifier.one(perm_chunks, 13)
    exports = verifier.parse_exports(perm_raw[export_chunk["start"]:export_chunk["end"]])
    export_uids = {row["uid"] for row in exports}
    check(hashes["class"] not in export_uids, "planned Nornir class UID collides with existing export")
    check(hashes["inworld"] not in export_uids, "planned Nornir in-world UID collides with existing export")

    pool_rows = parse_gopool(verifier, live["wad_r_ui"])
    pool_uids = {row["uid"] for row in pool_rows}
    check(hashes["map_go"] not in pool_uids, "planned Nornir map GameObject collides in GOPool")
    check(hashes["hud_go"] not in pool_uids, "planned Nornir HUD GameObject collides in GOPool")
    check(len(pool_rows) == 257 and pool_rows[-1]["index"] == 256, "unexpected GOPool tail")

    svg = repo / "assets/icons/source/nornir_chest.svg"
    png = repo / "assets/icons/concepts/nornir_chest_concept_master.png"
    art = {
        "source_svg": str(svg),
        "source_svg_sha256": sha256(svg),
        "concept_master_png": str(png),
        "concept_master_png_sha256": sha256(png),
        "planned_diffuse": planned_diffuse,
        "planned_emissive": planned_emissive,
        "resident_contract": {
            "diffuse": "148x148, 8 mips, BC7_UNORM_SRGB, resident GPU bytes 9228",
            "emissive": "148x148, 8 mips, BC1_UNORM, resident GPU bytes 4620",
            "layout": "reuse runtime-proven Raven partial-linearization reconstruction, not naive linear DDS bytes",
        },
    }

    after = {key: sha256(path) for key, path in live.items()}
    check(after == before, "a frozen Raven production file changed during read-only topology inspection")

    report = {
        "result": RESULT,
        "ready_for_nornir_resource_builder": True,
        "frozen_raven_production": {
            "hashes": before,
            "perm_verification": perm_verified,
            "pool_verification": pool_verified,
        },
        "nornir_native_data": {
            "marker_id": EXPECTED_NATIVE["marker_id"],
            "candidate_hashes": {
                "mapmaster": EXPECTED_NATIVE["mapmaster"],
                "mapcoords": EXPECTED_NATIVE["mapcoords"],
                "compassgraph": EXPECTED_NATIVE["compassgraph"],
            },
            "gate_preserved": True,
        },
        "donor_topology": {
            "source": "runtime-proven Raven custom resources",
            "groups": donor_groups,
            "textures": textures,
            "stock_DockPoint_resources_are_not_clone_targets": True,
        },
        "planned_nornir": {
            "names": {**PLANNED, "diffuse": planned_diffuse, "emissive": planned_emissive},
            "hashes": {key: f"{value:016X}" for key, value in hashes.items()},
            "gopool_plan": {
                "current_rows": 257,
                "map_row_index": 257,
                "map_capacity": 1,
                "hud_row_index": 258,
                "hud_capacity": 2,
                "resulting_rows": 259,
            },
            "perm_plan": {
                "class_type": "0x11E",
                "class_uid": f"{hashes['class']:016X}",
                "icon_name": f"{hashes['hud_go']:016X}",
                "inworld_type": "0x129",
                "inworld_uid": f"{hashes['inworld']:016X}",
                "clone_raven_class_and_carrier_without_mutating_raven": True,
            },
            "wad_name_collisions": 0,
            "perm_export_uid_collisions": 0,
            "gopool_uid_collisions": 0,
        },
        "art": art,
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "raven_production_files_changed": False,
            "stock_DockPoint_resources_modified": False,
        },
        "next_gate": "Build the real Nornir map/HUD WAD resources, 259-row GOPool DCB, CompletionistNornirChest class plus dedicated in-world carrier, and retarget only the offline Nornir mapmaster candidate to the new map GameObject. Keep all output outside the game directory.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"map GO:       {PLANNED['map_go']} = {hashes['map_go']:016X}")
    print(f"HUD GO:       {PLANNED['hud_go']} = {hashes['hud_go']:016X}")
    print(f"class:        {PLANNED['class']} = {hashes['class']:016X}")
    print(f"in-world:     {PLANNED['inworld']} = {hashes['inworld']:016X}")
    print(f"diffuse:      {planned_diffuse}")
    print(f"emissive:     {planned_emissive}")
    print("GOPool plan:  map index 257 cap 1; HUD index 258 cap 2; count 259")
    print("Raven donor groups: verified")
    print("planned WAD/DCB/GOPool collisions: 0")
    print("real Nornir art sources: verified")
    print("game files written: false")
    print("runtime install performed: false")
    print(f"report: {output}")


if __name__ == "__main__":
    main()
