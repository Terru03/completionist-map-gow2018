"""Inspect the stock permanent WAD DCB around CompassIconClass references.

Read-only v0.10.4 helper. The previous scan found every stock compass class hash
inside wad_r_perm.dcb but no standalone type-0x11E export. This tool narrows the
search to that file, maps hits to IFF chunks, compares the repeated class-hash
clusters and dumps aligned words around each occurrence so we can determine
whether a dedicated CompletionistRaven class can be authored safely.

It never writes inside the game directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_native_markers", HERE.parent / "v0.10.3" / "inspect-native-markers.py"
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

EXPECTED = "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039"

CLASSES = [
    "MAIN", "SIDE", "VendorLocation", "VendorLocationNoTrack", "FastTravel",
    "FastTravelNoTrack", "AreaEntrance", "FightLocation", "FightLocationNoTrack",
    "DockPoint", "ChiselLocation", "ChiselLocationNoTrack", "InfoOnly", "Valkyrie",
]
MAP_ICONS = [
    "goMapIconPrimaryQuest", "goMapIconSecondaryQuest", "goMapIconFastTravel",
    "goMapIconDock", "goMapIconVendor", "goMapIconAreaEntrance",
    "goMapIconFight_location", "goMapIconValkyrie_location", "goMapIconNoRender",
]
PRINTABLE = re.compile(rb"[ -~]{4,}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_all(blob: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    pos = 0
    while True:
        pos = blob.find(needle, pos)
        if pos < 0:
            return result
        result.append(pos)
        pos += 1


def parse_chunks(raw: bytes) -> list[dict]:
    chunks = []
    offset = 0
    index = 0
    while offset + 96 <= len(raw):
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        payload = offset + 96
        end = payload + size
        if end > len(raw):
            break
        chunks.append({
            "index": index,
            "header": offset,
            "kind": kind,
            "flags": flags,
            "size": size,
            "payload_start": payload,
            "payload_end": end,
        })
        index += 1
        offset = (end + 15) & ~15
    return chunks


def chunk_for(chunks: list[dict], offset: int) -> dict | None:
    for chunk in chunks:
        if chunk["payload_start"] <= offset < chunk["payload_end"]:
            return {
                "index": chunk["index"],
                "kind": chunk["kind"],
                "flags": chunk["flags"],
                "payload_offset": offset - chunk["payload_start"],
            }
    return None


def word_context(raw: bytes, hit: int, before: int = 32, after: int = 72) -> list[dict]:
    start = max(0, (hit - before) & ~7)
    end = min(len(raw), (hit + after + 7) & ~7)
    rows = []
    for at in range(start, end, 8):
        if at + 8 > len(raw):
            break
        value = struct.unpack_from("<Q", raw, at)[0]
        lo, hi = struct.unpack_from("<ff", raw, at)
        rows.append({
            "offset": at,
            "relative": at - hit,
            "u64": f"{value:016X}",
            "f32_lo": lo if abs(lo) < 1e20 else None,
            "f32_hi": hi if abs(hi) < 1e20 else None,
        })
    return rows


def nearby_strings(raw: bytes, hit: int, radius: int = 256) -> list[dict]:
    lo = max(0, hit - radius)
    hi = min(len(raw), hit + radius)
    out = []
    for match in PRINTABLE.finditer(raw, lo, hi):
        out.append({"offset": match.start(), "value": match.group().decode("ascii", "replace")})
    return out


def nearest_literal(literals: dict[str, list[int]], name: str, hit: int) -> dict | None:
    values = literals.get(name, [])
    if not values:
        return None
    at = min(values, key=lambda x: abs(x - hit))
    return {"offset": at, "delta": at - hit}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    source = game / "exec/dc/pc_le/wad_r_perm.dcb"
    if not source.is_file():
        raise FileNotFoundError(source)

    raw = source.read_bytes()
    digest = sha256(raw)
    if digest != EXPECTED:
        raise ValueError(f"Unexpected wad_r_perm.dcb SHA256: {digest}")

    chunks = parse_chunks(raw)
    literals = {name: find_all(raw, name.encode("ascii")) for name in CLASSES}
    class_hashes = {name: native.name_hash(name) for name in CLASSES}
    icon_hashes = {name: native.name_hash(name) for name in MAP_ICONS}

    occurrences = []
    all_class_hits = []
    for name in CLASSES:
        packed = struct.pack("<Q", class_hashes[name])
        hits = find_all(raw, packed)
        all_class_hits.extend((at, name) for at in hits)
        for ordinal, hit in enumerate(hits, 1):
            local_icons = []
            lo = max(0, hit - 128)
            hi = min(len(raw), hit + 128)
            window = raw[lo:hi]
            for icon_name, icon_hash in icon_hashes.items():
                needle = struct.pack("<Q", icon_hash)
                cursor = 0
                while True:
                    p = window.find(needle, cursor)
                    if p < 0:
                        break
                    local_icons.append({"name": icon_name, "offset": lo + p, "delta": lo + p - hit})
                    cursor = p + 1
            occurrences.append({
                "name": name,
                "hash": f"{class_hashes[name]:016X}",
                "ordinal": ordinal,
                "offset": hit,
                "chunk": chunk_for(chunks, hit),
                "nearest_same_name_literal": nearest_literal(literals, name, hit),
                "nearby_map_icon_hashes": local_icons,
                "words": word_context(raw, hit),
                "nearby_strings": nearby_strings(raw, hit),
            })

    # Cluster class-hash hits that sit close together. The first broad scan
    # showed a dense table near 0x230000 and a second set near the permanent
    # tweak data. This makes those patterns explicit without assuming layout.
    clusters = []
    for hit, name in sorted(all_class_hits):
        if not clusters or hit - clusters[-1]["last"] > 512:
            clusters.append({"first": hit, "last": hit, "hits": []})
        clusters[-1]["last"] = hit
        clusters[-1]["hits"].append({"offset": hit, "name": name, "hash": f"{class_hashes[name]:016X}"})
    for cluster in clusters:
        cluster["span"] = cluster["last"] - cluster["first"]
        cluster["unique_classes"] = sorted({row["name"] for row in cluster["hits"]})

    report = {
        "result": "READ_ONLY_WAD_R_PERM_COMPASS_LAYOUT",
        "game_files_written": False,
        "source": str(source),
        "sha256": digest,
        "bytes": len(raw),
        "chunk_count_parsed": len(chunks),
        "chunks": chunks,
        "class_hashes": {k: f"{v:016X}" for k, v in class_hashes.items()},
        "map_icon_hashes": {k: f"{v:016X}" for k, v in icon_hashes.items()},
        "literal_offsets": literals,
        "hash_clusters": clusters,
        "occurrences": occurrences,
        "notes": [
            "No game files were modified.",
            "Do not patch wad_r_perm.dcb from this report alone.",
            "A dedicated Raven class is only safe after the record/key layout is unambiguous and an offline rebuilt copy reparses/validates.",
        ],
    }

    out = args.output.resolve()
    if out.is_relative_to(game):
        raise ValueError("Output must stay outside the game directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved: {out}")
    print(f"Parsed IFF chunks: {len(chunks)}")
    print(f"Compass class hash occurrences: {len(occurrences)}")
    for cluster in clusters:
        if len(cluster["unique_classes"]) >= 4:
            print(
                f"  cluster 0x{cluster['first']:X}-0x{cluster['last']:X}: "
                f"{len(cluster['hits'])} hits / {len(cluster['unique_classes'])} classes"
            )


if __name__ == "__main__":
    main()
