"""Patch only the authored v0.10.3 Raven marker's map icon string offline.

Input must already contain exactly one Completionist_V103_Veithurgard_Raven_01
marker whose Icon is goMapIconDock. The output changes only that marker pointer
to goMapIconCompletionistRaven by appending one string to the DCB data chunk.
No game files are written by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_native_markers",
    HERE.parent / "v0.10.3" / "inspect-native-markers.py",
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

RAVEN_NAME = native.RAVEN_NAME
RAVEN_ID = native.name_hash(RAVEN_NAME)
OLD_ICON = "goMapIconDock"
NEW_ICON = "goMapIconCompletionistRaven"


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def align(blob: bytearray, boundary: int = 16) -> int:
    pad = (-len(blob)) % boundary
    if pad:
        blob.extend(b"\0" * pad)
    return len(blob)


def iter_markers(master: native.Dcb):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            for marker in master.array(region + 0x38, 0x48):
                yield realm_id, region_id, marker


def rebuild(source: native.Dcb, blob: bytes, output: Path) -> None:
    raw = source.raw
    rebuilt = bytearray()
    offset = 0
    while offset < len(raw):
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        header = bytearray(raw[offset : offset + 96])
        payload = raw[offset + 96 : offset + 96 + size]
        if kind == 12:
            payload = blob
        struct.pack_into("<I", header, 4, len(payload))
        rebuilt.extend(header)
        rebuilt.extend(payload)
        rebuilt.extend(b"\0" * ((-len(rebuilt)) % 16))
        offset = (offset + 96 + size + 15) & ~15
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rebuilt)
    native.Dcb(output)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    source = native.Dcb(args.input.resolve())
    matches = [(realm, region, marker) for realm, region, marker in iter_markers(source)
               if source.unpack("<Q", marker)[0] == RAVEN_ID]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one authored Raven marker, found {len(matches)}")
    realm, region, marker = matches[0]
    old_icon = source.string(marker + 8)
    if old_icon != OLD_ICON:
        raise ValueError(f"Expected Raven Icon {OLD_ICON!r}, got {old_icon!r}")
    if marker + 8 not in source.relocations:
        raise ValueError("Raven Icon pointer is not a DCB relocation")

    blob = bytearray(source.blob)
    string_offset = align(blob, 1)
    blob.extend(NEW_ICON.encode("ascii") + b"\0")
    struct.pack_into("<q", blob, marker + 8, string_offset - (marker + 8))

    output = args.output.resolve()
    rebuild(source, bytes(blob), output)
    patched = native.Dcb(output)
    patched_matches = [(r, g, m) for r, g, m in iter_markers(patched)
                       if patched.unpack("<Q", m)[0] == RAVEN_ID]
    if len(patched_matches) != 1:
        raise ValueError("Patched Raven marker did not reparse uniquely")
    _, _, patched_marker = patched_matches[0]
    if patched.string(patched_marker + 8) != NEW_ICON:
        raise ValueError("Patched Raven Icon did not resolve to the dedicated UI identity")

    report = {
        "result": "NATIVE_RAVEN_MAP_ICON_POINTER_PATCHED_OFFLINE",
        "input": str(args.input.resolve()),
        "output": str(output),
        "input_sha256": sha256(args.input.read_bytes()),
        "output_sha256": sha256(output.read_bytes()),
        "raven_name": RAVEN_NAME,
        "raven_id": f"{RAVEN_ID:016X}",
        "realm": f"{realm:016X}",
        "region": f"{region:016X}",
        "old_icon": OLD_ICON,
        "new_icon": NEW_ICON,
        "relocation_preserved": True,
        "game_files_written": False,
    }
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
