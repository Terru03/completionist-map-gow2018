#!/usr/bin/env python3
"""Build all-Raven v0.10.5 offline candidate from proven v3.3 files."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from raven_catalogue import canonical_json, validate_catalogue


STAGE_PATH = REPO / "tools" / "v0.10.4" / "build-raven-twin-stage-a-offline.py"
spec = importlib.util.spec_from_file_location("all_ravens_stage_base", STAGE_PATH)
stage = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(stage)


MASTER = "exec/dc/pc_le/mapmaster.dcb"
COORDS = "exec/dc/pc_le/mapcoords.dcb"
POOL = "exec/dc/pc_le/wad_r_ui.dcb"
MAP_LUA = "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
EVENT_LUA = "mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua"
SOURCE_HASHES = {
    MASTER: "1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31",
    COORDS: "36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c",
    POOL: "9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b",
    MAP_LUA: "16e13b342f3bbe98ac9b87eb34bf0115e6b04340d6e41270f38a557f2ed51493",
    EVENT_LUA: "61e6bc8efe1fcb9b2a6e796aa86ce9a5f74fc18e97229aae7cc52b652a565800",
}
TWIN_UID = 0x2F530E7F3F156D90
PROVEN_UID = 0xE15E6BC82AE2773E
RAVEN_ICON = "goMapIconCompletionistRaven"
RAVEN_ICON_HASH = 0x584F31DC8BD6E738
OUTPUT = REPO / "build/v0.10.5-all-ravens-release-candidate/offline/candidate/game-root"
REPORT = REPO / "archive/all-ravens/all-ravens-release-candidate-offline.json"
CATALOGUE = REPO / "catalogue/odins-ravens.json"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def lua_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_lua(catalogue: dict, template_path: Path, token: str, state_rows: bool = False) -> bytes:
    lines = []
    for row in catalogue["ravens"]:
        if state_rows:
            x, y, z = row["source"]["native_world_position"]
            lines.append(
                "    {CatalogueId=%s,Name=%s,ParentQuest=%s,X=%.15g,Y=%.15g,Z=%.15g},"
                % (lua_quote(row["catalogue_id"]), lua_quote(row["marker"]["name"]),
                   lua_quote(row["progression"]["parent_quest"]), x, y, z)
            )
        else:
            lines.append(
                "    {CatalogueId=%s,Name=%s,UidHex=%s,Realm=%s,RegionId=%s,ParentQuest=%s},"
                % (
                    lua_quote(row["catalogue_id"]), lua_quote(row["marker"]["name"]),
                    lua_quote(row["marker"]["uid"]), lua_quote(row["realm"]),
                    lua_quote(row["region_id"]),
                    lua_quote(row["progression"]["parent_quest"]),
                )
            )
    text = template_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    check(text.count(token) == 1, f"Lua template token count changed: {template_path.name}")
    return text.replace(token, "\n".join(lines)).encode("utf-8")


def parse_candidate(raw: bytes, name: str):
    return stage.parse_native_candidate(stage.load_native_module(), Path(name), raw)


def map_regions(dcb) -> dict[tuple[int, int], int]:
    result = {}
    root = dcb.root("MAP_PERM_DATA", 0x415)
    for realm in dcb.array(root + 0x10, 0x40):
        realm_id, = dcb.unpack("<Q", realm)
        for region in dcb.array(realm + 0x30, 0x68):
            region_id, = dcb.unpack("<Q", region)
            result[(realm_id, region_id)] = region
    return result


def build_mapmaster(source_path: Path, catalogue: dict) -> tuple[bytes, dict]:
    native = stage.load_native_module()
    source = native.Dcb(source_path)
    before = stage.marker_snapshot(source)
    donor = [row for row in before if int(row["uid"], 16) == PROVEN_UID]
    check(len(donor) == 1 and donor[0]["icon"] == RAVEN_ICON, "proven map marker missing")
    donor_offset = donor[0]["offset"]
    wanted = {int(row["marker"]["uid"], 16): row for row in catalogue["ravens"]}
    check(TWIN_UID not in wanted and PROVEN_UID in wanted and len(wanted) == 53, "catalogue marker identities changed")
    existing = {int(row["uid"], 16) for row in before}
    check(not ((set(wanted) - {PROVEN_UID}) & existing), "new Raven marker UID collides with source")
    grouped: dict[tuple[int, int], list[dict]] = collections.defaultdict(list)
    for row in catalogue["ravens"]:
        if int(row["marker"]["uid"], 16) != PROVEN_UID:
            grouped[(int(row["realm_id"], 16), int(row["region_id"], 16))].append(row)
    regions = map_regions(source)
    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    changed_fields = []
    for key in sorted(grouped):
        check(key in regions, f"catalogue realm/region absent from mapmaster: {key}")
        region = regions[key]
        field = region + 0x38
        old_offsets = list(source.array(field, 0x48))
        survivors = [offset for offset in old_offsets if source.unpack("<Q", offset)[0] != TWIN_UID]
        new_start = stage.align_blob(blob)
        for old_offset in survivors:
            destination = len(blob)
            blob.extend(source.blob[old_offset:old_offset + 0x48])
            stage.rebase_pointer(source, old_offset + 0x08, blob, destination + 0x08, relocations)
            stage.rebase_pointer(source, old_offset + 0x20, blob, destination + 0x20, relocations)
        for row in sorted(grouped[key], key=lambda item: item["marker"]["uid"]):
            destination = len(blob)
            blob.extend(source.blob[donor_offset:donor_offset + 0x48])
            struct.pack_into("<Q", blob, destination, int(row["marker"]["uid"], 16))
            stage.rebase_pointer(source, donor_offset + 0x08, blob, destination + 0x08, relocations)
            stage.rebase_pointer(source, donor_offset + 0x20, blob, destination + 0x20, relocations)
        stage.replace_array_pointer(blob, field, new_start, len(survivors) + len(grouped[key]))
        changed_fields.append(field)
    candidate = stage.rebuild_dcb_bytes(source, blob, relocations)
    parsed = parse_candidate(candidate, MASTER)
    after = stage.marker_snapshot(parsed)
    found = [row for row in after if int(row["uid"], 16) in wanted]
    check(len(found) == 53 and {int(row["uid"], 16) for row in found} == set(wanted), "candidate Raven markers incomplete")
    check(not any(int(row["uid"], 16) == TWIN_UID for row in after), "synthetic Twin marker remains active")
    for marker in found:
        row = wanted[int(marker["uid"], 16)]
        check(marker["realm"] == row["realm_id"] and marker["region"] == row["region_id"], "Raven marker owner differs")
        check(marker["icon"] == RAVEN_ICON, "Raven marker lost shared map resource")
    normalized = bytearray(parsed.blob[:len(source.blob)])
    for field in changed_fields:
        normalized[field:field + 16] = source.blob[field:field + 16]
    check(stage.rebuild_dcb_bytes(source, normalized, set(source.relocations)) == source.raw,
          "mapmaster inverse normalization differs")
    return candidate, {
        "source_markers": len(before), "candidate_markers": len(after),
        "active_raven_markers": len(found), "active_twin_markers": 0,
        "changed_region_arrays": len(changed_fields), "inverse_exact": True,
    }


def build_mapcoords(source_path: Path, catalogue: dict) -> tuple[bytes, dict]:
    native = stage.load_native_module()
    source = native.Dcb(source_path)
    before = stage.coordinate_snapshot(source)
    donor = [row for row in before if int(row["uid"], 16) == PROVEN_UID]
    check(len(donor) == 1, "proven map coordinate missing")
    donor_offset = donor[0]["offset"]
    wanted = {int(row["marker"]["uid"], 16): row for row in catalogue["ravens"]}
    existing = {int(row["uid"], 16) for row in before}
    check(not ((set(wanted) - {PROVEN_UID}) & existing), "new Raven coordinate UID collides with source")
    field = source.root("MAP_COORDS_PERM_DATA", 0x40A)
    old_offsets = list(source.array(field, 0x28))
    survivors = [offset for offset in old_offsets if source.unpack("<Q", offset)[0] != TWIN_UID]
    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    new_start = stage.align_blob(blob)
    for old_offset in survivors:
        destination = len(blob)
        blob.extend(source.blob[old_offset:old_offset + 0x28])
        stage.rebase_pointer(source, old_offset + 0x08, blob, destination + 0x08, relocations)
    new_offsets = {}
    for uid, row in sorted(wanted.items()):
        if uid == PROVEN_UID:
            continue
        destination = len(blob)
        blob.extend(source.blob[donor_offset:donor_offset + 0x28])
        struct.pack_into("<Q", blob, destination, uid)
        struct.pack_into("<3e", blob, destination + 0x10, *row["marker"]["position_world"])
        new_offsets[uid] = destination
    strings = {}
    for row in catalogue["ravens"]:
        name = row["marker"]["coordinate_wad"]
        if name not in strings:
            strings[name] = len(blob)
            blob.extend(name.encode("ascii") + b"\0")
    for uid, destination in new_offsets.items():
        target = strings[wanted[uid]["marker"]["coordinate_wad"]]
        struct.pack_into("<q", blob, destination + 0x08, target - (destination + 0x08))
        relocations.add(destination + 0x08)
    stage.replace_array_pointer(blob, field, new_start, len(survivors) + len(new_offsets))
    candidate = stage.rebuild_dcb_bytes(source, blob, relocations)
    parsed = parse_candidate(candidate, COORDS)
    after = stage.coordinate_snapshot(parsed)
    found = [row for row in after if int(row["uid"], 16) in wanted]
    check(len(found) == 53 and {int(row["uid"], 16) for row in found} == set(wanted), "candidate Raven coordinates incomplete")
    check(not any(int(row["uid"], 16) == TWIN_UID for row in after), "synthetic Twin coordinate remains active")
    for coordinate in found:
        row = wanted[int(coordinate["uid"], 16)]
        check(coordinate["wad"] == row["marker"]["coordinate_wad"], "Raven coordinate WAD differs")
        check(coordinate["position"] == row["marker"]["position_world"], "Raven coordinate position differs")
    normalized = bytearray(parsed.blob[:len(source.blob)])
    normalized[field:field + 16] = source.blob[field:field + 16]
    check(stage.rebuild_dcb_bytes(source, normalized, set(source.relocations)) == source.raw,
          "mapcoords inverse normalization differs")
    return candidate, {
        "source_coordinates": len(before), "candidate_coordinates": len(after),
        "active_raven_coordinates": len(found), "active_twin_coordinates": 0,
        "canonical_wad_strings": len(strings), "inverse_exact": True,
    }


def build_pool(source: bytes) -> tuple[bytes, dict]:
    chunks = stage.parse_dcb_chunks(source)
    chunk = stage.one_chunk(chunks, 12)
    data = bytearray(source[chunk["start"]:chunk["end"]])
    count, rows, end = stage.dcb_rows(data)
    raven = [row for row in rows if row["uid"] == RAVEN_ICON_HASH]
    before_capacity = sum(row["capacity"] for row in raven)
    check(before_capacity == 2 and len(raven) == 2, "v3.3 Raven pool capacity changed")
    add = 45 - before_capacity
    inserted = raven[0]["raw"] * add
    after = bytearray(data[:end] + inserted + data[end:])
    struct.pack_into("<I", after, 8, count + add)
    for field in (16, 32):
        struct.pack_into("<q", after, field, struct.unpack_from("<q", data, field)[0] + len(inserted))
    header = bytearray(source[chunk["header"]:chunk["start"]])
    struct.pack_into("<I", header, 4, len(after))
    candidate = source[:chunk["header"]] + header + after + source[chunk["end"]:]
    new_chunk = stage.one_chunk(stage.parse_dcb_chunks(candidate), 12)
    new_data = candidate[new_chunk["start"]:new_chunk["end"]]
    new_count, new_rows, new_end = stage.dcb_rows(new_data)
    after_capacity = sum(row["capacity"] for row in new_rows if row["uid"] == RAVEN_ICON_HASH)
    check(new_count == count + add and after_capacity == 45, "all-Raven pool capacity differs")
    inverse = bytearray(new_data[:end] + new_data[new_end:])
    struct.pack_into("<I", inverse, 8, count)
    inverse[16:24] = data[16:24]
    inverse[32:40] = data[32:40]
    inverse_header = bytearray(candidate[new_chunk["header"]:new_chunk["start"]])
    struct.pack_into("<I", inverse_header, 4, len(inverse))
    normalized = candidate[:new_chunk["header"]] + inverse_header + inverse + candidate[new_chunk["end"]:]
    check(bytes(normalized) == source, "pool inverse normalization differs")
    return candidate, {
        "source_rows": count, "candidate_rows": new_count,
        "raven_capacity_before": before_capacity, "raven_capacity_after": after_capacity,
        "rows_added": add, "inverse_exact": True,
    }


def router_contract() -> dict:
    return {
        "data_driven_entries": 53,
        "exact_collision_object_required_before_uid": True,
        "currMarkerID_alone_infers_raven": False,
        "single_active_target": True,
        "same_raven_second_click_removes": True,
        "stock_and_nornir_delegate_preserved": True,
        "shared_map_resource": RAVEN_ICON,
        "compass_class": "CompletionistRaven",
        "synthetic_twin_removed": True,
        "map_visibility_policy": "Show All, Completionist, or Ravens filter only",
        "fast_travel_map_visibility": False,
        "map_visibility_source": "existing filterButtonMapping/filterIndex plus isOpenedForFastTravel",
        "hidden_map_selection_policy": "disarm exact Raven selection while filtered or in fast travel",
        "raven_filter_scope": "every realm represented by the 53-Raven catalogue",
        "permanent_polling": False,
        "native_snapshot_transport": "loopback-only V1 latest snapshot plus V2 synchronous boundary capture",
        "native_snapshot_port": 43753,
        "native_snapshot_schema": 1,
        "native_boundary_snapshot_schema": 2,
        "native_generation_monotonic": True,
        "native_generation_is_capture_freshness": False,
        "native_generation_role": "ordering only; never sufficient to prove post-load authority",
        "native_boundary_authority": "bridge-owned restoreEpoch observed through V1 then matching echoed boundaryEpoch from synchronous V2 capture before state replacement",
        "native_refresh_before_icon_sync": True,
        "bootstrap_all_false_stability_ms": 750,
        "initial_marker_policy": "hidden_until_atomic_authority",
        "native_static_descriptor_writes": False,
    }


def state_contract() -> dict:
    return {
        "native_field": "ravenKilled",
        "loaded_instance_match": "exact parent quest plus unique native world position",
        "writes_progression": False,
        "unloaded_instance_query": "atomic 53-state native Raven snapshot",
        "lua_application_point": "CompletionistMapV105ApplyPersistedRavenKills",
        "map_open_refresh": "V1 requires valid restoreEpoch; any new nonzero bridge epoch is reconciled through matching V2 before state replacement",
        "native_unavailable_policy": "preserve last-good state and positive event-derived kills; before first authority render no Raven markers",
        "unknown_state_policy": "fail closed hidden until the first atomic 53-Raven authority snapshot",
        "bootstrap_all_false_policy": "explicit=0 absentWadFalse=53 killed=0 requires two accepted observations separated by at least 750ms with no rejection between them",
        "immediate_kill_path": "loaded Raven ravenKilled=true event -> loopback RAVEN_KILLED note -> current restoreEpoch overlay",
        "session_kill_merge": "authoritative decoded saved kills union bridge kill notes from current restoreEpoch",
        "event_false_policy": "defer alive state to atomic 53-Raven authority",
        "event_kill_overlay": "bridge process-local positive kills are unioned with decoded saved kills only inside the current restoreEpoch",
        "event_overlay_clear_policy": "restoreEpoch advance makes previous session-only kill notes ineligible; matching V2 supplies restored saved truth",
        "load_boundary_authority": "native loopback bridge coalesces gameplay OnRestoreCheckpoint notes into restoreEpoch and infers a new epoch when raw authoritative killed state revives; map V1 observes epoch changes and requires matching V2 capture",
        "boundary_epoch_policy": "bridge-owned monotonic restoreEpoch must be echoed as boundaryEpoch by synchronous V2 capture before state replacement",
        "load_boundary_sources": ["native_bridge_restoreEpoch", "OnRestoreCheckpoint_bridge_note", "authoritative_killed_to_alive_inference", "EVT_LoadSaveData_fallback", "EVT_LoadSaveFile_Done_fallback"],
    }


def generate(source_root: Path) -> tuple[dict[str, bytes], dict]:
    source_root = source_root.resolve()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    validate_catalogue(catalogue)
    source = {}
    for relative, expected in SOURCE_HASHES.items():
        raw = (source_root / relative).read_bytes()
        check(sha(raw) == expected, f"source differs from runtime-proven v3.3: {relative}")
        source[relative] = raw
    mapmaster, master_proof = build_mapmaster(source_root / MASTER, catalogue)
    mapcoords, coords_proof = build_mapcoords(source_root / COORDS, catalogue)
    pool, pool_proof = build_pool(source[POOL])
    map_hook = render_lua(catalogue, HERE / "all-ravens-map-runtime.lua", "-- @@RAVEN_CATALOGUE_ROWS@@")
    event_hook = render_lua(catalogue, HERE / "all-ravens-gameplay-events.lua", "-- @@RAVEN_STATE_ROWS@@", True)
    forbidden = ("SetMarkerState", "SetToken", "SetProgress", "IncrementQuestProgress", "StartQuest")
    for token in forbidden:
        check(token not in map_hook.decode("utf-8"), f"map hook progression write token: {token}")
        check(token not in event_hook.decode("utf-8"), f"event hook progression write token: {token}")
    outputs = {
        MASTER: mapmaster,
        COORDS: mapcoords,
        POOL: pool,
        MAP_LUA: source[MAP_LUA] + b"\n" + map_hook,
        EVENT_LUA: source[EVENT_LUA] + b"\n" + event_hook,
    }
    check(all((source_root / rel).read_bytes() == source[rel] for rel in source), "source changed during offline build")
    proof = {
        "schema": 1,
        "result": "ALL_RAVENS_OFFLINE_CANDIDATE_BUILT_NATIVE_DELIVERY_GATE_READY",
        "branch": "codex/all-ravens-release-candidate",
        "base_head": "6023dd419959bcb0645d08a4a4259dfe56a7b07a",
        "catalogue_sha256": sha(CATALOGUE.read_bytes()),
        "catalogue_entries": len(catalogue["ravens"]),
        "realms": ["Alfheim", "Helheim", "Midgard"],
        "source_sha256": SOURCE_HASHES,
        "files": {rel: {"sha256": sha(raw), "bytes": len(raw)} for rel, raw in outputs.items()},
        "proofs": {MASTER: master_proof, COORDS: coords_proof, POOL: pool_proof},
        "router": router_contract(),
        "state": state_contract(),
        "ready_for_runtime_test": True,
        "blocking_issue": None,
        "game_files_written": False,
        "game_launched": False,
        "save_or_progression_touched": False,
    }
    return outputs, proof


def write_or_check(source_root: Path, check_only: bool) -> None:
    outputs, proof = generate(source_root)
    if check_only:
        actual = {path.relative_to(OUTPUT).as_posix() for path in OUTPUT.rglob("*") if path.is_file()}
        check(actual == set(outputs), "candidate file set differs")
        for relative, raw in outputs.items():
            check((OUTPUT / relative).read_bytes() == raw, f"candidate differs: {relative}")
        check(json.loads(REPORT.read_text(encoding="utf-8")) == proof, "candidate proof differs")
        print("ALL_RAVENS_RELEASE_CANDIDATE_REBUILD_VERIFIED")
        return
    for relative, raw in outputs.items():
        stage.write_bytes_atomic(OUTPUT, OUTPUT / relative, raw, "all-Raven offline candidate")
    stage.write_bytes_atomic(REPORT.parent, REPORT, canonical_json(proof).encode("utf-8"), "all-Raven offline proof")
    print(proof["result"])
    print(json.dumps(proof["files"], indent=2, sort_keys=True))
    print("ready_for_runtime_test=true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check(OUTPUT.resolve().is_relative_to((REPO / "build").resolve()), "candidate output escaped build tree")
    check(REPORT.resolve().is_relative_to((REPO / "archive").resolve()), "report escaped archive tree")
    check(not OUTPUT.resolve().is_relative_to(args.source_root.resolve()), "candidate overlaps game source")
    write_or_check(args.source_root, args.check)


if __name__ == "__main__":
    main()
