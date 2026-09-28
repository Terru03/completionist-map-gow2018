#!/usr/bin/env python3
"""Build separate Nornir map art, marker IDs, and compass classes from pinned inputs."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location(
    "nornir_id_base", HERE / "build-nornir-map-id-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
import nornir_raven_handoff as handoff

ART_PACKAGE = (REPO.parent / "completionist-map-gow2018-all-ravens-release-candidate"
               / "build/nornir-native-stock-read-02")
ART_MANIFEST_SHA256 = "7911b551e5a30deea0cba3f6105e76105d659664fbaaa42407e41e5a158ba640"
OUT = REPO / "build/nornir-native-test/candidate/game-root"
REPORT = REPO / "build/nornir-native-test/report.json"
WAD = "exec/wad/pc_le/r_ui.wad"
PERM = "exec/dc/pc_le/wad_r_perm.dcb"
BOOT = "exec/boot-options.json"
GRAPH = "exec/dc/pc_le/compassgraph.dcb"
TEMPLATE = HERE / "nornir-native-map.lua"
BASE_FILES = {base.MASTER, base.COORDS, base.POOL, base.MAP_LUA,
              base.RUNIC_LUA, base.STANDARD_LUA}


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_art_wad(source: bytes, candidate: bytes) -> dict:
    logical = base.stage.load_module(
        "nornir_native_art_audit",
        base.stage.HERE / "build-raven-ui-logical-clone.py")
    original = logical.parse_wad(source)
    changed = logical.parse_wad(candidate)
    need(logical.serialize_wad(changed) == candidate, "custom art WAD fails roundtrip")
    accounting = {id(row) for row in logical.payload_records(original)[:2]}

    def key(row: dict) -> tuple:
        return (row["kind"], row["name"], row["id"], sha(bytes(row["data"])))

    before = Counter(key(row) for row in original if id(row) not in accounting)
    after = Counter(key(row) for row in changed)
    need(not before - after, "Raven or stock WAD record changed")
    material_keys = {}
    for family in ("nornir_chest", "nornir_seal", "nornir_bell", "nornir_mechanism"):
        materials = [row for row in changed if row["name"] == "MAT_cm_" + family
                     and len(row["data"]) >= 0x28]
        need(len(materials) == 1, f"Nornir material missing: {family}")
        material_keys[family] = int.from_bytes(materials[0]["data"][0x10:0x18], "little")
        for label in ("diff", "emis"):
            names = [row["name"] for row in changed
                     if row["name"].startswith("TX_cm_" + family + "_" + label)]
            need(len(names) >= 2, f"Nornir texture missing: {family}/{label}")
            definitions = [row for row in changed if row["name"] in names
                           and row["kind"] == 1 and len(row["data"]) >= 0xA4]
            need(len(definitions) == 1 and
                 bytes(definitions[0]["data"][0x0C:0x44]).split(b"\0", 1)[0]
                 == definitions[0]["name"].encode("ascii"),
                 f"Nornir texture embedded name differs: {family}/{label}")
    old_material_keys = {int.from_bytes(row["data"][0x10:0x18], "little")
                         for row in original if row["name"].startswith("MAT_")
                         and len(row["data"]) >= 0x28}
    need(len(set(material_keys.values())) == 4 and
         not old_material_keys.intersection(material_keys.values()),
         "Nornir material runtime key aliases Raven")
    return {"original_non_accounting_records_preserved": sum(before.values()),
            "four_unique_material_keys": True,
            "texture_definition_names_distinct": True}


def validate_pool(source: bytes, candidate: bytes) -> dict:
    original_chunk = base.stage.one_chunk(base.stage.parse_dcb_chunks(source), 12)
    candidate_chunk = base.stage.one_chunk(base.stage.parse_dcb_chunks(candidate), 12)
    count, rows, _ = base.stage.dcb_rows(
        source[original_chunk["start"]:original_chunk["end"]])
    new_count, new_rows, _ = base.stage.dcb_rows(
        candidate[candidate_chunk["start"]:candidate_chunk["end"]])
    need(new_count == count + 96 and
         [r["raw"] for r in new_rows[:count]] == [r["raw"] for r in rows],
         "Raven or stock UI pool changed")
    for family in ("NornirChest", "NornirSeal", "NornirBell", "NornirMechanism"):
        for resource in ("goMapIconCompletionist" + family,
                         "goCompletionist" + family + "HUD"):
            uid = base.name_hash(resource)
            need(sum(row["uid"] == uid for row in new_rows[count:]) >= 2,
                 f"Nornir UI pool resource missing: {resource}")
    return {"existing_pool_rows_preserved": count, "new_rows": 96}


def build(game: Path = base.GAME) -> tuple[dict[str, bytes], dict]:
    manifest_raw = (ART_PACKAGE / "manifest.json").read_bytes()
    need(sha(manifest_raw) == ART_MANIFEST_SHA256, "art package manifest differs")
    manifest = json.loads(manifest_raw)
    need(manifest.get("proof", {}).get(WAD, {}).get("inverse_exact") is True and
         manifest.get("proof", {}).get(PERM, {}).get("existing_exports_preserved") is True,
         "custom art isolation proof missing")
    source_paths = {**base.SOURCE, WAD: manifest["source_sha256"][WAD],
                    PERM: manifest["source_sha256"][PERM],
                    BOOT: manifest["source_sha256"][BOOT]}
    source = {rel: (game / rel).read_bytes() for rel in source_paths}
    for rel, expected in source_paths.items():
        need(sha(source[rel]) == expected, f"installed Raven base differs: {rel}")
    need(sha((game / GRAPH).read_bytes()) == manifest["files"][GRAPH]["sha256"],
         "Raven compass graph differs")
    asset_paths = set(manifest["files"]) - (BASE_FILES - {base.POOL}) - {GRAPH}
    need(len(asset_paths) == 12 and {WAD, base.POOL, PERM, BOOT} <= asset_paths,
         "custom art asset list differs")
    assets = {}
    for rel in sorted(asset_paths):
        data = (ART_PACKAGE / "candidate/game-root" / rel).read_bytes()
        need(sha(data) == manifest["files"][rel]["sha256"],
             f"custom art asset differs: {rel}")
        if rel not in source_paths:
            need(not (game / rel).exists(), f"Nornir texture pack already exists: {rel}")
        assets[rel] = data
    wad_proof = validate_art_wad(source[WAD], assets[WAD])
    pool_proof = validate_pool(source[base.POOL], assets[base.POOL])
    definitions = base.rows()
    master, master_proof = base.build_map(
        base.Dcb(game / base.MASTER), definitions, False,
        lambda row: row["marker"]["map_resource"])
    coords, coords_proof = base.build_map(
        base.Dcb(game / base.COORDS), definitions, True)
    raven_with_handoff = handoff.inject(source[base.MAP_LUA])
    lua, lua_proof = base.build_lua(raven_with_handoff, definitions, TEMPLATE)
    need(lua.startswith(raven_with_handoff) and
         handoff.inject(source[base.MAP_LUA]) == raven_with_handoff,
         "Raven handoff is not exact")
    runic, runic_proof = base.build_chest_lua(
        base.STOCK_RUNIC, base.STOCK_RUNIC_SHA256, base.RUNIC_EVENTS)
    standard, standard_proof = base.build_chest_lua(
        base.STOCK_STANDARD, base.STOCK_STANDARD_SHA256, base.STANDARD_EVENTS)
    outputs = {**assets, base.MASTER: master, base.COORDS: coords,
               base.MAP_LUA: lua, base.RUNIC_LUA: runic,
               base.STANDARD_LUA: standard}
    need(len(outputs) == 17, "native test file count differs")
    need(all((game / rel).read_bytes() == raw for rel, raw in source.items()),
         "installed game source changed during build")
    return outputs, {
        "schema": 1, "kind": "NORNIR_SEPARATE_NATIVE_MARKERS_TEST",
        "status": "OFFLINE_BUILT", "source_sha256": source_paths,
        "source_art_manifest_sha256": ART_MANIFEST_SHA256,
        "files": {rel: {"sha256": sha(raw), "bytes": len(raw)}
                  for rel, raw in sorted(outputs.items())},
        "proof": {base.MASTER: master_proof, base.COORDS: coords_proof,
                  base.POOL: pool_proof, WAD: wad_proof,
                  base.MAP_LUA: lua_proof,
                  base.RUNIC_LUA: runic_proof,
                  base.STANDARD_LUA: standard_proof},
        "new_marker_count": 88, "child_marker_count": 66,
        "renderer": "dedicated_nornir_family_art",
        "compass": "dedicated_nornir_family_classes",
        "children_gate": "exact_locked_chest_attempt",
        "unchanged_compassgraph_sha256": sha((game / GRAPH).read_bytes()),
    }


def main() -> None:
    outputs, report = build()
    for rel, data in outputs.items():
        target = OUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_NATIVE_TEST_OFFLINE_BUILT rows=88 children=66 raven_rows=preserved")
    print(REPORT)


if __name__ == "__main__":
    main()
