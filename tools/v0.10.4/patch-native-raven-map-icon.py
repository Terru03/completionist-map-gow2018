"""Patch only the authored v0.10.3 Raven marker's map icon string offline.

By default this preserves the previous v0.10.4 behaviour and changes
Completionist_V103_Veithurgard_Raven_01 from goMapIconDock to
goMapIconCompletionistRaven.  For controlled diagnostics the caller may select
another existing map-icon resource with --new-icon.  Only the Raven marker's
Icon pointer is changed; no stock marker record and no game file is written by
this tool.
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
DEFAULT_OLD_ICON = "goMapIconDock"
DEFAULT_NEW_ICON = "goMapIconCompletionistRaven"


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


def validate_icon_name(value: str, label: str) -> str:
    if not value or len(value) > 127:
        raise ValueError(f"{label} must be a non-empty ASCII resource name <= 127 bytes")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be ASCII") from exc
    if b"\0" in encoded:
        raise ValueError(f"{label} must not contain NUL")
    return value


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--expected-old-icon", default=DEFAULT_OLD_ICON)
    ap.add_argument("--new-icon", default=DEFAULT_NEW_ICON)
    args = ap.parse_args()

    expected_old_icon = validate_icon_name(args.expected_old_icon, "--expected-old-icon")
    new_icon = validate_icon_name(args.new_icon, "--new-icon")
    if new_icon == expected_old_icon:
        raise ValueError("--new-icon must differ from --expected-old-icon")

    input_path = args.input.resolve()
    source = native.Dcb(input_path)
    matches = [
        (realm, region, marker)
        for realm, region, marker in iter_markers(source)
        if source.unpack("<Q", marker)[0] == RAVEN_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one authored Raven marker, found {len(matches)}")
    realm, region, marker = matches[0]
    old_icon = source.string(marker + 8)
    if old_icon != expected_old_icon:
        raise ValueError(
            f"Expected Raven Icon {expected_old_icon!r}, got {old_icon!r}"
        )
    if marker + 8 not in source.relocations:
        raise ValueError("Raven Icon pointer is not a DCB relocation")

    blob = bytearray(source.blob)
    string_offset = align(blob, 1)
    blob.extend(new_icon.encode("ascii") + b"\0")
    struct.pack_into("<q", blob, marker + 8, string_offset - (marker + 8))

    output = args.output.resolve()
    rebuild(source, bytes(blob), output)
    patched = native.Dcb(output)
    patched_matches = [
        (r, g, m)
        for r, g, m in iter_markers(patched)
        if patched.unpack("<Q", m)[0] == RAVEN_ID
    ]
    if len(patched_matches) != 1:
        raise ValueError("Patched Raven marker did not reparse uniquely")
    _, _, patched_marker = patched_matches[0]
    if patched.string(patched_marker + 8) != new_icon:
        raise ValueError("Patched Raven Icon did not resolve to requested UI identity")
    if patched_marker + 8 not in patched.relocations:
        raise ValueError("Patched Raven Icon pointer lost its DCB relocation")

    report = {
        "result": "NATIVE_RAVEN_MAP_ICON_POINTER_PATCHED_OFFLINE",
        "input": str(input_path),
        "output": str(output),
        "input_sha256": sha256(input_path.read_bytes()),
        "output_sha256": sha256(output.read_bytes()),
        "raven_name": RAVEN_NAME,
        "raven_id": f"{RAVEN_ID:016X}",
        "realm": f"{realm:016X}",
        "region": f"{region:016X}",
        "old_icon": old_icon,
        "new_icon": new_icon,
        "relocation_preserved": True,
        "stock_control_resource": new_icon != DEFAULT_NEW_ICON,
        "game_files_written": False,
    }
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
