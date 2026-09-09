#!/usr/bin/env python3
"""Collision-safe wrapper for the offline Nornir map/HUD builder.

The pinned GOWTool Nornir texpack reports the same texpack `user_hash` for the
BC7 diffuse and BC1 emissive entries because both were authored from the same
source image. That texpack metadata is useful for locating streamed payloads,
but it cannot serve as the WAD GPU resource identity for two distinct texture
resources.

The runtime-proven Raven WAD already uses independent GPU user hashes from its
texture file hashes. This wrapper preserves the exact resident payload gate and
all structural/reversibility checks from build-nornir-map-hud-offline.py, but
assigns two deterministic, collision-checked Nornir GPU user hashes instead of
reusing the colliding texpack metadata.

No game file is modified by this wrapper; the underlying builder remains fully
offline and performs the same frozen-Raven normalization proofs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "build-nornir-map-hud-offline.py"


def load_base():
    spec = importlib.util.spec_from_file_location("completionist_nornir_map_hud_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load base builder: {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base()

# Pinned deterministic identities. These are folded-name hashes of dedicated
# internal GPU identity labels, not file hashes and not texpack stream metadata.
GPU_USER_HASHES = {
    "diffuse": 0x4806DF7DA196751C,   # CompletionistNornirChestDiffuseGPU
    "emissive": 0xA01A0B577D244D17,  # CompletionistNornirChestEmissiveGPU
}


def parse_art_report_collision_safe(path: Path):
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    base.check(report.get("result") == base.EXPECTED_ART_REPORT,
               "Nornir resident-art report result changed")
    base.check(report.get("source_raven_wad_sha256") == base.EXPECTED_WAD,
               "resident-art source WAD changed")
    base.check(report.get("nornir_texpack_sha256") == base.EXPECTED_TEXPACK,
               "Nornir texpack SHA changed")
    base.check(report.get("ready_for_nornir_wad_clone") is True,
               "resident-art report is not ready for WAD clone")

    rows = {row["label"]: row for row in report.get("rows", [])}
    base.check(set(rows) == {"diffuse", "emissive"},
               "resident-art report does not contain exactly diffuse/emissive")

    residents = {}
    texpack_users = {}
    for label in ("diffuse", "emissive"):
        row = rows[label]
        expected_bytes, expected_sha = base.EXPECTED_RESIDENT[label]
        base.check(row["resource_name"] == base.NORNIR[label],
                   f"{label}: resource name changed")
        base.check(int(row["file_hash"], 16) == base.FILE_HASH[label],
                   f"{label}: file hash changed")
        base.check(row["resident_bytes"] == expected_bytes and row["resident_sha256"] == expected_sha,
                   f"{label}: resident contract changed")

        resident_path = Path(row["output"])
        base.check(resident_path.is_file(), f"{label}: resident payload missing: {resident_path}")
        raw = resident_path.read_bytes()
        base.check(len(raw) == expected_bytes and base.sha(raw) == expected_sha,
                   f"{label}: resident payload bytes changed")
        residents[label] = raw

        user_value = row["texpack_stream"]["user_hash"]
        texpack_users[label] = int(user_value, 16) if isinstance(user_value, str) else int(user_value)

    # The failure that introduced this wrapper is deliberately preserved as a
    # diagnostic fact, while the two WAD GPU identities are independent.
    base.check(texpack_users["diffuse"] == texpack_users["emissive"],
               "Pinned Nornir texpack user-hash behavior changed; re-audit before proceeding")

    base.check(GPU_USER_HASHES["diffuse"] != GPU_USER_HASHES["emissive"],
               "deterministic Nornir GPU user hashes collide")
    base.check(base.folded_name_hash("CompletionistNornirChestDiffuseGPU") == GPU_USER_HASHES["diffuse"],
               "pinned diffuse GPU user hash changed")
    base.check(base.folded_name_hash("CompletionistNornirChestEmissiveGPU") == GPU_USER_HASHES["emissive"],
               "pinned emissive GPU user hash changed")

    report.setdefault("map_hud_builder_notes", {})
    report["map_hud_builder_notes"].update({
        "texpack_user_hashes_collide": True,
        "texpack_user_hash": f"{texpack_users['diffuse']:016X}",
        "wad_gpu_user_hash_source": "deterministic dedicated Nornir GPU identity labels",
        "wad_gpu_user_hashes": {
            "diffuse": f"{GPU_USER_HASHES['diffuse']:016X}",
            "emissive": f"{GPU_USER_HASHES['emissive']:016X}",
        },
    })
    return report, residents, dict(GPU_USER_HASHES)


base.parse_art_report = parse_art_report_collision_safe


if __name__ == "__main__":
    base.main()
