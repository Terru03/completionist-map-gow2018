#!/usr/bin/env python3
"""Build and strictly reparse an OFFLINE Veithurgard Nornir native-data candidate.

This tool never writes the God of War directory. It starts from the frozen Raven
production native data, clones the proven Raven marker/coordinate grammar for a
single Nornir chest, and attaches that new coordinate to the topology-selected
stock helper. The temporary map visual remains the Raven visual on purpose: this
stage proves native data/routing only. Nornir class/art is a later gate.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "completionist_route_discovery", HERE / "discover-native-route-anchor.py"
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

RESULT = "OFFLINE_NORNIR_NATIVE_DATA_BUILT_AND_REPARSED"
NORNIR_NAME = "Completionist_V104_Veithurgard_NornirChest_01"
NORNIR_ID = native.name_hash(NORNIR_NAME)
EXPECTED_NORNIR_ID = 0x381B067F07254A25
RAVEN_ID = 0xE15E6BC82AE2773E
RAVEN_NAME = "Completionist_V103_Veithurgard_Raven_01"
RAVEN_ANCHOR = 0xBABC033C454755A0
NORNIR_ANCHOR = 0x45DE535858C63212
ROUTE_HELPER_TYPE = 0x62BDC63B4FBF649D
MIDGARD_REALM = 0x7CE593BC21393690
VEITHURGARD_REGION = 0xA1845BEF17F0E7BB
WAD = "WAD_Xpl200_Funeral"
EXPECTED = {
    "mapcoords.dcb": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
    "compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def align(blob: bytearray, boundary: int = 16) -> int:
    pad = (-len(blob)) % boundary
    if pad:
        blob.extend(b"\0" * pad)
    return len(blob)


def rebase_pointer(source: native.Dcb, source_field: int, blob: bytearray,
                   destination_field: int, relocations: set[int]) -> None:
    check(source_field in source.relocations, f"missing source relocation {source_field:#x}")
    (delta,) = source.unpack("<q", source_field)
    if delta == 0:
        new_delta = 0
    else:
        target = source_field + delta
        check(0 <= target < len(source.blob), "source pointer target outside data blob")
        new_delta = target - destination_field
    struct.pack_into("<q", blob, destination_field, new_delta)
    relocations.add(destination_field)


def replace_array_pointer(blob: bytearray, field: int, new_start: int, new_count: int) -> None:
    struct.pack_into("<q", blob, field, new_start - field)
    struct.pack_into("<I", blob, field + 8, new_count)


def rebuild_dcb(source: native.Dcb, new_blob: bytearray, relocations: set[int], output: Path) -> None:
    rel_payload = struct.pack(f"<I{len(relocations)}I", len(relocations), *sorted(relocations))
    replacements = {12: bytes(new_blob), 15: rel_payload}
    rebuilt = bytearray()
    raw = source.raw
    offset = 0
    while offset < len(raw):
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        check(flags == 0x10, f"unexpected DCB flags in {source.path.name}")
        header = bytearray(raw[offset:offset + 96])
        payload = raw[offset + 96:offset + 96 + size]
        if kind in replacements:
            payload = replacements[kind]
        struct.pack_into("<I", header, 4, len(payload))
        rebuilt.extend(header)
        rebuilt.extend(payload)
        rebuilt.extend(b"\0" * ((-len(rebuilt)) % 16))
        offset = (offset + 96 + size + 15) & ~15
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rebuilt)
    native.Dcb(output)


def iter_markers(master: native.Dcb):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            for marker in master.array(region + 0x38, 0x48):
                yield realm_id, region_id, region, marker


def canonical_marker_bytes(master: native.Dcb, marker: int) -> str:
    row = bytearray(master.blob[marker:marker + 0x48])
    row[0x08:0x10] = b"\0" * 8
    row[0x20:0x28] = b"\0" * 8
    return bytes(row).hex()


def marker_snapshot(master: native.Dcb) -> list[dict]:
    rows = []
    for realm_id, region_id, _region, marker in iter_markers(master):
        (uid,) = master.unpack("<Q", marker)
        rows.append({
            "realm": f"{realm_id:016X}",
            "region": f"{region_id:016X}",
            "id": f"{uid:016X}",
            "icon": master.string(marker + 8),
            "flags": [f"{master.unpack('<Q', f)[0]:016X}" for f in master.array(marker + 0x20, 8)],
            "canonical_record": canonical_marker_bytes(master, marker),
        })
    return rows


def canonical_coord_bytes(coords: native.Dcb, row: int) -> str:
    data = bytearray(coords.blob[row:row + 0x28])
    data[0x08:0x10] = b"\0" * 8
    return bytes(data).hex()


def coord_snapshot(coords: native.Dcb) -> list[dict]:
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    rows = []
    for off in coords.array(field, 0x28):
        (uid,) = coords.unpack("<Q", off)
        rows.append({
            "id": f"{uid:016X}",
            "wad": coords.string(off + 8),
            "position": list(coords.unpack("<3e", off + 0x10)),
            "canonical_record": canonical_coord_bytes(coords, off),
        })
    return rows


def graph_edges(graph: native.Dcb) -> list[tuple[int, int]]:
    field = graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E)
    return [graph.unpack("<QQ", off) for off in graph.array(field, 0x10)]


def find_single_raven_marker(master: native.Dcb):
    found = [(r, g, region, marker) for r, g, region, marker in iter_markers(master)
             if master.unpack("<Q", marker)[0] == RAVEN_ID]
    check(len(found) == 1, f"expected one frozen Raven map marker, found {len(found)}")
    realm_id, region_id, region, marker = found[0]
    check(realm_id == MIDGARD_REALM and region_id == VEITHURGARD_REGION,
          "frozen Raven marker is no longer in Veithurgard")
    check(master.string(marker + 8) == "goMapIconCompletionistRaven",
          "frozen Raven map visual changed")
    return region, marker


def patch_mapmaster(master: native.Dcb):
    check(all(master.unpack("<Q", m)[0] != NORNIR_ID for *_x, m in iter_markers(master)),
          "Nornir candidate ID already exists in mapmaster")
    region, raven_marker = find_single_raven_marker(master)
    marker_field = region + 0x38
    old_rows = list(master.array(marker_field, 0x48))
    check(raven_marker in old_rows, "Raven marker is not in target region array")

    blob = bytearray(master.blob)
    relocs = set(master.relocations)
    new_start = align(blob)
    blob.extend(master.blob[old_rows[0]:old_rows[0] + len(old_rows) * 0x48])
    blob.extend(master.blob[raven_marker:raven_marker + 0x48])

    for index, source_row in enumerate(old_rows):
        dest = new_start + index * 0x48
        rebase_pointer(master, source_row + 0x08, blob, dest + 0x08, relocs)
        rebase_pointer(master, source_row + 0x20, blob, dest + 0x20, relocs)

    new_row = new_start + len(old_rows) * 0x48
    rebase_pointer(master, raven_marker + 0x08, blob, new_row + 0x08, relocs)
    rebase_pointer(master, raven_marker + 0x20, blob, new_row + 0x20, relocs)
    struct.pack_into("<Q", blob, new_row, NORNIR_ID)
    replace_array_pointer(blob, marker_field, new_start, len(old_rows) + 1)
    check(marker_field in relocs, "target marker-array relocation missing")
    return blob, relocs, {
        "old_region_marker_count": len(old_rows),
        "new_region_marker_count": len(old_rows) + 1,
        "template": RAVEN_NAME,
        "temporary_map_visual": "goMapIconCompletionistRaven",
        "temporary_visual_is_runtime_shippable": False,
    }


def find_raven_coord(coords: native.Dcb) -> int:
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    found = [off for off in coords.array(field, 0x28) if coords.unpack("<Q", off)[0] == RAVEN_ID]
    check(len(found) == 1, f"expected one frozen Raven map coordinate, found {len(found)}")
    check(coords.string(found[0] + 8) == WAD, "frozen Raven coordinate WAD changed")
    return found[0]


def patch_mapcoords(coords: native.Dcb, position: tuple[float, float, float]):
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    old_rows = list(coords.array(field, 0x28))
    check(all(coords.unpack("<Q", r)[0] != NORNIR_ID for r in old_rows),
          "Nornir candidate ID already exists in mapcoords")
    raven_row = find_raven_coord(coords)

    blob = bytearray(coords.blob)
    relocs = set(coords.relocations)
    new_start = align(blob)
    blob.extend(coords.blob[old_rows[0]:old_rows[0] + len(old_rows) * 0x28])
    blob.extend(coords.blob[raven_row:raven_row + 0x28])
    for index, source_row in enumerate(old_rows):
        dest = new_start + index * 0x28
        rebase_pointer(coords, source_row + 8, blob, dest + 8, relocs)
    new_row = new_start + len(old_rows) * 0x28
    rebase_pointer(coords, raven_row + 8, blob, new_row + 8, relocs)
    struct.pack_into("<Q", blob, new_row, NORNIR_ID)
    struct.pack_into("<3e", blob, new_row + 0x10, *position)
    replace_array_pointer(blob, field, new_start, len(old_rows) + 1)
    check(field in relocs, "mapcoords root relocation missing")
    authored = struct.unpack("<3e", struct.pack("<3e", *position))
    return blob, relocs, {
        "old_count": len(old_rows),
        "new_count": len(old_rows) + 1,
        "template": RAVEN_NAME,
        "wad": WAD,
        "requested_position": list(position),
        "authored_half_position": list(authored),
        "quantization_error_metres": round(math.dist(authored, position), 6),
    }


def component(adjacency: dict[int, set[int]], start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in adjacency.get(cur, set()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def validate_selected_anchor(coords: native.Dcb, graph: native.Dcb, position: tuple[float, float, float]) -> dict:
    helpers = native.read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    positions = native.read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    edges = graph_edges(graph)
    check(NORNIR_ANCHOR in helpers, "selected Nornir anchor is not a helper")
    h = helpers[NORNIR_ANCHOR]
    check(h["wad"] == WAD, "selected Nornir anchor is in the wrong WAD")
    check(int(h["helper_type"], 16) == ROUTE_HELPER_TYPE, "selected Nornir anchor helper type changed")
    check((RAVEN_ID, RAVEN_ANCHOR) in edges, "runtime-proven Raven graph edge is missing")

    adjacency: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    check(len(adjacency[NORNIR_ANCHOR]) == 4, "selected Nornir anchor degree changed")
    raven_comp = component(adjacency, RAVEN_ANCHOR)
    check(NORNIR_ANCHOR in raven_comp, "selected Nornir anchor left the Raven graph component")
    check(any(node in positions for node in component(adjacency, NORNIR_ANCHOR)),
          "selected Nornir anchor component has no stock/native map coordinate")
    return {
        "id": f"{NORNIR_ANCHOR:016X}",
        "helper_type": f"{ROUTE_HELPER_TYPE:016X}",
        "wad": h["wad"],
        "position": h["position"],
        "distance_to_chest_metres": round(math.dist(h["position"], position), 4),
        "degree_before_authored_edge": len(adjacency[NORNIR_ANCHOR]),
        "same_component_as_runtime_proven_raven_anchor": True,
    }


def patch_compassgraph(graph: native.Dcb):
    field = graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E)
    old_rows = list(graph.array(field, 0x10))
    pairs = [graph.unpack("<QQ", off) for off in old_rows]
    check(not any(NORNIR_ID in pair for pair in pairs), "Nornir candidate ID already exists in graph")
    blob = bytearray(graph.blob)
    relocs = set(graph.relocations)
    new_start = align(blob)
    blob.extend(graph.blob[old_rows[0]:old_rows[0] + len(old_rows) * 0x10])
    blob.extend(struct.pack("<QQ", NORNIR_ID, NORNIR_ANCHOR))
    replace_array_pointer(blob, field, new_start, len(old_rows) + 1)
    check(field in relocs, "compass edge-array relocation missing")
    return blob, relocs, {"old_edge_count": len(old_rows), "new_edge_count": len(old_rows) + 1,
                          "edge": [f"{NORNIR_ID:016X}", f"{NORNIR_ANCHOR:016X}"]}


def get_position(observed: Path) -> tuple[float, float, float]:
    j = json.loads(observed.read_text(encoding="utf-8"))
    check(j.get("realm") == "Midgard" and j.get("region") == "Veithurgard",
          "observed Nornir source is not the Veithurgard chest")
    world = j["chest"]["world"]
    return float(world["x"]), float(world["y"]), float(world["z"])


def verify_candidate(source_master: native.Dcb, source_coords: native.Dcb, source_graph: native.Dcb,
                     master: native.Dcb, coords: native.Dcb, graph: native.Dcb,
                     requested_position: tuple[float, float, float]) -> dict:
    source_markers = marker_snapshot(source_master)
    candidate_markers = marker_snapshot(master)
    new_marker_rows = [r for r in candidate_markers if r["id"] == f"{NORNIR_ID:016X}"]
    check(len(new_marker_rows) == 1, f"candidate has {len(new_marker_rows)} Nornir map markers")
    check(new_marker_rows[0]["realm"] == f"{MIDGARD_REALM:016X}" and
          new_marker_rows[0]["region"] == f"{VEITHURGARD_REGION:016X}", "Nornir marker landed in wrong region")
    check(new_marker_rows[0]["icon"] == "goMapIconCompletionistRaven", "route-only marker template changed unexpectedly")
    filtered_markers = [r for r in candidate_markers if r["id"] != f"{NORNIR_ID:016X}"]
    check(filtered_markers == source_markers, "one or more pre-existing map markers changed semantically")

    source_coords_rows = coord_snapshot(source_coords)
    candidate_coords_rows = coord_snapshot(coords)
    new_coord = [r for r in candidate_coords_rows if r["id"] == f"{NORNIR_ID:016X}"]
    check(len(new_coord) == 1, f"candidate has {len(new_coord)} Nornir coordinate rows")
    check(new_coord[0]["wad"] == WAD, "Nornir coordinate WAD mismatch")
    authored = struct.unpack("<3e", struct.pack("<3e", *requested_position))
    check(tuple(new_coord[0]["position"]) == tuple(authored), "Nornir coordinate position mismatch")
    filtered_coords = [r for r in candidate_coords_rows if r["id"] != f"{NORNIR_ID:016X}"]
    check(filtered_coords == source_coords_rows, "one or more pre-existing map coordinates changed semantically")

    source_edges = graph_edges(source_graph)
    candidate_edges = graph_edges(graph)
    check(candidate_edges == source_edges + [(NORNIR_ID, NORNIR_ANCHOR)],
          "candidate compass graph is not source graph plus exactly one Nornir edge")
    source_helpers = native.read_positions(source_graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    candidate_helpers = native.read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    check(candidate_helpers == source_helpers, "pre-existing compass helpers changed")

    all_nodes = set(native.read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)) | set(candidate_helpers)
    unresolved = sorted({uid for pair in candidate_edges for uid in pair if uid not in all_nodes})
    check(not unresolved, f"candidate graph has unresolved endpoints: {unresolved}")
    return {
        "preexisting_map_markers_semantically_identical": True,
        "preexisting_mapcoords_semantically_identical": True,
        "preexisting_compass_helpers_identical": True,
        "preexisting_compass_edges_identical_and_ordered": True,
        "runtime_proven_raven_edge_preserved": (RAVEN_ID, RAVEN_ANCHOR) in candidate_edges,
        "unresolved_graph_endpoints": 0,
        "new_marker": new_marker_rows[0],
        "new_coordinate": new_coord[0],
        "new_edge": [f"{NORNIR_ID:016X}", f"{NORNIR_ANCHOR:016X}"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    ap.add_argument("--repo-root", type=Path, default=HERE.parents[1])
    ap.add_argument("--observed", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    check(NORNIR_ID == EXPECTED_NORNIR_ID, f"unexpected deterministic Nornir ID {NORNIR_ID:016X}")
    game_root = args.game_root.resolve()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    check(not output_dir.is_relative_to(game_root) and not report_path.is_relative_to(game_root),
          "offline output/report must stay outside the game directory")
    source_dir = game_root / "exec/dc/pc_le"
    source_paths = {name: source_dir / name for name in ("mapmaster.dcb", "mapcoords.dcb", "compassgraph.dcb")}
    for path in source_paths.values():
        check(path.is_file(), f"missing source DCB: {path}")
    check(sha256(source_paths["mapcoords.dcb"]) == EXPECTED["mapcoords.dcb"], "mapcoords is not frozen Raven production data")
    check(sha256(source_paths["compassgraph.dcb"]) == EXPECTED["compassgraph.dcb"], "compassgraph is not frozen Raven production data")

    before_hashes = {name: sha256(path) for name, path in source_paths.items()}
    master = native.Dcb(source_paths["mapmaster.dcb"])
    coords = native.Dcb(source_paths["mapcoords.dcb"])
    graph = native.Dcb(source_paths["compassgraph.dcb"])
    position = get_position(args.observed.resolve())
    anchor_meta = validate_selected_anchor(coords, graph, position)

    if output_dir.exists():
        check(not output_dir.is_relative_to(repo_root / ".git"), "refusing to remove a Git metadata path")
        shutil.rmtree(output_dir)
    candidate_root = output_dir / "game-root"
    candidate_dir = candidate_root / "exec/dc/pc_le"

    master_blob, master_relocs, master_meta = patch_mapmaster(master)
    coords_blob, coords_relocs, coords_meta = patch_mapcoords(coords, position)
    graph_blob, graph_relocs, graph_meta = patch_compassgraph(graph)
    outputs = {name: candidate_dir / name for name in source_paths}
    rebuild_dcb(master, master_blob, master_relocs, outputs["mapmaster.dcb"])
    rebuild_dcb(coords, coords_blob, coords_relocs, outputs["mapcoords.dcb"])
    rebuild_dcb(graph, graph_blob, graph_relocs, outputs["compassgraph.dcb"])

    candidate_master = native.Dcb(outputs["mapmaster.dcb"])
    candidate_coords = native.Dcb(outputs["mapcoords.dcb"])
    candidate_graph = native.Dcb(outputs["compassgraph.dcb"])
    verification = verify_candidate(master, coords, graph, candidate_master, candidate_coords, candidate_graph, position)

    after_hashes = {name: sha256(path) for name, path in source_paths.items()}
    check(after_hashes == before_hashes, "a source game DCB changed during offline build")

    report = {
        "result": RESULT,
        "candidate": {
            "name": NORNIR_NAME,
            "id": f"{NORNIR_ID:016X}",
            "family": "nornir_chest",
            "realm": f"{MIDGARD_REALM:016X}",
            "region": f"{VEITHURGARD_REGION:016X}",
            "wad": WAD,
            "world_position": list(position),
            "selected_graph_neighbor": f"{NORNIR_ANCHOR:016X}",
        },
        "selected_anchor": anchor_meta,
        "source_hashes_before": before_hashes,
        "source_hashes_after": after_hashes,
        "source_game_files_unchanged": before_hashes == after_hashes,
        "mapmaster_patch": master_meta,
        "mapcoords_patch": coords_meta,
        "compassgraph_patch": graph_meta,
        "reparse_verification": verification,
        "generated_files": {name: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                            for name, path in outputs.items()},
        "game_files_written": False,
        "saves_progression_marker_state_written": False,
        "runtime_install_performed": False,
        "runtime_ready": False,
        "temporary_raven_map_visual_reused_for_native_data_proof_only": True,
        "next_gate": "Build dedicated Nornir map/HUD/in-world resources and CompletionistNornirChest class, then combine with this native-data candidate offline before any runtime install."
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("OFFLINE_NORNIR_NATIVE_DATA_BUILT")
    print(f"  marker: {NORNIR_NAME}")
    print(f"  id: {NORNIR_ID:016X}")
    print(f"  position: {position}")
    print(f"  graph neighbour: {NORNIR_ANCHOR:016X}")
    print(f"  anchor type: {ROUTE_HELPER_TYPE:016X}")
    print(f"  anchor distance: {anchor_meta['distance_to_chest_metres']}m")
    print("  Raven marker/coordinate/edge preserved: true")
    print("  all pre-existing native records preserved semantically: true")
    print("  temporary map visual: goMapIconCompletionistRaven (offline proof only)")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  report: {report_path}")
    print("NORNIR_NATIVE_DATA_OFFLINE_GATE_PASSED")


if __name__ == "__main__":
    main()
