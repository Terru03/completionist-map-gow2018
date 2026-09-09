#!/usr/bin/env python3
"""Offline acceptance checks for Nornir Candidate 3."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPECTED_RESULT = "NORNIR_CANDIDATE3_OFFLINE_ASSEMBLED"
EXPECTED_WAD = "90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660"
EXPECTED_UI_DCB = "93164584bc115b64144bef73680ce5163b7ddf48f74bfd2698fef1b165dc891a"
EXPECTED_PERM = "be453733a57a27dde5eb33e553973ec34c330e4841f7c632e4f784a8adc34350"
RAVEN_WAD = "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60"
RAVEN_UI_DCB = "765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d"
NORNIR_Q10 = 0xE2265134DFA7BA70
DONOR_Q20 = 0xD595197B0961F689


def check(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def sha(path: Path) -> str:
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


def group_members(logical, records: list[dict], payload_index: int) -> list[dict]:
    start = records[payload_index]["parent"]
    check(start is not None and records[start]["kind"] == 2,
          f"missing owner group for {records[payload_index]['name']}")
    end = logical.matching_group_end(records, start)
    return records[start:end + 1]


def exact_dependency(rows: list[dict], name: str) -> dict:
    hits = [row for row in rows if row["kind"] == 1 and not row["data"]
            and row["name"].lower() == name.lower()]
    check(len(hits) == 1, f"expected one dependency {name!r}, found {len(hits)}")
    return hits[0]


def dependency_owner(logical, records: list[dict], index: int) -> str:
    start = records[index]["parent"]
    check(start is not None and records[start]["kind"] == 2,
          f"dependency has no owner group: {records[index]['name']}")
    end = logical.matching_group_end(records, start)
    payloads = [records[row_index] for row_index in range(start + 1, end)
                if records[row_index]["kind"] == 1 and records[row_index]["data"]]
    check(payloads, f"dependency owner has no payload: {records[index]['name']}")
    return payloads[0]["name"]


def verify_wad(repo: Path, game: Path, root: Path, report: dict) -> None:
    logical = load_module("candidate3_test_logical", HERE / "build-raven-ui-logical-clone.py")
    builder = load_module("candidate3_test_builder", HERE / "build-nornir-candidate3-offline.py")
    source_path = game / "exec/wad/pc_le/r_ui.wad"
    candidate_path = root / "exec/wad/pc_le/r_ui.wad"
    check(sha(source_path) == RAVEN_WAD, "live Raven WAD hash changed")
    check(sha(candidate_path) == EXPECTED_WAD, "Candidate 3 WAD hash changed")
    source_raw = source_path.read_bytes()
    candidate_raw = candidate_path.read_bytes()
    source = logical.parse_wad(source_raw)
    candidate = logical.parse_wad(candidate_raw)
    check(logical.serialize_wad(candidate) == candidate_raw, "Candidate 3 WAD round-trip differs")

    _, material = one_payload(candidate, "MAT_completionistnornirchest")
    check(struct.unpack_from("<Q", material["data"], 0x10)[0] == NORNIR_Q10,
          "Candidate 3 fresh material +0x10 changed")
    check(struct.unpack_from("<Q", material["data"], 0x20)[0] == DONOR_Q20,
          "Candidate 3 did not preserve Raven/Dock +0x20")

    dedicated_mg = [row["name"] for row in candidate
                    if row["name"].lower().startswith("mg_completionistnornir")]
    check(not dedicated_mg, f"retired dedicated MG records found: {dedicated_mg}")

    map_index, _ = one_payload(candidate, "MDL_completionistnornirchest")
    hud_index, _ = one_payload(candidate, "MDL_completionistnornirchesthud")
    map_rows = group_members(logical, candidate, map_index)
    hud_rows = group_members(logical, candidate, hud_index)
    exact_dependency(map_rows, "MAT_completionistnornirchest")
    exact_dependency(map_rows, "MG_mapicondock_0")
    exact_dependency(hud_rows, "MAT_completionistnornirchest")
    exact_dependency(hud_rows, "MG_boatdock_0")

    material_refs = [index for index, row in enumerate(candidate)
                     if row["kind"] == 1 and not row["data"] and row["id"] == material["id"]]
    material_owners = [dependency_owner(logical, candidate, index) for index in material_refs]
    check(material_owners == ["MDL_completionistnornirchest", "MDL_completionistnornirchesthud"],
          f"Nornir material leaked to stock/Raven owner: {material_owners}")
    v5 = load_module("candidate3_test_v5", HERE / "build-nornir-map-hud-offline-v5.py")
    for label in ("diffuse", "emissive"):
        _, definition = v5.base.unique_texture(candidate, v5.base.NORNIR[label], gpu=False)
        refs = [index for index, row in enumerate(candidate)
                if row["kind"] == 1 and not row["data"] and row["id"] == definition["id"]]
        owners = [dependency_owner(logical, candidate, index) for index in refs]
        check(owners == [v5.base.NORNIR["material"]],
              f"Nornir {label} leaked to stock/Raven owner: {owners}")

    for name in builder.STOCK_DONOR_NAMES + builder.RAVEN_RESOURCE_NAMES:
        before = [logical.record_bytes(row) for row in source if row["name"].lower() == name.lower()]
        after = [logical.record_bytes(row) for row in candidate if row["name"].lower() == name.lower()]
        check(before, f"source proof resource missing: {name}")
        for record in before:
            check(record in after, f"source proof record changed: {name}")

    normalized = builder.normalize_to_raven(logical, source_raw, candidate, v5.base.NORNIR)
    check(normalized == source_raw, "Candidate 3 normalization does not recover frozen Raven WAD")

    wad_report = report["candidate3"]["wad"]
    check(wad_report["candidate1_to_candidate3_diff"]["raw_byte_difference_count"] == 8,
          "Candidate 3 correction is not one qword")
    check(wad_report["model_groups"]["opaque_mg_payload_bytes_changed"] is False,
          "Candidate 3 report permits opaque MG edits")


def dcb_rows(data: bytes) -> tuple[int, list[bytes], int]:
    count = struct.unpack_from("<I", data, 8)[0]
    base = 0x90
    end = base + count * 16
    check(end <= len(data), "GOPool exceeds DCB data chunk")
    return count, [data[base + index * 16:base + (index + 1) * 16] for index in range(count)], end


def verify_ui_dcb(game: Path, root: Path) -> None:
    verifier = load_module("candidate3_test_raven_verify", HERE / "verify-raven-production-state.py")
    source_path = game / "exec/dc/pc_le/wad_r_ui.dcb"
    candidate_path = root / "exec/dc/pc_le/wad_r_ui.dcb"
    check(sha(source_path) == RAVEN_UI_DCB, "live Raven UI DCB hash changed")
    check(sha(candidate_path) == EXPECTED_UI_DCB, "Candidate 3 UI DCB hash changed")
    source_raw = source_path.read_bytes()
    candidate_raw = candidate_path.read_bytes()
    source_chunk = verifier.one(verifier.parse_chunks(source_raw), 12)
    candidate_chunk = verifier.one(verifier.parse_chunks(candidate_raw), 12)
    source_data = source_raw[source_chunk["start"]:source_chunk["end"]]
    candidate_data = candidate_raw[candidate_chunk["start"]:candidate_chunk["end"]]
    source_count, source_rows, source_end = dcb_rows(source_data)
    candidate_count, candidate_rows, candidate_end = dcb_rows(candidate_data)
    check(source_count == 257 and candidate_count == 259, "GOPool count is not 257 -> 259")
    check(candidate_rows[:257] == source_rows, "an existing GOPool row changed")
    map_uid, map_capacity = struct.unpack_from("<QH", candidate_rows[257])
    hud_uid, hud_capacity = struct.unpack_from("<QH", candidate_rows[258])
    check((map_uid, map_capacity) == (0xE14C66C3B90633E0, 1), "Nornir map GOPool row changed")
    check((hud_uid, hud_capacity) == (0x7DDC11175EBD1E94, 2), "Nornir HUD GOPool row changed")
    check(candidate_data[candidate_end:] == source_data[source_end:], "GOPool tail changed instead of shifting")


def verify_perm(root: Path) -> None:
    verifier = load_module("candidate3_test_perm_verify", HERE / "verify-raven-production-state.py")
    path = root / "exec/dc/pc_le/wad_r_perm.dcb"
    check(sha(path) == EXPECTED_PERM, "Candidate 3 perm DCB hash changed")
    raw = path.read_bytes()
    chunks = verifier.parse_chunks(raw)
    data_chunk = verifier.one(chunks, 12)
    export_chunk = verifier.one(chunks, 13)
    data = raw[data_chunk["start"]:data_chunk["end"]]
    exports = verifier.parse_exports(raw[export_chunk["start"]:export_chunk["end"]])
    by_name = {row["name"]: row for row in exports}
    nornir_class = by_name["CompletionistNornirChest"]
    nornir_inworld = by_name["COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST"]
    check((nornir_class["uid"], nornir_class["type_id"]) == (0x8D5A770E0C4272CE, 0x11E),
          "Nornir compass class identity changed")
    icon, _, inworld_uid = struct.unpack_from("<QQQ", data, nornir_class["root"])
    check((icon, inworld_uid) == (0x7DDC11175EBD1E94, 0x32BBE7E267644D93),
          "Nornir compass class visual/carrier binding changed")
    check((nornir_inworld["uid"], nornir_inworld["type_id"]) == (0x32BBE7E267644D93, 0x129),
          "Nornir in-world carrier identity changed")
    check(struct.unpack_from("<Q", data, nornir_inworld["root"])[0] == 0x7DDC11175EBD1E94,
          "Nornir in-world carrier visual changed")
    check("CompletionistRaven" in by_name and "COMPASS_INWORLD_COMPLETIONIST_RAVEN" in by_name,
          "frozen Raven perm exports missing")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--game-root", type=Path,
                        default=Path(r"G:\SteamLibrary\steamapps\common\GodOfWar"))
    parser.add_argument("--candidate-root", type=Path,
                        default=REPO / "build/v0.10.4-nornir-candidate3/offline/candidate/game-root")
    parser.add_argument("--report", type=Path,
                        default=REPO / "archive/field-logs/completionist-v104-nornir-candidate3-offline-reconstruction.json")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    game = args.game_root.resolve()
    root = args.candidate_root.resolve()
    report_path = args.report.resolve()
    check(repo == REPO.resolve(), f"unexpected repo root: {repo}")
    check(not root.is_relative_to(game) and not report_path.is_relative_to(game),
          "test inputs must stay outside installed game except read-only baseline")

    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    check(report.get("result") == EXPECTED_RESULT, "Candidate 3 report result changed")
    check(report.get("candidate3", {}).get("runtime_install_allowed") is False,
          "Candidate 3 report permits runtime install")
    safety = report.get("safety", {})
    for key in ("god_of_war_launched", "installed_game_files_written", "save_files_written",
                "progression_state_written", "marker_state_written",
                "runtime_installer_created_or_modified", "arbitrary_opaque_mg_bytes_mutated"):
        check(safety.get(key) is False, f"unsafe Candidate 3 report flag: {key}")
    check(safety.get("runtime_install_allowed") is False, "runtime install safety flag changed")

    files = report["candidate3"]["files"]
    check(len(files) == 10, "Candidate 3 manifest is not ten files")
    for relative, facts in files.items():
        path = root / relative
        check(sha(path) == facts["sha256"], f"manifest hash mismatch: {relative}")
        check(path.stat().st_size == facts["bytes"], f"manifest byte count mismatch: {relative}")

    verify_wad(repo, game, root, report)
    verify_ui_dcb(game, root)
    verify_perm(root)
    print("NORNIR_CANDIDATE3_OFFLINE_TESTS_PASSED")
    print("  ten-file manifest: exact")
    print("  WAD round-trip and Raven normalization: exact")
    print("  stock Dock/BoatDock and Raven records: preserved")
    print("  model groups: shared, no dedicated Nornir MG payload")
    print("  runtime install allowed: false")


if __name__ == "__main__":
    main()
