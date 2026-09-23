#!/usr/bin/env python3
"""Read-only Triptych placement and native objective audit."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import collectible_catalogue as catalogue
import raven_catalogue as raven

GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
NAMES = ("gotriptych", "gotryptich_overrideinst")  # exact peak720 spelling; excludes light burst effect


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def objective(game_root: Path) -> dict:
    path = game_root / "exec/dc/pc_le/quests.dcb"
    quests = raven.Dcb(path)
    matches = []
    for item in quests.array(quests.root("QUESTS_PERM_DATA", 0x159), 8):
        record = quests.pointer(item)
        if quests.string(record) == "Quest_Triptychs_Objective":
            matches.append({"target": quests.unpack("<I", record + 0x30)[0],
                            "record_offset": f"0x{quests.file_base + record:X}"})
    require(len(matches) == 1 and matches[0]["target"] == 11,
            "Triptych native objective differs")
    return {"path": "exec/dc/pc_le/quests.dcb",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **matches[0]}


def scan(game_root: Path = GAME) -> dict:
    quest = objective(game_root)
    root = game_root / "exec/wad/pc_le"
    scanned = []
    raw_placements = []
    for path in sorted(root.glob("*.wad"), key=lambda item: item.name.lower()):
        raw = path.read_bytes()
        if b"triptych" not in raw.lower() and b"tryptich" not in raw.lower():
            continue
        records = raven.parse_wad(raw)
        script = [record for record in records if record["kind"] == 36 and
                  record["name"] == "interact_triptych"]
        require(len(script) <= 1, f"duplicate Triptych script: {path.name}")
        script_quest = bool(script) and all(
            token in script[0]["data"] for token in
            (b"Quest_Triptychs_Objective", b"IncrementQuestProgress",
             b"OnSaveCheckpoint", b"OnRestoreCheckpoint", b"triptychCompleted"))
        if script:
            require(script_quest, f"Triptych script semantics differ: {path.name}")
        digest = hashlib.sha256(raw).hexdigest()
        found = 0
        for index, record in enumerate(records):
            name = record["name"].lower()
            if not (name.endswith("_overrideinst") and
                    (name.startswith(NAMES[0]) or name == NAMES[1])):
                continue
            final = catalogue.instance_final(records, index)
            paths = catalogue.exact_world_transforms(final, records)
            require(len(paths) == 1, f"Triptych placement branches: {path.name} {name}")
            _matrix, world, chain, _raw_chain = paths[0]
            require(len(world) == 3 and all(math.isfinite(value) for value in world),
                    f"Triptych position differs: {path.name} {name}")
            raw_placements.append({
                "wad": path.name, "wad_sha256": digest,
                "override_name": record["name"],
                "override_record_id": record["id"].hex(),
                "override_offset": f"0x{record['offset']:X}",
                "world_position": list(world), "transform_chain": chain,
                "interact_triptych_script_in_wad": bool(script),
                "quest_literal_in_script": script_quest,
                "script_record_offset": f"0x{script[0]['offset']:X}" if script else None,
            })
            found += 1
        if found:
            scanned.append({"wad": path.name, "sha256": digest,
                            "named_placement_count": found,
                            "interact_triptych_script_in_wad": bool(script)})
    raw_placements.sort(key=lambda row: (row["wad"], row["override_offset"]))
    by_id = defaultdict(list)
    for item in raw_placements:
        by_id[item["override_record_id"]].append(item)
    repeated = [items for items in by_id.values() if len(items) > 1]
    require(len(raw_placements) == 14 and len(repeated) == 1 and
            len(repeated[0]) == 2 and
            {item["wad"] for item in repeated[0]} ==
            {"stn105_chiselsite.wad", "stn905_chiselsite.wad"},
            f"Triptych duplicate ledger differs: raw={len(raw_placements)} "
            f"repeated={[(items[0]['override_record_id'], [item['wad'] for item in items]) for items in repeated]} "
            f"names={[(item['wad'], item['override_name']) for item in raw_placements]}")
    a, b = repeated[0]
    require(a["override_name"] == b["override_name"] and
            all(abs(x-y) < 1e-9 for x, y in zip(a["world_position"], b["world_position"])),
            "cross-WAD Thamur duplicate is not identical")
    placements = []
    for record_id, items in sorted(by_id.items()):
        require(len(items) <= 2, f"Triptych repeated ID ambiguous: {record_id}")
        representative = min(items, key=lambda row: row["wad"])
        placements.append({"physical_record_id": record_id,
                           "source_placements": items,
                           "world_position": representative["world_position"],
                           "quest_script_in_source_wad": any(
                               item["interact_triptych_script_in_wad"] for item in items),
                           "exact_per_object_objective_membership_proven": False,
                           "persistent_unloaded_completion_proven": False,
                           "marker_generation_ready": False})
    placements.sort(key=lambda row: row["physical_record_id"])
    require(len(placements) == 13 and
            sum(row["quest_script_in_source_wad"] for row in placements) == 11 and
            {item["wad"] for row in placements if not row["quest_script_in_source_wad"]
             for item in row["source_placements"]} ==
            {"cal170_library1.wad", "cal590_runevaultelevator.wad"},
            "Triptych named/quest script split differs")
    return {
        "schema": 1, "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "game_launched": False, "game_files_written": False,
        "native_objective": quest,
        "external_guide_count_user_baseline": 11,
        "named_raw_placement_count": len(raw_placements),
        "exact_duplicate_raw_placement_count": 1,
        "named_distinct_placement_count": len(placements),
        "quest_script_wad_placement_count": 11,
        "story_context_placement_count": 2,
        "named_placement_wads": scanned,
        "raw_placements": raw_placements,
        "distinct_placements": placements,
        "exact_per_object_objective_membership_proven": False,
        "exhaustive_physical_census_proven": False,
        "persistent_unloaded_completion_proven": False,
        "native_marker_coverage_proven": False,
        "blockers": [
            "13 distinct named Triptych placements versus native objective 11; two Tyr story-context placements lack the quest script but exclusion is not proved per object",
            "peak720 authored override spells gotryptich; it is retained rather than dropped by a name filter",
            "interact_triptych Lua has quest and checkpoint fields, but exact per-object objective linkage and unloaded state lookup remain unproved",
            "native marker coverage and custom-marker policy remain unproved",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = scan()
    out = args.output.resolve()
    require(REPO in out.parents, "output must stay in repository")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("JOTNAR_STATIC_GATE BLOCKED objective=11 named_distinct=13 quest_script_wad=11 generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
