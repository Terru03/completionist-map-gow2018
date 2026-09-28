#!/usr/bin/env python3
"""Build a chest-only map-art probe over the Raven-safe stock Nornir build."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOURCE = REPO / "build/nornir-native-material-key-isolated-test/source-game-root"
STOCK = REPO / "build/nornir-stock-saved-state-test/candidate/game-root"
MAP_V4 = REPO / "build/nornir-stock-saved-state-v4-test/candidate/game-root"
ART = (REPO.parent / "completionist-map-gow2018-all-ravens-release-candidate"
       / "build/nornir-native-stock-read-02")
OUT = REPO / "build/nornir-one-family-art-probe/candidate/game-root"
REPORT = REPO / "build/nornir-one-family-art-probe/report.json"
WAD = "exec/wad/pc_le/r_ui.wad"
POOL = "exec/dc/pc_le/wad_r_ui.dcb"
MASTER = "exec/dc/pc_le/mapmaster.dcb"
BOOT = "exec/boot-options.json"
MAP = "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"
CHEST = "nornir_chest"
OTHER = ("nornir_seal", "nornir_bell", "nornir_mechanism")
CUSTOM_MAP = "goMapIconCompletionistNornirChest"
PACK = "completionist_v105_nornir_chest"
ART_MANIFEST_SHA256 = "7911b551e5a30deea0cba3f6105e76105d659664fbaaa42407e41e5a158ba640"
WAD_SOURCE_SHA256 = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stock = load("nornir_stock_probe", HERE / "build-nornir-stock-family-test.py")
base = stock.base
logical = base.stage.load_module(
    "nornir_one_family_logical", base.stage.HERE / "build-raven-ui-logical-clone.py")


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def asset(relative: str, manifest: dict) -> bytes:
    raw = (ART / "candidate/game-root" / relative).read_bytes()
    need(sha(raw) == manifest["files"][relative]["sha256"],
         "custom art package differs: " + relative)
    return raw


def remove_family(rows: list[dict], family: str) -> list[dict]:
    title = "".join(part.capitalize() for part in family.split("_"))
    payload_names = {
        "MAT_cm_" + family,
        "MDL_cm_" + family,
        "MDL_cm_" + family + "_hud",
        "goProtoMapIconCompletionist" + title,
        "gomapiconcompletionist" + title.lower(),
        "goProtoCompletionist" + title + "HUD",
        "gocompletionist" + title.lower() + "hud",
    }
    matches = [(i, row) for i, row in enumerate(rows)
               if row["kind"] == 1 and row["data"] and row["name"] in payload_names]
    need(len(matches) == 7, "family resource group count differs: " + family)
    remove = set()
    for index, row in matches:
        start = row["parent"]
        need(start is not None and rows[start]["kind"] == 2,
             "family payload group missing: " + row["name"])
        end = logical.matching_group_end(rows, start)
        need(index in range(start, end + 1), "family group mismatch")
        remove.update(range(start, end + 1))
    textures = [i for i, row in enumerate(rows)
                if row["kind"] in (1, 0x1D) and row["data"] and
                row["name"].startswith("TX_cm_" + family + "_")]
    need(len(textures) == 4, "family texture count differs: " + family)
    remove.update(textures)
    parent = [i for i, row in enumerate(rows)
              if row["kind"] == 1 and not row["data"] and
              row["name"] == "gomapiconcompletionist" + title.lower()]
    need(len(parent) == 1, "family map root link missing: " + family)
    remove.update(parent)
    before = len([row for row in rows if row["data"]])
    result = [row for i, row in enumerate(rows) if i not in remove]
    need(before - len([row for row in result if row["data"]]) == 12,
         "family physical payload count differs: " + family)
    return result


def set_accounting(rows: list[dict], raven: list[dict], families: int) -> None:
    heap, root = logical.payload_records(rows)[:2]
    old_heap, old_root = logical.payload_records(raven)[:2]
    before = logical.read_type_table(old_root["data"])
    increments = {0xA: 1, 0x10001: 2, 0x20001: 2,
                  0x2000C: 1, 0x10015: 2, 0x10005: 1}
    need(set(increments) <= {row["key"] for row in before}, "WAD type row missing")
    total = 0
    for row in before:
        count = row["count"] + families * increments.get(row["key"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"],
                         total, count)
        total += count
    need(total == struct.unpack_from("<I", old_heap["data"], 4)[0] + 9 * families,
         "WAD typed count differs")
    struct.pack_into("<I", heap["data"], 4, total)
    struct.pack_into("<I", root["data"], 0x1C, total)


def one_family_wad(raven_raw: bytes, four_raw: bytes) -> tuple[bytes, dict]:
    raven = logical.parse_wad(raven_raw)
    rows = logical.parse_wad(four_raw)
    need(logical.serialize_wad(raven) == raven_raw and
         logical.serialize_wad(rows) == four_raw, "WAD parse roundtrip failed")
    for family in OTHER:
        rows = logical.parse_wad(logical.serialize_wad(remove_family(rows, family)))
    set_accounting(rows, raven, 1)
    candidate = logical.serialize_wad(rows)
    reparsed = logical.parse_wad(candidate)
    need(logical.serialize_wad(reparsed) == candidate, "one-family WAD roundtrip failed")
    inverse = remove_family(reparsed, CHEST)
    for old, new in zip(logical.payload_records(raven)[:2],
                        logical.payload_records(inverse)[:2]):
        new["data"] = copy.deepcopy(old["data"])
    need(logical.serialize_wad(inverse) == raven_raw,
         "one-family WAD does not invert to exact Raven source")
    return candidate, {"families": [CHEST], "one_material_added": True,
                       "three_families_removed": list(OTHER),
                       "exact_inverse_to_raven": True}


def chest_pool(stock_raw: bytes) -> tuple[bytes, dict]:
    chunk = base.stage.one_chunk(base.stage.parse_dcb_chunks(stock_raw), 12)
    blob = bytearray(stock_raw)
    count, rows, _ = base.stage.dcb_rows(blob[chunk["start"]:chunk["end"]])
    need(count == 389, "stock UI pool count differs")
    old = base.name_hash(stock.ART[CHEST])
    new = base.name_hash(CUSTOM_MAP)
    need(old != new and all(row["uid"] != new for row in rows),
         "custom chest pool already present")
    indices = [i for i, row in enumerate(rows) if row["uid"] == old and i >= 301]
    need(len(indices) == 22, "stock chest pool row count differs")
    for index in indices:
        offset = chunk["start"] + 0x90 + index * 16
        need(struct.unpack_from("<Q", blob, offset)[0] == old,
             "UI pool row offset differs")
        struct.pack_into("<Q", blob, offset, new)
    changed = bytes(blob)
    candidate_chunk = base.stage.one_chunk(base.stage.parse_dcb_chunks(changed), 12)
    new_count, new_rows, _ = base.stage.dcb_rows(
        changed[candidate_chunk["start"]:candidate_chunk["end"]])
    need(new_count == 389 and
         Counter(row["uid"] for row in new_rows[301:])[new] == 22 and
         [row["raw"] for row in new_rows[:301]] ==
         [row["raw"] for row in rows[:301]], "custom chest pool readback differs")
    for index in indices:
        struct.pack_into("<Q", blob, chunk["start"] + 0x90 + index * 16, old)
    need(bytes(blob) == stock_raw, "custom chest pool inverse differs")
    return changed, {"chest_custom_rows": 22, "stock_child_rows": 66,
                     "raven_prefix_unchanged": 301, "exact_inverse": True}


def chest_master(raven_game: Path, stock_raw: bytes) -> tuple[bytes, dict]:
    definitions = base.rows()
    result, _ = base.build_map(
        base.Dcb(raven_game / MASTER), definitions, False,
        lambda row: CUSTOM_MAP if row["family"] == CHEST else
        stock.ART[row["family"]])
    native = base.stage.load_native_module()
    before = base.stage.marker_snapshot(
        base.stage.parse_native_candidate(native, Path(MASTER), stock_raw))
    after = base.stage.marker_snapshot(
        base.stage.parse_native_candidate(native, Path(MASTER), result))
    need(len(before) == len(after), "map marker count changed")
    changes = [(a, b) for a, b in zip(before, after) if a["icon"] != b["icon"]]
    need(len(changes) == 22 and all(a["icon"] == stock.ART[CHEST] and
                                    b["icon"] == CUSTOM_MAP and
                                    all(a[k] == b[k] for k in ("uid", "realm", "region"))
                                    for a, b in changes),
         "map change goes beyond 22 chest resources")
    return result, {"chest_resource_changes": 22,
                    "raven_and_children_unchanged": True}


def boot_options(raven_raw: bytes) -> bytes:
    options = json.loads(raven_raw)
    packs = options["patch-texpacks"]
    entry = "../../patch/pc_le/" + PACK
    need(entry not in packs, "chest texture pack already registered")
    packs.append(entry)
    candidate = (json.dumps(options, indent=2) + "\n").encode()
    check = json.loads(candidate)
    check["patch-texpacks"].remove(entry)
    need(check == json.loads(raven_raw), "boot options changed outside chest pack")
    return candidate


def build() -> tuple[dict[str, bytes], dict]:
    manifest_raw = (ART / "manifest.json").read_bytes()
    need(sha(manifest_raw) == ART_MANIFEST_SHA256, "art manifest differs")
    manifest = json.loads(manifest_raw)
    raven_wad = (SOURCE / WAD).read_bytes()
    need(sha(raven_wad) == WAD_SOURCE_SHA256, "Raven WAD source differs")
    stock_report = json.loads((REPO / "build/nornir-stock-saved-state-test/report.json")
                              .read_text(encoding="utf-8"))
    v4_report = json.loads((REPO / "build/nornir-stock-saved-state-v4-test/report.json")
                           .read_text(encoding="utf-8"))
    stock_master = (STOCK / MASTER).read_bytes()
    stock_pool = (STOCK / POOL).read_bytes()
    map_lua = (MAP_V4 / MAP).read_bytes()
    for relative, raw in ((MASTER, stock_master), (POOL, stock_pool)):
        need(sha(raw) == stock_report["files"][relative]["sha256"],
             "stock artifact differs: " + relative)
    need(sha(map_lua) == v4_report["files"][MAP]["after"],
         "v4 checkpoint map differs")
    wad, wad_proof = one_family_wad(raven_wad, asset(WAD, manifest))
    pool, pool_proof = chest_pool(stock_pool)
    master, master_proof = chest_master(SOURCE, stock_master)
    outputs = {WAD: wad, POOL: pool, MASTER: master,
               BOOT: boot_options((SOURCE / BOOT).read_bytes())}
    for suffix in (".texpack", ".texpack.toc"):
        relative = "exec/patch/pc_le/" + PACK + suffix
        outputs[relative] = asset(relative, manifest)
    return outputs, {
        "schema": 1, "kind": "NORNIR_CHEST_ONLY_MAP_ART_PROBE",
        "status": "OFFLINE_BUILT_NOT_INSTALLED",
        "raven_wad_sha256": sha(raven_wad),
        "source_stock_master_sha256": sha(stock_master),
        "source_stock_pool_sha256": sha(stock_pool),
        "untouched_map_lua_sha256": sha(map_lua),
        "untouched_compass_class_sha256": stock.UNTOUCHED[
            "exec/dc/pc_le/wad_r_perm.dcb"],
        "proof": {WAD: wad_proof, POOL: pool_proof, MASTER: master_proof},
        "files": {name: {"sha256": sha(raw), "bytes": len(raw)}
                  for name, raw in sorted(outputs.items())},
        "live_question": "Does one custom chest map material leave Raven art intact?",
    }


def main() -> None:
    outputs, report = build()
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_CHEST_ONLY_MAP_ART_PROBE_OFFLINE_BUILT")
    print(REPORT)


if __name__ == "__main__":
    main()
