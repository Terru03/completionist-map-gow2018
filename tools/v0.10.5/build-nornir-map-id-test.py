#!/usr/bin/env python3
"""Build a reversible 88-ID Nornir map placement test from the installed Raven base.

Uses a stock quest icon. It never edits Raven artwork, compass classes, saves,
or progression. Completion state is deliberately outside this diagnostic gate.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from raven_catalogue import Dcb, name_hash

spec = importlib.util.spec_from_file_location(
    "nornir_id_raven_builder", HERE / "build-all-ravens-release-candidate.py")
raven = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(raven)
stage = raven.stage

GAME = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar")
OUT = REPO / "build/nornir-id-test/candidate/game-root"
REPORT = REPO / "build/nornir-id-test/report.json"
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
NAMESPACE = REPO / "config/collectibles/v0.10.5/nornir-marker-namespace.json"
LUA_TEMPLATE = HERE / "nornir-map-id-test.lua"
MASTER = "exec/dc/pc_le/mapmaster.dcb"
COORDS = "exec/dc/pc_le/mapcoords.dcb"
POOL = "exec/dc/pc_le/wad_r_ui.dcb"
MAP_LUA = "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
RUNIC_LUA = ("mods/lua/gameart/scripts/levels/gameplaymodules/progression/"
             "interact_chest_runic.lua")
STANDARD_LUA = ("mods/lua/gameart/scripts/levels/gameplaymodules/progression/"
                "interact_chest_standard.lua")
STOCK_RUNIC = (REPO.parent / "completionist-map-gow2018/dist/gowlua-src/"
               "gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua")
STOCK_STANDARD = (REPO.parent / "completionist-map-gow2018/dist/gowlua-src/"
                  "gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua")
RUNIC_EVENTS = HERE / "nornir-chest-attempt-events.lua"
STANDARD_EVENTS = HERE / "nornir-reward-open-events.lua"
STOCK_RUNIC_SHA256 = "e232e0163cce8767b509c88db1734a19d1a8d0b438b6c87824f1944180b770ac"
STOCK_STANDARD_SHA256 = "943021f321c708561e62d4c9b6926c01b3c131c2057fbed7e4c136dbed707bdc"
SOURCE = {
    MASTER: "7d1d5e05315dce17326712a95901e1e753b6c14c4f1a71012ca337ae7ee9b223",
    COORDS: "d6786f9734473fa7bdb8eff39aadac4f3fb2ecd4a83d56bfc5d2832c17435514",
    POOL: "2cebb4bfc0a4cf76c0d4145b7408be10ad7c6ad2350d571263c5050c7ab6480a",
    MAP_LUA: "048ed3a5bfb5225da054683bc1167f58e876a3bb42e644b7d60887265e40fa15",
}
STOCK_RESOURCE = "goMapIconSecondaryQuest"
STOCK_HASH = name_hash(STOCK_RESOURCE)


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def rows() -> list[dict]:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8-sig"))
    namespace = json.loads(NAMESPACE.read_text(encoding="utf-8-sig"))
    wanted = {item["uid"] for group in namespace["groups"]
              for item in [group["parent"], *group["children"]]}
    result = [row for row in catalogue["collectibles"]
              if row["family"].startswith("nornir_")]
    need(len(result) == 88 and {row["marker"]["uid"] for row in result} == wanted,
         "Nornir catalogue differs from reserved family namespace")
    need(all(row["marker"]["position_world"] is not None and
             row["marker"]["coordinate_wad"] for row in result),
         "Nornir coordinate missing")
    return sorted(result, key=lambda row: row["marker"]["uid"])


def parsed(raw: bytes, label: str) -> Dcb:
    return raven.parse_candidate(raw, label)


def build_map(source: Dcb, definitions: list[dict], coordinates: bool,
              resource_for=None, expected_count: int = 88) -> tuple[bytes, dict]:
    snapshot = stage.coordinate_snapshot if coordinates else stage.marker_snapshot
    before = snapshot(source)
    before_uid = {row["uid"] for row in before}
    wanted = {row["marker"]["uid"]: row for row in definitions}
    need(len(wanted) == len(definitions) == expected_count and
         expected_count > 0 and not before_uid.intersection(wanted),
         "collectible count or UID collision with installed map data")
    donor = next(row["offset"] for row in before
                 if row["uid"] == f"{raven.PROVEN_UID:016X}")
    blob = bytearray(source.blob)
    relocations = set(source.relocations)
    changed_fields = []
    stride = 0x28 if coordinates else 0x48
    pointers = (8,) if coordinates else (8, 32)
    if coordinates:
        grouped = {source.root("MAP_COORDS_PERM_DATA", 0x40A): definitions}
    else:
        region_index = raven.map_regions(source)
        grouped = defaultdict(list)
        for row in definitions:
            key = (int(row["realm_id"], 16), int(row["region_id"], 16))
            need(key in region_index, f"missing native map region {key}")
            grouped[region_index[key] + 0x38].append(row)

    for field, additions in sorted(grouped.items()):
        old_offsets = list(source.array(field, stride))
        start = stage.align_blob(blob)
        for old_offset in old_offsets:
            dest = len(blob)
            blob.extend(source.blob[old_offset:old_offset + stride])
            for at in pointers:
                stage.rebase_pointer(source, old_offset + at, blob, dest + at, relocations)
        new_rows = []
        for row in additions:
            dest = len(blob)
            blob.extend(source.blob[donor:donor + stride])
            new_rows.append((dest, row))
            for at in pointers:
                stage.rebase_pointer(source, donor + at, blob, dest + at, relocations)
            struct.pack_into("<Q", blob, dest, int(row["marker"]["uid"], 16))
            if coordinates:
                struct.pack_into("<3e", blob, dest + 16, *row["marker"]["position_world"])
        for dest, row in new_rows:
            string = (row["marker"]["coordinate_wad"] if coordinates else
                      resource_for(row) if resource_for is not None else STOCK_RESOURCE)
            string_at = len(blob)
            blob.extend(string.encode("ascii") + b"\0")
            struct.pack_into("<q", blob, dest + 8, string_at - (dest + 8))
        stage.replace_array_pointer(blob, field, start, len(old_offsets) + len(additions))
        relocations.add(field)
        changed_fields.append(field)

    candidate = stage.rebuild_dcb_bytes(source, blob, relocations)
    after_dcb = parsed(candidate, "mapcoords.dcb" if coordinates else "mapmaster.dcb")
    after = snapshot(after_dcb)
    need(len(after) == len(before) + expected_count, "new marker count differs")
    survivors = [row for row in after if row["uid"] not in wanted]
    need([{k: v for k, v in row.items() if k != "offset"} for row in survivors] ==
         [{k: v for k, v in row.items() if k != "offset"} for row in before],
         "existing marker semantics changed")
    for row in before:
        off = row["offset"]
        need(after_dcb.blob[off:off + stride] == source.blob[off:off + stride],
             "existing marker physical bytes changed")
    for row in after:
        definition = wanted.get(row["uid"])
        if definition is None:
            continue
        if coordinates:
            expected = list(struct.unpack("<3e", struct.pack("<3e", *definition["marker"]["position_world"])))
            need(row["wad"] == definition["marker"]["coordinate_wad"] and
                 row["position"] == expected, "Nornir coordinate reparse differs")
        else:
            expected_resource = resource_for(definition) if resource_for is not None else STOCK_RESOURCE
            need(row["icon"] == expected_resource and
                 row["realm"] == definition["realm_id"] and
                 row["region"] == definition["region_id"],
                 "Nornir marker binding differs")
    normalized = bytearray(after_dcb.blob[:len(source.blob)])
    for field in changed_fields:
        normalized[field:field + 16] = source.blob[field:field + 16]
    need(stage.rebuild_dcb_bytes(source, normalized, set(source.relocations)) == source.raw,
         "map inverse is not exact Raven baseline")
    return candidate, {"added": expected_count, "existing_rows_preserved": True,
                       "exact_inverse": True, "changed_arrays": len(changed_fields)}


def build_pool(raw: bytes) -> tuple[bytes, dict]:
    chunk = stage.one_chunk(stage.parse_dcb_chunks(raw), 12)
    data = bytearray(raw[chunk["start"]:chunk["end"]])
    count, old_rows, end = stage.dcb_rows(data)
    need(count == 301 and any(row["uid"] == STOCK_HASH for row in old_rows),
         "stock quest icon pool missing")
    raven_rows = [row["raw"] for row in old_rows if row["uid"] == stage.RAVEN_MAP_HASH]
    need(len(raven_rows) == 45, "Raven pool baseline differs")
    additional = struct.pack("<QH6x", STOCK_HASH, 1) * 68
    after = bytearray(data[:end] + additional + data[end:])
    struct.pack_into("<I", after, 8, count + 68)
    for at in (16, 32):
        struct.pack_into("<q", after, at, struct.unpack_from("<q", data, at)[0] + len(additional))
    header = bytearray(raw[chunk["header"]:chunk["start"]])
    struct.pack_into("<I", header, 4, len(after))
    candidate = raw[:chunk["header"]] + header + after + raw[chunk["end"]:]
    new_chunk = stage.one_chunk(stage.parse_dcb_chunks(candidate), 12)
    new_data = candidate[new_chunk["start"]:new_chunk["end"]]
    new_count, new_rows, new_end = stage.dcb_rows(new_data)
    need(new_count == count + 68 and
         [row["raw"] for row in new_rows[:count]] == [row["raw"] for row in old_rows] and
         [row["raw"] for row in new_rows if row["uid"] == stage.RAVEN_MAP_HASH] == raven_rows,
         "Raven or stock pool row changed")
    inverse = bytearray(new_data[:end] + new_data[new_end:])
    inverse[8:12] = data[8:12]
    inverse[16:24] = data[16:24]
    inverse[32:40] = data[32:40]
    inverse_header = bytearray(candidate[new_chunk["header"]:new_chunk["start"]])
    struct.pack_into("<I", inverse_header, 4, len(inverse))
    restored = (candidate[:new_chunk["header"]] + inverse_header + inverse +
                candidate[new_chunk["end"]:])
    need(restored == raw, "pool inverse is not exact Raven baseline")
    return candidate, {"rows_added": 68, "raven_rows_unchanged": 45,
                       "exact_inverse": True}


def build_lua(raw: bytes, definitions: list[dict],
              template_path: Path = LUA_TEMPLATE) -> tuple[bytes, dict]:
    template = template_path.read_text(encoding="utf-8")
    token = "-- @@NORNIR_ROWS@@"
    need(template.count(token) == 1, "Lua insertion point changed")
    children = defaultdict(list)
    for row in definitions:
        if row["family"] != "nornir_chest":
            children[row["progression"]["parent_catalogue_id"]].append(row)
    def lua_literal(value: str | None) -> str:
        return "nil" if value is None else json.dumps(value)

    entries = []
    keys = set()
    for row in definitions:
        uid = int(row["marker"]["uid"], 16)
        signed = uid if uid < (1 << 63) else uid - (1 << 64)
        parent_id = row["progression"].get("parent_catalogue_id")
        key = None
        if row["family"] == "nornir_chest":
            siblings = children[row["catalogue_id"]]
            need(len(siblings) == 3, "Nornir chest child count differs")
            refs = sorted(child["native"]["reference_name"].lower() for child in siblings)
            key = row["marker"]["coordinate_wad"].lower() + "|" + "|".join(refs)
            need(key not in keys, "Nornir chest event identity collision")
            keys.add(key)
        entries.append("    {Name=%s,UidHex=%s,IdString=%s,Family=%s,Realm=%s,CatalogueId=%s,ParentId=%s,Reference=%s,EventKey=%s,Class=%s}," %
                       tuple(lua_literal(value) for value in
                             (row["marker"]["name"], row["marker"]["uid"],
                              str(signed), row["family"], row["realm"],
                              row["catalogue_id"], parent_id,
                              row["native"].get("reference_name"), key,
                              row["marker"].get("compass_class"))))
    appended = template.replace(token, "\n".join(entries)).encode("utf-8")
    need(raw.endswith(b"-- END COMPLETIONIST RAVEN ONLY CLEANUP\n"),
         "Raven Lua baseline tail changed")
    need(all(forbidden not in appended for forbidden in
             (b"SetMarkerState", b"SetToken", b"IncrementQuestProgress", b"StartQuest")),
         "Lua diagnostic contains progression write API")
    return raw + b"\n" + appended, {"raven_lua_exact_prefix": True,
                                     "rows": len(entries), "parent_event_keys": len(keys),
                                     "children_gate": "exact_locked_chest_attempt"}


def build_chest_lua(stock_path: Path, expected: str,
                    events_path: Path) -> tuple[bytes, dict]:
    stock = stock_path.read_bytes()
    need(sha(stock) == expected, f"stock chest script differs: {stock_path.name}")
    events = events_path.read_bytes()
    need(not any(value in events for value in
                 (b"SetMarkerState", b"IncrementQuestProgress", b"StartQuest")),
         "runic event hook changes progression")
    return stock + b"\n" + events, {"stock_lua_exact_prefix": True,
                                     "stock_sha256": expected}


def build(game: Path = GAME) -> tuple[dict[str, bytes], dict]:
    definitions = rows()
    source = {relative: (game / relative).read_bytes() for relative in SOURCE}
    for relative, expected in SOURCE.items():
        need(sha(source[relative]) == expected, f"installed Raven base differs: {relative}")
    need(sha((game / "exec/wad/pc_le/r_ui.wad").read_bytes()) ==
         "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
         "Raven artwork WAD base differs")
    master, master_proof = build_map(Dcb(game / MASTER), definitions, False)
    coords, coords_proof = build_map(Dcb(game / COORDS), definitions, True)
    pool, pool_proof = build_pool(source[POOL])
    lua, lua_proof = build_lua(source[MAP_LUA], definitions)
    runic_lua, runic_proof = build_chest_lua(
        STOCK_RUNIC, STOCK_RUNIC_SHA256, RUNIC_EVENTS)
    standard_lua, standard_proof = build_chest_lua(
        STOCK_STANDARD, STOCK_STANDARD_SHA256, STANDARD_EVENTS)
    outputs = {MASTER: master, COORDS: coords, POOL: pool, MAP_LUA: lua,
               RUNIC_LUA: runic_lua, STANDARD_LUA: standard_lua}
    need(all((game / relative).read_bytes() == raw for relative, raw in source.items()),
         "game source changed during build")
    return outputs, {
        "schema": 1,
        "kind": "NORNIR_ID_ISOLATED_MAP_PLACEMENT_TEST",
        "status": "OFFLINE_BUILT",
        "source_sha256": SOURCE,
        "files": {relative: {"sha256": sha(raw), "bytes": len(raw)}
                  for relative, raw in outputs.items()},
        "catalogue_sha256": sha(CATALOGUE.read_bytes()),
        "namespace_sha256": sha(NAMESPACE.read_bytes()),
        "proof": {MASTER: master_proof, COORDS: coords_proof,
                  POOL: pool_proof, MAP_LUA: lua_proof,
                  RUNIC_LUA: runic_proof, STANDARD_LUA: standard_proof},
        "untouched_raven_wad_sha256": sha((game / "exec/wad/pc_le/r_ui.wad").read_bytes()),
        "untouched_compassgraph_sha256": sha((game / "exec/dc/pc_le/compassgraph.dcb").read_bytes()),
        "new_marker_count": 88,
        "child_marker_count": 66,
        "completion_state_enabled": "loaded_event_only",
        "dedicated_nornir_art_enabled": False,
    }


def main() -> None:
    outputs, report = build()
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("NORNIR_ID_TEST_OFFLINE_BUILT rows=88 children=66 raven_inverse=exact")
    print(REPORT)


if __name__ == "__main__":
    main()
