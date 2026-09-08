"""Resolve DockPoint compass visual hashes into r_ui.wad resource chains.

Read-only v0.10.4 HUD research helper. The stock CompassIconClass record gives
DockPoint two opaque resource hashes: IconName for the HUD compass glyph and
InWorld_tMPIcon_Name for the marker rendered above the tracked world target.
This tool resolves those hashes against the names stored in the currently proven
r_ui.wad and reports every payload record that references either hash.

It never writes the game directory, save data, progression, marker state or Lua.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
HELPER = HERE / "build-raven-ui-logical-clone.py"
HELPER_SHA256_LF = "d5f7c5b77166b3e9ba46dec17174fc1f30ca5e3bab492527636cdf63c8b41b03"

# Proven registered-Raven base and the runtime-proven resident-artwork WAD.
ALLOWED_WAD_SHA256 = {
    "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959",
    "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3",
}
EXPECTED_PERM_SHA256 = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"

TARGETS = {
    "DockPoint.IconName": 0x82F0296748C7393D,
    "DockPoint.InWorld_tMPIcon_Name": 0x0E24C47DE2F769CA,
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    source = HELPER.read_bytes().replace(b"\r\n", b"\n")
    check(sha256_bytes(source) == HELPER_SHA256_LF, "pinned logical WAD helper changed")
    spec = importlib.util.spec_from_file_location("v104_hud_resource_logical", HELPER)
    check(spec is not None, "could not create logical helper spec")
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(HELPER), "exec"), module.__dict__)
    return module


def parent_chain(records: list[dict], index: int) -> list[dict]:
    out: list[dict] = []
    parent = records[index]["parent"]
    guard = 0
    while parent is not None:
        row = records[parent]
        out.append(
            {
                "index": parent,
                "name": row["name"],
                "kind": row["kind"],
                "flags": f"0x{row['flags']:X}",
                "file_offset": row["original_offset"],
            }
        )
        parent = row["parent"]
        guard += 1
        check(guard < 128, "WAD parent chain cycle")
    return out


def describe_record(records: list[dict], index: int) -> dict:
    row = records[index]
    return {
        "index": index,
        "name": row["name"],
        "name_hash": f"{logical.name_hash(row['name']):016X}" if row["name"] else None,
        "kind": row["kind"],
        "flags": f"0x{row['flags']:X}",
        "data_bytes": len(row["data"]),
        "file_offset": row["original_offset"],
        "parent_chain": parent_chain(records, index),
    }


def resolve(records: list[dict], label: str, value: int) -> dict:
    exact = [
        describe_record(records, i)
        for i, row in enumerate(records)
        if row["name"] and logical.name_hash(row["name"]) == value
    ]

    needle = struct.pack("<Q", value)
    references = []
    for i, row in enumerate(records):
        data = bytes(row["data"])
        start = 0
        while data:
            pos = data.find(needle, start)
            if pos < 0:
                break
            references.append(
                {
                    **describe_record(records, i),
                    "payload_offset": pos,
                    "absolute_hash_offset": row["original_offset"] + 96 + pos,
                }
            )
            start = pos + 1

    return {
        "label": label,
        "hash": f"{value:016X}",
        "exact_name_matches": exact,
        "exact_name_match_count": len(exact),
        "payload_references": references,
        "payload_reference_count": len(references),
    }


def relevant_name_hints(records: list[dict]) -> list[dict]:
    tokens = ("compass", "dock", "inworld", "marker")
    out = []
    seen = set()
    for i, row in enumerate(records):
        name = row["name"]
        lower = name.lower()
        if name and any(token in lower for token in tokens):
            key = (name.lower(), row["kind"], row["flags"])
            if key in seen:
                continue
            seen.add(key)
            out.append(describe_record(records, i))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    wad = game / "exec/wad/pc_le/r_ui.wad"
    perm = game / "exec/dc/pc_le/wad_r_perm.dcb"
    check(wad.is_file(), f"missing {wad}")
    check(perm.is_file(), f"missing {perm}")

    wad_raw = wad.read_bytes()
    perm_raw = perm.read_bytes()
    wad_hash = sha256_bytes(wad_raw)
    perm_hash = sha256_bytes(perm_raw)
    check(wad_hash in ALLOWED_WAD_SHA256, f"r_ui.wad is not a proven v0.10.4 state: {wad_hash}")
    check(perm_hash == EXPECTED_PERM_SHA256, "wad_r_perm.dcb is not the stock/proven DockPoint class base")

    global logical
    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "r_ui.wad does not round-trip exactly")

    targets = [resolve(records, label, value) for label, value in TARGETS.items()]
    report = {
        "result": "READ_ONLY_DOCKPOINT_HUD_RESOURCE_CHAIN",
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "r_ui_wad_sha256": wad_hash,
        "wad_r_perm_dcb_sha256": perm_hash,
        "dockpoint_class": {
            "IconName": "82F0296748C7393D",
            "RadiusIconName": "0000000000000000",
            "InWorld_tMPIcon_Name": "0E24C47DE2F769CA",
            "IconScale": 1.0,
            "IsMainQuest": False,
        },
        "targets": targets,
        "relevant_name_hints": relevant_name_hints(records),
        "next_gate": (
            "Use exact resolved names and parent chains to build a read-only live Compass_Base lookup probe. "
            "Do not call SetMaterialSwap or SetMPIconMaterialSwap until the Raven-owned runtime GO is uniquely identified."
        ),
    }

    out = args.output.resolve()
    check(not out.is_relative_to(game), "report must stay outside game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Re-read the inputs after analysis to prove this helper made no live changes.
    check(sha256_bytes(wad.read_bytes()) == wad_hash, "r_ui.wad changed during read-only inspection")
    check(sha256_bytes(perm.read_bytes()) == perm_hash, "wad_r_perm.dcb changed during read-only inspection")

    print(json.dumps({
        "result": report["result"],
        "r_ui_wad_sha256": wad_hash,
        "targets": {
            row["label"]: {
                "exact_name_matches": row["exact_name_match_count"],
                "payload_references": row["payload_reference_count"],
                "names": [x["name"] for x in row["exact_name_matches"]],
            }
            for row in targets
        },
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
