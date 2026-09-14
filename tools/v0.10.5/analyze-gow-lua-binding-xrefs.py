"""Read-only PE/xref analysis of God of War Lua-facing native binding names.

The earlier string scan proved that GoW.exe contains names such as game.SubObject,
SoftSave and LoadSubObject, but a string alone does not prove that it is a callable
Lua API. This helper distinguishes likely Lua registration-table entries from mere
callback/event/debug strings by parsing the PE image and tracing references to exact
binding names.

For each target string it records:
  * exact string VA/RVA/file offsets,
  * absolute 64-bit and 32-bit-RVA data references,
  * RIP-relative references from executable sections,
  * likely LuaL_Reg-style {name pointer, native function pointer} pairs,
  * contiguous 16-byte registration blocks around any such pair.

The scan is strictly read-only. It hashes GoW.exe before and after, never launches the
game, and never opens the user's save directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Optional

TARGETS = (
    "SubObject",
    "Sleep",
    "Wake",
    "SetRetainOnCheckpoint",
    "SetForgetOnCheckpoint",
    "SoftSave",
    "SetEntityZoneHandler",
    "LoadSubObject",
    "DebugGetSubObjectEnvironmentRoot",
    "CurrentlyExecutingSubObject",
    "SerializeHook",
    "GetAvailableWads",
    "GetPermWad",
    "GetUIWad",
    "FindGameObjects",
    "FindSingleGameObject",
    "FindGameObject",
    "GetGameObject",
    "IterateGameObjects",
)

IMAGE_SCN_MEM_EXECUTE = 0x20000000
MAX_XREFS_PER_KIND = 512
MAX_REG_BLOCK_ENTRIES = 128
MAX_ASCII = 120


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PEImage:
    def __init__(self, path: Path, data: bytes):
        self.path = path
        self.data = data
        if len(data) < 0x100 or data[:2] != b"MZ":
            raise RuntimeError("GoW.exe is not an MZ/PE image")
        self.pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if self.pe_off + 24 > len(data) or data[self.pe_off:self.pe_off + 4] != b"PE\0\0":
            raise RuntimeError("Invalid PE signature")
        self.num_sections = struct.unpack_from("<H", data, self.pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, self.pe_off + 20)[0]
        opt = self.pe_off + 24
        magic = struct.unpack_from("<H", data, opt)[0]
        if magic != 0x20B:
            raise RuntimeError(f"Expected PE32+ executable, optional-header magic={magic:#x}")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", data, opt + 60)[0]
        sec_off = opt + size_opt
        self.sections: list[dict] = []
        for i in range(self.num_sections):
            off = sec_off + i * 40
            if off + 40 > len(data):
                raise RuntimeError("Truncated PE section table")
            name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from("<IIII", data, off + 8)
            characteristics = struct.unpack_from("<I", data, off + 36)[0]
            self.sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
                "characteristics": characteristics,
                "executable": bool(characteristics & IMAGE_SCN_MEM_EXECUTE),
            })

    def section_for_file(self, offset: int) -> Optional[dict]:
        if 0 <= offset < self.size_of_headers:
            return {"name": "<headers>", "executable": False, "virtual_address": 0,
                    "raw_ptr": 0, "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers}
        for sec in self.sections:
            if sec["raw_ptr"] <= offset < sec["raw_ptr"] + sec["raw_size"]:
                return sec
        return None

    def section_for_rva(self, rva: int) -> Optional[dict]:
        if 0 <= rva < self.size_of_headers:
            return {"name": "<headers>", "executable": False, "virtual_address": 0,
                    "raw_ptr": 0, "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers}
        for sec in self.sections:
            span = max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + span:
                return sec
        return None

    def file_to_rva(self, offset: int) -> Optional[int]:
        sec = self.section_for_file(offset)
        if sec is None:
            return None
        return sec["virtual_address"] + (offset - sec["raw_ptr"])

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

    def va_to_rva(self, value: int) -> Optional[int]:
        if self.image_base <= value < self.image_base + self.size_of_image:
            return value - self.image_base
        return None

    def classify_pointer(self, value: int) -> dict:
        rva = self.va_to_rva(value)
        encoding = "va"
        if rva is None and 0 <= value < self.size_of_image and self.section_for_rva(value) is not None:
            rva = value
            encoding = "rva"
        if rva is None:
            return {"kind": "scalar", "value": value, "hex": hex(value)}
        sec = self.section_for_rva(rva)
        off = self.rva_to_file(rva)
        out = {
            "kind": "code" if sec and sec.get("executable") else "data",
            "encoding": encoding,
            "value": value,
            "hex": hex(value),
            "rva": rva,
            "rva_hex": hex(rva),
            "section": sec["name"] if sec else None,
            "file_offset": off,
            "file_offset_hex": hex(off) if off is not None else None,
        }
        if off is not None:
            s = self.ascii_at(off)
            if s is not None:
                out["kind"] = "string"
                out["string"] = s
        return out

    def ascii_at(self, offset: int) -> Optional[str]:
        if offset is None or offset < 0 or offset >= len(self.data):
            return None
        end = offset
        while end < len(self.data) and end - offset < MAX_ASCII:
            b = self.data[end]
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            end += 1
        if end == offset or end >= len(self.data) or self.data[end] != 0:
            return None
        return self.data[offset:end].decode("ascii", "replace")


def find_all(data: bytes, needle: bytes, cap: int = MAX_XREFS_PER_KIND) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < cap:
        pos = data.find(needle, start)
        if pos < 0:
            break
        out.append(pos)
        start = pos + 1
    return out


def describe_file_offset(pe: PEImage, off: int) -> dict:
    rva = pe.file_to_rva(off)
    sec = pe.section_for_file(off)
    return {
        "file_offset": off,
        "file_offset_hex": hex(off),
        "rva": rva,
        "rva_hex": hex(rva) if rva is not None else None,
        "va": pe.image_base + rva if rva is not None else None,
        "va_hex": hex(pe.image_base + rva) if rva is not None else None,
        "section": sec["name"] if sec else None,
    }


def qword_context(pe: PEImage, xref_off: int, radius_qwords: int = 5) -> list[dict]:
    base = max(0, xref_off - radius_qwords * 8)
    base -= base % 8
    end = min(len(pe.data), xref_off + (radius_qwords + 1) * 8)
    out: list[dict] = []
    for off in range(base, end - 7, 8):
        value = struct.unpack_from("<Q", pe.data, off)[0]
        rec = {"at": describe_file_offset(pe, off), "pointer": pe.classify_pointer(value)}
        if off == xref_off:
            rec["is_xref"] = True
        out.append(rec)
    return out


def is_reg_pair_at(pe: PEImage, xref_off: int, expected_string_va: int) -> Optional[dict]:
    if xref_off < 0 or xref_off + 16 > len(pe.data):
        return None
    name_ptr, fn_ptr = struct.unpack_from("<QQ", pe.data, xref_off)
    if name_ptr != expected_string_va:
        return None
    fn = pe.classify_pointer(fn_ptr)
    if fn.get("kind") != "code":
        return None
    sec = pe.section_for_file(xref_off)
    if sec is not None and sec.get("executable"):
        return None
    return {
        "pair_offset": xref_off,
        "pair_offset_hex": hex(xref_off),
        "pair_section": sec["name"] if sec else None,
        "name_pointer": hex(name_ptr),
        "function": fn,
    }


def decode_reg_entry(pe: PEImage, off: int) -> Optional[dict]:
    if off < 0 or off + 16 > len(pe.data):
        return None
    name_ptr, fn_ptr = struct.unpack_from("<QQ", pe.data, off)
    name_rva = pe.va_to_rva(name_ptr)
    fn_rva = pe.va_to_rva(fn_ptr)
    if name_rva is None or fn_rva is None:
        return None
    name_off = pe.rva_to_file(name_rva)
    if name_off is None:
        return None
    name = pe.ascii_at(name_off)
    if not name or len(name) > 96:
        return None
    fn_sec = pe.section_for_rva(fn_rva)
    if fn_sec is None or not fn_sec.get("executable"):
        return None
    return {
        "offset": off,
        "offset_hex": hex(off),
        "name": name,
        "name_va": hex(name_ptr),
        "function_va": hex(fn_ptr),
        "function_rva": hex(fn_rva),
        "function_section": fn_sec["name"],
    }


def walk_reg_block(pe: PEImage, anchor: int) -> list[dict]:
    start = anchor
    count = 0
    while count < MAX_REG_BLOCK_ENTRIES:
        prev = start - 16
        if decode_reg_entry(pe, prev) is None:
            break
        start = prev
        count += 1
    entries: list[dict] = []
    off = start
    while len(entries) < MAX_REG_BLOCK_ENTRIES:
        entry = decode_reg_entry(pe, off)
        if entry is None:
            break
        entries.append(entry)
        off += 16
    return entries


def riprel_xrefs(pe: PEImage, target_va: int) -> list[dict]:
    out: list[dict] = []
    for sec in pe.sections:
        if not sec.get("executable") or sec["raw_size"] < 4:
            continue
        raw = sec["raw_ptr"]
        raw_end = min(len(pe.data), raw + sec["raw_size"])
        # A RIP-relative disp32 ends at the instruction's next RIP for common LEA/MOV
        # forms. Scan every possible disp32 and retain only exact target resolutions.
        for disp_off in range(raw, raw_end - 3):
            disp = struct.unpack_from("<i", pe.data, disp_off)[0]
            disp_rva = sec["virtual_address"] + (disp_off - raw)
            next_va = pe.image_base + disp_rva + 4
            if next_va + disp != target_va:
                continue
            lo = max(raw, disp_off - 4)
            hi = min(raw_end, disp_off + 8)
            out.append({
                "disp_offset": disp_off,
                "disp_offset_hex": hex(disp_off),
                "disp_rva": hex(disp_rva),
                "section": sec["name"],
                "preceding_bytes_hex": pe.data[lo:disp_off].hex(),
                "window_hex": pe.data[lo:hi].hex(),
            })
            if len(out) >= MAX_XREFS_PER_KIND:
                return out
    return out


def analyze_target(pe: PEImage, name: str) -> dict:
    occurrences = find_all(pe.data, name.encode("ascii") + b"\0")
    out_occ: list[dict] = []
    all_blocks: dict[tuple[tuple[str, str], ...], list[dict]] = {}
    for string_off in occurrences:
        loc = describe_file_offset(pe, string_off)
        rva = loc["rva"]
        if rva is None:
            continue
        va = pe.image_base + rva
        abs_refs = find_all(pe.data, struct.pack("<Q", va))
        rva_refs = find_all(pe.data, struct.pack("<I", rva & 0xFFFFFFFF))
        reg_pairs: list[dict] = []
        for xref in abs_refs:
            pair = is_reg_pair_at(pe, xref, va)
            if pair is None:
                continue
            pair["qword_context"] = qword_context(pe, xref)
            reg_pairs.append(pair)
            block = walk_reg_block(pe, xref)
            key = tuple((e["name"], e["function_rva"]) for e in block)
            if key:
                all_blocks[key] = block

        out_occ.append({
            "string": loc,
            "absolute_qword_xrefs": [describe_file_offset(pe, x) for x in abs_refs],
            "rva_dword_xrefs": [describe_file_offset(pe, x) for x in rva_refs],
            "rip_relative_code_xrefs": riprel_xrefs(pe, va),
            "likely_registration_pairs": reg_pairs,
        })
    return {
        "name": name,
        "occurrence_count": len(out_occ),
        "occurrences": out_occ,
        "registration_blocks": list(all_blocks.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.expanduser().resolve()
    exe = (game_root / "GoW.exe").resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")

    before = sha256_file(exe)
    data = exe.read_bytes()
    pe = PEImage(exe, data)
    targets = [analyze_target(pe, name) for name in TARGETS]
    after = sha256_file(exe)
    if before != after:
        raise RuntimeError("GoW.exe hash changed during read-only scan")

    unique_blocks: dict[tuple[tuple[str, str], ...], list[dict]] = {}
    for target in targets:
        for block in target["registration_blocks"]:
            key = tuple((e["name"], e["function_rva"]) for e in block)
            if key:
                unique_blocks[key] = block

    report = {
        "schema": 1,
        "scan_kind": "read_only_gow_lua_binding_pe_xref_analysis",
        "game_root": str(game_root),
        "exe": str(exe),
        "exe_sha256": before,
        "image_base": hex(pe.image_base),
        "size_of_image": pe.size_of_image,
        "sections": pe.sections,
        "targets": targets,
        "unique_registration_blocks": list(unique_blocks.values()),
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
        "Completionist Map - GoW native Lua binding PE/xref analysis",
        f"exe={exe}",
        f"sha256={before}",
        f"image_base={pe.image_base:#x} size_of_image={pe.size_of_image}",
        "source_hashes_unchanged=true active_save_opened=false game_launched=false",
        "",
    ]
    for target in targets:
        abs_count = sum(len(o["absolute_qword_xrefs"]) for o in target["occurrences"])
        rva_count = sum(len(o["rva_dword_xrefs"]) for o in target["occurrences"])
        rip_count = sum(len(o["rip_relative_code_xrefs"]) for o in target["occurrences"])
        pair_count = sum(len(o["likely_registration_pairs"]) for o in target["occurrences"])
        lines.append(
            f"{target['name']}: strings={target['occurrence_count']} abs64={abs_count} "
            f"rva32={rva_count} riprel={rip_count} likely_reg_pairs={pair_count}"
        )
        for occ in target["occurrences"]:
            s = occ["string"]
            lines.append(
                f"  string file={s['file_offset_hex']} rva={s['rva_hex']} va={s['va_hex']} section={s['section']}"
            )
            for pair in occ["likely_registration_pairs"]:
                fn = pair["function"]
                lines.append(
                    f"    REG_PAIR table={pair['pair_offset_hex']} section={pair['pair_section']} "
                    f"fn_rva={fn.get('rva_hex')} fn_section={fn.get('section')}"
                )
        for block in target["registration_blocks"]:
            lines.append("  REG_BLOCK: " + " | ".join(f"{e['name']}->{e['function_rva']}" for e in block))

    lines.append("")
    lines.append(f"unique_registration_blocks={len(unique_blocks)}")
    for i, block in enumerate(unique_blocks.values(), 1):
        lines.append(f"BLOCK {i}: " + " | ".join(f"{e['name']}->{e['function_rva']}" for e in block))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    pairs = sum(
        len(o["likely_registration_pairs"])
        for t in targets
        for o in t["occurrences"]
    )
    print(f"GOW_LUA_BINDING_XREF_SCAN_PASSED targets={len(targets)} likely_reg_pairs={pairs} blocks={len(unique_blocks)}")
    print("source_hashes_unchanged=true active_save_opened=false game_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
