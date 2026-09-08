"""Inventory resident UI texture GPU/definition pairs relevant to map icons.

Read-only diagnostic for the v0.10.4 Raven artwork problem. The dedicated
Completionist Raven GO is proven to instantiate, but it still renders the low-
resolution Dock artwork even with the custom texpack and user-hash binding
active. This probe inventories stock resident texture GPU payloads that have the
same byte sizes as the Dock diffuse/emissive payloads so we can choose a safe,
visually distinct stock donor for a one-Raven resident-payload control proof.

No game file, save, boot option or progression state is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
EXPECTED_ACTIVE_WAD = "e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959"
EXPECTED_STOCK_WAD = "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04"

RAVEN_DIFFUSE = "TX_completionist_raven_map_diffuse_19A41F00834C19F3"
RAVEN_EMISSIVE = "TX_completionist_raven_map_emissive_63F1E18FF93B9037"
DOCK_DIFFUSE = "TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC"
DOCK_EMISSIVE = "TX_mapmarker_docklocation_emissive_FCC664130951154C"

TARGET_SIZES = {
    "diffuse": 9228,
    "emissive": 4620,
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_logical():
    path = HERE / "build-raven-ui-logical-clone.py"
    spec = importlib.util.spec_from_file_location("completionist_logical", path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def file_hash_from_name(name: str) -> str | None:
    m = re.search(r"_([0-9A-Fa-f]{16})$", name)
    return m.group(1).upper() if m else None


def family_key(name: str) -> str:
    base = re.sub(r"_[0-9A-Fa-f]{16}$", "", name)
    base = re.sub(r"_(diffuse|emissive|gloss|norm|normal|mask)$", "", base, flags=re.I)
    return base.lower()


def classify(name: str) -> str:
    low = name.lower()
    if "completionist_raven" in low:
        return "completionist_raven"
    if "docklocation" in low:
        return "dock"
    if "valkyr" in low:
        return "valkyrie"
    if "vendor" in low:
        return "vendor"
    if "fight" in low:
        return "fight"
    if "fasttravel" in low or "fast_travel" in low:
        return "fast_travel"
    if "quest" in low:
        return "quest"
    if "mapmarker" in low or "mapicon" in low:
        return "other_map_marker"
    return "other_ui"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    raw = args.wad.read_bytes()
    wad_sha = sha(raw)
    check(wad_sha in (EXPECTED_ACTIVE_WAD, EXPECTED_STOCK_WAD),
          f"unexpected r_ui.wad SHA256: {wad_sha}")

    logical = load_logical()
    records = logical.parse_wad(raw)

    defs: dict[str, list[dict]] = {}
    gpus: dict[str, list[dict]] = {}
    for r in records:
        if r["kind"] == 1 and r["flags"] == 0x8021 and len(r["data"]) == 356:
            defs.setdefault(r["name"], []).append(r)
        elif r["kind"] == 0x1D and r["flags"] == 0x80A1 and len(r["data"]) > 0:
            gpus.setdefault(r["name"], []).append(r)

    pairs = []
    for name in sorted(set(defs) & set(gpus)):
        if len(defs[name]) != 1 or len(gpus[name]) != 1:
            continue
        d = defs[name][0]
        g = gpus[name][0]
        user_hash = struct.unpack_from("<Q", d["data"], 0x9C)[0]
        pairs.append({
            "name": name,
            "family_key": family_key(name),
            "classification": classify(name),
            "file_hash": file_hash_from_name(name),
            "user_hash": f"{user_hash:016X}",
            "definition_payload_index": d["payload_index"],
            "gpu_payload_index": g["payload_index"],
            "gpu_bytes": len(g["data"]),
            "gpu_sha256": sha(bytes(g["data"])),
            "definition_id": d["id"].hex(),
            "gpu_id": g["id"].hex(),
        })

    by_name = {p["name"]: p for p in pairs}
    for required in (DOCK_DIFFUSE, DOCK_EMISSIVE):
        check(required in by_name, f"required stock texture pair missing: {required}")

    active_has_raven = RAVEN_DIFFUSE in by_name and RAVEN_EMISSIVE in by_name
    if wad_sha == EXPECTED_ACTIVE_WAD:
        check(active_has_raven, "active Raven WAD hash present but Raven textures were not found")

    same_size = {
        label: [p for p in pairs if p["gpu_bytes"] == size]
        for label, size in TARGET_SIZES.items()
    }

    # Families with both a 9228-byte and 4620-byte resident payload are strongest
    # candidates for a like-for-like diffuse/emissive control proof.
    diffuse_families: dict[str, list[dict]] = {}
    emissive_families: dict[str, list[dict]] = {}
    for p in same_size["diffuse"]:
        diffuse_families.setdefault(p["family_key"], []).append(p)
    for p in same_size["emissive"]:
        emissive_families.setdefault(p["family_key"], []).append(p)

    matched_families = []
    for family in sorted(set(diffuse_families) & set(emissive_families)):
        ds = diffuse_families[family]
        es = emissive_families[family]
        # Prefer obvious semantic diffuse/emissive names within each family.
        for d in ds:
            for e in es:
                score = 0
                dl = d["name"].lower()
                el = e["name"].lower()
                if "diffuse" in dl:
                    score += 5
                if "emissive" in el:
                    score += 5
                if d["classification"] != "other_ui":
                    score += 3
                if e["classification"] != "other_ui":
                    score += 3
                if d["classification"] == e["classification"]:
                    score += 2
                if d["classification"] in {"valkyrie", "vendor", "fight", "fast_travel", "quest", "other_map_marker"}:
                    score += 4
                if d["classification"] in {"dock", "completionist_raven"}:
                    score -= 20
                matched_families.append({
                    "family_key": family,
                    "score": score,
                    "classification": d["classification"],
                    "diffuse": d,
                    "emissive": e,
                })

    matched_families.sort(key=lambda x: (-x["score"], x["family_key"]))

    result = {
        "result": "MAP_ICON_RESIDENT_TEXTURES_INVENTORIED",
        "game_files_written": False,
        "save_files_written": False,
        "progression_state_written": False,
        "wad_sha256": wad_sha,
        "active_registered_raven_wad": wad_sha == EXPECTED_ACTIVE_WAD,
        "pair_count": len(pairs),
        "target_gpu_sizes": TARGET_SIZES,
        "stock_dock": {
            "diffuse": by_name[DOCK_DIFFUSE],
            "emissive": by_name[DOCK_EMISSIVE],
        },
        "completionist_raven": {
            "present": active_has_raven,
            "diffuse": by_name.get(RAVEN_DIFFUSE),
            "emissive": by_name.get(RAVEN_EMISSIVE),
        },
        "same_size_candidates": same_size,
        "matched_family_candidates": matched_families,
        "next_gate": (
            "Choose a visually distinct stock matched-family donor with identical resident GPU payload sizes, then build a reversible proof that copies only those two donor resident payload bytes into the isolated Completionist Raven GPU records. If the Raven changes to the donor artwork while docks remain stock, resident WAD texture payloads are confirmed as the active visual source."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": result["result"],
        "wad_sha256": wad_sha,
        "pair_count": len(pairs),
        "matched_family_candidate_count": len(matched_families),
        "top_candidates": [
            {
                "classification": x["classification"],
                "family": x["family_key"],
                "diffuse": x["diffuse"]["name"],
                "emissive": x["emissive"]["name"],
                "score": x["score"],
            }
            for x in matched_families[:12]
        ],
        "game_files_written": False,
    }, indent=2))


if __name__ == "__main__":
    main()
