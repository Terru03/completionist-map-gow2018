"""Build the dedicated Raven resident payload from the streamed mip tail.

The resident block-mapping field probe showed that every complete BC block in
stock Dock/Valkyrie resident payloads occurs in the corresponding root.texpack
stream at block alignment zero. The sizes are especially diagnostic:

  BC7 diffuse:  resident 9228 = 9216 compressed bytes + 12 trailing bytes
  BC1 emissive: resident 4620 = 4608 compressed bytes + 12 trailing bytes

For the stock 148/156px, 8-mip map textures, the complete streamed mip2..7
compressed tail is exactly 9216 bytes for BC7 and 4608 bytes for BC1. This
helper does not assume that relationship blindly: before producing an output it
requires BOTH stock Dock and stock Valkyrie to satisfy byte-for-byte:

  resident[:-12] == streamed_payload[-(resident_size-12):]

Only after both independent stock controls pass does it replace the isolated
Completionist Raven resident prefix with the same-sized tail from the custom
Raven patch texpack. The final 12 bytes of each Raven resident record are
preserved exactly from the proven Dock-derived baseline.

No game file is modified in place by this helper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_RAVEN_PACK = "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7"
TRAILER_BYTES = 12

TEXTURES = {
    "diffuse": {
        "raven_name": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
        "raven_hash": 0x19A41F00834C19F3,
        "dock_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "dock_hash": 0x982BF904AB84F2CC,
        "valk_name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "valk_hash": 0x8A041E6BFCE5E589,
        "resident_bytes": 9228,
        "stream_tail_bytes": 9216,
        "block_bytes": 16,
    },
    "emissive": {
        "raven_name": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
        "raven_hash": 0x63F1E18FF93B9037,
        "dock_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "dock_hash": 0xFCC664130951154C,
        "valk_name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "valk_hash": 0x9938C16BB9F6A5AC,
        "resident_bytes": 4620,
        "stream_tail_bytes": 4608,
        "block_bytes": 8,
    },
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


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


def one_def(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"] == name and r["kind"] == 1 and r["flags"] == 0x8021]
    check(len(rows) == 1, f"expected one texture definition for {name}, found {len(rows)}")
    return rows[0]


def patch(wad_raw: bytes, root_pack_path: Path, raven_pack_path: Path) -> tuple[bytes, dict]:
    check(sha(wad_raw) == EXPECTED_BASE_WAD, "input WAD is not the proven registered Raven base")
    check(root_pack_path.is_file(), f"root texpack missing: {root_pack_path}")
    check(raven_pack_path.is_file(), f"Raven texpack missing: {raven_pack_path}")
    check(sha_file(raven_pack_path) == EXPECTED_RAVEN_PACK, "active Raven patch texpack hash changed")

    logical = load_module("build-raven-ui-logical-clone.py", "completionist_logical_stream_tail")
    mapping = load_module("inspect-resident-block-mapping.py", "completionist_resident_mapping")

    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "input WAD does not round-trip exactly")
    root_pack = mapping.parse_texpack(root_pack_path)
    raven_pack = mapping.parse_texpack(raven_pack_path)

    rows = []
    preserved_defs: dict[str, bytes] = {}
    dock_passes = []
    valk_passes = []

    for label, spec in TEXTURES.items():
        raven_gpu = one_gpu(records, spec["raven_name"])
        dock_gpu = one_gpu(records, spec["dock_name"])
        valk_gpu = one_gpu(records, spec["valk_name"])
        raven_def = one_def(records, spec["raven_name"])

        expected_resident = spec["resident_bytes"]
        tail_bytes = spec["stream_tail_bytes"]
        block_bytes = spec["block_bytes"]
        check(expected_resident == tail_bytes + TRAILER_BYTES, f"{label}: resident/tail size contract is inconsistent")
        check(tail_bytes % block_bytes == 0, f"{label}: stream tail is not BC-block aligned")
        check(len(raven_gpu["data"]) == expected_resident, f"{label}: Raven resident size changed")
        check(len(dock_gpu["data"]) == expected_resident, f"{label}: Dock resident size changed")
        check(len(valk_gpu["data"]) == expected_resident, f"{label}: Valkyrie resident size changed")
        check(bytes(raven_gpu["data"]) == bytes(dock_gpu["data"]), f"{label}: Raven resident is not the expected Dock clone; remove any resident artwork proof first")

        dock_stream, dock_meta = mapping.streamed_payload(root_pack, spec["dock_hash"])
        valk_stream, valk_meta = mapping.streamed_payload(root_pack, spec["valk_hash"])
        raven_stream, raven_meta = mapping.streamed_payload(raven_pack, spec["raven_hash"])

        check(len(dock_stream) >= tail_bytes and len(valk_stream) >= tail_bytes and len(raven_stream) >= tail_bytes,
              f"{label}: streamed texture is shorter than the resident mip tail")

        dock_resident = bytes(dock_gpu["data"])
        valk_resident = bytes(valk_gpu["data"])
        raven_before = bytes(raven_gpu["data"])

        dock_relation = dock_resident[:tail_bytes] == dock_stream[-tail_bytes:]
        valk_relation = valk_resident[:tail_bytes] == valk_stream[-tail_bytes:]
        dock_passes.append(dock_relation)
        valk_passes.append(valk_relation)
        check(dock_relation,
              f"{label}: stock Dock disproves resident[:-12] == streamed mip2+ tail")
        check(valk_relation,
              f"{label}: stock Valkyrie disproves resident[:-12] == streamed mip2+ tail")

        # The extra 12 bytes are WAD-resident trailer data, not part of the BC
        # stream. Preserve them byte-for-byte from the isolated Dock-derived
        # Raven baseline and replace only the complete BC-block prefix.
        trailer = raven_before[tail_bytes:]
        check(len(trailer) == TRAILER_BYTES, f"{label}: Raven trailer is not 12 bytes")
        custom_tail = raven_stream[-tail_bytes:]
        check(len(custom_tail) == tail_bytes, f"{label}: custom stream tail length wrong")
        check(custom_tail != dock_stream[-tail_bytes:], f"{label}: custom Raven stream tail unexpectedly equals Dock")

        raven_gpu["data"][:] = custom_tail + trailer
        after = bytes(raven_gpu["data"])
        check(len(after) == expected_resident, f"{label}: patched resident size changed")
        check(after[:tail_bytes] == custom_tail, f"{label}: custom tail did not persist")
        check(after[tail_bytes:] == trailer, f"{label}: 12-byte trailer changed")
        check(after != raven_before, f"{label}: Raven resident did not change")

        preserved_defs[label] = bytes(raven_def["data"])
        rows.append({
            "label": label,
            "resident_bytes": expected_resident,
            "stream_tail_bytes": tail_bytes,
            "block_bytes": block_bytes,
            "complete_bc_blocks": tail_bytes // block_bytes,
            "trailing_bytes": TRAILER_BYTES,
            "trailer_hex": trailer.hex(),
            "dock_stream_bytes": len(dock_stream),
            "valkyrie_stream_bytes": len(valk_stream),
            "raven_stream_bytes": len(raven_stream),
            "dock_relation_exact": dock_relation,
            "valkyrie_relation_exact": valk_relation,
            "dock_tail_sha256": sha(dock_stream[-tail_bytes:]),
            "valkyrie_tail_sha256": sha(valk_stream[-tail_bytes:]),
            "custom_raven_tail_sha256": sha(custom_tail),
            "resident_before_sha256": sha(raven_before),
            "resident_after_sha256": sha(after),
            "dock_stream_meta": dock_meta,
            "valkyrie_stream_meta": valk_meta,
            "raven_stream_meta": raven_meta,
        })

    out = logical.serialize_wad(records)
    check(len(out) == len(wad_raw), "WAD byte length changed")
    reparsed = logical.parse_wad(out)
    check(logical.serialize_wad(reparsed) == out, "patched WAD does not round-trip exactly")

    for label, spec in TEXTURES.items():
        check(bytes(one_def(reparsed, spec["raven_name"])["data"]) == preserved_defs[label],
              f"{label}: Raven texture definition changed")

    report = {
        "result": "RAVEN_RESIDENT_STREAM_TAIL_ARTWORK_PATCHED_OFFLINE",
        "stock_dock_tail_relation_proven": all(dock_passes),
        "stock_valkyrie_tail_relation_proven": all(valk_passes),
        "custom_raven_tail_applied": True,
        "trailing_12_bytes_preserved": True,
        "relation": "resident complete BC-block prefix equals streamed mip2..7 tail; final 12 resident bytes are preserved separately",
        "input_wad_sha256": sha(wad_raw),
        "output_wad_sha256": sha(out),
        "root_texpack_sha256": sha_file(root_pack_path),
        "raven_texpack_sha256": sha_file(raven_pack_path),
        "rows": rows,
        "raven_texture_definitions_preserved": True,
        "raven_resource_identity_preserved": True,
        "real_dock_and_valkyrie_records_untouched": True,
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

    out, report = patch(args.wad.read_bytes(), args.root_texpack, args.raven_texpack)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
