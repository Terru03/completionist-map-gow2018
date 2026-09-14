"""Read-only structural probe for native Odin's Raven RegionSummary quest records.

This intentionally does not inspect the active save and does not launch the game.
It asks a narrower question than the save-forensics tools: do the native Raven
RegionSummary parent quest records expose child quest/objective references that can
identify WHICH Ravens contribute to an aggregate N/M regional counter?

The probe reuses the strict shipped-PC DCB reader from raven_catalogue.py, inventories
all quest records whose names contain 'raven', walks direct quest-record references,
and tests relocation-backed pointer arrays near each RegionSummary_*_Raven_Parent.
All findings are evidence only; array shape or proximity is never treated as proof.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import raven_catalogue as rc

QUEST_TYPE = 0x159
PARENT_SCAN_BYTES = 0x180
MAX_ARRAY_COUNT = 128
MAX_TEXT = 120


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ascii_at(blob: bytes, offset: int) -> str | None:
    if offset < 0 or offset >= len(blob):
        return None
    end = offset
    while end < len(blob) and end - offset < MAX_TEXT:
        b = blob[end]
        if b == 0:
            break
        if b < 0x20 or b > 0x7E:
            return None
        end += 1
    if end == offset or end >= len(blob) or blob[end] != 0:
        return None
    return blob[offset:end].decode("ascii", "replace")


def quest_records(dcb: rc.Dcb) -> list[dict]:
    rows: list[dict] = []
    root = dcb.root("QUESTS_PERM_DATA", QUEST_TYPE)
    for item in dcb.array(root, 8):
        record = dcb.pointer(item)
        name = dcb.string(record)
        rows.append({"record": record, "name": name})
    rows.sort(key=lambda row: row["record"])
    return rows


def relocation_fields_in(relocations: list[int], start: int, end: int) -> list[int]:
    lo = bisect_left(relocations, start)
    hi = bisect_left(relocations, end)
    return relocations[lo:hi]


def owner_for_field(records: list[dict], starts: list[int], field: int) -> dict | None:
    # Quest records are variable-sized. This is only a bounded ownership label used
    # for diagnostics; direct pointer equality remains the actual edge evidence.
    index = bisect_left(starts, field + 1) - 1
    if index < 0:
        return None
    row = records[index]
    delta = field - row["record"]
    if 0 <= delta < PARENT_SCAN_BYTES:
        return {"name": row["name"], "record": row["record"], "relative_field": delta}
    return None


def pointer_array_candidate(
    dcb: rc.Dcb,
    field: int,
    target: int,
    by_record: dict[int, str],
) -> dict | None:
    if field + 12 > len(dcb.blob):
        return None
    count = struct.unpack_from("<I", dcb.blob, field + 8)[0]
    if count <= 0 or count > MAX_ARRAY_COUNT or target + count * 8 > len(dcb.blob):
        return None

    elements = []
    relocation_elements = 0
    known_quest_elements = 0
    for index in range(count):
        elem_field = target + index * 8
        if elem_field not in dcb.relocations:
            continue
        relocation_elements += 1
        try:
            elem_target = dcb.pointer(elem_field)
        except Exception:
            continue
        quest_name = by_record.get(elem_target)
        if quest_name is not None:
            known_quest_elements += 1
        if len(elements) < 64:
            elements.append({
                "index": index,
                "element_field": elem_field,
                "target": elem_target,
                "quest_name": quest_name,
                "ascii": None if quest_name else ascii_at(dcb.blob, elem_target),
            })

    # Avoid flooding the report with ordinary pointers whose following bytes happen
    # to form a small integer. Keep only arrays with relocation-backed elements.
    if relocation_elements == 0:
        return None
    return {
        "field": field,
        "target": target,
        "count": count,
        "relocation_elements": relocation_elements,
        "known_quest_elements": known_quest_elements,
        "all_elements_are_relocations": relocation_elements == count,
        "elements": elements,
    }


def public_offset(dcb: rc.Dcb, offset: int) -> str:
    return f"0x{dcb.file_base + offset:X}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.expanduser().resolve()
    dcb_root = game_root / "exec" / "dc" / "pc_le"
    quest_path = dcb_root / "quests.dcb"
    map_path = dcb_root / "mapmaster.dcb"
    if not quest_path.is_file() or not map_path.is_file():
        raise RuntimeError(f"Unsupported game root or missing native DCBs: {game_root}")

    before = {str(path): sha256_file(path) for path in (quest_path, map_path)}
    quests = rc.Dcb(quest_path)
    records = quest_records(quests)
    by_record = {row["record"]: row["name"] for row in records}
    starts = [row["record"] for row in records]
    relocs = sorted(quests.relocations)

    raven_named = [
        {"name": row["name"], "record_offset": public_offset(quests, row["record"])}
        for row in records if "raven" in row["name"].lower()
    ]
    parents = [row for row in records if rc.RAVEN_PARENT_RE.fullmatch(row["name"].encode("ascii", "ignore"))]

    # Build exact direct quest-record edges: a relocation field inside a bounded
    # quest-record window points exactly at the root offset of another known quest.
    direct_edges: list[dict] = []
    for source in records:
        for field in relocation_fields_in(relocs, source["record"], min(len(quests.blob), source["record"] + PARENT_SCAN_BYTES)):
            try:
                target = quests.pointer(field)
            except Exception:
                continue
            target_name = by_record.get(target)
            if target_name is None:
                continue
            direct_edges.append({
                "source_name": source["name"],
                "source_record": source["record"],
                "relative_field": field - source["record"],
                "target_name": target_name,
                "target_record": target,
            })

    parent_reports = []
    strong_array_child_candidates = 0
    for parent in parents:
        record = parent["record"]
        target_count = quests.unpack("<I", record + 0x30)[0]
        fields = relocation_fields_in(relocs, record, min(len(quests.blob), record + PARENT_SCAN_BYTES))
        pointer_fields = []
        array_candidates = []
        for field in fields:
            try:
                target = quests.pointer(field)
            except Exception as exc:
                pointer_fields.append({
                    "relative_field": field - record,
                    "error": str(exc),
                })
                continue
            quest_name = by_record.get(target)
            text = None if quest_name else ascii_at(quests.blob, target)
            pointer_fields.append({
                "relative_field": field - record,
                "target_offset": public_offset(quests, target),
                "quest_name": quest_name,
                "ascii": text,
            })
            candidate = pointer_array_candidate(quests, field, target, by_record)
            if candidate is not None:
                candidate["relative_field"] = field - record
                candidate["field_offset"] = public_offset(quests, field)
                candidate["target_offset"] = public_offset(quests, target)
                for element in candidate["elements"]:
                    element["element_field"] = public_offset(quests, element["element_field"])
                    element["target"] = public_offset(quests, element["target"])
                array_candidates.append(candidate)
                if candidate["known_quest_elements"] > 0:
                    strong_array_child_candidates += 1

        outgoing = [edge for edge in direct_edges if edge["source_record"] == record]
        incoming = [edge for edge in direct_edges if edge["target_record"] == record]
        parent_reports.append({
            "name": parent["name"],
            "record_offset": public_offset(quests, record),
            "native_target_count": target_count,
            "direct_outgoing_quest_refs": [
                {
                    "relative_field": edge["relative_field"],
                    "target_name": edge["target_name"],
                    "target_record_offset": public_offset(quests, edge["target_record"]),
                }
                for edge in outgoing
            ],
            "direct_incoming_quest_refs": [
                {
                    "source_name": edge["source_name"],
                    "relative_field": edge["relative_field"],
                    "source_record_offset": public_offset(quests, edge["source_record"]),
                }
                for edge in incoming
            ],
            "pointer_fields": pointer_fields,
            "pointer_array_candidates": array_candidates,
        })

    # Reverse references from anywhere in the DCB to exact parent roots. This can
    # expose wrappers/containers that are not themselves quest records.
    reverse_parent_refs = []
    parent_by_record = {row["record"]: row["name"] for row in parents}
    for field in relocs:
        try:
            target = quests.pointer(field)
        except Exception:
            continue
        parent_name = parent_by_record.get(target)
        if parent_name is None:
            continue
        reverse_parent_refs.append({
            "parent_name": parent_name,
            "field_offset": public_offset(quests, field),
            "source_owner_hint": owner_for_field(records, starts, field),
        })

    after = {str(path): sha256_file(path) for path in (quest_path, map_path)}
    if before != after:
        raise RuntimeError("Native DCB hash changed during read-only RegionSummary probe")

    report = {
        "schema": 1,
        "scan_kind": "read_only_raven_regionsummary_structure",
        "game_root": str(game_root),
        "quests_dcb": {
            "path": str(quest_path),
            "sha256": before[str(quest_path)],
            "quest_records": len(records),
            "relocations": len(quests.relocations),
        },
        "mapmaster_sha256": before[str(map_path)],
        "raven_named_quest_records": raven_named,
        "raven_parent_count": len(parent_reports),
        "raven_parents": parent_reports,
        "reverse_parent_refs": reverse_parent_refs,
        "evidence_summary": {
            "raven_named_quest_records": len(raven_named),
            "raven_parent_records": len(parent_reports),
            "direct_parent_to_known_quest_refs": sum(len(row["direct_outgoing_quest_refs"]) for row in parent_reports),
            "pointer_array_candidates_with_known_quest_elements": strong_array_child_candidates,
            "child_objective_bridge_proven": False,
            "interpretation": "Evidence only. Exact pointer edges are real; child semantics require independent proof.",
        },
        "safety": {
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "source_hashes_unchanged": True,
        },
        "status": "EVIDENCE_ONLY",
    }

    lines = [
        "Completionist Map - Raven RegionSummary native structure probe",
        f"quests={quest_path}",
        f"sha256={report['quests_dcb']['sha256']}",
        f"quest_records={len(records)} relocations={len(quests.relocations)}",
        f"raven_named_records={len(raven_named)} raven_parents={len(parent_reports)}",
        f"direct_parent_to_known_quest_refs={report['evidence_summary']['direct_parent_to_known_quest_refs']}",
        f"array_candidates_with_known_quest_elements={strong_array_child_candidates}",
        "child_objective_bridge_proven=false",
        "status=EVIDENCE_ONLY",
        "",
        "=== RAVEN-NAMED QUEST RECORDS ===",
    ]
    for row in raven_named:
        lines.append(f"{row['record_offset']} {row['name']}")
    lines.append("")
    lines.append("=== RAVEN PARENTS ===")
    for row in parent_reports:
        lines.append(
            f"{row['name']} target={row['native_target_count']} record={row['record_offset']} "
            f"outgoingQuestRefs={len(row['direct_outgoing_quest_refs'])} "
            f"incomingQuestRefs={len(row['direct_incoming_quest_refs'])} "
            f"arrayCandidates={len(row['pointer_array_candidates'])}"
        )
        for edge in row["direct_outgoing_quest_refs"]:
            lines.append(
                f"  OUT +0x{edge['relative_field']:X} -> {edge['target_name']} {edge['target_record_offset']}"
            )
        for candidate in row["pointer_array_candidates"]:
            if candidate["known_quest_elements"] == 0:
                continue
            lines.append(
                f"  ARRAY +0x{candidate['relative_field']:X} count={candidate['count']} "
                f"relocElems={candidate['relocation_elements']} knownQuestElems={candidate['known_quest_elements']}"
            )
            for element in candidate["elements"]:
                if element["quest_name"]:
                    lines.append(f"    [{element['index']}] -> {element['quest_name']} {element['target']}")
    lines.extend([
        "",
        "=== SAFETY ===",
        "active_save_opened=false",
        "game_written=false",
        "save_or_progression_written=false",
        "game_launched=false",
        "source_hashes_unchanged=true",
    ])

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_text.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_REGIONSUMMARY_STRUCTURE_COMPLETED "
        f"parents={len(parent_reports)} raven_named={len(raven_named)} "
        f"direct_refs={report['evidence_summary']['direct_parent_to_known_quest_refs']} "
        f"array_child_candidates={strong_array_child_candidates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
