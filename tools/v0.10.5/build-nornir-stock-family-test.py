#!/usr/bin/env python3
"""Build separate Nornir IDs with distinct stock map icons and no WAD edits."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "nornir_stock_id_base", HERE / "build-nornir-map-id-test.py")
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
import nornir_raven_handoff as handoff

OUT = REPO / "build/nornir-stock-family-test/candidate/game-root"
REPORT = REPO / "build/nornir-stock-family-test/report.json"
TEMPLATE = HERE / "nornir-native-map.lua"
ART = {
    "nornir_chest": "goMapIconSecondaryQuest",
    "nornir_seal": "goMapIconValkyrie_location",
    "nornir_bell": "goMapIconFight_location",
    "nornir_mechanism": "goMapIconAreaEntrance",
}
COMPASS = {
    "nornir_chest": "SIDE",
    "nornir_seal": "Valkyrie",
    "nornir_bell": "FightLocation",
    "nornir_mechanism": "AreaEntrance",
}
UNTOUCHED = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/dc/pc_le/compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "exec/boot-options.json": "8bbac2bb2a522dfacf69c676e48665686f722289a44127518ae4e8ca299a0e92",
}


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_pool(raw: bytes, counts: Counter[str]) -> tuple[bytes, dict]:
    chunk = base.stage.one_chunk(base.stage.parse_dcb_chunks(raw), 12)
    data = bytearray(raw[chunk["start"]:chunk["end"]])
    count, old_rows, end = base.stage.dcb_rows(data)
    need(count == 301 and sum(row["uid"] == base.stage.RAVEN_MAP_HASH
                              for row in old_rows) == 45,
         "Raven UI pool baseline differs")
    for resource in counts:
        uid = base.name_hash(resource)
        need(sum(row["uid"] == uid for row in old_rows) == 1,
             f"stock map resource has no unique pool row: {resource}")
    additional = b"".join(struct.pack("<QH6x", base.name_hash(resource), 1) * amount
                          for resource, amount in sorted(counts.items()))
    need(len(additional) == 88 * 16, "stock family capacity count differs")
    after = bytearray(data[:end] + additional + data[end:])
    struct.pack_into("<I", after, 8, count + 88)
    for at in (16, 32):
        struct.pack_into("<q", after, at,
                         struct.unpack_from("<q", data, at)[0] + len(additional))
    header = bytearray(raw[chunk["header"]:chunk["start"]])
    struct.pack_into("<I", header, 4, len(after))
    candidate = raw[:chunk["header"]] + header + after + raw[chunk["end"]:]
    newer = base.stage.one_chunk(base.stage.parse_dcb_chunks(candidate), 12)
    new_data = candidate[newer["start"]:newer["end"]]
    new_count, new_rows, new_end = base.stage.dcb_rows(new_data)
    need(new_count == count + 88 and
         [row["raw"] for row in new_rows[:count]] == [row["raw"] for row in old_rows],
         "existing UI pool rows changed")
    added = new_rows[count:]
    need(Counter(row["uid"] for row in added) ==
         Counter({base.name_hash(name): amount for name, amount in counts.items()})
         and all(row["capacity"] == 1 for row in added),
         "stock family pool capacity differs")
    inverse = bytearray(new_data[:end] + new_data[new_end:])
    struct.pack_into("<I", inverse, 8, count)
    for at in (16, 32):
        struct.pack_into("<q", inverse, at,
                         struct.unpack_from("<q", inverse, at)[0] - len(additional))
    inverse_header = bytearray(candidate[newer["header"]:newer["start"]])
    struct.pack_into("<I", inverse_header, 4, len(inverse))
    restored = candidate[:newer["header"]] + inverse_header + inverse + candidate[newer["end"]:]
    need(restored == raw, "stock family pool inverse is not exact")
    return candidate, {"existing_rows_preserved": count, "new_rows": 88,
                       "family_capacities": dict(sorted(counts.items())),
                       "raven_rows_unchanged": 45, "exact_inverse": True}


def build(game: Path = base.GAME) -> tuple[dict[str, bytes], dict]:
    source = {relative: (game / relative).read_bytes() for relative in base.SOURCE}
    for relative, expected in base.SOURCE.items():
        need(sha(source[relative]) == expected,
             f"installed Raven base differs: {relative}")
    for relative, expected in UNTOUCHED.items():
        need(sha((game / relative).read_bytes()) == expected,
             f"untouched Raven resource differs: {relative}")
    definitions = copy.deepcopy(base.rows())
    counts = Counter(ART[row["family"]] for row in definitions)
    need(counts == Counter({"goMapIconSecondaryQuest": 22,
                            "goMapIconValkyrie_location": 30,
                            "goMapIconFight_location": 24,
                            "goMapIconAreaEntrance": 12}),
         "stock family catalogue counts differ")
    need(set(COMPASS) == set(ART), "stock family compass mapping differs")
    for row in definitions:
        row["marker"]["compass_class"] = COMPASS[row["family"]]
    master, master_proof = base.build_map(
        base.Dcb(game / base.MASTER), definitions, False,
        lambda row: ART[row["family"]])
    coords, coords_proof = base.build_map(
        base.Dcb(game / base.COORDS), definitions, True)
    pool, pool_proof = build_pool(source[base.POOL], counts)
    raven_with_handoff = handoff.inject(source[base.MAP_LUA])
    lua, lua_proof = base.build_lua(raven_with_handoff, definitions, TEMPLATE)
    old_header = b"-- Each Nornir family has its own map resource and compass class."
    new_header = b"-- Nornir families use distinct stock map icons and matching stock compass classes."
    old_log = b"renderer=dedicated compass=dedicated"
    new_log = b"renderer=stock_family compass=stock_family"
    need(lua.count(old_header) == 1 and lua.count(old_log) == 1,
         "Nornir stock Lua template differs")
    lua = lua.replace(old_header, new_header, 1).replace(old_log, new_log, 1)
    need(lua.startswith(raven_with_handoff), "Raven handoff prefix differs")
    runic, runic_proof = base.build_chest_lua(
        base.STOCK_RUNIC, base.STOCK_RUNIC_SHA256, base.RUNIC_EVENTS)
    standard, standard_proof = base.build_chest_lua(
        base.STOCK_STANDARD, base.STOCK_STANDARD_SHA256, base.STANDARD_EVENTS)
    outputs = {base.MASTER: master, base.COORDS: coords,
               base.POOL: pool, base.MAP_LUA: lua,
               base.RUNIC_LUA: runic, base.STANDARD_LUA: standard}
    need(all((game / relative).read_bytes() == raw for relative, raw in source.items()),
         "installed Raven source changed during build")
    return outputs, {
        "schema": 1, "kind": "NORNIR_STOCK_FAMILY_MARKERS_TEST",
        "status": "OFFLINE_BUILT", "source_sha256": base.SOURCE,
        "files": {rel: {"sha256": sha(raw), "bytes": len(raw)}
                  for rel, raw in sorted(outputs.items())},
        "proof": {base.MASTER: master_proof, base.COORDS: coords_proof,
                  base.POOL: pool_proof, base.MAP_LUA: lua_proof,
                  base.RUNIC_LUA: runic_proof, base.STANDARD_LUA: standard_proof},
        "new_marker_count": 88, "child_marker_count": 66,
        "renderer": "distinct_stock_family_icons", "compass": COMPASS,
        "children_gate": "exact_locked_chest_attempt",
        "stock_art": ART, "untouched_sha256": UNTOUCHED,
        "untouched_raven_wad_sha256": UNTOUCHED["exec/wad/pc_le/r_ui.wad"],
        "untouched_compassgraph_sha256": UNTOUCHED["exec/dc/pc_le/compassgraph.dcb"],
    }


def main() -> None:
    outputs, report = build()
    for relative, raw in outputs.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_STOCK_FAMILY_OFFLINE_BUILT rows=88 children=66 raven_wad=untouched")
    print(REPORT)


if __name__ == "__main__":
    main()
