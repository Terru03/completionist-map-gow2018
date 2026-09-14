"""Identify GoW's native Lua GameObject argument decoder by call intersection.

The Lua binding table gives us many independently-known GameObject handlers such
as GetDebugName, GetDebugPath, Level, GetCreature and GetBreakable.  Each handler
must turn the Lua-side opaque GameObject value back into a native object before
it can perform its operation.  This read-only, version-locked scanner recovers
exact x64 function boundaries for representative handlers, inventories their
direct CALL/JMP targets, ranks targets shared across handlers, and emits the
candidate helper functions with bounded bytes/strings/callers.

No game launch and no save I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
IMAGE_SCN_MEM_EXECUTE = 0x20000000
TOKEN_PACKER_RVA = 0x60B9C0

# Read-only / type-query GameObject bindings already recovered from the native
# GameObject registration table.  Use several unrelated methods so a helper
# shared by them is much more likely to be the common Lua -> GameObject decoder
# than method-specific implementation code.
HANDLERS = {
    "GetDebugName": 0x18F2A0,
    "GetDebugPath": 0x18F350,
    "Level": 0x195360,
    "GetCreature": 0x18F420,
    "GetBreakable": 0x18F500,
    "IsEffect": 0x18F5D0,
    "GetWorldPosition": 0x6056B0,
    "Parent": 0x6041C0,
    "Children": 0x6043C0,
    "IsCreature": 0x6084E0,
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
                "name": name, "vsize": vsize, "rva": rva,
                "rawsize": rawsize, "raw": raw,
                "exec": bool(ch & IMAGE_SCN_MEM_EXECUTE),
            })
        self.runtime_functions = self._runtime_functions()

    def rva_to_file(self, rva: int) -> int | None:
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                return s["raw"] + d if d < s["rawsize"] else None
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

    def ascii_at_rva(self, rva: int, cap: int = 120):
        off = self.rva_to_file(rva)
        if off is None:
            return None
        out = bytearray()
        for b in self.data[off:off + cap]:
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            out.append(b)
        if not out or off + len(out) >= len(self.data) or self.data[off + len(out)] != 0:
            return None
        return out.decode("ascii", "replace")


def direct_edges(pe: PE, fn):
    """Collect direct near CALL (E8) and JMP (E9) targets within the image."""
    blob = pe.bytes_for(fn)
    base = fn["begin"]
    out = []
    for i in range(max(0, len(blob) - 4)):
        op = blob[i]
        if op not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", blob, i + 1)[0]
        dest = base + i + 5 + disp
        if not (0 <= dest < pe.size_of_image):
            continue
        tf = pe.function_for(dest)
        out.append({
            "kind": "call" if op == 0xE8 else "jmp",
            "site": base + i,
            "dest": dest,
            "target_function_begin": tf["begin"] if tf else None,
        })
    return out


def rip_ascii_refs(pe: PE, fn):
    blob = pe.bytes_for(fn)
    base = fn["begin"]
    out, seen = [], set()
    for i in range(max(0, len(blob) - 7)):
        rex, op, modrm = blob[i], blob[i + 1], blob[i + 2]
        if not (0x40 <= rex <= 0x4F and op in (0x8D, 0x8B) and (modrm & 0xC7) == 0x05):
            continue
        disp = struct.unpack_from("<i", blob, i + 3)[0]
        target = base + i + 7 + disp
        text = pe.ascii_at_rva(target)
        if text and (target, text) not in seen:
            seen.add((target, text))
            out.append({"site": base + i, "target": target, "text": text})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    exe = args.game_root.resolve() / "GoW.exe"
    before = sha256(exe)
    if before != EXPECTED_SHA256:
        raise RuntimeError(f"Unexpected GoW.exe SHA-256: {before}")
    pe = PE(exe.read_bytes())

    handler_rows = []
    target_to_handlers = defaultdict(set)
    target_edge_sites = defaultdict(list)

    for name, entry in HANDLERS.items():
        fn = pe.function_for(entry)
        if fn is None:
            raise RuntimeError(f"No pdata function for {name} @ {entry:#x}")
        edges = direct_edges(pe, fn)
        for edge in edges:
            begin = edge["target_function_begin"]
            if begin is None:
                continue
            target_to_handlers[begin].add(name)
            target_edge_sites[begin].append({"handler": name, **edge})
        handler_rows.append({
            "name": name,
            "entry_rva": entry,
            "function_begin": fn["begin"],
            "function_end": fn["end"],
            "size": fn["end"] - fn["begin"],
            "edges": edges,
            "ascii_refs": rip_ascii_refs(pe, fn),
            "bytes_hex": pe.bytes_for(fn).hex(),
        })

    ranked = sorted(target_to_handlers.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    candidates = []
    for begin, names in ranked:
        # Shared by at least two representative GameObject handlers.  Include all
        # such helpers so the report can distinguish generic Lua helpers from the
        # actual GameObject decoder by callers, strings and byte shape.
        if len(names) < 2:
            continue
        fn = pe.function_for(begin)
        if fn is None:
            continue
        candidates.append({
            "begin": fn["begin"],
            "end": fn["end"],
            "size": fn["end"] - fn["begin"],
            "handler_count": len(names),
            "handlers": sorted(names),
            "edge_sites": target_edge_sites[begin],
            "edges": direct_edges(pe, fn),
            "ascii_refs": rip_ascii_refs(pe, fn),
            "bytes_hex": pe.bytes_for(fn).hex(),
            "is_token_packer": fn["begin"] <= TOKEN_PACKER_RVA < fn["end"],
        })

    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe changed during scan")

    report = {
        "schema": 1,
        "analysis": "gameobject_lua_argument_decoder",
        "exe_sha256": before,
        "handlers": handler_rows,
        "shared_candidates": candidates,
        "safety": {
            "read_only": True,
            "game_launched": False,
            "save_opened": False,
            "progression_written": False,
            "source_hash_unchanged": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - GameObject Lua argument decoder candidates",
        f"exe_sha256={before}",
        f"handler_count={len(handler_rows)}",
        f"shared_candidate_count={len(candidates)}",
        "",
        "HANDLERS",
    ]
    for row in handler_rows:
        lines.append(
            f"  {row['name']} entry=0x{row['entry_rva']:X} fn=0x{row['function_begin']:X}-0x{row['function_end']:X} size={row['size']}"
        )
        for edge in row["edges"]:
            target = f"0x{edge['target_function_begin']:X}" if edge["target_function_begin"] is not None else "none"
            lines.append(f"    {edge['kind'].upper()} 0x{edge['site']:X} -> 0x{edge['dest']:X} targetFn={target}")
    lines.append("")
    lines.append("SHARED CANDIDATES")
    for c in candidates:
        lines.append(
            f"  FUNCTION 0x{c['begin']:X}-0x{c['end']:X} size={c['size']} handlers={c['handler_count']} tokenPacker={str(c['is_token_packer']).lower()} names={','.join(c['handlers'])}"
        )
        for s in c["ascii_refs"]:
            lines.append(f"    STR 0x{s['site']:X} {s['text']!r}")
        for e in c["edges"][:20]:
            lines.append(f"    {e['kind'].upper()} 0x{e['site']:X} -> 0x{e['dest']:X}")
        lines.append("")
    lines.append("source_hash_unchanged=true game_launched=false save_opened=false progression_written=false")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GAMEOBJECT_ARGUMENT_DECODER_SCAN_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
