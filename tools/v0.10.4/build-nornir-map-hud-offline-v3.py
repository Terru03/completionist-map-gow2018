#!/usr/bin/env python3
"""WAD-header-safe Nornir map/HUD offline builder wrapper.

The Nornir resident-art texpack names are valid external texture names, but the
WAD record header has a fixed 56-byte field with one byte reserved for NUL, so
record names must be <=55 ASCII bytes. The original Nornir diffuse/emissive
names are 58/59 bytes and cannot be serialized into r_ui.wad.

This wrapper keeps the already-proven resident payloads and file-hash IDs, keeps
the collision-safe independent GPU user hashes from v2, and uses short internal
WAD header aliases that retain the exact 16-hex file-hash suffix. No game file
is modified.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2_PATH = HERE / "build-nornir-map-hud-offline-v2.py"


def load_v2():
    spec = importlib.util.spec_from_file_location("completionist_nornir_map_hud_v2", V2_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v2 builder: {V2_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2 = load_v2()
base = v2.base

ART_RESOURCE_NAMES = {
    "diffuse": "TX_completionist_nornir_chest_map_diffuse_0A43AEB29D6F80DA",
    "emissive": "TX_completionist_nornir_chest_map_emissive_58012A499511A0BB",
}
WAD_HEADER_NAMES = {
    "diffuse": "TX_completionist_nornir_chest_diff_0A43AEB29D6F80DA",
    "emissive": "TX_completionist_nornir_chest_emis_58012A499511A0BB",
}

for label in ("diffuse", "emissive"):
    base.check(len(ART_RESOURCE_NAMES[label].encode("ascii")) > 55,
               f"{label}: original art name no longer exceeds WAD header limit; re-audit wrapper")
    base.check(len(WAD_HEADER_NAMES[label].encode("ascii")) <= 55,
               f"{label}: WAD header alias is still too long")
    base.check(WAD_HEADER_NAMES[label].endswith(f"_{base.FILE_HASH[label]:016X}"),
               f"{label}: WAD header alias lost the file-hash suffix")

# The WAD resource names are internal header aliases. The file-hash constants,
# resident payloads and texpack identities stay exactly as already proven.
base.NORNIR["diffuse"] = WAD_HEADER_NAMES["diffuse"]
base.NORNIR["emissive"] = WAD_HEADER_NAMES["emissive"]


def parse_art_report_header_safe(path: Path):
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
        base.check(row["resource_name"] == ART_RESOURCE_NAMES[label],
                   f"{label}: resident-art resource name changed")
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

        value = row["texpack_stream"]["user_hash"]
        texpack_users[label] = int(value, 16) if isinstance(value, str) else int(value)

    # Preserve the v2 causal finding: texpack metadata collides, while WAD GPU
    # identities are intentionally independent and collision checked.
    base.check(texpack_users["diffuse"] == texpack_users["emissive"],
               "Pinned texpack user-hash behavior changed; re-audit before proceeding")
    base.check(v2.GPU_USER_HASHES["diffuse"] != v2.GPU_USER_HASHES["emissive"],
               "deterministic Nornir GPU user hashes collide")

    report.setdefault("map_hud_builder_notes", {})
    report["map_hud_builder_notes"].update({
        "wad_header_name_limit_ascii_bytes": 55,
        "art_resource_names": dict(ART_RESOURCE_NAMES),
        "wad_header_names": dict(WAD_HEADER_NAMES),
        "file_hashes_preserved": True,
        "resident_payloads_preserved": True,
        "texpack_user_hashes_collide": True,
        "wad_gpu_user_hashes": {
            "diffuse": f"{v2.GPU_USER_HASHES['diffuse']:016X}",
            "emissive": f"{v2.GPU_USER_HASHES['emissive']:016X}",
        },
    })
    return report, residents, dict(v2.GPU_USER_HASHES)


base.parse_art_report = parse_art_report_header_safe
_original_build_wad = base.build_wad


def build_wad_with_alias_report(source_raw: bytes, art_report: Path):
    candidate, report = _original_build_wad(source_raw, art_report)
    report["texture_header_aliases"] = {
        label: {
            "art_resource_name": ART_RESOURCE_NAMES[label],
            "wad_header_name": WAD_HEADER_NAMES[label],
            "wad_header_ascii_bytes": len(WAD_HEADER_NAMES[label].encode("ascii")),
            "file_hash": f"{base.FILE_HASH[label]:016X}",
        }
        for label in ("diffuse", "emissive")
    }
    report["all_wad_header_names_fit_55_bytes"] = True
    return candidate, report


base.build_wad = build_wad_with_alias_report


if __name__ == "__main__":
    base.main()
