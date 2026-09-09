#!/usr/bin/env python3
"""Verify the runtime-proven v0.10.4 Raven state without modifying God of War.

This is the production handoff gate. It validates the live files and the active
research manifests that together produced the end-to-end Raven success:
custom map art, custom compass HUD art, custom in-world art, native distance and
pathfinding, and stock single-target Add/Replace/Remove semantics.

No game file, save, progression value, or marker state is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

RESULT = "RAVEN_PRODUCTION_STATE_VERIFIED"
EXPECTED_BRANCH = "codex/v104-raven-production"

EXPECTED = {
    "r_ui_wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "wad_r_perm": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "mapcoords": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
    "compassgraph": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
}

RAVEN_MARKER = "Completionist_V103_Veithurgard_Raven_01"
RAVEN_CLASS = "CompletionistRaven"
RAVEN_CLASS_UID = 0x5DC46967D3095F7E
RAVEN_HUD_HASH = 0x45E5C7943749F81C
RAVEN_MAP_HASH = 0x584F31DC8BD6E738
RAVEN_INWORLD_NAME = "COMPASS_INWORLD_COMPLETIONIST_RAVEN"
RAVEN_INWORLD_UID = 0x21DC5A7D4AD17628
DOCK_HUD_HASH = 0x82F0296748C7393D
COMPASS_CLASS_TYPE = 0x11E
INWORLD_TYPE = 0x129
GOP_BASE = 0x90
GOP_ROW = 16


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def align16(v: int) -> int:
    return (v + 15) & ~15


def parse_chunks(raw: bytes) -> list[dict]:
    chunks: list[dict] = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short DCB header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        padded = align16(end)
        check(flags == 0x10 and padded <= len(raw), f"invalid DCB chunk at {off:#x}")
        chunks.append({"kind": kind, "header": off, "start": start, "end": end, "padded": padded})
        off = padded
    check(off == len(raw), "DCB chunk walk did not end at EOF")
    return chunks


def one(chunks: list[dict], kind: int) -> dict:
    rows = [c for c in chunks if c["kind"] == kind]
    check(len(rows) == 1, f"expected one DCB chunk {kind}, found {len(rows)}")
    return rows[0]


def cstring(blob: bytes, offset: int) -> str:
    check(0 <= offset < len(blob), f"string offset outside export payload: {offset:#x}")
    end = blob.find(b"\0", offset)
    check(end >= 0, "unterminated export string")
    return blob[offset:end].decode("ascii")


def parse_exports(payload: bytes) -> list[dict]:
    check(len(payload) >= 8, "export payload too short")
    count = struct.unpack_from("<I", payload, 0)[0]
    check(8 + count * 24 <= len(payload), "export count exceeds payload")
    rows = []
    for i in range(count):
        at = 8 + i * 24
        root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", payload, at)
        rows.append({
            "index": i,
            "root": root,
            "type_id": type_id,
            "string_offset": string_offset,
            "uid": uid,
            "name": cstring(payload, string_offset),
        })
    return rows


def verify_perm(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    check(digest == EXPECTED["wad_r_perm"], f"unexpected wad_r_perm.dcb SHA256: {digest}")
    chunks = parse_chunks(raw)
    check([c["kind"] for c in chunks] == [11, 12, 13, 14, 35, 15],
          f"unexpected wad_r_perm chunk order: {[c['kind'] for c in chunks]}")
    dc = one(chunks, 12)
    ec = one(chunks, 13)
    data = raw[dc["start"]:dc["end"]]
    exports = parse_exports(raw[ec["start"]:ec["end"]])
    by_name = {e["name"]: e for e in exports}

    check(RAVEN_CLASS in by_name, "CompletionistRaven export missing")
    check(RAVEN_INWORLD_NAME in by_name, "dedicated Raven in-world export missing")
    raven = by_name[RAVEN_CLASS]
    inworld = by_name[RAVEN_INWORLD_NAME]
    check(raven["uid"] == RAVEN_CLASS_UID, f"CompletionistRaven UID changed: {raven['uid']:016X}")
    check(raven["type_id"] == COMPASS_CLASS_TYPE, f"CompletionistRaven type changed: {raven['type_id']:#x}")
    check(inworld["uid"] == RAVEN_INWORLD_UID, f"Raven in-world UID changed: {inworld['uid']:016X}")
    check(inworld["type_id"] == INWORLD_TYPE, f"Raven in-world type changed: {inworld['type_id']:#x}")

    rr = raven["root"]
    check(rr + 0x20 <= len(data), "CompletionistRaven record outside data chunk")
    icon, _radius, inworld_uid = struct.unpack_from("<QQQ", data, rr)
    check(icon == RAVEN_HUD_HASH, f"CompletionistRaven IconName changed: {icon:016X}")
    check(inworld_uid == RAVEN_INWORLD_UID,
          f"CompletionistRaven in-world binding changed: {inworld_uid:016X}")

    ir = inworld["root"]
    later = sorted({e["root"] for e in exports if e["root"] > ir})
    iend = later[0] if later else len(data)
    check(iend - ir == 0x98, f"Raven in-world carrier span changed: {iend-ir}")
    check(ir + 8 <= len(data), "Raven in-world carrier outside data chunk")
    carrier_icon = struct.unpack_from("<Q", data, ir)[0]
    check(carrier_icon == RAVEN_HUD_HASH,
          f"Raven in-world carrier IconName changed: {carrier_icon:016X}")

    return {
        "sha256": digest,
        "completionist_class_uid": f"{raven['uid']:016X}",
        "completionist_icon": f"{icon:016X}",
        "completionist_inworld": f"{inworld_uid:016X}",
        "inworld_export": RAVEN_INWORLD_NAME,
        "inworld_type": f"0x{inworld['type_id']:X}",
        "inworld_span": iend - ir,
        "inworld_icon": f"{carrier_icon:016X}",
    }


def verify_ui_pool(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    chunks = parse_chunks(raw)
    check([c["kind"] for c in chunks] == [11, 12, 13, 14, 15],
          f"unexpected wad_r_ui chunk order: {[c['kind'] for c in chunks]}")
    dc = one(chunks, 12)
    data = raw[dc["start"]:dc["end"]]
    check(len(data) >= GOP_BASE, "WAD_R_UI data chunk too short")
    count = struct.unpack_from("<I", data, 8)[0]
    check(count == 257, f"expected 257 GOPool rows, found {count}")
    check(GOP_BASE + count * GOP_ROW <= len(data), "GOPool exceeds data chunk")
    rows = []
    for index in range(count):
        off = GOP_BASE + index * GOP_ROW
        uid, cap = struct.unpack_from("<QH", data, off)
        rows.append({"index": index, "uid": uid, "capacity": cap})

    def unique(uid: int) -> dict:
        found = [r for r in rows if r["uid"] == uid]
        check(len(found) == 1, f"expected one GOPool row for {uid:016X}, found {len(found)}")
        return found[0]

    hud = unique(RAVEN_HUD_HASH)
    dock = unique(DOCK_HUD_HASH)
    map_raven = unique(RAVEN_MAP_HASH)
    check(hud["index"] == 256 and hud["capacity"] == 2,
          f"Raven HUD GOPool row must be index 256 capacity 2, got index={hud['index']} cap={hud['capacity']}")
    check(dock["capacity"] == 2, f"stock Dock GOPool capacity changed: {dock['capacity']}")
    check(map_raven["index"] == 255 and map_raven["capacity"] == 1,
          f"map Raven GOPool row changed: index={map_raven['index']} cap={map_raven['capacity']}")

    return {
        "sha256": digest,
        "gopool_count": count,
        "raven_hud": {"hash": f"{RAVEN_HUD_HASH:016X}", "index": hud["index"], "capacity": hud["capacity"]},
        "map_raven": {"hash": f"{RAVEN_MAP_HASH:016X}", "index": map_raven["index"], "capacity": map_raven["capacity"]},
        "stock_dock": {"hash": f"{DOCK_HUD_HASH:016X}", "index": dock["index"], "capacity": dock["capacity"]},
    }


def load_json(path: Path) -> dict:
    check(path.is_file(), f"required active manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_manifests(repo: Path, mapmenu: Path, live_ui_sha: str) -> dict:
    paths = {
        "custom_class": repo / "build/v0.10.4-raven-native-custom-class-control/active.json",
        "single_active": repo / "build/v0.10.4-raven-single-active-compass-control/active.json",
        "gopool_registration": repo / "build/v0.10.4-raven-compass-hud-gopool-registration/active-install.json",
        "inworld_carrier": repo / "build/v0.10.4-raven-inworld-carrier/runtime/active.json",
        "capacity2": repo / "build/v0.10.4-raven-hud-gopool-capacity2-control/runtime/active.json",
    }
    m = {name: load_json(path) for name, path in paths.items()}

    check(m["custom_class"].get("kind") == "completionist-v104-raven-native-custom-class-control",
          "custom-class manifest kind mismatch")
    check(m["custom_class"].get("marker") == RAVEN_MARKER and
          m["custom_class"].get("marker_type_after") == RAVEN_CLASS,
          "custom-class manifest marker/class mismatch")

    check(m["single_active"].get("kind") == "completionist-v104-raven-single-active-compass-control" and
          m["single_active"].get("schema") == 3,
          "single-active manifest is not proven schema 3")
    live_map_sha = sha256(mapmenu)
    expected_map_sha = str(m["single_active"].get("map_after_sha256", "")).lower()
    check(live_map_sha == expected_map_sha,
          f"mapmenu.lua does not match active schema-3 control: {live_map_sha} != {expected_map_sha}")

    check(m["gopool_registration"].get("operation") == "raven_compass_hud_gopool_registration" and
          int(m["gopool_registration"].get("hud_capacity", 0)) == 1,
          "underlying GOPool registration manifest mismatch")

    check(m["inworld_carrier"].get("kind") == "completionist-v104-raven-inworld-carrier-runtime" and
          m["inworld_carrier"].get("schema") == 1 and
          str(m["inworld_carrier"].get("wad_r_perm_after_sha256", "")).lower() == EXPECTED["wad_r_perm"],
          "in-world carrier manifest mismatch")

    check(m["capacity2"].get("kind") == "completionist-v104-raven-hud-gopool-capacity2-control" and
          m["capacity2"].get("schema") == 1 and
          int(m["capacity2"].get("capacity_before", 0)) == 1 and
          int(m["capacity2"].get("capacity_after", 0)) == 2,
          "capacity-2 manifest mismatch")
    cap_after_sha = str(m["capacity2"].get("wad_r_ui_after_sha256", "")).lower()
    check(cap_after_sha == live_ui_sha,
          f"live wad_r_ui.dcb does not match capacity-2 manifest: {live_ui_sha} != {cap_after_sha}")

    # No temporary stock-art A/B may remain layered over the final custom-art state.
    forbidden = [
        repo / "build/v0.10.4-raven-native-custom-class-stock-art-control/active.json",
        repo / "build/v0.10.4-raven-inworld-carrier-stock-art-control/runtime/active.json",
    ]
    active_forbidden = [str(p) for p in forbidden if p.is_file()]
    check(not active_forbidden, f"temporary stock-art control still active: {active_forbidden}")

    ab_root = repo / "build/v0.10.4/native-raven-no-render/ab-transactions"
    installed_ab: list[Path] = []
    if ab_root.is_dir():
        for p in ab_root.rglob("manifest.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if j.get("kind") == "v104-native-raven-coordinate-graph-ab-v1" and j.get("state") == "installed":
                installed_ab.append(p)
    check(len(installed_ab) == 1,
          f"expected exactly one installed native Raven coordinate/graph A/B manifest, found {len(installed_ab)}")

    return {
        "mapmenu_sha256": live_map_sha,
        "manifests": {k: str(v) for k, v in paths.items()},
        "native_data_ab_manifest": str(installed_ab[0]),
        "temporary_stock_art_controls_active": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    out = args.output.resolve()
    check(not out.is_relative_to(game), "verification report must stay outside the game directory")

    files = {
        "r_ui.wad": game / "exec/wad/pc_le/r_ui.wad",
        "wad_r_ui.dcb": game / "exec/dc/pc_le/wad_r_ui.dcb",
        "wad_r_perm.dcb": game / "exec/dc/pc_le/wad_r_perm.dcb",
        "mapcoords.dcb": game / "exec/dc/pc_le/mapcoords.dcb",
        "compassgraph.dcb": game / "exec/dc/pc_le/compassgraph.dcb",
        "mapmenu.lua": game / "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
    }
    for p in files.values():
        check(p.is_file(), f"missing live file: {p}")

    hashes = {name: sha256(path) for name, path in files.items()}
    check(hashes["r_ui.wad"] == EXPECTED["r_ui_wad"], f"r_ui.wad SHA mismatch: {hashes['r_ui.wad']}")
    check(hashes["wad_r_perm.dcb"] == EXPECTED["wad_r_perm"], f"wad_r_perm SHA mismatch: {hashes['wad_r_perm.dcb']}")
    check(hashes["mapcoords.dcb"] == EXPECTED["mapcoords"], f"mapcoords SHA mismatch: {hashes['mapcoords.dcb']}")
    check(hashes["compassgraph.dcb"] == EXPECTED["compassgraph"], f"compassgraph SHA mismatch: {hashes['compassgraph.dcb']}")

    perm = verify_perm(files["wad_r_perm.dcb"])
    ui = verify_ui_pool(files["wad_r_ui.dcb"])
    manifests = verify_manifests(repo, files["mapmenu.lua"], ui["sha256"])

    report = {
        "schema": 1,
        "result": RESULT,
        "branch_contract": EXPECTED_BRANCH,
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "marker": RAVEN_MARKER,
        "compass_class": RAVEN_CLASS,
        "live_hashes": hashes,
        "wad_r_perm_contract": perm,
        "wad_r_ui_contract": ui,
        "research_state": manifests,
        "runtime_proof_source": "archive/field-logs/completionist-v104-raven-full-compass-runtime-success.json",
        "proven_invariants": {
            "custom_map_art": True,
            "custom_compass_hud_art": True,
            "custom_inworld_art": True,
            "native_distance": True,
            "native_pathfinding": True,
            "single_active_target": True,
            "add_replace_remove": True,
            "hud_gopool_capacity": 2,
        },
        "ready_to_adopt_as_production_baseline": True,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Recheck fixed live inputs after the read-only audit.
    for name, path in files.items():
        check(sha256(path) == hashes[name], f"live file changed during verification: {path}")

    print(RESULT)
    print(f"  Raven marker:             {RAVEN_MARKER}")
    print(f"  wad_r_perm.dcb:           {hashes['wad_r_perm.dcb']}")
    print(f"  wad_r_ui.dcb:             {hashes['wad_r_ui.dcb']}")
    print(f"  r_ui.wad:                 {hashes['r_ui.wad']}")
    print(f"  mapmenu.lua:              {hashes['mapmenu.lua']}")
    print(f"  HUD GOPool:               index {ui['raven_hud']['index']} capacity {ui['raven_hud']['capacity']}")
    print(f"  in-world carrier:         {RAVEN_INWORLD_NAME}")
    print("  temporary stock controls: inactive")
    print("  game files written:       false")
    print("  ready for adoption:       true")
    print(f"  report:                   {out}")


if __name__ == "__main__":
    main()
