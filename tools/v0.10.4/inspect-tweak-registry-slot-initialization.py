"""Read-only trace of the global tweak-registry pointer used by Compass ShowMarker.

The pinned GoW.exe validates CompassIconClass names by calling RVA 0x431B90 with:
  RCX = requested name hash
  RDX = qword loaded from global slot RVA 0x22C6948
  R8D = type id (0x11E for CompassIconClass)

This probe identifies exact reads/writes/address-takes of that global slot, nearby
registry-global activity, and caller chains for any function that can initialize
or publish the slot. It never writes into the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
REGISTRY_SLOT_RVA = 0x22C6948
TYPED_LOOKUP_RVA = 0x431B90
COMPASS_TYPE_ID = 0x11E
RESULT = "READ_ONLY_TWEAK_REGISTRY_SLOT_INITIALIZATION_TRACE"


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
            raise ValueError(f"expected exactly one section {name}, got {len(rows)}")
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
        if not (tlo <= target < thi):
            continue
        fn = containing(funcs, target)
        out.append({
            "site_rva": f"0x{site:X}",
            "target_rva": f"0x{target:X}",
            "target_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"
            },
        })
    return out


def callers_of(pe: PE, target_rva: int, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    base = s["rva"]
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = base + i
        if site + 5 + rel != target_rva:
            continue
        fn = containing(funcs, site)
        out.append({
            "site_rva": f"0x{site:X}",
            "containing_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"
            },
        })
    return out


def rip_accesses(pe: PE, target_lo: int, target_hi: int, funcs: list[dict]) -> list[dict]:
    """Recognize common RIP-relative memory instructions and classify direction.

    This is intentionally not a general x64 decoder. It covers MOV/LEA and direct
    immediate stores, which are the relevant forms for a global pointer slot.
    """
    s = pe.section(".text")
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    base = s["rva"]
    out = []
    seen = set()

    def emit(i: int, size: int, target: int, access: str, encoding: str):
        if not (target_lo <= target < target_hi):
            return
        key = (i, size, target, access)
        if key in seen:
            return
        seen.add(key)
        site = base + i
        fn = containing(funcs, site)
        lo = max(0, i - 48)
        hi = min(len(data), i + size + 48)
        out.append({
            "site_rva": f"0x{site:X}",
            "target_rva": f"0x{target:X}",
            "access": access,
            "encoding": encoding,
            "bytes": data[i:i+size].hex().upper(),
            "containing_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"
            },
            "context_start_rva": f"0x{base+lo:X}",
            "context_hex": data[lo:hi].hex().upper(),
        })

    for i in range(len(data) - 10):
        # Optional single REX prefix + MOV/LEA r64,[rip+disp32] / [rip+disp32],r64
        rex = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + rex
        op = data[opi]
        if op in (0x8B, 0x89, 0x8D) and opi + 6 <= len(data):
            modrm = data[opi + 1]
            if (modrm & 0xC7) == 0x05:
                disp = struct.unpack_from("<i", data, opi + 2)[0]
                size = rex + 6
                target = base + i + size + disp
                access = {0x8B: "read", 0x89: "write", 0x8D: "address"}[op]
                emit(i, size, target, access, f"rex={rex} op=0x{op:02X} rip")

        # MOV dword/qword ptr [rip+disp32], imm32. Optional REX.W.
        if data[i] == 0xC7 and data[i+1] == 0x05:
            disp = struct.unpack_from("<i", data, i + 2)[0]
            target = base + i + 10 + disp
            emit(i, 10, target, "write_immediate", "C7 /0 rip imm32")
        if data[i] == 0x48 and data[i+1] == 0xC7 and data[i+2] == 0x05:
            disp = struct.unpack_from("<i", data, i + 3)[0]
            target = base + i + 11 + disp
            emit(i, 11, target, "write_immediate", "REX.W C7 /0 rip imm32")
        if data[i] == 0xC6 and data[i+1] == 0x05:
            disp = struct.unpack_from("<i", data, i + 2)[0]
            target = base + i + 7 + disp
            emit(i, 7, target, "write_immediate", "C6 /0 rip imm8")

    out.sort(key=lambda r: int(r["site_rva"], 16))
    return out


def summarize_function(pe: PE, fn: dict, funcs: list[dict]) -> dict:
    b, e = fn["begin"], fn["end"]
    size = e - b
    head = pe.read_rva(b, min(size, 320))
    refs = rip_accesses(pe, max(0, REGISTRY_SLOT_RVA - 0x100), REGISTRY_SLOT_RVA + 0x108, funcs)
    refs = [r for r in refs if r["containing_function"] and int(r["containing_function"]["begin"], 16) == b]
    strings = []
    # Scan RIP-relative LEA/MOV refs within this function for printable targets.
    data = pe.read_rva(b, size)
    for i in range(max(0, len(data) - 6)):
        rex = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + rex
        if opi + 6 > len(data) or data[opi] not in (0x8B, 0x8D):
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        target = b + i + rex + 6 + disp
        text = pe.ascii_at(target)
        if text is not None:
            strings.append({"site_rva": f"0x{b+i:X}", "target_rva": f"0x{target:X}", "text": text})
    # de-duplicate printable refs
    uniq = []
    keys = set()
    for row in strings:
        key = (row["target_rva"], row["text"])
        if key not in keys:
            keys.add(key)
            uniq.append(row)
    return {
        "begin_rva": f"0x{b:X}", "end_rva": f"0x{e:X}", "bytes": size,
        "hex_head": head.hex().upper(),
        "direct_calls": direct_calls(pe, b, e, funcs),
        "callers": callers_of(pe, b, funcs),
        "near_registry_global_accesses": refs,
        "printable_rip_refs": uniq[:100],
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
        raise ValueError("report must remain outside the game directory")
    digest = sha256(exe)
    if digest != EXPECTED_EXE:
        raise ValueError(f"GoW.exe SHA mismatch: {digest}")

    pe = PE(exe.read_bytes())
    funcs = runtime_functions(pe)
    exact = rip_accesses(pe, REGISTRY_SLOT_RVA, REGISTRY_SLOT_RVA + 1, funcs)
    nearby = rip_accesses(pe, REGISTRY_SLOT_RVA - 0x100, REGISTRY_SLOT_RVA + 0x108, funcs)

    writes = [r for r in exact if r["access"].startswith("write")]
    addresses = [r for r in exact if r["access"] == "address"]
    reads = [r for r in exact if r["access"] == "read"]

    owner_begins = []
    for row in writes + addresses:
        fn = row["containing_function"]
        if fn is not None:
            b = int(fn["begin"], 16)
            if b not in owner_begins:
                owner_begins.append(b)

    owners = []
    for b in owner_begins:
        fn = containing(funcs, b)
        if fn is not None:
            owners.append(summarize_function(pe, fn, funcs))

    # If the exact slot is only ever read, rank functions that write/address-take
    # nearby globals; the actual singleton may be published through a neighboring
    # owner structure and copied/initialized indirectly.
    nearby_candidate_begins = []
    for row in nearby:
        if row["access"] not in ("write", "write_immediate", "address"):
            continue
        fn = row["containing_function"]
        if fn is None:
            continue
        b = int(fn["begin"], 16)
        if b not in nearby_candidate_begins:
            nearby_candidate_begins.append(b)
    nearby_owners = []
    for b in nearby_candidate_begins[:40]:
        fn = containing(funcs, b)
        if fn is not None:
            nearby_owners.append(summarize_function(pe, fn, funcs))

    try:
        slot_file_value = f"0x{struct.unpack('<Q', pe.read_rva(REGISTRY_SLOT_RVA, 8))[0]:X}"
    except Exception:
        slot_file_value = None

    conclusion = "REGISTRY_SLOT_DIRECT_INITIALIZER_LOCATED" if writes or addresses else "REGISTRY_SLOT_HAS_NO_DIRECT_STATIC_WRITE_OR_ADDRESS_TAKE"
    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "registry_slot": {
            "rva": f"0x{REGISTRY_SLOT_RVA:X}",
            "file_qword": slot_file_value,
            "typed_lookup_rva": f"0x{TYPED_LOOKUP_RVA:X}",
            "compass_type_id": f"0x{COMPASS_TYPE_ID:X}",
            "exact_access_count": len(exact),
            "reads": len(reads),
            "writes": len(writes),
            "address_takes": len(addresses),
            "accesses": exact,
        },
        "nearby_global_window": {
            "start_rva": f"0x{REGISTRY_SLOT_RVA - 0x100:X}",
            "end_rva": f"0x{REGISTRY_SLOT_RVA + 0x108:X}",
            "access_count": len(nearby),
            "accesses": nearby,
        },
        "direct_initializer_or_address_owner_functions": owners,
        "nearby_write_or_address_owner_functions": nearby_owners,
        "conclusion": conclusion,
        "next_gate": (
            "If a direct owner is found, trace its caller/startup chain and identify the DCB/tweak loader that publishes the registry. "
            "If the slot is read-only in .text, inspect the owning nearby singleton/global initialization path and static constructor tables. "
            "Do not bypass ShowMarker validation, patch GoW.exe, or mutate DCBs until the registry population path is proven."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(RESULT)
    print(f"  registry slot: 0x{REGISTRY_SLOT_RVA:X}")
    print(f"  exact accesses: {len(exact)} (reads={len(reads)} writes={len(writes)} address={len(addresses)})")
    print(f"  direct owner functions: {len(owners)}")
    print(f"  nearby owner functions: {len(nearby_owners)}")
    print(f"  conclusion: {conclusion}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
