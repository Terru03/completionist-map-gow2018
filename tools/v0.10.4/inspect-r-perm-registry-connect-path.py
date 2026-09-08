"""Read-only trace from the R_Perm connect sequence to the tweak-registry source slot.

Previous v0.10.4 probes proved:
  * LuaCompass::ShowMarker validates CompassIconClass through registry slot 0x22C6948.
  * RVA 0x67C800 publishes a prebuilt registry pointer from 0x12390E0 into 0x22C6948,
    clears 0x12390E0, and aliases the pointer at 0x2018928.
  * The same transfer owner contains the literal R_Perm and calls RVA 0x421040
    immediately before the pointer handoff.

This probe asks the smallest remaining static question: which exact source-slot writer,
if any, is reachable from the R_Perm connect call and the immediately preceding init
calls? It builds a direct-call graph from the pinned executable, inventories true
writes to 0x12390E0, and reports shortest paths from the R_Perm-related roots. It does
not patch the executable, game files, saves, progression or marker state.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
IMAGE_BASE = 0x140000000
SOURCE_SLOT = 0x12390E0
REGISTRY_SLOT = 0x22C6948
ALIAS_SLOT = 0x2018928
TRANSFER_OWNER = 0x67C800
TRANSFER_SITE = 0x67C969
RPERM_CONNECT_CALL_SITE = 0x67C952
RPERM_CONNECT_TARGET = 0x421040
OWNER_CALLER = 0x682020
OWNER_CALL_SITE = 0x683173
PRE_OWNER_ROOTS = {
    "pre_owner_helper_4E4D40": 0x4E4D40,
    "pre_owner_helper_74A700": 0x74A700,
    "rperm_connect_421040": RPERM_CONNECT_TARGET,
    "rperm_lookup_672AB0": 0x672AB0,
    "owner_caller_682020": OWNER_CALLER,
}
RESULT = "READ_ONLY_R_PERM_REGISTRY_CONNECT_PATH_TRACE"


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
            self.sections.append({
                "name": name, "virtual_size": virtual_size, "rva": rva,
                "raw_size": raw_size, "raw_ptr": raw_ptr,
            })

    def section(self, name: str) -> dict:
        rows = [s for s in self.sections if s["name"] == name]
        if len(rows) != 1:
            raise ValueError(f"expected exactly one section {name}, got {len(rows)}")
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
        off = self.rva_to_offset(rva)
        data = self.raw[off:off+size]
        if len(data) != size:
            raise ValueError("short read")
        return data

    def ascii_at(self, rva: int, max_len: int = 192) -> str | None:
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


def all_direct_calls(pe: PE, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    begin = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    lo = begin
    hi = begin + max(s["virtual_size"], s["raw_size"])
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        site = begin + i
        rel = struct.unpack_from("<i", data, i + 1)[0]
        target = site + 5 + rel
        if not (lo <= target < hi):
            continue
        owner = containing(funcs, site)
        target_fn = containing(funcs, target)
        if owner is None or target_fn is None:
            continue
        out.append({
            "site": site,
            "owner": owner["begin"],
            "target": target,
            "target_owner": target_fn["begin"],
        })
    return out


def ascii_rip_refs(pe: PE, begin: int, end: int) -> list[dict]:
    data = pe.read_rva(begin, end - begin)
    out = []
    seen = set()
    for i in range(len(data) - 6):
        prefix = 1 if 0x40 <= data[i] <= 0x4F else 0
        opi = i + prefix
        if opi + 6 > len(data):
            continue
        opcode = data[opi]
        if opcode not in (0x8B, 0x8D, 0x89):
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        size = prefix + 6
        site = begin + i
        target = site + size + disp
        text = pe.ascii_at(target)
        if text is None:
            continue
        key = (site, target, text)
        if key in seen:
            continue
        seen.add(key)
        out.append({"site_rva": f"0x{site:X}", "target_rva": f"0x{target:X}", "text": text})
    return out


REG_NAMES = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]


def source_slot_writes(pe: PE, funcs: list[dict]) -> list[dict]:
    """Decode exact RIP-relative MOV writes to SOURCE_SLOT and deduplicate REX overlaps."""
    s = pe.section(".text")
    base = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    rows = []
    seen = set()
    for i in range(len(data) - 7):
        # Prefer true instruction starts. Accept optional REX then MOV r/m64,r64.
        rex = None
        opi = i
        if 0x40 <= data[i] <= 0x4F:
            rex = data[i]
            opi += 1
        if opi + 6 > len(data) or data[opi] != 0x89:
            continue
        modrm = data[opi + 1]
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", data, opi + 2)[0]
        size = (1 if rex is not None else 0) + 6
        site = base + i
        target = site + size + disp
        if target != SOURCE_SLOT:
            continue
        # If this is the opcode byte inside a REX-prefixed instruction, skip it.
        if rex is None and i > 0 and 0x40 <= data[i-1] <= 0x4F:
            prev_rex = data[i-1]
            prev_modrm = data[i+1]
            if (prev_modrm & 0xC7) == 0x05:
                prev_disp = struct.unpack_from("<i", data, i + 2)[0]
                prev_site = base + i - 1
                if prev_site + 7 + prev_disp == SOURCE_SLOT:
                    continue
        reg = (modrm >> 3) & 7
        if rex is not None and (rex & 0x04):
            reg += 8
        owner = containing(funcs, site)
        key = site
        if key in seen:
            continue
        seen.add(key)
        ctx_start = max(base, site - 48)
        ctx_end = site + size + 24
        try:
            ctx = pe.read_rva(ctx_start, ctx_end - ctx_start).hex().upper()
        except Exception:
            ctx = ""
        rows.append({
            "site_rva": f"0x{site:X}",
            "source_register": REG_NAMES[reg],
            "bytes": data[i:i+size].hex().upper(),
            "owner": None if owner is None else {"begin_rva": f"0x{owner['begin']:X}", "end_rva": f"0x{owner['end']:X}"},
            "context_start_rva": f"0x{ctx_start:X}",
            "context_hex": ctx,
        })
    rows.sort(key=lambda r: int(r["site_rva"], 16))
    return rows


def build_graph(calls: list[dict]) -> dict[int, set[int]]:
    g: dict[int, set[int]] = {}
    for c in calls:
        g.setdefault(c["owner"], set()).add(c["target_owner"])
    return g


def shortest_path(graph: dict[int, set[int]], start: int, goals: set[int], max_depth: int = 6) -> list[int] | None:
    if start in goals:
        return [start]
    q = deque([(start, [start])])
    seen = {start}
    while q:
        node, path = q.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for nxt in sorted(graph.get(node, ())):
            if nxt in seen:
                continue
            np = path + [nxt]
            if nxt in goals:
                return np
            seen.add(nxt)
            q.append((nxt, np))
    return None


def fn_summary(pe: PE, funcs: list[dict], calls: list[dict], begin: int) -> dict:
    fn = next((f for f in funcs if f["begin"] == begin), None)
    if fn is None:
        return {"begin_rva": f"0x{begin:X}", "runtime_function": False}
    direct = [c for c in calls if c["owner"] == begin]
    callers = [c for c in calls if c["target_owner"] == begin]
    return {
        "begin_rva": f"0x{begin:X}",
        "end_rva": f"0x{fn['end']:X}",
        "bytes": fn["end"] - fn["begin"],
        "ascii_rip_refs": ascii_rip_refs(pe, fn["begin"], min(fn["end"], fn["begin"] + 0x1200)),
        "direct_calls": [{"site_rva": f"0x{c['site']:X}", "target_rva": f"0x{c['target_owner']:X}"} for c in direct],
        "callers": [{"site_rva": f"0x{c['site']:X}", "owner_rva": f"0x{c['owner']:X}"} for c in callers],
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
    calls = all_direct_calls(pe, funcs)
    graph = build_graph(calls)
    writes = source_slot_writes(pe, funcs)
    writer_owners = {int(w["owner"]["begin_rva"], 16) for w in writes if w["owner"] is not None}

    # Validate the already-proven R_Perm call and transfer byte neighborhoods.
    connect_bytes = pe.read_rva(RPERM_CONNECT_CALL_SITE, 5)
    if connect_bytes[0] != 0xE8:
        raise ValueError("R_Perm connect call encoding changed")
    rel = struct.unpack_from("<i", connect_bytes, 1)[0]
    if RPERM_CONNECT_CALL_SITE + 5 + rel != RPERM_CONNECT_TARGET:
        raise ValueError("R_Perm connect call target changed")
    transfer_window = pe.read_rva(TRANSFER_SITE, 29)
    expected_prefix = bytes.fromhex("488B1D70C7BB0048891DD19FC40148892D62C7BB0048891DA3BF9901")
    if transfer_window != expected_prefix:
        raise ValueError("registry transfer sequence changed")

    roots = {}
    for label, addr in PRE_OWNER_ROOTS.items():
        p = shortest_path(graph, addr, writer_owners, 6)
        roots[label] = {
            "root_rva": f"0x{addr:X}",
            "shortest_direct_call_path_to_source_writer": None if p is None else [f"0x{x:X}" for x in p],
            "summary": fn_summary(pe, funcs, calls, addr),
        }

    reachable_writers = {}
    for label, row in roots.items():
        p = row["shortest_direct_call_path_to_source_writer"]
        if p:
            reachable_writers[label] = p[-1]

    unique_writer_summaries = []
    for owner in sorted(writer_owners):
        owner_writes = [w for w in writes if w["owner"] and int(w["owner"]["begin_rva"], 16) == owner]
        unique_writer_summaries.append({
            "owner": fn_summary(pe, funcs, calls, owner),
            "writes": owner_writes,
        })

    owner_caller_fn = next((f for f in funcs if f["begin"] == OWNER_CALLER), None)
    pre_owner_calls = []
    if owner_caller_fn:
        for c in calls:
            if c["owner"] == OWNER_CALLER and c["site"] < OWNER_CALL_SITE:
                pre_owner_calls.append({"site_rva": f"0x{c['site']:X}", "target_rva": f"0x{c['target_owner']:X}"})

    transfer_fn = next((f for f in funcs if f["begin"] == TRANSFER_OWNER), None)
    transfer_strings = [] if transfer_fn is None else ascii_rip_refs(pe, transfer_fn["begin"], transfer_fn["end"])
    rperm_strings = [r for r in transfer_strings if r["text"] in ("R_Perm", "ST_Global", "LT_Global", "BL_Global", "resource_dependency_graph") or "Connecting" in r["text"]]

    if roots["rperm_connect_421040"]["shortest_direct_call_path_to_source_writer"]:
        conclusion = "R_PERM_CONNECT_DIRECT_CALL_GRAPH_REACHES_SOURCE_WRITER"
        next_gate = (
            "Inspect the identified writer path and the registry object it publishes. Then map that object's object/name/type index "
            "back to R_Perm authored data before modifying any DCB or WAD."
        )
    elif any(v for k, v in reachable_writers.items() if k != "owner_caller_682020"):
        conclusion = "R_PERM_PRETRANSFER_HELPER_REACHES_SOURCE_WRITER"
        next_gate = (
            "Inspect the reachable pre-transfer writer path and prove which R_Perm loader callback supplies 0x12390E0. "
            "Do not bypass ShowMarker or patch another data file yet."
        )
    else:
        conclusion = "R_PERM_SOURCE_WRITE_REQUIRES_INDIRECT_CALL_TRACE"
        next_gate = (
            "The source writer is not reachable through direct E8 calls from the R_Perm connect/pre-transfer roots, so resolve the "
            "indirect/vtable callback used by RVA 0x421040 or the immediately preceding owner-caller helpers."
        )

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_progression_marker_state_written": False,
        "source": str(exe),
        "source_sha256": digest,
        "known_handoff": {
            "source_slot_rva": f"0x{SOURCE_SLOT:X}",
            "registry_slot_rva": f"0x{REGISTRY_SLOT:X}",
            "alias_slot_rva": f"0x{ALIAS_SLOT:X}",
            "transfer_owner_rva": f"0x{TRANSFER_OWNER:X}",
            "transfer_site_rva": f"0x{TRANSFER_SITE:X}",
            "rperm_connect_call_site_rva": f"0x{RPERM_CONNECT_CALL_SITE:X}",
            "rperm_connect_target_rva": f"0x{RPERM_CONNECT_TARGET:X}",
            "rperm_related_strings_in_transfer_owner": rperm_strings,
        },
        "source_slot_writes": {
            "instruction_count": len(writes),
            "owner_function_count": len(writer_owners),
            "writes": writes,
            "writer_owner_summaries": unique_writer_summaries,
        },
        "root_reachability": roots,
        "reachable_writer_by_root": reachable_writers,
        "owner_caller_pre_transfer_direct_calls": pre_owner_calls,
        "conclusion": conclusion,
        "next_gate": next_gate,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  source-slot write instructions: {len(writes)}; writer owners: {len(writer_owners)}")
    for label, row in roots.items():
        p = row["shortest_direct_call_path_to_source_writer"]
        print(f"  {label}: {' -> '.join(p) if p else 'no direct-call path <=6'}")
    print(f"  conclusion: {conclusion}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
