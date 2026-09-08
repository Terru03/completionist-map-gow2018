"""Reduce the archived compass HUD chain trace to each class-local authored subtree.

This is intentionally report-only. It does not open God of War files. The input is
completionist-v104-compass-hud-gameobject-chain.json produced by the proven
read-only tracer.

For each stock CompassIconClass resource this reducer keeps only:
  instance root -> class prototype -> MDL -> MAT/MG -> material children
and separately proves that the root's 0x54 reference goes to the shared
``goProtocompassicons`` resource.

The goal is to isolate the smallest DockPoint artwork/resource contract before
building any Raven-only HUD clone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

RESULT = "REPORT_ONLY_COMPASS_HUD_LOCAL_SUBTREES"
SOURCE_RESULT = "READ_ONLY_COMPASS_HUD_GAMEOBJECT_CHAIN"
SHARED_COMPASS = "goProtocompassicons"
PROTOTYPES = {
    "MAIN": "goProtoMainQuest",
    "SIDE": "goProtoSideQuest",
    "VendorLocation": "goProtoVendor",
    "Valkyrie": "goProtoValkyrie",
    "DockPoint": "goProtoBoatDock",
    "FastTravel": "goProtoFastTravel",
    "AreaEntrance": "goProtoEntrance",
    "FightLocation": "goProtoFightLocation",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def compact(node: dict) -> dict:
    return {
        "record_index": int(node["record_index"]),
        "name": str(node["name"]),
        "id": str(node["id"]),
        "flags": str(node["flags"]),
        "bytes": int(node["bytes"]),
        "type_key": node.get("type_key"),
        "file_offset": node.get("file_offset"),
    }


def node(trace: dict, index: int) -> dict:
    result = trace["nodes"].get(str(index))
    check(result is not None, f"trace is missing node {index}")
    return result


def nodes_named(trace: dict, name: str) -> list[dict]:
    return [n for n in trace["nodes"].values() if str(n["name"]).lower() == name.lower()]


def unique_named(trace: dict, name: str) -> dict:
    hits = nodes_named(trace, name)
    check(len(hits) == 1, f"expected exactly one {name!r} node, found {len(hits)}")
    return hits[0]


def payload_edge_targets(trace: dict, source_index: int, offset: str) -> list[dict]:
    relation = f"payload_id_ref@{offset}"
    target_indices = {
        int(e["to"])
        for e in trace["edges"]
        if int(e["from"]) == source_index and str(e["relation"]) == relation
    }
    return [node(trace, i) for i in sorted(target_indices)]


def group_definition_targets(trace: dict, source: dict) -> list[dict]:
    target_indices: set[int] = set()
    for link in source.get("zero_data_group_links", []):
        for target in link.get("definition_targets", []):
            target_indices.add(int(target))
    return [node(trace, i) for i in sorted(target_indices)]


def names(items: Iterable[dict]) -> list[str]:
    return [str(x["name"]) for x in items]


def material_branch(trace: dict, material: dict) -> dict:
    children = group_definition_targets(trace, material)
    textures = [x for x in children if str(x["name"]).lower().startswith("tx_")]
    non_textures = [x for x in children if x not in textures]
    return {
        "material": compact(material),
        "textures": [compact(x) for x in textures],
        "other_group_dependencies": [compact(x) for x in non_textures],
    }


def class_branch(cls: str, trace: dict) -> dict:
    root = node(trace, int(trace["root"]["record_index"]))
    prototype_name = PROTOTYPES[cls]
    prototype = unique_named(trace, prototype_name)
    shared = unique_named(trace, SHARED_COMPASS)

    refs = {str(x["offset"]): str(x["id"]) for x in root.get("payload_id_refs", [])}
    check("0xC" in refs and "0x54" in refs,
          f"{cls} root does not expose the expected 0xC/0x54 resource references")

    at_c = payload_edge_targets(trace, int(root["record_index"]), "0xC")
    at_54 = payload_edge_targets(trace, int(root["record_index"]), "0x54")
    check(int(prototype["record_index"]) in {int(x["record_index"]) for x in at_c},
          f"{cls} 0xC does not resolve to {prototype_name}")
    check(int(shared["record_index"]) in {int(x["record_index"]) for x in at_54},
          f"{cls} 0x54 does not resolve to {SHARED_COMPASS}")

    proto_children = group_definition_targets(trace, prototype)
    models = [x for x in proto_children if str(x["name"]).lower().startswith("mdl_")]
    check(models, f"{prototype_name} has no MDL group dependency")

    model_rows = []
    for model in models:
        model_children = group_definition_targets(trace, model)
        materials = [x for x in model_children if str(x["name"]).lower().startswith("mat_")]
        meshes = [x for x in model_children if str(x["name"]).lower().startswith("mg_")]
        other = [x for x in model_children if x not in materials and x not in meshes]
        model_rows.append({
            "model": compact(model),
            "materials": [material_branch(trace, x) for x in materials],
            "meshes": [compact(x) for x in meshes],
            "other_group_dependencies": [compact(x) for x in other],
        })

    return {
        "root": compact(root),
        "root_resource_refs": {
            "class_prototype_0xC": {
                "id": refs["0xC"],
                "expected": compact(prototype),
                "all_definition_targets": [compact(x) for x in at_c],
            },
            "shared_compass_0x54": {
                "id": refs["0x54"],
                "expected": compact(shared),
                "all_definition_targets": [compact(x) for x in at_54],
            },
        },
        "prototype": compact(prototype),
        "prototype_group_dependencies": [compact(x) for x in proto_children],
        "models": model_rows,
    }


def collect_textures(branch: dict) -> list[dict]:
    out = []
    seen = set()
    for model in branch["models"]:
        for material in model["materials"]:
            for texture in material["textures"]:
                key = (texture["record_index"], texture["id"])
                if key not in seen:
                    seen.add(key)
                    out.append(texture)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    source_path = args.input.resolve()
    out_path = args.output.resolve()
    check(source_path.is_file(), f"missing source report: {source_path}")
    check(source_path != out_path, "input and output report paths must differ")

    source_raw = source_path.read_bytes()
    source = json.loads(source_raw)
    check(source.get("result") == SOURCE_RESULT,
          f"unexpected source result: {source.get('result')!r}")
    check(source.get("game_files_written") is False, "source report did not prove game-files read-only")
    check(source.get("save_state_written") is False, "source report did not prove save-state read-only")
    check(source.get("progression_state_written") is False, "source report did not prove progression-state read-only")
    check(source.get("marker_state_written") is False, "source report did not prove marker-state read-only")

    traces = source["traces"]
    check(set(PROTOTYPES).issubset(traces), "source report is missing one or more stock HUD traces")

    classes = {cls: class_branch(cls, traces[cls]) for cls in PROTOTYPES}
    dock = classes["DockPoint"]
    dock_textures = collect_textures(dock)
    dock_texture_names = names(dock_textures)

    root_shapes = {
        cls: {
            "flags": branch["root"]["flags"],
            "bytes": branch["root"]["bytes"],
            "prototype_ref_offset": "0xC",
            "shared_compass_ref_offset": "0x54",
            "shared_compass_id": branch["root_resource_refs"]["shared_compass_0x54"]["id"],
        }
        for cls, branch in classes.items()
    }
    shape_values = {
        (x["flags"], x["bytes"], x["shared_compass_id"])
        for x in root_shapes.values()
    }
    stock_root_contract_shared = len(shape_values) == 1
    check(stock_root_contract_shared, "stock compass roots do not share the expected root contract")

    dock_models = [m["model"]["name"] for m in dock["models"]]
    dock_materials = [
        material["material"]["name"]
        for model in dock["models"]
        for material in model["materials"]
    ]
    dock_meshes = [
        mesh["name"]
        for model in dock["models"]
        for mesh in model["meshes"]
    ]

    check("goProtoBoatDock" == dock["prototype"]["name"], "Dock prototype mismatch")
    check("MDL_boatdock" in dock_models, "Dock model mismatch")
    check("MG_boatdock_0" in dock_meshes, "Dock mesh mismatch")
    check(any("docklocation" in x.lower() for x in dock_texture_names),
          "Dock material did not resolve docklocation artwork textures")

    report = {
        "result": RESULT,
        "source_report": source_path.name,
        "source_report_sha256": sha256_bytes(source_raw),
        "game_files_read": False,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "stock_root_contract_shared": stock_root_contract_shared,
        "root_shapes": root_shapes,
        "classes": classes,
        "dock_local_contract": {
            "root": dock["root"]["name"],
            "prototype": dock["prototype"]["name"],
            "models": dock_models,
            "materials": dock_materials,
            "meshes": dock_meshes,
            "artwork_textures": dock_texture_names,
            "shared_compass": SHARED_COMPASS,
            "shared_compass_id": dock["root_resource_refs"]["shared_compass_0x54"]["id"],
        },
        "conclusion": "DOCK_LOCAL_HUD_SUBTREE_ISOLATED",
        "next_gate": (
            "Use the isolated DockPoint class-local contract as the template for an offline Raven-only HUD clone. "
            "Clone the Dock root/prototype/model/material/mesh identities to new Raven-only identities, keep the shared "
            "goProtocompassicons reference at root offset 0x54, and replace only the clone's Dock artwork texture dependencies. "
            "Do not mutate stock goboatdock resources and do not point IconName at the map GameObject chain."
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    check(sha256_bytes(source_path.read_bytes()) == report["source_report_sha256"],
          "source report changed during report-only reduction")

    print(RESULT)
    print(f"  source report: {source_path}")
    print(f"  stock classes reduced: {len(classes)}")
    print(f"  stock root contract shared: {str(stock_root_contract_shared).lower()}")
    print(f"  Dock root: {dock['root']['name']}")
    print(f"  Dock prototype: {dock['prototype']['name']}")
    print(f"  Dock models: {', '.join(dock_models)}")
    print(f"  Dock materials: {', '.join(dock_materials)}")
    print(f"  Dock meshes: {', '.join(dock_meshes)}")
    print(f"  Dock artwork textures: {', '.join(dock_texture_names)}")
    print(f"  shared compass: {SHARED_COMPASS}")
    print(f"  output: {out_path}")
    print("  game files read: false")
    print("  game files written: false")


if __name__ == "__main__":
    main()
