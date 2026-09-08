"""Build Raven resident artwork with four byte-exact stock gates. No live writes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_RAVEN_PACK = "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7"
EXPECTED_DCB = "b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b"
EXPECTED_MAPMASTER = "b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f"
PINS = {
    "build-raven-ui-logical-clone.py": "d5f7c5b77166b3e9ba46dec17174fc1f30ca5e3bab492527636cdf63c8b41b03",
    "patch-raven-resident-artwork.py": "ef99f400d805f36c9fa1fa9b35c5fa6d00dd3ee4fd8731e054480c9cc231c4f1",
    "inspect-resident-partial-linearization.py": "34eae60dbca4106f1c2c17aa27ade77a953838507a1a38d0b8d37339a55824f6",
}
TRAILER_BYTES = 12


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pinned(filename):
    path = HERE / filename
    # Pin Git source with LF newlines; compile same bytes, skip bytecode.
    source = path.read_bytes().replace(b"\r\n", b"\n")
    check(sha(source) == PINS[filename], f"pinned helper changed: {filename}")
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def reconstruct(meta, gnf, transform):
    check(meta["format"] in (0x29, 0x23), "unsupported GNF format")
    block_bytes = 16 if meta["format"] == 0x29 else 8
    layout = gnf.mip_layout(meta, block_bytes // 2)
    output = bytearray()
    details = []
    for row in layout[2:]:
        mip = row["level"]
        pw, ph = row["swizzled_width"] // 4, row["swizzled_height"] // 4
        aw, ah = transform.active_block_dims(meta["width"], meta["height"], mip)
        check(aw <= pw and ah <= ph, f"mip{mip}: active rows exceed padded surface")
        raw = meta["image"][row["offset"]:row["offset"] + row["bytes"]]
        check(len(raw) == pw * ph * block_bytes, f"mip{mip}: short stream")
        blocks = [raw[i:i + block_bytes] for i in range(0, len(raw), block_bytes)]
        linear = transform.unswizzle_blocks(blocks, pw, ph)
        packed = b"".join(b for y in range(ah) for b in linear[y * pw:y * pw + aw])
        segment = packed + raw[len(packed):]
        details.append({"mip": mip, "resident_offset": len(output), "bytes": len(segment),
                        "active_blocks": [aw, ah], "padded_blocks": [pw, ph],
                        "packed_bytes": len(packed), "sha256": sha(segment)})
        output.extend(segment)
    return bytes(output), details


def require_exact(actual, expected, label, details):
    if actual == expected:
        return
    # Report each exact half-open mismatch range, split at mip bounds.
    ranges = []
    for row in details:
        start = row["resident_offset"]
        end = start + row["bytes"]
        run = None
        for pos in range(start, end):
            differs = pos >= len(actual) or pos >= len(expected) or actual[pos] != expected[pos]
            if differs and run is None:
                run = pos
            if run is not None and (not differs or pos == end - 1):
                ranges.append({"mip": row["mip"], "start": run, "end_exclusive": pos + 1 if differs else pos})
                run = None
    raise ValueError(f"{label}: stock reconstruction failed; lengths={len(actual)}/{len(expected)}; byte_ranges={json.dumps(ranges)}")


def patch(wad_raw, root_pack, raven_pack, dcb, mapmaster):
    check(sha(wad_raw) == EXPECTED_BASE_WAD, "input WAD is not clean registered-Raven base")
    check(file_sha(dcb) == EXPECTED_DCB, "DCB is not proven registered-Raven state")
    check(file_sha(mapmaster) == EXPECTED_MAPMASTER, "mapmaster is not proven one-Raven state")
    check(file_sha(raven_pack) == EXPECTED_RAVEN_PACK, "Raven texpack hash changed")
    logical = load_pinned("build-raven-ui-logical-clone.py")
    gnf = load_pinned("patch-raven-resident-artwork.py")
    transform = load_pinned("inspect-resident-partial-linearization.py")
    records = logical.parse_wad(wad_raw)
    check(logical.serialize_wad(records) == wad_raw, "base WAD does not round-trip exactly")
    original = copy.deepcopy(records)
    stock_checks = []
    replacements = {}
    rows = []
    for label, spec in gnf.TEXTURES.items():
        for icon, width in (("dock", 148), ("valk", 156), ("raven", 148)):
            name = spec[f"{icon}_name"]
            resident = bytes(gnf.one_gpu(records, name)["data"])
            check(len(resident) == spec["resident_bytes"], f"{name}: resident size changed")
            blob, pack_info = gnf.read_texpack_gnf(raven_pack if icon == "raven" else root_pack, spec[f"{icon}_hash"])
            meta = gnf.parse_gnf(blob)
            check((meta["width"], meta["height"], meta["mips"], meta["format"]) ==
                  (width, width, 8, spec["gnf_format"]), f"{name}: GNF metadata changed")
            check(len(blob) == 0x100 + meta["data_size"], f"{name}: trailing GNF bytes")
            rebuilt, details = reconstruct(meta, gnf, transform)
            check(len(rebuilt) + TRAILER_BYTES == len(resident), f"{name}: reconstructed size changed")
            if icon != "raven":
                require_exact(rebuilt, resident[:-TRAILER_BYTES], name, details)
                stock_checks.append({"resource": name, "exact": True, "sha256": sha(rebuilt), "mips": details})
            else:
                check(resident == bytes(gnf.one_gpu(records, spec["dock_name"])["data"]), f"{name}: base is not Dock clone")
                gnf.one_def(records, name)
                after = rebuilt + resident[-TRAILER_BYTES:]
                check(after != resident, f"{name}: Raven artwork did not change")
                replacements[name] = after
                rows.append({"resource": name, "before_sha256": sha(resident), "after_sha256": sha(after),
                             "trailer_hex": resident[-TRAILER_BYTES:].hex(), "mips": details, "texpack": pack_info})
    check(len(stock_checks) == 4 and all(x["exact"] for x in stock_checks), "four stock gates required")
    for name, after in replacements.items():
        gnf.one_gpu(records, name)["data"][:] = after
    out = logical.serialize_wad(records)
    check(len(out) == len(wad_raw), "WAD length changed")
    reparsed = logical.parse_wad(out)
    check(logical.serialize_wad(reparsed) == out, "output WAD does not round-trip exactly")
    check(len(reparsed) == len(original), "WAD record count changed")
    changed = []
    for before, after in zip(original, reparsed):
        allowed = before["name"] in replacements and before["kind"] == 0x1D and before["flags"] == 0x80A1
        if allowed:
            check(bytes(after["data"]) == replacements[before["name"]], "Raven payload differs after serialization")
            check(after["data"][-TRAILER_BYTES:] == before["data"][-TRAILER_BYTES:], "Raven trailer changed")
            changed.append(before["name"])
            after["data"] = before["data"]
        check(logical.record_bytes(before) == logical.record_bytes(after), f"unallowed record change: {before['name']}")
    check(set(changed) == set(replacements) and len(changed) == 2, "only two Raven GPU records may change")
    return out, {
        "result": "RAVEN_RESIDENT_PARTIAL_LINEARIZATION_PATCHED_OFFLINE",
        "all_four_stock_resources_reconstructed_exactly": True, "runtime_patch_gate": True,
        "input_wad_sha256": sha(wad_raw), "output_wad_sha256": sha(out),
        "dcb_sha256": file_sha(dcb), "mapmaster_sha256": file_sha(mapmaster),
        "root_texpack_sha256": file_sha(root_pack), "raven_texpack_sha256": file_sha(raven_pack),
        "pinned_helpers": PINS, "stock_checks": stock_checks, "rows": rows,
        "trailing_12_bytes_preserved": True, "raven_texture_definitions_preserved": True,
        "raven_resource_identity_preserved": True, "real_dock_and_valkyrie_records_untouched": True,
        "only_two_raven_gpu_payloads_changed": True, "output_round_trip_exact": True,
        "game_files_written": False, "save_state_written": False,
        "progression_state_written": False, "marker_state_written": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wad", "root-texpack", "raven-texpack", "dcb", "mapmaster", "output", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.wad, args.root_texpack, args.raven_texpack, args.dcb, args.mapmaster]
    outputs = [args.output, args.report]
    check(all(not p.exists() for p in outputs), "outputs must be new files")
    check(len({p.resolve() for p in inputs + outputs}) == 7, "input/output paths overlap")
    # Offline output stays outside game tree and save/state inputs.
    game = args.wad.resolve().parents[3]
    check(all(not p.resolve().is_relative_to(game) for p in outputs), "output must be outside game tree")
    out, report = patch(args.wad.read_bytes(), args.root_texpack, args.raven_texpack, args.dcb, args.mapmaster)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(out)
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("result", "runtime_patch_gate", "output_wad_sha256")}, indent=2))


if __name__ == "__main__":
    main()
