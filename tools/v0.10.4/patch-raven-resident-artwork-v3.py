"""Build the dedicated Raven resident map texture from a 96x96 Raven image.

Field proof established that the isolated Completionist Raven map GO renders the
resident 0x80A1 WAD payload directly: copying the stock Valkyrie resident
payload into only the Raven resource made only that Raven render as Valkyrie.

The resident payload sizes are consistent with a 12-byte resource-specific
prefix followed by a standalone 96x96 BC-compressed body:

  BC7 diffuse:  9228 = 12 + 96*96*8/8
  BC1 emissive: 4620 = 12 + 96*96*4/8

The stock Valkyrie control proved that an entire alternate resident payload can
be rendered through the isolated Raven resource. A later static check showed
that the first 12 bytes are not universal: Dock and Valkyrie emissive prefixes
differ. The dedicated Raven resource was cloned from Dock, so this helper now
preserves the Raven/Dock 12-byte prefix exactly and changes only the 96x96 BC
body. It does not require unrelated stock resources to share that prefix.

No game file is modified in-place by this helper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_TEXCONV = "dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06"

TEXTURES = {
    "diffuse": {
        "raven_name": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
        "dock_name": "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC",
        "valk_name": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
        "resident_bytes": 9228,
        "body_bytes": 9216,
        "texconv_format": "BC7_UNORM_SRGB",
        "bits_per_pixel": 8,
    },
    "emissive": {
        "raven_name": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
        "dock_name": "TX_mapmarker_docklocation_emissive_FCC664130951154C",
        "valk_name": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
        "resident_bytes": 4620,
        "body_bytes": 4608,
        "texconv_format": "BC1_UNORM",
        "bits_per_pixel": 4,
    },
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def swizzle_96(linear: bytes, bits_per_pixel: int) -> bytes:
    # Exact GOWTool GnfImage::Swizzle traversal over a standalone 96x96 image,
    # i.e. a 24x24 grid of 4x4 BC blocks.
    width = height = 96
    pixbl = 4
    bytes_per_block = bits_per_pixel * 2
    blocks_y = height // pixbl
    blocks_x = width // pixbl
    expected = blocks_x * blocks_y * bytes_per_block
    check(len(linear) == expected, f"96px linear BC payload has {len(linear)} bytes, expected {expected}")

    out = bytearray(expected)
    write_off = 0
    for i in range((blocks_y + 7) // 8):
        for j in range((blocks_x + 7) // 8):
            for k in range(64):
                m = morton(k, 8, 8)
                row = m // 8
                col = m % 8
                x = j * 8 + col
                y = i * 8 + row
                if x < blocks_x and y < blocks_y:
                    src = bytes_per_block * (y * blocks_x + x)
                    out[write_off:write_off + bytes_per_block] = linear[src:src + bytes_per_block]
                    write_off += bytes_per_block
    check(write_off == expected, f"resident swizzle wrote {write_off} bytes, expected {expected}")
    return bytes(out)


def parse_dds(path: Path, label: str, spec: dict) -> dict:
    raw = path.read_bytes()
    check(len(raw) >= 128 and raw[:4] == b"DDS ", f"{label}: texconv output is not DDS")
    header_size = struct.unpack_from("<I", raw, 4)[0]
    check(header_size == 124, f"{label}: DDS header size {header_size} != 124")
    height = struct.unpack_from("<I", raw, 12)[0]
    width = struct.unpack_from("<I", raw, 16)[0]
    mips = struct.unpack_from("<I", raw, 28)[0] or 1
    fourcc = raw[84:88]
    data_off = 128
    format_ok = False
    format_desc = fourcc.decode("ascii", errors="replace")
    if fourcc == b"DX10":
        check(len(raw) >= 148, f"{label}: truncated DX10 DDS")
        dxgi = struct.unpack_from("<I", raw, 128)[0]
        data_off = 148
        format_desc = f"DX10/{dxgi}"
        if spec["texconv_format"] == "BC7_UNORM_SRGB":
            format_ok = dxgi == 99
        elif spec["texconv_format"] == "BC1_UNORM":
            format_ok = dxgi == 71
    else:
        if spec["texconv_format"] == "BC1_UNORM":
            format_ok = fourcc == b"DXT1"
    check((width, height, mips) == (96, 96, 1), f"{label}: DDS is {width}x{height} mips={mips}, expected 96x96 mips=1")
    check(format_ok, f"{label}: DDS format {format_desc} does not match {spec['texconv_format']}")
    body = raw[data_off:]
    check(len(body) == spec["body_bytes"], f"{label}: DDS BC body {len(body)} != {spec['body_bytes']}")
    return {
        "path": str(path),
        "sha256": sha(raw),
        "width": width,
        "height": height,
        "mips": mips,
        "format": format_desc,
        "data_offset": data_off,
        "linear_body": body,
    }


def build_dds(texconv: Path, source: Path, temp: Path, label: str, spec: dict) -> dict:
    out_dir = temp / label
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(texconv), "-nologo", "-y", "-w", "96", "-h", "96", "-m", "1",
        "-f", spec["texconv_format"], "-o", str(out_dir), str(source),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    check(proc.returncode == 0, f"{label}: texconv failed ({proc.returncode}): {proc.stdout}")
    generated = out_dir / (source.stem + ".DDS")
    if not generated.exists():
        generated = out_dir / (source.stem + ".dds")
    check(generated.exists(), f"{label}: texconv output missing under {out_dir}")
    meta = parse_dds(generated, label, spec)
    meta["texconv_output"] = proc.stdout.strip()
    return meta


def patch(wad_raw: bytes, source_png: Path, texconv: Path) -> tuple[bytes, dict]:
    check(sha(wad_raw) == EXPECTED_BASE_WAD, "input WAD is not the proven registered Raven base")
    check(source_png.is_file(), f"Raven source image missing: {source_png}")
    check(texconv.is_file(), f"texconv missing: {texconv}")
    check(sha_file(texconv) == EXPECTED_TEXCONV, "texconv SHA256 is not the pinned May 2026 build")

    logical = load_logical()
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "input WAD does not round-trip exactly")

    with tempfile.TemporaryDirectory(prefix="completionist-raven-resident-") as td:
        temp = Path(td)
        built = {
            label: build_dds(texconv, source_png, temp, label, spec)
            for label, spec in TEXTURES.items()
        }

    rows = []
    preserved_records: dict[str, bytes] = {}
    header_variation_observed = False
    for label, spec in TEXTURES.items():
        raven_gpu = one_gpu(records, spec["raven_name"])
        dock_gpu = one_gpu(records, spec["dock_name"])
        valk_gpu = one_gpu(records, spec["valk_name"])
        raven_def = one_def(records, spec["raven_name"])

        check(len(raven_gpu["data"]) == spec["resident_bytes"], f"{label}: Raven resident size changed")
        check(len(dock_gpu["data"]) == spec["resident_bytes"], f"{label}: Dock resident size changed")
        check(len(valk_gpu["data"]) == spec["resident_bytes"], f"{label}: Valkyrie resident size changed")
        check(bytes(raven_gpu["data"]) == bytes(dock_gpu["data"]), f"{label}: Raven resident is not the expected Dock clone")

        dock_header = bytes(dock_gpu["data"][:12])
        valk_header = bytes(valk_gpu["data"][:12])
        raven_header = bytes(raven_gpu["data"][:12])
        # The failed static gate established these prefixes are resource-specific
        # for at least the emissive channel. What matters for our cloned Raven is
        # that its prefix still exactly matches its Dock-derived baseline.
        check(raven_header == dock_header, f"{label}: Raven resident prefix differs from its Dock-derived baseline")
        if valk_header != dock_header:
            header_variation_observed = True

        linear = built[label]["linear_body"]
        swizzled = swizzle_96(linear, spec["bits_per_pixel"])
        check(len(swizzled) == spec["body_bytes"], f"{label}: swizzled body size wrong")

        before = bytes(raven_gpu["data"])
        raven_gpu["data"][:] = raven_header + swizzled
        after = bytes(raven_gpu["data"])
        check(len(after) == spec["resident_bytes"], f"{label}: resident output size changed")
        check(after[:12] == raven_header, f"{label}: Raven resident prefix changed")
        check(after != before, f"{label}: generated Raven resident payload equals Dock unexpectedly")

        preserved_records[label] = bytes(raven_def["data"])
        rows.append({
            "label": label,
            "resident_formula": f"12 + 96*96*{spec['bits_per_pixel']}/8",
            "raven_preserved_prefix_hex": raven_header.hex(),
            "dock_prefix_hex": dock_header.hex(),
            "valkyrie_prefix_hex": valk_header.hex(),
            "dock_valkyrie_prefix_equal": dock_header == valk_header,
            "resident_bytes": spec["resident_bytes"],
            "body_bytes": spec["body_bytes"],
            "linear_dds_sha256": sha(linear),
            "swizzled_body_sha256": sha(swizzled),
            "resident_before_sha256": sha(before),
            "resident_after_sha256": sha(after),
            "dds": {k: v for k, v in built[label].items() if k != "linear_body"},
        })

    out = logical.serialize_wad(records)
    check(len(out) == len(wad_raw), "WAD length changed")
    reparsed = logical.parse_wad(out)
    check(logical.serialize_wad(reparsed) == out, "patched WAD does not round-trip")

    for label, spec in TEXTURES.items():
        check(bytes(one_def(reparsed, spec["raven_name"])["data"]) == preserved_records[label],
              f"{label}: Raven texture definition changed")

    report = {
        "result": "RAVEN_RESIDENT_96PX_ARTWORK_PATCHED_OFFLINE",
        "resident_96px_layout_gate_passed": True,
        "resident_size_math": {
            "diffuse": "9228 = 12 + 96*96*8/8",
            "emissive": "4620 = 12 + 96*96*4/8",
        },
        "raven_dock_resident_prefix_preserved": True,
        "stock_resident_prefix_is_not_universal": header_variation_observed,
        "custom_raven_96px_swizzle_applied": True,
        "input_wad_sha256": sha(wad_raw),
        "output_wad_sha256": sha(out),
        "source_png": str(source_png),
        "source_png_sha256": sha_file(source_png),
        "texconv_sha256": sha_file(texconv),
        "rows": rows,
        "raven_texture_definitions_preserved": True,
        "raven_resource_identity_preserved": True,
        "real_dock_and_valkyrie_records_untouched": True,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "note": "The 12-byte resident prefix is resource-specific, not universal. The isolated Raven keeps its original Dock-derived prefix and only its 96x96 compressed body is replaced.",
    }
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--raven-png", type=Path, required=True)
    ap.add_argument("--texconv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    out, report = patch(args.wad.read_bytes(), args.raven_png, args.texconv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
