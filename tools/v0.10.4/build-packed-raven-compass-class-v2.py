"""Build the corrected packed CompletionistRaven CompassIconClass candidate.

The first packed candidate correctly placed a tenth type-0x11E record in the
contiguous CompassIconClass data block, but appended its 24-byte export entry to
the end of chunk 13. Native lookup RVA 0x431B90 binary-searches those 24-byte
entries by the u64 UID at +0x10 and returns data_base + the u32 root at +0x00.
Therefore the export table must remain strictly UID-sorted.

This v2 builder reuses the already-validated packed data/relocation transform,
then changes only export-entry ordering: CompletionistRaven is inserted at its
UID-sorted position while all entry fields and the string tail remain byte-for-
byte semantically identical. No game files, saves, progression, marker state, or
Lua are written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

LEGACY_NAME = "build-packed-raven-compass-class.py"
RUNTIME_LOOKUP_RVA = 0x431B90
ENTRY_SIZE = 24
ROOT_OFFSET = 0x00
UID_OFFSET = 0x10


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_legacy():
    path = Path(__file__).with_name(LEGACY_NAME)
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("completionist_packed_legacy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strictly_increasing(values: list[int]) -> bool:
    return all(a < b for a, b in zip(values, values[1:]))


def serialize_exports(header8: bytes, exports: list[dict], tail: bytes) -> bytes:
    out = bytearray(header8)
    for e in exports:
        out += struct.pack(
            "<IIQQ",
            int(e["root"]),
            int(e["type_id"]),
            int(e["string_offset"]),
            int(e["uid"]),
        )
    out += tail
    return bytes(out)


def build_corrected(stock_raw: bytes):
    legacy = load_legacy()

    # Prove the untouched stock export index is already strictly UID-sorted.
    stock_chunks = legacy.parse_chunks(stock_raw)
    _stock_h8, stock_exports, _stock_tail = legacy.parse_exports(
        legacy.one(stock_chunks, 13)["payload"]
    )
    stock_uids = [int(e["uid"]) for e in stock_exports]
    if not strictly_increasing(stock_uids):
        raise ValueError("stock export UID table is not strictly increasing")

    # Reuse the validated packed data insertion/root shifting/relocation rewrite.
    legacy_candidate, legacy_report = legacy.build_candidate(stock_raw)
    legacy_chunks = legacy.parse_chunks(legacy_candidate)
    header8, exports, tail = legacy.parse_exports(legacy.one(legacy_chunks, 13)["payload"])

    new_uid = int(legacy.name_hash(legacy.NEW_CLASS))
    legacy_uids = [int(e["uid"]) for e in exports]
    if len(exports) != len(stock_exports) + 1:
        raise ValueError("legacy packed candidate export count is unexpected")
    if exports[-1]["name"] != legacy.NEW_CLASS or int(exports[-1]["uid"]) != new_uid:
        raise ValueError("legacy candidate no longer appends CompletionistRaven as its final export")
    if legacy_uids[:-1] != stock_uids:
        raise ValueError("legacy candidate changed stock export UID order")
    if strictly_increasing(legacy_uids):
        raise ValueError("legacy candidate is unexpectedly already UID-sorted")

    # Reorder only the fixed-size export entries. String offsets remain valid
    # because the entry region size and the string-tail start do not change.
    sorted_exports = sorted(exports, key=lambda e: int(e["uid"]))
    sorted_uids = [int(e["uid"]) for e in sorted_exports]
    if not strictly_increasing(sorted_uids):
        raise ValueError("corrected export UID table is not strictly increasing")

    new_export_payload = serialize_exports(header8, sorted_exports, tail)
    corrected = legacy.build_file(legacy_chunks, {13: new_export_payload})

    # Parse again from serialized bytes and validate every semantic invariant.
    out_chunks = legacy.parse_chunks(corrected)
    _h8, out_exports, out_tail = legacy.parse_exports(legacy.one(out_chunks, 13)["payload"])
    out_uids = [int(e["uid"]) for e in out_exports]
    if out_uids != sorted_uids or not strictly_increasing(out_uids):
        raise ValueError("serialized corrected export table lost UID order")
    if out_tail != tail:
        raise ValueError("export string tail changed while sorting entries")

    legacy_by_name = {e["name"]: e for e in exports}
    out_by_name = {e["name"]: e for e in out_exports}
    if set(legacy_by_name) != set(out_by_name):
        raise ValueError("export name set changed during ordering fix")
    for name, before in legacy_by_name.items():
        after = out_by_name[name]
        for field in ("root", "type_id", "string_offset", "uid"):
            if int(after[field]) != int(before[field]):
                raise ValueError(f"export semantic changed for {name}: {field}")

    # Only chunk 13 may differ from the legacy packed candidate.
    for kind in (11, 12, 14, 35, 15):
        if legacy.one(legacy_chunks, kind)["payload"] != legacy.one(out_chunks, kind)["payload"]:
            raise ValueError(f"non-export chunk {kind} changed during ordering fix")

    raven = out_by_name.get(legacy.NEW_CLASS)
    if raven is None:
        raise ValueError("CompletionistRaven export disappeared")
    if int(raven["root"]) != legacy.INSERT_AT or int(raven["type_id"]) != legacy.TYPE_ID:
        raise ValueError("CompletionistRaven root/type changed")

    new_index = next(i for i, e in enumerate(out_exports) if e["name"] == legacy.NEW_CLASS)
    old_index = len(exports) - 1
    if new_index == old_index:
        raise ValueError("CompletionistRaven export was not moved into sorted position")

    report = dict(legacy_report)
    report["candidate_sha256"] = sha256(corrected)
    report["candidate_bytes"] = len(corrected)
    report["architecture"] = dict(report["architecture"])
    report["architecture"]["hypothesis"] = (
        "Native tweak lookup 0x431B90 binary-searches the 24-byte R_Perm export index by UID at +0x10; "
        "the packed CompassIconClass record must therefore also have a UID-sorted export entry."
    )
    report["runtime_lookup_contract"] = {
        "lookup_rva": f"0x{RUNTIME_LOOKUP_RVA:X}",
        "entry_size": ENTRY_SIZE,
        "root_offset": f"0x{ROOT_OFFSET:02X}",
        "uid_offset": f"0x{UID_OFFSET:02X}",
        "search": "binary_search_ascending_uid",
        "returns": "runtime_data_base_plus_u32_root",
    }
    report["export_order_fix"] = {
        "stock_export_uid_order_strictly_increasing": True,
        "legacy_candidate_export_uid_order_strictly_increasing": False,
        "corrected_candidate_export_uid_order_strictly_increasing": True,
        "legacy_candidate_sha256": sha256(legacy_candidate),
        "legacy_completionist_export_index": old_index,
        "corrected_completionist_export_index": new_index,
        "completionist_uid": f"{new_uid:016X}",
        "string_tail_byte_identical": True,
        "non_export_chunks_byte_identical_to_legacy_candidate": True,
    }
    report["validation"] = dict(report["validation"])
    report["validation"]["export_uid_order_strictly_increasing"] = True
    report["validation"]["runtime_lookup_entry_layout_matches_export_layout"] = True
    report["next_gate"] = (
        "Run the registration-only runtime proof again with this UID-sorted packed candidate. "
        "If CompletionistRaven is accepted while still cloning DockPoint visuals, proceed to independent Raven HUD/world artwork."
    )

    return corrected, report, legacy


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    legacy = load_legacy()
    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)
    stock_raw = source.read_bytes()
    digest = sha256(stock_raw)
    if digest != legacy.EXPECTED:
        raise ValueError(f"wad_r_perm.dcb is not the researched stock file: {digest}")

    output = args.output.resolve()
    report_path = args.report.resolve()
    if output.is_relative_to(game) or report_path.is_relative_to(game):
        raise ValueError("offline candidate/report must stay outside the game directory")

    candidate, report, legacy2 = build_corrected(stock_raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if source.read_bytes() != stock_raw:
        raise ValueError("source wad_r_perm.dcb changed during offline build")

    fix = report["export_order_fix"]
    print("OFFLINE_PACKED_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT")
    print(f"  class:            {legacy2.NEW_CLASS}")
    print(f"  uid:              {legacy2.name_hash(legacy2.NEW_CLASS):016X}")
    print(f"  packed root:      0x{legacy2.INSERT_AT:X}")
    print(f"  export index:     {fix['legacy_completionist_export_index']} -> {fix['corrected_completionist_export_index']} (UID-sorted)")
    print(f"  candidate SHA256: {sha256(candidate)}")
    print(f"  output:           {output}")
    print(f"  report:           {report_path}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
