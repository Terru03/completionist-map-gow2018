"""Inspect how stock map-icon resident WAD payloads relate to root.texpack blocks.

Read-only diagnostic. The dedicated Completionist Raven map GO is already proven
to render from its resident 0x80A1 WAD payload: replacing only that payload with
the stock Valkyrie payload made only the Raven render as Valkyrie. A generated
96x96 Raven payload produced corrupted/tiled pixels, so the remaining problem is
the exact resident byte layout, not resource selection.

This probe does not guess a layout. It compares stock Dock and Valkyrie resident
GPU payloads byte-for-byte against every block and block concatenation exported
from root.texpack for the same texture hashes, including prefixes/suffixes and
all contiguous block subsets. It records mip ranges and block metadata so the
next writer can be based on an observed stock relation.

No game file, save, boot option or progression state is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent

TARGETS = {
    "dock_diffuse": {
        "name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "file_hash": 0x982BF904AB84F2CC,
    },
    "dock_emissive": {
        "name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "file_hash": 0xFCC664130951154C,
    },
    "valkyrie_diffuse": {
        "name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "file_hash": 0x8A041E6BFCE5E589,
    },
    "valkyrie_emissive": {
        "name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "file_hash": 0x9938C16BB9F6A5AC,
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
    check(len(rows) == 1, f"expected one resident GPU record for {name}, found {len(rows)}")
    return rows[0]


def parse_texpack(path: Path) -> dict:
    with path.open("rb") as f:
        f.seek(0x20)
        head = f.read(16)
        check(len(head) == 16, "short texpack header")
        tex_section_off, block_count, blocks_info_off, tex_count = struct.unpack("<IIII", head)

        f.seek(0x38)
        texinfos = []
        for i in range(tex_count):
            raw = f.read(0x18)
            check(len(raw) == 0x18, "short TexInfo table")
            file_hash, user_hash, block_info_off = struct.unpack("<QQQ", raw)
            texinfos.append({
                "index": i,
                "file_hash": file_hash,
                "user_hash": user_hash,
                "block_info_off": block_info_off,
            })

        f.seek(blocks_info_off)
        blockinfos: dict[int, dict] = {}
        for i in range(block_count):
            table_offset = f.tell()
            raw = f.read(0x20)
            check(len(raw) == 0x20, "short BlockInfo table")
            block_off, raw_size, block_size = struct.unpack_from("<IIQ", raw, 0)
            mip_start = raw[16]
            mip_end = raw[17]
            toc_file_idx = struct.unpack_from("<H", raw, 18)[0]
            mip_width = struct.unpack_from("<H", raw, 20)[0]
            mip_height = struct.unpack_from("<H", raw, 22)[0]
            next_sibling = struct.unpack_from("<Q", raw, 24)[0]
            blockinfos[table_offset] = {
                "index": i,
                "table_offset": table_offset,
                "block_off": block_off,
                "raw_size": raw_size,
                "block_size": block_size,
                "mip_start": mip_start,
                "mip_end": mip_end,
                "toc_file_idx": toc_file_idx,
                "mip_width": mip_width,
                "mip_height": mip_height,
                "next_sibling": next_sibling,
            }

    return {
        "path": path,
        "tex_section_off": tex_section_off,
        "block_count": block_count,
        "blocks_info_off": blocks_info_off,
        "tex_count": tex_count,
        "texinfos": texinfos,
        "blockinfos": blockinfos,
    }


def ordered_chain(pack: dict, file_hash: int) -> tuple[dict, list[dict]]:
    matches = [x for x in pack["texinfos"] if x["file_hash"] == file_hash]
    check(len(matches) == 1, f"root.texpack expected one file hash {file_hash:016X}, found {len(matches)}")
    texinfo = matches[0]
    first = texinfo["block_info_off"]
    check(first in pack["blockinfos"], f"missing first BlockInfo 0x{first:X}")

    # Mirrors GOWTool Texpack::ExportGnf: start with TexInfo's BlockInfo and
    # repeatedly prepend the referenced sibling.
    chain = [pack["blockinfos"][first]]
    seen = {first}
    while chain[0]["next_sibling"] != 0xFFFFFFFFFFFFFFFF:
        nxt = chain[0]["next_sibling"]
        check(nxt in pack["blockinfos"], f"missing sibling BlockInfo 0x{nxt:X}")
        check(nxt not in seen, "BlockInfo sibling cycle")
        seen.add(nxt)
        chain.insert(0, pack["blockinfos"][nxt])
    return texinfo, chain


def read_storage_block(path: Path, info: dict) -> dict:
    with path.open("rb") as f:
        data_base = (int(info["block_off"]) << 4) + 4
        f.seek(data_base)
        raw = f.read(12)
        check(len(raw) == 12, f"short storage header at 0x{data_base:X}")
        header_span, packed_len, unknown0 = struct.unpack("<III", raw)

        gnf_header = b""
        if header_span != 0x20:
            gnf_header = f.read(0x100)
            check(len(gnf_header) == 0x100, "short GNF header")
            trailer = f.read(4)
            check(len(trailer) == 4, "short GNF-header trailer")
        else:
            trailer = b""

        skip8 = f.read(8)
        check(len(skip8) == 8, "short storage pre-decoded-size region")
        dec_size_raw = f.read(4)
        check(len(dec_size_raw) == 4, "short decoded-size field")
        dec_size = struct.unpack("<I", dec_size_raw)[0]
        skip4 = f.read(4)
        check(len(skip4) == 4, "short storage pre-payload region")
        payload = f.read(dec_size)
        check(len(payload) == dec_size, f"short block payload: wanted {dec_size}, got {len(payload)}")

    return {
        **info,
        "data_base": data_base,
        "header_span": header_span,
        "packed_len": packed_len,
        "unknown0": unknown0,
        "has_gnf_header": bool(gnf_header),
        "gnf_header_sha256": sha(gnf_header) if gnf_header else None,
        "dec_size": dec_size,
        "payload": payload,
        "payload_sha256": sha(payload),
        "payload_first32_hex": payload[:32].hex(),
        "payload_last32_hex": payload[-32:].hex(),
    }


def diff_stats(a: bytes, b: bytes) -> dict:
    if len(a) != len(b):
        return {"same_length": False, "a_bytes": len(a), "b_bytes": len(b)}
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return {
        "same_length": True,
        "bytes": len(a),
        "equal": not diffs,
        "different_bytes": len(diffs),
        "first_difference": diffs[0] if diffs else None,
        "last_difference": diffs[-1] if diffs else None,
    }


def relation(name: str, resident: bytes, resident_body: bytes, blocks: list[dict]) -> dict:
    payloads = [b["payload"] for b in blocks]
    concat = b"".join(payloads)
    reverse_concat = b"".join(reversed(payloads))

    exact = []
    candidates: list[tuple[str, bytes]] = [
        ("all_blocks_concat", concat),
        ("all_blocks_reverse_concat", reverse_concat),
        ("concat_prefix_resident", concat[:len(resident)]),
        ("concat_suffix_resident", concat[-len(resident):] if len(concat) >= len(resident) else b""),
        ("concat_prefix_body", concat[:len(resident_body)]),
        ("concat_suffix_body", concat[-len(resident_body):] if len(concat) >= len(resident_body) else b""),
    ]
    for i, p in enumerate(payloads):
        candidates.extend([
            (f"block_{i}_full", p),
            (f"block_{i}_prefix_resident", p[:len(resident)]),
            (f"block_{i}_suffix_resident", p[-len(resident):] if len(p) >= len(resident) else b""),
            (f"block_{i}_prefix_body", p[:len(resident_body)]),
            (f"block_{i}_suffix_body", p[-len(resident_body):] if len(p) >= len(resident_body) else b""),
        ])

    # Every contiguous block subset in both natural and reversed order.
    for start in range(len(payloads)):
        for end in range(start + 1, len(payloads) + 1):
            subset = b"".join(payloads[start:end])
            candidates.append((f"blocks_{start}_{end-1}_concat", subset))
            candidates.append((f"blocks_{start}_{end-1}_suffix_body", subset[-len(resident_body):] if len(subset) >= len(resident_body) else b""))

    for label, blob in candidates:
        if blob == resident:
            exact.append({"candidate": label, "matches": "resident_full"})
        if blob == resident_body:
            exact.append({"candidate": label, "matches": "resident_body_after_12"})

    body_in_concat = concat.find(resident_body)
    full_in_concat = concat.find(resident)

    same_size_block_stats = []
    for i, block in enumerate(blocks):
        p = block["payload"]
        if len(p) in {len(resident), len(resident_body)}:
            same_size_block_stats.append({
                "block_index_in_chain": i,
                "payload_bytes": len(p),
                "vs_resident_full": diff_stats(p, resident),
                "vs_resident_body": diff_stats(p, resident_body),
            })

    return {
        "target": name,
        "resident_bytes": len(resident),
        "resident_sha256": sha(resident),
        "resident_prefix12_hex": resident[:12].hex(),
        "resident_body_bytes": len(resident_body),
        "resident_body_sha256": sha(resident_body),
        "resident_body_first32_hex": resident_body[:32].hex(),
        "resident_body_last32_hex": resident_body[-32:].hex(),
        "concat_payload_bytes": len(concat),
        "concat_payload_sha256": sha(concat),
        "resident_full_offset_in_concat": full_in_concat,
        "resident_body_offset_in_concat": body_in_concat,
        "exact_relations": exact,
        "same_size_block_stats": same_size_block_stats,
    }


def serialisable_block(block: dict) -> dict:
    return {k: v for k, v in block.items() if k != "payload"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    wad_raw = args.wad.read_bytes()
    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "r_ui.wad does not round-trip exactly with the pinned parser")

    pack = parse_texpack(args.root_texpack)
    results = {}
    for label, spec in TARGETS.items():
        gpu = one_gpu(records, spec["name"])
        resident = bytes(gpu["data"])
        resident_body = resident[12:]
        texinfo, chain_infos = ordered_chain(pack, spec["file_hash"])
        blocks = [read_storage_block(args.root_texpack, x) for x in chain_infos]
        results[label] = {
            "wad_resource_name": spec["name"],
            "file_hash": f"{spec['file_hash']:016X}",
            "texinfo": {
                "index": texinfo["index"],
                "file_hash": f"{texinfo['file_hash']:016X}",
                "user_hash": f"{texinfo['user_hash']:016X}",
                "block_info_off": texinfo["block_info_off"],
            },
            "chain": [serialisable_block(x) for x in blocks],
            "relation": relation(label, resident, resident_body, blocks),
        }

    exact_count = sum(len(v["relation"]["exact_relations"]) for v in results.values())
    same_size_blocks = sum(len(v["relation"]["same_size_block_stats"]) for v in results.values())
    report = {
        "result": "RESIDENT_TEXPACK_BLOCK_RELATION_INSPECTED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": sha(wad_raw),
        "root_texpack_sha256": sha(args.root_texpack.read_bytes()),
        "root_texpack": {
            "tex_count": pack["tex_count"],
            "block_count": pack["block_count"],
            "blocks_info_off": pack["blocks_info_off"],
        },
        "targets": results,
        "summary": {
            "exact_relation_count": exact_count,
            "same_size_block_comparison_count": same_size_blocks,
            "next_gate": (
                "Use only an observed stock byte relation. If a resident body exactly matches one streamed block or a contiguous block suffix, construct the Raven resident bytes from the corresponding Raven texpack block. If no exact relation exists, stop assuming the resident payload is a copied texpack mip block and decode the resident tiling independently."
            ),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "result": report["result"],
        "wad_sha256": report["wad_sha256"],
        "root_texpack_sha256": report["root_texpack_sha256"],
        "exact_relation_count": exact_count,
        "same_size_block_comparison_count": same_size_blocks,
        "targets": {
            k: {
                "resident_bytes": v["relation"]["resident_bytes"],
                "resident_body_bytes": v["relation"]["resident_body_bytes"],
                "chain": [
                    {
                        "mip_start": b["mip_start"],
                        "mip_end": b["mip_end"],
                        "raw_size": b["raw_size"],
                        "dec_size": b["dec_size"],
                        "payload_sha256": b["payload_sha256"],
                    }
                    for b in v["chain"]
                ],
                "exact_relations": v["relation"]["exact_relations"],
            }
            for k, v in results.items()
        },
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
