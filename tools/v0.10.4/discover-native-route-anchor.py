"""Read-only discovery of stock native compass-route anchors around an observed world position."""

import argparse
import collections
import hashlib
import json
import math
import struct
from pathlib import Path

KNOWN_COMPLETIONIST_IDS = {0xE15E6BC82AE2773E}


def name_hash(name: str) -> int:
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


class Dcb:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.chunks = {}
        offset = 0
        while offset < len(self.raw):
            if offset + 96 > len(self.raw):
                raise ValueError(f"Truncated IFF header in {self.path.name}")
            kind, flags, size = struct.unpack_from("<HHI", self.raw, offset)
            end = offset + 96 + size
            if flags != 0x10 or kind in self.chunks or end > len(self.raw):
                raise ValueError(f"Invalid DCB chunk in {self.path.name}")
            self.chunks[kind] = (offset + 96, self.raw[offset + 96:end])
            offset = (end + 15) & ~15
        if offset != len(self.raw) or set(self.chunks) != {11, 12, 13, 14, 15}:
            raise ValueError(f"Unsupported DCB layout in {self.path.name}")
        self.file_base, self.blob = self.chunks[12]
        rel = self.chunks[15][1]
        count = struct.unpack_from("<I", rel)[0]
        if len(rel) != 4 + count * 4:
            raise ValueError(f"Invalid relocation table in {self.path.name}")
        self.relocations = set(struct.unpack_from(f"<{count}I", rel, 4))
        if len(self.relocations) != count:
            raise ValueError(f"Duplicate relocation in {self.path.name}")
        for field in self.relocations:
            self.pointer(field)
        exports = self.chunks[13][1]
        count = struct.unpack_from("<I", exports)[0]
        self.exports = {}
        for i in range(count):
            root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", exports, 8 + i * 24)
            name = exports[string_offset:exports.index(0, string_offset)].decode("ascii")
            if name_hash(name) != uid:
                raise ValueError(f"Export hash mismatch in {self.path.name}: {name}")
            self.exports[name] = (root, type_id)

    def unpack(self, fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(self.blob):
            raise ValueError(f"Read outside data chunk in {self.path.name}")
        return struct.unpack_from(fmt, self.blob, offset)

    def pointer(self, field):
        if field not in self.relocations:
            raise ValueError(f"Missing relocation at {field:#x} in {self.path.name}")
        (delta,) = self.unpack("<q", field)
        target = field + delta
        if not 0 <= target < len(self.blob):
            raise ValueError(f"Relative pointer outside data chunk in {self.path.name}")
        return target

    def array(self, field, stride):
        (count,) = self.unpack("<I", field + 8)
        if count == 0:
            return []
        start = self.pointer(field)
        self.unpack(f"<{count * stride}s", start)
        return range(start, start + count * stride, stride)

    def string(self, field):
        (delta,) = self.unpack("<q", field)
        if delta == 0:
            return ""
        start = self.pointer(field)
        return self.blob[start:self.blob.index(0, start)].decode("ascii")

    def root(self, name, expected_type):
        root, type_id = self.exports[name]
        if type_id != expected_type:
            raise ValueError(f"Unexpected type for {name} in {self.path.name}")
        return root

    def inventory(self):
        return {
            "file": self.path.name,
            "bytes": len(self.raw),
            "sha256": hashlib.sha256(self.raw).hexdigest(),
            "relocations": len(self.relocations),
            "exports": sorted(self.exports),
        }


def read_positions(dcb, export, type_id, helpers=False):
    records = {}
    for offset in dcb.array(dcb.root(export, type_id), 0x28):
        (uid,) = dcb.unpack("<Q", offset)
        if uid in records:
            raise ValueError("Duplicate coordinate/helper ID")
        xyz = dcb.unpack("<3e", offset + 0x10)
        if not all(math.isfinite(v) for v in xyz):
            raise ValueError("Nonfinite coordinate")
        record = {
            "id": f"{uid:016X}",
            "wad": dcb.string(offset + 8),
            "position": list(xyz),
            "file_offset": f"0x{dcb.file_base + offset:X}",
        }
        if helpers:
            record["helper_type"] = f"{dcb.unpack('<Q', offset + 0x18)[0]:016X}"
            record["advance_radius_multiplier"] = dcb.unpack("<f", offset + 0x20)[0]
            record["fuzz_radius"] = dcb.unpack("<f", offset + 0x24)[0]
        else:
            record["forward"] = list(dcb.unpack("<3e", offset + 0x16))
            record["advance_radius_multiplier"] = dcb.unpack("<f", offset + 0x1C)[0]
            record["fuzz_radius"] = dcb.unpack("<f", offset + 0x20)[0]
            record["in_world_marker_distance"] = dcb.unpack("<f", offset + 0x24)[0]
        records[uid] = record
    return records


def read_map_records(master):
    records = collections.defaultdict(list)
    for realm in master.array(master.root("MAP_PERM_DATA", 0x415) + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            for off in master.array(region + 0x38, 0x48):
                (uid,) = master.unpack("<Q", off)
                records[uid].append({
                    "realm": f"{realm_id:016X}",
                    "region": f"{region_id:016X}",
                    "icon": master.string(off + 8),
                    "init_state": master.unpack("<B", off + 0x1C)[0],
                    "file_offset": f"0x{master.file_base + off:X}",
                })
    return records


def get_target(observed_path: Path, selector: str):
    data = json.loads(observed_path.read_text(encoding="utf-8"))
    if selector == "chest":
        world = data["chest"]["world"]
        label = f"{data.get('region', 'unknown')} Nornir chest"
    elif selector.startswith("key:"):
        index = int(selector.split(":", 1)[1])
        key = next(k for k in data["chest"]["keys"] if int(k["index"]) == index)
        world = key["world"]
        label = f"{data.get('region', 'unknown')} Nornir key {index}"
    else:
        raise ValueError("selector must be 'chest' or 'key:N'")
    return label, (float(world["x"]), float(world["y"]), float(world["z"])), data


def discover(game_root: Path, observed_path: Path, selector: str, limit: int):
    dc_root = game_root / "exec/dc/pc_le"
    master = Dcb(dc_root / "mapmaster.dcb")
    coords = Dcb(dc_root / "mapcoords.dcb")
    graph = Dcb(dc_root / "compassgraph.dcb")
    positions = read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    helpers = read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    map_records = read_map_records(master)
    edges = [graph.unpack("<QQ", off) for off in graph.array(graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E), 0x10)]
    links = collections.defaultdict(set)
    for a, b in edges:
        links[a].add(b)
        links[b].add(a)

    label, target, observed = get_target(observed_path, selector)

    def rank(records, kind):
        ranked = []
        for uid, record in records.items():
            if uid in KNOWN_COMPLETIONIST_IDS:
                continue
            distance = math.dist(record["position"], target)
            ranked.append({
                **record,
                "kind": kind,
                "straight_line_metres_for_research": round(distance, 4),
                "edge_neighbours": [f"{v:016X}" for v in sorted(links[uid])],
                "map_records": map_records.get(uid, []),
                "stock_candidate": True,
            })
        return sorted(ranked, key=lambda x: x["straight_line_metres_for_research"])[:limit]

    nearest_coords = rank(positions, "map_coordinate")
    nearest_helpers = rank(helpers, "helper")
    merged = sorted(nearest_coords + nearest_helpers, key=lambda x: x["straight_line_metres_for_research"])

    wad_summary = {}
    for item in merged[: max(limit, 8)]:
        wad = item["wad"] or "<empty>"
        row = wad_summary.setdefault(wad, {"wad": wad, "nearest_distance": item["straight_line_metres_for_research"], "candidate_count": 0})
        row["candidate_count"] += 1
        row["nearest_distance"] = min(row["nearest_distance"], item["straight_line_metres_for_research"])

    return {
        "result": "NATIVE_ROUTE_ANCHOR_DISCOVERY_READ_ONLY",
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "source_observation": str(observed_path),
        "selector": selector,
        "target": {
            "label": label,
            "world_position": list(target),
            "realm_name": observed.get("realm"),
            "region_name": observed.get("region"),
        },
        "files": [d.inventory() for d in (master, coords, graph)],
        "counts": {
            "coordinates": len(positions),
            "helpers": len(helpers),
            "edges": len(edges),
            "map_ids": len(map_records),
        },
        "known_completionist_ids_excluded": [f"{v:016X}" for v in sorted(KNOWN_COMPLETIONIST_IDS)],
        "nearest_stock_map_coordinates": nearest_coords,
        "nearest_stock_helpers": nearest_helpers,
        "candidate_wads_by_proximity": sorted(wad_summary.values(), key=lambda x: (x["nearest_distance"], -x["candidate_count"])),
        "next_gate": "Choose a stock route neighbour/WAD only after reviewing this report. No Nornir marker, class, art, mapcoords or compassgraph mutation has been attempted.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--selector", default="chest")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit < 3 or args.limit > 50:
        raise ValueError("--limit must be between 3 and 50")
    game_root = args.game_root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(game_root):
        raise ValueError("Report must stay outside the game directory")
    report = discover(game_root, args.observed.resolve(), args.selector, args.limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("NATIVE_ROUTE_ANCHOR_DISCOVERY_READ_ONLY")
    print(f"  target: {report['target']['label']} {report['target']['world_position']}")
    print(f"  coordinates: {report['counts']['coordinates']} helpers: {report['counts']['helpers']} edges: {report['counts']['edges']}")
    for i, item in enumerate(report["nearest_stock_map_coordinates"][:5], 1):
        print(f"  coord#{i}: {item['id']} {item['straight_line_metres_for_research']}m wad={item['wad']} neighbours={','.join(item['edge_neighbours']) or '-'}")
    for i, item in enumerate(report["nearest_stock_helpers"][:5], 1):
        print(f"  helper#{i}: {item['id']} {item['straight_line_metres_for_research']}m wad={item['wad']} neighbours={','.join(item['edge_neighbours']) or '-'}")
    print("  game files written: false")
    print(f"  report: {output}")


if __name__ == "__main__":
    main()
