"""Read native DCB marker/route data. Never writes game files or binary dumps."""

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct

RAVEN = (-64.850898742676, 12.987384796143, 787.30694580078)
RAVEN_NAME = "Completionist_V103_Veithurgard_Raven_01"
WAD = "WAD_Xpl200_Funeral"


def name_hash(name):
    """64-bit case-folded hash loop observed in this executable."""
    value = 0
    for byte in name.upper().encode("ascii"):
        value = ((value + byte) * 0x401) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 6
    return value


class Dcb:
    def __init__(self, path):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.chunks = {}
        offset = 0
        while offset < len(self.raw):
            if offset + 96 > len(self.raw):
                raise ValueError("Truncated IFF header")
            kind, flags, size = struct.unpack_from("<HHI", self.raw, offset)
            end = offset + 96 + size
            if flags != 0x10 or kind in self.chunks or end > len(self.raw):
                raise ValueError("Invalid DCB chunk")
            self.chunks[kind] = (offset + 96, self.raw[offset + 96:end])
            offset = (end + 15) & ~15
        if offset != len(self.raw) or set(self.chunks) != {11, 12, 13, 14, 15}:
            raise ValueError("Unsupported DCB layout")
        self.file_base, self.blob = self.chunks[12]
        rel = self.chunks[15][1]
        count = struct.unpack_from("<I", rel)[0]
        if len(rel) != 4 + count * 4:
            raise ValueError("Invalid relocation count")
        self.relocations = set(struct.unpack_from(f"<{count}I", rel, 4))
        if len(self.relocations) != count:
            raise ValueError("Duplicate relocation")
        for field in self.relocations:
            self.pointer(field)
        exports = self.chunks[13][1]
        count = struct.unpack_from("<I", exports)[0]
        self.exports = {}
        for i in range(count):
            root, type_id, string_offset, uid = struct.unpack_from("<IIQQ", exports, 8 + i * 24)
            name = exports[string_offset:exports.index(0, string_offset)].decode("ascii")
            if name_hash(name) != uid:
                raise ValueError("Export hash mismatch")
            self.exports[name] = (root, type_id)

    def unpack(self, fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(self.blob):
            raise ValueError("DCB read outside data chunk")
        return struct.unpack_from(fmt, self.blob, offset)

    def pointer(self, field):
        if field not in self.relocations:
            raise ValueError(f"Missing relocation at {field:#x}")
        delta, = self.unpack("<q", field)
        target = field + delta
        if not 0 <= target < len(self.blob):
            raise ValueError("Relative pointer outside data chunk")
        return target

    def array(self, field, stride):
        count, = self.unpack("<I", field + 8)
        if count == 0:
            return []
        start = self.pointer(field)
        self.unpack(f"<{count * stride}s", start)
        return range(start, start + count * stride, stride)

    def string(self, field):
        delta, = self.unpack("<q", field)
        if delta == 0:
            return ""
        start = self.pointer(field)
        return self.blob[start:self.blob.index(0, start)].decode("ascii")

    def root(self, name, expected_type):
        root, type_id = self.exports[name]
        if type_id != expected_type:
            raise ValueError("Unexpected exported type")
        return root

    def inventory(self):
        return {"file": self.path.name, "bytes": len(self.raw),
                "sha256": hashlib.sha256(self.raw).hexdigest(),
                "relocations": len(self.relocations), "exports": self.exports}


def read_positions(dcb, export, type_id, helpers=False):
    records = {}
    for offset in dcb.array(dcb.root(export, type_id), 0x28):
        uid, = dcb.unpack("<Q", offset)
        if uid in records:
            raise ValueError("Duplicate coordinate/helper ID")
        xyz = dcb.unpack("<3e", offset + 0x10)
        if not all(math.isfinite(x) for x in xyz):
            raise ValueError("Nonfinite coordinate")
        record = {"id": f"{uid:016X}", "file_offset": f"0x{dcb.file_base + offset:X}",
                  "wad": dcb.string(offset + 8), "position": xyz,
                  "advance_radius_multiplier": dcb.unpack("<f", offset + 0x1C if not helpers else offset + 0x20)[0],
                  "fuzz_radius": dcb.unpack("<f", offset + 0x20 if not helpers else offset + 0x24)[0]}
        if helpers:
            record["helper_type"] = f"{dcb.unpack('<Q', offset + 0x18)[0]:016X}"
        else:
            record["forward"] = dcb.unpack("<3e", offset + 0x16)
            record["in_world_marker_distance"] = dcb.unpack("<f", offset + 0x24)[0]
        records[uid] = record
    return records


def inspect(game_root):
    root = Path(game_root) / "exec/dc/pc_le"
    master, coords, graph = [Dcb(root / f"{name}.dcb") for name in ("mapmaster", "mapcoords", "compassgraph")]
    positions = read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    helpers = read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    edges = [graph.unpack("<QQ", off) for off in graph.array(graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E), 0x10)]
    markers = collections.defaultdict(list)
    realms = []
    for realm in master.array(master.root("MAP_PERM_DATA", 0x415) + 0x10, 0x40):
        realm_id, = master.unpack("<Q", realm)
        regions = master.array(realm + 0x30, 0x68)
        marker_count = 0
        for region in regions:
            region_id, = master.unpack("<Q", region)
            for off in master.array(region + 0x38, 0x48):
                uid, = master.unpack("<Q", off)
                marker_count += 1
                flags = [f"{master.unpack('<Q', f)[0]:016X}" for f in master.array(off + 0x20, 8)]
                markers[uid].append({"realm": f"{realm_id:016X}", "region": f"{region_id:016X}",
                                     "file_offset": f"0x{master.file_base + off:X}", "icon": master.string(off + 8),
                                     "init_state": master.unpack("<B", off + 0x1C)[0], "flags": flags})
        realms.append({"id": f"{realm_id:016X}", "regions": len(regions), "markers": marker_count})
    nodes = set(positions) | set(helpers)
    missing = sorted({uid for edge in edges for uid in edge} - nodes)
    if missing:
        raise ValueError(f"{len(missing)} graph endpoints lack coordinate/helper records")
    links = collections.defaultdict(set)
    for a, b in edges:
        links[a].add(b)
        links[b].add(a)

    def nearby(records, limit=6):
        result = []
        for uid, record in records.items():
            if record["wad"] != WAD:
                continue
            result.append({**record, "straight_line_metres_for_research": round(math.dist(record["position"], RAVEN), 4),
                           "edge_neighbours": [f"{v:016X}" for v in sorted(links[uid])],
                           "map_records": markers.get(uid, [])})
        return sorted(result, key=lambda x: x["straight_line_metres_for_research"])[:limit]

    candidate = name_hash(RAVEN_NAME)
    return {"result": "PARTIAL_SUCCESS_STATIC_EVIDENCE_ONLY", "game_files_written": False,
            "files": [d.inventory() for d in (master, coords, graph)], "realms": realms,
            "counts": {"map_records": sum(x["markers"] for x in realms), "unique_map_ids": len(markers),
                       "coordinates": len(positions), "helpers": len(helpers), "edges": len(edges),
                       "unresolved_graph_endpoints": len(missing)},
            "raven": {"name": RAVEN_NAME, "hash_hex": f"{candidate:016X}", "world_position": RAVEN,
                      "authored_half_position": struct.unpack("<3e", struct.pack("<3e", *RAVEN)),
                      "id_collision": candidate in nodes or candidate in markers,
                      "nearest_helpers_are_candidates_not_verified_routes": True},
            "nearest_map_coordinates": nearby(positions), "nearest_helpers": nearby(helpers),
            "previous_crash_carrier": {"id": "2895F8500B9BD28E", "coordinates": positions[2924516555722838670],
                                       "map_records": markers[2924516555722838670],
                                       "edge_neighbours": [f"{v:016X}" for v in sorted(links[2924516555722838670])]},
            "next_gate": "Verify new ID, coordinate join, compass node and graph edges before any ShowMarker; no stock mutation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(args.game_root)
    if args.output:
        output = args.output.resolve()
        if output.is_relative_to(args.game_root.resolve()):
            raise ValueError("Report must stay outside game directory")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"NATIVE_MARKER_INFO report={output}")
    print("NATIVE_MARKER_INFO " + json.dumps(report["counts"]))
    print("NATIVE_MARKER_CREATE attempted=false id=" + report["raven"]["hash_hex"])


if __name__ == "__main__":
    main()
