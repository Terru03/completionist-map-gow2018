"""Rename one existing WAD_R_UI GOPool slot in-place.

This diagnostic intentionally does not add DCB rows or modify r_ui.wad.  It
changes only the 64-bit Name hash of an existing 16-byte GOPool row while
preserving its Cnt field and every other byte in wad_r_ui.dcb.

Historical offline byte-patch experiment, not a safe class-registration route.
GOPool Name selects an existing resource; it is not an alias-to-row index.
Valkyrie has live authored use and must not be a donor. No safe donor established.
See docs/research/astra-v104-map-class-registry-findings.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_DCB_SHA256 = "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a"
POOL_OFFSET = 0x90
POOL_COUNT = 255
ROW_SIZE = 0x10


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def align16(value: int) -> int:
    return (value + 15) & ~15


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


def data_chunk(raw: bytes) -> tuple[int, int]:
    off = 0
    found: list[tuple[int, int]] = []
    while off < len(raw):
        if off + 96 > len(raw):
            raise ValueError(f"short DCB chunk header at {off:#x}")
        kind, flags, size = struct.unpack_from("<HHI", raw, off)
        start = off + 96
        end = start + size
        if flags != 0x10 or end > len(raw):
            raise ValueError(f"invalid DCB chunk at {off:#x}")
        if kind == 12:
            found.append((start, end))
        off = align16(end)
    if off != len(raw) or len(found) != 1:
        raise ValueError(f"expected exactly one kind-12 data chunk, found {len(found)}")
    return found[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--old-name", required=True)
    ap.add_argument("--new-name", required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    input_path = args.input.resolve()
    raw = input_path.read_bytes()
    if sha256(raw) != EXPECTED_DCB_SHA256:
        raise ValueError("wad_r_ui.dcb is not the pinned stock build")

    old_hash = name_hash(args.old_name)
    new_hash = name_hash(args.new_name)
    if old_hash == new_hash:
        raise ValueError("old and new GOPool names hash identically")

    start, end = data_chunk(raw)
    blob = raw[start:end]
    if len(blob) != 4272:
        raise ValueError(f"unexpected WAD_R_UI data size: {len(blob)}")
    if POOL_OFFSET + POOL_COUNT * ROW_SIZE > len(blob):
        raise ValueError("GOPool range exceeds data chunk")

    rows = []
    for i in range(POOL_COUNT):
        at = POOL_OFFSET + i * ROW_SIZE
        name, cnt = struct.unpack_from("<QH", blob, at)
        rows.append((i, at, name, cnt))

    old_rows = [r for r in rows if r[2] == old_hash]
    new_rows = [r for r in rows if r[2] == new_hash]
    if len(old_rows) != 1:
        raise ValueError(f"expected exactly one old GOPool row, found {len(old_rows)}")
    if new_rows:
        raise ValueError(f"new GOPool hash already exists in {len(new_rows)} row(s)")

    row_index, row_off, _, cnt = old_rows[0]
    candidate = bytearray(raw)
    absolute = start + row_off
    before_row = bytes(candidate[absolute:absolute + ROW_SIZE])
    struct.pack_into("<Q", candidate, absolute, new_hash)
    after_row = bytes(candidate[absolute:absolute + ROW_SIZE])

    changed = [i for i, (a, b) in enumerate(zip(raw, candidate)) if a != b]
    expected_changed = [absolute + i for i in range(8)
                        if before_row[i] != after_row[i]]
    if changed != expected_changed:
        raise ValueError("candidate changed bytes outside the GOPool Name field")
    if struct.unpack_from("<H", candidate, absolute + 8)[0] != cnt:
        raise ValueError("GOPool Cnt changed unexpectedly")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)

    reread = output.read_bytes()
    rstart, rend = data_chunk(reread)
    rblob = reread[rstart:rend]
    patched_rows = [struct.unpack_from("<QH", rblob, POOL_OFFSET + i * ROW_SIZE)
                    for i in range(POOL_COUNT)]
    if sum(1 for name, _ in patched_rows if name == new_hash) != 1:
        raise ValueError("new GOPool hash did not reparse exactly once")
    if any(name == old_hash for name, _ in patched_rows):
        raise ValueError("old GOPool hash remains after patch")
    if patched_rows[row_index][1] != cnt:
        raise ValueError("patched GOPool row count did not remain stable")

    report = {
        "result": "R_UI_GOPOOL_SLOT_RENAMED_IN_PLACE",
        "input": str(input_path),
        "output": str(output),
        "input_sha256": sha256(raw),
        "output_sha256": sha256(reread),
        "old_name": args.old_name,
        "old_hash": f"{old_hash:016X}",
        "new_name": args.new_name,
        "new_hash": f"{new_hash:016X}",
        "row_index": row_index,
        "cnt_preserved": cnt,
        "pool_count_preserved": POOL_COUNT,
        "file_size_preserved": len(raw) == len(reread),
        "changed_byte_count": len(changed),
        "only_name_hash_bytes_changed": True,
        "r_ui_wad_written": False,
        "game_files_written": False,
    }
    if args.report:
        path = args.report.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
