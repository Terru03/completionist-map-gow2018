#!/usr/bin/env python3
"""Read pinned native UI assets for Legendary map-class evidence only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import raven_catalogue  # Generic WAD/DCB readers; no Raven resource IDs used.

MAPMASTER_SHA256 = "aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0"
MAPMASTER_BYTES = 74128
UI_SHA256 = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require_pinned(path: Path, expected_sha: str, expected_size: int | None = None) -> bytes:
    raw = path.read_bytes()
    if digest(raw) != expected_sha or (expected_size is not None and len(raw) != expected_size):
        raise ValueError(f"native asset baseline differs: {path}")
    return raw


def scan(mapmaster: Path, ui_wad: Path) -> dict:
    master_raw = require_pinned(mapmaster, MAPMASTER_SHA256, MAPMASTER_BYTES)
    ui_raw = require_pinned(ui_wad, UI_SHA256)
    stage_path = REPO / "tools/v0.10.4/build-raven-twin-stage-a-offline.py"
    spec = importlib.util.spec_from_file_location("legendary_marker_dcb_reader", stage_path)
    if spec is None or spec.loader is None:
        raise ValueError("native marker parser missing")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    dcb = raven_catalogue.Dcb(mapmaster)
    markers = stage.marker_snapshot(dcb)
    ui_records = raven_catalogue.parse_wad(ui_raw)
    ui_names = sorted({r["name"] for r in ui_records if "mapicon" in r["name"].lower()})
    icon_counts = Counter(r["icon"] for r in markers)
    if len(markers) != 382 or len(ui_records) != 53777 or len(ui_names) != 119:
        raise ValueError("pinned marker/UI census changed")
    terms = ("legendary", "chest")
    native_class_hits = sorted(name for name in icon_counts if any(term in name.lower() for term in terms))
    ui_class_hits = sorted(name for name in ui_names if any(term in name.lower() for term in terms))
    return {
        "schema": 1,
        "status": "NEGATIVE_CLASS_NAME_EVIDENCE_ONLY",
        "steam_build_id": "11168363",
        "mapmaster": {"bytes": len(master_raw), "sha256": digest(master_raw),
                      "marker_rows": len(markers), "icon_class_counts": dict(sorted(icon_counts.items())),
                      "legendary_or_chest_class_hits": native_class_hits},
        "r_ui_wad": {"bytes": len(ui_raw), "sha256": digest(ui_raw),
                     "records": len(ui_records), "distinct_mapicon_names": ui_names,
                     "legendary_or_chest_name_hits": ui_class_hits},
        "native_marker_coverage_proven": False,
        "custom_marker_resource_ready": False,
        "runtime_generation_allowed": False,
        "interpretation": "No Legendary/Chest-named class appears in these two pinned assets; dynamic or differently named paths remain unproved.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapmaster", type=Path, default=REPO / "build/native-source-cache/mapmaster.dcb")
    parser.add_argument("--ui-wad", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar/exec/wad/pc_le/r_ui.wad"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = scan(args.mapmaster, args.ui_wad)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"LEGENDARY_MARKER_ASSETS {report['status']} markers=382 ui_mapicon_names=119 generation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
