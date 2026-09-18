#!/usr/bin/env python3
"""Reconstruct the exact Raven GameObject identity vector using read-only memory.

This emulates the now-solved native control flow:
  0x550700  GameObject identity method
  0x1029C0  recursive parent/metadata identity append
  0x101A90  external identity-vector append
  0x1017F0  one 16-byte element wrapper

Only PROCESS_VM_READ | PROCESS_QUERY_INFORMATION are requested. No debugger,
remote thread, game-code call, process write, save write, or progression write
is performed.

For the proven inserted VikingFuneral Raven token, the tool reconstructs the
exact vector, verifies the native hash against the proven save object_hash, and
correlates every 16-byte element back to authored WAD bytes and catalogue IDs.
"""
from __future__ import annotations

import argparse
import ctypes as C
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import struct
import sys
import uuid

EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
KNOWN = (
    # Only this record is inserted with ravenKilled in the frozen DEAD carrier.
    ("raven_642d0d164af0a5d4076e77933c549a5d", 0x1BB001DD, 0x98BE1707BA2D65A9),
)
MAX_VECTOR_COUNT = 256
MAX_PARENT_DEPTH = 64
MASK64 = 0xFFFFFFFFFFFFFFFF


def load_module(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load helper {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raw_identity_hash(elements: list[bytes]) -> int:
    value = 0
    for element in elements:
        if len(element) != 16:
            raise ValueError("identity elements must be exactly 16 bytes")
        for byte in element:
            value = ((value + byte) * 0x401) & MASK64
            value ^= value >> 6
    return value


class Reader:
    def __init__(self, helper, k32, process):
        self.h = helper
        self.k32 = k32
        self.process = process
        self.read_count = 0

    def read(self, address: int, size: int) -> bytes:
        self.read_count += 1
        return self.h.read_mem(self.k32, self.process, address, size)

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]


def read_vector(reader: Reader, ptr: int, source: str) -> tuple[list[bytes], dict]:
    if ptr == 0:
        return [], {"source": source, "ptr": None, "count": 0}
    count = reader.u32(ptr)
    if count > MAX_VECTOR_COUNT:
        raise RuntimeError(f"{source}: implausible vector count {count} at 0x{ptr:X}")
    raw = reader.read(ptr + 4, count * 16) if count else b""
    elements = [raw[i:i + 16] for i in range(0, len(raw), 16)]
    return elements, {
        "source": source,
        "ptr": f"0x{ptr:X}",
        "count": count,
        "elements_hex": [x.hex() for x in elements],
    }


def append_1029c0(reader: Reader, obj: int, events: list[dict], depth: int = 0, seen=None) -> list[bytes]:
    """Exact semantic emulation of 0x1029C0."""
    if seen is None:
        seen = set()
    if depth > MAX_PARENT_DEPTH:
        raise RuntimeError("identity parent recursion exceeded safety cap")
    if obj in seen:
        raise RuntimeError(f"identity parent recursion cycle at 0x{obj:X}")
    seen.add(obj)

    external = reader.u64(obj + 0x240)
    if external:
        elements, evidence = read_vector(reader, external, f"object+0x240 depth={depth}")
        events.append({
            "kind": "external_vector",
            "object_ptr": f"0x{obj:X}",
            "depth": depth,
            **evidence,
        })
        seen.remove(obj)
        return elements

    flags_278 = reader.u8(obj + 0x278)
    if flags_278 & 0x80:
        events.append({
            "kind": "object_identity_suppressed",
            "object_ptr": f"0x{obj:X}",
            "depth": depth,
            "field_278_byte": flags_278,
        })
        seen.remove(obj)
        return []

    result: list[bytes] = []
    parent = reader.u64(obj + 0x28)
    if parent:
        events.append({
            "kind": "parent",
            "object_ptr": f"0x{obj:X}",
            "parent_ptr": f"0x{parent:X}",
            "depth": depth,
        })
        result.extend(append_1029c0(reader, parent, events, depth + 1, seen))

    meta = reader.u64(obj + 0x30)
    if meta:
        type_byte = reader.u8(meta + 2)
        if type_byte == 2:
            b0 = reader.u64(meta + 0xB0)
            vec_ptr = reader.u64(b0 + 0x10) if b0 else 0
            if vec_ptr:
                elements, evidence = read_vector(reader, vec_ptr, f"metadata depth={depth}")
                events.append({
                    "kind": "metadata_vector",
                    "object_ptr": f"0x{obj:X}",
                    "metadata_ptr": f"0x{meta:X}",
                    "metadata_b0_ptr": f"0x{b0:X}",
                    "depth": depth,
                    **evidence,
                })
                result.extend(elements)
            else:
                events.append({
                    "kind": "metadata_vector_missing",
                    "object_ptr": f"0x{obj:X}",
                    "metadata_ptr": f"0x{meta:X}",
                    "metadata_b0_ptr": f"0x{b0:X}" if b0 else None,
                    "depth": depth,
                })
        else:
            events.append({
                "kind": "metadata_type_skipped",
                "object_ptr": f"0x{obj:X}",
                "metadata_ptr": f"0x{meta:X}",
                "metadata_type_byte": type_byte,
                "depth": depth,
            })

    seen.remove(obj)
    return result


def build_550700(reader: Reader, obj: int) -> tuple[list[bytes], dict]:
    """Exact semantic emulation of the reachable 0x550700 Raven path."""
    meta = reader.u64(obj + 0x30)
    if not meta:
        raise RuntimeError(f"object 0x{obj:X} has NULL +0x30 metadata")
    meta_type = reader.u8(meta + 2)
    meta_flags_68 = reader.u32(meta + 0x68)
    special = meta_type == 1 and ((meta_flags_68 >> 19) & 1) != 0

    events: list[dict] = []
    if special:
        elements = append_1029c0(reader, obj, events)
        own = None
        path = "special_1029c0_only"
    else:
        elements = append_1029c0(reader, obj, events)
        own = reader.read(obj + 0x40, 16)
        elements.append(own)
        events.append({
            "kind": "object_plus_40_element",
            "object_ptr": f"0x{obj:X}",
            "depth": 0,
            "element_hex": own.hex(),
        })
        path = "recursive_then_object_plus_40"

    return elements, {
        "path": path,
        "object_ptr": f"0x{obj:X}",
        "metadata_ptr": f"0x{meta:X}",
        "metadata_type_byte": meta_type,
        "metadata_flags_68_hex": f"0x{meta_flags_68:08X}",
        "special_flag_bit19": bool((meta_flags_68 >> 19) & 1),
        "object_plus_40_hex": own.hex() if own is not None else None,
        "events": events,
    }


def catalogue_variants(row: dict) -> dict[str, bytes]:
    n = row["native"]
    out: dict[str, bytes] = {}

    def add_raw(label: str, text: str | None):
        if not text:
            return
        raw = bytes.fromhex(text.replace("-", ""))
        if len(raw) != 16:
            return
        out[label + ".raw"] = raw
        out[label + ".reverse"] = raw[::-1]
        out[label + ".guid_le_fields"] = raw[3::-1] + raw[5:3:-1] + raw[7:5:-1] + raw[8:]
        out[label + ".swap_u64"] = raw[8:] + raw[:8]

    for key in ("final_record_id", "override_record_id", "prototype_id", "parent_prototype_id"):
        add_raw(key, n.get(key))
    for key in ("instance_guid", "script_guid"):
        value = n.get(key)
        if value:
            u = uuid.UUID(value)
            out[key + ".uuid_be"] = u.bytes
            out[key + ".uuid_le_fields"] = u.bytes_le
            out[key + ".uuid_reverse"] = u.bytes[::-1]

    for i, item in enumerate(row.get("source", {}).get("transform_chain", [])):
        add_raw(f"transform_chain_{i}", item.get("record_id"))
    return out


def wad_hits(element: bytes, raw: bytes, records: list[dict]) -> list[dict]:
    hits = []
    start = 0
    while True:
        at = raw.find(element, start)
        if at < 0:
            break
        rec = None
        where = None
        for r in records:
            header_start = r["offset"]
            payload_start = r["offset"] + 96
            payload_end = payload_start + r["size"]
            if header_start <= at < payload_start:
                rec = r
                where = "record_header"
                break
            if payload_start <= at < payload_end:
                rec = r
                where = "record_payload"
                break
        hits.append({
            "wad_offset": f"0x{at:X}",
            "where": where,
            "record_name": rec["name"] if rec else None,
            "record_kind": rec["kind"] if rec else None,
            "record_offset": f"0x{rec['offset']:X}" if rec else None,
            "offset_within_record": f"0x{at - rec['offset']:X}" if rec else None,
        })
        start = at + 1
        if len(hits) >= 64:
            break
    return hits


def shared_structure(records: list[dict]) -> dict:
    if not records:
        return {}
    vectors = [[x["hex"] for x in r["identity_elements"]] for r in records]
    min_len = min(map(len, vectors))
    prefix = 0
    while prefix < min_len and len({v[prefix] for v in vectors}) == 1:
        prefix += 1
    suffix = 0
    while suffix < min_len - prefix and len({v[-1 - suffix] for v in vectors}) == 1:
        suffix += 1
    return {
        "vector_lengths": [len(v) for v in vectors],
        "shared_prefix_elements": prefix,
        "shared_suffix_elements": suffix,
        "shared_prefix_hex": vectors[0][:prefix],
        "shared_suffix_hex": vectors[0][len(vectors[0]) - suffix:] if suffix else [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--catalogue", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    if sys.platform != "win32":
        raise RuntimeError("this read-only live-memory capture requires Windows")

    helper = load_module("gow_readonly_identity", "read-raven-gameobject-identity-memory.py")
    rc = load_module("gow_raven_catalogue", "raven_catalogue.py")

    k32 = helper.configure_kernel32()
    pid, exe_name = helper.find_supported_process(k32)
    module_base, module_size, exe_path = helper.get_main_module(k32, pid, exe_name)
    exe_sha = helper.sha256_file(exe_path)
    if exe_sha.lower() != EXPECTED_EXE_SHA256:
        raise RuntimeError(f"unsupported GoW.exe SHA-256: {exe_sha}")

    access = helper.PROCESS_VM_READ | helper.PROCESS_QUERY_INFORMATION
    process = k32.OpenProcess(access, False, pid)
    if not process:
        raise helper.winerr("OpenProcess(read-only) failed")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    by_id = {r["catalogue_id"]: r for r in catalogue["ravens"]}
    rows = []
    try:
        for catalogue_id, token, target_hash in KNOWN:
            row = by_id[catalogue_id]
            resolved = helper.resolve_token_read_only(k32, process, module_base, token)
            obj = int(resolved["object_ptr"])
            reader = Reader(helper, k32, process)
            elements, build = build_550700(reader, obj)
            actual_hash = raw_identity_hash(elements)

            wad_path = args.game_root / "exec" / "wad" / "pc_le" / row["source"]["wad"]
            wad_raw = wad_path.read_bytes()
            if rc.digest(wad_raw) != row["source"]["wad_sha256"]:
                raise RuntimeError(f"WAD SHA mismatch for {wad_path.name}")
            wad_records = rc.parse_wad(wad_raw)
            variants = catalogue_variants(row)

            element_rows = []
            for index, element in enumerate(elements):
                labels = sorted(k for k, v in variants.items() if v == element)
                hits = wad_hits(element, wad_raw, wad_records)
                element_rows.append({
                    "index": index,
                    "hex": element.hex(),
                    "catalogue_variant_matches": labels,
                    "wad_exact_hits": hits,
                    "wad_exact_hit_count": len(hits),
                })

            rows.append({
                "catalogue_id": catalogue_id,
                "token_hex": f"0x{token:08X}",
                "expected_object_hash_hex": f"0x{target_hash:016X}",
                "reconstructed_object_hash_hex": f"0x{actual_hash:016X}",
                "hash_matches": actual_hash == target_hash,
                "resolved": {
                    "registry": resolved["registry"],
                    "flavor": resolved["flavor"],
                    "slot": resolved["slot"],
                    "object_ptr": f"0x{obj:X}",
                },
                "builder": build,
                "identity_element_count": len(elements),
                "identity_elements": element_rows,
                "read_process_memory_calls": reader.read_count,
                "wad": row["source"]["wad"],
            })
    finally:
        helper.close_handle(k32, process)

    all_match = all(r["hash_matches"] for r in rows)
    report = {
        "schema": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "result": "RAVEN_EXACT_IDENTITY_VECTOR_CAPTURED" if all_match else "RAVEN_IDENTITY_VECTOR_HASH_MISMATCH",
        "process": {
            "pid": pid,
            "exe_name": exe_name,
            "module_base": f"0x{module_base:X}",
            "module_size": module_size,
            "exe_sha256": exe_sha,
        },
        "native_rvas": {
            "identity_method": "0x550700",
            "recursive_append": "0x1029C0",
            "single_element_builder": "0x1017F0",
            "external_vector_append": "0x101A90",
        },
        "records": rows,
        "shared_structure": shared_structure(rows),
        "safety": {
            "open_process_access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
            "debugger_attached": False,
            "remote_game_code_called": False,
            "process_memory_written": False,
            "save_or_progression_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - exact Raven identity-vector read-only capture",
        f"result={report['result']}",
        f"exe_sha256={exe_sha}",
        "",
    ]
    for r in rows:
        lines.append(
            f"{r['catalogue_id']} token={r['token_hex']} slot={r['resolved']['slot']} "
            f"elements={r['identity_element_count']} hash={r['reconstructed_object_hash_hex']} "
            f"expected={r['expected_object_hash_hex']} matches={r['hash_matches']}"
        )
        lines.append(
            f"  path={r['builder']['path']} own40={r['builder']['object_plus_40_hex']}"
        )
        for e in r["identity_elements"]:
            lines.append(
                f"  [{e['index']}] {e['hex']} "
                f"catalogue={e['catalogue_variant_matches']} wad_hits={e['wad_exact_hit_count']}"
            )
            for hit in e["wad_exact_hits"][:8]:
                lines.append(
                    f"       {hit['wad_offset']} {hit['where']} "
                    f"{hit['record_name']} +{hit['offset_within_record']}"
                )
        lines.append("")
    lines.append("SHARED STRUCTURE")
    lines.append(json.dumps(report["shared_structure"], indent=2))
    lines += [
        "",
        "SAFETY",
        "OpenProcess=PROCESS_VM_READ|PROCESS_QUERY_INFORMATION",
        "debugger_attached=false",
        "remote_game_code_called=false",
        "process_memory_written=false",
        "save_or_progression_written=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all_match:
        raise RuntimeError("reconstructed identity vector did not reproduce all three proven save hashes")

    print(
        "RAVEN_EXACT_IDENTITY_VECTOR_CAPTURE_PASS "
        + " ".join(f"{r['catalogue_id'][:14]}={r['identity_element_count']}el" for r in rows)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
