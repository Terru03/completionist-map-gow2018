"""Read-only inspection of the native LuaCompass::ShowMarker type validator.

The packed CompletionistRaven experiment proved that the request is rejected
synchronously with:

    trying to set invalid type '%s' on compass marker '%s'

A source/string scan then located that exact format string inside the pinned
GoW.exe, adjacent to the exported Lua Compass binding names. Earlier v0.10.3
static analysis pinned LuaCompass::ShowMarker at RVA 0x94FF80, its marker lookup
near 0x94FFF8 and a CompassIconClass type-id 0x11E check near 0x95009E.

This probe automates the next read-only step. It parses the PE, resolves x64
runtime-function bounds from .pdata, inspects the ShowMarker function and its
nearby callees, records references to the invalid-type string, and records the
0x11E immediate/check neighborhood. If python-capstone is already installed it
also emits decoded instructions; otherwise a standard-library RIP/call scanner
still produces deterministic evidence. Nothing in the game directory is
written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Iterable

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SHOW_RVA = 0x94FF80
PRIOR_MARKER_LOOKUP_SITE = 0x94FFF8
PRIOR_TYPE_CHECK_SITE = 0x95009E
COMPASS_CLASS_TYPE_ID = 0x11E
ERROR_TEXT = b"trying to set invalid type '%s' on compass marker '%s'"
RESULT = "READ_ONLY_COMPASS_SHOWMARKER_NATIVE_VALIDATION"


class PE:
    def __init__(self, raw: bytes):
        self.raw = raw
        if raw[:2] != b"MZ":
            raise ValueError("not an MZ executable")
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[pe:pe + 4] != b"PE\0\0":
            raise ValueError("missing PE signature")
        count = struct.unpack_from("<H", raw, pe + 6)[0]
        optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
        optional = pe + 24
        magic = struct.unpack_from("<H", raw, optional)[0]
        if magic != 0x20B:
            raise ValueError(f"expected PE32+, got optional magic {magic:#x}")
        self.image_base = struct.unpack_from("<Q", raw, optional + 24)[0]
        if self.image_base != IMAGE_BASE:
            raise ValueError(f"unexpected preferred image base {self.image_base:#x}")
        self.sections = []
        table = optional + optional_size
        for i in range(count):
            o = table + i * 40
            name = raw[o:o + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, rva, raw_size, raw_ptr = struct.unpack_from("<IIII", raw, o + 8)
            self.sections.append({
                "name": name,
                "rva": rva,
                "virtual_size": virtual_size,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
            })

    def section(self, name: str) -> dict:
        rows = [s for s in self.sections if s["name"] == name]
        if len(rows) != 1:
            raise ValueError(f"expected one {name} section, found {len(rows)}")
        return rows[0]

    def rva_to_offset(self, rva: int) -> int:
        for s in self.sections:
            span = max(s["virtual_size"], s["raw_size"])
            if s["rva"] <= rva < s["rva"] + span:
                delta = rva - s["rva"]
                if delta >= s["raw_size"]:
                    raise ValueError(f"RVA {rva:#x} is not file-backed")
                return s["raw_ptr"] + delta
        raise ValueError(f"RVA outside sections: {rva:#x}")

    def offset_to_rva(self, offset: int) -> int:
        for s in self.sections:
            if s["raw_ptr"] <= offset < s["raw_ptr"] + s["raw_size"]:
                return s["rva"] + offset - s["raw_ptr"]
        raise ValueError(f"file offset outside sections: {offset:#x}")

    def read_rva(self, rva: int, size: int) -> bytes:
        off = self.rva_to_offset(rva)
        return self.raw[off:off + size]

    def ascii_at_rva(self, rva: int, max_len: int = 240) -> str | None:
        try:
            off = self.rva_to_offset(rva)
        except ValueError:
            return None
        end = min(len(self.raw), off + max_len)
        chunk = self.raw[off:end]
        nul = chunk.find(b"\0")
        if nul >= 0:
            chunk = chunk[:nul]
        if len(chunk) < 4 or any(b < 0x20 or b > 0x7E for b in chunk):
            return None
        try:
            return chunk.decode("ascii")
        except UnicodeDecodeError:
            return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_runtime_functions(pe: PE) -> list[dict]:
    pdata = pe.section(".pdata")
    payload = pe.raw[pdata["raw_ptr"]:pdata["raw_ptr"] + pdata["raw_size"]]
    rows = []
    for off in range(0, len(payload) - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", payload, off)
        if begin == 0 and end == 0 and unwind == 0:
            continue
        if begin >= end:
            continue
        rows.append({"begin": begin, "end": end, "unwind": unwind})
    rows.sort(key=lambda r: (r["begin"], r["end"]))
    return rows


def containing_function(rows: list[dict], rva: int) -> dict | None:
    # .pdata entries are sorted. Linear scan is still tiny relative to the EXE.
    best = None
    for row in rows:
        if row["begin"] > rva:
            break
        if row["begin"] <= rva < row["end"]:
            best = row
    return best


def hex_window(pe: PE, center_rva: int, radius: int = 64) -> dict:
    start = max(0, center_rva - radius)
    end = center_rva + radius
    try:
        data = pe.read_rva(start, end - start)
    except ValueError:
        data = b""
    return {
        "start_rva": f"0x{start:X}",
        "end_rva": f"0x{start + len(data):X}",
        "hex": data.hex().upper(),
    }


def binding_strings(raw: bytes, center: int, radius: int = 640) -> list[dict]:
    lo = max(0, center - radius)
    hi = min(len(raw), center + radius)
    out = []
    for m in re.finditer(rb"[ -~]{4,}\x00", raw[lo:hi]):
        value = m.group(0)[:-1].decode("ascii", "replace")
        out.append({"file_offset": f"0x{lo + m.start():X}", "text": value})
    return out


def heuristic_rip_refs(pe: PE, begin: int, end: int) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    rows = []
    for i in range(len(data) - 7):
        prefix_len = 1 if 0x40 <= data[i] <= 0x4F else 0
        op_i = i + prefix_len
        if op_i + 6 > len(data):
            continue
        opcode = data[op_i]
        if opcode not in (0x8D, 0x8B, 0x89):
            continue
        modrm = data[op_i + 1]
        if (modrm & 0xC7) != 0x05:  # mod=00, r/m=101 => RIP relative
            continue
        disp = struct.unpack_from("<i", data, op_i + 2)[0]
        size = prefix_len + 6
        insn_rva = begin + i
        target = insn_rva + size + disp
        text = pe.ascii_at_rva(target)
        if text is None:
            continue
        rows.append({
            "instruction_rva": f"0x{insn_rva:X}",
            "target_rva": f"0x{target:X}",
            "opcode": f"0x{opcode:02X}",
            "string": text,
        })
    return rows


def heuristic_calls(pe: PE, begin: int, end: int, funcs: list[dict]) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    text = pe.section(".text")
    text_lo = text["rva"]
    text_hi = text_lo + max(text["virtual_size"], text["raw_size"])
    rows = []
    for i in range(len(data) - 5):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = begin + i
        target = site + 5 + rel
        if not (text_lo <= target < text_hi):
            continue
        fn = containing_function(funcs, target)
        rows.append({
            "site_rva": f"0x{site:X}",
            "target_rva": f"0x{target:X}",
            "target_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"
            },
        })
    return rows


def parse_consts(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    pat = re.compile(r'^\s*consts\.(COMPASS_MARKER_TYPE_[A-Z0-9_]+)\s*=\s*"([^"]+)"', re.M)
    for m in pat.finditer(text):
        rows.append({"constant": m.group(1), "value": m.group(2)})
    return rows


def capstone_analysis(pe: PE, begin: int, end: int, funcs: list[dict], error_rva: int) -> dict:
    try:
        import capstone  # type: ignore
        from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP  # type: ignore
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = pe.read_rva(begin, end - begin)
    insns = list(md.disasm(data, IMAGE_BASE + begin))
    decoded = []
    string_refs = []
    direct_calls = []
    type_imm = []
    error_refs = []
    for insn in insns:
        rva = insn.address - IMAGE_BASE
        decoded.append({"rva": f"0x{rva:X}", "bytes": insn.bytes.hex().upper(),
                        "mnemonic": insn.mnemonic, "op_str": insn.op_str})
        for op in insn.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                target = rva + insn.size + op.mem.disp
                text = pe.ascii_at_rva(target)
                if text is not None:
                    row = {"instruction_rva": f"0x{rva:X}", "target_rva": f"0x{target:X}",
                           "mnemonic": insn.mnemonic, "op_str": insn.op_str, "string": text}
                    string_refs.append(row)
                    if target == error_rva:
                        error_refs.append(row)
            if op.type == X86_OP_IMM and int(op.imm) == COMPASS_CLASS_TYPE_ID:
                type_imm.append({"rva": f"0x{rva:X}", "mnemonic": insn.mnemonic,
                                 "op_str": insn.op_str, "bytes": insn.bytes.hex().upper()})
        if insn.mnemonic == "call" and insn.operands and insn.operands[0].type == X86_OP_IMM:
            target = int(insn.operands[0].imm) - IMAGE_BASE
            fn = containing_function(funcs, target)
            direct_calls.append({
                "site_rva": f"0x{rva:X}",
                "target_rva": f"0x{target:X}",
                "target_function": None if fn is None else {
                    "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"
                },
            })

    around_type = [row for row in decoded
                   if PRIOR_TYPE_CHECK_SITE - 0x60 <= int(row["rva"], 16) <= PRIOR_TYPE_CHECK_SITE + 0x80]
    around_lookup = [row for row in decoded
                     if PRIOR_MARKER_LOOKUP_SITE - 0x40 <= int(row["rva"], 16) <= PRIOR_MARKER_LOOKUP_SITE + 0x40]

    # A direct call immediately after loading 0x11E is the strongest candidate
    # for the authored CompassIconClass lookup. Keep the nearest calls explicit.
    near_type_calls = [row for row in direct_calls
                       if PRIOR_TYPE_CHECK_SITE - 0x80 <= int(row["site_rva"], 16) <= PRIOR_TYPE_CHECK_SITE + 0x80]

    callee_summaries = []
    seen = set()
    for row in near_type_calls:
        fn = row["target_function"]
        if not fn:
            continue
        key = (fn["begin"], fn["end"])
        if key in seen:
            continue
        seen.add(key)
        fb, fe = int(fn["begin"], 16), int(fn["end"], 16)
        refs = heuristic_rip_refs(pe, fb, min(fe, fb + 0x800))
        callee_summaries.append({
            "begin": fn["begin"], "end": fn["end"],
            "bytes": fe - fb,
            "ascii_rip_refs_first_0x800": refs[:80],
            "hex_head": pe.read_rva(fb, min(fe - fb, 160)).hex().upper(),
        })

    return {
        "available": True,
        "version": getattr(capstone, "__version__", "unknown"),
        "instruction_count": len(insns),
        "decoded_instructions": decoded,
        "string_refs": string_refs,
        "error_string_refs": error_refs,
        "type_0x11e_immediates": type_imm,
        "direct_calls": direct_calls,
        "near_type_check_calls": near_type_calls,
        "around_prior_marker_lookup_site": around_lookup,
        "around_prior_type_check_site": around_type,
        "near_type_callee_summaries": callee_summaries,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    exe = game / "GoW.exe"
    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("report must stay outside the game directory")
    if not exe.is_file():
        raise FileNotFoundError(exe)
    digest = sha256(exe)
    if digest != EXPECTED_EXE:
        raise ValueError(f"GoW.exe hash differs from pinned build: {digest}")

    raw = exe.read_bytes()
    pe = PE(raw)
    funcs = parse_runtime_functions(pe)
    show_fn = containing_function(funcs, SHOW_RVA)
    if show_fn is None:
        raise ValueError(".pdata did not contain prior ShowMarker RVA")

    error_offsets = []
    pos = 0
    while True:
        pos = raw.find(ERROR_TEXT, pos)
        if pos < 0:
            break
        error_offsets.append(pos)
        pos += len(ERROR_TEXT)
    if len(error_offsets) != 1:
        raise ValueError(f"expected one invalid-type format string, found {len(error_offsets)}")
    error_offset = error_offsets[0]
    error_rva = pe.offset_to_rva(error_offset)

    begin, end = show_fn["begin"], show_fn["end"]
    if not (begin <= PRIOR_MARKER_LOOKUP_SITE < end and begin <= PRIOR_TYPE_CHECK_SITE < end):
        raise ValueError(
            f"prior lookup/type-check anchors are not both inside ShowMarker function {begin:#x}-{end:#x}"
        )

    class_imm_offsets = []
    fn_data = pe.read_rva(begin, end - begin)
    needle = struct.pack("<I", COMPASS_CLASS_TYPE_ID)
    at = 0
    while True:
        i = fn_data.find(needle, at)
        if i < 0:
            break
        class_imm_offsets.append(begin + i)
        at = i + 1

    heuristic_refs = heuristic_rip_refs(pe, begin, end)
    heuristic_error_refs = [r for r in heuristic_refs if int(r["target_rva"], 16) == error_rva]
    heuristic_direct_calls = heuristic_calls(pe, begin, end, funcs)
    cs = capstone_analysis(pe, begin, end, funcs, error_rva)

    if cs.get("available"):
        error_ref_count = len(cs.get("error_string_refs", []))
        type_imm_count = len(cs.get("type_0x11e_immediates", []))
    else:
        error_ref_count = len(heuristic_error_refs)
        type_imm_count = len(class_imm_offsets)

    conclusion = "NATIVE_SHOWMARKER_VALIDATION_FUNCTION_LOCATED"
    if error_ref_count and type_imm_count:
        conclusion = "NATIVE_SHOWMARKER_OWNS_INVALID_TYPE_AND_0X11E_VALIDATION"

    consts_path = game / "mods/lua_source/gameart/ui/scripts/consts/consts.lua"
    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "preferred_image_base": f"0x{pe.image_base:X}",
        "prior_static_anchors": {
            "LuaCompass_ShowMarker_rva": f"0x{SHOW_RVA:X}",
            "marker_lookup_site_rva": f"0x{PRIOR_MARKER_LOOKUP_SITE:X}",
            "CompassIconClass_0x11E_check_site_rva": f"0x{PRIOR_TYPE_CHECK_SITE:X}",
        },
        "showmarker_runtime_function": {
            "begin_rva": f"0x{begin:X}",
            "end_rva": f"0x{end:X}",
            "bytes": end - begin,
            "unwind_rva": f"0x{show_fn['unwind']:X}",
        },
        "invalid_type_string": {
            "text": ERROR_TEXT.decode("ascii"),
            "file_offset": f"0x{error_offset:X}",
            "rva": f"0x{error_rva:X}",
            "binding_block_strings": binding_strings(raw, error_offset),
        },
        "compass_marker_type_constants": {
            "source": str(consts_path),
            "rows": parse_consts(consts_path),
        },
        "raw_0x11e_u32_occurrences_inside_showmarker": [f"0x{x:X}" for x in class_imm_offsets],
        "prior_marker_lookup_hex_window": hex_window(pe, PRIOR_MARKER_LOOKUP_SITE, 80),
        "prior_type_check_hex_window": hex_window(pe, PRIOR_TYPE_CHECK_SITE, 96),
        "heuristic_rip_string_refs": heuristic_refs,
        "heuristic_error_string_refs": heuristic_error_refs,
        "heuristic_direct_calls": heuristic_direct_calls,
        "capstone": cs,
        "conclusion": conclusion,
        "next_gate": (
            "Resolve the exact call/data dependency used by LuaCompass::ShowMarker when validating type 0x11E, "
            "and identify what authored registry/cache that lookup consults. Do not patch or bypass the wrapper, "
            "and do not mutate another DCB until that lookup ownership is proven."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  conclusion: {conclusion}")
    print(f"  ShowMarker function: 0x{begin:X}-0x{end:X} ({end-begin} bytes)")
    print(f"  invalid-type string: file=0x{error_offset:X} rva=0x{error_rva:X}")
    print(f"  error refs in function: {error_ref_count}")
    print(f"  type-0x11E immediates in function: {type_imm_count}")
    print(f"  capstone available: {bool(cs.get('available'))}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
