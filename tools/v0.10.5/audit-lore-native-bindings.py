#!/usr/bin/env python3
"""Recheck exact Lore object records and separate level-script clues."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import raven_catalogue as raven
import collectible_catalogue as catalogue

CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def assess(source: dict, game_root: Path = GAME) -> dict:
    rows = [row for row in source["collectibles"] if row["family"] == "lore_marker"]
    require(len(rows) == 43, "Lore physical census differs")
    by_wad = defaultdict(list)
    for row in rows:
        by_wad[row["source"]["wad"]].append(row)
    output = []
    for wad_name, wad_rows in sorted(by_wad.items()):
        raw = (game_root / "exec/wad/pc_le" / wad_name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        records = raven.parse_wad(raw)
        by_id = {record["id"].hex(): record for record in records if record["kind"] != 36}
        for row in wad_rows:
            cid = row["catalogue_id"]
            native, progress, origin = row["native"], row["progression"], row["source"]
            require(digest == origin["wad_sha256"], f"{cid}: WAD SHA differs")
            override = by_id.get(native["override_record_id"])
            require(override is not None and override["name"] == native["override_name"] and
                    override["offset"] == int(origin["override_offset"], 16),
                    f"{cid}: override locator differs")
            item = {"catalogue_id": cid, "subtype": row["subtype"], "wad": wad_name,
                    "wad_sha256": digest, "override_record_id": native["override_record_id"],
                    "override_offset": origin["override_offset"],
                    "world_position": row["marker"]["position_world"],
                    "physical_id": native["instance_guid"],
                    "state_adapter": progress["state_adapter"], "state_field": progress["field"],
                    "persistent_unloaded_state_proven": False}
            if row["subtype"] == "native_lore_marker":
                parent = progress["parent_quest"]
                require(parent and parent.encode() in override["data"] and
                        progress["parent_quest_source"] == "exact_native_object_attribute",
                        f"{cid}: direct parent absent")
                item.update(binding="direct_object_attribute", parent_quest=parent,
                            journal_ids=native["journal_ids"], script_blob_offset=None,
                            script_callback_literals_present=False,
                            journal_id_in_override=bool(native["journal_ids"]) and all(
                                journal.encode() in override["data"]
                                for journal in native["journal_ids"]))
            else:
                require(row["subtype"] == "level_script_lore_marker", f"{cid}: unknown subtype")
                require(progress["parent_quest"] is None and
                        progress["parent_quest_source"] is None,
                        f"{cid}: unproved object parent attached")
                expected = catalogue.SPECIAL_LORE.get(wad_name)
                require(expected and native["override_name"].lower() == expected[0].lower() and
                        native["journal_ids"] == [expected[1]],
                        f"{cid}: level script fixture differs")
                require(expected[2].encode() not in override["data"] and
                        expected[1].encode() not in override["data"],
                        f"{cid}: object/script separation differs")
                blobs = [record for record in records if record["kind"] == 36 and
                         record["name"].lower() == Path(wad_name).stem.lower()]
                require(len(blobs) == 1, f"{cid}: unique level Lua blob absent")
                blob = blobs[0]
                journal_at = blob["data"].find(expected[1].encode())
                quest_at = blob["data"].find(expected[2].encode())
                callback_at = blob["data"].find(b"ActivateAndIncrementQuest")
                require(journal_at >= 0 and quest_at > journal_at and
                        callback_at > journal_at and callback_at < quest_at and
                        quest_at - journal_at < 128 and
                        b"UpdateJournal" in blob["data"][max(0, journal_at-64):journal_at] and
                        expected[3].split(" ")[0].encode() in blob["data"],
                        f"{cid}: level callback evidence differs")
                item.update(binding="level_script_callback_object_link_unproved",
                            parent_quest=None, proposed_script_parent=expected[2],
                            journal_ids=native["journal_ids"],
                            script_blob_offset=f"0x{blob['offset']:X}",
                            script_callback_literals_present=True)
            output.append(item)
    output.sort(key=lambda row: row["catalogue_id"])
    require(len({row["catalogue_id"] for row in output}) == 43, "duplicate Lore ID")
    return {"schema": 1, "status": "OBJECT_BINDINGS_PARTIAL", "physical_count": 43,
            "direct_object_parent_count": sum(row["binding"] == "direct_object_attribute"
                                              for row in output),
            "level_script_context_count": sum(row["binding"] ==
                                               "level_script_callback_object_link_unproved"
                                               for row in output),
            "runtime_generation_allowed": False, "game_files_written": False,
            "rows": output}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = assess(json.loads(CATALOGUE.read_text(encoding="utf-8")))
    report["catalogue_lf_sha256"] = hashlib.sha256(CATALOGUE.read_bytes().replace(
        b"\r\n", b"\n")).hexdigest()
    target = args.output.resolve()
    require(REPO in target.parents, "output must stay in repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"LORE_NATIVE_AUDIT direct={report['direct_object_parent_count']} "
          f"script_context={report['level_script_context_count']} generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
