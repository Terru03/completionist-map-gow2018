"""Locate GoW's persistent GameObject pickle/unpickle codec.

Version-locked, read-only static analysis of GoW.exe. The runtime GameObject Lua
handle has now been proven to contain allocator slot state, so it is not a
static WAD identity. This scanner instead searches the engine's custom pickle
layer for the code that serializes/deserializes GameObject userdata across
processes.

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

KNOWN_TARGETS = {
    "gameobject_token_packer": 0x60B9C0,
    "gameobject_token_resolver": 0x4EF0B0,
    "lua_gameobject_unbox": 0x5F9350,
}

TERMS = (
    "pickle", "unpickle", "gameobject", "objectref", "object_ref",
    "refnode", "persistent", "serialize", "deserialize",
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


def ascii_strings(pe: PE):
    out = []
    for s in pe.sections:
        start, end = s["raw"], min(len(pe.data), s["raw"] + s["rawsize"])
        i = start
        while i < end:
            if 0x20 <= pe.data[i] <= 0x7E:
                j = i
                while j < end and 0x20 <= pe.data[j] <= 0x7E:
                    j += 1
                if j - i >= 4 and j < end and pe.data[j] == 0:
                    text = pe.data[i:j].decode("ascii", "replace")
                    low = text.lower()
                    if any(t in low for t in TERMS):
                        rva = pe.file_to_rva(i)
                        if rva is not None:
                            out.append({"rva": rva, "section": s["name"], "text": text})
                i = max(j + 1, i + 1)
            else:
                i += 1
    return out


def string_xrefs(pe: PE, strings):
    by_target = {s["rva"]: s for s in strings}
    xrefs = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        end = min(len(pe.data), start + sec["rawsize"])
        d = pe.data
        for off in range(start, end - 7):
            # REX + MOV/LEA r64,[RIP+disp32]
            if not (0x40 <= d[off] <= 0x4F):
                continue
            if d[off + 1] not in (0x8B, 0x8D) or (d[off + 2] & 0xC7) != 0x05:
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", d, off + 3)[0]
            target = site + 7 + disp
            s = by_target.get(target)
            if s is None:
                continue
            fn = pe.function_for(site)
            xrefs.append({
                "site": site,
                "target_rva": target,
                "text": s["text"],
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return xrefs


def calls_to_known(pe: PE):
    rev = {v: k for k, v in KNOWN_TARGETS.items()}
    out = []
    for sec in pe.sections:
        if not sec["exec"]:
            continue
        start = sec["raw"]
        end = min(len(pe.data), start + sec["rawsize"])
        for off in range(start, end - 4):
            if pe.data[off] not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            dest = site + 5 + disp
            name = rev.get(dest)
            if name is None:
                continue
            fn = pe.function_for(site)
            out.append({
                "kind": "call" if pe.data[off] == 0xE8 else "jmp",
                "site": site, "target": name, "dest": dest,
                "function_begin": fn["begin"] if fn else None,
                "function_end": fn["end"] if fn else None,
            })
    return out


def outgoing_calls(pe: PE, fn):
    blob = pe.bytes_for(fn)
    out = []
    for i in range(max(0, len(blob) - 4)):
        if blob[i] != 0xE8:
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = fn["begin"] + i + 5 + disp
        if 0 <= dest < pe.size_of_image:
            tf = pe.function_for(dest)
            out.append({
                "site": fn["begin"] + i,
                "dest": dest,
                "target_function_begin": tf["begin"] if tf else None,
            })
    return out


def score_text(text: str) -> int:
    low = text.lower()
    score = 0
    if "pickle" in low or "unpickle" in low:
        score += 12
    if "gameobject" in low:
        score += 10
    if "serialize" in low or "deserialize" in low:
        score += 8
    if "persistent" in low:
        score += 6
    if "objectref" in low or "object_ref" in low or "refnode" in low:
        score += 6
    return score


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

    strings = ascii_strings(pe)
    xrefs = string_xrefs(pe, strings)
    helper_calls = calls_to_known(pe)

    funcs = {}
    for x in xrefs:
        fb = x["function_begin"]
        if fb is None:
            continue
        row = funcs.setdefault(fb, {"score": 0, "string_xrefs": [], "known_calls": []})
        row["string_xrefs"].append(x)
        row["score"] += score_text(x["text"])
    for c in helper_calls:
        fb = c["function_begin"]
        if fb is None:
            continue
        row = funcs.setdefault(fb, {"score": 0, "string_xrefs": [], "known_calls": []})
        row["known_calls"].append(c)
        row["score"] += {
            "gameobject_token_packer": 10,
            "gameobject_token_resolver": 8,
            "lua_gameobject_unbox": 6,
        }[c["target"]]

    candidates = []
    for fb, row in funcs.items():
        fn = pe.function_for(fb)
        if fn is None:
            continue
        blob = pe.bytes_for(fn)
        candidates.append({
            "function_begin": fn["begin"],
            "function_end": fn["end"],
            "size": fn["end"] - fn["begin"],
            "score": row["score"],
            "string_xrefs": row["string_xrefs"],
            "known_calls": row["known_calls"],
            "outgoing_calls": outgoing_calls(pe, fn)[:100],
            "function_hex": blob[:1024].hex(),
        })
    candidates.sort(key=lambda r: (-r["score"], r["function_begin"]))

    result = {
        "schema": 1,
        "analysis": "gameobject_persistent_pickle_codec",
        "exe_sha256": digest,
        "known_targets": KNOWN_TARGETS,
        "relevant_strings": strings,
        "string_xrefs": xrefs,
        "known_target_calls": helper_calls,
        "candidates": candidates,
    }

    out_json = Path(args.output_json)
    out_text = Path(args.output_text)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "Completionist Map - GameObject persistent pickle codec scan",
        f"exe_sha256={digest}",
        f"relevant_strings={len(strings)} string_xrefs={len(xrefs)} candidate_functions={len(candidates)}",
        "",
        "RELEVANT STRINGS",
    ]
    for s in strings:
        lines.append(f"  0x{s['rva']:X} [{s['section']}] {s['text']}")
    lines.extend(["", "TOP CANDIDATES"])
    for r in candidates[:80]:
        lines.append(f"FUNCTION 0x{r['function_begin']:X}-0x{r['function_end']:X} score={r['score']} size={r['size']}")
        for x in r["string_xrefs"]:
            lines.append(f"  STRREF site=0x{x['site']:X} -> 0x{x['target_rva']:X} {x['text']}")
        for c in r["known_calls"]:
            lines.append(f"  {c['kind'].upper()} site=0x{c['site']:X} -> {c['target']} 0x{c['dest']:X}")
        for e in r["outgoing_calls"][:30]:
            tf = "none" if e["target_function_begin"] is None else f"0x{e['target_function_begin']:X}"
            lines.append(f"  OUTCALL site=0x{e['site']:X} -> 0x{e['dest']:X} targetFn={tf}")
        lines.append(f"  HEX {r['function_hex']}")
    lines.extend([
        "",
        "source_hash_unchanged=true",
        "game_launched=false",
        "save_opened=false",
        "progression_written=false",
    ])
    out_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GAMEOBJECT_PICKLE_CODEC_SCAN_PASSED")


if __name__ == "__main__":
    main()
