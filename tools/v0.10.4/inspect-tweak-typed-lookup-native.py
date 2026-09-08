"""Read-only trace of the native typed lookup used by LuaCompass::ShowMarker.

The pinned GoW.exe ShowMarker wrapper computes the requested marker-class hash,
loads type id 0x11E (CompassIconClass), loads a global registry pointer and calls
RVA 0x431B90. A null return takes the exact "trying to set invalid type" path.

This probe follows that lookup without touching the game: it inventories the
0x431B90 function, every direct call site to it, the type-id immediates and
registry globals supplied by those callers, and all common RIP-relative xrefs
to ShowMarker's registry slot. The purpose is to identify the runtime registry
/cache ownership that a valid authored CompassIconClass must enter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SHOWMARKER_RVA = 0x94FF80
SHOWMARKER_LOOKUP_CALL = 0x9500AE
TYPED_LOOKUP_RVA = 0x431B90
COMPASS_TYPE_ID = 0x11E
REGISTRY_SLOT_RVA = 0x22C6948
RESULT = "READ_ONLY_NATIVE_TYPED_TWEAK_LOOKUP_TRACE"


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
        raise ValueError(f"RVA {rva:#x} outside sections")

    def read_rva(self, rva: int, size: int) -> bytes:
        off = self.rva_to_offset(rva)
        data = self.raw[off:off+size]
        if len(data) != size:
            raise ValueError("short read")
        return data

    def ascii_at(self, rva: int, max_len: int = 160) -> str | None:
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
    lo, hi = text["rva"], text["rva"] + max(text["virtual_size"], text["raw_size"])
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = begin + i
        target = site + 5 + rel
        if not (lo <= target < hi):
            continue
        fn = containing(funcs, target)
        out.append({"site_rva": f"0x{site:X}", "target_rva": f"0x{target:X}",
                    "target_function": None if fn is None else {
                        "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"}})
    return out


def rip_refs(pe: PE, begin: int, end: int) -> list[dict]:
    """Decode common RIP-relative MOV/LEA forms (enough for static xref ownership)."""
    data = pe.read_rva(begin, end - begin)
    out = []
    for i in range(len(data) - 6):
        prefix = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + prefix
        if opi + 6 > len(data):
            continue
        opcode = data[opi]
        if opcode not in (0x8B, 0x89, 0x8D):
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        size = prefix + 6
        site = begin + i
        target = site + size + disp
        row = {"site_rva": f"0x{site:X}", "bytes": data[i:i+size].hex().upper(),
               "opcode": f"0x{opcode:02X}", "target_rva": f"0x{target:X}"}
        text = pe.ascii_at(target)
        if text is not None:
            row["ascii"] = text
        try:
            q = struct.unpack("<Q", pe.read_rva(target, 8))[0]
            row["file_qword"] = f"0x{q:X}"
        except Exception:
            pass
        out.append(row)
    return out


def all_text_callers(pe: PE, target_rva: int, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    begin = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    rows = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        site = begin + i
        rel = struct.unpack_from("<i", data, i + 1)[0]
        target = site + 5 + rel
        if target != target_rva:
            continue
        fn = containing(funcs, site)
        lo = max(0, i - 48)
        hi = min(len(data), i + 24)
        context = data[lo:hi]
        context_rva = begin + lo

        # The common call convention in this engine uses `41 B8 imm32` for R8D
        # and `48 8B 15 disp32` for RDX from a global slot. Decode the nearest
        # instances before the call, without pretending this is a full x64 decoder.
        type_ids = []
        registry_loads = []
        for j in range(max(0, i - 48), i):
            if j + 6 <= len(data) and data[j:j+2] == b"\x41\xB8":
                imm = struct.unpack_from("<I", data, j + 2)[0]
                type_ids.append({"site_rva": f"0x{begin+j:X}", "value": f"0x{imm:X}"})
            if j + 7 <= len(data) and data[j:j+3] == b"\x48\x8B\x15":
                disp = struct.unpack_from("<i", data, j + 3)[0]
                insn_rva = begin + j
                slot = insn_rva + 7 + disp
                registry_loads.append({"site_rva": f"0x{insn_rva:X}",
                                       "slot_rva": f"0x{slot:X}"})
        rows.append({
            "call_site_rva": f"0x{site:X}",
            "containing_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"},
            "context_start_rva": f"0x{context_rva:X}",
            "context_hex": context.hex().upper(),
            "nearby_r8d_type_immediates": type_ids,
            "nearby_rdx_registry_loads": registry_loads,
        })
    return rows


def all_text_rip_xrefs(pe: PE, target_rva: int, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    begin = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    rows = []
    for i in range(len(data) - 6):
        prefix = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + prefix
        if opi + 6 > len(data):
            continue
        opcode = data[opi]
        if opcode not in (0x8B, 0x89, 0x8D):
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        size = prefix + 6
        site = begin + i
        target = site + size + disp
        if target != target_rva:
            continue
        fn = containing(funcs, site)
        lo = max(0, i - 40)
        hi = min(len(data), i + size + 40)
        rows.append({
            "site_rva": f"0x{site:X}",
            "bytes": data[i:i+size].hex().upper(),
            "opcode": f"0x{opcode:02X}",
            "containing_function": None if fn is None else {
                "begin": f"0x{fn['begin']:X}", "end": f"0x{fn['end']:X}"},
            "context_start_rva": f"0x{begin+lo:X}",
            "context_hex": data[lo:hi].hex().upper(),
        })
    return rows


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

    raw = exe.read_bytes()
    pe = PE(raw)
    funcs = runtime_functions(pe)
    lookup_fn = containing(funcs, TYPED_LOOKUP_RVA)
    if lookup_fn is None or lookup_fn["begin"] != TYPED_LOOKUP_RVA:
        raise ValueError("typed lookup function boundary not recovered as expected")

    # Prove the exact fixed instruction sequence in ShowMarker:
    # 41 B8 1E010000                 mov r8d,0x11e
    # 48 8B 15 <disp32>              mov rdx,[rip+registry_slot]
    # 48 8B CE                       mov rcx,rsi  (computed requested class hash)
    # E8 <rel32 to 0x431B90>         call typed lookup
    show = pe.read_rva(0x95009E, 0x15)
    if show[:6] != b"\x41\xB8\x1E\x01\x00\x00":
        raise ValueError("ShowMarker no longer loads R8D=0x11E at expected site")
    if show[6:9] != b"\x48\x8B\x15":
        raise ValueError("ShowMarker registry load encoding changed")
    disp = struct.unpack_from("<i", show, 9)[0]
    slot = 0x9500A4 + 7 + disp
    if slot != REGISTRY_SLOT_RVA:
        raise ValueError(f"unexpected ShowMarker registry slot {slot:#x}")
    if show[13:16] != b"\x48\x8B\xCE":
        raise ValueError("ShowMarker RCX hash move changed")
    if show[16] != 0xE8:
        raise ValueError("ShowMarker typed lookup call encoding changed")
    rel = struct.unpack_from("<i", show, 17)[0]
    call_target = 0x9500AE + 5 + rel
    if call_target != TYPED_LOOKUP_RVA:
        raise ValueError(f"unexpected typed lookup target {call_target:#x}")

    lookup_begin, lookup_end = lookup_fn["begin"], lookup_fn["end"]
    callers = all_text_callers(pe, TYPED_LOOKUP_RVA, funcs)
    global_xrefs = all_text_rip_xrefs(pe, REGISTRY_SLOT_RVA, funcs)

    # Summarize caller type IDs/registry slots so we can determine whether
    # 0x431B90 is a generic type-aware authored-resource lookup.
    type_values = sorted({x["value"] for c in callers for x in c["nearby_r8d_type_immediates"]})
    registry_slots = sorted({x["slot_rva"] for c in callers for x in c["nearby_rdx_registry_loads"]})

    file_slot = None
    try:
        q = struct.unpack("<Q", pe.read_rva(REGISTRY_SLOT_RVA, 8))[0]
        file_slot = {"qword": f"0x{q:X}"}
    except Exception as exc:
        file_slot = {"file_backed": False, "reason": f"{type(exc).__name__}: {exc}"}

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "showmarker_validation_call": {
            "type_load_rva": "0x95009E",
            "type_id": "0x11E",
            "registry_load_rva": "0x9500A4",
            "registry_slot_rva": f"0x{REGISTRY_SLOT_RVA:X}",
            "name_hash_move_rva": "0x9500AB",
            "lookup_call_rva": f"0x{SHOWMARKER_LOOKUP_CALL:X}",
            "lookup_target_rva": f"0x{TYPED_LOOKUP_RVA:X}",
            "null_return_branches_to_invalid_type": True,
            "fixed_sequence_hex": show.hex().upper(),
        },
        "typed_lookup_function": {
            "begin_rva": f"0x{lookup_begin:X}",
            "end_rva": f"0x{lookup_end:X}",
            "bytes": lookup_end - lookup_begin,
            "unwind_rva": f"0x{lookup_fn['unwind']:X}",
            "full_hex": pe.read_rva(lookup_begin, lookup_end - lookup_begin).hex().upper(),
            "direct_calls": direct_calls(pe, lookup_begin, lookup_end, funcs),
            "rip_relative_refs": rip_refs(pe, lookup_begin, lookup_end),
        },
        "typed_lookup_callers": {
            "count": len(callers),
            "distinct_nearby_r8d_type_immediates": type_values,
            "distinct_nearby_rdx_registry_slots": registry_slots,
            "rows": callers,
        },
        "showmarker_registry_slot": {
            "rva": f"0x{REGISTRY_SLOT_RVA:X}",
            "file_value": file_slot,
            "text_xref_count": len(global_xrefs),
            "text_xrefs": global_xrefs,
        },
        "conclusion": "SHOWMARKER_VALIDATES_VIA_NATIVE_TYPED_REGISTRY_LOOKUP",
        "next_gate": (
            "Disassemble/trace RVA 0x431B90 and the functions that write or initialize registry slot 0x22C6948. "
            "Identify the authored loader/index that populates type 0x11E entries. Do not bypass ShowMarker validation, "
            "do not patch GoW.exe, and do not mutate another DCB until this registry ownership is proven."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(RESULT)
    print(f"  lookup function: 0x{lookup_begin:X}-0x{lookup_end:X}")
    print(f"  typed lookup callers: {len(callers)}")
    print(f"  distinct nearby type IDs: {', '.join(type_values) if type_values else '(none)'}")
    print(f"  registry slot xrefs: {len(global_xrefs)}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
