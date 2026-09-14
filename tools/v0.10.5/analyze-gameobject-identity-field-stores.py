"""Find exact native stores to GoW GameObject identity fields.

Version-locked, read-only analysis of the supported GoW.exe. Previous broad
scans proved the Lua GameObject token is built from live object fields at
+0x278/+0x280/+0x284, but a displacement-only heuristic confused loads with
stores. This scanner recognizes concrete x64 MOV store forms to those exact
fields and reports their containing function, source register/immediate,
nearby bytes, direct callers, direct edges, and relevant nearby strings.

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
FIELD_DISPS = {0x278: "field_278", 0x280: "field_280", 0x284: "field_284"}
FOCUS_FUNCTION = 0x62FC00
RELEVANT_WORDS = ("wad", "guid", "gameobject", "object", "instance", "spawn", "stream", "level", "ref")
REG32 = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi", "r8d", "r9d", "r10d", "r11d", "r12d", "r13d", "r14d", "r15d")
REG64 = ("rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15")
REG16 = ("ax", "cx", "dx", "bx", "sp", "bp", "si", "di", "r8w", "r9w", "r10w", "r11w", "r12w", "r13w", "r14w", "r15w")
REG8 = ("al", "cl", "dl", "bl", "spl", "bpl", "sil", "dil", "r8b", "r9b", "r10b", "r11b", "r12b", "r13b", "r14b", "r15b")


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
            self.sections.append({"name": name, "vsize": vsize, "rva": rva, "rawsize": rawsize, "raw": raw, "exec": bool(ch & IMAGE_SCN_MEM_EXECUTE)})
        self.runtime_functions = self._runtime_functions()

    def rva_to_file(self, rva: int) -> int | None:
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                return s["raw"] + d if d < s["rawsize"] else None
        return None

    def file_to_rva(self, off: int) -> int | None:
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

    def ascii_at_rva(self, rva: int, cap: int = 160):
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
        out.append({"kind": "call" if op == 0xE8 else "jmp", "site": base + i, "dest": dest, "target_function_begin": tf["begin"] if tf else None})
    return out


def direct_callers(pe: PE, target: int):
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start, end = s["raw"], min(len(pe.data), s["raw"] + s["rawsize"])
        for off in range(start, end - 4):
            if pe.data[off] not in (0xE8, 0xE9):
                continue
            site = pe.file_to_rva(off)
            if site is None:
                continue
            disp = struct.unpack_from("<i", pe.data, off + 1)[0]
            if site + 5 + disp != target:
                continue
            fn = pe.function_for(site)
            out.append({"kind": "call" if pe.data[off] == 0xE8 else "jmp", "site": site, "function_begin": fn["begin"] if fn else None, "function_end": fn["end"] if fn else None})
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


def rex_before(data: bytes, opcode_off: int):
    # Return optional 0x66 prefix plus optional REX byte immediately preceding opcode.
    rex = 0
    has66 = False
    p = opcode_off - 1
    if p >= 0 and 0x40 <= data[p] <= 0x4F:
        rex = data[p]
        p -= 1
    if p >= 0 and data[p] == 0x66:
        has66 = True
    return rex, has66


def decode_store_at_disp(data: bytes, disp_file_off: int, disp: int):
    """Recognize non-SIB mod=10 MOV stores whose disp32 begins at disp_file_off."""
    if disp_file_off < 2 or disp_file_off + 4 > len(data):
        return None
    modrm_off = disp_file_off - 1
    modrm = data[modrm_off]
    mod = (modrm >> 6) & 3
    rm = modrm & 7
    reg = (modrm >> 3) & 7
    if mod != 2 or rm == 4:  # exact disp32 base addressing; SIB handled separately below
        return None
    opcode_off = modrm_off - 1
    opcode = data[opcode_off]
    rex, has66 = rex_before(data, opcode_off)
    rex_r = 1 if (rex & 0x04) else 0
    rex_b = 1 if (rex & 0x01) else 0
    src_index = reg + 8 * rex_r
    base_index = rm + 8 * rex_b
    base_reg = REG64[base_index]
    if opcode == 0x88:
        width = 8
        source = REG8[src_index]
        start = opcode_off - (1 if rex else 0) - (1 if has66 else 0)
        length = disp_file_off + 4 - start
        return {"start_file": start, "end_file": start + length, "width": width, "source": source, "base": base_reg, "form": "mov_mem_reg8"}
    if opcode == 0x89:
        width = 16 if has66 else (64 if (rex & 0x08) else 32)
        regs = REG16 if width == 16 else REG64 if width == 64 else REG32
        source = regs[src_index]
        start = opcode_off - (1 if rex else 0) - (1 if has66 else 0)
        length = disp_file_off + 4 - start
        return {"start_file": start, "end_file": start + length, "width": width, "source": source, "base": base_reg, "form": "mov_mem_reg"}
    if opcode in (0xC6, 0xC7) and reg == 0:
        width = 8 if opcode == 0xC6 else (16 if has66 else 32)
        imm_size = 1 if opcode == 0xC6 else (2 if has66 else 4)
        imm_off = disp_file_off + 4
        if imm_off + imm_size > len(data):
            return None
        imm = int.from_bytes(data[imm_off:imm_off + imm_size], "little", signed=False)
        start = opcode_off - (1 if rex else 0) - (1 if has66 else 0)
        return {"start_file": start, "end_file": imm_off + imm_size, "width": width, "source": f"imm 0x{imm:X}", "base": base_reg, "form": "mov_mem_imm"}
    return None


def decode_store_sib_at_disp(data: bytes, disp_file_off: int, disp: int):
    # MOV stores with mod=10 and SIB byte immediately before disp32.
    if disp_file_off < 3:
        return None
    sib_off = disp_file_off - 1
    modrm_off = disp_file_off - 2
    modrm = data[modrm_off]
    if ((modrm >> 6) & 3) != 2 or (modrm & 7) != 4:
        return None
    sib = data[sib_off]
    if ((sib >> 3) & 7) != 4:  # keep only no-index SIB to stay unambiguous
        return None
    reg = (modrm >> 3) & 7
    base = sib & 7
    opcode_off = modrm_off - 1
    opcode = data[opcode_off]
    rex, has66 = rex_before(data, opcode_off)
    rex_r = 1 if (rex & 0x04) else 0
    rex_b = 1 if (rex & 0x01) else 0
    src_index = reg + 8 * rex_r
    base_index = base + 8 * rex_b
    base_reg = REG64[base_index]
    if opcode == 0x88:
        width, source = 8, REG8[src_index]
    elif opcode == 0x89:
        width = 16 if has66 else (64 if (rex & 0x08) else 32)
        regs = REG16 if width == 16 else REG64 if width == 64 else REG32
        source = regs[src_index]
    else:
        return None
    start = opcode_off - (1 if rex else 0) - (1 if has66 else 0)
    return {"start_file": start, "end_file": disp_file_off + 4, "width": width, "source": source, "base": base_reg, "form": "mov_mem_reg_sib"}


def find_exact_stores(pe: PE):
    stores = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start, end = s["raw"], min(len(pe.data), s["raw"] + s["rawsize"])
        section = pe.data[start:end]
        for disp, label in FIELD_DISPS.items():
            needle = struct.pack("<I", disp)
            pos = 0
            while True:
                rel = section.find(needle, pos)
                if rel < 0:
                    break
                file_off = start + rel
                decoded = decode_store_at_disp(pe.data, file_off, disp) or decode_store_sib_at_disp(pe.data, file_off, disp)
                if decoded:
                    site = pe.file_to_rva(decoded["start_file"])
                    if site is not None:
                        fn = pe.function_for(site)
                        lo = max(start, decoded["start_file"] - 64)
                        hi = min(end, decoded["end_file"] + 64)
                        inst = pe.data[decoded["start_file"]:decoded["end_file"]]
                        stores.append({
                            "field": label,
                            "disp": disp,
                            "site": site,
                            "function_begin": fn["begin"] if fn else None,
                            "function_end": fn["end"] if fn else None,
                            "width": decoded["width"],
                            "source": decoded["source"],
                            "base": decoded["base"],
                            "form": decoded["form"],
                            "instruction_hex": inst.hex(),
                            "context_rva": pe.file_to_rva(lo),
                            "context_hex": pe.data[lo:hi].hex(),
                        })
                pos = rel + 1
    # de-duplicate in case the same disp bytes were reached through overlapping scans
    uniq = {}
    for row in stores:
        uniq[(row["site"], row["field"], row["instruction_hex"])] = row
    return sorted(uniq.values(), key=lambda r: (r["site"], r["field"]))


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
    stores = find_exact_stores(pe)

    functions = {}
    for row in stores:
        begin = row["function_begin"]
        if begin is None or begin in functions:
            continue
        fn = pe.function_for(begin)
        if fn is None:
            continue
        strings = [x for x in rip_ascii_refs(pe, fn) if any(k in x["text"].lower() for k in RELEVANT_WORDS)]
        functions[begin] = {
            "begin": fn["begin"], "end": fn["end"], "size": fn["end"] - fn["begin"],
            "callers": direct_callers(pe, fn["begin"]),
            "edges": direct_edges(pe, fn),
            "ascii_refs": strings,
        }

    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe changed during scan")

    report = {
        "schema": 1,
        "analysis": "gameobject_identity_field_exact_stores",
        "exe_sha256": before,
        "focus_function": hex(FOCUS_FUNCTION),
        "store_count": len(stores),
        "stores": stores,
        "functions": [functions[k] for k in sorted(functions)],
        "safety": {"read_only": True, "game_launched": False, "save_opened": False, "progression_written": False, "source_hash_unchanged": True},
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - exact GameObject identity-field stores",
        f"exe_sha256={before}",
        f"exact_store_count={len(stores)}",
        "",
    ]
    grouped = {}
    for row in stores:
        grouped.setdefault(row["function_begin"], []).append(row)
    order = sorted(grouped, key=lambda b: (0 if b == FOCUS_FUNCTION else 1, b if b is not None else 0xFFFFFFFF))
    for begin in order:
        rows = grouped[begin]
        fn_text = "none" if begin is None else f"0x{begin:X}-0x{rows[0]['function_end']:X}"
        lines.append(f"FUNCTION {fn_text} stores={len(rows)} focus={str(begin == FOCUS_FUNCTION).lower()}")
        meta = functions.get(begin) if begin is not None else None
        if meta:
            for c in meta["callers"][:30]:
                caller = "none" if c["function_begin"] is None else f"0x{c['function_begin']:X}"
                lines.append(f"  CALLER {c['kind'].upper()} site=0x{c['site']:X} fn={caller}")
            for s in meta["ascii_refs"][:30]:
                lines.append(f"  STR 0x{s['site']:X} {s['text']!r}")
        for r in rows:
            lines.append(
                f"  STORE site=0x{r['site']:X} {r['field']} width={r['width']} base={r['base']} source={r['source']} form={r['form']} bytes={r['instruction_hex']}"
            )
            lines.append(f"    context_rva=0x{r['context_rva']:X} context={r['context_hex']}")
        lines.append("")
    lines.append("source_hash_unchanged=true game_launched=false save_opened=false progression_written=false")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GAMEOBJECT_IDENTITY_FIELD_STORE_SCAN_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
