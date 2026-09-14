"""Trace the exact native GameObject pickle/unpickle bridges and persistent-ID metadata.

Read-only, version-locked static analysis of the supported GoW.exe. The runtime
GameObject token has already been proven to be allocator state, so this tracer
focuses on the native persistence bridge instead:

  OnPickleInternal   0x5B2130
  OnUnpickleInternal 0x5B2324

It records direct callers/callees, nearby code bytes, RIP-relative string/data
references, and pointer-table references for GameObjectGUID / GameObjectIDA /
GameObjectIDB. No game launch and no save I/O.
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
    "on_pickle_internal": 0x5B2130,
    "on_unpickle_internal": 0x5B2324,
    "pickle_driver": 0x5AF8AD,
    "pickle_table_builder": 0x5AF01C,
    "unpickle_driver": 0x5B1030,
    "restore_dispatch": 0x5AD4A0,
}

FIELD_STRINGS = ("GameObjectGUID", "GameObjectIDA", "GameObjectIDB")
INTERESTING_TERMS = (
    "pickle", "unpickle", "gameobject", "guid", "persistent", "serialize",
    "deserialize", "refnode", "objectref", "object_ref", "wad", "level",
)


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
                "name": name, "vsize": vsize, "rva": rva,
                "rawsize": rawsize, "raw": raw,
                "exec": bool(ch & IMAGE_SCN_MEM_EXECUTE),
            })
        self.runtime_functions = self._runtime_functions()

    def _runtime_functions(self):
        off = self.rva_to_file(self.exception_rva)
        if off is None:
            raise RuntimeError("exception directory not mapped")
        out = []
        for p in range(off, off + self.exception_size - 11, 12):
            begin, end, unwind = struct.unpack_from("<III", self.data, p)
            if begin and end > begin and end <= self.size_of_image:
                out.append({"begin": begin, "end": end, "unwind": unwind})
        out.sort(key=lambda x: x["begin"])
        return out

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

    def bytes_for(self, fn):
        off = self.rva_to_file(fn["begin"])
        if off is None:
            return b""
        return self.data[off:off + fn["end"] - fn["begin"]]


def ascii_map(pe: PE):
    out = {}
    for s in pe.sections:
        start = s["raw"]
        end = min(len(pe.data), start + s["rawsize"])
        i = start
        while i < end:
            if 0x20 <= pe.data[i] <= 0x7E:
                j = i
                while j < end and 0x20 <= pe.data[j] <= 0x7E:
                    j += 1
                if j - i >= 4 and j < end and pe.data[j] == 0:
                    rva = pe.file_to_rva(i)
                    if rva is not None:
                        out[rva] = pe.data[i:j].decode("ascii", "replace")
                i = max(j + 1, i + 1)
            else:
                i += 1
    return out


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
            lo = max(start, off - 48)
            hi = min(end, off + 53)
            out.append({
                "kind": "call" if op == 0xE8 else "jmp",
                "site": site,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
                "context_hex": pe.data[lo:hi].hex(),
            })
    return out


def outgoing_calls(pe: PE, fn):
    blob = pe.bytes_for(fn)
    out = []
    for i in range(max(0, len(blob) - 4)):
        if blob[i] not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = fn["begin"] + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        tf = pe.function_for(dest)
        out.append({
            "kind": "call" if blob[i] == 0xE8 else "jmp",
            "site": fn["begin"] + i,
            "dest": dest,
            "target_function_begin": tf["begin"] if tf else None,
            "target_function_end": tf["end"] if tf else None,
        })
    return out


def rip_refs_in_fn(pe: PE, fn, strings):
    blob = pe.bytes_for(fn)
    out = []
    for i in range(max(0, len(blob) - 7)):
        rex = blob[i]
        if not (0x40 <= rex <= 0x4F):
            continue
        op = blob[i + 1]
        modrm = blob[i + 2]
        if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", blob, i + 3)[0]
        site = fn["begin"] + i
        target = site + 7 + disp
        sec = pe.section_for_rva(target)
        text = strings.get(target)
        out.append({
            "site": site,
            "opcode": "mov" if op == 0x8B else "lea",
            "target_rva": target,
            "target_section": sec["name"] if sec else None,
            "text": text,
        })
    return out


def trace_function(pe: PE, entry: int, strings):
    fn = pe.function_for(entry)
    if fn is None:
        raise RuntimeError(f"no runtime function for target {entry:#x}")
    return {
        "entry": entry,
        "function_begin": fn["begin"],
        "function_end": fn["end"],
        "size": fn["end"] - fn["begin"],
        "function_hex": pe.bytes_for(fn).hex(),
        "direct_callers": direct_callers(pe, entry),
        "outgoing_calls": outgoing_calls(pe, fn),
        "rip_refs": rip_refs_in_fn(pe, fn, strings),
    }


def find_field_strings(strings):
    wanted = {}
    for rva, text in strings.items():
        if text in FIELD_STRINGS:
            wanted[text] = rva
    return wanted


def pointer_occurrences(pe: PE, target_rva: int):
    out = []
    needles = (
        ("va64", struct.pack("<Q", IMAGE_BASE + target_rva)),
        ("rva32", struct.pack("<I", target_rva)),
    )
    for kind, needle in needles:
        pos = 0
        while True:
            off = pe.data.find(needle, pos)
            if off < 0:
                break
            rva = pe.file_to_rva(off)
            if rva is not None:
                sec = pe.section_for_rva(rva)
                lo = max(0, off - 64)
                hi = min(len(pe.data), off + len(needle) + 64)
                out.append({
                    "kind": kind,
                    "rva": rva,
                    "section": sec["name"] if sec else None,
                    "context_hex": pe.data[lo:hi].hex(),
                })
            pos = off + 1
    return out


def code_refs_to_range(pe: PE, begin: int, end: int):
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start = s["raw"]
        stop = min(len(pe.data), start + s["rawsize"])
        d = pe.data
        for off in range(start, stop - 7):
            if not (0x40 <= d[off] <= 0x4F):
                continue
            op = d[off + 1]
            modrm = d[off + 2]
            if op not in (0x8B, 0x8D) or (modrm & 0xC7) != 0x05:
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", d, off + 3)[0]
            target = site + 7 + disp
            if not (begin <= target < end):
                continue
            fn = pe.function_for(site)
            out.append({
                "site": site,
                "opcode": "mov" if op == 0x8B else "lea",
                "target_rva": target,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


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
    strings = ascii_map(pe)

    targets = {name: trace_function(pe, entry, strings) for name, entry in TARGETS.items()}

    # Include one function layer around the exact pickle/unpickle bridges.
    neighbors = {}
    for bridge_name in ("on_pickle_internal", "on_unpickle_internal"):
        row = targets[bridge_name]
        for c in row["direct_callers"]:
            fb = c["function_begin"]
            if fb is not None and fb not in neighbors:
                neighbors[fb] = trace_function(pe, fb, strings)
        for e in row["outgoing_calls"]:
            fb = e["target_function_begin"]
            if fb is not None and fb not in neighbors:
                neighbors[fb] = trace_function(pe, fb, strings)

    field_rvas = find_field_strings(strings)
    field_metadata = {}
    for name in FIELD_STRINGS:
        rva = field_rvas.get(name)
        if rva is None:
            field_metadata[name] = {"string_rva": None, "pointer_occurrences": [], "near_table_code_refs": []}
            continue
        ptrs = pointer_occurrences(pe, rva)
        refs = []
        for p in ptrs:
            refs.extend(code_refs_to_range(pe, max(0, p["rva"] - 64), p["rva"] + 72))
        field_metadata[name] = {
            "string_rva": rva,
            "pointer_occurrences": ptrs,
            "near_table_code_refs": refs,
        }

    result = {
        "schema": 1,
        "analysis": "gameobject_pickle_bridge_trace",
        "exe_sha256": digest,
        "targets": targets,
        "bridge_neighbors": {f"0x{k:X}": v for k, v in sorted(neighbors.items())},
        "field_metadata": field_metadata,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - GameObject pickle bridge trace",
        f"exe_sha256={digest}",
        "",
    ]
    for name, row in targets.items():
        lines.append(f"TARGET {name} entry=0x{row['entry']:X} fn=0x{row['function_begin']:X}-0x{row['function_end']:X} size={row['size']}")
        lines.append(f"  callers={len(row['direct_callers'])} outgoing={len(row['outgoing_calls'])} rip_refs={len(row['rip_refs'])}")
        for c in row["direct_callers"]:
            fb = "none" if c["function_begin"] is None else f"0x{c['function_begin']:X}"
            lines.append(f"    CALLER {c['kind'].upper()} site=0x{c['site']:X} fn={fb}")
        for e in row["outgoing_calls"]:
            tf = "none" if e["target_function_begin"] is None else f"0x{e['target_function_begin']:X}"
            lines.append(f"    OUT {e['kind'].upper()} site=0x{e['site']:X} dest=0x{e['dest']:X} fn={tf}")
        for r in row["rip_refs"]:
            if r["text"] or (r["target_section"] and r["target_section"] != ".text"):
                text = "" if r["text"] is None else f" text={r['text']}"
                lines.append(f"    RIP {r['opcode'].upper()} site=0x{r['site']:X} -> 0x{r['target_rva']:X} section={r['target_section']}{text}")
        lines.append(f"  HEX {row['function_hex']}")
        lines.append("")

    lines.append("FIELD METADATA")
    for name, row in field_metadata.items():
        sr = "none" if row["string_rva"] is None else f"0x{row['string_rva']:X}"
        lines.append(f"  {name} string={sr} pointers={len(row['pointer_occurrences'])} table_code_refs={len(row['near_table_code_refs'])}")
        for p in row["pointer_occurrences"]:
            lines.append(f"    PTR {p['kind']} rva=0x{p['rva']:X} section={p['section']} context={p['context_hex']}")
        for r in row["near_table_code_refs"]:
            fb = "none" if r["function_begin"] is None else f"0x{r['function_begin']:X}"
            lines.append(f"    CODE {r['opcode'].upper()} site=0x{r['site']:X} -> 0x{r['target_rva']:X} fn={fb}")

    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GAMEOBJECT_PICKLE_BRIDGE_TRACE_PASSED")


if __name__ == "__main__":
    main()
