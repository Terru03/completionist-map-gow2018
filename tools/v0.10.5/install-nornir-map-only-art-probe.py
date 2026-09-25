#!/usr/bin/env python3
"""Use the existing six-file transaction for the map-only Nornir art probe."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transaction = load("map_only_transaction", "install-nornir-one-family-art-probe.py")
audit = load("map_only_audit", "verify-nornir-composed-package.py")
transaction.BUILD = transaction.ROOT / "build/nornir-map-only-art-probe"
transaction.REPORT = transaction.BUILD / "report.json"
transaction.BACKUPS = transaction.BUILD / "backups"
transaction.KIND = "NORNIR_MAP_ONLY_NO_HUD_ART_PROBE_OPERATION"
original_candidate = transaction.candidate


def candidate() -> dict:
    report = original_candidate()
    proof = report["proof"][transaction.WAD]
    transaction.base.need(report.get("variant") == "MAP_ONLY_NO_NORNIR_HUD" and
                          proof.get("nornir_hud_resources") == 0 and
                          proof.get("added_physical_payloads") == 8 and
                          proof.get("added_typed_payloads") == 6,
                          "map-only/no-HUD proof absent")
    raw = (transaction.BUILD / "candidate/game-root" / transaction.WAD).read_bytes()
    records = audit.logical.parse_wad(raw)
    transaction.base.need(not any("nornir" in r["name"].lower() and
                                  "hud" in r["name"].lower() for r in records),
                          "Nornir HUD resource remains in map-only artifact")
    transaction.base.need(audit.sha(raw) not in audit.KNOWN_FAILED_LIVE_WADS,
                          "candidate WAD already failed live artwork")
    return report


transaction.candidate = candidate


def install(prior: Path, pack_operation: Path | None = None) -> Path:
    transaction.base.game_stopped()
    candidate()
    if pack_operation:
        pack = load("map_only_pack_rollback", "install-nornir-pack-only-probe.py")
        pack.rollback(pack_operation)
    return transaction.install(prior)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify", "rollback"))
    parser.add_argument("--prior-operation", type=Path)
    parser.add_argument("--pack-operation", type=Path)
    parser.add_argument("--operation", type=Path)
    args = parser.parse_args()
    if args.action == "install":
        transaction.base.need(args.prior_operation is not None and args.operation is None,
                              "install needs --prior-operation")
        print(install(args.prior_operation, args.pack_operation))
    else:
        transaction.base.need(args.operation is not None and
                              args.prior_operation is None and args.pack_operation is None,
                              "verify/rollback needs --operation")
        getattr(transaction, args.action)(args.operation)
        print("NORNIR_MAP_ONLY_ART_" + args.action.upper() + "_OK")


if __name__ == "__main__":
    main()
