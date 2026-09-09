#!/usr/bin/env python3
"""Build a narrow stock-art A/B for the dedicated Raven in-world carrier.

Input is the currently installed custom-art carrier candidate. The only intended
change is the first qword of COMPASS_INWORLD_COMPLETIONIST_RAVEN:
  goCompletionistRavenHUD -> stock Dock HUD icon hash.

CompletionistRaven keeps pointing at the new independent type-0x129 export. This
separates two failure mechanisms:
- if the boat renders, the new export resolves and custom Raven art is the issue;
- if nothing renders, the new type-0x129 export itself is not resolving at runtime.

No game file is written by this builder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_SOURCE_SHA256 = "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5"
NEW_NAME = "COMPASS_INWORLD_COMPLETIONIST_RAVEN"
DONOR_NAME = "COMPASS_INWORLD_DOCK"
RAVEN_CLASS = "CompletionistRaven"
INWORLD_TYPE = 0x129
COMPASS_CLASS_TYPE = 0x11E
RECORD_SIZE = 0x98
RAVEN_HUD_HASH = 0x45E5C7943749F81C
DOCK_HUD_HASH = 0x82F0296748C7393D
EXPECTED_NEW_UID = 0x21DC5A7D4AD17628
RESULT = "OFFLINE_RAVEN_INWORLD_STOCK_ART_CONTROL_BUILT"


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_packed():
    path = HERE / "build-packed-raven-compass-class.py"
    spec = importlib.util.spec_from_file_location("completionist_inworld_stock_art_packed", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def next_root(exports: list[dict], root: int, data_len: int) -> int:
    later = sorted({int(e["root"]) for e in exports if int(e["root"]) > root})
    return later[0] if later else data_len


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    source = args.input.resolve()
    raw = source.read_bytes()
    digest = sha256(raw)
    check(digest == EXPECTED_SOURCE_SHA256,
          f"input is not the installed custom-art Raven carrier candidate: {digest}")

    packed = load_packed()
    chunks = packed.parse_chunks(raw)
    data = bytes(packed.one(chunks, 12)["payload"])
    _h8, exports, _tail = packed.parse_exports(packed.one(chunks, 13)["payload"])
    relocs = packed.parse_relocations(packed.one(chunks, 15)["payload"], data)
    by_name = {e["name"]: e for e in exports}

    for name in (NEW_NAME, DONOR_NAME, RAVEN_CLASS):
        check(name in by_name, f"required export missing: {name}")
    new = by_name[NEW_NAME]
    donor = by_name[DONOR_NAME]
    raven = by_name[RAVEN_CLASS]

    check(int(new["uid"]) == EXPECTED_NEW_UID, "new in-world UID changed")
    check(int(new["type_id"]) == INWORLD_TYPE, "new in-world export type changed")
    check(int(donor["type_id"]) == INWORLD_TYPE, "Dock in-world export type changed")
    check(int(raven["type_id"]) == COMPASS_CLASS_TYPE, "CompletionistRaven type changed")

    new_root = int(new["root"])
    donor_root = int(donor["root"])
    raven_root = int(raven["root"])
    check(next_root(exports, new_root, len(data)) - new_root == RECORD_SIZE,
          "new in-world export span is not 0x98")
    check(next_root(exports, donor_root, len(data)) - donor_root == RECORD_SIZE,
          "Dock in-world export span is not 0x98")
    check(raven_root + 0x20 <= len(data), "CompletionistRaven class record outside data")

    new_record = data[new_root:new_root + RECORD_SIZE]
    donor_record = data[donor_root:donor_root + RECORD_SIZE]
    raven_record = data[raven_root:raven_root + 0x20]

    check(struct.unpack_from("<Q", new_record, 0)[0] == RAVEN_HUD_HASH,
          "new carrier no longer contains Raven HUD hash at +0x00")
    check(struct.unpack_from("<Q", donor_record, 0)[0] == DOCK_HUD_HASH,
          "Dock carrier HUD hash changed")
    check(new_record[8:] == donor_record[8:],
          "new carrier differs from Dock donor outside the first qword")

    raven_icon, _raven_radius, raven_inworld = struct.unpack_from("<QQQ", raven_record, 0)
    check(raven_icon == RAVEN_HUD_HASH, "CompletionistRaven HUD IconName changed")
    check(raven_inworld == EXPECTED_NEW_UID,
          "CompletionistRaven no longer points at the dedicated in-world export")

    patched_data = bytearray(data)
    struct.pack_into("<Q", patched_data, new_root, DOCK_HUD_HASH)
    candidate = packed.build_file(chunks, {12: bytes(patched_data)})

    out_chunks = packed.parse_chunks(candidate)
    out_data = bytes(packed.one(out_chunks, 12)["payload"])
    _oh, out_exports, out_tail = packed.parse_exports(packed.one(out_chunks, 13)["payload"])
    out_relocs = packed.parse_relocations(packed.one(out_chunks, 15)["payload"], out_data)
    out_by_name = {e["name"]: e for e in out_exports}

    check([int(e["uid"]) for e in out_exports] == [int(e["uid"]) for e in exports],
          "export UID order changed")
    check(out_tail == packed.one(chunks, 13)["payload"][8 + len(exports) * 24:],
          "export payload tail changed")
    check([(int(r["field"]), int(r["target"])) for r in out_relocs] ==
          [(int(r["field"]), int(r["target"])) for r in relocs],
          "relocation semantics changed")

    out_new = out_by_name[NEW_NAME]
    out_new_root = int(out_new["root"])
    out_new_record = out_data[out_new_root:out_new_root + RECORD_SIZE]
    check(out_new_record == donor_record,
          "stock-art control carrier is not byte-identical to Dock donor")
    out_raven = out_by_name[RAVEN_CLASS]
    out_raven_record = out_data[int(out_raven["root"]):int(out_raven["root"]) + 0x20]
    check(struct.unpack_from("<Q", out_raven_record, 16)[0] == EXPECTED_NEW_UID,
          "Raven binding changed away from new export")

    for kind in (11, 13, 14, 35, 15):
        check(packed.one(chunks, kind)["payload"] == packed.one(out_chunks, kind)["payload"],
              f"unexpected chunk {kind} change")

    changed = [i for i, (a, b) in enumerate(zip(data, out_data)) if a != b]
    check(changed and all(new_root <= i < new_root + 8 for i in changed),
          "data changes escaped the new carrier IconName qword")

    report = {
        "schema": 1,
        "result": RESULT,
        "source_sha256": digest,
        "candidate_sha256": sha256(candidate),
        "new_export": NEW_NAME,
        "new_export_uid": f"{EXPECTED_NEW_UID:016X}",
        "new_export_root": f"0x{new_root:X}",
        "completionist_raven_inworld_binding_unchanged": True,
        "carrier_before_icon_hash": f"{RAVEN_HUD_HASH:016X}",
        "carrier_after_icon_hash": f"{DOCK_HUD_HASH:016X}",
        "carrier_after_byte_identical_to_stock_dock": True,
        "changes_confined_to_new_carrier_icon_qword": True,
        "export_table_byte_identical": True,
        "relocation_table_semantics_identical": True,
        "other_dcb_chunks_byte_identical": True,
        "game_files_written": False,
        "runtime_interpretation": {
            "boat_renders": "new type-0x129 export resolves; custom Raven HUD resource is not valid through the in-world carrier path",
            "no_marker": "new type-0x129 export itself is not resolving/registered at runtime"
        }
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check(source.read_bytes() == raw, "input file changed during offline build")

    print(RESULT)
    print(f"  source SHA256:    {digest}")
    print(f"  candidate SHA256: {report['candidate_sha256']}")
    print(f"  Raven InWorld:    {EXPECTED_NEW_UID:016X} (unchanged)")
    print(f"  carrier IconName: {RAVEN_HUD_HASH:016X} -> {DOCK_HUD_HASH:016X}")
    print("  carrier now byte-identical to stock Dock: true")
    print("  export/relocation semantics changed: false")
    print("  game files written: false")
    print(f"  candidate: {args.output}")
    print(f"  report:    {args.report}")


if __name__ == "__main__":
    main()
