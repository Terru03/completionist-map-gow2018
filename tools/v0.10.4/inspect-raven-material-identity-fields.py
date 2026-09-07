"""Inspect true 0x10/0x20 material identity fields for Raven UI cloning.

Read-only. This corrects the earlier isolation probe, whose second qword label
accidentally read offset 0x18. It determines whether the two varying 64-bit
fields in 384-byte map-icon materials behave like per-material opaque identities
that can be regenerated for a dedicated Completionist Raven material.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
DOCK_INDEX = 13699
SIBLINGS = {
    "valkyrie": 13705,
    "fight": 13707,
    "primary_quest": 13708,
    "vendor": 13712,
}


def check(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def align16(v: int) -> int:
    return (v + 15) & ~15


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii", errors="ignore"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def parse_wad(raw: bytes) -> tuple[list[dict], list[dict]]:
    records, payloads = [], []
    stack: list[int] = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short WAD header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start, end = off + 96, off + 96 + size
        padded = align16(end)
        check(padded <= len(raw), f"short WAD payload at {off:#x}")
        header = raw[off:start]
        rec = {
            "physical_index": len(records),
            "payload_index": len(payloads) if size else None,
            "offset": off,
            "kind": kind,
            "flags": flags,
            "size": size,
            "id": header[8:24],
            "name": header[24:80].split(b"\0", 1)[0].decode("ascii", errors="replace"),
            "data": raw[start:end],
            "parent": stack[-1] if stack else None,
        }
        records.append(rec)
        if size:
            payloads.append(rec)
        if kind == 2:
            stack.append(rec["physical_index"])
        elif kind == 3:
            check(stack, f"unmatched group end at {off:#x}")
            stack.pop()
        off = padded
    check(not stack and off == len(raw), "WAD walk did not end cleanly")
    return records, payloads


def summary(r: dict) -> dict:
    return {
        "physical_index": r["physical_index"],
        "payload_index": r["payload_index"],
        "offset": f"0x{r['offset']:X}",
        "name": r["name"],
        "id": r["id"].hex(),
        "bytes": r["size"],
        "flags": f"0x{r['flags']:X}",
    }


def all_occurrences(payloads: list[dict], needle: bytes) -> list[dict]:
    out = []
    for r in payloads:
        at = 0
        while True:
            pos = r["data"].find(needle, at)
            if pos < 0:
                break
            out.append({
                "payload_index": r["payload_index"],
                "name": r["name"],
                "offset": f"0x{pos:X}",
            })
            at = pos + 1
    return out


def external_hits(paths: list[Path], needle: bytes) -> list[dict]:
    out = []
    for p in paths:
        try:
            blob = p.read_bytes()
        except OSError:
            continue
        count = blob.count(needle)
        if count:
            out.append({"path": str(p), "count": count})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    output = args.output.resolve()
    check(not output.is_relative_to(game), "output must stay outside game directory")

    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    exe_path = game / "GoW.exe"
    wad_raw = wad_path.read_bytes()
    exe_raw = exe_path.read_bytes()
    check(sha256(wad_raw) == EXPECTED_WAD, "unexpected r_ui.wad hash")
    check(sha256(exe_raw) == EXPECTED_EXE, "unexpected GoW.exe hash")

    records, payloads = parse_wad(wad_raw)
    check((len(records), len(payloads)) == (53777, 20407), "unexpected WAD counts")

    materials = [
        r for r in payloads
        if r["kind"] == 1 and r["flags"] == 0x14 and r["size"] == 384 and r["name"].startswith("MAT_")
    ]
    check(any(r["payload_index"] == DOCK_INDEX for r in materials), "Dock material missing")

    rows = []
    q10_map: dict[int, list[int]] = collections.defaultdict(list)
    q20_map: dict[int, list[int]] = collections.defaultdict(list)
    for r in materials:
        q10 = struct.unpack_from("<Q", r["data"], 0x10)[0]
        q20 = struct.unpack_from("<Q", r["data"], 0x20)[0]
        q10_map[q10].append(r["payload_index"])
        q20_map[q20].append(r["payload_index"])
        rows.append({
            "material": summary(r),
            "qword_0x10": f"{q10:016X}",
            "qword_0x20": f"{q20:016X}",
            "name_hash": f"{name_hash(r['name']):016X}",
            "suffix_hash": f"{name_hash(r['name'].removeprefix('MAT_')):016X}",
        })

    selected = {}
    indices = {"dock": DOCK_INDEX, **SIBLINGS}
    by_index = {r["payload_index"]: r for r in materials}
    for label, idx in indices.items():
        r = by_index[idx]
        q10 = struct.unpack_from("<Q", r["data"], 0x10)[0]
        q20 = struct.unpack_from("<Q", r["data"], 0x20)[0]
        selected[label] = {
            "material": summary(r),
            "qword_0x10": f"{q10:016X}",
            "qword_0x20": f"{q20:016X}",
            "qword_0x10_material_users": q10_map[q10],
            "qword_0x20_material_users": q20_map[q20],
            "qword_0x10_payload_occurrences": all_occurrences(payloads, struct.pack("<Q", q10)),
            "qword_0x20_payload_occurrences": all_occurrences(payloads, struct.pack("<Q", q20)),
        }

    dock = by_index[DOCK_INDEX]
    comparisons = {}
    for label, idx in SIBLINGS.items():
        other = by_index[idx]
        diff = [i for i, (a, b) in enumerate(zip(dock["data"], other["data"])) if a != b]
        comparisons[label] = {
            "different_offsets": [f"0x{i:X}" for i in diff],
            "only_identity_qwords_differ": diff == list(range(0x10, 0x18)) + list(range(0x20, 0x28)),
        }

    dcb_files = list((game / "exec/dc/pc_le").glob("*.dcb"))
    external_paths = dcb_files + [exe_path]
    dock_q10 = struct.unpack_from("<Q", dock["data"], 0x10)[0]
    dock_q20 = struct.unpack_from("<Q", dock["data"], 0x20)[0]
    external = {
        "dock_qword_0x10": external_hits(external_paths, struct.pack("<Q", dock_q10)),
        "dock_qword_0x20": external_hits(external_paths, struct.pack("<Q", dock_q20)),
    }

    reserved_q10 = name_hash("CompletionistRavenMaterialIdentity0")
    reserved_q20 = name_hash("CompletionistRavenMaterialIdentity1")
    existing_q10 = set(q10_map)
    existing_q20 = set(q20_map)
    reserved = {
        "qword_0x10": f"{reserved_q10:016X}",
        "qword_0x20": f"{reserved_q20:016X}",
        "qword_0x10_collision": reserved_q10 in existing_q10 or reserved_q10 in existing_q20,
        "qword_0x20_collision": reserved_q20 in existing_q10 or reserved_q20 in existing_q20,
    }

    all_unique_q10 = all(len(v) == 1 for v in q10_map.values())
    all_unique_q20 = all(len(v) == 1 for v in q20_map.values())
    dock_self_only_q10 = selected["dock"]["qword_0x10_payload_occurrences"] == [
        {"payload_index": DOCK_INDEX, "name": dock["name"], "offset": "0x10"}
    ]
    dock_self_only_q20 = selected["dock"]["qword_0x20_payload_occurrences"] == [
        {"payload_index": DOCK_INDEX, "name": dock["name"], "offset": "0x20"}
    ]
    external_clear = not external["dock_qword_0x10"] and not external["dock_qword_0x20"]
    comparisons_clean = all(v["only_identity_qwords_differ"] for v in comparisons.values())
    can_generate = (
        all_unique_q10 and all_unique_q20 and dock_self_only_q10 and dock_self_only_q20
        and external_clear and comparisons_clean
        and not reserved["qword_0x10_collision"] and not reserved["qword_0x20_collision"]
    )

    report = {
        "result": "RAVEN_MATERIAL_IDENTITY_FIELDS_INSPECTED",
        "game_files_written": False,
        "source_hashes": {"r_ui_wad": sha256(wad_raw), "GoW_exe": sha256(exe_raw)},
        "material_count": len(materials),
        "selected": selected,
        "sibling_comparisons": comparisons,
        "global_uniqueness": {
            "qword_0x10_unique_across_materials": all_unique_q10,
            "qword_0x20_unique_across_materials": all_unique_q20,
            "dock_qword_0x10_self_only_in_wad_payloads": dock_self_only_q10,
            "dock_qword_0x20_self_only_in_wad_payloads": dock_self_only_q20,
            "dock_identity_fields_absent_from_dcb_and_exe": external_clear,
        },
        "reserved_completionist_raven_pair": reserved,
        "decision": {
            "safe_to_generate_fresh_identity_pair_for_offline_clone": can_generate,
            "rule": (
                "Proceed only when both qwords are per-material unique, the Dock values occur only at their own "
                "material offsets, no DCB/EXE copies exist, sibling map-icon materials differ only at 0x10 and 0x20, "
                "and the reserved Raven values do not collide."
            ),
        },
        "next_gate": (
            "If decision is true, build a Raven-only material/model/prototype chain with fresh qword identities and "
            "fresh texture definition/GPU identities. Otherwise stop and trace the failing condition."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Materials inspected: {len(materials)}")
    print(f"Safe fresh identity pair: {can_generate}")
    print(f"Saved: {output}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
