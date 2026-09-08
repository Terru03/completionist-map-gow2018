"""Derive where stock resident map-icon blocks come from in the full streamed image.

The earlier block probe proved every complete resident BC block occurs somewhere
in the matching streamed texture, but a direct mip2..7 suffix and a four-texture
cross-icon composite permutation were both disproven. The latter combined Dock
and Valkyrie at the same logical source index even though their authored sizes
are different (148 vs 156), which is not a justified correspondence.

This read-only probe instead pairs only channels that belong to the SAME stock
icon and therefore share dimensions/layout:

  Dock diffuse + Dock emissive
  Valkyrie diffuse + Valkyrie emissive

For each resident block position it forms a composite (diffuse BC7 block,
emissive BC1 block), then searches the complete 5696-block streamed pair for the
same composite. It reports whether the resident composite multiset is contained
in the source, unique source matches, and the source-mip distribution. This can
distinguish a mip-tail representation from a crop/subset of mip0 without making
another runtime texture-format guess.

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
TRAILER_BYTES = 12

ICONS = {
    "dock": {
        "diffuse_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "diffuse_hash": 0x982BF904AB84F2CC,
        "emissive_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "emissive_hash": 0xFCC664130951154C,
        "authored_width": 148,
        "authored_height": 148,
    },
    "valkyrie": {
        "diffuse_name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "diffuse_hash": 0x8A041E6BFCE5E589,
        "emissive_name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "emissive_hash": 0x9938C16BB9F6A5AC,
        "authored_width": 156,
        "authored_height": 156,
    },
}

MIP_RANGES = [
    ("mip0", 0, 4096),
    ("mip1", 4096, 5120),
    ("mip2", 5120, 5376),
    ("mip3", 5376, 5440),
    ("mip4", 5440, 5504),
    ("mip5", 5504, 5568),
    ("mip6", 5568, 5632),
    ("mip7", 5632, 5696),
]


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


def one_gpu(records: list[dict], name: str) -> bytes:
    rows = [r for r in records if r["name"] == name and r["kind"] == 0x1D and r["flags"] == 0x80A1]
    check(len(rows) == 1, f"expected one resident GPU record for {name}, found {len(rows)}")
    return bytes(rows[0]["data"])


def chunks(raw: bytes, size: int) -> list[bytes]:
    check(len(raw) % size == 0, f"{len(raw)} bytes not divisible by {size}")
    return [raw[i:i+size] for i in range(0, len(raw), size)]


def key(d: bytes, e: bytes) -> str:
    return hashlib.sha256(d + e).hexdigest()


def mip_name(pos: int) -> str:
    for name, start, end in MIP_RANGES:
        if start <= pos < end:
            return name
    return "out_of_range"


def analyse_icon(records, pack, mapping, label: str, spec: dict) -> dict:
    rd_raw = one_gpu(records, spec["diffuse_name"])
    re_raw = one_gpu(records, spec["emissive_name"])
    check(len(rd_raw) == 9228, f"{label}: diffuse resident size {len(rd_raw)}")
    check(len(re_raw) == 4620, f"{label}: emissive resident size {len(re_raw)}")

    rd = chunks(rd_raw[:-TRAILER_BYTES], 16)
    re = chunks(re_raw[:-TRAILER_BYTES], 8)
    check(len(rd) == len(re) == 576, f"{label}: resident complete-block count mismatch")

    sd_raw, dmeta = mapping.streamed_payload(pack, spec["diffuse_hash"])
    se_raw, emeta = mapping.streamed_payload(pack, spec["emissive_hash"])
    sd = chunks(sd_raw, 16)
    se = chunks(se_raw, 8)
    check(len(sd) == len(se) == 5696, f"{label}: streamed block count mismatch")

    resident_keys = [key(rd[i], re[i]) for i in range(576)]
    source_keys = [key(sd[i], se[i]) for i in range(5696)]
    rc = Counter(resident_keys)
    sc = Counter(source_keys)

    positions: dict[str, list[int]] = defaultdict(list)
    for i, k in enumerate(source_keys):
        positions[k].append(i)

    missing_occurrences = sum(max(0, n - sc.get(k, 0)) for k, n in rc.items())
    contained = missing_occurrences == 0
    resident_unique_keys = sum(1 for k, n in rc.items() if n == 1)
    resident_positions_with_unique_source = sum(1 for k in resident_keys if len(positions.get(k, [])) == 1)

    unique_pairs = []
    for rpos, k in enumerate(resident_keys):
        src = positions.get(k, [])
        if len(src) == 1:
            unique_pairs.append((rpos, src[0]))

    mip_counts = Counter(mip_name(src) for _, src in unique_pairs)
    source_indices = [src for _, src in unique_pairs]
    source_min = min(source_indices) if source_indices else None
    source_max = max(source_indices) if source_indices else None

    # For each resident key, report source multiplicity and mip distribution.
    key_source_mips = []
    for k, n in rc.most_common():
        src = positions.get(k, [])
        mips = Counter(mip_name(x) for x in src)
        key_source_mips.append({
            "key": k,
            "resident_count": n,
            "source_count": len(src),
            "source_mips": dict(sorted(mips.items())),
            "source_positions_first32": src[:32],
        })

    # Candidate fixed 24x24 windows in linear mip0 block coordinates cannot be
    # tested directly against the swizzled byte sequence, but the source-index
    # mip distribution tells us whether such a mip0-only explanation is viable.
    all_occurrence_mips = Counter()
    for k, n in rc.items():
        src = positions.get(k, [])
        for p in src:
            all_occurrence_mips[mip_name(p)] += n

    return {
        "authored_width": spec["authored_width"],
        "authored_height": spec["authored_height"],
        "resident_blocks": 576,
        "stream_blocks": 5696,
        "resident_unique_key_count": len(rc),
        "source_unique_key_count": len(sc),
        "resident_singleton_key_count": resident_unique_keys,
        "resident_multiset_contained_in_stream": contained,
        "missing_occurrences": missing_occurrences,
        "resident_positions_with_unique_source": resident_positions_with_unique_source,
        "unique_source_fraction": resident_positions_with_unique_source / 576.0,
        "unique_pairs_mip_distribution": dict(sorted(mip_counts.items())),
        "unique_source_min": source_min,
        "unique_source_max": source_max,
        "first_128_unique_pairs": [
            {"resident_pos": r, "source_pos": s, "mip": mip_name(s)}
            for r, s in unique_pairs[:128]
        ],
        "all_candidate_occurrence_mip_weight": dict(sorted(all_occurrence_mips.items())),
        "key_source_groups_first64": key_source_mips[:64],
        "diffuse_stream_meta": dmeta,
        "emissive_stream_meta": emeta,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    logical = load_module("build-raven-ui-logical-clone.py", "resident_pair_logical")
    mapping = load_module("inspect-resident-block-mapping.py", "resident_pair_mapping")
    raw = args.wad.read_bytes()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "r_ui.wad does not round-trip")
    pack = mapping.parse_texpack(args.root_texpack)

    icons = {label: analyse_icon(records, pack, mapping, label, spec) for label, spec in ICONS.items()}
    report = {
        "result": "RESIDENT_PAIRED_SOURCE_MAP_INSPECTED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": sha(raw),
        "root_texpack_sha256": sha(args.root_texpack.read_bytes()),
        "mip_ranges": [{"name": n, "start": s, "end": e} for n, s, e in MIP_RANGES],
        "icons": icons,
        "next_gate": (
            "Use the same-icon diffuse+emissive source mapping to determine whether the 576 resident blocks come from a specific mip range or crop. Do not build another runtime payload until the stock source-position relation is explicit."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "dock_contained": icons["dock"]["resident_multiset_contained_in_stream"],
        "dock_unique_source_fraction": icons["dock"]["unique_source_fraction"],
        "dock_unique_mips": icons["dock"]["unique_pairs_mip_distribution"],
        "valkyrie_contained": icons["valkyrie"]["resident_multiset_contained_in_stream"],
        "valkyrie_unique_source_fraction": icons["valkyrie"]["unique_source_fraction"],
        "valkyrie_unique_mips": icons["valkyrie"]["unique_pairs_mip_distribution"],
        "game_files_written": False,
    }, indent=2))

if __name__ == "__main__":
    main()
