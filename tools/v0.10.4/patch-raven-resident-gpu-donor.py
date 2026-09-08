"""Patch only the dedicated Raven resident GPU payloads with a stock donor pair.

Diagnostic only. The dedicated Raven texture definitions, names, file hashes,
user hashes and GPU resource IDs remain unchanged. Only the opaque resident GPU
payload bytes are replaced. This proves whether map rendering is sourced from
the resident WAD GPU payload rather than the external texpack stream.

No game file is modified in-place by this helper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_BASE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"

RAVEN = {
    "diffuse": "TX_completionist_raven_map_diffuse_19A41F00834C19F3",
    "emissive": "TX_completionist_raven_map_emissive_63F1E18FF93B9037",
}
DONOR = {
    "diffuse": "TX_mapmarker_valkyrielocation_diffu_8A041E6BFCE5E589",
    "emissive": "TX_mapmarker_valkyrielocation_emiss_9938C16BB9F6A5AC",
}
EXPECTED_SIZES = {"diffuse": 9228, "emissive": 4620}


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
    check(len(rows) == 1, f"expected one GPU record for {name}, found {len(rows)}")
    return rows[0]


def one_def(records: list[dict], name: str) -> dict:
    rows = [r for r in records if r["name"] == name and r["kind"] == 1 and r["flags"] == 0x8021]
    check(len(rows) == 1, f"expected one texture definition for {name}, found {len(rows)}")
    return rows[0]


def patch(raw: bytes) -> tuple[bytes, dict]:
    check(sha(raw) == EXPECTED_BASE_WAD, "input is not the proven registered Raven WAD")
    logical = load_logical()
    records = logical.parse_wad(raw)
    check(logical.serialize_wad(records) == raw, "input WAD does not round-trip exactly")

    rows = []
    preserved = {}
    for label in ("diffuse", "emissive"):
        raven_gpu = one_gpu(records, RAVEN[label])
        donor_gpu = one_gpu(records, DONOR[label])
        raven_def = one_def(records, RAVEN[label])

        expected_size = EXPECTED_SIZES[label]
        check(len(raven_gpu["data"]) == expected_size, f"{label}: Raven GPU size changed")
        check(len(donor_gpu["data"]) == expected_size, f"{label}: donor GPU size differs")
        check(bytes(raven_gpu["data"]) != bytes(donor_gpu["data"]), f"{label}: donor is not visually distinct at payload level")

        preserved[label] = {
            "raven_gpu_id": raven_gpu["id"].hex(),
            "raven_definition_id": raven_def["id"].hex(),
            "raven_definition_sha256": sha(bytes(raven_def["data"])),
            "raven_name": raven_gpu["name"],
        }
        before = bytes(raven_gpu["data"])
        donor = bytes(donor_gpu["data"])
        raven_gpu["data"][:] = donor
        rows.append({
            "label": label,
            "raven_name": RAVEN[label],
            "donor_name": DONOR[label],
            "bytes": expected_size,
            "before_sha256": sha(before),
            "donor_sha256": sha(donor),
            "after_sha256": sha(bytes(raven_gpu["data"])),
        })

    out = logical.serialize_wad(records)
    check(len(out) == len(raw), "WAD byte length changed")
    reparsed = logical.parse_wad(out)
    check(logical.serialize_wad(reparsed) == out, "patched WAD does not round-trip")

    for label in ("diffuse", "emissive"):
        gpu = one_gpu(reparsed, RAVEN[label])
        definition = one_def(reparsed, RAVEN[label])
        donor = one_gpu(reparsed, DONOR[label])
        keep = preserved[label]
        check(gpu["id"].hex() == keep["raven_gpu_id"], f"{label}: Raven GPU resource ID changed")
        check(definition["id"].hex() == keep["raven_definition_id"], f"{label}: Raven definition ID changed")
        check(sha(bytes(definition["data"])) == keep["raven_definition_sha256"], f"{label}: Raven texture definition changed")
        check(bytes(gpu["data"]) == bytes(donor["data"]), f"{label}: donor payload did not persist")

    # Stock donors and Dock are read, never altered. The serializer should retain
    # every untouched record byte-for-byte; report the narrow diagnostic intent.
    report = {
        "result": "RAVEN_RESIDENT_GPU_DONOR_PATCHED_OFFLINE",
        "diagnostic_donor": "stock Valkyrie map marker",
        "input_wad_sha256": sha(raw),
        "output_wad_sha256": sha(out),
        "wad_bytes_preserved": len(out) == len(raw),
        "raven_identity_preserved": True,
        "raven_texture_definitions_preserved": True,
        "external_texpack_untouched": True,
        "rows": rows,
        "expected_runtime_interpretation": {
            "raven_becomes_valkyrie_visual": "resident WAD GPU payload is the rendered pixel source",
            "raven_stays_dock_visual": "rendering is resolving another material/texture path; resident payload is not sufficient",
        },
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
    }
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    raw = args.input.read_bytes()
    out, report = patch(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
