"""Build a class-only Raven native compass A/B from the proven route re-proof.

Input must be the exact installed v0.10.4 route re-proof mapmenu. The patch changes
only the markerType line inside the appended native Raven production bridge:
DockPoint -> CompletionistRaven. It never writes game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "d101bb60807ad95919e42d92e3155ea9e7bda9c713bc1cad646b932d6f7c928d"
BEGIN = b"-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE"
END = b"-- END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE"
SOURCE = b"  local markerType = consts.COMPASS_MARKER_TYPE_DOCK_POINT"
TARGET = b'  local markerType = "CompletionistRaven"'
SHOW = b"game.Compass.ShowMarker(candidate, markerType)"
RESULT = "OFFLINE_RAVEN_NATIVE_CUSTOM_CLASS_CONTROL_BUILT"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build(raw: bytes) -> tuple[bytes, dict]:
    source_sha = sha256(raw)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            f"mapmenu.lua is not the proven route re-proof baseline: expected {EXPECTED_SOURCE_SHA256}, got {source_sha}"
        )
    if raw.count(BEGIN) != 1 or raw.count(END) != 1:
        raise ValueError("expected exactly one native Raven production bridge")
    start = raw.index(BEGIN)
    end_marker = raw.index(END, start)
    end = end_marker + len(END)
    if end <= start:
        raise ValueError("native Raven production bridge bounds invalid")
    block = raw[start:end]
    if block.count(SOURCE) != 1:
        raise ValueError(f"expected exactly one DockPoint markerType in Raven bridge, found {block.count(SOURCE)}")
    if block.count(TARGET) != 0:
        raise ValueError("CompletionistRaven markerType is already active in Raven bridge")
    if block.count(SHOW) != 1:
        raise ValueError("expected exactly one dedicated Raven ShowMarker call in bridge")

    patched_block = block.replace(SOURCE, TARGET, 1)
    candidate = raw[:start] + patched_block + raw[end:]

    if candidate[:start] != raw[:start] or candidate[start + len(patched_block):] != raw[end:]:
        raise ValueError("bytes outside Raven production bridge changed")
    if patched_block.count(TARGET) != 1 or patched_block.count(SOURCE) != 0:
        raise ValueError("class-only markerType replacement did not resolve exactly")
    if patched_block.replace(TARGET, SOURCE, 1) != block:
        raise ValueError("reversing class-only replacement does not reconstruct bridge")
    if candidate.count(BEGIN) != 1 or candidate.count(END) != 1:
        raise ValueError("bridge markers changed during patch")
    if candidate.count(SHOW) < 1:
        raise ValueError("Raven ShowMarker call disappeared")

    return candidate, {
        "result": RESULT,
        "source_sha256": source_sha,
        "expected_source_sha256": EXPECTED_SOURCE_SHA256,
        "candidate_sha256": sha256(candidate),
        "source_bytes": len(raw),
        "candidate_bytes": len(candidate),
        "bridge_offset": start,
        "bridge_bytes_before": len(block),
        "bridge_bytes_after": len(patched_block),
        "marker_type_before": "DockPoint",
        "marker_type_after": "CompletionistRaven",
        "dedicated_showmarker_call_preserved": True,
        "native_marker_identity_unchanged": True,
        "native_coordinates_graph_unchanged": True,
        "bytes_outside_bridge_unchanged": True,
        "game_files_written": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    raw = source.read_bytes()
    candidate, report = build(raw)
    if output == source or report_path == source:
        raise ValueError("offline output/report must not overlap source")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report.update({"source": str(source), "output": str(output), "report": str(report_path)})
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if source.read_bytes() != raw:
        raise ValueError("source changed during offline build")
    print(RESULT)
    print("  markerType: DockPoint -> CompletionistRaven")
    print("  native marker ID / coords / graph unchanged: true")
    print("  game files written: false")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
