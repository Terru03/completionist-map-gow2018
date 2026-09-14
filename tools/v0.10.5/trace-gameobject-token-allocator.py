"""Trace the native GameObject token construction paths back to their inputs.

Read-only, version-locked static analysis of GoW.exe. This is deliberately
focused on the native functions around the known GameObject token resolver and
the two routines that write +0x278/+0x280/+0x284 with the same bit packing used
by Lua GameObject references.

No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
IMAGE_SCN_MEM_EXECUTE = 0x20000000

TARGETS = {
    "token_resolver": 0x4EF0B0,
    "flavor1_constructor": 0x4EF2B0,
    "flavor1_wrapper": 0x4EF3EB,
    "flavor0_constructor": 0x4EF540,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class PE:
    def __init__(self, data: bytes):
        self.data = data
        if data[:2] != b"MZ":
            raise RuntimeError("not MZ")
        peoff = struct.unpack_from("<I", data, 0x3C)[0]
        if data[peoff:peoff + 4] != b"PE\0\0":
            raise RuntimeError("bad PE")
        nsec = struct.unpack_from("<H", data, peoff + 6)[0]
        optsz = struct.unpack_from("<H", data, peoff + 20)[0]
        opt = peoff + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("not PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        if self.image_base != IMAGE_BASE:
            raise RuntimeError(f"unexpected image base {self.image_base:#x}")
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        dd = opt + 112
        self.exception_rva, self.exception_size = struct.unpack_from("<II", data, dd + 3 * 8)
        sec0 = opt + optsz
        self.sections = []
        for i in range(nsec):
            o = sec0 + i * 40
            name = data[o:o + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            vsize, rva, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
            ch = struct.unpack_from("<I", data, o + 36)[0]
            self.sections.append({
                "name": name, "vsize": vsize, "rva": rva, "rawsize": rawsize,
                "raw": raw, "exec": bool(ch & IMAGE_SCN_MEM_EXECUTE),
            })
        self.runtime_functions = self._runtime_functions()

    def _runtime_functions(self):
        off = self.rva_to_file(self.exception_rva)
        if off is None:
            raise RuntimeError("exception directory not mapped")
        rows = []
        for p in range(off, off + self.exception_size - 11, 12):
            begin, end, unwind = struct.unpack_from("<III", self.data, p)
            if begin and end > begin and end <= self.size_of_image:
                rows.append({"begin": begin, "end": end, "unwind": unwind})
        rows.sort(key=lambda r: r["begin"])
        return rows

    def rva_to_file(self, rva: int):
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                return s["raw"] + d if d < s["rawsize"] else None
        return None

    def file_to_rva(self, off: int):
        for s in self.sections:
            if s["raw"] <= off < s["raw"] + s["rawsize"]:
                return s["rva"] + off - s["raw"]
        return None

    def section_for_rva(self, rva: int):
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                return s
        return None

    def function_for(self, rva: int):
        lo, hi = 0, len(self.runtime_functions)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.runtime_functions[mid]["begin"] <= rva:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            return None
        row = self.runtime_functions[lo - 1]
        return row if row["begin"] <= rva < row["end"] else None

    def bytes_rva(self, begin: int, end: int) -> bytes:
        off = self.rva_to_file(begin)
        if off is None:
            return b""
        return self.data[off:off + max(0, end - begin)]

    def bytes_for_fn(self, fn) -> bytes:
        return self.bytes_rva(fn["begin"], fn["end"])


def direct_callers(pe: PE, target: int):
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start = s["raw"]
        end = min(len(pe.data), start + s["rawsize"])
        for off in range(start, end - 4):
            op = pe.data[off]
            if op not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            if site + 5 + disp != target:
                continue
            fn = pe.function_for(site)
            out.append({
                "kind": "call" if op == 0xE8 else "jmp",
                "site": site,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def outgoing_rel32(pe: PE, fn):
    blob = pe.bytes_for_fn(fn)
    out = []
    for i in range(0, max(0, len(blob) - 4)):
        op = blob[i]
        if op not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = fn["begin"] + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        tf = pe.function_for(dest)
        out.append({
            "kind": "call" if op == 0xE8 else "jmp",
            "site": fn["begin"] + i,
            "dest": dest,
            "target_function_begin": tf["begin"] if tf else None,
        })
    return out


def pointer_occurrences(pe: PE, target_rva: int):
    needles = [
        ("va64", struct.pack("<Q", IMAGE_BASE + target_rva)),
        ("rva32", struct.pack("<I", target_rva)),
    ]
    out = []
    for kind, needle in needles:
        pos = 0
        while True:
            off = pe.data.find(needle, pos)
            if off < 0:
                break
            rva = pe.file_to_rva(off)
            if rva is not None:
                sec = pe.section_for_rva(rva)
                lo = max(0, off - 32)
                hi = min(len(pe.data), off + len(needle) + 32)
                out.append({
                    "kind": kind,
                    "rva": rva,
                    "section": sec["name"] if sec else None,
                    "context_hex": pe.data[lo:hi].hex(),
                })
            pos = off + 1
    return out


def rip_relative_refs(pe: PE, target_rva: int):
    """Find common RIP+disp32 memory/LEA refs that land exactly on target_rva."""
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start = s["raw"]
        end = min(len(pe.data), start + s["rawsize"])
        data = pe.data
        for off in range(start, end - 7):
            # optional REX + opcode 8B/8D + modrm mod=00 rm=101 + disp32
            if not (0x40 <= data[off] <= 0x4F):
                continue
            op = data[off + 1]
            modrm = data[off + 2]
            if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", data, off + 3)[0]
            dest = site + 7 + disp
            if dest != target_rva:
                continue
            fn = pe.function_for(site)
            out.append({
                "site": site,
                "opcode": "mov" if op == 0x8B else "lea",
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def rip_targets_inside(pe: PE, fn):
    """Enumerate common RIP-relative MOV/LEA targets used by the target function."""
    blob = pe.bytes_for_fn(fn)
    out = []
    for i in range(0, max(0, len(blob) - 7)):
        if not (0x40 <= blob[i] <= 0x4F):
            continue
        op = blob[i + 1]
        modrm = blob[i + 2]
        if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", blob, i + 3)[0]
        site = fn["begin"] + i
        dest = site + 7 + disp
        sec = pe.section_for_rva(dest)
        target_off = pe.rva_to_file(dest)
        value = None
        if target_off is not None:
            value = pe.data[target_off:target_off + 16].hex()
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target_rva": dest,
            "target_section": sec["name"] if sec else None,
            "target_bytes16": value,
        })
    return out


def signatures(blob: bytes):
    sigs = {
        "mask_20bit": b"\xff\xff\x0f\x00" in blob,
        "shift_left_17": b"\xc1\xe3\x11" in blob or b"\x49\xc1\xe3\x11" in blob or b"\x48\xc1\xe2\x11" in blob,
        "write_278": b"\x78\x02\x00\x00" in blob,
        "write_280": b"\x80\x02\x00\x00" in blob,
        "write_284": b"\x84\x02\x00\x00" in blob,
        "or_flag_09_278": b"\x78\x02\x00\x00\x09" in blob,
        "clear_bit3_set_bit0_278": b"\x83\xe0\xf7\x83\xc8\x01" in blob,
        "bts_bit16": b"\x0f\xba\xea\x10" in blob,
    }
    return sigs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-text", required=True)
    args = ap.parse_args()

    exe = Path(args.game_root) / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"missing {exe}")
    digest = sha256(exe)
    if digest.lower() != EXPECTED_SHA256:
        raise RuntimeError(f"GoW.exe SHA-256 mismatch: {digest}")
    pe = PE(exe.read_bytes())

    result = {
        "schema": 1,
        "analysis": "gameobject_token_allocator_trace",
        "exe_sha256": digest,
        "targets": {},
    }

    for name, entry in TARGETS.items():
        fn = pe.function_for(entry)
        if fn is None:
            raise RuntimeError(f"runtime function missing for {name} {entry:#x}")
        blob = pe.bytes_for_fn(fn)
        refs = pointer_occurrences(pe, entry)
        for ref in refs:
            ref["rip_code_refs"] = rip_relative_refs(pe, ref["rva"])
        result["targets"][name] = {
            "entry": entry,
            "function_begin": fn["begin"],
            "function_end": fn["end"],
            "size": fn["end"] - fn["begin"],
            "function_hex": blob.hex(),
            "signatures": signatures(blob),
            "direct_callers": direct_callers(pe, entry),
            "outgoing_rel32": outgoing_rel32(pe, fn),
            "rip_targets": rip_targets_inside(pe, fn),
            "pointer_occurrences": refs,
        }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - GameObject token allocator trace",
        f"exe_sha256={digest}",
        "known_token_formula=(((field_284&0xFFFFF)<<1 | ((field_278>>3)&1))<<16 | (field_280&0xFFFF))<<1 | 1",
        "",
    ]
    for name, row in result["targets"].items():
        lines.append(f"TARGET {name} entry=0x{row['entry']:X} fn=0x{row['function_begin']:X}-0x{row['function_end']:X} size={row['size']}")
        lines.append("  signatures=" + json.dumps(row["signatures"], sort_keys=True))
        lines.append(f"  direct_callers={len(row['direct_callers'])}")
        for c in row["direct_callers"]:
            fb = "none" if c["function_begin"] is None else f"0x{c['function_begin']:X}"
            lines.append(f"    {c['kind'].upper()} site=0x{c['site']:X} fn={fb}")
        lines.append(f"  outgoing_rel32={len(row['outgoing_rel32'])}")
        for e in row["outgoing_rel32"]:
            tf = "none" if e["target_function_begin"] is None else f"0x{e['target_function_begin']:X}"
            lines.append(f"    {e['kind'].upper()} site=0x{e['site']:X} dest=0x{e['dest']:X} targetFn={tf}")
        lines.append(f"  rip_targets={len(row['rip_targets'])}")
        for r in row["rip_targets"]:
            lines.append(f"    {r['opcode'].upper()} site=0x{r['site']:X} -> 0x{r['target_rva']:X} section={r['target_section']} bytes16={r['target_bytes16']}")
        lines.append(f"  pointer_occurrences={len(row['pointer_occurrences'])}")
        for p in row["pointer_occurrences"]:
            lines.append(f"    PTR kind={p['kind']} rva=0x{p['rva']:X} section={p['section']} code_refs={len(p['rip_code_refs'])}")
            for cr in p["rip_code_refs"]:
                fb = "none" if cr["function_begin"] is None else f"0x{cr['function_begin']:X}"
                lines.append(f"      {cr['opcode'].upper()} site=0x{cr['site']:X} fn={fb}")
        lines.append(f"  function_hex={row['function_hex']}")
        lines.append("")

    lines.extend([
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GAMEOBJECT_TOKEN_ALLOCATOR_TRACE_PASSED")


if __name__ == "__main__":
    main()
