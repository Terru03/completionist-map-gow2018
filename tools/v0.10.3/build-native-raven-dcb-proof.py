"""Build an OFFLINE Raven-only native DCB proof. Never modifies the game directory.

The proof clones the three small authored data files into repo/build, adds one
Completionist marker, one matching map-coordinate record, and one graph edge,
then reparses the generated files with the v0.10.3 reader. It is intentionally
NOT an installer and never calls Compass.ShowMarker.
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
    "completionist_native_markers", HERE / "inspect-native-markers.py"
)
native = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(native)

RAVEN_NAME = native.RAVEN_NAME
RAVEN_ID = native.name_hash(RAVEN_NAME)
RAVEN = native.RAVEN
RAVEN_WAD = native.WAD
MIDGARD_REALM = 0x7CE593BC21393690
VEITHURGARD_REGION = 0xA1845BEF17F0E7BB

EXPECTED = {
    "mapmaster.dcb": "aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0",
    "mapcoords.dcb": "5d0b7591032d7b56581a0d77946c3fad4f0cbc1b9d245f3578407177c40bbe7d",
    "compassgraph.dcb": "c2fa6bab0c7c1dbe413a41f477a5e01ab396731fc6f6d611047a8bd346a56c5e",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def align(blob: bytearray, boundary: int = 16) -> int:
    pad = (-len(blob)) % boundary
    if pad:
        blob.extend(b"\0" * pad)
    return len(blob)


def rebase_pointer(
    source: native.Dcb,
    source_field: int,
    destination_blob: bytearray,
    destination_field: int,
    relocations: set[int],
) -> None:
    """Copy one serialized self-relative pointer to a new field location."""
    if source_field not in source.relocations:
        raise ValueError(f"Expected relocation at source field {source_field:#x}")
    (delta,) = source.unpack("<q", source_field)
    if delta == 0:
        new_delta = 0
    else:
        target = source_field + delta
        if not 0 <= target < len(source.blob):
            raise ValueError("Source pointer target outside data blob")
        new_delta = target - destination_field
    struct.pack_into("<q", destination_blob, destination_field, new_delta)
    relocations.add(destination_field)


def replace_array_pointer(blob: bytearray, field: int, new_start: int, new_count: int) -> None:
    struct.pack_into("<q", blob, field, new_start - field)
    struct.pack_into("<I", blob, field + 8, new_count)


def rebuild_dcb(source: native.Dcb, new_blob: bytearray, relocations: set[int], output: Path) -> None:
    relocation_payload = struct.pack(
        f"<I{len(relocations)}I", len(relocations), *sorted(relocations)
    )
    replacements = {12: bytes(new_blob), 15: relocation_payload}

    raw = source.raw
    rebuilt = bytearray()
    offset = 0
    while offset < len(raw):
        kind, flags, size = struct.unpack_from("<HHI", raw, offset)
        header = bytearray(raw[offset : offset + 96])
        payload = raw[offset + 96 : offset + 96 + size]
        if kind in replacements:
            payload = replacements[kind]
        struct.pack_into("<I", header, 4, len(payload))
        rebuilt.extend(header)
        rebuilt.extend(payload)
        rebuilt.extend(b"\0" * ((-len(rebuilt)) % 16))
        offset = (offset + 96 + size + 15) & ~15

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rebuilt)
    # Fail immediately if the generated file no longer satisfies our strict reader.
    native.Dcb(output)


def iter_markers(master: native.Dcb):
    root = master.root("MAP_PERM_DATA", 0x415)
    for realm in master.array(root + 0x10, 0x40):
        (realm_id,) = master.unpack("<Q", realm)
        for region in master.array(realm + 0x30, 0x68):
            (region_id,) = master.unpack("<Q", region)
            marker_field = region + 0x38
            for marker in master.array(marker_field, 0x48):
                yield realm_id, region_id, region, marker


def find_target_region(master: native.Dcb) -> int:
    regions = {
        region
        for realm_id, region_id, region, _ in iter_markers(master)
        if realm_id == MIDGARD_REALM and region_id == VEITHURGARD_REGION
    }
    if len(regions) != 1:
        raise ValueError(f"Expected one Veithurgard region record, found {len(regions)}")
    return next(iter(regions))


def choose_dock_template(master: native.Dcb):
    preferred = []
    fallback = []
    for realm_id, region_id, _region, marker in iter_markers(master):
        if master.string(marker + 8) != "goMapIconDock":
            continue
        entry = (realm_id, region_id, marker)
        if realm_id == MIDGARD_REALM and region_id == VEITHURGARD_REGION:
            preferred.append(entry)
        elif realm_id == MIDGARD_REALM:
            fallback.append(entry)
    choices = preferred or fallback
    if not choices:
        raise ValueError("No Midgard goMapIconDock marker available as a non-mutated template")
    return choices[0]


def patch_mapmaster(master: native.Dcb):
    if any(master.unpack("<Q", marker)[0] == RAVEN_ID for *_prefix, marker in iter_markers(master)):
        raise ValueError("Reserved Raven ID already exists in stock mapmaster")

    target_region = find_target_region(master)
    marker_field = target_region + 0x38
    old_offsets = list(master.array(marker_field, 0x48))
    if not old_offsets:
        raise ValueError("Target region unexpectedly has no markers")

    template_realm, template_region, template = choose_dock_template(master)
    template_flags = list(master.array(template + 0x20, 8))
    if not template_flags:
        raise ValueError("Dock template has no marker flags")

    blob = bytearray(master.blob)
    relocs = set(master.relocations)
    new_start = align(blob, 16)
    blob.extend(master.blob[old_offsets[0] : old_offsets[0] + len(old_offsets) * 0x48])
    blob.extend(master.blob[template : template + 0x48])

    for index, source_marker in enumerate(old_offsets):
        dest_marker = new_start + index * 0x48
        for relative in (0x08, 0x20):
            rebase_pointer(master, source_marker + relative, blob, dest_marker + relative, relocs)

    new_marker = new_start + len(old_offsets) * 0x48
    for relative in (0x08, 0x20):
        rebase_pointer(master, template + relative, blob, new_marker + relative, relocs)

    # Independent marker identity. Reuse only stock DockPoint icon/flag references.
    # No stock record is changed, and FastTravel is explicitly cleared.
    struct.pack_into("<Q", blob, new_marker + 0x00, RAVEN_ID)
    struct.pack_into("<I", blob, new_marker + 0x10, 0)  # LamsName
    struct.pack_into("<I", blob, new_marker + 0x14, 0)  # LamsDescription
    struct.pack_into("<f", blob, new_marker + 0x18, 0.0)  # HeightOffset
    struct.pack_into("<B", blob, new_marker + 0x1C, 1)  # discovered for proof copy only
    struct.pack_into("<Q", blob, new_marker + 0x30, 0)  # never a fast-travel destination
    struct.pack_into("<f", blob, new_marker + 0x40, 0.0)
    struct.pack_into("<f", blob, new_marker + 0x44, 0.0)

    replace_array_pointer(blob, marker_field, new_start, len(old_offsets) + 1)
    if marker_field not in relocs:
        raise ValueError("Target region marker-array field lost its stock relocation")

    return blob, relocs, {
        "realm": f"{MIDGARD_REALM:016X}",
        "region": f"{VEITHURGARD_REGION:016X}",
        "old_region_marker_count": len(old_offsets),
        "new_region_marker_count": len(old_offsets) + 1,
        "template_realm": f"{template_realm:016X}",
        "template_region": f"{template_region:016X}",
        "template_offset": f"0x{master.file_base + template:X}",
        "template_icon": master.string(template + 8),
        "template_flags": [f"{master.unpack('<Q', f)[0]:016X}" for f in template_flags],
    }


def choose_coordinate_template(coords: native.Dcb):
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    candidates = []
    for off in coords.array(field, 0x28):
        if coords.string(off + 8) != RAVEN_WAD:
            continue
        xyz = coords.unpack("<3e", off + 0x10)
        candidates.append((math.dist(xyz, RAVEN), off, xyz))
    if not candidates:
        raise ValueError(f"No coordinate record in {RAVEN_WAD}")
    return min(candidates)


def patch_mapcoords(coords: native.Dcb):
    field = coords.root("MAP_COORDS_PERM_DATA", 0x40A)
    old_offsets = list(coords.array(field, 0x28))
    if any(coords.unpack("<Q", off)[0] == RAVEN_ID for off in old_offsets):
        raise ValueError("Reserved Raven ID already exists in stock mapcoords")

    template_distance, template, template_xyz = choose_coordinate_template(coords)
    blob = bytearray(coords.blob)
    relocs = set(coords.relocations)
    new_start = align(blob, 16)
    blob.extend(coords.blob[old_offsets[0] : old_offsets[0] + len(old_offsets) * 0x28])
    blob.extend(coords.blob[template : template + 0x28])

    for index, source_row in enumerate(old_offsets):
        destination = new_start + index * 0x28
        rebase_pointer(coords, source_row + 8, blob, destination + 8, relocs)

    new_row = new_start + len(old_offsets) * 0x28
    rebase_pointer(coords, template + 8, blob, new_row + 8, relocs)
    struct.pack_into("<Q", blob, new_row, RAVEN_ID)
    struct.pack_into("<3e", blob, new_row + 0x10, *RAVEN)
    struct.pack_into("<f", blob, new_row + 0x1C, 1.0)
    struct.pack_into("<f", blob, new_row + 0x20, -1.0)
    struct.pack_into("<f", blob, new_row + 0x24, 0.0)

    replace_array_pointer(blob, field, new_start, len(old_offsets) + 1)
    if field not in relocs:
        raise ValueError("MapCoords root array field lost its stock relocation")

    authored = struct.unpack("<3e", struct.pack("<3e", *RAVEN))
    return blob, relocs, {
        "old_count": len(old_offsets),
        "new_count": len(old_offsets) + 1,
        "template_offset": f"0x{coords.file_base + template:X}",
        "template_position": template_xyz,
        "template_distance_metres": round(template_distance, 4),
        "authored_position": authored,
        "quantization_error_metres": round(math.dist(authored, RAVEN), 6),
        "wad": RAVEN_WAD,
    }


def choose_connected_helper(coords: native.Dcb, graph: native.Dcb):
    positions = native.read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    helpers = native.read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True)
    edge_root = graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E)
    edges = [graph.unpack("<QQ", off) for off in graph.array(edge_root, 0x10)]
    adjacency = collections.defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)

    def component(start):
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for nxt in adjacency[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    candidates = []
    for uid, record in helpers.items():
        if record["wad"] != RAVEN_WAD or not adjacency[uid]:
            continue
        comp = component(uid)
        same_wad_map_nodes = [
            node for node in comp if node in positions and positions[node]["wad"] == RAVEN_WAD
        ]
        if not same_wad_map_nodes:
            continue
        candidates.append(
            (
                math.dist(record["position"], RAVEN),
                uid,
                record,
                len(comp),
                same_wad_map_nodes,
            )
        )
    if not candidates:
        raise ValueError("No nearby helper connected to a native map coordinate in Raven WAD")
    return min(candidates)


def patch_compassgraph(coords: native.Dcb, graph: native.Dcb):
    distance, helper_id, helper, component_size, same_wad_nodes = choose_connected_helper(coords, graph)
    edge_field = graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E)
    old_edges = list(graph.array(edge_field, 0x10))
    pairs = [graph.unpack("<QQ", off) for off in old_edges]
    if any(RAVEN_ID in pair for pair in pairs):
        raise ValueError("Reserved Raven ID unexpectedly appears in stock compass graph")

    blob = bytearray(graph.blob)
    relocs = set(graph.relocations)
    new_start = align(blob, 16)
    blob.extend(graph.blob[old_edges[0] : old_edges[0] + len(old_edges) * 0x10])
    blob.extend(struct.pack("<QQ", RAVEN_ID, helper_id))
    replace_array_pointer(blob, edge_field, new_start, len(old_edges) + 1)
    if edge_field not in relocs:
        raise ValueError("Compass edge root array field lost its stock relocation")

    return blob, relocs, {
        "old_edge_count": len(old_edges),
        "new_edge_count": len(old_edges) + 1,
        "helper_id": f"{helper_id:016X}",
        "helper_position": helper["position"],
        "helper_distance_metres": round(distance, 4),
        "helper_original_degree": len([1 for a, b in pairs if a == helper_id or b == helper_id]),
        "original_component_size": component_size,
        "same_wad_native_map_nodes_in_component": len(same_wad_nodes),
        "attachment_is_authored_test_hypothesis_not_reachability_proof": True,
    }


def verify_candidate(master: native.Dcb, coords: native.Dcb, graph: native.Dcb, helper_hex: str):
    marker_rows = []
    for realm_id, region_id, _region, marker in iter_markers(master):
        if master.unpack("<Q", marker)[0] == RAVEN_ID:
            marker_rows.append(
                {
                    "realm": f"{realm_id:016X}",
                    "region": f"{region_id:016X}",
                    "icon": master.string(marker + 8),
                    "init_state": master.unpack("<B", marker + 0x1C)[0],
                    "fast_travel": f"{master.unpack('<Q', marker + 0x30)[0]:016X}",
                    "flags": [
                        f"{master.unpack('<Q', f)[0]:016X}"
                        for f in master.array(marker + 0x20, 8)
                    ],
                }
            )
    positions = native.read_positions(coords, "MAP_COORDS_PERM_DATA", 0x40A)
    edge_field = graph.root("COMPASS_GRAPH_EDGE_PERM_DATA", 0x40E)
    edges = [graph.unpack("<QQ", off) for off in graph.array(edge_field, 0x10)]
    helper_id = int(helper_hex, 16)
    matching_edges = [pair for pair in edges if RAVEN_ID in pair]

    if len(marker_rows) != 1:
        raise ValueError(f"Patched mapmaster has {len(marker_rows)} Raven records")
    if marker_rows[0]["realm"] != f"{MIDGARD_REALM:016X}" or marker_rows[0]["region"] != f"{VEITHURGARD_REGION:016X}":
        raise ValueError("Raven marker landed in wrong realm/region")
    if RAVEN_ID not in positions:
        raise ValueError("Patched mapcoords lacks Raven ID")
    if positions[RAVEN_ID]["wad"] != RAVEN_WAD:
        raise ValueError("Raven coordinate has wrong WAD")
    if matching_edges != [(RAVEN_ID, helper_id)]:
        raise ValueError(f"Unexpected Raven graph edges: {matching_edges!r}")

    all_nodes = set(positions) | set(native.read_positions(graph, "COMPASS_HELPER_PERM_DATA", 0x40C, True))
    unresolved = {uid for pair in edges for uid in pair if uid not in all_nodes}
    if unresolved:
        raise ValueError("Patched graph contains unresolved endpoints")

    return {
        "marker": marker_rows[0],
        "coordinate": positions[RAVEN_ID],
        "edge": [f"{RAVEN_ID:016X}", f"{helper_id:016X}"],
        "unresolved_graph_endpoints": 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--repo-root", type=Path, default=HERE.parents[1])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    game_root = args.game_root.resolve()
    repo_root = args.repo_root.resolve()
    source_dir = game_root / "exec/dc/pc_le"
    build_root = repo_root / "build/v0.10.3-dcb-proof/game-root"
    build_dir = build_root / "exec/dc/pc_le"
    report_path = args.output.resolve() if args.output else repo_root / "archive/field-logs/completionist-v103-dcb-build.json"

    if build_root.is_relative_to(game_root) or report_path.is_relative_to(game_root):
        raise ValueError("Build/report paths must stay outside the game directory")

    originals = {name: source_dir / name for name in EXPECTED}
    before = {}
    for name, path in originals.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256(path)
        if digest != EXPECTED[name]:
            raise ValueError(f"{name} hash differs from researched build")
        before[name] = digest

    if build_root.exists():
        shutil.rmtree(build_root)
    build_dir.mkdir(parents=True)

    master = native.Dcb(originals["mapmaster.dcb"])
    coords = native.Dcb(originals["mapcoords.dcb"])
    graph = native.Dcb(originals["compassgraph.dcb"])

    master_blob, master_relocs, marker_meta = patch_mapmaster(master)
    coords_blob, coords_relocs, coord_meta = patch_mapcoords(coords)
    graph_blob, graph_relocs, graph_meta = patch_compassgraph(coords, graph)

    outputs = {
        "mapmaster.dcb": build_dir / "mapmaster.dcb",
        "mapcoords.dcb": build_dir / "mapcoords.dcb",
        "compassgraph.dcb": build_dir / "compassgraph.dcb",
    }
    rebuild_dcb(master, master_blob, master_relocs, outputs["mapmaster.dcb"])
    rebuild_dcb(coords, coords_blob, coords_relocs, outputs["mapcoords.dcb"])
    rebuild_dcb(graph, graph_blob, graph_relocs, outputs["compassgraph.dcb"])

    patched_master = native.Dcb(outputs["mapmaster.dcb"])
    patched_coords = native.Dcb(outputs["mapcoords.dcb"])
    patched_graph = native.Dcb(outputs["compassgraph.dcb"])
    proof = verify_candidate(patched_master, patched_coords, patched_graph, graph_meta["helper_id"])

    after = {name: sha256(path) for name, path in originals.items()}
    if after != before:
        raise RuntimeError("A source game DCB changed during offline build")

    stock_counts = native.inspect(game_root)["counts"]
    patched_counts = native.inspect(build_root)["counts"]
    expected_counts = {
        "map_records": stock_counts["map_records"] + 1,
        "unique_map_ids": stock_counts["unique_map_ids"] + 1,
        "coordinates": stock_counts["coordinates"] + 1,
        "helpers": stock_counts["helpers"],
        "edges": stock_counts["edges"] + 1,
        "unresolved_graph_endpoints": 0,
    }
    if patched_counts != expected_counts:
        raise ValueError(f"Patched count mismatch: {patched_counts!r} != {expected_counts!r}")

    report = {
        "result": "OFFLINE_DCB_PROOF_BUILT_AND_REPARSED",
        "game_files_written": False,
        "compass_show_called": False,
        "save_files_written": False,
        "candidate": {"name": RAVEN_NAME, "id": f"{RAVEN_ID:016X}", "world_position": RAVEN},
        "stock_source_hashes_unchanged": after == before,
        "stock_counts": stock_counts,
        "patched_counts": patched_counts,
        "mapmaster_patch": marker_meta,
        "mapcoords_patch": coord_meta,
        "compassgraph_patch": graph_meta,
        "reparse_verification": proof,
        "generated_files": {
            name: {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in outputs.items()
        },
        "installation_status": "NOT_INSTALLED",
        "next_gate": (
            "Do not copy these files into the game yet. First review save/state semantics and choose a reversible "
            "load/override strategy; then use a Raven-only runtime test with no stock marker mutation."
        ),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"NATIVE_MARKER_CREATE offline_build=true id={RAVEN_ID:016X}")
    print(f"NATIVE_MARKER_INFO report={report_path}")
    print(f"NATIVE_MARKER_INFO build={build_root}")
    print("NATIVE_COMPASS_RESULT show_attempted=false installed=false game_files_written=false")


if __name__ == "__main__":
    main()
