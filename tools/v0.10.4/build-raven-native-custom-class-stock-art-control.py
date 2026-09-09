"""Build a current-state A/B DCB where CompletionistRaven keeps stock DockPoint art.

This is deliberately narrower than the dedicated Raven HUD candidate. It rebuilds the
runtime-proven UID-sorted packed CompletionistRaven class from the exact pre-HUD stock
wad_r_perm.dcb, so the custom class remains registered but its 0x20-byte class record
is byte-identical to DockPoint. It never writes the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_STOCK = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"
EXPECTED_CANDIDATE = "7f63cdda05f2dee6d56c961687bfe38c705c59b4d5fa9158aa218b435b2ec83e"
RESULT = "OFFLINE_RAVEN_NATIVE_CUSTOM_CLASS_STOCK_ART_CONTROL_BUILT"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_builder():
    # The successful runtime proof used the v2 builder. v1 deliberately left the
    # new export appended and therefore not UID-sorted for the native binary search.
    path = HERE / "build-packed-raven-compass-class-v2.py"
    spec = importlib.util.spec_from_file_location("packed_raven_stock_art_control_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    stock = args.stock.resolve()
    raw = stock.read_bytes()
    if sha(raw) != EXPECTED_STOCK:
        raise ValueError(f"Pre-HUD stock DCB hash mismatch: {sha(raw)}")

    packed_v2 = load_builder()
    candidate, base_report, legacy = packed_v2.build_corrected(raw)
    candidate_sha = sha(candidate)
    if candidate_sha != EXPECTED_CANDIDATE:
        raise ValueError(f"Runtime-proven UID-sorted packed candidate hash changed: {candidate_sha}")

    chunks = legacy.parse_chunks(candidate)
    data = legacy.one(chunks, 12)["payload"]
    exports = legacy.parse_exports(legacy.one(chunks, 13)["payload"])[1]
    by_name = {row["name"]: row for row in exports}
    dock = by_name["DockPoint"]
    raven = by_name["CompletionistRaven"]
    if raven["type_id"] != dock["type_id"]:
        raise ValueError("CompletionistRaven/DockPoint type mismatch")
    dock_record = bytes(data[dock["root"]:dock["root"] + 0x20])
    raven_record = bytes(data[raven["root"]:raven["root"] + 0x20])
    if raven_record != dock_record:
        raise ValueError("CompletionistRaven is not byte-identical to DockPoint in stock-art control")

    uids = [int(row["uid"]) for row in exports]
    if not packed_v2.strictly_increasing(uids):
        raise ValueError("Stock-art control export table is not strictly UID-sorted")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    report = {
        "result": RESULT,
        "stock": str(stock),
        "stock_sha256": EXPECTED_STOCK,
        "candidate": str(args.output.resolve()),
        "candidate_sha256": candidate_sha,
        "compass_class": "CompletionistRaven",
        "class_uid": f"{legacy.name_hash('CompletionistRaven'):016X}",
        "class_record_byte_identical_to_DockPoint": True,
        "export_uid_order_strictly_increasing": True,
        "DockPoint_root": hex(dock["root"]),
        "CompletionistRaven_root": hex(raven["root"]),
        "base_builder_result": base_report.get("result"),
        "base_builder": "build-packed-raven-compass-class-v2.py",
        "game_files_written": False,
        "purpose": "Isolate dedicated Raven HUD IconName/resource chain from custom-class registration and native routing.",
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(RESULT)
    print(f"  candidate SHA256: {candidate_sha}")
    print("  CompletionistRaven record == DockPoint record: true")
    print("  export UID order strictly increasing: true")
    print("  game files written: false")


if __name__ == "__main__":
    main()
