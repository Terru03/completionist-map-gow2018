#!/usr/bin/env python3
"""Export exact fetched branch files for a reproducible offline inventory run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--seed-branch", default="codex/collectible-ship-heads")
    args = ap.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    specs = [
        ("seed_catalogue", None, args.seed_branch, "config/collectibles/v0.10.5/all-collectibles.json", "seed-all-collectibles.json"),
        ("family_catalogue", "odin_raven", "codex/all-ravens-release-candidate", "catalogue/odins-ravens.json", "ravens-catalogue.json"),
        ("family_audit", "odin_raven", "codex/all-ravens-release-candidate", "archive/all-ravens/native-raven-catalogue-audit.json", "ravens-native-audit.json"),
        ("family_catalogue", "nornir_chest", "codex/collectible-nornir-chests", "config/collectibles/v0.10.5/all-collectibles.json", "nornir-all-collectibles.json"),
        ("family_gate", "nornir_chest", "codex/collectible-nornir-chests", "docs/research/nornir-static-gate.json", "nornir-static-gate.json"),
        ("family_catalogue", "legendary_chest", "codex/collectible-legendary-chests", "config/collectibles/v0.10.5/all-collectibles.json", "legendary-all-collectibles.json"),
        ("family_gate", "legendary_chest", "codex/collectible-legendary-chests", "docs/research/legendary-static-gate.json", "legendary-static-gate.json"),
        ("family_catalogue", "artefact", "codex/collectible-artefacts", "config/collectibles/v0.10.5/all-collectibles.json", "artefact-all-collectibles.json"),
        ("family_gate", "artefact", "codex/collectible-artefacts", "docs/research/artefact-static-gate.json", "artefact-static-gate.json"),
        ("family_catalogue", "lore_marker", "codex/collectible-lore-markers", "config/collectibles/v0.10.5/all-collectibles.json", "lore-all-collectibles.json"),
        ("family_gate", "lore_marker", "codex/collectible-lore-markers", "docs/research/lore-static-gate.json", "lore-static-gate.json"),
    ]
    sources = []
    for role, family, branch, source_path, name in specs:
        commit = git("rev-parse", f"origin/{branch}").decode().strip()
        if len(commit) != 40:
            raise ValueError(f"unresolved branch: {branch}")
        contents = git("show", f"{commit}:{source_path}")
        path = out / name
        path.write_bytes(contents)
        sources.append({"role": role, "family": family, "source_branch": branch,
                        "source_commit": commit, "source_path": source_path,
                        "sha256": hashlib.sha256(contents).hexdigest(), "file": name})
    (out / "source-manifest.json").write_text(json.dumps({"schema": 1, "sources": sources}, indent=2) + "\n", encoding="utf-8")
    (out / "source-branches.txt").write_text("".join(
        f"{e['role']} {e['family'] or '-'} {e['source_branch']}@{e['source_commit']} {e['source_path']} SHA-256={e['sha256']}\n"
        for e in sources), encoding="utf-8")
    print(f"EXPORTED_PINNED_SOURCES count={len(sources)} manifest={out / 'source-manifest.json'}")


if __name__ == "__main__":
    main()
