"""Isolated map artwork over the exact installed completion build.

Pair each resident GPU payload with its texture definition. GoW loads resident
pixels from the last GPU record, independent of texture IDs. The optional
render profile also isolates MG/PS resources and preserves donor material +0x20.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build/collectible-family-art"
WAD = "exec/wad/pc_le/r_ui.wad"
MASTER = "exec/dc/pc_le/mapmaster.dcb"
POOL = "exec/dc/pc_le/wad_r_ui.dcb"
BOOT = "exec/boot-options.json"
PERM = "exec/dc/pc_le/wad_r_perm.dcb"
NAMESPACE = "completionist-map-family-art-v1"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


logical = load("family_art_logical", HERE.parent / "v0.10.4/build-raven-ui-logical-clone.py")
clone = load("family_art_clone", HERE.parent / "v0.10.4/build-nornir-map-hud-offline.py")
locations = load("family_art_locations", HERE / "build-collectible-locations.py")
packed = load("family_art_packed_perm", HERE.parent / "v0.10.4/build-packed-raven-compass-class.py")
stage = locations.base.stage
safe_io = load('family_art_safe_files', HERE / 'install-nornir-map-id-test.py')
RAVEN = clone.RAVEN
MAP_ROLES = ("material", "map_model", "map_proto", "map_root")
HUD_ROLES = ("hud_model", "hud_proto", "hud_root")
ALL_ROLES = MAP_ROLES + HUD_ROLES
RENDER_DONORS = {"model_group": "MG_mapicondock_0",
                 "pixel_shader": "0c599dc8dc7e2170_ps_10000207"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(family, role, size=16):
    return hashlib.sha256(f"{NAMESPACE}:{family}:{role}".encode("ascii")).digest()[:size]


def spec_for(family, *, include_hud=True):
    title = "".join(word.capitalize() for word in family.split("_"))
    roles = ALL_ROLES if include_hud else MAP_ROLES
    names = {"material": f"MAT_cmf_{family}", "map_model": f"MDL_cmf_{family}",
             "map_proto": "goProtoMapIconCompletionist" + title,
             "map_root": "gomapiconcompletionist" + title.lower()}
    if include_hud:
        names.update({
            "hud_model": f"MDL_cmf_{family}_hud",
            "hud_proto": "goProtoCompletionist" + title + "HUD",
            "hud_root": "gocompletionist" + title.lower() + "hud",
        })
    res = {"family": family, "resource": "goMapIconCompletionist" + title,
           "names": names, "ids": {role: identity(family, role) for role in roles},
           "q10": int.from_bytes(identity(family, "material-q10", 8), "little"),
           "q20": int.from_bytes(identity(family, "material-q20", 8), "little")}
    if include_hud:
        res["hud_resource"] = "goCompletionist" + title + "HUD"
        res["compass_class"] = "Completionist" + title
    return res


def all_definitions():
    rows, _, _ = locations.definitions()
    return locations.base.rows() + rows


def build_wad(source, families, *, isolate_render_resources=False):
    """families: (spec, {role: {name, file_hash, user_hash, resident}})."""
    records = logical.parse_wad(source)
    need(logical.serialize_wad(records) == source, "source WAD roundtrip differs")
    originals = [logical.record_bytes(r) for r in records]
    old_heap, old_root = [bytes(r["data"]) for r in logical.payload_records(records)[:2]]
    jobs = defaultdict(list)
    reserved_ids = {r["id"] for r in records}
    reserved_keys = {struct.unpack_from("<Q", r["data"], off)[0]
                     for r in records if r["kind"] == 1 and r["name"].startswith("MAT_")
                     and len(r["data"]) >= 0x28 for off in (0x10, 0x20)}
    reserved_names = {r["name"].lower() for r in records}
    _, raven_material = clone.unique_payload(records, RAVEN["material"])
    donor_q20 = struct.unpack_from("<Q", raven_material["data"], 0x20)[0]
    proof = []
    for spec, textures in families:
        names, ids = spec["names"], spec["ids"]
        need(set(textures) == {"diffuse", "emissive"}, "texture roles differ")
        for role in MAP_ROLES:
            need(ids[role] not in reserved_ids, f"resource collision: {names[role]}")
            reserved_ids.add(ids[role])
        for field in (("q10",) if isolate_render_resources else ("q10", "q20")):
            need(spec[field] not in reserved_keys, "material identity collision")
            reserved_keys.add(spec[field])
        chains = {}
        infos = {}
        for role in MAP_ROLES:
            group, target, info = clone.clone_group(logical, records, RAVEN[role], names[role], ids[role])
            chains[role], infos[role] = group, info
            # Rename references and embedded prototype GUIDs only inside the new chain.
            for r in group:
                for old_role in MAP_ROLES:
                    _, donor = clone.unique_payload(records, RAVEN[old_role])
                    if r["id"] == donor["id"]:
                        r["id"] = ids[old_role]
                        clone.set_name(r, names[old_role])
                    if donor["id"] in r["data"]:
                        clone.replace_id(r["data"], donor["id"], ids[old_role])
            if role == "material":
                struct.pack_into("<Q", target["data"], 0x10, spec["q10"])
                struct.pack_into("<Q", target["data"], 0x20,
                                 donor_q20 if isolate_render_resources else spec["q20"])
            elif role == "map_root":
                target["data"][0x1C:0x54] = names[role].encode("ascii").ljust(56, b"\0")
        render_proof = {}
        if isolate_render_resources:
            # Stock map icons have their own MG and PS resource objects, even
            # when PS bytecode is identical. Keep the binary programs/geometry;
            # give each new family private resource wrappers and dependencies.
            for role, owner, type_key, flags, name in (
                ("model_group", "map_model", 0x1000C, 0x98, f"MG_cmf_{spec['family']}_0"),
                ("pixel_shader", "material", 0x1000A, 0x0B, f"cmf_{spec['family']}_ps_10000207"),
            ):
                index, donor = clone.unique_payload(records, RENDER_DONORS[role])
                need(donor["parent"] is None and donor["flags"] == flags and
                     struct.unpack_from("<I", donor["data"])[0] == type_key,
                     "render donor grammar differs: " + role)
                rid = identity(spec["family"], role)
                need(rid not in reserved_ids and name.lower() not in reserved_names,
                     "render resource collision: " + role)
                reserved_ids.add(rid)
                reserved_names.add(name.lower())
                new = clone.clone_texture(donor, name, rid, bytes(donor["data"]))
                clone.retarget_link(chains[owner], donor["name"], donor["id"], name, rid)
                jobs[index].append(new)
                render_proof[role] = {"name": name, "id": rid.hex(), "type_key": type_key,
                                      "payload_sha256": sha(donor["data"])}
        for role, texture in textures.items():
            name = texture["name"]
            need(len(name.encode("ascii")) < 56, "texture name too long")
            did = clone.texture_def_id(texture["file_hash"])
            gid = clone.texture_gpu_id(texture["user_hash"])
            need(did not in reserved_ids and gid not in reserved_ids, "texture identity collision")
            reserved_ids.update((did, gid))
            _, gpu = clone.unique_texture(records, RAVEN[role], gpu=True)
            di, definition = clone.unique_texture(records, RAVEN[role], gpu=False)
            need(len(texture["resident"]) == len(gpu["data"]), "resident size differs")
            new_gpu = clone.clone_texture(gpu, name, gid, texture["resident"])
            new_def = clone.clone_texture(definition, name, did, bytes(definition["data"]))
            # The old builders changed only WAD labels, retaining Dock's internal name.
            new_def["data"][0x0C:0x44] = name.encode("ascii").ljust(56, b"\0")
            if "dimensions" in texture:
                struct.pack_into("<HH", new_def["data"], 0x48, *texture["dimensions"])
            struct.pack_into("<Q", new_def["data"], 0x9C, texture["user_hash"])
            clone.retarget_link(chains["material"], RAVEN[role], definition["id"], name, did)
            # Loader uses last GPU payload. Keep each pair after donor pair.
            jobs[di].extend((new_gpu, new_def))
        for role in MAP_ROLES:
            jobs[infos[role]["end"]].extend(chains[role])
        if "hud_model" in names:
            for role in HUD_ROLES:
                need(ids[role] not in reserved_ids, f"resource collision: {names[role]}")
                reserved_ids.add(ids[role])
            hud_m_rows, _, hud_m_info = clone.clone_group(logical, records, RAVEN["hud_model"], names["hud_model"], ids["hud_model"])
            clone.retarget_link(hud_m_rows, RAVEN["material"], raven_material["id"], names["material"], ids["material"])
            hud_p_rows, hud_p_target, hud_p_info = clone.clone_group(logical, records, RAVEN["hud_proto"], names["hud_proto"], ids["hud_proto"])
            clone.replace_id(hud_p_target["data"], hud_p_info["source"]["id"], ids["hud_proto"])
            clone.retarget_link(hud_p_rows, RAVEN["hud_model"], hud_m_info["source"]["id"], names["hud_model"], ids["hud_model"])
            hud_r_rows, hud_r_target, hud_r_info = clone.clone_group(logical, records, RAVEN["hud_root"], names["hud_root"], ids["hud_root"])
            hud_r_target["data"][0x0C:0x1C] = ids["hud_proto"]
            hud_r_target["data"][0x1C:0x54] = names["hud_root"].encode("ascii").ljust(56, b"\0")

            jobs[hud_m_info["end"]].extend(hud_m_rows)
            jobs[hud_p_info["end"]].extend(hud_p_rows)
            jobs[hud_r_info["end"]].extend(hud_r_rows)

        root_id = infos["map_root"]["source"]["id"]
        links = [(i, r) for i, r in enumerate(records) if r["kind"] == 1 and
                 not r["data"] and r["id"] == root_id and r["name"] == RAVEN["map_root"]]
        need(len(links) == 1, "map registration link differs")
        i, link = links[0]
        new_link = copy.deepcopy(link)
        clone.set_name(new_link, names["map_root"])
        new_link["id"] = ids["map_root"]
        jobs[i].append(new_link)
        proof.append({"family": spec["family"], "resource": spec["resource"],
                      "hud_resource": spec.get("hud_resource"),
                      "compass_class": spec.get("compass_class"),
                      "material_q10": f"{spec['q10']:016X}",
                      "material_q20": f"{donor_q20 if isolate_render_resources else spec['q20']:016X}",
                      **({"render_resources": render_proof} if isolate_render_resources else {}),
                      "textures": {role: {k: v for k, v in tex.items() if k != "resident"}
                                   for role, tex in textures.items()}})
    # Base map chains have six typed records and two untyped resident GPU records.
    # Private model groups and pixel shaders each add their actual payload type.
    heap, root = logical.payload_records(records)[:2]
    has_hud = any("hud_model" in spec["names"] for spec, _ in families)
    increments = {0xA: 1, 0x10001: 2 if has_hud else 1, 0x20001: 2 if has_hud else 1,
                  0x2000C: 1, 0x10015: 2}
    if has_hud:
        increments[0x10005] = 1
    if isolate_render_resources:
        increments.update({0x1000C: 1, 0x1000A: 1})
    typed_per_family = sum(increments.values())
    total = 0
    for row in logical.read_type_table(old_root):
        count = row["count"] + len(families) * increments.get(row["key"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], total, count)
        total += count
    need(total == struct.unpack_from("<I", old_heap, 4)[0] + len(families) * typed_per_family,
         "typed resource accounting differs")
    struct.pack_into("<I", heap["data"], 4, total)
    struct.pack_into("<I", root["data"], 0x1C, total)
    inserted = set()
    out = []
    for i, record in enumerate(records):
        out.append(record)
        for new in jobs[i]:
            inserted.add(len(out))
            out.append(new)
    candidate = logical.serialize_wad(out)
    reread = logical.parse_wad(candidate)
    need(logical.serialize_wad(reread) == candidate, "candidate WAD roundtrip differs")
    untyped_per_family = 3 if has_hud else 2
    need(len(logical.payload_records(reread)) - len(logical.payload_records(records)) ==
         (typed_per_family + untyped_per_family) * len(families),
         "physical resource accounting differs")
    inverse = [r for i, r in enumerate(reread) if i not in inserted]
    for r, data in zip(logical.payload_records(inverse)[:2], (old_heap, old_root)):
        r["data"] = bytearray(data)
    need([logical.record_bytes(r) for r in inverse] == originals,
         "existing Raven/stock record changed")
    need(logical.serialize_wad(inverse) == source, "WAD exact inverse failed")
    return candidate, {"exact_inverse": True, "families": proof,
                       "added_typed": typed_per_family * len(families),
                       "added_payloads": (typed_per_family + 2) * len(families),
                       "runtime_coexistence_verified": False}


def build_master(raw, resources):
    source = locations.base.parsed(raw, "mapmaster.dcb")
    before = stage.marker_snapshot(source)
    definitions = {r["marker"]["uid"]: r for r in all_definitions() if r["family"] in resources}
    need(definitions and set(definitions) <= {r["uid"] for r in before}, "marker definitions absent")
    blob = bytearray(source.blob)
    offsets = {}
    for family, resource in sorted(resources.items()):
        offsets[family] = len(blob)
        blob.extend(resource.encode("ascii") + b"\0")
    changed = []
    for row in before:
        definition = definitions.get(row["uid"])
        if definition:
            at = row["offset"] + 8
            need(at in source.relocations, "marker resource pointer not relocated")
            struct.pack_into("<q", blob, at, offsets[definition["family"]] - at)
            changed.append(at)
    candidate = stage.rebuild_dcb_bytes(source, blob, set(source.relocations))
    after_dcb = locations.base.parsed(candidate, "mapmaster.dcb")
    after = stage.marker_snapshot(after_dcb)
    expected = [{**r, "icon": resources[definitions[r["uid"]]["family"]]} if r["uid"] in definitions else r
                for r in before]
    need(after == expected, "map semantics changed outside icon bindings")
    inverse = bytearray(after_dcb.blob[:len(source.blob)])
    for at in changed:
        inverse[at:at + 8] = source.blob[at:at + 8]
    need(stage.rebuild_dcb_bytes(source, inverse, set(source.relocations)) == raw, "map inverse failed")
    return candidate, {"exact_inverse": True, "changed_bindings": len(changed),
                       "families": dict(Counter(r["family"] for r in definitions.values()))}


def inworld_name_for(compass_class: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', compass_class)
    snake = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).upper()
    return "COMPASS_INWORLD_" + snake


def build_pool(raw, resources, hud_resources=None):
    # Reassign the extra stock quest reserve; do not increase UI physics objects.
    chunk = stage.one_chunk(stage.parse_dcb_chunks(raw), 12)
    count, rows, _ = stage.dcb_rows(raw[chunk["start"]:chunk["end"]])
    spare = [i for i, r in enumerate(rows) if i >= 389 and r["uid"] == locations.base.STOCK_HASH]
    counts = Counter(r["family"] for r in all_definitions() if r["family"] in resources)
    hud_count = len(hud_resources) if hud_resources else 0
    need(len(spare) >= sum(counts.values()) + hud_count + 128, "insufficient stock quest reserve")
    result = bytearray(raw)
    offsets = []
    start = 0
    for family in sorted(resources):
        uid = locations.base.name_hash(resources[family])
        need(not any(r["uid"] == uid for r in rows), "custom pool already present")
        for i in spare[start:start + counts[family]]:
            at = chunk["start"] + 0x90 + i * 16
            struct.pack_into("<Q", result, at, uid)
            offsets.append(at)
        start += counts[family]
    hud_indices = set()
    if hud_resources:
        for family in sorted(hud_resources):
            hud_name = hud_resources[family]
            uid = locations.base.name_hash(hud_name)
            need(not any(r["uid"] == uid for r in rows), f"custom HUD pool already present: {hud_name}")
            i = spare[start]
            hud_indices.add(i)
            at = chunk["start"] + 0x90 + i * 16
            struct.pack_into("<QH", result, at, uid, 2)
            offsets.append(at)
            start += 1
    candidate = bytes(result)
    new_count, new_rows, _ = stage.dcb_rows(candidate[chunk["start"]:chunk["end"]])
    need(new_count == count, "pool count changed")
    need([r["raw"] for r in rows[:389]] == [r["raw"] for r in new_rows[:389]], "original pool changed")
    for i, (orig_r, new_r) in enumerate(zip(rows, new_rows)):
        if i in hud_indices:
            need(new_r["capacity"] == 2, f"hud slot {i} capacity not 2")
        else:
            need(new_r["capacity"] == orig_r["capacity"], f"slot {i} capacity changed")
    for at in offsets:
        result[at:at + 16] = raw[at:at + 16]
    need(bytes(result) == raw, "pool exact inverse failed")
    return candidate, {"exact_inverse": True, "total_rows": count, "reassigned": start,
                       "family_slots": dict(counts), "hud_slots": hud_count, "added_physics_objects": 0}


def build_perm(raw, specs):
    chunks = packed.parse_chunks(raw)
    data = bytearray(packed.one(chunks, 12)["payload"])
    header8, exports, tail = packed.parse_exports(packed.one(chunks, 13)["payload"])
    relocs = packed.parse_relocations(packed.one(chunks, 15)["payload"], bytes(data))

    by_name = {e["name"]: e for e in exports}
    globals_row = by_name["COMPASS_GLOBALS"]
    raven_row = by_name["CompletionistRaven"]
    side_iw = by_name["COMPASS_INWORLD_SIDE"]

    # 1. In-world insertion position (at end of type-0x129 block)
    iw_exports = sorted([e for e in exports if int(e["type_id"]) == 0x129 and e["name"].startswith("COMPASS_INWORLD_")], key=lambda e: int(e["root"]))
    INWORLD_SIZE = 0x98
    CLASS_SIZE = 0x20
    insert_iw = int(iw_exports[-1]["root"]) + INWORLD_SIZE

    # 2. Prepare new in-world carrier records
    side_iw_rec = bytearray(data[side_iw["root"]:side_iw["root"] + INWORLD_SIZE])
    sorted_specs = sorted(specs, key=lambda s: s["compass_class"])

    new_iw_bytes = bytearray()
    new_iw_exports = []

    for idx, s in enumerate(sorted_specs):
        hud_hash = packed.name_hash(s["hud_resource"])
        iw_name = inworld_name_for(s["compass_class"])
        iw_uid = packed.name_hash(iw_name)

        rec = bytearray(side_iw_rec)
        struct.pack_into("<Q", rec, 0, hud_hash)
        rec_field = 0x10
        rec_target = 0x90
        struct.pack_into("<q", rec, rec_field, rec_target - rec_field)
        new_iw_bytes.extend(rec)

        new_iw_exports.append({
            "root": insert_iw + idx * INWORLD_SIZE,
            "type_id": 0x129,
            "uid": iw_uid,
            "name": iw_name,
        })

    total_iw_size = len(new_iw_bytes)

    # Insert in-world bytes at insert_iw
    data1 = bytearray(data[:insert_iw] + bytes(new_iw_bytes) + data[insert_iw:])
    relocs1 = []
    for r in relocs:
        f = int(r["field"]) + total_iw_size if int(r["field"]) >= insert_iw else int(r["field"])
        t = int(r["target"]) + total_iw_size if int(r["target"]) >= insert_iw else int(r["target"])
        struct.pack_into("<q", data1, f, t - f)
        relocs1.append({"field": f, "target": t, "delta": t - f})

    for idx in range(len(sorted_specs)):
        f = insert_iw + idx * INWORLD_SIZE + 0x10
        t = insert_iw + idx * INWORLD_SIZE + 0x90
        struct.pack_into("<q", data1, f, t - f)
        relocs1.append({"field": f, "target": t, "delta": t - f})

    # 3. Class insertion position (at end of type-0x11E block, immediately before COMPASS_GLOBALS)
    orig_insert_class = int(globals_row["root"])
    insert_class = orig_insert_class + total_iw_size

    new_class_bytes = bytearray()
    new_class_exports = []
    for idx, s in enumerate(sorted_specs):
        hud_hash = packed.name_hash(s["hud_resource"])
        class_name = s["compass_class"]
        class_uid = packed.name_hash(class_name)
        carrier_name = inworld_name_for(class_name)
        carrier_uid = packed.name_hash(carrier_name)

        record = bytearray(CLASS_SIZE)
        struct.pack_into("<QQQI", record, 0, hud_hash, 0, carrier_uid, 0x3F800000)
        new_class_bytes.extend(record)

        new_class_exports.append({
            "root": insert_class + idx * CLASS_SIZE,
            "type_id": 0x11E,
            "uid": class_uid,
            "name": class_name,
        })

    total_class_size = len(new_class_bytes)
    data2 = bytearray(data1[:insert_class] + bytes(new_class_bytes) + data1[insert_class:])
    relocs2 = []
    for r in relocs1:
        f = r["field"] + total_class_size if r["field"] >= insert_class else r["field"]
        t = r["target"] + total_class_size if r["target"] >= insert_class else r["target"]
        struct.pack_into("<q", data2, f, t - f)
        relocs2.append({"field": f, "target": t, "delta": t - f})

    # 4. Exports table
    all_new_exports = new_iw_exports + new_class_exports
    table_growth = len(all_new_exports) * 24

    def final_offset(offset: int) -> int:
        shifted1 = offset + total_iw_size if offset >= insert_iw else offset
        shifted2 = shifted1 + total_class_size if shifted1 >= insert_class else shifted1
        return shifted2

    final_exports = []
    for e in exports:
        final_exports.append({
            **e,
            "root": final_offset(int(e["root"])),
            "string_offset": int(e["string_offset"]) + table_growth,
        })

    strings_tail = bytearray()
    curr_str_offset = 8 + (len(exports) + len(all_new_exports)) * 24 + len(tail)
    for ne in all_new_exports:
        ne["string_offset"] = curr_str_offset
        curr_str_offset += len(ne["name"]) + 1
        strings_tail.extend(ne["name"].encode("ascii") + b"\0")
        final_exports.append(ne)

    final_exports.sort(key=lambda e: int(e["uid"]))
    need(all(a["uid"] < b["uid"] for a, b in zip(final_exports, final_exports[1:])), "exports not strictly sorted")

    final_tail = tail + bytes(strings_tail)
    h = bytearray(header8)
    struct.pack_into("<I", h, 0, len(final_exports))
    export_payload = bytearray(h)
    for e in final_exports:
        export_payload += struct.pack("<IIQQ", int(e["root"]), int(e["type_id"]), int(e["string_offset"]), int(e["uid"]))
    export_payload += final_tail

    fields = [int(r["field"]) for r in relocs2]
    reloc_payload = struct.pack("<I", len(fields))
    if fields:
        reloc_payload += struct.pack(f"<{len(fields)}I", *fields)

    candidate = packed.build_file(chunks, {12: bytes(data2), 13: bytes(export_payload), 15: reloc_payload})

    # Exact inverse verification:
    inv_chunks = packed.parse_chunks(candidate)
    inv_data = bytearray(packed.one(inv_chunks, 12)["payload"])
    _, inv_exports, inv_tail = packed.parse_exports(packed.one(inv_chunks, 13)["payload"])
    inv_relocs = packed.parse_relocations(packed.one(inv_chunks, 15)["payload"], bytes(inv_data))

    # Remove class bytes first (higher offset)
    inv_data_no_class = bytearray(inv_data[:insert_class] + inv_data[insert_class + total_class_size:])
    # Remove in-world bytes (lower offset)
    orig_data = bytearray(inv_data_no_class[:insert_iw] + inv_data_no_class[insert_iw + total_iw_size:])

    # Invert relocations: remove new in-world carrier relocations and shift remaining
    new_carrier_fields = {insert_iw + idx * INWORLD_SIZE + 0x10 for idx in range(len(sorted_specs))}
    orig_relocs = []
    for r in inv_relocs:
        f = int(r["field"])
        t = int(r["target"])
        if f in new_carrier_fields:
            continue
        f1 = f - total_class_size if f >= insert_class + total_class_size else f
        t1 = t - total_class_size if t >= insert_class + total_class_size else t
        f0 = f1 - total_iw_size if f1 >= insert_iw + total_iw_size else f1
        t0 = t1 - total_iw_size if t1 >= insert_iw + total_iw_size else t1
        struct.pack_into("<q", orig_data, f0, t0 - f0)
        orig_relocs.append(f0)

    new_uids = {ne["uid"] for ne in all_new_exports}
    orig_exports = []
    for e in inv_exports:
        if e["uid"] not in new_uids:
            root = int(e["root"])
            r1 = root - total_class_size if root >= insert_class + total_class_size else root
            r0 = r1 - total_iw_size if r1 >= insert_iw + total_iw_size else r1
            orig_exports.append({
                **e,
                "root": r0,
                "string_offset": int(e["string_offset"]) - table_growth,
            })

    orig_tail = inv_tail[:-len(strings_tail)]
    orig_h = bytearray(header8)
    struct.pack_into("<I", orig_h, 0, len(orig_exports))
    orig_exp_payload = bytearray(orig_h)
    for e in orig_exports:
        orig_exp_payload += struct.pack("<IIQQ", int(e["root"]), int(e["type_id"]), int(e["string_offset"]), int(e["uid"]))
    orig_exp_payload += orig_tail

    orig_reloc_payload = struct.pack("<I", len(orig_relocs))
    if orig_relocs:
        orig_reloc_payload += struct.pack(f"<{len(orig_relocs)}I", *orig_relocs)

    inverted_file = packed.build_file(chunks, {12: bytes(orig_data), 13: bytes(orig_exp_payload), 15: orig_reloc_payload})
    need(inverted_file == raw, "wad_r_perm.dcb exact inverse failed")

    return candidate, {
        "exact_inverse": True,
        "added_classes": len(new_class_exports),
        "added_inworld": len(new_iw_exports),
        "insert_offset": insert_class,
    }


def freeze_package(outputs, proof, output, baseline_root=BUILD, source_inputs=None):
    output, baseline_root = safe_io.safe(output), safe_io.safe(baseline_root)
    baseline = json.loads(safe_io.safe(baseline_root / 'baseline.json').read_text())
    allowed_base = {WAD, MASTER, POOL, BOOT}
    if PERM in outputs:
        allowed_base.add(PERM)
    allowed_packs = [{'exec/patch/pc_le/completionist_v105_family_art' + stem + suffix
                     for suffix in ('.texpack', '.texpack.toc')} for stem in ('', '_probe')]
    need(allowed_base <= set(outputs) and set(outputs) - allowed_base in allowed_packs,
         'artwork output allowlist differs')
    for name, expected in baseline["files"].items():
        need(isinstance(name, str) and name and '\\' not in name and ':' not in name and
             not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')),
             'invalid baseline path')
        need(safe_io.sha(baseline_root / 'baseline' / name) == expected, 'baseline drift: ' + name)
    files = {n: {"before": baseline["files"].get(n), "after": sha(raw)} for n, raw in sorted(outputs.items())}
    preserved = {n: h for n, h in baseline["files"].items() if n not in files}
    identity_data = files if source_inputs is None else {'files': files, 'source_inputs': source_inputs}
    package_id = sha(json.dumps(identity_data, sort_keys=True).encode())
    package = safe_io.safe(output / 'packages' / package_id)
    report = {"schema": 1 if source_inputs is None else 2, "kind": "COLLECTIBLE_FAMILY_MAP_ART", "package_id": package_id,
              "files": files, "preserved": preserved, "proof": proof,
              "runtime_coexistence_verified": False}
    if source_inputs is not None:
        report['source_inputs'] = source_inputs
    immutable_report = safe_io.safe(package / 'report.json')
    if package.exists():
        for name, raw in outputs.items():
            need(safe_io.sha(package / 'game-root' / name) == sha(raw), 'immutable candidate drift')
        if immutable_report.exists():
            need(json.loads(immutable_report.read_text()) == report, 'immutable report drift')
        else:
            safe_io.write_json(immutable_report, report)
    else:
        staging = safe_io.safe(output / 'packages' / ('.staging-' + uuid.uuid4().hex))
        staging.mkdir(parents=True, exist_ok=False)
        for name, raw in outputs.items():
            path = safe_io.safe(staging / 'game-root' / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            need(safe_io.sha(path) == sha(raw), 'staged art file differs')
        safe_io.write_json(staging / 'report.json', report)
        safe_io.safe(package)
        os.rename(staging, package)
    safe_io.write_json(output / 'report.json', report)
    return report
