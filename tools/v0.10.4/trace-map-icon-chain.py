"""Trace stock map-icon links. Read game files; write JSON evidence only.

Keep zero-byte WAD records. GOWTool payload index skips these records.
No game writes, install, runtime calls, or clone build in this tool.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
FAMILIES = {
    "dock": (13906, 13914),
    "vendor": (13888, 13896),
    "fight_location": (13897, 13905),
    "valkyrie_location": (13915, 13923),
    "fast_travel": (13815, 13823),
    "primary_quest": (13745, 13753),
    "secondary_quest": (13754, 13762),
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def hx(value: int) -> str:
    return f"0x{value:X}"


def u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def hits(blob: bytes, needle: bytes) -> list[str]:
    result = []
    start = 0
    while (at := blob.find(needle, start)) >= 0:
        result.append(hx(at))
        start = at + 1
    return result


def load_helper(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    check(spec.loader is not None, "No module loader")
    spec.loader.exec_module(module)
    return module


class Wad:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.records = []
        self.payloads = []
        self.children = collections.defaultdict(list)
        self.definitions = collections.defaultdict(list)
        stack = []
        offset = 0
        while offset < len(raw):
            check(offset + 96 <= len(raw), f"Short header at {offset:#x}")
            kind, flags, size = struct.unpack_from("<HHI", raw, offset)
            end = offset + 96 + size
            padded_end = (end + 15) & ~15
            check(padded_end <= len(raw), f"Short payload at {offset:#x}")
            header = raw[offset:offset + 96]
            record = {
                "offset": offset, "kind": kind, "flags": flags, "size": size,
                "name": header[24:80].split(b"\0", 1)[0].decode("ascii"),
                "id": header[8:24], "header": header,
                "data": raw[offset + 96:end], "padding": raw[end:padded_end],
                "parent": stack[-1] if stack else None,
                "index": len(self.payloads) if size else None,
            }
            self.records.append(record)
            self.children[record["parent"]].append(record)
            if size:
                self.payloads.append(record)
                if kind == 1:
                    self.definitions[record["id"]].append(record)
            if kind == 2:
                stack.append(offset)
            elif kind == 3:
                check(bool(stack), f"Unmatched group end at {offset:#x}")
                stack.pop()
            offset = padded_end
        check(not stack and offset == len(raw), "Unclosed WAD group")

    def serialize(self) -> bytes:
        parts = []
        for r in self.records:
            header = (struct.pack("<HHI", r["kind"], r["flags"], len(r["data"]))
                      + r["id"] + r["header"][24:])
            parts.extend((header, r["data"], r["padding"]))
        return b"".join(parts)

    def group(self, record: dict) -> list[dict]:
        check(record["parent"] is not None, "Record has no group")
        return self.children[record["parent"]]

    def describe(self, record: dict, resolve: bool = False) -> dict:
        r = record
        result = {
            "index": r["index"], "header": hx(r["offset"]),
            "payload": hx(r["offset"] + 96), "kind": hx(r["kind"]),
            "flags": hx(r["flags"]), "bytes": r["size"], "name": r["name"],
            "id_bytes": r["id"].hex(),
            "group_start": None if r["parent"] is None else hx(r["parent"]),
        }
        if r["size"]:
            result["sha256"] = digest(r["data"])
        elif resolve and r["kind"] == 1:
            result["definition_candidates"] = [
                self.describe(d) for d in self.definitions[r["id"]]
            ]
        return result


def mesh_parts(blob: bytes) -> list[dict]:
    parts = []
    for i in range(struct.unpack_from("<H", blob, 0x38)[0]):
        definition = u32(blob, 0x4C + 4 * i)
        bone, sub_count = struct.unpack_from("<HB", blob, definition)
        for sub in range(sub_count):
            table = definition + u32(blob, definition + 60 + 4 * sub)
            for j in range(u32(blob, table)):
                field = table + 12 + 4 * j
                part = field + u32(blob, field)
                parts.append({
                    "definition": hx(definition), "bone": bone, "part": hx(part),
                    "material_slot_field": hx(part + 0x28),
                    "material_slot_candidate": u32(blob, part + 0x28),
                    "gpu_index_offset": u32(blob, part + 0x30),
                    "gpu_vertex_offset": u32(blob, part + 0x38),
                    "vertices": u32(blob, part + 0x40),
                    "indices": u32(blob, part + 0x44),
                })
    return parts


def trace_family(wad: Wad, lo: int, hi: int) -> dict:
    family = wad.payloads[lo:hi + 1]
    check(len(family) == 9, "Wrong family span")
    gpu, mg, mdl, anm, proto, *scripts, instance = family
    check([r["flags"] for r in family] ==
          [0x8198, 0x98, 0x8E, 0x72, 0x3D, 0x18, 0x18, 0x18, 0x3D],
          f"Unexpected family flags at {lo}")
    pb = proto["data"]
    node_count = struct.unpack_from("<H", pb, 0xC)[0]
    id_table = u32(pb, 0x18)
    name_table = id_table - node_count * 56
    nodes = [{
        "index": i, "descriptor_offset": hx(0x28 + 8 * i),
        "descriptor_bytes": pb[0x28 + 8 * i:0x30 + 8 * i].hex(),
        "name_offset": hx(name_table + 56 * i),
        "name": pb[name_table + 56 * i:name_table + 56 * (i + 1)].split(b"\0")[0].decode("ascii"),
        "id_offset": hx(id_table + 16 * i),
        "id_bytes": pb[id_table + 16 * i:id_table + 16 * (i + 1)].hex(),
    } for i in range(node_count)]
    check(bytes.fromhex(nodes[0]["id_bytes"]) == proto["id"], "Root ID mismatch")
    check(instance["data"][0xC:0x1C] == proto["id"], "Instance prototype mismatch")
    model_links = [r for r in wad.group(mdl) if r["kind"] == 1 and not r["size"]]
    material_links = [r for r in model_links if r["name"].startswith("MAT_")]
    material_anm_refs = [{"id_bytes": r["id"].hex(), "name": r["name"],
                          "payload_offsets": hits(anm["data"], r["id"])}
                         for r in material_links]
    name_hash = load_helper("family_hash", "decode-r-ui-map-icon-layout.py").name_hash
    animation_name_hash = struct.unpack_from("<Q", anm["data"], 0x18)[0]
    check(animation_name_hash == name_hash(anm["name"][4:]), "Animation name hash mismatch")
    return {
        "payloads": [wad.describe(r) for r in family],
        "model_links": [wad.describe(r, True) for r in model_links],
        "prototype_group": [wad.describe(r, True) for r in wad.group(proto)],
        "model_u32_fields": {hx(o): u32(mdl["data"], o) for o in [0x20, 0x28, 0x2C, 0x48]},
        "nodes": nodes,
        "script_node_fields": [{"name": r["name"], "offset": "0x48",
                                "node_index": struct.unpack_from("<H", r["data"], 0x48)[0]}
                               for r in scripts],
        "mesh_parts": mesh_parts(mg["data"]),
        "animation_material_ids": material_anm_refs,
        "animation_name_hash_at_0x18": f"{animation_name_hash:016X}",
        "instance_parent_id_at_0x54": instance["data"][0x54:0x64].hex(),
    }


def inspect_dcb(raw: bytes, exe: bytes) -> dict:
    dcb = load_helper("chain_dcb", "decode-r-ui-map-icon-layout.py")
    pe = load_helper("chain_pe", "inspect-raven-visual-resources.py")
    chunks = dcb.parse_chunks(raw)
    c = chunks[12]
    data = raw[c["start"]:c["end"]]
    check(dcb.parse_exports(raw, chunks)[0]["root"] == 0, "Wrong DCB root")
    check(u32(data, 8) == 255, "Wrong stock GOPool count")
    read, string = pe.pe_reader(exe)
    attr_table = 0x141082030
    attrs = []
    for i in [0x17C4, 0x17C5, 0x17CC]:
        field = read(attr_table + 32 * i, 32)
        name_ptr, _, offset, size, flags, _, parent, _, custom, _, _ = struct.unpack("<QQHHBBHHHHH", field)
        attrs.append({"index": hx(i), "va": hx(attr_table + 32 * i),
                      "name": string(name_ptr), "offset": hx(offset), "size": size,
                      "kind": flags >> 2, "parent_type": hx(parent), "custom_index": hx(custom)})
    pattern = re.escape(bytes.fromhex("8b94c8")) + b".{4}" + re.escape(bytes.fromhex("85d27512410f10010f29442420"))
    matches = list(re.finditer(pattern, exe, re.S))
    check(len(matches) == 1, "Array table signature not unique")
    array_table = 0x140000000 + struct.unpack_from("<i", exe, matches[0].start() + 3)[0]
    array_entry = read(array_table + 0xA5 * 24, 24)
    check(u32(array_entry, 0) == 0 and array_entry[4] == 1 and u32(array_entry, 8) == 0x10C,
          "GOPool element type mismatch")
    check([(r["name"], r["size"]) for r in attrs[:2]] == [("Name", 8), ("Cnt", 2)],
          "GOPool fields mismatch")
    uid = dcb.name_hash("goMapIconCompletionistRaven")
    check(uid == 0x584F31DC8BD6E738, "Raven hash mismatch")
    stock_rows = [data[o:o + 16] for o in range(0x90, 0x1080, 16)]
    check(all(row[10:] == bytes(6) for row in stock_rows), "Nonzero stock row padding")
    check(all(struct.unpack_from("<Q", row)[0] != uid for row in stock_rows), "Raven row exists")
    row = struct.pack("<QH6x", uid, 1)
    candidate_data = bytearray(data[:0x1080] + row + data[0x1080:])
    struct.pack_into("<I", candidate_data, 8, 256)
    struct.pack_into("<q", candidate_data, 0x10, 0x1080)
    struct.pack_into("<q", candidate_data, 0x20, 0x1090)
    header = bytearray(raw[c["header"]:c["start"]])
    struct.pack_into("<I", header, 4, len(candidate_data))
    candidate = (raw[:c["header"]] + header + candidate_data
                 + raw[c["end"]:])
    reparsed = dcb.parse_chunks(candidate)
    check(dcb.parse_exports(candidate, reparsed) == dcb.parse_exports(raw, chunks), "DCB exports changed")
    check(dcb.parse_relocations(candidate, reparsed) == [0, 0x10, 0x20], "DCB relocations changed")
    check(candidate_data[0x90:0x1080] == data[0x90:0x1080], "Stock GOPool rows changed")
    check(candidate_data[0x1090:] == data[0x1080:], "MemoryPools/Lua bytes changed")
    return {
        "bytes": len(raw), "sha256": digest(raw), "data_payload_file_offset": hx(c["start"]),
        "data_bytes": len(data), "rtti_attributes": attrs,
        "array_table_va": hx(array_table), "array_entry_va": hx(array_table + 0xA5 * 24),
        "array_entry_bytes": array_entry.hex(), "stock_row_count": 255,
        "stock_dock_row": data[0xF80:0xF90].hex(),
        "raven_single_instance_row": row.hex(),
        "in_memory_append_reparse": {
            "passed": True, "written_to_disk": False, "candidate_bytes": len(candidate),
            "sha256": digest(candidate), "gopool_count": u32(candidate_data, 8),
            "gopool_target": "0x90", "memory_pools_target": "0x1090", "memory_lua_target": "0x10B0",
            "stock_rows_unchanged": True, "stock_memory_arrays_unchanged": True,
            "exports_unchanged": True, "relocations": ["0x0", "0x10", "0x20"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--extracted", type=Path, default=Path(os.environ.get("LOCALAPPDATA", ".")) / "CompletionistMap/work/v0.10.4/r_ui-wad-files")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    game, output = args.game_root.resolve(), args.output.resolve()
    check(not output.is_relative_to(game), "Output must stay outside game tree")
    check(output.suffix.lower() == ".json", "Output must be JSON")
    paths = [game / "exec/wad/pc_le/r_ui.wad", game / "exec/dc/pc_le/wad_r_ui.dcb", game / "GoW.exe"]
    inputs = [p.read_bytes() for p in paths]
    for path, blob, expected in zip(paths, inputs, [EXPECTED_WAD, EXPECTED_DCB, EXPECTED_EXE]):
        check(digest(blob) == expected, f"Wrong source hash: {path}")
    wad = Wad(inputs[0])
    check(wad.serialize() == inputs[0], "WAD byte round-trip failed")
    files = {}
    for p in args.extracted.glob("*.bin"):
        index = int(p.name.rsplit(".", 2)[1])
        check(index not in files, "Duplicate extraction index")
        files[index] = p
    check(len(files) == len(wad.payloads) == 20407, "Wrong extraction count")
    for r in wad.payloads:
        check(files[r["index"]].read_bytes() == r["data"], f"Extract differs: {r['index']}")
    families = {name: trace_family(wad, *span) for name, span in FAMILIES.items()}
    material = wad.payloads[13699]
    material_group = wad.group(material)
    material_comparisons = {}
    for family_name in ["vendor", "fight_location", "valkyrie_location", "primary_quest"]:
        mdl = wad.payloads[FAMILIES[family_name][0] + 2]
        link = [r for r in wad.group(mdl) if r["name"].startswith("MAT_")][-1]
        definitions = wad.definitions[link["id"]]
        check(len(definitions) == 1, "Ambiguous comparison material")
        other = definitions[0]
        check(len(other["data"]) == len(material["data"]), "Material size differs")
        differences = [i for i, (a, b) in enumerate(zip(material["data"], other["data"])) if a != b]
        check(differences == list(range(0x10, 0x18)) + list(range(0x20, 0x28)), "Unexpected material differences")
        material_comparisons[family_name] = {
            "material": wad.describe(other), "only_different_offsets": [hx(i) for i in differences],
            "qword_0x10": f"{struct.unpack_from('<Q', other['data'], 0x10)[0]:016X}",
            "qword_0x20": f"{struct.unpack_from('<Q', other['data'], 0x20)[0]:016X}",
        }
    texture_rows = []
    for index, expected_hash in [(2962, 0xFCC664130951154C), (2964, 0x982BF904AB84F2CC)]:
        r, gpu = wad.payloads[index], wad.payloads[index - 1]
        expected_id = bytes.fromhex("5458455400455255") + struct.pack("<II", expected_hash >> 32, expected_hash & 0xFFFFFFFF)
        check(r["id"] == expected_id, "Texture ID word order mismatch")
        user_hash = struct.unpack_from("<Q", r["data"], 0x9C)[0]
        check(gpu["id"] == bytes(8) + struct.pack("<II", user_hash >> 32, user_hash & 0xFFFFFFFF),
              "Texture GPU ID mismatch")
        texture_rows.append({"definition": wad.describe(r), "gpu": wad.describe(gpu),
                             "file_hash": f"{expected_hash:016X}", "user_hash": f"{user_hash:016X}",
                             "user_hash_payload_offset": "0x9C"})
    root = wad.payloads[1]
    count_table = []
    base = 0
    for i in range(u32(root["data"], 0x20)):
        offset = 0x28 + i * 12
        key, start, count = struct.unpack_from("<III", root["data"], offset)
        check(start == base, "WAD type table ranges not contiguous")
        base += count
        count_table.append({"payload_offset": hx(offset), "type_key": hx(key), "base": start, "count": count})
    check(base == u32(root["data"], 0x1C) == u32(wad.payloads[0]["data"], 4), "WAD total mismatch")
    report = {
        "status": "PARTIAL", "game_files_written": False,
        "source_wad": {"bytes": len(inputs[0]), "sha256": digest(inputs[0]),
                       "physical_records": len(wad.records), "payloads": len(wad.payloads),
                       "zero_size_records": len(wad.records) - len(wad.payloads),
                       "full_byte_round_trip": True, "all_extracted_payloads_equal": True},
        "source_exe_sha256": digest(inputs[2]), "families": families,
        "dock_material_group": [wad.describe(r, True) for r in material_group],
        "dock_material_payload_fields": {hx(o): u32(material["data"], o) for o in [0xC0, 0xC4, 0xC8, 0xCC]},
        "material_payload_comparisons": material_comparisons,
        "dock_material_users": [wad.describe(r) for r in wad.records if r["kind"] == 1 and not r["size"] and r["id"] == material["id"]],
        "dock_textures": texture_rows,
        "auxiliary_0_7_0": wad.describe(wad.payloads[13729]),
        "mapicons_parent_group": [wad.describe(r, True) for r in wad.group(wad.payloads[13927])],
        "wad_type_count_table": count_table, "wad_type_count_total": base,
        "wad_heap_words": [hx(u32(wad.payloads[0]["data"], i)) for i in [0, 4]],
        "dcb": inspect_dcb(inputs[1], inputs[2]),
        "limits": ["Resource scopes and heap accounting not decoded fully.",
                   "Minimum clone set remains candidate, not runtime proof.",
                   "WAD mutation and texture packing not done."],
    }
    check(all(digest(p.read_bytes()) == digest(blob) for p, blob in zip(paths, inputs)), "Source changed during trace")
    report["source_hashes_unchanged_after_trace"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"WAD: {len(wad.records)} records; {len(wad.payloads)} payloads; byte round-trip passed.")
    print("All 20407 extracted payloads match WAD. Seven stock families checked.")
    print("GOPool RTTI and in-memory row append reparse passed. Game hashes unchanged.")
    print(f"Saved: {output}")
    print("Status PARTIAL. No clone built. No game writes.")


if __name__ == "__main__":
    main()
