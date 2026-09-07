"""Inspect the remaining Raven-only material/texture isolation problem.

Read-only.  This tool keeps every physical r_ui.wad record, correlates the two
opaque Dock artwork-material qwords, and looks for stock texture definitions
that could safely act as Raven-only donor identities without changing any real
Dock resource.  It never writes the game directory.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import struct

EXPECTED_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"
EXPECTED_DCB = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
EXPECTED_EXE = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
DOCK_DIFFUSE = "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC"
DOCK_EMISSIVE = "TX_mapmarker_docklocation_emissive_FCC664130951154C"
DOCK_MATERIAL_INDEX = 13699
SIBLING_MATERIAL_INDICES = {
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


def parse_wad(raw: bytes) -> tuple[list[dict], list[dict], dict[int, list[int]]]:
    records: list[dict] = []
    payloads: list[dict] = []
    children: dict[int, list[int]] = collections.defaultdict(list)
    stack: list[int] = []
    off = 0
    while off < len(raw):
        check(off + 96 <= len(raw), f"short WAD header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start, end = off + 96, off + 96 + size
        padded = align16(end)
        check(padded <= len(raw), f"short WAD payload at {off:#x}")
        header = raw[off:start]
        name = header[24:80].split(b"\0", 1)[0].decode("ascii", errors="replace")
        rec = {
            "physical_index": len(records),
            "payload_index": len(payloads) if size else None,
            "offset": off,
            "kind": kind,
            "flags": flags,
            "size": size,
            "id": header[8:24],
            "name": name,
            "data": raw[start:end],
            "parent": stack[-1] if stack else None,
        }
        records.append(rec)
        if rec["parent"] is not None:
            children[rec["parent"]].append(rec["physical_index"])
        if size:
            payloads.append(rec)
        if kind == 2:
            stack.append(rec["physical_index"])
        elif kind == 3:
            check(stack, f"unmatched WAD group end at {off:#x}")
            stack.pop()
        off = padded
    check(not stack and off == len(raw), "WAD walk did not end cleanly")
    return records, payloads, children


def dds_meta(path: Path) -> dict | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) < 128 or raw[:4] != b"DDS ":
        return None
    height, width = struct.unpack_from("<II", raw, 12)
    mips = struct.unpack_from("<I", raw, 28)[0] or 1
    fourcc = raw[84:88].decode("ascii", errors="replace")
    dxgi = None
    if fourcc == "DX10" and len(raw) >= 132:
        dxgi = struct.unpack_from("<I", raw, 128)[0]
    fmt = {
        "DXT1": "BC1_UNORM",
        "DXT3": "BC2_UNORM",
        "DXT5": "BC3_UNORM",
        "ATI1": "BC4_UNORM",
        "BC4U": "BC4_UNORM",
        "ATI2": "BC5_UNORM",
        "BC5U": "BC5_UNORM",
    }.get(fourcc)
    if fourcc == "DX10":
        fmt = {
            28: "R8G8B8A8_UNORM", 29: "R8G8B8A8_UNORM_SRGB",
            71: "BC1_UNORM", 72: "BC1_UNORM_SRGB",
            74: "BC2_UNORM", 75: "BC2_UNORM_SRGB",
            77: "BC3_UNORM", 78: "BC3_UNORM_SRGB",
            80: "BC4_UNORM", 81: "BC4_SNORM",
            83: "BC5_UNORM", 84: "BC5_SNORM",
            98: "BC7_UNORM", 99: "BC7_UNORM_SRGB",
        }.get(dxgi, f"DXGI_{dxgi}")
    return {"width": width, "height": height, "mips": mips, "format": fmt,
            "fourcc": fourcc, "dxgi": dxgi, "bytes": len(raw)}


def record_summary(r: dict) -> dict:
    return {
        "physical_index": r["physical_index"],
        "payload_index": r["payload_index"],
        "offset": f"0x{r['offset']:X}",
        "kind": f"0x{r['kind']:X}",
        "flags": f"0x{r['flags']:X}",
        "bytes": r["size"],
        "name": r["name"],
        "id": r["id"].hex(),
    }


def occurrences(payloads: list[dict], needle: bytes, exclude_phys: int | None = None) -> list[dict]:
    out = []
    for r in payloads:
        if exclude_phys is not None and r["physical_index"] == exclude_phys:
            continue
        start = 0
        while True:
            at = r["data"].find(needle, start)
            if at < 0:
                break
            out.append({"payload_index": r["payload_index"], "name": r["name"],
                        "offset": f"0x{at:X}"})
            start = at + 1
            if len(out) >= 32:
                return out
    return out


def external_hits(paths: list[Path], needles: dict[str, bytes]) -> dict:
    result = {}
    for label, needle in needles.items():
        rows = []
        if not needle:
            result[label] = rows
            continue
        for p in paths:
            try:
                blob = p.read_bytes()
            except OSError:
                continue
            count = blob.count(needle)
            if count:
                rows.append({"path": str(p), "count": count})
        result[label] = rows
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--dds-dir", type=Path,
                    default=Path(os.environ.get("LOCALAPPDATA", ".")) / "CompletionistMap/work/v0.10.2/r_ui-dds")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    output = args.output.resolve()
    check(not output.is_relative_to(game), "output must stay outside game directory")
    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    dcb_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    exe_path = game / "GoW.exe"
    wad_raw, dcb_raw, exe_raw = wad_path.read_bytes(), dcb_path.read_bytes(), exe_path.read_bytes()
    check(sha256(wad_raw) == EXPECTED_WAD, "unexpected r_ui.wad hash")
    check(sha256(dcb_raw) == EXPECTED_DCB, "unexpected wad_r_ui.dcb hash")
    check(sha256(exe_raw) == EXPECTED_EXE, "unexpected GoW.exe hash")

    records, payloads, children = parse_wad(wad_raw)
    check((len(records), len(payloads)) == (53777, 20407), "unexpected WAD record counts")

    name_hash_map: dict[int, set[str]] = collections.defaultdict(set)
    for r in records:
        if r["name"]:
            name_hash_map[name_hash(r["name"])].add(r["name"])

    def group_rows(rec: dict) -> list[dict]:
        parent = rec["parent"]
        return [records[i] for i in children.get(parent, [])] if parent is not None else []

    def material_info(index: int) -> dict:
        m = payloads[index]
        check(m["flags"] == 0x14 and len(m["data"]) == 384 and m["name"].startswith("MAT_"),
              f"unexpected material at {index}")
        q10, q20 = struct.unpack_from("<QQ", m["data"], 0x10)
        links = [r for r in group_rows(m) if r["kind"] == 1 and r["size"] == 0]
        candidates = {"material_name": m["name"], "material_suffix": m["name"].removeprefix("MAT_")}
        for i, r in enumerate(links):
            candidates[f"link_{i}_{r['name']}"] = r["name"]
        candidate_hashes = {k: f"{name_hash(v):016X}" for k, v in candidates.items()}
        return {
            "record": record_summary(m),
            "qword_0x10": f"{q10:016X}",
            "qword_0x20": f"{q20:016X}",
            "qword_0x10_name_hash_matches": sorted(name_hash_map.get(q10, [])),
            "qword_0x20_name_hash_matches": sorted(name_hash_map.get(q20, [])),
            "candidate_name_hashes": candidate_hashes,
            "qword_0x10_payload_occurrences": occurrences(payloads, struct.pack("<Q", q10)),
            "qword_0x20_payload_occurrences": occurrences(payloads, struct.pack("<Q", q20)),
            "group_links": [record_summary(r) for r in links],
        }

    dock_material = material_info(DOCK_MATERIAL_INDEX)
    siblings = {k: material_info(v) for k, v in SIBLING_MATERIAL_INDICES.items()}

    zero_refs: dict[bytes, list[dict]] = collections.defaultdict(list)
    for r in records:
        if r["kind"] == 1 and r["size"] == 0:
            zero_refs[r["id"]].append(r)

    dds_by_stem = {}
    if args.dds_dir.is_dir():
        for p in args.dds_dir.glob("*.dds"):
            dds_by_stem[p.stem.lower()] = (p, dds_meta(p))

    texture_defs = [r for r in payloads
                    if r["kind"] == 1 and r["flags"] == 0x8021 and r["size"] == 356
                    and r["name"].startswith("TX_")]
    by_name = {r["name"].lower(): r for r in texture_defs}
    check(DOCK_DIFFUSE.lower() in by_name and DOCK_EMISSIVE.lower() in by_name, "Dock texture definitions missing")

    dcb_files = list((game / "exec/dc/pc_le").glob("*.dcb"))
    external_paths = dcb_files + [exe_path]

    def texture_info(r: dict, include_external: bool = False) -> dict:
        pi = r["payload_index"]
        gpu = payloads[pi - 1] if pi and pi > 0 else None
        gpu_ok = bool(gpu and gpu["kind"] == 0x1D and gpu["flags"] == 0x80A1 and gpu["name"] == r["name"])
        meta_entry = dds_by_stem.get(r["name"].lower())
        meta = meta_entry[1] if meta_entry else None
        payload_refs = occurrences(payloads, r["id"], exclude_phys=r["physical_index"])
        suffix = r["name"].rsplit("_", 1)[-1]
        file_hash = int(suffix, 16) if len(suffix) == 16 and all(c in "0123456789abcdefABCDEF" for c in suffix) else None
        ext = {}
        if include_external:
            needles = {"resource_id": r["id"]}
            if file_hash is not None:
                needles["file_hash_le"] = struct.pack("<Q", file_hash)
                needles["file_hash_be"] = struct.pack(">Q", file_hash)
            ext = external_hits(external_paths, needles)
        return {
            "definition": record_summary(r),
            "gpu_pair": record_summary(gpu) if gpu_ok else None,
            "dds": meta,
            "zero_size_link_users": [record_summary(x) for x in zero_refs.get(r["id"], [])],
            "payload_id_occurrences": payload_refs,
            "file_hash": f"{file_hash:016X}" if file_hash is not None else None,
            "external_hits": ext,
        }

    dock_diff = texture_info(by_name[DOCK_DIFFUSE.lower()], True)
    dock_emis = texture_info(by_name[DOCK_EMISSIVE.lower()], True)
    target_meta = {"diffuse": dock_diff["dds"], "emissive": dock_emis["dds"]}

    donor_sets = {}
    for role, dock in [("diffuse", dock_diff), ("emissive", dock_emis)]:
        wanted = dock["dds"]
        rows = []
        for r in texture_defs:
            if r["name"].lower() in {DOCK_DIFFUSE.lower(), DOCK_EMISSIVE.lower()}:
                continue
            meta_entry = dds_by_stem.get(r["name"].lower())
            meta = meta_entry[1] if meta_entry else None
            if wanted is not None:
                if meta is None:
                    continue
                if any(meta.get(k) != wanted.get(k) for k in ("width", "height", "mips", "format")):
                    continue
            info = texture_info(r, False)
            if info["gpu_pair"] is None:
                continue
            # Expensive external scans only for locally unreferenced candidates.
            locally_unused = not info["zero_size_link_users"] and not info["payload_id_occurrences"]
            if locally_unused:
                full = texture_info(r, True)
                ext_busy = any(full["external_hits"].get(k) for k in full["external_hits"])
                full["candidate_grade"] = "A_ORPHAN" if not ext_busy else "B_EXTERNAL_REFERENCE"
                rows.append(full)
        rows.sort(key=lambda x: (x["candidate_grade"], x["definition"]["name"]))
        donor_sets[role] = rows

    report = {
        "result": "RAVEN_MATERIAL_TEXTURE_ISOLATION_INSPECTED",
        "game_files_written": False,
        "source_hashes": {"r_ui_wad": sha256(wad_raw), "wad_r_ui_dcb": sha256(dcb_raw), "GoW_exe": sha256(exe_raw)},
        "record_counts": {"physical": len(records), "payloads": len(payloads), "texture_definitions": len(texture_defs)},
        "dds_inventory": {"directory": str(args.dds_dir), "available": args.dds_dir.is_dir(), "matched_files": len(dds_by_stem)},
        "dock_material": dock_material,
        "sibling_materials": siblings,
        "dock_textures": {"diffuse": dock_diff, "emissive": dock_emis},
        "donor_candidates": donor_sets,
        "decision": {
            "grade_A_diffuse_count": sum(x.get("candidate_grade") == "A_ORPHAN" for x in donor_sets["diffuse"]),
            "grade_A_emissive_count": sum(x.get("candidate_grade") == "A_ORPHAN" for x in donor_sets["emissive"]),
            "rule": "Use a donor route only if both roles have Grade A orphan identities. Otherwise clone new texture definitions/GPU identities; never overwrite stock Dock hashes.",
        },
        "next_gate": "Choose orphan donor identities only if both diffuse and emissive are structurally unreferenced; otherwise build fresh Raven texture definition/GPU clones and a Raven-only material/model/prototype chain.",
    }
    check(wad_path.read_bytes() == wad_raw and dcb_path.read_bytes() == dcb_raw and exe_path.read_bytes() == exe_raw,
          "source files changed during inspection")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"Texture definitions: {len(texture_defs)}")
    print(f"Grade A diffuse donors: {report['decision']['grade_A_diffuse_count']}")
    print(f"Grade A emissive donors: {report['decision']['grade_A_emissive_count']}")
    print("No God of War files were modified.")


if __name__ == "__main__":
    main()
