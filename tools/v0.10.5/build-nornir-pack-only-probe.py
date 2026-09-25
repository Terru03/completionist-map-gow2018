#!/usr/bin/env python3
"""Stage the chest texture pack alone over the Raven-safe v4 installation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ART = ROOT / "build/nornir-one-family-art-probe"
OUT = ROOT / "build/nornir-pack-only-probe/candidate/game-root"
REPORT = ROOT / "build/nornir-pack-only-probe/report.json"
BOOT = "exec/boot-options.json"
PACK = "completionist_v105_nornir_chest"
FILES = (BOOT, "exec/patch/pc_le/" + PACK + ".texpack",
         "exec/patch/pc_le/" + PACK + ".texpack.toc")
OLD_BOOT_SHA256 = "8bbac2bb2a522dfacf69c676e48665686f722289a44127518ae4e8ca299a0e92"


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build() -> tuple[dict[str, bytes], dict]:
    art = json.loads((ART / "report.json").read_text(encoding="utf-8"))
    need(art["kind"] == "NORNIR_CHEST_ONLY_MAP_ART_PROBE" and
         set(FILES) <= set(art["files"]), "chest pack source report differs")
    source = ROOT / "build/nornir-native-material-key-isolated-test/source-game-root"
    old_raw = (source / BOOT).read_bytes()
    need(sha(old_raw) == OLD_BOOT_SHA256, "Raven boot options changed")
    old = json.loads(old_raw)
    outputs = {name: (ART / "candidate/game-root" / name).read_bytes()
               for name in FILES}
    for name, raw in outputs.items():
        need(sha(raw) == art["files"][name]["sha256"],
             "chest pack artifact changed: " + name)
    new = json.loads(outputs[BOOT])
    added = "../../patch/pc_le/" + PACK
    need(new["patch-texpacks"] == old["patch-texpacks"] + [added],
         "chest pack registration differs")
    new["patch-texpacks"].pop()
    need(new == old, "boot options changed beyond chest pack registration")
    report = {
        "schema": 1,
        "kind": "NORNIR_CHEST_PACK_ONLY_PROBE",
        "status": "OFFLINE_BUILT_NOT_INSTALLED",
        "prior_operation_kind": "NORNIR_STOCK_SAVED_STATE_RESTORED_SEALS_OVERLAY_TEST",
        "files": {name: {"before": OLD_BOOT_SHA256 if name == BOOT else None,
                         "after": sha(outputs[name]), "bytes": len(outputs[name])}
                  for name in FILES},
        "unchanged_wad_sha256": "5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60",
        "live_question": "Does chest pack registration alone alter Raven artwork?",
    }
    return outputs, report


def main() -> None:
    outputs, report = build()
    for name, raw in outputs.items():
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("NORNIR_CHEST_PACK_ONLY_PROBE_OFFLINE_BUILT")
    print(REPORT)


if __name__ == "__main__":
    main()
