"""Read-only live audit for CompletionistRaven compass HUD resource registration.

The native custom-class stock-art A/B proved that CompletionistRaven registration,
Raven mapcoords/compassgraph, and native routing are safe while the dedicated HUD
binding crashes. This audit asks the next narrow question without writing the game:

- is goCompletionistRavenHUD physically present in the installed r_ui.wad?
- is its folded-name hash registered in the installed WAD_R_UI GOPool?
- do the working stock DockPoint and working custom map Raven provide controls?

The report is evidence only. It does not install or patch anything.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
HUD_NAME = "goCompletionistRavenHUD"
HUD_HASH = 0x45E5C7943749F81C
DOCK_ICON_HASH = 0x82F0296748C7393D
MAP_RAVEN_NAME = "goMapIconCompletionistRaven"
MAP_RAVEN_HASH = 0x584F31DC8BD6E738
EXPECTED_CURRENT_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def folded_name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def load_wad_parser():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("completionist_live_hud_audit_wad", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_gopool(dcb_raw: bytes, logical) -> dict:
    chunks = logical.parse_dcb_chunks(dcb_raw)
    data_chunk = logical.one_chunk(chunks, 12)
    data = dcb_raw[data_chunk["start"]:data_chunk["end"]]
    check(len(data) >= 0x90, "WAD_R_UI data chunk is unexpectedly short")
    count = struct.unpack_from("<I", data, 8)[0]
    end = 0x90 + count * 16
    check(end <= len(data), f"WAD_R_UI GOPool exceeds data chunk: count={count}")
    rows = []
    for index in range(count):
        off = 0x90 + index * 16
        uid, capacity = struct.unpack_from("<QH", data, off)
        rows.append({
            "index": index,
            "uid": uid,
            "uid_hex": f"{uid:016X}",
            "capacity": capacity,
            "raw_hex": data[off:off + 16].hex(),
        })
    return {
        "count": count,
        "rows": rows,
        "data_bytes": len(data),
        "chunk_layout": [c["kind"] for c in chunks],
    }


def rows_for(pool: dict, uid: int) -> list[dict]:
    return [row for row in pool["rows"] if row["uid"] == uid]


def wad_names_for_hash(records: list[dict], uid: int) -> list[str]:
    return sorted({
        str(record["name"])
        for record in records
        if record.get("name") and folded_name_hash(str(record["name"])) == uid
    })


def wad_defs_for_hash(records: list[dict], uid: int) -> list[dict]:
    out = []
    for index, record in enumerate(records):
        name = str(record.get("name") or "")
        if not name or folded_name_hash(name) != uid or not record.get("data"):
            continue
        out.append({
            "record_index": index,
            "name": name,
            "kind": int(record["kind"]),
            "flags": int(record["flags"]),
            "payload_bytes": len(record["data"]),
            "resource_id": bytes(record["id"]).hex(),
            "original_offset": record.get("original_offset"),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    check(wad_path.is_file(), f"missing {wad_path}")
    check(dcb_path.is_file(), f"missing {dcb_path}")

    wad_raw = wad_path.read_bytes()
    dcb_raw = dcb_path.read_bytes()
    wad_sha = sha256(wad_raw)
    dcb_sha = sha256(dcb_raw)
    check(wad_sha == EXPECTED_CURRENT_WAD,
          f"installed r_ui.wad is not the current dedicated-HUD candidate: {wad_sha}")
    check(folded_name_hash(HUD_NAME) == HUD_HASH, "HUD name/hash constant mismatch")
    check(folded_name_hash(MAP_RAVEN_NAME) == MAP_RAVEN_HASH, "map Raven name/hash constant mismatch")

    logical = load_wad_parser()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "installed r_ui.wad byte round-trip failed")
    pool = parse_gopool(dcb_raw, logical)

    probes = {
        "completionist_hud": {
            "expected_name": HUD_NAME,
            "hash": HUD_HASH,
        },
        "stock_dock_icon": {
            "expected_name": None,
            "hash": DOCK_ICON_HASH,
        },
        "working_map_raven": {
            "expected_name": MAP_RAVEN_NAME,
            "hash": MAP_RAVEN_HASH,
        },
    }
    for probe in probes.values():
        uid = int(probe["hash"])
        probe["hash"] = f"{uid:016X}"
        probe["wad_names"] = wad_names_for_hash(records, uid)
        probe["wad_definitions"] = wad_defs_for_hash(records, uid)
        probe["gopool_rows"] = rows_for(pool, uid)
        probe["physically_defined"] = bool(probe["wad_definitions"])
        probe["registered"] = len(probe["gopool_rows"]) == 1

    hud = probes["completionist_hud"]
    dock = probes["stock_dock_icon"]
    map_raven = probes["working_map_raven"]

    if not hud["physically_defined"]:
        classification = "HUD_RESOURCE_NOT_PHYSICALLY_DEFINED"
    elif not hud["registered"]:
        classification = "HUD_RESOURCE_PHYSICAL_BUT_GOPool_UNREGISTERED"
    else:
        classification = "HUD_RESOURCE_PHYSICAL_AND_GOPool_REGISTERED_DEEPER_AUDIT_REQUIRED"

    controls = {
        "stock_dock_registered": bool(dock["registered"]),
        "working_map_raven_registered": bool(map_raven["registered"]),
        "working_map_raven_physically_defined": bool(map_raven["physically_defined"]),
    }

    report = {
        "schema": 1,
        "result": classification,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "installed": {
            "r_ui.wad": {"path": str(wad_path), "sha256": wad_sha, "bytes": len(wad_raw)},
            "wad_r_ui.dcb": {"path": str(dcb_path), "sha256": dcb_sha, "bytes": len(dcb_raw)},
        },
        "gopool": {
            "count": pool["count"],
            "data_bytes": pool["data_bytes"],
            "chunk_layout": pool["chunk_layout"],
        },
        "probes": probes,
        "controls": controls,
        "interpretation": (
            "If the dedicated HUD root is physically present but absent from WAD_R_UI.GOPool while the stock Dock and "
            "working map Raven controls are registered, missing resource registration is the leading crash mechanism. "
            "Do not patch runtime files until a reversible wad_r_ui.dcb candidate is built and validated offline."
        ),
    }

    check(wad_path.read_bytes() == wad_raw, "r_ui.wad changed during read-only audit")
    check(dcb_path.read_bytes() == dcb_raw, "wad_r_ui.dcb changed during read-only audit")

    out = args.output.resolve()
    check(not out.is_relative_to(game), "audit output must stay outside game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(classification)
    print(f"  r_ui.wad SHA256:              {wad_sha}")
    print(f"  wad_r_ui.dcb SHA256:          {dcb_sha}")
    print(f"  GOPool rows:                  {pool['count']}")
    print(f"  goCompletionistRavenHUD WAD:  {'present' if hud['physically_defined'] else 'MISSING'}")
    print(f"  goCompletionistRavenHUD pool: {'REGISTERED' if hud['registered'] else 'MISSING'}")
    print(f"  stock Dock pool control:      {'REGISTERED' if dock['registered'] else 'missing'}")
    print(f"  map Raven pool control:       {'REGISTERED' if map_raven['registered'] else 'missing'}")
    print(f"  output:                       {out}")
    print("  game files written:           false")


if __name__ == "__main__":
    main()
