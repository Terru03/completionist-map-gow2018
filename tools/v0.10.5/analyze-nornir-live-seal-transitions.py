#!/usr/bin/env python3
"""Compare loaded Nornir seal components across both save captures.

The component byte is a field-observed candidate, not yet a proven
``destructible.IsDestroyed()`` implementation or an unloaded-state query.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
STAGES_BY_SAVE = {
    "A": ("A0_before_runes", "A1_after_first_rune", "A2_after_second_rune",
          "A3_after_chest_open"),
    "B": ("B0_before_chest_open", "B1_after_chest_open"),
}
WADS_BY_SAVE = {
    "A": ("xpl200_funeral.wad", 238),
    "B": ("peak720_summitascenthub.wad", 221),
}
EXPECTED_COMPONENT_VTABLE_RVA = 0xE0DEF8
COMPONENT_POINTER_OFFSET = 0x220
CANDIDATE_BYTE_OFFSET = 0x124


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DUMPS = load_module(HERE / "analyze-nornir-two-save-dumps.py", "nornir_dump_reader")
IDENTITIES = load_module(HERE / "prove-nornir-two-save-gameobject-identities.py",
                         "nornir_identity_proof")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def read_u64(dump, address: int) -> int:
    return struct.unpack("<Q", dump.read_virtual(address, 8))[0]


def object_name(dump, obj: int) -> str:
    metadata = read_u64(dump, obj + 0x30)
    require(metadata != 0, "GameObject has no metadata")
    return dump.read_virtual(metadata + 0x20, 72).split(b"\0", 1)[0].decode(
        "ascii", errors="replace")


def registry_objects(dump, base: int, registry_id: int) -> list[tuple[int, int]]:
    _, slots = IDENTITIES.registry_slots(dump, base, registry_id)
    return [(index, obj) for index, obj in enumerate(slots) if obj]


def locate_seals(dump, base: int, registry_id: int,
                 catalogue_rows: list[dict]) -> dict[str, dict]:
    expected = {
        row["native"]["object_name"]: (
            row["catalogue_id"],
            IDENTITIES.runtime_guid(row["native"]["instance_guid"]),
        )
        for row in catalogue_rows
    }
    roots = {}
    break_objects = {}
    for slot, obj in registry_objects(dump, base, registry_id):
        name = object_name(dump, obj)
        if name in expected:
            catalogue_id, guid = expected[name]
            require(dump.read_virtual(obj + 0x40, 16) == guid,
                    f"loaded {name} identity does not match static catalogue")
            require(name not in roots, f"duplicate loaded seal root: {name}")
            roots[name] = {"catalogue_id": catalogue_id, "root_slot": slot,
                           "root_pointer": obj, "root_name": name}
        if name in ("gorunic1_break", "gorunic2_break", "gorunic3_break"):
            break_objects.setdefault(name, []).append((slot, obj))
    found = {}
    for root_name, root in roots.items():
        number = root_name[-2:].lstrip("0")
        break_name = f"gorunic{number}_break"
        children = [(slot, obj) for slot, obj in break_objects.get(break_name, [])
                    if read_u64(dump, obj + 0x28) == root["root_pointer"]]
        require(len(children) == 1, f"expected one direct {break_name} child; got {len(children)}")
        slot, obj = children[0]
        component = read_u64(dump, obj + COMPONENT_POINTER_OFFSET)
        require(component != 0, f"{break_name} component pointer is null")
        vtable = read_u64(dump, component)
        require(vtable == base + EXPECTED_COMPONENT_VTABLE_RVA,
                f"{break_name} component vtable differs")
        found[root["catalogue_id"]] = {
            **root,
            "break_name": break_name,
            "break_slot": slot,
            "break_pointer": obj,
            "component_pointer": component,
            "component_vtable_rva": f"0x{EXPECTED_COMPONENT_VTABLE_RVA:X}",
        }
    return found


def inspect(root: Path) -> dict:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    by_save = {}
    for save_label, stage_order in STAGES_BY_SAVE.items():
        wad, registry_id = WADS_BY_SAVE[save_label]
        rows = [row for row in catalogue["collectibles"]
                if row["family"] == "nornir_seal" and
                row["source"]["wad"].lower() == wad]
        require(len(rows) == 3, f"expected three seals in {wad}; found {len(rows)}")
        snapshots = []
        source_process = None
        for stage in stage_order:
            metadata = json.loads((root / f"{stage}.json").read_text(encoding="utf-8-sig"))
            require(metadata["executable_sha256"] == DUMPS.EXPECTED_EXE_SHA,
                    f"unsupported game executable: {stage}")
            if source_process is None:
                source_process = (metadata["process_id"], metadata["process_start_utc"])
            require(source_process == (metadata["process_id"], metadata["process_start_utc"]),
                    f"{save_label} stages were not captured in one process")
            dump = DUMPS.FullMemoryDump(root / f"{stage}.dmp")
            try:
                base = dump.module_base()
                seals = locate_seals(dump, base, registry_id, rows)
                values = {}
                for catalogue_id, seal in seals.items():
                    component = seal["component_pointer"]
                    value = dump.read_virtual(component + CANDIDATE_BYTE_OFFSET, 1)[0]
                    values[catalogue_id] = {"candidate_byte": value, **{
                        key: (f"0x{val:X}" if key.endswith("pointer") else val)
                        for key, val in seal.items()
                    }}
                snapshots.append({"stage": stage, "loaded_seals": values,
                                  "unlocated_seals": sorted({row["catalogue_id"] for row in rows} -
                                                            set(values))})
            finally:
                dump.close()
        by_id = {row["catalogue_id"]: [snapshot["loaded_seals"].get(row["catalogue_id"])
                                        for snapshot in snapshots] for row in rows}
        transitions = {
            catalogue_id: [None if state is None else state["candidate_byte"] for state in states]
            for catalogue_id, states in by_id.items()
        }
        by_save[save_label] = {
            "wad": wad,
            "registry_id": registry_id,
            "process_id": source_process[0],
            "stage_order": list(stage_order),
            "candidate_values_by_seal": transitions,
            "snapshots": snapshots,
        }
    return {
        "schema": 1,
        "classification": "LOADED_SEAL_FIELD_CANDIDATE_ONLY",
        "game_executable_sha256": DUMPS.EXPECTED_EXE_SHA,
        "capture_root": str(root),
        "candidate_path": "gorunicN_break GameObject +0x220 component +0x124 byte",
        "component_vtable_rva": f"0x{EXPECTED_COMPONENT_VTABLE_RVA:X}",
        "by_save": by_save,
        "semantic_status": "correlates_with_player_rune_breaks; IsDestroyed_binding_unproved",
        "unloaded_state_status": "unproved",
        "game_or_save_writes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root", type=Path)
    args = parser.parse_args()
    root = args.capture_root.resolve()
    require(root.is_dir(), f"capture directory missing: {root}")
    report = inspect(root)
    output = root / "live-seal-transitions.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NORNIR_LIVE_SEAL_CANDIDATES seals="
          f"{sum(len(group['candidate_values_by_seal']) for group in report['by_save'].values())} "
          f"report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
