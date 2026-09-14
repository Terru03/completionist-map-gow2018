"""Read-only enumeration of native Lua registration tables in God of War.

This follows the PE/xref scan that proved several names (for example game.SubObject
SoftSave/Sleep/Wake) are backed by native registration records while LoadSubObject
is not an obvious registration-table entry.  The previous scanner assumed 16-byte
LuaL_Reg-style entries, but the confirmed SubObject entries are spaced 0x18 bytes
apart.  This helper therefore infers the record stride around proven name-pointer
anchors and walks the complete contiguous tables without assuming that every method
name was known in advance.

Goals:
  * enumerate the full native table containing SoftSave/Sleep/Wake,
  * enumerate the object lookup table containing FindGameObject/GetGameObject,
  * surface any previously-unscanned Get/Load/Save/State/Persistence methods,
  * retain third/fourth record words so table shape can be reasoned about later.

The executable is opened read-only, hashed before/after, the game is never launched,
and the active save directory is never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Optional

IMAGE_SCN_MEM_EXECUTE = 0x20000000
MAX_ASCII = 160
MAX_ENTRIES = 512
STRIDES = (16, 24, 32, 40, 48)

ANCHOR_GROUPS = {
    "subobject": (
        "Sleep", "Wake", "SetRetainOnCheckpoint", "SetForgetOnCheckpoint",
        "SoftSave", "SetEntityZoneHandler",
    ),
    "object_lookup": (
        "FindGameObjects", "FindSingleGameObject", "FindGameObject",
        "GetGameObject", "IterateGameObjects",
    ),
}

INTERESTING_NEEDLES = (
    "get", "find", "load", "save", "restore", "checkpoint", "state",
    "persist", "serial", "subobject", "object", "wad", "environment",
    "retain", "forget", "soft",
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
        self.pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[self.pe_off:self.pe_off + 4] != b"PE\0\0":
            raise RuntimeError("Invalid PE signature")
        self.num_sections = struct.unpack_from("<H", data, self.pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, self.pe_off + 20)[0]
        opt = self.pe_off + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise RuntimeError("Expected PE32+")
        self.image_base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", data, opt + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", data, opt + 60)[0]
        sec_off = opt + size_opt
        self.sections: list[dict] = []
        for i in range(self.num_sections):
            off = sec_off + i * 40
            name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from("<IIII", data, off + 8)
            characteristics = struct.unpack_from("<I", data, off + 36)[0]
            self.sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_ptr": raw_ptr,
                "executable": bool(characteristics & IMAGE_SCN_MEM_EXECUTE),
            })

    def section_for_file(self, offset: int) -> Optional[dict]:
        if 0 <= offset < self.size_of_headers:
            return {"name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                    "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                    "executable": False}
        for sec in self.sections:
            if sec["raw_ptr"] <= offset < sec["raw_ptr"] + sec["raw_size"]:
                return sec
        return None

    def section_for_rva(self, rva: int) -> Optional[dict]:
        if 0 <= rva < self.size_of_headers:
            return {"name": "<headers>", "virtual_address": 0, "raw_ptr": 0,
                    "raw_size": self.size_of_headers, "virtual_size": self.size_of_headers,
                    "executable": False}
        for sec in self.sections:
            span = max(sec["virtual_size"], sec["raw_size"])
            if sec["virtual_address"] <= rva < sec["virtual_address"] + span:
                return sec
        return None

    def file_to_rva(self, off: int) -> Optional[int]:
        sec = self.section_for_file(off)
        if sec is None:
            return None
        return sec["virtual_address"] + (off - sec["raw_ptr"])

    def rva_to_file(self, rva: int) -> Optional[int]:
        if 0 <= rva < self.size_of_headers:
            return rva if rva < len(self.data) else None
        sec = self.section_for_rva(rva)
        if sec is None:
            return None
        delta = rva - sec["virtual_address"]
        if delta >= sec["raw_size"]:
            return None
        off = sec["raw_ptr"] + delta
        return off if off < len(self.data) else None

    def va_to_rva(self, va: int) -> Optional[int]:
        if self.image_base <= va < self.image_base + self.size_of_image:
            return va - self.image_base
        return None

    def ascii_at(self, off: int) -> Optional[str]:
        if off < 0 or off >= len(self.data):
            return None
        end = off
        while end < len(self.data) and end - off <= MAX_ASCII:
            b = self.data[end]
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            end += 1
        if end == off or end >= len(self.data) or self.data[end] != 0:
            return None
        return self.data[off:end].decode("ascii", "replace")

    def decode_name_fn(self, off: int, stride: int) -> Optional[dict]:
        if off < 0 or off + stride > len(self.data) or stride < 16:
            return None
        name_va, fn_va = struct.unpack_from("<QQ", self.data, off)
        name_rva = self.va_to_rva(name_va)
        fn_rva = self.va_to_rva(fn_va)
        if name_rva is None or fn_rva is None:
            return None
        name_off = self.rva_to_file(name_rva)
        if name_off is None:
            return None
        name = self.ascii_at(name_off)
        if not name:
            return None
        fn_sec = self.section_for_rva(fn_rva)
        if fn_sec is None or not fn_sec.get("executable"):
            return None
        extra = []
        for p in range(off + 16, off + stride, 8):
            extra.append(struct.unpack_from("<Q", self.data, p)[0])
        sec = self.section_for_file(off)
        return {
            "offset": off,
            "offset_hex": hex(off),
            "section": sec["name"] if sec else None,
            "name": name,
            "name_va": hex(name_va),
            "function_va": hex(fn_va),
            "function_rva": hex(fn_rva),
            "function_section": fn_sec["name"],
            "extra_qwords": [hex(x) for x in extra],
        }


def find_all(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        p = data.find(needle, start)
        if p < 0:
            return out
        out.append(p)
        start = p + 1


def absolute_name_xrefs(pe: PEImage, name: str) -> list[int]:
    refs: list[int] = []
    for s_off in find_all(pe.data, name.encode("ascii") + b"\0"):
        rva = pe.file_to_rva(s_off)
        if rva is None:
            continue
        va = pe.image_base + rva
        refs.extend(find_all(pe.data, struct.pack("<Q", va)))
    return sorted(set(refs))


def walk(pe: PEImage, anchor_off: int, stride: int) -> list[dict]:
    if pe.decode_name_fn(anchor_off, stride) is None:
        return []
    start = anchor_off
    for _ in range(MAX_ENTRIES):
        prev = start - stride
        if pe.decode_name_fn(prev, stride) is None:
            break
        start = prev
    out: list[dict] = []
    off = start
    for _ in range(MAX_ENTRIES):
        entry = pe.decode_name_fn(off, stride)
        if entry is None:
            break
        out.append(entry)
        off += stride
    return out


def table_key(entries: list[dict], stride: int) -> tuple:
    return (stride, tuple((e["offset"], e["name"], e["function_rva"]) for e in entries))


def score_table(entries: list[dict], group: tuple[str, ...]) -> dict:
    names = [e["name"] for e in entries]
    anchors = [x for x in group if x in names]
    interesting = [n for n in names if any(k in n.lower() for k in INTERESTING_NEEDLES)]
    return {
        "entry_count": len(entries),
        "anchor_hits": anchors,
        "anchor_hit_count": len(anchors),
        "interesting_names": interesting,
    }


def infer_tables(pe: PEImage) -> list[dict]:
    tables: dict[tuple, dict] = {}
    for group_name, anchors in ANCHOR_GROUPS.items():
        for anchor in anchors:
            for xref in absolute_name_xrefs(pe, anchor):
                sec = pe.section_for_file(xref)
                if sec is not None and sec.get("executable"):
                    continue
                for stride in STRIDES:
                    entry = pe.decode_name_fn(xref, stride)
                    if entry is None or entry["name"] != anchor:
                        continue
                    entries = walk(pe, xref, stride)
                    if not entries:
                        continue
                    score = score_table(entries, anchors)
                    # A useful table must contain the anchor and either at least two entries
                    # or at least two known anchors.  This suppresses accidental one-record hits.
                    if score["anchor_hit_count"] < 1:
                        continue
                    if score["entry_count"] < 2 and score["anchor_hit_count"] < 2:
                        continue
                    key = table_key(entries, stride)
                    rec = tables.get(key)
                    evidence = {"group": group_name, "anchor": anchor, "xref": hex(xref)}
                    if rec is None:
                        tables[key] = {
                            "stride": stride,
                            "stride_hex": hex(stride),
                            "start_offset": entries[0]["offset"],
                            "start_offset_hex": entries[0]["offset_hex"],
                            "end_offset": entries[-1]["offset"] + stride,
                            "end_offset_hex": hex(entries[-1]["offset"] + stride),
                            "entries": entries,
                            "evidence": [evidence],
                            "groups": {group_name: score},
                        }
                    else:
                        rec["evidence"].append(evidence)
                        rec["groups"].setdefault(group_name, score)
    out = list(tables.values())
    for table in out:
        table["evidence"] = sorted(table["evidence"], key=lambda x: (x["group"], x["anchor"], x["xref"]))
    out.sort(key=lambda t: (
        -max((x["anchor_hit_count"] for x in t["groups"].values()), default=0),
        -len(t["entries"]), t["stride"], t["start_offset"]
    ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    root = args.game_root.expanduser().resolve()
    exe = (root / "GoW.exe").resolve()
    if not exe.is_file():
        raise RuntimeError(f"GoW.exe not found: {exe}")

    before = sha256_file(exe)
    data = exe.read_bytes()
    pe = PEImage(data)
    tables = infer_tables(pe)
    after = sha256_file(exe)
    if before != after:
        raise RuntimeError("GoW.exe hash changed during read-only scan")

    best_by_group: dict[str, Optional[dict]] = {}
    for group_name, anchors in ANCHOR_GROUPS.items():
        candidates = []
        for table in tables:
            score = score_table(table["entries"], anchors)
            if score["anchor_hit_count"]:
                candidates.append((score["anchor_hit_count"], len(table["entries"]), table))
        best_by_group[group_name] = max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else None

    report = {
        "schema": 1,
        "scan_kind": "read_only_gow_lua_registration_table_enumeration",
        "game_root": str(root),
        "exe": str(exe),
        "exe_sha256": before,
        "image_base": hex(pe.image_base),
        "candidate_table_count": len(tables),
        "tables": tables,
        "best_table_summary": {
            k: None if v is None else {
                "stride": v["stride"],
                "stride_hex": v["stride_hex"],
                "start_offset_hex": v["start_offset_hex"],
                "entry_count": len(v["entries"]),
                "names": [e["name"] for e in v["entries"]],
            }
            for k, v in best_by_group.items()
        },
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
        "Completionist Map - native Lua registration table enumeration",
        f"exe={exe}",
        f"sha256={before}",
        f"candidate_tables={len(tables)}",
        "source_hashes_unchanged=true active_save_opened=false game_launched=false",
        "",
    ]
    for group_name, table in best_by_group.items():
        lines.append(f"=== BEST {group_name} ===")
        if table is None:
            lines.append("none")
            lines.append("")
            continue
        score = score_table(table["entries"], ANCHOR_GROUPS[group_name])
        lines.append(
            f"stride={table['stride']} start={table['start_offset_hex']} "
            f"entries={len(table['entries'])} anchors={','.join(score['anchor_hits'])}"
        )
        for e in table["entries"]:
            flag = "*" if any(k in e["name"].lower() for k in INTERESTING_NEEDLES) else " "
            extra = ",".join(e["extra_qwords"]) if e["extra_qwords"] else "-"
            lines.append(
                f"{flag} {e['offset_hex']} {e['name']} -> {e['function_rva']} extra=[{extra}]"
            )
        lines.append("")

    lines.append("=== ALL CANDIDATE TABLES (summary) ===")
    for i, table in enumerate(tables, 1):
        names = [e["name"] for e in table["entries"]]
        lines.append(
            f"{i}: stride={table['stride']} start={table['start_offset_hex']} entries={len(names)} "
            f"names={' | '.join(names)}"
        )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sub = best_by_group.get("subobject")
    obj = best_by_group.get("object_lookup")
    print(
        "LUA_REGISTRATION_TABLE_ENUMERATION_PASSED "
        f"tables={len(tables)} "
        f"subobject_entries={0 if sub is None else len(sub['entries'])} "
        f"object_entries={0 if obj is None else len(obj['entries'])}"
    )
    print("source_hashes_unchanged=true active_save_opened=false game_written=false game_launched=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
