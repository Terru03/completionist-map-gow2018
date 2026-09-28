#!/usr/bin/env python3
"""Read the six Nornir process dumps without loading full dumps into RAM."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path
import struct
import uuid


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
EXPECTED_EXE_SHA = "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452"
STAGES = (
    "A0_before_runes", "A1_after_first_rune", "A2_after_second_rune",
    "A3_after_chest_open", "B0_before_chest_open", "B1_after_chest_open",
)

# Exact shipped GoW.exe staging layout already used by the read-only Raven probe.
POOL_SIZE_RVA = 0x22C6938
POOL_BASE_RVA = 0x22C6940
RECORD_COUNT_RVA = 0x22C696C
RECORD_BASE_RVA = 0x22C7170
RECORD_STRIDE = 0xA8
MAX_RECORDS = 4096
MAX_POOL_SIZE = 0x140000
MAX_PAYLOAD = 0x140000
SAVE_PREFIX = 4160
SAVE_SLOT_SIZE = 1_677_512
SAVE_SLOT_COUNT = 20


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


class FullMemoryDump:
    def __init__(self, path: Path):
        self.path = path
        self.file = path.open("rb")
        self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.size = len(self.data)
        require(self.size >= 32 and self.data[:4] == b"MDMP", f"invalid minidump: {path}")
        _, _, count, directory, _, _, self.flags = struct.unpack_from("<IIIIIIQ", self.data)
        require(count <= 128 and directory + count * 12 <= self.size,
                f"invalid minidump stream directory: {path}")
        self.streams = {}
        for index in range(count):
            kind, size, rva = struct.unpack_from("<III", self.data, directory + index * 12)
            # DbgHelp may leave several unused directory slots (stream type 0).
            if kind == 0:
                continue
            require(kind not in self.streams and rva + size <= self.size,
                    f"invalid minidump stream {kind}: {path}")
            self.streams[kind] = (rva, size)
        require(9 in self.streams, f"full memory stream missing: {path}")
        stream_rva, stream_size = self.streams[9]
        require(stream_size >= 16, f"short full memory stream: {path}")
        memory_count, file_rva = struct.unpack_from("<QQ", self.data, stream_rva)
        require(memory_count <= 1_000_000 and stream_size >= 16 + memory_count * 16,
                f"invalid full memory range count: {path}")
        ranges = []
        for index in range(memory_count):
            start, size = struct.unpack_from("<QQ", self.data, stream_rva + 16 + index * 16)
            require(file_rva + size <= self.size and start + size >= start,
                    f"invalid full memory range {index}: {path}")
            ranges.append((start, start + size, file_rva))
            file_rva += size
        self.ranges = sorted(ranges)
        self.starts = [row[0] for row in self.ranges]

    def close(self) -> None:
        self.data.close()
        self.file.close()

    def read_virtual(self, address: int, size: int) -> bytes:
        require(size >= 0 and size <= MAX_PAYLOAD, f"invalid virtual read size {size}")
        result = bytearray()
        current = address
        while len(result) < size:
            index = bisect_right(self.starts, current) - 1
            if index < 0:
                raise ValueError(f"virtual address not captured: 0x{current:X}")
            start, end, file_offset = self.ranges[index]
            if current >= end:
                raise ValueError(f"virtual address not captured: 0x{current:X}")
            take = min(size - len(result), end - current)
            result.extend(self.data[file_offset + current - start:
                                    file_offset + current - start + take])
            current += take
        return bytes(result)

    def module_base(self, executable_name: str = "gow.exe") -> int:
        require(4 in self.streams, "minidump module stream missing")
        rva, size = self.streams[4]
        require(size >= 4, "short module stream")
        count, = struct.unpack_from("<I", self.data, rva)
        require(count <= 10_000 and size >= 4 + count * 108, "bad module count")
        for index in range(count):
            off = rva + 4 + index * 108
            base, = struct.unpack_from("<Q", self.data, off)
            name_rva, = struct.unpack_from("<I", self.data, off + 20)
            require(name_rva + 4 <= self.size, "bad module name RVA")
            byte_count, = struct.unpack_from("<I", self.data, name_rva)
            require(byte_count <= 4096 and name_rva + 4 + byte_count <= self.size,
                    "bad module name length")
            name = self.data[name_rva + 4:name_rva + 4 + byte_count].decode("utf-16le")
            if Path(name.replace("\\", "/")).name.lower() == executable_name:
                return base
        raise ValueError(f"{executable_name} module absent from dump")


def identity_tokens(rows: list[dict]) -> list[tuple[bytes, str, str]]:
    result = []
    for row in rows:
        label = row["catalogue_id"]
        for field in ("instance_guid",):
            value = row["native"].get(field)
            if not isinstance(value, str):
                continue
            try:
                parsed = uuid.UUID(value)
            except ValueError:
                continue
            for token, encoding in ((str(parsed).encode(), "guid_ascii"),
                                    (str(parsed).encode("utf-16le"), "guid_utf16"),
                                    (parsed.bytes_le, "guid_bytes_le")):
                result.append((token, label, f"{field}:{encoding}"))
        key = row["progression"].get("instance_key")
        if isinstance(key, str) and len(key) >= 16:
            result.extend(((key.encode(), label, "instance_key_ascii"),
                           (key.encode("utf-16le"), label, "instance_key_utf16")))
    return result


def payload_identity_hits(payload: bytes, tokens: list[tuple[bytes, str, str]]) -> list[dict]:
    hits = []
    for token, catalogue_id, form in tokens:
        at = payload.find(token)
        if at >= 0:
            hits.append({"catalogue_id": catalogue_id, "form": form, "offset": at})
    return sorted(hits, key=lambda row: (row["catalogue_id"], row["form"], row["offset"]))


def inspect_stage(root: Path, stage: str, tokens: list[tuple[bytes, str, str]]) -> dict:
    metadata_path = root / f"{stage}.json"
    dump_path = root / f"{stage}.dmp"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    require(metadata["stage"] == stage, f"wrong stage metadata: {stage}")
    require(metadata.get("executable_sha256") == EXPECTED_EXE_SHA,
            f"unsupported GoW executable for staging offsets: {stage}")
    dump = FullMemoryDump(dump_path)
    try:
        module_base = dump.module_base()
        claimed_base = metadata.get("module_base")
        if claimed_base is not None:
            require(module_base == int(claimed_base, 16), f"module base differs: {stage}")
        pool_size, = struct.unpack("<I", dump.read_virtual(module_base + POOL_SIZE_RVA, 4))
        pool_base, = struct.unpack("<Q", dump.read_virtual(module_base + POOL_BASE_RVA, 8))
        record_count, = struct.unpack("<I", dump.read_virtual(module_base + RECORD_COUNT_RVA, 4))
        require(record_count <= MAX_RECORDS and pool_size <= MAX_POOL_SIZE,
                f"implausible staging state: {stage}")
        records = []
        for index in range(record_count):
            raw = dump.read_virtual(module_base + RECORD_BASE_RVA + index * RECORD_STRIDE,
                                    RECORD_STRIDE)
            key, = struct.unpack_from("<I", raw, 0x24)
            payload_address, = struct.unpack_from("<Q", raw, 0x48)
            payload_size, = struct.unpack_from("<I", raw, 0x58)
            name = raw[0x84:0xA8].split(b"\x00", 1)[0].decode("ascii", errors="replace")
            record = {"index": index, "key_hex": f"0x{key:08X}", "name": name,
                      "payload_size": payload_size, "payload_sha256": None,
                      "nornir_identity_hits": []}
            if (payload_size and payload_size <= MAX_PAYLOAD and
                    pool_base <= payload_address and
                    payload_address + payload_size <= pool_base + pool_size):
                payload = dump.read_virtual(payload_address, payload_size)
                record["payload_sha256"] = hashlib.sha256(payload).hexdigest()
                record["nornir_identity_hits"] = payload_identity_hits(payload, tokens)
            records.append(record)
        return {
            "stage": stage,
            "process_id": metadata["process_id"],
            "dump_bytes": dump.size,
            "module_base": f"0x{module_base:X}",
            "memory_range_count": len(dump.ranges),
            "staging_pool_size": pool_size,
            "staging_record_count": record_count,
            "records": records,
            "identity_hit_catalogue_ids": sorted({hit["catalogue_id"] for record in records
                                                  for hit in record["nornir_identity_hits"]}),
        }
    finally:
        dump.close()


def save_summary(root: Path, stage: str, previous: str | None) -> dict:
    path = root / f"{stage}.game.sav"
    if not path.exists():
        return {"stage": stage, "present": False}
    data = path.read_bytes()
    result = {"stage": stage, "present": True, "bytes": len(data),
              "sha256": hashlib.sha256(data).hexdigest()}
    if previous is None:
        return result
    old_path = root / f"{previous}.game.sav"
    if not old_path.exists():
        return result
    old = old_path.read_bytes()
    if len(old) != len(data) or len(data) != SAVE_PREFIX + SAVE_SLOT_COUNT * SAVE_SLOT_SIZE:
        result["layout_comparison"] = "size_differs_or_unknown"
        return result
    changed = []
    for index in range(SAVE_SLOT_COUNT):
        start = SAVE_PREFIX + index * SAVE_SLOT_SIZE
        end = start + SAVE_SLOT_SIZE
        if data[start:end] != old[start:end]:
            changed.append(index)
    result["changed_slots_since_previous_stage"] = changed
    result["global_prefix_changed"] = data[:SAVE_PREFIX] != old[:SAVE_PREFIX]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.capture_root.resolve()
    require(root.is_dir(), f"capture directory missing: {root}")
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    rows = [row for row in catalogue["collectibles"] if row["family"].startswith("nornir_")]
    tokens = identity_tokens(rows)
    stages = []
    saves = []
    last_by_save: dict[str, str] = {}
    for stage in STAGES:
        if not (root / f"{stage}.dmp").exists():
            continue
        stages.append(inspect_stage(root, stage, tokens))
        label = stage[0]
        saves.append(save_summary(root, stage, last_by_save.get(label)))
        last_by_save[label] = stage
    report = {
        "schema": 1,
        "result": "NORNIR_TWO_SAVE_DUMPS_READ_ONLY_ANALYZED",
        "capture_root": str(root),
        "stage_count": len(stages),
        "stage_labels": [row["stage"] for row in stages],
        "identity_hit_counts": dict(sorted(Counter(
            identity for stage in stages for identity in stage["identity_hit_catalogue_ids"]
        ).items())),
        "stages": stages,
        "save_snapshots": saves,
        "game_or_save_writes": False,
    }
    target = (args.output or root / "analysis.json").resolve()
    require(target != root and root in target.parents,
            "analysis output must stay inside the capture directory")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NORNIR_DUMP_ANALYSIS stages={len(stages)} identities={len(report['identity_hit_counts'])} "
          f"report={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
