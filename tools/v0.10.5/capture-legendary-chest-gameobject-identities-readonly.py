#!/usr/bin/env python3
"""Resolve the 33 tracked Legendary Chests to exact GameObject identities.

Read-only runtime proof. The script never calls game code and never writes
process memory. It walks the same registry-238 identity vectors used for the
Raven proof and matches each chest only when the complete static scene identity
sequence is exact and unique.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import struct
import sys
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

import legendary_chest_identity as identity

EXE_SHA = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
REGISTRY_ID = 238
TABLE_BEGIN = 0x22A98C0
TABLE_END = 0x22A9AC0
IDENTITY_METHOD_RVA = 0x550700
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 2
TH32CS_SNAPMODULE = 8
TH32CS_SNAPMODULE32 = 16
INVALID_HANDLE_VALUE = C.c_void_p(-1).value
MAX_PATH = 260
MAX_VECTOR_COUNT = 256
MAX_PARENT_DEPTH = 64


class PROCESSENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("cntUsage", W.DWORD),
        ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", C.c_size_t),
        ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
        ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG),
        ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("th32ModuleID", W.DWORD),
        ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
        ("ProccntUsage", W.DWORD), ("modBaseAddr", C.POINTER(C.c_ubyte)),
        ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
        ("szModule", W.WCHAR * 256), ("szExePath", W.WCHAR * MAX_PATH),
    ]


def k32_api():
    k = C.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    k.CreateToolhelp32Snapshot.restype = W.HANDLE
    k.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    k.Process32FirstW.restype = W.BOOL
    k.Process32NextW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    k.Process32NextW.restype = W.BOOL
    k.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
    k.Module32FirstW.restype = W.BOOL
    k.Module32NextW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
    k.Module32NextW.restype = W.BOOL
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.ReadProcessMemory.argtypes = [
        W.HANDLE, W.LPCVOID, W.LPVOID, C.c_size_t, C.POINTER(C.c_size_t)
    ]
    k.ReadProcessMemory.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    k.CloseHandle.restype = W.BOOL
    return k


def close(k, handle):
    if handle and int(C.cast(handle, C.c_void_p).value or 0) not in (
        0, INVALID_HANDLE_VALUE
    ):
        k.CloseHandle(handle)


def winerr(prefix):
    code = C.get_last_error()
    return RuntimeError(f"{prefix}: WinError {code}: {C.FormatError(code).strip()}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_process(k):
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("process snapshot failed")
    found = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = C.sizeof(pe)
        ok = k.Process32FirstW(snap, C.byref(pe))
        while ok:
            name = str(pe.szExeFile)
            if name.lower() in {"gow.exe", "godofwar.exe"}:
                found.append((int(pe.th32ProcessID), name))
            ok = k.Process32NextW(snap, C.byref(pe))
    finally:
        close(k, snap)
    if len(found) != 1:
        raise RuntimeError(
            f"expected one running God of War process, found {found}"
        )
    return found[0]


def main_module(k, pid, name):
    snap = k.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    if C.cast(snap, C.c_void_p).value == INVALID_HANDLE_VALUE:
        raise winerr("module snapshot failed")
    try:
        me = MODULEENTRY32W()
        me.dwSize = C.sizeof(me)
        ok = k.Module32FirstW(snap, C.byref(me))
        while ok:
            if str(me.szModule).lower() == name.lower():
                base = C.cast(me.modBaseAddr, C.c_void_p).value
                if not base:
                    raise RuntimeError("NULL module base")
                return int(base), int(me.modBaseSize), str(me.szExePath)
            ok = k.Module32NextW(snap, C.byref(me))
    finally:
        close(k, snap)
    raise RuntimeError("main GoW module not found")


def read(k, process, address, size):
    if size <= 0:
        return b""
    buf = (C.c_ubyte * size)()
    done = C.c_size_t()
    if not k.ReadProcessMemory(
        process, C.c_void_p(address), buf, size, C.byref(done)
    ):
        raise winerr(f"ReadProcessMemory(0x{address:X},{size}) failed")
    if done.value != size:
        raise RuntimeError(
            f"short read 0x{address:X}: {done.value}/{size}"
        )
    return bytes(buf)


def safe_read(k, process, address, size):
    try:
        return read(k, process, address, size)
    except Exception:
        return None


class Reader:
    def __init__(self, k, process):
        self.k = k
        self.process = process
        self.read_count = 0

    def read(self, address, size):
        self.read_count += 1
        return read(self.k, self.process, address, size)

    def u8(self, address):
        return self.read(address, 1)[0]

    def u32(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def u64(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]


def read_vector(reader, pointer, source):
    if not pointer:
        return [], {"source": source, "ptr": None, "count": 0}
    count = reader.u32(pointer)
    if count > MAX_VECTOR_COUNT:
        raise RuntimeError(f"{source}: vector count {count}")
    raw = reader.read(pointer + 4, count * 16) if count else b""
    elements = [raw[i:i + 16] for i in range(0, len(raw), 16)]
    return elements, {
        "source": source,
        "ptr": f"0x{pointer:X}",
        "count": count,
        "elements_hex": [item.hex() for item in elements],
    }


def append_identity(reader, obj, events, depth=0, seen=None):
    if seen is None:
        seen = set()
    if depth > MAX_PARENT_DEPTH:
        raise RuntimeError("identity recursion cap")
    if obj in seen:
        raise RuntimeError("identity recursion cycle")
    seen.add(obj)
    try:
        external = reader.u64(obj + 0x240)
        if external:
            elements, event = read_vector(
                reader, external, f"object+0x240 depth={depth}"
            )
            events.append(
                {
                    "kind": "external_vector",
                    "object_ptr": f"0x{obj:X}",
                    "depth": depth,
                    **event,
                }
            )
            return elements
        flags = reader.u8(obj + 0x278)
        if flags & 0x80:
            return []
        output = []
        parent = reader.u64(obj + 0x28)
        if parent:
            output.extend(
                append_identity(reader, parent, events, depth + 1, seen)
            )
        metadata = reader.u64(obj + 0x30)
        if metadata and reader.u8(metadata + 2) == 2:
            b0 = reader.u64(metadata + 0xB0)
            vector = reader.u64(b0 + 0x10) if b0 else 0
            if vector:
                elements, event = read_vector(
                    reader, vector, f"metadata depth={depth}"
                )
                events.append(
                    {
                        "kind": "metadata_vector",
                        "object_ptr": f"0x{obj:X}",
                        "depth": depth,
                        **event,
                    }
                )
                output.extend(elements)
        return output
    finally:
        seen.remove(obj)


def build_identity(reader, obj):
    metadata = reader.u64(obj + 0x30)
    if not metadata:
        raise RuntimeError("NULL metadata")
    metadata_type = reader.u8(metadata + 2)
    flags = reader.u32(metadata + 0x68)
    special = metadata_type == 1 and ((flags >> 19) & 1) != 0
    events = []
    elements = append_identity(reader, obj, events)
    own = None
    if not special:
        own = reader.read(obj + 0x40, 16)
        elements.append(own)
    return elements, {
        "metadata_ptr": f"0x{metadata:X}",
        "metadata_type_byte": metadata_type,
        "metadata_flags_68_hex": f"0x{flags:08X}",
        "special_flag_bit19": bool((flags >> 19) & 1),
        "object_plus_40_hex": own.hex() if own is not None else None,
        "events": events,
    }


def validate_catalogue(game_root, catalogue):
    contract = identity.static_contract(catalogue)
    rows = identity.tracked_rows(catalogue)
    checks = []
    files = {}
    try:
        for row in rows:
            wad = game_root / "exec" / "wad" / "pc_le" / row["source"]["wad"]
            handle = files.get(wad)
            if handle is None:
                handle = wad.open("rb")
                files[wad] = handle
            for item in row["source"]["transform_chain"]:
                offset = int(item["offset"], 0)
                expected = bytes.fromhex(item["record_id"])
                handle.seek(offset + 8)
                actual = handle.read(16)
                exact = actual == expected
                checks.append(
                    {
                        "catalogue_id": row["catalogue_id"],
                        "wad": wad.name,
                        "record_name": item["name"],
                        "offset": item["offset"],
                        "expected_record_id_hex": expected.hex(),
                        "actual_record_id_hex": actual.hex(),
                        "exact": exact,
                    }
                )
                if not exact:
                    raise RuntimeError(
                        f"{row['catalogue_id']}: WAD record identity drift at "
                        f"{item['name']} {item['offset']}"
                    )
    finally:
        for handle in files.values():
            handle.close()
    return rows, contract, checks


def find_registry(k, process, base):
    matches = []
    for entry in range(base + TABLE_BEGIN, base + TABLE_END, 8):
        raw = safe_read(k, process, entry, 8)
        if raw is None:
            continue
        descriptor = struct.unpack("<Q", raw)[0]
        if not descriptor:
            continue
        rid = safe_read(k, process, descriptor, 4)
        if rid is None or struct.unpack("<I", rid)[0] != REGISTRY_ID:
            continue
        head = read(k, process, descriptor + 8, 0x18)
        array = struct.unpack_from("<Q", head, 0)[0]
        count = struct.unpack_from("<I", head, 0x10)[0]
        matches.append((descriptor, entry, array, count))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one registry {REGISTRY_ID}, found {len(matches)}"
        )
    descriptor, entry, array, count = matches[0]
    if count > 1048576:
        raise RuntimeError(f"implausible registry count {count}")
    return {
        "descriptor": descriptor,
        "table_entry": entry,
        "array_ptr": array,
        "count": count,
    }


def sweep(k, process, base, registry, rows):
    expected = {}
    static_rows = {}
    adjusted_placement_anchors = {}
    raw_placement_anchors = {}
    for row in rows:
        scene, skipped = identity.scene_identity_elements(row)
        key = tuple(scene)
        if key in expected:
            raise RuntimeError("duplicate tracked Legendary scene identity")
        expected[key] = row["catalogue_id"]
        static_rows[row["catalogue_id"]] = (row, scene, skipped)
        placement = row["source"]["transform_chain"][2]
        adjusted_anchor = identity.adjusted_record_id(
            placement["record_id"]
        ).hex()
        raw_anchor = placement["record_id"].lower()
        adjusted_placement_anchors.setdefault(adjusted_anchor, []).append(
            row["catalogue_id"]
        )
        raw_placement_anchors.setdefault(raw_anchor, []).append(
            row["catalogue_id"]
        )

    count = registry["count"]
    array = registry["array_ptr"]
    raw = read(k, process, array, count * 8) if count else b""
    objects = struct.unpack(f"<{count}Q", raw) if count else ()
    expected_method = base + IDENTITY_METHOD_RVA
    stats = {
        "non_null": 0,
        "identity_method": 0,
        "built": 0,
        "failures": 0,
    }
    matches = []
    ambiguous = []
    prefix_matches = {row["catalogue_id"]: [] for row in rows}
    anchor_hits = {row["catalogue_id"]: [] for row in rows}
    suffix_signature_counts = {}

    for slot, obj in enumerate(objects):
        if not obj:
            continue
        stats["non_null"] += 1
        vtable_raw = safe_read(k, process, obj, 8)
        if vtable_raw is None:
            continue
        vtable = struct.unpack("<Q", vtable_raw)[0]
        method_raw = safe_read(k, process, vtable + 0x38, 8)
        if (
            method_raw is None
            or struct.unpack("<Q", method_raw)[0] != expected_method
        ):
            continue
        stats["identity_method"] += 1
        reader = Reader(k, process)
        try:
            elements, build = build_identity(reader, obj)
            stats["built"] += 1
        except Exception:
            stats["failures"] += 1
            continue

        element_hex = [item.hex() for item in elements]
        base_row = {
            "runtime_registry": REGISTRY_ID,
            "slot": slot,
            "runtime_token_hex": (
                f"0x{(1 | (REGISTRY_ID << 1) | (slot << 18)):016X}"
            ),
            "object_ptr": f"0x{obj:X}",
            "object_hash_hex": f"0x{identity.identity_hash(elements):016X}",
            "identity_elements_hex": element_hex,
            "prototype_identity_element_hex": (
                None if build["special_flag_bit19"] else elements[-1].hex()
            ),
            "builder": build,
            "read_process_memory_calls": reader.read_count,
        }

        # Diagnostic 1: exact placement-anchor hits anywhere in the runtime
        # identity vector.  This is intentionally weaker than acceptance and
        # is archived only to explain a failed exact grammar.
        for position, element in enumerate(element_hex):
            for mode, table in (
                ("adjusted_placement", adjusted_placement_anchors),
                ("raw_placement", raw_placement_anchors),
            ):
                catalogue_ids = table.get(element)
                if not catalogue_ids:
                    continue
                for catalogue_id in catalogue_ids:
                    bucket = anchor_hits[catalogue_id]
                    if len(bucket) < 8:
                        bucket.append(
                            {
                                **base_row,
                                "anchor_mode": mode,
                                "anchor_position": position,
                                "anchor_catalogue_candidates": sorted(
                                    catalogue_ids
                                ),
                            }
                        )

        candidates = []
        for scene_key, catalogue_id in expected.items():
            scene = list(scene_key)

            # Strong diagnostic: the exact physical scene path is a prefix,
            # while one or more descendant/subobject identity elements may
            # follow it.  This lets us discover chest-specific suffix grammar
            # without accepting it prematurely.
            if len(elements) >= len(scene) and elements[:len(scene)] == scene:
                suffix = elements[len(scene):]
                suffix_hex = [item.hex() for item in suffix]
                bucket = prefix_matches[catalogue_id]
                if len(bucket) < 16:
                    bucket.append(
                        {
                            **base_row,
                            "scene_prefix_length": len(scene),
                            "suffix_elements_hex": suffix_hex,
                            "suffix_count": len(suffix),
                        }
                    )
                signature = "|".join(suffix_hex) if suffix_hex else "<empty>"
                suffix_signature_counts[signature] = (
                    suffix_signature_counts.get(signature, 0) + 1
                )

            # Acceptance remains conservative: one exact physical scene plus
            # exactly one native own/prototype element, matching the already
            # proven Raven GameObject identity shape.
            special = build["special_flag_bit19"]
            exact = (
                elements == scene
                if special
                else len(elements) == len(scene) + 1
                and elements[:-1] == scene
            )
            if exact:
                candidates.append(catalogue_id)

        if not candidates:
            continue
        if len(candidates) != 1:
            ambiguous.append(
                {**base_row, "catalogue_ids": sorted(candidates)}
            )
            continue

        catalogue_id = candidates[0]
        row, scene, skipped = static_rows[catalogue_id]
        registry_hash = identity.registry_hash_for_wad(row["source"]["wad"])
        object_hash = identity.identity_hash(elements)
        matches.append(
            {
                **base_row,
                "catalogue_id": catalogue_id,
                "display_name": row["display_name"],
                "wad": row["source"]["wad"],
                "physical_instance_guid": row["native"]["instance_guid"],
                "state_instance_guid": row["native"]["state_instance_guid"],
                "scene_identity_elements_hex": [
                    item.hex() for item in scene
                ],
                "skipped_nested_records": skipped,
                "serialized_registry_hash_hex": (
                    f"0x{registry_hash:016X}"
                ),
                "serialized_object_hash_hex": f"0x{object_hash:016X}",
                "serialized_flag1_hex": identity.serialized_payload(
                    registry_hash, object_hash
                ).hex(),
            }
        )

    duplicate_adjusted_anchors = {
        key: sorted(values)
        for key, values in adjusted_placement_anchors.items()
        if len(values) > 1
    }
    duplicate_raw_anchors = {
        key: sorted(values)
        for key, values in raw_placement_anchors.items()
        if len(values) > 1
    }
    diagnostics = {
        "placement_anchor_contract": {
            "adjusted_unique_values": len(adjusted_placement_anchors),
            "raw_unique_values": len(raw_placement_anchors),
            "duplicate_adjusted_anchors": duplicate_adjusted_anchors,
            "duplicate_raw_anchors": duplicate_raw_anchors,
            "anchors_are_diagnostic_only": True,
            "full_scene_path_remains_acceptance_identity": True,
        },
        "prefix_match_rows": sum(
            1 for values in prefix_matches.values() if values
        ),
        "prefix_match_objects": sum(len(values) for values in prefix_matches.values()),
        "prefix_matches": {
            key: values
            for key, values in prefix_matches.items()
            if values
        },
        "anchor_hit_rows": sum(
            1 for values in anchor_hits.values() if values
        ),
        "anchor_hit_objects": sum(len(values) for values in anchor_hits.values()),
        "anchor_hits": {
            key: values
            for key, values in anchor_hits.items()
            if values
        },
        "suffix_signature_counts": dict(
            sorted(
                suffix_signature_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
    }
    return stats, matches, ambiguous, diagnostics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-root",
        type=Path,
        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"),
    )
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("64-bit Windows required")

    game_root = args.game_root.resolve()
    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    rows, contract, source_checks = validate_catalogue(game_root, catalogue)

    k = k32_api()
    pid, name = find_process(k)
    base, size, exe = main_module(k, pid, name)
    exe_sha = sha256_file(exe)
    if exe_sha.lower() != EXE_SHA:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    process = k.OpenProcess(
        PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
    )
    if not process:
        raise winerr("OpenProcess read-only failed")
    try:
        registry = find_registry(k, process, base)
        stats, raw_matches, ambiguous, diagnostics = sweep(
            k, process, base, registry, rows
        )
    finally:
        close(k, process)

    by_id = {}
    for row in raw_matches:
        by_id.setdefault(row["catalogue_id"], []).append(row)

    resolved = []
    duplicates = []
    for catalogue_id, items in sorted(by_id.items()):
        if len(items) == 1:
            resolved.append(items[0])
        else:
            duplicates.append(
                {
                    "catalogue_id": catalogue_id,
                    "slots": [item["slot"] for item in items],
                    "object_hashes": [
                        item["object_hash_hex"] for item in items
                    ],
                }
            )

    expected_ids = sorted(row["catalogue_id"] for row in rows)
    found = {row["catalogue_id"] for row in resolved}
    missing = [item for item in expected_ids if item not in found]
    prototype_elements = sorted(
        {
            row["prototype_identity_element_hex"]
            for row in resolved
            if row["prototype_identity_element_hex"] is not None
        }
    )
    complete = (
        len(resolved) == identity.EXPECTED_TRACKED
        and not missing
        and not duplicates
        and not ambiguous
    )

    report = {
        "schema": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "result": (
            "ALL_33_TRACKED_LEGENDARY_CHEST_GAMEOBJECT_IDENTITIES_RESOLVED"
            if complete
            else "PARTIAL_LEGENDARY_CHEST_GAMEOBJECT_IDENTITY_SWEEP"
        ),
        "process": {
            "pid": pid,
            "exe_name": name,
            "module_base": f"0x{base:X}",
            "module_size": size,
            "exe_sha256": exe_sha,
        },
        "static_contract": contract,
        "source_identity_checks": {
            "count": len(source_checks),
            "all_exact": all(item["exact"] for item in source_checks),
            "rows": source_checks,
        },
        "registry": {
            "id": REGISTRY_ID,
            "descriptor": f"0x{registry['descriptor']:X}",
            "table_entry": f"0x{registry['table_entry']:X}",
            "array_ptr": f"0x{registry['array_ptr']:X}",
            "count": registry["count"],
            **stats,
        },
        "resolved_count": len(resolved),
        "resolved": resolved,
        "prototype_identity_elements_hex": prototype_elements,
        "missing_count": len(missing),
        "missing_catalogue_ids": missing,
        "duplicate_catalogue_matches": duplicates,
        "ambiguous_scene_matches": ambiguous,
        "identity_diagnostics": diagnostics,
        "safety": {
            "open_process_access": (
                "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION"
            ),
            "debugger_attached": False,
            "remote_game_code_called": False,
            "process_memory_written": False,
            "active_save_opened": False,
            "save_or_progression_written": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "Completionist Map - tracked Legendary Chest GameObject identities",
        f"result={report['result']}",
        (
            f"registry={REGISTRY_ID} count={registry['count']} "
            f"non_null={stats['non_null']} "
            f"identity_method={stats['identity_method']} "
            f"vectors={stats['built']} failures={stats['failures']}"
        ),
        (
            f"resolved={len(resolved)} missing={len(missing)} "
            f"duplicates={len(duplicates)} ambiguous={len(ambiguous)}"
        ),
        (
            "prototype_identity_elements="
            + (
                ",".join(prototype_elements)
                if prototype_elements
                else "-"
            )
        ),
        (
            "diagnostic_prefix_rows="
            f"{diagnostics['prefix_match_rows']} "
            "diagnostic_anchor_rows="
            f"{diagnostics['anchor_hit_rows']}"
        ),
        "",
        "RESOLVED",
    ]
    for row in resolved:
        lines.append(
            f"{row['catalogue_id']} "
            f"registry_hash={row['serialized_registry_hash_hex']} "
            f"object_hash={row['serialized_object_hash_hex']} "
            f"payload={row['serialized_flag1_hex']} "
            f"wad={row['wad']}"
        )
    if missing:
        lines += ["", "MISSING", *missing]
    lines += [
        "",
        "SAFETY",
        "OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
        "process_memory_written=false",
        "active_save_opened=false",
        "save_or_progression_written=false",
        "game_files_written=false",
    ]
    args.output_text.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(
        "LEGENDARY_CHEST_GAMEOBJECT_IDENTITIES_READONLY_SWEEP_COMPLETE "
        f"resolved={len(resolved)} missing={len(missing)} "
        f"registry_non_null={stats['non_null']} vectors={stats['built']}"
    )
    print(
        "process_memory_written=false active_save_opened=false "
        "save_or_progression_written=false"
    )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
