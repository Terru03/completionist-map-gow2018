"""List stock map-marker icon names and usage counts from mapmaster.dcb.

Read-only v0.10.4 helper used to find visual carriers that are not shared with
boat docks. It reuses the validated v0.10.3 DCB reader and never writes game
files.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V103 = HERE.parent / "v0.10.3" / "inspect-native-markers.py"
SPEC = importlib.util.spec_from_file_location("completionist_native_markers", V103)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)


def iter_markers(master: native.Dcb):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            for marker in master.array(region + 0x38, 0x48):
                yield realm_id, region_id, marker


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--game-root",
        type=Path,
        default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"),
    )
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    game = args.game_root.resolve()
    master_path = game / "exec/dc/pc_le/mapmaster.dcb"
    master = native.Dcb(master_path)

    counts: collections.Counter[str] = collections.Counter()
    realms: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    examples: dict[str, list[dict[str, str | int]]] = collections.defaultdict(list)

    for realm_id, region_id, marker in iter_markers(master):
        icon = master.string(marker + 8)
        counts[icon] += 1
        realm_hex = f"{realm_id:016X}"
        realms[realm_hex][icon] += 1
        if len(examples[icon]) < 8:
            marker_id = master.unpack("<Q", marker)[0]
            examples[icon].append(
                {
                    "id": f"{marker_id:016X}",
                    "realm": realm_hex,
                    "region": f"{region_id:016X}",
                    "init_state": master.unpack("<B", marker + 0x1C)[0],
                }
            )

    report = {
        "result": "READ_ONLY_MAP_ICON_USAGE_SCAN",
        "game_files_written": False,
        "total_records": sum(counts.values()),
        "icon_counts": dict(sorted(counts.items(), key=lambda kv: (kv[1], kv[0]))),
        "per_realm_counts": {
            realm: dict(sorted(counter.items())) for realm, counter in sorted(realms.items())
        },
        "examples": {icon: rows for icon, rows in sorted(examples.items())},
    }

    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Saved: {out}")
    else:
        print(text, end="")

    print("Stock map icon usage:")
    for icon, count in sorted(counts.items(), key=lambda kv: (kv[1], kv[0])):
        print(f"  {count:4d}  {icon}")


if __name__ == "__main__":
    main()
