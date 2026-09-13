"""Build canonical all-Raven catalogue and audit from native game data."""
from __future__ import annotations

import argparse
from pathlib import Path

from raven_catalogue import build_catalogue, canonical_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, default=Path("G:/SteamLibrary/steamapps/common/GodOfWar"))
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    catalogue, audit = build_catalogue(args.game_root)
    args.catalogue.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.catalogue.write_text(canonical_json(catalogue), encoding="utf-8", newline="\n")
    args.audit.write_text(canonical_json(audit), encoding="utf-8", newline="\n")
    print(f"catalogue={args.catalogue} entries={len(catalogue['ravens'])}")
    print(f"audit={args.audit} ready_for_runtime_test={audit['ready_for_runtime_test']}")


if __name__ == "__main__":
    main()
