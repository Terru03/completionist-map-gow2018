"""Exhaustively enumerate direct native Lua registration-table shapes in GoW.exe.

This is a read-only PE scan. Unlike the earlier anchor-driven enumerator, this
scanner does not begin from known method names. It walks every 8-byte-aligned
location in non-executable PE sections and recognizes direct records whose first
qword points to a printable NUL-terminated ASCII name and whose second qword
points into executable code. It then groups all contiguous records for a bounded
set of common native registration strides.

The result is exhaustive for this *direct name-pointer + function-pointer* table
shape and the scanned strides. It does not claim that every engine binding must
use this representation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Optional

IMAGE_SCN_MEM_EXECUTE = 0x20000000
MAX_ASCII = 192
STRIDES = (16, 24, 32, 40, 48, 56, 64)
MIN_TABLE_ENTRIES = 2
MAX_TABLE_ENTRIES = 2048

INTERESTING_NEEDLES = (
    "checkpoint", "save", "load", "restore", "state", "persist", "serial",
    "subobject", "object", "guid", "instance", "query", "find", "get",
    "soft", "retain", "forget", "stream", "lookup", "resolve",
)

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:.<>/+-]{0,191}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PEImage:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x100 or data[:2] != b"MZ":
            raise RuntimeError("GoW.exe is not an MZ image")
        self.pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[self.pe_off:self.pe_off + 4] != b"PE\0\0":
            raise RuntimeError("Invalid PE signature")
        self.num_sections = struct.unpack_from("<H", data, self.pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, self.pe_off + 20)[0]
        opt = self.pe_off + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("Expected PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", data, opt + 60)[0]
        sec_off = opt + size_opt
        self.sections: list[dict] = []
        for i in range(self.num_sections):
            off = sec_off + i * 40
            name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from(
                "<IIII", data, off + 8)
            characteristics = struct.unpack_from("<I", data, off + 36)[0]
            self.sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
                "executable": bool(characteristics & IMAGE_SCN_MEM_EXECUTE),
            })

    def section_for_file(self, offset: int) -> Optional[dict]:
        if 0 <= offset < self.size_of_headers:
            return {
                "name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                "executable": False,
            }
        for sec in self.sections:
            if sec["raw_ptr"] <= offset < sec["raw_ptr"] + sec["raw_size"]:
                return sec
        return None

    def section_for_rva(self, rva: int) -> Optional[dict]:
        if 0 <= rva < self.size_of_headers:
            return {
                "name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                "executable": False,
            }
        for sec in self.sections:
            span = max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + span:
                return sec
        return None

    def file_to_rva(self, off: int) -> Optional[int]:
        sec = self.section_for_file(off)
        if sec is None:
            return None
        return sec["virtual_address"] + (off - sec["raw_ptr"])

    def rva_to_file(self, rva: int) -> Optional[int]:
        if 0 <= rva < self.size_of_headers:
            return rva if rva < len(self.data) else None
        sec = self.section_for_rva(rva)
        if sec is None:
            return None
        delta = rva - sec["virtual_address"]
        if delta >= sec["raw_size"]:
            return None
        off = sec["raw_ptr"] + delta
        return off if off < len(self.data) else None

    def va_to_rva(self, va: int) -> Optional[int]:
        if self.image_base <= va < self.image_base + self.size_of_image:
            return va - self.image_base
        return None

    def ascii_at(self, off: int) -> Optional[str]:
        if off < 0 or off >= len(self.data):
            return None
        end = off
        while end < len(self.data) and end - off <= MAX_ASCII:
            b = self.data[end]
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            end += 1
        if end == off or end >= len(self.data) or self.data[end] != 0:
            return None
        value = self.data[off:end].decode("ascii", "replace")
        return value if NAME_RE.fullmatch(value) else None

    def decode_pair(self, off: int) -> Optional[dict]:
        if off < 0 or off + 16 > len(self.data):
            return None
        sec = self.section_for_file(off)
        if sec is None or sec.get("executable"):
            return None
        name_va, fn_va = struct.unpack_from("<QQ", self.data, off)
        name_rva = self.va_to_rva(name_va)
        fn_rva = self.va_to_rva(fn_va)
        if name_rva is None or fn_rva is None:
            return None
        name_off = self.rva_to_file(name_rva)
        if name_off is None:
            return None
        name = self.ascii_at(name_off)
        if not name:
            return None
        fn_sec = self.section_for_rva(fn_rva)
        if fn_sec is None or not fn_sec.get("executable"):
            return None
        return {
            "offset": off,
            "offset_hex": f"0x{off:X}",
            "section": sec["name"],
            "name": name,
            "name_va": f"0x{name_va:X}",
            "name_rva": f"0x{name_rva:X}",
            "function_va": f"0x{fn_va:X}",
            "function_rva": f"0x{fn_rva:X}",
            "function_section": fn_sec["name"],
        }


def aligned_range(start: int, end: int, alignment: int = 8):
    first = (start + alignment - 1) // alignment * alignment
    return range(first, end, alignment)


def discover_pairs(pe: PEImage) -> dict[int, dict]:
    pairs: dict[int, dict] = {}
    for sec in pe.sections:
        if sec["executable"] or sec["raw_size"] < 16:
            continue
        start = sec["raw_ptr"]
        end = min(len(pe.data), start + sec["raw_size"] - 15)
        for off in aligned_range(start, end):
            pair = pe.decode_pair(off)
            if pair is not None:
                pairs[off] = pair
    return pairs


def extra_qwords(pe: PEImage, off: int, stride: int) -> list[str]:
    return [
        f"0x{struct.unpack_from('<Q', pe.data, pos)[0]:X}"
        for pos in range(off + 16, off + stride, 8)
    ]


def discover_tables(pe: PEImage, pairs: dict[int, dict]) -> list[dict]:
    tables: list[dict] = []
    offsets = set(pairs)
    for stride in STRIDES:
        for start in sorted(offsets):
            if start - stride in offsets:
                continue
            entries = []
            off = start
            while off in offsets and len(entries) < MAX_TABLE_ENTRIES:
                pair = dict(pairs[off])
                pair["extra_qwords"] = extra_qwords(pe, off, stride)
                entries.append(pair)
                off += stride
            if len(entries) < MIN_TABLE_ENTRIES:
                continue
            tables.append({
                "stride": stride,
                "stride_hex": f"0x{stride:X}",
                "start_offset": start,
                "start_offset_hex": f"0x{start:X}",
                "end_offset": off,
                "end_offset_hex": f"0x{off:X}",
                "entry_count": len(entries),
                "section": entries[0]["section"],
                "entries": entries,
            })
    tables.sort(key=lambda t: (t["start_offset"], t["stride"], -t["entry_count"]))
    return tables


def is_interesting(name: str) -> bool:
    low = name.lower()
    return any(needle in low for needle in INTERESTING_NEEDLES)


def interesting_string_inventory(pe: PEImage, pairs: dict[int, dict], tables: list[dict]) -> list[dict]:
    registered_offsets = {
        entry["offset"] for table in tables for entry in table["entries"]
    }
    direct_pair_offsets = set(pairs)

    # Build a map of interesting ASCII string VA -> metadata, then scan aligned qwords
    # once for absolute pointers. This avoids one full executable scan per string.
    strings_by_va: dict[int, dict] = {}
    ascii_rx = re.compile(rb"[ -~]{3,192}\x00")
    for sec in pe.sections:
        if sec["raw_size"] <= 0:
            continue
        start = sec["raw_ptr"]
        end = min(len(pe.data), start + sec["raw_size"])
        blob = pe.data[start:end]
        for match in ascii_rx.finditer(blob):
            raw = match.group()[:-1]
            try:
                value = raw.decode("ascii")
            except UnicodeDecodeError:
                continue
            if not NAME_RE.fullmatch(value) or not is_interesting(value):
                continue
            off = start + match.start()
            rva = pe.file_to_rva(off)
            if rva is None:
                continue
            va = pe.image_base + rva
            strings_by_va[va] = {
                "name": value,
                "string_offset": f"0x{off:X}",
                "string_rva": f"0x{rva:X}",
                "string_va": f"0x{va:X}",
                "absolute_xrefs": [],
            }

    targets = set(strings_by_va)
    if targets:
        for off in aligned_range(0, len(pe.data) - 7):
            value = struct.unpack_from("<Q", pe.data, off)[0]
            if value in targets:
                strings_by_va[value]["absolute_xrefs"].append(f"0x{off:X}")

    out = []
    for va, item in strings_by_va.items():
        xref_ints = [int(x, 16) for x in item["absolute_xrefs"]]
        pair_refs = [x for x in xref_ints if x in direct_pair_offsets]
        table_refs = [x for x in xref_ints if x in registered_offsets]
        out.append({
            **item,
            "direct_name_function_pair_xrefs": [f"0x{x:X}" for x in pair_refs],
            "contiguous_table_entry_xrefs": [f"0x{x:X}" for x in table_refs],
            "orphan_absolute_xrefs": [
                f"0x{x:X}" for x in xref_ints if x not in registered_offsets
            ],
        })
    out.sort(key=lambda x: (x["name"].lower(), x["string_rva"]))
    return out


def canonical_direct_tables(tables: list[dict]) -> list[dict]:
    """Prefer densest/minimum-stride views for overlapping starts.

    Raw candidate_tables remains authoritative. This derived list only reduces
    obvious every-Nth-entry aliases such as 48-byte views of a 24-byte table.
    """
    ranked = sorted(tables, key=lambda t: (-t["entry_count"], t["stride"], t["start_offset"]))
    chosen: list[dict] = []
    covered: set[int] = set()
    for table in ranked:
        offsets = {entry["offset"] for entry in table["entries"]}
        if len(offsets - covered) == 0:
            continue
        chosen.append(table)
        covered.update(offsets)
    chosen.sort(key=lambda t: (t["start_offset"], t["stride"]))
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    root = args.game_root.expanduser().resolve()
    exe = (root / "GoW.exe").resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")

    before = sha256_file(exe)
    data = exe.read_bytes()
    pe = PEImage(data)
    pairs = discover_pairs(pe)
    tables = discover_tables(pe, pairs)
    canonical = canonical_direct_tables(tables)
    interesting_entries = []
    for table in canonical:
        for entry in table["entries"]:
            if is_interesting(entry["name"]):
                interesting_entries.append({
                    "table_start": table["start_offset_hex"],
                    "stride": table["stride"],
                    **entry,
                })
    interesting_entries.sort(key=lambda x: (x["name"].lower(), x["offset"]))
    string_inventory = interesting_string_inventory(pe, pairs, tables)

    after = sha256_file(exe)
    if before != after:
        raise RuntimeError("GoW.exe hash changed during read-only scan")

    report = {
        "schema": 1,
        "scan_kind": "read_only_exhaustive_direct_lua_registration_enumeration",
        "scope_contract": (
            "Exhaustive for direct absolute name-pointer + executable function-pointer "
            "records at 8-byte alignment and strides 16,24,32,40,48,56,64; does not "
            "claim all engine binding mechanisms use this shape."
        ),
        "game_root": str(root),
        "exe": str(exe),
        "exe_sha256": before,
        "image_base": f"0x{pe.image_base:X}",
        "strides_scanned": list(STRIDES),
        "direct_name_function_pairs": len(pairs),
        "candidate_table_count": len(tables),
        "canonical_table_count": len(canonical),
        "interesting_registration_count": len(interesting_entries),
        "interesting_registrations": interesting_entries,
        "candidate_tables": tables,
        "canonical_tables": canonical,
        "interesting_string_inventory": string_inventory,
        "safety": {
            "source_hashes_unchanged": True,
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "scan_only": True,
        },
    }

    lines = [
        "Completionist Map - exhaustive direct native Lua registration enumeration",
        f"exe={exe}",
        f"sha256={before}",
        f"direct_name_function_pairs={len(pairs)}",
        f"candidate_tables={len(tables)}",
        f"canonical_tables={len(canonical)}",
        f"interesting_registrations={len(interesting_entries)}",
        "scope=direct absolute name-pointer + executable function-pointer tables; not all possible binding mechanisms",
        "source_hashes_unchanged=true active_save_opened=false game_written=false save_or_progression_written=false game_launched=false",
        "",
        "=== INTERESTING REGISTERED METHODS ===",
    ]
    if not interesting_entries:
        lines.append("none")
    else:
        for e in interesting_entries:
            lines.append(
                f"{e['name']} table={e['table_start']} stride={e['stride']} "
                f"entry={e['offset_hex']} fn={e['function_rva']}"
            )

    lines.extend(["", "=== CANONICAL TABLES ==="])
    for index, table in enumerate(canonical, 1):
        names = " | ".join(entry["name"] for entry in table["entries"])
        lines.append(
            f"{index}: section={table['section']} stride={table['stride']} "
            f"start={table['start_offset_hex']} entries={table['entry_count']} names={names}"
        )

    lines.extend(["", "=== INTERESTING STRINGS WITHOUT CONTIGUOUS TABLE ENTRY ==="])
    orphan_rows = [row for row in string_inventory if not row["contiguous_table_entry_xrefs"]]
    if not orphan_rows:
        lines.append("none")
    else:
        for row in orphan_rows:
            lines.append(
                f"{row['name']} string_rva={row['string_rva']} "
                f"absolute_xrefs={','.join(row['absolute_xrefs']) or '-'} "
                f"direct_pair_xrefs={','.join(row['direct_name_function_pair_xrefs']) or '-'}"
            )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_text.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "EXHAUSTIVE_LUA_REGISTRATION_SCAN_COMPLETED "
        f"pairs={len(pairs)} tables={len(tables)} canonical={len(canonical)} "
        f"interesting={len(interesting_entries)}"
    )
    print("source_hashes_unchanged=true active_save_opened=false game_written=false save_or_progression_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
