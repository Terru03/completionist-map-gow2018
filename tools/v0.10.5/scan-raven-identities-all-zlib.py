"""Read-only exhaustive Veithurgard Raven identity scan across frozen GoW save backups.

Reads only recognized Desktop backup copies. Searches raw save bytes and every
successfully decompressible zlib stream for exact representations of the proven
Veithurgard Raven identity: native/script GUIDs, parent quest, WAD, marker name,
custom UID and native world position. It never opens or writes the active save
folder and never patches save data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import uuid
import zlib

MAX_DECOMPRESSED = 16 * 1024 * 1024
INPUT_LIMIT = 4 * 1024 * 1024
TARGET_INSTANCE = "642d0d16-4af0-a5d4-076e-77933c549a5d"
TARGET_SCRIPT = "2f0f1759-4a6c-864f-c4db-caa4bbc7ea61"
TARGET_CATALOGUE = "raven_642d0d164af0a5d4076e77933c549a5d"
TARGET_PARENT = "RegionSummary_VF_Raven_Parent"
TARGET_WAD = "xpl200_funeral.wad"
TARGET_MARKER = "Completionist_V103_Veithurgard_Raven_01"
TARGET_UID_HEX = "E15E6BC82AE2773E"
TARGET_UID_UNSIGNED = int(TARGET_UID_HEX, 16)
RAVEN_FIELD_ID = bytes.fromhex("b0b227342530c24ea0a803505c2eb7ad")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_backup_dirs(desktop: Path) -> list[Path]:
    patterns = ("GodOfWar-SaveBackup-*", "GodOfWar-BeforeRestore-*", "GoW-TestSave-*", "GodOfWar-TestSave-*")
    found: dict[str, Path] = {}
    for pattern in patterns:
        for p in desktop.glob(pattern):
            if p.is_dir():
                found[str(p.resolve()).lower()] = p.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())


def locate_game_save(backup: Path) -> Path | None:
    saves = [p for p in backup.rglob("game.sav") if p.is_file()]
    return saves[0] if len(saves) == 1 else None


def valid_zlib_header(data: bytes, offset: int) -> bool:
    if offset + 1 >= len(data):
        return False
    cmf, flg = data[offset], data[offset + 1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) + flg) % 31 == 0


def decompress_stream(data: bytes, offset: int) -> tuple[bytes, int] | None:
    source = data[offset:min(len(data), offset + INPUT_LIMIT)]
    try:
        obj = zlib.decompressobj()
        raw = obj.decompress(source, MAX_DECOMPRESSED + 1)
        if len(raw) > MAX_DECOMPRESSED or not obj.eof or not raw:
            return None
        consumed = len(source) - len(obj.unused_data)
        if consumed <= 2:
            return None
        return raw, consumed
    except zlib.error:
        return None


def find_all(data: bytes, needle: bytes, limit: int = 256) -> list[int]:
    if not needle:
        return []
    out = []
    start = 0
    while len(out) < limit:
        pos = data.find(needle, start)
        if pos < 0:
            break
        out.append(pos)
        start = pos + 1
    return out


def context_hex(data: bytes, pos: int, needle_len: int, radius: int = 48) -> str:
    lo = max(0, pos - radius)
    hi = min(len(data), pos + needle_len + radius)
    return data[lo:hi].hex()


def ascii_variants(label: str, text: str) -> dict[str, bytes]:
    return {
        f"{label}_ascii": text.encode("ascii"),
        f"{label}_ascii_lower": text.lower().encode("ascii"),
        f"{label}_utf16le": text.encode("utf-16le"),
    }


def load_position(repo: Path) -> tuple[float, float, float]:
    cat = json.loads((repo / "catalogue" / "odins-ravens.json").read_text(encoding="utf-8"))
    rows = [r for r in cat["ravens"] if r["catalogue_id"] == TARGET_CATALOGUE]
    if len(rows) != 1:
        raise RuntimeError(f"Expected one target catalogue row, found {len(rows)}")
    xyz = rows[0]["source"]["native_world_position"]
    if len(xyz) != 3:
        raise RuntimeError("Target native world position is not xyz")
    return float(xyz[0]), float(xyz[1]), float(xyz[2])


def patterns(repo: Path) -> dict[str, bytes]:
    p: dict[str, bytes] = {}
    for label, text in (
        ("instance_guid", TARGET_INSTANCE),
        ("script_guid", TARGET_SCRIPT),
        ("parent_quest", TARGET_PARENT),
        ("wad", TARGET_WAD),
        ("marker_name", TARGET_MARKER),
        ("marker_uid_hex", TARGET_UID_HEX),
        ("catalogue_id", TARGET_CATALOGUE),
    ):
        p.update(ascii_variants(label, text))
    for label, value in (("instance_guid", TARGET_INSTANCE), ("script_guid", TARGET_SCRIPT)):
        u = uuid.UUID(value)
        p[f"{label}_uuid_bytes"] = u.bytes
        p[f"{label}_uuid_bytes_le"] = u.bytes_le
    p["marker_uid_u64_le"] = TARGET_UID_UNSIGNED.to_bytes(8, "little", signed=False)
    p["marker_uid_u64_be"] = TARGET_UID_UNSIGNED.to_bytes(8, "big", signed=False)
    signed = TARGET_UID_UNSIGNED - (1 << 64) if TARGET_UID_UNSIGNED >= (1 << 63) else TARGET_UID_UNSIGNED
    p["marker_uid_i64_le"] = int(signed).to_bytes(8, "little", signed=True)
    p["marker_uid_i64_be"] = int(signed).to_bytes(8, "big", signed=True)
    x, y, z = load_position(repo)
    for fmt_label, fmt in (("f32le", "<fff"), ("f32be", ">fff"), ("f64le", "<ddd"), ("f64be", ">ddd")):
        p[f"world_xyz_{fmt_label}"] = struct.pack(fmt, x, y, z)
    p["ravenKilled_field_id"] = RAVEN_FIELD_ID
    return p


def scan_blob(data: bytes, needles: dict[str, bytes]) -> dict:
    raw_hits = []
    for name, needle in needles.items():
        for pos in find_all(data, needle):
            raw_hits.append({"pattern": name, "offset": pos, "context_hex": context_hex(data, pos, len(needle))})

    streams = []
    attempted = successful = 0
    cursor = 0
    while True:
        at = data.find(b"\x78", cursor)
        if at < 0:
            break
        cursor = at + 1
        if not valid_zlib_header(data, at):
            continue
        attempted += 1
        result = decompress_stream(data, at)
        if result is None:
            continue
        successful += 1
        raw, consumed = result
        hits = []
        for name, needle in needles.items():
            for pos in find_all(raw, needle):
                hits.append({"pattern": name, "offset": pos, "context_hex": context_hex(raw, pos, len(needle))})
        if hits:
            identity_hits = [h for h in hits if h["pattern"] != "ravenKilled_field_id"]
            field_hits = [h for h in hits if h["pattern"] == "ravenKilled_field_id"]
            streams.append({
                "compressed_offset": at,
                "compressed_bytes": consumed,
                "decompressed_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "identity_hit_count": len(identity_hits),
                "field_hit_count": len(field_hits),
                "co_located_identity_and_field": bool(identity_hits and field_hits),
                "hits": hits,
            })
    return {"raw_hits": raw_hits, "zlib_attempted": attempted, "zlib_successful": successful, "streams": streams}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desktop", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    desktop = args.desktop.expanduser().resolve()
    repo = args.repo.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    backups = []
    for b in candidate_backup_dirs(desktop):
        s = locate_game_save(b)
        if s is not None:
            backups.append((b, s))
    if len(backups) != 2:
        raise RuntimeError(f"Expected exactly two recognized frozen game.sav backups, found {len(backups)}")

    needles = patterns(repo)
    before = {str(s): sha256_file(s) for _, s in backups}
    results = []
    for backup, save in backups:
        data = save.read_bytes()
        scan = scan_blob(data, needles)
        results.append({"backup": backup.name, "path": str(save), "sha256": before[str(save)], **scan})
    after = {str(s): sha256_file(s) for _, s in backups}
    if before != after:
        raise RuntimeError("Frozen backup hash changed during read-only identity scan")

    identity_names = [n for n in needles if n != "ravenKilled_field_id"]
    report = {
        "schema": 1,
        "scan_kind": "read_only_all_zlib_raven_identity_scan",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_hashes_unchanged": True,
        "target": {
            "catalogue_id": TARGET_CATALOGUE,
            "instance_guid": TARGET_INSTANCE,
            "script_guid": TARGET_SCRIPT,
            "parent_quest": TARGET_PARENT,
            "wad": TARGET_WAD,
            "marker": TARGET_MARKER,
            "uid_hex": TARGET_UID_HEX,
            "world_position": list(load_position(repo)),
        },
        "patterns_hex": {k: v.hex() for k, v in needles.items()},
        "files": results,
        "safety": {"active_save_opened": False, "game_written": False, "save_or_progression_written": False, "source_hashes_unchanged": True},
    }

    lines = [
        "Completionist Map - exhaustive Raven identity scan",
        f"target={TARGET_CATALOGUE}",
        f"world_position={load_position(repo)}",
        f"identity_patterns={len(identity_names)} plus ravenKilled_field_id",
        "",
    ]
    for item in results:
        identity_raw = [h for h in item["raw_hits"] if h["pattern"] != "ravenKilled_field_id"]
        field_raw = [h for h in item["raw_hits"] if h["pattern"] == "ravenKilled_field_id"]
        identity_streams = [s for s in item["streams"] if s["identity_hit_count"]]
        colocated = [s for s in item["streams"] if s["co_located_identity_and_field"]]
        lines += [
            f"=== {item['backup']} ===",
            f"sha256={item['sha256']}",
            f"zlib attempted={item['zlib_attempted']} successful={item['zlib_successful']}",
            f"raw identity hits={len(identity_raw)} raw field-id hits={len(field_raw)}",
            f"zlib streams with identity={len(identity_streams)} total matched streams={len(item['streams'])} colocated_identity_field={len(colocated)}",
        ]
        for s in identity_streams:
            names = sorted({h["pattern"] for h in s["hits"] if h["pattern"] != "ravenKilled_field_id"})
            lines.append(f"  stream@{s['compressed_offset']} bytes={s['decompressed_bytes']} sha={s['sha256']} identities={names} fieldHit={bool(s['field_hit_count'])}")
            for h in s["hits"]:
                if h["pattern"] != "ravenKilled_field_id":
                    lines.append(f"    {h['pattern']} +{h['offset']} context={h['context_hex']}")
        lines.append("")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("RAVEN_IDENTITY_ALL_ZLIB_PASSED " + " ".join(f"{r['backup']}:successful={r['zlib_successful']}" for r in results))
    print("active_save_opened=false source_hashes_unchanged=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
