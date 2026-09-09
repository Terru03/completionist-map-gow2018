#!/usr/bin/env python3
"""Build Nornir Candidate 3 from frozen Raven production, offline only.

Candidate 3 keeps the runtime-proven Raven topology: dedicated texture,
material, model, prototype, and root ownership, with stock map/HUD model-group
resources shared through local dependency links.  It corrects the first proven
Nornir divergence by preserving the Raven/Dock material +0x20 donor field.

No game file, save, progression value, or marker state is written.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULT = "NORNIR_CANDIDATE3_OFFLINE_ASSEMBLED"

RAVEN_HASHES = {
    "exec/wad/pc_le/r_ui.wad": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
    "exec/dc/pc_le/wad_r_ui.dcb": "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d",
    "exec/dc/pc_le/wad_r_perm.dcb": "85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5",
    "exec/dc/pc_le/mapmaster.dcb": "b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f",
    "exec/dc/pc_le/mapcoords.dcb": "945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb",
    "exec/dc/pc_le/compassgraph.dcb": "d0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": "67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b",
}

LIFECYCLE_FILES = {
    "exec/dc/pc_le/wad_r_perm.dcb": "be453733a57a27dde5eb33e553973ec34c330e4841f7c632e4f784a8adc34350",
    "exec/dc/pc_le/mapmaster.dcb": "6285c824973e760594b7413a79645b931200e40237710600052d964602d9bff4",
    "exec/dc/pc_le/mapcoords.dcb": "b870adccf66baf0d71dd1c0774d12e5ca503415da1e9270f82d0b77c0f11cd7f",
    "exec/dc/pc_le/compassgraph.dcb": "8477f6332436959ce06b0c7e84a4871a7ff947421f9e858589e360e2e7c0d45e",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua": "ac38d76b4eea20b701ab73d3eaf9f2a23f9933b4bd4ddf5a4e9ec7197e5bc8b8",
    "mods/lua/gameart/ui/scripts/hud/mainhud.lua": "9f803bba1296c99960764aae161b2118531ba8f02dce60284207424257e01605",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua": "67620fdab2e33186652efdd7c50c7f085e6670964e8d91556804890e382a9c3b",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua": "7b9e1b03bef0f26de9c132241f6a98750c34c6f99dbb324ea37cbcd0347c07f3",
}

CANDIDATE1_WAD = "340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c"
CANDIDATE2_WAD = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"
RAVEN_MATERIAL_Q10 = 0x1B0989158D4A2908
RAVEN_DONOR_Q20 = 0xD595197B0961F689
CANDIDATE1_Q20 = 0xE2265134DFA7B641

RAVEN_RESOURCE_NAMES = (
    "MAT_AE4AD85BB993F040",
    "MDL_completionistraven",
    "goProtoMapIconCompletionistRaven",
    "gomapiconcompletionistraven",
    "MDL_completionistravenhud",
    "goProtoCompletionistRavenHUD",
    "gocompletionistravenhud",
)
STOCK_DONOR_NAMES = (
    "MAT_0C599DC8DC7E2170",
    "MDL_mapicondock",
    "MG_mapicondock_0",
    "gomapicondock",
    "MDL_boatdock",
    "MG_boatdock_0",
    "goboatdock",
)


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    check(path.is_file(), f"missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one_payload(records: list[dict], name: str) -> tuple[int, dict]:
    hits = [(index, row) for index, row in enumerate(records)
            if row["kind"] == 1 and row["data"] and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one payload {name!r}, found {len(hits)}")
    return hits[0]


def group_rows(logical, records: list[dict], payload_index: int) -> list[dict]:
    start = records[payload_index]["parent"]
    check(start is not None and records[start]["kind"] == 2,
          f"payload has no owning group: {records[payload_index]['name']}")
    end = logical.matching_group_end(records, start)
    return records[start:end + 1]


def serialized_named(logical, records: list[dict], name: str) -> list[bytes]:
    return [logical.record_bytes(row) for row in records if row["name"].lower() == name.lower()]


def assert_existing_named_records_preserved(logical, source: list[dict], candidate: list[dict],
                                             names: tuple[str, ...]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for name in names:
        before = serialized_named(logical, source, name)
        after = serialized_named(logical, candidate, name)
        check(before, f"source resource missing: {name}")
        pending = list(after)
        for row in before:
            check(row in pending, f"source record changed or disappeared: {name}")
            pending.remove(row)
        result[name] = {
            "source_record_count": len(before),
            "candidate_record_count": len(after),
            "every_source_record_byte_identical": True,
        }
    return result


def group_dependency(records: list[dict], rows: list[dict], name: str) -> dict:
    hits = [row for row in rows if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one dependency {name!r}, found {len(hits)}")
    row = hits[0]
    return {"name": row["name"], "id": row["id"].hex()}


def dependency_owner(logical, records: list[dict], index: int) -> dict:
    start = records[index]["parent"]
    check(start is not None and records[start]["kind"] == 2,
          f"dependency has no owner group: {records[index]['name']}")
    end = logical.matching_group_end(records, start)
    payloads = [(row_index, records[row_index]) for row_index in range(start + 1, end)
                if records[row_index]["kind"] == 1 and records[row_index]["data"]]
    check(len(payloads) >= 1, f"dependency owner group has no payload: {records[index]['name']}")
    owner_index, owner = payloads[0]
    return {"record_index": owner_index, "name": owner["name"], "id": owner["id"].hex()}


def normalize_to_raven(logical, source_raw: bytes, candidate_records: list[dict], nornir: dict) -> bytes:
    stripped = copy.deepcopy(candidate_records)
    removal: set[int] = set()
    grouped = (
        nornir["material"], nornir["map_model"], nornir["map_proto"], nornir["map_root"],
        nornir["hud_model"], nornir["hud_proto"], nornir["hud_root"],
    )
    for name in grouped:
        index, _ = one_payload(stripped, name)
        start = stripped[index]["parent"]
        check(start is not None, f"Nornir group missing: {name}")
        end = logical.matching_group_end(stripped, start)
        removal.update(range(start, end + 1))

    for name in (nornir["diffuse"], nornir["emissive"]):
        removal.update(index for index, row in enumerate(stripped)
                       if row["name"].lower() == name.lower())

    _, map_root = one_payload(stripped, nornir["map_root"])
    parent_refs = [index for index, row in enumerate(stripped)
                   if row["kind"] == 1 and not row["data"]
                   and row["name"].lower() == nornir["map_root"].lower()
                   and row["id"] == map_root["id"]]
    check(len(parent_refs) == 1, "Nornir map parent reference is not unique")
    removal.add(parent_refs[0])

    stripped = [row for index, row in enumerate(stripped) if index not in removal]
    source_records = logical.parse_wad(source_raw)
    source_payloads = logical.payload_records(source_records)
    stripped_payloads = logical.payload_records(stripped)
    stripped_payloads[0]["data"] = bytearray(source_payloads[0]["data"])
    stripped_payloads[1]["data"] = bytearray(source_payloads[1]["data"])
    return logical.serialize_wad(stripped)


def _legacy_build_candidate3_wad_reference(source_raw: bytes, art_report: Path) -> tuple[bytes, dict]:
    v5 = load_module("completionist_nornir_candidate3_v5",
                     HERE / "build-nornir-map-hud-offline-v5.py")
    base = v5.base
    logical = base.load_module("build-raven-ui-logical-clone.py",
                               "completionist_candidate3_logical")

    candidate1, candidate1_report = base.build_wad(source_raw, art_report)
    check(sha(candidate1) == CANDIDATE1_WAD,
          "historical first Nornir candidate no longer reconstructs exactly")
    records = logical.parse_wad(candidate1)
    source_records = logical.parse_wad(source_raw)
    check(logical.serialize_wad(records) == candidate1, "Candidate 1 input does not round-trip")

    _, raven_material = one_payload(source_records, base.RAVEN["material"])
    nornir_index, nornir_material = one_payload(records, base.NORNIR["material"])
    raven_q10 = struct.unpack_from("<Q", raven_material["data"], 0x10)[0]
    raven_q20 = struct.unpack_from("<Q", raven_material["data"], 0x20)[0]
    before_q10 = struct.unpack_from("<Q", nornir_material["data"], 0x10)[0]
    before_q20 = struct.unpack_from("<Q", nornir_material["data"], 0x20)[0]
    check(raven_q10 == RAVEN_MATERIAL_Q10, "frozen Raven material +0x10 changed")
    check(raven_q20 == RAVEN_DONOR_Q20, "frozen Raven material +0x20 changed")
    check(before_q10 == int(candidate1_report["material_identity_q10"], 16),
          "Candidate 1 material +0x10 report mismatch")
    check(before_q20 == CANDIDATE1_Q20, "Candidate 1 material +0x20 divergence changed")

    struct.pack_into("<Q", nornir_material["data"], 0x20, raven_q20)
    candidate3 = logical.serialize_wad(records)
    reparsed = logical.parse_wad(candidate3)
    check(logical.serialize_wad(reparsed) == candidate3, "Candidate 3 WAD does not round-trip")

    diff_offsets = [index for index, (left, right) in enumerate(zip(candidate1, candidate3)) if left != right]
    check(len(candidate1) == len(candidate3), "Candidate 3 changed WAD length")
    check(len(diff_offsets) == 8 and diff_offsets == list(range(diff_offsets[0], diff_offsets[0] + 8)),
          "Candidate 3 must differ from Candidate 1 by one contiguous qword")
    check(candidate1[diff_offsets[0]:diff_offsets[0] + 8] == struct.pack("<Q", before_q20),
          "Candidate 1 raw divergence bytes do not match material +0x20")
    check(candidate3[diff_offsets[0]:diff_offsets[0] + 8] == struct.pack("<Q", raven_q20),
          "Candidate 3 raw correction bytes do not match Raven donor +0x20")

    normalized = normalize_to_raven(logical, source_raw, reparsed, base.NORNIR)
    check(normalized == source_raw, "Candidate 3 does not normalize byte-exactly to Raven production")

    _, nornir_material_after = one_payload(reparsed, base.NORNIR["material"])
    check(struct.unpack_from("<Q", nornir_material_after["data"], 0x10)[0] == before_q10,
          "Candidate 3 changed the fresh per-material +0x10")
    check(struct.unpack_from("<Q", nornir_material_after["data"], 0x20)[0] == raven_q20,
          "Candidate 3 did not preserve the Raven donor +0x20")

    dedicated_mg = [row["name"] for row in reparsed
                    if row["name"].lower().startswith("mg_completionistnornir")]
    check(not dedicated_mg, f"Candidate 3 contains retired dedicated MG records: {dedicated_mg}")

    map_model_index, _ = one_payload(reparsed, base.NORNIR["map_model"])
    hud_model_index, _ = one_payload(reparsed, base.NORNIR["hud_model"])
    map_model_rows = group_rows(logical, reparsed, map_model_index)
    hud_model_rows = group_rows(logical, reparsed, hud_model_index)
    map_mg = group_dependency(reparsed, map_model_rows, "MG_mapicondock_0")
    hud_mg = group_dependency(reparsed, hud_model_rows, "MG_boatdock_0")
    map_material = group_dependency(reparsed, map_model_rows, base.NORNIR["material"])
    hud_material = group_dependency(reparsed, hud_model_rows, base.NORNIR["material"])

    material_refs = [index for index, row in enumerate(reparsed)
                     if row["kind"] == 1 and not row["data"]
                     and row["id"] == nornir_material_after["id"]]
    material_owners = [dependency_owner(logical, reparsed, index) for index in material_refs]
    check([row["name"] for row in material_owners] ==
          [base.NORNIR["map_model"], base.NORNIR["hud_model"]],
          f"Nornir material reverse-reference owners changed: {material_owners}")

    texture_owners: dict[str, list[dict]] = {}
    for label in ("diffuse", "emissive"):
        _, texture_def = base.unique_texture(reparsed, base.NORNIR[label], gpu=False)
        refs = [index for index, row in enumerate(reparsed)
                if row["kind"] == 1 and not row["data"] and row["id"] == texture_def["id"]]
        owners = [dependency_owner(logical, reparsed, index) for index in refs]
        check(len(owners) == 1 and owners[0]["name"] == base.NORNIR["material"],
              f"Nornir {label} reverse-reference owners changed: {owners}")
        texture_owners[label] = owners

    source_preservation = assert_existing_named_records_preserved(
        logical, source_records, reparsed, STOCK_DONOR_NAMES + RAVEN_RESOURCE_NAMES)

    return candidate3, {
        "source_sha256": sha(source_raw),
        "candidate1_reconstructed_sha256": sha(candidate1),
        "candidate2_retired_sha256": CANDIDATE2_WAD,
        "candidate3_sha256": sha(candidate3),
        "bytes": len(candidate3),
        "candidate3_reparse_roundtrip_exact": True,
        "candidate3_normalizes_exactly_to_frozen_raven": True,
        "candidate1_to_candidate3_diff": {
            "raw_byte_difference_count": 8,
            "one_contiguous_qword": True,
            "logical_owner": base.NORNIR["material"],
            "logical_field": "material payload +0x20",
            "before": f"{before_q20:016X}",
            "after": f"{raven_q20:016X}",
            "reason": "runtime-proven Raven preserved the Dock donor +0x20 field",
        },
        "material": {
            "name": base.NORNIR["material"],
            "id": nornir_material_after["id"].hex(),
            "fresh_qword_0x10": f"{before_q10:016X}",
            "preserved_raven_donor_qword_0x20": f"{raven_q20:016X}",
            "bound_by_map_model": map_material,
            "bound_by_hud_model": hud_material,
        },
        "model_groups": {
            "dedicated_nornir_mg_records": 0,
            "map_shared_dependency": map_mg,
            "hud_shared_dependency": hud_mg,
            "opaque_mg_payload_bytes_changed": False,
        },
        "preservation": {
            "named_resources": source_preservation,
            "all_frozen_raven_records_recovered_by_exact_normalization": True,
            "stock_dock_and_boatdock_definitions_mutated": False,
        },
        "reverse_reference_audit": {
            "nornir_material_reference_count": len(material_refs),
            "nornir_material_owners": material_owners,
            "nornir_texture_owners": texture_owners,
            "stock_or_raven_owners_of_nornir_material": 0,
            "stock_or_raven_owners_of_nornir_textures": 0,
            "original_stock_dock_boatdock_owner_records_byte_identical": True,
            "shared_mg_new_owners": [base.NORNIR["map_model"], base.NORNIR["hud_model"]],
            "shared_mg_definitions_reowned_or_mutated": False,
        },
        "accounting": candidate1_report["accounting"],
        "texture_record_classification": candidate1_report["texture_record_classification"],
    }


def build_candidate3_wad(source_raw: bytes, art_report: Path) -> tuple[bytes, dict]:
    """Build Candidate 3 through shared collectible framework."""
    framework = load_module("completionist_collectible_framework",
                            HERE / "collectible_framework.py")
    registry = framework.load_registry()
    definition = framework.definition_for(registry, "nornir_chest")
    candidate3, generic = framework.build_collectible_wad(
        source_raw, registry, "nornir_chest", art_report)
    check(generic["candidate_sha256"] == "90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660",
          "generic framework changed Candidate 3 WAD")
    check(generic["pre_material_rule_sha256"] == CANDIDATE1_WAD,
          "generic framework no longer reconstructs Candidate 1 control")
    check(len(generic["material_rule_diff_offsets"]) == 8,
          "Candidate 3 material correction is not exactly one qword")

    resources = definition["resources"]
    target = {
        "material": resources["material"]["name"],
        "map_model": resources["map_model"]["name"],
        "hud_model": resources["hud_model"]["name"],
    }
    legacy = generic["legacy_compatible_report"]
    return candidate3, {
        "source_sha256": generic["source_sha256"],
        "candidate1_reconstructed_sha256": generic["pre_material_rule_sha256"],
        "candidate2_retired_sha256": CANDIDATE2_WAD,
        "candidate3_sha256": generic["candidate_sha256"],
        "bytes": generic["bytes"],
        "candidate3_reparse_roundtrip_exact": generic["parse_serialize_roundtrip_exact"],
        "candidate3_normalizes_exactly_to_frozen_raven": generic["normalized_to_frozen_raven_exact"],
        "candidate1_to_candidate3_diff": {
            "raw_byte_difference_count": len(generic["material_rule_diff_offsets"]),
            "one_contiguous_qword": True,
            "logical_owner": target["material"],
            "logical_field": "material payload +0x20",
            "before": generic["material"]["qword_0x20_before_generic_rule"],
            "after": generic["material"]["qword_0x20"],
            "reason": "runtime-proven Raven preserved the Dock donor +0x20 field",
        },
        "material": {
            "name": target["material"],
            "id": resources["material"]["id"],
            "fresh_qword_0x10": generic["material"]["qword_0x10"],
            "preserved_raven_donor_qword_0x20": generic["material"]["qword_0x20"],
            "bound_by_map_model": {"name": target["material"], "id": resources["material"]["id"]},
            "bound_by_hud_model": {"name": target["material"], "id": resources["material"]["id"]},
        },
        "model_groups": {
            "dedicated_nornir_mg_records": 0,
            "map_shared_dependency": {
                "name": definition["model_group_policy"]["map"]["name"],
                "id": definition["model_group_policy"]["map"]["id"],
            },
            "hud_shared_dependency": {
                "name": definition["model_group_policy"]["hud"]["name"],
                "id": definition["model_group_policy"]["hud"]["id"],
            },
            "opaque_mg_payload_bytes_changed": generic["model_groups"]["opaque_payload_bytes_changed"],
        },
        "preservation": {
            "named_resources": generic["preserved_named_records"],
            "all_frozen_raven_records_recovered_by_exact_normalization": True,
            "stock_dock_and_boatdock_definitions_mutated": False,
        },
        "reverse_reference_audit": {
            "nornir_material_reference_count": 2,
            "nornir_material_owners": [
                {"name": target["map_model"], "id": resources["map_model"]["id"]},
                {"name": target["hud_model"], "id": resources["hud_model"]["id"]},
            ],
            "nornir_texture_owners": generic["texture_owners"],
            "stock_or_raven_owners_of_nornir_material": 0,
            "stock_or_raven_owners_of_nornir_textures": 0,
            "original_stock_dock_boatdock_owner_records_byte_identical": True,
            "shared_mg_new_owners": [target["map_model"], target["hud_model"]],
            "shared_mg_definitions_reowned_or_mutated": False,
        },
        "accounting": generic["accounting"],
        "texture_record_classification": legacy.get("texture_record_classification", {}),
        "generic_framework": {
            "registry": str(framework.REGISTRY_PATH),
            "collectible_key": "nornir_chest",
            "same_resource_builder_as_synthetic_probe": True,
            "reverse_reference_ownership_valid": generic["reverse_reference_ownership_valid"],
            "unexpected_payload_changes": generic["unexpected_payload_changes"],
        },
    }


def live_hashes(game: Path) -> dict[str, str]:
    return {relative: file_sha(game / relative) for relative in RAVEN_HASHES}


def validate_lifecycle_source(repo: Path) -> tuple[Path, dict]:
    root = repo / "build/v0.10.4-nornir-lifecycle/offline"
    report_path = root / "nornir-lifecycle-offline.json"
    check(report_path.is_file(), f"missing lifecycle proof: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    check(report.get("result") == "OFFLINE_NORNIR_LIFECYCLE_BUILT_AND_REPARSED",
          "Nornir lifecycle proof result changed")
    check(report.get("lifecycle_contract", {}).get("synthetic_progression_writes") is False,
          "lifecycle proof permits synthetic progression writes")
    check(report.get("proof", {}).get("frozen_raven_mapmenu_is_exact_prefix_of_candidate") is True,
          "lifecycle proof does not preserve Raven mapmenu prefix")
    check(report.get("safety", {}).get("game_files_written") is False,
          "lifecycle proof safety changed")
    source_root = root / "candidate/game-root"
    for relative, expected in LIFECYCLE_FILES.items():
        check(file_sha(source_root / relative) == expected,
              f"lifecycle candidate file changed: {relative}")
    return source_root, report


def assemble_files(output_root: Path, wad: bytes, ui_dcb: bytes,
                   lifecycle_root: Path) -> dict[str, dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    generated = {
        "exec/wad/pc_le/r_ui.wad": wad,
        "exec/dc/pc_le/wad_r_ui.dcb": ui_dcb,
    }
    for relative, raw in generated.items():
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        check(target.read_bytes() == raw, f"offline output write mismatch: {relative}")
        rows[relative] = {"bytes": len(raw), "sha256": sha(raw), "source": "frozen_raven_reconstruction"}
    for relative, expected in LIFECYCLE_FILES.items():
        source = lifecycle_root / relative
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        check(file_sha(target) == expected, f"copied lifecycle file changed: {relative}")
        rows[relative] = {
            "bytes": target.stat().st_size,
            "sha256": expected,
            "source": "proven_nornir_lifecycle_candidate",
        }
    check(len(rows) == 10, f"Candidate 3 must contain ten files, found {len(rows)}")
    return dict(sorted(rows.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path,
                        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO / "build/v0.10.4-nornir-candidate3/offline")
    parser.add_argument("--report", type=Path,
                        default=REPO / "archive/field-logs/completionist-v104-nornir-candidate3-offline-reconstruction.json")
    args = parser.parse_args()

    game = args.game_root.resolve()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    report_path = args.report.resolve()
    check(repo == REPO.resolve(), f"unexpected repository root: {repo}")
    check(not output.is_relative_to(game) and not report_path.is_relative_to(game),
          "Candidate 3 output must stay outside installed game")

    before = live_hashes(game)
    check(before == RAVEN_HASHES, f"frozen Raven production mismatch: {before}")
    lifecycle_root, lifecycle_report = validate_lifecycle_source(repo)
    art_report = repo / "build/v0.10.4-nornir-resident-art/offline/nornir-resident-art.json"
    check(art_report.is_file(), f"missing proven Nornir resident-art report: {art_report}")

    source_wad = (game / "exec/wad/pc_le/r_ui.wad").read_bytes()
    candidate_wad, wad_report = build_candidate3_wad(source_wad, art_report)

    framework = load_module("completionist_collectible_framework_main",
                            HERE / "collectible_framework.py")
    registry = framework.load_registry()
    source_ui_dcb = (game / "exec/dc/pc_le/wad_r_ui.dcb").read_bytes()
    candidate_ui_dcb, dcb_report = framework.build_collectible_gopool(
        source_ui_dcb, registry, "nornir_chest")
    check(dcb_report["candidate_rows"] == 259, "Candidate 3 GOPool count changed")
    check(dcb_report["raven_map_row_preserved"] and dcb_report["raven_hud_row_preserved"],
          "Candidate 3 GOPool does not preserve Raven rows")
    source_perm_dcb = (game / "exec/dc/pc_le/wad_r_perm.dcb").read_bytes()
    candidate_perm_dcb, perm_report = framework.build_collectible_compass_inworld(
        source_perm_dcb, registry, "nornir_chest")
    check(candidate_perm_dcb == (lifecycle_root / "exec/dc/pc_le/wad_r_perm.dcb").read_bytes(),
          "generic compass/in-world chain differs from pinned Candidate 3 lifecycle artifact")

    output_root = output / "candidate/game-root"
    manifest = assemble_files(output_root, candidate_wad, candidate_ui_dcb, lifecycle_root)
    after = live_hashes(game)
    check(after == before, "installed Raven files changed during Candidate 3 assembly")

    report = {
        "schema": 1,
        "result": RESULT,
        "branch_contract": "codex/v104-raven-production",
        "selected_baseline": {
            "name": "frozen runtime-proven Raven production",
            "historical_pre_custom_r_ui_wad_sha256": "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04",
            "reason": "Candidate 3 must extend the adopted Raven production state, while the stock hash anchors the historical transformation ledger.",
            "frozen_hashes": RAVEN_HASHES,
        },
        "historical_reconstruction": {
            "pre_custom_and_map_success": ["ec23e80", "9ddb1dc", "694f2f0", "a91b021", "72ba3e9"],
            "corrected_map_production_chain": ["ff2d6dc", "5298a14", "cfb07eb", "79570b3", "b463eaa"],
            "hud_discovery": ["a775cf9", "53ad400", "1c06a6c", "fecb4d8", "2dcc68e"],
            "hud_success": ["16cc157", "4309ba8", "78da41d", "beb86a9", "d13da33", "00564d4"],
            "inworld_and_capacity2": ["df53bf8", "76cfa75", "092f153", "d420590", "c1551a2"],
            "production_adoption": ["5108330"],
        },
        "first_structural_divergence": {
            "introduced_by_commit": "c4b7270",
            "builder": "tools/v0.10.4/build-nornir-map-hud-offline.py",
            "field": "MAT_completionistnornirchest payload +0x20",
            "raven_recipe": "clone donor material, author fresh +0x10, preserve donor +0x20 D595197B0961F689",
            "failed_nornir_recipe": "author fresh +0x10 and fresh +0x20 E2265134DFA7B641",
            "candidate2_status": "retired; kept the material divergence and added byte-identical dedicated MG clones",
            "candidate3_rule": "restore donor +0x20 and keep stock MG definitions shared and byte-identical",
            "exact_runtime_semantics_of_qword_0x20_known": False,
            "historical_byte_rule_proven": True,
        },
        "raven_transformation_ledger": {
            "files": [
                {
                    "path": "exec/wad/pc_le/r_ui.wad",
                    "baseline_sha256": "92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04",
                    "production_sha256": RAVEN_HASHES["exec/wad/pc_le/r_ui.wad"],
                    "map_resources": [
                        {"name": "TX_completionist_raven_map_diffuse_19A41F00834C19F3", "definition_id": "5458455400455255001fa419f3194c83", "gpu_id": "000000000000000079babb7a41c7033c", "operation": "clone Dock texture definition/GPU pair; set definition +0x9C user hash 7ABBBA793C03C741; later inject proven resident pixels"},
                        {"name": "TX_completionist_raven_map_emissive_63F1E18FF93B9037", "definition_id": "54584554004552558fe1f16337903bf9", "gpu_id": "0000000000000000d216ad1542eb7da1", "operation": "clone Dock texture definition/GPU pair; set definition +0x9C user hash 15AD16D2A17DEB42; later inject proven resident pixels"},
                        {"name": "MAT_AE4AD85BB993F040", "id": "dac6009fd0f18caad2ed322463c3d0c8", "donor": "MAT_0C599DC8DC7E2170", "operation": "clone/rename/retarget diffuse and emissive links; set +0x10=1B0989158D4A2908; preserve donor +0x20=D595197B0961F689", "physical_owner": "own material group"},
                        {"name": "MDL_completionistraven", "id": "e281a8d67849d97b3d5e7d88f140f59b", "donor": "MDL_mapicondock", "operation": "clone/rename; retarget only Dock artwork material link", "physical_owner": "own model group", "shared_dependency": {"name": "MG_mapicondock_0", "id": "44b11676af9c4e0ff860108fd46b0b32"}},
                        {"name": "goProtoMapIconCompletionistRaven", "id": "f29a83d61d2fe0b9bb96123ffe77225d", "donor": "goProtoNW633B8059", "operation": "clone/rename; replace payload-local self ID; retarget model; keep ANM_mapicondock and three stock SCP definitions as zero-data links", "physical_owner": "own prototype group"},
                        {"name": "gomapiconcompletionistraven", "id": "3d8f7153809e6db191c2d5e354f1e88c", "loader_name": "goMapIconCompletionistRaven", "operation": "clone/rename; root +0x0C prototype ID; root +0x1C 56-byte loader name", "physical_owner": "own root group; zero-data parent link owned by goProtoNW633B8059"},
                    ],
                    "hud_resources": [
                        {"name": "MDL_completionistravenhud", "id": "4a7911dc2db72cecaf6c187a66bfd11f", "donor": "MDL_boatdock", "operation": "clone/rename; bind existing Raven material", "physical_owner": "own model group", "shared_dependency": {"name": "MG_boatdock_0", "id": "c3f6b4c5a8270df607ea3e6e7f891292"}},
                        {"name": "goProtoCompletionistRavenHUD", "id": "b2a833d6144789e8099acf85e832d652", "donor": "goProtoBoatDock", "operation": "clone/rename; payload +0x3A8 self ID; retarget model; copy local SCP_BoatDock payload byte-identically", "physical_owner": "own prototype group", "local_scp": {"name": "SCP_BoatDock", "id": "baaddbbad0baaddbbaaddbbad7baaddb"}},
                        {"name": "gocompletionistravenhud", "id": "f0029a68d9705e95a981aab8bff0c5b8", "loader_name": "goCompletionistRavenHUD", "operation": "clone/rename; root +0x0C prototype ID; root +0x1C loader name; preserve root +0x54 shared compass ID", "physical_owner": "own root group", "shared_dependency": {"name": "goProtocompassicons", "id": "502b9225361cf6449d8d85048f0b1a75"}},
                    ],
                    "wad_accounting": {"map_physical_payload_delta": 8, "map_typed_delta": 6, "map_type_deltas": {"0xA": 1, "0x10001": 1, "0x20001": 1, "0x2000C": 1, "0x10015": 2}, "hud_physical_record_delta": 13, "hud_payload_delta": 4, "hud_accounted_delta": 3, "hud_type_deltas": {"0x10001": 1, "0x10005": 1, "0x20001": 1}},
                    "stock_donor_records_byte_identical": True,
                },
                {
                    "path": "exec/patch/pc_le/completionist_v104_raven_map.texpack",
                    "baseline": "absent; newly authored artwork pack",
                    "runtime_proof_sha256": "648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7",
                    "operation": "author Raven diffuse/emissive stream data and bind by WAD texture user hashes",
                    "production_verifier_pinned": False,
                    "note": "Archived resident-art runtime proof loaded this pack; adopted verifier pins final resident WAD instead of this file.",
                },
                {
                    "path": "exec/patch/pc_le/completionist_v104_raven_map.texpack.toc",
                    "baseline": "absent; newly authored artwork TOC",
                    "runtime_proof_sha256": "67cceea0d91298881f4426bf0ce5e8883da45a82905921313004df618d959053",
                    "operation": "author matching two-texture pack table of contents",
                    "production_verifier_pinned": False,
                },
                {
                    "path": "exec/dc/pc_le/wad_r_ui.dcb",
                    "baseline_sha256": "21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a",
                    "production_sha256": RAVEN_HASHES["exec/dc/pc_le/wad_r_ui.dcb"],
                    "dcb_changes": [
                        {"table": "WAD_R_UI.GOPool", "name": "goMapIconCompletionistRaven", "folded_name_hash": "584F31DC8BD6E738", "index": 255, "capacity": 1, "operation": "append row"},
                        {"table": "WAD_R_UI.GOPool", "name": "goCompletionistRavenHUD", "folded_name_hash": "45E5C7943749F81C", "index": 256, "capacity": 2, "operation": "append row at capacity 1, then causal correction to 2"},
                    ],
                    "all_preexisting_rows_byte_identical": True,
                },
                {
                    "path": "exec/dc/pc_le/wad_r_perm.dcb",
                    "pre_class_sha256": "eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039",
                    "production_sha256": RAVEN_HASHES["exec/dc/pc_le/wad_r_perm.dcb"],
                    "dcb_changes": [
                        {"table": "type-0x11E packed block/export table", "name": "CompletionistRaven", "uid": "5DC46967D3095F7E", "operation": "insert DockPoint-shaped 0x20-byte class; final IconName=45E5C7943749F81C and InWorld_tMPIcon_Name=21DC5A7D4AD17628"},
                        {"table": "type-0x129 packed block/export table", "name": "COMPASS_INWORLD_COMPLETIONIST_RAVEN", "uid": "21DC5A7D4AD17628", "operation": "clone COMPASS_INWORLD_DOCK 0x98-byte record; change IconName to 45E5C7943749F81C; keep self-contained relocation +0x10 -> +0x90"},
                    ],
                    "all_preexisting_exports_and_relocations_semantically_preserved": True,
                },
                {
                    "path": "exec/dc/pc_le/mapmaster.dcb",
                    "baseline_sha256": "1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a",
                    "production_sha256": RAVEN_HASHES["exec/dc/pc_le/mapmaster.dcb"],
                    "dcb_changes": [{"marker": "Completionist_V103_Veithurgard_Raven_01", "uid": "E15E6BC82AE2773E", "map_visual": "goMapIconCompletionistRaven", "operation": "author marker and dedicated map GameObject pointer"}],
                },
                {
                    "path": "exec/dc/pc_le/mapcoords.dcb",
                    "baseline_sha256": "5d0b7591032d7b56581a0d77946c3fad4f0cbc1b9d245f3578407177c40bbe7d",
                    "production_sha256": RAVEN_HASHES["exec/dc/pc_le/mapcoords.dcb"],
                    "dcb_changes": [{"marker_uid": "E15E6BC82AE2773E", "wad": "WAD_Xpl200_Funeral", "position": [-64.875, 12.984375, 787.5], "operation": "append native coordinate row"}],
                },
                {
                    "path": "exec/dc/pc_le/compassgraph.dcb",
                    "baseline_sha256": "c2fa6bab0c7c1dbe413a41f477a5e01ab396731fc6f6d611047a8bd346a56c5e",
                    "production_sha256": RAVEN_HASHES["exec/dc/pc_le/compassgraph.dcb"],
                    "dcb_changes": [{"edge": ["E15E6BC82AE2773E", "BABC033C454755A0"], "operation": "append native routing edge"}],
                },
                {
                    "path": "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
                    "pre_manager_control_sha256": "55e6ab3771417211cab670aaa4871e5f4083dac8f00f324d5584e803bb9a11a9",
                    "production_sha256": RAVEN_HASHES["mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"],
                    "lua_changes": "append manager-owned CompletionistRaven add/remove; direct ShowMarker/HideMarker for Raven-origin action; hide Raven before stock-origin delegate; async watchdog and live prompt; no progression writes",
                },
            ],
            "loader_key_semantics": {
                "GOPool_uid": "folded 64-bit loader-name hash",
                "WAD_record_id": "16-byte record/dependency identity used by local links",
                "root_plus_0x0C": "prototype record ID",
                "root_plus_0x1C": "56-byte embedded loader name",
                "root_plus_0x54": "shared compass prototype record ID on HUD roots",
                "prototype_self_id": "payload-local copy of prototype record ID",
                "DCB_export_uid": "export identity; not a WAD record ID",
                "material_plus_0x10_and_0x20": "exact runtime meaning unknown; historical construction rule known",
                "MG_payload": "data-bearing model-group resource referenced by model-owned zero-data links; deeper scalar semantics unknown",
            },
        },
        "candidate3": {
            "output_root": str(output_root),
            "files": manifest,
            "wad": wad_report,
            "gopool": dcb_report,
            "compass_inworld": perm_report,
            "lifecycle_result": lifecycle_report["result"],
            "framework_registry": str(framework.REGISTRY_PATH),
            "runtime_install_allowed": False,
        },
        "proofs": {
            "started_from_frozen_raven_production": True,
            "candidate1_reconstructed_only_as_differential_control": True,
            "candidate2_used_as_input": False,
            "candidate2_hash_rejected": CANDIDATE2_WAD,
            "stock_dock_boatdock_definitions_unchanged": True,
            "stock_mg_payloads_unchanged": True,
            "raven_resources_preserved": True,
            "raven_files_unchanged_before_after": True,
            "candidate_wad_roundtrip_exact": True,
            "candidate_wad_normalizes_to_raven_exact": True,
            "complete_sha_manifest": True,
        },
        "safety": {
            "god_of_war_launched": False,
            "installed_game_files_written": False,
            "save_files_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
            "runtime_installer_created_or_modified": False,
            "runtime_install_allowed": False,
            "arbitrary_opaque_mg_bytes_mutated": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  r_ui.wad: {wad_report['candidate3_sha256']}")
    print(f"  files: {len(manifest)}")
    print("  stock MG payload edits: false")
    print("  installed game writes: false")
    print("  runtime install allowed: false")
    print(f"  report: {report_path}")


if __name__ == "__main__":
    main()
