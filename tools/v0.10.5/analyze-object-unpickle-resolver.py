"""Trace GoW's native object-reference unpickle/resolution path.

Read-only and version-locked to the supported GoW.exe.  This scan does not
launch the game or open saves.  It inventories code references to the native
pickle/unpickle bookkeeping strings and every direct CALL to the already-proved
GameObject token packer, then archives bounded byte windows for follow-up native
analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SHA256 = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
TOKEN_PACKER_RVA = 0x60B9C0
TARGET_STRINGS = (
    "__prevunpickle",
    "__PickleTable",
    "__SoftPickleTable",
    "__subobjs",
)
IMAGE_SCN_MEM_EXECUTE = 0x20000000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class PE:
    def __init__(self, data: bytes):
        if data[:2] != b"MZ":
            raise RuntimeError("not MZ")
        peoff = struct.unpack_from("<I", data, 0x3C)[0]
        if data[peoff:peoff+4] != b"PE\0\0":
            raise RuntimeError("bad PE")
        nsec = struct.unpack_from("<H", data, peoff + 6)[0]
        optsz = struct.unpack_from("<H", data, peoff + 20)[0]
        opt = peoff + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("not PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        if self.image_base != IMAGE_BASE:
            raise RuntimeError(f"unexpected image base {self.image_base:#x}")
        sec0 = opt + optsz
        self.sections = []
        for i in range(nsec):
            o = sec0 + i * 40
            name = data[o:o+8].split(b"\0", 1)[0].decode("ascii", "replace")
            vsize, rva, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
            ch = struct.unpack_from("<I", data, o + 36)[0]
            self.sections.append({
                "name": name, "vsize": vsize, "rva": rva,
                "rawsize": rawsize, "raw": raw,
                "exec": bool(ch & IMAGE_SCN_MEM_EXECUTE),
            })
        self.data = data

    def file_to_rva(self, off: int) -> int | None:
        for s in self.sections:
            if s["raw"] <= off < s["raw"] + s["rawsize"]:
                return s["rva"] + off - s["raw"]
        return None

    def rva_to_file(self, rva: int) -> int | None:
        for s in self.sections:
            span = max(s["vsize"], s["rawsize"])
            if s["rva"] <= rva < s["rva"] + span:
                d = rva - s["rva"]
                if d < s["rawsize"]:
                    return s["raw"] + d
        return None


def all_occurrences(data: bytes, needle: bytes) -> list[int]:
    out, pos = [], 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            return out
        out.append(pos)
        pos += 1


def window(data: bytes, center: int, radius: int = 192) -> dict:
    lo = max(0, center - radius)
    hi = min(len(data), center + radius)
    return {"file_start": hex(lo), "file_end": hex(hi), "hex": data[lo:hi].hex()}


def riprel_refs(pe: PE, target_va: int) -> list[dict]:
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start, end = s["raw"], min(len(pe.data), s["raw"] + s["rawsize"])
        for disp_off in range(start, end - 3):
            disp = struct.unpack_from("<i", pe.data, disp_off)[0]
            disp_rva = s["rva"] + disp_off - start
            if IMAGE_BASE + disp_rva + 4 + disp != target_va:
                continue
            site_rva = disp_rva
            out.append({
                "disp_file": hex(disp_off),
                "disp_rva": hex(site_rva),
                "section": s["name"],
                "window": window(pe.data, disp_off),
            })
    return out


def direct_call_refs(pe: PE, target_rva: int) -> list[dict]:
    target_va = IMAGE_BASE + target_rva
    out = []
    for s in pe.sections:
        if not s["exec"]:
            continue
        start, end = s["raw"], min(len(pe.data), s["raw"] + s["rawsize"])
        data = pe.data
        for off in range(start, end - 4):
            if data[off] != 0xE8:
                continue
            disp = struct.unpack_from("<i", data, off + 1)[0]
            call_rva = s["rva"] + off - start
            dest = IMAGE_BASE + call_rva + 5 + disp
            if dest == target_va:
                out.append({
                    "call_file": hex(off),
                    "call_rva": hex(call_rva),
                    "section": s["name"],
                    "window": window(data, off),
                })
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
    data = exe.read_bytes()
    pe = PE(data)

    strings = {}
    for name in TARGET_STRINGS:
        hits = all_occurrences(data, name.encode("ascii") + b"\0")
        rows = []
        for off in hits:
            rva = pe.file_to_rva(off)
            if rva is None:
                continue
            rows.append({
                "file": hex(off), "rva": hex(rva), "va": hex(IMAGE_BASE + rva),
                "code_xrefs": riprel_refs(pe, IMAGE_BASE + rva),
            })
        strings[name] = rows

    packer_calls = direct_call_refs(pe, TOKEN_PACKER_RVA)
    after = sha256(exe)
    if after != before:
        raise RuntimeError("GoW.exe changed during scan")

    report = {
        "schema": 1,
        "analysis": "object_unpickle_resolver_trace",
        "exe_sha256": before,
        "token_packer_rva": hex(TOKEN_PACKER_RVA),
        "strings": strings,
        "token_packer_direct_calls": packer_calls,
        "safety": {
            "read_only": True, "game_launched": False, "save_opened": False,
            "progression_written": False, "source_hash_unchanged": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - object unpickle resolver trace",
        f"exe_sha256={before}",
        f"token_packer_direct_calls={len(packer_calls)}",
    ]
    for name, rows in strings.items():
        lines.append(f"{name}.occurrences={len(rows)}")
        for i, row in enumerate(rows):
            lines.append(f"  [{i}] rva={row['rva']} code_xrefs={len(row['code_xrefs'])}")
            for x in row["code_xrefs"]:
                lines.append(f"      xref_rva={x['disp_rva']} section={x['section']}")
    lines.append("")
    lines.append("Direct CALLs to object token packer:")
    for x in packer_calls:
        lines.append(f"  call_rva={x['call_rva']} section={x['section']}")
    lines.append("")
    lines.append("source_hash_unchanged=true game_launched=false save_opened=false progression_written=false")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("OBJECT_UNPICKLE_RESOLVER_SCAN_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
