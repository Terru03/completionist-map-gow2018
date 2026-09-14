"""Read-only triage of native Lua bindings that may expose unloaded collectible state.

Consumes the latest exhaustive Lua registration scan and inspects a deliberately
small set of high-value native wrapper functions in GoW.exe.  The goal is not to
claim an oracle automatically, but to rank bindings worth reversing next and expose
shared call targets / nearby RIP-relative strings that can connect object identity,
checkpoint persistence, counters, refs, regions, and save state.

Safety contract:
- reads GoW.exe only;
- reads archived scan JSON inside this repository;
- never opens the active save directory;
- never launches or writes to the game;
- verifies GoW.exe SHA-256 is unchanged after the scan.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable, Optional


WINDOW_BYTES = 0x240
MAX_STRING = 192

# Explicit shortlist discovered from the exhaustive registration pass.  Generic
# getters are intentionally excluded unless they carry persistence/object meaning.
TARGET_WEIGHTS = {
    "ResolveGameObject": 120,
    "GetRefBool": 115,
    "GetRefInt": 115,
    "GetRefFloat": 115,
    "GetRefString": 115,
    "GetVariable": 110,
    "GetHeroPersistentLevel": 110,
    "GetSonPersistentLevel": 110,
    "GetPermLevel": 110,
    "GetCounter": 108,
    "GetCounterChild": 108,
    "GetCounterChildrenCount": 108,
    "GetCounterName": 105,
    "GetCounterThreshold": 105,
    "GetCounterThresholdCount": 105,
    "GetCounterThresholdName": 105,
    "MarkForSave": 103,
    "Retain": 102,
    "SetRetainOnCheckpoint": 101,
    "SetForgetOnCheckpoint": 101,
    "CheckPoint": 100,
    "GetRegionHash": 98,
    "GetLevelId": 98,
    "MarkerID": 95,
    "EventField": 92,
    "EventFieldBool": 92,
    "EventFieldFloat": 92,
    "EventFieldString": 92,
    "EntityBool": 90,
    "EntityInt": 90,
    "EntityFloat": 90,
    "EntityString": 90,
    "GetCurrentSlot": 82,
    "GetLatestSlot": 82,
    "LoadSaveGame": 80,
    "GetSlotCount": 78,
    "GetSlotSaveTime": 78,
    "GetSlotTitle": 75,
    "gameProgress": 75,
}

STRING_NEEDLES = (
    "save", "checkpoint", "persist", "retain", "forget", "restore",
    "object", "entity", "state", "ref", "counter", "region", "level",
    "marker", "guid", "slot", "progress", "variable", "subobject",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PEImage:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x100 or data[:2] != b"MZ":
            raise RuntimeError("GoW.exe is not an MZ image")
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_off:pe_off + 4] != b"PE\0\0":
            raise RuntimeError("Invalid PE signature")
        num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, pe_off + 20)[0]
        opt = pe_off + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("Expected PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.size_of_headers = struct.unpack_from("<I", data, opt + 60)[0]
        sec_off = opt + size_opt
        self.sections: list[dict] = []
        for i in range(num_sections):
            off = sec_off + i * 40
            name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from(
                "<IIII", data, off + 8
            )
            self.sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
            })

    def section_for_rva(self, rva: int) -> Optional[dict]:
        if 0 <= rva < self.size_of_headers:
            return {
                "name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
            }
        for sec in self.sections:
            span = max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + span:
                return sec
        return None

    def rva_to_file(self, rva: int) -> Optional[int]:
        if 0 <= rva < self.size_of_headers:
            return rva if rva < len(self.data) else None
        sec = self.section_for_rva(rva)
        if sec is None:
            return None
        delta = rva - sec["virtual_address"]
        if delta < 0 or delta >= sec["raw_size"]:
            return None
        off = sec["raw_ptr"] + delta
        return off if off < len(self.data) else None

    def ascii_at_rva(self, rva: int) -> Optional[str]:
        off = self.rva_to_file(rva)
        if off is None:
            return None
        end = off
        while end < len(self.data) and end - off <= MAX_STRING:
            b = self.data[end]
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            end += 1
        if end == off or end >= len(self.data) or self.data[end] != 0:
            return None
        return self.data[off:end].decode("ascii", "replace")

    def utf16_at_rva(self, rva: int) -> Optional[str]:
        off = self.rva_to_file(rva)
        if off is None:
            return None
        chars: list[str] = []
        pos = off
        while pos + 1 < len(self.data) and len(chars) <= MAX_STRING:
            lo, hi = self.data[pos], self.data[pos + 1]
            if lo == 0 and hi == 0:
                break
            if hi != 0 or lo < 0x20 or lo > 0x7E:
                return None
            chars.append(chr(lo))
            pos += 2
        return "".join(chars) if chars else None


def parse_hex(value: object) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.lower().startswith("0x") else int(value)
        except ValueError:
            return None
    return None


def latest_exhaustive_json(repo: Path) -> Path:
    root = repo / "archive" / "field-logs" / "source-scans"
    candidates = sorted(
        root.glob("lua-registration-exhaustive-*/registration-exhaustive.json"),
        key=lambda p: p.parent.name,
    )
    if not candidates:
        raise RuntimeError("No archived exhaustive Lua registration JSON found")
    return candidates[-1]


def all_registration_entries(report: dict) -> Iterable[dict]:
    tables = report.get("canonical_tables") or report.get("candidate_tables") or []
    if tables:
        for table in tables:
            for entry in table.get("entries", []):
                item = dict(entry)
                item.setdefault("table_start", table.get("start_offset_hex"))
                item.setdefault("stride", table.get("stride"))
                yield item
        return
    yield from report.get("interesting_registrations", [])


def select_candidates(report: dict) -> list[dict]:
    selected: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for entry in all_registration_entries(report):
        name = str(entry.get("name", ""))
        if name not in TARGET_WEIGHTS:
            continue
        rva = parse_hex(entry.get("function_rva"))
        if rva is None:
            continue
        table = str(entry.get("table_start", ""))
        key = (name, rva, table)
        if key in seen:
            continue
        seen.add(key)
        item = dict(entry)
        item["function_rva_int"] = rva
        item["base_score"] = TARGET_WEIGHTS[name]
        selected.append(item)
    selected.sort(key=lambda x: (-x["base_score"], x["name"], x["function_rva_int"]))
    return selected


def rel32_targets(window: bytes, function_rva: int) -> list[dict]:
    """Heuristic x86-64 rel32 CALL/JMP scan.

    This is intentionally labelled heuristic because it is not a full instruction
    decoder.  Shared targets across several thin Lua wrappers are still high-value
    reverse-engineering clues.
    """
    out: list[dict] = []
    for i in range(0, max(0, len(window) - 4)):
        opcode = window[i]
        if opcode not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", window, i + 1)[0]
        target = function_rva + i + 5 + disp
        if target < 0:
            continue
        out.append({
            "kind": "call" if opcode == 0xE8 else "jmp",
            "offset": i,
            "target_rva": f"0x{target:X}",
            "target_rva_int": target,
        })
    return out


def rip_relative_refs(pe: PEImage, window: bytes, function_rva: int) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for i in range(0, max(0, len(window) - 6)):
        rex = window[i]
        opcode = window[i + 1]
        modrm = window[i + 2]
        if not (0x40 <= rex <= 0x4F and opcode in (0x8D, 0x8B)):
            continue
        # mod=00 and r/m=101 means RIP-relative addressing.
        if (modrm & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", window, i + 3)[0]
        target = function_rva + i + 7 + disp
        key = (i, target)
        if key in seen:
            continue
        seen.add(key)
        ascii_value = pe.ascii_at_rva(target)
        utf16_value = None if ascii_value else pe.utf16_at_rva(target)
        out.append({
            "offset": i,
            "opcode": "lea" if opcode == 0x8D else "mov",
            "target_rva": f"0x{target:X}",
            "string": ascii_value or utf16_value,
            "encoding": "ascii" if ascii_value else ("utf16le" if utf16_value else None),
        })
    return out


def inspect_candidate(pe: PEImage, entry: dict) -> dict:
    rva = entry["function_rva_int"]
    off = pe.rva_to_file(rva)
    if off is None:
        return {**entry, "error": "function RVA cannot be mapped to file offset"}
    window = pe.data[off:min(len(pe.data), off + WINDOW_BYTES)]
    calls = rel32_targets(window, rva)
    refs = rip_relative_refs(pe, window, rva)
    meaningful_strings = [
        ref for ref in refs
        if ref.get("string") and any(n in ref["string"].lower() for n in STRING_NEEDLES)
    ]
    score = int(entry["base_score"]) + min(20, len(meaningful_strings) * 5)
    return {
        **entry,
        "function_file_offset": f"0x{off:X}",
        "window_bytes": len(window),
        "head_hex": window[:96].hex(" "),
        "rel32_targets": calls,
        "rip_relative_refs": refs,
        "meaningful_string_refs": meaningful_strings,
        "score": score,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--registration-json", type=Path)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    game_root = args.game_root.expanduser().resolve()
    exe = game_root / "GoW.exe"
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")

    registration_json = (
        args.registration_json.expanduser().resolve()
        if args.registration_json else latest_exhaustive_json(repo)
    )
    if not registration_json.is_file():
        raise RuntimeError(f"Registration scan JSON not found: {registration_json}")

    before = sha256_file(exe)
    data = exe.read_bytes()
    pe = PEImage(data)
    report = json.loads(registration_json.read_text(encoding="utf-8-sig"))
    candidates = select_candidates(report)
    inspected = [inspect_candidate(pe, item) for item in candidates]

    call_users: dict[int, set[str]] = defaultdict(set)
    for item in inspected:
        for target in item.get("rel32_targets", []):
            if target.get("kind") == "call":
                call_users[target["target_rva_int"]].add(item["name"])
    shared_calls = [
        {
            "target_rva": f"0x{target:X}",
            "candidate_names": sorted(names),
            "candidate_count": len(names),
        }
        for target, names in call_users.items() if len(names) >= 2
    ]
    shared_calls.sort(key=lambda x: (-x["candidate_count"], x["target_rva"]))

    shared_lookup = {
        int(item["target_rva"], 16): item["candidate_count"] for item in shared_calls
    }
    for item in inspected:
        bonus = 0
        for target in item.get("rel32_targets", []):
            if target.get("kind") == "call":
                bonus += min(12, max(0, shared_lookup.get(target["target_rva_int"], 1) - 1) * 2)
        item["shared_call_bonus"] = bonus
        item["score"] = int(item.get("score", item.get("base_score", 0))) + bonus
        for target in item.get("rel32_targets", []):
            target.pop("target_rva_int", None)
        item.pop("function_rva_int", None)

    inspected.sort(key=lambda x: (-int(x.get("score", 0)), x.get("name", ""), x.get("function_rva", "")))

    after = sha256_file(exe)
    if before != after:
        raise RuntimeError("GoW.exe hash changed during read-only candidate analysis")

    output = {
        "schema": 1,
        "scan_kind": "read_only_unloaded_state_oracle_candidate_function_triage",
        "game_root": str(game_root),
        "exe": str(exe),
        "exe_sha256": before,
        "registration_json": str(registration_json),
        "candidate_count": len(inspected),
        "shared_call_target_count": len(shared_calls),
        "candidates": inspected,
        "shared_call_targets": shared_calls,
        "safety": {
            "source_hashes_unchanged": True,
            "active_save_opened": False,
            "game_written": False,
            "save_or_progression_written": False,
            "game_launched": False,
            "scan_only": True,
        },
    }

    lines = [
        "Completionist Map - unloaded-state oracle candidate triage",
        f"exe={exe}",
        f"sha256={before}",
        f"registration_json={registration_json}",
        f"candidates={len(inspected)} shared_call_targets={len(shared_calls)}",
        "source_hashes_unchanged=true active_save_opened=false game_written=false game_launched=false",
        "",
        "Ranked candidates:",
    ]
    for idx, item in enumerate(inspected, 1):
        lines.append(
            f"{idx:02d}. score={item.get('score', 0):3d} {item.get('name')} "
            f"fn={item.get('function_rva')} table={item.get('table_start', '?')} "
            f"calls={len(item.get('rel32_targets', []))} strings={len(item.get('meaningful_string_refs', []))}"
        )
        for ref in item.get("meaningful_string_refs", [])[:8]:
            lines.append(f"    str {ref['target_rva']} {ref.get('string')!r}")
        shared_here = []
        for target in item.get("rel32_targets", []):
            target_int = int(target["target_rva"], 16)
            users = shared_lookup.get(target_int, 1)
            if target.get("kind") == "call" and users >= 2:
                shared_here.append((users, target["target_rva"]))
        for users, target in sorted(set(shared_here), reverse=True)[:8]:
            lines.append(f"    shared-call {target} used_by={users} shortlisted wrappers")

    lines.extend(["", "Shared call targets:"])
    if shared_calls:
        for item in shared_calls[:80]:
            lines.append(
                f"  {item['target_rva']} count={item['candidate_count']} "
                + " | ".join(item["candidate_names"])
            )
    else:
        lines.append("  none detected by heuristic rel32 scan")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "UNLOADED_STATE_ORACLE_CANDIDATE_SCAN_PASSED "
        f"candidates={len(inspected)} shared_call_targets={len(shared_calls)}"
    )
    print("source_hashes_unchanged=true active_save_opened=false game_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
