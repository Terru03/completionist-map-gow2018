#!/usr/bin/env python3
"""Assemble Nornir runtime candidate #2 entirely offline.

Candidate #2 is the already-proven ten-file Nornir lifecycle candidate with one
and only one substitution: r_ui.wad is replaced by the dedicated-model-group
isolated WAD that passed the post-isolation reverse-reference audit.

No God of War file is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

RESULT = "OFFLINE_NORNIR_RUNTIME_CANDIDATE2_ASSEMBLED"
EXPECTED_LIFECYCLE_WAD = "340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c"
EXPECTED_ISOLATED_WAD = "96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef"
EXPECTED_AUDIT_RESULT = "NORNIR_MG_ISOLATED_CANDIDATE_AUDIT_READ_ONLY"

FILES = {
    "r_ui.wad": "exec/wad/pc_le/r_ui.wad",
    "wad_r_ui.dcb": "exec/dc/pc_le/wad_r_ui.dcb",
    "wad_r_perm.dcb": "exec/dc/pc_le/wad_r_perm.dcb",
    "mapmaster.dcb": "exec/dc/pc_le/mapmaster.dcb",
    "mapcoords.dcb": "exec/dc/pc_le/mapcoords.dcb",
    "compassgraph.dcb": "exec/dc/pc_le/compassgraph.dcb",
    "mapmenu.lua": "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
    "mainhud.lua": "mods/lua/gameart/ui/scripts/hud/mainhud.lua",
    "interact_chest_runic.lua": "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua",
    "interact_chest_standard.lua": "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua",
}


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lifecycle-root", type=Path, required=True)
    ap.add_argument("--isolated-wad", type=Path, required=True)
    ap.add_argument("--audit-report", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    lifecycle = args.lifecycle_root.resolve()
    isolated = args.isolated_wad.resolve()
    audit_path = args.audit_report.resolve()
    output = args.output_root.resolve()

    for path in (lifecycle, isolated, audit_path):
        check(path.exists(), f"missing input: {path}")

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    check(audit.get("result") == EXPECTED_AUDIT_RESULT, "isolated MG audit result changed")
    proofs = audit.get("proofs", {})
    required = [
        "isolated_candidate_reparse_roundtrip_exact",
        "original_stock_mg_payloads_preserved",
        "dedicated_mg_payloads_match_stock_donors",
        "nornir_models_use_dedicated_mg_only",
        "raven_models_use_stock_mg_only",
        "dedicated_mg_reverse_refs_exactly_intended_nornir_models",
        "raven_model_groups_unchanged",
        "nornir_material_refs_do_not_leak",
        "nornir_texture_refs_do_not_leak",
        "shared_stock_model_group_isolation_gap_closed",
        "safe_to_assemble_runtime_candidate_2",
    ]
    check(all(proofs.get(k) is True for k in required), "isolated MG audit did not clear candidate #2 assembly")
    check(audit.get("sha256", {}).get("isolated_candidate") == EXPECTED_ISOLATED_WAD,
          "archived audit isolated WAD SHA changed")
    check(sha(isolated) == EXPECTED_ISOLATED_WAD, "isolated WAD bytes changed")

    lifecycle_wad = lifecycle / FILES["r_ui.wad"]
    check(lifecycle_wad.is_file(), f"lifecycle r_ui.wad missing: {lifecycle_wad}")
    check(sha(lifecycle_wad) == EXPECTED_LIFECYCLE_WAD, "lifecycle candidate WAD changed")

    check(not output.exists(), f"output root already exists: {output}")
    output.mkdir(parents=True)

    entries = {}
    changed = []
    for name, rel in FILES.items():
        src = lifecycle / rel
        check(src.is_file(), f"lifecycle candidate file missing: {name}: {src}")
        dst = output / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if name == "r_ui.wad":
            shutil.copy2(isolated, dst)
            source_kind = "isolated_nornir_mg_wad"
        else:
            shutil.copy2(src, dst)
            source_kind = "unchanged_lifecycle_candidate"
        src_sha = sha(src)
        dst_sha = sha(dst)
        if name == "r_ui.wad":
            check(dst_sha == EXPECTED_ISOLATED_WAD, "candidate #2 r_ui.wad SHA mismatch")
            check(src_sha == EXPECTED_LIFECYCLE_WAD, "candidate #2 source lifecycle WAD SHA mismatch")
            check(dst_sha != src_sha, "candidate #2 did not replace the failed WAD")
            changed.append(name)
        else:
            check(dst_sha == src_sha, f"candidate #2 unexpectedly changed {name}")
        entries[name] = {
            "relative": rel.replace("/", "\\"),
            "source_kind": source_kind,
            "lifecycle_sha256": src_sha,
            "candidate2_sha256": dst_sha,
            "byte_identical_to_lifecycle_candidate": dst_sha == src_sha,
        }

    check(changed == ["r_ui.wad"], f"candidate #2 changed unexpected files: {changed}")

    report = {
        "schema": 1,
        "result": RESULT,
        "candidate_root": str(output),
        "files": entries,
        "proofs": {
            "exactly_ten_files_present": len(entries) == 10,
            "only_r_ui_wad_differs_from_lifecycle_candidate": True,
            "r_ui_wad_is_exact_isolated_mg_candidate": True,
            "all_other_nine_files_byte_identical_to_lifecycle_candidate": True,
            "isolated_mg_audit_cleared_runtime_candidate_2_assembly": True,
            "candidate2_ready_for_transactional_installer_gate": True,
        },
        "safety": {
            "game_files_written": False,
            "runtime_install_performed": False,
            "save_state_written": False,
            "progression_state_written": False,
            "marker_state_written": False,
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(RESULT)
    print(f"  lifecycle failed WAD: {EXPECTED_LIFECYCLE_WAD}")
    print(f"  isolated WAD:         {EXPECTED_ISOLATED_WAD}")
    print("  only changed file vs lifecycle candidate: r_ui.wad")
    print("  other nine files byte-identical to lifecycle candidate: true")
    print("  isolated MG audit cleared candidate #2 assembly: true")
    print("  game files written: false")
    print("  runtime install performed: false")
    print(f"  candidate root: {output}")
    print(f"  report: {args.report}")


if __name__ == "__main__":
    main()
