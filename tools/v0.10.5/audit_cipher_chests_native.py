#!/usr/bin/env python3
"""Read-only cipher item/quest scan; never promotes shared script to chest ID."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import raven_catalogue as raven

GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
QUESTS = ("Quest_SonLanguage_Muspelheim", "Quest_SonLanguage_Niflheim")
ITEMS = (b"MuspelheimCipherPiece", b"NiflheimCipherPiece")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def scan(game_root: Path = GAME) -> dict:
    dc = game_root / "exec/dc/pc_le"
    quest_path = dc / "quests.dcb"
    resource_path = dc / "resources.dcb"
    quests = raven.Dcb(quest_path)
    targets = {}
    for item in quests.array(quests.root("QUESTS_PERM_DATA", 0x159), 8):
        record = quests.pointer(item)
        name = quests.string(record)
        if name in QUESTS:
            targets[name] = {"target": quests.unpack("<I", record + 0x30)[0],
                             "record_offset": f"0x{quests.file_base + record:X}"}
    require(set(targets) == set(QUESTS) and
            all(row["target"] == 4 for row in targets.values()),
            "native language quest targets differ")
    resource_raw = resource_path.read_bytes()
    require(all(item in resource_raw for item in ITEMS),
            "cipher item names absent from native resources")
    matched_wads = []
    direct_records = []
    for path in sorted((game_root / "exec/wad/pc_le").glob("*.wad"),
                       key=lambda item: item.name.lower()):
        raw = path.read_bytes()
        if not any(item in raw for item in ITEMS):
            continue
        digest = hashlib.sha256(raw).hexdigest()
        records = raven.parse_wad(raw)
        shared_scripts = [record for record in records if record["kind"] == 36 and
                          record["name"] == "interact_chest_standard" and
                          all(item in record["data"] for item in ITEMS)]
        other_scripts = [record for record in records if record["kind"] == 36 and
                         record not in shared_scripts and
                         any(item in record["data"] for item in ITEMS)]
        for record in records:
            if record["kind"] != 36 and any(item in record["data"] for item in ITEMS):
                direct_records.append({"wad": path.name, "wad_sha256": digest,
                                       "record_name": record["name"],
                                       "record_id": record["id"].hex(),
                                       "record_offset": f"0x{record['offset']:X}"})
        matched_wads.append({"wad": path.name, "sha256": digest,
                             "shared_standard_chest_script_count": len(shared_scripts),
                             "script_offsets": [f"0x{r['offset']:X}" for r in shared_scripts],
                             "other_script_records": [{"name": r["name"],
                                                       "offset": f"0x{r['offset']:X}"}
                                                      for r in other_scripts]})
    shared_count = sum(row["shared_standard_chest_script_count"] for row in matched_wads)
    require(len(matched_wads) >= 100 and not direct_records and shared_count >= 100 and
            all(row["shared_standard_chest_script_count"] <= 1 for row in matched_wads),
            f"cipher literal source scan differs: wads={len(matched_wads)} "
            f"direct={direct_records[:8]} shared={shared_count}")
    return {
        "schema": 1, "status": "BLOCKED_FAIL_CLOSED",
        "runtime_generation_allowed": False,
        "game_launched": False, "game_files_written": False,
        "quest_dcb_sha256": hashlib.sha256(quest_path.read_bytes()).hexdigest(),
        "resource_dcb_sha256": hashlib.sha256(resource_raw).hexdigest(),
        "native_language_quest_targets": dict(sorted(targets.items())),
        "native_language_piece_target_sum": 8,
        "external_guide_chest_count_user_baseline": 13,
        "matching_wad_count": len(matched_wads),
        "shared_standard_chest_script_wad_count": shared_count,
        "matching_wads": matched_wads,
        "non_script_cipher_literal_records": direct_records,
        "shared_script_only_literal_evidence": True,
        "physical_cipher_chest_census_proven": False,
        "physical_cipher_chest_rows": [],
        "per_object_cipher_reward_identity_proven": False,
        "persistent_unloaded_state_proven": False,
        "native_marker_coverage_proven": False,
        "blockers": [
            "cipher item and quest names occur in a shared standard chest script, not an exact placed chest override in this scan",
            "two native language quests each require four pieces; guide count 13 chests is a distinct physical claim",
            "per-chest reward table, completion state, and stock marker coverage remain unproved",
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
    print(f"CIPHER_STATIC_GATE BLOCKED language_target=8 matched_wads={report['matching_wad_count']} physical_census=unproved generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
