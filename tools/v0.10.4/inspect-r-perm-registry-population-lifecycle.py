"""Read-only lifecycle trace for the R_Perm tweak-registry pointer.

This probe follows the remaining static gap after the v0.10.4 Compass research
proved that ShowMarker consumes the registry published at 0x22C6948 and that
R_Perm's connect owner moves a prebuilt pointer from 0x12390E0 into that slot.

It resolves the five previously reported indirect-call candidates (including
PE import/IAT names where possible), inventories source-slot writers, and asks
which non-proven-clear writer owners are reachable through direct calls that
occur *before* the R_Perm transfer in the known startup owner. It also inspects
the second caller of the R_Perm transfer owner at 0x66CA8E.

No executable, DCB, WAD, save, progression, or marker state is modified.
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
RPERM_CONNECT = 0x421040
RPERM_TRANSFER_OWNER = 0x67C800
RPERM_TRANSFER_SITE = 0x67C969
STARTUP_OWNER = 0x682020
STARTUP_TRANSFER_CALL_SITE = 0x683173
SECOND_OWNER_CALLER = 0x66CA8E
RESULT = "READ_ONLY_R_PERM_REGISTRY_POPULATION_LIFECYCLE_TRACE"

KNOWN_INDIRECT_SITES = {
    0x421096: {"kind": "rip_iat", "slot": 0xD48F78, "owner": 0x421040},
    0x40A0DB: {"kind": "rip_iat", "slot": 0xD48440, "owner": 0x40A0D0},
    0x40A100: {"kind": "rip_iat", "slot": 0xD484E0, "owner": 0x40A0D0},
    0x41F695: {"kind": "vtable", "vtable_offset": 0x88, "owner": 0x41F640},
    0x41F6C6: {"kind": "vtable", "vtable_offset": 0x90, "owner": 0x41F640},
}

REG_NAMES = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
             "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]


class PE:
    def __init__(self, raw: bytes):
        self.raw = raw
        if raw[:2] != b"MZ":
            raise ValueError("not an MZ executable")
        self.pe = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[self.pe:self.pe+4] != b"PE\0\0":
            raise ValueError("missing PE signature")
        self.count = struct.unpack_from("<H", raw, self.pe + 6)[0]
        optional_size = struct.unpack_from("<H", raw, self.pe + 20)[0]
        self.optional = self.pe + 24
        if struct.unpack_from("<H", raw, self.optional)[0] != 0x20B:
            raise ValueError("expected PE32+")
        self.image_base = struct.unpack_from("<Q", raw, self.optional + 24)[0]
        if self.image_base != IMAGE_BASE:
            raise ValueError(f"unexpected image base {self.image_base:#x}")
        self.sections = []
        table = self.optional + optional_size
        for i in range(self.count):
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

    def cstr(self, rva: int, max_len: int = 512) -> str:
        o = self.rva_to_offset(rva)
        blob = self.raw[o:min(len(self.raw), o + max_len)]
        nul = blob.find(b"\0")
        if nul >= 0:
            blob = blob[:nul]
        return blob.decode("ascii", "replace")

    def data_directory(self, index: int) -> tuple[int, int]:
        # PE32+ data directories begin at optional header + 112.
        o = self.optional + 112 + index * 8
        return struct.unpack_from("<II", self.raw, o)

    def imports(self) -> dict[int, str]:
        """Return IAT-slot RVA -> DLL!symbol for normal imports."""
        import_rva, import_size = self.data_directory(1)
        out: dict[int, str] = {}
        if not import_rva or not import_size:
            return out
        desc_off = self.rva_to_offset(import_rva)
        for n in range(0, import_size, 20):
            o = desc_off + n
            oft, _ts, _fc, name_rva, ft = struct.unpack_from("<IIIII", self.raw, o)
            if not any((oft, name_rva, ft)):
                break
            dll = self.cstr(name_rva)
            lookup = oft or ft
            idx = 0
            while True:
                try:
                    thunk = struct.unpack("<Q", self.read_rva(lookup + idx * 8, 8))[0]
                except Exception:
                    break
                if thunk == 0:
                    break
                slot = ft + idx * 8
                if thunk & (1 << 63):
                    sym = f"ordinal_{thunk & 0xFFFF}"
                else:
                    try:
                        sym = self.cstr(int(thunk) + 2)
                    except Exception:
                        sym = f"name_rva_{int(thunk):X}"
                out[slot] = f"{dll}!{sym}"
                idx += 1
        return out


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


def fn_by_begin(funcs: list[dict], begin: int) -> dict | None:
    return next((f for f in funcs if f["begin"] == begin), None)


def all_direct_calls(pe: PE, funcs: list[dict]) -> list[dict]:
    s = pe.section(".text")
    base = s["rva"]
    data = pe.raw[s["raw_ptr"]:s["raw_ptr"] + s["raw_size"]]
    lo = base
    hi = base + max(s["virtual_size"], s["raw_size"])
    out = []
    for i in range(len(data) - 4):
        if data[i] != 0xE8:
            continue
        site = base + i
        rel = struct.unpack_from("<i", data, i + 1)[0]
        target = site + 5 + rel
        if not (lo <= target < hi):
            continue
        owner = containing(funcs, site)
        target_fn = containing(funcs, target)
        if owner is None or target_fn is None:
            continue
        out.append({"site": site, "owner": owner["begin"],
                    "target": target, "target_owner": target_fn["begin"]})
    return out


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
        if site + size + disp != SOURCE_SLOT:
            continue
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
        rows.append({"site": site, "owner": None if owner is None else owner["begin"],
                     "source_register": REG_NAMES[reg], "bytes": data[i:i+size].hex().upper()})
    return rows


def proven_clear(pe: PE, row: dict) -> tuple[bool, str | None]:
    site, owner, reg = row["site"], row["owner"], row["source_register"]
    if site == 0x41F66A and owner == 0x41F640 and reg == "rdi":
        if b"\x33\xFF" in pe.read_rva(0x41F640, 32):
            return True, "0x41F640 zeroes EDI/RDI before the source-slot store"
    if site == 0x675988 and reg == "rbx" and pe.read_rva(site - 2, 2) == b"\x33\xDB":
        return True, "immediate xor ebx,ebx precedes the source-slot store"
    if site == 0x67C977 and owner == 0x67C800 and reg == "rbp":
        if b"\x33\xED" in pe.read_rva(0x67C800, 48):
            return True, "R_Perm transfer owner zeroes EBP/RBP before post-publication clear"
    return False, None


def graph_from_calls(calls: list[dict]) -> dict[int, set[int]]:
    g: dict[int, set[int]] = {}
    for c in calls:
        g.setdefault(c["owner"], set()).add(c["target_owner"])
    return g


def shortest_path(g: dict[int, set[int]], start: int, goals: set[int], max_depth: int = 7) -> list[int] | None:
    if start in goals:
        return [start]
    q = deque([(start, [start])])
    seen = {start}
    while q:
        node, path = q.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for nxt in sorted(g.get(node, ())):
            if nxt in seen:
                continue
            np = path + [nxt]
            if nxt in goals:
                return np
            seen.add(nxt)
            q.append((nxt, np))
    return None


def function_report(pe: PE, funcs: list[dict], calls: list[dict], begin: int) -> dict:
    fn = fn_by_begin(funcs, begin)
    if fn is None:
        return {"begin_rva": f"0x{begin:X}", "runtime_function": False}
    data = pe.read_rva(fn["begin"], fn["end"] - fn["begin"])
    direct = [c for c in calls if c["owner"] == begin]
    callers = [c for c in calls if c["target_owner"] == begin]
    return {
        "begin_rva": f"0x{begin:X}", "end_rva": f"0x{fn['end']:X}", "bytes": len(data),
        "full_hex": data.hex().upper(),
        "direct_calls": [{"site_rva": f"0x{c['site']:X}", "target_rva": f"0x{c['target_owner']:X}"} for c in direct],
        "callers": [{"site_rva": f"0x{c['site']:X}", "owner_rva": f"0x{c['owner']:X}"} for c in callers],
    }


def nearest_rip_load(pe: PE, site: int, window: int = 40) -> dict | None:
    """Find nearest preceding RIP-relative MOV load ending before a vtable call."""
    begin = site - window
    data = pe.read_rva(begin, window)
    best = None
    for i in range(len(data) - 7):
        if data[i:i+3] not in (b"\x48\x8B\x0D", b"\x48\x8B\x05", b"\x48\x8B\x15"):
            continue
        disp = struct.unpack_from("<i", data, i+3)[0]
        insn = begin + i
        target = insn + 7 + disp
        best = {"load_site_rva": f"0x{insn:X}", "target_global_rva": f"0x{target:X}",
                "bytes": data[i:i+7].hex().upper()}
    return best


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
    graph = graph_from_calls(calls)
    imports = pe.imports()

    # Re-prove R_Perm transfer bytes before relying on the lifecycle addresses.
    transfer = pe.read_rva(RPERM_TRANSFER_SITE, 28)
    expected = bytes.fromhex("488B1D70C7BB0048891DD19FC40148892D62C7BB0048891DA3BF9901")
    if transfer != expected:
        raise ValueError("R_Perm registry transfer sequence changed")

    writes = source_slot_writes(pe, funcs)
    classified = []
    candidate_owners = set()
    for w in writes:
        is_clear, proof = proven_clear(pe, w)
        if not is_clear and w["owner"] is not None:
            candidate_owners.add(w["owner"])
        classified.append({
            "site_rva": f"0x{w['site']:X}",
            "owner_rva": None if w["owner"] is None else f"0x{w['owner']:X}",
            "source_register": w["source_register"],
            "classification": "proven_zero_clear" if is_clear else "potential_population_or_unknown",
            "proof": proof,
        })

    indirect = []
    for site, spec in KNOWN_INDIRECT_SITES.items():
        row = {"site_rva": f"0x{site:X}", "owner_rva": f"0x{spec['owner']:X}", "kind": spec["kind"]}
        if spec["kind"] == "rip_iat":
            slot = spec["slot"]
            row["iat_slot_rva"] = f"0x{slot:X}"
            row["resolved_import"] = imports.get(slot)
        else:
            row["vtable_offset"] = f"0x{spec['vtable_offset']:X}"
            row["nearest_preceding_rip_load"] = nearest_rip_load(pe, site)
        indirect.append(row)

    # Only direct calls made before startup's call into the R_Perm transfer owner
    # are valid pre-transfer roots. This fixes the prior order-insensitive graph.
    startup_pre = [c for c in calls if c["owner"] == STARTUP_OWNER and c["site"] < STARTUP_TRANSFER_CALL_SITE]
    startup_paths = []
    for root in startup_pre:
        p = shortest_path(graph, root["target_owner"], candidate_owners, 7)
        if p:
            startup_paths.append({
                "startup_call_site_rva": f"0x{root['site']:X}",
                "root_rva": f"0x{root['target_owner']:X}",
                "path": [f"0x{x:X}" for x in p],
                "candidate_writer_owner_rva": f"0x{p[-1]:X}",
            })

    # Also examine the alternate direct caller observed for 0x67C800.
    second_paths = []
    second_fn = fn_by_begin(funcs, SECOND_OWNER_CALLER)
    if second_fn is not None:
        for c in calls:
            if c["owner"] != SECOND_OWNER_CALLER:
                continue
            p = shortest_path(graph, c["target_owner"], candidate_owners, 7)
            if p:
                second_paths.append({"call_site_rva": f"0x{c['site']:X}",
                                     "path": [f"0x{x:X}" for x in p]})

    # Inspect the caller one level above startup and only its calls before it enters
    # STARTUP_OWNER, because registry creation may precede the giant startup owner.
    startup_callers = [c for c in calls if c["target_owner"] == STARTUP_OWNER]
    parent_pre_paths = []
    for entry in startup_callers:
        parent = entry["owner"]
        for c in calls:
            if c["owner"] != parent or c["site"] >= entry["site"]:
                continue
            p = shortest_path(graph, c["target_owner"], candidate_owners, 7)
            if p:
                parent_pre_paths.append({
                    "parent_owner_rva": f"0x{parent:X}",
                    "startup_call_site_rva": f"0x{entry['site']:X}",
                    "prior_call_site_rva": f"0x{c['site']:X}",
                    "path": [f"0x{x:X}" for x in p],
                    "candidate_writer_owner_rva": f"0x{p[-1]:X}",
                })

    imports_resolved = sum(1 for r in indirect if r.get("resolved_import"))
    if startup_paths or parent_pre_paths or second_paths:
        conclusion = "PRETRANSFER_DIRECT_PATH_TO_POTENTIAL_SOURCE_WRITER_LOCATED"
        next_gate = (
            "Inspect the ordered writer path(s), prove whether the stored pointer is non-zero registry population, and map the "
            "producer to the authored R_Perm/DCB loader before modifying any game data."
        )
    else:
        conclusion = "NO_ORDERED_DIRECT_PATH_TO_POTENTIAL_SOURCE_WRITER"
        next_gate = (
            "With import calls resolved, trace the remaining vtable/indirect callback or an earlier initialization path that "
            "creates 0x12390E0. Do not patch GoW.exe or mutate DCB/WAD data yet."
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
            "transfer_owner_rva": f"0x{RPERM_TRANSFER_OWNER:X}",
            "transfer_site_rva": f"0x{RPERM_TRANSFER_SITE:X}",
            "startup_owner_rva": f"0x{STARTUP_OWNER:X}",
            "startup_transfer_call_site_rva": f"0x{STARTUP_TRANSFER_CALL_SITE:X}",
        },
        "indirect_candidates": {"count": len(indirect), "resolved_import_count": imports_resolved, "rows": indirect},
        "source_slot_writes": {"count": len(classified), "candidate_owner_count": len(candidate_owners), "rows": classified},
        "ordered_pretransfer_reachability": {
            "startup_pretransfer_direct_call_count": len(startup_pre),
            "startup_paths": startup_paths,
            "parent_pre_startup_paths": parent_pre_paths,
            "second_transfer_owner_caller_paths": second_paths,
        },
        "second_transfer_owner_caller": function_report(pe, funcs, calls, SECOND_OWNER_CALLER),
        "startup_owner_callers": [{"call_site_rva": f"0x{c['site']:X}", "owner_rva": f"0x{c['owner']:X}"} for c in startup_callers],
        "conclusion": conclusion,
        "next_gate": next_gate,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  indirect candidates: {len(indirect)}; imports resolved: {imports_resolved}")
    for r in indirect:
        extra = r.get("resolved_import") or ("vtable+" + r.get("vtable_offset", "?"))
        print(f"  {r['site_rva']}: {extra}")
    print(f"  source-slot writers: {len(classified)}; potential owner functions: {len(candidate_owners)}")
    print(f"  ordered startup pre-transfer paths: {len(startup_paths)}")
    print(f"  parent pre-startup paths: {len(parent_pre_paths)}")
    print(f"  alternate-owner-caller paths: {len(second_paths)}")
    print(f"  conclusion: {conclusion}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
