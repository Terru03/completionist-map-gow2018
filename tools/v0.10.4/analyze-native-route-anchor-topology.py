"""Compare native-route helper candidates with the runtime-proven Raven graph anchor. Read-only."""

import argparse
import collections
import hashlib
import json
import math
import struct
from pathlib import Path

RAVEN_ID = 0xE15E6BC82AE2773E
RAVEN_ANCHOR = 0xBABC033C454755A0


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

    @property
    def sha256(self):
        return hashlib.sha256(self.raw).hexdigest()


def read_positions(dcb: Dcb, export: str, type_id: int, helpers=False):
    records = {}
    for offset in dcb.array(dcb.root(export, type_id), 0x28):
        (uid,) = dcb.unpack("<Q", offset)
        xyz = dcb.unpack("<3e", offset + 0x10)
        record = {
            "id": f"{uid:016X}",
            "wad": dcb.string(offset + 8),
            "position": list(xyz),
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


def component(start, links):
    seen = {start}
    queue = collections.deque([start])
    while queue:
        node = queue.popleft()
        for other in links[node]:
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return seen


def nearest_stock_coordinate_steps(start, links, positions):
    seen = {start}
    queue = collections.deque([(start, 0)])
    hits = []
    best_steps = None
    while queue:
        node, steps = queue.popleft()
        if best_steps is not None and steps > best_steps:
            break
        if node in positions and node != RAVEN_ID and node != start:
            best_steps = steps
            hits.append(node)
            continue
        for other in links[node]:
            if other not in seen:
                seen.add(other)
                queue.append((other, steps + 1))
    return best_steps, sorted(hits)


def analyze(game_root: Path, discovery_path: Path):
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    if discovery.get("result") != "NATIVE_ROUTE_ANCHOR_DISCOVERY_READ_ONLY":
        raise ValueError("Input is not a native-route discovery report")

    dc_root = game_root / "exec/dc/pc_le"
    coords = Dcb(dc_root / "mapcoords.dcb")
    graph = Dcb(dc_root / "compassgraph.dcb")

    expected = {row["file"]: row["sha256"] for row in discovery.get("files", [])}
    if expected.get("mapcoords.dcb") and expected["mapcoords.dcb"] != coords.sha256:
        raise ValueError("mapcoords.dcb changed since discovery")
    if expected.get("compassgraph.dcb") and expected["compassgraph.dcb"] != graph.sha256:
        raise ValueError("compassgraph.dcb changed since discovery")

    positions = read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    helpers = read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    edges = [graph.unpack("<QQ", off) for off in graph.array(graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E), 0x10)]
    links = collections.defaultdict(set)
    edge_set = set()
    for a, b in edges:
        links[a].add(b)
        links[b].add(a)
        edge_set.add(tuple(sorted((a, b))))

    if RAVEN_ID not in positions:
        raise ValueError("Frozen Raven marker coordinate is missing")
    if tuple(sorted((RAVEN_ID, RAVEN_ANCHOR))) not in edge_set:
        raise ValueError("Frozen Raven graph edge is missing")
    if RAVEN_ANCHOR not in helpers and RAVEN_ANCHOR not in positions:
        raise ValueError("Frozen Raven anchor is not a known graph node")

    target = tuple(float(v) for v in discovery["target"]["world_position"])
    raven_anchor_record = helpers.get(RAVEN_ANCHOR) or positions[RAVEN_ANCHOR]
    raven_anchor_kind = "helper" if RAVEN_ANCHOR in helpers else "map_coordinate"
    raven_component = component(RAVEN_ANCHOR, links)
    raven_helper_type = raven_anchor_record.get("helper_type")

    def node_kind(uid):
        if uid in helpers:
            return "helper"
        if uid in positions:
            return "map_coordinate"
        return "unresolved"

    def neighbour_summary(uid):
        record = helpers.get(uid) or positions.get(uid)
        row = {"id": f"{uid:016X}", "kind": node_kind(uid)}
        if record:
            row["wad"] = record["wad"]
            row["position"] = record["position"]
            row["distance_to_target_m"] = round(math.dist(record["position"], target), 4)
            if uid in helpers:
                row["helper_type"] = record["helper_type"]
        return row

    candidate_rows = []
    for source in discovery.get("nearest_stock_helpers", []):
        uid = int(source["id"], 16)
        if uid not in helpers:
            raise ValueError(f"Discovery helper is no longer present: {source['id']}")
        record = helpers[uid]
        steps, coordinate_hits = nearest_stock_coordinate_steps(uid, links, positions)
        row = {
            "id": source["id"],
            "wad": record["wad"],
            "position": record["position"],
            "distance_to_target_m": round(math.dist(record["position"], target), 4),
            "helper_type": record["helper_type"],
            "same_helper_type_as_raven_anchor": bool(raven_helper_type and record["helper_type"] == raven_helper_type),
            "same_graph_component_as_raven_anchor": uid in raven_component,
            "degree": len(links[uid]),
            "stock_map_coordinate_neighbours": [f"{v:016X}" for v in sorted(links[uid]) if v in positions and v != RAVEN_ID],
            "nearest_stock_map_coordinate_graph_steps": steps,
            "nearest_stock_map_coordinates_at_that_depth": [f"{v:016X}" for v in coordinate_hits],
            "neighbours": [neighbour_summary(v) for v in sorted(links[uid])],
        }
        candidate_rows.append(row)

    candidate_rows.sort(key=lambda row: (
        not row["same_helper_type_as_raven_anchor"],
        not row["same_graph_component_as_raven_anchor"],
        row["distance_to_target_m"],
        row["id"],
    ))

    same_type = [row for row in candidate_rows if row["same_helper_type_as_raven_anchor"]]
    provisional = same_type[0]["id"] if same_type else None

    raven_steps, raven_coordinate_hits = nearest_stock_coordinate_steps(RAVEN_ANCHOR, links, positions)
    return {
        "result": "NATIVE_ROUTE_ANCHOR_TOPOLOGY_READ_ONLY",
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "discovery_report": str(discovery_path),
        "validated_file_hashes": {
            "mapcoords.dcb": coords.sha256,
            "compassgraph.dcb": graph.sha256,
        },
        "target": discovery["target"],
        "runtime_proven_raven_reference": {
            "marker_id": f"{RAVEN_ID:016X}",
            "anchor_id": f"{RAVEN_ANCHOR:016X}",
            "edge_verified": True,
            "anchor_kind": raven_anchor_kind,
            "anchor_wad": raven_anchor_record["wad"],
            "anchor_position": raven_anchor_record["position"],
            "anchor_distance_from_raven_marker_m": round(math.dist(raven_anchor_record["position"], positions[RAVEN_ID]["position"]), 4),
            "anchor_helper_type": raven_helper_type,
            "anchor_degree": len(links[RAVEN_ANCHOR]),
            "nearest_stock_map_coordinate_graph_steps": raven_steps,
            "nearest_stock_map_coordinates_at_that_depth": [f"{v:016X}" for v in raven_coordinate_hits],
            "neighbours": [neighbour_summary(v) for v in sorted(links[RAVEN_ANCHOR])],
        },
        "candidate_ranking": candidate_rows,
        "provisional_same-type_nearest_candidate": provisional,
        "selection_status": "TOPOLOGY_EVIDENCE_ONLY_NOT_RUNTIME_PROOF",
        "next_gate": "Select a Nornir graph neighbour only after reviewing helper type, local graph shape and Raven-anchor compatibility. Do not mutate Raven production files during this analysis.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    game_root = args.game_root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(game_root):
        raise ValueError("Report must stay outside the game directory")
    report = analyze(game_root, args.discovery.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    ref = report["runtime_proven_raven_reference"]
    print("NATIVE_ROUTE_ANCHOR_TOPOLOGY_READ_ONLY")
    print(f"  Raven reference: marker={ref['marker_id']} anchor={ref['anchor_id']} kind={ref['anchor_kind']} type={ref['anchor_helper_type'] or '-'} degree={ref['anchor_degree']}")
    for index, row in enumerate(report["candidate_ranking"][:10], 1):
        print(
            f"  candidate#{index}: {row['id']} {row['distance_to_target_m']}m "
            f"type={row['helper_type']} sameRavenType={str(row['same_helper_type_as_raven_anchor']).lower()} "
            f"sameComponent={str(row['same_graph_component_as_raven_anchor']).lower()} degree={row['degree']} "
            f"stepsToStockCoord={row['nearest_stock_map_coordinate_graph_steps']}"
        )
    print(f"  provisional same-type nearest: {report['provisional_same-type_nearest_candidate'] or '-'}")
    print("  game files written: false")
    print(f"  report: {output}")


if __name__ == "__main__":
    main()
