"""Corrected resident Raven artwork patch wrapper.

The first resident-artwork proof assumed the stock Valkyrie map textures were
148x148 because their resident GPU payload sizes match Dock exactly. Field data
from root.texpack shows the Valkyrie pair is actually 156x156, still with eight
mips. That does not invalidate the control: GOWTool power-of-two pads the
swizzled mip surfaces, and the resulting byte offsets/sizes for mip 2 onward are
identical to the 148x148 Dock/Raven textures.

This wrapper keeps every static gate from patch-raven-resident-artwork.py, but
allows only the exact, now-observed 156x156/8-mip Valkyrie metadata exception.
The base patcher then still has to prove that Dock, Valkyrie and Raven share the
same padded mip byte layout and that both stock resident payloads equal their
actual GNF mip-2+ tails byte-for-byte before any output WAD is produced.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "patch-raven-resident-artwork.py"


def load_base():
    spec = importlib.util.spec_from_file_location("completionist_resident_artwork_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {BASE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", type=Path, required=True)
    ap.add_argument("--root-texpack", type=Path, required=True)
    ap.add_argument("--raven-texpack", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    base = load_base()
    original_check = base.check

    allowed = {
        "diffuse: Valkyrie GNF metadata changed: 156x156 mips=8",
        "emissive: Valkyrie GNF metadata changed: 156x156 mips=8",
    }

    def corrected_check(ok: bool, message: str) -> None:
        if ok:
            return
        if message in allowed:
            return
        original_check(False, message)

    base.check = corrected_check

    wad_raw = args.wad.read_bytes()
    out, report = base.patch(wad_raw, args.root_texpack, args.raven_texpack)

    # Make the corrected dimension assumption explicit in the persisted report.
    report["valkyrie_dimension_gate_corrected"] = True
    report["valkyrie_expected_dimensions"] = "156x156, 8 mips"
    report["why_layout_still_valid"] = (
        "Although stock Valkyrie is 156x156 and Dock/Raven are 148x148, the base patcher independently proved identical padded swizzled mip offsets/sizes and exact stock resident-payload == GNF mip2+ byte relations before applying Raven data."
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    import json
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
