#!/usr/bin/env python3
"""Strict same-name texture proof for Nornir offline WAD build.

Pick one GPU row and one definition row by exact WAD shape. Treat all other
same-name rows as refs. Each ref must sit in a Nornir group already marked for
removal. This keeps byte-exact Raven normalization strict.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4_PATH = HERE / "build-nornir-map-hud-offline-v4.py"


def load_v4():
    spec = importlib.util.spec_from_file_location("completionist_nornir_map_hud_v4", V4_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load v4 builder: {V4_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v4 = load_v4()
base = v4.base
_v4_build_wad = base.build_wad
_classifications: dict[str, dict] = {}


def record_facts(records: list[dict], index: int, classification: str,
                 group_removal: set[int]) -> dict:
    row = records[index]
    parent_index = row["parent"]
    parent = records[parent_index] if parent_index is not None else None
    return {
        "classification": classification,
        "record_index": index,
        "original_offset": row["original_offset"],
        "payload_index": row["payload_index"],
        "kind": f"0x{row['kind']:X}",
        "flags": f"0x{row['flags']:04X}",
        "data_bytes": len(row["data"]),
        "id": row["id"].hex(),
        "parent_index": parent_index,
        "parent_kind": None if parent is None else f"0x{parent['kind']:X}",
        "parent_name": None if parent is None else parent["name"],
        "in_scheduled_nornir_group": index in group_removal,
    }


def strict_texture_removal_rows(records: list[dict], name: str,
                                group_removal: set[int]) -> set[int]:
    label_hits = [label for label in ("diffuse", "emissive")
                  if base.NORNIR[label].lower() == name.lower()]
    base.check(len(label_hits) == 1, f"unknown Nornir texture name in removal proof: {name!r}")
    label = label_hits[0]

    gpu_index, _ = base.unique_texture(records, name, gpu=True)
    definition_index, _ = base.unique_texture(records, name, gpu=False)
    base.check(gpu_index != definition_index, f"{label}: GPU and definition rows alias")
    base.check(gpu_index not in group_removal,
               f"{label}: standalone GPU row is inside a scheduled Nornir group")
    base.check(definition_index not in group_removal,
               f"{label}: standalone definition row is inside a scheduled Nornir group")

    same_name = [i for i, row in enumerate(records) if row["name"].lower() == name.lower()]
    extra_indices = [i for i in same_name if i not in {gpu_index, definition_index}]
    extras = []
    for index in extra_indices:
        row = records[index]
        if row["kind"] == 1 and row["flags"] == 0 and not row["data"]:
            classification = "zero_data_dependency_link"
        elif row["data"]:
            classification = "data_bearing_same_name_group_record"
        else:
            classification = "zero_data_same_name_group_record"
        facts = record_facts(records, index, classification, group_removal)
        base.check(facts["in_scheduled_nornir_group"],
                   f"{label}: unexpected same-name record outside scheduled Nornir groups: {facts!r}")
        extras.append(facts)

    _classifications[label] = {
        "resource_name": name,
        "same_name_record_count": len(same_name),
        "gpu": record_facts(records, gpu_index, "standalone_gpu_texture", group_removal),
        "definition": record_facts(records, definition_index, "standalone_texture_definition", group_removal),
        "additional_record_count": len(extras),
        "additional_records": extras,
        "standalone_records_removed_explicitly": True,
        "all_additional_records_in_scheduled_nornir_groups": True,
    }
    return {gpu_index, definition_index}


def build_wad_strict_texture_proof(source_raw: bytes, art_report: Path):
    _classifications.clear()
    candidate, report = _v4_build_wad(source_raw, art_report)
    base.check(set(_classifications) == {"diffuse", "emissive"},
               "strict Nornir texture classification did not cover diffuse and emissive")
    report["texture_record_classification"] = {
        label: _classifications[label] for label in ("diffuse", "emissive")
    }
    report["strict_texture_reversibility_verified"] = True
    return candidate, report


base.texture_removal_rows = strict_texture_removal_rows
base.build_wad = build_wad_strict_texture_proof


if __name__ == "__main__":
    base.main()
