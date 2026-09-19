#!/usr/bin/env python3
"""Read-only same-identity Raven state/context comparison across all GoW save-ring slots.

This probe combines two already-proven pieces of evidence:
1. exact 53-Raven save-side object hashes;
2. decoded ravenKilled custom-userdata carriers per slot.

For every Raven hash occurrence in each of the 20 aligned save-ring slots, it records
small byte contexts and whether that SAME slot's decoded carrier contains the SAME
Raven identity. The strongest evidence is a single catalogue identity observed in
multiple slots with carrier_absent -> carrier_present while its neighboring raw bytes
also change.

Absence from a carrier is NOT treated as proof of alive state. The report labels it
only as carrier_absent.

Read only. The active game.sav SHA-256 is verified unchanged after the scan.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENTITIES = REPO / "catalogue" / "odins-ravens-save-identities.json"
AUTHORITY = HERE / "probe-active-save-raven-ring-authority.py"
CONTEXT = 80
FOCUS = {
    "raven_642d0d164af0a5d4076e77933c549a5d",
    "raven_c945cb53465b58decfcbd4a221cb5326",
    "raven_e32f7bab42fd7298890f6aa56a734562",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_all(data: bytes, needle: bytes, limit: int = 64) -> list[int]:
    out = []
    start = 0
    while len(out) < limit:
        at = data.find(needle, start)
        if at < 0:
            break
        out.append(at)
        start = at + 1
    return out


def context(data: bytes, at: int, n: int) -> dict:
    lo = max(0, at - CONTEXT)
    hi = min(len(data), at + n + CONTEXT)
    raw = data[lo:hi]
    center = at - lo
    post = raw[center + n:center + n + 32]
    pre = raw[max(0, center - 32):center]
    return {
        "context_start": lo,
        "hash_offset_in_context": center,
        "context_hex": raw.hex(),
        "pre32_hex": pre.hex(),
        "post32_hex": post.hex(),
        "post8_hex": post[:8].hex(),
        "post16_hex": post[:16].hex(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-text", type=Path, required=True)
    args = ap.parse_args()

    root = args.save_root.expanduser().resolve()
    saves = sorted(p.resolve() for p in root.rglob("game.sav") if p.is_file())
    if len(saves) != 1:
        raise RuntimeError(f"expected exactly one active game.sav under {root}, found {len(saves)}")
    save = saves[0]

    identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    if identities.get("identity_count") != 53:
        raise RuntimeError("Raven identity catalogue is incomplete")
    registry_hash = int(identities["registry_hash_hex"], 16)
    rows = identities["identities"]
    by_hash = {int(r["object_hash_hex"], 16): r["catalogue_id"] for r in rows}
    hash_by_id = {r["catalogue_id"]: int(r["object_hash_hex"], 16) for r in rows}
    if len(by_hash) != 53:
        raise RuntimeError("Raven object hashes are not one-to-one")

    authority = load_module("raven_ring_authority_cross_slot", AUTHORITY)
    scanner = authority.load_module("gow_carrier_scan_cross_slot", HERE / "gow-custom-userdata-carrier-scan.py")
    parser = authority.load_module("gow_carrier_cross_slot", HERE / "gow-custom-userdata-carrier.py")

    before = sha256_file(save)
    blob = save.read_bytes()
    lay = authority.layout(blob)
    prefix = lay["global_prefix"]
    stride = lay["slot_stride"]

    slots = []
    headers = []
    occupied = []
    observations = []
    per_id = defaultdict(list)

    for idx in range(lay["slot_count"]):
        start = prefix + idx * stride
        slot = blob[start:start + stride]
        if len(slot) != stride:
            raise RuntimeError(f"slot {idx} extraction failed")
        headers.append(slot[:authority.HEADER_BYTES])
        carrier = authority.scan_slot(slot, idx, scanner, parser, by_hash, registry_hash)
        is_occupied = carrier["stream_count"] > 0
        if is_occupied:
            occupied.append(idx)
        killed = set(carrier["killed_raven_catalogue_ids"])

        slot_obs = []
        for identity in rows:
            cid = identity["catalogue_id"]
            needle = int(identity["object_hash_hex"], 16).to_bytes(8, "little")
            for at in find_all(slot, needle):
                obs = {
                    "slot_index": idx,
                    "catalogue_id": cid,
                    "object_hash_hex": identity["object_hash_hex"],
                    "slot_offset": at,
                    "carrier_state": "carrier_present" if cid in killed else "carrier_absent",
                    **context(slot, at, len(needle)),
                }
                observations.append(obs)
                slot_obs.append(obs)
                per_id[cid].append(obs)

        slots.append({
            "slot_index": idx,
            "occupied": is_occupied,
            "stream_count": carrier["stream_count"],
            "raven_stream_count": carrier["raven_stream_count"],
            "parsed_raven_carrier_count": carrier["parsed_raven_carrier_count"],
            "carrier_raven_ids": sorted(killed),
            "raw_raven_hash_occurrences": len(slot_obs),
            "raw_raven_ids": sorted({o["catalogue_id"] for o in slot_obs}),
        })

    header = authority.header_fields(headers, occupied)

    transitions = []
    for cid, obs_rows in sorted(per_id.items()):
        states = {o["carrier_state"] for o in obs_rows}
        post16 = {o["post16_hex"] for o in obs_rows}
        if len(states) > 1 or len(post16) > 1:
            transitions.append({
                "catalogue_id": cid,
                "observation_count": len(obs_rows),
                "carrier_states": sorted(states),
                "post16_variants": sorted(post16),
                "observations": obs_rows,
            })

    focus = {}
    for cid in sorted(FOCUS):
        focus[cid] = {
            "object_hash_hex": f"0x{hash_by_id[cid]:016X}",
            "observations": per_id.get(cid, []),
        }

    tag_by_carrier = defaultdict(Counter)
    for obs in observations:
        tag_by_carrier[obs["carrier_state"]][obs["post16_hex"]] += 1

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav changed during read-only cross-slot probe")

    report = {
        "schema": 1,
        "analysis": "same_identity_raven_cross_slot_context",
        "save_sha256": before,
        "layout": lay,
        "occupied_slots": occupied,
        "header_analysis": {
            "consensus_latest_slot": header.get("consensus_latest_slot"),
            "consensus_reason": header.get("consensus_reason"),
            "timestamp_fields": header.get("timestamp_fields", [])[:8],
        },
        "slots": slots,
        "observation_count": len(observations),
        "raven_ids_with_raw_occurrences": len(per_id),
        "same_identity_variant_count": len(transitions),
        "same_identity_variants": transitions,
        "focus": focus,
        "post16_counts_by_carrier_state": {
            state: dict(counter.most_common())
            for state, counter in sorted(tag_by_carrier.items())
        },
        "safety": {
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "Completionist Map - same-identity Raven cross-slot context probe",
        f"save_sha256={before}",
        f"occupied_slots={','.join(map(str, occupied))}",
        f"consensus_latest_slot={header.get('consensus_latest_slot')}",
        f"observations={len(observations)} raven_ids_with_raw={len(per_id)}",
        f"same_identity_variants={len(transitions)}",
        "",
        "FOCUS VEITHURGARD",
    ]
    for cid in sorted(FOCUS):
        obs_rows = per_id.get(cid, [])
        lines.append(f"{cid} observations={len(obs_rows)}")
        for o in obs_rows:
            lines.append(
                f"  slot={o['slot_index']} carrier={o['carrier_state']} "
                f"offset={o['slot_offset']} post16={o['post16_hex']}"
            )

    lines.extend(["", "SAME-IDENTITY VARIANTS"])
    for row in transitions:
        lines.append(
            f"{row['catalogue_id']} observations={row['observation_count']} "
            f"carrierStates={','.join(row['carrier_states'])} "
            f"post16Variants={len(row['post16_variants'])}"
        )
        for o in row["observations"]:
            lines.append(
                f"  slot={o['slot_index']} carrier={o['carrier_state']} "
                f"offset={o['slot_offset']} post16={o['post16_hex']}"
            )

    lines.extend([
        "",
        "POST16 TAG COUNTS BY CARRIER STATE",
    ])
    for state, counter in sorted(tag_by_carrier.items()):
        lines.append(state)
        for tag, count in counter.most_common(20):
            lines.append(f"  {count:4d} {tag}")

    lines.extend([
        "",
        "SAFETY active_save_opened_read_only=true source_hash_unchanged=true "
        "save_written=false progression_written=false game_process_opened=false game_files_written=false",
    ])
    args.output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        "RAVEN_SAME_IDENTITY_CROSS_SLOT_COMPLETE "
        f"observations={len(observations)} ids={len(per_id)} variants={len(transitions)} "
        f"latest={header.get('consensus_latest_slot')}"
    )
    for cid in sorted(FOCUS):
        obs_rows = per_id.get(cid, [])
        print(f"FOCUS {cid} observations={len(obs_rows)}")
        for o in obs_rows:
            print(
                f"  slot={o['slot_index']} carrier={o['carrier_state']} "
                f"post16={o['post16_hex']}"
            )
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
