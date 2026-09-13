"""Read-only forensic scan of Desktop God of War save backups.

This tool never opens the active save directory for writing and never modifies a
backup. It hashes every source file before and after scanning and searches for the
proven Veithurgard Raven identity in several plausible serialized forms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

VEITHURGARD_INSTANCE_GUID = "642d0d16-4af0-a5d4-076e-77933c549a5d"
VEITHURGARD_SCRIPT_GUID = "2f0f1759-4a6c-864f-c4db-caa4bbc7ea61"
VEITHURGARD_PARENT = "RegionSummary_VF_Raven_Parent"
VEITHURGARD_UID = "E15E6BC82AE2773E"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relative_key(path: Path, root: Path) -> str:
    """Return one canonical cross-platform relative path key.

    pathlib renders Windows relative paths with backslashes.  The forensic report
    uses POSIX separators so hashes and later per-file records must use the same
    representation or dictionary lookups fail on Windows.
    """
    return path.relative_to(root).as_posix()


def windows_guid_bytes(guid: str) -> bytes:
    a, b, c, d, e = guid.split("-")
    return (
        bytes.fromhex(a)[::-1]
        + bytes.fromhex(b)[::-1]
        + bytes.fromhex(c)[::-1]
        + bytes.fromhex(d)
        + bytes.fromhex(e)
    )


def patterns_for(label: str, value: str, guid: bool = False) -> list[tuple[str, bytes]]:
    compact = value.replace("-", "")
    rows = [
        (f"{label}:ascii", value.encode("ascii")),
        (f"{label}:ascii_upper", value.upper().encode("ascii")),
        (f"{label}:utf16le", value.encode("utf-16le")),
        (f"{label}:compact_ascii", compact.encode("ascii")),
        (f"{label}:compact_ascii_upper", compact.upper().encode("ascii")),
        (f"{label}:compact_utf16le", compact.encode("utf-16le")),
    ]
    if guid:
        rows.extend(
            [
                (f"{label}:raw_rfc", bytes.fromhex(compact)),
                (f"{label}:raw_windows_guid", windows_guid_bytes(value)),
                (f"{label}:raw_reversed", bytes.fromhex(compact)[::-1]),
            ]
        )
    return rows


def entropy_sample(data: bytes) -> float:
    if not data:
        return 0.0
    sample = data[: min(len(data), 1024 * 1024)]
    counts = [0] * 256
    for byte in sample:
        counts[byte] += 1
    total = len(sample)
    return -sum((count / total) * math.log2(count / total) for count in counts if count)


def printable_context(data: bytes, offset: int, radius: int = 64) -> str:
    start = max(0, offset - radius)
    end = min(len(data), offset + radius)
    blob = data[start:end]
    return "".join(chr(b) if 32 <= b < 127 else "." for b in blob)


def find_all(data: bytes, needle: bytes, limit: int = 20) -> list[int]:
    if not needle:
        return []
    offsets: list[int] = []
    cursor = 0
    while len(offsets) < limit:
        at = data.find(needle, cursor)
        if at < 0:
            break
        offsets.append(at)
        cursor = at + 1
    return offsets


def candidate_backup_dirs(desktop: Path) -> list[Path]:
    patterns = (
        "GodOfWar-SaveBackup-*",
        "GodOfWar-BeforeRestore-*",
        "GoW-TestSave-*",
        "GodOfWar-TestSave-*",
    )
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in desktop.glob(pattern):
            if path.is_dir():
                found[str(path.resolve()).lower()] = path.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    args = parser.parse_args()

    desktop = args.desktop.expanduser().resolve()
    active = (Path.home() / "Saved Games" / "God of War").resolve()
    backups = candidate_backup_dirs(desktop)

    search_patterns: list[tuple[str, bytes]] = []
    search_patterns += patterns_for("veithurgard_instance_guid", VEITHURGARD_INSTANCE_GUID, True)
    search_patterns += patterns_for("veithurgard_script_guid", VEITHURGARD_SCRIPT_GUID, True)
    search_patterns += patterns_for("veithurgard_parent", VEITHURGARD_PARENT, False)
    search_patterns += patterns_for("veithurgard_marker_uid", VEITHURGARD_UID, False)
    search_patterns += patterns_for("ravenKilled", "ravenKilled", False)

    report: dict = {
        "schema": 1,
        "scan_kind": "read_only_desktop_save_backup_forensics",
        "active_save_directory": str(active),
        "active_save_opened": False,
        "source_files_modified": False,
        "reference": {
            "catalogue_id": "raven_642d0d164af0a5d4076e77933c549a5d",
            "instance_guid": VEITHURGARD_INSTANCE_GUID,
            "script_guid": VEITHURGARD_SCRIPT_GUID,
            "parent_quest": VEITHURGARD_PARENT,
            "marker_uid": VEITHURGARD_UID,
        },
        "backup_count": len(backups),
        "backups": [],
    }

    lines = [
        "Completionist Map - read-only God of War backup forensics",
        f"Desktop: {desktop}",
        f"Active saves deliberately not scanned: {active}",
        f"Backup folders found: {len(backups)}",
        "",
    ]

    for backup in backups:
        try:
            backup.relative_to(active)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"Refusing active-save overlap: {backup}")

        files = sorted((p for p in backup.rglob("*") if p.is_file()), key=lambda p: relative_key(p, backup).lower())
        before = {relative_key(p, backup): sha256_file(p) for p in files}
        backup_entry = {
            "path": str(backup),
            "name": backup.name,
            "file_count": len(files),
            "files": [],
            "total_hits": 0,
            "source_hashes_unchanged": None,
        }
        lines.append(f"=== {backup.name} ===")
        lines.append(f"Path: {backup}")
        lines.append(f"Files: {len(files)}")

        for path in files:
            relative = relative_key(path, backup)
            data = path.read_bytes()
            hits = []
            for label, needle in search_patterns:
                offsets = find_all(data, needle)
                if offsets:
                    hits.append(
                        {
                            "pattern": label,
                            "needle_hex": needle.hex(),
                            "offsets": offsets,
                            "contexts": [printable_context(data, at) for at in offsets[:5]],
                        }
                    )
            entry = {
                "path": relative,
                "bytes": len(data),
                "sha256": before[relative],
                "magic_hex": data[:16].hex(),
                "entropy_first_1MiB": round(entropy_sample(data), 4),
                "hits": hits,
            }
            backup_entry["files"].append(entry)
            hit_count = sum(len(hit["offsets"]) for hit in hits)
            backup_entry["total_hits"] += hit_count
            if hit_count:
                lines.append(f"  HIT {relative}: {hit_count}")
                for hit in hits:
                    lines.append(f"    {hit['pattern']}: {hit['offsets']}")

        after = {relative_key(p, backup): sha256_file(p) for p in files}
        unchanged = before == after
        backup_entry["source_hashes_unchanged"] = unchanged
        if not unchanged:
            report["source_files_modified"] = True
            raise RuntimeError(f"Backup source hash changed during read-only scan: {backup}")
        lines.append(f"Total pattern hits: {backup_entry['total_hits']}")
        lines.append("Source hashes unchanged: true")
        lines.append("")
        report["backups"].append(backup_entry)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not backups:
        print("SAVE_BACKUP_SCAN_NO_CANDIDATE_FOLDERS")
        return 2
    print(f"SAVE_BACKUP_SCAN_COMPLETE backups={len(backups)}")
    for backup in report["backups"]:
        print(f"{backup['name']}: files={backup['file_count']} hits={backup['total_hits']}")
    print("active_save_opened=false source_files_modified=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
