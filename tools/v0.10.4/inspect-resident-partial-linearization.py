"""Prove the stock resident map-icon mip layout by exact reconstruction.

The paired source-map probe exposed a strong structure that earlier probes did
not model: resident positions split exactly at the streamed padded mip2..7
boundaries (256, then five 64-block segments). Within the meaningful portion of
each mip, unique stock blocks map as if the streamed GNF mip was unswizzled and
its authored/4x4-aligned rows were packed at the start of that fixed-size mip
segment. Unique blocks after the packed region map back to the same raw streamed
block index, suggesting the unused remainder of each fixed-size segment is left
in its original streamed/swizzled form.

This read-only probe tests that hypothesis byte-for-byte against four independent
stock resources:

  Dock diffuse / emissive (148x148)
  Valkyrie diffuse / emissive (156x156)

For every mip 2..7 it:
  1. copies the complete raw streamed/swizzled padded mip segment;
  2. unswizzles that segment with the exact GOWTool 8x8-block Morton traversal;
  3. packs only the authored, 4x4-aligned BC block rows at the start of the
     copied segment;
  4. leaves the remainder of the segment byte-for-byte as the original stream;
  5. concatenates mip2..7 and compares it to resident[:-12].

No game file, save, boot option or progression state is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAILER_BYTES = 12
PIXBL = 4

ICONS = {
    "dock": {
        "width": 148,
        "height": 148,
        "diffuse_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "diffuse_hash": 0x982BF904AB84F2CC,
        "emissive_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "emissive_hash": 0xFCC664130951154C,
    },
    "valkyrie": {
        "width": 156,
        "height": 156,
        "diffuse_name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "diffuse_hash": 0x8A041E6BFCE5E589,
        "emissive_name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "emissive_hash": 0x9938C16BB9F6A5AC,
    },
}

CHANNELS = {
    "diffuse": {"block_bytes": 16, "resident_bytes": 9228},
    "emissive": {"block_bytes": 8, "resident_bytes": 4620},
}

# GOWTool / stock GNF padded block counts for these eight-mip map textures.
MIP_BLOCK_COUNTS = [4096, 1024, 256, 64, 64, 64, 64, 64]


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_module(filename: str, module_name: str):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def one_gpu(records: list[dict], name: str) -> bytes:
    rows = [r for r in records if r["name"] == name and r["kind"] == 0x1D and r["flags"] == 0x80A1]
    check(len(rows) == 1, f"expected one resident GPU record for {name}, found {len(rows)}")
    return bytes(rows[0]["data"])


def morton(t: int, sx: int, sy: int) -> int:
    num = 0
    num2 = 0
    num3 = 1
    num4 = 1
    num5 = t
    num6 = sx
    num7 = sy
    while num6 > 1 or num7 > 1:
        if num6 > 1:
            num += num4 * (num5 & 1)
            num5 >>= 1
            num4 *= 2
            num6 >>= 1
        if num7 > 1:
            num2 += num3 * (num5 & 1)
            num5 >>= 1
            num3 *= 2
            num7 >>= 1
    return num2 * sx + num


def swizzled_to_linear_index_order(blocks_w: int, blocks_h: int) -> list[int]:
    """Return the GOWTool destination linear block index for each stream block."""
    out: list[int] = []
    for macro_y in range((blocks_h + 7) // 8):
        for macro_x in range((blocks_w + 7) // 8):
            for k in range(64):
                m = morton(k, 8, 8)
                row = m // 8
                col = m % 8
                x = macro_x * 8 + col
                y = macro_y * 8 + row
                if x < blocks_w and y < blocks_h:
                    out.append(y * blocks_w + x)
    check(len(out) == blocks_w * blocks_h, "swizzle traversal block count mismatch")
    check(sorted(out) == list(range(blocks_w * blocks_h)), "swizzle traversal is not a permutation")
    return out


def unswizzle_blocks(stream_blocks: list[bytes], blocks_w: int, blocks_h: int) -> list[bytes]:
    order = swizzled_to_linear_index_order(blocks_w, blocks_h)
    check(len(stream_blocks) == len(order), "mip stream/order block count mismatch")
    linear = [b""] * len(stream_blocks)
    for source_pos, linear_pos in enumerate(order):
        linear[linear_pos] = stream_blocks[source_pos]
    check(all(linear), "unswizzle left an empty block")
    return linear


def align4_pixels(v: int) -> int:
    v = max(v, PIXBL)
    return (v + (PIXBL - 1)) & ~(PIXBL - 1)


def active_block_dims(authored_w: int, authored_h: int, mip: int) -> tuple[int, int]:
    w = max(1, authored_w >> mip)
    h = max(1, authored_h >> mip)
    w = align4_pixels(w)
    h = align4_pixels(h)
    return w // PIXBL, h // PIXBL


def padded_block_dims(mip: int) -> tuple[int, int]:
    if mip == 2:
        return 16, 16
    check(3 <= mip <= 7, f"unexpected resident mip {mip}")
    return 8, 8


def split_stream_blocks(stream: bytes, block_bytes: int) -> list[list[bytes]]:
    expected_blocks = sum(MIP_BLOCK_COUNTS)
    check(len(stream) == expected_blocks * block_bytes,
          f"stream length {len(stream)} != {expected_blocks}*{block_bytes}")
    blocks = [stream[i:i + block_bytes] for i in range(0, len(stream), block_bytes)]
    out = []
    pos = 0
    for n in MIP_BLOCK_COUNTS:
        out.append(blocks[pos:pos + n])
        pos += n
    check(pos == len(blocks), "stream mip split did not consume all blocks")
    return out


def reconstruct_resident_body(stream: bytes, block_bytes: int, authored_w: int, authored_h: int) -> tuple[bytes, list[dict]]:
    mips = split_stream_blocks(stream, block_bytes)
    output: list[bytes] = []
    details = []

    for mip in range(2, 8):
        raw_segment = list(mips[mip])
        padded_w, padded_h = padded_block_dims(mip)
        check(len(raw_segment) == padded_w * padded_h,
              f"mip{mip}: expected {padded_w*padded_h} stream blocks, got {len(raw_segment)}")
        linear = unswizzle_blocks(raw_segment, padded_w, padded_h)
        active_w, active_h = active_block_dims(authored_w, authored_h, mip)
        check(active_w <= padded_w and active_h <= padded_h,
              f"mip{mip}: active {active_w}x{active_h} exceeds padded {padded_w}x{padded_h}")

        packed_active: list[bytes] = []
        for y in range(active_h):
            row = linear[y * padded_w:y * padded_w + active_w]
            check(len(row) == active_w, f"mip{mip}: short active row")
            packed_active.extend(row)

        # Hypothesis under test: fixed-size segment starts as the original raw
        # swizzled stream, then its prefix is overwritten by packed linear rows.
        candidate = list(raw_segment)
        candidate[:len(packed_active)] = packed_active
        output.extend(candidate)
        details.append({
            "mip": mip,
            "padded_blocks": [padded_w, padded_h],
            "active_blocks": [active_w, active_h],
            "segment_blocks": len(candidate),
            "packed_active_blocks": len(packed_active),
            "untouched_raw_tail_blocks": len(candidate) - len(packed_active),
            "raw_segment_sha256": sha(b"".join(raw_segment)),
            "packed_active_sha256": sha(b"".join(packed_active)),
            "candidate_segment_sha256": sha(b"".join(candidate)),
        })

    body = b"".join(output)
    check(len(output) == 576, f"reconstructed resident has {len(output)} blocks, expected 576")
    return body, details


def first_diff(a: bytes, b: bytes) -> int | None:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n if len(a) != len(b) else None


def analyse_channel(records, pack, mapping, icon_label: str, icon: dict, channel: str) -> dict:
    cs = CHANNELS[channel]
    name = icon[f"{channel}_name"]
    file_hash = int(icon[f"{channel}_hash"])
    resident = one_gpu(records, name)
    check(len(resident) == cs["resident_bytes"], f"{icon_label}/{channel}: resident size changed")
    resident_body = resident[:-TRAILER_BYTES]
    trailer = resident[-TRAILER_BYTES:]
    stream, stream_meta = mapping.streamed_payload(pack, file_hash)

    rebuilt, mip_details = reconstruct_resident_body(
        stream,
        int(cs["block_bytes"]),
        int(icon["width"]),
        int(icon["height"]),
    )
    check(len(rebuilt) == len(resident_body),
          f"{icon_label}/{channel}: reconstructed bytes {len(rebuilt)} != resident body {len(resident_body)}")

    diff_positions = [i for i, (a, b) in enumerate(zip(rebuilt, resident_body)) if a != b]
    exact = not diff_positions
    return {
        "resource": name,
        "authored_dimensions": [icon["width"], icon["height"]],
        "block_bytes": cs["block_bytes"],
        "resident_bytes": len(resident),
        "resident_body_bytes": len(resident_body),
        "trailer_hex": trailer.hex(),
        "stream_bytes": len(stream),
        "stream_meta": stream_meta,
        "candidate_exact": exact,
        "different_bytes": len(diff_positions),
        "first_difference": diff_positions[0] if diff_positions else None,
        "last_difference": diff_positions[-1] if diff_positions else None,
        "resident_body_sha256": sha(resident_body),
        "candidate_body_sha256": sha(rebuilt),
        "mips": mip_details,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    logical = load_module("build-raven-ui-logical-clone.py", "resident_partial_linear_logical")
    mapping = load_module("inspect-resident-block-mapping.py", "resident_partial_linear_mapping")
    wad_raw = args.wad.read_bytes()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "r_ui.wad does not round-trip exactly")
    pack = mapping.parse_texpack(args.root_texpack)

    results = {}
    for icon_label, icon in ICONS.items():
        results[icon_label] = {
            channel: analyse_channel(records, pack, mapping, icon_label, icon, channel)
            for channel in ("diffuse", "emissive")
        }

    exact_flags = [row["candidate_exact"] for icon in results.values() for row in icon.values()]
    exact_all = all(exact_flags)
    report = {
        "result": "RESIDENT_PARTIAL_LINEARIZATION_INSPECTED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": sha(wad_raw),
        "root_texpack_sha256": sha(args.root_texpack.read_bytes()),
        "hypothesis": (
            "For each mip2..7 fixed-size resident segment: copy raw streamed/swizzled segment, "
            "unswizzle it, pack authored 4x4-aligned rows into the segment prefix, and leave the "
            "remaining segment bytes in original streamed/swizzled order."
        ),
        "icons": results,
        "all_four_stock_resources_reconstructed_exactly": exact_all,
        "runtime_patch_gate": exact_all,
        "next_gate": (
            "If runtime_patch_gate is true, apply this exact stock-proven transform to the custom Raven "
            "diffuse/emissive streamed mips2..7 and preserve the Raven resident final 12 bytes. If false, "
            "inspect per-mip mismatch ranges before any runtime write."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "result": report["result"],
        "runtime_patch_gate": report["runtime_patch_gate"],
        "all_four_stock_resources_reconstructed_exactly": exact_all,
        "checks": {
            f"{icon}/{channel}": row["candidate_exact"]
            for icon, channels in results.items()
            for channel, row in channels.items()
        },
        "different_bytes": {
            f"{icon}/{channel}": row["different_bytes"]
            for icon, channels in results.items()
            for channel, row in channels.items()
        },
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
