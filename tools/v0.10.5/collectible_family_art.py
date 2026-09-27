"""Isolated map artwork over the exact installed completion build.

Test independent material fields at +0x10 and +0x20 alongside distinct WAD and
texture IDs. Their renderer effect still needs live proof. Structural checks
alone cannot prove artwork coexistence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
stage = locations.base.stage
safe_io = load('family_art_safe_files', HERE / 'install-nornir-map-id-test.py')
RAVEN = clone.RAVEN
MAP_ROLES = ("material", "map_model", "map_proto", "map_root")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(family, role, size=16):
    return hashlib.sha256(f"{NAMESPACE}:{family}:{role}".encode("ascii")).digest()[:size]


def spec_for(family):
    title = "".join(word.capitalize() for word in family.split("_"))
    names = {"material": f"MAT_cmf_{family}", "map_model": f"MDL_cmf_{family}",
             "map_proto": "goProtoMapIconCompletionist" + title,
             "map_root": "gomapiconcompletionist" + title.lower()}
    return {"family": family, "resource": "goMapIconCompletionist" + title,
            "names": names, "ids": {role: identity(family, role) for role in MAP_ROLES},
            "q10": int.from_bytes(identity(family, "material-q10", 8), "little"),
            "q20": int.from_bytes(identity(family, "material-q20", 8), "little")}


def all_definitions():
    rows, _, _ = locations.definitions()
    return locations.base.rows() + rows


def build_wad(source, families):
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
    proof = []
    for spec, textures in families:
        names, ids = spec["names"], spec["ids"]
        need(set(textures) == {"diffuse", "emissive"}, "texture roles differ")
        for role in MAP_ROLES:
            need(ids[role] not in reserved_ids, f"resource collision: {names[role]}")
            reserved_ids.add(ids[role])
        for field in ("q10", "q20"):
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
                struct.pack_into("<Q", target["data"], 0x20, spec["q20"])
            elif role == "map_root":
                target["data"][0x1C:0x54] = names[role].encode("ascii").ljust(56, b"\0")
        for role, texture in textures.items():
            name = texture["name"]
            need(len(name.encode("ascii")) < 56, "texture name too long")
            did = clone.texture_def_id(texture["file_hash"])
            gid = clone.texture_gpu_id(texture["user_hash"])
            need(did not in reserved_ids and gid not in reserved_ids, "texture identity collision")
            reserved_ids.update((did, gid))
            gi, gpu = clone.unique_texture(records, RAVEN[role], gpu=True)
            di, definition = clone.unique_texture(records, RAVEN[role], gpu=False)
            need(len(texture["resident"]) == len(gpu["data"]), "resident size differs")
            new_gpu = clone.clone_texture(gpu, name, gid, texture["resident"])
            new_def = clone.clone_texture(definition, name, did, bytes(definition["data"]))
            # The old builders changed only WAD labels, retaining Dock's internal name.
            new_def["data"][0x0C:0x44] = name.encode("ascii").ljust(56, b"\0")
            struct.pack_into("<Q", new_def["data"], 0x9C, texture["user_hash"])
            clone.retarget_link(chains["material"], RAVEN[role], definition["id"], name, did)
            jobs[gi].append(new_gpu)
            jobs[di].append(new_def)
        for role in MAP_ROLES:
            jobs[infos[role]["end"]].extend(chains[role])
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
                      "material_q10": f"{spec['q10']:016X}", "material_q20": f"{spec['q20']:016X}",
                      "textures": {role: {k: v for k, v in tex.items() if k != "resident"}
                                   for role, tex in textures.items()}})
    # Map resources have six typed records plus two untyped resident GPU records.
    heap, root = logical.payload_records(records)[:2]
    increments = {0xA: 1, 0x10001: 1, 0x20001: 1, 0x2000C: 1, 0x10015: 2}
    total = 0
    for row in logical.read_type_table(old_root):
        count = row["count"] + len(families) * increments.get(row["key"], 0)
        struct.pack_into("<III", root["data"], row["offset"], row["key"], total, count)
        total += count
    need(total == struct.unpack_from("<I", old_heap, 4)[0] + len(families) * 6,
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
    need(len(logical.payload_records(reread)) - len(logical.payload_records(records)) == 8 * len(families),
         "physical resource accounting differs")
    inverse = [r for i, r in enumerate(reread) if i not in inserted]
    for r, data in zip(logical.payload_records(inverse)[:2], (old_heap, old_root)):
        r["data"] = bytearray(data)
    need([logical.record_bytes(r) for r in inverse] == originals,
         "existing Raven/stock record changed")
    need(logical.serialize_wad(inverse) == source, "WAD exact inverse failed")
    return candidate, {"exact_inverse": True, "families": proof, "added_typed": 6 * len(families),
                       "added_payloads": 8 * len(families), "runtime_coexistence_verified": False}


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


def build_pool(raw, resources):
    # Reassign the extra stock quest reserve; do not increase UI physics objects.
    chunk = stage.one_chunk(stage.parse_dcb_chunks(raw), 12)
    count, rows, _ = stage.dcb_rows(raw[chunk["start"]:chunk["end"]])
    spare = [i for i, r in enumerate(rows) if i >= 389 and r["uid"] == locations.base.STOCK_HASH]
    counts = Counter(r["family"] for r in all_definitions() if r["family"] in resources)
    need(len(spare) >= sum(counts.values()) + 128, "insufficient stock quest reserve")
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
    candidate = bytes(result)
    new_count, new_rows, _ = stage.dcb_rows(candidate[chunk["start"]:chunk["end"]])
    need(new_count == count and all(a["capacity"] == b["capacity"] for a, b in zip(rows, new_rows)),
         "pool count/capacity changed")
    need([r["raw"] for r in rows[:389]] == [r["raw"] for r in new_rows[:389]], "original pool changed")
    for at in offsets:
        result[at:at + 8] = raw[at:at + 8]
    need(bytes(result) == raw, "pool exact inverse failed")
    return candidate, {"exact_inverse": True, "total_rows": count, "reassigned": start,
                       "family_slots": dict(counts), "added_physics_objects": 0}


def freeze_package(outputs, proof, output, baseline_root=BUILD, source_inputs=None):
    output, baseline_root = safe_io.safe(output), safe_io.safe(baseline_root)
    baseline = json.loads(safe_io.safe(baseline_root / 'baseline.json').read_text())
    allowed_base = {WAD, MASTER, POOL, BOOT}
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
