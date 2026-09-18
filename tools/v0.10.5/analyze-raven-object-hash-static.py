#!/usr/bin/env python3
"""Resolve Raven serialized object-hash provenance from native WAD identity paths.

Read-only. Uses the runtime-proven inserted Veithurgard Raven object hash as
ground truth, then tests authored WAD record/group identity elements and native
GUID fields against GoW's exact raw-byte hash loop observed at RVA 0x5495E1.

No game process, save file, progression state, or game file is modified.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import raven_catalogue as rc

CATALOGUE = REPO / "catalogue/odins-ravens.json"

KNOWN = {
    # Frozen DEAD inserts only this GameObject record with ravenKilled.
    "raven_642d0d164af0a5d4076e77933c549a5d": 0x98BE1707BA2D65A9,
}


MASK64 = 0xFFFFFFFFFFFFFFFF
MULTIPLIER = 0x401
MULTIPLIER_INV = pow(MULTIPLIER, -1, 1 << 64)


def hash_update(value: int, data: bytes) -> int:
    for byte in data:
        value = ((value + byte) * MULTIPLIER) & MASK64
        value ^= value >> 6
    return value


def raw_identity_hash(data: bytes) -> int:
    """Exact encoder loop at 0x5495E1: byte-add, *0x401, xor >> 6."""
    return hash_update(0, data)


def invert_xor_shift_right(value: int, shift: int = 6) -> int:
    result = value
    distance = shift
    while distance < 64:
        result ^= value >> distance
        distance += shift
    return result & MASK64


def hash_rewind(value: int, data: bytes) -> int:
    for byte in reversed(data):
        before_xor = invert_xor_shift_right(value)
        value = ((before_xor * MULTIPLIER_INV) & MASK64)
        value = (value - byte) & MASK64
    return value


def guid_variants(text: str) -> dict[str, bytes]:
    value = uuid.UUID(text)
    return {
        "uuid_be": value.bytes,
        "uuid_le_fields": value.bytes_le,
        "uuid_reverse": value.bytes[::-1],
    }


def id_variants(raw: bytes) -> dict[str, bytes]:
    if len(raw) != 16:
        raise ValueError(f"identity element must be 16 bytes, got {len(raw)}")
    return {
        "raw": raw,
        "reverse": raw[::-1],
        "guid_le_fields": raw[3::-1] + raw[5:3:-1] + raw[7:5:-1] + raw[8:],
        "swap_u64": raw[8:] + raw[:8],
    }


def one_record(
    records: list[dict],
    record_id_hex: str,
    *,
    expected_offset: int | None = None,
    expected_name: str | None = None,
) -> tuple[int, dict]:
    target = bytes.fromhex(record_id_hex)
    hits = [(i, row) for i, row in enumerate(records) if row["id"] == target]
    if expected_offset is not None:
        hits = [(i, row) for i, row in hits if row["offset"] == expected_offset]
    if expected_name is not None:
        hits = [(i, row) for i, row in hits if row["name"] == expected_name]
    if len(hits) != 1:
        offsets = [f"0x{row['offset']:X}:{row['name']}" for _, row in hits]
        raise ValueError(
            f"record {record_id_hex} expected once after authored identity filters, "
            f"found {len(hits)} candidates={offsets}"
        )
    return hits[0]


def group_chain(records: list[dict], record: dict) -> list[dict]:
    result = []
    parent = record["parent"]
    while parent is not None:
        row = records[parent]
        result.append(row)
        parent = row["parent"]
    return result


def element_map(row: dict, records: list[dict]) -> tuple[dict[str, bytes], dict]:
    final_index, final = one_record(
        records,
        row["native"]["final_record_id"],
        expected_offset=int(row["source"]["final_offset"], 16),
        expected_name=row["native"]["object_name"],
    )
    override_index, override = one_record(
        records,
        row["native"]["override_record_id"],
        expected_offset=int(row["source"]["override_offset"], 16),
        expected_name=row["native"]["override_name"],
    )
    groups = group_chain(records, final)

    elements: dict[str, bytes] = {}

    def add_id(label: str, raw: bytes) -> None:
        for variant, value in id_variants(raw).items():
            elements[f"{label}.{variant}"] = value

    add_id("final", final["id"])
    add_id("override", override["id"])
    add_id("prototype", bytes.fromhex(row["native"]["prototype_id"]))
    add_id("parent_prototype", bytes.fromhex(row["native"]["parent_prototype_id"]))
    for index, group in enumerate(groups):
        add_id(f"group{index}", group["id"])

    for label, text in (
        ("instance_guid", row["native"]["instance_guid"]),
        ("script_guid", row["native"]["script_guid"]),
    ):
        for variant, value in guid_variants(text).items():
            elements[f"{label}.{variant}"] = value

    evidence = {
        "final_index": final_index,
        "final_offset": f"0x{final['offset']:X}",
        "final_name": final["name"],
        "override_index": override_index,
        "override_offset": f"0x{override['offset']:X}",
        "override_name": override["name"],
        "group_chain": [
            {
                "kind": group["kind"],
                "name": group["name"],
                "id": group["id"].hex(),
                "offset": f"0x{group['offset']:X}",
            }
            for group in groups
        ],
        "element_variant_count": len(elements),
    }
    return elements, evidence


def recipe_bytes(elements: dict[str, bytes], recipe: tuple[str, ...]) -> bytes:
    return b"".join(elements[name] for name in recipe)


def search_common_recipe(
    rows: list[dict],
    maps: dict[str, dict[str, bytes]],
    max_length: int,
) -> list[dict]:
    """Meet-in-the-middle search of shared authored 16-byte identity elements.

    The byte hash is reversible because 0x401 is odd and xor-right-shift is
    invertible. This keeps exhaustive searches through six elements small and
    deterministic instead of evaluating tens of millions of full prefixes.
    """
    common = sorted(set.intersection(*(set(maps[row["catalogue_id"]]) for row in rows)))
    targets = [KNOWN[row["catalogue_id"]] for row in rows]
    first_map = maps[rows[0]["catalogue_id"]]
    matches: list[dict] = []

    def validate(recipe: tuple[str, ...]) -> bool:
        if len(set(recipe)) != len(recipe):
            return False
        return all(
            raw_identity_hash(recipe_bytes(maps[row["catalogue_id"]], recipe)) == target
            for row, target in zip(rows, targets)
        )

    for length in range(1, max_length + 1):
        left_len = length // 2
        right_len = length - left_len
        if left_len == 0:
            for recipe in itertools.permutations(common, right_len):
                if validate(recipe):
                    matches.append({"recipe": list(recipe), "elements": length, "bytes": length * 16})
            if matches:
                return matches
            continue

        forward: dict[int, list[tuple[str, ...]]] = {}
        for left in itertools.permutations(common, left_len):
            value = 0
            for name in left:
                value = hash_update(value, first_map[name])
            forward.setdefault(value, []).append(left)

        for right in itertools.permutations(common, right_len):
            value = targets[0]
            for name in reversed(right):
                value = hash_rewind(value, first_map[name])
            for left in forward.get(value, ()):
                recipe = left + right
                if validate(recipe):
                    matches.append({"recipe": list(recipe), "elements": length, "bytes": length * 16})
        if matches:
            return matches
    return matches


def structural_candidates(row: dict, records: list[dict]) -> list[dict]:
    _, final = one_record(
        records,
        row["native"]["final_record_id"],
        expected_offset=int(row["source"]["final_offset"], 16),
        expected_name=row["native"]["object_name"],
    )
    _, override = one_record(
        records,
        row["native"]["override_record_id"],
        expected_offset=int(row["source"]["override_offset"], 16),
        expected_name=row["native"]["override_name"],
    )
    groups = group_chain(records, final)
    candidates: list[tuple[str, list[bytes]]] = [
        ("final", [final["id"]]),
        ("override", [override["id"]]),
        ("final_then_groups", [final["id"], *[g["id"] for g in groups]]),
        ("groups_then_final", [*[g["id"] for g in reversed(groups)], final["id"]]),
        ("override_then_groups", [override["id"], *[g["id"] for g in groups]]),
        ("groups_then_override", [*[g["id"] for g in reversed(groups)], override["id"]]),
        ("override_final_groups", [override["id"], final["id"], *[g["id"] for g in groups]]),
    ]
    return [
        {
            "name": name,
            "element_count": len(parts),
            "bytes": b"".join(parts).hex(),
            "hash_hex": f"0x{raw_identity_hash(b''.join(parts)):016X}",
        }
        for name, parts in candidates
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-recipe-length", type=int, default=6)
    args = parser.parse_args()

    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    rows = [row for row in catalogue["ravens"] if row["catalogue_id"] in KNOWN]
    if len(rows) != 3:
        raise ValueError(f"expected three known Raven rows, found {len(rows)}")
    wads = {row["source"]["wad"] for row in rows}
    if len(wads) != 1:
        raise ValueError(f"known Ravens no longer share one WAD: {sorted(wads)}")
    wad_name = next(iter(wads))
    wad_path = args.game_root / "exec" / "wad" / "pc_le" / wad_name
    raw = wad_path.read_bytes()
    expected_sha = rows[0]["source"]["wad_sha256"]
    if rc.digest(raw) != expected_sha:
        raise ValueError(
            f"WAD SHA differs for {wad_name}: expected {expected_sha}, got {rc.digest(raw)}"
        )
    records = rc.parse_wad(raw)

    maps = {}
    row_evidence = {}
    for row in rows:
        elements, evidence = element_map(row, records)
        maps[row["catalogue_id"]] = elements
        target = KNOWN[row["catalogue_id"]]
        individual = [
            {
                "element": name,
                "bytes": value.hex(),
                "hash_hex": f"0x{raw_identity_hash(value):016X}",
                "matches": raw_identity_hash(value) == target,
            }
            for name, value in sorted(elements.items())
        ]
        row_evidence[row["catalogue_id"]] = {
            "target_object_hash_hex": f"0x{target:016X}",
            "native": evidence,
            "individual_elements": individual,
            "structural_candidates": structural_candidates(row, records),
        }

    recipes = search_common_recipe(rows, maps, max(1, args.max_recipe_length))
    result = {
        "schema": 1,
        "result": "STATIC_RAVEN_OBJECT_HASH_RECIPE_FOUND" if recipes else "STATIC_RAVEN_OBJECT_HASH_RECIPE_NOT_FOUND",
        "wad": wad_name,
        "wad_sha256": rc.digest(raw),
        "known_records": row_evidence,
        "common_recipe_matches": recipes,
        "max_recipe_length": args.max_recipe_length,
        "hash_algorithm": "for each byte: value=((value+byte)*0x401)&u64; value^=value>>6",
        "encoder_evidence": {
            "registry_name_hash_loop": "GoW.exe 0x5494F0-0x549525",
            "object_identity_vector_call": "GoW.exe 0x5495C1-0x5495C9",
            "object_identity_count": "dword [rsp+0x1C0], each element 16 bytes",
            "object_identity_hash_loop": "GoW.exe 0x5495E1-0x549600",
        },
        "read_only": True,
        "game_launched": False,
        "save_or_progression_written": False,
    }

    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    print(result["result"])
    print(f"common_recipe_matches={len(recipes)}")
    for match in recipes[:20]:
        print("MATCH " + " -> ".join(match["recipe"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
