"""Derive the stock map-icon resident mip-tail permutation without guessing.

The block-mapping probe proved that the complete BC blocks in the resident
Dock/Valkyrie textures are all reused from the corresponding streamed GNF data,
but the resident bytes are not a direct contiguous suffix. For these textures
there are exactly 576 complete resident blocks in both channels, equal to the
combined padded mip2..7 block count.

This read-only probe uses FOUR independent stock observations at once:
  Dock diffuse, Valkyrie diffuse, Dock emissive, Valkyrie emissive.

At every logical block position it builds a composite key from all four stock
blocks. It compares the 576 streamed mip2..7 composite keys with the 576
resident composite keys. If every composite key is unique and the sets match,
the resident permutation is proven exactly and can later be applied to the
custom Raven streamed mip tail without reverse-engineering PS4 tiling rules.

No game file, save, boot option or progression state is modified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
BLOCK_COUNT = 576
TRAILER_BYTES = 12

TARGETS = {
    "dock_diffuse": {
        "name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "hash": 0x982BF904AB84F2CC,
        "block_bytes": 16,
    },
    "valkyrie_diffuse": {
        "name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "hash": 0x8A041E6BFCE5E589,
        "block_bytes": 16,
    },
    "dock_emissive": {
        "name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "hash": 0xFCC664130951154C,
        "block_bytes": 8,
    },
    "valkyrie_emissive": {
        "name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "hash": 0x9938C16BB9F6A5AC,
        "block_bytes": 8,
    },
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_module(filename: str, name: str):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def one_gpu(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"] == name and r["kind"] == 0x1D and r["flags"] == 0x80A1]
    check(len(rows) == 1, f"expected one resident GPU record for {name}, found {len(rows)}")
    return rows[0]


def chunks(raw: bytes, size: int) -> list[bytes]:
    check(len(raw) % size == 0, f"{len(raw)} bytes not divisible by block size {size}")
    return [raw[i:i + size] for i in range(0, len(raw), size)]


def composite_key(parts: list[bytes]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(len(p).to_bytes(2, "little"))
        h.update(p)
    return h.hexdigest()


def run(wad_raw: bytes, root_texpack: Path) -> dict:
    check(sha(wad_raw) == EXPECTED_BASE_WAD,
          "r_ui.wad is not the proven registered Raven base; remove active resident artwork proofs first")
    check(root_texpack.is_file(), f"root texpack missing: {root_texpack}")

    logical = load_module("build-raven-ui-logical-clone.py", "completionist_logical_composite_perm")
    mapping = load_module("inspect-resident-block-mapping.py", "completionist_mapping_composite_perm")
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "r_ui.wad does not round-trip exactly")
    pack = mapping.parse_texpack(root_texpack)

    resident_blocks: dict[str, list[bytes]] = {}
    stream_tail_blocks: dict[str, list[bytes]] = {}
    target_meta = {}

    for label, spec in TARGETS.items():
        resident = bytes(one_gpu(records, spec["name"])["data"])
        body = resident[:-TRAILER_BYTES]
        block_bytes = int(spec["block_bytes"])
        rb = chunks(body, block_bytes)
        check(len(rb) == BLOCK_COUNT, f"{label}: resident has {len(rb)} blocks, expected {BLOCK_COUNT}")

        stream, meta = mapping.streamed_payload(pack, int(spec["hash"]))
        sb = chunks(stream, block_bytes)
        check(len(sb) >= BLOCK_COUNT, f"{label}: stream has only {len(sb)} blocks")
        tail = sb[-BLOCK_COUNT:]

        resident_blocks[label] = rb
        stream_tail_blocks[label] = tail
        target_meta[label] = {
            "resident_bytes": len(resident),
            "resident_body_bytes": len(body),
            "block_bytes": block_bytes,
            "stream_bytes": len(stream),
            "stream_blocks": len(sb),
            "tail_start_block": len(sb) - BLOCK_COUNT,
            "stream_meta": meta,
        }

    order = ["dock_diffuse", "valkyrie_diffuse", "dock_emissive", "valkyrie_emissive"]
    resident_keys = [
        composite_key([resident_blocks[label][i] for label in order])
        for i in range(BLOCK_COUNT)
    ]
    source_keys = [
        composite_key([stream_tail_blocks[label][i] for label in order])
        for i in range(BLOCK_COUNT)
    ]

    rc = Counter(resident_keys)
    sc = Counter(source_keys)
    multisets_equal = rc == sc

    source_positions: dict[str, list[int]] = defaultdict(list)
    for i, key in enumerate(source_keys):
        source_positions[key].append(i)

    ambiguous = [
        {"key": key, "source_positions": pos, "resident_count": rc.get(key, 0)}
        for key, pos in source_positions.items() if len(pos) != 1 or rc.get(key, 0) != 1
    ]
    missing_keys = [key for key in rc if key not in sc]
    extra_keys = [key for key in sc if key not in rc]

    permutation = []
    fully_unique = multisets_equal and not ambiguous and not missing_keys and not extra_keys
    if fully_unique:
        permutation = [source_positions[key][0] for key in resident_keys]

    reconstruct = {}
    if permutation:
        for label in order:
            rebuilt = b"".join(stream_tail_blocks[label][src] for src in permutation)
            original = b"".join(resident_blocks[label])
            reconstruct[label] = {
                "exact": rebuilt == original,
                "rebuilt_sha256": sha(rebuilt),
                "resident_body_sha256": sha(original),
            }
    all_reconstruct = bool(reconstruct) and all(x["exact"] for x in reconstruct.values())
    bijection = bool(permutation) and sorted(permutation) == list(range(BLOCK_COUNT))

    deltas = []
    if permutation:
        deltas = [b - a for a, b in zip(permutation, permutation[1:])]
        delta_counts = Counter(deltas)
    else:
        delta_counts = Counter()

    contiguous_runs = []
    if permutation:
        start_i = 0
        for i in range(1, len(permutation)):
            if permutation[i] != permutation[i - 1] + 1:
                contiguous_runs.append({
                    "resident_start": start_i,
                    "resident_end": i - 1,
                    "source_start": permutation[start_i],
                    "source_end": permutation[i - 1],
                    "length": i - start_i,
                })
                start_i = i
        contiguous_runs.append({
            "resident_start": start_i,
            "resident_end": len(permutation) - 1,
            "source_start": permutation[start_i],
            "source_end": permutation[-1],
            "length": len(permutation) - start_i,
        })

    return {
        "result": "RESIDENT_COMPOSITE_PERMUTATION_INSPECTED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": sha(wad_raw),
        "root_texpack_sha256": sha(root_texpack.read_bytes()),
        "block_count": BLOCK_COUNT,
        "targets": target_meta,
        "composite": {
            "stock_channels": order,
            "resident_unique_keys": len(rc),
            "source_unique_keys": len(sc),
            "multisets_equal": multisets_equal,
            "ambiguous_key_groups": len(ambiguous),
            "ambiguous_examples": ambiguous[:16],
            "missing_key_count": len(missing_keys),
            "extra_key_count": len(extra_keys),
            "fully_unique_permutation": fully_unique,
        },
        "permutation": {
            "derived": bool(permutation),
            "bijection_0_to_575": bijection,
            "reconstructs_all_four_stock_residents": all_reconstruct,
            "first_128_source_indices": permutation[:128],
            "sha256_u16le": sha(b"".join(int(x).to_bytes(2, "little") for x in permutation)) if permutation else None,
            "top_deltas": [{"delta": d, "count": n} for d, n in delta_counts.most_common(24)],
            "contiguous_run_count": len(contiguous_runs),
            "contiguous_runs": contiguous_runs[:128],
        },
        "reconstruction": reconstruct,
        "runtime_patch_gate": bool(fully_unique and bijection and all_reconstruct),
        "next_gate": (
            "If runtime_patch_gate is true, apply this empirically derived 576-block permutation to the custom Raven streamed mip2..7 tail and preserve the Raven resident's final 12 bytes. No texture-layout guess is then required."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    report = run(args.wad.read_bytes(), args.root_texpack)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "runtime_patch_gate": report["runtime_patch_gate"],
        "resident_unique_keys": report["composite"]["resident_unique_keys"],
        "source_unique_keys": report["composite"]["source_unique_keys"],
        "ambiguous_key_groups": report["composite"]["ambiguous_key_groups"],
        "multisets_equal": report["composite"]["multisets_equal"],
        "bijection": report["permutation"]["bijection_0_to_575"],
        "reconstructs_all_four": report["permutation"]["reconstructs_all_four_stock_residents"],
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
