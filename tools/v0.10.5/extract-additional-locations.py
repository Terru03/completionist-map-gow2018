#!/usr/bin/env python3
"""Extract fixed chest, shrine, rift, scroll and treasure placements, read-only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import collectible_catalogue as catalogue
import raven_catalogue as raven

GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
OUTPUT = ROOT / "config/collectibles/v0.10.5/additional-locations.json"
PARENTS = {"gochest_common_parent": "wooden_chest", "gocoffin_parent": "coffin",
           "gochest_dispell_parent": "cipher_chest"}
EXTRA_REGIONS = {
    "xpl150": ("Midgard", "HTTK"), "xpl160": ("Midgard", "HTTK"),
    "xpl450": ("Midgard", "HuldraMine01"),
    "xpl475": ("Midgard", "HuldraMine01"),
    "xpl325": ("Midgard", "HuldraStronghold"), "xpl350": ("Midgard", "HuldraStronghold"),
    "xpl600": ("Midgard", "MasonTrail"), "xpl625": ("Midgard", "MasonTrail"),
    "xpl875": ("Midgard", "ForestDungeon"),
    "xpl930": ("Midgard", "BeachRuins"), "nid": ("Niflheim", "NiflheimMain"),
}
TREASURE = re.compile(r"^Quest_TreasureMap[A-Za-z0-9_]*$")


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def map_regions(master):
    result = {}
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        realm_id = master.unpack("<Q", realm)[0]
        for region in master.array(realm + 0x30, 0x68):
            result[(realm_id, master.unpack("<Q", region)[0])] = region
    return result


def resolve_region(path, raw, summaries, regions):
    region, evidence = catalogue.choose_region(path, raw, summaries, None)
    if region is None:
        for prefix, (realm, name) in EXTRA_REGIONS.items():
            if path.stem.startswith(prefix):
                region = {"realm": realm, "realm_id": f"{raven.name_hash(realm):016X}",
                          "region": name, "region_id": f"{raven.name_hash(name):016X}"}
                evidence = "native_level_namespace"
                break
    need(region is not None, f"unresolved map realm/region for {path.name}")
    region = dict(region)
    key = (int(region["realm_id"], 16), int(region["region_id"], 16))
    if key not in regions:
        candidates = [rid for realm, rid in regions if realm == key[0]]
        need(len(candidates) == 1, f"ambiguous map region for {path.name}: {region}")
        region["region_id"] = f"{candidates[0]:016X}"
        region["region"] = region["realm"] + " map region"
        evidence = "sole_native_map_region_in_realm"
    return {key: region[key] for key in ("realm", "realm_id", "region", "region_id")}, evidence


def candidates(records):
    scripts = {row["name"] for row in records if row["kind"] == 36}
    for index, record in enumerate(records):
        name = record["name"].lower()
        if record["kind"] == 1 and record["flags"] == 0x3D and record["size"] == 164:
            if name in PARENTS and "interact_chest_standard" in scripts:
                yield PARENTS[name], record, record, "exact_chest_prefab_parent", None
            elif name == "golootpocketgeo" and "interact_loot_pocketrift" in scripts:
                yield "realm_tear", record, record, "exact_rift_prefab_parent", None
        if not name.endswith("_overrideinst"):
            continue
        values = catalogue.strings(record["data"])
        quests = [value for value in values if TREASURE.fullmatch(value)]
        if quests:
            need(len(set(quests)) == 1, f"ambiguous treasure quest on {name}")
            quest = quests[0]
            family = "treasure_map" if quest.endswith("_Parent") else "treasure_dig"
            expected = "sonlanguagepickup" if family == "treasure_map" else "interact_loot_dirtdig"
            need(expected in scripts, f"treasure placement lacks gameplay script: {name}")
            yield family, catalogue.instance_final(records, index), record, "exact_object_treasure_quest", quest
        elif "treasuremapinteract" in name and "sonlanguagepickup" in scripts:
            journal = [value for value in values if value.endswith("_Lore")]
            if journal:
                need(len(set(journal)) == 1, f"ambiguous scroll journal ID: {name}")
                yield "lore_scroll", catalogue.instance_final(records, index), record, "exact_object_journal_id", journal[0]
        elif (name.startswith("gotriptych_") or name in {
                "gotriptych_overrideinst", "gotriptychbasic_overrideinst", "gotryptich_overrideinst"}):
            yield "jotnar_shrine", catalogue.instance_final(records, index), record, "named_triptych_placement", None


def scan(game=GAME):
    master = raven.Dcb(game / "exec/dc/pc_le/mapmaster.dcb")
    regions = map_regions(master)
    summaries, _, _ = catalogue.collectible_summary_index(game / "exec/dc/pc_le")
    rows, excluded, physical = {}, [], {}
    native_rifts = {f"gocombatrift_0{i}": f"Nif_400_RealmTear0{i}" for i in (1, 2, 3)}
    files = sorted((game / "exec/wad/pc_le").glob("*.wad"))
    for number, path in enumerate(files):
        raw = path.read_bytes()
        if not any(needle in raw for needle in
                   (b"interact_chest_standard", b"interact_triptych", b"triptych_tyr",
                    b"interact_loot_pocketrift", b"Quest_TreasureMap", b"sonlanguagepickup")):
            continue
        records = raven.parse_wad(raw)
        digest = hashlib.sha256(raw).hexdigest()
        for family, final, evidence_record, proof, identity_label in candidates(records):
            if family in PARENTS.values() and path.stem.startswith(("nid", "msp")):
                excluded.append({"wad": path.name, "family": family,
                                 "reason": "procedural_or_repeatable_chest_region"})
                continue
            for matrix, world, chain, raw_chain in catalogue.exact_world_transforms(final, records):
                need(all(math.isfinite(value) for value in world), f"nonfinite transform: {path.name}")
                if raw_chain[-1]["data"][0x54:0x64] != bytes(16):
                    excluded.append({"wad": path.name, "family": family,
                                     "record_id": final["id"].hex(),
                                     "reason": "unplaced_prefab_with_no_world_root"})
                    continue
                names = {row["name"] for row in chain}
                if family in PARENTS.values() and "godirtpatch" in names:
                    excluded.append({"wad": path.name, "family": family,
                                     "record_id": final["id"].hex(),
                                     "reason": "buried_loot_reuses_chest_prefab"})
                    continue
                if family == "realm_tear" and "goqueencombatrift" in names:
                    excluded.append({"wad": path.name, "family": family,
                                     "reason": "native_valkyrie_queen_encounter"})
                    continue
                # Some resources embed a second copy of their own prefab.
                # Canonicalize to its outermost occurrence so both scans describe
                # one physical chest, retaining its ID even when it is placed
                # directly under a level root.
                anchor = max(i for i, part in enumerate(chain) if part["name"] == final["name"])
                placement_path = chain[anchor:] if proof.endswith("prefab_parent") else chain
                need(bool(placement_path), f"unplaced prefab: {path.name} {final['name']}")
                placement = placement_path[min(1, len(placement_path) - 1)] if proof.endswith("prefab_parent") else placement_path[0]
                identity = "/".join(part["record_id"] for part in placement_path)
                key = family + "_" + hashlib.sha256(identity.encode("ascii")).hexdigest()[:32]
                region, region_evidence = resolve_region(path, raw, summaries, regions)
                source = {"wad": path.name, "wad_sha256": digest,
                          "record_id": evidence_record["id"].hex(),
                          "record_offset": f"0x{evidence_record['offset']:X}",
                          "proof": proof, "identity_label": identity_label,
                          "transform_chain": chain, "root_complete": True}
                physical_key = (family, placement["record_id"], region["realm_id"])
                prior = next((row for row in physical.get(physical_key, [])
                              if all(abs(a-b) < 1e-6 for a,b in
                                     zip(row["marker"]["position_world"], world))), None)
                if prior is not None:
                    prior["sources"].append(source)
                    continue
                need(key not in rows, f"same full native path has conflicting transforms: {key}")
                native_name = next((name for ancestor, name in native_rifts.items()
                                    if family == "realm_tear" and path.name == "nid400_center.wad" and
                                    ancestor in names), None)
                custom_name, uid = catalogue.marker_identity(family, identity)
                if native_name:
                    custom_name, uid = native_name, f"{raven.name_hash(native_name):016X}"
                rows[key] = {
                    "catalogue_id": key, "family": family, **region,
                    "region_source": region_evidence,
                    "marker": {"name": custom_name, "uid": uid,
                               "map_resource": "goMapIconSecondaryQuest", "compass_class": "SIDE",
                               "position_world": list(world), "coordinate_wad": "WAD_" + path.stem,
                               "existing_native": native_name is not None},
                    "placement": placement, "sources": [source],
                    "completion_state": "untracked_location_only",
                }
                physical.setdefault(physical_key, []).append(rows[key])
        if number % 80 == 0:
            print(f"scanned={number}/{len(files)} additional_locations={len(rows)}", flush=True)
    result = sorted(rows.values(), key=lambda row: row["catalogue_id"])
    maps = {s["identity_label"][:-7] for row in result if row["family"] == "treasure_map" for s in row["sources"]}
    digs = {s["identity_label"] for row in result if row["family"] == "treasure_dig" for s in row["sources"]}
    need(maps == digs and len(maps) == 12, "treasure map/dig quest pairing differs")
    need(len({row["marker"]["uid"] for row in result}) == len(result), "additional marker UID collision")
    return {"schema": 1, "mode": "all_known_locations", "source_authority": "native_game_placements",
            "collectibles": result, "counts": dict(sorted(Counter(row["family"] for row in result).items())),
            "existing_native_markers": sum(row["marker"]["existing_native"] for row in result),
            "excluded": excluded, "treasure_pairs": sorted(maps)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = scan(args.game)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], sort_keys=True))
    print(f"existing_native_markers={result['existing_native_markers']}")


if __name__ == "__main__":
    main()
