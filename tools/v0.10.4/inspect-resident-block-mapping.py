"""Map stock resident map-icon bytes against their streamed texture bytes.

Read-only diagnostic for the v0.10.4 Completionist Raven artwork pipeline.
The dedicated Raven map GO and resident-payload selection are field-proven, but
a generated 96x96 Morton-swizzled surface rendered as corrupted horizontal
blocks. This probe therefore avoids assuming dimensions or tiling.

For stock Dock and Valkyrie diffuse/emissive textures it:
  * measures byte-level common prefixes/suffixes against root.texpack payloads;
  * tests every BC-block alignment on both resident and streamed payloads;
  * scores exact block reuse, with a separate score for low-frequency blocks so
    transparent/background blocks do not dominate the result;
  * records source block positions and stride/delta patterns when matches exist;
  * tests whether the resident bytes are likely a reordered/subset view of the
    streamed compressed blocks versus a separately generated resident image.

No game file, save, boot option or progression state is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent

TARGETS = {
    "dock_diffuse": {
        "name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "file_hash": 0x982BF904AB84F2CC,
        "block_bytes": 16,
    },
    "dock_emissive": {
        "name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "file_hash": 0xFCC664130951154C,
        "block_bytes": 8,
    },
    "valkyrie_diffuse": {
        "name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "file_hash": 0x8A041E6BFCE5E589,
        "block_bytes": 16,
    },
    "valkyrie_emissive": {
        "name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "file_hash": 0x9938C16BB9F6A5AC,
        "block_bytes": 8,
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
        tex_section_off, block_count, blocks_info_off, tex_count = struct.unpack("<IIII", f.read(16))
        f.seek(0x38)
        texinfos = []
        for i in range(tex_count):
            fh, uh, bio = struct.unpack("<QQQ", f.read(24))
            texinfos.append((i, fh, uh, bio))
        f.seek(blocks_info_off)
        blocks = {}
        for i in range(block_count):
            off = f.tell()
            raw = f.read(0x20)
            block_off, raw_size, block_size = struct.unpack_from("<IIQ", raw, 0)
            blocks[off] = {
                "index": i,
                "table_offset": off,
                "block_off": block_off,
                "raw_size": raw_size,
                "block_size": block_size,
                "mip_start": raw[16],
                "mip_end": raw[17],
                "mip_width": struct.unpack_from("<H", raw, 20)[0],
                "mip_height": struct.unpack_from("<H", raw, 22)[0],
                "next": struct.unpack_from("<Q", raw, 24)[0],
            }
    return {
        "path": path,
        "tex_section_off": tex_section_off,
        "block_count": block_count,
        "blocks_info_off": blocks_info_off,
        "tex_count": tex_count,
        "texinfos": texinfos,
        "blocks": blocks,
    }


def read_block_payload(path: Path, info: dict) -> bytes:
    with path.open("rb") as f:
        base = (int(info["block_off"]) << 4) + 4
        f.seek(base)
        header_span, _packed_len, _unknown = struct.unpack("<III", f.read(12))
        if header_span != 0x20:
            f.seek(0x104, 1)  # 0x100 GNF header + 4-byte trailer
        f.seek(8, 1)
        dec_size = struct.unpack("<I", f.read(4))[0]
        f.seek(4, 1)
        payload = f.read(dec_size)
        check(len(payload) == dec_size, "short texpack decoded payload")
        return payload


def streamed_payload(pack: dict, file_hash: int) -> tuple[bytes, dict]:
    matches = [x for x in pack["texinfos"] if x[1] == file_hash]
    check(len(matches) == 1, f"expected one file hash {file_hash:016X}, found {len(matches)}")
    idx, fh, uh, first = matches[0]
    check(first in pack["blocks"], f"missing first BlockInfo 0x{first:X}")
    chain = [pack["blocks"][first]]
    seen = {first}
    while chain[0]["next"] != 0xFFFFFFFFFFFFFFFF:
        nxt = chain[0]["next"]
        check(nxt in pack["blocks"], f"missing sibling BlockInfo 0x{nxt:X}")
        check(nxt not in seen, "BlockInfo cycle")
        seen.add(nxt)
        chain.insert(0, pack["blocks"][nxt])
    payloads = [read_block_payload(pack["path"], x) for x in chain]
    return b"".join(payloads), {
        "texinfo_index": idx,
        "file_hash": f"{fh:016X}",
        "user_hash": f"{uh:016X}",
        "chain": [
            {
                "index": x["index"],
                "raw_size": x["raw_size"],
                "mip_start": x["mip_start"],
                "mip_end": x["mip_end"],
                "mip_width": x["mip_width"],
                "mip_height": x["mip_height"],
            }
            for x in chain
        ],
    }


def common_prefix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[len(a) - 1 - i] == b[len(b) - 1 - i]:
        i += 1
    return i


def delta_summary(pos: list[int]) -> dict:
    if len(pos) < 2:
        return {"matched_positions": len(pos), "delta_count": 0, "top_deltas": []}
    ds = [b - a for a, b in zip(pos, pos[1:])]
    c = Counter(ds)
    return {
        "matched_positions": len(pos),
        "delta_count": len(ds),
        "unique_deltas": len(c),
        "top_deltas": [{"delta_blocks": d, "count": n} for d, n in c.most_common(12)],
    }


def alignment_score(resident: bytes, stream: bytes, block_bytes: int, roff: int, soff: int) -> dict:
    rchunks = [resident[i:i+block_bytes] for i in range(roff, len(resident) - block_bytes + 1, block_bytes)]
    schunks = [stream[i:i+block_bytes] for i in range(soff, len(stream) - block_bytes + 1, block_bytes)]
    positions: dict[bytes, list[int]] = defaultdict(list)
    for i, chunk in enumerate(schunks):
        positions[chunk].append(i)

    matched = 0
    informative_total = 0
    informative_matched = 0
    unique_source_matched = 0
    chosen_positions = []
    unmatched_examples = []
    for chunk in rchunks:
        src = positions.get(chunk, [])
        if src:
            matched += 1
            chosen_positions.append(src[0])
            if len(src) == 1:
                unique_source_matched += 1
        # Low-frequency source blocks are much more informative than transparent
        # or flat-colour blocks that may occur hundreds of times.
        freq = len(src)
        informative = chunk != b"\x00" * block_bytes and freq <= 8
        if informative:
            informative_total += 1
            if src:
                informative_matched += 1
        if not src and len(unmatched_examples) < 8:
            unmatched_examples.append(chunk.hex())

    return {
        "resident_alignment": roff,
        "stream_alignment": soff,
        "resident_blocks": len(rchunks),
        "matched_blocks": matched,
        "match_ratio": (matched / len(rchunks)) if rchunks else 0.0,
        "unique_source_matched_blocks": unique_source_matched,
        "informative_blocks": informative_total,
        "informative_matched_blocks": informative_matched,
        "informative_match_ratio": (informative_matched / informative_total) if informative_total else 0.0,
        "position_delta_summary": delta_summary(chosen_positions),
        "first_source_positions": chosen_positions[:64],
        "unmatched_block_examples": unmatched_examples,
    }


def analyse_target(resident: bytes, stream: bytes, block_bytes: int) -> dict:
    scores = []
    for roff in range(block_bytes):
        for soff in range(block_bytes):
            scores.append(alignment_score(resident, stream, block_bytes, roff, soff))
    scores.sort(key=lambda x: (
        -x["informative_match_ratio"],
        -x["match_ratio"],
        -x["unique_source_matched_blocks"],
        x["resident_alignment"],
        x["stream_alignment"],
    ))
    best = scores[0]
    return {
        "resident_bytes": len(resident),
        "stream_bytes": len(stream),
        "resident_sha256": sha(resident),
        "stream_sha256": sha(stream),
        "common_prefix_bytes": common_prefix(resident, stream),
        "common_suffix_bytes": common_suffix(resident, stream),
        "resident_prefix64_hex": resident[:64].hex(),
        "stream_prefix64_hex": stream[:64].hex(),
        "block_bytes": block_bytes,
        "best_alignment": best,
        "top_alignments": scores[:12],
        "interpretation": (
            "High informative block-match ratio means the resident surface substantially reuses streamed compressed blocks and the source-position deltas can reveal its extraction/tiling. Low informative match ratio means the resident surface was separately authored/generated and must be decoded from its own metadata/layout rather than copied from root.texpack."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    raw = args.wad.read_bytes()
    logical = load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "r_ui.wad does not round-trip exactly")
    pack = parse_texpack(args.root_texpack)

    targets = {}
    for label, spec in TARGETS.items():
        resident = bytes(one_gpu(records, spec["name"])["data"])
        stream, meta = streamed_payload(pack, spec["file_hash"])
        targets[label] = {
            "wad_resource_name": spec["name"],
            "stream_meta": meta,
            "analysis": analyse_target(resident, stream, spec["block_bytes"]),
        }

    report = {
        "result": "RESIDENT_BLOCK_MAPPING_INSPECTED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": sha(raw),
        "root_texpack_sha256": sha(args.root_texpack.read_bytes()),
        "targets": targets,
        "summary": {
            label: {
                "common_prefix_bytes": row["analysis"]["common_prefix_bytes"],
                "common_suffix_bytes": row["analysis"]["common_suffix_bytes"],
                "best_alignment": row["analysis"]["best_alignment"],
            }
            for label, row in targets.items()
        },
        "next_gate": "If exact informative BC blocks map strongly into the streamed payload, infer the resident extraction/tiling from their source positions. Otherwise inspect the 356-byte texture definition and native texture loader because the resident image is independently generated.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "wad_sha256": report["wad_sha256"],
        "summary": {
            k: {
                "common_prefix_bytes": v["common_prefix_bytes"],
                "common_suffix_bytes": v["common_suffix_bytes"],
                "best_match_ratio": v["best_alignment"]["match_ratio"],
                "best_informative_match_ratio": v["best_alignment"]["informative_match_ratio"],
                "resident_alignment": v["best_alignment"]["resident_alignment"],
                "stream_alignment": v["best_alignment"]["stream_alignment"],
            }
            for k, v in report["summary"].items()
        },
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
