"""Patch the Raven texpack user-hash binding to match the dedicated WAD textures.

GOWTool preserves an existing texpack user hash when importing a DDS whose file
hash already exists in the loaded game texpack set. For a brand-new file hash,
its GNF header keeps the default UINT64_MAX user hash. The dedicated Raven WAD
uses unique non-FFFF user hashes so its two texture GPU resources can remain
unique. This helper patches only the generated Raven texpack metadata and the
embedded GNF headers to those already-authored WAD user hashes.

No game file is modified in-place by this helper. Inputs are read-only and
patched outputs are written to explicit output paths.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent

TEXTURES = {
    0x19A41F00834C19F3: {
        "label": "diffuse",
        "name": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
        "stock_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "desired_user_hash": 0x7ABBBA793C03C741,
    },
    0x63F1E18FF93B9037: {
        "label": "emissive",
        "name": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
        "stock_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "desired_user_hash": 0x15AD16D2A17DEB42,
    },
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def hex64(value: int) -> str:
    return f"{value:016X}"


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("completionist_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def texture_gpu_id(user_hash: int) -> bytes:
    return bytes(8) + struct.pack("<II", user_hash >> 32, user_hash & 0xFFFFFFFF)


def parse_texpack_entries(raw: bytes) -> list[dict]:
    check(len(raw) >= 0x38, "texpack too small")
    tex_count = struct.unpack_from("<I", raw, 0x2C)[0]
    entries = []
    off = 0x38
    check(off + tex_count * 0x18 <= len(raw), "texpack TexInfo table exceeds file")
    for index in range(tex_count):
        file_hash, user_hash, block_info_off = struct.unpack_from("<QQQ", raw, off)
        entries.append({
            "index": index,
            "entry_offset": off,
            "file_hash": file_hash,
            "user_hash": user_hash,
            "block_info_off": block_info_off,
        })
        off += 0x18
    return entries


def find_one(entries: list[dict], file_hash: int, label: str) -> dict:
    rows = [row for row in entries if row["file_hash"] == file_hash]
    check(len(rows) == 1, f"expected exactly one {label} file hash {hex64(file_hash)}, found {len(rows)}")
    return rows[0]


def inspect_wad(wad_raw: bytes) -> dict:
    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    result = {}
    for file_hash, spec in TEXTURES.items():
        custom = [r for r in records if r["name"] == spec["name"]]
        stock = [r for r in records if r["name"] == spec["stock_name"]]
        custom_def = [r for r in custom if r["kind"] == 1 and r["flags"] == 0x8021 and len(r["data"]) == 356]
        custom_gpu = [r for r in custom if r["kind"] == 0x1D and r["flags"] == 0x80A1]
        stock_gpu = [r for r in stock if r["kind"] == 0x1D and r["flags"] == 0x80A1]
        check(len(custom_def) == 1, f"{spec['label']}: expected one custom texture definition")
        check(len(custom_gpu) == 1, f"{spec['label']}: expected one custom GPU texture payload")
        check(len(stock_gpu) == 1, f"{spec['label']}: expected one stock GPU texture payload")

        wad_user_hash = struct.unpack_from("<Q", custom_def[0]["data"], 0x9C)[0]
        desired = spec["desired_user_hash"]
        check(wad_user_hash == desired,
              f"{spec['label']}: WAD user hash changed: {hex64(wad_user_hash)} != {hex64(desired)}")
        check(custom_gpu[0]["id"] == texture_gpu_id(desired),
              f"{spec['label']}: custom GPU resource ID no longer matches desired user hash")

        result[spec["label"]] = {
            "name": spec["name"],
            "file_hash": hex64(file_hash),
            "wad_user_hash": hex64(wad_user_hash),
            "gpu_resource_id": custom_gpu[0]["id"].hex(),
            "embedded_gpu_payload_matches_stock_dock": bytes(custom_gpu[0]["data"]) == bytes(stock_gpu[0]["data"]),
            "custom_gpu_payload_sha256": sha(bytes(custom_gpu[0]["data"])),
            "stock_gpu_payload_sha256": sha(bytes(stock_gpu[0]["data"])),
        }
    return result


def patch(pack_raw: bytes, toc_raw: bytes, wad_raw: bytes) -> tuple[bytes, bytes, dict]:
    wad_info = inspect_wad(wad_raw)
    pack_entries = parse_texpack_entries(pack_raw)
    toc_entries = parse_texpack_entries(toc_raw)
    check(len(pack_entries) == len(toc_entries), "texpack/toc texture counts differ")

    out_pack = bytearray(pack_raw)
    out_toc = bytearray(toc_raw)
    rows = []

    for file_hash, spec in TEXTURES.items():
        p = find_one(pack_entries, file_hash, spec["label"])
        t = find_one(toc_entries, file_hash, spec["label"])
        check(p["block_info_off"] == t["block_info_off"], f"{spec['label']}: pack/toc block-info offsets differ")
        check(p["user_hash"] == t["user_hash"], f"{spec['label']}: pack/toc user hashes differ before patch")

        desired = spec["desired_user_hash"]
        before = p["user_hash"]
        check(before in (0xFFFFFFFFFFFFFFFF, desired),
              f"{spec['label']}: unexpected generated texpack user hash {hex64(before)}")

        struct.pack_into("<Q", out_pack, p["entry_offset"] + 8, desired)
        struct.pack_into("<Q", out_toc, t["entry_offset"] + 8, desired)

        block_info_off = p["block_info_off"]
        check(block_info_off + 0x20 <= len(out_pack), f"{spec['label']}: BlockInfo exceeds texpack")
        block_off = struct.unpack_from("<I", out_pack, block_info_off)[0]
        block_base = block_off << 4
        check(block_base + 0x50 <= len(out_pack), f"{spec['label']}: texture block exceeds texpack")
        block_tag, header_span, block_size, block_kind = struct.unpack_from("<IIII", out_pack, block_base)
        check(block_tag == 1 and header_span == 0x124 and block_kind == 5,
              f"{spec['label']}: unexpected GOWTool texture block preamble")
        gnf = block_base + 0x10
        check(struct.unpack_from("<I", out_pack, gnf)[0] == 0x20464E47,
              f"{spec['label']}: GNF magic missing")
        check(struct.unpack_from("<I", out_pack, gnf + 0x30)[0] == 0x52455355,
              f"{spec['label']}: GNF USER magic missing")
        gnf_before = struct.unpack_from("<Q", out_pack, gnf + 0x38)[0]
        check(gnf_before in (0xFFFFFFFFFFFFFFFF, desired),
              f"{spec['label']}: unexpected embedded GNF user hash {hex64(gnf_before)}")
        struct.pack_into("<Q", out_pack, gnf + 0x38, desired)

        rows.append({
            "label": spec["label"],
            "file_hash": hex64(file_hash),
            "desired_user_hash": hex64(desired),
            "texinfo_user_hash_before": hex64(before),
            "texinfo_user_hash_after": hex64(desired),
            "embedded_gnf_user_hash_before": hex64(gnf_before),
            "embedded_gnf_user_hash_after": hex64(desired),
            "texinfo_index": p["index"],
            "block_info_offset": f"0x{block_info_off:X}",
            "block_base": f"0x{block_base:X}",
            "block_size_field": block_size,
        })

    reparsed_pack = parse_texpack_entries(bytes(out_pack))
    reparsed_toc = parse_texpack_entries(bytes(out_toc))
    for file_hash, spec in TEXTURES.items():
        desired = spec["desired_user_hash"]
        check(find_one(reparsed_pack, file_hash, spec["label"])["user_hash"] == desired,
              f"{spec['label']}: patched pack user hash did not persist")
        check(find_one(reparsed_toc, file_hash, spec["label"])["user_hash"] == desired,
              f"{spec['label']}: patched toc user hash did not persist")

    report = {
        "result": "RAVEN_TEXPACK_USERHASH_BINDING_PATCHED_OFFLINE",
        "binding_gate_passed": True,
        "input_pack_sha256": sha(pack_raw),
        "input_toc_sha256": sha(toc_raw),
        "output_pack_sha256": sha(bytes(out_pack)),
        "output_toc_sha256": sha(bytes(out_toc)),
        "wad_sha256": sha(wad_raw),
        "wad_texture_contract": wad_info,
        "texpack_bindings": rows,
        "explanation": (
            "GOWTool gives new file hashes the GNF default UINT64_MAX user hash unless the file hash already exists in a loaded texpack. "
            "The dedicated Raven WAD intentionally uses unique non-FFFF user hashes. The patch aligns both TexInfo and embedded GNF headers with those WAD hashes."
        ),
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
    }
    return bytes(out_pack), bytes(out_toc), report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--toc", type=Path, required=True)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--out-pack", type=Path, required=True)
    ap.add_argument("--out-toc", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    pack_raw = args.pack.read_bytes()
    toc_raw = args.toc.read_bytes()
    wad_raw = args.wad.read_bytes()
    patched_pack, patched_toc, report = patch(pack_raw, toc_raw, wad_raw)

    args.out_pack.parent.mkdir(parents=True, exist_ok=True)
    args.out_toc.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out_pack.write_bytes(patched_pack)
    args.out_toc.write_bytes(patched_toc)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
