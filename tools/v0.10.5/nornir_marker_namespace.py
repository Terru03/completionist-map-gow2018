#!/usr/bin/env python3
"""Reserve Nornir marker identities without registering anything in the game."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from collectible_catalogue import marker_identity
from raven_catalogue import Dcb, PROVEN_NAME, PROVEN_UID, name_hash


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
RAVENS = REPO / "catalogue/odins-ravens.json"
OUTPUT = REPO / "config/collectibles/v0.10.5/nornir-marker-namespace.json"
INSTALLED_AUDIT = REPO / "docs/research/nornir-installed-marker-id-audit.json"
NAMESPACE_NAME = "Completionist_V105_Nornir_Family"
FAMILIES = {"nornir_chest", "nornir_seal", "nornir_bell", "nornir_mechanism"}
CHILD_FAMILIES = FAMILIES - {"nornir_chest"}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def marker_record(row: dict) -> dict:
    return {
        "catalogue_id": row["catalogue_id"],
        "family": row["family"],
        "name": row["marker"]["name"],
        "uid": row["marker"]["uid"],
    }


def build_manifest(catalogue: dict, ravens: dict) -> dict:
    """Pin one independent marker UID per chest and child, plus exact ownership."""
    all_rows = catalogue["collectibles"]
    nornir = [row for row in all_rows if row["family"] in FAMILIES]
    parents = {row["catalogue_id"]: row for row in nornir
               if row["family"] == "nornir_chest"}
    children = [row for row in nornir if row["family"] in CHILD_FAMILIES]
    require(len(nornir) == 88 and len(parents) == 22 and len(children) == 66,
            "Nornir marker census differs")
    require(Counter(row["family"] for row in children) ==
            {"nornir_seal": 30, "nornir_bell": 24, "nornir_mechanism": 12},
            "Nornir child marker census differs")
    require(len({row["catalogue_id"] for row in nornir}) == len(nornir),
            "duplicate Nornir catalogue identity")

    raven_rows = ravens["ravens"]
    reserved_names = {PROVEN_NAME, *(row["marker"]["name"] for row in raven_rows)}
    reserved_uids = {PROVEN_UID, *(row["marker"]["uid"] for row in raven_rows)}
    reserved_names.update(row["marker"]["name"] for row in all_rows
                          if row["family"] not in FAMILIES)
    reserved_uids.update(row["marker"]["uid"] for row in all_rows
                         if row["family"] not in FAMILIES)
    namespace_uid = f"{name_hash(NAMESPACE_NAME):016X}"
    require(namespace_uid not in reserved_uids,
            "Nornir namespace UID collides with another marker")
    names: set[str] = set()
    uids: set[str] = {namespace_uid}
    for row in nornir:
        marker = row["marker"]
        name, uid = marker["name"], marker["uid"]
        require(name not in reserved_names and uid not in reserved_uids,
                f"Nornir marker reuses reserved Raven/other identity: {row['catalogue_id']}")
        require(name not in names and uid not in uids,
                f"duplicate Nornir marker identity: {row['catalogue_id']}")
        names.add(name)
        uids.add(uid)
        family_name = "".join(part.title() for part in row["family"].split("_"))
        require(marker["map_resource"] == f"goMapIconCompletionist{family_name}" and
                marker["compass_class"] == f"Completionist{family_name}",
                f"Nornir marker uses another family's visual/class: {row['catalogue_id']}")
        if row["family"] == "nornir_chest":
            identity = row["native"]["instance_guid"]
        else:
            parent_id = row["progression"].get("parent_catalogue_id")
            require(parent_id in parents and row["native"].get("parent_catalogue_id") == parent_id,
                    f"Nornir child has no exact chest owner: {row['catalogue_id']}")
            identity = f"{parent_id}:{row['native']['reference_name'].lower()}"
        require((name, uid) == marker_identity(row["family"], identity),
                f"Nornir marker UID/name differs from its physical identity: {row['catalogue_id']}")

    by_parent: dict[str, list[dict]] = defaultdict(list)
    for child in children:
        by_parent[child["progression"]["parent_catalogue_id"]].append(child)
    groups = []
    for parent_id, parent in sorted(parents.items()):
        siblings = sorted(by_parent[parent_id], key=lambda row: row["catalogue_id"])
        require(len(siblings) == 3, f"Nornir chest does not own three children: {parent_id}")
        groups.append({
            "parent": marker_record(parent),
            "native_parent_instance_guid": parent["native"]["instance_guid"],
            "children": [marker_record(child) for child in siblings],
        })
    return {
        "schema": 1,
        "status": "OFFLINE_IDENTITY_RESERVATION_ONLY",
        "namespace": {"name": NAMESPACE_NAME, "uid": namespace_uid},
        "native_registration_allowed": False,
        "parent_count": 22,
        "child_count": 66,
        "reserved_raven_marker_count": len(raven_rows) + 1,
        "groups": groups,
    }


def audit_installed_game(game_root: Path, manifest: dict) -> dict:
    """Check reserved UIDs against native marker and route tables, read only."""
    root = game_root / "exec/dc/pc_le"
    master = Dcb(root / "mapmaster.dcb")
    coords = Dcb(root / "mapcoords.dcb")
    graph = Dcb(root / "compassgraph.dcb")
    marker_ids: set[str] = set()
    for realm in master.array(master.root("MAP_PERM_DATA", 0x415) + 0x10, 0x40):
        for region in master.array(realm + 0x30, 0x68):
            for offset in master.array(region + 0x38, 0x48):
                marker_ids.add(f"{master.unpack('<Q', offset)[0]:016X}")
    coordinate_ids = {f"{coords.unpack('<Q', offset)[0]:016X}" for offset in
                      coords.array(coords.root("MAP_COORDS_PERM_DATA", 0x40A), 0x28)}
    helper_ids = {f"{graph.unpack('<Q', offset)[0]:016X}" for offset in
                  graph.array(graph.root("COMPASS_HELPER_PERM_DATA", 0x40C), 0x28)}
    export_ids = {f"{name_hash(name):016X}" for dcb in (master, coords, graph)
                  for name in dcb.exports}
    proposed = {manifest["namespace"]["uid"]}
    proposed.update(record["uid"] for group in manifest["groups"]
                    for record in [group["parent"], *group["children"]])
    collisions = sorted(proposed & (marker_ids | coordinate_ids | helper_ids | export_ids))
    require(not collisions, f"Nornir marker UID collides with installed game: {collisions}")
    return {
        "schema": 1,
        "result": "NORNIR_INSTALLED_MARKER_IDS_CLEAR_READ_ONLY",
        "game_files_written": False,
        "namespace_manifest_sha256": hashlib.sha256(
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).hexdigest(),
        "sources": [dcb.evidence() for dcb in (master, coords, graph)],
        "installed_counts": {
            "map_marker_uids": len(marker_ids),
            "map_coordinate_uids": len(coordinate_ids),
            "compass_helper_uids": len(helper_ids),
        },
        "proposed_nornir_uid_count": len(proposed),
        "collision_count": 0,
        "frozen_raven_marker_present": PROVEN_UID in marker_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--audit-output", type=Path, default=INSTALLED_AUDIT)
    args = parser.parse_args()
    manifest = build_manifest(json.loads(CATALOGUE.read_text(encoding="utf-8")),
                              json.loads(RAVENS.read_text(encoding="utf-8")))
    audit = audit_installed_game(args.game_root, manifest) if args.game_root else None
    target = args.output.resolve()
    require(target != REPO and REPO in target.parents, "output must stay inside repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if audit is not None:
        audit_target = args.audit_output.resolve()
        require(audit_target != REPO and REPO in audit_target.parents and
                not audit_target.is_relative_to(args.game_root.resolve()),
                "audit output must stay inside repository and outside game root")
        audit_target.parent.mkdir(parents=True, exist_ok=True)
        audit_target.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
        print(f"NORNIR_INSTALLED_ID_AUDIT_READ_ONLY clear={audit['proposed_nornir_uid_count']}")
    print(f"NORNIR_MARKER_NAMESPACE_OFFLINE parent=22 child=66 uid={manifest['namespace']['uid']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
