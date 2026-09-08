"""Read-only semantic trace of the R_Perm registry connect path.

The prior direct-call tracer correctly found `0x421040 -> 0x41F640`, but the
reached write to tweak-registry source slot 0x12390E0 is not a population:
0x41F640 begins with `xor edi,edi` and stores zero to several globals,
including 0x12390E0. This probe separates proven source-slot clears from
potential population writes and inventories indirect/vtable calls in the
R_Perm connect function and its immediate callees.

Nothing in the game directory, executable, DCBs, saves, progression, or marker
state is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SOURCE_SLOT = 0x12390E0
REGISTRY_SLOT = 0x22C6948
RPERM_CONNECT = 0x421040
RPERM_CALL_SITE = 0x67C952
ZERO_HELPER = 0x41F640
ZERO_WRITE_SITE = 0x41F66A
TRANSFER_OWNER = 0x67C800
TRANSFER_CLEAR_SITE = 0x67C977
RESULT = "READ_ONLY_R_PERM_INDIRECT_POPULATION_TRACE"

REG_NAMES = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]


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
                d = rva - s["rva"]
                if d >= s["raw_size"]:
                    raise ValueError(f"RVA {rva:#x} is not file-backed")
                return s["raw_ptr"] + d
        raise ValueError(f"RVA {rva:#x} outside sections")

    def read_rva(self, rva: int, size: int) -> bytes:
        o = self.rva_to_offset(rva)
        data = self.raw[o:o+size]
        if len(data) != size:
            raise ValueError("short read")
        return data

    def ascii_at(self, rva: int, max_len: int = 192) -> str | None:
        try:
            o = self.rva_to_offset(rva)
        except ValueError:
            return None
        blob = self.raw[o:min(len(self.raw), o + max_len)]
        nul = blob.find(b"\0")
        if nul >= 0:
            blob = blob[:nul]
        if len(blob) < 3 or any(b < 0x20 or b > 0x7E for b in blob):
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
    lo, hi = 0, len(funcs)
    while lo < hi:
        mid = (lo + hi) // 2
        if funcs[mid]["begin"] <= rva:
            lo = mid + 1
        else:
            hi = mid
    for i in range(min(lo - 1, len(funcs) - 1), max(-1, lo - 4), -1):
        if i >= 0 and funcs[i]["begin"] <= rva < funcs[i]["end"]:
            return funcs[i]
    return None


def fn_by_begin(funcs: list[dict], begin: int) -> dict:
    fn = next((f for f in funcs if f["begin"] == begin), None)
    if fn is None:
        raise ValueError(f"runtime function not found at {begin:#x}")
    return fn


def direct_calls(pe: PE, funcs: list[dict], begin: int, end: int) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    text = pe.section(".text")
    lo = text["rva"]
    hi = lo + max(text["virtual_size"], text["raw_size"])
    rows = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        site = begin + i
        target = site + 5 + rel
        if not (lo <= target < hi):
            continue
        target_fn = containing(funcs, target)
        rows.append({
            "site_rva": f"0x{site:X}",
            "target_rva": f"0x{target:X}",
            "target_function_begin_rva": None if target_fn is None else f"0x{target_fn['begin']:X}",
        })
    return rows


def indirect_calls(pe: PE, begin: int, end: int) -> list[dict]:
    """Conservative byte scan for x64 FF /2 CALL r/m64 forms.

    This is intentionally reported as heuristic evidence because no full decoder is
    assumed to be installed. RIP-relative targets are resolved exactly where present.
    """
    data = pe.read_rva(begin, end - begin)
    rows = []
    seen = set()
    for i in range(len(data) - 2):
        # Treat optional REX as part of candidate instruction.
        p = i
        rex = None
        if 0x40 <= data[p] <= 0x4F:
            rex = data[p]
            p += 1
        if p + 1 >= len(data) or data[p] != 0xFF:
            continue
        modrm = data[p + 1]
        reg_field = (modrm >> 3) & 7
        if reg_field != 2:  # CALL r/m64
            continue
        mod = (modrm >> 6) & 3
        rm = modrm & 7
        site = begin + i
        if site in seen:
            continue
        seen.add(site)
        row = {
            "site_rva": f"0x{site:X}",
            "rex": None if rex is None else f"0x{rex:02X}",
            "mod": mod,
            "rm": rm,
            "kind": "register" if mod == 3 else "memory",
            "context_start_rva": f"0x{max(begin, site-16):X}",
        }
        c0 = max(0, i - 16)
        c1 = min(len(data), i + 20)
        row["context_hex"] = data[c0:c1].hex().upper()
        # Exact RIP-relative FF 15 disp32.
        if mod == 0 and rm == 5 and p + 6 <= len(data):
            disp = struct.unpack_from("<i", data, p + 2)[0]
            size = (1 if rex is not None else 0) + 6
            target_slot = site + size + disp
            row["kind"] = "rip_memory"
            row["rip_target_slot_rva"] = f"0x{target_slot:X}"
        rows.append(row)
    return rows


def source_slot_writes(pe: PE, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    base = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    rows = []
    seen = set()
    for i in range(len(data) - 7):
        rex = None
        p = i
        if 0x40 <= data[p] <= 0x4F:
            rex = data[p]
            p += 1
        if p + 6 > len(data) or data[p] != 0x89:
            continue
        modrm = data[p+1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, p + 2)[0]
        size = (1 if rex is not None else 0) + 6
        site = base + i
        target = site + size + disp
        if target != SOURCE_SLOT:
            continue
        # Drop overlap beginning on opcode byte of a REX-prefixed instruction.
        if rex is None and i > 0 and 0x40 <= data[i-1] <= 0x4F:
            prev_modrm = data[i+1]
            if (prev_modrm & 0xC7) == 0x05:
                prev_disp = struct.unpack_from("<i", data, i+2)[0]
                prev_site = base + i - 1
                if prev_site + 7 + prev_disp == SOURCE_SLOT:
                    continue
        if site in seen:
            continue
        seen.add(site)
        reg = (modrm >> 3) & 7
        if rex is not None and (rex & 0x04):
            reg += 8
        owner = containing(funcs, site)
        rows.append({
            "site": site,
            "site_rva": f"0x{site:X}",
            "source_register": REG_NAMES[reg],
            "owner": None if owner is None else owner["begin"],
            "owner_rva": None if owner is None else f"0x{owner['begin']:X}",
            "bytes": data[i:i+size].hex().upper(),
        })
    return rows


def classify_write(pe: PE, funcs: list[dict], row: dict) -> dict:
    site = row["site"]
    owner = row["owner"]
    classification = "potential_population_or_unknown"
    proof = None

    # Two clears already proven from exact static context.
    if site == ZERO_WRITE_SITE and owner == ZERO_HELPER and row["source_register"] == "rdi":
        fn = fn_by_begin(funcs, ZERO_HELPER)
        head = pe.read_rva(fn["begin"], min(48, fn["end"] - fn["begin"]))
        if b"\x33\xFF" not in head[:24]:
            raise ValueError("0x41F640 no longer proves xor edi,edi before source-slot store")
        classification = "proven_zero_clear"
        proof = "0x41F640 executes xor edi,edi before storing RDI to 0x12390E0"
    elif site == TRANSFER_CLEAR_SITE and owner == TRANSFER_OWNER and row["source_register"] == "rbp":
        fn = fn_by_begin(funcs, TRANSFER_OWNER)
        head = pe.read_rva(fn["begin"], min(48, fn["end"] - fn["begin"]))
        if b"\x33\xED" in head[:32]:
            classification = "proven_zero_clear"
            proof = "transfer owner zeroes EBP/RBP before clearing 0x12390E0 after publication"
    elif site == 0x675988 and row["source_register"] == "rbx":
        # Context is exact and immediate: 33 DB ; 48 89 1D <disp32>
        before = pe.read_rva(site - 2, 2)
        if before == b"\x33\xDB":
            classification = "proven_zero_clear"
            proof = "immediate xor ebx,ebx directly precedes the source-slot store"

    return {
        "site_rva": row["site_rva"],
        "owner_rva": row["owner_rva"],
        "source_register": row["source_register"],
        "classification": classification,
        "proof": proof,
    }


def function_report(pe: PE, funcs: list[dict], begin: int) -> dict:
    fn = fn_by_begin(funcs, begin)
    data = pe.read_rva(fn["begin"], fn["end"] - fn["begin"])
    return {
        "begin_rva": f"0x{fn['begin']:X}",
        "end_rva": f"0x{fn['end']:X}",
        "bytes": len(data),
        "full_hex": data.hex().upper(),
        "direct_calls": direct_calls(pe, funcs, fn["begin"], fn["end"]),
        "heuristic_indirect_calls": indirect_calls(pe, fn["begin"], fn["end"]),
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
    if not exe.is_file():
        raise FileNotFoundError(exe)
    digest = sha256(exe)
    if digest != EXPECTED_EXE:
        raise ValueError(f"GoW.exe SHA mismatch: {digest}")

    pe = PE(exe.read_bytes())
    funcs = runtime_functions(pe)

    # Re-prove call site is R_Perm with EDX=0 immediately before the call.
    call = pe.read_rva(RPERM_CALL_SITE, 5)
    if call[0] != 0xE8:
        raise ValueError("R_Perm connect call encoding changed")
    rel = struct.unpack_from("<i", call, 1)[0]
    if RPERM_CALL_SITE + 5 + rel != RPERM_CONNECT:
        raise ValueError("R_Perm connect target changed")
    arg_window = pe.read_rva(RPERM_CALL_SITE - 9, 9)
    # Expected: 33 D2 ; 48 8D 0D disp32
    if arg_window[:2] != b"\x33\xD2" or arg_window[2:5] != b"\x48\x8D\x0D":
        raise ValueError("R_Perm call argument setup changed")
    disp = struct.unpack_from("<i", arg_window, 5)[0]
    string_rva = (RPERM_CALL_SITE - 7) + 7 + disp
    string_value = pe.ascii_at(string_rva)
    if string_value != "R_Perm":
        raise ValueError(f"expected R_Perm call string, got {string_value!r} at {string_rva:#x}")

    writes = source_slot_writes(pe, funcs)
    classified = [classify_write(pe, funcs, w) for w in writes]
    proven_clears = [w for w in classified if w["classification"] == "proven_zero_clear"]
    unknown = [w for w in classified if w["classification"] != "proven_zero_clear"]

    connect = function_report(pe, funcs, RPERM_CONNECT)
    zero_helper = function_report(pe, funcs, ZERO_HELPER)

    immediate_callee_reports = []
    seen = set()
    for c in connect["direct_calls"]:
        fb = c["target_function_begin_rva"]
        if fb is None:
            continue
        b = int(fb, 16)
        if b in seen:
            continue
        seen.add(b)
        immediate_callee_reports.append(function_report(pe, funcs, b))

    # The prior direct-call conclusion is only valid as a population path if the
    # reached 0x41F640 write is not a clear. Fail closed if this semantic proof changes.
    zero_row = next((w for w in classified if w["site_rva"] == f"0x{ZERO_WRITE_SITE:X}"), None)
    if zero_row is None or zero_row["classification"] != "proven_zero_clear":
        raise ValueError("could not prove 0x421040 -> 0x41F640 source-slot writer is a clear")

    indirect_total = len(connect["heuristic_indirect_calls"]) + sum(
        len(r["heuristic_indirect_calls"]) for r in immediate_callee_reports
    )

    conclusion = "R_PERM_DIRECT_PATH_REACHES_ONLY_PROVEN_SOURCE_CLEAR"
    next_gate = (
        "Resolve the indirect/vtable call candidates in 0x421040 and its immediate callees, and identify which callback "
        "publishes a non-zero tweak registry object before 0x67C800 transfers 0x12390E0 into 0x22C6948. "
        "Do not patch GoW.exe or mutate DCB/WAD data yet."
    )

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "rperm_call_proof": {
            "call_site_rva": f"0x{RPERM_CALL_SITE:X}",
            "target_rva": f"0x{RPERM_CONNECT:X}",
            "edx_zeroed": True,
            "rcx_string_rva": f"0x{string_rva:X}",
            "rcx_string": string_value,
            "argument_setup_hex": arg_window.hex().upper(),
        },
        "source_slot": {
            "rva": f"0x{SOURCE_SLOT:X}",
            "write_instruction_count": len(writes),
            "proven_zero_clear_count": len(proven_clears),
            "potential_population_or_unknown_count": len(unknown),
            "classified_writes": classified,
        },
        "semantic_correction": {
            "prior_direct_path": ["0x421040", "0x41F640"],
            "writer_site_rva": f"0x{ZERO_WRITE_SITE:X}",
            "classification": "proven_zero_clear",
            "meaning": "the prior direct path reaches reset/clear logic, not registry population",
        },
        "rperm_connect_function": connect,
        "zero_helper_function": zero_helper,
        "immediate_direct_callee_reports": immediate_callee_reports,
        "heuristic_indirect_call_candidate_count": indirect_total,
        "conclusion": conclusion,
        "next_gate": next_gate,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  R_Perm connect: 0x{RPERM_CONNECT:X}")
    print(f"  source-slot writes: {len(writes)}; proven clears: {len(proven_clears)}; unknown/potential: {len(unknown)}")
    print("  0x421040 -> 0x41F640: PROVEN ZERO/CLEAR, not population")
    print(f"  indirect-call candidates in connect + immediate callees: {indirect_total}")
    print(f"  conclusion: {conclusion}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
