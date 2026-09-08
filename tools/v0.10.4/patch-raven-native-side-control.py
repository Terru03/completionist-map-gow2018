"""Build a byte-preserving mapmenu.lua control that uses stock SIDE for the Raven.

This is a diagnostic only. It changes exactly the CompassIconClass name used by
the existing Raven native bridge from CompletionistRaven to SIDE. The output
has the same byte length as the input and is never written to the game by this
script.

Bridge detection deliberately uses the runtime contract rather than a historical
BEGIN comment. Later v0.10.4 installers preserve the same Raven candidate and
markerType call path but may use a different wrapper/comment banner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE = b'local markerType = "CompletionistRaven"'
SHORT_TARGET = b'local markerType = "SIDE"'
TARGET = SHORT_TARGET + (b" " * (len(SOURCE) - len(SHORT_TARGET)))
CANDIDATE_ASSIGNMENT = b'local candidate = "Completionist_V103_Veithurgard_Raven_01"'
CANDIDATE = b'Completionist_V103_Veithurgard_Raven_01'
SHOW_CALL = b'game.Compass.ShowMarker(candidate, markerType)'
RESULT = "OFFLINE_RAVEN_NATIVE_SIDE_CONTROL_BUILT"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build(raw: bytes) -> tuple[bytes, dict]:
    source_count = raw.count(SOURCE)
    candidate_assignment_count = raw.count(CANDIDATE_ASSIGNMENT)
    show_call_count = raw.count(SHOW_CALL)

    if source_count != 1:
        raise ValueError(
            f"expected exactly one CompletionistRaven markerType assignment, found {source_count}"
        )
    if candidate_assignment_count != 1:
        raise ValueError(
            "expected exactly one installed Raven native candidate assignment, "
            f"found {candidate_assignment_count}"
        )
    if show_call_count != 1:
        raise ValueError(
            f"expected exactly one Raven ShowMarker(candidate, markerType) call, found {show_call_count}"
        )
    if raw.count(TARGET) != 0:
        raise ValueError("SIDE control already appears to be applied")

    offset = raw.index(SOURCE)
    candidate_offset = raw.index(CANDIDATE_ASSIGNMENT)
    show_offset = raw.index(SHOW_CALL)

    # The three anchors must belong to one local Raven bridge. This prevents a
    # generic markerType assignment elsewhere in mapmenu.lua from being patched.
    if not candidate_offset < offset < show_offset:
        raise ValueError(
            "Raven bridge anchors are out of order; refusing to patch an ambiguous mapmenu"
        )
    if offset - candidate_offset > 2048:
        raise ValueError("Raven candidate and markerType anchors are unexpectedly far apart")
    if show_offset - offset > 16384:
        raise ValueError("Raven markerType and ShowMarker anchors are unexpectedly far apart")
    if raw.count(CANDIDATE) < 1:
        raise ValueError("Raven candidate identity missing")

    candidate = raw[:offset] + TARGET + raw[offset + len(SOURCE):]
    if len(candidate) != len(raw):
        raise ValueError("control patch changed mapmenu byte length")

    changed = [i for i, (a, b) in enumerate(zip(raw, candidate)) if a != b]
    if not changed:
        raise ValueError("control patch produced no changes")
    expected_span = set(range(offset, offset + len(SOURCE)))
    if any(i not in expected_span for i in changed):
        raise ValueError("control patch changed bytes outside markerType assignment")
    if candidate.count(TARGET) != 1 or candidate.count(SOURCE) != 0:
        raise ValueError("SIDE control substitution did not resolve exactly once")
    if candidate.count(CANDIDATE_ASSIGNMENT) != 1 or candidate.count(SHOW_CALL) != 1:
        raise ValueError("SIDE control altered Raven bridge identity/call anchors")

    return candidate, {
        "result": RESULT,
        "source_sha256": sha256(raw),
        "candidate_sha256": sha256(candidate),
        "bytes": len(raw),
        "byte_length_unchanged": True,
        "changed_byte_count": len(changed),
        "changed_span": [offset, offset + len(SOURCE)],
        "only_marker_type_assignment_changed": True,
        "bridge_detection": {
            "method": "unique_raven_candidate_markerType_show_call_contract",
            "candidate_assignment_count": candidate_assignment_count,
            "marker_type_assignment_count": source_count,
            "show_call_count": show_call_count,
            "candidate_assignment_offset": candidate_offset,
            "marker_type_assignment_offset": offset,
            "show_call_offset": show_offset,
            "historical_begin_comment_required": False,
        },
        "marker_name": "Completionist_V103_Veithurgard_Raven_01",
        "marker_type_before": "CompletionistRaven",
        "marker_type_after": "SIDE",
        "native_marker_coordinates_graph_unchanged": True,
        "raven_wad_artwork_unchanged": True,
        "wad_r_perm_dcb_unchanged": True,
        "game_files_written": False,
        "purpose": (
            "A/B control: if stock SIDE restores routed/native compass behavior for the exact same "
            "Raven marker ID, coordinates and graph, the remaining defect is CompassIconClass behavior. "
            "If not, investigate native graph/marker registration instead."
        ),
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
        raise ValueError("offline control output/report must not overlap source")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    report["source"] = str(source)
    report["output"] = str(output)
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if source.read_bytes() != raw:
        raise ValueError("source mapmenu changed during offline build")

    print(RESULT)
    print("  bridge detection: unique Raven candidate + markerType + ShowMarker call")
    print("  markerType: CompletionistRaven -> SIDE")
    print("  same marker ID / coords / graph: true")
    print("  output length unchanged: true")
    print("  game files written: false")
    print(f"  candidate: {output}")
    print(f"  report:    {report_path}")


if __name__ == "__main__":
    main()
