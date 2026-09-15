"""One-shot read-only diagnostic for the canonical Alfheim Raven WAD context.

This tool exists because the 0x82CF00 reconciliation loop passes
[WAD+0x50]+0x54 as an opaque filename/path key; that address is not proven to be
an 8-bit C string.  The diagnostic enumerates the already-proved 64 runtime WAD
contexts, records WAD+0xC3C registry IDs, and decodes the key conservatively as
both UTF-8 and UTF-16 (direct and one pointer indirection).  It never attaches a
debugger and never writes process memory or save/progression data.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct


def load_base_module():
    path = Path(__file__).with_name("capture-raven-readonly-registry.py")
    spec = importlib.util.spec_from_file_location("raven_readonly_registry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


def read_utf16z(reader, address: int, limit_chars: int = 512) -> str | None:
    raw = reader.try_read(address, limit_chars * 2)
    if not raw:
        return None
    end = None
    for offset in range(0, len(raw) - 1, 2):
        if raw[offset:offset + 2] == b"\x00\x00":
            end = offset
            break
    if end is not None:
        raw = raw[:end]
    if len(raw) < 2:
        return None
    if len(raw) & 1:
        raw = raw[:-1]
    try:
        text = raw.decode("utf-16-le", "strict")
    except UnicodeDecodeError:
        return None
    text = text.strip()
    return text or None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    if any(ord(ch) < 0x20 and ch not in "\t\r\n" for ch in value):
        return None
    return value


def decode_key(reader, wad_ptr: int) -> dict:
    result = {
        "owner": None,
        "key_address": None,
        "key_raw_hex": None,
        "direct_utf8": None,
        "direct_utf16": None,
        "key_qword0": None,
        "pointed_utf8": None,
        "pointed_utf16": None,
        "name_candidates": [],
    }
    try:
        owner = reader.u64(wad_ptr + 0x50)
    except OSError:
        return result
    result["owner"] = f"0x{owner:X}"
    if not BASE.plausible_ptr(owner):
        return result

    key = owner + 0x54
    result["key_address"] = f"0x{key:X}"
    raw = reader.try_read(key, 0x80)
    if raw:
        result["key_raw_hex"] = raw.hex()

    direct_utf8 = clean_text(reader.cstring(key, 512))
    direct_utf16 = clean_text(read_utf16z(reader, key, 512))
    result["direct_utf8"] = direct_utf8
    result["direct_utf16"] = direct_utf16

    try:
        qword0 = reader.u64(key)
    except OSError:
        qword0 = 0
    result["key_qword0"] = f"0x{qword0:X}"
    if BASE.plausible_ptr(qword0):
        result["pointed_utf8"] = clean_text(reader.cstring(qword0, 512))
        result["pointed_utf16"] = clean_text(read_utf16z(reader, qword0, 512))

    candidates = []
    for value in (
        result["direct_utf8"], result["direct_utf16"],
        result["pointed_utf8"], result["pointed_utf16"],
    ):
        if value and value not in candidates:
            candidates.append(value)
    result["name_candidates"] = candidates
    return result


def context_rows(reader, base: int) -> list[dict]:
    rows = []
    start = base + BASE.WAD_CONTEXT_ARRAY_RVA
    for index in range(BASE.WAD_CONTEXT_COUNT):
        context = start + index * BASE.WAD_CONTEXT_STRIDE
        try:
            wad_ptr = reader.u64(context + BASE.WAD_CONTEXT_WAD_OFFSET)
        except OSError:
            continue
        if not BASE.plausible_ptr(wad_ptr):
            continue
        try:
            registry_id = reader.u32(wad_ptr + BASE.WAD_REGISTRY_ID_OFFSET)
        except OSError:
            registry_id = None
        identity = decode_key(reader, wad_ptr)
        target_text_match = any(
            BASE.TARGET_WAD in text.lower()
            for text in identity["name_candidates"]
        )
        rows.append({
            "context_index": index,
            "context": f"0x{context:X}",
            "wad_ptr": f"0x{wad_ptr:X}",
            "registry_id": registry_id,
            "target_text_match": target_text_match,
            "identity": identity,
        })
    return rows


def public_registry(row: dict) -> dict:
    return {
        key: (f"0x{value:X}" if key in ("address", "bank") else value)
        for key, value in row.items()
    }


def snapshot(pid: int, exe: Path, wad: Path) -> dict:
    if BASE.sha256_path(exe) != BASE.EXPECTED_EXE_SHA256:
        raise RuntimeError("GoW.exe SHA256 mismatch")
    payload = BASE.load_target_payload(wad)
    reader = BASE.Reader(pid)
    try:
        base, module_path = reader.module()
        if Path(module_path).resolve() != exe.resolve():
            raise RuntimeError(f"PID {pid} executable mismatch: {module_path}")

        contexts = context_rows(reader, base)
        registries = BASE.registry_rows(reader, base)
        registry_by_id = {row["registry_id"]: row for row in registries}
        targets = [row for row in contexts if row["target_text_match"]]
        inspected_targets = []
        candidates = []
        for context in targets:
            registry_id = context.get("registry_id")
            registry = registry_by_id.get(registry_id)
            inspection = None
            if registry is not None:
                inspection = BASE.inspect_registry(reader, registry, payload)
                for obj in inspection.get("objects", []):
                    if obj.get("score", 0) > 0:
                        candidates.append({**obj, "registry_id": registry_id})
            inspected_targets.append({
                "context": context,
                "registry": public_registry(registry) if registry else None,
                "inspection": inspection,
            })
        candidates.sort(key=lambda item: (-item["score"], item["slot"]))

        return {
            "schema": 1,
            "analysis": "gow_raven_readonly_wad_context_identity_diagnostic",
            "pid": pid,
            "module_base": f"0x{base:X}",
            "module_path": module_path,
            "exe_sha256": BASE.EXPECTED_EXE_SHA256,
            "wad_sha256": BASE.EXPECTED_WAD_SHA256,
            "safety": {
                "debugger_attached": False,
                "breakpoints_installed": False,
                "process_writes": False,
                "thread_suspend_resume": False,
                "save_or_progression_writes": False,
                "access": "PROCESS_QUERY_INFORMATION|PROCESS_VM_READ",
            },
            "mapping_proof": {
                "source_function": "0x82CF00",
                "wad_context_array_rva": f"0x{BASE.WAD_CONTEXT_ARRAY_RVA:X}",
                "wad_context_count": BASE.WAD_CONTEXT_COUNT,
                "wad_context_stride": f"0x{BASE.WAD_CONTEXT_STRIDE:X}",
                "wad_pointer_offset": f"0x{BASE.WAD_CONTEXT_WAD_OFFSET:X}",
                "opaque_identity_key": "[WAD+0x50]+0x54",
                "wad_registry_id_offset": f"0x{BASE.WAD_REGISTRY_ID_OFFSET:X}",
                "metadata_identity_key": "metadata_record+0x84",
            },
            "live_wad_context_count": len(contexts),
            "live_wad_contexts": contexts,
            "registry_table_live_entries": len(registries),
            "live_registry_ids": sorted(row["registry_id"] for row in registries),
            "target_text_match_count": len(targets),
            "target_text_matches": inspected_targets,
            "candidate_count": len(candidates),
            "top_candidates": candidates[:25],
            "gameobject_persistent_key_status": "BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY",
            "production_oracle_status": "BLOCKED_EXACT_UNLOADED_STATE_ORACLE",
        }
    finally:
        reader.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = snapshot(args.pid, args.exe, args.wad)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WAD_CONTEXT_DIAGNOSTIC_OK pid={args.pid}")
    print(f"live_wad_context_count={report['live_wad_context_count']}")
    print("live_registry_ids=" + ",".join(str(value) for value in report["live_registry_ids"]))
    print(f"target_text_match_count={report['target_text_match_count']}")
    for item in report["target_text_matches"]:
        context = item["context"]
        print(f"target_context=index={context['context_index']} registry={context['registry_id']} wad={context['wad_ptr']}")
    print(f"candidate_count={report['candidate_count']}")
    for index, candidate in enumerate(report["top_candidates"][:5], 1):
        print(f"candidate_{index}=token={candidate['token_hex']} registry={candidate['registry_id']} slot={candidate['slot']} score={candidate['score']} evidence={','.join(candidate['evidence'])}")
    print("BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY")
    print("BLOCKED_EXACT_UNLOADED_STATE_ORACLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
