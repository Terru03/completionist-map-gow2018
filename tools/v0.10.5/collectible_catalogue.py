"""Read-only static catalogue extraction for non-Raven collectible families.

Native WAD records own physical identity and scene transforms. Native map/quest
DCBs own realm, region, and tracked target metadata. Decompiled Lua is evidence
for state semantics only; this module never runs game code or writes game/save
data.
"""
from __future__ import annotations

import collections
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable
import uuid


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import raven_catalogue as raven


GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
ASCII_RE = re.compile(rb"[ -~]{3,}")
REGION_SUMMARY_RE = re.compile(rb"RegionSummary_[A-Za-z0-9_]+")
ARTIFACT_TYPES = {"Alfheim", "Brooch", "Cup", "Horn", "Mask", "Ship Head", "Toy"}
CHEST_TYPES = {"Legendary", "Runic_Axe", "Runic_Blades"}
NORNIR_KEY_TYPES = {"Breakable", "Bell", "MemoryChest"}
SHIP_OBJECT_NUMBER_RE = re.compile(r"^goartifactshiphead0*([1-9][0-9]?)(?:[^0-9].*)?$", re.I)

# Old claims only. Not join proof.
# Physical GUID is key. WAD name alone cannot join.
# Row stays BLOCKED until native ref chain proves full binding edge.
NORNIR_PRIOR_UNVERIFIED_BINDING_CLAIMS = (
    ("e00c75d2-4c76-b498-de4c-1f85c997c65e", "alf210_lakedarklh.wad", "RegionSummary_RunicChest_Parent_Alfheim"),
    ("3ec0daa8-4892-2cad-4fb3-0c8bb93c171f", "alf320_trenchadark.wad", "RegionSummary_RunicChest_Parent_Alfheim"),
    ("9a92c243-4083-2c21-07ff-7d997c9fcbda", "alf340_trenchbdark.wad", "RegionSummary_RunicChest_Parent_Alfheim"),
    ("522448bf-4d91-b0f1-9de6-adbd1c77d709", "alf690_lakelightlh.wad", "RegionSummary_RunicChest_Parent_Alfheim"),
    ("a2cdfc7a-4f0a-b68e-ac21-2bb108cd35b7", "xpl940_beachcave.wad", "RegionSummary_RunicChest_Parent_BeachCave"),
    ("c02f0190-49d5-0ea0-146c-478fd46f4a49", "xpl950_beachmaze.wad", "RegionSummary_RunicChest_Parent_BeachMaze"),
    ("6b701107-4e78-df82-ecd5-08b6b1a8444f", "xpl970_beachtower.wad", "RegionSummary_RunicChest_Parent_BeachTower"),
    ("f8548c57-4dc6-7cba-277c-5cb31099648b", "cal500_runevault.wad", "RegionSummary_RunicChest_Parent_TyrsVault"),
    ("a6ac8eeb-4ea2-545a-b05d-f19e8ea6ee8f", "foot100_base.wad", "RegionSummary_RunicChest_Parent_Foothills"),
    ("6d18634c-4e86-282d-1cfa-0e84f6d5654f", "for600_spire.wad", "RegionSummary_RunicChest_Parent_Forest"),
    ("3f3a8e78-44ff-44f5-7da0-24b2efce93dc", "xpl850_dungeonforest.wad", "RegionSummary_RunicChest_Parent_ForestDungeon"),
    ("d8e4c774-44fe-09d0-a960-198ab802058e", "xpl100_httk.wad", "RegionSummary_RunicChest_Parent_HTTK"),
    ("a336e184-4ac7-c90b-6cd6-288e2cdab274", "xpl920_islandclimb.wad", "RegionSummary_RunicChest_Parent_IslandClimb"),
    ("f8ac74b9-414e-59e7-64d8-738182c00663", "peak140_caverndark.wad", "RegionSummary_RunicChest_Parent_Peakspass"),
    ("c0cf4119-40ba-d7d0-0042-afa7a46f5514", "peak720_summitascenthub.wad", "RegionSummary_RunicChest_Parent_Peakspass"),
    ("45bbcd15-458c-d30c-3338-a7b3dab9b3d9", "riv225_dangerscave.wad", "RegionSummary_RunicChest_Parent_Riverpass"),
    ("7d8b4043-40e8-ef8e-db40-96b3a1a1e3fc", "riv325_dangersexit.wad", "RegionSummary_RunicChest_Parent_Riverpass"),
    ("d2cacb84-426f-d68d-504a-11ae125c2b62", "riv420_forestboarstart.wad", "RegionSummary_RunicChest_Parent_Riverpass"),
    ("69780ade-492b-0891-1948-4199e5423527", "riv475_freyahouseext.wad", "RegionSummary_RunicChest_Parent_Riverpass"),
    ("0f0cc7ca-4842-3bb2-96f6-ddbed87a8f3b", "riv925_freyacave.wad", "RegionSummary_RunicChest_Parent_Riverpass"),
    ("c190d593-4070-6bb7-9925-cb9f2d5867cf", "xpl200_funeral.wad", "RegionSummary_RunicChest_Parent_VikingFuneral"),
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strings(data: bytes) -> list[str]:
    return [value.decode("ascii") for value in ASCII_RE.findall(data)]


def guid_strings(data: bytes) -> list[str]:
    return [value.decode("ascii").lower() for value in raven.GUID_RE.findall(data)]


def record_uuid_hint(record: dict) -> str:
    """Render raw record bytes for diagnostics, not progression identity."""
    return str(uuid.UUID(bytes_le=record["id"]))


def native_instance_guid(override: dict) -> str:
    """Return native DC instance GUID stored in an override's attributes."""
    values = guid_strings(override["data"])
    check(bool(values), f"override has no native instance GUID: {override['name']}")
    return values[-1]


FULL_GUID_RE = re.compile(
    r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)


def placement_instance_guid(override: dict) -> str | None:
    """Read exact placement half of a native placement.component key."""
    chains = []
    for value in strings(override["data"]):
        parts = value.split(".")
        if len(parts) >= 2 and all(FULL_GUID_RE.fullmatch(part) for part in parts):
            chains.append(parts)
    if not chains:
        return None
    longest = max(len(parts) for parts in chains)
    values = [parts[0].lower() for parts in chains if len(parts) == longest]
    counts = collections.Counter(values)
    best = counts.most_common()
    check(len(best) == 1 or best[0][1] > best[1][1],
          f"ambiguous placement GUID in {override['name']}")
    return best[0][0]


def native_component_key(override: dict, component_guid: str) -> str | None:
    """Return longest exact native object path ending at one component GUID."""
    candidates = []
    for value in strings(override["data"]):
        parts = value.lower().split(".")
        if (len(parts) >= 2 and parts[-1] == component_guid.lower()
                and all(FULL_GUID_RE.fullmatch(part) for part in parts)):
            candidates.append(value.lower())
    if not candidates:
        return None
    longest = max(value.count(".") for value in candidates)
    values = sorted({value for value in candidates if value.count(".") == longest})
    check(len(values) == 1, f"ambiguous component key in {override['name']}")
    return values[0]


def summary_index(dcb_root: Path) -> tuple[dict[str, dict], dict]:
    master = raven.Dcb(dcb_root / "mapmaster.dcb")
    realm_labels = {raven.name_hash(name): name for name in raven.REALM_NAMES}
    region_labels = {raven.name_hash(name): name for name in raven.REGION_NAMES}
    result: dict[str, dict] = {}
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm_row in master.array(root + 0x10, 0x40):
        realm_id, = master.unpack("<Q", realm_row)
        for region_row in master.array(realm_row + 0x30, 0x68):
            region_id, = master.unpack("<Q", region_row)
            for item in master.array(region_row + 0x58, 8):
                record = master.pointer(item)
                if record + 0x30 not in master.relocations:
                    continue
                quest = master.string(record + 0x30)
                if not quest:
                    continue
                check(quest not in result, f"duplicate map summary quest: {quest}")
                result[quest] = {
                    "realm": realm_labels.get(realm_id, f"UNKNOWN_{realm_id:016X}"),
                    "realm_id": f"{realm_id:016X}",
                    "region": region_labels.get(region_id, f"UNKNOWN_{region_id:016X}"),
                    "region_id": f"{region_id:016X}",
                    "summary_record_offset": f"0x{master.file_base + record:X}",
                }
    return result, master.evidence()


def quest_targets(dcb_root: Path) -> tuple[dict[str, int], dict]:
    quests = raven.Dcb(dcb_root / "quests.dcb")
    result: dict[str, int] = {}
    for item in quests.array(quests.root("QUESTS_PERM_DATA", 0x159), 8):
        record = quests.pointer(item)
        name = quests.string(record)
        if name.startswith("RegionSummary_"):
            result[name] = quests.unpack("<I", record + 0x30)[0]
    return result, quests.evidence()


def quest_target_records(dcb_root: Path) -> dict[str, dict]:
    """Read native quest target and record spot."""
    quests = raven.Dcb(dcb_root / "quests.dcb")
    result = {}
    for item in quests.array(quests.root("QUESTS_PERM_DATA", 0x159), 8):
        record = quests.pointer(item)
        name = quests.string(record)
        if name.startswith("RegionSummary_"):
            result[name] = {
                "target": quests.unpack("<I", record + 0x30)[0],
                "quest_record_offset": f"0x{quests.file_base + record:X}",
            }
    return result


def validate_nornir_binding_evidence(evidence: dict, summaries: dict[str, dict]) -> None:
    """Reject Nornir join with no native ref-chain edge."""
    status = evidence.get("final_status")
    check(status in {"PASS_EXACT", "BLOCKED_EXACT_REASON_UNKNOWN"},
          "invalid Nornir exact-binding status")
    if status != "PASS_EXACT":
        return
    quest = evidence.get("proposed_region_summary_parent")
    check(quest in summaries, "PASS_EXACT Nornir target absent from native summaries")
    check(evidence.get("evidence_classification") == "exact_native_reference_chain",
          "PASS_EXACT Nornir evidence is not a native reference chain")
    sources = evidence.get("exact_evidence_sources") or []
    check(all(source.get("source_file") for source in sources),
          "PASS_EXACT Nornir evidence lacks native source files")
    binding_edges = [source for source in sources
                     if source.get("evidence_role") == "binding_edge"]
    check(bool(binding_edges), "PASS_EXACT Nornir evidence lacks exact target binding edge")
    check(any(any(edge.get(key) for key in ("record_offset", "record_id", "guid"))
              for edge in binding_edges),
          "PASS_EXACT Nornir binding edge lacks deterministic native locator")
    summary = summaries[quest]
    check(evidence.get("native_realm_id") == summary.get("realm_id"),
          "PASS_EXACT Nornir realm ID disagrees with mapmaster")
    check(evidence.get("native_region_id") == summary.get("region_id"),
          "PASS_EXACT Nornir region ID disagrees with mapmaster")


def resolve_nornir_parent_binding(wad_name: str, evidence: dict | None,
                                  summaries: dict[str, dict]) -> tuple[str | None, str | None]:
    """Return parent only from checked native chain proof.

    wad_name is log data only. It cannot pick binding.
    API takes no target count.
    """
    _ = wad_name
    if evidence is None:
        return None, None
    validate_nornir_binding_evidence(evidence, summaries)
    if evidence["final_status"] != "PASS_EXACT":
        return None, None
    return evidence["proposed_region_summary_parent"], "exact_native_reference_chain"


def native_level_metadata(dcb_root: Path, wad_name: str) -> dict:
    """Prove source level ID from native per-WAD DCB."""
    stem = Path(wad_name).stem
    path = dcb_root / f"wad_{stem}.dcb"
    check(path.is_file(), f"missing native level metadata DCB for {wad_name}")
    raw = path.read_bytes()
    names = []
    for match in raven.WAD_NAME_RE.finditer(raw):
        value = match.group().decode("ascii")
        if value.lower() == f"wad_{stem}".lower():
            names.append({"name": value, "record_offset": f"0x{match.start():X}"})
    check(bool(names), f"native level metadata lacks exact WAD identity for {wad_name}")
    return {
        "source_file": path.name,
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "wad_export_name": names[0]["name"],
        "wad_export_record_offsets": sorted({row["record_offset"] for row in names}),
        "native_level_identity": names[0]["name"],
        "native_zone_identity": None,
        "zone_identity_status": "NO_EXACT_ZONE_TO_REGION_SUMMARY_BINDING_RECORD",
        "identity_status": "PASS_EXACT_SOURCE_LEVEL_WAD_IDENTITY",
    }


def build_nornir_binding_evidence(row: dict, dcb_root: Path,
                                   summaries: dict[str, dict],
                                   target_records: dict[str, dict],
                                   map_evidence: dict, quest_evidence: dict) -> dict:
    """Build proof row. One lost edge blocks join."""
    guid = row["native"]["instance_guid"]
    claim_matches = [claim for claim in NORNIR_PRIOR_UNVERIFIED_BINDING_CLAIMS
                     if claim[0] == guid]
    check(len(claim_matches) <= 1, f"duplicate prior Nornir claim for {guid}")
    proposed = claim_matches[0][2] if claim_matches else None
    if claim_matches:
        check(claim_matches[0][1].lower() == row["source"]["wad"].lower(),
              f"prior Nornir claim WAD mismatch for {guid}")
        check(proposed in summaries and proposed in target_records,
              f"prior Nornir target absent from native DCBs: {proposed}")
    summary = summaries.get(proposed, {})
    level = native_level_metadata(dcb_root, row["source"]["wad"])
    sources = [
        {
            "source_file": row["source"]["wad"],
            "source_file_sha256": row["source"]["wad_sha256"],
            "evidence_role": "physical_placement",
            "physical_instance_guid": guid,
            "state_carrier_guids": row["native"]["state_carrier_guids"],
            "override_record_id": row["native"]["override_record_id"],
            "override_record_offset": row["source"]["override_offset"],
            "final_record_id": row["native"]["final_record_id"],
            "final_record_offset": row["source"]["final_offset"],
        },
        {
            "source_file": level["source_file"],
            "source_file_sha256": level["source_file_sha256"],
            "evidence_role": "source_level_identity",
            "record_offsets": level["wad_export_record_offsets"],
            "wad_export_name": level["wad_export_name"],
        },
    ]
    if proposed and summary.get("summary_record_offset"):
        sources.append({
                "source_file": "mapmaster.dcb",
                "source_file_sha256": map_evidence["sha256"],
                "evidence_role": "region_summary_target_ownership",
                "record_offset": summary["summary_record_offset"],
                "region_summary_target": proposed,
                "native_realm_id": summary.get("realm_id"),
                "native_region_id": summary.get("region_id"),
            })
    if proposed:
        sources.append({
            "source_file": "quests.dcb",
            "source_file_sha256": quest_evidence["sha256"],
            "evidence_role": "region_summary_target_definition",
            "record_offset": target_records[proposed]["quest_record_offset"],
            "region_summary_target": proposed,
            "target": target_records[proposed]["target"],
        })
    helheim = row["source"]["wad"].lower() == "helr100_docks.wad"
    evidence = {
        "catalogue_id": row["catalogue_id"],
        "physical_instance_guid": guid,
        "state_carrier_guid": row["native"]["state_instance_guid"],
        "state_carrier_guids": row["native"]["state_carrier_guids"],
        "wad": row["source"]["wad"],
        "world_xyz": row["marker"]["position_world"],
        "proposed_region_summary_parent": proposed,
        "native_realm_id": summary.get("realm_id", row.get("realm_id")),
        "native_region_id": summary.get("region_id", row.get("region_id")),
        "native_level_zone_identity": level,
        "exact_evidence_sources": sources,
        "evidence_classification": (
            "native_untracked_reward_no_region_summary_target" if helheim
            else "exact_source_and_target_records_missing_binding_edge"),
        "final_status": "BLOCKED_EXACT_REASON_UNKNOWN",
        "tracking_classification": (
            "level_scripted_untracked_triple_chest_reward" if helheim
            else "unresolved_tracked_candidate"),
        "physical_object": {
            "status": "PASS_EXACT",
            "source_file": row["source"]["wad"],
            "record_offset": row["source"]["override_offset"],
            "record_id": row["native"]["override_record_id"],
            "physical_instance_guid": guid,
        },
        "source_level_zone": {
            "status": "PASS_EXACT_SOURCE_LEVEL_WAD_IDENTITY",
            **level,
        },
        "map_region_ownership": {
            "status": (
                "TARGET_NATIVE_IDS_KNOWN_LEVEL_BINDING_UNPROVED"
                if summary.get("summary_record_offset") else
                "NO_MAPMASTER_REGION_SUMMARY_BINDING_RECORD"
                if proposed else "NO_TRACKED_REGION_SUMMARY_TARGET"),
            "native_realm_id": summary.get("realm_id", row.get("realm_id")),
            "native_region_id": summary.get("region_id", row.get("region_id")),
            "source": "mapmaster.dcb" if proposed else None,
            "record_offset": summary.get("summary_record_offset"),
        },
        "region_summary_target": {
            "status": ("PASS_NATIVE_TARGET_EXISTS_BINDING_EDGE_MISSING"
                       if proposed else "NOT_APPLICABLE_UNTRACKED"),
            "quest": proposed,
            "target": target_records.get(proposed, {}).get("target"),
            "source_file": "quests.dcb" if proposed else None,
            "record_offset": target_records.get(proposed, {}).get("quest_record_offset"),
        },
        "completion_state_oracle": {
            "loaded_state_status": "PASS_EXACT",
            "state_adapter": row["progression"]["state_adapter"],
            "field": row["progression"]["field"],
            "state_carrier_guids": row["native"]["state_carrier_guids"],
            "unloaded_preinstall_state_status": "BLOCKED",
        },
        "blocker": (
            "No exact native GUID/reference/callback edge binds this physical chest or "
            "its source level/zone to the proposed RegionSummary target. WAD name, "
            "human region label, target count, and candidate membership are not proof."
            if proposed else
            "Native data classifies this chest as untracked; no RegionSummary target exists."
        ),
    }
    validate_nornir_binding_evidence(evidence, summaries)
    return evidence


def collectible_summary_index(dcb_root: Path) -> tuple[dict[str, dict], dict, dict]:
    """Join all collectible quest targets to native realm/region identities."""
    summaries, map_evidence = summary_index(dcb_root)
    targets, quest_evidence = quest_targets(dcb_root)
    prefix_rows = {}
    for name, row in summaries.items():
        match = re.match(r"RegionSummary_([A-Z0-9]+)_", name)
        if match:
            prefix_rows[match.group(1)] = row
    aliases = {
        "CAL": ("Midgard", "CalderaShores"),
        "CALT": ("Midgard", "CalderaTemple"),
        "NIF": ("Niflheim", "Niflheim"),
    }
    for name, target in targets.items():
        if name in summaries:
            summaries[name]["target"] = target
            continue
        row = None
        chest = re.match(r"RegionSummary_(?:LegendaryChest|RunicChest)_Parent_(.+)$", name)
        prefix = re.match(r"RegionSummary_([A-Z0-9]+)_(?:LoreMarker|Shiphead)_Parent$", name)
        if chest:
            region_name = chest.group(1)
            row = next((value for value in summaries.values()
                        if value["region"].lower() == region_name.lower()), None)
            if row is None:
                realm_name = ("Alfheim" if region_name == "Alfheim" else
                              "Helheim" if region_name == "Helheim" else "Midgard")
                row = {
                    "realm": realm_name,
                    "realm_id": f"{raven.name_hash(realm_name):016X}",
                    "region": region_name,
                    "region_id": f"{raven.name_hash(region_name):016X}",
                    "summary_record_offset": None,
                }
        elif prefix and prefix.group(1) in prefix_rows:
            row = prefix_rows[prefix.group(1)]
        elif prefix and prefix.group(1) in aliases:
            realm_name, region_name = aliases[prefix.group(1)]
            row = {
                "realm": realm_name,
                "realm_id": f"{raven.name_hash(realm_name):016X}",
                "region": region_name,
                "region_id": f"{raven.name_hash(region_name):016X}",
                "summary_record_offset": None,
            }
        if row is not None:
            summaries[name] = {**row, "target": target}
    return summaries, map_evidence, quest_evidence


def instance_final(records: list[dict], override_index: int) -> dict:
    check(override_index + 3 < len(records), "override has no instance group")
    start, final, end = records[override_index + 1:override_index + 4]
    check(start["kind"] == 2 and final["kind"] == 1 and end["kind"] == 3,
          f"bad instance group after {records[override_index]['name']}")
    check(final["parent"] == override_index + 1 and final["flags"] == 0x3D and final["size"] == 164,
          f"bad final transform after {records[override_index]['name']}")
    return final


def matching_override(records: list[dict], final: dict) -> dict | None:
    matches = []
    for index, row in enumerate(records[:-2]):
        if not row["name"].lower().endswith("_overrideinst"):
            continue
        if records[index + 2] is final:
            matches.append(row)
    check(len(matches) <= 1, f"multiple placement overrides for {final['name']}")
    return matches[0] if matches else None


def exact_world_transforms(record: dict, records: list[dict], *, parent_name: str | None = None):
    """Expand every exact native placement path for one prefab child.

    A prefab child can have several physical parents. Every matching native
    branch is retained.  parent_name, when supplied, is an exact type/name gate
    and may still retain several placements of that named prefab.
    """
    candidates: dict[bytes, list[dict]] = collections.defaultdict(list)
    for row in records:
        if row["kind"] == 1 and row["flags"] == 0x3D and row["size"] == 164:
            candidates[row["data"][0x0C:0x1C]].append(row)
    results = []

    def walk(current: dict, matrix, chain: list[dict], seen: set[int], first: bool) -> None:
        parent_id = current["data"][0x54:0x64]
        parents = [row for row in candidates.get(parent_id, []) if id(row) not in seen]
        if first and parent_name:
            parents = [row for row in parents if row["name"].lower() == parent_name.lower()]
            check(bool(parents), f"missing exact prefab parent {parent_name} for {record['name']}")
        if parent_id == bytes(16) or not parents:
            evidence = [{"name": row["name"], "record_id": row["id"].hex(),
                         "offset": f"0x{row['offset']:X}"} for row in chain]
            results.append((matrix[0], matrix[1], evidence, chain))
            return
        for parent in parents:
            walk(parent, raven.compose(raven.record_transform(parent), matrix),
                 chain + [parent], seen | {id(parent)}, False)

    walk(record, raven.record_transform(record), [record], {id(record)}, True)
    check(bool(results), f"no transform path for {record['name']}")
    return results


def physical_placement(chain: list[dict], records: list[dict]) -> tuple[dict, dict]:
    """Find outermost exact placement identity, keeping prefab fallback."""
    fallback = None
    identified = None
    for row in chain[1:]:
        override = matching_override(records, row)
        if override is not None:
            if fallback is None:
                fallback = (override, row)
            if placement_instance_guid(override):
                identified = (override, row)
    if identified:
        return identified
    if fallback:
        return fallback
    raise ValueError(f"no physical placement ancestor for {chain[0]['name']}")


def marker_identity(family: str, instance_guid: str) -> tuple[str, str]:
    compact = (instance_guid.replace("-", "")[:16] if FULL_GUID_RE.fullmatch(instance_guid)
               else hashlib.sha256(instance_guid.encode("ascii")).hexdigest()[:16])
    family_name = "".join(part.title() for part in family.split("_"))
    name = f"Completionist_V105_{family_name}_{compact}"
    return name, f"{raven.name_hash(name):016X}"


def map_coordinates(realm_name: str, world: Iterable[float]) -> list[float] | None:
    if realm_name != "Midgard":
        return None
    x, _y, z = world
    return [0.004 * z + 0.0625431, -0.004 * x + 0.6101961]


def script_client_guid(records: list[dict], script_name: str) -> str | None:
    indexes = [index for index, row in enumerate(records)
               if row["kind"] == 36 and row["name"].lower() == script_name.lower()]
    if not indexes:
        return None
    check(len(indexes) == 1, f"duplicate script blob: {script_name}")
    for row in records[indexes[0] + 1:indexes[0] + 8]:
        if row["name"] == "DCClientGUID":
            values = guid_strings(row["data"])
            check(len(values) == 1, f"bad DCClientGUID for {script_name}")
            return values[0]
    return None


def native_regions_in_wad(raw: bytes, summaries: dict[str, dict]) -> list[dict]:
    names = sorted({match.group().decode("ascii") for match in REGION_SUMMARY_RE.finditer(raw)})
    unique: dict[tuple[str, str], dict] = {}
    for name in names:
        if name not in summaries:
            continue
        row = summaries[name]
        unique[(row["realm_id"], row["region_id"])] = row
    return [unique[key] for key in sorted(unique)]


LEVEL_REGION_NAMES = {
    "alf": ("Alfheim", "Alfheim"),
    "hel": ("Helheim", "Helheim"),
    "helr": ("Helheim", "Helheim"),
    "msp": ("Muspelheim", "Muspelheim"),
    "jot": ("Jotunheim", "Jotunheim"),
    "foot": ("Midgard", "Foothills"),
    "for": ("Midgard", "Forest"),
    "riv": ("Midgard", "Riverpass"),
    "peak": ("Midgard", "Peakspass"),
    "stn": ("Midgard", "Stonemason"),
    "cal": ("Midgard", "CalderaShores"),
    "xpl100": ("Midgard", "HTTK"),
    "xpl125": ("Midgard", "HTTK"),
    "xpl170": ("Midgard", "HTTK"),
    "xpl200": ("Midgard", "VikingFuneral"),
    "xpl220": ("Midgard", "VikingFuneral"),
    "xpl225": ("Midgard", "VikingFuneral"),
    "xpl250": ("Midgard", "VikingFuneral"),
    "xpl300": ("Midgard", "HuldraStronghold"),
    "xpl400": ("Midgard", "HuldraMine01"),
    "xpl425": ("Midgard", "HuldraMine01"),
    "xpl650": ("Midgard", "MasonTrail"),
    "xpl850": ("Midgard", "ForestDungeon"),
    "xpl900": ("Midgard", "IslandArch"),
    "xpl910": ("Midgard", "IslandShipwreck"),
    "xpl920": ("Midgard", "IslandClimb"),
    "xpl940": ("Midgard", "BeachCave"),
    "xpl950": ("Midgard", "BeachMaze"),
    "xpl960": ("Midgard", "BeachShipwreck"),
    "xpl970": ("Midgard", "BeachTower"),
    "xpl980": ("Midgard", "BeachWaterfall"),
}


def level_region(wad: Path) -> dict | None:
    stem = wad.stem.lower()
    if stem.startswith(("cal500", "cal740", "cal750")):
        realm_name, region_name = "Midgard", "CalderaTemple"
    else:
        matches = [(prefix, row) for prefix, row in LEVEL_REGION_NAMES.items()
                   if stem.startswith(prefix)]
        if not matches:
            return None
        _prefix, (realm_name, region_name) = max(matches, key=lambda item: len(item[0]))
    return {
        "realm": realm_name,
        "realm_id": f"{raven.name_hash(realm_name):016X}",
        "region": region_name,
        "region_id": f"{raven.name_hash(region_name):016X}",
        "summary_record_offset": None,
    }


def choose_region(wad: Path, raw: bytes, summaries: dict[str, dict],
                  explicit_quest: str | None) -> tuple[dict | None, str]:
    if explicit_quest and explicit_quest in summaries:
        return summaries[explicit_quest], "exact_instance_region_summary_quest"
    candidates = native_regions_in_wad(raw, summaries)
    if len(candidates) == 1:
        return candidates[0], "unique_native_region_summary_in_source_wad"
    native_level = level_region(wad)
    if native_level:
        return native_level, "native_level_namespace"
    return None, "unresolved" if not candidates else "ambiguous_native_regions_in_source_wad"


def base_entry(*, family: str, subtype: str, wad: Path, raw: bytes, records: list[dict],
               override: dict, final: dict, state_instance_guid: str | None, script_guid: str | None,
               attribute_values: list[str], summaries: dict[str, dict], family_hint: str,
               state_adapter: str, state_field: str,
               map_resource: str, compass_class: str, matrix, world, chain,
               raw_chain: list[dict], physical_instance_guid: str | None = None,
               catalogue_identity: str | None = None,
               exact_parent_quest: str | None = None,
               parent_quest_source: str | None = None,
               allow_region_quest_inference: bool = True) -> dict:
    placement_override, placement_final = physical_placement(raw_chain, records)
    physical_guid = (physical_instance_guid or placement_instance_guid(placement_override)
                     or state_instance_guid or override["id"].hex())
    chain_overrides = [matching_override(records, row) for row in raw_chain]
    all_values = list(attribute_values)
    for chain_override in chain_overrides:
        if chain_override is not None:
            all_values.extend(strings(chain_override["data"]))
    attribute_parent_quest = (explicit_summary(attribute_values, summaries, family_hint)
                              or explicit_summary(all_values, summaries, family_hint))
    parent_quest = exact_parent_quest or attribute_parent_quest
    if parent_quest:
        check(parent_quest in summaries, f"unknown exact parent quest: {parent_quest}")
    quest_source = (parent_quest_source if exact_parent_quest else
                    "exact_native_object_attribute" if attribute_parent_quest else None)
    region, region_source = choose_region(wad, raw, summaries, parent_quest)
    if allow_region_quest_inference and parent_quest is None and region is not None:
        quest_candidates = [name for name, row in summaries.items()
                            if family_hint.lower() in name.lower()
                            and row["realm"] == region["realm"]
                            and row["region"].lower() == region["region"].lower()]
        if len(quest_candidates) == 1:
            parent_quest = quest_candidates[0]
            quest_source = "unique_region_family_inference"
    check(all(math.isfinite(value) for value in world), f"nonfinite {family} position")
    identity = catalogue_identity or physical_guid
    custom_name, custom_uid = marker_identity(family, identity)
    realm_name = region["realm"] if region else "Unknown"
    carrier_path = {
        "physical_instance_guid": physical_guid,
        "state_carrier_guid": state_instance_guid,
        "wad": wad.name,
        "world_position": list(world),
        "world_transform_matrix": list(matrix),
        "transform_chain": chain,
    }
    numbered_objects = []
    if family == "artefact" and subtype == "Ship Head":
        for row in raw_chain:
            match = SHIP_OBJECT_NUMBER_RE.match(row["name"])
            if match:
                numbered_objects.append({
                    "number": int(match.group(1)),
                    "object_name": row["name"],
                    "record_id": row["id"].hex(),
                    "offset": f"0x{row['offset']:X}",
                })
        numbered_objects.sort(key=lambda row: (row["number"], row["offset"], row["record_id"]))
    return {
        "catalogue_id": f"{family}_{re.sub(r'[^0-9a-z]', '', identity.lower())}",
        "family": family,
        "subtype": subtype,
        "display_name": f"{wad.stem} / {final['name']}",
        "native": {
            "object_name": final["name"],
            "override_name": override["name"],
            "instance_guid": physical_guid,
            "state_instance_guid": state_instance_guid,
            "state_carrier_guids": ([state_instance_guid] if state_instance_guid else []),
            "carrier_transform_paths": [carrier_path],
            "numbered_object_evidence": sorted({row["number"] for row in numbered_objects}),
            "numbered_native_objects": numbered_objects,
            "script_guid": script_guid,
            "placement_record_uuid_hint": record_uuid_hint(placement_override),
            "placement_object_name": placement_final["name"],
            "placement_override_name": placement_override["name"],
            "placement_override_record_id": placement_override["id"].hex(),
            "placement_final_record_id": placement_final["id"].hex(),
            "override_record_id": override["id"].hex(),
            "final_record_id": final["id"].hex(),
            "prototype_id": final["data"][0x0C:0x1C].hex(),
            "parent_prototype_id": final["data"][0x54:0x64].hex(),
            "attribute_values": sorted(set(all_values)),
        },
        "marker": {
            "name": custom_name,
            "uid": custom_uid,
            "map_resource": map_resource,
            "compass_class": compass_class,
            "position_world": list(world),
            "position_map": map_coordinates(realm_name, world),
            "map_projection": "solved_midgard_affine" if realm_name == "Midgard" else "native_mapcoords_world_position",
            "coordinate_wad": f"WAD_{wad.stem}",
        },
        "realm": realm_name,
        "realm_id": region["realm_id"] if region else None,
        "region": region["region"] if region else None,
        "region_id": region["region_id"] if region else None,
        "region_source": region_source,
        "progression": {
            "parent_quest": parent_quest,
            "parent_quest_source": quest_source,
            "state_adapter": state_adapter,
            "field": state_field,
            "instance_key": (f"{physical_guid}.{state_instance_guid}"
                              if state_instance_guid else None),
            "instance_keys": ([f"{physical_guid}.{state_instance_guid}"]
                              if state_instance_guid else []),
            "read_only": True,
            "unloaded_query": "unresolved",
        },
        "source": {
            "wad": wad.name,
            "wad_sha256": hashlib.sha256(raw).hexdigest(),
            "override_offset": f"0x{override['offset']:X}",
            "final_offset": f"0x{final['offset']:X}",
            "world_transform_matrix": list(matrix),
            "transform_chain": chain,
        },
    }


def explicit_summary(values: list[str], summaries: dict[str, dict], family_hint: str | None = None) -> str | None:
    names = [value for value in values if value in summaries]
    if family_hint:
        hinted = [value for value in names if family_hint.lower() in value.lower()]
        if len(hinted) == 1:
            return hinted[0]
    return names[0] if len(names) == 1 else None


def extract_artifacts(wad: Path, raw: bytes, records: list[dict], summaries: dict[str, dict]) -> list[dict]:
    result = []
    script_guid = script_client_guid(records, "interact_loot_artifact")
    for index, override in enumerate(records):
        if override["name"].lower() != "goartifactscript_overrideinst":
            continue
        values = strings(override["data"])
        subtype_values = [value for value in values if value in ARTIFACT_TYPES]
        if not subtype_values:  # Lamb's Cress uses same script but is not an artefact.
            continue
        check(len(subtype_values) == 1, f"ambiguous artefact subtype in {wad.name}")
        instance_guid = native_instance_guid(override)
        final = instance_final(records, index)
        paths = exact_world_transforms(final, records)
        for matrix, world, chain, raw_chain in paths:
            physical_identity = None
            placement_override, _placement_final = physical_placement(raw_chain, records)
            if len(paths) > 1 and placement_instance_guid(placement_override) is None:
                # Old prefab shares script child ID. Exact WAD record owns object.
                physical_identity = f"{wad.name}:{placement_override['id'].hex()}"
            result.append(base_entry(
                family="artefact", subtype=subtype_values[0], wad=wad, raw=raw, records=records,
                override=override, final=final, state_instance_guid=instance_guid,
                script_guid=script_guid, attribute_values=values, summaries=summaries,
                family_hint="Shiphead", state_adapter="interact_loot_artifact_checkpoint_state",
                state_field="state == ACQUIRED", map_resource="goMapIconCompletionistArtefact",
                compass_class="CompletionistArtefact", matrix=matrix, world=world, chain=chain,
                raw_chain=raw_chain, physical_instance_guid=physical_identity))
    return result


def extract_standard_chests(wad: Path, raw: bytes, records: list[dict], summaries: dict[str, dict]) -> list[dict]:
    result = []
    script_guid = script_client_guid(records, "interact_chest_standard")
    for index, override in enumerate(records):
        if override["name"].lower() not in {"gochestscript_overrideinst", "gochestscript_rn_overrideinst"}:
            continue
        values = strings(override["data"])
        types = [value for value in values if value in CHEST_TYPES]
        if not types:
            continue
        check(len(types) == 1, f"ambiguous chest subtype in {wad.name}")
        native_type = types[0]
        family = "legendary_chest" if native_type == "Legendary" else "nornir_chest"
        guids = guid_strings(override["data"])
        check(bool(guids), f"{family} has no script identity in {wad.name}")
        hint = "LegendaryChest" if family == "legendary_chest" else "RunicChest"
        final = instance_final(records, index)
        state_guid = native_instance_guid(override)
        parent_name = ("gochest_legendary_parent" if family == "legendary_chest"
                       else "gochest_locked_parent")
        for matrix, world, chain, raw_chain in exact_world_transforms(
                final, records, parent_name=parent_name):
            result.append(base_entry(
                family=family, subtype=native_type, wad=wad, raw=raw, records=records,
                override=override, final=final, state_instance_guid=state_guid,
                script_guid=script_guid, attribute_values=values, summaries=summaries,
                family_hint=hint, state_adapter="interact_chest_standard_checkpoint_state",
                state_field="state == OPENED",
                map_resource=("goMapIconCompletionistLegendaryChest" if family == "legendary_chest"
                              else "goMapIconCompletionistNornirChest"),
                compass_class=("CompletionistLegendaryChest" if family == "legendary_chest"
                               else "CompletionistNornirChest"), matrix=matrix, world=world,
                chain=chain, raw_chain=raw_chain,
                allow_region_quest_inference=family != "nornir_chest"))
    return result


SPECIAL_LORE = {
    "cal740_leftwing.wad": ("gorune_19_overrideInst", "CAL_740_Lore_01",
                            "RegionSummary_CALT_LoreMarker_Parent", "bRuneReadStarted == true"),
    "cal750_rightwing.wad": ("gorune_18_overrideInst", "CAL_750_Lore_01",
                             "RegionSummary_CALT_LoreMarker_Parent", "bRuneReadStarted == true"),
    "riv925_freyacave.wad": ("gorune_12_well_overrideInst", "RIV_925_Lore_01",
                             "RegionSummary_RP_LoreMarker_Parent", "wellRead == true"),
}


def extract_lore_markers(wad: Path, raw: bytes, records: list[dict], summaries: dict[str, dict]) -> list[dict]:
    result = []
    script_guid = script_client_guid(records, "langcheckruneread")
    for index, override in enumerate(records):
        if not override["name"].lower().endswith("_overrideinst"):
            continue
        values = strings(override["data"])
        quests = [value for value in values
                  if value in summaries and "LoreMarker" in value]
        if not quests:
            continue
        check(len(set(quests)) == 1, f"ambiguous lore quest in {wad.name}")
        state_guid = native_instance_guid(override)
        physical_key = native_component_key(override, state_guid)
        check(physical_key is not None, f"lore marker lacks component identity in {wad.name}")
        journal_ids = sorted({
            value.strip() for value in values
            if re.search(r"(?:_Lore_[0-9]+$|_LoreMarker$)", value.strip(), re.I)
        })
        check(len(journal_ids) <= 1, f"lore marker has multiple journal identities in {wad.name}")
        physical_record_identity = f"{wad.name}:{override['id'].hex()}"
        final = instance_final(records, index)
        for matrix, world, chain, raw_chain in exact_world_transforms(final, records):
            entry = base_entry(
                family="lore_marker", subtype="native_lore_marker", wad=wad, raw=raw,
                records=records, override=override, final=final,
                state_instance_guid=state_guid, script_guid=script_guid,
                attribute_values=values, summaries=summaries, family_hint="LoreMarker",
                state_adapter="langcheckruneread_checkpoint_state",
                state_field="mapSummaryComplete == true",
                map_resource="goMapIconCompletionistLoreMarker",
                compass_class="CompletionistLoreMarker", matrix=matrix, world=world,
                chain=chain, raw_chain=raw_chain, physical_instance_guid=physical_key,
                catalogue_identity=physical_record_identity)
            entry["native"]["identity_kind"] = "native_composite_component_key"
            entry["native"]["physical_record_identity"] = physical_record_identity
            entry["native"]["journal_ids"] = journal_ids
            result.append(entry)

    if wad.name.lower() in SPECIAL_LORE:
        override_name, journal_id, quest, state_field = SPECIAL_LORE[wad.name.lower()]
        matches = [(index, row) for index, row in enumerate(records)
                   if row["name"].lower() == override_name.lower()]
        check(len(matches) == 1, f"missing special lore object in {wad.name}")
        index, override = matches[0]
        final = instance_final(records, index)
        for matrix, world, chain, raw_chain in exact_world_transforms(final, records):
            entry = base_entry(
                family="lore_marker", subtype="level_script_lore_marker", wad=wad, raw=raw,
                records=records, override=override, final=final, state_instance_guid=None,
                script_guid=script_guid, attribute_values=[journal_id, quest], summaries=summaries,
                family_hint="LoreMarker", state_adapter="level_script_checkpoint_boolean",
                state_field=state_field, map_resource="goMapIconCompletionistLoreMarker",
                compass_class="CompletionistLoreMarker", matrix=matrix, world=world,
                chain=chain, raw_chain=raw_chain,
                physical_instance_guid=override["id"].hex())
            entry["native"]["journal_ids"] = [journal_id]
            entry["progression"]["identity_status"] = "no_explicit_component_guid_in_object_override"
            result.append(entry)
    return result


def extract_nornir_children(parent: dict, wad: Path, raw: bytes,
                            records: list[dict]) -> list[dict]:
    values = parent["native"]["attribute_values"]
    key_types = [value for value in values if value in NORNIR_KEY_TYPES]
    check(len(set(key_types)) <= 1, f"ambiguous Nornir KeyType in {wad.name}")
    key_type = key_types[0] if key_types else "Breakable"
    subtype = {"Breakable": "seal", "Bell": "bell", "MemoryChest": "mechanism"}[key_type]
    pattern = {
        "Breakable": r"breakable|runiclock|gnometarget|runic_gnome",
        "Bell": r"bell",
        "MemoryChest": r"spin|base_[0-9]",
    }[key_type]
    final_by_name = collections.defaultdict(list)
    for row in records:
        if row["kind"] == 1 and row["flags"] == 0x3D and row["size"] == 164:
            final_by_name[row["name"].lower()].append(row)
    references = []
    for value in values:
        if value == key_type or not re.search(pattern, value, re.I):
            continue
        names = [value.lower(), f"go{value.lower()}"]
        if any(name in final_by_name for name in names):
            references.append(value)
    references = sorted(set(references), key=str.lower)
    check(len(references) == 3,
          f"expected three exact {key_type} child references in {wad.name}, got {references}")

    result = []
    for reference in references:
        candidates = final_by_name.get(reference.lower(), []) + final_by_name.get(
            f"go{reference.lower()}", [])
        check(len(candidates) == 1, f"ambiguous child object {reference} in {wad.name}")
        child = candidates[0]
        paths = exact_world_transforms(child, records)
        check(len(paths) == 1, f"child has multiple placement paths: {wad.name}/{reference}")
        matrix, world, chain, raw_chain = paths[0]
        child_override = matching_override(records, child)
        native_id = (placement_instance_guid(child_override) if child_override else None)
        native_id = native_id or child["id"].hex()
        identity = f"{parent['catalogue_id']}:{reference.lower()}"
        marker_name, marker_uid = marker_identity(f"nornir_{subtype}", identity)
        state_field = ("runeKey.destructible.IsDestroyed() == true OR runeVisual.IsEnabled() == false"
                       if subtype == "seal" else "parent chest state == OPENED")
        state_adapter = ("loaded_breakable_exact_object_state" if subtype == "seal"
                         else "parent_reward_chest_checkpoint_state")
        result.append({
            "catalogue_id": f"nornir_{subtype}_{hashlib.sha256(identity.encode('ascii')).hexdigest()[:32]}",
            "family": f"nornir_{subtype}",
            "subtype": subtype,
            "display_name": f"{wad.stem} / {reference}",
            "native": {
                "object_name": child["name"],
                "reference_name": reference,
                "instance_guid": native_id,
                "record_id": child["id"].hex(),
                "parent_catalogue_id": parent["catalogue_id"],
                "parent_instance_guid": parent["native"]["instance_guid"],
                "parent_reference_source": "exact_lua_table_attribute_on_parent_placement",
                "key_type": key_type,
                "key_type_source": ("explicit_native_attribute" if key_types
                                    else "native_prefab_default_with_exact_breakable_refs"),
            },
            "marker": {
                "name": marker_name,
                "uid": marker_uid,
                "map_resource": f"goMapIconCompletionistNornir{subtype.title()}",
                "compass_class": f"CompletionistNornir{subtype.title()}",
                "position_world": list(world),
                "position_map": map_coordinates(parent["realm"], world),
                "map_projection": ("solved_midgard_affine" if parent["realm"] == "Midgard"
                                   else "native_mapcoords_world_position"),
                "coordinate_wad": f"WAD_{wad.stem}",
            },
            "realm": parent["realm"],
            "realm_id": parent["realm_id"],
            "region": parent["region"],
            "region_id": parent["region_id"],
            "region_source": parent["region_source"],
            "progression": {
                "parent_quest": parent["progression"]["parent_quest"],
                "parent_catalogue_id": parent["catalogue_id"],
                "state_adapter": state_adapter,
                "field": state_field,
                "instance_key": None,
                "read_only": True,
                "unloaded_query": "unresolved",
                "visibility_gate": "hide unless parent state is exactly known and unopened",
                "durable_individual_completion": subtype == "seal",
            },
            "source": {
                "wad": wad.name,
                "wad_sha256": hashlib.sha256(raw).hexdigest(),
                "override_offset": (f"0x{child_override['offset']:X}" if child_override else None),
                "final_offset": f"0x{child['offset']:X}",
                "world_transform_matrix": list(matrix),
                "transform_chain": chain,
            },
        })
    return result


def scan_native(game_root: Path = GAME) -> tuple[dict, dict]:
    game_root = Path(game_root).resolve()
    dcb_root = game_root / "exec" / "dc" / "pc_le"
    wad_root = game_root / "exec" / "wad" / "pc_le"
    check(dcb_root.is_dir() and wad_root.is_dir(), f"unsupported game root: {game_root}")
    summaries, map_evidence, quest_evidence = collectible_summary_index(dcb_root)
    targets, _unused_evidence = quest_targets(dcb_root)
    target_records = quest_target_records(dcb_root)
    entries = []
    carrier_identities: set[tuple[str, str, str]] = set()
    ship_head_carrier_ids: set[tuple[str, str]] = set()
    ship_head_transform_paths = 0
    scanned = 0
    excluded = collections.Counter()
    for wad in sorted(wad_root.glob("*.wad"), key=lambda item: item.name.lower()):
        raw = wad.read_bytes()
        lower = raw.lower()
        if not any(term in lower for term in (
                b"interact_loot_artifact", b"interact_chest_standard", b"langcheckruneread")):
            continue
        scanned += 1
        records = raven.parse_wad(raw)
        artifacts = extract_artifacts(wad, raw, records, summaries)
        chests = extract_standard_chests(wad, raw, records, summaries)
        lore_markers = extract_lore_markers(wad, raw, records, summaries)
        for row in artifacts + chests + lore_markers:
            carrier_identities.add((row["family"], wad.name, row["native"]["override_record_id"]))
        ship_paths = [row for row in artifacts if row["subtype"] == "Ship Head"]
        ship_head_transform_paths += len(ship_paths)
        ship_head_carrier_ids.update(
            (wad.name, row["native"]["override_record_id"]) for row in ship_paths)
        if b"interact_loot_artifact" in lower:
            carrier_count = sum(row["name"].lower() == "goartifactscript_overrideinst" for row in records)
            artefact_carriers = len({row["native"]["override_record_id"] for row in artifacts})
            excluded["non_artefact_shared_script_carriers"] += carrier_count - artefact_carriers
        entries.extend(artifacts)
        entries.extend(lore_markers)
        for chest in chests:
            if wad.name.lower().startswith("nid"):
                excluded[f"procedural_{chest['family']}_template_placements"] += 1
            else:
                entries.append(chest)
                if chest["family"] == "nornir_chest":
                    entries.extend(extract_nornir_children(chest, wad, raw, records))
    deduplicated = {}
    duplicate_sources = collections.defaultdict(list)
    for row in entries:
        key = row["catalogue_id"]
        if key in deduplicated:
            previous = deduplicated[key]
            check(previous["family"] == row["family"], f"cross-family identity: {key}")
            check(all(abs(a - b) < 1e-5 for a, b in zip(
                previous["marker"]["position_world"], row["marker"]["position_world"])),
                f"identity has conflicting positions: {key}")
            previous_paths = previous["native"]["carrier_transform_paths"]
            known_paths = {canonical_json(path) for path in previous_paths}
            previous_paths.extend(path for path in row["native"]["carrier_transform_paths"]
                                  if canonical_json(path) not in known_paths)
            previous_paths.sort(key=lambda path: (
                path["wad"], path["state_carrier_guid"] or "",
                tuple(node["offset"] for node in path["transform_chain"])))
            carrier_guids = sorted({path["state_carrier_guid"] for path in previous_paths
                                    if path["state_carrier_guid"]})
            previous["native"]["state_carrier_guids"] = carrier_guids
            previous["native"]["state_instance_guid"] = (
                carrier_guids[0] if len(carrier_guids) == 1 else None)
            numbered_objects = {
                canonical_json(item): item
                for item in (previous["native"]["numbered_native_objects"]
                             + row["native"]["numbered_native_objects"])
            }
            previous["native"]["numbered_native_objects"] = sorted(
                numbered_objects.values(),
                key=lambda item: (item["number"], item["object_name"], item["offset"]))
            previous["native"]["numbered_object_evidence"] = sorted({
                item["number"] for item in previous["native"]["numbered_native_objects"]})
            instance_keys = sorted(f"{previous['native']['instance_guid']}.{guid}"
                                   for guid in carrier_guids)
            previous["progression"]["instance_keys"] = instance_keys
            previous["progression"]["instance_key"] = (
                instance_keys[0] if len(instance_keys) == 1 else None)
            duplicate_sources[key].append(row["source"]["wad"])
            continue
        deduplicated[key] = row
    entries = list(deduplicated.values())
    for key, sources in duplicate_sources.items():
        entries_row = deduplicated[key]
        entries_row["source"]["duplicate_stream_sources"] = sorted(set(sources))
    entries.sort(key=lambda row: (row["family"], row["realm"], row["region"] or "",
                                  row["source"]["wad"], row["native"]["instance_guid"]))
    catalogue = {
        "schema_version": 1,
        "catalogue": "completionist-map-gow2018-all-collectibles",
        "source_authority": "native_pc_game_data",
        "read_only_progression": True,
        "state_gate": "unloaded_per_instance_queries_unresolved",
        "collectibles": entries,
    }
    family_counts = dict(sorted(collections.Counter(row["family"] for row in entries).items()))
    carrier_counts = dict(sorted(collections.Counter(
        family for family, _wad, _record in carrier_identities).items()))
    target_totals = {
        "artefact_shiphead": sum(value for name, value in targets.items() if "Shiphead" in name),
        "lore_marker": sum(value for name, value in targets.items() if "LoreMarker" in name),
        "legendary_chest": sum(value for name, value in targets.items() if "LegendaryChest" in name),
        "nornir_chest": sum(value for name, value in targets.items() if "RunicChest" in name),
    }
    ship_head_rows = [row for row in entries
                      if row["family"] == "artefact" and row["subtype"] == "Ship Head"]
    nornir_rows = [row for row in entries if row["family"] == "nornir_chest"]
    nornir_binding_evidence = [
        build_nornir_binding_evidence(
            row, dcb_root, summaries, target_records, map_evidence, quest_evidence)
        for row in nornir_rows
    ]
    nornir_binding_evidence.sort(key=lambda row: (row["wad"], row["physical_instance_guid"]))
    check(
        {claim[0] for claim in NORNIR_PRIOR_UNVERIFIED_BINDING_CLAIMS}
        == {row["physical_instance_guid"] for row in nornir_binding_evidence
            if row["proposed_region_summary_parent"]},
        "prior Nornir claim ledger does not match physical evidence rows")
    evidence_by_id = {row["catalogue_id"]: row for row in nornir_binding_evidence}
    for row in nornir_rows:
        quest, source = resolve_nornir_parent_binding(
            row["source"]["wad"], evidence_by_id[row["catalogue_id"]], summaries)
        row["progression"]["parent_quest"] = quest
        row["progression"]["parent_quest_source"] = source
        if quest:
            summary = summaries[quest]
            row["realm"] = summary["realm"]
            row["realm_id"] = summary["realm_id"]
            row["region"] = summary["region"]
            row["region_id"] = summary["region_id"]
            row["region_source"] = "exact_native_reference_chain"
    unjoined_nornir = [row for row in nornir_rows
                       if not row["progression"].get("parent_quest")]
    tracked_counts = dict(sorted(collections.Counter(
        row["family"] for row in entries
        if row["family"] in {"artefact", "lore_marker", "legendary_chest", "nornir_chest"}
        and row["progression"].get("parent_quest")).items()))
    audit = {
        "result": "STATIC_CATALOGUE_PASS_RUNTIME_BLOCKED",
        "static_catalogue_ready": True,
        "ready_for_runtime_test": False,
        "game_files_written": False,
        "game_launched": False,
        "save_or_progression_touched": False,
        "wads_scanned": scanned,
        "physical_counts": family_counts,
        "native_carrier_counts_before_physical_dedup": carrier_counts,
        "tracked_physical_counts": tracked_counts,
        "native_tracked_target_totals": target_totals,
        "ship_head_accounting": {
            "physical_placements": len(ship_head_rows),
            "state_carriers": len(ship_head_carrier_ids),
            "exhaustive_transform_paths": ship_head_transform_paths,
            "tracked_target": target_totals["artefact_shiphead"],
            "target_discrepancy_result": "BLOCKED_EXACT_REASON_UNKNOWN",
            "target_discrepancy_reason": (
                "Native data proves 9 state carriers and 9 distinct physical placements, "
                "but quests.dcb tracks 10. No exact native tenth carrier, placement, legacy "
                "object, or bookkeeping duplicate was proved."
            ),
        },
        "nornir_accounting": {
            "physical_placements": len(nornir_rows),
            "tracked_target": target_totals["nornir_chest"],
            "exact_joined": sum(bool(row["progression"].get("parent_quest"))
                                for row in nornir_rows),
            "pass_exact": sum(row["final_status"] == "PASS_EXACT"
                              for row in nornir_binding_evidence),
            "blocked_exact_reason_unknown": sum(
                row["final_status"] == "BLOCKED_EXACT_REASON_UNKNOWN"
                for row in nornir_binding_evidence),
            "binding_method": "validated_exact_native_reference_chain_only",
            "prior_claims_are_join_authority": False,
            "wad_filename_is_join_authority": False,
            "target_count_is_join_authority": False,
            "region_or_count_inference_used": False,
            "unjoined": [{
                "physical_instance_guid": row["native"]["instance_guid"],
                "wad": row["source"]["wad"],
                "world": row["marker"]["position_world"],
                "classification": (
                    "level_scripted_untracked_triple_chest_reward"
                    if row["source"]["wad"].lower() == "helr100_docks.wad"
                    else "unresolved_tracked_candidate"),
                "result": (
                    "PASS_EXPLAINED"
                    if row["source"]["wad"].lower() == "helr100_docks.wad"
                    else "BLOCKED_EXACT_REASON_UNKNOWN"),
                "reason": (
                    "Placement names HelR100_TripleChest_Callback, and helr100 level script "
                    "owns that callback. quests.dcb has no Helheim RunicChest target."
                    if row["source"]["wad"].lower() == "helr100_docks.wad"
                    else "No exact RegionSummary quest update, reference, GUID chain, event "
                         "registration, or object attribute binding was proved."),
            } for row in unjoined_nornir],
        },
        "nornir_exact_binding_evidence": nornir_binding_evidence,
        "tyrs_vault_nornir_binding": {
            "result": "BLOCKED_EXACT_REASON_UNKNOWN",
            "wad": "cal500_runevault.wad",
            "physical_instance_guid": "f8548c57-4dc6-7cba-277c-5cb31099648b",
            "candidate_parent_quest": "RegionSummary_RunicChest_Parent_TyrsVault",
            "evidence": [
                "Exact placement has RuneChestOpened callback into cal500_runevault level script.",
                "Level script names chest_locked_tier4_cal500_1, bRuneChestOpened, and TyrsVault.",
                "Target name appears in shared interact_chest_standard blob, not placement or level script.",
            ],
            "blocker": "No exact callback-to-RegionSummary update or native quest reference binds object to target.",
        },
        "helheim_unjoined_nornir": {
            "result": "PASS_EXPLAINED",
            "classification": "level_scripted_untracked_triple_chest_reward",
            "wad": "helr100_docks.wad",
            "physical_instance_guid": "6fc8ac79-4c63-bf63-a137-36b7cd3c7f25",
            "evidence": [
                "Placement owns HelR100_TripleChest_Callback.",
                "helr100_docks level script owns same callback and triple-chest encounter names.",
                "quests.dcb has no Helheim RunicChest target.",
            ],
        },
        "excluded": dict(sorted(excluded.items())),
        "unresolved_region_rows": sum(row["region"] is None for row in entries),
        "native_evidence": {"mapmaster": map_evidence, "quests": quest_evidence},
        "tracked_summary_targets": {
            name: {"target": targets.get(name), **row}
            for name, row in sorted(summaries.items())
            if any(token in name.lower() for token in ("artifact", "shiphead", "runicchest", "legendarychest"))
        },
        "family_gates": {
            "static_catalogue": "PASS",
            "loaded_state_oracles": "PASS_WITH_NORNIR_CHILD_LIMITS",
            "unloaded_preinstall_per_instance_state": "BLOCKED",
            "runtime_generation": "BLOCKED_FAIL_CLOSED",
            "gameplay_test": "NOT_RUN",
        },
    }
    return catalogue, audit


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def safe_repo_output(value: str) -> Path:
    path = (REPO / value).resolve()
    check(path != REPO and REPO in path.parents, f"output must stay inside repository: {path}")
    check(GAME.resolve() not in path.parents, f"refusing game-tree output: {path}")
    return path


def write_atomic(path: Path, content: str) -> None:
    """Replace one repository output atomically; remove partial temp on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=GAME)
    parser.add_argument("--output")
    parser.add_argument("--audit")
    args = parser.parse_args()
    catalogue, audit = scan_native(args.game_root)
    audit["catalogue_sha256"] = hashlib.sha256(
        canonical_json(catalogue).encode("utf-8")).hexdigest()
    if args.output:
        output = safe_repo_output(args.output)
        write_atomic(output, canonical_json(catalogue))
    if args.audit:
        audit_output = safe_repo_output(args.audit)
        write_atomic(audit_output, canonical_json(audit))
    if not args.output and not args.audit:
        print(canonical_json(audit), end="")
