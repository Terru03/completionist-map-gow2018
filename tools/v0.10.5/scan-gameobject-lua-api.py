"""Enumerate the version-locked native GameObject Lua binding table.

Read-only PE scan. It verifies the exact GoW.exe build already used by the
object-checkpoint analysis, then scans the descriptor neighbourhood containing
known GameObject bindings (Level/GetDebugName/GetDebugPath) for 24-byte
{handler, zero, name} records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
KNOWN = {
    "Level": (0x11BC618, 0x195360),
    "GetDebugName": (0x11BC880, 0x18F2A0),
    "GetDebugPath": (0x11BC898, 0x18F350),
}
# Deliberately wider than the three known records. Candidate validation below
# rejects non-descriptor data.
SCAN_START_RVA = 0x11B8000
SCAN_END_RVA = 0x11C1000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def c_string(data: bytes, off: int, limit: int = 256) -> str | None:
    if off < 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, min(len(data), off + limit))
    if end < 0 or end == off:
        return None
    raw = data[off:end]
    if any(b < 0x20 or b > 0x7E for b in raw):
        return None
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def plausible_name(name: str) -> bool:
    if not (1 <= len(name) <= 96):
        return False
    first = name[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(ch.isalnum() or ch in "_:." for ch in name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.game_root.resolve() / "GoW.exe"
    digest = sha256(exe)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Unexpected GoW.exe SHA-256: {digest}")

    data = exe.read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    if pe.OPTIONAL_HEADER.ImageBase != IMAGE_BASE:
        raise RuntimeError(f"Unexpected image base: {pe.OPTIONAL_HEADER.ImageBase:#x}")
    image_size = pe.OPTIONAL_HEADER.SizeOfImage

    # Re-verify the three anchors so a coincidental hash/configuration error
    # cannot silently turn this into an unrelated table scan.
    for name, (entry_rva, handler_rva) in KNOWN.items():
        off = pe.get_offset_from_rva(entry_rva)
        handler_va, zero, name_va = struct.unpack_from("<QQQ", data, off)
        if handler_va != IMAGE_BASE + handler_rva or zero != 0:
            raise RuntimeError(f"Known GameObject entry changed: {name}")
        name_rva = name_va - IMAGE_BASE
        got = c_string(data, pe.get_offset_from_rva(name_rva))
        if got != name:
            raise RuntimeError(f"Known GameObject name changed: expected {name!r}, got {got!r}")

    rows: dict[int, dict[str, object]] = {}
    # Descriptor records are 24 bytes, but scan on 8-byte boundaries to avoid
    # assuming the table's first record alignment.
    for rva in range(SCAN_START_RVA, SCAN_END_RVA - 23, 8):
        try:
            off = pe.get_offset_from_rva(rva)
        except Exception:
            continue
        if off + 24 > len(data):
            continue
        handler_va, middle, name_va = struct.unpack_from("<QQQ", data, off)
        if middle != 0:
            continue
        if not (IMAGE_BASE <= handler_va < IMAGE_BASE + image_size):
            continue
        if not (IMAGE_BASE <= name_va < IMAGE_BASE + image_size):
            continue
        try:
            name_off = pe.get_offset_from_rva(name_va - IMAGE_BASE)
        except Exception:
            continue
        name = c_string(data, name_off)
        if name is None or not plausible_name(name):
            continue
        rows[rva] = {
            "name": name,
            "entry_rva": f"0x{rva:X}",
            "handler_rva": f"0x{handler_va - IMAGE_BASE:X}",
        }

    # Keep the contiguous cluster containing all known anchors. This avoids
    # reporting unrelated descriptor families that happen to share the layout.
    sorted_rvas = sorted(rows)
    clusters: list[list[int]] = []
    current: list[int] = []
    for rva in sorted_rvas:
        if not current or rva - current[-1] <= 0x30:
            current.append(rva)
        else:
            clusters.append(current)
            current = [rva]
    if current:
        clusters.append(current)
    anchor_rvas = {entry for entry, _ in KNOWN.values()}
    cluster = next((c for c in clusters if anchor_rvas.issubset(set(c))), None)
    if cluster is None:
        # Some tables contain non-method records between methods. Fall back to
        # all validated descriptors in the narrow scan window while still
        # requiring all anchors to exist.
        if not anchor_rvas.issubset(set(rows)):
            raise RuntimeError("Unable to recover known GameObject descriptor anchors")
        cluster = sorted_rvas

    methods = [rows[rva] for rva in cluster]
    interesting_terms = (
        "id", "guid", "uid", "hash", "record", "instance", "object", "pickle",
        "name", "path", "level", "debug", "key", "ref",
    )
    interesting = [
        row for row in methods
        if any(term in str(row["name"]).lower() for term in interesting_terms)
    ]

    after = sha256(exe)
    if after != digest:
        raise RuntimeError("GoW.exe changed during read-only scan")

    report = {
        "schema": 1,
        "analysis": "gameobject_lua_api_inventory",
        "exe_sha256": digest,
        "scan_start_rva": f"0x{SCAN_START_RVA:X}",
        "scan_end_rva": f"0x{SCAN_END_RVA:X}",
        "method_count": len(methods),
        "methods": methods,
        "identity_candidates": interesting,
        "safety": {
            "read_only": True,
            "game_launched": False,
            "save_opened": False,
            "game_written": False,
            "progression_written": False,
            "source_hash_unchanged": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - GameObject Lua API inventory",
        f"exe_sha256={digest}",
        f"method_count={len(methods)}",
        "",
        "All recovered descriptors:",
    ]
    lines.extend(
        f"  {row['entry_rva']}  {row['handler_rva']}  {row['name']}" for row in methods
    )
    lines += ["", "Identity/read-only candidates:"]
    lines.extend(
        f"  {row['entry_rva']}  {row['handler_rva']}  {row['name']}" for row in interesting
    )
    lines += [
        "",
        "source_hash_unchanged=true game_launched=false save_opened=false progression_written=false",
    ]
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"GAMEOBJECT_LUA_API_SCAN_PASSED methods={len(methods)} identity_candidates={len(interesting)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
