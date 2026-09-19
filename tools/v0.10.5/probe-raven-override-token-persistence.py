#!/usr/bin/env python3
"""Read-only Raven override-token persistence probe.

Mines each of the 53 native Raven override records for per-instance candidates
that were NOT exhaustively covered by the solved GameObject identity scan:
- override/final/prototype/parent-prototype IDs;
- script GUID in RFC and Windows-memory order;
- game 64-bit hashes of native names, GUID text, parent quest and embedded strings;
- opaque aligned 8/16-byte values near the RegionSummary_*_Raven_Parent field.

All candidates are searched with an Aho-Corasick multi-pattern scanner in:
- the newest authoritative aligned save-ring slot;
- historical test slots 18 and 19 when occupied;
- every validated zlib stream in those slots.

This is presence evidence only. No candidate is called a killed/alive flag merely
because it occurs. Aggregate quest state is used only to annotate Raven rows as
definitely-killed, definitely-alive, or ambiguous for triage.

The active game.sav and native game data are read only. The save SHA-256 is
verified unchanged after analysis.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOGUE = REPO / "catalogue" / "odins-ravens.json"
IDENTITIES = REPO / "catalogue" / "odins-ravens-save-identities.json"
AUTHORITY = HERE / "probe-active-save-raven-ring-authority.py"
QUEST_CAPTURE_GLOB = "raven-authoritative-quest-records-*/console-log.txt"
ASCII_RE = re.compile(rb"[A-Za-z0-9_./\\:\\-]{4,}")
QUEST_RE = re.compile(rb"RegionSummary_[A-Z0-9]+_Raven_Parent")
MASK64 = 0xFFFFFFFFFFFFFFFF


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


def game_hash(text: str) -> int:
    value = 0
    try:
        raw = text.upper().encode("ascii")
    except UnicodeEncodeError:
        return 0
    for byte in raw:
        value = ((value + byte) * 0x401) & MASK64
        value ^= value >> 6
    return value


def guid_forms(text: str) -> dict[str, bytes]:
    u = uuid.UUID(text)
    return {"guid_rfc": u.bytes, "guid_windows": u.bytes_le}


def latest_quest_capture() -> Path | None:
    root = REPO / "archive" / "field-logs" / "runtime-captures"
    rows = sorted(root.glob(QUEST_CAPTURE_GLOB), key=lambda p: p.parent.name, reverse=True)
    return rows[0] if rows else None


def quest_states(path: Path | None) -> dict[str, dict[str, int]]:
    out = {}
    if path is None:
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("RegionSummary_") or " found=True " not in line:
            continue
        parts = line.split()
        fields = {}
        for token in parts[1:]:
            if "=" in token:
                k, v = token.split("=", 1)
                fields[k] = v
        try:
            out[parts[0]] = {"progress": int(fields["progress"]), "goal": int(fields["goal"])}
        except (KeyError, ValueError):
            pass
    return out


def classify(catalogue: dict, qstate: dict[str, dict[str, int]]) -> dict[str, dict]:
    by_parent = defaultdict(list)
    for row in catalogue["ravens"]:
        by_parent[row["progression"]["parent_quest"]].append(row)
    result = {}
    for parent, rows in by_parent.items():
        q = qstate.get(parent)
        surplus = any("parent_contains_one_bonus_untracked_raven" in r.get("special_handling", []) for r in rows)
        if q is None:
            label, reason = "unknown", "no_quest_capture"
            progress = goal = None
        else:
            progress, goal = q["progress"], q["goal"]
            if progress == 0:
                label, reason = "alive", "aggregate_zero_progress"
            elif not surplus and goal == len(rows) and progress >= goal:
                label, reason = "killed", "aggregate_complete_exact_count"
            else:
                label, reason = "ambiguous", "partial_or_surplus_parent"
        for row in rows:
            result[row["catalogue_id"]] = {
                "state_label": label,
                "state_reason": reason,
                "parent": parent,
                "progress": progress,
                "goal": goal,
                "catalogue_count": len(rows),
                "surplus_parent": surplus,
            }
    return result


class Aho:
    def __init__(self, patterns: list[bytes]):
        self.next = [dict()]
        self.fail = [0]
        self.out = [[]]
        for idx, pat in enumerate(patterns):
            state = 0
            for byte in pat:
                nxt = self.next[state].get(byte)
                if nxt is None:
                    nxt = len(self.next)
                    self.next[state][byte] = nxt
                    self.next.append({})
                    self.fail.append(0)
                    self.out.append([])
                state = nxt
            self.out[state].append(idx)
        q = deque()
        for nxt in self.next[0].values():
            q.append(nxt)
        while q:
            state = q.popleft()
            for byte, nxt in self.next[state].items():
                q.append(nxt)
                f = self.fail[state]
                while f and byte not in self.next[f]:
                    f = self.fail[f]
                self.fail[nxt] = self.next[f].get(byte, 0)
                self.out[nxt].extend(self.out[self.fail[nxt]])

    def scan(self, data: bytes):
        state = 0
        for pos, byte in enumerate(data):
            while state and byte not in self.next[state]:
                state = self.fail[state]
            state = self.next[state].get(byte, 0)
            for idx in self.out[state]:
                yield idx, pos


def candidate_ok(raw: bytes) -> bool:
    if len(raw) not in (8, 16):
        return False
    if raw == bytes(len(raw)):
        return False
    if len(set(raw)) <= 2:
        return False
    if len(raw) == 8:
        value = int.from_bytes(raw, "little")
        if value < 0x10000:
            return False
    return True


def add_candidate(store, raw: bytes, cid: str, kind: str, detail: str):
    if not raw or len(raw) < 8:
        return
    store[raw].append({"catalogue_id": cid, "kind": kind, "detail": detail})


def load_override_payloads(game_root: Path, catalogue: dict):
    raven_catalogue = load_module("raven_catalogue_override_probe", HERE / "raven_catalogue.py")
    wad_root = game_root / "exec" / "wad" / "pc_le"
    grouped = defaultdict(list)
    for row in catalogue["ravens"]:
        grouped[row["source"]["wad"]].append(row)

    payloads = {}
    for wad_name, rows in grouped.items():
        path = wad_root / wad_name
        if not path.is_file():
            raise RuntimeError(f"missing Raven WAD: {path}")
        records = raven_catalogue.parse_wad(path.read_bytes())
        by_offset = {r["offset"]: r for r in records}
        for row in rows:
            off = int(row["source"]["override_offset"], 16)
            rec = by_offset.get(off)
            if rec is None:
                raise RuntimeError(f"override offset not found: {wad_name} {off:#x}")
            payloads[row["catalogue_id"]] = rec["data"]
    return payloads


def build_candidates(catalogue: dict, identities: dict, payloads: dict[str, bytes]):
    store = defaultdict(list)
    identity_by_id = {r["catalogue_id"]: r for r in identities["identities"]}

    for row in catalogue["ravens"]:
        cid = row["catalogue_id"]
        native = row["native"]
        prog = row["progression"]
        payload = payloads[cid]

        explicit_hex = {
            "override_record_id": native["override_record_id"],
            "final_record_id": native["final_record_id"],
            "prototype_id": native["prototype_id"],
            "parent_prototype_id": native["parent_prototype_id"],
        }
        for kind, value in explicit_hex.items():
            try:
                add_candidate(store, bytes.fromhex(value), cid, kind, value)
            except ValueError:
                pass

        for kind, raw in guid_forms(native["script_guid"]).items():
            add_candidate(store, raw, cid, "script_" + kind, native["script_guid"])

        strings = {
            "object_name": native["object_name"],
            "override_name": native["override_name"],
            "instance_guid_text": native["instance_guid"],
            "instance_guid_compact": native["instance_guid"].replace("-", ""),
            "script_guid_text": native["script_guid"],
            "script_guid_compact": native["script_guid"].replace("-", ""),
            "parent_quest": prog["parent_quest"],
            "catalogue_id": cid,
        }
        for m in ASCII_RE.finditer(payload):
            try:
                text = m.group().decode("ascii")
            except UnicodeDecodeError:
                continue
            strings.setdefault(f"payload_string_0x{m.start():X}", text)

        for kind, text in strings.items():
            hv = game_hash(text)
            if hv:
                add_candidate(store, hv.to_bytes(8, "little"), cid, kind + "_hash_le", text)
                add_candidate(store, hv.to_bytes(8, "big"), cid, kind + "_hash_be", text)

        qmatch = QUEST_RE.search(payload)
        if qmatch is None:
            raise RuntimeError(f"Raven override lacks RegionSummary parent: {cid}")
        lo = max(0, qmatch.start() - 0x100)
        hi = min(len(payload), qmatch.end() + 0x100)
        # Mine opaque aligned binary tokens around the exact progression field.
        for off in range(lo, max(lo, hi - 7), 4):
            raw8 = payload[off:off + 8]
            if candidate_ok(raw8):
                add_candidate(store, raw8, cid, "near_parent_u64", f"payload+0x{off:X}")
            raw16 = payload[off:off + 16]
            if candidate_ok(raw16):
                add_candidate(store, raw16, cid, "near_parent_128", f"payload+0x{off:X}")

        # Mark solved GameObject representations so any rediscovery is obvious.
        ident = identity_by_id.get(cid)
        if ident:
            oh = int(ident["object_hash_hex"], 16)
            add_candidate(store, oh.to_bytes(8, "little"), cid, "known_object_hash_le", ident["object_hash_hex"])

    return store


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    ap.add_argument("--save-root", type=Path, default=Path.home() / "Saved Games" / "God of War")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    game_root = args.game_root.expanduser().resolve()
    if not (game_root / "exec" / "wad" / "pc_le").is_dir():
        raise RuntimeError(f"unsupported game root: {game_root}")

    saves = sorted(p.resolve() for p in args.save_root.expanduser().resolve().rglob("game.sav") if p.is_file())
    if len(saves) != 1:
        raise RuntimeError(f"expected exactly one active game.sav, found {len(saves)}")
    save = saves[0]

    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    if len(catalogue.get("ravens", [])) != 53 or identities.get("identity_count") != 53:
        raise RuntimeError("Raven catalogue/identity contract incomplete")

    qpath = latest_quest_capture()
    states = classify(catalogue, quest_states(qpath))
    payloads = load_override_payloads(game_root, catalogue)
    candidates = build_candidates(catalogue, identities, payloads)
    patterns = list(candidates)
    matcher = Aho(patterns)

    before = sha256_file(save)
    blob = save.read_bytes()
    authority = load_module("raven_override_token_authority", AUTHORITY)
    lay = authority.layout(blob)
    prefix, stride = lay["global_prefix"], lay["slot_stride"]

    headers = []
    occupied = []
    raw_slots = []
    for idx in range(lay["slot_count"]):
        slot = blob[prefix + idx * stride:prefix + (idx + 1) * stride]
        headers.append(slot[:authority.HEADER_BYTES])
        # Occupancy is cheap to establish from any validated zlib stream.
        stream_count = 0
        cursor = 0
        while True:
            at = slot.find(b"\x78", cursor)
            if at < 0:
                break
            cursor = at + 1
            if authority.decompress_stream(slot, at) is not None:
                stream_count += 1
        if stream_count:
            occupied.append(idx)
        raw_slots.append(slot)

    hinfo = authority.header_fields(headers, occupied)
    latest = hinfo.get("consensus_latest_slot")
    if latest is None:
        raise RuntimeError("unable to resolve authoritative/latest save-ring slot")
    scan_slots = sorted(set([latest] + [x for x in (18, 19) if x in occupied]))

    hits = []
    hit_counts = Counter()
    for idx in scan_slots:
        slot = raw_slots[idx]
        seen_raw = set()
        for pat_idx, end in matcher.scan(slot):
            start = end - len(patterns[pat_idx]) + 1
            key = (pat_idx, start)
            if key in seen_raw:
                continue
            seen_raw.add(key)
            hit_counts[(idx, "raw", pat_idx)] += 1
            hits.append({"slot": idx, "scope": "raw", "offset": start, "pattern_index": pat_idx})

        cursor = 0
        stream_seen = set()
        while True:
            at = slot.find(b"\x78", cursor)
            if at < 0:
                break
            cursor = at + 1
            got = authority.decompress_stream(slot, at)
            if got is None:
                continue
            decoded, consumed = got
            local = set()
            for pat_idx, end in matcher.scan(decoded):
                start = end - len(patterns[pat_idx]) + 1
                key = (pat_idx, start)
                if key in local:
                    continue
                local.add(key)
                global_key = (at, pat_idx, start)
                if global_key in stream_seen:
                    continue
                stream_seen.add(global_key)
                hit_counts[(idx, f"zlib@{at}", pat_idx)] += 1
                hits.append({
                    "slot": idx,
                    "scope": "zlib",
                    "stream_offset": at,
                    "compressed_bytes": consumed,
                    "decoded_offset": start,
                    "pattern_index": pat_idx,
                })

    candidate_rows = []
    for pat_idx, raw in enumerate(patterns):
        labels = candidates[raw]
        owners = sorted({x["catalogue_id"] for x in labels})
        relevant = [h for h in hits if h["pattern_index"] == pat_idx]
        if not relevant:
            continue
        owner_states = Counter(states.get(cid, {}).get("state_label", "unknown") for cid in owners)
        kinds = sorted({x["kind"] for x in labels})
        candidate_rows.append({
            "pattern_hex": raw.hex(),
            "bytes": len(raw),
            "owner_count": len(owners),
            "owners": owners,
            "owner_state_counts": dict(sorted(owner_states.items())),
            "kinds": kinds,
            "details": labels[:20],
            "known_object_hash_only": all(k == "known_object_hash_le" for k in kinds),
            "hits": relevant,
        })

    candidate_rows.sort(key=lambda r: (
        r["known_object_hash_only"],
        r["owner_count"],
        -len(r["hits"]),
        r["bytes"],
        r["pattern_hex"],
    ))

    novel_unique = [
        r for r in candidate_rows
        if r["owner_count"] == 1 and not r["known_object_hash_only"]
    ]

    summary = {
        "candidate_patterns": len(patterns),
        "patterns_with_hits": len(candidate_rows),
        "novel_unique_patterns_with_hits": len(novel_unique),
        "latest_slot": latest,
        "scanned_slots": scan_slots,
        "state_labels": dict(Counter(v["state_label"] for v in states.values())),
        "novel_unique_by_state": dict(Counter(
            next(iter(r["owner_state_counts"])) if len(r["owner_state_counts"]) == 1 else "mixed"
            for r in novel_unique
        )),
    }

    after = sha256_file(save)
    if before != after:
        raise RuntimeError("active game.sav changed during read-only override-token probe")

    report = {
        "schema": 1,
        "analysis": "raven_override_token_persistence",
        "save_sha256": before,
        "quest_capture": str(qpath.relative_to(REPO)) if qpath else None,
        "layout": lay,
        "header_consensus": {
            "latest_slot": latest,
            "reason": hinfo.get("consensus_reason"),
        },
        "summary": summary,
        "novel_unique_candidates": novel_unique,
        "all_hit_candidates": candidate_rows,
        "safety": {
            "native_game_data_read_only": True,
            "active_save_opened_read_only": True,
            "source_hash_unchanged": True,
            "save_written": False,
            "progression_written": False,
            "game_process_opened": False,
            "game_files_written": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "RAVEN_OVERRIDE_TOKEN_PERSISTENCE_COMPLETE "
        f"patterns={summary['candidate_patterns']} hitPatterns={summary['patterns_with_hits']} "
        f"novelUnique={summary['novel_unique_patterns_with_hits']} latest={latest}"
    )
    print("state_labels=" + ",".join(f"{k}:{v}" for k, v in sorted(summary["state_labels"].items())))
    print("scanned_slots=" + ",".join(map(str, scan_slots)))
    for row in novel_unique[:40]:
        cid = row["owners"][0]
        state = states.get(cid, {}).get("state_label", "unknown")
        print(
            f"CANDIDATE raven={cid} state={state} bytes={row['bytes']} "
            f"kinds={'+'.join(row['kinds'])} hits={len(row['hits'])} hex={row['pattern_hex']}"
        )
    print("source_hash_unchanged=true save_written=false progression_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
