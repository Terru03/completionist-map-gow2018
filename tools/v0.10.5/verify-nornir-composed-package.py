#!/usr/bin/env python3
"""Read-only Raven + Nornir structural verifier for the 53-Raven package.

An overlay is a sparse candidate game-root; later overlays take precedence.
The frozen Raven files and manifest are pinned independently of the candidate.
Structural preservation does not establish runtime renderer isolation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RAVEN_ROOT = (REPO.parent / "completionist-map-gow2018-all-ravens-release-candidate"
              / "build/raven-clean-baseline/package/game-root")
GAME = Path(r"G:\SteamLibrary\steamapps\common\GodOfWar")
sys.path.insert(0, str(HERE))
from raven_catalogue import Dcb, name_hash  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load("nornir_composed_stage", HERE.parent / "v0.10.4/build-raven-twin-stage-a-offline.py")
logical = load("nornir_composed_wad", HERE.parent / "v0.10.4/build-raven-ui-logical-clone.py")
legacy = load("nornir_composed_perm", HERE.parent / "v0.10.4/verify-raven-production-state.py")

WAD = "exec/wad/pc_le/r_ui.wad"
UI = "exec/dc/pc_le/wad_r_ui.dcb"
PERM = "exec/dc/pc_le/wad_r_perm.dcb"
MASTER = "exec/dc/pc_le/mapmaster.dcb"
COORDS = "exec/dc/pc_le/mapcoords.dcb"
GRAPH = "exec/dc/pc_le/compassgraph.dcb"
BOOT = "exec/boot-options.json"
PACK = "exec/patch/pc_le/completionist_v104_raven_map.texpack"
TOC = PACK + ".toc"
PINNED = {
    WAD: "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    UI: "2cebb4bfc0a4cf76c0d4145b7408be10ad7c6ad2350d571263c5050c7ab6480a",
    PERM: "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    MASTER: "7d1d5e05315dce17326712a95901e1e753b6c14c4f1a71012ca337ae7ee9b223",
    COORDS: "d6786f9734473fa7bdb8eff39aadac4f3fb2ecd4a83d56bfc5d2832c17435514",
    GRAPH: "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    BOOT: "8bbac2bb2a522dfacf69c676e48665686f722289a44127518ae4e8ca299a0e92",
    PACK: "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7",
    TOC: "67cceea0d91298881f4426bf0ce5e8883da45a82905921313004df618d959053",
}
KNOWN_FAILED_LIVE_WADS = {
    "ead7d42b31e08bac7fe98085b54076e008fad2a65cc88db66fc3c1b3048b60bd",
    "60c95709e027637e749a460c64a5cc04a661eca6f4da8a3bef36640ffbeb7130",
    "b1ba84815a90127e9319968d18fd6a0433d1294128624a40872fa623bcaf4186",
    "d32994c885bef8ba598d3885b58de0df2909c0d3308994908229c93d2341da31",
    "aebebaee06c91e1f5663cf25624a44b3401d74645f837d4cc0b33e4e4ba52ef5",
}


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source(root: Path, overlays: list[Path], relative: str) -> Path:
    for overlay in reversed(overlays):
        path = overlay / relative
        if path.is_file():
            return path
    path = root / relative
    need(path.is_file(), f"missing candidate file: {path}")
    return path


def verify_baseline(root: Path) -> dict:
    actual = {}
    for relative, expected in PINNED.items():
        path = root / relative
        need(path.is_file(), f"frozen Raven file missing: {path}")
        actual[relative] = sha(path.read_bytes())
        need(actual[relative] == expected, f"frozen Raven baseline drift: {relative}")
    return actual


def verify_wad(before: bytes, after: bytes) -> dict:
    original = logical.parse_wad(before)
    composed = logical.parse_wad(after)
    need(logical.serialize_wad(original) == before and
         logical.serialize_wad(composed) == after, "WAD parse/serialize mismatch")
    old_payloads = logical.payload_records(original)
    new_payloads = logical.payload_records(composed)
    need(len(old_payloads) >= 2 and len(new_payloads) >= 2, "WAD accounting missing")
    # Only the first two accounting payloads may change. All other original
    # physical records, including the full Raven visual dependency chain,
    # must survive in their original order with their exact header and data.
    accounting = {id(old_payloads[0]), id(old_payloads[1])}
    baseline = [r for r in original if id(r) not in accounting]
    old_index = 0
    additions = []
    for row in composed:
        if old_index < len(baseline) and logical.record_bytes(row) == logical.record_bytes(baseline[old_index]):
            old_index += 1
        elif row is new_payloads[0] or row is new_payloads[1]:
            continue
        else:
            additions.append(row)
    need(old_index == len(baseline),
         f"Raven/stock WAD record changed or removed at baseline record {old_index}")
    need(len(new_payloads) >= len(old_payloads), "WAD payload count shrank")
    old_table = logical.read_type_table(old_payloads[1]["data"])
    new_table = logical.read_type_table(new_payloads[1]["data"])
    need([r["key"] for r in old_table] == [r["key"] for r in new_table] and
         all(n["count"] >= o["count"] for o, n in zip(old_table, new_table)),
         "WAD type accounting changed an existing type")
    old_total = struct.unpack_from("<I", old_payloads[0]["data"], 4)[0]
    new_total = struct.unpack_from("<I", new_payloads[0]["data"], 4)[0]
    need(new_total - old_total ==
         sum(n["count"] - o["count"] for o, n in zip(old_table, new_table)),
         "WAD heap and type accounting disagree")
    shared_stock = {logical.record_bytes(r) for r in original
                    if r["name"] == "SCP_BoatDock" and r["data"]}
    nornir_prefixes = ("MAT_cm_nornir", "MDL_cm_nornir", "MG_cm_nornir",
                       "TX_cm_nornir",
                       "goProtoMapIconCompletionistNornir", "gomapiconcompletionistnornir",
                       "goProtoCompletionistNornir", "gocompletionistnornir")
    need(all(r["name"].startswith(nornir_prefixes) or
             (r["name"] == "SCP_BoatDock" and logical.record_bytes(r) in shared_stock)
             for r in additions if r["data"] and r["kind"] in (1, 0x1D)),
         "WAD contains a new payload outside the Nornir namespace")
    added_nornir = [r for r in additions if r["data"] and r["name"].startswith(nornir_prefixes)]
    old_ids = {r["id"] for r in original if r["data"]}
    added_ids = [r["id"] for r in added_nornir]
    need(len(added_ids) == len(set(added_ids)) and
         all(any(uid) and uid not in old_ids for uid in added_ids),
         "Nornir WAD payload resource ID aliases an existing ID")
    return {"baseline_records_preserved_byte_exact": len(baseline),
            "added_physical_records": len(additions),
            "added_payloads": len(new_payloads) - len(old_payloads),
            "unique_new_nornir_payload_ids": len(added_ids),
            "typed_total_before": old_total, "typed_total_after": new_total,
            "candidate_sha256": sha(after)}


def verify_pool(before: bytes, after: bytes) -> dict:
    old_chunks = stage.parse_dcb_chunks(before)
    new_chunks = stage.parse_dcb_chunks(after)
    need([c["kind"] for c in old_chunks] == [c["kind"] for c in new_chunks] ==
         [11, 12, 13, 14, 15], "UI DCB chunk layout changed")
    for old, new in zip(old_chunks, new_chunks):
        if old["kind"] != 12:
            need(before[old["start"]:old["end"]] == after[new["start"]:new["end"]],
                 f"UI DCB non-pool chunk {old['kind']} changed")
    old_chunk = stage.one_chunk(old_chunks, 12)
    new_chunk = stage.one_chunk(new_chunks, 12)
    old_data = before[old_chunk["start"]:old_chunk["end"]]
    new_data = after[new_chunk["start"]:new_chunk["end"]]
    count, rows, old_end = stage.dcb_rows(old_data)
    new_count, new_rows, new_end = stage.dcb_rows(new_data)
    need(count == 301 and new_count >= count, "expected current 301-row Raven pool")
    need([r["raw"] for r in new_rows[:count]] == [r["raw"] for r in rows],
         "Raven/stock UI pool prefix changed")
    normalized = bytearray(new_data[:old_end] + new_data[new_end:])
    for start, end in ((8, 12), (16, 24), (32, 40)):
        normalized[start:end] = old_data[start:end]
    need(bytes(normalized) == old_data, "UI pool does not invert to Raven data")
    need(before[:old_chunk["header"]] == after[:new_chunk["header"]] and
         before[old_chunk["padded"]:] == after[new_chunk["padded"]:],
         "UI pool changed bytes outside its data chunk")
    for uid, capacity in ((legacy.RAVEN_MAP_HASH, 1), (legacy.RAVEN_HUD_HASH, 2)):
        expected = [r for r in rows if r["uid"] == uid and r["capacity"] == capacity]
        actual = [r for r in new_rows[:count] if r["uid"] == uid and r["capacity"] == capacity]
        need(expected and [r["raw"] for r in actual] == [r["raw"] for r in expected],
             f"Raven UI pool resource {uid:016X} changed")
    return {"baseline_rows_preserved_byte_exact": count,
            "candidate_rows": new_count, "added_rows": new_count - count,
            "candidate_sha256": sha(after)}


def export_span(data: bytes, exports: list[dict], name: str) -> bytes:
    row = next((r for r in exports if r["name"] == name), None)
    need(row is not None, f"missing perm export: {name}")
    root = row["root"]
    later = sorted({r["root"] for r in exports if r["root"] > root})
    end = later[0] if later else len(data)
    return data[root:end]


def verify_perm(before: bytes, after: bytes) -> dict:
    old_chunks = legacy.parse_chunks(before)
    new_chunks = legacy.parse_chunks(after)
    need([c["kind"] for c in old_chunks] == [c["kind"] for c in new_chunks] ==
         [11, 12, 13, 14, 35, 15], "perm DCB chunk layout changed")
    old_data = before[legacy.one(old_chunks, 12)["start"]:legacy.one(old_chunks, 12)["end"]]
    new_data = after[legacy.one(new_chunks, 12)["start"]:legacy.one(new_chunks, 12)["end"]]
    old_exports = legacy.parse_exports(
        before[legacy.one(old_chunks, 13)["start"]:legacy.one(old_chunks, 13)["end"]])
    new_exports = legacy.parse_exports(
        after[legacy.one(new_chunks, 13)["start"]:legacy.one(new_chunks, 13)["end"]])
    old_by_name = {r["name"]: r for r in old_exports}
    new_by_name = {r["name"]: r for r in new_exports}
    need(len(old_by_name) == len(old_exports) and len(new_by_name) == len(new_exports),
         "perm export name duplicated")
    need(len({r["uid"] for r in new_exports}) == len(new_exports),
         "perm export UID duplicated")
    for name, old in old_by_name.items():
        new = new_by_name.get(name)
        need(new is not None and (old["uid"], old["type_id"]) ==
             (new["uid"], new["type_id"]), f"perm export changed: {name}")
    additions = sorted(set(new_by_name) - set(old_by_name))
    need(all(name.startswith(("CompletionistNornir", "COMPASS_INWORLD_CM_NORNIR_",
                                    "COMPASS_INWORLD_COMPLETIONIST_NORNIR_"))
             for name in additions), "perm export outside Nornir namespace")
    classes = [new_by_name[name] for name in additions if name.startswith("CompletionistNornir")]
    carriers = [new_by_name[name] for name in additions if name.startswith("COMPASS_INWORLD_")]
    need(len(classes) == len(carriers) and
         all(r["type_id"] == 0x11E for r in classes) and
         all(r["type_id"] == 0x129 for r in carriers),
         "Nornir compass class and in-world carrier counts/types differ")
    bindings = {}
    for row in classes:
        name = row["name"]
        suffix = name.removeprefix("CompletionistNornir")
        carrier_name = "COMPASS_INWORLD_CM_NORNIR_" + suffix.upper()
        if carrier_name not in new_by_name:
            carrier_name = "COMPASS_INWORLD_COMPLETIONIST_NORNIR_" + suffix.upper()
        carrier = new_by_name.get(carrier_name)
        need(carrier is not None, f"Nornir in-world carrier missing: {name}")
        class_data = export_span(new_data, new_exports, name)
        carrier_data = export_span(new_data, new_exports, carrier_name)
        need(len(class_data) == 0x20 and len(carrier_data) == 0x98,
             f"Nornir compass/carrier size differs: {name}")
        hud = name_hash("goCompletionistNornir" + suffix + "HUD")
        need(row["uid"] == name_hash(name) and
             carrier["uid"] == name_hash(carrier_name) and
             struct.unpack_from("<Q", class_data, 0)[0] == hud and
             struct.unpack_from("<Q", class_data, 0x10)[0] == carrier["uid"] and
             struct.unpack_from("<Q", carrier_data, 0)[0] == hud,
             f"Nornir HUD/class/in-world binding differs: {name}")
        bindings[suffix.lower()] = f"{hud:016X}"
    raven_names = ("CompletionistRaven", "COMPASS_INWORLD_COMPLETIONIST_RAVEN")
    for name in raven_names:
        need(export_span(old_data, old_exports, name) == export_span(new_data, new_exports, name),
             f"Raven perm payload changed: {name}")
    return {"baseline_exports_preserved": len(old_exports),
            "added_exports": additions, "raven_class_and_carrier_byte_exact": True,
            "nornir_hud_bindings": bindings,
            "candidate_sha256": sha(after)}


def compare_map(before: Dcb, after: Dcb, snapshot, label: str) -> dict:
    old = snapshot(before)
    new = snapshot(after)
    old_uids = {r["uid"] for r in old}
    survivors = [r for r in new if r["uid"] in old_uids]
    strip_offset = lambda rows: [{k: v for k, v in row.items() if k != "offset"} for row in rows]
    need(strip_offset(survivors) == strip_offset(old),
         f"Raven/stock {label} marker bytes or active order changed")
    added = [r["uid"] for r in new if r["uid"] not in old_uids]
    need(len(set(added)) == len(added), f"candidate {label} Nornir UID duplicated")
    return {"baseline_rows_preserved": len(old), "added_rows": len(added),
            "added_uids": added}


def verify_boot(before: bytes, after: bytes) -> dict:
    old = json.loads(before)
    new = json.loads(after)
    old_packs = old["patch-texpacks"]
    packs = new["patch-texpacks"]
    added = [p for p in packs if p not in old_packs]
    need(len(set(packs)) == len(packs) and
         all(p.startswith("../../patch/pc_le/completionist_v105_nornir_") for p in added),
         "boot options include non-Nornir or duplicate pack")
    new["patch-texpacks"] = [p for p in packs if p not in added]
    need(new == old, "Raven boot options changed")
    return {"raven_options_preserved": True, "nornir_packs_added": added}


def verify(root: Path, candidate_root: Path, overlays: list[Path]) -> dict:
    verify_baseline(root)
    def candidate(relative: str) -> Path:
        return source(candidate_root, overlays, relative)
    for relative in (PACK, TOC, GRAPH):
        need(sha(candidate(relative).read_bytes()) == PINNED[relative],
             f"Raven texture/graph changed: {relative}")
    wad = verify_wad((root / WAD).read_bytes(), candidate(WAD).read_bytes())
    pool = verify_pool((root / UI).read_bytes(), candidate(UI).read_bytes())
    perm = verify_perm((root / PERM).read_bytes(), candidate(PERM).read_bytes())
    candidate_ui = candidate(UI).read_bytes()
    ui_chunk = stage.one_chunk(stage.parse_dcb_chunks(candidate_ui), 12)
    _, ui_rows, _ = stage.dcb_rows(candidate_ui[ui_chunk["start"]:ui_chunk["end"]])
    for family, hud_hex in perm["nornir_hud_bindings"].items():
        need(sum(row["uid"] == int(hud_hex, 16) for row in ui_rows) >= 2,
             f"Nornir {family} HUD class has no two-row UI pool registration")
    master = compare_map(Dcb(root / MASTER), Dcb(candidate(MASTER)),
                         stage.marker_snapshot, "mapmaster")
    coords = compare_map(Dcb(root / COORDS), Dcb(candidate(COORDS)),
                         stage.coordinate_snapshot, "mapcoords")
    need(master["added_rows"] == coords["added_rows"] and
         set(master["added_uids"]) == set(coords["added_uids"]),
         "map/coordinate Nornir UID sets differ")
    namespace = json.loads((REPO / "config/collectibles/v0.10.5/nornir-marker-namespace.json")
                           .read_text(encoding="utf-8-sig"))
    reserved = {item["uid"] for group in namespace["groups"]
                for item in [group["parent"], *group["children"]]}
    need(len(reserved) == 88 and set(master["added_uids"]) <= reserved,
         "new map UID is outside 88-ID Nornir namespace")
    raven_markers = [r for r in stage.marker_snapshot(Dcb(root / MASTER))
                     if r["icon"] == "goMapIconCompletionistRaven"]
    need(len(raven_markers) == 53, "frozen 53-Raven map baseline changed")
    boot = verify_boot((root / BOOT).read_bytes(), candidate(BOOT).read_bytes())
    for pack_name in boot["nornir_packs_added"]:
        stem = "exec/patch/pc_le/" + pack_name.rsplit("/", 1)[-1]
        for suffix in (".texpack", ".texpack.toc"):
            path = candidate(stem + suffix)
            need(path.stat().st_size > 0, f"Nornir texture pack is empty: {path}")
    known_failed = wad["candidate_sha256"] in KNOWN_FAILED_LIVE_WADS
    return {"schema": 1, "result": "NORNIR_COMPOSED_STRUCTURAL_INTEGRITY_VERIFIED",
            "offline_structural_integrity": True,
            "runtime_art_isolation_proven": False,
            "known_failed_live_art": known_failed,
            "install_eligible": False,
            "baseline": "pinned_all_53_ravens_301_pool_rows",
            "candidate_root": str(candidate_root), "overlays": [str(p) for p in overlays],
            "raven_marker_count": len(raven_markers),
            "nornir_marker_count": master["added_rows"],
            "wad": wad, "ui_pool": pool, "perm": perm,
            "mapmaster": {k: v for k, v in master.items() if k != "added_uids"},
            "mapcoords": {k: v for k, v in coords.items() if k != "added_uids"},
            "boot": boot}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raven-root", type=Path, default=RAVEN_ROOT)
    parser.add_argument("--candidate-root", type=Path, default=GAME)
    parser.add_argument("--overlay-root", type=Path, action="append", default=[])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.raven_root, args.candidate_root, args.overlay_root)
    if args.report:
        output = args.report.resolve()
        need(not any(output.is_relative_to(root.resolve()) for root in
                     [GAME, args.raven_root, args.candidate_root, *args.overlay_root]),
             "report must stay outside game and candidate roots")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
