#!/usr/bin/env python3
"""Match Ship Head scene paths to frozen staged state, with no runtime access."""
from __future__ import annotations

import argparse
from itertools import combinations
import hashlib
import json
from pathlib import Path

import raven_catalogue as raven
import staged_state_graph as graph


REPO = Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "config/collectibles/v0.10.5/all-collectibles.json"
CAPTURE = REPO / "archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1"
GAME = Path("G:/SteamLibrary/steamapps/common/GodOfWar")
ROOT_NAME = "goProtoArtifactScript_Root"
ROOT_ID = "bdff29c1ed8dba4aa015b7b27261f0f0"
MASK = (1 << 64) - 1
STATE_SIGNATURE = [{"name": "state", "value_tag": 1}]


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def name_hash(name: str) -> int:
    return rolling_hash([name.upper().encode("ascii")])


def rolling_hash(elements: list[bytes]) -> int:
    value = 0
    for element in elements:
        for byte in element:
            value = ((value + byte) * 0x401) & MASK
            value ^= value >> 6
    return value


def adjusted(hex_id: str) -> bytes:
    value = bytearray.fromhex(hex_id)
    require(len(value) == 16, "scene record ID width differs")
    value[12] = (value[12] - 1) & 255
    return bytes(value)


def native_guid(hex_id: str) -> str:
    value = adjusted(hex_id)
    words = b"".join(value[i:i + 4][::-1] for i in range(0, 16, 4)).hex()
    return (words[:8] + "-" + words[8:12] + "-" + words[12:16] +
            "-" + words[16:20] + "-" + words[20:])


def candidate_subsets(path: dict):
    """Try every owner-chain subset, keeping placement and script records."""
    chain = path["transform_chain"]
    require(len(chain) >= 3 and chain[0]["name"] == "goartifactscript",
            "Ship Head transform grammar differs")
    placement = [i for i, item in enumerate(chain) if
                 native_guid(item["record_id"]) == path["physical_instance_guid"]]
    require(len(placement) == 1,
            "Ship Head physical placement absent from chain")
    required = {0, placement[0]}
    optional = [i for i in range(len(chain)) if i not in required]
    for size in range(len(optional) + 1):
        for picked in combinations(optional, size):
            kept = required | set(picked)
            chosen = [chain[i] for i in reversed(range(len(chain))) if i in kept]
            yield chosen


def canonical_subset(path: dict) -> list[dict]:
    """Rule reproduced by all eight exact frozen Ship Head identity hits."""
    chain = path["transform_chain"]
    physical_is_script = (native_guid(chain[0]["record_id"]) ==
                          path["physical_instance_guid"])
    outer_shiphead = next((item for item in reversed(chain[1:]) if
                           item["name"].lower().startswith("goartifactshiphead")), None)
    require(not physical_is_script or outer_shiphead is not None,
            "Ship Head script placement lacks outer object")
    chosen = [item for item in reversed(chain) if
              item["name"].lower().endswith(("_ents", "_ents_nooffset")) or
              native_guid(item["record_id"]) == path["physical_instance_guid"] or
              item is chain[0] or (physical_is_script and item is outer_shiphead)]
    require(len(chosen) >= 3 and chosen[-1] is chain[0],
            "Ship Head canonical identity chain differs")
    return chosen


def hash_path_records(chosen: list[dict]) -> int:
    return rolling_hash([adjusted(item["record_id"]) for item in chosen] +
                        [bytes.fromhex(ROOT_ID)])


def normalize(name: str) -> str:
    return "".join(c for c in name.lower().removesuffix(".wad") if c.isalnum())


def read_capture(wad_names: set[str], capture: Path) -> tuple[dict, dict]:
    manifest = json.loads((capture / "report.json").read_text(encoding="utf-8"))
    require(len(manifest["records"]) == 425, "frozen staged census differs")
    by_name = {normalize(row["name"]): row for row in manifest["records"]}
    by_wad = {}
    for wad in sorted(wad_names):
        meta = by_name.get(normalize(wad))
        require(meta is not None and meta.get("payload_file"),
                f"{wad}: frozen capture absent")
        envelope = (capture / meta["payload_file"]).read_bytes()
        require(hashlib.sha256(envelope).hexdigest() == meta["sha256"],
                f"{wad}: frozen payload digest differs")
        candidates = graph.carrier_with_tokens(
            envelope, int(meta["cached_channel_a_lua_length"]))
        require(len(candidates) == 1, f"{wad}: staged graph ambiguous or absent")
        item = candidates[0]
        entries = graph.extract_state_entries(
            item["raw"], item["decoded"], item["parsed"])
        states = {}
        for entry in entries:
            parent = entry["parent"].get("gameobject")
            if parent is None or entry["field_signature"] != STATE_SIGNATURE:
                continue
            key = (int(parent["registry_hash_hex"], 16),
                   int(parent["object_hash_hex"], 16))
            require(key not in states, f"{wad}: duplicate frozen state key")
            states[key] = entry
        by_wad[wad] = {"meta": meta, "states": states,
                       "alignment": item["alignment"],
                       "bit_offset": item["bit_offset"]}
    return manifest, by_wad


def verify_roots(wad_names: set[str], game: Path) -> dict[str, dict]:
    result = {}
    for wad in sorted(wad_names):
        raw = (game / "exec/wad/pc_le" / wad).read_bytes()
        matches = [record for record in raven.parse_wad(raw)
                   if record["name"] == ROOT_NAME]
        require(len(matches) == 1 and matches[0]["id"].hex() == ROOT_ID,
                f"{wad}: Ship Head prototype root differs")
        result[wad] = {"wad_sha256": hashlib.sha256(raw).hexdigest(),
                       "root_record_offset": hex(matches[0]["offset"]),
                       "root_record_id": ROOT_ID}
    return result


def assess(catalogue: dict, by_wad: dict, roots: dict) -> dict:
    rows = [row for row in catalogue["collectibles"]
            if row.get("subtype") == "Ship Head" and row["family"] == "artefact"]
    require(len(rows) == 9, "Ship Head catalogue census differs")
    proof = []
    seen = set()
    for row in sorted(rows, key=lambda r: r["native"]["numbered_object_evidence"][0]):
        wad = row["source"]["wad"]
        require(roots[wad]["wad_sha256"] == row["source"]["wad_sha256"],
                f"{wad}: catalogue WAD digest differs")
        registry = name_hash(Path(wad).stem)
        paths = []
        hits = []
        for path in row["native"]["carrier_transform_paths"]:
            canonical = canonical_subset(path)
            canonical_hash = hash_path_records(canonical)
            matches = []
            for chosen in candidate_subsets(path):
                object_hash = hash_path_records(chosen)
                entry = by_wad[wad]["states"].get((registry, object_hash))
                if entry is not None:
                    matches.append({"object_hash_hex": f"0x{object_hash:016X}",
                                    "serialized_flag1_hex": (b"\x01" + registry.to_bytes(8, "little") + object_hash.to_bytes(8, "little")).hex(),
                                    "state_raw_hex": entry["state"]["raw_hex"],
                                    "state_tag": entry["state"]["tag"],
                                    "state_scalar_bits": entry["state"]["payload"],
                                    "identity_record_ids": [item["record_id"] for item in chosen],
                                    "identity_record_names": [item["name"] for item in chosen],
                                    "frozen_subobj_row": entry["subobj_table_row"],
                                    "frozen_state_row": entry["state_row"]})
            require(len(matches) <= 1, "Ship Head path has ambiguous frozen state keys")
            require(not matches or matches[0]["object_hash_hex"] not in seen,
                    "Ship Head frozen state key repeats")
            if matches:
                require(matches[0]["object_hash_hex"] == f"0x{canonical_hash:016X}",
                        "frozen Ship Head key disagrees with canonical owner chain")
                seen.add(matches[0]["object_hash_hex"])
                hits += matches
            paths.append({"state_carrier_guid": path["state_carrier_guid"],
                          "candidate_subset_count": sum(1 for _ in candidate_subsets(path)),
                          "canonical_object_hash_hex": f"0x{canonical_hash:016X}",
                          "canonical_serialized_flag1_hex": (
                              b"\x01" + registry.to_bytes(8, "little") +
                              canonical_hash.to_bytes(8, "little")).hex(),
                          "canonical_identity_record_ids": [item["record_id"] for item in canonical],
                          "matches": matches})
        require(len(hits) <= 1, "Ship Head physical row has two frozen keys")
        proof.append({"number": row["native"]["numbered_object_evidence"][0],
                      "catalogue_id": row["catalogue_id"], "wad": wad,
                      "registry_hash_hex": f"0x{registry:016X}",
                      "frozen_identity_match": bool(hits),
                      "frozen_state": hits[0] if hits else None,
                      "path_results": paths})
    require(sum(p["frozen_identity_match"] for p in proof) == 8,
            "frozen Ship Head match census differs")
    require([p["number"] for p in proof if not p["frozen_identity_match"]] == [8],
            "Ship Head unresolved frozen row differs")
    return {"schema": 1, "analysis": "ship_head_frozen_staged_identity",
            "status": "BLOCKED_FAIL_CLOSED", "runtime_generation_allowed": False,
            "physical_count": 9, "transform_path_count": sum(len(p["path_results"]) for p in proof),
            "frozen_exact_identity_count": 8,
            "unresolved_physical_numbers": [8],
            "unloaded_state_query_proven": False,
            "state_values_are_frozen_capture_observations": True,
            "source_capture": str(CAPTURE.relative_to(REPO)).replace("\\", "/"),
            "rows": proof}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    parser.add_argument("--game-root", type=Path, default=GAME)
    args = parser.parse_args()
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    wad_names = {row["source"]["wad"] for row in catalogue["collectibles"]
                 if row.get("subtype") == "Ship Head" and row["family"] == "artefact"}
    _, by_wad = read_capture(wad_names, args.capture)
    roots = verify_roots(wad_names, args.game_root)
    report = assess(catalogue, by_wad, roots)
    report["source_sha256"] = {
        "catalogue": hashlib.sha256(CATALOGUE.read_bytes()).hexdigest(),
        "capture_manifest": hashlib.sha256((args.capture / "report.json").read_bytes()).hexdigest(),
        "wad_roots": roots,
        "frozen_payloads": {wad: by_wad[wad]["meta"]["sha256"] for wad in sorted(wad_names)}}
    output = args.output.resolve()
    require(REPO in output.parents, "output must stay inside repository")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SHIP_HEAD_STAGED_IDENTITY BLOCKED_FAIL_CLOSED exact=8/9 unresolved=08")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
