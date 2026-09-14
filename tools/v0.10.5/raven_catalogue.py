"""Extract and validate Odin's Raven static identity from native PC data.

Read-only tool. It never writes game or save files. Native WAD scene records are
the source for per-instance identity and position. Native map/quest DCB records
are the source for realm, region, and parent target counts.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Iterable


RAVEN_PARENT_RE = re.compile(rb"RegionSummary_[A-Z0-9]+_Raven_Parent")
GUID_RE = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
WAD_NAME_RE = re.compile(rb"WAD_[A-Za-z0-9_]+")
EXPECTED_OBJECT_COUNT = 53
EXPECTED_LABOR_TARGET = 51
PROVEN_NAME = "Completionist_V103_Veithurgard_Raven_01"
PROVEN_UID = "E15E6BC82AE2773E"
PROVEN_NATIVE_WORLD = (-64.850898742676, 12.987384796143, 787.30694580078)
PROVEN_AUTHORED_WORLD = (-64.875, 12.984375, 787.5)

REALM_NAMES = (
    "Midgard", "Alfheim", "Helheim", "Jotunheim", "Niflheim", "Muspelheim",
    "Svartalheim", "Vanaheim", "Asgard", "FastTravel_Realm",
)

# Strings come from native gameart/ui/scripts/consts/mapconsts.lua. Their hashes
# are checked against mapmaster.dcb; they are labels, not identity sources.
REGION_NAMES = (
    "Alfheim Bridge", "Alfheim", "BeachCave", "BeachMaze", "BeachRuins",
    "BeachShipwreck", "BeachTower", "BeachWaterfall", "CalderaShores",
    "CalderaShoresA", "CalderaShoresB", "CalderaShoresC", "CalderaShoresD",
    "CalderaShoresE", "CalderaShoresF", "CalderaShoresG", "CalderaShoresH",
    "CalderaTemple", "Foothills", "Forest", "ForestDungeon", "Helheim",
    "Helheim Docks", "HTTK", "HuldraMine01", "HuldraMine02",
    "HuldraStronghold", "IslandArch", "IslandClimb", "IslandShipwreck",
    "LightTemple", "MasonTrail", "StoneMason Connector", "NiflheimMain",
    "Peakspass", "Belly of the Mountain", "Base of the Mountain", "Riverpass",
    "Sanctuary Grove", "Stonemason", "VikingFuneral",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def name_hash(name: str) -> int:
    """64-bit case-folded hash loop observed in God of War PC."""
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def align16(value: int) -> int:
    return (value + 15) & ~15


def parse_wad(raw: bytes) -> list[dict]:
    records: list[dict] = []
    stack: list[int] = []
    offset = 0
    while offset < len(raw):
        check(offset + 96 <= len(raw), f"short WAD header at {offset:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        start = offset + 96
        end = start + size
        padded = align16(end)
        check(padded <= len(raw), f"short WAD payload at {offset:#x}")
        name = raw[offset + 24:offset + 80].split(b"\0", 1)[0].decode("ascii")
        records.append({
            "kind": kind,
            "flags": flags,
            "size": size,
            "name": name,
            "id": raw[offset + 8:offset + 24],
            "data": raw[start:end],
            "offset": offset,
            "parent": stack[-1] if stack else None,
        })
        here = len(records) - 1
        if kind == 2:
            stack.append(here)
        elif kind == 3:
            check(bool(stack), f"unmatched WAD group end at {offset:#x}")
            stack.pop()
        offset = padded
    check(not stack and offset == len(raw), "WAD group walk did not end cleanly")
    return records


class Dcb:
    """Small strict reader for shipped PC DCB layout."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.chunks: dict[int, tuple[int, bytes]] = {}
        offset = 0
        while offset < len(self.raw):
            check(offset + 96 <= len(self.raw), "truncated DCB chunk header")
            kind, flags, size = struct.unpack_from("<HHI", self.raw, offset)
            end = offset + 96 + size
            check(flags == 0x10 and kind not in self.chunks and end <= len(self.raw), "invalid DCB chunk")
            self.chunks[kind] = (offset + 96, self.raw[offset + 96:end])
            offset = align16(end)
        check(offset == len(self.raw) and set(self.chunks) == {11, 12, 13, 14, 15}, "unsupported DCB layout")
        self.file_base, self.blob = self.chunks[12]
        relocation_blob = self.chunks[15][1]
        count = struct.unpack_from("<I", relocation_blob)[0]
        check(len(relocation_blob) == 4 + count * 4, "invalid DCB relocation table")
        self.relocations = set(struct.unpack_from(f"<{count}I", relocation_blob, 4))
        check(len(self.relocations) == count, "duplicate DCB relocation")
        exports = self.chunks[13][1]
        count = struct.unpack_from("<I", exports)[0]
        self.exports: dict[str, tuple[int, int]] = {}
        for index in range(count):
            root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", exports, 8 + index * 24)
            name = exports[string_offset:exports.index(0, string_offset)].decode("ascii")
            check(name_hash(name) == uid, "DCB export hash mismatch")
            self.exports[name] = (root, type_id)

    def unpack(self, fmt: str, offset: int):
        check(0 <= offset <= len(self.blob) - struct.calcsize(fmt), "DCB read outside data chunk")
        return struct.unpack_from(fmt, self.blob, offset)

    def pointer(self, field: int) -> int:
        check(field in self.relocations, f"missing DCB relocation at {field:#x}")
        delta, = self.unpack("<q", field)
        target = field + delta
        check(0 <= target < len(self.blob), "DCB pointer outside data chunk")
        return target

    def array(self, field: int, stride: int) -> range:
        count, = self.unpack("<I", field + 8)
        if count == 0:
            return range(0)
        start = self.pointer(field)
        self.unpack(f"<{count * stride}s", start)
        return range(start, start + count * stride, stride)

    def string(self, field: int) -> str:
        delta, = self.unpack("<q", field)
        if delta == 0:
            return ""
        start = self.pointer(field)
        return self.blob[start:self.blob.index(0, start)].decode("ascii")

    def root(self, name: str, expected_type: int) -> int:
        check(name in self.exports, f"missing DCB export {name}")
        root, type_id = self.exports[name]
        check(type_id == expected_type, f"wrong DCB export type for {name}")
        return root

    def evidence(self) -> dict:
        return {
            "path": self.path.name,
            "bytes": len(self.raw),
            "sha256": digest(self.raw),
            "relocations": len(self.relocations),
        }


def identity_transform() -> tuple[tuple[float, ...], tuple[float, ...]]:
    return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0)


def record_transform(record: dict) -> tuple[tuple[float, ...], tuple[float, ...]]:
    check(record["size"] == 164, "scene transform record is not 164 bytes")
    data = record["data"]
    return struct.unpack_from("<9f", data, 0x68), struct.unpack_from("<3f", data, 0x8C)


def transform_point(transform, point: Iterable[float]) -> tuple[float, float, float]:
    matrix, translation = transform
    x, y, z = point
    return (
        matrix[0] * x + matrix[3] * y + matrix[6] * z + translation[0],
        matrix[1] * x + matrix[4] * y + matrix[7] * z + translation[1],
        matrix[2] * x + matrix[5] * y + matrix[8] * z + translation[2],
    )


def compose(parent, child):
    """Return parent * child for column-major affine transforms."""
    pm, pt = parent
    cm, ct = child
    columns = []
    for column in range(3):
        vector = cm[column * 3:column * 3 + 3]
        columns.extend((
            pm[0] * vector[0] + pm[3] * vector[1] + pm[6] * vector[2],
            pm[1] * vector[0] + pm[4] * vector[1] + pm[7] * vector[2],
            pm[2] * vector[0] + pm[5] * vector[1] + pm[8] * vector[2],
        ))
    return tuple(columns), transform_point((pm, pt), ct)


def world_transform(record: dict, records: list[dict]) -> tuple[tuple[float, ...], tuple[float, ...], list[dict]]:
    candidates: dict[bytes, list[dict]] = collections.defaultdict(list)
    for row in records:
        if row["kind"] == 1 and row["flags"] == 0x3D and row["size"] == 164:
            candidates[row["data"][0x0C:0x1C]].append(row)
    result = record_transform(record)
    chain = [{"name": record["name"], "record_id": record["id"].hex(), "offset": f"0x{record['offset']:X}"}]
    parent_id = record["data"][0x54:0x64]
    seen = {record["id"]}
    while parent_id != bytes(16):
        parents = [row for row in candidates.get(parent_id, []) if row["id"] not in seen]
        if not parents:
            break
        check(len(parents) == 1, f"ambiguous scene parent {parent_id.hex()} for {record['name']}")
        parent = parents[0]
        seen.add(parent["id"])
        result = compose(record_transform(parent), result)
        chain.append({"name": parent["name"], "record_id": parent["id"].hex(), "offset": f"0x{parent['offset']:X}"})
        parent_id = parent["data"][0x54:0x64]
    return result[0], result[1], chain


def read_region_index(dcb_root: Path) -> tuple[dict[str, dict], dict]:
    master = Dcb(dcb_root / "mapmaster.dcb")
    realm_labels = {name_hash(name): name for name in REALM_NAMES}
    region_labels = {name_hash(name): name for name in REGION_NAMES}
    result: dict[str, dict] = {}
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        realm_id, = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            region_id, = master.unpack("<Q", region)
            for item in master.array(region + 0x58, 8):
                summary = master.pointer(item)
                if summary + 0x30 not in master.relocations:
                    continue
                quest = master.string(summary + 0x30)
                if RAVEN_PARENT_RE.fullmatch(quest.encode("ascii")):
                    check(quest not in result, f"duplicate Raven parent in mapmaster: {quest}")
                    result[quest] = {
                        "realm": realm_labels.get(realm_id, f"UNKNOWN_{realm_id:016X}"),
                        "realm_id": f"{realm_id:016X}",
                        "region": region_labels.get(region_id, f"UNKNOWN_{region_id:016X}"),
                        "region_id": f"{region_id:016X}",
                        "summary_record_offset": f"0x{master.file_base + summary:X}",
                    }
    return result, master.evidence()


def read_parent_targets(dcb_root: Path) -> tuple[dict[str, int], dict]:
    quests = Dcb(dcb_root / "quests.dcb")
    result = {}
    for item in quests.array(quests.root("QUESTS_PERM_DATA", 0x159), 8):
        record = quests.pointer(item)
        name = quests.string(record)
        if RAVEN_PARENT_RE.fullmatch(name.encode("ascii")):
            result[name] = quests.unpack("<I", record + 0x30)[0]
    return result, quests.evidence()


def read_canonical_wad_names(dcb_root: Path) -> tuple[dict[str, str], dict]:
    result: dict[str, str] = {}
    evidence = {}
    for name in ("mapcoords.dcb", "compassgraph.dcb"):
        path = dcb_root / name
        raw = path.read_bytes()
        evidence[name] = {"sha256": digest(raw), "bytes": len(raw)}
        for match in WAD_NAME_RE.finditer(raw):
            value = match.group().decode("ascii")
            result.setdefault(value.lower(), value)
    return result, evidence


def quantize_half(values: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(values)
    return struct.unpack("<3e", struct.pack("<3e", *values))


def marker_name(instance_guid: str) -> str:
    return f"Completionist_V105_Raven_{instance_guid.replace('-', '')[:16]}"


def extract_wad_ravens(wad: Path, region_index: dict[str, dict], wad_names: dict[str, str]) -> list[dict]:
    raw = wad.read_bytes()
    if not RAVEN_PARENT_RE.search(raw):
        return []
    records = parse_wad(raw)
    result = []
    for index, override in enumerate(records):
        match = RAVEN_PARENT_RE.search(override["data"])
        if not match or not override["name"].lower().endswith("_overrideinst"):
            continue
        check(override["kind"] == 1 and override["flags"] == 0x3D, "unexpected Raven override record kind")
        check(index + 3 < len(records), "Raven override has no instance group")
        start, final, end = records[index + 1:index + 4]
        check(start["kind"] == 2 and final["kind"] == 1 and end["kind"] == 3, "Raven instance group shape changed")
        check(final["parent"] == index + 1 and final["size"] == 164 and final["flags"] == 0x3D,
              "Raven final transform shape changed")
        quest = match.group().decode("ascii")
        check(quest in region_index, f"Raven parent absent from mapmaster: {quest}")
        guids = [value.decode("ascii").lower() for value in GUID_RE.findall(override["data"])]
        check(bool(guids), f"Raven override has no native instance GUID: {override['name']}")
        instance_guid = guids[-1]
        matrix, world, chain = world_transform(final, records)
        check(all(math.isfinite(value) for value in world), "nonfinite Raven world position")
        native_world = tuple(float(value) for value in world)
        is_proven = math.dist(native_world, PROVEN_NATIVE_WORLD) < 0.01 and quest == "RegionSummary_VF_Raven_Parent"
        custom_name = PROVEN_NAME if is_proven else marker_name(instance_guid)
        custom_uid = f"{name_hash(custom_name):016X}"
        check(not is_proven or custom_uid == PROVEN_UID, "proven v3.3 Raven UID changed")
        authored_world = PROVEN_AUTHORED_WORLD if is_proven else quantize_half(native_world)
        region = region_index[quest]
        wad_key = f"wad_{wad.stem}".lower()
        check(wad_key in wad_names, f"canonical WAD loader name absent from native route data: {wad.name}")
        entry = {
            "catalogue_id": f"raven_{instance_guid.replace('-', '')}",
            "family": "raven",
            "display_name": f"{region['region']} / {wad.stem} / {final['name']}",
            "native": {
                "object_name": final["name"],
                "override_name": override["name"],
                "instance_guid": instance_guid,
                "script_guid": guids[0],
                "override_record_id": override["id"].hex(),
                "final_record_id": final["id"].hex(),
                "prototype_id": final["data"][0x0C:0x1C].hex(),
                "parent_prototype_id": final["data"][0x54:0x64].hex(),
                "marker_name": None,
                "marker_uid": None,
            },
            "marker": {
                "name": custom_name,
                "uid": custom_uid,
                "map_resource": "goMapIconCompletionistRaven",
                "compass_class": "CompletionistRaven",
                "hud_resource": "goCompletionistRavenHUD",
                "in_world_resource": "COMPASS_INWORLD_COMPLETIONIST_RAVEN",
                "position_world": list(authored_world),
                "map_projection": "native_mapcoords_world_position",
                "coordinate_wad": wad_names[wad_key],
            },
            "realm": region["realm"],
            "realm_id": region["realm_id"],
            "region": region["region"],
            "region_id": region["region_id"],
            "progression": {
                "parent_quest": quest,
                "state_adapter": "precisionchallenge_checkpoint_ravenKilled",
                "field": "ravenKilled",
                "instance_key": instance_guid,
                "read_only": True,
                "unloaded_query": "unresolved",
            },
            "source": {
                "wad": wad.name,
                "wad_sha256": digest(raw),
                "override_offset": f"0x{override['offset']:X}",
                "final_offset": f"0x{final['offset']:X}",
                "native_world_position": list(native_world),
                "world_transform_matrix": list(matrix),
                "transform_chain": chain,
            },
            "special_handling": ["preserve_v3_3_identity_and_position"] if is_proven else [],
        }
        result.append(entry)
    return result


def validate_catalogue(catalogue: dict) -> dict:
    check(catalogue.get("schema_version") == 2, "wrong Raven catalogue schema version")
    entries = catalogue.get("ravens")
    check(isinstance(entries, list), "ravens must be a list")
    check(len(entries) == EXPECTED_OBJECT_COUNT, f"expected {EXPECTED_OBJECT_COUNT} Raven objects, found {len(entries)}")
    keys = {
        "catalogue_id": [row.get("catalogue_id") for row in entries],
        "instance_guid": [row.get("native", {}).get("instance_guid") for row in entries],
        "marker_uid": [row.get("marker", {}).get("uid") for row in entries],
        "marker_name": [row.get("marker", {}).get("name") for row in entries],
    }
    for label, values in keys.items():
        check(all(isinstance(value, str) and value for value in values), f"missing {label}")
        check(len(values) == len(set(values)), f"duplicate {label}")
    realm_counts = collections.Counter()
    region_counts = collections.Counter()
    for row in entries:
        check(row.get("family") == "raven", "wrong collectible family")
        check(row.get("realm") in {"Midgard", "Alfheim", "Helheim"}, "invalid Raven realm")
        check(not str(row.get("region", "")).startswith("UNKNOWN_"), "unknown Raven region")
        marker = row.get("marker", {})
        check(marker.get("map_resource") == "goMapIconCompletionistRaven", "wrong Raven map resource")
        check(marker.get("compass_class") == "CompletionistRaven", "wrong Raven compass class")
        position = marker.get("position_world")
        check(isinstance(position, list) and len(position) == 3, "invalid Raven world position")
        check(all(isinstance(value, (int, float)) and math.isfinite(value) for value in position), "nonfinite Raven position")
        check(any(abs(value) > 0.001 for value in position), "zero/default Raven position")
        check(all(abs(value) < 65504 for value in position), "Raven position outside half-float mapcoords bounds")
        progression = row.get("progression", {})
        check(progression.get("state_adapter") == "precisionchallenge_checkpoint_ravenKilled", "missing Raven state adapter")
        check(progression.get("field") == "ravenKilled" and progression.get("read_only") is True,
              "Raven state adapter is not read-only native state")
        check(row.get("source", {}).get("wad_sha256"), "missing Raven position source")
        realm_counts[row["realm"]] += 1
        region_counts[row["region"]] += 1
    check(dict(sorted(realm_counts.items())) == {"Alfheim": 2, "Helheim": 6, "Midgard": 45},
          f"unexpected Raven realm distribution: {dict(realm_counts)}")
    proven = [row for row in entries if row["marker"]["uid"] == PROVEN_UID]
    check(len(proven) == 1, "proven v3.3 Raven missing or duplicated")
    check(tuple(proven[0]["marker"]["position_world"]) == PROVEN_AUTHORED_WORLD, "proven v3.3 Raven position changed")
    return {
        "catalogue_entries": len(entries),
        "unique_catalogue_ids": len(set(keys["catalogue_id"])),
        "unique_native_instance_guids": len(set(keys["instance_guid"])),
        "unique_marker_uids": len(set(keys["marker_uid"])),
        "realms": dict(sorted(realm_counts.items())),
        "regions": dict(sorted(region_counts.items())),
        "all_positions_valid": True,
        "all_entries_have_state_oracle": True,
        "all_entries_have_position_source": True,
    }


def build_catalogue(game_root: Path) -> tuple[dict, dict]:
    game_root = Path(game_root).resolve()
    dcb_root = game_root / "exec" / "dc" / "pc_le"
    wad_root = game_root / "exec" / "wad" / "pc_le"
    check(dcb_root.is_dir() and wad_root.is_dir(), f"unsupported game root: {game_root}")
    region_index, map_evidence = read_region_index(dcb_root)
    parent_targets, quest_evidence = read_parent_targets(dcb_root)
    wad_names, route_evidence = read_canonical_wad_names(dcb_root)
    check(set(parent_targets) == set(region_index), "mapmaster/quests Raven parent mismatch")
    check(sum(parent_targets.values()) == EXPECTED_LABOR_TARGET, "native Raven parent target sum changed")
    ravens = []
    scanned = 0
    for wad in sorted(wad_root.glob("*.wad"), key=lambda path: path.name.lower()):
        raw_prefix_test = wad.read_bytes()
        if not RAVEN_PARENT_RE.search(raw_prefix_test):
            continue
        scanned += 1
        ravens.extend(extract_wad_ravens(wad, region_index, wad_names))
    ravens.sort(key=lambda row: (row["realm"], row["region"], row["source"]["wad"], row["native"]["instance_guid"]))
    by_parent = collections.Counter(row["progression"]["parent_quest"] for row in ravens)
    surplus = {quest: count - parent_targets[quest] for quest, count in sorted(by_parent.items()) if count != parent_targets[quest]}
    check(surplus == {"RegionSummary_CALS_Raven_Parent": 1, "RegionSummary_RP_Raven_Parent": 1},
          f"unexpected native Raven object/target difference: {surplus}")
    for row in ravens:
        if row["progression"]["parent_quest"] in surplus:
            row["special_handling"].append("parent_contains_one_bonus_untracked_raven")
    catalogue = {
        "schema_version": 2,
        "catalogue": "completionist-map-gow2018-odins-ravens",
        "source_authority": "native_pc_game_data",
        "expected_native_object_count": EXPECTED_OBJECT_COUNT,
        "native_labor_target_count": EXPECTED_LABOR_TARGET,
        "read_only_progression": True,
        "shared_resources": {
            "map": "goMapIconCompletionistRaven",
            "compass_class": "CompletionistRaven",
            "hud": "goCompletionistRavenHUD",
            "in_world": "COMPASS_INWORLD_COMPLETIONIST_RAVEN",
        },
        "state_oracle": {
            "adapter": "precisionchallenge_checkpoint_ravenKilled",
            "native_field": "ravenKilled",
            "native_identity": "WAD object instance GUID",
            "writes_progression": False,
            "unloaded_instance_query": "unresolved",
        },
        "ravens": ravens,
    }
    summary = validate_catalogue(catalogue)
    audit = {
        "result": "STATIC_CATALOGUE_COMPLETE_STATE_GATE_BLOCKED",
        "ready_for_runtime_test": False,
        "game_files_written": False,
        "game_launched": False,
        "save_or_progression_touched": False,
        "expected_native_object_count": EXPECTED_OBJECT_COUNT,
        "native_labor_target_count": EXPECTED_LABOR_TARGET,
        "native_hidden_surplus_count": EXPECTED_OBJECT_COUNT - EXPECTED_LABOR_TARGET,
        "wad_files_with_raven_parent": scanned,
        "parent_object_counts": dict(sorted(by_parent.items())),
        "parent_target_counts": dict(sorted(parent_targets.items())),
        "parent_surplus": surplus,
        "catalogue_validation": summary,
        "native_evidence": {"mapmaster": map_evidence, "quests": quest_evidence, "route_wad_names": route_evidence},
        "blocking_issue": "No proven read-only API can query ravenKilled for an unloaded Raven WAD instance.",
    }
    return catalogue, audit


def canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
