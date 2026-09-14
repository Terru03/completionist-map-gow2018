"""Read-only decoder for selected GoW native binding descriptor records.

The exhaustive registration scan proved direct name-pointer + code-pointer pairs, but
some 32-byte records may carry additional executable callbacks or metadata in qwords
2/3. This probe finds selected names directly in GoW.exe, dumps the complete descriptor
qwords, classifies each value, and reports adjacent records for context.

Safety: reads GoW.exe only; does not open saves, launch the game, or write game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Optional

TARGETS = {
    "GetCounter",
    "GetCounterChild",
    "GetCounterChildrenCount",
    "GetCounterName",
    "GetRefBool",
    "GetRefFloat",
    "GetRefInt",
    "GetRefString",
    "GetRegionHash",
    "EntityBool",
    "MarkerID",
    "ResolveGameObject",
}

BASELINES = {"GetVariable"}
EXPECTED_EXE_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
MAX_ASCII = 160


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PE:
    def __init__(self, data: bytes):
        self.data = data
        if data[:2] != b"MZ":
            raise RuntimeError("GoW.exe is not an MZ image")
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_off:pe_off + 4] != b"PE\0\0":
            raise RuntimeError("Invalid PE signature")
        nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, pe_off + 20)[0]
        opt = pe_off + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("Expected PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", data, opt + 60)[0]
        sec_off = opt + size_opt
        self.sections = []
        for i in range(nsec):
            off = sec_off + i * 40
            name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from("<IIII", data, off + 8)
            characteristics = struct.unpack_from("<I", data, off + 36)[0]
            self.sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
                "executable": bool(characteristics & 0x20000000),
            })

    def section_for_rva(self, rva: int) -> Optional[dict]:
        if 0 <= rva < self.size_of_headers:
            return {"name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                    "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                    "executable": False}
        for sec in self.sections:
            span = max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + span:
                return sec
        return None

    def section_for_file(self, off: int) -> Optional[dict]:
        if 0 <= off < self.size_of_headers:
            return {"name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                    "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                    "executable": False}
        for sec in self.sections:
            if sec["raw_ptr"] <= off < sec["raw_ptr"] + sec["raw_size"]:
                return sec
        return None

    def va_to_rva(self, va: int) -> Optional[int]:
        if self.image_base <= va < self.image_base + self.size_of_image:
            return va - self.image_base
        return None

    def rva_to_file(self, rva: int) -> Optional[int]:
        if 0 <= rva < self.size_of_headers:
            return rva if rva < len(self.data) else None
        sec = self.section_for_rva(rva)
        if sec is None:
            return None
        delta = rva - sec["virtual_address"]
        if delta < 0 or delta >= sec["raw_size"]:
            return None
        off = sec["raw_ptr"] + delta
        return off if off < len(self.data) else None

    def ascii_at_file(self, off: int) -> Optional[str]:
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
        return self.data[off:end].decode("ascii", "replace")

    def classify(self, value: int) -> dict:
        out = {"value": value, "hex": f"0x{value:X}"}
        rva = self.va_to_rva(value)
        if rva is None:
            out["kind"] = "zero" if value == 0 else "scalar"
            return out
        sec = self.section_for_rva(rva)
        off = self.rva_to_file(rva)
        out.update({
            "rva": f"0x{rva:X}",
            "section": sec["name"] if sec else None,
            "file_offset": f"0x{off:X}" if off is not None else None,
        })
        if sec and sec.get("executable"):
            out["kind"] = "code"
        else:
            text = self.ascii_at_file(off) if off is not None else None
            if text:
                out["kind"] = "string"
                out["string"] = text
            else:
                out["kind"] = "data"
        return out


def find_descriptor_candidates(pe: PE, wanted: set[str]) -> dict[str, list[int]]:
    string_vas: dict[int, str] = {}
    for sec in pe.sections:
        if sec["raw_size"] <= 0:
            continue
        start = sec["raw_ptr"]
        end = min(len(pe.data), start + sec["raw_size"])
        blob = pe.data[start:end]
        for name in wanted:
            needle = name.encode("ascii") + b"\0"
            pos = blob.find(needle)
            while pos >= 0:
                off = start + pos
                rva = sec["virtual_address"] + pos
                string_vas[pe.image_base + rva] = name
                pos = blob.find(needle, pos + 1)

    hits: dict[str, list[int]] = {name: [] for name in wanted}
    for off in range(0, len(pe.data) - 15, 8):
        name_va, second = struct.unpack_from("<QQ", pe.data, off)
        name = string_vas.get(name_va)
        if name is None:
            continue
        second_info = pe.classify(second)
        if second_info.get("kind") == "code":
            hits[name].append(off)
    return hits


def record_qwords(pe: PE, off: int, stride: int) -> list[dict]:
    if off + stride > len(pe.data):
        return []
    rows = []
    for rel in range(0, stride, 8):
        value = struct.unpack_from("<Q", pe.data, off + rel)[0]
        rows.append({"relative": rel, "relative_hex": f"+0x{rel:X}", **pe.classify(value)})
    return rows


def adjacent_name(pe: PE, off: int) -> Optional[str]:
    if off < 0 or off + 8 > len(pe.data):
        return None
    value = struct.unpack_from("<Q", pe.data, off)[0]
    info = pe.classify(value)
    return info.get("string") if info.get("kind") == "string" else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.expanduser().resolve()
    exe = game_root / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")

    before = sha256_file(exe)
    if before != EXPECTED_EXE_SHA256:
        raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    raw = exe.read_bytes()
    pe = PE(raw)

    wanted = TARGETS | BASELINES
    hits = find_descriptor_candidates(pe, wanted)
    entries = []
    text = []

    for name in sorted(wanted):
        offsets = hits.get(name, [])
        text.append(f"=== {name} candidates={len(offsets)} ===")
        for off in offsets:
            # Use both layouts: GetVariable belongs to a 24-byte table, most target
            # game/UI methods belong to the 32-byte table. Showing both prevents us
            # from assuming the record shape before the evidence proves it.
            layouts = {}
            for stride in (24, 32):
                layouts[str(stride)] = {
                    "qwords": record_qwords(pe, off, stride),
                    "prev_name": adjacent_name(pe, off - stride),
                    "next_name": adjacent_name(pe, off + stride),
                }
            item = {
                "name": name,
                "record_offset": f"0x{off:X}",
                "section": (pe.section_for_file(off) or {}).get("name"),
                "layouts": layouts,
            }
            entries.append(item)
            text.append(f"record=0x{off:X} section={item['section']}")
            for stride in (24, 32):
                lay = layouts[str(stride)]
                text.append(f"  stride={stride} prev={lay['prev_name']!r} next={lay['next_name']!r}")
                for q in lay["qwords"]:
                    extra = ""
                    if q.get("kind") == "string":
                        extra = f" string={q.get('string')!r}"
                    elif q.get("kind") == "code":
                        extra = f" rva={q.get('rva')}"
                    elif q.get("section"):
                        extra = f" section={q.get('section')}"
                    text.append(f"    {q['relative_hex']}: {q['hex']} {q['kind']}{extra}")
        text.append("")

    after = sha256_file(exe)
    if after != before:
        raise RuntimeError("GoW.exe hash changed during read-only descriptor scan")

    output = {
        "schema": 1,
        "scan_kind": "native_binding_descriptor_layout",
        "exe": str(exe),
        "exe_sha256": before,
        "targets": sorted(TARGETS),
        "baselines": sorted(BASELINES),
        "entries": entries,
        "safety": {
            "scan_only": True,
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "source_hash_unchanged": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(text) + "\n", encoding="utf-8")
    print(f"NATIVE_BINDING_DESCRIPTOR_SCAN_COMPLETED entries={len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
