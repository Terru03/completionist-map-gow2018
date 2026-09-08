"""Read-only trace of the native tweak-registry pointer transfer feeding Compass ShowMarker.

The v0.10.4 registry-slot initialization scan located the only direct writer of
ShowMarker's shared typed-tweak registry slot (RVA 0x22C6948) inside function
0x67C800-0x67CBEB.  The transfer sequence is:

    mov rbx, [rip + source]      ; source resolves to 0x12390E0
    mov [0x22C6948], rbx
    mov [source], rbp            ; rbp is zeroed at function entry
    mov [0x2018928], rbx         ; second published alias

This probe verifies that sequence byte-for-byte and follows the source/alias
slots to the functions that populate, clear, or consume them.  It also records
callers/callees and nearby printable-string references for the ownership path.
It never opens the running process and never writes inside the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
OWNER_BEGIN = 0x67C800
OWNER_END = 0x67CBEB
TRANSFER_RVA = 0x67C969
SOURCE_SLOT = 0x12390E0
REGISTRY_SLOT = 0x22C6948
ALIAS_SLOT = 0x2018928
CALLER_SITE = 0x683173
RESULT = "READ_ONLY_TWEAK_REGISTRY_TRANSFER_SOURCE_TRACE"


class PE:
    def __init__(self, raw: bytes):
        self.raw = raw
        if raw[:2] != b"MZ":
            raise ValueError("not an MZ executable")
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[pe:pe+4] != b"PE\0\0":
            raise ValueError("missing PE signature")
        count = struct.unpack_from("<H", raw, pe + 6)[0]
        optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
        optional = pe + 24
        if struct.unpack_from("<H", raw, optional)[0] != 0x20B:
            raise ValueError("expected PE32+")
        self.image_base = struct.unpack_from("<Q", raw, optional + 24)[0]
        if self.image_base != IMAGE_BASE:
            raise ValueError(f"unexpected image base {self.image_base:#x}")
        self.sections = []
        table = optional + optional_size
        for i in range(count):
            o = table + i * 40
            name = raw[o:o+8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, rva, raw_size, raw_ptr = struct.unpack_from("<IIII", raw, o + 8)
            self.sections.append({"name": name, "virtual_size": virtual_size,
                                  "rva": rva, "raw_size": raw_size, "raw_ptr": raw_ptr})

    def section(self, name: str) -> dict:
        rows = [s for s in self.sections if s["name"] == name]
        if len(rows) != 1:
            raise ValueError(f"expected one {name} section, got {len(rows)}")
        return rows[0]

    def rva_to_offset(self, rva: int) -> int:
        for s in self.sections:
            span = max(s["virtual_size"], s["raw_size"])
            if s["rva"] <= rva < s["rva"] + span:
                delta = rva - s["rva"]
                if delta >= s["raw_size"]:
                    raise ValueError(f"RVA {rva:#x} is not file-backed")
                return s["raw_ptr"] + delta
        raise ValueError(f"RVA {rva:#x} outside file-backed sections")

    def read_rva(self, rva: int, size: int) -> bytes:
        off = self.rva_to_offset(rva)
        data = self.raw[off:off+size]
        if len(data) != size:
            raise ValueError("short read")
        return data

    def ascii_at(self, rva: int, max_len: int = 200) -> str | None:
        try:
            off = self.rva_to_offset(rva)
        except ValueError:
            return None
        blob = self.raw[off:min(len(self.raw), off + max_len)]
        nul = blob.find(b"\0")
        if nul >= 0:
            blob = blob[:nul]
        if len(blob) < 4 or any(b < 0x20 or b > 0x7E for b in blob):
            return None
        return blob.decode("ascii", "replace")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def runtime_functions(pe: PE) -> list[dict]:
    s = pe.section(".pdata")
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    rows = []
    for o in range(0, len(data) - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", data, o)
        if begin and begin < end:
            rows.append({"begin": begin, "end": end, "unwind": unwind})
    rows.sort(key=lambda r: r["begin"])
    return rows


def containing(funcs: list[dict], rva: int) -> dict | None:
    found = None
    for row in funcs:
        if row["begin"] > rva:
            break
        if row["begin"] <= rva < row["end"]:
            found = row
    return found


def function_row(fn: dict | None) -> dict | None:
    if fn is None:
        return None
    return {"begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"}


def direct_calls(pe: PE, begin: int, end: int, funcs: list[dict]) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    text = pe.section(".text")
    tlo, thi = text["rva"], text["rva"] + max(text["virtual_size"], text["raw_size"])
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = begin + i
        target = site + 5 + rel
        if tlo <= target < thi:
            out.append({"site_rva": f"0x{site:X}", "target_rva": f"0x{target:X}",
                        "target_function": function_row(containing(funcs, target))})
    return out


def callers_of(pe: PE, target_rva: int, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    begin = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = begin + i
        if site + 5 + rel == target_rva:
            out.append({"site_rva": f"0x{site:X}",
                        "containing_function": function_row(containing(funcs, site))})
    return out


def ascii_rip_refs(pe: PE, begin: int, end: int) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    out = []
    for i in range(len(data) - 6):
        prefix = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + prefix
        if opi + 6 > len(data):
            continue
        opcode = data[opi]
        if opcode not in (0x8B, 0x8D):
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        size = prefix + 6
        site = begin + i
        target = site + size + disp
        text = pe.ascii_at(target)
        if text is not None:
            out.append({"site_rva": f"0x{site:X}", "target_rva": f"0x{target:X}",
                        "text": text})
    return out


def slot_accesses(pe: PE, target_rva: int, funcs: list[dict]) -> list[dict]:
    """Find common RIP-relative read/write/address accesses to one global slot."""
    s = pe.section(".text")
    begin = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    out = []
    seen = set()
    for i in range(len(data) - 10):
        prefix = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + prefix
        opcode = data[opi]
        # MOV/LEA r64,[rip+disp] or MOV [rip+disp],r64
        if opcode in (0x8B, 0x89, 0x8D) and opi + 6 <= len(data):
            modrm = data[opi + 1]
            if (modrm & 0xC7) == 0x05:
                disp = struct.unpack_from("<i", data, opi + 2)[0]
                size = prefix + 6
                site = begin + i
                target = site + size + disp
                if target == target_rva:
                    access = "read" if opcode == 0x8B else "write" if opcode == 0x89 else "address"
                    key = (site, access)
                    if key not in seen:
                        seen.add(key)
                        lo = max(0, i - 40); hi = min(len(data), i + size + 40)
                        out.append({"site_rva": f"0x{site:X}", "access": access,
                                    "bytes": data[i:i+size].hex().upper(),
                                    "containing_function": function_row(containing(funcs, site)),
                                    "context_start_rva": f"0x{begin+lo:X}",
                                    "context_hex": data[lo:hi].hex().upper()})
        # C7 /0 [rip+disp], imm32
        if opcode == 0xC7 and opi + 10 <= len(data):
            modrm = data[opi + 1]
            if (modrm & 0xC7) == 0x05 and ((modrm >> 3) & 7) == 0:
                disp = struct.unpack_from("<i", data, opi + 2)[0]
                size = prefix + 10
                site = begin + i
                target = site + prefix + 6 + disp
                if target == target_rva:
                    imm = struct.unpack_from("<I", data, opi + 6)[0]
                    key = (site, "write_immediate")
                    if key not in seen:
                        seen.add(key)
                        out.append({"site_rva": f"0x{site:X}", "access": "write_immediate",
                                    "immediate": f"0x{imm:X}",
                                    "containing_function": function_row(containing(funcs, site))})
    return out


def summarize_owners(pe: PE, accesses: list[dict], funcs: list[dict]) -> list[dict]:
    uniq = {}
    for a in accesses:
        fn = a["containing_function"]
        if not fn:
            continue
        begin = int(fn["begin"], 16); end = int(fn["end"], 16)
        uniq[(begin, end)] = (begin, end)
    rows = []
    for begin, end in sorted(uniq.values()):
        rows.append({
            "begin_rva": f"0x{begin:X}", "end_rva": f"0x{end:X}", "bytes": end - begin,
            "slot_accesses": [a for a in accesses if a["containing_function"] and int(a["containing_function"]["begin"],16) == begin],
            "callers": callers_of(pe, begin, funcs),
            "direct_calls": direct_calls(pe, begin, end, funcs),
            "ascii_rip_refs": ascii_rip_refs(pe, begin, end)[:100],
            "hex_head": pe.read_rva(begin, min(192, end-begin)).hex().upper(),
        })
    return rows


def qword_at(pe: PE, rva: int) -> str | None:
    try:
        return f"0x{struct.unpack('<Q', pe.read_rva(rva, 8))[0]:X}"
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    exe = game / "GoW.exe"
    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("report must remain outside the game directory")
    if not exe.is_file():
        raise FileNotFoundError(exe)
    digest = sha256(exe)
    if digest != EXPECTED_EXE:
        raise ValueError(f"GoW.exe SHA mismatch: {digest}")

    pe = PE(exe.read_bytes())
    funcs = runtime_functions(pe)
    owner = containing(funcs, OWNER_BEGIN)
    if owner is None or owner["begin"] != OWNER_BEGIN or owner["end"] != OWNER_END:
        raise ValueError("registry owner function bounds changed")

    # Verify the exact four-instruction pointer handoff. RBP is proven zeroed by
    # `33 ED` near function entry before this sequence.
    transfer = pe.read_rva(TRANSFER_RVA, 28)
    expected_prefix = bytes.fromhex("488B1D70C7BB0048891DD19FC40148892D62C7BB0048891DA3BF9901")
    if transfer != expected_prefix:
        raise ValueError(f"registry transfer bytes changed: {transfer.hex().upper()}")

    def rip_target(site: int, insn: bytes) -> int:
        disp = struct.unpack_from("<i", insn, 3)[0]
        return site + 7 + disp

    src = rip_target(TRANSFER_RVA, transfer[0:7])
    dst = rip_target(TRANSFER_RVA+7, transfer[7:14])
    clear = rip_target(TRANSFER_RVA+14, transfer[14:21])
    alias = rip_target(TRANSFER_RVA+21, transfer[21:28])
    if (src, dst, clear, alias) != (SOURCE_SLOT, REGISTRY_SLOT, SOURCE_SLOT, ALIAS_SLOT):
        raise ValueError(f"unexpected transfer targets: {src:#x},{dst:#x},{clear:#x},{alias:#x}")

    # Function entry contains `33 ED` before the first global publication, making
    # the later `mov [source], rbp` a zero/NULL clear in this path.
    owner_head = pe.read_rva(OWNER_BEGIN, 0x40)
    rbp_zeroed = b"\x33\xED" in owner_head

    source_access = slot_accesses(pe, SOURCE_SLOT, funcs)
    alias_access = slot_accesses(pe, ALIAS_SLOT, funcs)
    registry_access = slot_accesses(pe, REGISTRY_SLOT, funcs)

    caller_fn = containing(funcs, CALLER_SITE)
    caller_summary = None
    if caller_fn:
        caller_summary = {
            "call_site_rva": f"0x{CALLER_SITE:X}",
            "function": function_row(caller_fn),
            "direct_calls": direct_calls(pe, caller_fn["begin"], caller_fn["end"], funcs),
            "ascii_rip_refs": ascii_rip_refs(pe, caller_fn["begin"], caller_fn["end"])[:120],
            "hex_around_call": pe.read_rva(CALLER_SITE-64, 128).hex().upper(),
        }

    source_writers = [a for a in source_access if a["access"].startswith("write")]
    alias_writers = [a for a in alias_access if a["access"].startswith("write")]

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "transfer": {
            "owner_function": {"begin_rva": f"0x{OWNER_BEGIN:X}", "end_rva": f"0x{OWNER_END:X}"},
            "transfer_rva": f"0x{TRANSFER_RVA:X}",
            "bytes": transfer.hex().upper(),
            "source_slot_rva": f"0x{SOURCE_SLOT:X}",
            "registry_slot_rva": f"0x{REGISTRY_SLOT:X}",
            "source_clear_slot_rva": f"0x{SOURCE_SLOT:X}",
            "published_alias_slot_rva": f"0x{ALIAS_SLOT:X}",
            "rbp_zeroed_before_transfer": rbp_zeroed,
            "semantic": "pointer is moved from source slot into ShowMarker typed registry slot, source is cleared, same pointer is published to alias slot",
        },
        "static_file_values": {
            "source_slot": qword_at(pe, SOURCE_SLOT),
            "registry_slot": qword_at(pe, REGISTRY_SLOT),
            "alias_slot": qword_at(pe, ALIAS_SLOT),
        },
        "source_slot": {
            "rva": f"0x{SOURCE_SLOT:X}",
            "access_count": len(source_access),
            "writer_count": len(source_writers),
            "accesses": source_access,
            "owner_functions": summarize_owners(pe, source_access, funcs),
        },
        "published_alias_slot": {
            "rva": f"0x{ALIAS_SLOT:X}",
            "access_count": len(alias_access),
            "writer_count": len(alias_writers),
            "accesses": alias_access,
            "owner_functions": summarize_owners(pe, alias_access, funcs),
        },
        "registry_slot_crosscheck": {
            "rva": f"0x{REGISTRY_SLOT:X}",
            "access_count": len(registry_access),
            "writes": [a for a in registry_access if a["access"].startswith("write")],
        },
        "registry_owner": {
            "callers": callers_of(pe, OWNER_BEGIN, funcs),
            "direct_calls": direct_calls(pe, OWNER_BEGIN, OWNER_END, funcs),
            "ascii_rip_refs": ascii_rip_refs(pe, OWNER_BEGIN, OWNER_END)[:160],
        },
        "known_owner_caller": caller_summary,
        "conclusion": "REGISTRY_POINTER_TRANSFER_SOURCE_TRACED",
        "next_gate": (
            "Use the source-slot writer ownership to identify the native tweak/WAD loader object that constructs the registry before RVA 0x67C800 transfers it. "
            "Then trace how DCB exports are inserted into that object and why the packed CompletionistRaven export is absent. Do not patch GoW.exe, bypass ShowMarker, or mutate additional DCBs yet."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  transfer: 0x{SOURCE_SLOT:X} -> 0x{REGISTRY_SLOT:X}, clear source, alias -> 0x{ALIAS_SLOT:X}")
    print(f"  source accesses: {len(source_access)}; writers: {len(source_writers)}")
    print(f"  alias accesses: {len(alias_access)}; writers: {len(alias_writers)}")
    print(f"  owner callers: {len(callers_of(pe, OWNER_BEGIN, funcs))}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
