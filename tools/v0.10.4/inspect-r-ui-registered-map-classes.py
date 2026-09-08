"""Inventory registered r_ui map-icon classes and find unused donor candidates.

Read-only. Intersects three independent sources:
1. WAD_R_UI.GOPool rows from stock wad_r_ui.dcb
2. concrete gomapicon* final-instance resources from stock r_ui.wad
3. authored marker Icon usage from mapmaster.dcb

This deliberately replaces the previous guess-and-test donor selection. A WAD
resource is not assumed to be a registered map class unless its case-folded name
hash is actually present in GOPool.

Important: GOPool Name hashes are not assumed unique. The stock file contains
repeated Name hashes, so this tool records duplicate groups explicitly and only
considers a class a donor candidate when its matching GOPool hash resolves to a
single row.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


logical = load_module("completionist_logical_clone", HERE / "build-raven-ui-logical-clone.py")
native = load_module("completionist_native_markers", HERE.parent / "v0.10.3" / "inspect-native-markers.py")

EXPECTED_WAD_SHA256 = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB_SHA256 = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
EXPECTED_MAPMASTER_SHA256 = "1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a"
POOL_OFFSET = 0x90
POOL_COUNT = 255
ROW_SIZE = 0x10
RAVEN_ID = native.name_hash(native.RAVEN_NAME)

# These can be runtime-created even when authored mapmaster usage is zero.
# Never classify them as donor candidates from authored usage alone.
RUNTIME_RESERVED_NAMES = {
    "gomapiconplayer",
    "gomapiconnorender",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_gopool(dcb: native.Dcb) -> list[dict]:
    blob = dcb.blob
    if len(blob) != 4272:
        raise ValueError(f"unexpected WAD_R_UI data size: {len(blob)}")
    if POOL_OFFSET + POOL_COUNT * ROW_SIZE > len(blob):
        raise ValueError("GOPool extends past DCB data")
    rows = []
    for i in range(POOL_COUNT):
        at = POOL_OFFSET + i * ROW_SIZE
        name_hash, cnt = struct.unpack_from("<QH", blob, at)
        rows.append({
            "row_index": i,
            "offset": f"0x{at:X}",
            "name_hash": f"{name_hash:016X}",
            "name_hash_int": name_hash,
            "cnt": cnt,
        })
    return rows


def iter_map_markers(master: native.Dcb):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            for marker in master.array(region + 0x38, 0x48):
                (marker_id,) = master.unpack("<Q", marker)
                yield realm_id, region_id, marker_id, master.string(marker + 8)


def public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "name_hash_int"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--r-ui-wad", type=Path, required=True)
    ap.add_argument("--wad-r-ui-dcb", type=Path, required=True)
    ap.add_argument("--mapmaster", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    wad_raw = args.r_ui_wad.resolve().read_bytes()
    dcb_raw = args.wad_r_ui_dcb.resolve().read_bytes()
    map_raw = args.mapmaster.resolve().read_bytes()
    if digest(wad_raw) != EXPECTED_WAD_SHA256:
        raise ValueError("r_ui.wad is not the pinned stock build")
    if digest(dcb_raw) != EXPECTED_DCB_SHA256:
        raise ValueError("wad_r_ui.dcb is not the pinned stock build")
    if digest(map_raw) != EXPECTED_MAPMASTER_SHA256:
        raise ValueError("mapmaster.dcb is not the tested v0.10.3 native Raven baseline")

    dcb = native.Dcb(args.wad_r_ui_dcb.resolve())
    gopool_rows = parse_gopool(dcb)
    by_hash: dict[int, list[dict]] = collections.defaultdict(list)
    for row in gopool_rows:
        by_hash[row["name_hash_int"]].append(row)

    duplicate_groups = []
    for h, rows in sorted(by_hash.items()):
        if len(rows) <= 1:
            continue
        duplicate_groups.append({
            "name_hash": f"{h:016X}",
            "row_count": len(rows),
            "rows": [public_row(r) for r in rows],
            "cnt_values": [r["cnt"] for r in rows],
        })

    records = logical.parse_wad(wad_raw)
    if logical.serialize_wad(records) != wad_raw:
        raise ValueError("stock r_ui.wad round-trip failed")

    concrete = []
    for r in records:
        if not r["data"]:
            continue
        lname = r["name"].lower()
        if not lname.startswith("gomapicon"):
            continue
        if len(r["data"]) != 164 or r["flags"] != 0x3D:
            continue
        h = native.name_hash(r["name"])
        concrete.append({
            "wad_name": r["name"],
            "wad_hash": f"{h:016X}",
            "wad_hash_int": h,
            "payload_index": r["payload_index"],
            "resource_id": r["id"].hex(),
            "registered": h in by_hash,
        })

    master = native.Dcb(args.mapmaster.resolve())
    usage_by_hash = collections.Counter()
    usage_names = collections.defaultdict(collections.Counter)
    raven_record = None
    marker_total = 0
    for realm, region, marker_id, icon in iter_map_markers(master):
        marker_total += 1
        h = native.name_hash(icon) if icon else 0
        if icon:
            usage_by_hash[h] += 1
            usage_names[h][icon] += 1
        if marker_id == RAVEN_ID:
            raven_record = {
                "realm": f"{realm:016X}",
                "region": f"{region:016X}",
                "icon": icon,
            }

    registered_concrete = []
    donor_candidates = []
    ambiguous_registered_concrete = []
    unregistered_wad_resources = []
    for item in sorted(concrete, key=lambda x: x["payload_index"]):
        h = item["wad_hash_int"]
        rows = by_hash.get(h, [])
        entry = {k: v for k, v in item.items() if not k.endswith("_int")}
        entry["authored_mapmaster_usage"] = usage_by_hash[h]
        entry["authored_icon_spellings"] = dict(usage_names[h])
        entry["runtime_reserved"] = item["wad_name"].lower() in RUNTIME_RESERVED_NAMES
        entry["gopool_match_count"] = len(rows)
        entry["gopool_rows"] = [public_row(r) for r in rows]
        if rows:
            registered_concrete.append(entry)
            if len(rows) == 1:
                entry["gopool_row_index"] = rows[0]["row_index"]
                entry["gopool_cnt"] = rows[0]["cnt"]
                if usage_by_hash[h] == 0 and not entry["runtime_reserved"]:
                    donor_candidates.append(entry)
            else:
                entry["ambiguous_duplicate_gopool_hash"] = True
                ambiguous_registered_concrete.append(entry)
        else:
            unregistered_wad_resources.append(entry)

    known_hashes = {x["wad_hash_int"] for x in concrete}
    opaque_rows = [
        public_row(row)
        for row in gopool_rows
        if row["name_hash_int"] not in known_hashes
    ]

    # Sort donor diagnostics so low-count, likely-specialised slots appear first.
    donor_candidates.sort(key=lambda x: (x["gopool_cnt"], x["wad_name"].lower()))

    result = {
        "result": "REGISTERED_R_UI_MAP_CLASS_INVENTORY",
        "game_files_written": False,
        "source_hashes": {
            "r_ui_wad": digest(wad_raw),
            "wad_r_ui_dcb": digest(dcb_raw),
            "mapmaster": digest(map_raw),
        },
        "counts": {
            "gopool_rows": len(gopool_rows),
            "unique_gopool_name_hashes": len(by_hash),
            "duplicate_gopool_name_hash_groups": len(duplicate_groups),
            "concrete_gomapicon_final_instances": len(concrete),
            "registered_concrete_map_classes": len(registered_concrete),
            "ambiguous_registered_concrete_classes": len(ambiguous_registered_concrete),
            "unregistered_wad_map_resources": len(unregistered_wad_resources),
            "opaque_gopool_rows": len(opaque_rows),
            "authored_mapmaster_markers": marker_total,
            "zero_authored_usage_registered_candidates": len(donor_candidates),
        },
        "raven_baseline": raven_record,
        "duplicate_gopool_name_hash_groups": duplicate_groups,
        "registered_concrete_map_classes": registered_concrete,
        "ambiguous_registered_concrete_classes": ambiguous_registered_concrete,
        "zero_authored_usage_registered_candidates": donor_candidates,
        "unregistered_wad_map_resources": unregistered_wad_resources,
        "opaque_gopool_rows": opaque_rows,
        "interpretation": {
            "important": "A gomapicon* WAD resource is not a registered class unless its hash is also present in WAD_R_UI.GOPool.",
            "gopool_name_hashes_are_not_assumed_unique": True,
            "duplicate_hash_classes_are_excluded_from_donor_candidates": True,
            "donor_candidates_are_not_yet_proven_safe": True,
            "next_gate": "Choose only a uniquely registered zero-authored-usage candidate, then inspect runtime/code references before any in-game rename proof.",
        },
    }

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"GOPool duplicate Name-hash groups: {len(duplicate_groups)}")
    print(f"Registered concrete map classes: {len(registered_concrete)}")
    print(f"Zero-authored-usage uniquely registered candidates: {len(donor_candidates)}")
    for c in donor_candidates:
        print(f"  {c['wad_name']} row={c['gopool_row_index']} cnt={c['gopool_cnt']} payload={c['payload_index']}")
    print(f"Saved: {out}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
