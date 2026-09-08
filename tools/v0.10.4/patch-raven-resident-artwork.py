"""Patch the dedicated Raven resident WAD mip tail from its custom texpack.

The v0.10.4 Valkyrie donor proof field-proved that the dedicated Raven map icon
renders from the 0x80A1 resident GPU payload. For these 148x148 map textures the
payload is 12 bytes of resource metadata followed by the swizzled GNF mip tail
(mip levels 2..7). The external texpack carries the complete GNF image.

This helper proves that layout independently against BOTH stock Dock and stock
Valkyrie textures in root.texpack before it is allowed to patch anything. It
then copies only the custom Raven GNF mip tail into the already-isolated Raven
GPU records. Resource names, IDs, definitions, material/model/prototype links,
stock Dock/Valkyrie records and the external texpack are left unchanged.

No game file is modified in-place by this helper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_PATCH_PACK = "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7"

TEXTURES = {
    "diffuse": {
        "raven_name": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
        "raven_hash": 0x19A41F00834C19F3,
        "dock_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "dock_hash": 0x982BF904AB84F2CC,
        "valk_name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "valk_hash": 0x8A041E6BFCE5E589,
        "resident_bytes": 9228,
        "gnf_format": 0x29,  # BC7
        "bits_per_pixel": 8,
    },
    "emissive": {
        "raven_name": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
        "raven_hash": 0x63F1E18FF93B9037,
        "dock_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "dock_hash": 0xFCC664130951154C,
        "valk_name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "valk_hash": 0x9938C16BB9F6A5AC,
        "resident_bytes": 4620,
        "gnf_format": 0x23,  # BC1
        "bits_per_pixel": 4,
    },
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("completionist_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def one_gpu(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"] == name and r["kind"] == 0x1D and r["flags"] == 0x80A1]
    check(len(rows) == 1, f"expected one GPU record for {name}, found {len(rows)}")
    return rows[0]


def one_def(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"] == name and r["kind"] == 1 and r["flags"] == 0x8021]
    check(len(rows) == 1, f"expected one texture definition for {name}, found {len(rows)}")
    return rows[0]


def round_up_pow2(value: int) -> int:
    check(value > 0, "round_up_pow2 requires positive input")
    return 1 << (value - 1).bit_length()


def parse_gnf(blob: bytes) -> dict:
    check(len(blob) >= 0x100, "GNF blob is shorter than its header")
    check(struct.unpack_from("<I", blob, 0)[0] == 0x20464E47, "GNF magic missing")
    format_word = struct.unpack_from("<I", blob, 0x14)[0]
    size_word = struct.unpack_from("<I", blob, 0x18)[0]
    mip_word = struct.unpack_from("<I", blob, 0x1C)[0]
    format_id = (format_word >> 20) & 0x3F
    format_type = (format_word >> 26) & 0xF
    width = (size_word & 0x3FFF) + 1
    height = ((size_word >> 14) & 0x3FFF) + 1
    mip_count = ((mip_word >> 16) & 0xF) + 1
    data_size = struct.unpack_from("<I", blob, 0x2C)[0]
    check(0x100 + data_size <= len(blob), f"GNF data exceeds extracted blob: need {data_size}, have {len(blob)-0x100}")
    return {
        "format": format_id,
        "format_type": format_type,
        "width": width,
        "height": height,
        "mips": mip_count,
        "data_size": data_size,
        "image": blob[0x100:0x100 + data_size],
    }


def mip_layout(meta: dict, bits_per_pixel: int) -> list[dict]:
    # Mirrors GOWTool ConvertDDSToGnf: compressed formats are 4x4 pixel blocks;
    # each mip surface is power-of-two padded and at least 32x32 before swizzle.
    rows = []
    offset = 0
    for level in range(meta["mips"]):
        w = max(meta["width"] >> level, 4)
        h = max(meta["height"] >> level, 4)
        w = (w + 3) & ~3
        h = (h + 3) & ~3
        tempw = max(round_up_pow2(w), 32)
        temph = max(round_up_pow2(h), 32)
        size = tempw * temph * bits_per_pixel // 8
        rows.append({
            "level": level,
            "logical_width": max(meta["width"] >> level, 1),
            "logical_height": max(meta["height"] >> level, 1),
            "swizzled_width": tempw,
            "swizzled_height": temph,
            "offset": offset,
            "bytes": size,
        })
        offset += size
    check(offset == meta["data_size"], f"calculated GNF mip bytes {offset} != header dataSize {meta['data_size']}")
    return rows


def read_texpack_gnf(path: Path, file_hash: int) -> tuple[bytes, dict]:
    # Mirrors GOWTool Texpack::ExportGnf. Only the requested texture blocks are
    # read, so root.texpack does not need to be loaded wholly into memory.
    with path.open("rb") as f:
        f.seek(0x20)
        tex_section_off, block_count, blocks_info_off, tex_count = struct.unpack("<IIII", f.read(16))
        del tex_section_off
        f.seek(0x38)
        texinfos = []
        for i in range(tex_count):
            fh, uh, bio = struct.unpack("<QQQ", f.read(24))
            texinfos.append((i, fh, uh, bio))
        matches = [x for x in texinfos if x[1] == file_hash]
        check(len(matches) == 1, f"texpack {path.name}: expected one file hash {file_hash:016X}, found {len(matches)}")
        tex_index, _, user_hash, first_bio = matches[0]

        blockinfos: dict[int, dict] = {}
        f.seek(blocks_info_off)
        for _ in range(block_count):
            here = f.tell()
            raw = f.read(0x20)
            check(len(raw) == 0x20, "short texpack BlockInfo table")
            block_off, raw_size, block_size = struct.unpack_from("<IIQ", raw, 0)
            mip_start = raw[16]
            mip_end = raw[17]
            toc_idx = struct.unpack_from("<H", raw, 18)[0]
            mip_width = struct.unpack_from("<H", raw, 20)[0]
            mip_height = struct.unpack_from("<H", raw, 22)[0]
            next_sibling = struct.unpack_from("<Q", raw, 24)[0]
            blockinfos[here] = {
                "table_offset": here,
                "block_off": block_off,
                "raw_size": raw_size,
                "block_size": block_size,
                "mip_start": mip_start,
                "mip_end": mip_end,
                "toc_idx": toc_idx,
                "mip_width": mip_width,
                "mip_height": mip_height,
                "next": next_sibling,
            }

        check(first_bio in blockinfos, f"TexInfo blockInfoOff 0x{first_bio:X} not present")
        chain = [blockinfos[first_bio]]
        # GOWTool follows nextSiblingBlockInfoOff and prepends each referenced
        # block before exporting.
        while chain[0]["next"] != 0xFFFFFFFFFFFFFFFF:
            nxt = chain[0]["next"]
            check(nxt in blockinfos, f"missing sibling BlockInfo 0x{nxt:X}")
            check(all(x["table_offset"] != nxt for x in chain), "texpack BlockInfo cycle")
            chain.insert(0, blockinfos[nxt])

        out = bytearray()
        chain_report = []
        for block in chain:
            base = (block["block_off"] << 4) + 4
            f.seek(base)
            header_span, packed_len = struct.unpack("<II", f.read(8))
            f.seek(4, 1)
            wrote_header = header_span != 0x20
            if wrote_header:
                header = f.read(0x100)
                check(len(header) == 0x100, "short GNF header in texpack block")
                out += header
                f.seek(4, 1)
            f.seek(8, 1)
            dec_size_raw = f.read(4)
            check(len(dec_size_raw) == 4, "short texpack block decoded-size field")
            dec_size = struct.unpack("<I", dec_size_raw)[0]
            f.seek(4, 1)
            payload = f.read(dec_size)
            check(len(payload) == dec_size, "short texpack block payload")
            out += payload
            chain_report.append({
                **block,
                "data_base": base,
                "header_span": header_span,
                "packed_len": packed_len,
                "wrote_gnf_header": wrote_header,
                "decoded_bytes": dec_size,
            })

    return bytes(out), {
        "path": str(path),
        "file_hash": f"{file_hash:016X}",
        "texinfo_index": tex_index,
        "user_hash": f"{user_hash:016X}",
        "block_chain": chain_report,
        "exported_gnf_bytes": len(out),
    }


def patch(wad_raw: bytes, root_pack: Path, raven_pack: Path) -> tuple[bytes, dict]:
    check(sha(wad_raw) == EXPECTED_BASE_WAD, "input WAD is not the proven registered Raven base")
    check(sha(raven_pack.read_bytes()) == EXPECTED_PATCH_PACK, "active Raven patch texpack hash changed")

    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "input WAD does not round-trip exactly")

    rows = []
    for label, spec in TEXTURES.items():
        raven_gpu = one_gpu(records, spec["raven_name"])
        raven_def = one_def(records, spec["raven_name"])
        dock_gpu = one_gpu(records, spec["dock_name"])
        valk_gpu = one_gpu(records, spec["valk_name"])

        check(len(raven_gpu["data"]) == spec["resident_bytes"], f"{label}: Raven resident size changed")
        check(len(dock_gpu["data"]) == spec["resident_bytes"], f"{label}: Dock resident size changed")
        check(len(valk_gpu["data"]) == spec["resident_bytes"], f"{label}: Valkyrie resident size changed")
        check(bytes(raven_gpu["data"]) == bytes(dock_gpu["data"]), f"{label}: Raven base resident payload is not the expected Dock clone; remove donor proof first")

        dock_blob, dock_pack_info = read_texpack_gnf(root_pack, spec["dock_hash"])
        valk_blob, valk_pack_info = read_texpack_gnf(root_pack, spec["valk_hash"])
        raven_blob, raven_pack_info = read_texpack_gnf(raven_pack, spec["raven_hash"])
        dock_meta = parse_gnf(dock_blob)
        valk_meta = parse_gnf(valk_blob)
        raven_meta = parse_gnf(raven_blob)

        for name, meta in (("Dock", dock_meta), ("Valkyrie", valk_meta), ("Raven", raven_meta)):
            check(meta["width"] == 148 and meta["height"] == 148 and meta["mips"] == 8,
                  f"{label}: {name} GNF metadata changed: {meta['width']}x{meta['height']} mips={meta['mips']}")
            check(meta["format"] == spec["gnf_format"], f"{label}: {name} GNF format changed: {meta['format']:#x}")

        dock_layout = mip_layout(dock_meta, spec["bits_per_pixel"])
        valk_layout = mip_layout(valk_meta, spec["bits_per_pixel"])
        raven_layout = mip_layout(raven_meta, spec["bits_per_pixel"])
        check([(x["offset"], x["bytes"]) for x in dock_layout] == [(x["offset"], x["bytes"]) for x in valk_layout] == [(x["offset"], x["bytes"]) for x in raven_layout],
              f"{label}: mip layouts differ")

        tail_offset = dock_layout[2]["offset"]
        dock_tail = dock_meta["image"][tail_offset:]
        valk_tail = valk_meta["image"][tail_offset:]
        raven_tail = raven_meta["image"][tail_offset:]
        expected_tail_bytes = spec["resident_bytes"] - 12
        check(len(dock_tail) == len(valk_tail) == len(raven_tail) == expected_tail_bytes,
              f"{label}: mip2+ tail size does not equal resident payload minus 12")

        # This is the critical static proof. Both unrelated stock resources must
        # independently show the same 12-byte-header + exact GNF mip2+ relation.
        check(bytes(dock_gpu["data"])[12:] == dock_tail,
              f"{label}: stock Dock resident payload does not equal GNF mip2+ tail")
        check(bytes(valk_gpu["data"])[12:] == valk_tail,
              f"{label}: stock Valkyrie resident payload does not equal GNF mip2+ tail")

        before = bytes(raven_gpu["data"])
        first12 = before[:12]
        raven_gpu["data"][:] = first12 + raven_tail
        after = bytes(raven_gpu["data"])
        check(len(after) == spec["resident_bytes"], f"{label}: patched resident length changed")
        check(after[12:] == raven_tail, f"{label}: custom Raven mip tail did not persist in memory")
        check(after != bytes(dock_gpu["data"]), f"{label}: custom Raven resident payload still equals Dock")
        check(after != bytes(valk_gpu["data"]), f"{label}: custom Raven resident payload unexpectedly equals Valkyrie")

        rows.append({
            "label": label,
            "resident_bytes": spec["resident_bytes"],
            "resident_header_bytes_preserved": 12,
            "mip_tail_starts_at_level": 2,
            "mip_tail_offset_in_gnf_image": tail_offset,
            "mip_tail_bytes": expected_tail_bytes,
            "mip_layout": dock_layout,
            "stock_dock_relation_proven": True,
            "stock_valkyrie_relation_proven": True,
            "raven_definition_id": raven_def["id"].hex(),
            "raven_gpu_id": raven_gpu["id"].hex(),
            "before_sha256": sha(before),
            "after_sha256": sha(after),
            "custom_gnf_tail_sha256": sha(raven_tail),
            "preserved_first12_hex": first12.hex(),
            "dock_texpack": dock_pack_info,
            "valkyrie_texpack": valk_pack_info,
            "raven_texpack": raven_pack_info,
        })

    out = logical.serialize_wad(records)
    check(len(out) == len(wad_raw), "patched WAD size changed")
    reparsed = logical.parse_wad(out)
    check(logical.serialize_wad(reparsed) == out, "patched WAD does not round-trip")

    for label, spec in TEXTURES.items():
        before_def = one_def(logical.parse_wad(wad_raw), spec["raven_name"])
        after_def = one_def(reparsed, spec["raven_name"])
        check(after_def["id"] == before_def["id"] and bytes(after_def["data"]) == bytes(before_def["data"]),
              f"{label}: Raven texture definition changed")

    report = {
        "result": "RAVEN_RESIDENT_ARTWORK_PATCHED_OFFLINE",
        "input_wad_sha256": sha(wad_raw),
        "output_wad_sha256": sha(out),
        "resident_layout_gate_passed": True,
        "stock_dock_mip_tail_relation_proven": True,
        "stock_valkyrie_mip_tail_relation_proven": True,
        "custom_raven_mip_tail_applied": True,
        "raven_texture_definitions_preserved": True,
        "raven_resource_identity_preserved": True,
        "external_texpack_untouched": True,
        "real_dock_records_untouched": True,
        "real_valkyrie_records_untouched": True,
        "rows": rows,
        "expected_runtime_result": "Dedicated Raven map marker renders custom Raven artwork. Stock Dock and Valkyrie map markers remain unchanged. HUD compass remains DockPoint for this proof.",
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
    }
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--raven-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    wad_raw = args.wad.read_bytes()
    out, report = patch(wad_raw, args.root_texpack, args.raven_texpack)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "output_wad_sha256": report["output_wad_sha256"],
        "resident_layout_gate_passed": report["resident_layout_gate_passed"],
        "stock_dock_mip_tail_relation_proven": report["stock_dock_mip_tail_relation_proven"],
        "stock_valkyrie_mip_tail_relation_proven": report["stock_valkyrie_mip_tail_relation_proven"],
        "custom_raven_mip_tail_applied": report["custom_raven_mip_tail_applied"],
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
