#!/usr/bin/env python3
"""Verify two non-Ship-Head overrides lack the inferred Shiphead parent."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import raven_catalogue


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
TARGET_IDS = (
    "artefact_989065ff4bde64f5ec957da2759037cb",
    "artefact_c9b7e23040c21e2da5fe8ba4be8ad415",
)
INFERRED_TARGET = b"RegionSummary_CALS_Shiphead_Parent"


def scan(game_root: Path) -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    by_id = {row["catalogue_id"]: row for row in catalogue["collectibles"]}
    results = []
    for cid in TARGET_IDS:
        row = by_id[cid]
        if row["family"] != "artefact" or row["subtype"] == "Ship Head" or row["progression"]["parent_quest"] is not None:
            raise ValueError(f"non-Ship-Head catalogue classification changed: {cid}")
        wad = game_root / "exec/wad/pc_le" / row["source"]["wad"]
        raw = wad.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["source"]["wad_sha256"]:
            raise ValueError(f"WAD source hash changed: {wad}")
        offset = int(row["source"]["override_offset"], 16)
        hits = [record for record in raven_catalogue.parse_wad(raw) if record["offset"] == offset]
        if len(hits) != 1 or hits[0]["id"].hex() != row["native"]["override_record_id"]:
            raise ValueError(f"Artefact override identity changed: {cid}")
        record = hits[0]
        if INFERRED_TARGET in record["data"]:
            raise ValueError(f"inferred parent actually appears in exact override: {cid}")
        results.append({
            "catalogue_id": cid, "subtype": row["subtype"], "wad": wad.name,
            "wad_sha256": digest, "override_offset": row["source"]["override_offset"],
            "override_record_id": record["id"].hex(), "override_name": record["name"],
            "searched_parent": INFERRED_TARGET.decode(), "parent_present_in_exact_override": False,
            "classification": "region_only_shiphead_inference_rejected",
        })
    return {
        "schema": 1, "status": "TWO_CROSS_SUBTYPE_REGION_INFERENCES_REJECTED",
        "catalogue_lf_sha256": hashlib.sha256(CATALOGUE.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "rows": results,
        "conclusion": "Exact override bytes do not name the inferred Shiphead parent; no direct per-object parent proof follows from region alone.",
        "runtime_generation_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = scan(args.game_root)
    target = args.output.resolve()
    if target == REPO or REPO not in target.parents:
        raise ValueError("output must stay inside repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ARTEFACT_PARENT_INFERENCE_REJECTED rows=2 game_files_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
