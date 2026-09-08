"""Verify the minimal Raven compass HUD resource-reuse contract read-only.

This gate inspects the currently proven r_ui.wad and answers one question:
can a new compass-only Raven GameObject reuse the already-dedicated Raven map
material/textures while sharing stock Dock HUD geometry?

No candidate is built and no game, save, progression, marker, DCB or WAD file is
written. Only the requested JSON report outside the game directory is created.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

RESULT = "READ_ONLY_RAVEN_COMPASS_HUD_REUSE_GATE"
CONCLUSION = "EXISTING_RAVEN_ARTWORK_REUSABLE_FOR_COMPASS_HUD"
EXPECTED_WAD = "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3"

STOCK_ROOT = "goboatdock"
STOCK_PROTO = "goProtoBoatDock"
STOCK_MODEL = "MDL_boatdock"
STOCK_MATERIAL = "MAT_0C599DC8DC7E2170"
STOCK_MESH = "MG_boatdock_0"
SHARED_COMPASS = "goProtocompassicons"

RAVEN_MATERIAL = "MAT_AE4AD85BB993F040"
RAVEN_MATERIAL_ID = bytes.fromhex("dac6009fd0f18caad2ed322463c3d0c8")
RAVEN_MATERIAL_Q10 = 0x1B0989158D4A2908
STOCK_DOCK_MATERIAL_Q20 = 0xD595197B0961F689
RAVEN_DIFFUSE = "TX_completionist_raven_map_diffuse_19A41F00834C19F3"
RAVEN_EMISSIVE = "TX_completionist_raven_map_emissive_63F1E18FF93B9037"
RAVEN_DIFFUSE_DEF_ID = bytes.fromhex("5458455400455255001fa419f3194c83")
RAVEN_EMISSIVE_DEF_ID = bytes.fromhex("54584554004552558fe1f16337903bf9")
RAVEN_DIFFUSE_GPU_ID = bytes.fromhex("000000000000000079babb7a41c7033c")
RAVEN_EMISSIVE_GPU_ID = bytes.fromhex("0000000000000000d216ad1542eb7da1")

GENERIC_MATERIAL_LINKS = {
    "TX_rewards_headerbacking_[0_1]_norm_182F0CA0F54A6666",
    "TX_mapmarker_vendorlocation_gloss_0F72BB3EB6D02EA3",
    "0c599dc8dc7e2170_ps_10000207",
    "transp_vs_10000207",
}

PROPOSED_ROOT = "gocompletionistravenhud"
PROPOSED_PROTO = "goProtoCompletionistRavenHUD"
PROPOSED_MODEL = "MDL_completionistravenhud"
PROPOSED_ICON_NAME = "goCompletionistRavenHUD"
PROPOSED_IDS = {
    PROPOSED_ROOT: bytes.fromhex("f0029a68d9705e95a981aab8bff0c5b8"),
    PROPOSED_PROTO: bytes.fromhex("b2a833d6144789e8099acf85e832d652"),
    PROPOSED_MODEL: bytes.fromhex("4a7911dc2db72cecaf6c187a66bfd11f"),
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def load_wad_helper():
    path = Path(__file__).with_name("build-raven-ui-logical-clone.py")
    spec = importlib.util.spec_from_file_location("completionist_hud_reuse_wad", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def definition(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"].lower() == name.lower() and int(r["kind"]) == 1 and len(r["data"])]
    check(len(rows) == 1, f"expected one data definition for {name}, found {len(rows)}")
    return rows[0]


def texture_record(records: list[dict], name: str, kind: int, flags: int, size: int | None = None) -> dict:
    rows = [r for r in records if r["name"].lower() == name.lower() and int(r["kind"]) == kind
            and int(r["flags"]) == flags and len(r["data"]) > 0 and (size is None or len(r["data"]) == size)]
    check(len(rows) == 1, f"expected one texture record {name} kind={kind:#x} flags={flags:#x}, found {len(rows)}")
    return rows[0]


def group_records(wadmod, records: list[dict], payload: dict) -> list[dict]:
    parent = payload.get("parent")
    check(parent is not None, f"{payload['name']} has no containing group")
    end = wadmod.matching_group_end(records, int(parent))
    return records[int(parent):end + 1]


def zero_links(group: list[dict]) -> list[dict]:
    return [r for r in group if int(r["kind"]) == 1 and not len(r["data"])]


def brief(r: dict) -> dict:
    return {
        "name": r["name"],
        "id": bytes(r["id"]).hex(),
        "kind": int(r["kind"]),
        "flags": f"0x{int(r['flags']):X}",
        "bytes": len(r["data"]),
        "payload_index": r.get("payload_index"),
        "file_offset": None if r.get("original_offset") is None else f"0x{int(r['original_offset']):X}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    out = args.output.resolve()
    check(not out.is_relative_to(game), "report must stay outside the game directory")
    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    check(wad_path.is_file(), f"missing {wad_path}")
    raw = wad_path.read_bytes()
    digest = sha256(raw)
    check(digest == EXPECTED_WAD, f"r_ui.wad differs from current proven Raven baseline: {digest}")

    wadmod = load_wad_helper()
    records = wadmod.parse_wad(raw)
    check(wadmod.serialize_wad(records) == raw, "r_ui.wad byte round-trip failed")

    root = definition(records, STOCK_ROOT)
    proto = definition(records, STOCK_PROTO)
    model = definition(records, STOCK_MODEL)
    stock_material = definition(records, STOCK_MATERIAL)
    mesh = definition(records, STOCK_MESH)
    shared = definition(records, SHARED_COMPASS)
    raven_material = definition(records, RAVEN_MATERIAL)

    check(len(root["data"]) == 164 and int(root["flags"]) == 0x3D, "Dock HUD root layout changed")
    check(bytes(root["data"])[0x0C:0x1C] == bytes(proto["id"]), "Dock HUD root no longer points to goProtoBoatDock at 0x0C")
    check(bytes(root["data"])[0x54:0x64] == bytes(shared["id"]), "Dock HUD root no longer points to shared compass prototype at 0x54")
    check(len(proto["data"]) == 1184 and int(proto["flags"]) == 0x3D, "Dock HUD prototype layout changed")
    check(len(model["data"]) == 80 and int(model["flags"]) == 0x8E, "Dock HUD model layout changed")
    check(len(mesh["data"]) == 388 and int(mesh["flags"]) == 0x98, "Dock HUD mesh layout changed")
    check(len(stock_material["data"]) == len(raven_material["data"]) == 384, "Dock/Raven material payload shapes differ")
    check(bytes(raven_material["id"]) == RAVEN_MATERIAL_ID, "existing Raven material id changed")
    check(struct.unpack_from("<Q", raven_material["data"], 0x10)[0] == RAVEN_MATERIAL_Q10,
          "existing Raven material identity qword +0x10 changed")
    check(struct.unpack_from("<Q", raven_material["data"], 0x20)[0] == STOCK_DOCK_MATERIAL_Q20,
          "existing Raven material no longer preserves Dock-compatible +0x20")

    proto_links = zero_links(group_records(wadmod, records, proto))
    model_links = zero_links(group_records(wadmod, records, model))
    raven_material_links = zero_links(group_records(wadmod, records, raven_material))

    proto_model_links = [r for r in proto_links if r["name"].lower() == STOCK_MODEL.lower() and bytes(r["id"]) == bytes(model["id"])]
    check(len(proto_model_links) == 1, "Dock HUD prototype does not have exactly one model link")
    model_material_links = [r for r in model_links if r["name"].lower() == STOCK_MATERIAL.lower() and bytes(r["id"]) == bytes(stock_material["id"])]
    model_mesh_links = [r for r in model_links if r["name"].lower() == STOCK_MESH.lower() and bytes(r["id"]) == bytes(mesh["id"])]
    check(len(model_material_links) == 1, "Dock HUD model does not have exactly one Dock material link")
    check(len(model_mesh_links) == 1, "Dock HUD model does not have exactly one Dock mesh link")

    raven_diff_def = texture_record(records, RAVEN_DIFFUSE, 1, 0x8021, 356)
    raven_emis_def = texture_record(records, RAVEN_EMISSIVE, 1, 0x8021, 356)
    raven_diff_gpu = texture_record(records, RAVEN_DIFFUSE, 0x1D, 0x80A1)
    raven_emis_gpu = texture_record(records, RAVEN_EMISSIVE, 0x1D, 0x80A1)
    check(bytes(raven_diff_def["id"]) == RAVEN_DIFFUSE_DEF_ID, "Raven diffuse definition id changed")
    check(bytes(raven_emis_def["id"]) == RAVEN_EMISSIVE_DEF_ID, "Raven emissive definition id changed")
    check(bytes(raven_diff_gpu["id"]) == RAVEN_DIFFUSE_GPU_ID, "Raven diffuse GPU id changed")
    check(bytes(raven_emis_gpu["id"]) == RAVEN_EMISSIVE_GPU_ID, "Raven emissive GPU id changed")

    raven_link_by_name = {r["name"]: r for r in raven_material_links}
    check(RAVEN_DIFFUSE in raven_link_by_name and bytes(raven_link_by_name[RAVEN_DIFFUSE]["id"]) == RAVEN_DIFFUSE_DEF_ID,
          "Raven material lost dedicated diffuse link")
    check(RAVEN_EMISSIVE in raven_link_by_name and bytes(raven_link_by_name[RAVEN_EMISSIVE]["id"]) == RAVEN_EMISSIVE_DEF_ID,
          "Raven material lost dedicated emissive link")
    missing_generic = sorted(GENERIC_MATERIAL_LINKS - set(raven_link_by_name))
    check(not missing_generic, f"Raven material lost Dock-compatible generic links: {missing_generic}")

    # Proposed identities are only reserved here. No WAD record is created.
    for name, rid in PROPOSED_IDS.items():
        check(not any(r["name"].lower() == name.lower() for r in records), f"proposed name already exists: {name}")
        check(not any(bytes(r["id"]) == rid for r in records), f"proposed resource id collision: {rid.hex()}")
    icon_hash = name_hash(PROPOSED_ICON_NAME)
    check(icon_hash == 0x45E5C7943749F81C, "proposed IconName hash changed")

    report = {
        "result": RESULT,
        "game_files_read": True,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "r_ui_wad_sha256": digest,
        "stock_hud_contract": {
            "root": brief(root),
            "prototype": brief(proto),
            "model": brief(model),
            "material": brief(stock_material),
            "mesh": brief(mesh),
            "shared_compass": brief(shared),
            "root_prototype_ref_offset": "0x0C",
            "root_shared_compass_ref_offset": "0x54",
            "prototype_model_link_count": len(proto_model_links),
            "model_material_link_count": len(model_material_links),
            "model_mesh_link_count": len(model_mesh_links),
        },
        "existing_raven_artwork": {
            "material": brief(raven_material),
            "material_qword_0x10": f"{RAVEN_MATERIAL_Q10:016X}",
            "material_qword_0x20": f"{STOCK_DOCK_MATERIAL_Q20:016X}",
            "diffuse_definition": brief(raven_diff_def),
            "diffuse_gpu": brief(raven_diff_gpu),
            "emissive_definition": brief(raven_emis_def),
            "emissive_gpu": brief(raven_emis_gpu),
            "generic_links_preserved": sorted(GENERIC_MATERIAL_LINKS),
        },
        "reuse_decision": {
            "existing_raven_material_payload_shape_matches_dock": True,
            "existing_raven_material_is_dock_compatible": True,
            "existing_raven_material_already_owns_dedicated_diffuse_emissive": True,
            "stock_hud_geometry_can_remain_shared": True,
            "new_material_payload_required": False,
            "new_texture_definition_payloads_required": False,
            "new_texture_gpu_payloads_required": False,
            "new_mesh_payload_required": False,
            "minimal_new_payloads": [PROPOSED_ROOT, PROPOSED_PROTO, PROPOSED_MODEL],
            "minimal_new_payload_count": 3,
        },
        "proposed_compass_hud_identity": {
            "IconName_source_string": PROPOSED_ICON_NAME,
            "IconName_hash": f"{icon_hash:016X}",
            "root": {"name": PROPOSED_ROOT, "id": PROPOSED_IDS[PROPOSED_ROOT].hex()},
            "prototype": {"name": PROPOSED_PROTO, "id": PROPOSED_IDS[PROPOSED_PROTO].hex()},
            "model": {"name": PROPOSED_MODEL, "id": PROPOSED_IDS[PROPOSED_MODEL].hex()},
            "material_reused": RAVEN_MATERIAL,
            "mesh_reused": STOCK_MESH,
            "shared_compass_reused": SHARED_COMPASS,
        },
        "conclusion": CONCLUSION,
        "next_gate": (
            "Build an offline three-payload Raven compass HUD clone from goboatdock/goProtoBoatDock/MDL_boatdock. "
            "Retarget only the cloned model material link to MAT_AE4AD85BB993F040, keep MG_boatdock_0 shared, "
            "keep goProtocompassicons at root offset 0x54, and do not modify wad_r_perm.dcb yet."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    check(sha256(wad_path.read_bytes()) == digest, "r_ui.wad changed during read-only gate")
    print(RESULT)
    print(f"  r_ui.wad: {digest}")
    print(f"  Raven material: {RAVEN_MATERIAL}")
    print(f"  Raven diffuse: {RAVEN_DIFFUSE}")
    print(f"  Raven emissive: {RAVEN_EMISSIVE}")
    print("  stock MG_boatdock_0 reusable: true")
    print("  minimal new payloads: 3")
    print(f"  proposed IconName hash: {icon_hash:016X}")
    print(f"  conclusion: {CONCLUSION}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
