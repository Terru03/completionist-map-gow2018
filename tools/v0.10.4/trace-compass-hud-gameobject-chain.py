"""Trace stock CompassIconClass HUD GameObject resource chains in r_ui.wad.

Read-only follow-up to the failed CompletionistRaven HUD IconName experiment.
Stock DockPoint.IconName resolves to ``goboatdock`` whereas the crashing test
pointed IconName at the map GameObject ``gomapiconcompletionistraven``.  This
probe follows exact 16-byte WAD resource-id references, sibling group links and
payload neighborhoods for every stock compass HUD GameObject so we can identify
the actual authored HUD contract before creating another runtime candidate.

No game, save, progression, marker-state, Lua, DCB or WAD file is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from collections import defaultdict, deque

EXPECTED_RUI = "9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3"
RESULT = "READ_ONLY_COMPASS_HUD_GAMEOBJECT_CHAIN"
ROOTS = {
    "MAIN": "gomainquest",
    "SIDE": "gosidequest",
    "VendorLocation": "govendor",
    "Valkyrie": "govalkyrie",
    "DockPoint": "goboatdock",
    "FastTravel": "gofasttravel",
    "AreaEntrance": "goentrance",
    "FightLocation": "gofightlocation",
}
INTERESTING_PREFIXES = ("tx_", "mat_", "mdl_", "mg_", "anm_", "goproto", "go")


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_wad_helper():
    path = Path(__file__).with_name("build-raven-ui-logical-clone.py")
    spec = importlib.util.spec_from_file_location("completionist_hud_chain_wad", path)
    check(spec is not None and spec.loader is not None, f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def type_rows(wadmod, records: list[dict]) -> list[dict]:
    payloads = wadmod.payload_records(records)
    check(len(payloads) >= 2, "r_ui.wad has no root/type table")
    return wadmod.read_type_table(bytes(payloads[1]["data"]))


def type_key_for(rows: list[dict], payload_index: int | None) -> str | None:
    if payload_index is None:
        return None
    hits = [r for r in rows if int(r["base"]) <= payload_index < int(r["base"]) + int(r["count"])]
    return None if len(hits) != 1 else f"0x{int(hits[0]['key']):X}"


def describe(records: list[dict], rows: list[dict], index: int) -> dict:
    r = records[index]
    off = r.get("original_offset")
    return {
        "record_index": index,
        "payload_index": r.get("payload_index"),
        "type_key": type_key_for(rows, r.get("payload_index")),
        "name": r["name"],
        "kind": int(r["kind"]),
        "flags": f"0x{int(r['flags']):X}",
        "bytes": len(r["data"]),
        "id": bytes(r["id"]).hex(),
        "parent_index": r.get("parent"),
        "file_offset": None if off is None else f"0x{int(off):X}",
    }


def definitions(records: list[dict]) -> dict[bytes, list[int]]:
    out: dict[bytes, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        if int(r["kind"]) == 1 and len(r["data"]):
            out[bytes(r["id"])].append(i)
    return out


def group_children(records: list[dict]) -> dict[int | None, list[int]]:
    out: dict[int | None, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        out[r.get("parent")].append(i)
    return out


def id_refs(data: bytes, known_ids: set[bytes]) -> list[dict]:
    found = []
    seen = set()
    # WAD resource references are exact 16-byte ids. Scan bytewise because some
    # authored structures are not naturally 16-byte aligned.
    for off in range(0, max(0, len(data) - 15)):
        value = data[off:off + 16]
        if value in known_ids and (off, value) not in seen:
            seen.add((off, value))
            found.append({"offset": f"0x{off:X}", "id": value.hex()})
    return found


def root_definition(records: list[dict], name: str) -> int:
    rows = [i for i, r in enumerate(records)
            if r["name"].lower() == name.lower() and int(r["kind"]) == 1 and len(r["data"])]
    check(len(rows) == 1, f"expected one data definition for {name}, found {len(rows)}")
    return rows[0]


def trace_root(records: list[dict], rows: list[dict], defs: dict[bytes, list[int]],
               children: dict[int | None, list[int]], root: int, max_depth: int = 6) -> dict:
    known = set(defs)
    queue = deque([(root, 0, "root", None)])
    best_depth: dict[int, int] = {}
    edges = []
    nodes = {}

    while queue:
        idx, depth, relation, source = queue.popleft()
        if depth > max_depth:
            continue
        old = best_depth.get(idx)
        if old is not None and old <= depth:
            if source is not None:
                edges.append({"from": source, "to": idx, "relation": relation, "depth": depth})
            continue
        best_depth[idx] = depth
        if source is not None:
            edges.append({"from": source, "to": idx, "relation": relation, "depth": depth})

        rec = records[idx]
        meta = describe(records, rows, idx)
        refs = id_refs(bytes(rec["data"]), known)
        meta["payload_id_refs"] = refs
        sibling_links = []
        parent = rec.get("parent")
        if parent is not None:
            for sib in children.get(parent, []):
                sr = records[sib]
                if sib == idx or int(sr["kind"]) != 1 or len(sr["data"]):
                    continue
                sid = bytes(sr["id"])
                targets = defs.get(sid, [])
                sibling_links.append({
                    "record_index": sib,
                    "name": sr["name"],
                    "id": sid.hex(),
                    "definition_targets": targets,
                })
                for target in targets:
                    queue.append((target, depth + 1, "zero_data_group_link", idx))
        meta["zero_data_group_links"] = sibling_links
        nodes[str(idx)] = meta

        for ref in refs:
            rid = bytes.fromhex(ref["id"])
            for target in defs.get(rid, []):
                # Self-id fields are common; retain the ref metadata but do not
                # waste traversal depth by re-queuing the same definition.
                if target != idx:
                    queue.append((target, depth + 1, f"payload_id_ref@{ref['offset']}", idx))

    interesting = []
    for key, node in nodes.items():
        lower = str(node["name"]).lower()
        if lower.startswith(INTERESTING_PREFIXES):
            interesting.append({"record_index": int(key), "name": node["name"],
                                "type_key": node["type_key"], "bytes": node["bytes"],
                                "id": node["id"]})
    interesting.sort(key=lambda x: (x["name"].lower(), x["record_index"]))

    return {
        "root": describe(records, rows, root),
        "reachable_definition_count": len(nodes),
        "nodes": nodes,
        "edges": edges,
        "interesting_resources": interesting,
    }


def payload_neighborhood(wadmod, records: list[dict], rows: list[dict], root: int, radius: int = 12) -> list[dict]:
    payloads = wadmod.payload_records(records)
    pidx = records[root].get("payload_index")
    check(pidx is not None, "root has no payload index")
    lo = max(0, int(pidx) - radius)
    hi = min(len(payloads), int(pidx) + radius + 1)
    index_by_identity = {id(r): i for i, r in enumerate(records)}
    out = []
    for pi in range(lo, hi):
        rec = payloads[pi]
        ri = index_by_identity[id(rec)]
        item = describe(records, rows, ri)
        item["delta_from_root_payload"] = pi - int(pidx)
        out.append(item)
    return out


def backlinks(records: list[dict], target_ids: set[bytes]) -> list[dict]:
    out = []
    for i, r in enumerate(records):
        data = bytes(r["data"])
        if not data:
            continue
        for target in target_ids:
            start = 0
            while True:
                pos = data.find(target, start)
                if pos < 0:
                    break
                out.append({"record_index": i, "name": r["name"], "target_id": target.hex(),
                            "payload_offset": f"0x{pos:X}"})
                start = pos + 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game = args.game_root.resolve()
    out = args.output.resolve()
    check(not out.is_relative_to(game), "report must stay outside game directory")
    wad_path = game / "exec/wad/pc_le/r_ui.wad"
    check(wad_path.is_file(), f"missing {wad_path}")
    raw = wad_path.read_bytes()
    digest = sha256_bytes(raw)
    check(digest == EXPECTED_RUI, f"r_ui.wad differs from proven Raven-map baseline: {digest}")

    wadmod = load_wad_helper()
    records = wadmod.parse_wad(raw)
    check(wadmod.serialize_wad(records) == raw, "r_ui.wad byte round-trip failed")
    rows = type_rows(wadmod, records)
    defs = definitions(records)
    children = group_children(records)

    traces = {}
    root_indices = {}
    for cls, name in ROOTS.items():
        root = root_definition(records, name)
        root_indices[cls] = root
        trace = trace_root(records, rows, defs, children, root)
        trace["payload_neighborhood"] = payload_neighborhood(wadmod, records, rows, root)
        traces[cls] = trace

    dock = traces["DockPoint"]
    dock_ids = {bytes.fromhex(node["id"]) for node in dock["nodes"].values()}
    dock_backlinks = backlinks(records, dock_ids)

    # Compare structural signatures rather than assuming all stock classes share
    # one prototype/layout. This tells the next builder which properties are HUD
    # contract and which are Dock-specific artwork/resources.
    signatures = {}
    for cls, trace in traces.items():
        root = trace["root"]
        signatures[cls] = {
            "root_type_key": root["type_key"],
            "root_flags": root["flags"],
            "root_bytes": root["bytes"],
            "reachable_definitions": trace["reachable_definition_count"],
            "interesting_names": [x["name"] for x in trace["interesting_resources"]],
            "root_payload_ref_offsets": [x["offset"] for x in trace["nodes"][str(root["record_index"])]["payload_id_refs"]],
            "root_zero_data_link_names": [x["name"] for x in trace["nodes"][str(root["record_index"])]["zero_data_group_links"]],
        }

    report = {
        "result": RESULT,
        "game_files_written": False,
        "save_state_written": False,
        "progression_state_written": False,
        "marker_state_written": False,
        "r_ui_wad_sha256": digest,
        "reason": (
            "DockPoint.IconName resolves to goboatdock. The crashing Raven test used the distinct map GameObject "
            "gomapiconcompletionistraven, so the compass HUD GameObject chain must be cloned independently."
        ),
        "roots": ROOTS,
        "structural_signatures": signatures,
        "traces": traces,
        "dock_reachable_id_backlinks": dock_backlinks,
        "conclusion": "STOCK_COMPASS_HUD_GAMEOBJECT_CHAIN_TRACED",
        "next_gate": (
            "Identify the smallest Dock-specific HUD resource subtree from goboatdock and its stock peer signatures. "
            "Only then build an offline Raven-only HUD GameObject clone and point CompletionistRaven.IconName at that new HUD hash. "
            "Do not reuse goMapIconCompletionistRaven, do not alter InWorld_tMPIcon_Name, and do not mutate goboatdock or real DockPoint resources."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    check(sha256_bytes(wad_path.read_bytes()) == digest, "r_ui.wad changed during read-only trace")
    print(RESULT)
    print(f"  r_ui.wad: {digest}")
    print(f"  stock HUD roots traced: {len(traces)}")
    print(f"  Dock reachable definitions: {dock['reachable_definition_count']}")
    print(f"  Dock interesting resources: {len(dock['interesting_resources'])}")
    print(f"  Dock backlinks: {len(dock_backlinks)}")
    print(f"  report: {out}")
    print("  game files written: false")


if __name__ == "__main__":
    main()
