#!/usr/bin/env python3
"""Read-only PocketRift quest/carrier audit; no encounter census inferred."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import collectible_catalogue as catalogue
import raven_catalogue as raven

GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
PARENT = re.compile(rb"RegionSummary_[A-Za-z0-9_]*PocketRift_Parent")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def scan(game_root: Path = GAME) -> dict:
    root = game_root / "exec/wad/pc_le"
    dc = game_root / "exec/dc/pc_le"
    quest = dc / "quests.dcb"
    targets, _ = catalogue.quest_targets(dc)
    rift_targets = {name: value for name, value in targets.items()
                    if PARENT.fullmatch(name.encode())}
    require(len(rift_targets) == 10 and sum(rift_targets.values()) == 19,
            "PocketRift native Summary targets differ")
    wads = []
    carriers = []
    marker_calls = []
    for path in sorted(root.glob("*.wad"), key=lambda item: item.name.lower()):
        raw = path.read_bytes()
        if b"pocketrift" not in raw.lower():
            continue
        records = raven.parse_wad(raw)
        digest = hashlib.sha256(raw).hexdigest()
        matched = 0
        for index, record in enumerate(records):
            if record["name"].lower().endswith("_overrideinst"):
                parents = sorted(set(x.decode() for x in PARENT.findall(record["data"])))
                if not parents:
                    continue
                require(len(parents) == 1 and parents[0] in rift_targets,
                        f"ambiguous/unknown PocketRift parent: {path.name} {record['name']}")
                final = catalogue.instance_final(records, index)
                paths = catalogue.exact_world_transforms(final, records)
                require(len(paths) == 1, f"multiple carrier transforms: {path.name} {record['name']}")
                _matrix, world, chain, _raw_chain = paths[0]
                carriers.append({
                    "wad": path.name, "wad_sha256": digest,
                    "override_name": record["name"],
                    "override_record_id": record["id"].hex(),
                    "override_offset": f"0x{record['offset']:X}",
                    "parent_summary": parents[0],
                    "world_position": list(world),
                    "transform_chain": chain,
                    "role": "placed_parent_callback_carrier_not_proven_encounter_entity",
                })
                matched += 1
            if record["kind"] == 36 and b"SetMarkerState" in record["data"]:
                names = sorted(set(s.decode() for s in re.findall(
                    rb"Nif_400_RealmTear[0-9]+", record["data"])))
                if names:
                    marker_calls.append({"wad": path.name, "wad_sha256": digest,
                                         "script_name": record["name"],
                                         "script_offset": f"0x{record['offset']:X}",
                                         "marker_names": names,
                                         "semantics": "native_marker_state_calls_present_coverage_unproved"})
        wads.append({"wad": path.name, "sha256": digest,
                     "parent_callback_carrier_count": matched})
    carriers.sort(key=lambda row: (row["wad"], row["override_offset"]))
    counts = Counter(row["parent_summary"] for row in carriers)
    require(len(wads) >= 20 and len(carriers) == 14 and len(marker_calls) >= 1,
            "PocketRift scan census differs")
    unlocated = {name: target - counts[name] for name, target in rift_targets.items()
                 if target != counts[name]}
    require(all(value > 0 for value in unlocated.values()) and
            sum(unlocated.values()) == 5,
            "PocketRift carrier/target gap differs")
    return {
        "schema": 1, "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "game_launched": False, "game_files_written": False,
        "quest_dcb": "exec/dc/pc_le/quests.dcb",
        "quest_dcb_sha256": hashlib.sha256(quest.read_bytes()).hexdigest(),
        "native_summary_targets": dict(sorted(rift_targets.items())),
        "native_summary_target_sum": 19,
        "external_guide_count_user_baseline": 18,
        "external_normal_completion_subset_user_baseline": 11,
        "matched_wad_count": len(wads), "matched_wads": wads,
        "direct_parent_callback_carrier_count": len(carriers),
        "parent_callback_carriers": carriers,
        "unlocated_target_slots_by_summary": dict(sorted(unlocated.items())),
        "native_marker_call_clues": marker_calls,
        "physical_encounter_census_proven": False,
        "physical_encounter_rows": [],
        "persistent_unloaded_state_proven": False,
        "native_marker_coverage_proven": False,
        "blockers": [
            "14 placed records carry direct PocketRift Summary parents, but callback carriers are not proved encounter entities",
            "5 native Summary target slots lack a direct parent callback carrier in this override scan",
            "native Summary target 19 and user guide 18/normal subset 11 require exact reconciliation",
            "per-encounter persistent completion state and native marker coverage are unproved",
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
    print(f"REALM_TEAR_STATIC_GATE BLOCKED targets=19 carriers={len(report['parent_callback_carriers'])} "
          f"physical_census=unproved generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
