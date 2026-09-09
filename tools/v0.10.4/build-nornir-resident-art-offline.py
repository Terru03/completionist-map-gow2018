#!/usr/bin/env python3
"""Build the real Nornir chest resident map-icon artwork payloads offline.

Consumes a GOWTool texpack built from the verified Nornir concept art and applies
exactly the resident partial-linearization transform that reconstructs the stock
Dock/Valkyrie resources and the runtime-proven Completionist Raven. It writes
only build artifacts, never God of War files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
RAVEN_TEXTURES = {
    "diffuse": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
    "emissive": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
}
NORNIR = {
    "diffuse": {
        "name": "TX_completionist_nornir_chest_map_diffuse_0A43AEB29D6F80DA",
        "file_hash": 0x0A43AEB29D6F80DA,
        "block_bytes": 16,
        "resident_bytes": 9228,
    },
    "emissive": {
        "name": "TX_completionist_nornir_chest_map_emissive_58012A499511A0BB",
        "file_hash": 0x58012A499511A0BB,
        "block_bytes": 8,
        "resident_bytes": 4620,
    },
}
TRAILER_BYTES = 12


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(filename: str, module_name: str):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one_gpu(records: list[dict], name: str) -> bytes:
    rows = [
        row for row in records
        if row["name"] == name and row["kind"] == 0x1D and row["flags"] == 0x80A1
    ]
    check(len(rows) == 1, f"expected one resident GPU record for {name}, found {len(rows)}")
    return bytes(rows[0]["data"])


def build(raven_wad: Path, nornir_texpack: Path, output_dir: Path, report_path: Path) -> dict:
    check(file_sha(raven_wad) == EXPECTED_RAVEN_WAD, "r_ui.wad is not the frozen Raven production WAD")
    logical = load_module("build-raven-ui-logical-clone.py", "nornir_art_logical")
    mapping = load_module("inspect-resident-block-mapping.py", "nornir_art_mapping")
    transform = load_module("inspect-resident-partial-linearization.py", "nornir_art_transform")

    raw = raven_wad.read_bytes()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "Raven production WAD does not round-trip exactly")
    pack = mapping.parse_texpack(nornir_texpack)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, spec in NORNIR.items():
        raven = one_gpu(records, RAVEN_TEXTURES[label])
        check(len(raven) == spec["resident_bytes"], f"{label}: Raven donor resident size changed")
        stream, stream_meta = mapping.streamed_payload(pack, spec["file_hash"])
        rebuilt, mips = transform.reconstruct_resident_body(stream, spec["block_bytes"], 148, 148)
        check(len(rebuilt) == spec["resident_bytes"] - TRAILER_BYTES,
              f"{label}: reconstructed body size changed")
        trailer = raven[-TRAILER_BYTES:]
        resident = rebuilt + trailer
        check(len(resident) == spec["resident_bytes"], f"{label}: final resident size changed")
        check(resident != raven, f"{label}: Nornir resident unexpectedly equals Raven donor")

        out = output_dir / f"{spec['name']}.resident.bin"
        out.write_bytes(resident)
        rows.append({
            "label": label,
            "resource_name": spec["name"],
            "file_hash": f"{spec['file_hash']:016X}",
            "block_bytes": spec["block_bytes"],
            "authored_dimensions": [148, 148],
            "resident_bytes": len(resident),
            "resident_body_bytes": len(rebuilt),
            "preserved_raven_trailer_hex": trailer.hex(),
            "raven_donor_sha256": sha(raven),
            "resident_body_sha256": sha(rebuilt),
            "resident_sha256": sha(resident),
            "output": str(out),
            "texpack_stream": stream_meta,
            "mips": mips,
        })

    check(len(rows) == 2, "expected exactly two Nornir resident payloads")
    report = {
        "result": "OFFLINE_NORNIR_RESIDENT_ART_BUILT",
        "source_raven_wad_sha256": file_sha(raven_wad),
        "nornir_texpack_sha256": file_sha(nornir_texpack),
        "art_source": "assets/icons/concepts/nornir_chest_concept_master.png",
        "resident_transform": "runtime-proven partial-linearization of streamed GNF mips 2..7",
        "rows": rows,
        "all_payloads_match_raven_resident_dimensions": True,
        "all_payloads_differ_from_raven_art": True,
        "ready_for_nornir_wad_clone": True,
        "game_files_written": False,
        "runtime_install_performed": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "next_gate": "Clone the Raven-proven map/HUD resource grammar under Nornir identities, inject these two resident payloads, and add the two planned GOPool rows entirely offline."
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raven-wad", type=Path, required=True)
    parser.add_argument("--nornir-texpack", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.raven_wad, args.nornir_texpack, args.output_dir, args.report)
    print("OFFLINE_NORNIR_RESIDENT_ART_BUILT")
    for row in report["rows"]:
        print(f"  {row['label']}: {row['resource_name']} {row['resident_bytes']} bytes sha256={row['resident_sha256']}")
    print("  Raven production WAD changed: false")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
